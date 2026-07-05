"""
Zocken 🎮
- Spiele-Tinder: Bibliothek eintragen, blind swipen, Match-Reveal.
- Kartendealer: Deck mischen, verdeckte Karten per DM, offene im Kanal.
- Entscheidungsrad: /entscheide mit animiertem Rad (GIF via PIL).
- Valorant-Tracker (#valorant) – komplett automatisiert per /ranked valorant
  (HenrikDev API, da die offizielle Riot-API keinen individuellen Rang
  liefert – nur Leaderboards): Rang, RR, Elo, Peak, Season-Bilanz,
  Leaderboard-Platz, plus KDA/Headshot-%/Winrate/Lieblings-Agent aus den
  letzten 20 Competitive-Matches.
"""
import datetime as dt
import json
import random

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import henrikdev_client, steam_client, tracked
from utils.design import emb, render_entscheidungsrad

RAENGE = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
FARBEN = ["♠", "♥", "♦", "♣"]


def _neues_deck() -> list[str]:
    deck = [f"{r}{f}" for f in FARBEN for r in RAENGE]
    random.shuffle(deck)
    return deck


class SwipeView(discord.ui.View):
    """Eine ganze Swipe-Runde: geht Spiel für Spiel durch, bis alle noch
    unbewerteten Spiele einmal dran waren – erst danach gibt's die Matches."""
    def __init__(self, cog: "Zocken", spiele: list[dict]):
        super().__init__(timeout=600)
        self.cog = cog
        self.spiele = spiele
        self.index = 0

    def embed(self) -> discord.Embed:
        e = emb("spiele", "🎮 Spiele-Tinder", f"**{self.spiele[self.index]['name']}**")
        e.set_footer(text=f"{self.index + 1}/{len(self.spiele)}")
        return e

    @discord.ui.button(label="Like", style=discord.ButtonStyle.success, emoji="👍")
    async def like(self, itx: discord.Interaction, _button: discord.ui.Button):
        await self.cog.swipe_weiter(itx, self, 1)

    @discord.ui.button(label="Nope", style=discord.ButtonStyle.danger, emoji="👎")
    async def nope(self, itx: discord.Interaction, _button: discord.ui.Button):
        await self.cog.swipe_weiter(itx, self, 0)


class Zocken(commands.Cog):
    spiel_group = app_commands.Group(name="spiel", description="Spiele-Tinder.")
    karten_group = app_commands.Group(name="karten", description="Kartendealer.")
    ranked_group = app_commands.Group(name="ranked", description="Duo-Ranked-Tracker.")

    def __init__(self, bot):
        self.bot = bot
        self.valorant_daily_sync.start()

    def cog_unload(self):
        self.valorant_daily_sync.cancel()

    # ---------- Spiele-Tinder ----------
    @spiel_group.command(name="add",
                         description="Fügt ein Spiel zur Spiele-Tinder-Bibliothek hinzu (gilt automatisch für euch beide).")
    @app_commands.describe(name="Name des Spiels")
    async def spiel_add(self, itx: discord.Interaction, name: str):
        try:
            await self.bot.db.execute("INSERT INTO spiele (name) VALUES (?)", name)
        except Exception:
            await itx.response.send_message(f"„{name}“ steht schon in der Bibliothek.",
                                            ephemeral=True)
            return
        await itx.response.send_message(
            f"„{name}“ hinzugefügt – ab in die Swipe-Runde mit `/spiel swipe`!", ephemeral=True)

    @spiel_group.command(name="steam_import",
                         description="Importiert deine Steam-Bibliothek (nur gemeinsame Spiele landen in der Swipe-Runde).")
    async def spiel_steam_import(self, itx: discord.Interaction):
        steam_id_roh = config.STEAM_ID_MELI if itx.user.id == config.MELI_ID else config.STEAM_ID_JUSTI
        if not config.STEAM_API_KEY or not steam_id_roh:
            await itx.response.send_message(
                "⚠️ Steam ist noch nicht eingerichtet (STEAM_API_KEY + "
                "STEAM_ID_MELI/STEAM_ID_JUSTI in der .env nötig – Spieleliste im "
                "Steam-Profil muss außerdem auf „öffentlich“ stehen).", ephemeral=True)
            return
        await itx.response.defer(ephemeral=True)
        try:
            steamid = await steam_client.resolve_vanity(config.STEAM_API_KEY, steam_id_roh)
            if not steamid:
                await itx.followup.send("⚠️ Steam-Profil nicht gefunden.", ephemeral=True)
                return
            spiele = await steam_client.get_owned_games(config.STEAM_API_KEY, steamid)
        except aiohttp.ClientError:
            await itx.followup.send("⚠️ Steam-Import gerade fehlgeschlagen – später nochmal.",
                                    ephemeral=True)
            return
        if not spiele:
            await itx.followup.send(
                "Keine Spiele gefunden – steht die Spieleliste im Steam-Profil auf „öffentlich“?",
                ephemeral=True)
            return
        ist_meli = itx.user.id == config.MELI_ID
        meli_wert, justi_wert = (1, 0) if ist_meli else (0, 1)
        for s in spiele:
            await self.bot.db.execute(
                "INSERT INTO spiele (name, besitzer_meli, besitzer_justi) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "besitzer_meli = MAX(besitzer_meli, excluded.besitzer_meli), "
                "besitzer_justi = MAX(besitzer_justi, excluded.besitzer_justi)",
                s["name"], meli_wert, justi_wert)
        gemeinsam = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS n FROM spiele WHERE besitzer_meli = 1 AND besitzer_justi = 1")
        await itx.followup.send(
            f"{len(spiele)} Spiele aus deiner Steam-Bibliothek verarbeitet. Aktuell "
            f"**{gemeinsam['n']}** Spiele, die ihr beide habt – ab in die Swipe-Runde mit "
            "`/spiel swipe`!", ephemeral=True)

    @spiel_group.command(name="swipe",
                         description="Startet eine Swipe-Runde durch alle Spiele, die ihr beide habt.")
    async def spiel_swipe(self, itx: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT id, name FROM spiele WHERE besitzer_meli = 1 AND besitzer_justi = 1 "
            "ORDER BY RANDOM()")
        if not rows:
            await itx.response.send_message(
                "Noch keine gemeinsamen Spiele – `/spiel add` oder `/spiel steam_import` "
                "für Nachschub!", ephemeral=True)
            return
        view = SwipeView(self, [dict(r) for r in rows])
        await itx.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def swipe_weiter(self, itx: discord.Interaction, view: "SwipeView", wert: int):
        spiel = view.spiele[view.index]
        spalte = f"swipe_{config.slot_of(itx.user.id)}"
        await self.bot.db.execute(f"UPDATE spiele SET {spalte} = ? WHERE id = ?", wert, spiel["id"])
        row = await self.bot.db.fetchone("SELECT * FROM spiele WHERE id = ?", spiel["id"])
        ist_match = row["swipe_a"] == 1 and row["swipe_b"] == 1
        if ist_match and not row["match"]:
            await self.bot.db.execute("UPDATE spiele SET match = 1 WHERE id = ?", spiel["id"])
            ch = self.bot.channel_by_name("spiele-tinder")
            if ch:
                await ch.send(embed=emb("spiele", "🎉 ES IST EIN MATCH!",
                                        f"Ihr wollt beide **{row['name']}** spielen! Heute Abend?"))
            await self._sync_matches()
        elif not ist_match and row["match"]:
            await self.bot.db.execute("UPDATE spiele SET match = 0 WHERE id = ?", spiel["id"])
            await self._sync_matches()
        view.index += 1
        if view.index >= len(view.spiele):
            matches = await self.bot.db.fetchall("SELECT name FROM spiele WHERE match = 1 ORDER BY name")
            text = "\n".join(f"**{m['name']}**" for m in matches) if matches else "Noch keine Matches."
            await itx.response.edit_message(
                embed=emb("spiele", "🎮 Runde durch!",
                         f"Alle {len(view.spiele)} Spiele bewertet.\n\n**Eure Matches bisher:**\n{text}"),
                view=None)
            return
        await itx.response.edit_message(embed=view.embed(), view=view)

    async def _build_matches(self):
        rows = await self.bot.db.fetchall("SELECT * FROM spiele WHERE match = 1 ORDER BY name")
        if not rows:
            return emb("spiele", "🎮 Eure Matches", "Noch keine Matches – fleißig swipen!"), None
        zeilen = [f"**{r['name']}**" for r in rows]
        return emb("spiele", f"🎮 Eure Matches ({len(rows)})", "\n".join(zeilen)), None

    async def _sync_matches(self):
        ch = self.bot.channel_by_name("spiele-tinder")
        await tracked.sync(self.bot, "spiele_matches", "global", ch, self._build_matches)

    @spiel_group.command(name="matches", description="Zeigt alle Spiele-Matches.")
    async def spiele_matches_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, "spiele_matches", "global", itx.channel,
                                 self._build_matches)
        await itx.followup.send(
            f"Matches aktuell: {msg.jump_url}" if msg else "Noch keine Matches.", ephemeral=True)

    # ---------- Kartendealer ----------
    TISCH_KEY = "kartentisch"

    async def _deck_laden(self) -> list[str]:
        raw = await self.bot.db.get_setting("karten_deck")
        return json.loads(raw) if raw else []

    async def _deck_speichern(self, deck: list[str]):
        await self.bot.db.set_setting("karten_deck", json.dumps(deck))

    async def _hand_laden(self, user_id: int) -> list[str]:
        raw = await self.bot.db.get_setting(f"karten_hand_{user_id}")
        return json.loads(raw) if raw else []

    async def _hand_speichern(self, user_id: int, hand: list[str]):
        await self.bot.db.set_setting(f"karten_hand_{user_id}", json.dumps(hand))

    async def _offene_laden(self) -> list[str]:
        raw = await self.bot.db.get_setting("karten_offene")
        return json.loads(raw) if raw else []

    async def _offene_speichern(self, offene: list[str]):
        await self.bot.db.set_setting("karten_offene", json.dumps(offene))

    async def _ablage_laden(self) -> list[dict]:
        raw = await self.bot.db.get_setting("karten_ablage")
        return json.loads(raw) if raw else []

    async def _ablage_speichern(self, ablage: list[dict]):
        await self.bot.db.set_setting("karten_ablage", json.dumps(ablage))

    async def _hand_autocomplete(self, itx: discord.Interaction, current: str):
        hand = await self._hand_laden(itx.user.id)
        return [app_commands.Choice(name=karte, value=karte)
               for karte in hand if current.lower() in karte.lower()][:25]

    @karten_group.command(name="start", description="Mischt ein neues Deck und teilt Karten aus.")
    @app_commands.describe(spieler_karten="Karten pro Person (Standard 5)",
                           offene_karten="Offene Karten im Kanal (Standard 3)")
    async def karten_start(self, itx: discord.Interaction,
                           spieler_karten: app_commands.Range[int, 1, 20] = 5,
                           offene_karten: app_commands.Range[int, 0, 20] = 3):
        deck = _neues_deck()
        if spieler_karten * 2 + offene_karten > len(deck):
            await itx.response.send_message("⚠️ Zusammen zu viele Karten für ein Deck (52).",
                                            ephemeral=True)
            return
        for uid in (config.MELI_ID, config.JUSTI_ID):
            hand = [deck.pop() for _ in range(spieler_karten)]
            await self._hand_speichern(uid, hand)
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            try:
                await user.send(embed=emb("spiele", "🃏 Deine Karten", "  ".join(hand)))
            except discord.Forbidden:
                pass
        offene = [deck.pop() for _ in range(offene_karten)]
        await self._offene_speichern(offene)
        await self._ablage_speichern([])
        await self._deck_speichern(deck)
        await self._sync_tisch()
        await itx.response.send_message(
            "Karten ausgeteilt – schaut in eure DMs! Tisch siehe #kartentisch "
            "(`/karten legen` zum Ablegen, `/karten hand` falls die DM untergeht).",
            ephemeral=True)

    @karten_group.command(name="ziehen", description="Zieht die oberste Karte vom Stapel.")
    @app_commands.describe(privat="Auf die Hand (Standard) oder offen in den Kanal?")
    async def karten_ziehen(self, itx: discord.Interaction, privat: bool = True):
        deck = await self._deck_laden()
        if not deck:
            await itx.response.send_message(
                "Stapel ist leer – `/karten start` neu mischen.", ephemeral=True)
            return
        karte = deck.pop()
        await self._deck_speichern(deck)
        if privat:
            hand = await self._hand_laden(itx.user.id)
            hand.append(karte)
            await self._hand_speichern(itx.user.id, hand)
            try:
                await itx.user.send(embed=emb("spiele", "🃏 Gezogen", karte))
            except discord.Forbidden:
                pass
            await itx.response.send_message(
                f"Karte gezogen, jetzt auf deiner Hand ({len(deck)} übrig im Stapel).",
                ephemeral=True)
        else:
            ch = self.bot.channel_by_name("kartentisch") or itx.channel
            await ch.send(embed=emb("spiele", f"{config.name_of(itx.user.id)} deckt auf", karte))
            await itx.response.send_message("Aufgedeckt!", ephemeral=True)

    @karten_group.command(name="legen", description="Legt eine Karte aus deiner Hand offen auf den Tisch.")
    @app_commands.describe(karte="Welche Karte aus deiner Hand?")
    @app_commands.autocomplete(karte=_hand_autocomplete)
    async def karten_legen(self, itx: discord.Interaction, karte: str):
        hand = await self._hand_laden(itx.user.id)
        if karte not in hand:
            await itx.response.send_message("⚠️ Die hast du nicht (mehr) auf der Hand.",
                                            ephemeral=True)
            return
        hand.remove(karte)
        await self._hand_speichern(itx.user.id, hand)
        ablage = await self._ablage_laden()
        ablage.append({"karte": karte, "von": itx.user.id})
        await self._ablage_speichern(ablage)
        await self._sync_tisch()
        await itx.response.send_message(
            f"„{karte}“ liegt jetzt offen auf dem Tisch ({len(hand)} Karten noch auf der Hand).",
            ephemeral=True)

    @karten_group.command(name="hand", description="Zeigt dir nochmal deine aktuelle Hand.")
    async def karten_hand(self, itx: discord.Interaction):
        hand = await self._hand_laden(itx.user.id)
        if not hand:
            await itx.response.send_message("Du hast gerade keine Karten auf der Hand.",
                                            ephemeral=True)
            return
        await itx.response.send_message(embed=emb("spiele", "🃏 Deine Hand", "  ".join(hand)),
                                        ephemeral=True)

    async def _build_tisch(self):
        offene = await self._offene_laden()
        ablage = await self._ablage_laden()
        deck = await self._deck_laden()
        bloecke = []
        if offene:
            bloecke.append("**Offene Karten (Start)**\n" + "  ".join(offene))
        if ablage:
            zeilen = [f"{config.name_of(a['von'])}: {a['karte']}" for a in ablage]
            bloecke.append("**Gelegte Karten**\n" + "\n".join(zeilen))
        if not bloecke:
            bloecke.append("Noch nichts offen – `/karten start` legt los!")
        beschreibung = "\n\n".join(bloecke) + f"\n\n{len(deck)} Karten noch im Stapel."
        return emb("spiele", "🃏 Kartentisch", beschreibung), None

    async def _sync_tisch(self):
        ch = self.bot.channel_by_name("kartentisch")
        await tracked.sync(self.bot, self.TISCH_KEY, "global", ch, self._build_tisch)

    # ---------- Entscheidungsrad ----------
    @app_commands.command(name="entscheide", description="Dreht ein Entscheidungsrad für eure Optionen.")
    @app_commands.describe(optionen="Optionen, mit Komma getrennt (z.B. 'Pizza, Sushi, Pasta')")
    async def entscheide(self, itx: discord.Interaction, optionen: str):
        liste = [o.strip() for o in optionen.split(",") if o.strip()]
        if len(liste) < 2:
            await itx.response.send_message(
                "⚠️ Gib mindestens 2 Optionen an (mit Komma getrennt).", ephemeral=True)
            return
        liste = liste[:8]
        await itx.response.defer()
        gewinner_index = random.randrange(len(liste))
        datei = discord.File(render_entscheidungsrad(liste, gewinner_index), filename="rad.gif")
        e = emb("spiele", "🎡 Das Rad entscheidet...",
               f"Und der Gewinner ist: **{liste[gewinner_index]}**!")
        e.set_image(url="attachment://rad.gif")
        await itx.followup.send(embed=e, file=datei)

    # ---------- Duo-Ranked-Tracker: nur noch Valorant, komplett automatisiert ----------
    async def _build_ranked(self):
        zeilen = []
        for uid in (config.MELI_ID, config.JUSTI_ID):
            row = await self.bot.db.fetchone(
                "SELECT * FROM ranked_progress WHERE spieler = ? ORDER BY ts DESC LIMIT 1", uid)
            if not row:
                zeilen.append(f"**{config.name_of(uid)}**: noch kein Eintrag")
                continue
            verlauf = await self.bot.db.fetchall(
                "SELECT lp FROM ranked_progress WHERE spieler = ? ORDER BY ts DESC LIMIT 2", uid)
            trend = ""
            if len(verlauf) == 2:
                delta = verlauf[0]["lp"] - verlauf[1]["lp"]
                if delta != 0:
                    trend = f" ({'+' if delta > 0 else ''}{delta} RR)"
            zeilen.append(f"**{config.name_of(uid)}**: {row['rang']} · {row['lp']} RR{trend}")
        return emb("spiele", "🎯 Valorant", "\n".join(zeilen)), None

    async def _sync_ranked(self):
        ch = self.bot.channel_by_name("valorant")
        await tracked.sync(self.bot, "ranked_status", "global", ch, self._build_ranked)

    # ---------- Valorant: alle verfügbaren Stats live über HenrikDev ----------
    def _valorant_stats_feld(self, stats: dict, form: dict | None) -> str:
        zeilen = [f"**{stats['rang']}** · {stats['rr']} RR"]
        if stats["elo"] is not None:
            zeilen[0] += f" (Elo {stats['elo']})"
        if stats["delta"]:
            vorzeichen = "+" if stats["delta"] > 0 else ""
            zeilen.append(f"Letztes Match: {vorzeichen}{stats['delta']} RR")
        zeilen.append(f"Peak-Rang: {stats['peak_rang']}")
        if stats["season_spiele"]:
            zeilen.append(f"Diese Season: {stats['season_siege']}S / "
                          f"{stats['season_niederlagen']}N ({stats['season_spiele']} Spiele, "
                          f"{stats['season_winrate']}% Winrate)")
        if stats["leaderboard_platz"]:
            zeilen.append(f"Leaderboard-Platz: #{stats['leaderboard_platz']}")
        if form:
            zeilen.append(f"Letzte {form['anzahl']} Comp-Matches: {form['avg_kda']} KDA "
                          f"({form['kd']} K/D), {form['hs_prozent']}% HS, "
                          f"{form['winrate']}% Winrate")
            zeilen.append(f"Meistgespielt: {form['top_agent']}")
        return "\n".join(zeilen)

    @ranked_group.command(name="valorant",
                          description="Holt alle verfügbaren Valorant-Stats live ab (HenrikDev API).")
    async def valorant_rang(self, itx: discord.Interaction):
        if not config.HENRIKDEV_API_KEY:
            await itx.response.send_message(
                "HENRIKDEV_API_KEY fehlt noch in der .env – Key aus dem HenrikDev-Discord holen.",
                ephemeral=True)
            return
        await itx.response.defer(ephemeral=False)
        e = emb("spiele", "🎯 Valorant-Stats")
        for uid, riot_id in ((config.MELI_ID, config.RIOT_ID_MELI),
                             (config.JUSTI_ID, config.RIOT_ID_JUSTI)):
            if not riot_id or "#" not in riot_id:
                e.add_field(name=config.name_of(uid), value="keine Riot-ID hinterlegt", inline=True)
                continue
            name, tag = riot_id.split("#", 1)
            try:
                daten = await henrikdev_client.get_mmr(config.RIOT_REGION, name, tag)
            except henrikdev_client.HenrikDevError as fehler:
                e.add_field(name=config.name_of(uid), value=f"Abfrage fehlgeschlagen ({fehler})",
                           inline=True)
                continue
            stats = henrikdev_client.voller_stats(daten)
            try:
                matches = await henrikdev_client.get_recent_matches(config.RIOT_REGION, name, tag)
                form = henrikdev_client.match_stats(matches)
            except henrikdev_client.HenrikDevError:
                form = None
            await self.bot.db.execute(
                "INSERT INTO ranked_progress (spieler, spiel, rang, lp) VALUES (?, 'Valorant', ?, ?)",
                uid, stats["rang"], stats["rr"])
            e.add_field(name=config.name_of(uid), value=self._valorant_stats_feld(stats, form),
                       inline=True)
        await self._sync_ranked()
        await itx.followup.send(embed=e)

    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, minute=30, tzinfo=config.TZ))
    async def valorant_daily_sync(self):
        if not config.HENRIKDEV_API_KEY:
            return
        aktualisiert = False
        for uid, riot_id in ((config.MELI_ID, config.RIOT_ID_MELI),
                             (config.JUSTI_ID, config.RIOT_ID_JUSTI)):
            if not riot_id or "#" not in riot_id:
                continue
            name, tag = riot_id.split("#", 1)
            try:
                daten = await henrikdev_client.get_mmr(config.RIOT_REGION, name, tag)
            except henrikdev_client.HenrikDevError:
                continue
            stats = henrikdev_client.voller_stats(daten)
            await self.bot.db.execute(
                "INSERT INTO ranked_progress (spieler, spiel, rang, lp) VALUES (?, 'Valorant', ?, ?)",
                uid, stats["rang"], stats["rr"])
            aktualisiert = True
        if aktualisiert:
            await self._sync_ranked()

    @valorant_daily_sync.before_loop
    async def _before_valorant_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Zocken(bot))
