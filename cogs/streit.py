"""
Streit-Modus 🔧 – geführter Klärungs-Prozess:
Thema → beide Sichten (per DM/Command) → Reveal → Lösung → blinder
Fairness-Check (1-5) → bei einer Bewertung <3: Known Issue statt Geklärt.
Dazu die Pause-Karte: Auszeit mit Timer + Rückkehr-Ping.
"""
import asyncio
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

STREIT_KEY = "streit_liste"


class Streit(commands.Cog):
    streit_group = app_commands.Group(name="streit", description="Geführter Klärungs-Modus.")

    def __init__(self, bot):
        self.bot = bot

    async def _streit_autocomplete_offen(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall(
            "SELECT id, thema FROM streits WHERE status = 'offen' ORDER BY gestartet DESC")
        return [app_commands.Choice(name=r["thema"][:100], value=r["id"])
                for r in rows if current.lower() in r["thema"].lower()][:25]

    async def _streit_autocomplete_alle(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall(
            "SELECT id, thema, status FROM streits ORDER BY gestartet DESC")
        out = []
        for r in rows:
            label = f"{r['thema']} ({r['status']})"
            if current.lower() in label.lower():
                out.append(app_commands.Choice(name=label[:100], value=r["id"]))
        return out[:25]

    @streit_group.command(name="start",
                          description="Startet den geführten Klärungs-Modus für ein Thema.")
    @app_commands.describe(thema="Worum geht's?")
    async def streit_start(self, itx: discord.Interaction, thema: str):
        await self.bot.db.execute(
            "INSERT INTO streits (thema) VALUES (?)", thema)
        for uid in (config.MELI_ID, config.JUSTI_ID):
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await user.send(embed=emb(
                    "rot", "Neuer Klärungs-Prozess",
                    f"Thema: **{thema}**\n\nSchreib deine Sicht mit `/streit sicht` "
                    "(wird erst gezeigt, wenn ihr beide fertig seid)."))
            except discord.Forbidden:
                pass
        await self._sync_liste()
        await itx.response.send_message(
            "Gestartet – ihr bekommt beide eine DM. Sichtweisen mit `/streit sicht` eintragen.",
            ephemeral=True)

    @streit_group.command(name="sicht", description="Trägt deine Sicht der Dinge ein.")
    @app_commands.describe(streit="Welches Thema?", text="Deine Sichtweise")
    @app_commands.autocomplete(streit=_streit_autocomplete_offen)
    async def streit_sicht(self, itx: discord.Interaction, streit: int, text: str):
        row = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if not row or row["status"] != "offen":
            await itx.response.send_message("⚠️ Diesen offenen Klärungs-Prozess gibt es nicht.",
                                            ephemeral=True)
            return
        spalte = f"sicht_{config.slot_of(itx.user.id)}"
        await self.bot.db.execute(f"UPDATE streits SET {spalte} = ? WHERE id = ?", text, streit)
        aktuell = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if aktuell["sicht_a"] and aktuell["sicht_b"]:
            await self._reveal(aktuell)
        await itx.response.send_message("Deine Sicht ist gespeichert.", ephemeral=True)

    async def _reveal(self, row):
        ch = self.bot.channel_by_name("streit-modus")
        if not ch:
            return
        e = emb("rot", f"Reveal: {row['thema']}", "Beide Sichtweisen liegen jetzt vor.")
        e.add_field(name=config.MELI_NAME, value=row["sicht_a"], inline=False)
        e.add_field(name=config.JUSTI_NAME, value=row["sicht_b"], inline=False)
        e.add_field(name="Nächster Schritt", value="Löst es gemeinsam und trägt die Lösung "
                    "mit `/streit loesung` ein.", inline=False)
        await ch.send(embed=e)

    @streit_group.command(name="loesung", description="Trägt die gemeinsame Lösung ein.")
    @app_commands.describe(streit="Welches Thema?", loesung="Wie habt ihr's gelöst?")
    @app_commands.autocomplete(streit=_streit_autocomplete_offen)
    async def streit_loesung(self, itx: discord.Interaction, streit: int, loesung: str):
        row = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if not row or row["status"] != "offen":
            await itx.response.send_message("⚠️ Diesen offenen Klärungs-Prozess gibt es nicht.",
                                            ephemeral=True)
            return
        if not (row["sicht_a"] and row["sicht_b"]):
            await itx.response.send_message(
                "⚠️ Erst müssen beide ihre Sicht eintragen (`/streit sicht`).", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE streits SET loesung = ? WHERE id = ?", loesung, streit)
        for uid in (config.MELI_ID, config.JUSTI_ID):
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await user.send(embed=emb(
                    "gelb", "Fairness-Check", f"Zu „{row['thema']}“: Wie fair war die Lösung "
                    "für dich? Bewerte blind mit `/streit fairness` (1-5)."))
            except discord.Forbidden:
                pass
        await itx.response.send_message(
            "Lösung gespeichert – ihr bekommt beide eine DM für den blinden Fairness-Check.",
            ephemeral=True)

    @streit_group.command(name="fairness",
                          description="Blinder Fairness-Check zur Lösung (1-5).")
    @app_commands.describe(streit="Welches Thema?", wert="1 (unfair) bis 5 (sehr fair)")
    @app_commands.autocomplete(streit=_streit_autocomplete_offen)
    async def streit_fairness(self, itx: discord.Interaction, streit: int,
                              wert: app_commands.Range[int, 1, 5]):
        row = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if not row or row["status"] != "offen" or not row["loesung"]:
            await itx.response.send_message(
                "⚠️ Dafür muss erst eine Lösung eingetragen sein.", ephemeral=True)
            return
        spalte = f"fairness_{config.slot_of(itx.user.id)}"
        await self.bot.db.execute(f"UPDATE streits SET {spalte} = ? WHERE id = ?", wert, streit)
        aktuell = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if aktuell["fairness_a"] is not None and aktuell["fairness_b"] is not None:
            await self._abschliessen(aktuell, itx.user.id)
        await itx.response.send_message("Bewertung gespeichert (bleibt geheim).", ephemeral=True)

    async def _abschliessen(self, row, user_id: int):
        known_issue = row["fairness_a"] < 3 or row["fairness_b"] < 3
        status = "known_issue" if known_issue else "geklaert"
        heute = dt.datetime.now(config.TZ).date().isoformat()
        await self.bot.db.execute(
            "UPDATE streits SET status = ?, geklaert_am = ? WHERE id = ?", status, heute, row["id"])
        ch = self.bot.channel_by_name("streit-modus")
        if not known_issue:
            await self.bot.feed_melusti(user_id, "streit_geklaert", 40)
            if ch:
                await ch.send(embed=emb("gruen", "Geklärt!",
                                        f"**{row['thema']}** ist abgeschlossen – beide fanden "
                                        "die Lösung fair. 🌱"))
        else:
            if ch:
                await ch.send(embed=emb(
                    "gelb", "Known Issue",
                    f"**{row['thema']}**: Die Lösung wurde von mindestens einem als nicht "
                    "fair genug empfunden – bleibt als offenes Thema vermerkt, sprecht "
                    "nochmal drüber."))
        await self._sync_liste()

    @streit_group.command(name="delete",
                          description="Löscht einen Klärungs-Prozess unwiderruflich.")
    @app_commands.describe(streit="Welcher Klärungs-Prozess?")
    @app_commands.autocomplete(streit=_streit_autocomplete_alle)
    async def streit_delete(self, itx: discord.Interaction, streit: int):
        row = await self.bot.db.fetchone("SELECT * FROM streits WHERE id = ?", streit)
        if not row:
            await itx.response.send_message("⚠️ Diesen Klärungs-Prozess gibt es nicht mehr.",
                                            ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM streits WHERE id = ?", streit)
        await self._sync_liste()
        await itx.response.send_message(f"„{row['thema']}“ gelöscht.", ephemeral=True)

    async def _build_liste(self):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM streits WHERE status != 'geklaert' ORDER BY gestartet DESC")
        if not rows:
            return emb("rot", "🔧 Klärungs-Prozesse", "Nichts Offenes – alles geklärt!"), None
        zeilen = []
        for r in rows:
            status = {"offen": "in Klärung", "known_issue": "Known Issue"}.get(r["status"], r["status"])
            zeilen.append(f"**{r['thema']}** – {status} ({r['gestartet'][:10]})")
        return emb("rot", f"🔧 Klärungs-Prozesse ({len(rows)})", "\n".join(zeilen)), None

    async def _sync_liste(self):
        ch = self.bot.channel_by_name("streit-modus")
        await tracked.sync(self.bot, STREIT_KEY, "global", ch, self._build_liste)

    @streit_group.command(name="liste", description="Zeigt offene Klärungs-Prozesse.")
    async def streit_liste(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, STREIT_KEY, "global", itx.channel, self._build_liste)
        await itx.followup.send(
            f"Liste aktuell: {msg.jump_url}" if msg else "Nichts Offenes.", ephemeral=True)

    # ---------- Pause-Karte ----------
    @app_commands.command(name="pause_karte",
                          description="Zieht die Pause-Karte: Auszeit mit Rückkehr-Ping.")
    @app_commands.describe(minuten="Wie lange? (Standard 30)")
    async def pause_karte(self, itx: discord.Interaction,
                          minuten: app_commands.Range[int, 5, 240] = 30):
        ch = self.bot.channel_by_name("streit-modus") or itx.channel
        rueckkehr = dt.datetime.now(config.TZ) + dt.timedelta(minutes=minuten)
        await itx.response.send_message(embed=emb(
            "gelb", "Pause-Karte gezogen",
            f"{config.name_of(itx.user.id)} braucht {minuten} Minuten Auszeit.\n"
            f"Rückkehr um **{rueckkehr:%H:%M}** Uhr."))
        asyncio.create_task(self._pause_timer(ch, minuten))

    async def _pause_timer(self, ch, minuten: int):
        await asyncio.sleep(minuten * 60)
        await ch.send(embed=emb(
            "gruen", "Zeit ist um",
            f"<@{config.MELI_ID}> <@{config.JUSTI_ID}> Zeit für ein Gespräch."))


async def setup(bot):
    await bot.add_cog(Streit(bot))
