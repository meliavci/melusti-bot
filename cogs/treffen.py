"""
Treffen & Termine 📌
- /termin_add: Zeitraum (von-bis) eintragen, Ersteller gilt automatisch als
  bestätigt, Status "planung" bis auch der Partner bestätigt hat ("safe").
- /termin_bestaetigen (+ Button direkt unter der Ankündigung).
- Täglicher Countdown-Post zum nächsten Termin.
- Kalender-Integration läuft über cogs/meilensteine.py (liest dieselbe
  treffen-Tabelle); nach jeder Änderung wird dessen Kalender mit-aktualisiert.
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import tracked
from utils.design import emb

TERMINE_KEY = "termine_liste"
COUNTDOWN_KEY = "countdown"


class BestaetigenView(discord.ui.View):
    def __init__(self, cog: "Treffen", termin_id: int):
        super().__init__(timeout=86400)
        self.cog = cog
        self.termin_id = termin_id

    @discord.ui.button(label="Ich bin dabei", style=discord.ButtonStyle.success, emoji="✅")
    async def bestaetigen(self, itx: discord.Interaction, _button: discord.ui.Button):
        await self.cog.bestaetige(itx, self.termin_id)


class Treffen(commands.Cog):
    termin_group = app_commands.Group(name="termin", description="Termine & Treffen verwalten.")

    def __init__(self, bot):
        self.bot = bot
        self.countdown_post.start()

    def cog_unload(self):
        self.countdown_post.cancel()

    async def _refresh_meilensteine(self):
        cog = self.bot.get_cog("Meilensteine")
        if cog:
            await cog.refresh_all_views()

    # ---------- Autocomplete ----------
    async def _termin_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall(
            "SELECT id, aktivitaet, datum, datum_bis FROM treffen ORDER BY datum")
        out = []
        for r in rows:
            von = dt.date.fromisoformat(r["datum"])
            zeitraum = f"{von:%d.%m.%Y}"
            if r["datum_bis"]:
                zeitraum += f"–{dt.date.fromisoformat(r['datum_bis']):%d.%m.%Y}"
            label = f"{r['aktivitaet']} ({zeitraum})"
            if current.lower() in label.lower():
                out.append(app_commands.Choice(name=label[:100], value=r["id"]))
        return out[:25]

    # ---------- Hinzufügen, ändern, löschen ----------
    @termin_group.command(name="add",
                          description="Trägt einen Termin oder Zeitraum ein (Planung, bis beide bestätigen).")
    @app_commands.describe(name="z.B. 'Urlaub in Kroatien'", von="Start-Datum TT.MM.JJJJ",
                           bis="End-Datum TT.MM.JJJJ (optional, für mehrtägige Termine)",
                           ort="Optional: wo?", emoji="Optional: ein Emoji dafür")
    async def termin_add(self, itx: discord.Interaction, name: str, von: str,
                         bis: str | None = None, ort: str | None = None,
                         emoji: str = "📌"):
        try:
            von_d = dt.datetime.strptime(von, "%d.%m.%Y").date()
        except ValueError:
            await itx.response.send_message("⚠️ Start-Datum bitte als `TT.MM.JJJJ`.",
                                            ephemeral=True)
            return
        bis_d = None
        if bis:
            try:
                bis_d = dt.datetime.strptime(bis, "%d.%m.%Y").date()
            except ValueError:
                await itx.response.send_message("⚠️ End-Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
            if bis_d < von_d:
                await itx.response.send_message(
                    "⚠️ Das End-Datum liegt vor dem Start-Datum.", ephemeral=True)
                return
        tid = await self.bot.db.execute(
            "INSERT INTO treffen (datum, datum_bis, ort, aktivitaet, emoji, erstellt_von, "
            "bestaetigt_von, status) VALUES (?,?,?,?,?,?,?,'planung')",
            von_d.isoformat(), bis_d.isoformat() if bis_d else None, ort, name, emoji,
            itx.user.id, str(itx.user.id))
        await self._refresh_meilensteine()
        await self._sync_termine()
        await self._post_countdown()
        zeitraum = f"{von_d:%d.%m.%Y}" + (f" – {bis_d:%d.%m.%Y}" if bis_d else "")
        partner = config.name_of(config.partner_of(itx.user.id))
        beschreibung = (f"**{name}**\n{zeitraum}" + (f"\n{ort}" if ort else "") +
                        f"\n\nStatus: 📝 Planung – {partner}, bestätige mit dem Button oder "
                        "`/termin bestaetigen`!")
        await itx.response.send_message(
            embed=emb("info", f"{emoji} Termin vorgeschlagen", beschreibung),
            view=BestaetigenView(self, tid))

    async def bestaetige(self, itx: discord.Interaction, termin_id: int):
        row = await self.bot.db.fetchone("SELECT * FROM treffen WHERE id = ?", termin_id)
        if not row:
            await itx.response.send_message("⚠️ Diesen Termin gibt es nicht mehr.", ephemeral=True)
            return
        bestaetigt = set(filter(None, (row["bestaetigt_von"] or "").split(",")))
        bestaetigt.add(str(itx.user.id))
        beide = {str(config.MELI_ID), str(config.JUSTI_ID)} <= bestaetigt
        neuer_status = "safe" if beide else "planung"
        await self.bot.db.execute(
            "UPDATE treffen SET bestaetigt_von = ?, status = ? WHERE id = ?",
            ",".join(bestaetigt), neuer_status, termin_id)
        await self._refresh_meilensteine()
        await self._sync_termine()
        await self._post_countdown()
        if beide:
            ch = self.bot.channel_by_name("kalender-treffen")
            if ch:
                await ch.send(embed=emb("info", "Termin ist safe",
                                        f"**{row['aktivitaet']}** – beide haben bestätigt."))
        await itx.response.send_message("Teilnahme bestätigt.", ephemeral=True)

    @termin_group.command(name="bestaetigen",
                          description="Bestätigt deine Teilnahme an einem Termin.")
    @app_commands.describe(id="Termin auswählen (tippen zum Suchen)")
    @app_commands.autocomplete(id=_termin_autocomplete)
    async def termin_bestaetigen(self, itx: discord.Interaction, id: int):
        await self.bestaetige(itx, id)

    @termin_group.command(name="edit", description="Ändert einen bestehenden Termin.")
    @app_commands.describe(id="Termin auswählen (tippen zum Suchen)",
                           name="Neuer Name (optional)",
                           von="Neues Start-Datum TT.MM.JJJJ (optional)",
                           bis="Neues End-Datum TT.MM.JJJJ (optional, 'keins' zum Entfernen)",
                           ort="Neuer Ort (optional)", emoji="Neues Emoji (optional)")
    @app_commands.autocomplete(id=_termin_autocomplete)
    async def termin_edit(self, itx: discord.Interaction, id: int, name: str | None = None,
                          von: str | None = None, bis: str | None = None,
                          ort: str | None = None, emoji: str | None = None):
        row = await self.bot.db.fetchone("SELECT * FROM treffen WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Diesen Termin gibt es nicht mehr – "
                                            "bitte neu aus der Liste auswählen.", ephemeral=True)
            return
        if all(v is None for v in (name, von, bis, ort, emoji)):
            await itx.response.send_message(
                "⚠️ Gib mindestens ein Feld an (name/von/bis/ort/emoji).", ephemeral=True)
            return
        new_von = row["datum"]
        if von:
            try:
                new_von = dt.datetime.strptime(von, "%d.%m.%Y").date().isoformat()
            except ValueError:
                await itx.response.send_message("⚠️ Start-Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        new_bis = row["datum_bis"]
        if bis is not None:
            if bis.strip().lower() in ("keins", "keine", "-", "none"):
                new_bis = None
            else:
                try:
                    new_bis = dt.datetime.strptime(bis, "%d.%m.%Y").date().isoformat()
                except ValueError:
                    await itx.response.send_message("⚠️ End-Datum bitte als `TT.MM.JJJJ`.",
                                                    ephemeral=True)
                    return
        if new_bis and new_bis < new_von:
            await itx.response.send_message(
                "⚠️ Das End-Datum liegt vor dem Start-Datum.", ephemeral=True)
            return
        # Termin inhaltlich geändert -> Bestätigungen verfallen, beide müssen erneut bestätigen.
        await self.bot.db.execute(
            "UPDATE treffen SET datum = ?, datum_bis = ?, ort = ?, aktivitaet = ?, emoji = ?, "
            "bestaetigt_von = ?, status = 'planung' WHERE id = ?",
            new_von, new_bis, ort if ort is not None else row["ort"],
            name if name is not None else row["aktivitaet"],
            emoji if emoji is not None else row["emoji"], str(itx.user.id), id)
        await self._refresh_meilensteine()
        await self._sync_termine()
        await self._post_countdown()
        await itx.response.send_message(
            f"„{name if name is not None else row['aktivitaet']}“ aktualisiert – "
            "der Partner muss den geänderten Termin neu bestätigen.", ephemeral=True)

    @termin_group.command(name="delete", description="Löscht einen Termin unwiderruflich.")
    @app_commands.describe(id="Termin auswählen (tippen zum Suchen)")
    @app_commands.autocomplete(id=_termin_autocomplete)
    async def termin_delete(self, itx: discord.Interaction, id: int):
        row = await self.bot.db.fetchone("SELECT * FROM treffen WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Diesen Termin gibt es nicht mehr.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM treffen WHERE id = ?", id)
        await self._refresh_meilensteine()
        await self._sync_termine()
        await self._post_countdown()
        await itx.response.send_message(f"„{row['aktivitaet']}“ gelöscht.", ephemeral=True)

    # ---------- Liste ----------
    @termin_group.command(name="liste", description="Zeigt alle eingetragenen Termine.")
    async def termine_list(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, TERMINE_KEY, "global", itx.channel, self._build_termine)
        await itx.followup.send(
            f"Terminliste aktuell: {msg.jump_url}" if msg else "Noch keine Termine.", ephemeral=True)

    async def _build_termine(self):
        rows = await self.bot.db.fetchall("SELECT * FROM treffen ORDER BY datum")
        if not rows:
            return emb("info", "📌 Eure Termine",
                       "Noch keine Termine – `/termin add` legt los!"), None
        heute = dt.datetime.now(config.TZ).date()
        zeilen = []
        for r in rows:
            von = dt.date.fromisoformat(r["datum"])
            ende = dt.date.fromisoformat(r["datum_bis"]) if r["datum_bis"] else von
            zeitraum = f"{von:%d.%m.%Y}" + (f" – {ende:%d.%m.%Y}" if ende != von else "")
            zeit_status = "vorbei" if ende < heute else "bevorstehend"
            planung_status = "safe" if r["status"] == "safe" else "planung, unbestätigt"
            zeilen.append(f"{r['emoji']} **{r['aktivitaet']}** · {zeitraum}"
                         + (f" · {r['ort']}" if r["ort"] else "")
                         + f" · {zeit_status} · {planung_status}")
        return emb("info", "📌 Eure Termine", "\n".join(zeilen)), None

    async def _sync_termine(self):
        ch = self.bot.channel_by_name("kalender-treffen")
        await tracked.sync(self.bot, TERMINE_KEY, "global", ch, self._build_termine)

    # ---------- Countdown: sofort nach jeder Änderung, manuell UND täglich ----------
    async def _post_countdown(self) -> discord.Message | None:
        heute = dt.datetime.now(config.TZ).date()
        row = await self.bot.db.fetchone(
            "SELECT * FROM treffen WHERE datum >= ? ORDER BY datum LIMIT 1", heute.isoformat())
        ch = self.bot.channel_by_name("countdown")
        if not row or not ch:
            return None
        von = dt.date.fromisoformat(row["datum"])
        tage = (von - heute).days
        hinweis = "" if row["status"] == "safe" else " (noch nicht von beiden bestätigt)"
        if tage == 0:
            text = f"Heute ist es soweit: **{row['aktivitaet']}**!{hinweis}"
        else:
            text = f"Noch **{tage}** Tag{'e' if tage != 1 else ''} bis **{row['aktivitaet']}**{hinweis}"
        e = emb("info", f"{row['emoji']} Countdown", text)
        return await tracked.sync(self.bot, COUNTDOWN_KEY, "global", ch, self._const(e))

    @staticmethod
    def _const(e: discord.Embed):
        async def build():
            return e, None
        return build

    @termin_group.command(name="countdown",
                          description="Postet/aktualisiert den Countdown zum nächsten Termin sofort.")
    async def termin_countdown(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await self._post_countdown()
        await itx.followup.send(
            f"Countdown aktuell: {msg.jump_url}" if msg else "Noch kein anstehender Termin.",
            ephemeral=True)

    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, tzinfo=config.TZ))
    async def countdown_post(self):
        await self._post_countdown()

    @countdown_post.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Treffen(bot))
