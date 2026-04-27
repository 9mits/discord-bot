"""Shared multi-process fleet status store.

Each bot token should use its own operational data directory/database, but all
instances can report lightweight aggregate status into this separate SQLite DB.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite
from modules.mbx_utils import now_iso


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FLEET_DB = BASE_DIR / "database" / "fleet_status.db"


def _configured_path(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


FLEET_DB = _configured_path("MBX_FLEET_DB_FILE", DEFAULT_FLEET_DB)
INSTANCE_ID = os.getenv("MBX_INSTANCE_ID", "").strip()


@dataclass(frozen=True)
class FleetSnapshot:
    instance_id: str
    bot_user_id: int
    bot_name: str
    guild_count: int
    member_count: int
    total_cases: int
    active_cases: int
    open_tickets: int


@dataclass(frozen=True)
class FleetTotals:
    instance_count: int
    guild_count: int
    member_count: int
    total_cases: int
    active_cases: int
    open_tickets: int


def _instance_id(bot) -> str:
    configured = INSTANCE_ID
    if configured:
        return configured
    user_id = getattr(getattr(bot, "user", None), "id", None)
    if user_id:
        return str(user_id)
    return "local"


def build_fleet_snapshot(bot) -> FleetSnapshot:
    data_manager = getattr(bot, "data_manager", None)
    all_punishments = getattr(data_manager, "_punishments", {}) if data_manager else {}
    all_modmail = getattr(data_manager, "_modmail", {}) if data_manager else {}
    total_cases = 0
    active_cases = 0
    open_tickets = 0

    for guild_records in all_punishments.values():
        for records in guild_records.values():
            if not isinstance(records, list):
                continue
            total_cases += len(records)
            active_cases += sum(1 for record in records if isinstance(record, dict) and record.get("active"))

    for guild_tickets in all_modmail.values():
        open_tickets += sum(
            1 for ticket in guild_tickets.values()
            if isinstance(ticket, dict) and ticket.get("status") == "open"
        )

    member_count = sum(int(guild.member_count or 0) for guild in getattr(bot, "guilds", []) or [])
    bot_user = getattr(bot, "user", None)
    return FleetSnapshot(
        instance_id=_instance_id(bot),
        bot_user_id=int(getattr(bot_user, "id", 0) or 0),
        bot_name=str(bot_user or "Unknown"),
        guild_count=len(getattr(bot, "guilds", []) or []),
        member_count=member_count,
        total_cases=total_cases,
        active_cases=active_cases,
        open_tickets=open_tickets,
    )


async def _init_db(db_path: Optional[Path] = None) -> Path:
    path = db_path or FLEET_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_fleet_status (
                instance_id  TEXT PRIMARY KEY,
                bot_user_id  INTEGER NOT NULL,
                bot_name     TEXT    NOT NULL,
                guild_count  INTEGER NOT NULL,
                member_count INTEGER NOT NULL,
                total_cases  INTEGER NOT NULL,
                active_cases INTEGER NOT NULL,
                open_tickets INTEGER NOT NULL,
                updated_at   TEXT    NOT NULL
            )
            """
        )
        await db.commit()
    return path


async def write_fleet_snapshot(bot, *, db_path: Optional[Path] = None) -> FleetSnapshot:
    path = await _init_db(db_path)
    snapshot = build_fleet_snapshot(bot)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT INTO bot_fleet_status (
                instance_id, bot_user_id, bot_name, guild_count, member_count,
                total_cases, active_cases, open_tickets, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instance_id) DO UPDATE SET
                bot_user_id=excluded.bot_user_id,
                bot_name=excluded.bot_name,
                guild_count=excluded.guild_count,
                member_count=excluded.member_count,
                total_cases=excluded.total_cases,
                active_cases=excluded.active_cases,
                open_tickets=excluded.open_tickets,
                updated_at=excluded.updated_at
            """,
            (
                snapshot.instance_id,
                snapshot.bot_user_id,
                snapshot.bot_name,
                snapshot.guild_count,
                snapshot.member_count,
                snapshot.total_cases,
                snapshot.active_cases,
                snapshot.open_tickets,
                now_iso(),
            ),
        )
        await db.commit()
    return snapshot


async def read_fleet_totals(*, db_path: Optional[Path] = None) -> FleetTotals:
    path = await _init_db(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            """
            SELECT
                COUNT(*) AS instance_count,
                COALESCE(SUM(guild_count), 0) AS guild_count,
                COALESCE(SUM(member_count), 0) AS member_count,
                COALESCE(SUM(total_cases), 0) AS total_cases,
                COALESCE(SUM(active_cases), 0) AS active_cases,
                COALESCE(SUM(open_tickets), 0) AS open_tickets
            FROM bot_fleet_status
            """
        ) as cur:
            row = await cur.fetchone()
    return FleetTotals(
        instance_count=int(row[0] or 0),
        guild_count=int(row[1] or 0),
        member_count=int(row[2] or 0),
        total_cases=int(row[3] or 0),
        active_cases=int(row[4] or 0),
        open_tickets=int(row[5] or 0),
    )


async def build_status_numbers(bot) -> tuple[FleetSnapshot, FleetTotals]:
    snapshot = await write_fleet_snapshot(bot)
    totals = await read_fleet_totals()
    return snapshot, totals


__all__ = [
    "FLEET_DB",
    "FleetSnapshot",
    "FleetTotals",
    "build_fleet_snapshot",
    "build_status_numbers",
    "read_fleet_totals",
    "write_fleet_snapshot",
]
