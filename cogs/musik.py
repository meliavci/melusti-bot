"""
Playlist 🎵 – gemeinsame Songliste.
Optional mit echter Spotify-Playlist-Synchronisation: sobald
SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET in der .env stehen, verbindet
sich jede Person einmalig mit /spotify login, danach landet /song add
automatisch auch in einer gemeinsamen Spotify-Playlist. Ohne Spotify-Setup
funktioniert alles weiterhin über einfache Links.
Sobald Spotify verbunden ist, lesen "Eure Playlist" (/song liste), /song
delete und /musik playlist IMMER live direkt aus der echten Spotify-
Playlist (nicht aus einer separaten Bot-internen Liste) – so werden auch
Songs erkannt, die schon vor der Bot-Anbindung dort lagen.

Echte Audio-Wiedergabe im Voice-Channel (/musik play, skip, pause, resume,
queue, stop) läuft über YouTube-Suche (yt-dlp) + ffmpeg – Spotifys API
liefert keine Audio-Streams (verbietet deren ToS), daher dieser Umweg.

Commands sind über app_commands.Group gebündelt (Discord erlaubt max.
100 Top-Level-Commands global) – siehe CLAUDE.md-Konvention.
"""
import asyncio
import datetime as dt
from urllib.parse import urlparse, parse_qs

import aiohttp
import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked, spotify_client
from utils.design import emb

PLAYLIST_KEY = "playlist"

YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Musik(commands.Cog):
    song_group = app_commands.Group(name="song", description="Gemeinsame Songliste verwalten.")
    spotify_group = app_commands.Group(name="spotify", description="Spotify-Playlist-Anbindung.")
    musik_group = app_commands.Group(name="musik", description="Musik im Voice-Channel abspielen.")

    def __init__(self, bot):
        self.bot = bot
        self._warteschlangen: dict[int, list[dict]] = {}

    # ---------- /song ----------
    async def _song_autocomplete(self, itx: discord.Interaction, current: str):
        spotify_tracks = await self._spotify_tracks_or_none()
        if spotify_tracks is not None:
            out = []
            for t in spotify_tracks:
                label = f"{t['titel']} – {t['kuenstler']}" if t["kuenstler"] else t["titel"]
                if current.lower() in label.lower():
                    out.append(app_commands.Choice(name=label[:100], value=t["uri"]))
            return out[:25]
        rows = await self.bot.db.fetchall("SELECT id, titel FROM songs ORDER BY titel")
        return [app_commands.Choice(name=r["titel"][:100], value=str(r["id"]))
               for r in rows if current.lower() in r["titel"].lower()][:25]

    @song_group.command(name="add", description="Fügt einen Song zur gemeinsamen Playlist hinzu.")
    @app_commands.describe(titel="Songtitel (+ Künstler)", link="Optional: Link (Spotify/YouTube/...)")
    async def song_add(self, itx: discord.Interaction, titel: str, link: str | None = None):
        await self.bot.db.execute("INSERT INTO songs (titel, link, added_by) VALUES (?,?,?)",
                                  titel, link, itx.user.id)
        spotify_hinweis = await self._spotify_push(itx.user.id, titel)
        await self._sync_playlist()
        text = f"„{titel}“ zur Playlist hinzugefügt."
        if spotify_hinweis:
            text += f" {spotify_hinweis}"
        await itx.response.send_message(text, ephemeral=True)

    @song_group.command(name="delete", description="Entfernt einen Song aus der Playlist.")
    @app_commands.describe(song="Welcher Song?")
    @app_commands.autocomplete(song=_song_autocomplete)
    async def song_delete(self, itx: discord.Interaction, song: str):
        if song.startswith("spotify:track:"):
            playlist_id = await self.bot.db.get_setting("spotify_playlist_id")
            access_token = (await self._spotify_access_token(itx.user.id)
                           or await self._service_access_token())
            if not access_token:
                await itx.response.send_message(
                    "Verbinde erst dein Spotify-Konto mit `/spotify login`.", ephemeral=True)
                return
            try:
                await spotify_client.remove_track(access_token, playlist_id, song)
            except aiohttp.ClientError:
                await itx.response.send_message("⚠️ Löschen bei Spotify fehlgeschlagen.",
                                                ephemeral=True)
                return
            await self._sync_playlist()
            await itx.response.send_message("Song aus der Spotify-Playlist entfernt.",
                                            ephemeral=True)
            return
        row = await self.bot.db.fetchone("SELECT * FROM songs WHERE id = ?", int(song))
        if not row:
            await itx.response.send_message("⚠️ Song nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM songs WHERE id = ?", int(song))
        await self._sync_playlist()
        await itx.response.send_message(f"„{row['titel']}“ gelöscht.", ephemeral=True)

    async def _service_access_token(self) -> str | None:
        """Für rein lesende Spotify-Zugriffe (Playlist anzeigen/abspielen), bei
        denen kein bestimmter User im Kontext ist – nimmt den Token von wem
        auch immer gerade verbunden ist."""
        for uid in (config.MELI_ID, config.JUSTI_ID):
            token = await self._spotify_access_token(uid)
            if token:
                return token
        return None

    async def _spotify_tracks_or_none(self) -> list[dict] | None:
        """None = Spotify nicht verbunden (Aufrufer soll auf die lokale
        Songliste zurückfallen). Liste = echte, aktuelle Spotify-Playlist,
        inkl. Songs, die schon vor der Bot-Anbindung dort lagen."""
        playlist_id = await self.bot.db.get_setting("spotify_playlist_id")
        if not playlist_id:
            return None
        access_token = await self._service_access_token()
        if not access_token:
            return None
        try:
            return await spotify_client.get_playlist_tracks(access_token, playlist_id)
        except aiohttp.ClientError:
            return None

    async def _build_playlist(self):
        spotify_url = await self.bot.db.get_setting("spotify_playlist_url")
        spotify_tracks = await self._spotify_tracks_or_none()
        if spotify_tracks is not None:
            if not spotify_tracks:
                beschreibung = "Noch leer – `/song add` legt los!"
            else:
                zeilen = [f"**{t['titel']}**" + (f" – {t['kuenstler']}" if t["kuenstler"] else "")
                         for t in spotify_tracks]
                beschreibung = "\n".join(zeilen)[:3900]
            anzahl = len(spotify_tracks)
        else:
            rows = await self.bot.db.fetchall("SELECT * FROM songs ORDER BY ts DESC")
            if not rows:
                beschreibung = "Noch leer – `/song add` legt los!"
            else:
                zeilen = [f"**{r['titel']}**" + (f" – {r['link']}" if r["link"] else "")
                         for r in rows]
                beschreibung = "\n".join(zeilen)[:3900]
            anzahl = len(rows)
        if spotify_url:
            beschreibung += f"\n\nSpotify-Playlist: {spotify_url}"
        titel = f"🎵 Eure Playlist ({anzahl})" if anzahl else "🎵 Eure Playlist"
        return emb("medien", titel, beschreibung), None

    async def _sync_playlist(self):
        ch = self.bot.channel_by_name("unsere-playlist")
        await tracked.sync(self.bot, PLAYLIST_KEY, "global", ch, self._build_playlist)

    @song_group.command(name="liste", description="Zeigt die gemeinsame Playlist.")
    async def playlist_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, PLAYLIST_KEY, "global", itx.channel, self._build_playlist)
        await itx.followup.send(f"Playlist aktuell: {msg.jump_url}" if msg else "Playlist ist leer.",
                                ephemeral=True)


    # ---------- /spotify (optional) ----------
    async def _spotify_access_token(self, user_id: int) -> str | None:
        refresh = await self.bot.db.get_setting(f"spotify_refresh_{user_id}")
        if not refresh:
            return None
        try:
            daten = await spotify_client.refresh_access_token(refresh)
        except aiohttp.ClientError:
            return None
        return daten.get("access_token")

    async def _spotify_push(self, user_id: int, titel: str) -> str | None:
        """Sucht den Song bei Spotify und fügt ihn der gemeinsamen Playlist hinzu,
        falls Spotify verbunden ist. Gibt None zurück (kein Hinweis), wenn Spotify
        gar nicht eingerichtet ist – sonst eine kurze Statusmeldung."""
        playlist_id = await self.bot.db.get_setting("spotify_playlist_id")
        if not playlist_id:
            return None
        access_token = await self._spotify_access_token(user_id)
        if not access_token:
            return None
        try:
            track = await spotify_client.search_track(access_token, titel)
            if not track:
                return "(bei Spotify nicht gefunden)"
            await spotify_client.add_track(access_token, playlist_id, track["uri"])
        except aiohttp.ClientError as fehler:
            print(f"Spotify-Sync-Fehler für {titel!r}: {fehler}")
            return "(Spotify-Sync gerade fehlgeschlagen)"
        return "Auch zur Spotify-Playlist hinzugefügt!"

    @spotify_group.command(name="login", description="Verbindet deinen Spotify-Account mit dem Bot.")
    async def spotify_login(self, itx: discord.Interaction):
        if not config.SPOTIFY_CLIENT_ID:
            await itx.response.send_message(
                "Spotify ist noch nicht eingerichtet (SPOTIFY_CLIENT_ID fehlt in der .env).",
                ephemeral=True)
            return
        url = spotify_client.login_url(state=str(itx.user.id))
        await itx.response.send_message(
            f"1. Öffne diesen Link und logg dich bei Spotify ein:\n{url}\n\n"
            "2. Nach der Bestätigung landet ihr auf einer Fehlerseite – das ist normal, "
            "wir haben keinen eigenen Server dahinter. Kopiert einfach die komplette "
            "Adresse aus der Adressleiste und schickt sie mit `/spotify code`.",
            ephemeral=True)

    @spotify_group.command(name="code",
                           description="Schließt die Spotify-Anmeldung ab (Code oder Adresse aus dem Browser).")
    @app_commands.describe(code="Der 'code'-Wert oder die komplette Adresse aus dem Browser")
    async def spotify_code(self, itx: discord.Interaction, code: str):
        wert = code.strip()
        if "code=" in wert:
            wert = parse_qs(urlparse(wert).query).get("code", [wert])[0]
        try:
            token_daten = await spotify_client.exchange_code(wert)
        except aiohttp.ClientError:
            await itx.response.send_message(
                "⚠️ Konnte den Code nicht einlösen – war er schon abgelaufen oder benutzt? "
                "`/spotify login` nochmal starten.", ephemeral=True)
            return
        await self.bot.db.set_setting(f"spotify_refresh_{itx.user.id}", token_daten["refresh_token"])
        await itx.response.send_message(
            "Spotify verbunden! Falls noch keine gemeinsame Playlist existiert, "
            "einmalig mit `/spotify playlist_neu` anlegen (oder `/spotify playlist_verbinden`, "
            "falls ihr schon eine habt).", ephemeral=True)

    @spotify_group.command(name="playlist_neu",
                           description="Erstellt einmalig eine neue gemeinsame Spotify-Playlist.")
    async def spotify_playlist_setup(self, itx: discord.Interaction):
        access_token = await self._spotify_access_token(itx.user.id)
        if not access_token:
            await itx.response.send_message(
                "Verbinde erst dein Spotify-Konto mit `/spotify login`.", ephemeral=True)
            return
        vorhanden = await self.bot.db.get_setting("spotify_playlist_url")
        if vorhanden:
            await itx.response.send_message(
                f"Es gibt schon eine gemeinsame Playlist: {vorhanden}", ephemeral=True)
            return
        try:
            profil = await spotify_client.me(access_token)
            playlist = await spotify_client.create_playlist(
                access_token, profil["id"], "Melusti – Unsere Playlist")
        except aiohttp.ClientError:
            await itx.response.send_message("⚠️ Playlist konnte nicht erstellt werden.",
                                            ephemeral=True)
            return
        await self.bot.db.set_setting("spotify_playlist_id", playlist["id"])
        await self.bot.db.set_setting("spotify_playlist_url", playlist["external_urls"]["spotify"])
        await self._sync_playlist()
        partner = config.name_of(config.partner_of(itx.user.id))
        await itx.response.send_message(
            f"Playlist erstellt: {playlist['external_urls']['spotify']}\n"
            f"{partner} kann jetzt mit `/spotify login` auch beitreten, dann landen "
            "neue `/song add`-Songs automatisch bei beiden in der Playlist.",
            ephemeral=True)

    @spotify_group.command(name="playlist_verbinden",
                           description="Verbindet eine bereits bestehende Spotify-Playlist mit dem Bot.")
    @app_commands.describe(playlist="Playlist-Link (oder ID) von Spotify")
    async def spotify_playlist_verbinden(self, itx: discord.Interaction, playlist: str):
        access_token = await self._spotify_access_token(itx.user.id)
        if not access_token:
            await itx.response.send_message(
                "Verbinde erst dein Spotify-Konto mit `/spotify login`.", ephemeral=True)
            return
        playlist_id = playlist.strip()
        if "open.spotify.com/playlist/" in playlist_id:
            playlist_id = playlist_id.split("open.spotify.com/playlist/")[1].split("?")[0].split("/")[0]
        try:
            daten = await spotify_client.get_playlist(access_token, playlist_id)
        except aiohttp.ClientError:
            await itx.response.send_message(
                "⚠️ Playlist nicht gefunden – Link korrekt und Zugriff vorhanden?", ephemeral=True)
            return
        await self.bot.db.set_setting("spotify_playlist_id", daten["id"])
        await self.bot.db.set_setting("spotify_playlist_url", daten["external_urls"]["spotify"])
        await self._sync_playlist()
        await itx.response.send_message(
            f"Verbunden mit „{daten['name']}“: {daten['external_urls']['spotify']}\n"
            "Neue `/song add`-Songs landen jetzt automatisch dort. Falls das Hinzufügen bei "
            f"{config.name_of(config.partner_of(itx.user.id))} fehlschlägt: die Playlist in der "
            "Spotify-App unter den Playlist-Optionen als „gemeinsam bearbeitbar“ (collaborative) "
            "markieren.", ephemeral=True)

    # ---------- /musik: echte Audio-Wiedergabe im Voice-Channel ----------
    def _warteschlange(self, guild_id: int) -> list[dict]:
        return self._warteschlangen.setdefault(guild_id, [])

    async def _song_suchen(self, suchbegriff: str) -> dict | None:
        loop = asyncio.get_event_loop()

        def _extrahieren():
            with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                info = ydl.extract_info(f"ytsearch1:{suchbegriff}", download=False)
                eintraege = info.get("entries") if info else None
                if not eintraege:
                    return None
                treffer = eintraege[0]
                return {"title": treffer.get("title", suchbegriff), "url": treffer["url"],
                        "webpage_url": treffer.get("webpage_url", "")}

        return await loop.run_in_executor(None, _extrahieren)

    async def _naechster_song(self, guild: discord.Guild, text_channel):
        warteschlange = self._warteschlange(guild.id)
        vc = guild.voice_client
        if not warteschlange or not vc:
            return
        song = warteschlange.pop(0)
        quelle = discord.FFmpegPCMAudio(song["url"], executable=config.FFMPEG_PATH, **FFMPEG_OPTS)

        def _nach_ende(fehler: Exception | None):
            if fehler:
                print(f"Musik-Player-Fehler: {fehler}")
            asyncio.run_coroutine_threadsafe(self._naechster_song(guild, text_channel), self.bot.loop)

        vc.play(quelle, after=_nach_ende)
        asyncio.run_coroutine_threadsafe(
            text_channel.send(embed=emb("spiele", "🎶 Spielt jetzt", f"**{song['title']}**")),
            self.bot.loop)

    async def _verbinden(self, itx: discord.Interaction) -> bool:
        """Erwartet eine BEREITS bestätigte (deferred) Interaction – der
        Verbindungsaufbau zum Voice-Channel dauert oft länger als Discords
        3-Sekunden-Limit für die erste Antwort, daher muss vorher defer()
        aufgerufen worden sein (sonst: 'The application did not respond')."""
        if not config.FFMPEG_PATH:
            await itx.followup.send(
                "⚠️ ffmpeg wurde nicht gefunden. `winget install Gyan.FFmpeg` ausführen, "
                "dann Bot neu starten.", ephemeral=True)
            return False
        if not itx.user.voice or not itx.user.voice.channel:
            await itx.followup.send("Du musst dafür in einem Voice-Channel sein.",
                                    ephemeral=True)
            return False
        kanal = itx.user.voice.channel
        if not itx.guild.voice_client:
            await kanal.connect()
        elif itx.guild.voice_client.channel != kanal:
            await itx.guild.voice_client.move_to(kanal)
        return True

    @musik_group.command(name="play",
                         description="Spielt einen Song im Voice-Channel ab (YouTube-Suche).")
    @app_commands.describe(suchbegriff="Songtitel und/oder Interpret")
    async def play(self, itx: discord.Interaction, suchbegriff: str):
        await itx.response.defer()
        if not await self._verbinden(itx):
            return
        song = await self._song_suchen(suchbegriff)
        if not song:
            await itx.followup.send("Nichts gefunden.")
            return
        warteschlange = self._warteschlange(itx.guild.id)
        warteschlange.append(song)
        vc = itx.guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused():
            await self._naechster_song(itx.guild, itx.channel)
            await itx.followup.send(f"Spielt jetzt: **{song['title']}**")
        else:
            await itx.followup.send(f"Zur Warteschlange hinzugefügt: **{song['title']}**")

    @musik_group.command(name="playlist",
                         description="Spielt eure Playlist der Reihe nach ab (echte Spotify-Playlist, falls verbunden).")
    async def play_playlist(self, itx: discord.Interaction):
        spotify_tracks = await self._spotify_tracks_or_none()
        if spotify_tracks is not None:
            suchbegriffe = [f"{t['titel']} {t['kuenstler']}".strip() for t in spotify_tracks]
        else:
            rows = await self.bot.db.fetchall("SELECT * FROM songs ORDER BY ts")
            suchbegriffe = [r["titel"] for r in rows]
        if not suchbegriffe:
            await itx.response.send_message("Eure Playlist ist leer – erst `/song add`.",
                                            ephemeral=True)
            return
        await itx.response.defer()
        if not await self._verbinden(itx):
            return
        warteschlange = self._warteschlange(itx.guild.id)
        hinzugefuegt = 0
        for suchbegriff in suchbegriffe:
            song = await self._song_suchen(suchbegriff)
            if song:
                warteschlange.append(song)
                hinzugefuegt += 1
        vc = itx.guild.voice_client
        if vc and not vc.is_playing() and not vc.is_paused():
            await self._naechster_song(itx.guild, itx.channel)
        await itx.followup.send(f"{hinzugefuegt} Songs zur Warteschlange hinzugefügt.")

    @musik_group.command(name="skip", description="Überspringt den aktuellen Song.")
    async def skip(self, itx: discord.Interaction):
        vc = itx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            await itx.response.send_message("Gerade läuft nichts.", ephemeral=True)
            return
        vc.stop()  # triggert automatisch den nächsten Song aus der Warteschlange
        await itx.response.send_message("Übersprungen.", ephemeral=True)

    @musik_group.command(name="pause", description="Pausiert die Musik-Wiedergabe.")
    async def pause(self, itx: discord.Interaction):
        vc = itx.guild.voice_client
        if not vc or not vc.is_playing():
            await itx.response.send_message("Gerade läuft nichts.", ephemeral=True)
            return
        vc.pause()
        await itx.response.send_message("Pausiert.", ephemeral=True)

    @musik_group.command(name="resume", description="Setzt die Musik-Wiedergabe fort.")
    async def resume(self, itx: discord.Interaction):
        vc = itx.guild.voice_client
        if not vc or not vc.is_paused():
            await itx.response.send_message("Nichts pausiert.", ephemeral=True)
            return
        vc.resume()
        await itx.response.send_message("Geht weiter.", ephemeral=True)

    @musik_group.command(name="stop",
                         description="Stoppt die Wiedergabe, leert die Warteschlange, verlässt den Voice-Channel.")
    async def stop(self, itx: discord.Interaction):
        self._warteschlangen.pop(itx.guild.id, None)
        vc = itx.guild.voice_client
        if vc:
            await vc.disconnect(force=True)
        await itx.response.send_message("Gestoppt, bin raus.", ephemeral=True)

    @musik_group.command(name="queue", description="Zeigt die aktuelle Musik-Warteschlange.")
    async def queue_cmd(self, itx: discord.Interaction):
        warteschlange = self._warteschlange(itx.guild.id)
        if not warteschlange:
            await itx.response.send_message("Warteschlange ist leer.", ephemeral=True)
            return
        zeilen = [f"{i + 1}. {s['title']}" for i, s in enumerate(warteschlange)]
        await itx.response.send_message(
            embed=emb("spiele", "🎶 Warteschlange", "\n".join(zeilen)[:4000]), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Musik(bot))
