"""Handy laden 🔋 – tägliche Erinnerung für Justi um Mitternacht."""
import datetime as dt

import discord
from discord.ext import commands, tasks

import config
from utils.design import emb

MSG_KEY = "handyladen_msg"


class Handyladen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.erinnerung.start()

    def cog_unload(self):
        self.erinnerung.cancel()

    @tasks.loop(time=dt.time(hour=0, minute=0, tzinfo=config.TZ))
    async def erinnerung(self):
        ch = self.bot.channel_by_name("handyladen")
        if not ch:
            return
        # Alte Erinnerung löschen, damit der Kanal nicht jeden Tag um eine
        # weitere Nachricht wächst.
        alte_ref = await self.bot.db.get_setting(MSG_KEY)
        if alte_ref:
            try:
                alte_msg = await ch.fetch_message(int(alte_ref))
                await alte_msg.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        neue_msg = await ch.send(
            content=f"<@{config.JUSTI_ID}>",
            embed=emb("info", "🔋 Handy laden!",
                     "Nicht vergessen, dein Handy ans Ladekabel zu hängen!"))
        await self.bot.db.set_setting(MSG_KEY, str(neue_msg.id))

    @erinnerung.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Handyladen(bot))
