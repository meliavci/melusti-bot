"""Zaubertricks 🪄 – einer führt vor, der andere bewertet."""
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

TRICKS_KEY = "zaubertricks_liste"


class Zaubertricks(commands.Cog):
    trick_group = app_commands.Group(name="trick", description="Zaubertricks vorführen & bewerten.")

    def __init__(self, bot):
        self.bot = bot

    async def _unbewertet_autocomplete(self, itx: discord.Interaction, current: str):
        partner = config.partner_of(itx.user.id)
        rows = await self.bot.db.fetchall(
            "SELECT id, name FROM zaubertricks WHERE von = ? AND bewertung IS NULL ORDER BY ts DESC",
            partner)
        return [app_commands.Choice(name=r["name"][:100], value=r["id"])
                for r in rows if current.lower() in r["name"].lower()][:25]

    async def _alle_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, name FROM zaubertricks ORDER BY ts DESC")
        return [app_commands.Choice(name=r["name"][:100], value=r["id"])
               for r in rows if current.lower() in r["name"].lower()][:25]

    @trick_group.command(name="add", description="Trägt einen vorgeführten Zaubertrick ein.")
    @app_commands.describe(name="Name/Titel des Tricks",
                           beschreibung="Optional: was war das Besondere daran?")
    async def trick_add(self, itx: discord.Interaction, name: str, beschreibung: str | None = None):
        await self.bot.db.execute(
            "INSERT INTO zaubertricks (name, von, beschreibung) VALUES (?,?,?)",
            name, itx.user.id, beschreibung)
        await self.bot.feed_melusti(itx.user.id, "trick", None)
        await self._sync_liste()
        partner = config.name_of(config.partner_of(itx.user.id))
        await itx.response.send_message(
            f"„{name}“ eingetragen – {partner} kann ihn mit `/trick bewerten` bewerten!",
            ephemeral=True)

    @trick_group.command(name="bewerten", description="Bewertet einen dir vorgeführten Trick (1-10).")
    @app_commands.describe(trick="Welcher Trick?", bewertung="1 bis 10")
    @app_commands.autocomplete(trick=_unbewertet_autocomplete)
    async def trick_bewerten(self, itx: discord.Interaction, trick: int,
                             bewertung: app_commands.Range[int, 1, 10]):
        row = await self.bot.db.fetchone("SELECT * FROM zaubertricks WHERE id = ?", trick)
        if not row or row["von"] != config.partner_of(itx.user.id):
            await itx.response.send_message(
                "⚠️ Diesen unbewerteten Trick vom Partner gibt es nicht (mehr).", ephemeral=True)
            return
        await self.bot.db.execute(
            "UPDATE zaubertricks SET bewertung = ? WHERE id = ?", bewertung, trick)
        await self._sync_liste()
        ch = self.bot.channel_by_name("zaubertricks")
        if ch:
            await ch.send(embed=emb(
                "spiele", f"🪄 {row['name']} – bewertet!",
                f"{config.name_of(row['von'])}s Trick bekommt **{bewertung}/10** von "
                f"{config.name_of(itx.user.id)}!"))
        await itx.response.send_message("Bewertung gespeichert.", ephemeral=True)

    @trick_group.command(name="delete", description="Löscht einen Zaubertrick-Eintrag.")
    @app_commands.describe(trick="Welcher Trick?")
    @app_commands.autocomplete(trick=_alle_autocomplete)
    async def trick_delete(self, itx: discord.Interaction, trick: int):
        row = await self.bot.db.fetchone("SELECT * FROM zaubertricks WHERE id = ?", trick)
        if not row:
            await itx.response.send_message("⚠️ Diesen Trick gibt es nicht mehr.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM zaubertricks WHERE id = ?", trick)
        await self._sync_liste()
        await itx.response.send_message(f"„{row['name']}“ gelöscht.", ephemeral=True)

    async def _build_liste(self):
        rows = await self.bot.db.fetchall("SELECT * FROM zaubertricks ORDER BY ts DESC")
        if not rows:
            return emb("spiele", "🪄 Zaubertricks", "Noch keine – `/trick add` legt los!"), None
        zeilen = []
        for r in rows:
            bewertung = f" · **{r['bewertung']}/10**" if r["bewertung"] is not None else " · noch unbewertet"
            zeile = f"**{r['name']}** – von {config.name_of(r['von'])}{bewertung}"
            if r["beschreibung"]:
                zeile += f"\n*{r['beschreibung']}*"
            zeilen.append(zeile)
        return emb("spiele", f"🪄 Zaubertricks ({len(rows)})", "\n\n".join(zeilen)[:4000]), None

    async def _sync_liste(self):
        ch = self.bot.channel_by_name("zaubertricks")
        await tracked.sync(self.bot, TRICKS_KEY, "global", ch, self._build_liste)

    @trick_group.command(name="liste", description="Zeigt alle Zaubertricks mit Bewertung.")
    async def trick_liste(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, TRICKS_KEY, "global", itx.channel, self._build_liste)
        await itx.followup.send(
            f"Zaubertricks aktuell: {msg.jump_url}" if msg else "Noch keine Tricks.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Zaubertricks(bot))
