"""Meilensteine 💛 – eure Daten, Live-Zähler, automatische Jubiläums-Posts,
Kalender-Visualisierung (Meilensteine + Termine) mit Auto-Aktualisierung."""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import tracked
from utils.design import emb, render_kalender, render_jahresblick, MONATE

KALENDER_KEY = "kalender_tracked"
JAHRESBLICK_KEY = "jahresblick_tracked"
TAGE_KEY = "tage_uebersicht"


class Meilensteine(commands.Cog):
    meilenstein_group = app_commands.Group(name="meilenstein", description="Eure Meilensteine.")

    def __init__(self, bot):
        self.bot = bot
        self.morning_post.start()

    def cog_unload(self):
        self.morning_post.cancel()

    # ---------- Datenzugriff ----------
    async def _meilensteine_dicts(self):
        rows = await self.bot.db.fetchall("SELECT * FROM meilensteine ORDER BY datum")
        return [{"id": r["id"], "name": r["name"], "emoji": r["emoji"],
                "datum": dt.date.fromisoformat(r["datum"])} for r in rows]

    async def _termine_dicts(self):
        rows = await self.bot.db.fetchall("SELECT * FROM treffen ORDER BY datum")
        out = []
        for r in rows:
            von = dt.date.fromisoformat(r["datum"])
            bis = dt.date.fromisoformat(r["datum_bis"]) if r["datum_bis"] else von
            out.append({"id": r["id"], "name": r["aktivitaet"] or "Termin",
                        "emoji": r["emoji"] or "📌", "von": von, "bis": bis,
                        "ort": r["ort"]})
        return out

    # ---------- Autocomplete (Auswahl per Name statt ID) ----------
    async def _meilenstein_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, name, datum FROM meilensteine ORDER BY datum")
        out = []
        for r in rows:
            d = dt.date.fromisoformat(r["datum"])
            label = f"{r['name']} ({d:%d.%m.%Y})"
            if current.lower() in label.lower():
                out.append(app_commands.Choice(name=label[:100], value=r["id"]))
        return out[:25]

    # ---------- Meilensteine: hinzufügen, ändern, löschen ----------
    @meilenstein_group.command(name="add",
                               description="Fügt einen Meilenstein hinzu (Kennenlernen, 1. Kuss, ...).")
    @app_commands.describe(name="z.B. 'Zusammengekommen'", datum="Format: TT.MM.JJJJ",
                           emoji="Optional: ein Emoji dafür")
    async def add(self, itx: discord.Interaction, name: str, datum: str,
                  emoji: str = "💛"):
        try:
            d = dt.datetime.strptime(datum, "%d.%m.%Y").date()
        except ValueError:
            await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                            ephemeral=True)
            return
        heute = dt.datetime.now(config.TZ).date()
        hinweise = []
        dup = await self.bot.db.fetchone(
            "SELECT 1 FROM meilensteine WHERE name = ? COLLATE NOCASE", name)
        if dup:
            hinweise.append("Es gibt schon einen Meilenstein mit diesem Namen – "
                            "falls das ein Tippfehler war, `/meilenstein edit` nutzen.")
        if d > heute:
            hinweise.append("Das Datum liegt in der Zukunft – ist das so gewollt?")
        evolution_stand = await self.bot.melusti_evolution_stand()
        await self.bot.db.execute(
            "INSERT INTO meilensteine (name, datum, emoji) VALUES (?, ?, ?)",
            name, d.isoformat(), emoji)
        await self.bot.melusti_evolution_pruefen(evolution_stand)
        await self.refresh_all_views()
        tage = (heute - d).days
        zeitangabe = f"vor {tage} Tagen" if tage >= 0 else f"in {-tage} Tagen"
        beschreibung = f"**{name}** – {d:%d.%m.%Y} *({zeitangabe})*"
        if hinweise:
            beschreibung += "\n\n" + "\n".join(hinweise)
        await itx.response.send_message(embed=emb(
            "info", f"{emoji} Meilenstein gespeichert", beschreibung))

    @meilenstein_group.command(name="edit",
                               description="Ändert einen bestehenden Meilenstein.")
    @app_commands.describe(id="Meilenstein auswählen (tippen zum Suchen)",
                           name="Neuer Name (optional)",
                           datum="Neues Datum TT.MM.JJJJ (optional)",
                           emoji="Neues Emoji (optional)")
    @app_commands.autocomplete(id=_meilenstein_autocomplete)
    async def edit(self, itx: discord.Interaction, id: int, name: str | None = None,
                  datum: str | None = None, emoji: str | None = None):
        row = await self.bot.db.fetchone("SELECT * FROM meilensteine WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Diesen Meilenstein gibt es nicht mehr – "
                                            "bitte neu aus der Liste auswählen.", ephemeral=True)
            return
        if name is None and datum is None and emoji is None:
            await itx.response.send_message(
                "⚠️ Gib mindestens ein Feld an (name/datum/emoji).", ephemeral=True)
            return
        new_datum = row["datum"]
        if datum:
            try:
                new_datum = dt.datetime.strptime(datum, "%d.%m.%Y").date().isoformat()
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        await self.bot.db.execute(
            "UPDATE meilensteine SET name = ?, datum = ?, emoji = ? WHERE id = ?",
            name if name is not None else row["name"], new_datum,
            emoji if emoji is not None else row["emoji"], id)
        await self.refresh_all_views()
        await itx.response.send_message(
            f"„{name if name is not None else row['name']}“ aktualisiert.", ephemeral=True)

    @meilenstein_group.command(name="delete",
                               description="Löscht einen Meilenstein unwiderruflich.")
    @app_commands.describe(id="Meilenstein auswählen (tippen zum Suchen)")
    @app_commands.autocomplete(id=_meilenstein_autocomplete)
    async def delete(self, itx: discord.Interaction, id: int):
        row = await self.bot.db.fetchone("SELECT * FROM meilensteine WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Diesen Meilenstein gibt es nicht mehr.",
                                            ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM meilensteine WHERE id = ?", id)
        await self.refresh_all_views()
        await itx.response.send_message(f"„{row['name']}“ gelöscht.", ephemeral=True)

    @meilenstein_group.command(name="tage", description="Wie lange schon? Alle Zähler auf einen Blick.")
    async def tage(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, TAGE_KEY, "global", itx.channel, self._build_tage)
        await itx.followup.send(
            f"Übersicht aktuell: {msg.jump_url}" if msg else "Noch keine Meilensteine.",
            ephemeral=True)

    async def _build_tage(self):
        rows = await self.bot.db.fetchall("SELECT * FROM meilensteine ORDER BY datum")
        if not rows:
            return emb("liebe", "💛 Eure Geschichte in Zahlen",
                       "Noch keine Meilensteine – `/meilenstein add` legt los!"), None
        heute = dt.datetime.now(config.TZ).date()
        e = emb("liebe", "💛 Eure Geschichte in Zahlen",
               f"{len(rows)} Meilenstein{'e' if len(rows) != 1 else ''} – "
               "Bearbeiten/Löschen über `/meilenstein edit` bzw. `/meilenstein delete`")
        for r in rows:
            d = dt.date.fromisoformat(r["datum"])
            tage_seit = (heute - d).days
            naechstes = self._naechster_jahrestag(d, heute)
            in_tagen = (naechstes - heute).days
            wert = f"{d:%d.%m.%Y}\nseit **{tage_seit}** Tagen"
            wert += "\n**heute Jahrestag!**" if in_tagen == 0 else \
                    f"\nnächstes Jubiläum in {in_tagen} Tagen"
            e.add_field(name=f"{r['emoji']} {r['name']}", value=wert, inline=True)
        return e, None

    @staticmethod
    def _naechster_jahrestag(d: dt.date, heute: dt.date) -> dt.date:
        try:
            naechstes = d.replace(year=heute.year)
        except ValueError:  # 29. Februar in einem Nicht-Schaltjahr
            naechstes = d.replace(year=heute.year, day=28)
        if naechstes < heute:
            try:
                naechstes = naechstes.replace(year=heute.year + 1)
            except ValueError:
                naechstes = naechstes.replace(year=heute.year + 1, day=28)
        return naechstes

    # ---------- Kalender-Visualisierung ----------
    @app_commands.command(name="kalender",
                          description="Zeigt eine Monatsansicht mit euren Jubiläen & Terminen.")
    @app_commands.describe(monat="Monat 1-12 (Standard: aktueller Monat)",
                           jahr="Jahr (Standard: aktuelles Jahr)")
    async def kalender(self, itx: discord.Interaction, monat: int | None = None,
                       jahr: int | None = None):
        heute = dt.datetime.now(config.TZ).date()
        monat = monat or heute.month
        jahr = jahr or heute.year
        if not 1 <= monat <= 12:
            await itx.response.send_message("⚠️ Monat muss zwischen 1 und 12 liegen.",
                                            ephemeral=True)
            return
        await itx.response.defer(ephemeral=True)
        sub_key = f"{jahr}-{monat:02d}"
        msg = await tracked.sync(self.bot, KALENDER_KEY, sub_key, itx.channel,
                                 lambda: self._build_kalender(jahr, monat))
        await itx.followup.send(
            f"Kalender aktuell: {msg.jump_url}" if msg else "⚠️ Kalender konnte nicht angezeigt werden.",
            ephemeral=True)

    async def _build_kalender(self, jahr: int, monat: int):
        heute = dt.datetime.now(config.TZ).date()
        meilensteine = await self._meilensteine_dicts()
        termine = await self._termine_dicts()
        file = discord.File(render_kalender(jahr, monat, heute, meilensteine, termine),
                            filename="kalender.png")
        e = emb("info", f"📅 {MONATE[monat - 1]} {jahr}")
        e.set_image(url="attachment://kalender.png")
        return e, file

    @app_commands.command(name="jahresblick",
                          description="Zeigt das ganze Jahr mit euren Jubiläen & Terminen.")
    @app_commands.describe(jahr="Jahr (Standard: aktuelles Jahr)")
    async def jahresblick(self, itx: discord.Interaction, jahr: int | None = None):
        heute = dt.datetime.now(config.TZ).date()
        jahr = jahr or heute.year
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, JAHRESBLICK_KEY, str(jahr), itx.channel,
                                 lambda: self._build_jahresblick(jahr))
        await itx.followup.send(
            f"Jahresblick aktuell: {msg.jump_url}" if msg else "⚠️ Jahresblick konnte nicht angezeigt werden.",
            ephemeral=True)

    async def _build_jahresblick(self, jahr: int):
        heute = dt.datetime.now(config.TZ).date()
        meilensteine = await self._meilensteine_dicts()
        termine = await self._termine_dicts()
        file = discord.File(render_jahresblick(jahr, heute, meilensteine, termine),
                            filename="jahresblick.png")
        e = emb("info", f"🗓️ Jahresblick {jahr}")
        e.set_image(url="attachment://jahresblick.png")
        return e, file

    # ---------- Alle Übersichten aktualisieren ----------
    async def refresh_all_views(self):
        """Wird nach jedem Add/Edit/Delete von Meilensteinen ODER Terminen
        (siehe cogs/treffen.py) sowie einmal täglich aufgerufen – hält alle
        Übersichten aktuell, statt veraltete Nachrichten stehen zu lassen."""

        async def build_kalender(sub_key: str):
            jahr_s, monat_s = sub_key.split("-")
            return await self._build_kalender(int(jahr_s), int(monat_s))

        async def build_jahresblick(sub_key: str):
            return await self._build_jahresblick(int(sub_key))

        async def build_tage(_sub_key: str):
            return await self._build_tage()

        await tracked.refresh_all(self.bot, KALENDER_KEY, build_kalender)
        await tracked.refresh_all(self.bot, JAHRESBLICK_KEY, build_jahresblick)
        await tracked.refresh_all(self.bot, TAGE_KEY, build_tage)

    # ---------- automatische Jubiläen + täglicher Refresh ----------
    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, tzinfo=config.TZ))
    async def morning_post(self):
        heute = dt.datetime.now(config.TZ).date()
        rows = await self.bot.db.fetchall("SELECT * FROM meilensteine")
        ch = self.bot.channel_by_name("meilensteine")
        for r in rows:
            d = dt.date.fromisoformat(r["datum"])
            if d >= heute or not ch:
                continue
            if d.day == heute.day and d.month == heute.month:
                jahre = heute.year - d.year
                await ch.send(embed=emb(
                    "liebe", f"🎉 {jahre}. Jahrestag: {r['name']}!",
                    f"{r['emoji']} Am {d:%d.%m.%Y} war's – heute vor **{jahre} "
                    f"Jahr{'en' if jahre != 1 else ''}**. Feiert euch!"))
            elif d.day == heute.day:
                monate = (heute.year - d.year) * 12 + heute.month - d.month
                await ch.send(embed=emb(
                    "liebe", f"💫 Monats-Jubiläum: {r['name']}",
                    f"{r['emoji']} **{monate} Monate** ist das heute her. "
                    f"({(heute - d).days} Tage!)"))
        # Countdown-/Tage-Zähler driften täglich – alle lebenden Übersichten
        # deshalb einmal am Tag neu rendern, nicht nur bei Änderungen.
        await self.refresh_all_views()

    @morning_post.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Meilensteine(bot))
