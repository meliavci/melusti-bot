"""Witzebuch 😂 – einer trägt den Witz ein, der andere bewertet mit bis zu 5 Sternen."""
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

WITZE_KEY = "witze_liste"


def _sterne(wert: int) -> str:
    return "★" * wert + "☆" * (5 - wert)


class Witze(commands.Cog):
    witz_group = app_commands.Group(name="witz", description="Witze eintragen & bewerten.")

    def __init__(self, bot):
        self.bot = bot

    async def _unbewertet_autocomplete(self, itx: discord.Interaction, current: str):
        partner = config.partner_of(itx.user.id)
        rows = await self.bot.db.fetchall(
            "SELECT id, text FROM witze WHERE von = ? AND bewertung IS NULL ORDER BY ts DESC",
            partner)
        return [app_commands.Choice(name=r["text"][:100], value=r["id"])
               for r in rows if current.lower() in r["text"].lower()][:25]

    async def _alle_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, text FROM witze ORDER BY ts DESC")
        return [app_commands.Choice(name=r["text"][:100], value=r["id"])
               for r in rows if current.lower() in r["text"].lower()][:25]

    @witz_group.command(name="add", description="Trägt einen Witz ein.")
    @app_commands.describe(text="Der Witz")
    async def witz_add(self, itx: discord.Interaction, text: str):
        await self.bot.db.execute("INSERT INTO witze (text, von) VALUES (?,?)", text, itx.user.id)
        await self.bot.feed_melusti(itx.user.id, "witz", None)
        await self._sync_liste()
        partner = config.name_of(config.partner_of(itx.user.id))
        await itx.response.send_message(
            f"Witz eingetragen – {partner} kann ihn mit `/witz bewerten` bewerten!", ephemeral=True)

    @witz_group.command(name="bewerten", description="Bewertet einen Witz des Partners (1-5 Sterne).")
    @app_commands.describe(witz="Welcher Witz?", sterne="1 bis 5 Sterne")
    @app_commands.autocomplete(witz=_unbewertet_autocomplete)
    async def witz_bewerten(self, itx: discord.Interaction, witz: int,
                            sterne: app_commands.Range[int, 1, 5]):
        row = await self.bot.db.fetchone("SELECT * FROM witze WHERE id = ?", witz)
        if not row or row["von"] != config.partner_of(itx.user.id):
            await itx.response.send_message(
                "⚠️ Diesen unbewerteten Witz vom Partner gibt es nicht (mehr).", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE witze SET bewertung = ? WHERE id = ?", sterne, witz)
        await self._sync_liste()
        ch = self.bot.channel_by_name("witze")
        if ch:
            await ch.send(embed=emb(
                "spiele", "😂 Witz bewertet!",
                f"„{row['text']}“ von {config.name_of(row['von'])} bekommt "
                f"**{_sterne(sterne)}** von {config.name_of(itx.user.id)}!"))
        await itx.response.send_message("Bewertung gespeichert.", ephemeral=True)

    @witz_group.command(name="delete", description="Löscht einen Witz.")
    @app_commands.describe(witz="Welcher Witz?")
    @app_commands.autocomplete(witz=_alle_autocomplete)
    async def witz_delete(self, itx: discord.Interaction, witz: int):
        row = await self.bot.db.fetchone("SELECT * FROM witze WHERE id = ?", witz)
        if not row:
            await itx.response.send_message("⚠️ Diesen Witz gibt es nicht mehr.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM witze WHERE id = ?", witz)
        await self._sync_liste()
        await itx.response.send_message("Witz gelöscht.", ephemeral=True)

    async def _build_liste(self):
        rows = await self.bot.db.fetchall("SELECT * FROM witze ORDER BY ts DESC")
        if not rows:
            return emb("spiele", "😂 Witzebuch", "Noch keine – `/witz add` legt los!"), None
        zeilen = []
        for r in rows:
            bewertung = f" · {_sterne(r['bewertung'])}" if r["bewertung"] is not None else " · noch unbewertet"
            zeilen.append(f"„{r['text']}“ – von {config.name_of(r['von'])}{bewertung}")
        return emb("spiele", f"😂 Witzebuch ({len(rows)})", "\n".join(zeilen)[:4000]), None

    async def _sync_liste(self):
        ch = self.bot.channel_by_name("witze")
        await tracked.sync(self.bot, WITZE_KEY, "global", ch, self._build_liste)

    @witz_group.command(name="liste", description="Zeigt alle Witze mit Bewertung.")
    async def witz_liste(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, WITZE_KEY, "global", itx.channel, self._build_liste)
        await itx.followup.send(
            f"Witzebuch aktuell: {msg.jump_url}" if msg else "Noch keine Witze.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Witze(bot))
