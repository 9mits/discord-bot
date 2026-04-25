"""Per-guild capability-based permission engine.

This replaces the hardcoded "mod commands" / "admin commands" bucket model
with a real configurable system: capabilities, custom permission groups,
role/user/Discord-perm mappings, and per-command/feature/panel overrides.

Storage shape, kept inside each guild's config under the ``permissions`` key:

    {
        "schema":  1,
        "guild_owner_override":  True,         # guild owner always passes
        "discord_admin_override": True,        # users with `administrator` always pass

        # Capability granted to the holders of a Discord role.
        "role_capabilities":   {"<role_id>":  ["mod.case_panel", ...]},

        # Capability granted to a single user (bypasses roles).
        "user_capabilities":   {"<user_id>":  ["..."]},

        # Capability granted to anyone holding a Discord permission flag.
        "discord_permission_capabilities": {
            "moderate_members": ["mod.case_panel", "mod.history"],
            "manage_guild":     ["setup.run", "config.edit"],
        },

        # Custom permission groups — admins can author these in the UI.
        "groups": {
            "<group_id>": {
                "name": "Senior Mods",
                "members": {"roles": [<rid>], "users": [<uid>]},
                "capabilities": ["..."],
            },
        },

        # Per-command / feature / panel overrides. Each entry can:
        #   - require an extra capability,
        #   - allow specific role/user IDs,
        #   - deny specific role/user IDs (deny always wins).
        "command_overrides": {"mod punish": {...}},
        "feature_overrides": {"branding": {...}},
        "panel_overrides":   {"setup_panel": {...}},
    }

Resolution precedence for a single ``allowed(user, capability)`` check
(highest to lowest):

    1. explicit deny (user_id or any role_id)
    2. guild owner override
    3. discord administrator override
    4. user_capabilities entry
    5. group capabilities (where the user is a member)
    6. role_capabilities (any of the user's roles)
    7. discord_permission_capabilities (any matching Discord perm flag)
    8. legacy fallback (PERMISSIONS_MATRIX + legacy role keys, for guilds that
       never ran ``/start`` and still have the old shape)

The legacy fallback exists so guilds that haven't been onboarded to the new
permission system keep working without any user-visible change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import discord


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------
# Capabilities are namespaced by area. Keep the list explicit so the UI can
# enumerate them. Adding a capability requires gating *somewhere* in code.
#
# Format: <area>.<action>.

CAPABILITIES: Dict[str, str] = {
    # Moderation
    "mod.case_panel":      "Open and edit the case panel",
    "mod.history":         "View user moderation history",
    "mod.punish":           "Issue warnings, timeouts, and bans",
    "mod.public_punish":   "Issue punishments publicly in-channel",
    "mod.undo":            "Reverse punishments",
    "mod.purge":           "Bulk delete messages",
    "mod.lock":            "Lock and unlock channels",
    "mod.active":          "View the active-punishments list",
    "mod.appeals":         "Review and act on appeals",

    # Modmail
    "modmail.reply":       "Reply to modmail threads",
    "modmail.claim":       "Claim and assign modmail tickets",
    "modmail.close":       "Close modmail tickets",
    "modmail.canned":      "Manage canned replies",
    "modmail.settings":    "Edit modmail settings (SLA, channels, prompts)",

    # AutoMod
    "automod.view":        "View the automod dashboard",
    "automod.configure":   "Edit automod policy and immunity",
    "automod.respond":     "Respond to automod reports",

    # Roles
    "roles.use":           "Use the custom-role panel for self",
    "roles.admin":         "Manage other users' custom roles",
    "roles.settings":      "Edit role settings (limits, eligibility)",

    # Setup / config
    "setup.run":           "Run /start and apply templates",
    "setup.validate":      "Run setup validation checks",
    "config.edit":         "Edit non-onboarding configuration",
    "config.export":       "Export configuration",
    "config.import":       "Import configuration",
    "branding.edit":       "Edit per-server bot branding",
    "permissions.edit":    "Edit the permission system itself",
    "rules.edit":          "Edit punishment rule presets",
    "escalation.edit":     "Edit the punishment escalation matrix",

    # System / safety / analytics
    "system.lockdown":     "Activate and lift server lockdowns",
    "system.archive":      "Archive, unarchive, and clone channels",
    "system.safety":       "Manage anti-nuke immunity list",
    "system.status":       "View bot status",
    "system.stats":        "View moderation analytics",
    "system.directory":    "View staff directory",
    "system.internals":    "View read-only system internals",
}

# Aliases used by old code. Resolution maps these to the new capability names so
# call sites can be migrated incrementally.
CAPABILITY_ALIASES: Dict[str, str] = {
    "case_panel":   "mod.case_panel",
    "modmail_panel": "modmail.reply",
    "setup_panel":  "setup.run",
    "config_panel": "config.edit",
    "owner_panel":  "permissions.edit",
}


def normalize_capability(capability: str) -> str:
    return CAPABILITY_ALIASES.get(capability, capability)


# ---------------------------------------------------------------------------
# Discord permission flags that can be wired to capabilities.
# ---------------------------------------------------------------------------

DISCORD_PERMISSION_FLAGS: Tuple[str, ...] = (
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_messages",
    "moderate_members",
    "ban_members",
    "kick_members",
    "manage_webhooks",
    "manage_threads",
    "view_audit_log",
)


# ---------------------------------------------------------------------------
# Default permission payload for a fresh guild.
# ---------------------------------------------------------------------------
# This is intentionally conservative: the Discord-permission mapping is the
# only thing populated, so a guild owner can /start and grant capabilities
# via the wizard rather than landing in a half-locked-down state.

def default_permission_payload() -> Dict[str, Any]:
    return {
        "schema": 1,
        "guild_owner_override":   True,
        "discord_admin_override": True,
        "role_capabilities":   {},
        "user_capabilities":   {},
        "discord_permission_capabilities": {
            "manage_guild": [
                "setup.run", "setup.validate", "config.edit", "config.export",
                "config.import", "branding.edit", "permissions.edit",
                "rules.edit", "escalation.edit", "system.archive",
                "system.lockdown", "system.safety", "system.directory",
                "system.stats", "system.internals", "modmail.settings",
                "automod.configure", "roles.settings",
            ],
            "moderate_members": [
                "mod.case_panel", "mod.history", "mod.punish",
                "mod.public_punish", "mod.undo", "mod.active",
                "mod.appeals", "modmail.reply", "modmail.claim",
                "modmail.close", "modmail.canned", "automod.view",
                "automod.respond", "system.status",
            ],
            "manage_messages": ["mod.purge"],
            "manage_channels": ["mod.lock"],
            "manage_roles":    ["roles.admin"],
        },
        "groups": {},
        "command_overrides": {},
        "feature_overrides": {},
        "panel_overrides":   {},
    }


# ---------------------------------------------------------------------------
# Override descriptor used by command/feature/panel rules.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Override:
    required_capability: Optional[str] = None
    allow_roles:  FrozenSet[int] = field(default_factory=frozenset)
    allow_users:  FrozenSet[int] = field(default_factory=frozenset)
    deny_roles:   FrozenSet[int] = field(default_factory=frozenset)
    deny_users:   FrozenSet[int] = field(default_factory=frozenset)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Override":
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            required_capability=_str_or_none(payload.get("required_capability")),
            allow_roles=_id_set(payload.get("allow_roles")),
            allow_users=_id_set(payload.get("allow_users")),
            deny_roles=_id_set(payload.get("deny_roles")),
            deny_users=_id_set(payload.get("deny_users")),
        )


def _id_set(value: Any) -> FrozenSet[int]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    out: Set[int] = set()
    for item in value:
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return frozenset(out)


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class PermissionEngine:
    """Resolve capability + override checks against a guild's permission payload.

    Construct one per check — the object is cheap, holds no I/O state, and
    reading from the config dict is just a dictionary lookup.
    """
    payload: Mapping[str, Any]
    legacy_config: Mapping[str, Any]

    @classmethod
    def for_guild(cls, config: Mapping[str, Any]) -> "PermissionEngine":
        payload = config.get("permissions") if isinstance(config, Mapping) else None
        if not isinstance(payload, Mapping):
            payload = {}
        return cls(payload=payload, legacy_config=config or {})

    # -- public --------------------------------------------------------------

    def has_capability(
        self,
        capability: str,
        *,
        user_id: Optional[int],
        role_ids: Sequence[int],
        guild_owner_id: Optional[int],
        discord_permissions: Optional[discord.Permissions] = None,
    ) -> bool:
        cap = normalize_capability(capability)
        role_ids_set = _id_set(role_ids)

        if self._guild_owner_override() and user_id is not None and user_id == guild_owner_id:
            return True

        if self._discord_admin_override() and discord_permissions and discord_permissions.administrator:
            return True

        # Direct user grant
        if cap in self._user_capabilities(user_id):
            return True

        # Group membership
        for group in self._groups_for(user_id, role_ids_set):
            if cap in _as_str_set(group.get("capabilities")):
                return True

        # Role grants
        for rid in role_ids_set:
            if cap in self._role_capabilities(rid):
                return True

        # Discord permission mapping
        if discord_permissions is not None:
            for flag, caps in self._discord_perm_caps().items():
                if not getattr(discord_permissions, flag, False):
                    continue
                if cap in caps:
                    return True

        # Legacy fallback for guilds that never ran the new wizard.
        if not self.payload:
            return _legacy_has_capability(
                cap,
                role_ids=role_ids_set,
                user_id=user_id,
                guild_owner_id=guild_owner_id,
                config=self.legacy_config,
                administrator=bool(discord_permissions and discord_permissions.administrator),
            )

        return False

    def check_override(
        self,
        kind: str,
        key: str,
        *,
        user_id: Optional[int],
        role_ids: Sequence[int],
        guild_owner_id: Optional[int],
        discord_permissions: Optional[discord.Permissions] = None,
    ) -> Optional[bool]:
        """Apply a per-command / feature / panel override.

        Returns:
            ``True``  — explicitly allowed (override grants access),
            ``False`` — explicitly denied (deny rule matched),
            ``None``  — no override applies, fall through to capability check.
        """
        bucket = self._overrides_for(kind).get(key)
        if not isinstance(bucket, Mapping):
            return None
        override = Override.from_payload(bucket)

        role_ids_set = _id_set(role_ids)

        if user_id is not None and user_id in override.deny_users:
            return False
        if role_ids_set & override.deny_roles:
            return False

        if user_id is not None and user_id in override.allow_users:
            return True
        if role_ids_set & override.allow_roles:
            return True

        if override.required_capability:
            return self.has_capability(
                override.required_capability,
                user_id=user_id,
                role_ids=role_ids_set,
                guild_owner_id=guild_owner_id,
                discord_permissions=discord_permissions,
            )

        return None

    # -- internal lookups ----------------------------------------------------

    def _guild_owner_override(self) -> bool:
        return bool(self.payload.get("guild_owner_override", True)) if self.payload else True

    def _discord_admin_override(self) -> bool:
        return bool(self.payload.get("discord_admin_override", True)) if self.payload else True

    def _user_capabilities(self, user_id: Optional[int]) -> Set[str]:
        if user_id is None:
            return set()
        table = self.payload.get("user_capabilities") or {}
        return _as_str_set(table.get(str(user_id)) or table.get(user_id))

    def _role_capabilities(self, role_id: int) -> Set[str]:
        table = self.payload.get("role_capabilities") or {}
        return _as_str_set(table.get(str(role_id)) or table.get(role_id))

    def _discord_perm_caps(self) -> Dict[str, Set[str]]:
        table = self.payload.get("discord_permission_capabilities") or {}
        if not isinstance(table, Mapping):
            return {}
        return {str(k): _as_str_set(v) for k, v in table.items()}

    def _groups_for(self, user_id: Optional[int], role_ids: FrozenSet[int]) -> List[Mapping[str, Any]]:
        groups = self.payload.get("groups") or {}
        if not isinstance(groups, Mapping):
            return []
        out: List[Mapping[str, Any]] = []
        for group in groups.values():
            if not isinstance(group, Mapping):
                continue
            members = group.get("members") or {}
            if not isinstance(members, Mapping):
                continue
            member_role_ids = _id_set(members.get("roles"))
            member_user_ids = _id_set(members.get("users"))
            if user_id is not None and user_id in member_user_ids:
                out.append(group)
                continue
            if role_ids & member_role_ids:
                out.append(group)
        return out

    def _overrides_for(self, kind: str) -> Mapping[str, Any]:
        key = {"command": "command_overrides", "feature": "feature_overrides", "panel": "panel_overrides"}.get(kind)
        if key is None:
            return {}
        bucket = self.payload.get(key)
        return bucket if isinstance(bucket, Mapping) else {}


def _as_str_set(value: Any) -> Set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    out: Set[str] = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        out.add(normalize_capability(text))
    return out


# ---------------------------------------------------------------------------
# Legacy fallback
# ---------------------------------------------------------------------------
# When a guild has no ``permissions`` block (i.e. has not been onboarded yet)
# we fall back to the old role-key-based matrix in mbx_services.PERMISSIONS_MATRIX.
# This keeps existing deployments behaving as before until /start is run.

_LEGACY_MATRIX: Dict[str, Dict[str, Any]] = {
    "mod.case_panel":  {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.history":     {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.punish":      {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.public_punish": {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.undo":        {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.active":      {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.appeals":     {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "mod.purge":       {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_messages"},
    "mod.lock":        {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_channels"},
    "modmail.reply":   {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "modmail.claim":   {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "modmail.close":   {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "modmail.canned":  {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "modmail.settings": {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "automod.view":    {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "automod.respond": {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "automod.configure": {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "roles.use":       {"role_keys": (), "discord_perm": None, "always_true": True},
    "roles.admin":     {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_roles"},
    "roles.settings":  {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "setup.run":       {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "setup.validate":  {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "config.edit":     {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "config.export":   {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "config.import":   {"role_keys": ("role_owner",), "discord_perm": "manage_guild"},
    "branding.edit":   {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "permissions.edit": {"role_keys": ("role_owner", "role_admin"), "discord_perm": "manage_guild"},
    "rules.edit":      {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "escalation.edit": {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "system.lockdown": {"role_keys": ("role_owner", "role_admin"), "discord_perm": "manage_guild"},
    "system.archive":  {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_channels"},
    "system.safety":   {"role_keys": ("role_owner",), "discord_perm": "manage_guild"},
    "system.status":   {"role_keys": ("role_mod", "role_admin", "role_owner", "role_community_manager"), "discord_perm": "moderate_members"},
    "system.stats":    {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "system.directory": {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
    "system.internals": {"role_keys": ("role_admin", "role_owner", "role_community_manager"), "discord_perm": "manage_guild"},
}


def _legacy_has_capability(
    capability: str,
    *,
    role_ids: FrozenSet[int],
    user_id: Optional[int],
    guild_owner_id: Optional[int],
    config: Mapping[str, Any],
    administrator: bool,
) -> bool:
    if user_id is not None and user_id == guild_owner_id:
        return True
    if administrator:
        return True
    rule = _LEGACY_MATRIX.get(capability)
    if rule is None:
        return administrator
    if rule.get("always_true"):
        return True

    allowed_role_ids: Set[int] = set()
    for key in rule.get("role_keys", ()):
        rid = config.get(key)
        if rid:
            try:
                allowed_role_ids.add(int(rid))
            except (TypeError, ValueError):
                continue

    extra_mod_roles = config.get("mod_roles") or []
    if isinstance(extra_mod_roles, list) and capability.startswith(("mod.", "modmail.", "automod.view", "automod.respond", "system.status")):
        for rid in extra_mod_roles:
            try:
                allowed_role_ids.add(int(rid))
            except (TypeError, ValueError):
                continue

    return bool(role_ids & allowed_role_ids)


# ---------------------------------------------------------------------------
# Helpers used by the new public mbx_permissions API.
# ---------------------------------------------------------------------------

def can_member_use(
    member_or_user: Any,
    capability: str,
    config: Mapping[str, Any],
    *,
    guild_owner_id: Optional[int] = None,
) -> bool:
    """Convenience: resolve a capability check from a discord.Member-like object."""
    engine = PermissionEngine.for_guild(config)
    role_ids: List[int] = []
    discord_permissions: Optional[discord.Permissions] = None

    roles = getattr(member_or_user, "roles", None) or []
    for role in roles:
        rid = getattr(role, "id", None)
        if rid is not None:
            role_ids.append(int(rid))

    discord_permissions = getattr(member_or_user, "guild_permissions", None)
    user_id = int(getattr(member_or_user, "id", 0)) or None

    return engine.has_capability(
        capability,
        user_id=user_id,
        role_ids=role_ids,
        guild_owner_id=guild_owner_id,
        discord_permissions=discord_permissions,
    )


def evaluate_command_access(
    member: Any,
    command_key: str,
    capability: str,
    config: Mapping[str, Any],
    *,
    guild_owner_id: Optional[int] = None,
) -> bool:
    """Apply command override (if any), then fall back to a capability check."""
    engine = PermissionEngine.for_guild(config)
    role_ids: List[int] = [int(r.id) for r in getattr(member, "roles", []) or [] if hasattr(r, "id")]
    user_id = int(getattr(member, "id", 0)) or None
    discord_permissions = getattr(member, "guild_permissions", None)

    override_result = engine.check_override(
        "command",
        command_key,
        user_id=user_id,
        role_ids=role_ids,
        guild_owner_id=guild_owner_id,
        discord_permissions=discord_permissions,
    )
    if override_result is not None:
        return override_result

    return engine.has_capability(
        capability,
        user_id=user_id,
        role_ids=role_ids,
        guild_owner_id=guild_owner_id,
        discord_permissions=discord_permissions,
    )


__all__ = [
    "CAPABILITIES",
    "CAPABILITY_ALIASES",
    "DISCORD_PERMISSION_FLAGS",
    "Override",
    "PermissionEngine",
    "can_member_use",
    "default_permission_payload",
    "evaluate_command_access",
    "normalize_capability",
]
