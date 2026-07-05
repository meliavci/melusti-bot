"""
Minimaler Spotify-Web-API-Client (Authorization Code Flow), ohne SDK.
Braucht SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET/SPOTIFY_REDIRECT_URI in der
.env. Da der Bot keinen eigenen Webserver für den OAuth-Redirect hat, wird
der Autorisierungs-Code manuell aus der Browser-Adresszeile kopiert
(siehe /spotify_login in cogs/musik.py).
"""
import base64
from urllib.parse import urlencode

import aiohttp

import config

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"


def login_url(state: str) -> str:
    params = {
        "client_id": config.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.SPOTIFY_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _basic_auth_header() -> dict:
    roh = f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode()
    return {"Authorization": "Basic " + base64.b64encode(roh).decode()}


async def exchange_code(code: str) -> dict:
    """Tauscht den einmaligen Autorisierungs-Code gegen Access-/Refresh-Token."""
    data = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": config.SPOTIFY_REDIRECT_URI}
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=data, headers=_basic_auth_header()) as resp:
            resp.raise_for_status()
            return await resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=data, headers=_basic_auth_header()) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _api(method: str, path: str, access_token: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, f"{API_BASE}{path}", headers=headers, **kwargs) as resp:
            resp.raise_for_status()
            if resp.status == 204 or resp.content_length == 0:
                return None
            return await resp.json()


async def me(access_token: str) -> dict:
    return await _api("GET", "/me", access_token)


async def search_track(access_token: str, query: str) -> dict | None:
    ergebnis = await _api("GET", "/search", access_token,
                          params={"q": query, "type": "track", "limit": 1})
    items = ergebnis.get("tracks", {}).get("items", [])
    return items[0] if items else None


async def create_playlist(access_token: str, spotify_user_id: str, name: str) -> dict:
    return await _api("POST", f"/users/{spotify_user_id}/playlists", access_token,
                      json={"name": name, "public": False, "collaborative": True})


async def get_playlist(access_token: str, playlist_id: str) -> dict:
    return await _api("GET", f"/playlists/{playlist_id}", access_token,
                      params={"fields": "id,name,external_urls"})


async def add_track(access_token: str, playlist_id: str, track_uri: str):
    # Spotify hat den Endpunkt am 11.02.2026 von /tracks auf /items umgestellt
    # (alter Pfad liefert seitdem nur noch ein generisches 403 ohne Erklärung).
    await _api("POST", f"/playlists/{playlist_id}/items", access_token,
              json={"uris": [track_uri]})


async def remove_track(access_token: str, playlist_id: str, track_uri: str):
    # Live verifiziert: DELETE /items braucht {"items": [{"uri": ...}]} –
    # weder {"uris": [...]} noch das alte {"tracks": [{"uri": ...}]} geht.
    await _api("DELETE", f"/playlists/{playlist_id}/items", access_token,
              json={"items": [{"uri": track_uri}]})


async def get_playlist_tracks(access_token: str, playlist_id: str) -> list[dict]:
    """Liefert ALLE Tracks der Playlist (Titel, Künstler, URI) – paginiert
    über /items, den Nachfolger von /tracks seit Spotifys API-Update vom
    11.02.2026. Damit erkennt der Bot auch Songs, die schon vor der
    Bot-Anbindung in der Playlist lagen, nicht nur über /song add."""
    tracks = []
    url = f"{API_BASE}/playlists/{playlist_id}/items"
    params = {"limit": 50}
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        while url:
            async with session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                body = await resp.json()
            for entry in body.get("items", []):
                item = entry.get("item")
                if not item or item.get("type") != "track":
                    continue
                tracks.append({
                    "titel": item.get("name", "?"),
                    "kuenstler": ", ".join(a["name"] for a in item.get("artists", [])),
                    "uri": item.get("uri"),
                })
            url = body.get("next")
            params = None  # 'next' enthält die Query-Parameter schon
    return tracks
