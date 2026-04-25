from __future__ import annotations

import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from modules.mbx_automod import (
    AUTOMOD_PUNISHMENT_OPTIONS,
    AUTOMOD_REPORT_RESPONSE_PRESETS,
    AUTOMOD_THRESHOLD_PRESETS,
    AUTOMOD_TIMEOUT_PRESETS,
    AUTOMOD_WINDOW_PRESETS,
    apply_automod_report_response,
    build_automod_bridge_embed,
    build_automod_dashboard_embed,
    build_automod_immunity_embed,
    build_automod_policy_embed,
    build_automod_routing_embed,
    build_automod_rule_browser_embed,
    build_default_native_automod_policy,
    build_default_native_automod_step,
    build_numeric_select_options,
    build_smart_automod_embed,
    ensure_native_rule_override_policy,
    fetch_native_automod_rules,
    format_compact_minutes_input,
    format_minutes_interval,
    format_native_automod_step_summary,
    get_automod_report_preset,
    get_native_automod_policy_steps,
    get_native_rule_override,
    get_smart_automod_settings,
    parse_automod_punishment_input,
    parse_minutes_input,
    parse_positive_integer_input,
    respond_with_error,
    store_native_automod_settings,
    store_smart_automod_settings,
)
from modules.mbx_constants import SCOPE_MODERATION
from modules.mbx_context import abuse_system, bot, tree
from modules.mbx_embeds import make_confirmation_embed
from modules.mbx_formatters import format_user_ref
from modules.mbx_logging import get_punishment_log_channel_id, make_action_log_embed, normalize_log_embed
from modules.mbx_permissions import respond_with_error
from modules.mbx_services import DEFAULT_NATIVE_AUTOMOD_SETTINGS, get_feature_flag, get_native_automod_settings
from modules.mbx_utils import truncate_text
from ui.shared import ExpirableMixin


logger = logging.getLogger("MGXBot")

class AutoModPolicyReasonModal(discord.ui.Modal, title="Edit AutoMod Reason Template"):
    reason_template = discord.ui.TextInput(
        label="Reason Template",
        style=discord.TextStyle.paragraph,
        max_length=200,
        placeholder="Repeated native AutoMod violations",
    )

    def __init__(self, *, rule: Optional[discord.AutoModRule] = None, rules: Optional[List[discord.AutoModRule]] = None):
        super().__init__()
        self.rule = rule
        self.rules = rules or []
        settings = get_native_automod_settings(bot.data_manager.config)
        if rule is None:
            policy = build_default_native_automod_policy()
        else:
            _, policy, _ = get_native_rule_override(settings, rule)
        self.reason_template.default = str(policy.get("reason_template", DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"]))

    async def on_submit(self, interaction: discord.Interaction):
        settings = get_native_automod_settings(bot.data_manager.config)
        if self.rule is None:
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        _, policy = ensure_native_rule_override_policy(settings, self.rule)
        policy["reason_template"] = self.reason_template.value.strip()[:200] or DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"]
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()

        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules)
        await interaction.response.send_message(embed=view.build_embed(interaction.guild), view=view, ephemeral=True)

class AutoModStepValuesModal(discord.ui.Modal, title="Edit AutoMod Step"):
    punishment_type = discord.ui.TextInput(
        label="Action",
        placeholder="warn, timeout, kick, or ban",
        max_length=10,
    )
    warning_count = discord.ui.TextInput(
        label="Warnings",
        placeholder="3",
        max_length=4,
    )
    warning_window = discord.ui.TextInput(
        label="Window",
        placeholder="6h, 2d, or 1w",
        max_length=12,
    )
    timeout_length = discord.ui.TextInput(
        label="Timeout Length",
        placeholder="1h or 12h",
        required=False,
        max_length=12,
    )

    def __init__(self, *, parent_view):
        super().__init__()
        self.parent_view = parent_view
        current_step = parent_view.get_current_step()
        self.punishment_type.default = str(current_step.get("punishment_type", "warn")).lower()
        self.warning_count.default = str(current_step.get("threshold", 1))
        self.warning_window.default = format_compact_minutes_input(int(current_step.get("window_minutes", 1440) or 1440))
        if str(current_step.get("punishment_type", "warn")).lower() == "timeout":
            self.timeout_length.default = format_compact_minutes_input(int(current_step.get("duration_minutes", 60) or 60))
        else:
            self.timeout_length.default = ""

    async def on_submit(self, interaction: discord.Interaction):
        policy = self.parent_view.get_current_policy()
        steps = self.parent_view.get_current_steps()
        if not steps:
            overview = AutoModPolicyEditorView(rule=self.parent_view.rule, rules=self.parent_view.rules)
            await interaction.response.send_message(embed=overview.build_embed(interaction.guild), view=overview, ephemeral=True)
            return

        current_step = dict(steps[self.parent_view.step_index])

        try:
            punishment_type = parse_automod_punishment_input(self.punishment_type.value, field_name="Action")
            current_step["punishment_type"] = punishment_type
            current_step["threshold"] = parse_positive_integer_input(self.warning_count.value, field_name="Warning count")
            current_step["window_minutes"] = parse_minutes_input(self.warning_window.value, field_name="Warning window", maximum=43200)
            if punishment_type == "timeout":
                timeout_raw = self.timeout_length.value.strip() or format_compact_minutes_input(int(current_step.get("duration_minutes", 60) or 60))
                current_step["duration_minutes"] = parse_minutes_input(timeout_raw, field_name="Timeout length", maximum=40320)
            elif punishment_type == "ban":
                current_step["duration_minutes"] = -1
            else:
                current_step["duration_minutes"] = 0
        except ValueError as exc:
            await respond_with_error(interaction, str(exc), scope=SCOPE_MODERATION)
            return

        steps[self.parent_view.step_index] = current_step
        policy["steps"] = steps
        await self.parent_view.persist_policy(policy)

        view = AutoModPolicyEditorView(rule=self.parent_view.rule, rules=self.parent_view.rules, step_index=self.parent_view.step_index)
        if getattr(interaction, "message", None) is not None:
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            return
        await interaction.response.send_message(embed=view.build_embed(interaction.guild), view=view, ephemeral=True)

class AutoModStepSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = []
        for index, step in enumerate(self.parent_view.get_current_steps()):
            options.append(
                discord.SelectOption(
                    label=f"Step {index + 1}",
                    value=str(index),
                    description=truncate_text(format_native_automod_step_summary(step), 100),
                    default=index == getattr(self.parent_view, "step_index", 0),
                )
            )
        super().__init__(placeholder="Choose which step to edit...", min_values=1, max_values=1, options=options[:25], row=0)

    async def callback(self, interaction: discord.Interaction):
        step_index = int(self.values[0])
        view = AutoModPolicyEditorView(rule=self.parent_view.rule, rules=self.parent_view.rules, step_index=step_index)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

class AutoModStepPunishmentTypeSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        current_type = self.parent_view.get_current_step().get("punishment_type", "warn")
        options = [
            discord.SelectOption(label=label, value=value, default=value == current_type)
            for value, label in AUTOMOD_PUNISHMENT_OPTIONS
        ]
        super().__init__(placeholder="Choose the punishment for this step...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.set_step_punishment_type(interaction, self.values[0])

class AutoModStepThresholdSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        current = int(self.parent_view.get_current_step().get("threshold", 3) or 3)
        super().__init__(
            placeholder="Trigger this step after this many warnings...",
            min_values=1,
            max_values=1,
            options=build_numeric_select_options(current, AUTOMOD_THRESHOLD_PRESETS, lambda value: f"{value} hit{'s' if value != 1 else ''}"),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.set_step_value(interaction, "threshold", int(self.values[0]))

class AutoModStepWindowSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        current = int(self.parent_view.get_current_step().get("window_minutes", 1440) or 1440)
        super().__init__(
            placeholder="Only count warnings inside this time window...",
            min_values=1,
            max_values=1,
            options=build_numeric_select_options(current, AUTOMOD_WINDOW_PRESETS, format_minutes_interval),
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.set_step_value(interaction, "window_minutes", int(self.values[0]))

class AutoModStepTimeoutDurationSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        current_step = self.parent_view.get_current_step()
        current = int(current_step.get("duration_minutes", 60) or 60)
        super().__init__(
            placeholder="Timeout length when action is timeout...",
            min_values=1,
            max_values=1,
            options=build_numeric_select_options(current, AUTOMOD_TIMEOUT_PRESETS, format_minutes_interval),
            row=3,
        )
        self.disabled = str(current_step.get("punishment_type", "warn")).lower() != "timeout"

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.set_step_value(interaction, "duration_minutes", int(self.values[0]))

class AutoModRuleSelect(discord.ui.Select):
    def __init__(self, parent_view, rules: List[discord.AutoModRule]):
        self.parent_view = parent_view
        self.rules = rules[:25]
        options = []
        settings = get_native_automod_settings(bot.data_manager.config)
        for rule in self.rules:
            _, policy, using_override = get_native_rule_override(settings, rule)
            steps = get_native_automod_policy_steps(policy)
            summary_label = f"{len(steps)} step{'s' if len(steps) != 1 else ''}" if steps else "No steps"
            options.append(
                discord.SelectOption(
                    label=truncate_text(rule.name, 100),
                    value=str(rule.id),
                    description=truncate_text(
                        f"{'On' if policy.get('enabled') and steps else 'Off'} • {summary_label}",
                        100,
                    ),
                )
            )
        super().__init__(placeholder="Choose a native AutoMod rule...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        selected = next((rule for rule in self.rules if str(rule.id) == self.values[0]), None)
        if selected is None:
            await respond_with_error(interaction, "That AutoMod rule could not be found anymore.", scope=SCOPE_MODERATION)
            return
        view = AutoModPolicyEditorView(rule=selected, rules=self.parent_view.rules)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

class AutoModBridgeSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.sync_buttons()

    def sync_buttons(self):
        settings = get_native_automod_settings(bot.data_manager.config)
        self.toggle_bridge.label = f"Bot Response: {'On' if settings.get('enabled', True) else 'Off'}"
        self.toggle_bridge.style = discord.ButtonStyle.success if settings.get("enabled", True) else discord.ButtonStyle.secondary
        self.toggle_dm.label = f"User DMs: {'On' if settings.get('warning_dm_enabled', True) else 'Off'}"
        self.toggle_dm.style = discord.ButtonStyle.success if settings.get("warning_dm_enabled", True) else discord.ButtonStyle.secondary
        self.toggle_report.label = f"Report Button: {'On' if settings.get('report_button_enabled', True) else 'Off'}"
        self.toggle_report.style = discord.ButtonStyle.success if settings.get("report_button_enabled", True) else discord.ButtonStyle.secondary

    async def _save_and_refresh(self, interaction: discord.Interaction, settings: dict):
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()
        self.sync_buttons()
        await interaction.response.edit_message(embed=build_automod_bridge_embed(interaction.guild), view=self)

    @discord.ui.button(label="Bot Response", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_bridge(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_native_automod_settings(bot.data_manager.config)
        settings["enabled"] = not settings.get("enabled", True)
        await self._save_and_refresh(interaction, settings)

    @discord.ui.button(label="User DMs", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_native_automod_settings(bot.data_manager.config)
        settings["warning_dm_enabled"] = not settings.get("warning_dm_enabled", True)
        await self._save_and_refresh(interaction, settings)

    @discord.ui.button(label="Report Button", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_native_automod_settings(bot.data_manager.config)
        settings["report_button_enabled"] = not settings.get("report_button_enabled", True)
        await self._save_and_refresh(interaction, settings)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())

class AutoModRuleBrowserView(discord.ui.View):
    def __init__(self, rules: List[discord.AutoModRule]):
        super().__init__(timeout=180)
        self.rules = rules[:25]
        if self.rules:
            self.add_item(AutoModRuleSelect(self, self.rules))

    @discord.ui.button(label="Refresh Rules", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules = await fetch_native_automod_rules(interaction.guild)
        view = AutoModRuleBrowserView(rules)
        await interaction.response.edit_message(embed=build_automod_rule_browser_embed(interaction.guild, rules), view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())

class AutoModPolicyEditorView(discord.ui.View):
    def __init__(self, *, rule: Optional[discord.AutoModRule] = None, rules: Optional[List[discord.AutoModRule]] = None, step_index: int = 0):
        super().__init__(timeout=180)
        self.rule = rule
        self.rules = rules or []
        self.step_index = step_index
        steps = self.get_current_steps() if self.rule is not None else []
        if steps:
            self.step_index = max(0, min(step_index, len(steps) - 1))
            self.add_item(AutoModStepSelect(self))
        self.sync_buttons()

    def get_current_policy(self) -> dict:
        settings = get_native_automod_settings(bot.data_manager.config)
        if self.rule is None:
            return build_default_native_automod_policy()
        _, policy, _ = get_native_rule_override(settings, self.rule)
        return {
            "enabled": bool(policy.get("enabled", False)),
            "reason_template": str(policy.get("reason_template", DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"]) or DEFAULT_NATIVE_AUTOMOD_SETTINGS["default_escalation"]["reason_template"])[:200],
            "steps": get_native_automod_policy_steps(policy),
        }

    def get_current_steps(self) -> List[dict]:
        return get_native_automod_policy_steps(self.get_current_policy())

    def get_current_step(self) -> dict:
        steps = self.get_current_steps()
        if not steps:
            self.step_index = 0
            return build_default_native_automod_step()
        self.step_index = max(0, min(self.step_index, len(steps) - 1))
        return dict(steps[self.step_index])

    def build_embed(self, guild: discord.Guild) -> discord.Embed:
        if self.rule is None:
            return build_automod_policy_embed(
                guild,
                build_default_native_automod_policy(),
                title="AutoMod Rule Punishment",
                description="> Pick a Discord AutoMod rule first, then edit that rule's punishment settings.",
            )
        settings = get_native_automod_settings(bot.data_manager.config)
        _, policy, using_override = get_native_rule_override(settings, self.rule)
        return build_automod_policy_embed(
            guild,
            policy,
            title=f"Rule Punishment: {self.rule.name}",
            description="> Pick a step from the dropdown, then use the buttons below to edit that step or the rule.",
            rule=self.rule,
            using_override=using_override,
            selected_step_index=self.step_index if self.get_current_steps() else None,
        )

    def sync_buttons(self):
        settings = get_native_automod_settings(bot.data_manager.config)
        enabled = False
        using_override = False
        steps = self.get_current_steps() if self.rule is not None else []
        if self.rule is not None:
            _, policy, using_override = get_native_rule_override(settings, self.rule)
            enabled = bool(policy.get("enabled", False) and steps)
        self.toggle_enabled.label = f"Auto Punish: {'On' if enabled else 'Off'}"
        self.toggle_enabled.style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        self.toggle_enabled.disabled = not bool(steps)
        self.add_step.disabled = self.rule is None or len(steps) >= 5
        self.custom_amounts.disabled = not bool(steps)
        self.remove_step.disabled = not bool(steps)
        self.remove_step.style = discord.ButtonStyle.secondary if self.remove_step.disabled else discord.ButtonStyle.danger
        self.clear_override.disabled = self.rule is None or not using_override
        self.clear_override.style = discord.ButtonStyle.secondary if self.clear_override.disabled else discord.ButtonStyle.danger

    async def persist_policy(self, policy: dict):
        settings = get_native_automod_settings(bot.data_manager.config)
        if self.rule is None:
            return
        override_key, _ = ensure_native_rule_override_policy(settings, self.rule)
        policy["steps"] = get_native_automod_policy_steps(policy)
        if not policy["steps"]:
            policy["enabled"] = False
            self.step_index = 0
        else:
            self.step_index = max(0, min(self.step_index, len(policy["steps"]) - 1))
        settings.setdefault("rule_overrides", {})[override_key] = policy
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()

    async def save_policy(self, interaction: discord.Interaction, policy: dict):
        if self.rule is None:
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        await self.persist_policy(policy)

    async def set_step_value(self, interaction: discord.Interaction, key: str, value: int):
        policy = self.get_current_policy()
        steps = self.get_current_steps()
        if not steps:
            view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            return
        steps[self.step_index][key] = value
        policy["steps"] = steps
        await self.save_policy(interaction, policy)
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    async def set_step_punishment_type(self, interaction: discord.Interaction, punishment_type: str):
        policy = self.get_current_policy()
        steps = self.get_current_steps()
        if not steps:
            view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            return
        steps[self.step_index]["punishment_type"] = punishment_type
        if punishment_type == "timeout" and int(steps[self.step_index].get("duration_minutes", 0) or 0) <= 0:
            steps[self.step_index]["duration_minutes"] = 60
        elif punishment_type == "ban":
            steps[self.step_index]["duration_minutes"] = -1
        else:
            steps[self.step_index]["duration_minutes"] = 0
        policy["steps"] = steps
        await self.save_policy(interaction, policy)
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    @discord.ui.button(label="Auto Punish", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_enabled(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_native_automod_settings(bot.data_manager.config)
        if self.rule is None:
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        _, policy = ensure_native_rule_override_policy(settings, self.rule)
        if not policy.get("steps"):
            view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            return
        policy["enabled"] = not bool(policy.get("enabled", False))
        await self.save_policy(interaction, policy)
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    @discord.ui.button(label="Add Step", style=discord.ButtonStyle.primary, row=1)
    async def add_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = get_native_automod_settings(bot.data_manager.config)
        if self.rule is None:
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        _, policy = ensure_native_rule_override_policy(settings, self.rule)
        steps = get_native_automod_policy_steps(policy)
        if len(steps) >= 5:
            await interaction.response.edit_message(embed=self.build_embed(interaction.guild), view=self)
            return
        steps.append(build_default_native_automod_step(steps))
        policy["steps"] = steps
        policy["enabled"] = True
        await self.save_policy(interaction, policy)
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=len(steps) - 1)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    @discord.ui.button(label="Edit Selected Step", style=discord.ButtonStyle.primary, row=1)
    async def custom_amounts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AutoModStepValuesModal(parent_view=self))

    @discord.ui.button(label="Edit Reason", style=discord.ButtonStyle.secondary, row=2)
    async def edit_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AutoModPolicyReasonModal(rule=self.rule, rules=self.rules))

    @discord.ui.button(label="Remove Selected", style=discord.ButtonStyle.danger, row=2)
    async def remove_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        policy = self.get_current_policy()
        steps = self.get_current_steps()
        if not steps:
            view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=self.step_index)
            await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)
            return
        steps.pop(self.step_index)
        policy["steps"] = steps
        if not steps:
            policy["enabled"] = False
        await self.save_policy(interaction, policy)
        next_index = min(self.step_index, max(0, len(steps) - 1))
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=next_index)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    @discord.ui.button(label="Reset Rule", style=discord.ButtonStyle.danger, row=2)
    async def clear_override(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.rule is None:
            await interaction.response.defer()
            return
        settings = get_native_automod_settings(bot.data_manager.config)
        override_key, _, using_override = get_native_rule_override(settings, self.rule)
        if using_override:
            settings.setdefault("rule_overrides", {}).pop(override_key, None)
            settings.setdefault("rule_overrides", {}).pop(self.rule.name, None)
            settings.setdefault("rule_overrides", {}).pop(str(self.rule.id), None)
            store_native_automod_settings(settings)
            await bot.data_manager.save_config()
        view = AutoModPolicyEditorView(rule=self.rule, rules=self.rules, step_index=0)
        await interaction.response.edit_message(embed=view.build_embed(interaction.guild), view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.rule is None:
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        rules = self.rules or await fetch_native_automod_rules(interaction.guild)
        await interaction.response.edit_message(embed=build_automod_rule_browser_embed(interaction.guild, rules), view=AutoModRuleBrowserView(rules))

class AutoModChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, config_key: str, label: str):
        super().__init__(
            placeholder=f"Select {label}...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
        )
        self.config_key = config_key
        self.label = label

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        channel = interaction.guild.get_channel(selected.id) or await interaction.guild.fetch_channel(selected.id)
        bot.data_manager.config[self.config_key] = channel.id
        await bot.data_manager.save_config()
        view = AutoModChannelSettingsView()
        await interaction.response.edit_message(embed=build_automod_routing_embed(interaction.guild), view=view)

class AutoModChannelSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(AutoModChannelSelect("automod_log_channel_id", "AutoMod Log Channel"))
        self.add_item(AutoModChannelSelect("automod_report_channel_id", "AutoMod Report Channel"))
        self.add_item(AutoModChannelActionSelect())

class AutoModChannelActionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Back to Dashboard", value="back", description="Return to the main AutoMod control panel."),
            discord.SelectOption(label="Clear Log Channel", value="clear_log", description="Clear the dedicated AutoMod log channel."),
            discord.SelectOption(label="Clear Report Channel", value="clear_report", description="Clear the dedicated AutoMod report channel."),
        ]
        super().__init__(
            placeholder="More log channel actions...",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "back":
            await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())
            return
        if action == "clear_log":
            bot.data_manager.config["automod_log_channel_id"] = 0
            await bot.data_manager.save_config()
            await interaction.response.edit_message(embed=build_automod_routing_embed(interaction.guild), view=AutoModChannelSettingsView())
            return
        if action == "clear_report":
            bot.data_manager.config["automod_report_channel_id"] = 0
            await bot.data_manager.save_config()
            await interaction.response.edit_message(embed=build_automod_routing_embed(interaction.guild), view=AutoModChannelSettingsView())

class AutoModStoredValueRemoveSelect(discord.ui.Select):
    def __init__(self, *, label: str, config_scope: str, config_key: str, options: List[discord.SelectOption]):
        self.config_scope = config_scope
        self.config_key = config_key
        super().__init__(
            placeholder=f"Remove {label}...",
            min_values=1,
            max_values=min(len(options), 10),
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        selected_ids = {int(value) for value in self.values}
        if self.config_scope == "native":
            settings = get_native_automod_settings(bot.data_manager.config)
            settings[self.config_key] = [value for value in settings.get(self.config_key, []) if int(value) not in selected_ids]
            store_native_automod_settings(settings)
        else:
            settings = get_smart_automod_settings()
            settings[self.config_key] = [value for value in settings.get(self.config_key, []) if int(value) not in selected_ids]
            store_smart_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(content="Removed the selected entries.", view=None)

class AutoModStoredValueRemoveView(discord.ui.View):
    def __init__(self, *, label: str, config_scope: str, config_key: str, options: List[discord.SelectOption]):
        super().__init__(timeout=180)
        self.add_item(AutoModStoredValueRemoveSelect(label=label, config_scope=config_scope, config_key=config_key, options=options))

class AutoModImmunityUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Add immune users...", min_values=1, max_values=10, row=0)

    async def callback(self, interaction: discord.Interaction):
        settings = get_native_automod_settings(bot.data_manager.config)
        current = {int(value) for value in settings.get("immunity_users", [])}
        current.update(int(user.id) for user in self.values)
        settings["immunity_users"] = sorted(current)
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_automod_immunity_embed(interaction.guild), view=AutoModImmunityView())

class AutoModImmunityRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Add immune roles...", min_values=1, max_values=10, row=1)

    async def callback(self, interaction: discord.Interaction):
        settings = get_native_automod_settings(bot.data_manager.config)
        current = {int(value) for value in settings.get("immunity_roles", [])}
        current.update(int(role.id) for role in self.values)
        settings["immunity_roles"] = sorted(current)
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_automod_immunity_embed(interaction.guild), view=AutoModImmunityView())

class AutoModImmunityChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Add immune channels...", min_values=1, max_values=10, channel_types=[discord.ChannelType.text], row=2)

    async def callback(self, interaction: discord.Interaction):
        settings = get_native_automod_settings(bot.data_manager.config)
        current = {int(value) for value in settings.get("immunity_channels", [])}
        current.update(int(channel.id) for channel in self.values)
        settings["immunity_channels"] = sorted(current)
        store_native_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_automod_immunity_embed(interaction.guild), view=AutoModImmunityView())

class AutoModImmunityView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(AutoModImmunityUserSelect())
        self.add_item(AutoModImmunityRoleSelect())
        self.add_item(AutoModImmunityChannelSelect())

    async def _send_remove_picker(self, interaction: discord.Interaction, *, label: str, config_key: str):
        settings = get_native_automod_settings(bot.data_manager.config)
        values = settings.get(config_key, [])
        if not values:
            await interaction.response.send_message(f"No {label.lower()} are configured.", ephemeral=True)
            return
        options = []
        for value in values[:25]:
            if config_key == "immunity_users":
                member = interaction.guild.get_member(int(value))
                option_label = member.display_name if member else f"User {value}"
            elif config_key == "immunity_roles":
                role = interaction.guild.get_role(int(value))
                option_label = role.name if role else f"Role {value}"
            else:
                channel = interaction.guild.get_channel(int(value)) or interaction.guild.get_channel_or_thread(int(value))
                option_label = f"#{channel.name}" if channel else f"Channel {value}"
            options.append(discord.SelectOption(label=truncate_text(option_label, 100), value=str(value)))
        await interaction.response.send_message(
            f"Choose which {label.lower()} to remove:",
            view=AutoModStoredValueRemoveView(label=label, config_scope="native", config_key=config_key, options=options),
            ephemeral=True,
        )

    @discord.ui.button(label="Remove Users", style=discord.ButtonStyle.secondary, row=3)
    async def remove_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_remove_picker(interaction, label="Users", config_key="immunity_users")

    @discord.ui.button(label="Remove Roles", style=discord.ButtonStyle.secondary, row=3)
    async def remove_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_remove_picker(interaction, label="Roles", config_key="immunity_roles")

    @discord.ui.button(label="Remove Channels", style=discord.ButtonStyle.secondary, row=3)
    async def remove_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_remove_picker(interaction, label="Channels", config_key="immunity_channels")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())

class SmartAutoModThresholdModal(discord.ui.Modal, title="Edit Smart Filter Thresholds"):
    duplicate_window_seconds = discord.ui.TextInput(label="Duplicate window seconds", placeholder="20", max_length=4)
    duplicate_threshold = discord.ui.TextInput(label="Duplicate message count", placeholder="4", max_length=4)
    caps_min_length = discord.ui.TextInput(label="Minimum length before caps check", placeholder="12", max_length=4)
    max_caps_ratio = discord.ui.TextInput(label="Caps percent before block", placeholder="75", max_length=5)

    def __init__(self):
        super().__init__()
        settings = get_smart_automod_settings()
        self.duplicate_window_seconds.default = str(settings.get("duplicate_window_seconds", 20))
        self.duplicate_threshold.default = str(settings.get("duplicate_threshold", 4))
        self.caps_min_length.default = str(settings.get("caps_min_length", 12))
        self.max_caps_ratio.default = str(int(round(float(settings.get("max_caps_ratio", 0.75)) * 100)))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ratio_value = float(self.max_caps_ratio.value)
            if ratio_value > 1:
                ratio_value = ratio_value / 100
            settings = get_smart_automod_settings()
            settings["duplicate_window_seconds"] = max(5, int(self.duplicate_window_seconds.value))
            settings["duplicate_threshold"] = max(2, int(self.duplicate_threshold.value))
            settings["caps_min_length"] = max(3, int(self.caps_min_length.value))
            settings["max_caps_ratio"] = max(0.1, min(1.0, ratio_value))
        except ValueError:
            await respond_with_error(interaction, "Smart AutoMod thresholds must be valid numbers.", scope=SCOPE_MODERATION)
            return

        store_smart_automod_settings(settings)
        await bot.data_manager.save_config()
        view = SmartAutoModSettingsView()
        await interaction.response.send_message(embed=build_smart_automod_embed(interaction.guild), view=view, ephemeral=True)

class SmartAutoModPatternModal(discord.ui.Modal, title="Edit Blocked Patterns"):
    blocked_patterns = discord.ui.TextInput(
        label="One pattern per line",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
        placeholder="slur here\nanother blocked phrase",
    )

    def __init__(self):
        super().__init__()
        self.blocked_patterns.default = "\n".join(get_smart_automod_settings().get("blocked_patterns", []))

    async def on_submit(self, interaction: discord.Interaction):
        lines = [line.strip() for line in self.blocked_patterns.value.splitlines() if line.strip()]
        settings = get_smart_automod_settings()
        settings["blocked_patterns"] = lines[:50]
        store_smart_automod_settings(settings)
        await bot.data_manager.save_config()
        view = SmartAutoModSettingsView()
        await interaction.response.send_message(embed=build_smart_automod_embed(interaction.guild), view=view, ephemeral=True)

class SmartAutoModExemptRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Add smart-filter exempt roles...", min_values=1, max_values=10, row=0)

    async def callback(self, interaction: discord.Interaction):
        settings = get_smart_automod_settings()
        current = {int(value) for value in settings.get("exempt_roles", [])}
        current.update(int(role.id) for role in self.values)
        settings["exempt_roles"] = sorted(current)
        store_smart_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_smart_automod_embed(interaction.guild), view=SmartAutoModSettingsView())

class SmartAutoModExemptChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Add smart-filter exempt channels...", min_values=1, max_values=10, channel_types=[discord.ChannelType.text], row=1)

    async def callback(self, interaction: discord.Interaction):
        settings = get_smart_automod_settings()
        current = {int(value) for value in settings.get("exempt_channels", [])}
        current.update(int(channel.id) for channel in self.values)
        settings["exempt_channels"] = sorted(current)
        store_smart_automod_settings(settings)
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_smart_automod_embed(interaction.guild), view=SmartAutoModSettingsView())

class SmartAutoModSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(SmartAutoModExemptRoleSelect())
        self.add_item(SmartAutoModExemptChannelSelect())
        enabled = get_feature_flag(bot.data_manager.config, "smart_automod", False)
        self.toggle_feature.label = f"Smart Filters: {'On' if enabled else 'Off'}"
        self.toggle_feature.style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary

    async def _send_remove_picker(self, interaction: discord.Interaction, *, label: str, config_key: str):
        settings = get_smart_automod_settings()
        values = settings.get(config_key, [])
        if not values:
            await interaction.response.send_message(f"No {label.lower()} are configured.", ephemeral=True)
            return
        options = []
        for value in values[:25]:
            if config_key == "exempt_roles":
                role = interaction.guild.get_role(int(value))
                option_label = role.name if role else f"Role {value}"
            else:
                channel = interaction.guild.get_channel(int(value)) or interaction.guild.get_channel_or_thread(int(value))
                option_label = f"#{channel.name}" if channel else f"Channel {value}"
            options.append(discord.SelectOption(label=truncate_text(option_label, 100), value=str(value)))
        await interaction.response.send_message(
            f"Choose which {label.lower()} to remove:",
            view=AutoModStoredValueRemoveView(label=label, config_scope="smart", config_key=config_key, options=options),
            ephemeral=True,
        )

    @discord.ui.button(label="Smart Filters", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_feature(self, interaction: discord.Interaction, button: discord.ui.Button):
        flags = bot.data_manager.config.setdefault("feature_flags", {})
        flags["smart_automod"] = not bool(flags.get("smart_automod", False))
        await bot.data_manager.save_config()
        view = SmartAutoModSettingsView()
        await interaction.response.edit_message(embed=build_smart_automod_embed(interaction.guild), view=view)

    @discord.ui.button(label="Edit Thresholds", style=discord.ButtonStyle.primary, row=2)
    async def edit_thresholds(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SmartAutoModThresholdModal())

    @discord.ui.button(label="Edit Pattern List", style=discord.ButtonStyle.primary, row=2)
    async def edit_patterns(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SmartAutoModPatternModal())

    @discord.ui.button(label="Remove Exempt Roles", style=discord.ButtonStyle.secondary, row=3)
    async def remove_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_remove_picker(interaction, label="Roles", config_key="exempt_roles")

    @discord.ui.button(label="Remove Exempt Channels", style=discord.ButtonStyle.secondary, row=3)
    async def remove_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_remove_picker(interaction, label="Channels", config_key="exempt_channels")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())

class AutoModDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_dashboard_embed(interaction.guild), view=AutoModDashboardView())

    @discord.ui.button(label="Bot Response", style=discord.ButtonStyle.primary, row=0)
    async def bridge(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_bridge_embed(interaction.guild), view=AutoModBridgeSettingsView())

    @discord.ui.button(label="Rule Punishments", style=discord.ButtonStyle.primary, row=0)
    async def native_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        rules = await fetch_native_automod_rules(interaction.guild)
        view = AutoModRuleBrowserView(rules)
        await interaction.edit_original_response(embed=build_automod_rule_browser_embed(interaction.guild, rules), view=view)

    @discord.ui.button(label="Log Channels", style=discord.ButtonStyle.success, row=1)
    async def routing(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_routing_embed(interaction.guild), view=AutoModChannelSettingsView())

    @discord.ui.button(label="Immunity", style=discord.ButtonStyle.success, row=1)
    async def immunity(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_automod_immunity_embed(interaction.guild), view=AutoModImmunityView())

class AutoModCustomReportResponseModal(discord.ui.Modal, title="Custom AutoMod Report Response"):
    response_text = discord.ui.TextInput(
        label="Response",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        placeholder="Write the response that should be sent to the user.",
    )

    def __init__(self, *, guild_id: int, reporter_id: int, warning_id: str, rule_name: str, source_message: Optional[discord.Message]):
        super().__init__()
        self.guild_id = guild_id
        self.reporter_id = reporter_id
        self.warning_id = warning_id
        self.rule_name = rule_name
        self.source_message = source_message

    async def on_submit(self, interaction: discord.Interaction):
        success = await apply_automod_report_response(
            interaction,
            guild_id=self.guild_id,
            reporter_id=self.reporter_id,
            warning_id=self.warning_id,
            rule_name=self.rule_name,
            response_key="custom",
            response_text=self.response_text.value.strip()[:1000],
            source_message=self.source_message,
        )
        if success and not interaction.response.is_done():
            await interaction.response.send_message("Response sent.", ephemeral=True)
        elif success:
            await interaction.followup.send("Response sent.", ephemeral=True)

class AutoModReportResponseSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=preset["label"],
                value=key,
                description=truncate_text(preset["description"], 100),
            )
            for key, preset in AUTOMOD_REPORT_RESPONSE_PRESETS.items()
        ]
        super().__init__(
            placeholder="Respond to this report...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "custom":
            await interaction.response.send_modal(
                AutoModCustomReportResponseModal(
                    guild_id=self.parent_view.guild_id,
                    reporter_id=self.parent_view.reporter_id,
                    warning_id=self.parent_view.warning_id,
                    rule_name=self.parent_view.rule_name,
                    source_message=interaction.message,
                )
            )
            return

        preset = get_automod_report_preset(selected)
        await interaction.response.defer(ephemeral=True)
        success = await apply_automod_report_response(
            interaction,
            guild_id=self.parent_view.guild_id,
            reporter_id=self.parent_view.reporter_id,
            warning_id=self.parent_view.warning_id,
            rule_name=self.parent_view.rule_name,
            response_key=selected,
            response_text=preset["message"],
            source_message=interaction.message,
        )
        if success:
            await interaction.followup.send(
                embed=make_confirmation_embed(
                    "Report Response Sent",
                    f"> {preset['label']} was sent to the user.",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                ),
                ephemeral=True,
            )

class AutoModReportResponseView(discord.ui.View):
    def __init__(self, *, guild_id: int, reporter_id: int, warning_id: str, rule_name: str):
        super().__init__(timeout=604800)
        self.guild_id = guild_id
        self.reporter_id = reporter_id
        self.warning_id = warning_id
        self.rule_name = rule_name
        self.add_item(AutoModReportResponseSelect(self))

class AutoModReportModal(discord.ui.Modal, title="Report AutoMod Warning"):
    why_incorrect = discord.ui.TextInput(
        label="What was wrong?",
        style=discord.TextStyle.paragraph,
        max_length=600,
        placeholder="Explain why you think the filter was wrong.",
    )
    extra_context = discord.ui.TextInput(
        label="Anything else staff should know?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=600,
        placeholder="Context, screenshots, or what you were trying to say.",
    )

    def __init__(self, *, guild_id: int, warning_id: str, rule_id: int, rule_name: str, content: str, matched_keyword: Optional[str]):
        super().__init__()
        self.guild_id = guild_id
        self.warning_id = warning_id
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.content = content
        self.matched_keyword = matched_keyword

    async def on_submit(self, interaction: discord.Interaction):
        guild = bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("The server for this report could not be resolved.", ephemeral=True)
            return

        channel_id = (
            bot.data_manager.config.get("automod_report_channel_id")
            or bot.data_manager.config.get("appeal_channel_id")
            or get_punishment_log_channel_id()
        )
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if channel is None:
            await interaction.response.send_message("No AutoMod report channel is configured yet. Please contact staff directly.", ephemeral=True)
            return

        embed = make_action_log_embed(
            "AutoMod Report Submitted",
            "A user reported that a native AutoMod warning may have been incorrect.",
            guild=guild,
            kind="warning",
            scope=SCOPE_MODERATION,
            actor=format_user_ref(interaction.user),
            target=self.rule_name,
            reason="User reported a possible false positive.",
            message=self.content or '[Unavailable]',
            notes=[
                f"Rule ID: {self.rule_id}",
                f"Matched Keyword: {self.matched_keyword or 'Unknown'}",
                f"User Report: {truncate_text(self.why_incorrect.value, 500)}",
                f"Extra Context: {truncate_text(self.extra_context.value, 500) if self.extra_context.value else 'None'}",
            ],
            thumbnail=interaction.user.display_avatar.url,
            author_name=f"{interaction.user.display_name} ({interaction.user.id})",
            author_icon=interaction.user.display_avatar.url,
        )
        await channel.send(
            embed=normalize_log_embed(embed, guild=guild),
            view=AutoModReportResponseView(
                guild_id=guild.id,
                reporter_id=interaction.user.id,
                warning_id=self.warning_id,
                rule_name=self.rule_name,
            ),
        )
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                "Report Sent",
                "> Your AutoMod report was sent to the staff team for review.",
                scope=SCOPE_MODERATION,
                guild=guild,
            ),
            ephemeral=True,
        )

class AutoModWarningView(discord.ui.View):
    def __init__(self, *, guild_id: int, warning_id: str, rule_id: int, rule_name: str, content: str, matched_keyword: Optional[str]):
        super().__init__(timeout=86400)
        self.guild_id = guild_id
        self.warning_id = warning_id
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.content = truncate_text(content or "", 1000)
        self.matched_keyword = matched_keyword

    @discord.ui.button(label="Report to Moderator", style=discord.ButtonStyle.secondary)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AutoModReportModal(
                guild_id=self.guild_id,
                warning_id=self.warning_id,
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                content=self.content,
                matched_keyword=self.matched_keyword,
            )
        )


__all__ = [
    "AutoModPolicyReasonModal",
    "AutoModStepValuesModal",
    "AutoModStepSelect",
    "AutoModStepPunishmentTypeSelect",
    "AutoModStepThresholdSelect",
    "AutoModStepWindowSelect",
    "AutoModStepTimeoutDurationSelect",
    "AutoModRuleSelect",
    "AutoModBridgeSettingsView",
    "AutoModRuleBrowserView",
    "AutoModPolicyEditorView",
    "AutoModChannelSelect",
    "AutoModChannelSettingsView",
    "AutoModChannelActionSelect",
    "AutoModStoredValueRemoveSelect",
    "AutoModStoredValueRemoveView",
    "AutoModImmunityUserSelect",
    "AutoModImmunityRoleSelect",
    "AutoModImmunityChannelSelect",
    "AutoModImmunityView",
    "SmartAutoModThresholdModal",
    "SmartAutoModPatternModal",
    "SmartAutoModExemptRoleSelect",
    "SmartAutoModExemptChannelSelect",
    "SmartAutoModSettingsView",
    "AutoModDashboardView",
    "AutoModCustomReportResponseModal",
    "AutoModReportResponseSelect",
    "AutoModReportResponseView",
    "AutoModReportModal",
    "AutoModWarningView",
    "build_automod_bridge_embed",
    "build_automod_dashboard_embed",
    "build_automod_immunity_embed",
    "build_automod_policy_embed",
]
