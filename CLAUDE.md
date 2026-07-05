# Melusti Bot

Ein privater Discord-Bot für zwei Menschen (Meli & Justi): Tamagotchi
("Melusti"), Ampel-Check-ins, Lebenszeichen, Meilensteine, Zitate,
Wörterbuch, Zeitkapseln – und laut `BAUPLAN.md` noch viel mehr.

## Konventionen

- **Sprache:** Alle Texte, die Discord-Nutzern angezeigt werden (Embeds,
  Command-Beschreibungen, Fehlermeldungen, Channel-Namen), sind auf Deutsch.
  Code (Variablen, Funktionsnamen) darf englisch bleiben, wo es natürlicher ist.
- **Cog-Struktur:** Jedes Feature ist ein eigenes Cog unter `cogs/`, registriert
  in `config.COGS` und mit eigenem `async def setup(bot)`. Slash-Commands über
  `app_commands`, keine reinen Text-Commands.
- **Design-System:** Alle Embeds über `utils/design.py:emb()` erzeugen (feste
  Farbpalette in `COLORS`, einheitlicher Footer). Fortschrittsbalken über
  `progress_bar()`. Keine eigenen `discord.Embed()`-Instanzen in Cogs bauen.
- **Datenbank:** `database/schema.sql` deckt bereits ALLE geplanten Features
  ab (V1–V3) – beim Bauen neuer Sessions die passenden Tabellen einfach
  benutzen, nicht neu entwerfen oder migrieren. Zugriff nur über
  `database/db.py:Database` (execute/fetchone/fetchall), kein rohes
  aiosqlite in Cogs.
- **Session für Session:** Der Fahrplan steht in `BAUPLAN.md`. Wir bauen
  Feature-Blöcke in der dort vorgegebenen Reihenfolge, nicht querbeet.
  Nach jeder abgeschlossenen Session `BAUPLAN.md` aktualisieren (✅ markieren).
- **Namensgebung:** Der Bot heißt überall "Melusti" (Klassen, Commands,
  Texte). Der Datenbankdateiname `moli.db` sowie interne SQL-Tabellennamen
  (`moli`, `moli_feed_log`) sind Legacy-Namen und bleiben absichtlich so.
- **Lebende Nachrichten statt Spam:** Jede Übersicht/Liste (Kalender,
  Jahresblick, Lexikon, Tage-Übersicht, Termine-Liste – und künftig
  Countdown, Watchlists, Film-Archiv, etc.) ist genau EINE Nachricht, die
  über `utils/tracked.py` (`tracked.sync()` / `tracked.refresh_all()`)
  getrackt und bei jeder Änderung editiert wird, statt bei jedem
  Add/Edit/Delete oder erneutem Command-Aufruf eine neue zu posten.
  Neue Cogs mit einer Listen-Ansicht binden sich genauso an: eigener
  `KEY`-String, `_build_x()`-Methode liefert `(embed, file_oder_None)`,
  nach jedem Add/Edit/Delete `tracked.sync(...)`/`refresh_all(...)` aufrufen.
- **Kein manuelles Eintippen von IDs:** Edit/Delete/Lookup-Commands nutzen
  `app_commands.autocomplete` (Dropdown mit Name+Datum als Label, DB-ID als
  Wert dahinter), damit man nie eine ID nachschlagen muss. Siehe
  `_meilenstein_autocomplete`/`_termin_autocomplete` in `cogs/meilensteine.py`
  oder `_wort_autocomplete` in `cogs/woerterbuch.py` als Vorlage.
- **Täglicher Refresh:** Ansichten mit Datums-/Tage-Zählern, die auch ohne
  Änderung "altern" (Countdowns, "seit X Tagen"), werden zusätzlich einmal
  täglich über einen bestehenden `tasks.loop`-Task neu gerendert (siehe
  `Meilensteine.morning_post`, das am Ende `_refresh_all_views()` aufruft).
