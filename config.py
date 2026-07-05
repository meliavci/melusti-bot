"""Zentrale Konfiguration – Werte kommen aus der .env-Datei."""
import glob
import os
import shutil
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


def _find_ffmpeg() -> str | None:
    """Sucht ffmpeg im PATH, sonst am bekannten winget-Installationsort
    (falls die aktuelle Shell die frisch gesetzte PATH-Variable noch nicht
    kennt – winget braucht dafür einen Neustart des Terminals)."""
    gefunden = shutil.which("ffmpeg")
    if gefunden:
        return gefunden
    treffer = glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffmpeg.exe"))
    return treffer[0] if treffer else None


def _ensure_deno_on_path() -> None:
    """yt-dlp nutzt deno (falls vorhanden) zum Lösen von YouTube-JS-Challenges.
    Gleiches PATH-Problem wie bei ffmpeg nach winget-Installation – daher
    Installationsordner defensiv selbst suchen und vorn an PATH anhängen."""
    if shutil.which("deno"):
        return
    treffer = glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\DenoLand.Deno_*"))
    if treffer:
        os.environ["PATH"] = treffer[0] + os.pathsep + os.environ.get("PATH", "")


_ensure_deno_on_path()

TOKEN = os.getenv("DISCORD_TOKEN", "")
MELI_ID = int(os.getenv("MELI_ID", "0"))
JUSTI_ID = int(os.getenv("JUSTI_ID", "0"))
MELI_NAME = os.getenv("MELI_NAME", "Meli")
JUSTI_NAME = os.getenv("JUSTI_NAME", "Justi")

TZ = ZoneInfo("Europe/Berlin")
DB_PATH = os.getenv("DB_PATH", "moli.db")

# Cloud-Datenbank (Turso/libSQL) fürs Hosting – wenn gesetzt, wird statt der
# lokalen SQLite-Datei (DB_PATH) die Cloud-DB genutzt, damit die Daten auch
# auf Hosts ohne dauerhafte Festplatte (z.B. Render Free Tier) erhalten bleiben.
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# Port für den Keep-Alive-Webserver (Render setzt PORT selbst, lokal egal).
PORT = int(os.getenv("PORT", "8080"))

# Uhrzeit (Stunde, Europe/Berlin), zu der der tägliche Check-in spätestens angestoßen wird,
# falls ihr an dem Tag nicht zusammen im Call wart.
CHECKIN_HOUR = int(os.getenv("CHECKIN_HOUR", "21"))
# Uhrzeit für Wort des Tages / Countdown-Posts
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "11"))

# ---------- Optionale Integrationen ----------
# Letterboxd: öffentliche Profile, kein API-Key nötig.
LETTERBOXD_MELI = os.getenv("LETTERBOXD_MELI", "")
LETTERBOXD_JUSTI = os.getenv("LETTERBOXD_JUSTI", "")

# Spotify: Developer App unter developer.spotify.com/dashboard anlegen.
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# Riot Games API (Valorant): developer.riotgames.com.
# Achtung: liefert KEINEN individuellen Rang (nur Leaderboards) – für
# /valorant_rang wird stattdessen HENRIKDEV_API_KEY genutzt (s.u.).
RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")
RIOT_ID_MELI = os.getenv("RIOT_ID_MELI", "")   # Format: Name#TAG
RIOT_ID_JUSTI = os.getenv("RIOT_ID_JUSTI", "")
RIOT_REGION = os.getenv("RIOT_REGION", "eu")   # eu / na / ap / kr / latam / br

# HenrikDev API (inoffiziell, aber der einzig praktikable Weg an den
# aktuellen individuellen Valorant-Rang): Key per Discord/Dashboard, siehe
# docs.henrikdev.xyz.
HENRIKDEV_API_KEY = os.getenv("HENRIKDEV_API_KEY", "")

# Steam Web API (für /spiel steam_import): kostenloser Key, sofort unter
# steamcommunity.com/dev/apikey. STEAM_ID_MELI/JUSTI: SteamID64 oder
# Vanity-Name aus der Profil-URL. Spieleliste muss im Profil öffentlich sein.
STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")
STEAM_ID_MELI = os.getenv("STEAM_ID_MELI", "")
STEAM_ID_JUSTI = os.getenv("STEAM_ID_JUSTI", "")

# Musik-Wiedergabe im Voice-Channel (YouTube-Suche + ffmpeg, siehe cogs/musik.py).
FFMPEG_PATH = os.getenv("FFMPEG_PATH") or _find_ffmpeg()

COGS = [
    "cogs.setup_server",
    "cogs.melusti",
    "cogs.checkin",
    "cogs.lebenszeichen",
    "cogs.meilensteine",
    "cogs.zitate",
    "cogs.woerterbuch",
    "cogs.zeitkapsel",
    # Session 1 – Filmabend & Watchlists
    "cogs.filme",
    # Session 2 – Treffen, Tagebuch, Packliste, Countdown
    "cogs.treffen",
    "cogs.tagebuch",
    "cogs.packliste",
    # Session 3 – Zocken
    "cogs.zocken",
    # Session 4 – Streit-Modus
    "cogs.streit",
    # Session 5 – Kreativ & Alltag
    "cogs.kreativ",
    # Session 6 – Musik, Wetten & Stats
    "cogs.musik",
    "cogs.tippliga",
    "cogs.calls",
    "cogs.spielideen",
    "cogs.export",
    "cogs.zaubertricks",
    "cogs.witze",
    "cogs.handyladen",
    "cogs.hilfe",
]

COUPLE = {}  # wird in main.py gefüllt: {id: name}


def partner_of(user_id: int) -> int:
    return JUSTI_ID if user_id == MELI_ID else MELI_ID


def name_of(user_id: int) -> str:
    return MELI_NAME if user_id == MELI_ID else JUSTI_NAME


def is_couple(user_id: int) -> bool:
    return user_id in (MELI_ID, JUSTI_ID)


def slot_of(user_id: int) -> str:
    """'a' für Meli, 'b' für Justi – Konvention für Doppel-Spalten wie
    rating_a/rating_b, fairness_a/fairness_b, swipe_a/swipe_b."""
    return "a" if user_id == MELI_ID else "b"
