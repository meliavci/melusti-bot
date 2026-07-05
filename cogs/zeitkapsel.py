"""Zeitkapsel 💌 – Nachrichten an die Zukunft. Der andere weiß nur, DASS etwas wartet."""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils.design import emb


class KapselModal(discord.ui.Modal, title="💌 Zeitkapsel schreiben"):
    datum = discord.ui.TextInput(label="Öffnet sich am (TT.MM.JJJJ)",
                                 placeholder="z.B. 21.12.2026")
    text = discord.ui.TextInput(label="Deine Nachricht an die Zukunft",
                                style=discord.TextStyle.paragraph, max_length=1500)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, itx: discord.Interaction):
        try:
            d = dt.datetime.strptime(str(self.datum), "%d.%m.%Y").date()
        except ValueError:
            await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                            ephemeral=True)
            return
        if d <= dt.datetime.now(config.TZ).date():
            await itx.response.send_message("⚠️ Das Datum muss in der Zukunft liegen.",
                                            ephemeral=True)
            return
        await self.cog.bot.db.execute(
            "INSERT INTO zeitkapseln (autor_id, unlock_datum, text) VALUES (?,?,?)",
            itx.user.id, d.isoformat(), str(self.text))
        await self.cog.bot.feed_melusti(itx.user.id, "zeitkapsel", None)
        await itx.response.send_message(
            f"💌 Vergraben! Öffnet sich am **{d:%d.%m.%Y}**.", ephemeral=True)

        ch = self.cog.bot.channel_by_name("zeitkapsel")
        if ch:
            partner = config.partner_of(itx.user.id)
            await ch.send(content=f"<@{partner}>", embed=emb(
                "liebe", "📦 Eine Zeitkapsel wurde vergraben...",
                f"**{config.name_of(itx.user.id)}** hat etwas für dich geschrieben.\n"
                f"🔒 Öffnet sich am **{d:%d.%m.%Y}** – kein Spicken möglich."))


class Zeitkapsel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_unlock.start()

    def cog_unload(self):
        self.check_unlock.cancel()

    @app_commands.command(name="zeitkapsel",
                          description="Schreibt eine Nachricht, die sich erst später öffnet.")
    async def schreiben(self, itx: discord.Interaction):
        await itx.response.send_modal(KapselModal(self))

    @app_commands.command(name="zeitkapsel_status",
                          description="Wie viele Kapseln sind noch vergraben?")
    async def status(self, itx: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT autor_id, unlock_datum FROM zeitkapseln WHERE geliefert = 0 "
            "ORDER BY unlock_datum")
        if not rows:
            await itx.response.send_message("Keine vergrabenen Kapseln. `/zeitkapsel`!",
                                            ephemeral=True)
            return
        lines = [f"🔒 von **{config.name_of(r['autor_id'])}** → öffnet "
                 f"{dt.date.fromisoformat(r['unlock_datum']):%d.%m.%Y}" for r in rows]
        await itx.response.send_message(embed=emb(
            "liebe", f"📦 {len(rows)} vergrabene Zeitkapseln", "\n".join(lines)))

    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, tzinfo=config.TZ))
    async def check_unlock(self):
        heute = dt.datetime.now(config.TZ).date().isoformat()
        rows = await self.bot.db.fetchall(
            "SELECT * FROM zeitkapseln WHERE geliefert = 0 AND unlock_datum <= ?", heute)
        ch = self.bot.channel_by_name("zeitkapsel")
        for r in rows:
            partner = config.partner_of(r["autor_id"])
            e = emb("liebe", "💌 EINE ZEITKAPSEL ÖFFNET SICH!",
                    f"Geschrieben von **{config.name_of(r['autor_id'])}** "
                    f"am {r['ts'][:10]}:\n\n>>> {r['text']}")
            if ch:
                await ch.send(content=f"<@{partner}>", embed=e)
            await self.bot.db.execute(
                "UPDATE zeitkapseln SET geliefert = 1 WHERE id = ?", r["id"])

    @check_unlock.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Zeitkapsel(bot))
