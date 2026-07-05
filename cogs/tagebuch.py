"""Tagebuch 📔 – alle Einträge in EINER lebenden Timeline-Nachricht in #tagebuch,
statt jeden Eintrag einzeln zu posten. Chronologisch sortiert (älteste zuerst)."""
import datetime as dt
import json

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

TIMELINE_KEY = "tagebuch_timeline"
MAX_EINTRAEGE = 10  # Discord erlaubt maximal 10 Embeds pro Nachricht


class Tagebuch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tagebuch_add", description="Neuer Tagebuch-Eintrag.")
    @app_commands.describe(titel="Überschrift", text="Was ist passiert?",
                           bild="Optional: ein Bild dazu",
                           datum="Format TT.MM.JJJJ (optional, Standard: heute)")
    async def add(self, itx: discord.Interaction, titel: str, text: str,
                  bild: discord.Attachment | None = None, datum: str | None = None):
        if datum:
            try:
                d = dt.datetime.strptime(datum, "%d.%m.%Y").date()
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        else:
            d = dt.datetime.now(config.TZ).date()
        bild_urls = json.dumps([bild.url]) if bild else None
        await self.bot.db.execute(
            "INSERT INTO tagebuch (autor_id, datum, titel, text, bild_urls) VALUES (?,?,?,?,?)",
            itx.user.id, d.isoformat(), titel, text, bild_urls)
        await self._sync_timeline()
        await itx.response.send_message(
            "Eintrag gespeichert – Timeline in #tagebuch aktualisiert.", ephemeral=True)

    def _eintrag_embed(self, r) -> discord.Embed:
        d = dt.date.fromisoformat(r["datum"])
        e = emb("liebe", f"📔 {r['titel']}",
               f"{r['text']}\n\n— {config.name_of(r['autor_id'])}, {d:%d.%m.%Y}")
        bilder = json.loads(r["bild_urls"]) if r["bild_urls"] else []
        if bilder:
            e.set_image(url=bilder[0])
        return e

    async def _build_timeline(self):
        rows = await self.bot.db.fetchall("SELECT * FROM tagebuch ORDER BY datum ASC, ts ASC")
        if not rows:
            return emb("liebe", "📔 Tagebuch-Timeline",
                       "Noch leer – `/tagebuch_add` legt los!"), None
        gezeigt = rows[-MAX_EINTRAEGE:]
        embeds = [self._eintrag_embed(r) for r in gezeigt]
        if len(rows) > MAX_EINTRAEGE:
            uebrig = len(rows) - MAX_EINTRAEGE
            embeds[0].set_footer(text=f"+ {uebrig} ältere Einträge (Discord zeigt max. "
                                 f"{MAX_EINTRAEGE} Embeds pro Nachricht)")
        return embeds, None

    async def _sync_timeline(self):
        ch = self.bot.channel_by_name("tagebuch")
        await tracked.sync(self.bot, TIMELINE_KEY, "global", ch, self._build_timeline)

    @app_commands.command(name="timeline", description="Zeigt/aktualisiert die Tagebuch-Timeline.")
    async def timeline(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, TIMELINE_KEY, "global", itx.channel, self._build_timeline)
        await itx.followup.send(
            f"Timeline aktuell: {msg.jump_url}" if msg else "Noch keine Einträge.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tagebuch(bot))
