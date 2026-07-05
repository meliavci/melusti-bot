"""Spiel-Projekt-Brainstorm 💡 – Ideen sammeln, per Voting priorisieren."""
import discord
from discord import app_commands
from discord.ext import commands

from utils import tracked
from utils.design import emb

IDEEN_KEY = "spielideen_liste"


class Spielideen(commands.Cog):
    idee_group = app_commands.Group(name="idee", description="Spiel-Projekt-Brainstorm.")

    def __init__(self, bot):
        self.bot = bot

    async def _idee_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall(
            "SELECT id, text FROM spielideen WHERE status = 'pool' ORDER BY votes DESC")
        return [app_commands.Choice(name=r["text"][:100], value=r["id"])
                for r in rows if current.lower() in r["text"].lower()][:25]

    @idee_group.command(name="add", description="Trägt eine Idee für euer Spiel-Projekt ein.")
    async def idee_add(self, itx: discord.Interaction, text: str):
        await self.bot.db.execute("INSERT INTO spielideen (text, von) VALUES (?,?)",
                                  text, itx.user.id)
        await self._sync_liste()
        await itx.response.send_message("Idee eingetragen – abstimmen mit `/idee vote`.",
                                        ephemeral=True)

    @idee_group.command(name="vote", description="Stimmt für eine Idee.")
    @app_commands.autocomplete(idee=_idee_autocomplete)
    async def idee_vote(self, itx: discord.Interaction, idee: int):
        row = await self.bot.db.fetchone("SELECT * FROM spielideen WHERE id = ?", idee)
        if not row:
            await itx.response.send_message("⚠️ Idee nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE spielideen SET votes = votes + 1 WHERE id = ?", idee)
        await self._sync_liste()
        await itx.response.send_message(f"Stimme für „{row['text']}“ gezählt.", ephemeral=True)

    @idee_group.command(name="status", description="Setzt den Status einer Idee.")
    @app_commands.describe(status="pool / angenommen / verworfen")
    @app_commands.autocomplete(idee=_idee_autocomplete)
    async def idee_status(self, itx: discord.Interaction, idee: int,
                          status: str):
        status_clean = status.strip().lower()
        if status_clean not in ("pool", "angenommen", "verworfen"):
            await itx.response.send_message(
                "⚠️ Status muss 'pool', 'angenommen' oder 'verworfen' sein.", ephemeral=True)
            return
        row = await self.bot.db.fetchone("SELECT * FROM spielideen WHERE id = ?", idee)
        if not row:
            await itx.response.send_message("⚠️ Idee nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE spielideen SET status = ? WHERE id = ?", status_clean, idee)
        await self._sync_liste()
        await itx.response.send_message(f"„{row['text']}“ ist jetzt: {status_clean}.", ephemeral=True)

    async def _build_liste(self):
        rows = await self.bot.db.fetchall("SELECT * FROM spielideen ORDER BY votes DESC")
        if not rows:
            return emb("spiele", "💡 Spiel-Projekt-Ideen", "Noch leer – `/idee add` legt los!"), None
        gruppen: dict[str, list] = {"angenommen": [], "pool": [], "verworfen": []}
        for r in rows:
            gruppen.setdefault(r["status"], []).append(r)
        bloecke = []
        titel = {"angenommen": "Angenommen", "pool": "Im Pool", "verworfen": "Verworfen"}
        for status in ("angenommen", "pool", "verworfen"):
            if gruppen[status]:
                zeilen = [f"{r['votes']} · {r['text']}" for r in gruppen[status]]
                bloecke.append(f"**{titel[status]}**\n" + "\n".join(zeilen))
        return emb("spiele", "💡 Spiel-Projekt-Ideen", "\n\n".join(bloecke)), None

    async def _sync_liste(self):
        ch = self.bot.channel_by_name("spiel-projekt")
        await tracked.sync(self.bot, IDEEN_KEY, "global", ch, self._build_liste)

    @idee_group.command(name="liste", description="Zeigt alle Spiel-Projekt-Ideen.")
    async def ideen_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, IDEEN_KEY, "global", itx.channel, self._build_liste)
        await itx.followup.send(f"Ideen aktuell: {msg.jump_url}" if msg else "Noch keine Ideen.",
                                ephemeral=True)


async def setup(bot):
    await bot.add_cog(Spielideen(bot))
