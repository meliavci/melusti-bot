"""
Melusti – euer gemeinsames Tamagotchi. 🌱
Kernregeln:
  • Melusti hängt von EUCH BEIDEN ab – einer allein reicht nicht für "strahlend".
  • Melusti stirbt NIE. Bei Vernachlässigung schläft es nur ein.
  • Streit klären HEILT Melusti – Klärung ist etwas Gutes, kein Schadensfall.
"""
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.design import emb, progress_bar, render_melusti

# (XP-Schwelle, Mindestanzahl echter Meilensteine, Key, Label) – Evolution
# braucht beides: genug XP UND genug eingetragene echte Meilensteine.
STAGES = [
    (0,    0, "ei",     "🥚 Ei"),
    (100,  0, "baby",   "🐣 Baby"),
    (400,  1, "kind",   "🌿 Kind"),
    (1200, 3, "teen",   "🌳 Teen"),
    (3000, 5, "legend", "✨ Legende"),
]

XP_ACTIONS = {
    "checkin": 10,
    "lebenszeichen": 5,
    "zitat": 5,
    "wort": 5,
    "zeitkapsel": 15,
    "kompliment": 8,
    "streit_geklaert": 40,   # Heilung!
    "trick": 10,
    "witz": 5,
}

MOOD_BAROMETER_BONUS = {
    "strahlend": 10, "zufrieden": 5, "quengelig": -5, "krank": -20, "schlafend": -10,
}


def stage_for(xp: int, meilensteine: int):
    current = STAGES[0]
    nxt = None
    for threshold, min_meilensteine, key, label in STAGES:
        if xp >= threshold and meilensteine >= min_meilensteine:
            current = (threshold, min_meilensteine, key, label)
        elif nxt is None:
            nxt = (threshold, min_meilensteine, key, label)
    return current, nxt


class Melusti(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- Stimmungs-Logik: beide zählen ----------
    async def mood(self) -> tuple[str, str]:
        now = datetime.now(config.TZ)
        moods = []
        for uid in (config.MELI_ID, config.JUSTI_ID):
            row = await self.bot.db.fetchone(
                "SELECT MAX(ts) AS letzte FROM moli_feed_log WHERE user_id = ?", uid)
            if row is None or row["letzte"] is None:
                moods.append(999)
                continue
            last = datetime.fromisoformat(row["letzte"]).replace(tzinfo=None)
            hours = (now.replace(tzinfo=None) - last).total_seconds() / 3600
            moods.append(hours)

        a, b = moods
        if max(a, b) >= 48:
            return "schlafend", "Melusti ist eingeschlafen... 💤 (Keine Sorge – ein Check-in weckt es sofort wieder auf.)"

        offener_streit = await self.bot.db.fetchone(
            "SELECT * FROM streits WHERE status = 'offen' ORDER BY gestartet LIMIT 1")
        if offener_streit:
            return "krank", ("Melusti fühlt sich nicht gut – da hängt noch etwas Ungeklärtes "
                             "in der Luft. 🤒 (`/streit loesung` hilft euch beiden.)")

        if max(a, b) >= 24:
            hungrig = config.MELI_NAME if a > b else config.JUSTI_NAME
            satt = config.JUSTI_NAME if a > b else config.MELI_NAME
            return "quengelig", f"{satt} hat mich gefüttert, aber {hungrig}... 👀"
        if max(a, b) >= 12:
            return "zufrieden", "Melusti ist zufrieden und knabbert an einem Blatt. 🌿"
        return "strahlend", "Melusti strahlt! Ihr habt euch heute beide gekümmert. 💚"

    # ---------- gemeinsamer Stand für Evolutions-Check ----------
    async def _aktueller_stand(self) -> tuple[int, int]:
        row = await self.bot.db.fetchone("SELECT xp FROM moli WHERE id = 1")
        m = await self.bot.db.fetchone("SELECT COUNT(*) AS n FROM meilensteine")
        return row["xp"], m["n"]

    async def pruefe_evolution(self, old_xp: int, old_meilensteine: int):
        """Vergleicht Stand vor/nach einer Änderung (XP ODER neuer Meilenstein)
        und postet eine Entwicklungs-Ankündigung, falls sich die Stufe ändert."""
        neu_xp, neu_meilensteine = await self._aktueller_stand()
        (_, _, old_key, _), _ = stage_for(old_xp, old_meilensteine)
        (_, _, new_key, new_label), _ = stage_for(neu_xp, neu_meilensteine)
        if new_key == old_key:
            return
        ch = self.bot.channel_by_name("melusti")
        if ch:
            mood_key, _ = await self.mood()
            file = discord.File(render_melusti(new_key, mood_key), filename="melusti.png")
            e = emb("melusti", f"🎉 MELUSTI HAT SICH ENTWICKELT: {new_label}!",
                    "Euer gemeinsames Kümmern zahlt sich aus. "
                    "Schaut euch die neue Form mit `/melusti` an!")
            e.set_image(url="attachment://melusti.png")
            await ch.send(embed=e, file=file)

    # ---------- zentrale Fütter-Funktion ----------
    async def feed(self, user_id: int, action: str, xp: int | None = None):
        xp = xp if xp is not None else XP_ACTIONS.get(action, 5)
        old_xp, old_meilensteine = await self._aktueller_stand()
        await self.bot.db.execute("UPDATE moli SET xp = xp + ? WHERE id = 1", xp)
        await self.bot.db.execute(
            "INSERT INTO moli_feed_log (user_id, action, xp) VALUES (?, ?, ?)",
            user_id, action, xp)
        await self.pruefe_evolution(old_xp, old_meilensteine)

    # ---------- Beziehungsbarometer ----------
    async def _barometer_wert(self) -> tuple[int, list[str]]:
        score = 50
        gruende = []
        vor_14_tagen = (datetime.now(config.TZ).date() - timedelta(days=14)).isoformat()

        checkins = await self.bot.db.fetchall(
            "SELECT farbe FROM checkins WHERE datum >= ?", vor_14_tagen)
        punkte = {"gruen": 3, "gelb": 0, "rot": -3}
        if checkins:
            summe = sum(punkte.get(c["farbe"], 0) for c in checkins)
            score += summe
            gruende.append(f"{len(checkins)} Check-ins (letzte 14 Tage): {summe:+d}")

        offene = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS n FROM streits WHERE status = 'offen'")
        if offene["n"]:
            abzug = 15 * offene["n"]
            score -= abzug
            wort = "Klärung" if offene["n"] == 1 else "Klärungen"
            gruende.append(f"{offene['n']} offene {wort}: -{abzug}")

        geklaert = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS n FROM streits WHERE status = 'geklaert' AND geklaert_am >= ?",
            vor_14_tagen)
        if geklaert["n"]:
            bonus = min(20, geklaert["n"] * 5)
            score += bonus
            gruende.append(f"{geklaert['n']} geklärte Konflikte (14 Tage): +{bonus}")

        mood_key, _ = await self.mood()
        mood_bonus = MOOD_BAROMETER_BONUS.get(mood_key, 0)
        score += mood_bonus
        gruende.append(f"Melusti-Zustand ({mood_key}): {mood_bonus:+d}")

        return max(0, min(100, score)), gruende

    @app_commands.command(name="beziehungsbarometer",
                          description="Zeigt, wie's um eure Beziehung gerade steht.")
    async def beziehungsbarometer(self, itx: discord.Interaction):
        await itx.response.defer()
        wert, gruende = await self._barometer_wert()
        if wert >= 80:
            label = "Harmonisch 💚"
        elif wert >= 55:
            label = "Stabil 🙂"
        elif wert >= 35:
            label = "Angespannt 😕"
        else:
            label = "Redebedarf 🔴"
        e = emb("liebe", f"💞 Beziehungsbarometer – {label}",
               f"{progress_bar(wert, 100)}  `{wert}/100`")
        e.add_field(name="Woraus sich das errechnet",
                   value="\n".join(f"• {g}" for g in gruende), inline=False)
        await itx.followup.send(embed=e)

    # ---------- Commands ----------
    @app_commands.command(name="melusti", description="Zeigt Melusti und seinen Zustand.")
    async def show(self, itx: discord.Interaction):
        await itx.response.defer()
        row = await self.bot.db.fetchone("SELECT xp, name FROM moli WHERE id = 1")
        xp = row["xp"]
        _, meilensteine = await self._aktueller_stand()
        (thr, min_m, key, label), nxt = stage_for(xp, meilensteine)
        mood_key, mood_text = await self.mood()

        file = discord.File(render_melusti(key, mood_key), filename="melusti.png")
        e = emb("melusti", f"{row['name']} – {label}", mood_text)
        if nxt:
            n_thr, n_min_m, _, n_label = nxt
            zeilen = [f"{progress_bar(min(xp, n_thr) - thr, n_thr - thr)}  "
                     f"`{min(xp, n_thr)}/{n_thr} XP`"]
            if n_min_m > 0:
                haken = "✅" if meilensteine >= n_min_m else "⬜"
                wort = "Meilenstein" if n_min_m == 1 else "Meilensteine"
                zeilen.append(f"{haken} mindestens {n_min_m} {wort} eingetragen "
                             f"({meilensteine}/{n_min_m})")
            e.add_field(name=f"Entwicklung zu {n_label}", value="\n".join(zeilen), inline=False)
        else:
            e.add_field(name="Maximale Stufe erreicht", value=f"`{xp} XP` ✨", inline=False)

        # Wer hat heute schon gefüttert?
        today = datetime.now(config.TZ).strftime("%Y-%m-%d")
        status = []
        for uid in (config.MELI_ID, config.JUSTI_ID):
            fed = await self.bot.db.fetchone(
                "SELECT 1 FROM moli_feed_log WHERE user_id = ? AND date(ts) = ? LIMIT 1",
                uid, today)
            status.append(f"{'✅' if fed else '⬜'} {config.name_of(uid)}")
        e.add_field(name="Heute gefüttert", value="\n".join(status), inline=False)
        e.set_image(url="attachment://melusti.png")
        await itx.followup.send(embed=e, file=file)

    @app_commands.command(name="melusti_taufen", description="Gebt eurem Wesen einen Namen.")
    @app_commands.describe(name="Der neue Name")
    async def rename(self, itx: discord.Interaction, name: str):
        await self.bot.db.execute("UPDATE moli SET name = ? WHERE id = 1", name[:32])
        await itx.response.send_message(
            embed=emb("melusti", "🍼 Getauft!", f"Euer Wesen heißt jetzt **{name[:32]}**."))


async def setup(bot):
    await bot.add_cog(Melusti(bot))
