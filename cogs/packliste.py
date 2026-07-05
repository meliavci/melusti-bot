"""Packliste 🎒 – interaktive Checkliste pro Person und Trip."""
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

PACKLISTE_KEY = "packliste"


class Packliste(commands.Cog):
    packliste_group = app_commands.Group(name="packliste", description="Packliste pro Trip.")

    def __init__(self, bot):
        self.bot = bot

    async def _item_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall(
            "SELECT id, item, trip FROM packliste WHERE user_id = ? ORDER BY trip, item",
            itx.user.id)
        return [app_commands.Choice(name=f"{r['item']} ({r['trip']})"[:100], value=r["id"])
                for r in rows if current.lower() in r["item"].lower()][:25]

    async def _trip_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT DISTINCT trip FROM packliste ORDER BY trip")
        return [app_commands.Choice(name=r["trip"], value=r["trip"])
                for r in rows if current.lower() in r["trip"].lower()][:25]

    @packliste_group.command(name="add", description="Fügt etwas zu deiner Packliste hinzu.")
    @app_commands.describe(item="Was musst du einpacken?",
                           trip="Für welchen Trip? (bestehenden auswählen oder neuen Namen eintippen)")
    @app_commands.autocomplete(trip=_trip_autocomplete)
    async def add(self, itx: discord.Interaction, item: str, trip: str = "Nächstes Treffen"):
        await self.bot.db.execute(
            "INSERT INTO packliste (user_id, trip, item) VALUES (?,?,?)", itx.user.id, trip, item)
        await self._sync(trip)
        await itx.response.send_message(f"„{item}“ zur Packliste ({trip}) hinzugefügt.",
                                        ephemeral=True)

    @packliste_group.command(name="abhaken",
                             description="Hakt einen Packlisten-Punkt ab oder wieder auf.")
    @app_commands.describe(item="Welcher Punkt?")
    @app_commands.autocomplete(item=_item_autocomplete)
    async def check(self, itx: discord.Interaction, item: int):
        row = await self.bot.db.fetchone(
            "SELECT * FROM packliste WHERE id = ? AND user_id = ?", item, itx.user.id)
        if not row:
            await itx.response.send_message(
                "⚠️ Eintrag nicht gefunden (nur eigene Punkte abhakbar).", ephemeral=True)
            return
        neu = 0 if row["gepackt"] else 1
        await self.bot.db.execute("UPDATE packliste SET gepackt = ? WHERE id = ?", neu, item)
        await self._sync(row["trip"])
        status = "abgehakt" if neu else "wieder aufgemacht"
        await itx.response.send_message(f"„{row['item']}“ {status}.", ephemeral=True)

    @packliste_group.command(name="delete", description="Entfernt einen Packlisten-Punkt.")
    @app_commands.describe(item="Welcher Punkt?")
    @app_commands.autocomplete(item=_item_autocomplete)
    async def delete(self, itx: discord.Interaction, item: int):
        row = await self.bot.db.fetchone(
            "SELECT * FROM packliste WHERE id = ? AND user_id = ?", item, itx.user.id)
        if not row:
            await itx.response.send_message("⚠️ Eintrag nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM packliste WHERE id = ?", item)
        await self._sync(row["trip"])
        await itx.response.send_message(f"„{row['item']}“ gelöscht.", ephemeral=True)

    async def _build(self, trip: str):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM packliste WHERE trip = ? ORDER BY user_id", trip)
        if not rows:
            return emb("info", f"🎒 Packliste – {trip}",
                       "Noch leer – `/packliste add` legt los!"), None
        nach_person: dict[int, list] = {}
        for r in rows:
            nach_person.setdefault(r["user_id"], []).append(r)
        bloecke = []
        for uid, items in nach_person.items():
            zeilen = [f"{'✅' if r['gepackt'] else '⬜'} {r['item']}" for r in items]
            bloecke.append(f"**{config.name_of(uid)}**\n" + "\n".join(zeilen))
        return emb("info", f"🎒 Packliste – {trip}", "\n\n".join(bloecke)), None

    async def _sync(self, trip: str):
        ch = self.bot.channel_by_name("packliste")
        await tracked.sync(self.bot, PACKLISTE_KEY, trip, ch, lambda: self._build(trip))

    @packliste_group.command(name="liste", description="Zeigt die Packliste für einen Trip.")
    @app_commands.describe(trip="Für welchen Trip? (optional)")
    @app_commands.autocomplete(trip=_trip_autocomplete)
    async def packliste_cmd(self, itx: discord.Interaction, trip: str = "Nächstes Treffen"):
        await itx.response.defer(ephemeral=True)
        ch = self.bot.channel_by_name("packliste") or itx.channel
        msg = await tracked.sync(self.bot, PACKLISTE_KEY, trip, ch, lambda: self._build(trip))
        await itx.followup.send(
            f"Packliste aktuell: {msg.jump_url}" if msg else "Packliste ist leer.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Packliste(bot))
