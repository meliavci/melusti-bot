# 🌱 Melusti Bot – euer Beziehungs-Betriebssystem

Ein Discord-Bot nur für euch zwei: Tamagotchi, Ampel-Check-ins, Lebenszeichen,
Meilensteine, Zitate, euer eigenes Lexikon und Zeitkapseln – alles gespeichert,
nichts geht verloren.

---

## Schritt 1: Discord-Server anlegen (5 Min)

1. In Discord unten links auf **+** → *Eigenen erstellen* → *Für mich und meine Freunde*.
2. Name z.B. **„Meli & Justi 🌱"** – Icon könnt ihr später hübsch machen.
3. Justi einladen. Fertig – die Channels baut der Bot gleich selbst!

## Schritt 2: Bot bei Discord registrieren (10 Min)

1. https://discord.com/developers/applications → **New Application** → Name: `Melusti`.
2. Links auf **Bot**:
   - **Reset Token** → Token kopieren → kommt gleich in die `.env`.
     ⚠️ Der Token ist wie ein Passwort – niemals teilen/posten.
   - **Privileged Gateway Intents**: ALLE DREI anschalten
     (Presence, Server Members, Message Content).
3. Links auf **OAuth2 → URL Generator**:
   - Scopes: `bot` + `applications.commands`
   - Bot Permissions: `Administrator` (einfachster Weg auf eurem Privat-Server)
   - Generierte URL öffnen → euren Server auswählen → Bot ist drin! 🎉

## Schritt 3: Bot konfigurieren (5 Min)

1. `.env.example` kopieren und in `.env` umbenennen.
2. Eintragen:
   - `DISCORD_TOKEN` = der Token aus Schritt 2
   - `MELI_ID` / `JUSTI_ID` = eure Discord-IDs
     (*Discord → Einstellungen → Erweitert → Entwicklermodus AN, dann
     Rechtsklick auf euren Namen → „ID kopieren"*)

## Schritt 4: Starten (lokal testen)

```bash
pip install -r requirements.txt
python main.py
```

Dann im Server: **`/setup_server`** eintippen – der Bot baut alle Kategorien
und Channels automatisch. Danach:

| Befehl | Was passiert |
|---|---|
| `/melusti` | Euer Ei anschauen 🥚 |
| `/melusti_taufen` | Namen geben |
| `/meilenstein_add` | Kennenlernen, 1. Kuss, Zusammenkommen... eintragen |
| `/checkin` | Ersten Ampel-Check-in starten (kommt per DM!) |
| `/denk` | Lebenszeichen senden 💭 |
| `/wort_add` | Lexikon füttern (squanchen, guti, Wadde...) |
| `/zitat_add` | Legendäre Sprüche archivieren |
| `/zeitkapsel` | Nachricht an die Zukunft schreiben 💌 |

⚠️ **Wichtig:** Beide müssen dem Bot DMs erlauben (Server →
Datenschutzeinstellungen → Direktnachrichten AN), sonst kommt der Check-in nicht an.

## Schritt 5: Hosting (damit der Bot 24/7 läuft)

Solange `python main.py` nur auf deinem PC läuft, schläft der Bot, wenn dein
PC aus ist. Optionen:

- **Raspberry Pi** (falls einer rumliegt): perfekt, einmal einrichten, läuft ewig.
- **Cloud Free/Cheap Tier** (z.B. Railway, Fly.io, Hetzner ~4€/Monat):
  Projekt hochladen, `python main.py` als Startbefehl, `.env`-Werte als
  Umgebungsvariablen setzen.
- Die Datei `moli.db` ist eure gesamte Datenbank – **regelmäßig sichern**
  (einfach kopieren), dann ist nichts jemals weg.

## Der 🔒-Channel

`/setup_server` legt eine Kategorie **🔒 PRIVAT** an, die per Berechtigung nur
für euch zwei sichtbar ist (nicht mal für Bots). Dafür braucht es keinen Code –
das ist reine Discord-Berechtigung. Da euer Server eh nur euch gehört, ist das
doppelt abgesichert.

## Wie es weitergeht

Alle weiteren Features (Filmabend, Kalender, Spiele-Tinder, Pixel-Canvas, ...)
bauen wir Session für Session zusammen – der Plan steht in **BAUPLAN.md**.
Das Datenbank-Schema ist schon jetzt für ALLES vorbereitet, wir müssen nie
etwas umbauen.
