"""
Ampel-Check-in 🟢🟡🔴
Ablauf:
  1. Trigger: Ihr seid beide im Call (einmal pro Tag) ODER /checkin ODER 21-Uhr-Fallback.
  2. Beide bekommen per DM drei Farb-Buttons. Nach Klick: optionales Modal
     (Stichwort fürs Reveal + private Notiz, die NIE gezeigt wird).
  3. Erst wenn BEIDE geantwortet haben: gleichzeitiger Reveal in #check-in.
     -> Keiner kann sich an der Antwort des anderen orientieren.
  4. Gelb -> Thema wandert automatisch in den #briefkasten.
     Rot  -> sanfter Hinweis auf Gespräch / Pause-Karte.
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.design import emb, AMPEL_EMOJI, progress_bar

FARBEN = {
    "gruen": ("🟢", "Alles gut", discord.ButtonStyle.success),
    "gelb": ("🟡", "Da ist was Kleines", discord.ButtonStyle.secondary),
    "rot": ("🔴", "Ich brauch ein Gespräch", discord.ButtonStyle.danger),
}


def today() -> str:
    return dt.datetime.now(config.TZ).strftime("%Y-%m-%d")


class CheckinModal(discord.ui.Modal):
    thema = discord.ui.TextInput(
        label="Stichwort (wird beim Reveal gezeigt)",
        placeholder="z.B. 'Zeit füreinander' – oder leer lassen",
        required=False, max_length=80)
    notiz = discord.ui.TextInput(
        label="Private Notiz (niemand sieht sie)",
        style=discord.TextStyle.paragraph, required=False, max_length=500)

    def __init__(self, cog: "Checkin", farbe: str):
        super().__init__(title=f"Check-in {AMPEL_EMOJI[farbe]}")
        self.cog = cog
        self.farbe = farbe

    async def on_submit(self, itx: discord.Interaction):
        await self.cog.save_checkin(itx, self.farbe,
                                    str(self.thema) or None, str(self.notiz) or None)


class ColorView(discord.ui.View):
    def __init__(self, cog: "Checkin"):
        super().__init__(timeout=None)
        for key, (emoji, label, style) in FARBEN.items():
            self.add_item(self._make_button(cog, key, emoji, label, style))

    @staticmethod
    def _make_button(cog, key, emoji, label, style):
        btn = discord.ui.Button(emoji=emoji, label=label, style=style,
                                custom_id=f"checkin:{key}")
        async def cb(itx: discord.Interaction):
            await itx.response.send_modal(CheckinModal(cog, key))
        btn.callback = cb
        return btn


class Checkin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_fallback.start()

    def cog_unload(self):
        self.daily_fallback.cancel()

    # ---------- Trigger 1: beide im Call ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not config.is_couple(member.id) or after.channel is None:
            return
        ids_im_call = {m.id for m in after.channel.members}
        if {config.MELI_ID, config.JUSTI_ID} <= ids_im_call:
            await self.start_checkin(force=False)

    # ---------- Trigger 2: Fallback am Abend ----------
    @tasks.loop(time=dt.time(hour=config.CHECKIN_HOUR, tzinfo=config.TZ))
    async def daily_fallback(self):
        await self.start_checkin(force=False)

    @daily_fallback.before_loop
    async def before_fallback(self):
        await self.bot.wait_until_ready()

    # ---------- Trigger 3: manuell ----------
    @app_commands.command(name="checkin", description="Startet den heutigen Ampel-Check-in.")
    async def manual(self, itx: discord.Interaction):
        started = await self.start_checkin(force=True)
        msg = ("📬 Check-in verschickt – schaut in eure DMs!"
               if started else "Ihr habt heute schon beide eingecheckt. 💚")
        await itx.response.send_message(msg, ephemeral=True)

    # ---------- Kernlogik ----------
    async def start_checkin(self, force: bool) -> bool:
        if not force:
            sent = await self.bot.db.get_setting("checkin_prompted")
            if sent == today():
                return False
        sent_any = False
        for uid in (config.MELI_ID, config.JUSTI_ID):
            done = await self.bot.db.fetchone(
                "SELECT 1 FROM checkins WHERE user_id = ? AND datum = ?", uid, today())
            if done:
                continue
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            e = emb("checkin", "🚦 Zeit für euren Check-in!",
                    "Wie war dein Beziehungs-Tag?\n\n"
                    "🟢 alles gut · 🟡 Kleinigkeit (kein Alarm – Wartung!) · "
                    "🔴 Gesprächsbedarf\n\n"
                    "*Gezeigt wird eure Farbe erst, wenn ihr **beide** geantwortet "
                    "habt – gleichzeitig.*")
            try:
                await user.send(embed=e, view=ColorView(self))
                sent_any = True
            except discord.Forbidden:
                ch = self.bot.channel_by_name("check-in")
                if ch:
                    await ch.send(f"⚠️ Ich kann {config.name_of(uid)} keine DM schicken "
                                  "(DMs für den Bot freigeben!).")
        if sent_any:
            await self.bot.db.set_setting("checkin_prompted", today())
        return sent_any

    async def save_checkin(self, itx: discord.Interaction, farbe: str,
                           thema: str | None, notiz: str | None):
        uid = itx.user.id
        exists = await self.bot.db.fetchone(
            "SELECT 1 FROM checkins WHERE user_id = ? AND datum = ?", uid, today())
        if exists:
            await itx.response.send_message("Du hast heute schon eingecheckt. 💛",
                                            ephemeral=True)
            return
        await self.bot.db.execute(
            "INSERT INTO checkins (user_id, datum, farbe, thema, notiz) VALUES (?,?,?,?,?)",
            uid, today(), farbe, thema, notiz)
        if farbe == "gelb" and thema:
            await self.bot.db.execute(
                "INSERT INTO briefkasten (user_id, thema) VALUES (?, ?)", uid, thema)
        await self.bot.feed_melusti(uid, "checkin", None)
        await itx.response.send_message(
            f"{AMPEL_EMOJI[farbe]} Gespeichert! Reveal kommt, sobald "
            f"{config.name_of(config.partner_of(uid))} auch eingecheckt hat.",
            ephemeral=False)
        await self.try_reveal()

    async def try_reveal(self):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM checkins WHERE datum = ?", today())
        if len(rows) < 2:
            return
        if await self.bot.db.get_setting("checkin_revealed") == today():
            return
        await self.bot.db.set_setting("checkin_revealed", today())

        ch = self.bot.channel_by_name("check-in")
        if not ch:
            return

        by_user = {r["user_id"]: r for r in rows}
        worst = "rot" if any(r["farbe"] == "rot" for r in rows) else (
            "gelb" if any(r["farbe"] == "gelb" for r in rows) else "gruen")

        e = emb(worst, f"🚦 Check-in Reveal – {dt.datetime.now(config.TZ):%d.%m.%Y}")
        for uid in (config.MELI_ID, config.JUSTI_ID):
            r = by_user.get(uid)
            val = f"{AMPEL_EMOJI[r['farbe']]} " + (f"„{r['thema']}“" if r["thema"] else "")
            e.add_field(name=config.name_of(uid), value=val or "–", inline=True)

        streak = await self.calc_streak()
        e.add_field(name="Streak", value=f"🔥 **{streak}** Tage in Folge eingecheckt",
                    inline=False)

        if worst == "rot":
            e.add_field(
                name="🔴 Gesprächsbedarf",
                value="Nehmt euch heute bewusst Zeit – im Call, nicht im Chat.\n"
                      "Oder zieht die **Pause-Karte**: 30–60 Min Auszeit *mit* "
                      "angesagter Rückkehrzeit.",
                inline=False)
        elif worst == "gelb":
            e.add_field(
                name="🟡 Ab in den Briefkasten",
                value="Kein Alarm – das Thema ist notiert und kommt beim "
                      "Wochen-Check-in auf den Tisch. `/briefkasten` zeigt alles Offene.",
                inline=False)
        await ch.send(embed=e)

    async def calc_streak(self) -> int:
        streak, d = 0, dt.datetime.now(config.TZ).date()
        while True:
            rows = await self.bot.db.fetchall(
                "SELECT COUNT(DISTINCT user_id) AS n FROM checkins WHERE datum = ?",
                d.strftime("%Y-%m-%d"))
            if rows and rows[0]["n"] == 2:
                streak += 1
                d -= dt.timedelta(days=1)
            else:
                break
        return streak

    # ---------- Briefkasten & Verlauf ----------
    @app_commands.command(name="briefkasten", description="Zeigt offene gelbe Themen.")
    async def briefkasten(self, itx: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM briefkasten WHERE erledigt = 0 ORDER BY erstellt")
        if not rows:
            await itx.response.send_message(
                embed=emb("gruen", "📮 Briefkasten leer!", "Nichts Offenes."))
            return
        lines = [f"`#{r['id']}` **{r['thema']}** – von {config.name_of(r['user_id'])} "
                 f"({r['erstellt'][:10]})" for r in rows]
        e = emb("gelb", "📮 Offene Themen", "\n".join(lines) +
                "\n\n*Geklärt? → `/briefkasten_erledigt id`*")
        await itx.response.send_message(embed=e)

    @app_commands.command(name="briefkasten_erledigt",
                          description="Markiert ein Briefkasten-Thema als geklärt.")
    async def erledigt(self, itx: discord.Interaction, id: int):
        await self.bot.db.execute(
            "UPDATE briefkasten SET erledigt = 1, erledigt_am = datetime('now') WHERE id = ?",
            id)
        await self.bot.feed_melusti(itx.user.id, "streit_geklaert", 15)
        await itx.response.send_message(
            embed=emb("gruen", "✅ Geklärt!", f"Thema `#{id}` abgehakt – Melusti freut sich, "
                      "geklärte Themen sind sein Lieblingsessen. 🌱"))

    @app_commands.command(name="checkin_verlauf",
                          description="Eure Ampel-Historie der letzten 14 Tage.")
    async def verlauf(self, itx: discord.Interaction):
        e = emb("checkin", "📈 Check-in-Verlauf (14 Tage)")
        for uid in (config.MELI_ID, config.JUSTI_ID):
            cells = []
            for i in range(13, -1, -1):
                d = (dt.datetime.now(config.TZ).date() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
                row = await self.bot.db.fetchone(
                    "SELECT farbe FROM checkins WHERE user_id = ? AND datum = ?", uid, d)
                cells.append(AMPEL_EMOJI[row["farbe"]] if row else "▫️")
            e.add_field(name=config.name_of(uid), value="".join(cells), inline=False)
        gruene = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS n FROM checkins WHERE farbe = 'gruen'")
        alle = await self.bot.db.fetchone("SELECT COUNT(*) AS n FROM checkins")
        if alle["n"]:
            e.add_field(name="Grün-Quote insgesamt",
                        value=f"{progress_bar(gruene['n'], alle['n'])} "
                              f"`{round(gruene['n']/alle['n']*100)}%`", inline=False)
        await itx.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Checkin(bot))
