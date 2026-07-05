"""
Gemeinsame Infrastruktur für "lebende" Nachrichten.

Konvention für den ganzen Bot: Statt bei jedem Hinzufügen/Ändern/Löschen
eine neue Nachricht zu posten, merkt sich der Bot Channel+Message-ID der
zuletzt verschickten Übersicht (in der settings-Tabelle, als JSON unter
einem eindeutigen `key`) und editiert sie. Jedes Cog mit einer Liste/Ansicht
(Kalender, Lexikon, Zitate, künftige Features wie Countdown/Watchlists)
nutzt dafür `sync()` bzw. `refresh_all()` statt eigener Tracking-Logik.
"""
import json
from typing import Awaitable, Callable

import discord

BuildResult = tuple[discord.Embed | list[discord.Embed], discord.File | None] | None


async def _load(bot, key: str) -> dict:
    raw = await bot.db.get_setting(key)
    return json.loads(raw) if raw else {}


async def _save(bot, key: str, data: dict):
    await bot.db.set_setting(key, json.dumps(data))


async def untrack(bot, key: str, sub_key: str):
    data = await _load(bot, key)
    if sub_key in data:
        del data[sub_key]
        await _save(bot, key, data)


async def _edit_or_none(ch, ref: dict, embed: discord.Embed | list[discord.Embed],
                        file: discord.File | None) -> bool:
    try:
        msg = await ch.fetch_message(ref["message_id"])
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False
    try:
        if isinstance(embed, list):
            await msg.edit(embeds=embed)
        elif file:
            await msg.edit(embed=embed, attachments=[file])
        else:
            await msg.edit(embed=embed)
    except discord.HTTPException:
        return False
    return True


async def sync(bot, key: str, sub_key: str, channel: discord.abc.Messageable | None,
               build: Callable[[], Awaitable[BuildResult]]) -> discord.Message | None:
    """
    Hält GENAU EINE Nachricht pro (key, sub_key) aktuell: existiert schon eine
    getrackte Nachricht, wird sie editiert – sonst wird eine neue in `channel`
    gesendet und ab da getrackt. `build()` liefert (embed, file_oder_None).
    Gibt die Nachricht zurück (z.B. für ein Ephemeral-Feedback ans UI), oder
    None, wenn weder editiert noch neu gesendet werden konnte.
    """
    data = await _load(bot, key)
    ref = data.get(sub_key)
    if ref:
        ch = bot.get_channel(ref["channel_id"])
        if ch:
            embed, file = await build()
            if await _edit_or_none(ch, ref, embed, file):
                return await ch.fetch_message(ref["message_id"])
    if channel is None:
        return None
    embed, file = await build()
    if isinstance(embed, list):
        msg = await channel.send(embeds=embed)
    else:
        msg = await channel.send(embed=embed, file=file) if file else await channel.send(embed=embed)
    data[sub_key] = {"channel_id": channel.id, "message_id": msg.id}
    await _save(bot, key, data)
    return msg


async def delete_tracked(bot, key: str, sub_key: str):
    """Löscht die getrackte Nachricht (z.B. wenn der zugehörige Eintrag
    komplett gelöscht wurde) und entfernt das Tracking."""
    data = await _load(bot, key)
    ref = data.get(sub_key)
    if not ref:
        return
    ch = bot.get_channel(ref["channel_id"])
    if ch:
        try:
            msg = await ch.fetch_message(ref["message_id"])
            await msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    del data[sub_key]
    await _save(bot, key, data)


async def refresh_all(bot, key: str,
                      build_for: Callable[[str], Awaitable[BuildResult]]):
    """
    Aktualisiert ALLE getrackten Nachrichten unter `key` (z.B. beim täglichen
    Refresh oder nach einer Änderung, die mehrere Ansichten betrifft – etwa
    ein Meilenstein, der in mehreren Kalendermonaten auftaucht).
    `build_for(sub_key)` liefert (embed, file_oder_None); liefert es None,
    wird die Nachricht nicht mehr getrackt (z.B. weil sie nicht mehr existiert).
    """
    data = await _load(bot, key)
    changed = False
    for sub_key, ref in list(data.items()):
        ch = bot.get_channel(ref["channel_id"])
        if ch is None:
            del data[sub_key]
            changed = True
            continue
        result = await build_for(sub_key)
        if result is None:
            del data[sub_key]
            changed = True
            continue
        embed, file = result
        if not await _edit_or_none(ch, ref, embed, file):
            del data[sub_key]
            changed = True
    if changed:
        await _save(bot, key, data)
