"""
Minimaler Steam-Web-API-Client für den Spiele-Tinder-Import.
Braucht STEAM_API_KEY (kostenlos & sofort unter steamcommunity.com/dev/apikey)
sowie STEAM_ID_MELI/STEAM_ID_JUSTI (SteamID64 oder Vanity-Name aus der
Profil-URL) in der .env. Die Spieleliste im Steam-Profil muss auf
"öffentlich" stehen, sonst liefert die API eine leere Liste.
"""
import aiohttp

API_BASE = "https://api.steampowered.com"


async def resolve_vanity(api_key: str, vanity: str) -> str | None:
    """Wandelt einen Profil-Namen in eine SteamID64 um (falls nötig)."""
    if vanity.isdigit() and len(vanity) >= 15:
        return vanity
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/ISteamUser/ResolveVanityURL/v1/",
                               params={"key": api_key, "vanityurl": vanity}) as resp:
            resp.raise_for_status()
            daten = await resp.json()
            antwort = daten.get("response", {})
            return antwort.get("steamid") if antwort.get("success") == 1 else None


async def get_owned_games(api_key: str, steamid: str) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/IPlayerService/GetOwnedGames/v1/",
                               params={"key": api_key, "steamid": steamid,
                                       "include_appinfo": 1, "format": "json"}) as resp:
            resp.raise_for_status()
            daten = await resp.json()
            return daten.get("response", {}).get("games", [])
