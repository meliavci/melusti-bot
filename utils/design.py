"""
Design-System für alle Bot-Nachrichten.
Jede Kategorie hat ihre feste Farbe, jedes Embed denselben Look –
so fühlt sich der Server wie EIN Produkt an, nicht wie Bot-Spam.
"""
import calendar as _calendar
from datetime import date, datetime
import io
import math

import discord
from PIL import Image, ImageDraw, ImageFont

import config

# Farbige Emoji-Fonts sind plattformabhängig (Windows: Segoe UI Emoji,
# Linux-Hosting: Noto Color Emoji, falls installiert). Fehlt beides,
# lassen wir das Emoji einfach weg statt abzustürzen.
_EMOJI_FONT_PATHS = [
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-emoji/NotoColorEmoji.ttf",
]
_emoji_font_cache: dict[int, "ImageFont.FreeTypeFont | None"] = {}


def _emoji_font(size: int):
    if size not in _emoji_font_cache:
        font = None
        for path in _EMOJI_FONT_PATHS:
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        _emoji_font_cache[size] = font
    return _emoji_font_cache[size]


def _draw_emoji(d: ImageDraw.ImageDraw, xy: tuple[float, float], emoji: str,
                size: int, anchor: str = "mm"):
    """Zeichnet ein farbiges Emoji, falls eine passende Schrift verfügbar ist."""
    font = _emoji_font(size)
    if font is None:
        return
    try:
        d.text(xy, emoji, font=font, embedded_color=True, anchor=anchor)
    except Exception:
        pass


# PILs eingebauter Bitmap-Font (über font_size) kann keine Umlaute/Gedankenstriche –
# für Kalender-Text brauchen wir eine echte TTF-Schrift, mit Fallback pro Plattform.
_TEXT_FONT_PATHS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]
_text_font_cache: dict[int, "ImageFont.FreeTypeFont | None"] = {}


def _text_font(size: int):
    if size not in _text_font_cache:
        font = None
        for path in _TEXT_FONT_PATHS:
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        _text_font_cache[size] = font
    return _text_font_cache[size]


def _draw_text(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
              size: int, fill, anchor: str | None = None):
    """Zeichnet Text mit echter TTF-Schrift; fällt ohne TTF auf font_size zurück."""
    font = _text_font(size)
    if font is not None:
        d.text(xy, text, font=font, fill=fill, anchor=anchor)
    else:
        d.text(xy, text, fill=fill, font_size=size, anchor=anchor)

# ---------- Farbpalette ----------
COLORS = {
    "melusti":  0x3DDC6A,   # frisches Grün – Melustis Farbe
    "checkin":  0xFFC93C,   # warmes Amber
    "gruen":    0x3DDC6A,
    "gelb":     0xFFC93C,
    "rot":      0xFF5D5D,
    "liebe":    0xFF7AA2,   # rosé – Lebenszeichen, Komplimente, Zeitkapsel
    "medien":   0x9B7BFF,   # lila – Filme, YouTube, Musik
    "spiele":   0xFF9F45,   # orange – Zocken, Wetten
    "info":     0x5CB8FF,   # blau – Kalender, Meilensteine, Listen
    "neutral":  0x2B2D31,
}

AMPEL_EMOJI = {"gruen": "🟢", "gelb": "🟡", "rot": "🔴"}


def emb(kind: str, title: str, desc: str = "", *, footer: str | None = None) -> discord.Embed:
    """Einheitliche Embed-Fabrik."""
    e = discord.Embed(
        title=title,
        description=desc,
        color=COLORS.get(kind, COLORS["neutral"]),
        timestamp=datetime.now(config.TZ),
    )
    e.set_footer(text=footer or "Melusti 🌱 euer gemeinsamer Server")
    return e


def progress_bar(value: int, maximum: int, length: int = 10) -> str:
    """Hübsche Fortschrittsleiste: ▰▰▰▰▱▱▱▱▱▱"""
    maximum = max(maximum, 1)
    filled = round(min(value, maximum) / maximum * length)
    return "▰" * filled + "▱" * (length - filled)


# ============================================================
#  Melusti-Renderer (PIL) – zeichnet das Wesen je nach Stimmung/Stufe
# ============================================================

BODY = {
    "ei":     (232, 224, 210),
    "baby":   (155, 226, 178),
    "kind":   (100, 220, 140),
    "teen":   (61, 220, 106),
    "legend": (61, 220, 180),
}


def render_melusti(stage: str, mood: str) -> io.BytesIO:
    """Rendert Melusti als 512x512-PNG mit transparentem Hintergrund."""
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 + 30

    body_col = BODY.get(stage, BODY["baby"])
    dark = tuple(max(0, c - 60) for c in body_col)

    if stage == "ei":
        # Ei mit Sprenkeln
        d.ellipse([cx - 130, cy - 170, cx + 130, cy + 150], fill=body_col,
                  outline=dark, width=8)
        for sx, sy, r in [(-50, -60, 18), (40, -20, 14), (-10, 60, 20), (60, 70, 12)]:
            d.ellipse([cx + sx - r, cy + sy - r, cx + sx + r, cy + sy + r],
                      fill=(190, 210, 170))
        if mood == "strahlend":  # kurz vorm Schlüpfen: Riss
            d.line([cx - 60, cy - 10, cx - 20, cy + 20, cx + 20, cy - 15,
                    cx + 60, cy + 10], fill=dark, width=7, joint="curve")
    else:
        # Blob-Körper
        d.ellipse([cx - 150, cy - 130, cx + 150, cy + 150], fill=body_col,
                  outline=dark, width=8)
        # Blatt-Antenne 🌱
        d.line([cx, cy - 128, cx, cy - 180], fill=(90, 160, 90), width=10)
        d.ellipse([cx - 4, cy - 218, cx + 44, cy - 172], fill=(120, 200, 110))
        # Bäckchen
        for bx in (-95, 95):
            d.ellipse([cx + bx - 22, cy + 18, cx + bx + 22, cy + 50],
                      fill=(255, 170, 180, 180))

        eye_y = cy - 30
        if mood == "schlafend":
            for ex in (-60, 60):
                d.arc([cx + ex - 26, eye_y - 8, cx + ex + 26, eye_y + 28],
                      start=200, end=340, fill=(40, 50, 45), width=9)
            d.text((cx + 150, cy - 190), "z", fill=(120, 130, 125), font_size=44)
            d.text((cx + 185, cy - 240), "z", fill=(150, 160, 155), font_size=58)
        elif mood == "quengelig":
            for ex in (-60, 60):
                d.ellipse([cx + ex - 18, eye_y - 18, cx + ex + 18, eye_y + 18],
                          fill=(40, 50, 45))
            d.arc([cx - 45, cy + 55, cx + 45, cy + 115], start=200, end=340,
                  fill=(40, 50, 45), width=9)  # trauriger Mund
            d.ellipse([cx - 110, eye_y - 55, cx - 80, eye_y - 25],
                      fill=(140, 190, 255))    # Schweißtropfen
        elif mood == "zufrieden":
            for ex in (-60, 60):
                d.ellipse([cx + ex - 18, eye_y - 18, cx + ex + 18, eye_y + 18],
                          fill=(40, 50, 45))
            d.arc([cx - 40, cy + 30, cx + 40, cy + 90], start=20, end=160,
                  fill=(40, 50, 45), width=9)
        elif mood == "krank":
            for ex in (-60, 60):  # X_X-Augen
                d.line([cx + ex - 16, eye_y - 16, cx + ex + 16, eye_y + 16],
                      fill=(40, 50, 45), width=8)
                d.line([cx + ex - 16, eye_y + 16, cx + ex + 16, eye_y - 16],
                      fill=(40, 50, 45), width=8)
            d.arc([cx - 45, cy + 55, cx + 45, cy + 115], start=200, end=340,
                  fill=(40, 50, 45), width=9)  # unwohler Mund
            # Fieberthermometer
            d.rounded_rectangle([cx + 85, cy - 65, cx + 105, cy - 5], radius=8,
                                fill=(235, 235, 235), outline=dark, width=4)
            d.ellipse([cx + 82, cy - 15, cx + 108, cy + 11], fill=(230, 70, 70),
                      outline=dark, width=4)
            d.rectangle([cx + 92, cy - 45, cx + 98, cy - 8], fill=(230, 70, 70))
        else:  # strahlend
            for ex in (-60, 60):  # ^_^ Augen
                d.arc([cx + ex - 26, eye_y - 20, cx + ex + 26, eye_y + 20],
                      start=200, end=340, fill=(40, 50, 45), width=10)
            d.chord([cx - 55, cy + 20, cx + 55, cy + 105], start=0, end=180,
                    fill=(200, 90, 100), outline=(40, 50, 45), width=7)
            # Funkel-Sterne
            for sx, sy in [(-190, -140), (190, -110), (-170, 80)]:
                _star(d, cx + sx, cy + sy, 16, (255, 220, 120))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _star(d: ImageDraw.ImageDraw, x: int, y: int, r: int, col):
    d.polygon([(x, y - r), (x + r // 3, y - r // 3), (x + r, y),
               (x + r // 3, y + r // 3), (x, y + r), (x - r // 3, y + r // 3),
               (x - r, y), (x - r // 3, y - r // 3)], fill=col)


# ============================================================
#  Kalender-Renderer (PIL) – Monats- & Jahresansicht mit Meilensteinen
# ============================================================

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
               "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _rgb(color: int) -> tuple[int, int, int]:
    return (color >> 16 & 255, color >> 8 & 255, color & 255)


def _blend(bg: tuple[int, int, int], fg: tuple[int, int, int], anteil: float) -> tuple[int, int, int]:
    """Mischt fg über bg (kein echtes Alpha nötig, da d.rounded_rectangle auf
    RGBA-Bildern nicht blendet, sondern Pixel einfach überschreibt)."""
    return tuple(round(b * (1 - anteil) + f * anteil) for b, f in zip(bg, fg))


def render_kalender(jahr: int, monat: int, heute: date, meilensteine: list[dict],
                    termine: list[dict] = ()) -> io.BytesIO:
    """
    Rendert eine Monatsansicht als Karte.
    `meilensteine`: Dicts mit 'name', 'emoji', 'datum' (date) – jährlich
    wiederkehrende Jubiläen, markiert mit rosa Kreis + eigenem Emoji an
    Tag+Monat des Jubiläums.
    `termine`: Dicts mit 'name', 'emoji', 'von', 'bis' (date) – konkrete
    (mehrtägige) Termine, als blaues Band dargestellt.
    Unter dem Raster steht eine Legende mit Tag-Nummer, damit klar ist,
    welcher markierte Tag zu welchem Eintrag gehört.
    """
    W = 900
    margin = 30
    header_h = 140
    weekday_h = 50
    row_h = 110

    weeks = _calendar.Calendar(firstweekday=0).monthdayscalendar(jahr, monat)

    jub_matches = [
        (day, m) for woche in weeks for day in woche if day
        for m in meilensteine if m["datum"].month == monat and m["datum"].day == day
    ]
    termin_matches = [
        (t, max(t["von"], date(jahr, monat, 1)))
        for t in termine
        if t["von"] <= date(jahr, monat, _calendar.monthrange(jahr, monat)[1])
        and t["bis"] >= date(jahr, monat, 1)
    ]

    legend_lines = (len(jub_matches) or 1) + (len(termin_matches) if termin_matches else 0)
    if termin_matches:
        legend_lines += 1  # Extra-Überschrift "Termine"
    grid_h = weekday_h + row_h * len(weeks)
    legend_h = 50 + legend_lines * 42 + 30
    H = margin * 2 + header_h + grid_h + legend_h

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([margin, margin, W - margin, H - margin], radius=40,
                        fill=_rgb(COLORS["neutral"]))

    _draw_text(d, (W / 2, margin + 60), f"{MONATE[monat - 1]} {jahr}",
              52, (255, 255, 255), anchor="mm")

    grid_left, grid_right = 80, W - 80
    cell_w = (grid_right - grid_left) / 7
    grid_top = margin + header_h
    for i, wd in enumerate(WOCHENTAGE):
        cx = grid_left + cell_w * i + cell_w / 2
        _draw_text(d, (cx, grid_top), wd, 24, (160, 165, 175), anchor="mm")

    grid_start_y = grid_top + weekday_h
    termin_farbe = _blend(_rgb(COLORS["neutral"]), _rgb(COLORS["info"]), 0.35)
    for row, woche in enumerate(weeks):
        for col, day in enumerate(woche):
            if day == 0:
                continue
            cx = grid_left + cell_w * col + cell_w / 2
            cy = grid_start_y + row_h * row + row_h / 2
            day_date = date(jahr, monat, day)
            is_today = day_date == heute
            in_termin = any(t["von"] <= day_date <= t["bis"] for t in termine)
            full_hit = next((m for m in meilensteine if m["datum"].month == monat
                            and m["datum"].day == day), None)

            if in_termin:
                d.rounded_rectangle(
                    [grid_left + cell_w * col + 4, cy - row_h / 2 + 6,
                     grid_left + cell_w * (col + 1) - 4, cy + row_h / 2 - 6],
                    radius=14, fill=termin_farbe)
            if full_hit:
                d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], fill=_rgb(COLORS["liebe"]))
            if is_today:
                d.ellipse([cx - 36, cy - 36, cx + 36, cy + 36],
                         outline=_rgb(COLORS["gruen"]), width=5)

            num_col = (40, 20, 28) if full_hit else (255, 255, 255)
            _draw_text(d, (cx, cy - (14 if full_hit else 0)), str(day), 28, num_col,
                      anchor="mm")
            if full_hit:
                _draw_emoji(d, (cx, cy + 22), full_hit["emoji"], 26)

    ly = grid_start_y + row_h * len(weeks) + 30
    _draw_text(d, (grid_left, ly), "Jubiläen diesen Monat", 26, (200, 200, 205))
    ly += 44
    if jub_matches:
        for day, m in jub_matches:
            tage = (date(jahr, monat, day) - m["datum"]).days
            _draw_emoji(d, (grid_left + 14, ly + 14), m["emoji"], 26, anchor="mm")
            _draw_text(d, (grid_left + 36, ly),
                      f"{day:02d}. – {m['name']} – seit {tage} Tagen",
                      25, (255, 255, 255))
            ly += 42
    else:
        _draw_text(d, (grid_left, ly), "Keine – genießt den ruhigen Monat",
                  25, (160, 165, 175))
        ly += 42

    if termin_matches:
        ly += 8
        _draw_text(d, (grid_left, ly), "Termine", 26, (200, 200, 205))
        ly += 44
        for t, _ in termin_matches:
            zeitraum = f"{t['von']:%d.%m.}" + (f"–{t['bis']:%d.%m.}" if t["bis"] != t["von"] else "")
            _draw_emoji(d, (grid_left + 14, ly + 14), t["emoji"], 26, anchor="mm")
            _draw_text(d, (grid_left + 36, ly), f"{zeitraum} – {t['name']}",
                      25, (255, 255, 255))
            ly += 42

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def render_jahresblick(jahr: int, heute: date, meilensteine: list[dict],
                       termine: list[dict] = ()) -> io.BytesIO:
    """
    Rendert alle 12 Monate als Mini-Kalender im 4x3-Raster (Jubiläen rosa,
    Termine blau, heute grün umrandet). Darunter steht zusätzlich eine
    Textliste aller Meilensteine & Termine, damit klar ist, was die
    Markierungen im Raster bedeuten.
    """
    cols, rows = 4, 3
    mini_w, mini_h = 340, 300
    margin = 30
    header_h = 110
    W = margin * 2 + cols * mini_w
    grid_h = rows * mini_h

    termine_jahr = [t for t in termine if t["von"].year <= jahr <= t["bis"].year]
    legend_lines = (len(meilensteine) or 1) + (len(termine_jahr) if termine_jahr else 0)
    if termine_jahr:
        legend_lines += 1  # "Termine"-Überschrift
    legend_h = 50 + legend_lines * 42 + 30

    H = margin * 2 + header_h + grid_h + legend_h

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([margin, margin, W - margin, H - margin], radius=40,
                        fill=_rgb(COLORS["neutral"]))
    _draw_text(d, (W / 2, margin + 55), f"Jahresblick {jahr}",
              48, (255, 255, 255), anchor="mm")

    cal = _calendar.Calendar(firstweekday=0)
    for monat in range(1, 13):
        col = (monat - 1) % cols
        row = (monat - 1) // cols
        ox = margin + col * mini_w + 20
        oy = margin + header_h + row * mini_h + 10

        _draw_text(d, (ox + (mini_w - 40) / 2, oy), MONATE_KURZ[monat - 1],
                  24, (210, 210, 215), anchor="mm")

        weeks = cal.monthdayscalendar(jahr, monat)
        cell = (mini_w - 40) / 7
        grid_top = oy + 26
        for r, woche in enumerate(weeks):
            for c, day in enumerate(woche):
                if day == 0:
                    continue
                cx = ox + cell * c + cell / 2
                cy = grid_top + cell * r + cell / 2
                day_date = date(jahr, monat, day)
                is_today = day_date == heute
                is_jub = any(m["datum"].month == monat and m["datum"].day == day
                            for m in meilensteine)
                in_termin = (not is_jub) and any(t["von"] <= day_date <= t["bis"]
                                                 for t in termine)
                if is_jub:
                    d.ellipse([cx - cell * 0.4, cy - cell * 0.4,
                             cx + cell * 0.4, cy + cell * 0.4], fill=_rgb(COLORS["liebe"]))
                elif in_termin:
                    d.ellipse([cx - cell * 0.4, cy - cell * 0.4,
                             cx + cell * 0.4, cy + cell * 0.4],
                             fill=_blend(_rgb(COLORS["neutral"]), _rgb(COLORS["info"]), 0.6))
                if is_today:
                    d.ellipse([cx - cell * 0.42, cy - cell * 0.42,
                             cx + cell * 0.42, cy + cell * 0.42],
                             outline=_rgb(COLORS["gruen"]), width=2)
                _draw_text(d, (cx, cy), str(day),
                          max(10, int(cell * 0.55)),
                          (40, 20, 28) if (is_jub or in_termin) else (200, 200, 205), anchor="mm")

    ly = margin + header_h + grid_h + 20
    _draw_text(d, (margin + 20, ly), "Jubiläen", 26, (200, 200, 205))
    ly += 44
    if meilensteine:
        for m in meilensteine:
            _draw_emoji(d, (margin + 34, ly + 14), m["emoji"], 26, anchor="mm")
            _draw_text(d, (margin + 56, ly), f"{m['name']} – {m['datum']:%d.%m.}",
                      25, (255, 255, 255))
            ly += 42
    else:
        _draw_text(d, (margin + 20, ly), "Noch keine Meilensteine", 25, (160, 165, 175))
        ly += 42

    if termine_jahr:
        ly += 8
        _draw_text(d, (margin + 20, ly), "Termine", 26, (200, 200, 205))
        ly += 44
        for t in termine_jahr:
            zeitraum = f"{t['von']:%d.%m.}" + (f"–{t['bis']:%d.%m.}" if t["bis"] != t["von"] else "")
            _draw_emoji(d, (margin + 34, ly + 14), t["emoji"], 26, anchor="mm")
            _draw_text(d, (margin + 56, ly), f"{zeitraum} – {t['name']}",
                      25, (255, 255, 255))
            ly += 42

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ============================================================
#  Entscheidungsrad (PIL) – animiertes GIF, landet beim Gewinner
# ============================================================

_RAD_FARBEN = [COLORS["liebe"], COLORS["info"], COLORS["spiele"], COLORS["gruen"],
              COLORS["medien"], COLORS["gelb"]]


def render_entscheidungsrad(optionen: list[str], gewinner_index: int) -> io.BytesIO:
    """
    Rendert ein sich drehendes Rad als GIF, das bei `optionen[gewinner_index]`
    zum Stehen kommt (Pfeil zeigt immer nach oben).
    """
    size = 500
    cx, cy = size // 2, size // 2
    radius = size // 2 - 20
    n = len(optionen)
    slice_winkel = 360 / n

    # Zielwinkel: Mitte des Gewinner-Segments soll unter dem Pfeil (oben, -90°) liegen.
    ziel_mitte = gewinner_index * slice_winkel + slice_winkel / 2
    ziel_rotation = -90 - ziel_mitte

    frames = []
    n_frames = 24
    umdrehungen = 3
    for f in range(n_frames):
        t = f / (n_frames - 1)
        eased = 1 - (1 - t) ** 3  # ease-out: schnell los, sanft bremsen
        aktueller_winkel = -umdrehungen * 360 * (1 - eased) + eased * ziel_rotation
        frames.append(_rad_frame(size, cx, cy, radius, optionen, slice_winkel, aktueller_winkel))

    # Pillow verwirft identische Folge-Frames beim GIF-Export automatisch – statt
    # den letzten Frame zu duplizieren, bekommt er einfach eine lange Anzeigedauer.
    dauern = [70] * (len(frames) - 1) + [2500]

    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=dauern, loop=1, disposal=2)
    buf.seek(0)
    return buf


def _rad_frame(size, cx, cy, radius, optionen, slice_winkel, rotation) -> Image.Image:
    # Volltonfarbe statt Transparenz: GIFs kennen nur binäre Transparenz,
    # ein durchgehender Kartenhintergrund umgeht das Problem sauber.
    img = Image.new("RGB", (size, size), _rgb(COLORS["neutral"]))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - radius - 8, cy - radius - 8, cx + radius + 8, cy + radius + 8],
             fill=_rgb(COLORS["neutral"]))
    for i, opt in enumerate(optionen):
        start = rotation + i * slice_winkel
        d.pieslice([cx - radius, cy - radius, cx + radius, cy + radius],
                  start=start, end=start + slice_winkel,
                  fill=_rgb(_RAD_FARBEN[i % len(_RAD_FARBEN)]), outline=_rgb(COLORS["neutral"]),
                  width=3)
        mitte = math.radians(start + slice_winkel / 2)
        tx = cx + math.cos(mitte) * radius * 0.62
        ty = cy + math.sin(mitte) * radius * 0.62
        _draw_text(d, (tx, ty), opt[:16], 20, (255, 255, 255), anchor="mm")
    d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=_rgb(COLORS["neutral"]))
    # Pfeil oben, zeigt zur Mitte des Rads
    d.polygon([(cx - 16, cy - radius - 6), (cx + 16, cy - radius - 6), (cx, cy - radius + 22)],
              fill=_rgb(COLORS["liebe"]))
    return img


# ============================================================
#  Pixel-Canvas (PIL) – gemeinsames 32x32-Pixelbild
# ============================================================

def _hex_to_rgb(hexfarbe: str) -> tuple[int, int, int]:
    h = hexfarbe.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def render_pixel_canvas(pixel_map: dict[tuple[int, int], str], n: int = 32) -> io.BytesIO:
    """Rendert das Pixel-Canvas; `pixel_map` bildet (x, y) auf eine Hex-Farbe ab."""
    cell = 16
    margin = 24
    raster = n * cell
    W = H = raster + margin * 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([margin - 12, margin - 12, W - margin + 12, H - margin + 12],
                        radius=24, fill=_rgb(COLORS["neutral"]))

    leer = (60, 62, 68)
    for y in range(n):
        for x in range(n):
            farbe = pixel_map.get((x, y))
            rgb = _hex_to_rgb(farbe) if farbe else leer
            d.rectangle([margin + x * cell, margin + y * cell,
                        margin + (x + 1) * cell - 1, margin + (y + 1) * cell - 1], fill=rgb)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
