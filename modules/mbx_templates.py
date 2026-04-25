"""Setup templates — realistic, editable starting points for new guilds.

Each template is a stable identifier (used by ``/start template:<id>``) plus a
human-readable name, description, and a *patch* that gets deep-merged into the
guild's config. Templates are only starting points: every value they apply is
editable afterwards through ``/setup`` and the existing dashboards.

Adding a template:
    1. Add an entry to ``TEMPLATES`` below with a stable id.
    2. Implement a ``_template_<id>`` function returning a patch dict.
    3. Document what it does in the description so the wizard can show it.

Templates do NOT include role/channel IDs — those are guild-specific and the
``/start`` wizard collects them through dropdowns.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from modules.mbx_permission_engine import default_permission_payload


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    summary: str
    description: str
    builder: Callable[[], Dict[str, Any]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> list[Template]:
    return list(TEMPLATES.values())


def get_template(template_id: str) -> Template | None:
    return TEMPLATES.get(template_id)


def apply_template(config: Dict[str, Any], template_id: str) -> Dict[str, Any]:
    """Deep-merge a template's patch into ``config`` (in-place) and return it.

    Existing user-set values are preserved unless the template explicitly
    overrides them. Lists are *replaced*, not concatenated, so editing a list
    after applying a template won't get clobbered by re-application of the
    same template later.
    """
    template = get_template(template_id)
    if template is None:
        raise KeyError(f"Unknown template: {template_id}")
    patch = template.builder()
    _deep_merge(config, patch)
    config.setdefault("_setup_metadata", {})["last_applied_template"] = template_id
    return config


def _deep_merge(target: Dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


def _baseline_feature_flags(**overrides: bool) -> Dict[str, bool]:
    base = {
        "advanced_case_panel":   True,
        "advanced_modmail":      True,
        "setup_validation":      True,
        "config_panel":          True,
        "role_cleanup":          False,
        "smart_automod":         False,
        "native_automod_bridge": True,
        "automod_panel":         True,
        "dm_modmail_prompt":     True,
    }
    base.update(overrides)
    return base


def _light_escalation() -> list[dict]:
    return [
        {"minimum_points": 0,  "mode": "base",      "multiplier": 1, "force_ban": False, "label": "Standard"},
        {"minimum_points": 4,  "mode": "escalated", "multiplier": 1, "force_ban": False, "label": "Escalated"},
        {"minimum_points": 10, "mode": "escalated", "multiplier": 2, "force_ban": False, "label": "Heavy"},
        {"minimum_points": 18, "mode": "ban",       "multiplier": 1, "force_ban": True,  "label": "Auto Ban"},
    ]


def _balanced_escalation() -> list[dict]:
    return [
        {"minimum_points": 0,  "mode": "base",      "multiplier": 1, "force_ban": False, "label": "Standard"},
        {"minimum_points": 3,  "mode": "escalated", "multiplier": 1, "force_ban": False, "label": "Escalated"},
        {"minimum_points": 8,  "mode": "escalated", "multiplier": 2, "force_ban": False, "label": "Escalated x2"},
        {"minimum_points": 12, "mode": "escalated", "multiplier": 4, "force_ban": False, "label": "Escalated x4"},
        {"minimum_points": 16, "mode": "ban",       "multiplier": 1, "force_ban": True,  "label": "Auto Ban"},
    ]


def _strict_escalation() -> list[dict]:
    return [
        {"minimum_points": 0,  "mode": "base",      "multiplier": 1, "force_ban": False, "label": "Standard"},
        {"minimum_points": 2,  "mode": "escalated", "multiplier": 1, "force_ban": False, "label": "Escalated"},
        {"minimum_points": 5,  "mode": "escalated", "multiplier": 2, "force_ban": False, "label": "Heavy"},
        {"minimum_points": 9,  "mode": "escalated", "multiplier": 3, "force_ban": False, "label": "Severe"},
        {"minimum_points": 12, "mode": "ban",       "multiplier": 1, "force_ban": True,  "label": "Auto Ban"},
    ]


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------


def _template_balanced() -> Dict[str, Any]:
    return {
        "feature_flags": _baseline_feature_flags(),
        "escalation_matrix": _balanced_escalation(),
        "modmail_sla_minutes": 60,
        "dm_modmail_panel_cooldown_minutes": 30,
        "smart_automod": {
            "duplicate_window_seconds": 20,
            "duplicate_threshold":      4,
            "max_caps_ratio":           0.75,
            "caps_min_length":          12,
        },
        "permissions": default_permission_payload(),
    }


def _template_light() -> Dict[str, Any]:
    return {
        "feature_flags": _baseline_feature_flags(
            smart_automod=False,
            native_automod_bridge=False,
            role_cleanup=False,
            advanced_case_panel=True,
        ),
        "escalation_matrix": _light_escalation(),
        "modmail_sla_minutes": 240,            # less aggressive SLA reminders
        "dm_modmail_panel_cooldown_minutes": 120,
        "smart_automod": {
            "duplicate_window_seconds": 30,
            "duplicate_threshold":      6,
            "max_caps_ratio":           0.85,
            "caps_min_length":          18,
        },
        "permissions": default_permission_payload(),
    }


def _template_large_public() -> Dict[str, Any]:
    return {
        "feature_flags": _baseline_feature_flags(
            smart_automod=True,
            native_automod_bridge=True,
            role_cleanup=True,
            dm_modmail_prompt=True,
        ),
        "escalation_matrix": _strict_escalation(),
        "modmail_sla_minutes": 30,
        "dm_modmail_panel_cooldown_minutes": 15,
        "smart_automod": {
            "duplicate_window_seconds": 15,
            "duplicate_threshold":      3,
            "max_caps_ratio":           0.65,
            "caps_min_length":          10,
        },
        "permissions": default_permission_payload(),
    }


def _template_support_heavy() -> Dict[str, Any]:
    payload = default_permission_payload()
    # Support-heavy guilds tend to have many staff with modmail-only access.
    # Wire a "support" slot of capabilities anyone with `manage_messages` can use.
    payload["discord_permission_capabilities"]["manage_messages"] = list(set(
        payload["discord_permission_capabilities"].get("manage_messages", [])
        + ["modmail.reply", "modmail.claim", "modmail.canned", "automod.respond", "system.status"]
    ))
    return {
        "feature_flags": _baseline_feature_flags(
            advanced_modmail=True,
            dm_modmail_prompt=True,
            smart_automod=False,
        ),
        "escalation_matrix": _balanced_escalation(),
        "modmail_sla_minutes": 20,             # tight SLA for support orgs
        "dm_modmail_panel_cooldown_minutes": 10,
        "modmail_discussion_threads": True,
        "permissions": payload,
    }


def _template_community() -> Dict[str, Any]:
    return {
        "feature_flags": _baseline_feature_flags(
            role_cleanup=True,
            smart_automod=True,
            advanced_case_panel=True,
        ),
        "escalation_matrix": _balanced_escalation(),
        "modmail_sla_minutes": 90,
        "dm_modmail_panel_cooldown_minutes": 45,
        "smart_automod": {
            "duplicate_window_seconds": 25,
            "duplicate_threshold":      4,
            "max_caps_ratio":           0.7,
            "caps_min_length":          15,
        },
        "permissions": default_permission_payload(),
    }


def _template_blank() -> Dict[str, Any]:
    """Bare scaffold: feature flags off-ish, conservative defaults, no presets."""
    return {
        "feature_flags": {
            "advanced_case_panel":   True,
            "advanced_modmail":      True,
            "setup_validation":      True,
            "config_panel":          True,
            "role_cleanup":          False,
            "smart_automod":         False,
            "native_automod_bridge": False,
            "automod_panel":         False,
            "dm_modmail_prompt":     False,
        },
        "escalation_matrix": _balanced_escalation(),
        "modmail_sla_minutes": 60,
        "permissions": default_permission_payload(),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TEMPLATES: Dict[str, Template] = {
    "balanced": Template(
        id="balanced",
        name="Balanced Server",
        summary="Sensible defaults for most communities. Mid-strength automod, standard escalation.",
        description=(
            "A neutral starting point for general communities. Enables the case panel, "
            "modmail SLA reminders, and Discord-native automod follow-up. Smart automod "
            "and role cleanup are off by default — turn them on after the wizard if you "
            "need them."
        ),
        builder=_template_balanced,
    ),
    "light": Template(
        id="light",
        name="Light Moderation",
        summary="Minimal automation. Slower escalation, longer SLA, smart automod off.",
        description=(
            "Best for small or trust-based communities where heavy automation feels "
            "intrusive. Disables smart automod and the native automod bridge. "
            "Punishments escalate slowly and modmail reminders are calmer."
        ),
        builder=_template_light,
    ),
    "large-public": Template(
        id="large-public",
        name="Large Public Server",
        summary="Strict automod and escalation. Tight modmail SLA. Role cleanup on.",
        description=(
            "Tuned for high-traffic public servers. Smart automod, native automod, "
            "and role cleanup are all enabled. Escalation reaches an auto-ban faster "
            "and modmail SLA reminders fire sooner."
        ),
        builder=_template_large_public,
    ),
    "support-heavy": Template(
        id="support-heavy",
        name="Support-Heavy Server",
        summary="Modmail-first. Tight SLA. `manage_messages` unlocks support tools.",
        description=(
            "For servers where modmail is the central workflow. SLA reminders fire "
            "every 20 minutes by default, the DM modmail prompt is enabled, and "
            "anyone with `manage_messages` automatically gets the modmail/automod "
            "support capabilities — no extra role configuration needed."
        ),
        builder=_template_support_heavy,
    ),
    "community": Template(
        id="community",
        name="Community-Focused",
        summary="Custom roles + smart automod + active case panel. Booster cleanup on.",
        description=(
            "Optimised for communities where booster perks and custom roles matter. "
            "Smart automod is enabled with friendly thresholds and the lost-booster "
            "role cleanup task runs every 6 hours."
        ),
        builder=_template_community,
    ),
    "blank": Template(
        id="blank",
        name="Blank Server",
        summary="Minimal scaffold. Most features off. You wire it up yourself.",
        description=(
            "A fully manual starting point. Feature flags for automod, role cleanup, "
            "and DM modmail prompts are off — turn things on as you need them via "
            "/setup → Features."
        ),
        builder=_template_blank,
    ),
}


__all__ = [
    "Template",
    "TEMPLATES",
    "apply_template",
    "get_template",
    "list_templates",
]
