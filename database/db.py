"""Zentrale Datenbank-Schicht.

Lokal (kein TURSO_DATABASE_URL gesetzt) läuft alles über aiosqlite auf einer
lokalen Datei. Ist TURSO_DATABASE_URL gesetzt, geht stattdessen alles über
libsql_client an eine Turso-Cloud-Datenbank – nötig für Hosts ohne dauerhafte
Festplatte (z.B. Render Free Tier), damit die Daten Neustarts überleben.
Beide Zweige bedienen dieselbe execute/fetchone/fetchall-Schnittstelle, damit
Cogs den Unterschied nie merken.
"""
from pathlib import Path
import aiosqlite
import libsql_client

import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _sql_statements(script: str) -> list[str]:
    """Zerlegt schema.sql in einzelne Statements (libsql_client kann pro
    Aufruf nur ein Statement, anders als aiosqlite.executescript). Kommentare
    werden VOR dem Split auf ';' entfernt, da manche Kommentare selbst ein
    Semikolon enthalten (z.B. "-- ... beide;") und sonst ein Statement
    mittendrin zerreißen würden."""
    ohne_kommentare = "\n".join(zeile.split("--", 1)[0] for zeile in script.splitlines())
    statements = [s.strip() for s in ohne_kommentare.split(";")]
    return [s for s in statements if s and not s.upper().startswith("PRAGMA")]


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._client: libsql_client.Client | None = None

    @property
    def _remote(self) -> bool:
        return bool(config.TURSO_DATABASE_URL)

    async def init(self):
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        if self._remote:
            # https statt libsql/wss: einzelne HTTP-Requests pro Statement,
            # ohne dauerhafte Websocket-Verbindung – robuster für einen Bot
            # mit seltenen, sporadischen Abfragen.
            url = config.TURSO_DATABASE_URL.replace("libsql://", "https://", 1)
            self._client = libsql_client.create_client(
                url=url, auth_token=config.TURSO_AUTH_TOKEN)
            for stmt in _sql_statements(schema):
                await self._client.execute(stmt)
        else:
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(schema)
            await self._conn.commit()
        # Melusti-Zeile sicherstellen
        await self.execute("INSERT OR IGNORE INTO moli (id, xp) VALUES (1, 0)")
        await self._migrate_columns()

    async def _migrate_columns(self):
        """Ergänzt Spalten, die zu bestehenden Tabellen nachträglich dazugekommen
        sind (CREATE TABLE IF NOT EXISTS legt sie bei schon existierenden DBs
        nicht automatisch an)."""
        neue_spalten = [
            ("treffen", "datum_bis", "TEXT"),
            ("treffen", "emoji", "TEXT DEFAULT '📌'"),
            # Bestehende Spiele-Einträge (vor Besitzer-Tracking) werden als
            # "beide besitzen es" behandelt, da sich alte Steam-Importe
            # nachträglich nicht mehr pro Person zuordnen lassen.
            ("spiele", "besitzer_meli", "INTEGER DEFAULT 1"),
            ("spiele", "besitzer_justi", "INTEGER DEFAULT 1"),
            ("film_archiv", "jahr", "INTEGER"),
            ("film_archiv", "letterboxd_url", "TEXT"),
            ("film_archiv", "poster_url", "TEXT"),
        ]
        for table, column, coltype in neue_spalten:
            rows = await self.fetchall(f"PRAGMA table_info({table})")
            spalten = {row["name"] for row in rows}
            if column not in spalten:
                await self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    # ---------- Kern-Helfer ----------
    async def execute(self, sql: str, *params) -> int:
        if self._remote:
            rs = await self._client.execute(sql, list(params))
            return rs.last_insert_rowid
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur.lastrowid

    async def fetchone(self, sql: str, *params):
        if self._remote:
            rs = await self._client.execute(sql, list(params))
            return rs.rows[0] if rs.rows else None
        cur = await self._conn.execute(sql, params)
        return await cur.fetchone()

    async def fetchall(self, sql: str, *params):
        if self._remote:
            rs = await self._client.execute(sql, list(params))
            return rs.rows
        cur = await self._conn.execute(sql, params)
        return await cur.fetchall()

    # ---------- Settings ----------
    async def set_setting(self, key: str, value: str):
        await self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            key, str(value),
        )

    async def get_setting(self, key: str, default=None):
        row = await self.fetchone("SELECT value FROM settings WHERE key = ?", key)
        return row["value"] if row else default

    async def close(self):
        if self._conn:
            await self._conn.close()
        if self._client:
            await self._client.close()
