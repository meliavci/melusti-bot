"""
Minimaler Client für die inoffizielle HenrikDev-Valorant-API
(docs.henrikdev.xyz) – der einzig praktikable Weg an den aktuellen
individuellen Valorant-Rang, da die offizielle Riot-API dafür keinen
öffentlichen Endpunkt hat (nur Leaderboards).
Key holen: Discord discord.gg/X3GaVkX2YN beitreten, Bot gibt ihn direkt.
"""
import aiohttp

import config

API_BASE = "https://api.henrikdev.xyz"


class HenrikDevError(Exception):
    pass


async def get_mmr(region: str, name: str, tag: str, platform: str = "pc") -> dict:
    """Liefert die aktuellen MMR-Daten für einen Spieler (Name#Tag)."""
    if not config.HENRIKDEV_API_KEY:
        raise HenrikDevError("Kein HENRIKDEV_API_KEY in der .env hinterlegt.")
    url = f"{API_BASE}/valorant/v3/mmr/{region}/{platform}/{name}/{tag}"
    headers = {"Authorization": config.HENRIKDEV_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            body = await resp.json()
            if resp.status != 200:
                nachricht = body.get("errors", [{}])[0].get("message", f"HTTP {resp.status}")
                raise HenrikDevError(nachricht)
            return body.get("data", {})


def rang_text(daten: dict) -> tuple[str, int, int]:
    """Extrahiert (Rang-Name, RR, Änderung seit letztem Match) aus der
    tatsächlichen v3-Antwortstruktur: data.current.tier.name / .rr / .last_change."""
    current = daten.get("current", {}) or {}
    rang = current.get("tier", {}).get("name", "Unbekannt")
    rr = current.get("rr", 0)
    delta = current.get("last_change", 0)
    return rang, rr, delta


async def get_recent_matches(region: str, name: str, tag: str, size: int = 20,
                             platform: str = "pc") -> list[dict]:
    """Liefert die letzten `size` Competitive-Matches – Grundlage für aggregierte
    Form-Stats (KDA, Headshot-%, Winrate, Lieblings-Agent), die die reine
    MMR-Abfrage nicht hergibt."""
    if not config.HENRIKDEV_API_KEY:
        raise HenrikDevError("Kein HENRIKDEV_API_KEY in der .env hinterlegt.")
    url = f"{API_BASE}/valorant/v1/lifetime/matches/{region}/{name}/{tag}"
    headers = {"Authorization": config.HENRIKDEV_API_KEY}
    params = {"mode": "competitive", "size": size}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            body = await resp.json()
            if resp.status != 200:
                nachricht = body.get("errors", [{}])[0].get("message", f"HTTP {resp.status}")
                raise HenrikDevError(nachricht)
            return body.get("data", [])


def match_stats(matches: list[dict]) -> dict | None:
    """Aggregiert die letzten Matches zu KDA, Headshot-%, Winrate und Lieblings-Agent."""
    if not matches:
        return None
    kills = deaths = assists = head = koerper = beine = siege = 0
    agenten: dict[str, int] = {}
    for m in matches:
        s = m["stats"]
        kills += s["kills"]
        deaths += s["deaths"]
        assists += s["assists"]
        head += s["shots"]["head"]
        koerper += s["shots"]["body"]
        beine += s["shots"]["leg"]
        agent = s["character"]["name"]
        agenten[agent] = agenten.get(agent, 0) + 1
        team = s["team"].lower()
        gegner = "blue" if team == "red" else "red"
        if m["teams"].get(team, 0) > m["teams"].get(gegner, 0):
            siege += 1
    anzahl = len(matches)
    gesamt_schuesse = head + koerper + beine
    return {
        "anzahl": anzahl,
        "kd": round(kills / deaths, 2) if deaths else float(kills),
        "avg_kda": f"{kills / anzahl:.1f}/{deaths / anzahl:.1f}/{assists / anzahl:.1f}",
        "hs_prozent": round(100 * head / gesamt_schuesse) if gesamt_schuesse else 0,
        "winrate": round(100 * siege / anzahl),
        "top_agent": max(agenten, key=agenten.get),
    }


def voller_stats(daten: dict) -> dict:
    """Extrahiert alle verfügbaren Werte aus der v3-MMR-Antwort – nicht nur
    den aktuellen Rang, sondern auch Elo, Peak-Rang, Leaderboard-Platz und
    die Sieg/Niederlage-Bilanz der laufenden Season (letzter Eintrag in
    `seasonal`, verifiziert deckungsgleich mit `current` bei echten Daten)."""
    current = daten.get("current", {}) or {}
    peak = daten.get("peak", {}) or {}
    seasonal = daten.get("seasonal") or []
    season = seasonal[-1] if seasonal else {}
    spiele = season.get("games", 0)
    siege = season.get("wins", 0)
    return {
        "rang": current.get("tier", {}).get("name", "Unbekannt"),
        "rr": current.get("rr", 0),
        "elo": current.get("elo"),
        "delta": current.get("last_change", 0),
        "leaderboard_platz": current.get("leaderboard_placement"),
        "peak_rang": peak.get("tier", {}).get("name", "Unbekannt"),
        "season_spiele": spiele,
        "season_siege": siege,
        "season_niederlagen": spiele - siege,
        "season_winrate": round(100 * siege / spiele) if spiele else None,
    }
