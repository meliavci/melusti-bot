"""/export – komplette Datenbank als lesbare Textdatei."""
import datetime as dt
import io

import discord
from discord import app_commands
from discord.ext import commands

import config

TABELLEN = [
    "meilensteine", "checkins", "briefkasten", "streits", "treffen", "tagebuch",
    "film_runden", "film_archiv", "film_awards", "watchlist", "woerterbuch", "zitate",
    "songs", "spiele", "ranked_progress", "zeitkapseln", "lebenszeichen", "komplimente",
    "fotos", "pixel_canvas", "packliste", "bucketlist", "traeume", "calls", "wetten",
    "quests", "spielideen", "fragen", "frage_antworten",
]


class Export(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="export", description="Exportiert die komplette Datenbank als lesbare Datei.")
    async def export(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        teile = []
        for tabelle in TABELLEN:
            try:
                rows = await self.bot.db.fetchall(f"SELECT * FROM {tabelle}")
            except Exception:
                continue
            teile.append(f"=== {tabelle} ({len(rows)} Einträge) ===")
            for r in rows:
                teile.append(", ".join(f"{k}={r[k]}" for k in r.keys()))
            teile.append("")
        inhalt = "\n".join(teile)
        datei = discord.File(io.BytesIO(inhalt.encode("utf-8")),
                             filename=f"melusti_export_{dt.datetime.now(config.TZ):%Y-%m-%d}.txt")
        await itx.followup.send("Hier ist der komplette Export.", file=datei, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Export(bot))
