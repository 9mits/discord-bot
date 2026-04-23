"""Shared text and user formatting helpers.

Extracted from mbx_legacy. Pure functions — no Discord API calls, no I/O.
Depends only on discord.py types, mbx_utils, and stdlib.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Union

import discord

from modules.mbx_utils import extract_snowflake_id, format_duration, iso_to_dt, truncate_text


def join_lines(lines: List[str], fallback: str = "None") -> str:
    rendered = [line for line in lines if line]
    return "\n".join(rendered) if rendered else fallback


def get_modal_item_label(item: discord.ui.Item) -> str:
    underlying = getattr(item, "_underlying", None)
    label = getattr(underlying, "label", None)
    if label:
        return str(label)
    return "Field"


def get_user_display_name(user: Union[discord.User, discord.Member]) -> str:
    raw_name = (
        getattr(user, "display_name", None)
        or getattr(user, "global_name", None)
        or getattr(user, "name", None)
        or str(getattr(user, "id", "Unknown User"))
    )
    return truncate_text(discord.utils.escape_markdown(str(raw_name).strip() or "Unknown User"), 80)


def format_user_ref(user: Union[discord.User, discord.Member]) -> str:
    return f"{get_user_display_name(user)} • {user.mention} (`{user.id}`)"


def format_user_id_ref(user_id: Union[int, str], *, fallback_name: Optional[str] = None) -> str:
    prefix = ""
    if fallback_name:
        clean_name = truncate_text(discord.utils.escape_markdown(str(fallback_name).strip()), 80)
        if clean_name:
            prefix = f"{clean_name} • "
    return f"{prefix}<@{user_id}> (`{user_id}`)"


def get_case_id(record: dict) -> Optional[int]:
    case_id = record.get("case_id")
    if isinstance(case_id, int) and case_id > 0:
        return case_id
    return None


def get_case_label(record: dict, fallback: Optional[int] = None) -> str:
    case_id = get_case_id(record)
    if case_id is not None:
        return f"Case #{case_id}"
    if fallback is not None:
        return f"Case #{fallback}"
    return "Case"


def get_record_expiry(record: dict) -> Optional[datetime]:
    duration = record.get("duration_minutes", 0)
    if duration in (0, None):
        return None
    if duration == -1:
        return None
    issued_at = iso_to_dt(record.get("timestamp"))
    if not issued_at:
        return None
    return issued_at + timedelta(minutes=duration)


def format_case_status(record: dict) -> str:
    status = str(record.get("status", "open")).replace("_", " ").title()
    resolution = str(record.get("resolution_state", "pending")).replace("_", " ").title()
    return f"{status} • {resolution}"


def is_record_active(record: dict, now: Optional[datetime] = None) -> bool:
    now = now or discord.utils.utcnow()
    punishment_type = record.get("type")
    duration = record.get("duration_minutes", 0)

    if punishment_type == "ban":
        if duration == -1:
            return record.get("active", True)
        expiry = get_record_expiry(record)
        return bool(record.get("active", True) and expiry and expiry > now)

    if punishment_type == "timeout" and duration > 0:
        expiry = get_record_expiry(record)
        return bool(expiry and expiry > now)

    return False


def describe_punishment_record(record: dict) -> str:
    punishment_type = record.get("type", "warn")
    duration = record.get("duration_minutes", 0)

    if punishment_type == "ban":
        return "Permanent Ban" if duration == -1 else f"Tempban • {format_duration(duration)}"
    if punishment_type == "timeout":
        return f"Timeout • {format_duration(duration)}"
    if punishment_type == "kick":
        return "Kick"
    if punishment_type == "softban":
        return "Softban"
    return "Warning"


def get_punishment_duration_and_expiry(record: dict):
    punishment_type = str(record.get("type", "warn") or "warn").lower()
    duration = int(record.get("duration_minutes", 0) or 0)
    expires_at = get_record_expiry(record)

    if punishment_type == "timeout" and duration > 0:
        return format_duration(duration), discord.utils.format_dt(expires_at, "F") if expires_at else None
    if punishment_type == "ban":
        if duration == -1:
            return "Ban", "Never"
        if duration > 0:
            return format_duration(duration), discord.utils.format_dt(expires_at, "F") if expires_at else None
        return "Ban", None
    if punishment_type == "kick":
        return "Kick", None
    if punishment_type == "softban":
        return "Softban", None
    return None, None


def hex_valid(s: str) -> bool:
    if not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) != 7 or not s.startswith("#"):
        return False
    try:
        int(s[1:], 16)
        return True
    except ValueError:
        return False
