"""
Call-Stats 📞 – trackt automatisch:
- gemeinsame Call-Zeit (beide im selben Voice-Channel)
- Einzelzeit pro Person (Meli/Justi jeweils insgesamt im Call)
- Bildschirmfreigabe-Dauer pro Person
- wie lange Melusti (der Bot) selbst im Call war (z.B. während /musik play)
Wöchentlicher Report (sonntags) in #stats, zusätzlich jederzeit per /call_stats.
"""
import datetime as dt

import discord
from discord.ext import commands, tasks
from discord import app_commands

import config
from utils import tracked
from utils.design import emb

CALL_STATS_KEY = "call_stats"


def _fmt(minuten: int) -> str:
    stunden, rest = divmod(minuten, 60)
    return f"{stunden}h {rest}min" if stunden else f"{rest}min"


class Calls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.call_recap.start()

    def cog_unload(self):
        self.call_recap.cancel()

    async def _session_beenden(self, tabelle: str, row):
        start = dt.datetime.fromisoformat(row["start"])
        ende = dt.datetime.now(config.TZ)
        minuten = max(1, round((ende - start).total_seconds() / 60))
        await self.bot.db.execute(
            f"UPDATE {tabelle} SET ende = ?, minuten = ? WHERE id = ?",
            ende.isoformat(), minuten, row["id"])

    async def _gemeinsam_start_stop(self, kanal):
        ids_im_call = {m.id for m in kanal.members if not m.bot} if kanal else set()
        beide_zusammen = {config.MELI_ID, config.JUSTI_ID} <= ids_im_call
        laufender = await self.bot.db.fetchone("SELECT * FROM calls WHERE ende IS NULL")
        if beide_zusammen and not laufender:
            await self.bot.db.execute(
                "INSERT INTO calls (start) VALUES (?)", dt.datetime.now(config.TZ).isoformat())
        elif not beide_zusammen and laufender:
            await self._session_beenden("calls", laufender)

    async def _einzeln_start_stop(self, user_id: int, im_call: bool):
        laufender = await self.bot.db.fetchone(
            "SELECT * FROM voice_sessions WHERE typ = 'einzeln' AND user_id = ? AND ende IS NULL",
            user_id)
        if im_call and not laufender:
            await self.bot.db.execute(
                "INSERT INTO voice_sessions (typ, user_id, start) VALUES ('einzeln', ?, ?)",
                user_id, dt.datetime.now(config.TZ).isoformat())
        elif not im_call and laufender:
            await self._session_beenden("voice_sessions", laufender)

    async def _screenshare_start_stop(self, user_id: int, teilt: bool):
        laufender = await self.bot.db.fetchone(
            "SELECT * FROM voice_sessions WHERE typ = 'screenshare' AND user_id = ? AND ende IS NULL",
            user_id)
        if teilt and not laufender:
            await self.bot.db.execute(
                "INSERT INTO voice_sessions (typ, user_id, start) VALUES ('screenshare', ?, ?)",
                user_id, dt.datetime.now(config.TZ).isoformat())
        elif not teilt and laufender:
            await self._session_beenden("voice_sessions", laufender)

    async def _bot_start_stop(self, im_call: bool):
        laufender = await self.bot.db.fetchone(
            "SELECT * FROM voice_sessions WHERE typ = 'bot' AND ende IS NULL")
        if im_call and not laufender:
            await self.bot.db.execute(
                "INSERT INTO voice_sessions (typ, user_id, start) VALUES ('bot', NULL, ?)",
                dt.datetime.now(config.TZ).isoformat())
        elif not im_call and laufender:
            await self._session_beenden("voice_sessions", laufender)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id:
            await self._bot_start_stop(after.channel is not None)
            return
        if not config.is_couple(member.id):
            return
        kanal = after.channel or before.channel
        await self._gemeinsam_start_stop(kanal)
        await self._einzeln_start_stop(member.id, after.channel is not None)
        await self._screenshare_start_stop(member.id, bool(after.channel and after.self_stream))

    async def _laufend_plus_abgeschlossen(self, typ: str, user_id: int | None,
                                          wochenstart: str, jetzt: dt.datetime) -> int:
        """Minuten aus abgeschlossenen Sessions dieser Woche PLUS die gerade
        laufende Session (falls es eine gibt) – sonst zeigt /call_stats
        während eines laufenden Calls fälschlich 0 an."""
        abgeschlossen = await self.bot.db.fetchall(
            "SELECT minuten FROM voice_sessions WHERE typ = ? AND user_id IS ? "
            "AND start >= ? AND minuten IS NOT NULL", typ, user_id, wochenstart)
        summe = sum(r["minuten"] for r in abgeschlossen)
        laufend = await self.bot.db.fetchone(
            "SELECT start FROM voice_sessions WHERE typ = ? AND user_id IS ? AND ende IS NULL",
            typ, user_id)
        if laufend and laufend["start"] >= wochenstart:
            start = dt.datetime.fromisoformat(laufend["start"])
            summe += max(0, round((jetzt - start).total_seconds() / 60))
        return summe

    async def _build_stats(self):
        heute = dt.datetime.now(config.TZ).date()
        wochenstart = (heute - dt.timedelta(days=heute.weekday())).isoformat()
        jetzt = dt.datetime.now(config.TZ)

        gemeinsam = await self.bot.db.fetchall(
            "SELECT * FROM calls WHERE start >= ? AND minuten IS NOT NULL", wochenstart)
        gemeinsam_min = sum(r["minuten"] for r in gemeinsam)
        gemeinsam_anzahl = len(gemeinsam)
        laufender_gemeinsam = await self.bot.db.fetchone("SELECT * FROM calls WHERE ende IS NULL")
        if laufender_gemeinsam and laufender_gemeinsam["start"] >= wochenstart:
            start = dt.datetime.fromisoformat(laufender_gemeinsam["start"])
            gemeinsam_min += max(0, round((jetzt - start).total_seconds() / 60))
            gemeinsam_anzahl += 1
        zeilen = [f"**Gemeinsam im Call**: {gemeinsam_anzahl}× · {_fmt(gemeinsam_min)}"]

        for uid in (config.MELI_ID, config.JUSTI_ID):
            einzeln_min = await self._laufend_plus_abgeschlossen(
                "einzeln", uid, wochenstart, jetzt)
            teilen_min = await self._laufend_plus_abgeschlossen(
                "screenshare", uid, wochenstart, jetzt)
            zeile = f"**{config.name_of(uid)}**: {_fmt(einzeln_min)} im Call insgesamt"
            if teilen_min:
                zeile += f", davon {_fmt(teilen_min)} Bildschirm geteilt"
            zeilen.append(zeile)

        bot_min = await self._laufend_plus_abgeschlossen("bot", None, wochenstart, jetzt)
        if bot_min:
            zeilen.append(f"**Melusti** war {_fmt(bot_min)} dabei (Musik-Wiedergabe)")

        titel = f"📊 Call-Stats – Woche ab {dt.date.fromisoformat(wochenstart):%d.%m.%Y}"
        return emb("info", titel, "\n".join(zeilen)), None

    @app_commands.command(name="call_stats", description="Zeigt eure Call-Zeit diese Woche.")
    async def call_stats(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, CALL_STATS_KEY, "global", itx.channel, self._build_stats)
        await itx.followup.send(f"Call-Stats aktuell: {msg.jump_url}" if msg else "Noch keine Calls.",
                                ephemeral=True)

    # Einmal pro Woche (sonntags) – aktualisiert die EINE lebende
    # Call-Stats-Nachricht in #stats, statt eine neue zu posten (Spam).
    @tasks.loop(time=dt.time(hour=config.MORNING_HOUR, tzinfo=config.TZ))
    async def call_recap(self):
        if dt.datetime.now(config.TZ).date().weekday() != 6:  # nur sonntags
            return
        ch = self.bot.channel_by_name("stats")
        if not ch:
            return
        await tracked.sync(self.bot, CALL_STATS_KEY, "global", ch, self._build_stats)

    @call_recap.before_loop
    async def _before_call_recap(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Calls(bot))
