"""
Kreativ & Alltag 💛
- Pixel-Canvas 32x32: 5 Pixel/Tag/Person, X/Y per Modal + Farbe per
  Dropdown-Palette (kein Hex-Code nötig), Bild wird neu gerendert.
- Foto des Tages: 1/Tag/Person, mit Streak.
- Traum-Tagebuch mit /traum + Timeline.
- Bucket List mit Abhaken + Feier-Post.
"""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb, render_pixel_canvas

# (Name, Hex, Emoji) – Farbauswahl per Dropdown statt Hex-Code auswendig zu kennen.
FARBPALETTE = [
    ("Rot", "FF0000", "🟥"),
    ("Orange", "FF7F00", "🟧"),
    ("Gelb", "FFFF00", "🟨"),
    ("Grün", "00FF00", "🟩"),
    ("Türkis", "00FFFF", "🔷"),
    ("Blau", "0000FF", "🟦"),
    ("Lila", "8B00FF", "🟪"),
    ("Pink", "FF1493", "🌸"),
    ("Braun", "8B4513", "🟫"),
    ("Schwarz", "000000", "⬛"),
    ("Weiß", "FFFFFF", "⬜"),
    ("Grau", "808080", "⚫"),
    ("Hellblau", "87CEEB", "🩵"),
    ("Hellgrün", "90EE90", "💚"),
    ("Hellrosa", "FFB6C1", "🩷"),
    ("Dunkelrot", "8B0000", "❤️"),
    ("Dunkelblau", "00008B", "💙"),
    ("Dunkelgrün", "006400", "🌲"),
    ("Gold", "FFD700", "✨"),
    ("Beige", "F5F5DC", "🟡"),
]


class PixelModal(discord.ui.Modal, title="Pixel setzen"):
    x = discord.ui.TextInput(label="X (0-31)", max_length=2)
    y = discord.ui.TextInput(label="Y (0-31)", max_length=2)

    def __init__(self, cog: "Kreativ"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, itx: discord.Interaction):
        await self.cog.pixel_farbe_waehlen(itx, str(self.x), str(self.y))


class FarbSelect(discord.ui.Select):
    def __init__(self, cog: "Kreativ", x: str, y: str):
        self.cog = cog
        self.x = x
        self.y = y
        options = [discord.SelectOption(label=name, value=hexcode, emoji=icon)
                  for name, hexcode, icon in FARBPALETTE]
        super().__init__(placeholder="Farbe wählen...", options=options)

    async def callback(self, itx: discord.Interaction):
        await self.cog.pixel_setzen(itx, self.x, self.y, self.values[0])


class FarbView(discord.ui.View):
    def __init__(self, cog: "Kreativ", x: str, y: str):
        super().__init__(timeout=120)
        self.add_item(FarbSelect(cog, x, y))


class TraumTimelineView(discord.ui.View):
    def __init__(self, rows: list):
        super().__init__(timeout=300)
        self.rows = rows
        self.index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.zurueck.disabled = self.index <= 0
        self.vor.disabled = self.index >= len(self.rows) - 1

    def embed(self) -> discord.Embed:
        r = self.rows[self.index]
        d = dt.date.fromisoformat(r["datum"])
        e = emb("liebe", f"💭 Traum von {config.name_of(r['von'])}", f"{r['text']}\n\n— {d:%d.%m.%Y}")
        e.set_footer(text=f"Traum {self.index + 1}/{len(self.rows)}")
        return e

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def zurueck(self, itx: discord.Interaction, _button: discord.ui.Button):
        self.index -= 1
        self._update_buttons()
        await itx.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def vor(self, itx: discord.Interaction, _button: discord.ui.Button):
        self.index += 1
        self._update_buttons()
        await itx.response.edit_message(embed=self.embed(), view=self)


class Kreativ(commands.Cog):
    pixel_group = app_commands.Group(name="pixel", description="Gemeinsames Pixel-Canvas.")
    traum_group = app_commands.Group(name="traum", description="Traum-Tagebuch.")
    bucket_group = app_commands.Group(name="bucket", description="Bucket List.")

    def __init__(self, bot):
        self.bot = bot

    # ---------- Pixel-Canvas ----------
    @pixel_group.command(name="setzen", description="Setzt einen Pixel im gemeinsamen Canvas (5/Tag).")
    async def pixel(self, itx: discord.Interaction):
        await itx.response.send_modal(PixelModal(self))

    async def pixel_farbe_waehlen(self, itx: discord.Interaction, x_str: str, y_str: str):
        heute = dt.datetime.now(config.TZ).date().isoformat()
        quota_row = await self.bot.db.fetchone(
            "SELECT gesetzt FROM pixel_quota WHERE user_id = ? AND datum = ?", itx.user.id, heute)
        gesetzt = quota_row["gesetzt"] if quota_row else 0
        if gesetzt >= 5:
            await itx.response.send_message("Du hast heute schon alle 5 Pixel gesetzt!",
                                            ephemeral=True)
            return
        try:
            x, y = int(x_str), int(y_str)
        except ValueError:
            await itx.response.send_message("⚠️ X und Y müssen Zahlen sein.", ephemeral=True)
            return
        if not (0 <= x < 32 and 0 <= y < 32):
            await itx.response.send_message("⚠️ X und Y müssen zwischen 0 und 31 liegen.",
                                            ephemeral=True)
            return
        await itx.response.send_message(
            f"Pixel ({x}, {y}) – welche Farbe soll's werden?",
            view=FarbView(self, str(x), str(y)), ephemeral=True)

    async def pixel_setzen(self, itx: discord.Interaction, x_str: str, y_str: str, farbe_str: str):
        x, y = int(x_str), int(y_str)
        heute = dt.datetime.now(config.TZ).date().isoformat()
        quota_row = await self.bot.db.fetchone(
            "SELECT gesetzt FROM pixel_quota WHERE user_id = ? AND datum = ?", itx.user.id, heute)
        gesetzt = quota_row["gesetzt"] if quota_row else 0
        if gesetzt >= 5:
            await itx.response.edit_message(
                content="Du hast heute schon alle 5 Pixel gesetzt!", view=None)
            return
        farbe_clean = farbe_str.strip().lstrip("#").upper()
        await self.bot.db.execute(
            "INSERT INTO pixel_canvas (x, y, farbe, von) VALUES (?,?,?,?) "
            "ON CONFLICT(x,y) DO UPDATE SET farbe = excluded.farbe, von = excluded.von, "
            "ts = datetime('now')", x, y, farbe_clean, itx.user.id)
        await self.bot.db.execute(
            "INSERT INTO pixel_quota (user_id, datum, gesetzt) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, datum) DO UPDATE SET gesetzt = gesetzt + 1", itx.user.id, heute)
        await self._sync_canvas()
        await itx.response.edit_message(
            content=f"Pixel ({x}, {y}) gesetzt! Noch {4 - gesetzt} übrig heute.", view=None)

    async def _build_canvas(self):
        rows = await self.bot.db.fetchall("SELECT * FROM pixel_canvas")
        pixel_map = {(r["x"], r["y"]): r["farbe"] for r in rows}
        datei = discord.File(render_pixel_canvas(pixel_map), filename="canvas.png")
        e = emb("liebe", "🎨 Euer Pixel-Canvas",
               f"{len(rows)}/{32 * 32} Pixel gesetzt · `/pixel setzen` zum Mitmalen")
        e.set_image(url="attachment://canvas.png")
        return e, datei

    async def _sync_canvas(self):
        ch = self.bot.channel_by_name("pixel-canvas")
        await tracked.sync(self.bot, "pixel_canvas_msg", "global", ch, self._build_canvas)

    @pixel_group.command(name="canvas", description="Zeigt das aktuelle Pixel-Canvas.")
    async def canvas_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, "pixel_canvas_msg", "global", itx.channel,
                                 self._build_canvas)
        await itx.followup.send(f"Canvas aktuell: {msg.jump_url}" if msg else "Canvas ist leer.",
                                ephemeral=True)

    # ---------- Foto des Tages ----------
    @app_commands.command(name="foto_add", description="Teilt dein Foto des Tages.")
    @app_commands.describe(bild="Das Bild")
    async def foto_add(self, itx: discord.Interaction, bild: discord.Attachment):
        heute = dt.datetime.now(config.TZ).date()
        vorhanden = await self.bot.db.fetchone(
            "SELECT 1 FROM fotos WHERE von = ? AND datum = ?", itx.user.id, heute.isoformat())
        if vorhanden:
            await itx.response.send_message("Du hast heute schon ein Foto geteilt!", ephemeral=True)
            return
        await self.bot.db.execute("INSERT INTO fotos (von, datum, url) VALUES (?,?,?)",
                                  itx.user.id, heute.isoformat(), bild.url)
        streak = await self._foto_streak(itx.user.id, heute)
        ch = self.bot.channel_by_name("foto-des-tages")
        e = emb("liebe", f"📸 Foto des Tages – {config.name_of(itx.user.id)}",
               f"Streak: **{streak}** Tag{'e' if streak != 1 else ''}")
        e.set_image(url=bild.url)
        if ch:
            await ch.send(embed=e)
        await itx.response.send_message("Foto geteilt!", ephemeral=True)

    async def _foto_streak(self, user_id: int, heute: dt.date) -> int:
        streak = 0
        tag = heute
        while True:
            row = await self.bot.db.fetchone(
                "SELECT 1 FROM fotos WHERE von = ? AND datum = ?", user_id, tag.isoformat())
            if not row:
                break
            streak += 1
            tag -= dt.timedelta(days=1)
        return streak

    # ---------- Traum-Tagebuch ----------
    @traum_group.command(name="add", description="Trägt einen Traum ins Traum-Tagebuch ein.")
    @app_commands.describe(text="Was hast du geträumt?",
                           datum="Format TT.MM.JJJJ (optional, Standard: heute)")
    async def traum(self, itx: discord.Interaction, text: str, datum: str | None = None):
        if datum:
            try:
                d = dt.datetime.strptime(datum, "%d.%m.%Y").date()
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.", ephemeral=True)
                return
        else:
            d = dt.datetime.now(config.TZ).date()
        await self.bot.db.execute("INSERT INTO traeume (von, datum, text) VALUES (?,?,?)",
                                  itx.user.id, d.isoformat(), text)
        ch = self.bot.channel_by_name("traum-tagebuch")
        if ch:
            await ch.send(embed=emb("liebe", f"💭 Traum von {config.name_of(itx.user.id)}",
                                    f"{text}\n\n— {d:%d.%m.%Y}"))
        await itx.response.send_message("Traum gespeichert.", ephemeral=True)

    @traum_group.command(name="timeline", description="Blättert durch die Träume.")
    async def traum_timeline(self, itx: discord.Interaction):
        rows = await self.bot.db.fetchall("SELECT * FROM traeume ORDER BY datum DESC")
        if not rows:
            await itx.response.send_message("Noch keine Träume – `/traum add` legt los!",
                                            ephemeral=True)
            return
        view = TraumTimelineView(rows)
        await itx.response.send_message(embed=view.embed(), view=view)

    # ---------- Bucket List ----------
    async def _bucket_offen_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, item FROM bucketlist WHERE erledigt = 0")
        return [app_commands.Choice(name=r["item"][:100], value=r["id"])
                for r in rows if current.lower() in r["item"].lower()][:25]

    async def _bucket_alle_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, item FROM bucketlist")
        return [app_commands.Choice(name=r["item"][:100], value=r["id"])
                for r in rows if current.lower() in r["item"].lower()][:25]

    @bucket_group.command(name="add", description="Fügt etwas zur Bucket List hinzu.")
    async def bucket_add(self, itx: discord.Interaction, item: str):
        await self.bot.db.execute("INSERT INTO bucketlist (item, added_by) VALUES (?,?)",
                                  item, itx.user.id)
        await self._sync_bucket()
        await itx.response.send_message(f"„{item}“ zur Bucket List hinzugefügt.", ephemeral=True)

    @bucket_group.command(name="abhaken", description="Hakt einen Bucket-List-Punkt ab.")
    @app_commands.autocomplete(item=_bucket_offen_autocomplete)
    async def bucket_abhaken(self, itx: discord.Interaction, item: int):
        row = await self.bot.db.fetchone("SELECT * FROM bucketlist WHERE id = ?", item)
        if not row:
            await itx.response.send_message("⚠️ Eintrag nicht gefunden.", ephemeral=True)
            return
        heute = dt.datetime.now(config.TZ).date().isoformat()
        await self.bot.db.execute(
            "UPDATE bucketlist SET erledigt = 1, erledigt_am = ? WHERE id = ?", heute, item)
        await self._sync_bucket()
        ch = self.bot.channel_by_name("bucket-list")
        if ch:
            await ch.send(embed=emb("gruen", "Abgehakt!", f"**{row['item']}** ist geschafft!"))
        await itx.response.send_message(f"„{row['item']}“ abgehakt!", ephemeral=True)

    @bucket_group.command(name="delete", description="Entfernt einen Bucket-List-Punkt.")
    @app_commands.autocomplete(item=_bucket_alle_autocomplete)
    async def bucket_delete(self, itx: discord.Interaction, item: int):
        row = await self.bot.db.fetchone("SELECT * FROM bucketlist WHERE id = ?", item)
        if not row:
            await itx.response.send_message("⚠️ Eintrag nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM bucketlist WHERE id = ?", item)
        await self._sync_bucket()
        await itx.response.send_message(f"„{row['item']}“ gelöscht.", ephemeral=True)

    async def _build_bucket(self):
        rows = await self.bot.db.fetchall("SELECT * FROM bucketlist ORDER BY erledigt, id")
        if not rows:
            return emb("info", "🪣 Bucket List", "Noch leer – `/bucket add` legt los!"), None
        zeilen = [f"{'✅' if r['erledigt'] else '⬜'} {r['item']}" for r in rows]
        erledigt_n = sum(1 for r in rows if r["erledigt"])
        return emb("info", f"🪣 Bucket List ({erledigt_n}/{len(rows)})", "\n".join(zeilen)), None

    async def _sync_bucket(self):
        ch = self.bot.channel_by_name("bucket-list")
        await tracked.sync(self.bot, "bucket_liste", "global", ch, self._build_bucket)

    @bucket_group.command(name="liste", description="Zeigt die Bucket List.")
    async def bucket_liste_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, "bucket_liste", "global", itx.channel, self._build_bucket)
        await itx.followup.send(f"Bucket List aktuell: {msg.jump_url}" if msg else "Noch leer.",
                                ephemeral=True)


async def setup(bot):
    await bot.add_cog(Kreativ(bot))
