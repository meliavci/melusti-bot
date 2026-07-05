"""
Tipp-Liga ⚽ – erinnert automatisch vor jedem WM-2026-Spiel, damit ihr nicht
vergesst, bei Kicktipp zu tippen. Nutzt die freie, öffentliche WM-Spielplan-
Datei von thestatsapi.com (kein API-Key, kein Login nötig).

Hinweis: Das ist der statische Spielplan von vor dem Turnier – bei K.o.-Spielen
stehen daher teils Platzhalter ("Winner Match 76") statt der inzwischen
feststehenden echten Team-Namen, die genauen Anstoßzeiten stimmen aber.
Die Kicktipp-Tabelle selbst wird NICHT angezeigt (eure Gruppe ist privat,
dafür bräuchte der Bot euer Kicktipp-Passwort – darauf verzichten wir bewusst).
"""
import datetime as dt

import aiohttp
import discord
from discord.ext import commands, tasks

import config
from utils.design import emb

FIXTURES_URL = "https://www.thestatsapi.com/world-cup/data/fixtures.json"
ERINNERUNG_VORLAUF_STUNDEN = 2


class TippLiga(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wm_erinnerung.start()

    def cog_unload(self):
        self.wm_erinnerung.cancel()

    async def _fixtures_laden(self) -> list[dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        FIXTURES_URL, headers={"User-Agent": "Mozilla/5.0"},
                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    body = await resp.json(content_type=None)
                    return body.get("fixtures", [])
        except aiohttp.ClientError:
            return []

    @tasks.loop(hours=1)
    async def wm_erinnerung(self):
        ch = self.bot.channel_by_name("tipp-liga")
        if not ch:
            return
        fixtures = await self._fixtures_laden()
        jetzt = dt.datetime.now(dt.timezone.utc)
        for f in fixtures:
            kickoff = dt.datetime.fromisoformat(f["kickoffUtc"].replace("Z", "+00:00"))
            stunden_bis_anstoss = (kickoff - jetzt).total_seconds() / 3600
            if not (0 < stunden_bis_anstoss <= ERINNERUNG_VORLAUF_STUNDEN):
                continue
            schon_erinnert = await self.bot.db.get_setting(f"wm_erinnert_{f['matchNumber']}")
            if schon_erinnert:
                continue
            kickoff_lokal = kickoff.astimezone(config.TZ)
            await ch.send(
                content=f"<@{config.MELI_ID}> <@{config.JUSTI_ID}>",
                embed=emb("spiele", "⚽ WM-Spiel steht bald an!",
                         f"**{f['homeTeam']}** vs **{f['awayTeam']}**\n"
                         f"Anstoß: **{kickoff_lokal:%H:%M} Uhr** – nicht vergessen, "
                         "bei Kicktipp zu tippen!"))
            await self.bot.db.set_setting(f"wm_erinnert_{f['matchNumber']}", "1")

    @wm_erinnerung.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TippLiga(bot))
