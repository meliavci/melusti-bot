# 🗺️ Bauplan – wir bauen Session für Session zusammen

Das DB-Schema (`database/schema.sql`) deckt schon ALLE Features ab.
Jede Session = 1 Chat mit Claude: Zip hochladen, Session nennen, bauen, testen.

## ✅ Session 0 – Fundament (FERTIG)
Bot-Grundgerüst · Datenbank · Design-System · `/setup_server` ·
**Melusti** (Tamagotchi mit PIL-Renderer, XP, Evolution, Stimmungen –
Evolution ab "Kind" braucht zusätzlich zur XP-Schwelle echte eingetragene
Meilensteine, nicht nur XP allein; 5 Stimmungen strahlend/zufrieden/
quengelig/krank/schlafend – "krank" wird durch einen offenen ungeklärten
Streit ausgelöst und heilt automatisch mit `/streit loesung`) ·
`/beziehungsbarometer` (errechnet sich aus Check-in-Historie der letzten
14 Tage, offenen/geklärten Streits und Melustis aktuellem Zustand) ·
**Ampel-Check-in** (DM-Buttons, Blind-Reveal, Streaks, Briefkasten, Call-Trigger) ·
**Lebenszeichen** + Komplimente · **Meilensteine** (Live-Zähler, Auto-Jubiläen) ·
**Zitate** · **Wörterbuch** (Wort des Tages) · **Zeitkapsel** ·
**Kalender-Visualisierung** (`/kalender`, `/jahresblick` – PIL-Monats-/Jahresbild
mit Meilenstein-Jubiläen, aus Session 2 vorgezogen)

Seitdem gilt außerdem als Standard-Konvention (siehe `CLAUDE.md`): lebende
Nachrichten statt Spam (`utils/tracked.py`), Autocomplete statt IDs bei
Edit/Delete, sparsamer Emoji-Einsatz, täglicher Refresh für alles mit
Datums-/Tage-Zählern.

## ✅ Session 1 – 🎬 Filmabend & Watchlists (FERTIG)
`cogs/filme.py` – Filmabend läuft unabhängig von der Watchlist: wer dran
ist, sieht per `/filmabend` erst seine Reste vom letzten Mal und
entscheidet dann per Button (Reste behalten / auffüllen / 3 komplett neue –
neue Filme immer per Modal auf einmal eingetragen), der Partner wählt.
Rolle wechselt automatisch ab (Meli startet). Film-Archiv mit
Doppel-Rating (1-10) · Watchlists Filme & YouTube (Kategorien,
gesehen-Status, Links) · Letterboxd-CSV-Import UND täglicher
Auto-Sync über den öffentlichen RSS-Feed (`LETTERBOXD_MELI`/
`LETTERBOXD_JUSTI` in `.env`, kein API-Key nötig) · Film-Awards
(Reaction-Voting, alle 4 Kategorien: bester/schlechtester/lustigster/
Überraschung des Monats) – startet automatisch am 1. jeden Monats für
den Vormonat und wertet sich 3 Tage später automatisch selbst aus, geht
aber auch jederzeit manuell per `/film awards_start`/`awards_auswerten`.

## ✅ Session 2 – 📅 Treffen, Tagebuch, Packliste, Countdown (FERTIG)
`cogs/treffen.py` – Termine mit Planung/Safe-Status + Bestätigung
(`/termin_bestaetigen` + Button), täglicher Countdown-Post.
`cogs/tagebuch.py` – `/tagebuch_add` mit Bild-Upload, `/timeline` zum
Durchblättern. `cogs/packliste.py` – Checkliste pro Person/Trip.
**Vereinfacht:** Die Bestätigung läuft über einen Button (kurzlebig) +
zuverlässig immer per Slash-Command `/termin_bestaetigen` – der Button
übersteht keinen Bot-Neustart (kein vollständiges Nachregistrieren beim
Hochfahren), der Command schon.

## ✅ Session 3 – 🎮 Zocken (FERTIG)
`cogs/zocken.py` – Spiele-Tinder (blindes Swipen, Match-Reveal,
`/spiel steam_import` importiert die eigene Steam-Bibliothek automatisch
als Karten über die Steam Web API – `STEAM_API_KEY`/`STEAM_ID_MELI`/
`STEAM_ID_JUSTI` in `.env`, Spieleliste im Profil muss öffentlich sein) ·
Kartendealer (Deck mischen, Karten per DM + offene Karten im Kanal) ·
Entscheidungsrad `/entscheide` (echtes animiertes GIF, landet exakt beim
Gewinner) · Duo-Ranked-Tracker `/ranked_update` (manuell).
**Valorant-Rang fertig – über HenrikDev statt offizieller Riot-API:**
Recherche ergab, dass die offizielle Riot-API für Valorant keinen
individuellen Rang liefert (nur Leaderboards) – das ist eine echte
API-Grenze, keine Genehmigungsfrage. `/valorant_rang` nutzt daher die
inoffizielle HenrikDev-API (`utils/henrikdev_client.py`), Ergebnis fließt
auch automatisch in den bestehenden `/ranked_status`-Verlauf ein. Täglicher
Auto-Sync, sobald `HENRIKDEV_API_KEY` in der `.env` steht.

## ✅ Session 4 – 🔧 Streit-Modus & Quests (FERTIG)
`cogs/streit.py` – geführter Modus (`/streit_start` → `/streit_sicht` per
DM-Aufforderung → Reveal im Kanal → `/streit_loesung` → blinder
Fairness-Check `/streit_fairness` 1-5 → bei <3 "Known Issue" statt
"Geklärt") · Pause-Karte `/pause` mit Timer + Rückkehr-Ping.
`cogs/quests.py` – anonymer Quest-Pool, Partner-Bestätigung, XP für
Melusti, sonntäglicher Wochen-Report ("Patch Notes").

## ✅ Session 5 – 💛 Kreativ & Alltag (FERTIG)
`cogs/kreativ.py` – Pixel-Canvas 32×32 per Modal (5 Pixel/Tag/Person,
Bild wird bei jedem Pixel neu gerendert) · Foto des Tages mit Streak,
täglicher aktiver Reminder-Post statt nur passivem `/foto_add` ·
Traum-Tagebuch mit Timeline · Bucket List mit Abhaken + Feier-Post ·
Frage des Tages (täglicher Pool-Zug, blinde Antworten, Reveal sobald
beide geantwortet haben – neue Tabellen `fragen`/`frage_antworten`
ergänzt, die im Schema noch fehlten).

## ✅ Session 6 – 🎵 Musik, Wetten & Stats (FERTIG)
`cogs/musik.py` – Playlist + Song des Tages (fragt täglich abwechselnd
Meli/Justi nach einem neuen Vorschlag, statt nur zufällig einen
bestehenden Song zu wiederholen) + echte Voice-Wiedergabe (`/musik play`
etc., YouTube-Suche über yt-dlp + ffmpeg). `cogs/wetten.py` – Tipp-Liga
+ Wetten mit ewiger Tabelle. `cogs/calls.py` – Call-Stats (automatisches
Tracking, wenn ihr beide im selben Voice-Channel seid, plus automatischer
Recap-Post alle 3 Tage). `cogs/export.py` – `/export`.
`cogs/spielideen.py` – `/idee_add` + Voting.
**Spotify-Playlist-Sync fertig:** `/spotify login` (Browser-Login,
Autorisierungs-Code manuell zurückgeben, da kein eigener Webserver) →
`/spotify code` → `/spotify playlist_neu` (neue Playlist) ODER
`/spotify playlist_verbinden` (bestehende Playlist verbinden). Danach
landet jeder `/song add` automatisch auch in der gemeinsamen
Spotify-Playlist (`utils/spotify_client.py`).

## Ideen-Parkplatz (wenn alles läuft)
Zaubertricks-Bewertungssystem · Wetter-Brücke · Guten-Morgen-Tracker ·
virtueller Date-Generator · Melusti-Accessoires als XP-Belohnung
