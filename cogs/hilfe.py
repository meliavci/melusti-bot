"""
Hilfe ❓ – durchsuchbare Übersicht aller Commands nach Kategorie.
- /hilfe: interaktiver Kategorie-Browser (Dropdown, ephemeral).
- /hilfe suche: durchsucht alle Commands nach einem Begriff.
- #info bekommt zusätzlich EINE dauerhafte lebende Nachricht mit ALLEN
  Kategorien auf einmal (mehrere Embeds in einer Nachricht), damit man nicht
  erst /hilfe tippen muss.
"""
import discord
from discord import app_commands
from discord.ext import commands

from utils import tracked
from utils.design import emb

INFO_KEY = "hilfe_info_uebersicht"

# (Kategorie-Key, Emoji, Titel, Channel-Hinweis, [(Command, Erklärung)])
KATEGORIEN = [
    ("kern", "🥚", "Kern & Melusti", "#melusti, #check-in, #briefkasten, #info (Command-Übersicht), #handyladen (automatisch)", [
        ("/melusti", "Zeigt euer gemeinsames Wesen und seinen Zustand (wächst durch Nutzung des Bots)."),
        ("/melusti_taufen", "Gebt eurem Wesen einen eigenen Namen."),
        ("/beziehungsbarometer", "Zeigt, wie's um eure Beziehung gerade steht (aus Check-ins, Klärungen & Melusti berechnet)."),
        ("/checkin", "Startet den täglichen Ampel-Check-in (grün/gelb/rot)."),
        ("/checkin_verlauf", "Zeigt den Verlauf eurer letzten Check-ins."),
        ("/briefkasten", "Zeigt offene gelbe Check-in-Themen, die noch geklärt werden wollen."),
        ("/briefkasten_erledigt", "Markiert ein Briefkasten-Thema als erledigt."),
    ]),
    ("planung", "📅", "Planung & Meilensteine", "#kalender-treffen, #countdown, #meilensteine, #tagebuch, #packliste, #bucket-list", [
        ("/termin add", "Trägt einen neuen Termin oder Treffen-Zeitraum (von-bis) ein."),
        ("/termin bestaetigen", "Bestätigt einen vorgeschlagenen Termin verbindlich."),
        ("/termin edit", "Ändert Datum/Uhrzeit/Titel eines bestehenden Termins."),
        ("/termin delete", "Löscht einen Termin unwiderruflich."),
        ("/termin liste", "Zeigt alle eingetragenen Termine."),
        ("/termin countdown", "Postet/aktualisiert den Countdown zum nächsten Termin sofort (läuft sonst automatisch täglich)."),
        ("/kalender", "Zeigt euren Monats-Kalender mit Meilensteinen & Terminen als Bild."),
        ("/jahresblick", "Zeigt das ganze Jahr auf einen Blick als Bild."),
        ("/meilenstein add", "Trägt ein wichtiges Datum ein (Kennenlernen, erstes Date, ...)."),
        ("/meilenstein edit", "Ändert einen bestehenden Meilenstein."),
        ("/meilenstein delete", "Löscht einen Meilenstein."),
        ("/meilenstein tage", "Zeigt alle 'Wie lange schon?'-Zähler auf einen Blick."),
        ("/tagebuch_add", "Neuer Tagebuch-Eintrag, optional mit Bild – landet automatisch in der Timeline, kein Einzelpost."),
        ("/timeline", "Zeigt/aktualisiert die eine lebende Tagebuch-Timeline (chronologisch, neuester unten)."),
        ("/packliste add", "Fügt einen Punkt zur Packliste für einen Trip hinzu."),
        ("/packliste abhaken", "Hakt einen Packlisten-Punkt ab oder wieder auf."),
        ("/packliste delete", "Entfernt einen Packlisten-Punkt."),
        ("/packliste liste", "Zeigt die Packliste für einen Trip."),
        ("/bucket add", "Fügt etwas zu eurer Bucket List hinzu."),
        ("/bucket abhaken", "Hakt einen Bucket-List-Punkt ab."),
        ("/bucket delete", "Entfernt einen Bucket-List-Punkt."),
        ("/bucket liste", "Zeigt die Bucket List."),
    ]),
    ("zocken", "🎮", "Zocken", "#valorant, #spiele-tinder, #kartentisch, #spiel-projekt", [
        ("/spiel add", "Fügt ein Spiel manuell hinzu – gilt automatisch als gemeinsames Spiel für euch beide."),
        ("/spiel steam_import", "Importiert deine Steam-Bibliothek – nur Spiele, die ihr beide habt, landen in der Swipe-Runde."),
        ("/spiel swipe", "Startet eine Runde durch alle gemeinsamen Spiele von vorn, zeigt am Ende alle Matches."),
        ("/spiel matches", "Zeigt alle Spiele, bei denen ihr beide 'Ja' geswiped habt."),
        ("/karten start", "Mischt ein neues Kartendeck und teilt Karten aus."),
        ("/karten ziehen", "Zieht die oberste Karte vom Stapel (auf die Hand oder offen in den Kanal)."),
        ("/karten legen", "Legt eine Karte aus deiner Hand offen auf den Kartentisch."),
        ("/karten hand", "Zeigt dir nochmal deine aktuelle Hand (falls die DM untergegangen ist)."),
        ("/entscheide", "Dreht ein Entscheidungsrad, wenn ihr euch nicht einigen könnt."),
        ("/ranked valorant", "Ruft ALLE verfügbaren Valorant-Stats ab: Rang, RR, Elo, Peak-Rang, Season-Bilanz, Leaderboard-Platz, KDA/HS-%/Winrate der letzten 20 Matches, Lieblings-Agent."),
        ("/idee add", "Trägt eine Idee für euer gemeinsames Spiel-Projekt ein."),
        ("/idee vote", "Stimmt für eine Spiel-Projekt-Idee."),
        ("/idee status", "Setzt den Status einer Idee (pool/angenommen/verworfen)."),
        ("/idee liste", "Zeigt alle Spiel-Projekt-Ideen."),
    ]),
    ("filme", "🎬", "Filme & Watchlist", "#filmabend, #film-archiv, #film-benachrichtigung, #film-awards, #watchlist-filme, #watchlist-youtube", [
        ("/filmabend", "Startet oder führt die Filmabend-Runde fort (abwechselnd: 3 Optionen vorschlagen, Partner wählt)."),
        ("/film archiv", "Zeigt alle über /filmabend gewählten Filme mit Sterne-Bewertung, Jahr & Letterboxd-Link (kommt automatisch von Letterboxd)."),
        ("/film awards_start", "Startet die Monats-Abstimmung in allen 4 Kategorien (Bester/Schlechtester/Lustigster/Überraschung) – läuft sonst automatisch am 1. jeden Monats."),
        ("/film awards_auswerten", "Wertet alle 4 Kategorien aus – läuft sonst automatisch 3 Tage nach dem Start."),
        ("/watchlist add", "Fügt einen Film/eine Serie zur Watchlist hinzu."),
        ("/watchlist gesehen", "Markiert einen Watchlist-Eintrag als gesehen."),
        ("/watchlist delete", "Entfernt einen Watchlist-Eintrag."),
        ("/watchlist liste", "Zeigt die Watchlist."),
        ("/letterboxd import", "Einmaliger CSV-Import eurer bisherigen Letterboxd-Historie – danach läuft alles automatisch, kein erneuter Import nötig."),
        ("/letterboxd sync", "Holt neue Letterboxd-Einträge sofort (läuft sonst eh alle 10 Minuten automatisch von selbst)."),
    ]),
    ("musik", "🎵", "Musik", "#unsere-playlist (Songliste/Spotify) · 🎧 unser call (Wiedergabe)", [
        ("/song add", "Fügt einen Song zur gemeinsamen Playlist hinzu (pusht auch zu Spotify, falls verbunden)."),
        ("/song delete", "Entfernt einen Song (bei verbundenem Spotify direkt aus der echten Playlist, sonst aus der Bot-internen Liste)."),
        ("/song liste", "Zeigt die Playlist – bei verbundenem Spotify live die echte Playlist inkl. Songs, die schon vorher drin waren."),
        ("/spotify login", "Startet die Verbindung eures Spotify-Accounts mit dem Bot."),
        ("/spotify code", "Schließt den Spotify-Login mit dem erhaltenen Code ab."),
        ("/spotify playlist_neu", "Erstellt eine neue Spotify-Playlist für eure Songs."),
        ("/spotify playlist_verbinden", "Verbindet eine bereits bestehende Spotify-Playlist statt einer neuen."),
        ("/musik play", "Bot joint euren Voice-Channel und spielt einen Song von YouTube ab."),
        ("/musik playlist", "Spielt eure ganze Playlist nacheinander ab (bei verbundenem Spotify live von dort, sonst die Bot-interne Liste)."),
        ("/musik skip", "Überspringt den aktuellen Song."),
        ("/musik pause", "Pausiert die Wiedergabe."),
        ("/musik resume", "Setzt die pausierte Wiedergabe fort."),
        ("/musik stop", "Stoppt die Wiedergabe und leert die Warteschlange."),
        ("/musik queue", "Zeigt die aktuelle Warteschlange."),
    ]),
    ("wir", "💛", "Wir (Beziehung)", "#lebenszeichen, #komplimente, #zitate, #wörterbuch, #foto-des-tages, #zeitkapsel", [
        ("/denk", "Schickt ein kleines 'ich denk an dich'-Lebenszeichen (optional mit Text) – geht auch ganz ohne Command per Knopf direkt in #lebenszeichen."),
        ("/kompliment", "Schickt dem Partner ein Kompliment."),
        ("/zitat add", "Speichert ein legendäres Zitat (Datum optional, Standard: heute)."),
        ("/zitat zufall", "Zieht ein zufälliges Zitat aus dem Archiv."),
        ("/zitat edit", "Ändert ein gespeichertes Zitat."),
        ("/zitat delete", "Löscht ein gespeichertes Zitat."),
        ("/wort add", "Trägt ein neues Wort in euer gemeinsames Lexikon ein."),
        ("/wort edit", "Ändert einen bestehenden Lexikon-Eintrag."),
        ("/wort delete", "Löscht einen Lexikon-Eintrag."),
        ("/wort schlagnach", "Schlägt ein Wort in eurem Lexikon nach."),
        ("/wort liste", "Zeigt das ganze Wörterbuch."),
        ("/foto_add", "Teilt dein Foto des Tages."),
        ("/zeitkapsel", "Verschließt eine Nachricht/ein Bild bis zu einem bestimmten Datum."),
        ("/zeitkapsel_status", "Zeigt, welche Zeitkapseln noch verschlossen sind und wann sie öffnen."),
    ]),
    ("kreativ", "🎨", "Kreativ & Spielereien", "#traum-tagebuch, #pixel-canvas, #zaubertricks, #witze", [
        ("/traum add", "Trägt einen Traum ins Traum-Tagebuch ein."),
        ("/traum timeline", "Blättert durch die eingetragenen Träume."),
        ("/pixel setzen", "Setzt einen Pixel im gemeinsamen Pixel-Canvas (5 pro Tag) – Farbe per Dropdown, kein Hex-Code nötig."),
        ("/pixel canvas", "Zeigt das aktuelle Pixel-Canvas."),
        ("/trick add", "Trägt einen vorgeführten Zaubertrick ein."),
        ("/trick bewerten", "Bewertet einen dir vorgeführten Trick (1-10)."),
        ("/trick delete", "Löscht einen Zaubertrick-Eintrag."),
        ("/trick liste", "Zeigt alle Zaubertricks mit Bewertung."),
        ("/witz add", "Trägt einen Witz ein."),
        ("/witz bewerten", "Bewertet einen Witz des Partners (1-5 Sterne)."),
        ("/witz delete", "Löscht einen Witz."),
        ("/witz liste", "Zeigt alle Witze mit Bewertung."),
    ]),
    ("spass", "⚽", "Spaß & Klärung", "#tipp-liga (automatisch), #wetten (reiner Screenshot-Kanal, kein Bot), #stats, 🎧 unser call, #streit-modus", [
        ("(automatisch)", "#tipp-liga bekommt automatisch eine Erinnerung ~2h vor jedem WM-2026-Spiel, damit ihr nicht vergesst bei Kicktipp zu tippen – kein Command nötig."),
        ("/call_stats", "Zeigt eure Call-Zeit diese Woche: gemeinsam, einzeln pro Person, Bildschirmfreigabe, Melusti-Anwesenheit – läuft sonntags auch automatisch in #stats."),
        ("/streit start", "Startet den geführten Klärungs-Modus bei einem Konflikt."),
        ("/streit sicht", "Trägt eure jeweilige Sicht der Dinge ein."),
        ("/streit loesung", "Trägt die gemeinsam gefundene Lösung ein."),
        ("/streit fairness", "Bewertet, wie fair die Klärung ablief."),
        ("/streit delete", "Löscht einen Klärungs-Prozess unwiderruflich."),
        ("/streit liste", "Zeigt offene Klärungs-Prozesse."),
        ("/pause_karte", "Zieht eine Karte für eine bewusste Gesprächspause."),
    ]),
    ("verwaltung", "⚙️", "Verwaltung", "#info, irgendwo sonst nur einmalig / bei Bedarf nötig", [
        ("/setup_server", "Erstellt einmalig alle Kategorien & Channels (nur Admin)."),
        ("/export", "Exportiert die komplette Datenbank als lesbare Datei zum Backup."),
        ("/hilfe", "Zeigt diese Übersicht als interaktives Dropdown-Menü."),
        ("/hilfe_suche", "Durchsucht alle Commands nach einem Stichwort."),
    ]),
]


def _kategorie_embed(index: int) -> discord.Embed:
    _key, icon, titel, channel, eintraege = KATEGORIEN[index]
    e = emb("melusti", f"{icon} {titel}",
           f"📍 Am besten in: **{channel}**")
    for cmd, erklaerung in eintraege:
        e.add_field(name=cmd, value=erklaerung, inline=False)
    e.set_footer(text=f"Kategorie {index + 1}/{len(KATEGORIEN)} – Melusti 🌱 euer gemeinsamer Server")
    return e


def _embed_laenge(e: discord.Embed) -> int:
    total = len(e.title or "") + len(e.description or "")
    for f in e.fields:
        total += len(f.name) + len(f.value)
    if e.footer and e.footer.text:
        total += len(e.footer.text)
    return total


def _alle_embeds_gruppen() -> list[list[discord.Embed]]:
    """Packt alle Kategorie-Embeds in möglichst wenige Nachrichten, ohne
    Discords Limits zu reißen: max. 10 Embeds UND max. 6000 Zeichen
    (Summe aller Embeds) pro Nachricht."""
    gruppen: list[list[discord.Embed]] = []
    aktuelle: list[discord.Embed] = []
    aktuelle_laenge = 0
    for i in range(len(KATEGORIEN)):
        e = _kategorie_embed(i)
        laenge = _embed_laenge(e)
        if aktuelle and (len(aktuelle) >= 10 or aktuelle_laenge + laenge > 5500):
            gruppen.append(aktuelle)
            aktuelle, aktuelle_laenge = [], 0
        aktuelle.append(e)
        aktuelle_laenge += laenge
    if aktuelle:
        gruppen.append(aktuelle)
    return gruppen


class KategorieSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=titel, emoji=icon, value=str(i),
                                 description=channel[:100])
            for i, (_key, icon, titel, channel, _e) in enumerate(KATEGORIEN)
        ]
        super().__init__(placeholder="Kategorie wählen...", options=options)

    async def callback(self, itx: discord.Interaction):
        index = int(self.values[0])
        await itx.response.edit_message(embed=_kategorie_embed(index), view=self.view)


class HilfeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.add_item(KategorieSelect())


class Hilfe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await self._ensure_info_uebersicht()

    async def _ensure_info_uebersicht(self):
        """Postet die volle Command-Übersicht einmalig dauerhaft in #info,
        damit man nicht erst /hilfe tippen muss – wird bei jedem Neustart
        aktualisiert, falls sich was geändert hat. Läuft über mehrere
        Nachrichten, falls der Inhalt Discords 6000-Zeichen-Limit pro
        Nachricht sprengt."""
        ch = self.bot.channel_by_name("info")
        if not ch:
            return
        gruppen = _alle_embeds_gruppen()
        for i, gruppe in enumerate(gruppen):
            await tracked.sync(self.bot, INFO_KEY, str(i), ch, self._build_info(gruppe))

    @staticmethod
    def _build_info(gruppe: list[discord.Embed]):
        async def build():
            return gruppe, None
        return build

    @app_commands.command(name="hilfe", description="Zeigt alle Commands nach Kategorie, inkl. Channel-Empfehlung.")
    async def hilfe(self, itx: discord.Interaction):
        view = HilfeView()
        await itx.response.send_message(embed=_kategorie_embed(0), view=view, ephemeral=True)

    @app_commands.command(name="hilfe_suche", description="Durchsucht alle Commands nach einem Stichwort.")
    @app_commands.describe(begriff="Wonach suchen? (z.B. 'Film' oder 'löschen')")
    async def hilfe_suche(self, itx: discord.Interaction, begriff: str):
        suche = begriff.lower()
        treffer = []
        for _key, icon, titel, _channel, eintraege in KATEGORIEN:
            for cmd, erklaerung in eintraege:
                if suche in cmd.lower() or suche in erklaerung.lower():
                    treffer.append((icon, titel, cmd, erklaerung))
        if not treffer:
            await itx.response.send_message(
                f"Keine Commands zu „{begriff}“ gefunden.", ephemeral=True)
            return
        e = emb("melusti", f"🔍 Suche: „{begriff}“")
        for icon, titel, cmd, erklaerung in treffer[:20]:
            e.add_field(name=cmd, value=f"{erklaerung}\n-# {icon} {titel}", inline=False)
        if len(treffer) > 20:
            e.set_footer(text=f"{len(treffer)} Treffer, zeige die ersten 20.")
        await itx.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Hilfe(bot))
