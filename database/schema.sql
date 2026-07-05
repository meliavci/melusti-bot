-- ============================================================
--  MELUSTI BOT – Komplettes Datenbank-Schema
--  Deckt ALLE geplanten Features ab (V1, V2, V3),
--  damit wir später nie migrieren müssen.
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------- Grundlagen ----------
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    discord_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL
);

-- ---------- Melusti (Tamagotchi) ----------
CREATE TABLE IF NOT EXISTS moli (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    name       TEXT DEFAULT 'Melusti',
    xp         INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS moli_feed_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    action    TEXT,               -- checkin / lebenszeichen / zitat / quest / streit_geklaert ...
    xp        INTEGER,
    ts        TEXT DEFAULT (datetime('now'))
);

-- ---------- Ampel-Check-in ----------
CREATE TABLE IF NOT EXISTS checkins (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    datum    TEXT NOT NULL,       -- YYYY-MM-DD (Europe/Berlin)
    farbe    TEXT NOT NULL,       -- gruen / gelb / rot
    thema    TEXT,                -- optionales Stichwort (wird beim Reveal gezeigt)
    notiz    TEXT,                -- private Notiz (wird NIE gezeigt, nur gespeichert)
    ts       TEXT DEFAULT (datetime('now')),
    UNIQUE (user_id, datum)
);

CREATE TABLE IF NOT EXISTS briefkasten (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    thema      TEXT NOT NULL,
    quelle     TEXT DEFAULT 'checkin',   -- checkin / manuell
    erstellt   TEXT DEFAULT (datetime('now')),
    erledigt   INTEGER DEFAULT 0,
    erledigt_am TEXT
);

-- ---------- Streit-Modus ----------
CREATE TABLE IF NOT EXISTS streits (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thema        TEXT NOT NULL,
    gestartet    TEXT DEFAULT (datetime('now')),
    sicht_a      TEXT,            -- Sichtweise User A (per DM)
    sicht_b      TEXT,
    loesung      TEXT,
    fairness_a   INTEGER,         -- 1-5, blind
    fairness_b   INTEGER,
    status       TEXT DEFAULT 'offen',   -- offen / geklaert / known_issue
    geklaert_am  TEXT
);

-- ---------- Kalender & Treffen ----------
CREATE TABLE IF NOT EXISTS treffen (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    datum         TEXT NOT NULL,
    datum_bis     TEXT,                     -- optional: Ende bei mehrtägigen Terminen
    ort           TEXT,
    aktivitaet    TEXT,
    emoji         TEXT DEFAULT '📌',
    status        TEXT DEFAULT 'planung',   -- planung / safe
    bestaetigt_von TEXT DEFAULT '',         -- kommagetrennte user_ids
    erstellt_von  INTEGER,
    erstellt      TEXT DEFAULT (datetime('now'))
);

-- ---------- Meilensteine & Tagebuch ----------
CREATE TABLE IF NOT EXISTS meilensteine (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    datum  TEXT NOT NULL,        -- YYYY-MM-DD
    emoji  TEXT DEFAULT '💛'
);

CREATE TABLE IF NOT EXISTS tagebuch (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    autor_id   INTEGER NOT NULL,
    datum      TEXT NOT NULL,
    titel      TEXT,
    text       TEXT,
    bild_urls  TEXT,             -- JSON-Liste von Attachment-URLs
    treffen_id INTEGER REFERENCES treffen(id),
    ts         TEXT DEFAULT (datetime('now'))
);

-- ---------- Filmabend ----------
CREATE TABLE IF NOT EXISTS film_runden (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vorschlagender INTEGER NOT NULL,
    optionen      TEXT NOT NULL,   -- JSON-Liste der Filmtitel
    gewaehlt      TEXT,
    reste         TEXT,            -- JSON: übrig gebliebene Optionen
    ts            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS film_archiv (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    titel          TEXT NOT NULL,
    geschaut_am    TEXT,
    rating_a       INTEGER,       -- Halbe Sterne als 1-10 gespeichert (÷2 = 0.5-5★), kommt von Letterboxd
    rating_b       INTEGER,
    quelle         TEXT DEFAULT 'filmabend',   -- filmabend / letterboxd_import
    jahr           INTEGER,       -- von Letterboxd
    letterboxd_url TEXT,
    poster_url     TEXT
);

-- Verhindert doppelte Benachrichtigungen: merkt sich, welche Letterboxd-
-- Diary-Einträge (pro Person) schon verarbeitet wurden.
CREATE TABLE IF NOT EXISTS letterboxd_verarbeitet (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    titel    TEXT NOT NULL,
    datum    TEXT NOT NULL,
    UNIQUE (username, titel, datum)
);

CREATE TABLE IF NOT EXISTS film_awards (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    monat     TEXT NOT NULL,      -- YYYY-MM
    kategorie TEXT NOT NULL,      -- bester / schlechtester / lustigster / ueberraschung
    film_id   INTEGER REFERENCES film_archiv(id)
);

-- ---------- Watchlists (Filme & YouTube) ----------
CREATE TABLE IF NOT EXISTS watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    typ         TEXT NOT NULL,     -- film / youtube
    kategorie   TEXT DEFAULT 'Allgemein',
    titel       TEXT NOT NULL,
    link        TEXT,
    gesehen     INTEGER DEFAULT 0,
    gesehen_am  TEXT,
    added_by    INTEGER,
    ts          TEXT DEFAULT (datetime('now'))
);

-- ---------- Wörterbuch & Zitate ----------
CREATE TABLE IF NOT EXISTS woerterbuch (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    wort       TEXT NOT NULL UNIQUE,
    definition TEXT NOT NULL,
    herkunft   TEXT,
    added_by   INTEGER,
    ts         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS zitate (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    text     TEXT NOT NULL,
    kontext  TEXT,
    von      TEXT,               -- wer hat's gesagt (Name)
    added_by INTEGER,
    datum    TEXT,
    ts       TEXT DEFAULT (datetime('now'))
);

-- ---------- Musik ----------
CREATE TABLE IF NOT EXISTS songs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    titel    TEXT NOT NULL,
    link     TEXT,
    added_by INTEGER,
    ts       TEXT DEFAULT (datetime('now'))
);

-- ---------- Spiele-Tinder ----------
CREATE TABLE IF NOT EXISTS spiele (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    swipe_a        INTEGER,             -- NULL = noch nicht geswiped, 1 = like, 0 = nope
    swipe_b        INTEGER,
    match          INTEGER DEFAULT 0,
    besitzer_meli  INTEGER DEFAULT 1,   -- manuell hinzugefügt = automatisch beide;
    besitzer_justi INTEGER DEFAULT 1    -- Steam-Import setzt nur den jeweiligen Besitzer
);

-- ---------- Duo-Ranked-Tracker (Road to Gold), manuell ----------
CREATE TABLE IF NOT EXISTS ranked_progress (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    spieler INTEGER NOT NULL,
    spiel   TEXT DEFAULT 'League of Legends',
    rang    TEXT NOT NULL,        -- z.B. "Gold 3"
    lp      INTEGER DEFAULT 0,
    notiz   TEXT,
    ts      TEXT DEFAULT (datetime('now'))
);

-- ---------- Zeitkapsel ----------
CREATE TABLE IF NOT EXISTS zeitkapseln (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    autor_id     INTEGER NOT NULL,
    unlock_datum TEXT NOT NULL,   -- YYYY-MM-DD
    text         TEXT NOT NULL,
    geliefert    INTEGER DEFAULT 0,
    ts           TEXT DEFAULT (datetime('now'))
);

-- ---------- Lebenszeichen, Komplimente, Foto des Tages ----------
CREATE TABLE IF NOT EXISTS lebenszeichen (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    von     INTEGER NOT NULL,
    text    TEXT,
    ts      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS komplimente (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    von     INTEGER NOT NULL,
    text    TEXT NOT NULL,
    ts      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fotos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    von     INTEGER NOT NULL,
    datum   TEXT NOT NULL,
    url     TEXT NOT NULL,
    UNIQUE (von, datum)
);

-- ---------- Pixel-Canvas ----------
CREATE TABLE IF NOT EXISTS pixel_canvas (
    x       INTEGER NOT NULL,
    y       INTEGER NOT NULL,
    farbe   TEXT NOT NULL,       -- Hex
    von     INTEGER,
    ts      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (x, y)
);

CREATE TABLE IF NOT EXISTS pixel_quota (
    user_id INTEGER,
    datum   TEXT,
    gesetzt INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, datum)
);

-- ---------- Listen: Packliste & Bucket List ----------
CREATE TABLE IF NOT EXISTS packliste (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trip    TEXT DEFAULT 'Nächstes Treffen',
    item    TEXT NOT NULL,
    gepackt INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bucketlist (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item      TEXT NOT NULL,
    erledigt  INTEGER DEFAULT 0,
    erledigt_am TEXT,
    added_by  INTEGER
);

-- ---------- Träume ----------
CREATE TABLE IF NOT EXISTS traeume (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    von     INTEGER NOT NULL,
    datum   TEXT NOT NULL,
    text    TEXT NOT NULL
);

-- ---------- Zaubertricks ----------
CREATE TABLE IF NOT EXISTS zaubertricks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    von          INTEGER NOT NULL,     -- wer hat ihn vorgeführt
    beschreibung TEXT,
    bewertung    INTEGER,              -- 1-10, vom anderen vergeben
    ts           TEXT DEFAULT (datetime('now'))
);

-- ---------- Witzebuch ----------
CREATE TABLE IF NOT EXISTS witze (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    text      TEXT NOT NULL,
    von       INTEGER NOT NULL,
    bewertung INTEGER,              -- 1-5 Sterne, vom Partner vergeben
    ts        TEXT DEFAULT (datetime('now'))
);

-- ---------- Frage des Tages ----------
CREATE TABLE IF NOT EXISTS fragen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT NOT NULL,
    erstellt_von INTEGER,
    ts           TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS frage_antworten (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    frage_id INTEGER NOT NULL REFERENCES fragen(id),
    datum    TEXT NOT NULL,
    von      INTEGER NOT NULL,
    antwort  TEXT NOT NULL,
    UNIQUE (frage_id, datum, von)
);

-- ---------- Call-Stats ----------
CREATE TABLE IF NOT EXISTS calls (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    start    TEXT NOT NULL,
    ende     TEXT,
    minuten  INTEGER
);

-- Feinere Call-Stats: Einzelzeit pro Person, Bildschirmfreigabe pro Person,
-- und wie lange Melusti (der Bot) selbst im Call war (z.B. Musik-Wiedergabe).
CREATE TABLE IF NOT EXISTS voice_sessions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    typ     TEXT NOT NULL,     -- einzeln / screenshare / bot
    user_id INTEGER,           -- NULL bei typ='bot'
    start   TEXT NOT NULL,
    ende    TEXT,
    minuten INTEGER
);

-- ---------- Wetten & Tipp-Liga ----------
CREATE TABLE IF NOT EXISTS wetten (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    beschreibung TEXT NOT NULL,
    tipp_a       TEXT,
    tipp_b       TEXT,
    einsatz      TEXT,
    ergebnis     TEXT,
    gewinner     INTEGER,
    ts           TEXT DEFAULT (datetime('now'))
);

-- ---------- Quests ----------
CREATE TABLE IF NOT EXISTS quests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    kategorie  TEXT DEFAULT 'Wertschätzung',
    xp         INTEGER DEFAULT 10,
    erstellt_von INTEGER,        -- anonym eingespeist
    gezogen_von  INTEGER,
    gezogen_am   TEXT,
    erledigt     INTEGER DEFAULT 0,
    bestaetigt_von INTEGER
);

-- ---------- Spiel-Projekt Brainstorm ----------
CREATE TABLE IF NOT EXISTS spielideen (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    text     TEXT NOT NULL,
    von      INTEGER,
    votes    INTEGER DEFAULT 0,
    status   TEXT DEFAULT 'pool',   -- pool / angenommen / verworfen
    ts       TEXT DEFAULT (datetime('now'))
);
