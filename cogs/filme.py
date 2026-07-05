"""
Filmabend & Watchlists 🎬
- /filmabend: läuft UNABHÄNGIG von der Watchlist. Wer dran ist, schlägt 3
  eigene Filme vor, der/die andere wählt per Button einen davon aus.
  Die Vorschlagenden-Rolle wechselt danach automatisch ab (Meli startet).
- Watchlists (Filme & YouTube) mit Kategorien und gesehen-Status – reine
  Merkliste, hat mit dem Filmabend-Ablauf nichts zu tun.
- Film-Archiv (nur Filmabend-Filme) mit Doppel-Rating auf der Letterboxd-
  Sterne-Skala (0.5-5★, intern als 1-10 gespeichert) – kommt automatisch
  rein, sobald ihr den Film auf Letterboxd bewertet, kein manuelles
  Bewerten auf Discord nötig.
- Letterboxd: CSV-Import (einmalig, historisch) UND automatischer
  automatischer RSS-Sync alle 10 Minuten (öffentliche Profile, kein API-Key nötig –
  LETTERBOXD_MELI/LETTERBOXD_JUSTI in .env). Filme, die über /filmabend
  gewählt wurden, bekommen so automatisch Bewertung + Jahr + Poster-Link
  ins Film-Archiv; alle anderen (eigenständig geschauten) Filme lösen
  stattdessen eine Benachrichtigung in #film-benachrichtigung aus.
- Film-Awards: Monats-Abstimmung per Reaction.
"""
import csv
import datetime as dt
import io
import json
import re
import xml.etree.ElementTree as ET
from typing import Literal

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import tracked
from utils.design import emb

LETTERBOXD_NS = {"lb": "https://letterboxd.com"}
LETTERBOXD_RSS_URL = "https://letterboxd.com/{user}/rss/"
_POSTER_RE = re.compile(r'<img src="([^"]+)"')

ZIFFERN = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _sterne_text(wert_zehntel: int) -> str:
    """Rendert einen intern als 1-10 gespeicherten Wert als Letterboxd-Sterne
    (halbe Sterne als ½), z.B. 7 -> '★★★½ (3.5/5)'."""
    voll = wert_zehntel // 2
    halb = wert_zehntel % 2 == 1
    sterne = "★" * voll + ("½" if halb else "")
    return f"{sterne} ({wert_zehntel / 2:g}/5)"


FILMABEND_DRAN_KEY = "filmabend_dran"
FILMABEND_RESTE_KEY = "filmabend_reste"

FILM_AWARDS_KATEGORIEN = {
    "bester": "🏆 Bester Film",
    "schlechtester": "🗑️ Schlechtester Film",
    "lustigster": "😂 Lustigster Film",
    "ueberraschung": "😮 Überraschung des Monats",
}


class FilmabendView(discord.ui.View):
    def __init__(self, cog: "Filme", vorschlagender_id: int, filme: list[str]):
        super().__init__(timeout=259200)  # 3 Tage
        self.cog = cog
        self.vorschlagender_id = vorschlagender_id
        self.filme = filme
        for i, titel in enumerate(filme):
            self.add_item(self._pick_button(i, titel))

    def _pick_button(self, i: int, titel: str) -> discord.ui.Button:
        btn = discord.ui.Button(label=titel[:80], style=discord.ButtonStyle.success, row=0)
        async def cb(itx: discord.Interaction):
            await self.cog.filmabend_pick(itx, self, i)
        btn.callback = cb
        return btn


class NeueFilmeModal(discord.ui.Modal):
    """Nimmt alle benötigten neuen Filmvorschläge gleichzeitig entgegen."""
    def __init__(self, cog: "Filme", user_id: int, reste: list[str], anzahl: int):
        endung = "n Film" if anzahl == 1 else " Filme"
        super().__init__(title=f"{anzahl} neue{endung} vorschlagen")
        self.cog = cog
        self.user_id = user_id
        self.reste = reste
        self.eingaben: list[discord.ui.TextInput] = []
        for i in range(anzahl):
            eingabe = discord.ui.TextInput(label=f"Film {i + 1}", max_length=100)
            self.add_item(eingabe)
            self.eingaben.append(eingabe)

    async def on_submit(self, itx: discord.Interaction):
        neue = [str(e) for e in self.eingaben]
        kandidaten = self.reste + neue
        await itx.response.send_message("Vorschlag gepostet – siehe Kanal!", ephemeral=True)
        await self.cog.poste_runde(itx.channel, self.user_id, kandidaten)


class FilmabendStartView(discord.ui.View):
    """Erst die eigenen Reste sehen, dann per Button entscheiden. Für neue
    Filme öffnet sich ein Modal, in dem alle auf einmal eingetragen werden."""
    def __init__(self, cog: "Filme", user_id: int, reste: list[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.reste = reste
        if reste:
            self.add_item(self._reste_button())
        if 0 < len(reste) < 3:
            self.add_item(self._auffuellen_button())
        self.add_item(self._alle_neu_button())

    def _reste_button(self) -> discord.ui.Button:
        btn = discord.ui.Button(label=f"Reste behalten ({len(self.reste)})",
                                style=discord.ButtonStyle.success)
        async def cb(itx: discord.Interaction):
            await itx.response.edit_message(
                embed=emb("medien", "Vorschlag gepostet", "Siehe Kanal für die Wahl-Buttons."),
                view=None)
            await self.cog.poste_runde(itx.channel, self.user_id, self.reste)
        btn.callback = cb
        return btn

    def _auffuellen_button(self) -> discord.ui.Button:
        benoetigt = 3 - len(self.reste)
        btn = discord.ui.Button(label=f"Auffüllen (+{benoetigt} neu)",
                                style=discord.ButtonStyle.primary)
        async def cb(itx: discord.Interaction):
            await itx.response.send_modal(
                NeueFilmeModal(self.cog, self.user_id, self.reste, benoetigt))
        btn.callback = cb
        return btn

    def _alle_neu_button(self) -> discord.ui.Button:
        btn = discord.ui.Button(label="3 komplett neue Filme", style=discord.ButtonStyle.danger)
        async def cb(itx: discord.Interaction):
            await itx.response.send_modal(NeueFilmeModal(self.cog, self.user_id, [], 3))
        btn.callback = cb
        return btn


class Filme(commands.Cog):
    watchlist_group = app_commands.Group(name="watchlist", description="Watchlist verwalten.")
    film_group = app_commands.Group(name="film", description="Film-Archiv, Bewertungen & Awards.")
    letterboxd_group = app_commands.Group(name="letterboxd", description="Letterboxd-Import/Sync.")

    def __init__(self, bot):
        self.bot = bot
        self.letterboxd_daily_sync.start()
        self.film_awards_monatsende.start()

    def cog_unload(self):
        self.letterboxd_daily_sync.cancel()
        self.film_awards_monatsende.cancel()

    # ---------- Filmabend-Runde (unabhängig von der Watchlist) ----------
    # Jede Person hat ihre eigenen "Reste" (übrig gebliebene Filme aus der
    # letzten eigenen Vorschlagsrunde). Beim Vorschlagen wählt man einen
    # von drei Modi: die Reste unverändert lassen, sie auf 3 auffüllen,
    # oder komplett neu vorschlagen. Nach der Wahl werden die nicht
    # gewählten Filme automatisch die neuen Reste für nächstes Mal.
    async def _wer_ist_dran(self) -> int:
        dran = await self.bot.db.get_setting(FILMABEND_DRAN_KEY)
        return int(dran) if dran else config.MELI_ID

    async def _lade_reste(self) -> dict:
        raw = await self.bot.db.get_setting(FILMABEND_RESTE_KEY)
        return json.loads(raw) if raw else {}

    async def _speichere_reste(self, user_id: int, filme: list[str]):
        alle = await self._lade_reste()
        alle[str(user_id)] = filme
        await self.bot.db.set_setting(FILMABEND_RESTE_KEY, json.dumps(alle))

    @app_commands.command(name="filmabend",
                          description="Zeigt deine Reste und lässt dich Filme für den Filmabend vorschlagen.")
    async def filmabend(self, itx: discord.Interaction):
        dran_id = await self._wer_ist_dran()
        if itx.user.id != dran_id:
            await itx.response.send_message(
                f"Gerade ist {config.name_of(dran_id)} mit Vorschlagen dran, nicht du.",
                ephemeral=True)
            return
        reste_alle = await self._lade_reste()
        meine_reste = reste_alle.get(str(itx.user.id), [])
        reste_text = ("Deine Reste von letztem Mal:\n" +
                     "\n".join(f"**{f}**" for f in meine_reste)) if meine_reste else \
                    "Du hast gerade keine Reste von letztem Mal – schlag 3 neue Filme vor."
        view = FilmabendStartView(self, itx.user.id, meine_reste)
        await itx.response.send_message(
            embed=emb("medien", "🎬 Filmabend – wie möchtest du vorschlagen?", reste_text),
            view=view, ephemeral=True)

    async def poste_runde(self, channel, user_id: int, kandidaten: list[str]):
        partner_id = config.partner_of(user_id)
        await self.bot.db.set_setting(FILMABEND_DRAN_KEY, partner_id)
        view = FilmabendView(self, user_id, kandidaten)
        zeilen = "\n".join(f"**{f}**" for f in kandidaten)
        e = emb("medien", "🎬 Filmabend – wähl einen aus!",
               f"{config.name_of(user_id)} schlägt vor:\n\n{zeilen}\n\n"
               f"{config.name_of(partner_id)}, du bist dran zu wählen!")
        await channel.send(embed=e, view=view)

    async def filmabend_pick(self, itx: discord.Interaction, view: FilmabendView, i: int):
        if itx.user.id != config.partner_of(view.vorschlagender_id):
            await itx.response.send_message(
                "Nur die vorgeschlagene Person wählt hier – du hast ja schon vorgeschlagen.",
                ephemeral=True)
            return
        titel = view.filme[i]
        heute = dt.datetime.now(config.TZ).date()
        reste = [f for j, f in enumerate(view.filme) if j != i]
        await self._speichere_reste(view.vorschlagender_id, reste)
        await self.bot.db.execute(
            "INSERT INTO film_runden (vorschlagender, optionen, gewaehlt, reste) VALUES (?,?,?,?)",
            view.vorschlagender_id, ",".join(view.filme), titel, ",".join(reste))
        await self.bot.db.execute(
            "INSERT INTO film_archiv (titel, geschaut_am, quelle) VALUES (?, ?, 'filmabend')",
            titel, heute.isoformat())
        await self._sync_film_archiv()
        for item in view.children:
            item.disabled = True
        reste_text = (f"Für {config.name_of(view.vorschlagender_id)} bleiben übrig: "
                     f"{', '.join(reste)}") if reste else \
                    f"{config.name_of(view.vorschlagender_id)} hat keine Reste mehr übrig."
        await itx.response.edit_message(
            embed=emb("medien", "🎬 Entschieden!",
                     f"Heute wird **{titel}** geschaut. Danach mit `/film bewerten` bewerten!\n\n"
                     f"Nächstes Mal ist {config.name_of(itx.user.id)} mit Vorschlagen dran. "
                     f"{reste_text}"),
            view=view)

    # ---------- Film-Archiv & Doppel-Rating (kommt automatisch von Letterboxd) ----------
    async def _pruefe_doppelrating(self, film_id: int):
        """Postet die 'Doppel-Rating komplett'-Meldung, sobald beide Letterboxd-
        Bewertungen für einen Film eingetroffen sind."""
        aktuell = await self.bot.db.fetchone("SELECT * FROM film_archiv WHERE id = ?", film_id)
        if aktuell["rating_a"] is None or aktuell["rating_b"] is None:
            return
        schnitt = (aktuell["rating_a"] + aktuell["rating_b"]) / 2 / 2
        ch = self.bot.channel_by_name("film-archiv")
        if ch:
            await ch.send(embed=emb(
                "medien", f"🎬 {aktuell['titel']} – Doppel-Rating komplett",
                f"{config.MELI_NAME}: **{_sterne_text(aktuell['rating_a'])}**\n"
                f"{config.JUSTI_NAME}: **{_sterne_text(aktuell['rating_b'])}**\n"
                f"Schnitt: **{schnitt:g}/5**"))

    async def _build_film_archiv(self):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM film_archiv WHERE geschaut_am IS NOT NULL ORDER BY geschaut_am DESC")
        if not rows:
            return emb("medien", "🎬 Film-Archiv", "Noch nichts geschaut – `/filmabend` starten!"), None
        zeilen = []
        for r in rows:
            if r["rating_a"] is not None and r["rating_b"] is not None:
                schnitt = (r["rating_a"] + r["rating_b"]) / 2 / 2
                bewertung = (f" · {config.MELI_NAME} {_sterne_text(r['rating_a'])} · "
                            f"{config.JUSTI_NAME} {_sterne_text(r['rating_b'])} · Ø{schnitt:g}/5")
            elif r["rating_a"] is not None or r["rating_b"] is not None:
                bewertung = " · eine Bewertung steht noch aus"
            else:
                bewertung = " · noch nicht bewertet"
            titel = f"[{r['titel']}]({r['letterboxd_url']})" if r["letterboxd_url"] else r["titel"]
            jahr = f" ({r['jahr']})" if r["jahr"] else ""
            zeilen.append(f"**{titel}**{jahr} – {r['geschaut_am'] or '?'}{bewertung}")
        return emb("medien", f"🎬 Film-Archiv ({len(rows)})", "\n".join(zeilen)[:4000]), None

    async def _sync_film_archiv(self):
        ch = self.bot.channel_by_name("film-archiv")
        await tracked.sync(self.bot, "film_archiv", "global", ch, self._build_film_archiv)

    @film_group.command(name="archiv", description="Zeigt alle geschauten Filme mit Bewertungen.")
    async def film_archiv_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, "film_archiv", "global", itx.channel, self._build_film_archiv)
        await itx.followup.send(
            f"Film-Archiv aktuell: {msg.jump_url}" if msg else "Noch nichts im Archiv.", ephemeral=True)

    # ---------- Watchlists ----------
    async def _watchlist_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT id, titel, typ FROM watchlist ORDER BY titel")
        return [app_commands.Choice(name=f"{r['titel']} ({r['typ']})"[:100], value=r["id"])
                for r in rows if current.lower() in r["titel"].lower()][:25]

    @watchlist_group.command(name="add",
                             description="Fügt einen Film oder ein YouTube-Video zur Watchlist hinzu.")
    @app_commands.describe(typ="Film oder YouTube", titel="Titel",
                           kategorie="Optional: Kategorie", link="Optional: Link")
    async def watchlist_add(self, itx: discord.Interaction, typ: Literal["film", "youtube"],
                            titel: str, kategorie: str = "Allgemein", link: str | None = None):
        await self.bot.db.execute(
            "INSERT INTO watchlist (typ, kategorie, titel, link, added_by) VALUES (?,?,?,?,?)",
            typ, kategorie, titel, link, itx.user.id)
        await self._sync_watchlist(typ)
        label = "Film" if typ == "film" else "YouTube"
        await itx.response.send_message(f"„{titel}“ zur {label}-Watchlist hinzugefügt.", ephemeral=True)

    @watchlist_group.command(name="gesehen",
                             description="Markiert einen Watchlist-Eintrag als gesehen/ungesehen.")
    @app_commands.describe(eintrag="Welcher Eintrag?")
    @app_commands.autocomplete(eintrag=_watchlist_autocomplete)
    async def watchlist_toggle(self, itx: discord.Interaction, eintrag: int):
        row = await self.bot.db.fetchone("SELECT * FROM watchlist WHERE id = ?", eintrag)
        if not row:
            await itx.response.send_message("⚠️ Eintrag nicht gefunden.", ephemeral=True)
            return
        neu = 0 if row["gesehen"] else 1
        heute = dt.datetime.now(config.TZ).date().isoformat() if neu else None
        await self.bot.db.execute("UPDATE watchlist SET gesehen = ?, gesehen_am = ? WHERE id = ?",
                                  neu, heute, eintrag)
        await self._sync_watchlist(row["typ"])
        status = "gesehen" if neu else "ungesehen"
        await itx.response.send_message(f"„{row['titel']}“ als {status} markiert.", ephemeral=True)

    @watchlist_group.command(name="delete", description="Entfernt einen Watchlist-Eintrag.")
    @app_commands.describe(eintrag="Welcher Eintrag?")
    @app_commands.autocomplete(eintrag=_watchlist_autocomplete)
    async def watchlist_delete(self, itx: discord.Interaction, eintrag: int):
        row = await self.bot.db.fetchone("SELECT * FROM watchlist WHERE id = ?", eintrag)
        if not row:
            await itx.response.send_message("⚠️ Eintrag nicht gefunden.", ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM watchlist WHERE id = ?", eintrag)
        await self._sync_watchlist(row["typ"])
        await itx.response.send_message(f"„{row['titel']}“ gelöscht.", ephemeral=True)

    @watchlist_group.command(name="liste", description="Zeigt die Watchlist.")
    @app_commands.describe(typ="Film oder YouTube")
    async def watchlist_cmd(self, itx: discord.Interaction, typ: Literal["film", "youtube"] = "film"):
        await itx.response.defer(ephemeral=True)
        ch_name = "watchlist-filme" if typ == "film" else "watchlist-youtube"
        ch = self.bot.channel_by_name(ch_name) or itx.channel
        msg = await tracked.sync(self.bot, f"watchlist_{typ}", "global", ch,
                                 lambda: self._build_watchlist(typ))
        await itx.followup.send(
            f"Watchlist aktuell: {msg.jump_url}" if msg else "Watchlist ist leer.", ephemeral=True)

    async def _build_watchlist(self, typ: str):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM watchlist WHERE typ = ? ORDER BY kategorie, titel", typ)
        label = "Filme" if typ == "film" else "YouTube"
        if not rows:
            return emb("medien", f"🎬 Watchlist – {label}",
                       "Noch leer – `/watchlist add` legt los!"), None
        kategorien: dict[str, list] = {}
        for r in rows:
            kategorien.setdefault(r["kategorie"], []).append(r)
        bloecke = []
        for kat, items in kategorien.items():
            zeilen = []
            for r in items:
                haken = "✅" if r["gesehen"] else "⬜"
                link_teil = f" – {r['link']}" if r["link"] else ""
                zeilen.append(f"{haken} {r['titel']}{link_teil}")
            bloecke.append(f"**{kat}**\n" + "\n".join(zeilen))
        return emb("medien", f"🎬 Watchlist – {label} ({len(rows)})", "\n\n".join(bloecke)[:4000]), None

    async def _sync_watchlist(self, typ: str):
        ch_name = "watchlist-filme" if typ == "film" else "watchlist-youtube"
        ch = self.bot.channel_by_name(ch_name)
        await tracked.sync(self.bot, f"watchlist_{typ}", "global", ch, lambda: self._build_watchlist(typ))

    # ---------- Gemeinsame Verarbeitung: Filmabend-Treffer vs. eigenständig ----------
    async def _verarbeite_letterboxd_eintrag(self, user_id: int, eintrag: dict,
                                             benachrichtigen: bool) -> None:
        """Ein Letterboxd-Diary-Eintrag betrifft entweder einen bereits über
        /filmabend gewählten Film (dann fließen Bewertung + Metadaten dort
        automatisch ein) oder einen eigenständig geschauten Film (dann gibt's
        nur eine Benachrichtigung, er landet NICHT im Film-Archiv)."""
        spalte = "rating_a" if config.slot_of(user_id) == "a" else "rating_b"
        vorhanden = await self.bot.db.fetchone(
            "SELECT * FROM film_archiv WHERE titel = ? COLLATE NOCASE AND quelle = 'filmabend'",
            eintrag["titel"])
        if vorhanden:
            felder, werte = [], []
            if vorhanden[spalte] is None and eintrag["rating"] is not None:
                felder.append(f"{spalte} = ?")
                werte.append(eintrag["rating"])
            for spalte_name in ("jahr", "letterboxd_url", "poster_url"):
                if not vorhanden[spalte_name] and eintrag.get(spalte_name):
                    felder.append(f"{spalte_name} = ?")
                    werte.append(eintrag[spalte_name])
            if felder:
                werte.append(vorhanden["id"])
                await self.bot.db.execute(
                    f"UPDATE film_archiv SET {', '.join(felder)} WHERE id = ?", *werte)
                await self._sync_film_archiv()
                await self._pruefe_doppelrating(vorhanden["id"])
            return
        if benachrichtigen:
            await self._film_benachrichtigung(user_id, eintrag)

    async def _film_benachrichtigung(self, user_id: int, eintrag: dict):
        ch = self.bot.channel_by_name("film-benachrichtigung")
        if not ch:
            return
        titel = eintrag["titel"] + (f" ({eintrag['jahr']})" if eintrag.get("jahr") else "")
        beschreibung = f"{config.name_of(user_id)} hat **{titel}** geschaut"
        if eintrag["rating"] is not None:
            beschreibung += f" – {_sterne_text(eintrag['rating'])}"
        e = emb("medien", "🎬 Neuer Letterboxd-Eintrag", beschreibung)
        if eintrag.get("letterboxd_url"):
            e.url = eintrag["letterboxd_url"]
        if eintrag.get("poster_url"):
            e.set_thumbnail(url=eintrag["poster_url"])
        await ch.send(embed=e)

    # ---------- Letterboxd-Import (einmalig, historisch – ohne Kanal-Spam) ----------
    @letterboxd_group.command(name="import",
                              description="Importiert eine Letterboxd-CSV (diary.csv-Export), nur einmalig nötig.")
    @app_commands.describe(datei="Die exportierte CSV-Datei von Letterboxd")
    async def letterboxd_import(self, itx: discord.Interaction, datei: discord.Attachment):
        await itx.response.defer(ephemeral=True)
        # Gleicher Dedup-Namensraum wie der RSS-Sync (echter Letterboxd-Name),
        # damit spätere Syncs überlappende Einträge nicht doppelt melden.
        username = config.LETTERBOXD_MELI if itx.user.id == config.MELI_ID else config.LETTERBOXD_JUSTI
        roh = await datei.read()
        text = roh.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        verarbeitet = 0
        for zeile in reader:
            titel = zeile.get("Name") or zeile.get("Title")
            if not titel:
                continue
            datum = zeile.get("Watched Date") or zeile.get("Date")
            try:
                await self.bot.db.execute(
                    "INSERT INTO letterboxd_verarbeitet (username, titel, datum) VALUES (?,?,?)",
                    username or f"csv:{itx.user.id}", titel, datum or "")
            except Exception:
                continue  # schon mal importiert
            roh_rating = zeile.get("Rating")
            eintrag = {
                "titel": titel, "datum": datum,
                "rating": round(float(roh_rating) * 2) if roh_rating else None,
                "jahr": int(zeile["Year"]) if zeile.get("Year") else None,
                "letterboxd_url": zeile.get("Letterboxd URI"),
                "poster_url": None,
            }
            # Historischer Bulk-Import: keine Benachrichtigungen, nur Filmabend-Treffer aktualisieren.
            await self._verarbeite_letterboxd_eintrag(itx.user.id, eintrag, benachrichtigen=False)
            verarbeitet += 1
        await itx.followup.send(
            f"{verarbeitet} Einträge verarbeitet – Bewertungen für eure Filmabend-Filme sind jetzt "
            "eingetragen, sofern enthalten.", ephemeral=True)

    # ---------- Letterboxd-Auto-Sync (öffentlicher RSS-Feed, kein API-Key) ----------
    async def _letterboxd_fetch(self, username: str) -> list[dict]:
        url = LETTERBOXD_RSS_URL.format(user=username)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()
        except aiohttp.ClientError:
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        eintraege = []
        for item in root.iter("item"):
            titel = item.find("lb:filmTitle", LETTERBOXD_NS)
            datum = item.find("lb:watchedDate", LETTERBOXD_NS)
            if titel is None or datum is None or not titel.text or not datum.text:
                continue  # z.B. eine Watchlist-/Listen-Aktivität ohne Diary-Eintrag
            rating = item.find("lb:memberRating", LETTERBOXD_NS)
            jahr = item.find("lb:filmYear", LETTERBOXD_NS)
            link = item.find("link")
            beschreibung = item.find("description")
            poster_treffer = _POSTER_RE.search(beschreibung.text) if beschreibung is not None \
                and beschreibung.text else None
            eintraege.append({
                "titel": titel.text,
                "datum": datum.text,
                "rating": round(float(rating.text) * 2) if rating is not None and rating.text else None,
                "jahr": int(jahr.text) if jahr is not None and jahr.text else None,
                "letterboxd_url": link.text if link is not None else None,
                "poster_url": poster_treffer.group(1) if poster_treffer else None,
            })
        return eintraege

    async def _letterboxd_sync_user(self, username: str) -> int:
        user_id = config.MELI_ID if username == config.LETTERBOXD_MELI else config.JUSTI_ID
        neu = 0
        for eintrag in await self._letterboxd_fetch(username):
            try:
                await self.bot.db.execute(
                    "INSERT INTO letterboxd_verarbeitet (username, titel, datum) VALUES (?,?,?)",
                    username, eintrag["titel"], eintrag["datum"])
            except Exception:
                continue  # schon verarbeitet, nichts Neues
            await self._verarbeite_letterboxd_eintrag(user_id, eintrag, benachrichtigen=True)
            neu += 1
        return neu

    @letterboxd_group.command(name="sync",
                              description="Holt neue Letterboxd-Diary-Einträge sofort (statt auf Nachts zu warten).")
    async def letterboxd_sync_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        namen = [n for n in (config.LETTERBOXD_MELI, config.LETTERBOXD_JUSTI) if n]
        if not namen:
            await itx.followup.send(
                "Kein Letterboxd-Nutzername in der .env hinterlegt "
                "(LETTERBOXD_MELI / LETTERBOXD_JUSTI).", ephemeral=True)
            return
        gesamt = sum([await self._letterboxd_sync_user(n) for n in namen])
        await itx.followup.send(f"{gesamt} neue Letterboxd-Einträge verarbeitet.", ephemeral=True)

    @tasks.loop(minutes=10)
    async def letterboxd_daily_sync(self):
        namen = [n for n in (config.LETTERBOXD_MELI, config.LETTERBOXD_JUSTI) if n]
        if not namen:
            return
        for n in namen:
            await self._letterboxd_sync_user(n)

    @letterboxd_daily_sync.before_loop
    async def _before_letterboxd_sync(self):
        await self.bot.wait_until_ready()

    # ---------- Film-Awards (Monats-Abstimmung per Reaction, 4 Kategorien) ----------
    async def _start_awards_fuer_monat(self, monat_date: dt.date, ch) -> bool:
        monatsanfang = monat_date.replace(day=1)
        monatsende = (monatsanfang.replace(day=28) + dt.timedelta(days=4)).replace(day=1) \
            - dt.timedelta(days=1)
        rows = await self.bot.db.fetchall(
            "SELECT * FROM film_archiv WHERE geschaut_am >= ? AND geschaut_am <= ? "
            "ORDER BY geschaut_am", monatsanfang.isoformat(), monatsende.isoformat())
        if not rows:
            return False
        rows = rows[:10]
        monat_key = f"{monatsanfang:%Y-%m}"
        liste = "\n".join(f"{ZIFFERN[i]} {r['titel']}" for i, r in enumerate(rows))
        for kategorie, label in FILM_AWARDS_KATEGORIEN.items():
            e = emb("medien", f"{label} – {monatsanfang:%B %Y}",
                   f"Reagiert mit der Zahl für euren Favoriten in dieser Kategorie!\n\n{liste}")
            msg = await ch.send(embed=e)
            for i in range(len(rows)):
                await msg.add_reaction(ZIFFERN[i])
            await self.bot.db.set_setting(f"film_awards_msg_{kategorie}_{monat_key}",
                                          f"{msg.channel.id}:{msg.id}")
        await self.bot.db.set_setting(f"film_awards_filme_{monat_key}",
                                      ",".join(str(r["id"]) for r in rows))
        await self.bot.db.set_setting("film_awards_gestartet_am",
                                      dt.datetime.now(config.TZ).isoformat())
        return True

    async def _auswerten_fuer_monat(self, monat_key: str) -> list[str] | None:
        ids_roh = await self.bot.db.get_setting(f"film_awards_filme_{monat_key}")
        if not ids_roh:
            return None
        ids = [int(x) for x in ids_roh.split(",")]
        ergebnisse = []
        for kategorie, label in FILM_AWARDS_KATEGORIEN.items():
            ref = await self.bot.db.get_setting(f"film_awards_msg_{kategorie}_{monat_key}")
            if not ref:
                continue
            channel_id, message_id = (int(x) for x in ref.split(":"))
            zielkanal = self.bot.get_channel(channel_id)
            if not zielkanal:
                continue
            try:
                msg = await zielkanal.fetch_message(message_id)
            except discord.HTTPException:
                continue
            bester_id, beste_stimmen = None, -1
            for i, film_id in enumerate(ids):
                reaction = discord.utils.get(msg.reactions, emoji=ZIFFERN[i])
                stimmen = (reaction.count - 1) if reaction else 0  # -1: Bots eigene Reaction
                if stimmen > beste_stimmen:
                    beste_stimmen, bester_id = stimmen, film_id
            if bester_id is None:
                continue
            row = await self.bot.db.fetchone("SELECT * FROM film_archiv WHERE id = ?", bester_id)
            await self.bot.db.execute(
                "INSERT INTO film_awards (monat, kategorie, film_id) VALUES (?, ?, ?)",
                monat_key, kategorie, bester_id)
            ergebnisse.append(f"{label}: **{row['titel']}** ({beste_stimmen} Stimme(n))")
        return ergebnisse

    async def _offene_auswertung(self) -> str | None:
        """Monats-Key (YYYY-MM) der letzten gestarteten, aber noch nicht
        ausgewerteten Award-Runde – oder None, falls keine offen ist."""
        gestartet_am_roh = await self.bot.db.get_setting("film_awards_gestartet_am")
        if not gestartet_am_roh:
            return None
        monat_key = f"{dt.datetime.fromisoformat(gestartet_am_roh):%Y-%m}"
        if await self.bot.db.get_setting(f"film_awards_ausgewertet_{monat_key}"):
            return None
        return monat_key

    @film_group.command(name="awards_start",
                        description="Startet die Abstimmung für alle Award-Kategorien des Monats.")
    async def film_awards_start(self, itx: discord.Interaction):
        heute = dt.datetime.now(config.TZ).date()
        ch = self.bot.channel_by_name("film-awards") or itx.channel
        erfolgreich = await self._start_awards_fuer_monat(heute, ch)
        if not erfolgreich:
            await itx.response.send_message("Diesen Monat wurde noch nichts geschaut.", ephemeral=True)
            return
        await itx.response.send_message(
            "Abstimmung für alle 4 Kategorien gestartet – siehe Kanal!", ephemeral=True)

    @film_group.command(name="awards_auswerten",
                        description="Zählt die Reaktionen aus und kürt die Monats-Gewinner.")
    async def film_awards_auswerten(self, itx: discord.Interaction):
        monat_key = await self._offene_auswertung()
        if not monat_key:
            await itx.response.send_message(
                "Keine laufende Abstimmung gefunden.", ephemeral=True)
            return
        ergebnisse = await self._auswerten_fuer_monat(monat_key)
        if not ergebnisse:
            await itx.response.send_message("Keine Stimmen gefunden.", ephemeral=True)
            return
        await self.bot.db.set_setting(f"film_awards_ausgewertet_{monat_key}", "1")
        monat_date = dt.datetime.strptime(monat_key, "%Y-%m").date()
        ch = self.bot.channel_by_name("film-awards") or itx.channel
        await ch.send(embed=emb("medien", f"🏆 Film-Awards {monat_date:%B %Y} – Ergebnisse",
                                "\n".join(ergebnisse)))
        await itx.response.send_message("Ausgewertet.", ephemeral=True)

    # Startet automatisch am 1. eines Monats die Abstimmung für den
    # vergangenen Monat, und wertet sie automatisch 3 Tage später aus,
    # falls das nicht schon manuell per /film awards_auswerten passiert ist.
    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, minute=0, tzinfo=config.TZ))
    async def film_awards_monatsende(self):
        heute = dt.datetime.now(config.TZ).date()
        ch = self.bot.channel_by_name("film-awards")
        if not ch:
            return
        if heute.day == 1:
            letzter_monat = heute.replace(day=1) - dt.timedelta(days=1)
            monat_key = f"{letzter_monat:%Y-%m}"
            if not await self.bot.db.get_setting(f"film_awards_filme_{monat_key}"):
                await self._start_awards_fuer_monat(letzter_monat, ch)
            return
        monat_key = await self._offene_auswertung()
        if not monat_key:
            return
        gestartet_am = dt.datetime.fromisoformat(
            await self.bot.db.get_setting("film_awards_gestartet_am"))
        if (dt.datetime.now(config.TZ) - gestartet_am).days < 3:
            return
        ergebnisse = await self._auswerten_fuer_monat(monat_key)
        if ergebnisse:
            await self.bot.db.set_setting(f"film_awards_ausgewertet_{monat_key}", "1")
            monat_date = dt.datetime.strptime(monat_key, "%Y-%m").date()
            await ch.send(embed=emb("medien", f"🏆 Film-Awards {monat_date:%B %Y} – Ergebnisse",
                                    "\n".join(ergebnisse)))

    @film_awards_monatsende.before_loop
    async def _before_film_awards_monatsende(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Filme(bot))
