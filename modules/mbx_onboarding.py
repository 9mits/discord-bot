"""State and validation helpers for the /start onboarding wizard."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import discord

from modules.mbx_permission_engine import CAPABILITIES, default_permission_payload
from modules.mbx_templates import apply_template, get_template


WIZARD_TIMEOUT = timedelta(minutes=15)


@dataclass(frozen=True)
class WizardStep:
    key: str
    title: str
    summary: str
    required: bool = True


WIZARD_STEPS: Tuple[WizardStep, ...] = (
    WizardStep("welcome", "Welcome", "Pick a setup template."),
    WizardStep("channels", "Channels", "Choose log, support, appeal, and archive destinations."),
    WizardStep("logs", "Logs", "Review routing for moderation and AutoMod events.", required=False),
    WizardStep("modmail", "Modmail", "Set ticket SLA, cooldown, thread, and DM prompt behavior.", required=False),
    WizardStep("branding", "Branding", "Optionally set server-specific bot presentation.", required=False),
    WizardStep("permissions", "Permission Groups", "Map Discord roles and permission bundles to capabilities."),
    WizardStep("moderation", "Moderation Defaults", "Review escalation defaults from the selected template."),
    WizardStep("features", "Features", "Choose which feature flags are enabled."),
    WizardStep("panels", "Control Panels", "Choose which setup panels need explicit capabilities.", required=False),
    WizardStep("review", "Review", "Review every staged choice before applying."),
    WizardStep("done", "Done", "Setup is complete.", required=False),
)


CHANNEL_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("general_log_channel_id", "General Log"),
    ("punishment_log_channel_id", "Punishment Log"),
    ("modmail_inbox_channel", "Modmail Inbox"),
    ("modmail_panel_channel", "Modmail Panel"),
    ("appeal_channel_id", "Appeals"),
    ("category_archive", "Archive Category"),
)

LOG_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("general_log_channel_id", "General Log"),
    ("punishment_log_channel_id", "Punishment Log"),
    ("automod_log_channel_id", "AutoMod Log"),
    ("automod_report_channel_id", "AutoMod Reports"),
)

PANEL_CAPABILITIES: Dict[str, str] = {
    "roles": "config.edit",
    "channels": "config.edit",
    "features": "config.edit",
    "modmail": "modmail.settings",
    "rules": "rules.edit",
    "escalation": "escalation.edit",
    "branding": "branding.edit",
    "permissions": "permissions.edit",
    "automod": "automod.configure",
}


@dataclass
class WizardSession:
    guild_id: int
    user_id: int
    started_at: datetime
    step_index: int = 0
    template_id: Optional[str] = None
    staging_config: Dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    last_active_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def step(self) -> WizardStep:
        return WIZARD_STEPS[max(0, min(self.step_index, len(WIZARD_STEPS) - 1))]

    @property
    def key(self) -> Tuple[int, int]:
        return (self.guild_id, self.user_id)

    def touch(self) -> None:
        self.last_active_at = datetime.now(timezone.utc)

    def expired(self, *, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now - self.last_active_at > WIZARD_TIMEOUT

    def to_draft(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "step_index": self.step_index,
            "template_id": self.template_id,
            "staging_config": copy.deepcopy(self.staging_config),
            "completed": self.completed,
        }

    @classmethod
    def from_draft(cls, guild_id: int, user_id: int, payload: Mapping[str, Any]) -> "WizardSession":
        started_raw = str(payload.get("started_at") or "")
        active_raw = str(payload.get("last_active_at") or "")
        now = datetime.now(timezone.utc)
        try:
            started_at = datetime.fromisoformat(started_raw)
        except ValueError:
            started_at = now
        try:
            last_active_at = datetime.fromisoformat(active_raw)
        except ValueError:
            last_active_at = now
        staging = payload.get("staging_config")
        return cls(
            guild_id=guild_id,
            user_id=user_id,
            started_at=started_at,
            last_active_at=last_active_at,
            step_index=int(payload.get("step_index") or 0),
            template_id=_str_or_none(payload.get("template_id")),
            staging_config=copy.deepcopy(staging) if isinstance(staging, dict) else {},
            completed=bool(payload.get("completed", False)),
        )


def create_session(guild_id: int, user_id: int, config: Optional[Mapping[str, Any]] = None) -> WizardSession:
    draft = (config or {}).get("_onboarding_draft") if isinstance(config, Mapping) else None
    if isinstance(draft, Mapping):
        session = WizardSession.from_draft(guild_id, user_id, draft)
        if not session.completed and not session.expired():
            return session
    return WizardSession(guild_id=guild_id, user_id=user_id, started_at=datetime.now(timezone.utc))


def persist_draft(config: Dict[str, Any], session: WizardSession) -> None:
    session.touch()
    config["_onboarding_draft"] = session.to_draft()


def set_template(session: WizardSession, template_id: str) -> None:
    if get_template(template_id) is None:
        raise ValueError(f"Unknown template: {template_id}")
    session.template_id = template_id
    apply_template(session.staging_config, template_id)
    _ensure_permissions(session.staging_config)


def set_channel(session: WizardSession, key: str, channel_id: int) -> None:
    allowed = {field for field, _ in CHANNEL_FIELDS} | {"automod_log_channel_id", "automod_report_channel_id"}
    if key not in allowed:
        raise ValueError(f"Unsupported channel field: {key}")
    session.staging_config[key] = int(channel_id)
    if key == "general_log_channel_id":
        session.staging_config["log_channel_id"] = int(channel_id)


def set_modmail_options(
    session: WizardSession,
    *,
    sla_minutes: int,
    dm_prompt_cooldown_minutes: int,
    discussion_threads: bool,
    dm_prompt: bool,
) -> None:
    session.staging_config["modmail_sla_minutes"] = max(1, int(sla_minutes))
    session.staging_config["dm_modmail_panel_cooldown_minutes"] = max(1, int(dm_prompt_cooldown_minutes))
    session.staging_config["modmail_discussion_threads"] = bool(discussion_threads)
    flags = session.staging_config.setdefault("feature_flags", {})
    flags["dm_modmail_prompt"] = bool(dm_prompt)


def set_branding_options(
    session: WizardSession,
    *,
    display_name: Optional[str] = None,
    color: Optional[str] = None,
    avatar_url: Optional[str] = None,
    banner_url: Optional[str] = None,
) -> None:
    branding = session.staging_config.setdefault("_branding", {})
    for key, value in {
        "display_name": display_name,
        "embed_color": color,
        "avatar_url": avatar_url,
        "modmail_banner_url": banner_url,
    }.items():
        text = str(value or "").strip()
        if text:
            branding[key] = text


def set_feature_flags(session: WizardSession, enabled_keys: Iterable[str]) -> None:
    existing = session.staging_config.setdefault("feature_flags", {})
    all_keys = set(existing) | set(enabled_keys)
    for key in all_keys:
        existing[key] = key in set(enabled_keys)


def set_permissions_payload(session: WizardSession, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError("Permission payload must be a JSON object.")
    session.staging_config["permissions"] = copy.deepcopy(dict(payload))
    _ensure_permissions(session.staging_config)


def map_role_to_capabilities(session: WizardSession, role_id: int, capabilities: Iterable[str]) -> None:
    permissions = _ensure_permissions(session.staging_config)
    caps = [cap for cap in capabilities if cap in CAPABILITIES]
    permissions.setdefault("role_capabilities", {})[str(int(role_id))] = caps


def set_roles_use_open_access(session: WizardSession, *, open_access: bool) -> None:
    permissions = _ensure_permissions(session.staging_config)
    everyone_key = str(session.guild_id)
    role_caps = permissions.setdefault("role_capabilities", {})
    caps = set(role_caps.get(everyone_key) or [])
    if open_access:
        caps.add("roles.use")
    else:
        caps.discard("roles.use")
    if caps:
        role_caps[everyone_key] = sorted(caps)
    else:
        role_caps.pop(everyone_key, None)


def set_panel_overrides(session: WizardSession, panel_caps: Mapping[str, str]) -> None:
    permissions = _ensure_permissions(session.staging_config)
    overrides = permissions.setdefault("panel_overrides", {})
    for panel, capability in panel_caps.items():
        if capability in CAPABILITIES:
            overrides[str(panel)] = {"required_capability": capability}


def validate_step(session: WizardSession, *, guild: Optional[discord.Guild] = None) -> List[str]:
    key = session.step.key
    errors: List[str] = []
    if key == "welcome" and not session.template_id:
        errors.append("Choose a setup template before continuing.")
    if key == "channels":
        for field, label in CHANNEL_FIELDS:
            channel_id = session.staging_config.get(field)
            if not channel_id:
                errors.append(f"{label} is not selected.")
                continue
            if guild is not None and guild.get_channel(int(channel_id)) is None:
                errors.append(f"{label} could not be found in this server.")
    if key == "permissions":
        permissions = session.staging_config.get("permissions")
        if not isinstance(permissions, Mapping):
            errors.append("Permission settings are missing.")
    return errors


def advance(session: WizardSession, *, guild: Optional[discord.Guild] = None) -> List[str]:
    errors = validate_step(session, guild=guild)
    if errors:
        return errors
    session.step_index = min(session.step_index + 1, len(WIZARD_STEPS) - 1)
    session.touch()
    return []


def back(session: WizardSession) -> None:
    session.step_index = max(0, session.step_index - 1)
    session.touch()


def finalize_session(config: Dict[str, Any], session: WizardSession) -> Dict[str, Any]:
    _deep_merge_preserving_branding(config, session.staging_config)
    config["_setup_complete"] = True
    config.pop("_onboarding_draft", None)
    session.completed = True
    session.step_index = len(WIZARD_STEPS) - 1
    session.touch()
    return config


def build_review_lines(session: WizardSession) -> List[str]:
    cfg = session.staging_config
    lines = [f"Template: `{session.template_id or 'not selected'}`"]
    for key, label in CHANNEL_FIELDS:
        value = cfg.get(key)
        lines.append(f"{label}: {f'<#{value}>' if value else '`Not set`'}")
    flags = cfg.get("feature_flags") or {}
    if isinstance(flags, Mapping):
        enabled = sorted(k for k, v in flags.items() if v)
        lines.append(f"Features: {', '.join(enabled) if enabled else '`None`'}")
    permissions = cfg.get("permissions") or {}
    if isinstance(permissions, Mapping):
        role_count = len(permissions.get("role_capabilities") or {})
        group_count = len(permissions.get("groups") or {})
        panel_count = len(permissions.get("panel_overrides") or {})
        lines.append(f"Permissions: {role_count} role map(s), {group_count} group(s), {panel_count} panel override(s)")
    return lines


def _ensure_permissions(config: Dict[str, Any]) -> Dict[str, Any]:
    permissions = config.get("permissions")
    if not isinstance(permissions, dict):
        permissions = default_permission_payload()
        config["permissions"] = permissions
    permissions.setdefault("schema", 1)
    permissions.setdefault("role_capabilities", {})
    permissions.setdefault("user_capabilities", {})
    permissions.setdefault("discord_permission_capabilities", {})
    permissions.setdefault("groups", {})
    permissions.setdefault("command_overrides", {})
    permissions.setdefault("feature_overrides", {})
    permissions.setdefault("panel_overrides", {})
    return permissions


def _deep_merge_preserving_branding(target: Dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if key == "_branding":
            branding = target.setdefault("_branding", {})
            if isinstance(branding, dict) and isinstance(value, Mapping):
                for b_key, b_value in value.items():
                    if b_value not in (None, ""):
                        branding[b_key] = copy.deepcopy(b_value)
            continue
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge_preserving_branding(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _str_or_none(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "CHANNEL_FIELDS",
    "LOG_FIELDS",
    "PANEL_CAPABILITIES",
    "WIZARD_STEPS",
    "WIZARD_TIMEOUT",
    "WizardSession",
    "WizardStep",
    "advance",
    "back",
    "build_review_lines",
    "create_session",
    "finalize_session",
    "map_role_to_capabilities",
    "persist_draft",
    "set_branding_options",
    "set_channel",
    "set_feature_flags",
    "set_modmail_options",
    "set_panel_overrides",
    "set_permissions_payload",
    "set_roles_use_open_access",
    "set_template",
    "validate_step",
]
