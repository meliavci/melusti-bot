"""
MELUSTI BOT – euer Beziehungs-Betriebssystem 🌱
Start: python main.py
"""
import logging

import discord
from discord.ext import commands

import config
import keepalive
from database.db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("melusti")


class MelustiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents,
                         activity=discord.CustomActivity("Flupp und Zahn 🌱"))
        self.db = Database(config.DB_PATH)

    async def setup_hook(self):
        await self.db.init()
        for uid, name in ((config.MELI_ID, config.MELI_NAME),
                          (config.JUSTI_ID, config.JUSTI_NAME)):
            await self.db.execute(
                "INSERT OR REPLACE INTO users (discord_id, name) VALUES (?, ?)",
                uid, name)
        for ext in config.COGS:
            await self.load_extension(ext)
            log.info("Cog geladen: %s", ext)
        await self.tree.sync()
        log.info("Slash-Commands synchronisiert.")

    async def on_ready(self):
        log.info("Eingeloggt als %s (%s)", self.user, self.user.id)

    # ---------- Helfer, die alle Cogs nutzen ----------
    def home_guild(self) -> discord.Guild | None:
        return self.guilds[0] if self.guilds else None

    def channel_by_name(self, name: str) -> discord.TextChannel | None:
        g = self.home_guild()
        if not g:
            return None
        return discord.utils.get(g.text_channels, name=name)

    async def feed_melusti(self, user_id: int, action: str, xp: int):
        """Zentrale Fütter-Funktion – Cogs rufen die auf, Melusti-Cog reagiert."""
        cog = self.get_cog("Melusti")
        if cog:
            await cog.feed(user_id, action, xp)

    async def melusti_evolution_stand(self) -> tuple[int, int] | None:
        """Von Cogs VOR einer Änderung aufrufen, die die Meilenstein-Anzahl
        beeinflusst (z.B. /meilenstein add) – danach melusti_evolution_pruefen()
        mit dem Ergebnis aufrufen, um eine mögliche Entwicklung zu erkennen."""
        cog = self.get_cog("Melusti")
        return await cog._aktueller_stand() if cog else None

    async def melusti_evolution_pruefen(self, stand: tuple[int, int] | None):
        cog = self.get_cog("Melusti")
        if cog and stand is not None:
            await cog.pruefe_evolution(*stand)


def main():
    if not config.TOKEN:
        raise SystemExit("❌ Kein DISCORD_TOKEN in der .env gefunden – siehe README Schritt 2.")
    keepalive.start()
    MelustiBot().run(config.TOKEN)


if __name__ == "__main__":
    main()
