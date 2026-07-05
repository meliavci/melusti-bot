"""Wörterbuch 📖 – euer offizielles Lexikon (guti, supi, bezz, Wadde, ...)."""
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import tracked
from utils.design import emb

LEXIKON_KEY = "lexikon"


class Woerterbuch(commands.Cog):
    wort_group = app_commands.Group(name="wort", description="Euer gemeinsames Lexikon.")

    def __init__(self, bot):
        self.bot = bot

    # ---------- Autocomplete (Auswahl per Wort statt Tippfehler-Risiko) ----------
    async def _wort_autocomplete(self, itx: discord.Interaction, current: str):
        rows = await self.bot.db.fetchall("SELECT wort FROM woerterbuch ORDER BY wort")
        return [app_commands.Choice(name=r["wort"], value=r["wort"])
                for r in rows if current.lower() in r["wort"].lower()][:25]

    @wort_group.command(name="add", description="Neues Wort ins Lexikon eintragen.")
    @app_commands.describe(wort="Das Wort", definition="Was heißt es?",
                           herkunft="Woher kommt's? (optional)",
                           datum="Wann entstanden? Format TT.MM.JJJJ (optional, Standard: heute)")
    async def add(self, itx: discord.Interaction, wort: str, definition: str,
                  herkunft: str | None = None, datum: str | None = None):
        ts_value = None
        if datum:
            try:
                ts_value = dt.datetime.strptime(datum, "%d.%m.%Y").date().isoformat()
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        try:
            if ts_value:
                await self.bot.db.execute(
                    "INSERT INTO woerterbuch (wort, definition, herkunft, added_by, ts) "
                    "VALUES (?,?,?,?,?)", wort, definition, herkunft, itx.user.id, ts_value)
            else:
                await self.bot.db.execute(
                    "INSERT INTO woerterbuch (wort, definition, herkunft, added_by) "
                    "VALUES (?,?,?,?)", wort, definition, herkunft, itx.user.id)
        except Exception:
            await itx.response.send_message(f"„{wort}“ steht schon drin! "
                                            "(Ändern geht mit `/wort edit`)", ephemeral=True)
            return
        await self.bot.feed_melusti(itx.user.id, "wort", None)
        await self._sync_lexikon()
        await itx.response.send_message(f"„{wort}“ ist jetzt im Lexikon.", ephemeral=True)

    @wort_group.command(name="edit", description="Ändert einen bestehenden Lexikon-Eintrag.")
    @app_commands.describe(wort="Welches Wort?", definition="Neue Definition (optional)",
                           herkunft="Neue Herkunft (optional)",
                           datum="Neues Datum TT.MM.JJJJ (optional)")
    @app_commands.autocomplete(wort=_wort_autocomplete)
    async def edit(self, itx: discord.Interaction, wort: str, definition: str | None = None,
                   herkunft: str | None = None, datum: str | None = None):
        row = await self.bot.db.fetchone(
            "SELECT * FROM woerterbuch WHERE wort = ? COLLATE NOCASE", wort)
        if not row:
            await itx.response.send_message(f"„{wort}“ steht (noch) nicht im Lexikon.",
                                            ephemeral=True)
            return
        if definition is None and herkunft is None and datum is None:
            await itx.response.send_message("⚠️ Gib mindestens ein Feld zum Ändern an "
                                            "(definition/herkunft/datum).", ephemeral=True)
            return
        new_ts = row["ts"]
        if datum:
            try:
                new_ts = dt.datetime.strptime(datum, "%d.%m.%Y").date().isoformat()
            except ValueError:
                await itx.response.send_message("⚠️ Datum bitte als `TT.MM.JJJJ`.",
                                                ephemeral=True)
                return
        await self.bot.db.execute(
            "UPDATE woerterbuch SET definition = ?, herkunft = ?, ts = ? WHERE id = ?",
            definition if definition is not None else row["definition"],
            herkunft if herkunft is not None else row["herkunft"],
            new_ts, row["id"])
        await self._sync_lexikon()
        await itx.response.send_message(f"„{row['wort']}“ aktualisiert.", ephemeral=True)

    @wort_group.command(name="delete", description="Löscht einen Lexikon-Eintrag.")
    @app_commands.describe(wort="Welches Wort?")
    @app_commands.autocomplete(wort=_wort_autocomplete)
    async def delete(self, itx: discord.Interaction, wort: str):
        row = await self.bot.db.fetchone(
            "SELECT * FROM woerterbuch WHERE wort = ? COLLATE NOCASE", wort)
        if not row:
            await itx.response.send_message(f"„{wort}“ steht (noch) nicht im Lexikon.",
                                            ephemeral=True)
            return
        await self.bot.db.execute("DELETE FROM woerterbuch WHERE id = ?", row["id"])
        await self._sync_lexikon()
        await itx.response.send_message(f"„{row['wort']}“ gelöscht.", ephemeral=True)

    @wort_group.command(name="schlagnach", description="Schlägt ein Wort nach.")
    @app_commands.autocomplete(wort=_wort_autocomplete)
    async def lookup(self, itx: discord.Interaction, wort: str):
        row = await self.bot.db.fetchone(
            "SELECT * FROM woerterbuch WHERE wort LIKE ?", wort)
        if not row:
            await itx.response.send_message(f"„{wort}“ steht (noch) nicht im Lexikon.",
                                            ephemeral=True)
            return
        await itx.response.send_message(embed=self._eintrag(row))

    @wort_group.command(name="liste", description="Zeigt das ganze Wörterbuch.")
    async def alle(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        msg = await tracked.sync(self.bot, LEXIKON_KEY, "global", itx.channel, self._build_lexikon)
        await itx.followup.send(f"Lexikon aktuell: {msg.jump_url}" if msg else
                                "Lexikon ist noch leer.", ephemeral=True)

    def _eintrag(self, row, titel=None):
        datum_str = dt.date.fromisoformat(row["ts"][:10]).strftime("%d.%m.%Y")
        wer = config.name_of(row["added_by"]) if row["added_by"] else "?"
        e = emb("medien", titel or f"📖 {row['wort']}",
               f"## {row['wort']}\n*{row['definition']}*",
               footer=f"hinzugefügt {datum_str} von {wer}")
        if row["herkunft"]:
            e.add_field(name="Etymologie", value=row["herkunft"])
        return e

    async def _build_lexikon(self):
        rows = await self.bot.db.fetchall("SELECT * FROM woerterbuch ORDER BY wort")
        if not rows:
            return emb("medien", "📖 Das Meli-Justi-Lexikon",
                       "Noch leer – `/wort add` legt los!"), None
        bloecke = []
        for r in rows:
            datum_str = dt.date.fromisoformat(r["ts"][:10]).strftime("%d.%m.%Y")
            wer = config.name_of(r["added_by"]) if r["added_by"] else "?"
            block = f"**{r['wort']}**\n{r['definition']}"
            if r["herkunft"]:
                block += f"\n*↳ {r['herkunft']}*"
            block += f"\n-# hinzugefügt {datum_str} von {wer}"
            bloecke.append(block)
        beschreibung = "\n\n".join(bloecke)[:4000]
        return emb("medien", f"📖 Das Meli-Justi-Lexikon ({len(rows)} Einträge)", beschreibung), None

    async def _sync_lexikon(self):
        """Hält eine einzige Lexikon-Übersicht im #wörterbuch-Channel aktuell,
        statt bei jedem Wort eine neue Nachricht zu spammen."""
        ch = self.bot.channel_by_name("wörterbuch")
        await tracked.sync(self.bot, LEXIKON_KEY, "global", ch, self._build_lexikon)

async def setup(bot):
    await bot.add_cog(Woerterbuch(bot))
