"""Lebenszeichen 💭 – ein Knopf, null Aufwand, viel Gefühl."""
import random

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.design import emb

VARIANTEN = [
    "ist unterwegs und denkt an dich",
    "hat gerade an dich gedacht",
    "schickt dir ein Herz durch die Leitung",
    "wollte nur sagen: alles gut, du bist im Kopf",
]


class DenkView(discord.ui.View):
    """Button unterm Lebenszeichen: mit einem Tap zurückdenken."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="zurückdenken", emoji="💭",
                       style=discord.ButtonStyle.secondary, custom_id="denk:zurueck")
    async def zurueck(self, itx: discord.Interaction, _):
        cog = self.bot.get_cog("Lebenszeichen")
        await cog.send_zeichen(itx, None, reply=True)


class LebenszeichenStartView(discord.ui.View):
    """Ein Klick, ohne Command tippen zu müssen – steht dauerhaft als eigene
    Nachricht in #lebenszeichen."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Ich denk an dich", emoji="💭",
                       style=discord.ButtonStyle.primary, custom_id="denk:start")
    async def start(self, itx: discord.Interaction, _):
        cog = self.bot.get_cog("Lebenszeichen")
        await cog.send_zeichen(itx, None, reply=False)


STARTER_KEY = "lebenszeichen_starter_msg"
PING_KEY = "lebenszeichen_ping_msg"


class Lebenszeichen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(DenkView(bot))  # persistent über Neustarts
        bot.add_view(LebenszeichenStartView(bot))

    @commands.Cog.listener()
    async def on_ready(self):
        await self._ensure_starter()

    async def _ensure_starter(self):
        """Sorgt dafür, dass GENAU EINE Knopf-Nachricht in #lebenszeichen liegt,
        über die man ganz ohne Command ein Lebenszeichen verschicken kann."""
        ch = self.bot.channel_by_name("lebenszeichen")
        if not ch:
            return
        ref = await self.bot.db.get_setting(STARTER_KEY)
        if ref:
            channel_id, message_id = (int(x) for x in ref.split(":"))
            try:
                await ch.fetch_message(message_id)
                return  # existiert schon, nichts zu tun
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Nachricht weg -> unten neu posten
        msg = await ch.send(
            embed=emb("liebe", "💭 Lebenszeichen",
                     "Ein Klick reicht – dein Schatz bekommt sofort Bescheid im Channel."),
            view=LebenszeichenStartView(self.bot))
        await self.bot.db.set_setting(STARTER_KEY, f"{ch.id}:{msg.id}")

    @app_commands.command(name="denk",
                          description="Schickt ein Lebenszeichen: 'Ich denke an dich' 💭")
    @app_commands.describe(nachricht="Optional: kleine Nachricht dazu")
    async def denk(self, itx: discord.Interaction, nachricht: str | None = None):
        await self.send_zeichen(itx, nachricht, reply=False)

    async def send_zeichen(self, itx: discord.Interaction,
                           nachricht: str | None, reply: bool):
        von = itx.user.id
        partner = config.partner_of(von)
        ch = self.bot.channel_by_name("lebenszeichen")

        titel = f"💭 {config.name_of(von)} " + random.choice(VARIANTEN)
        if reply:
            titel = f"💭↩️ {config.name_of(von)} denkt zurück"
        e = emb("liebe", titel, f"„{nachricht}“" if nachricht else "")
        e.set_author(name=itx.user.display_name,
                     icon_url=itx.user.display_avatar.url)

        await self.bot.db.execute(
            "INSERT INTO lebenszeichen (von, text) VALUES (?, ?)", von, nachricht)
        await self.bot.feed_melusti(von, "lebenszeichen", None)

        if ch:
            # Alte Ping-Nachricht löschen statt den Kanal vollzuspammen – es
            # bleibt immer nur das jeweils letzte Lebenszeichen sichtbar.
            alte_ref = await self.bot.db.get_setting(PING_KEY)
            if alte_ref:
                try:
                    alte_msg = await ch.fetch_message(int(alte_ref))
                    await alte_msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            neue_msg = await ch.send(content=f"<@{partner}>", embed=e, view=DenkView(self.bot))
            await self.bot.db.set_setting(PING_KEY, str(neue_msg.id))
        if itx.response.is_done():
            await itx.followup.send("💭 raus!", ephemeral=True)
        else:
            await itx.response.send_message("💭 raus!", ephemeral=True)

    @app_commands.command(name="kompliment",
                          description="Schickt deinem Schatz ein Kompliment. 💛")
    @app_commands.describe(text="Dein Kompliment")
    async def kompliment(self, itx: discord.Interaction, text: str):
        partner = config.partner_of(itx.user.id)
        await self.bot.db.execute(
            "INSERT INTO komplimente (von, text) VALUES (?, ?)", itx.user.id, text)
        await self.bot.feed_melusti(itx.user.id, "kompliment", None)
        ch = self.bot.channel_by_name("komplimente")
        e = emb("liebe", f"💌 Für {config.name_of(partner)}", f"„{text}“")
        e.set_author(name=itx.user.display_name, icon_url=itx.user.display_avatar.url)
        if ch:
            await ch.send(content=f"<@{partner}>", embed=e)
        await itx.response.send_message("💌 zugestellt!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Lebenszeichen(bot))
