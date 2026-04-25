"""AutoMod configuration, escalation, and bridge helpers."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord

from modules.mbx_cases import (
    build_punishment_execution_log_embed,
    calculate_member_risk,
    get_active_records_for_user,
)
from modules.mbx_constants import (
    EMBED_PALETTE,
    SCOPE_MODERATION,
    SCOPE_SYSTEM,
)
from modules.mbx_context import abuse_system, bot
from modules.mbx_embeds import brand_embed, make_embed, make_error_embed, upsert_embed_field
from modules.mbx_formatters import (
    format_user_ref,
    get_case_label,
    get_user_display_name,
    join_lines,
)
from modules.mbx_logging import (
    format_log_notes,
    format_log_quote,
    format_plain_log_block,
    format_reason_value,
    get_punishment_log_channel_id,
    get_punishment_log_channel_ids,
    make_action_log_embed,
    send_automod_log,
    send_log,
    send_punishment_log,
)
from modules.mbx_permissions import (
    has_capability,
    is_staff as _permission_is_staff,
    is_staff_member,
    resolve_member,
    respond_with_error as _permission_respond_with_error,
)
from modules.mbx_punish import execute_punishment, get_valid_duration
from modules.mbx_services import (
    DEFAULT_NATIVE_AUTOMOD_SETTINGS,
    get_feature_flag,
    get_escalation_steps,
    get_native_automod_settings,
    resolve_escalation_duration,
    resolve_native_automod_policy,
)
from modules.mbx_utils import extract_snowflake_id, format_duration, iso_to_dt, now_iso, truncate_text


logger = logging.getLogger("MGXBot")


def AntiNukeResolveView(*args, **kwargs):
    from ui.config import AntiNukeResolveView as _cls
    return _cls(*args, **kwargs)


def AppealView(*args, **kwargs):
    from ui.moderation import AppealView as _cls
    return _cls(*args, **kwargs)


def AutoModWarningView(*args, **kwargs):
    from ui.automod import AutoModWarningView as _cls
    return _cls(*args, **kwargs)


is_staff = _permission_is_staff
respond_with_error = _permission_respond_with_error


def calculate_smart_punishment(user_id: str, reason: str, rules: dict, history: list) -> tuple[int, bool, str]:
    """
    Internal Point System Calculation:
    - Lookback: 90 days.
    - Points:
        - Standard: Different=1, Same=4
        - Light: Different=0.5, Same=2

    Light Offenses: Spamming, Begging, Political, Inappropriate Lang, Off-Topic, Argumentative

    Thresholds:
    - 0-2 points: Tier 0 (Base)
    - 3-7 points: Tier 1 (Escalated)
    - 8-11 points: Tier 2 (Escalated x2)
    - 12+ points: Tier 3 (Escalated x4 or Ban)
    - 16+ points: Tier 4 (Auto-Ban)
    """
    now = discord.utils.utcnow()
    lookback_days = 90

    light_offenses = {
        "Spamming", "Begging", "Political", "Inappropriate Lang",
        "Off-Topic", "Argumentative"
    }

    points = 0
    has_same_offense = False

    for rec in history:
        ts_str = rec.get("timestamp")
        if not ts_str: continue
        dt = iso_to_dt(ts_str)
        if not dt: continue
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)

        if (now - dt).days <= lookback_days:
            rec_reason = rec.get("reason")
            is_light = rec_reason in light_offenses

            if rec_reason == reason:
                points += 2 if is_light else 4
                has_same_offense = True
            else:
                points += 0.5 if is_light else 1

    base = rules.get("base", 0)
    esc = rules.get("escalated", 0)
    config = bot.data_manager.config if getattr(bot, "data_manager", None) else {}
    duration, escalated, label = resolve_escalation_duration(points, base, esc, config)

    if not escalated:
        return duration, False, label

    context = "Recidivism" if has_same_offense else "General Toxicity"
    return duration, True, f"{label} ({context})"

def build_automod_dashboard_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_native_automod_settings(bot.data_manager.config)
    total_steps = 0
    configured_rules = 0
    for payload in settings.get("rule_overrides", {}).values():
        step_count = len(get_native_automod_policy_steps(payload))
        total_steps += step_count
        if step_count:
            configured_rules += 1
    embed = make_embed(
        "AutoMod Setup",
        "> Configure the bot's follow-up after Discord AutoMod triggers.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(
        name="Bot Response",
        value=join_lines([
            f"Status: {'On' if settings.get('enabled', True) else 'Off'}",
            f"User DMs: {'On' if settings.get('warning_dm_enabled', True) else 'Off'}",
            f"Report Button: {'On' if settings.get('report_button_enabled', True) else 'Off'}",
        ]),
        inline=True,
    )
    embed.add_field(
        name="Rules",
        value=join_lines([
            f"Rules Configured: {configured_rules}",
            f"Punishment Steps: {total_steps}",
        ]),
        inline=True,
    )
    embed.add_field(
        name="Log Channels",
        value=join_lines([
            f"Warn Logs: <#{bot.data_manager.config.get('automod_log_channel_id', 0)}>" if bot.data_manager.config.get('automod_log_channel_id') else "Warn Logs: Uses the native alert channel or punishment logs",
            f"Reports: <#{bot.data_manager.config.get('automod_report_channel_id', 0)}>" if bot.data_manager.config.get('automod_report_channel_id') else "Reports: Uses appeals or punishment logs",
        ]),
        inline=False,
    )
    embed.add_field(name="Exempt Users", value=str(len(settings.get("immunity_users", []))), inline=True)
    embed.add_field(name="Exempt Roles", value=str(len(settings.get("immunity_roles", []))), inline=True)
    embed.add_field(name="Exempt Channels", value=str(len(settings.get("immunity_channels", []))), inline=True)
    return embed

AUTOMOD_PUNISHMENT_OPTIONS = [
    ("warn", "Warn Only"),
    ("timeout", "Timeout"),
    ("kick", "Kick"),
    ("ban", "Ban"),
]

AUTOMOD_THRESHOLD_PRESETS = [1, 2, 3, 4, 5, 6, 8, 10, 12]

AUTOMOD_WINDOW_PRESETS = [15, 60, 120, 360, 720, 1440, 2880, 4320, 10080]

AUTOMOD_TIMEOUT_PRESETS = [10, 30, 60, 120, 180, 720, 1440, 2880, 10080, 40320]

SMART_DUPLICATE_THRESHOLD_PRESETS = [2, 3, 4, 5, 6, 8, 10]

SMART_DUPLICATE_WINDOW_PRESETS = [10, 15, 20, 30, 45, 60, 120]

SMART_CAPS_PERCENT_PRESETS = [50, 60, 70, 75, 80, 90]

SMART_CAPS_LENGTH_PRESETS = [5, 8, 12, 16, 24, 32]

AUTOMOD_REPORT_RESPONSE_PRESETS = {
    "fixed": {
        "label": "We fixed the AutoMod",
        "description": "Tell the user the AutoMod setup was corrected.",
        "message": "We reviewed your report and fixed the AutoMod setup for that warning. Thanks for reporting it.",
        "status": "Resolved - AutoMod Updated",
        "kind": "success",
    },
    "justified": {
        "label": "Warn was justified",
        "description": "Tell the user the AutoMod warning will stand.",
        "message": "We reviewed your report and the AutoMod warning was justified, so it will remain as-is.",
        "status": "Reviewed - Warning Stands",
        "kind": "warning",
    },
    "removed": {
        "label": "Warn was removed",
        "description": "Tell the user the warning was treated as a false positive.",
        "message": "We reviewed your report and treated this as a false positive. The warning has been cleared on our side.",
        "status": "Resolved - False Positive",
        "kind": "success",
    },
    "custom": {
        "label": "Custom response",
        "description": "Write and send a custom staff response.",
        "message": "",
        "status": "Staff Replied",
        "kind": "info",
    },
}

SMART_AUTOMOD_DEFAULTS = {
    "duplicate_window_seconds": 20,
    "duplicate_threshold": 4,
    "max_caps_ratio": 0.75,
    "caps_min_length": 12,
    "blocked_patterns": [],
    "exempt_channels": [],
    "exempt_roles": [],
}

def format_minutes_interval(minutes: int) -> str:
    minutes = max(1, int(minutes or 1))
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    if minutes < 1440:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = minutes // 1440
    return f"{days} day{'s' if days != 1 else ''}"

def format_seconds_interval(seconds: int) -> str:
    seconds = max(1, int(seconds or 1))
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = seconds // 60
    return format_minutes_interval(minutes)

def format_compact_minutes_input(minutes: int) -> str:
    minutes = max(1, int(minutes or 1))
    if minutes % 10080 == 0:
        return f"{minutes // 10080}w"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"

def parse_positive_integer_input(raw_value: str, *, field_name: str, minimum: int = 1, maximum: int = 999) -> int:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if not text.isdigit():
        raise ValueError(f"{field_name} must be a whole number.")
    value = int(text)
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return value

def parse_minutes_input(raw_value: str, *, field_name: str, minimum: int = 1, maximum: int = 40320) -> int:
    text = str(raw_value or "").strip().lower()
    if not text:
        raise ValueError(f"{field_name} is required.")

    match = re.fullmatch(r"(\d+)\s*([a-z]+)?", text)
    if not match:
        raise ValueError(f"{field_name} must look like 30m, 12h, 2d, or 1w.")

    amount = int(match.group(1))
    unit = (match.group(2) or "m").lower()

    if unit in {"m", "min", "mins", "minute", "minutes"}:
        minutes = amount
    elif unit in {"h", "hr", "hrs", "hour", "hours"}:
        minutes = amount * 60
    elif unit in {"d", "day", "days"}:
        minutes = amount * 1440
    elif unit in {"w", "wk", "wks", "week", "weeks"}:
        minutes = amount * 10080
    else:
        raise ValueError(f"{field_name} must use m, h, d, or w.")

    if minutes < minimum or minutes > maximum:
        raise ValueError(f"{field_name} must be between {format_minutes_interval(minimum)} and {format_minutes_interval(maximum)}.")
    return minutes

def parse_automod_punishment_input(raw_value: str, *, field_name: str = "Action") -> str:
    text = str(raw_value or "").strip().lower()
    mapping = {
        "warn": "warn",
        "warning": "warn",
        "timeout": "timeout",
        "mute": "timeout",
        "kick": "kick",
        "ban": "ban",
    }
    punishment_type = mapping.get(text)
    if punishment_type is None:
        raise ValueError(f"{field_name} must be one of: warn, timeout, kick, or ban.")
    return punishment_type

def build_numeric_select_options(current: int, presets: List[int], formatter) -> List[discord.SelectOption]:
    values = []
    for value in presets:
        if value not in values:
            values.append(value)
    if current not in values:
        values.append(current)
    return [
        discord.SelectOption(label=truncate_text(formatter(value), 100), value=str(value), default=value == current)
        for value in values[:25]
    ]

def get_smart_automod_settings() -> dict:
    current = bot.data_manager.config.get("smart_automod", {})
    normalized = {
        "duplicate_window_seconds": max(5, int(current.get("duplicate_window_seconds", SMART_AUTOMOD_DEFAULTS["duplicate_window_seconds"]) or SMART_AUTOMOD_DEFAULTS["duplicate_window_seconds"])),
        "duplicate_threshold": max(2, int(current.get("duplicate_threshold", SMART_AUTOMOD_DEFAULTS["duplicate_threshold"]) or SMART_AUTOMOD_DEFAULTS["duplicate_threshold"])),
        "max_caps_ratio": max(0.1, min(1.0, float(current.get("max_caps_ratio", SMART_AUTOMOD_DEFAULTS["max_caps_ratio"]) or SMART_AUTOMOD_DEFAULTS["max_caps_ratio"]))),
        "caps_min_length": max(3, int(current.get("caps_min_length", SMART_AUTOMOD_DEFAULTS["caps_min_length"]) or SMART_AUTOMOD_DEFAULTS["caps_min_length"])),
        "blocked_patterns": [str(item).strip()[:80] for item in current.get("blocked_patterns", []) if str(item).strip()][:50],
        "exempt_channels": [int(item) for item in current.get("exempt_channels", []) if isinstance(item, int) or str(item).isdigit()],
        "exempt_roles": [int(item) for item in current.get("exempt_roles", []) if isinstance(item, int) or str(item).isdigit()],
    }
    return normalized

def store_native_automod_settings(settings: dict) -> dict:
    normalized = get_native_automod_settings({"native_automod": settings})
    bot.data_manager.config["native_automod"] = normalized
    return normalized

def store_smart_automod_settings(settings: dict) -> dict:
    normalized = get_smart_automod_settings()
    normalized.update({
        "duplicate_window_seconds": max(5, int(settings.get("duplicate_window_seconds", normalized["duplicate_window_seconds"]) or normalized["duplicate_window_seconds"])),
        "duplicate_threshold": max(2, int(settings.get("duplicate_threshold", normalized["duplicate_threshold"]) or normalized["duplicate_threshold"])),
        "max_caps_ratio": max(0.1, min(1.0, float(settings.get("max_caps_ratio", normalized["max_caps_ratio"]) or normalized["max_caps_ratio"]))),
        "caps_min_length": max(3, int(settings.get("caps_min_length", normalized["caps_min_length"]) or normalized["caps_min_length"])),
        "blocked_patterns": [str(item).strip()[:80] for item in settings.get("blocked_patterns", normalized["blocked_patterns"]) if str(item).strip()][:50],
        "exempt_channels": [int(item) for item in settings.get("exempt_channels", normalized["exempt_channels"]) if isinstance(item, int) or str(item).isdigit()],
        "exempt_roles": [int(item) for item in settings.get("exempt_roles", normalized["exempt_roles"]) if isinstance(item, int) or str(item).isdigit()],
    })
    bot.data_manager.config["smart_automod"] = normalized
    return normalized

def format_automod_punishment_label(policy: dict) -> str:
    punishment_type = str(policy.get("punishment_type", "warn") or "warn").lower()
    if punishment_type == "timeout":
        return f"Timeout ({format_duration(int(policy.get('duration_minutes', 60) or 60))})"
    if punishment_type == "ban":
        return "Ban"
    if punishment_type == "kick":
        return "Kick"
    return "Warn Only"

def get_automod_report_preset(key: str) -> dict:
    return AUTOMOD_REPORT_RESPONSE_PRESETS.get(key, AUTOMOD_REPORT_RESPONSE_PRESETS["custom"])

def build_default_native_automod_policy() -> dict:
    return {
        "enabled": False,
        "reason_template": str(DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"]),
        "steps": [],
    }

def get_native_automod_policy_steps(policy: Optional[dict]) -> List[dict]:
    if not isinstance(policy, dict):
        return []
    steps = []
    for payload in policy.get("steps", []):
        if not isinstance(payload, dict):
            continue
        punishment_type = str(payload.get("punishment_type", "warn") or "warn").lower()
        threshold = max(1, int(payload.get("threshold", 1) or 1))
        window_minutes = max(1, int(payload.get("window_minutes", 1440) or 1440))
        duration_minutes = int(payload.get("duration_minutes", 0) or 0)
        if punishment_type == "timeout":
            duration_minutes = max(1, min(40320, duration_minutes or 60))
        elif punishment_type == "ban":
            duration_minutes = -1
        else:
            duration_minutes = 0
        steps.append({
            "threshold": threshold,
            "window_minutes": window_minutes,
            "duration_minutes": duration_minutes,
            "punishment_type": punishment_type,
        })
    steps.sort(key=lambda step: (int(step.get("threshold", 1)), int(step.get("window_minutes", 1)), str(step.get("punishment_type", "warn"))))
    return steps[:5]

def build_default_native_automod_step(existing_steps: Optional[List[dict]] = None) -> dict:
    steps = get_native_automod_policy_steps({"steps": existing_steps or []})
    if steps:
        last_step = steps[-1]
        threshold = min(25, max(1, int(last_step.get("threshold", 3) or 3) + 1))
        window_minutes = int(last_step.get("window_minutes", 1440) or 1440)
    else:
        threshold = 3
        window_minutes = 1440
    return {
        "threshold": threshold,
        "window_minutes": window_minutes,
        "duration_minutes": 60,
        "punishment_type": "timeout",
    }

def format_native_automod_step_summary(step: dict) -> str:
    threshold = int(step.get("threshold", 1) or 1)
    return f"{threshold} warning{'s' if threshold != 1 else ''} in {format_minutes_interval(int(step.get('window_minutes', 1440) or 1440))} -> {format_automod_punishment_label(step)}"

def get_native_rule_override(settings: dict, rule: discord.AutoModRule) -> Tuple[str, dict, bool]:
    overrides = settings.get("rule_overrides", {})
    for candidate in (str(rule.id), rule.name):
        if candidate in overrides:
            return candidate, overrides[candidate], True
    return str(rule.id), build_default_native_automod_policy(), False

def render_id_mentions(ids: List[int], *, prefix: str, limit: int = 6) -> str:
    cleaned = [int(value) for value in ids if isinstance(value, int) or str(value).isdigit()]
    if not cleaned:
        return "None"
    rendered = [f"<{prefix}{value}>" for value in cleaned[:limit]]
    if len(cleaned) > limit:
        rendered.append(f"+{len(cleaned) - limit} more")
    return ", ".join(rendered)

def build_automod_bridge_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_native_automod_settings(bot.data_manager.config)
    embed = make_embed(
        "AutoMod Bot Response",
        "> Control what the bot does after Discord AutoMod triggers.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(name="Bot Response", value="On" if settings.get("enabled", True) else "Off", inline=True)
    embed.add_field(name="User DMs", value="On" if settings.get("warning_dm_enabled", True) else "Off", inline=True)
    embed.add_field(name="False-Positive Report", value="On" if settings.get("report_button_enabled", True) else "Off", inline=True)
    embed.add_field(
        name="What Happens",
        value=join_lines([
            "Discord AutoMod blocks or flags a message.",
            "The bot can DM the user and log the event.",
            "Any automatic punishment must be turned on per rule.",
            "The report button lets the user ask staff to review the warning.",
        ]),
        inline=False,
    )
    return embed

def build_automod_policy_embed(
    guild: discord.Guild,
    policy: dict,
    *,
    title: str,
    description: str,
    rule: Optional[discord.AutoModRule] = None,
    using_override: bool = False,
    selected_step_index: Optional[int] = None,
) -> discord.Embed:
    steps = get_native_automod_policy_steps(policy)
    embed = make_embed(title, description, kind="warning", scope=SCOPE_MODERATION, guild=guild)
    if rule is not None:
        embed.add_field(name="Rule", value=rule.name, inline=True)
        embed.add_field(name="Discord Actions", value=describe_automod_rule_actions(rule), inline=True)
    embed.add_field(name="Auto Punish", value="On" if policy.get("enabled") and steps else "Off", inline=True)
    embed.add_field(name="Steps", value=str(len(steps)), inline=True)
    if steps:
        step_lines = [f"{index + 1}. {format_native_automod_step_summary(step)}" for index, step in enumerate(steps[:5])]
        embed.add_field(name="Escalation Ladder", value=join_lines(step_lines, fallback="No punishment steps set yet."), inline=False)
    else:
        embed.add_field(name="Escalation Ladder", value="No punishment steps set yet.", inline=False)
    if steps and selected_step_index is not None and 0 <= selected_step_index < len(steps):
        selected_step = steps[selected_step_index]
        selected_lines = [
            f"Step: {selected_step_index + 1}",
            f"Warnings: {selected_step.get('threshold', 1)}",
            f"Window: {format_minutes_interval(int(selected_step.get('window_minutes', 1440) or 1440))}",
            f"Action: {format_automod_punishment_label(selected_step)}",
        ]
        if str(selected_step.get("punishment_type", "warn")).lower() == "timeout":
            selected_lines.append(f"Timeout: {format_minutes_interval(int(selected_step.get('duration_minutes', 60) or 60))}")
        embed.add_field(name="Selected Step", value=join_lines(selected_lines), inline=False)
    embed.add_field(name="Reason Template", value=format_log_quote(policy.get("reason_template", "Repeated native AutoMod violations"), limit=500), inline=False)
    return embed

def build_automod_immunity_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_native_automod_settings(bot.data_manager.config)
    embed = make_embed(
        "AutoMod Immunity",
        "> Choose who should be ignored by the native AutoMod bridge follow-up.",
        kind="info",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(name="Users", value=render_id_mentions(settings.get("immunity_users", []), prefix="@"), inline=False)
    embed.add_field(name="Roles", value=render_id_mentions(settings.get("immunity_roles", []), prefix="@&"), inline=False)
    embed.add_field(name="Channels", value=render_id_mentions(settings.get("immunity_channels", []), prefix="#"), inline=False)
    return embed

def build_automod_routing_embed(guild: discord.Guild) -> discord.Embed:
    embed = make_embed(
        "AutoMod Log Channels",
        "> Use the selectors below to set or clear where the bot sends AutoMod logs and user reports.",
        kind="info",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(
        name="Log Channel",
        value=f"<#{bot.data_manager.config.get('automod_log_channel_id', 0)}>" if bot.data_manager.config.get("automod_log_channel_id") else "Uses punishment logs or the native alert channel fallback",
        inline=False,
    )
    embed.add_field(
        name="Report Channel",
        value=f"<#{bot.data_manager.config.get('automod_report_channel_id', 0)}>" if bot.data_manager.config.get("automod_report_channel_id") else "Uses the appeal log channel or punishment logs",
        inline=False,
    )
    return embed

def build_smart_automod_embed(guild: discord.Guild) -> discord.Embed:
    settings = get_smart_automod_settings()
    embed = make_embed(
        "Smart AutoMod Filters",
        "> Configure the bot's own duplicate, caps, and blocked-pattern checks.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(name="Duplicate Window", value=f"{settings.get('duplicate_threshold', 4)} messages in {settings.get('duplicate_window_seconds', 20)} seconds", inline=True)
    embed.add_field(name="Caps Rule", value=f"{round(float(settings.get('max_caps_ratio', 0.75)) * 100)}% after {settings.get('caps_min_length', 12)} chars", inline=True)
    embed.add_field(name="Blocked Patterns", value=str(len(settings.get("blocked_patterns", []))), inline=True)
    embed.add_field(
        name="Current Pattern Preview",
        value=join_lines([f"- `{pattern}`" for pattern in settings.get("blocked_patterns", [])[:8]], fallback="No patterns configured."),
        inline=False,
    )
    embed.add_field(name="Exempt Roles", value=render_id_mentions(settings.get("exempt_roles", []), prefix="@&"), inline=False)
    embed.add_field(name="Exempt Channels", value=render_id_mentions(settings.get("exempt_channels", []), prefix="#"), inline=False)
    return embed

def build_automod_rule_browser_embed(guild: discord.Guild, rules: List[discord.AutoModRule]) -> discord.Embed:
    settings = get_native_automod_settings(bot.data_manager.config)
    configured_rules = sum(1 for payload in settings.get("rule_overrides", {}).values() if get_native_automod_policy_steps(payload))
    embed = make_embed(
        "Native AutoMod Rules",
        "> Pick one Discord AutoMod rule below to set up that rule's automatic punishment steps.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    if not rules:
        embed.add_field(name="Rules", value="No native Discord AutoMod rules were found in this server.", inline=False)
        return embed
    embed.add_field(name="Native Rules", value=str(len(rules)), inline=True)
    embed.add_field(name="Rules Configured", value=str(configured_rules), inline=True)
    for rule in rules[:6]:
        _, policy, using_override = get_native_rule_override(settings, rule)
        steps = get_native_automod_policy_steps(policy)
        embed.add_field(
            name=f"{'On' if rule.enabled else 'Off'} • {rule.name}",
            value=join_lines([
                f"Discord: {describe_automod_rule_actions(rule)}",
                f"Auto Punish: {'On' if policy.get('enabled') and steps else 'Off'}",
                f"Steps: {len(steps)}",
                (f"Last Step: {format_automod_punishment_label(steps[-1])}" if steps else "No steps set"),
            ]),
            inline=False,
        )
    return embed

def describe_automod_rule_trigger(rule: discord.AutoModRule) -> str:
    trigger = rule.trigger
    if trigger.type == discord.AutoModRuleTriggerType.keyword:
        keywords = ", ".join(f"`{truncate_text(value, 20)}`" for value in trigger.keyword_filter[:4]) or "No keywords"
        regexes = ", ".join(f"`{truncate_text(value, 20)}`" for value in trigger.regex_patterns[:2])
        details = [f"Keywords: {keywords}"]
        if regexes:
            details.append(f"Regex: {regexes}")
        return join_lines(details)
    if trigger.type == discord.AutoModRuleTriggerType.keyword_preset:
        presets = []
        if trigger.presets.profanity:
            presets.append("Profanity")
        if trigger.presets.sexual_content:
            presets.append("Sexual Content")
        if trigger.presets.slurs:
            presets.append("Slurs")
        return ", ".join(presets) or "Preset Rule"
    if trigger.type == discord.AutoModRuleTriggerType.mention_spam:
        raid = "On" if trigger.mention_raid_protection else "Off"
        return f"Mention Limit: {trigger.mention_limit or 0} • Raid Protection: {raid}"
    if trigger.type == discord.AutoModRuleTriggerType.spam:
        return "Spam detection"
    return trigger.type.name.replace('_', ' ').title()

def describe_automod_rule_actions(rule: discord.AutoModRule) -> str:
    parts = []
    for action in rule.actions:
        if action.type == discord.AutoModRuleActionType.block_message:
            parts.append(f"Block message{' + custom notice' if action.custom_message else ''}")
        elif action.type == discord.AutoModRuleActionType.send_alert_message:
            parts.append(f"Send alert to <#{action.channel_id}>")
        elif action.type == discord.AutoModRuleActionType.timeout:
            minutes = int(action.duration.total_seconds() // 60) if action.duration else 0
            parts.append(f"Timeout for {format_duration(minutes)}")
        elif action.type == discord.AutoModRuleActionType.block_member_interactions:
            parts.append("Block member interactions")
    return ", ".join(parts) or "No actions"

def serialize_automod_rule(rule: discord.AutoModRule) -> dict:
    trigger = rule.trigger
    presets = []
    if trigger.presets.profanity:
        presets.append("profanity")
    if trigger.presets.sexual_content:
        presets.append("sexual_content")
    if trigger.presets.slurs:
        presets.append("slurs")

    payload = {
        "name": rule.name,
        "enabled": rule.enabled,
        "trigger_type": rule.trigger.type.name,
        "keyword_filter": trigger.keyword_filter,
        "regex_patterns": trigger.regex_patterns,
        "allow_list": trigger.allow_list,
        "mention_limit": trigger.mention_limit,
        "mention_raid_protection": trigger.mention_raid_protection,
        "presets": presets,
        "actions": [],
        "exempt_roles": list(rule.exempt_role_ids),
        "exempt_channels": list(rule.exempt_channel_ids),
    }
    for action in rule.actions:
        action_payload = {"type": action.type.name}
        if action.custom_message:
            action_payload["custom_message"] = action.custom_message
        if action.channel_id:
            action_payload["channel_id"] = action.channel_id
        if action.duration:
            action_payload["duration_minutes"] = int(action.duration.total_seconds() // 60)
        payload["actions"].append(action_payload)
    return payload

def build_automod_trigger_from_payload(payload: dict, existing_type: Optional[discord.AutoModRuleTriggerType] = None) -> discord.AutoModTrigger:
    trigger_name = str(payload.get("trigger_type") or (existing_type.name if existing_type else "keyword")).lower()
    trigger_type = discord.AutoModRuleTriggerType[trigger_name]
    if trigger_type == discord.AutoModRuleTriggerType.keyword:
        return discord.AutoModTrigger(
            type=trigger_type,
            keyword_filter=[str(v) for v in payload.get("keyword_filter", []) if str(v).strip()],
            regex_patterns=[str(v) for v in payload.get("regex_patterns", []) if str(v).strip()],
            allow_list=[str(v) for v in payload.get("allow_list", []) if str(v).strip()],
        )
    if trigger_type == discord.AutoModRuleTriggerType.keyword_preset:
        presets = discord.AutoModPresets.none()
        for name in payload.get("presets", []):
            if name == "profanity":
                presets.profanity = True
            elif name == "sexual_content":
                presets.sexual_content = True
            elif name == "slurs":
                presets.slurs = True
        return discord.AutoModTrigger(type=trigger_type, presets=presets, allow_list=[str(v) for v in payload.get("allow_list", []) if str(v).strip()])
    if trigger_type == discord.AutoModRuleTriggerType.mention_spam:
        return discord.AutoModTrigger(
            type=trigger_type,
            mention_limit=max(1, min(50, int(payload.get("mention_limit", 5) or 5))),
            mention_raid_protection=bool(payload.get("mention_raid_protection", False)),
        )
    return discord.AutoModTrigger(type=trigger_type)

def build_automod_actions_from_payload(payload: dict, guild: discord.Guild) -> List[discord.AutoModRuleAction]:
    actions: List[discord.AutoModRuleAction] = []
    for action_payload in payload.get("actions", []):
        if not isinstance(action_payload, dict):
            continue
        action_type = str(action_payload.get("type", "block_message")).lower()
        if action_type == "send_alert_message":
            channel_id = action_payload.get("channel_id") or bot.data_manager.config.get("automod_log_channel_id") or get_punishment_log_channel_id()
            if channel_id:
                actions.append(discord.AutoModRuleAction(channel_id=int(channel_id)))
        elif action_type == "timeout":
            duration_minutes = max(1, min(40320, int(action_payload.get("duration_minutes", 60) or 60)))
            actions.append(discord.AutoModRuleAction(duration=timedelta(minutes=duration_minutes)))
        elif action_type == "block_member_interactions":
            actions.append(discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_member_interactions))
        else:
            actions.append(discord.AutoModRuleAction(custom_message=str(action_payload.get("custom_message") or "This message was blocked by server AutoMod.")))
    if not actions:
        actions.append(discord.AutoModRuleAction(custom_message="This message was blocked by server AutoMod."))
        alert_channel_id = bot.data_manager.config.get("automod_log_channel_id") or get_punishment_log_channel_id()
        if alert_channel_id:
            actions.append(discord.AutoModRuleAction(channel_id=int(alert_channel_id)))
    return actions

async def fetch_native_automod_rules(guild: discord.Guild) -> List[discord.AutoModRule]:
    return await guild.fetch_automod_rules()

def build_native_automod_rules_embed(guild: discord.Guild, rules: List[discord.AutoModRule]) -> discord.Embed:
    embed = make_embed(
        "Native AutoMod Rules",
        "> Discord's built-in AutoMod rules currently configured for this server.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    if not rules:
        embed.add_field(name="Rules", value="No native AutoMod rules are configured yet.", inline=False)
        return embed
    embed.add_field(name="Total Rules", value=str(len(rules)), inline=True)
    embed.add_field(name="Enabled", value=str(sum(1 for rule in rules if rule.enabled)), inline=True)
    for rule in rules[:10]:
        embed.add_field(
            name=f"{'On' if rule.enabled else 'Off'} • {rule.name}",
            value=join_lines([
                f"Trigger: {describe_automod_rule_trigger(rule)}",
                f"Actions: {describe_automod_rule_actions(rule)}",
                f"Exempt Roles: {len(rule.exempt_role_ids)} • Exempt Channels: {len(rule.exempt_channel_ids)}",
            ]),
            inline=False,
        )
    return embed

def build_native_automod_rule_detail_embed(guild: discord.Guild, rule: discord.AutoModRule) -> discord.Embed:
    embed = make_embed(
        f"AutoMod Rule: {rule.name}",
        "> Detailed view of one Discord native AutoMod rule.",
        kind="warning",
        scope=SCOPE_MODERATION,
        guild=guild,
    )
    embed.add_field(name="Target", value=rule.name, inline=True)
    embed.add_field(name="Reason", value=format_reason_value(rule.trigger.type.name.replace('_', ' ').title(), limit=300), inline=False)
    embed.add_field(name="Trigger", value=describe_automod_rule_trigger(rule), inline=False)
    embed.add_field(name="Actions", value=describe_automod_rule_actions(rule), inline=False)
    embed.add_field(name="Enabled", value="Yes" if rule.enabled else "No", inline=True)
    embed.add_field(name="Rule ID", value=str(rule.id), inline=True)
    embed.add_field(name="Exempt Roles", value=", ".join(f"<@&{rid}>" for rid in rule.exempt_role_ids) or "None", inline=False)
    embed.add_field(name="Exempt Channels", value=", ".join(f"<#{cid}>" for cid in rule.exempt_channel_ids) or "None", inline=False)
    return embed

async def handle_abuse(interaction: discord.Interaction, moderator: discord.Member):
    # Security Protocol: Strip Roles
    mod_roles = bot.data_manager.config.get("mod_roles", [])
    to_remove = []
    for rid in mod_roles:
        role = interaction.guild.get_role(rid)
        if role and role in moderator.roles:
            to_remove.append(role)

    if to_remove:
        try:
            await moderator.remove_roles(*to_remove, reason="Anti-Abuse: Rate limit exceeded")
        except Exception:
            pass

    embed = make_embed(
        "Security Alert: Abuse Detected",
        "> The anti-abuse rate limiter flagged a moderation action burst and removed elevated roles.",
        kind="danger",
        scope=SCOPE_SYSTEM,
        guild=interaction.guild,
        thumbnail=moderator.display_avatar.url,
    )
    embed.add_field(name="Actor", value=format_user_ref(moderator), inline=True)
    embed.add_field(name="System Action", value="Roles stripped due to rate-limit violation", inline=True)
    await send_log(interaction.guild, embed)
    await interaction.response.send_message("Action blocked. You have been flagged for abuse.", ephemeral=True)

async def punish_rogue_mod(guild: discord.Guild, member: discord.User, reason: str, embed: discord.Embed = None, restore_data: dict = None):
    # Fetch fresh member to ensure roles are up to date and we have a Member object
    target_member = guild.get_member(member.id)
    if not target_member:
        try:
            target_member = await guild.fetch_member(member.id)
        except Exception:
            target_member = None

    action_log = "No configured staff roles found on user."
    stripped_ids = []

    if target_member:
        # 1. Strip Mod Roles
        mod_roles_ids = bot.data_manager.config.get("mod_roles", [])
        to_remove = []
        for rid in mod_roles_ids:
            role = guild.get_role(rid)
            if role and role in target_member.roles:
                to_remove.append(role)

        if to_remove:
            try:
                await target_member.remove_roles(*to_remove, reason=f"ANTI-NUKE: {reason}")
                action_log = f"Stripped Staff Roles: {', '.join([r.name for r in to_remove])}"
                stripped_ids = [r.id for r in to_remove]
            except Exception as e:
                action_log = f"Failed to strip roles: {e}"
    else:
        action_log = "User left guild or not found."

    # 2. Log
    if embed is None:
        embed = make_embed(
            "Security Alert: Anti-Nuke Triggered",
            "> A protected action was automatically reverted and the actor was restricted.",
            kind="danger",
            scope=SCOPE_SYSTEM,
            guild=guild,
        )
        embed.add_field(name="Actor", value=f"<@{member.id}> (`{member.id}`)", inline=True)
        embed.add_field(name="Violation", value=truncate_text(reason, 1000), inline=False)

    embed.add_field(name="System Action", value=f"> {action_log}", inline=True)
    brand_embed(embed, guild=guild, scope=SCOPE_SYSTEM)

    view = None
    if restore_data:
        restore_data["stripped_roles"] = stripped_ids
        restore_data["actor_id"] = member.id
        view = AntiNukeResolveView(restore_data)

    # Dynamic pings — only include roles that are actually configured for this guild
    r_admin = bot.data_manager.config.get("role_admin")
    r_owner = bot.data_manager.config.get("role_owner")
    ping_parts = [f"<@&{r}>" for r in (r_admin, r_owner) if r]
    pings = " ".join(ping_parts) if ping_parts else None

    await send_log(guild, embed, content=pings, view=view)

def get_native_automod_stats_bucket(user_id: int) -> dict:
    store = bot.data_manager.mod_stats.setdefault("native_automod", {})
    if not isinstance(store, dict):
        store = {}
        bot.data_manager.mod_stats["native_automod"] = store
    bucket = store.setdefault(str(user_id), {"events": [], "applied_steps": []})
    if not isinstance(bucket, dict):
        bucket = {"events": [], "applied_steps": []}
        store[str(user_id)] = bucket
    events = bucket.setdefault("events", [])
    if not isinstance(events, list):
        bucket["events"] = []
    applied_steps = bucket.setdefault("applied_steps", [])
    if not isinstance(applied_steps, list):
        bucket["applied_steps"] = []
    return bucket

def prune_native_automod_bucket(bucket: dict, *, now_value: Optional[datetime] = None) -> None:
    now_value = now_value or discord.utils.utcnow()

    fresh_events = []
    for event in bucket.get("events", []):
        dt = iso_to_dt(event.get("timestamp")) if isinstance(event, dict) else None
        if dt and now_value - dt <= timedelta(days=30):
            fresh_events.append(event)
    bucket["events"] = fresh_events[-100:]

    fresh_steps = []
    for record in bucket.get("applied_steps", []):
        dt = iso_to_dt(record.get("timestamp")) if isinstance(record, dict) else None
        if dt and now_value - dt <= timedelta(days=30):
            fresh_steps.append(record)
    bucket["applied_steps"] = fresh_steps[-100:]

def record_native_automod_event(*, user_id: int, rule_id: int, rule_name: str, content: str, matched_keyword: Optional[str]) -> None:
    bucket = get_native_automod_stats_bucket(user_id)
    now_value = discord.utils.utcnow()
    prune_native_automod_bucket(bucket, now_value=now_value)
    events = list(bucket.get("events", []))
    events.append({
        "timestamp": now_iso(),
        "rule_id": int(rule_id),
        "rule_name": rule_name,
        "content": truncate_text(content, 500),
        "matched_keyword": matched_keyword,
    })
    bucket["events"] = events[-100:]

def count_recent_native_automod_hits(*, user_id: int, rule_id: int, rule_name: str, window_minutes: int) -> int:
    bucket = get_native_automod_stats_bucket(user_id)
    prune_native_automod_bucket(bucket)
    cutoff = discord.utils.utcnow() - timedelta(minutes=max(1, window_minutes))
    count = 0
    for event in bucket.get("events", []):
        if not isinstance(event, dict):
            continue
        dt = iso_to_dt(event.get("timestamp"))
        if not dt or dt < cutoff:
            continue
        event_rule_id = event.get("rule_id")
        event_rule_name = str(event.get("rule_name", ""))
        if str(event_rule_id) == str(rule_id) or event_rule_name == rule_name:
            count += 1
    return count

def has_recent_native_automod_step_application(
    *,
    user_id: int,
    rule_id: int,
    rule_name: str,
    threshold: int,
    window_minutes: int,
) -> bool:
    bucket = get_native_automod_stats_bucket(user_id)
    prune_native_automod_bucket(bucket)
    cutoff = discord.utils.utcnow() - timedelta(minutes=max(1, window_minutes))
    for record in bucket.get("applied_steps", []):
        if not isinstance(record, dict):
            continue
        dt = iso_to_dt(record.get("timestamp"))
        if not dt or dt < cutoff:
            continue
        record_rule_id = record.get("rule_id")
        record_rule_name = str(record.get("rule_name", ""))
        if str(record_rule_id) != str(rule_id) and record_rule_name != rule_name:
            continue
        if int(record.get("threshold", 0) or 0) != int(threshold):
            continue
        if int(record.get("window_minutes", 0) or 0) != int(window_minutes):
            continue
        return True
    return False

def record_native_automod_step_application(
    *,
    user_id: int,
    rule_id: int,
    rule_name: str,
    step: dict,
) -> None:
    bucket = get_native_automod_stats_bucket(user_id)
    now_value = discord.utils.utcnow()
    prune_native_automod_bucket(bucket, now_value=now_value)
    applied_steps = list(bucket.get("applied_steps", []))
    applied_steps.append({
        "timestamp": now_iso(),
        "rule_id": int(rule_id),
        "rule_name": str(rule_name),
        "threshold": int(step.get("threshold", 1) or 1),
        "window_minutes": int(step.get("window_minutes", 1440) or 1440),
        "punishment_type": str(step.get("punishment_type", "warn") or "warn"),
        "duration_minutes": int(step.get("duration_minutes", 0) or 0),
    })
    bucket["applied_steps"] = applied_steps[-100:]

def get_triggered_native_automod_step(*, user_id: int, rule_id: int, rule_name: str, policy: dict) -> Tuple[Optional[dict], int]:
    if not bool(policy.get("enabled", False)):
        return None, 0

    for step in get_native_automod_policy_steps(policy):
        threshold = int(step.get("threshold", 1) or 1)
        window_minutes = int(step.get("window_minutes", 1440) or 1440)
        hit_count = count_recent_native_automod_hits(
            user_id=user_id,
            rule_id=rule_id,
            rule_name=rule_name,
            window_minutes=window_minutes,
        )
        if hit_count < threshold:
            continue
        if has_recent_native_automod_step_application(
            user_id=user_id,
            rule_id=rule_id,
            rule_name=rule_name,
            threshold=threshold,
            window_minutes=window_minutes,
        ):
            continue
        return step, hit_count
    return None, 0

def build_native_automod_dedupe_key(execution: discord.AutoModAction) -> Tuple[int, int, int, str, str]:
    return (
        int(execution.guild_id or 0),
        int(execution.user_id or 0),
        int(execution.rule_id or 0),
        str(execution.channel_id or 0),
        truncate_text(execution.matched_keyword or execution.matched_content or execution.content or "", 120),
    )

def claim_native_automod_execution(execution: discord.AutoModAction, *, ttl_seconds: int = 15) -> bool:
    now_ts = time.time()
    cache = bot.native_automod_event_cache
    for cache_key, seen_at in list(cache.items()):
        if now_ts - seen_at > ttl_seconds:
            cache.pop(cache_key, None)

    dedupe_key = build_native_automod_dedupe_key(execution)
    previous = cache.get(dedupe_key)
    if previous and now_ts - previous <= ttl_seconds:
        return False

    cache[dedupe_key] = now_ts
    return True

def get_native_automod_action_label(execution: discord.AutoModAction) -> str:
    return execution.action.type.name.replace("_", " ").title()

def native_automod_rule_has_enforcement(rule: Optional[discord.AutoModRule], execution: discord.AutoModAction) -> bool:
    enforcement_types = {
        discord.AutoModRuleActionType.block_message,
        discord.AutoModRuleActionType.timeout,
        discord.AutoModRuleActionType.block_member_interactions,
    }
    if execution.action.type in enforcement_types:
        return True
    if rule is None:
        return False
    return any(getattr(action, "type", None) in enforcement_types for action in getattr(rule, "actions", []))

def is_native_automod_exempt(member: discord.Member, channel_id: Optional[int], settings: dict) -> bool:
    if str(member.id) in bot.data_manager.config.get("immunity_list", []):
        return True

    immunity_users = {int(value) for value in settings.get("immunity_users", []) if isinstance(value, int) or str(value).isdigit()}
    immunity_roles = {int(value) for value in settings.get("immunity_roles", []) if isinstance(value, int) or str(value).isdigit()}
    immunity_channels = {int(value) for value in settings.get("immunity_channels", []) if isinstance(value, int) or str(value).isdigit()}

    if member.id in immunity_users:
        return True
    if channel_id and channel_id in immunity_channels:
        return True
    return any(role.id in immunity_roles for role in member.roles)

async def apply_native_automod_escalation(
    guild: discord.Guild,
    member: discord.Member,
    *,
    rule_id: int,
    rule_name: str,
    content: str,
    matched_keyword: Optional[str],
    warning_count: int,
    policy: dict,
    step: dict,
) -> Tuple[bool, str, Optional[dict]]:
    punishment_type = str(step.get("punishment_type", "warn") or "warn").lower()
    duration_minutes = int(step.get("duration_minutes", 0) or 0)
    threshold = int(step.get("threshold", 1) or 1)
    window_minutes = int(step.get("window_minutes", 1440) or 1440)
    reason_template = str(policy.get("reason_template", "Repeated native AutoMod violations") or "Repeated native AutoMod violations")
    reason = f"{reason_template} [{rule_name}]"
    if punishment_type == "ban":
        action_label = "Banned"
    elif punishment_type == "timeout":
        action_label = "Timed Out"
    elif punishment_type == "kick":
        action_label = "Kicked"
    else:
        action_label = "Warned"
    user_message_text = f"You have been **{action_label}** in **{guild.name}**."
    note = truncate_text(
        "\n".join([
            "Discord AutoMod escalation triggered.",
            f"Rule: {rule_name}",
            f"Hit Count: {warning_count} warning(s) in {format_minutes_interval(window_minutes)}",
            f"Triggered Step: {threshold} warning(s)",
            f"Matched Keyword: {matched_keyword or 'Unknown'}",
            f"Blocked Message: {content or '[Unavailable]'}",
        ]),
        1000,
    )
    timestamp_iso = now_iso()
    case_record = None

    if punishment_type == "timeout" and duration_minutes <= 0:
        duration_minutes = 60
    if punishment_type == "ban":
        duration_minutes = -1

    try:
        if punishment_type == "timeout":
            await member.timeout(get_valid_duration(duration_minutes), reason=f"{reason} (By {bot.user})")
        elif punishment_type == "ban":
            await guild.ban(member, reason=f"{reason} (By {bot.user})", delete_message_days=0)
        elif punishment_type == "kick":
            await guild.kick(member, reason=f"{reason} (By {bot.user})")
    except discord.Forbidden:
        return False, "The bot does not have permission to apply the configured escalation.", None
    except Exception as exc:
        return False, f"Failed to apply escalation: {exc}", None

    record = {
        "reason": reason,
        "moderator": bot.user.id,
        "duration_minutes": duration_minutes if punishment_type != "kick" else 0,
        "timestamp": timestamp_iso,
        "escalated": True,
        "note": note,
        "user_msg": user_message_text,
        "target_name": get_user_display_name(member),
        "type": punishment_type if punishment_type in {"warn", "timeout", "ban", "kick"} else "warn",
        "active": punishment_type in {"ban", "timeout"},
    }
    case_record = await bot.data_manager.add_punishment(str(member.id), record, persist=False)
    bot.data_manager.config.setdefault("stats", {})["total_issued"] = bot.data_manager.config.get("stats", {}).get("total_issued", 0) + 1
    bot.data_manager.mark_config_dirty()
    await bot.data_manager.save_all()

    try:
        dm_embed = make_embed(
            "Moderation Action Issued",
            f"> {user_message_text}",
            kind="danger",
            scope=SCOPE_MODERATION,
            guild=guild,
            thumbnail=guild.icon.url if guild.icon else None,
        )
        dm_embed.add_field(name="Reason", value=format_reason_value(reason, limit=1000), inline=False)
        if punishment_type == "timeout" and duration_minutes > 0:
            dm_embed.add_field(name="Duration", value=format_duration(duration_minutes), inline=True)
            expires = discord.utils.format_dt(discord.utils.utcnow() + get_valid_duration(duration_minutes), "R")
            dm_embed.add_field(name="Expires", value=expires, inline=True)
        elif punishment_type == "ban":
            dm_embed.add_field(name="Duration", value="Ban" if duration_minutes == -1 else format_duration(duration_minutes), inline=True)
            if duration_minutes > 0:
                expires = discord.utils.format_dt(discord.utils.utcnow() + get_valid_duration(duration_minutes), "R")
                dm_embed.add_field(name="Expires", value=expires, inline=True)
        appeal_view = AppealView(guild.id, member.id, bot.user.id, duration_minutes if punishment_type != 'kick' else 0, timestamp_iso, reason)
        await member.send(embed=dm_embed, view=appeal_view)
    except Exception:
        pass

    status = punishment_type.title()
    if punishment_type == "warn":
        status = "Warning"
    elif punishment_type == "timeout":
        status = f"Timeout ({format_duration(duration_minutes)})"
    elif punishment_type == "ban":
        status = "Ban"

    return True, f"Applied {status} automatically at {warning_count} warnings in {format_minutes_interval(window_minutes)}.", case_record

async def run_smart_automod(message: discord.Message) -> bool:
    if not message.guild or isinstance(message.channel, discord.Thread):
        return False
    if not get_feature_flag(bot.data_manager.config, "smart_automod", False):
        return False
    if not isinstance(message.author, discord.Member) or message.author.bot:
        return False

    settings = bot.data_manager.config.get("smart_automod", {})
    exempt_channels = {int(cid) for cid in settings.get("exempt_channels", []) if str(cid).isdigit()}
    exempt_roles = {int(rid) for rid in settings.get("exempt_roles", []) if str(rid).isdigit()}

    if message.channel.id in exempt_channels:
        return False
    if any(role.id in exempt_roles for role in message.author.roles):
        return False
    if is_staff_member(message.author):
        return False

    content = (message.content or "").strip()
    if not content:
        return False

    now = time.time()
    window_seconds = max(5, int(settings.get("duplicate_window_seconds", 20)))
    duplicate_threshold = max(2, int(settings.get("duplicate_threshold", 4)))
    tracker = abuse_system.smart_automod_tracker[message.author.id]
    normalized = re.sub(r"\s+", " ", content.lower())
    tracker.append((now, normalized))
    while tracker and now - tracker[0][0] > window_seconds:
        tracker.popleft()

    duplicate_count = sum(1 for _, entry in tracker if entry == normalized)
    alpha_chars = [char for char in content if char.isalpha()]
    max_caps_ratio = float(settings.get("max_caps_ratio", 0.75))
    caps_min_length = max(5, int(settings.get("caps_min_length", 12)))
    caps_ratio = (
        sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)
        if len(alpha_chars) >= caps_min_length
        else 0.0
    )

    blocked_pattern = None
    for pattern in settings.get("blocked_patterns", []):
        try:
            if re.search(pattern, content, re.IGNORECASE):
                blocked_pattern = pattern
                break
        except re.error:
            continue

    trigger_reason = None
    if blocked_pattern:
        trigger_reason = f"Blocked pattern matched: `{blocked_pattern}`"
    elif duplicate_count >= duplicate_threshold:
        trigger_reason = f"Duplicate spam detected ({duplicate_count} matching messages in {window_seconds}s)"
    elif caps_ratio >= max_caps_ratio:
        trigger_reason = f"Excessive caps ratio detected ({round(caps_ratio * 100)}%)"

    if not trigger_reason:
        return False

    try:
        await message.delete()
    except Exception:
        pass

    notice = None
    try:
        notice = await message.channel.send(
            f"{message.author.mention} your message was removed by smart automod.",
            delete_after=10,
        )
    except Exception:
        notice = None

    embed = make_action_log_embed(
        "Smart AutoMod Triggered",
        "A message was removed by the bot's smart filter layer.",
        guild=message.guild,
        kind="warning",
        scope=SCOPE_MODERATION,
        actor=format_user_ref(message.author),
        target=f"{message.channel.mention} (`{message.channel.id}`)",
        reason=trigger_reason,
        duration="Message Removed",
        expires="N/A",
        message=content,
        notes=[
            f"Duplicate Hits: {duplicate_count}",
            f"Caps Ratio: {round(caps_ratio * 100)}%",
            f"Blocked Pattern: {blocked_pattern or 'None'}",
        ],
        thumbnail=message.author.display_avatar.url,
    )
    await send_automod_log(message.guild, embed)
    return True

def ensure_native_rule_override_policy(settings: dict, rule: discord.AutoModRule) -> Tuple[str, dict]:
    override_key, current_policy, _ = get_native_rule_override(settings, rule)
    policy = {
        "enabled": bool(current_policy.get("enabled", False)),
        "reason_template": str(current_policy.get("reason_template", DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"]) or DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"])[:200],
        "steps": get_native_automod_policy_steps(current_policy),
    }
    settings.setdefault("rule_overrides", {})[override_key] = policy
    return override_key, policy

async def resolve_user_for_automod_report(guild: Optional[discord.Guild], user_id: int) -> Optional[Union[discord.Member, discord.User]]:
    if guild is not None:
        member = guild.get_member(user_id)
        if member is not None:
            return member
    cached = bot.get_user(user_id)
    if cached is not None:
        return cached
    try:
        return await bot.fetch_user(user_id)
    except Exception:
        return None

async def apply_automod_report_response(
    interaction: discord.Interaction,
    *,
    guild_id: int,
    reporter_id: int,
    warning_id: str,
    rule_name: str,
    response_key: str,
    response_text: str,
    source_message: Optional[discord.Message],
) -> bool:
    if not has_capability(interaction, "automod.respond"):
        await respond_with_error(interaction, "Access denied.", scope=SCOPE_MODERATION)
        return False

    guild = bot.get_guild(guild_id) or interaction.guild
    if guild is None:
        await respond_with_error(interaction, "The server for this AutoMod report could not be resolved.", scope=SCOPE_MODERATION)
        return False

    if source_message is not None and source_message.embeds:
        for field in source_message.embeds[0].fields:
            if str(field.name).strip().lower() == "report status":
                await respond_with_error(interaction, "This AutoMod report already has a staff response.", scope=SCOPE_MODERATION)
                return False

    target_user = await resolve_user_for_automod_report(guild, reporter_id)
    if target_user is None:
        await respond_with_error(interaction, "The user for this AutoMod report could not be found.", scope=SCOPE_MODERATION)
        return False

    preset = get_automod_report_preset(response_key)
    dm_embed = make_embed(
        "AutoMod Report Update",
        f"> {response_text}",
        kind=preset.get("kind", "info"),
        scope=SCOPE_MODERATION,
        guild=guild,
        thumbnail=guild.icon.url if guild and guild.icon else None,
    )
    dm_embed.add_field(name="Reason", value=format_reason_value(rule_name, limit=300), inline=False)
    dm_embed.add_field(name="Responder", value=format_user_ref(interaction.user), inline=False)

    try:
        await target_user.send(embed=dm_embed)
    except discord.Forbidden:
        await respond_with_error(interaction, "The user has DMs closed, so the response could not be delivered.", scope=SCOPE_MODERATION)
        return False
    except Exception as exc:
        await respond_with_error(interaction, f"Failed to send the AutoMod report response: {exc}", scope=SCOPE_MODERATION)
        return False

    report_message = source_message
    if report_message is None:
        report_channel_id = (
            bot.data_manager.config.get("automod_report_channel_id")
            or bot.data_manager.config.get("appeal_channel_id")
            or get_punishment_log_channel_id()
        )
        report_channel = guild.get_channel_or_thread(int(report_channel_id)) if report_channel_id else None
        if report_channel is not None and interaction.message is not None:
            report_message = interaction.message

    if report_message is not None and report_message.embeds:
        updated_embed = discord.Embed.from_dict(report_message.embeds[0].to_dict())
        updated_embed.color = EMBED_PALETTE.get(preset.get("kind", "info"), EMBED_PALETTE["info"])
        upsert_embed_field(updated_embed, "Report Status", preset.get("status", "Staff Replied"), inline=True)
        upsert_embed_field(updated_embed, "Responder", format_user_ref(interaction.user), inline=True)
        upsert_embed_field(updated_embed, "Responded", discord.utils.format_dt(discord.utils.utcnow(), "F"), inline=True)
        upsert_embed_field(updated_embed, "Staff Response", format_log_quote(response_text, limit=800), inline=False)
        brand_embed(updated_embed, guild=guild, scope=SCOPE_MODERATION)
        try:
            await report_message.edit(embed=updated_embed, view=None)
        except Exception:
            pass
    return True

def claim_native_automod_bridge_event(
    *,
    guild_id: int,
    user_id: int,
    rule_id: int,
    rule_name: str,
    channel_id: Optional[int],
    content: str,
    matched_keyword: Optional[str],
    ttl_seconds: int = 20,
) -> bool:
    now_ts = time.time()
    cache = bot.native_automod_event_cache
    for cache_key, seen_at in list(cache.items()):
        if now_ts - seen_at > ttl_seconds:
            cache.pop(cache_key, None)

    normalized_rule = str(rule_id or 0) if rule_id else str(rule_name or "unknown-rule").strip().lower()
    dedupe_key = (
        int(guild_id or 0),
        int(user_id or 0),
        0,
        str(channel_id or 0),
        truncate_text(matched_keyword or content or normalized_rule, 120).strip().lower(),
    )
    previous = cache.get(dedupe_key)
    if previous and now_ts - previous <= ttl_seconds:
        return False

    cache[dedupe_key] = now_ts
    return True

def claim_native_automod_alert_message(message: discord.Message, *, ttl_seconds: int = 300) -> bool:
    now_ts = time.time()
    cache = bot.native_automod_event_cache
    for cache_key, seen_at in list(cache.items()):
        if now_ts - seen_at > ttl_seconds:
            cache.pop(cache_key, None)

    dedupe_key = (
        int(message.guild.id if message.guild else 0),
        0,
        0,
        f"native-alert-{message.id}",
        "",
    )
    previous = cache.get(dedupe_key)
    if previous and now_ts - previous <= ttl_seconds:
        return False

    cache[dedupe_key] = now_ts
    return True

def clean_native_automod_alert_value(value: Optional[str]) -> str:
    text = str(value or "").replace(">>>", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)

def extract_native_automod_alert_context(message: discord.Message) -> Dict[str, Any]:
    user_id = None
    channel_id = None
    rule_name = None
    content = None
    matched_keyword = None

    if message.mentions:
        for mentioned in message.mentions:
            if not getattr(mentioned, "bot", False):
                user_id = mentioned.id
                break

    for embed in message.embeds:
        if not rule_name and embed.title:
            title_value = clean_native_automod_alert_value(embed.title)
            if title_value:
                rule_name = title_value
        if not content and embed.description:
            description_value = clean_native_automod_alert_value(embed.description)
            if description_value:
                content = description_value
        for field in embed.fields:
            field_name = clean_native_automod_alert_value(field.name).lower()
            field_value = clean_native_automod_alert_value(field.value)
            if not user_id and any(key in field_name for key in ("user", "member", "sender", "author", "who")):
                user_id = extract_snowflake_id(field_value)
            if not channel_id and any(key in field_name for key in ("channel", "where", "location")):
                channel_id = extract_snowflake_id(field_value)
            if not rule_name and any(key in field_name for key in ("rule", "filter")):
                rule_name = field_value
            if not matched_keyword and any(key in field_name for key in ("keyword", "match", "trigger")):
                matched_keyword = field_value
            if not content and any(key in field_name for key in ("content", "message", "what")):
                content = field_value

    return {
        "user_id": user_id,
        "channel_id": channel_id,
        "rule_name": truncate_text(rule_name or "", 250) or None,
        "content": truncate_text(content or "", 500) or None,
        "matched_keyword": truncate_text(matched_keyword or "", 120) or None,
    }

async def find_recent_native_automod_audit_entry(
    guild: discord.Guild,
    *,
    rule_name: Optional[str] = None,
    channel_id: Optional[int] = None,
) -> Optional[discord.AuditLogEntry]:
    cutoff = discord.utils.utcnow() - timedelta(minutes=2)
    actions = {
        discord.AuditLogAction.automod_block_message,
        discord.AuditLogAction.automod_flag_message,
        discord.AuditLogAction.automod_timeout_member,
        discord.AuditLogAction.automod_quarantine_user,
    }
    try:
        async for entry in guild.audit_logs(limit=20):
            if entry.action not in actions:
                continue
            if entry.created_at < cutoff:
                continue
            entry_rule_name = getattr(getattr(entry, "extra", None), "automod_rule_name", None)
            entry_channel = getattr(getattr(entry, "extra", None), "channel", None)
            if rule_name and entry_rule_name and str(entry_rule_name).lower() != str(rule_name).lower():
                continue
            if channel_id and entry_channel and getattr(entry_channel, "id", None) and int(entry_channel.id) != int(channel_id):
                continue
            return entry
    except discord.Forbidden:
        logger.warning("Native AutoMod alert fallback could not read audit logs in guild %s.", guild.id)
    except Exception as exc:
        logger.warning("Failed to read audit logs for native AutoMod alert fallback: %s", exc)
    return None

async def find_matching_native_automod_alert_message(
    guild: discord.Guild,
    *,
    alert_channel_id: Optional[int],
    member_id: int,
    rule_name: str,
    channel_id: Optional[int],
    content: str,
    attempts: int = 3,
    delay_seconds: float = 0.75,
) -> Optional[discord.Message]:
    if not alert_channel_id:
        return None

    channel = guild.get_channel_or_thread(int(alert_channel_id)) or guild.get_channel(int(alert_channel_id))
    if channel is None or not hasattr(channel, "history"):
        return None

    expected_rule = str(rule_name or "").strip().lower()
    expected_content = clean_native_automod_alert_value(content).lower()

    for attempt in range(max(1, attempts)):
        if attempt:
            await asyncio.sleep(delay_seconds)
        try:
            async for candidate in channel.history(limit=15):
                if candidate.author.id == bot.user.id:
                    continue
                if discord.utils.utcnow() - candidate.created_at > timedelta(minutes=3):
                    break

                context = extract_native_automod_alert_context(candidate)
                context_user_id = context.get("user_id")
                context_channel_id = context.get("channel_id")
                context_rule = str(context.get("rule_name") or "").strip().lower()
                context_content = clean_native_automod_alert_value(context.get("content")).lower()

                if context_user_id and int(context_user_id) != int(member_id):
                    continue
                if channel_id and context_channel_id and int(context_channel_id) != int(channel_id):
                    continue
                if expected_rule and context_rule and expected_rule != context_rule:
                    continue
                if expected_content and context_content:
                    if expected_content not in context_content and context_content not in expected_content:
                        continue

                return candidate
        except discord.Forbidden:
            logger.warning("Could not read native AutoMod alert channel %s in guild %s.", alert_channel_id, guild.id)
            return None
        except Exception as exc:
            logger.warning("Failed while searching native AutoMod alert channel %s: %s", alert_channel_id, exc)
            return None

    return None

def get_native_automod_audit_action_label(entry: Optional[discord.AuditLogEntry]) -> str:
    if entry is None:
        return "Send Alert Message"
    mapping = {
        discord.AuditLogAction.automod_block_message: "Block Message",
        discord.AuditLogAction.automod_flag_message: "Send Alert Message",
        discord.AuditLogAction.automod_timeout_member: "Timeout Member",
        discord.AuditLogAction.automod_quarantine_user: "Block Member Interactions",
    }
    return mapping.get(entry.action, "Send Alert Message")

def is_native_automod_audit_blocked(entry: Optional[discord.AuditLogEntry]) -> bool:
    if entry is None:
        return True
    return entry.action in {
        discord.AuditLogAction.automod_block_message,
        discord.AuditLogAction.automod_timeout_member,
        discord.AuditLogAction.automod_quarantine_user,
    }

async def run_native_automod_bridge(
    *,
    guild: discord.Guild,
    member: discord.Member,
    channel_id: Optional[int],
    rule_id: int,
    rule_name: str,
    content: str,
    matched_keyword: Optional[str],
    action_label: str,
    treated_as_blocked: bool,
    preferred_log_channel_id: Optional[int],
    native_log_url: Optional[str],
    source: str,
) -> None:
    settings = get_native_automod_settings(bot.data_manager.config)
    if is_native_automod_exempt(member, channel_id, settings):
        return

    content = content or "[Unavailable due to native AutoMod alert formatting]"
    if not claim_native_automod_bridge_event(
        guild_id=guild.id,
        user_id=member.id,
        rule_id=rule_id,
        rule_name=rule_name,
        channel_id=channel_id,
        content=content,
        matched_keyword=matched_keyword,
    ):
        return

    record_native_automod_event(
        user_id=member.id,
        rule_id=rule_id,
        rule_name=rule_name,
        content=content,
        matched_keyword=matched_keyword,
    )

    policy = resolve_native_automod_policy(bot.data_manager.config, rule_id=rule_id, rule_name=rule_name)
    triggered_step, warning_count = get_triggered_native_automod_step(
        user_id=member.id,
        rule_id=rule_id,
        rule_name=rule_name,
        policy=policy,
    )

    warning_id = f"AM-{rule_id}-{member.id}-{int(time.time())}"
    escalation_applied = False
    escalation_summary = "No automatic punishment was applied."
    escalated_case = None
    if triggered_step is not None:
        escalation_applied, escalation_summary, escalated_case = await apply_native_automod_escalation(
            guild,
            member,
            rule_id=rule_id,
            rule_name=rule_name,
            content=content,
            matched_keyword=matched_keyword,
            warning_count=warning_count,
            policy=policy,
            step=triggered_step,
        )
        if escalation_applied:
            record_native_automod_step_application(
                user_id=member.id,
                rule_id=rule_id,
                rule_name=rule_name,
                step=triggered_step,
            )
    await bot.data_manager.save_mod_stats()

    action_word = "blocked" if treated_as_blocked else "flagged"
    if settings.get("warning_dm_enabled", True) and not escalation_applied:
        try:
            dm_embed = make_embed(
                "AutoMod Warning",
                "\n".join([
                    f"> Your message in **{guild.name}** was {action_word} by Discord AutoMod.",
                    "> Repeating this rule can lead to a proper punishment.",
                ]),
                kind="warning" if not escalation_applied else "danger",
                scope=SCOPE_MODERATION,
                guild=guild,
                thumbnail=guild.icon.url if guild.icon else None,
            )
            dm_embed.add_field(name="Reason", value=format_reason_value(rule_name, limit=250), inline=False)
            dm_embed.add_field(
                name="Blocked Message" if treated_as_blocked else "Flagged Message",
                value=format_log_quote(content, limit=400),
                inline=False,
            )
            view = None
            if settings.get("report_button_enabled", True):
                view = AutoModWarningView(
                    guild_id=guild.id,
                    warning_id=warning_id,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    content=content,
                    matched_keyword=matched_keyword,
                )
            await member.send(embed=dm_embed, view=view)
        except discord.Forbidden:
            logger.info("Native AutoMod bridge could not DM user %s for rule %s.", member.id, rule_id)
        except Exception as exc:
            logger.warning("Failed to send native AutoMod warning DM to %s: %s", member.id, exc)

    target_channel = guild.get_channel_or_thread(channel_id) if channel_id else None
    target_label = f"<#{channel_id}>" if channel_id else "Unknown Channel"
    if isinstance(target_channel, discord.Thread):
        target_label = f"{target_channel.mention} (`{target_channel.id}`)"
    elif hasattr(target_channel, "mention"):
        target_label = f"{target_channel.mention} (`{target_channel.id}`)"

    if not native_log_url and preferred_log_channel_id:
        native_alert_message = await find_matching_native_automod_alert_message(
            guild,
            alert_channel_id=preferred_log_channel_id,
            member_id=member.id,
            rule_name=rule_name,
            channel_id=channel_id,
            content=content,
        )
        if native_alert_message is not None:
            native_log_url = native_alert_message.jump_url

    if escalation_applied and escalated_case:
        detail_embed = build_punishment_execution_log_embed(
            guild=guild,
            case_label=get_case_label(escalated_case),
            actor=format_user_ref(bot.user),
            target=format_user_ref(member),
            record=escalated_case,
            thumbnail=member.display_avatar.url,
            native_log_url=native_log_url,
        )
    else:
        detail_embed = make_action_log_embed(
            "AutoMod Warning",
            "Discord AutoMod blocked or flagged a message and the bot sent a warning.",
            guild=guild,
            kind="warning",
            scope=SCOPE_MODERATION,
            actor=format_user_ref(member),
            target=target_label,
            reason=rule_name,
            message=content,
            notes=[
                f"Action: {action_label}",
                f"Matched Keyword: {matched_keyword or 'Unknown'}",
            ],
            thumbnail=member.display_avatar.url,
        )
        detail_embed.color = discord.Color.from_rgb(255, 153, 0)
        if native_log_url:
            detail_embed.add_field(name="Discord AutoMod Log", value=f"[Open Native Log]({native_log_url})", inline=False)

    selected_log_channel_id = None
    native_alert_channel_id = int(preferred_log_channel_id or 0) if preferred_log_channel_id else None

    log_candidates: List[int] = []
    preferred_candidates = (
        get_punishment_log_channel_ids()
        if escalation_applied
        else [
            bot.data_manager.config.get("automod_log_channel_id"),
            *get_punishment_log_channel_ids(),
        ]
    )
    for raw_channel_id in preferred_candidates:
        if not raw_channel_id:
            continue
        try:
            candidate_id = int(raw_channel_id)
        except (TypeError, ValueError):
            continue
        if candidate_id not in log_candidates:
            log_candidates.append(candidate_id)

    for candidate_id in log_candidates:
        if native_alert_channel_id and candidate_id == native_alert_channel_id:
            continue
        selected_log_channel_id = candidate_id
        break

    if selected_log_channel_id:
        log_channel = guild.get_channel_or_thread(selected_log_channel_id) or guild.get_channel(selected_log_channel_id)
        if log_channel is not None:
            try:
                await log_channel.send(embed=detail_embed)
            except Exception as exc:
                logger.warning("Failed to send native AutoMod moderation log to channel %s: %s", selected_log_channel_id, exc)
    logger.info(
        "Native AutoMod bridge processed event: guild=%s user=%s rule=%s action=%s source=%s",
        guild.id,
        member.id,
        rule_id,
        action_label,
        source,
    )

async def handle_native_automod_execution(execution: discord.AutoModAction, *, source: str) -> None:
    if not getattr(bot, "data_manager", None):
        return
    if not get_feature_flag(bot.data_manager.config, "native_automod_bridge", True):
        return

    settings = get_native_automod_settings(bot.data_manager.config)
    if not settings.get("enabled", True):
        return

    tracked_actions = {
        discord.AutoModRuleActionType.block_message,
        discord.AutoModRuleActionType.send_alert_message,
        discord.AutoModRuleActionType.timeout,
        discord.AutoModRuleActionType.block_member_interactions,
    }
    if execution.action.type not in tracked_actions:
        return
    if not claim_native_automod_execution(execution):
        return

    guild = bot.get_guild(execution.guild_id) or execution.guild
    if guild is None:
        return

    member = execution.member or await resolve_member(guild, execution.user_id)
    if member is None or member.bot:
        logger.warning(
            "Skipped native AutoMod bridge event without a resolvable member: guild=%s user=%s rule=%s source=%s",
            execution.guild_id,
            execution.user_id,
            execution.rule_id,
            source,
        )
        return

    rule = None
    try:
        rule = await execution.fetch_rule()
    except discord.Forbidden:
        logger.warning(
            "Native AutoMod bridge could not fetch rule %s in guild %s. Grant Manage Guild to allow detailed rule lookups.",
            execution.rule_id,
            execution.guild_id,
        )
    except Exception as exc:
        logger.warning("Failed to fetch native AutoMod rule %s: %s", execution.rule_id, exc)

    rule_name = rule.name if rule else f"Rule {execution.rule_id}"
    action_label = get_native_automod_action_label(execution)
    treated_as_blocked = native_automod_rule_has_enforcement(rule, execution)
    content = execution.content or execution.matched_content or "[Unavailable due to content intent settings]"
    matched_keyword = execution.matched_keyword or execution.matched_content or None
    native_alert_channel_id = None
    if rule is not None:
        for action in getattr(rule, "actions", []):
            if getattr(action, "type", None) == discord.AutoModRuleActionType.send_alert_message and getattr(action, "channel_id", None):
                native_alert_channel_id = int(action.channel_id)
                break

    await run_native_automod_bridge(
        guild=guild,
        member=member,
        channel_id=execution.channel_id,
        rule_id=int(execution.rule_id),
        rule_name=rule_name,
        content=content,
        matched_keyword=matched_keyword,
        action_label=action_label,
        treated_as_blocked=treated_as_blocked,
        preferred_log_channel_id=native_alert_channel_id,
        native_log_url=None,
        source=source,
    )

async def handle_native_automod_alert_message(message: discord.Message) -> None:
    if not message.guild:
        return
    if not getattr(bot, "data_manager", None):
        return
    if not get_feature_flag(bot.data_manager.config, "native_automod_bridge", True):
        return

    settings = get_native_automod_settings(bot.data_manager.config)
    if not settings.get("enabled", True):
        return
    if not claim_native_automod_alert_message(message):
        return

    context = extract_native_automod_alert_context(message)
    audit_entry = await find_recent_native_automod_audit_entry(
        message.guild,
        rule_name=context.get("rule_name"),
        channel_id=context.get("channel_id"),
    )

    user_id = context.get("user_id")
    audit_user = getattr(audit_entry, "user", None)
    if not user_id and audit_user and not getattr(audit_user, "bot", False):
        user_id = audit_user.id

    member = await resolve_member(message.guild, int(user_id)) if user_id else None
    if member is None or member.bot:
        logger.warning(
            "Native AutoMod alert fallback could not resolve the affected member. message_id=%s channel=%s",
            message.id,
            message.channel.id,
        )
        return

    rule_name = context.get("rule_name") or getattr(getattr(audit_entry, "extra", None), "automod_rule_name", None) or "Native AutoMod Rule"
    rule_target = getattr(audit_entry, "target", None)
    rule_id = int(getattr(rule_target, "id", 0) or 0)
    action_label = get_native_automod_audit_action_label(audit_entry)
    treated_as_blocked = is_native_automod_audit_blocked(audit_entry)
    content = context.get("content") or "[Unavailable from Discord native AutoMod alert]"
    matched_keyword = context.get("matched_keyword")
    action_channel = getattr(getattr(audit_entry, "extra", None), "channel", None)
    channel_id = context.get("channel_id") or getattr(action_channel, "id", None)

    await run_native_automod_bridge(
        guild=message.guild,
        member=member,
        channel_id=channel_id,
        rule_id=rule_id,
        rule_name=rule_name,
        content=content,
        matched_keyword=matched_keyword,
        action_label=action_label,
        treated_as_blocked=treated_as_blocked,
        preferred_log_channel_id=message.channel.id,
        native_log_url=message.jump_url,
        source="native alert message",
    )


__all__ = [
    "AUTOMOD_PUNISHMENT_OPTIONS",
    "AUTOMOD_THRESHOLD_PRESETS",
    "AUTOMOD_WINDOW_PRESETS",
    "AUTOMOD_TIMEOUT_PRESETS",
    "SMART_DUPLICATE_THRESHOLD_PRESETS",
    "SMART_DUPLICATE_WINDOW_PRESETS",
    "SMART_CAPS_PERCENT_PRESETS",
    "SMART_CAPS_LENGTH_PRESETS",
    "AUTOMOD_REPORT_RESPONSE_PRESETS",
    "SMART_AUTOMOD_DEFAULTS",
    "calculate_smart_punishment",
    "build_automod_dashboard_embed",
    "format_minutes_interval",
    "format_seconds_interval",
    "format_compact_minutes_input",
    "parse_positive_integer_input",
    "parse_minutes_input",
    "parse_automod_punishment_input",
    "build_numeric_select_options",
    "get_smart_automod_settings",
    "store_native_automod_settings",
    "store_smart_automod_settings",
    "format_automod_punishment_label",
    "get_automod_report_preset",
    "build_default_native_automod_policy",
    "get_native_automod_policy_steps",
    "build_default_native_automod_step",
    "format_native_automod_step_summary",
    "get_native_rule_override",
    "render_id_mentions",
    "build_automod_bridge_embed",
    "build_automod_policy_embed",
    "build_automod_immunity_embed",
    "build_automod_routing_embed",
    "build_smart_automod_embed",
    "build_automod_rule_browser_embed",
    "describe_automod_rule_trigger",
    "describe_automod_rule_actions",
    "serialize_automod_rule",
    "build_automod_trigger_from_payload",
    "build_automod_actions_from_payload",
    "fetch_native_automod_rules",
    "build_native_automod_rules_embed",
    "build_native_automod_rule_detail_embed",
    "handle_abuse",
    "punish_rogue_mod",
    "get_native_automod_stats_bucket",
    "prune_native_automod_bucket",
    "record_native_automod_event",
    "count_recent_native_automod_hits",
    "has_recent_native_automod_step_application",
    "record_native_automod_step_application",
    "get_triggered_native_automod_step",
    "build_native_automod_dedupe_key",
    "claim_native_automod_execution",
    "get_native_automod_action_label",
    "native_automod_rule_has_enforcement",
    "is_native_automod_exempt",
    "apply_native_automod_escalation",
    "run_smart_automod",
    "ensure_native_rule_override_policy",
    "resolve_user_for_automod_report",
    "apply_automod_report_response",
    "claim_native_automod_bridge_event",
    "claim_native_automod_alert_message",
    "clean_native_automod_alert_value",
    "extract_native_automod_alert_context",
    "find_recent_native_automod_audit_entry",
    "find_matching_native_automod_alert_message",
    "get_native_automod_audit_action_label",
    "is_native_automod_audit_blocked",
    "run_native_automod_bridge",
    "handle_native_automod_execution",
    "handle_native_automod_alert_message",
]
