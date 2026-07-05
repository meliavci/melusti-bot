"""/setup_server – baut die komplette Channel-Struktur automatisch auf."""
import discord
from discord import app_commands
from discord.ext import commands

from utils.design import emb

STRUKTUR = {
    "📋 KERN": ["info", "check-in", "melusti", "briefkasten", "handyladen"],
    "📅 PLANUNG": ["kalender-treffen", "countdown", "meilensteine", "tagebuch",
                   "packliste", "bucket-list"],
    "🎮 ZOCKEN": ["valorant", "spiele-tinder", "kartentisch", "spiel-projekt"],
    "🎬 MEDIEN": ["filmabend", "film-archiv", "film-benachrichtigung", "film-awards",
                  "watchlist-filme", "watchlist-youtube", "unsere-playlist"],
    "💛 WIR": ["lebenszeichen", "komplimente", "zitate", "wörterbuch",
               "foto-des-tages", "zeitkapsel", "traum-tagebuch", "pixel-canvas",
               "zaubertricks", "witze"],
    "⚽ SPASS": ["tipp-liga", "wetten", "entscheidungsrad"],
    "🔧 KLÄRUNG": ["streit-modus"],
    "📊 STATS": ["stats"],
}


class SetupServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_server",
                          description="Erstellt alle Kategorien & Channels (einmalig).")
    @app_commands.default_permissions(administrator=True)
    async def setup_server(self, itx: discord.Interaction):
        await itx.response.defer(thinking=True)
        g = itx.guild
        created = 0

        for cat_name, channels in STRUKTUR.items():
            cat = discord.utils.get(g.categories, name=cat_name)
            if cat is None:
                cat = await g.create_category(cat_name)
                created += 1
            for ch_name in channels:
                if discord.utils.get(g.text_channels, name=ch_name) is None:
                    await g.create_text_channel(ch_name, category=cat)
                    created += 1

        # Privater, gesperrter Channel – nur ihr zwei, kein Bot-Feature nötig:
        # unsichtbar für alle Rollen außer euch beiden (auf einem 2-Personen-Server
        # ist das Gürtel + Hosenträger, aber sicher ist sicher).
        cat = discord.utils.get(g.categories, name="🔒 PRIVAT")
        if cat is None:
            overwrites = {
                g.default_role: discord.PermissionOverwrite(view_channel=False),
            }
            for m in g.members:
                if not m.bot:
                    overwrites[m] = discord.PermissionOverwrite(view_channel=True)
            cat = await g.create_category("🔒 PRIVAT", overwrites=overwrites)
            await g.create_text_channel("nur-für-uns", category=cat)
            created += 2

        # Voice-Channel für eure Calls (Call-Stats kommen in einer späteren Session)
        if discord.utils.get(g.voice_channels, name="🎧 unser call") is None:
            await g.create_voice_channel("🎧 unser call")
            created += 1

        await self.bot.db.set_setting("guild_id", g.id)
        e = emb("melusti", "🏗️ Server aufgebaut!",
                f"**{created}** Kategorien/Channels erstellt.\n\n"
                "Nächste Schritte:\n"
                "• `/melusti` – schaut euer frisch geschlüpftes Ei an 🥚\n"
                "• `/meilenstein add` – tragt eure wichtigen Daten ein\n"
                "• `/checkin` – startet den ersten Ampel-Check-in\n"
                "• `/wort add` & `/zitat add` – füttert euer Lexikon")
        await itx.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(SetupServer(bot))
