"""Zitate 📜 – Sprüche mit Kontext sammeln, zufällig wieder ausgraben."""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.design import emb

RANDOM_ZITAT_MSG_KEY = "random_zitat_msg"


class Zitate(commands.Cog):
    zitat_group = app_commands.Group(name="zitat", description="Legendäre Zitate archivieren.")

    def __init__(self, bot):
        self.bot = bot
        self.random_zitat.start()

    def cog_unload(self):
        self.random_zitat.cancel()

    # ---------- Autocomplete (Auswahl per Zitat-Vorschau statt ID) ----------
    async def _zitat_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, text, von, datum FROM zitate ORDER BY datum")
        out = []
        for r in rows:
            label = f"„{r['text']}“ – {r['von']} ({r['datum']})"
            if current.lower() in label.lower():
                out.append(app_commands.Choice(name=label[:100], value=r["id"]))
        return out[:25]

    @zitat_group.command(name="add", description="Speichert ein legendäres Zitat.")
    @app_commands.describe(text="Das Zitat", von="Wer hat's gesagt?",
                           kontext="Was war los? (optional)",
                           datum="Wann? Format TT.MM.JJJJ (optional, Standard: heute)")
    async def add(self, itx: discord.Interaction, text: str, von: str,
                  kontext: str | None = None, datum: str | None = None):
        if datum:
            try:
                dt.datetime.strptime(datum, "%d.%m.%Y")
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        else:
            datum = dt.datetime.now(config.TZ).strftime("%d.%m.%Y")
        await self.bot.db.execute(
            "INSERT INTO zitate (text, kontext, von, added_by, datum) VALUES (?,?,?,?,?)",
            text, kontext, von, itx.user.id, datum)
        await self.bot.feed_melusti(itx.user.id, "zitat", None)
        await itx.response.send_message(embed=self._zitat_embed(
            text, von, kontext, datum, titel="📜 Zitat archiviert"))

    @zitat_group.command(name="zufall", description="Zieht ein zufälliges Zitat aus dem Archiv.")
    async def random_cmd(self, itx: discord.Interaction):
        row = await self.bot.db.fetchone("SELECT * FROM zitate ORDER BY RANDOM() LIMIT 1")
        if not row:
            await itx.response.send_message("Noch keine Zitate – `/zitat add`!", ephemeral=True)
            return
        await itx.response.send_message(embed=self._zitat_embed(
            row["text"], row["von"], row["kontext"], row["datum"]))

    @zitat_group.command(name="edit", description="Ändert ein gespeichertes Zitat.")
    @app_commands.describe(id="Zitat auswählen (tippen zum Suchen)",
                           text="Neuer Text (optional)", von="Neuer Sprecher (optional)",
                           kontext="Neuer Kontext (optional)",
                           datum="Neues Datum TT.MM.JJJJ (optional)")
    @app_commands.autocomplete(id=_zitat_autocomplete)
    async def edit(self, itx: discord.Interaction, id: int, text: str | None = None,
                  von: str | None = None, kontext: str | None = None,
                  datum: str | None = None):
        row = await self.bot.db.fetchone("SELECT * FROM zitate WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Dieses Zitat gibt es nicht mehr – "
                                            "bitte neu aus der Liste auswählen.", ephemeral=True)
            return
        if all(v is None for v in (text, von, kontext, datum)):
            await itx.response.send_message(
                "⚠️ Gib mindestens ein Feld an (text/von/kontext/datum).", ephemeral=True)
            return
        new_datum = row["datum"]
        if datum:
            try:
                dt.datetime.strptime(datum, "%d.%m.%Y")
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
            new_datum = datum
        await self.bot.db.execute(
            "UPDATE zitate SET text = ?, von = ?, kontext = ?, datum = ? WHERE id = ?",
            text if text is not None else row["text"],
            von if von is not None else row["von"],
            kontext if kontext is not None else row["kontext"],
            new_datum, id)
        await itx.response.send_message("Zitat aktualisiert.", ephemeral=True)

    @zitat_group.command(name="delete", description="Löscht ein gespeichertes Zitat.")
    @app_commands.describe(id="Zitat auswählen (tippen zum Suchen)")
    @app_commands.autocomplete(id=_zitat_autocomplete)
    async def delete(self, itx: discord.Interaction, id: int):
        row = await self.bot.db.fetchone("SELECT * FROM zitate WHERE id = ?", id)
        if not row:
            await itx.response.send_message("⚠️ Dieses Zitat gibt es nicht mehr.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM zitate WHERE id = ?", id)
        await itx.response.send_message(f"Zitat von {row['von']} gelöscht.", ephemeral=True)

    def _zitat_embed(self, text, von, kontext, datum, titel="📜 Aus dem Archiv"):
        e = emb("medien", titel, f"## „{text}“\n— **{von}**, {datum}")
        if kontext:
            e.add_field(name="Kontext", value=f"*{kontext}*")
        return e

    # Alle 3 Tage gräbt der Bot abends ein zufälliges Zitat aus
    @tasks.loop(hours=72)
    async def random_zitat(self):
        row = await self.bot.db.fetchone("SELECT * FROM zitate ORDER BY RANDOM() LIMIT 1")
        ch = self.bot.channel_by_name("zitate")
        if row and ch:
            # Alte Resurface-Nachricht löschen, damit der Kanal nicht alle
            # 3 Tage um eine weitere Nachricht wächst.
            alte_ref = await self.bot.db.get_setting(RANDOM_ZITAT_MSG_KEY)
            if alte_ref:
                try:
                    alte_msg = await ch.fetch_message(int(alte_ref))
                    await alte_msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            e = self._zitat_embed(row["text"], row["von"], row["kontext"],
                                  row["datum"], titel="📜 Wisst ihr noch...?")
            msg = await ch.send(embed=e)
            await msg.add_reaction("😂")
            await msg.add_reaction("🏆")
            await self.bot.db.set_setting(RANDOM_ZITAT_MSG_KEY, str(msg.id))

    @random_zitat.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Zitate(bot))
