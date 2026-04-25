from __future__ import annotations

import json
from typing import Dict, Optional

import discord

from modules.mbx_branding import BRANDING_UNSET, apply_guild_member_branding
from modules.mbx_constants import FEATURE_FLAG_LABELS, SCOPE_SYSTEM
from modules.mbx_context import bot
from modules.mbx_embeds import make_confirmation_embed, make_embed
from modules.mbx_onboarding import (
    CHANNEL_FIELDS,
    LOG_FIELDS,
    PANEL_CAPABILITIES,
    WIZARD_STEPS,
    WizardSession,
    advance,
    back,
    build_review_lines,
    finalize_session,
    map_role_to_capabilities,
    persist_draft,
    set_branding_options,
    set_channel,
    set_feature_flags,
    set_modmail_options,
    set_panel_overrides,
    set_permissions_payload,
    set_roles_use_open_access,
    set_template,
)
from modules.mbx_permission_engine import CAPABILITIES, default_permission_payload
from modules.mbx_templates import list_templates
from modules.mbx_utils import truncate_text
from ui.shared import ExpirableMixin


CAPABILITY_BUNDLES: Dict[str, tuple[str, ...]] = {
    "moderator": (
        "mod.case_panel", "mod.history", "mod.punish", "mod.undo", "mod.active",
        "modmail.reply", "modmail.claim", "modmail.close", "automod.view",
        "automod.respond", "system.status",
    ),
    "senior_mod": (
        "mod.case_panel", "mod.history", "mod.punish", "mod.public_punish",
        "mod.undo", "mod.purge", "mod.lock", "mod.active", "mod.appeals",
        "modmail.reply", "modmail.claim", "modmail.close", "modmail.canned",
        "automod.view", "automod.respond", "system.status",
    ),
    "support": ("modmail.reply", "modmail.claim", "modmail.close", "modmail.canned", "system.status"),
    "admin": tuple(sorted(CAPABILITIES)),
    "roles": ("roles.use", "roles.admin", "roles.settings"),
}


class TemplateSelect(discord.ui.Select):
    def __init__(self, session: WizardSession):
        options = [
            discord.SelectOption(
                label=template.name,
                value=template.id,
                description=truncate_text(template.summary, 100),
                default=template.id == session.template_id,
            )
            for template in list_templates()
        ]
        super().__init__(placeholder="Choose a setup template...", min_values=1, max_values=1, options=options, row=0)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        try:
            set_template(self.session, self.values[0])
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class ChannelFieldSelect(discord.ui.Select):
    def __init__(self, session: WizardSession, *, log_fields: bool = False):
        fields = LOG_FIELDS if log_fields else CHANNEL_FIELDS
        self.selection_key = "_selected_log_field" if log_fields else "_selected_channel_field"
        current = _selected_channel_field(session, log_fields=log_fields)
        options = [
            discord.SelectOption(label=label, value=key, default=key == current)
            for key, label in fields
        ]
        super().__init__(placeholder="Choose which channel setting to edit...", min_values=1, max_values=1, options=options, row=0)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        self.session.staging_config[self.selection_key] = self.values[0]
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class WizardChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, session: WizardSession, *, log_fields: bool = False):
        key = _selected_channel_field(session, log_fields=log_fields)
        channel_types = [discord.ChannelType.category] if key == "category_archive" else [
            discord.ChannelType.text,
            discord.ChannelType.news,
            discord.ChannelType.public_thread,
            discord.ChannelType.private_thread,
        ]
        super().__init__(placeholder="Select the Discord channel/category...", min_values=1, max_values=1, channel_types=channel_types, row=1)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        key = _selected_channel_field(self.session, log_fields=self.session.step.key == "logs")
        channel = self.values[0]
        error = _validate_channel(interaction.guild, channel)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        set_channel(self.session, key, channel.id)
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class ModmailOptionsModal(discord.ui.Modal, title="Modmail Defaults"):
    sla = discord.ui.TextInput(label="SLA minutes", placeholder="60", max_length=5)
    cooldown = discord.ui.TextInput(label="DM prompt cooldown minutes", placeholder="30", max_length=5)
    discussion_threads = discord.ui.TextInput(label="Discussion threads (yes/no)", placeholder="yes", max_length=5)
    dm_prompt = discord.ui.TextInput(label="DM modmail prompt (yes/no)", placeholder="yes", max_length=5)

    def __init__(self, session: WizardSession):
        super().__init__()
        self.session = session
        cfg = session.staging_config
        self.sla.default = str(cfg.get("modmail_sla_minutes", 60))
        self.cooldown.default = str(cfg.get("dm_modmail_panel_cooldown_minutes", 30))
        self.discussion_threads.default = "yes" if cfg.get("modmail_discussion_threads", True) else "no"
        self.dm_prompt.default = "yes" if cfg.get("feature_flags", {}).get("dm_modmail_prompt", True) else "no"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            set_modmail_options(
                self.session,
                sla_minutes=int(self.sla.value.strip()),
                dm_prompt_cooldown_minutes=int(self.cooldown.value.strip()),
                discussion_threads=_parse_bool(self.discussion_threads.value),
                dm_prompt=_parse_bool(self.dm_prompt.value),
            )
        except (TypeError, ValueError) as exc:
            await interaction.response.send_message(f"Invalid modmail settings: {exc}", ephemeral=True)
            return
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class BrandingModal(discord.ui.Modal, title="Server Branding"):
    display_name = discord.ui.TextInput(label="Display name", required=False, max_length=32)
    color = discord.ui.TextInput(label="Embed color hex", required=False, placeholder="#ff9900", max_length=7)
    avatar_url = discord.ui.TextInput(label="Avatar URL", required=False, max_length=300)
    banner_url = discord.ui.TextInput(label="Modmail banner URL", required=False, max_length=300)

    def __init__(self, session: WizardSession):
        super().__init__()
        self.session = session
        branding = session.staging_config.get("_branding", {})
        self.display_name.default = branding.get("display_name", "")
        self.color.default = branding.get("embed_color", "")
        self.avatar_url.default = branding.get("avatar_url", "")
        self.banner_url.default = branding.get("modmail_banner_url", "")

    async def on_submit(self, interaction: discord.Interaction):
        color = self.color.value.strip()
        if color and not _valid_hex_color(color):
            await interaction.response.send_message("Color must look like #ff9900.", ephemeral=True)
            return
        set_branding_options(
            self.session,
            display_name=self.display_name.value,
            color=color,
            avatar_url=self.avatar_url.value,
            banner_url=self.banner_url.value,
        )
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class PermissionRoleSelect(discord.ui.RoleSelect):
    def __init__(self, session: WizardSession):
        super().__init__(placeholder="Select a Discord role to map...", min_values=1, max_values=1, row=0)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        self.session.staging_config["_selected_permission_role"] = role.id
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class CapabilityBundleSelect(discord.ui.Select):
    def __init__(self, session: WizardSession):
        options = [
            discord.SelectOption(label="Moderator", value="moderator", description="Case, punish, modmail, AutoMod response"),
            discord.SelectOption(label="Senior Moderator", value="senior_mod", description="Moderator plus purge, lock, appeals, public punish"),
            discord.SelectOption(label="Support", value="support", description="Modmail-only support workflow"),
            discord.SelectOption(label="Role Manager", value="roles", description="Custom role management"),
            discord.SelectOption(label="Administrator", value="admin", description="All capabilities"),
        ]
        super().__init__(placeholder="Choose a capability bundle for the selected role...", min_values=1, max_values=1, options=options, row=1)
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        role_id = self.session.staging_config.get("_selected_permission_role")
        if not role_id:
            await interaction.response.send_message("Select a role first.", ephemeral=True)
            return
        map_role_to_capabilities(self.session, int(role_id), CAPABILITY_BUNDLES[self.values[0]])
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class PermissionsJsonModal(discord.ui.Modal, title="Permission Payload JSON"):
    payload = discord.ui.TextInput(label="permissions JSON", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, session: WizardSession):
        super().__init__()
        self.session = session
        self.payload.default = json.dumps(session.staging_config.get("permissions") or default_permission_payload(), indent=2)[:4000]

    async def on_submit(self, interaction: discord.Interaction):
        try:
            set_permissions_payload(self.session, json.loads(self.payload.value))
        except Exception as exc:
            await interaction.response.send_message(f"Invalid permissions JSON: {exc}", ephemeral=True)
            return
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class FeatureFlagSelect(discord.ui.Select):
    def __init__(self, session: WizardSession):
        flags = session.staging_config.get("feature_flags", {})
        options = [
            discord.SelectOption(
                label=FEATURE_FLAG_LABELS.get(key, key.replace("_", " ").title()),
                value=key,
                default=bool(value),
            )
            for key, value in sorted(flags.items())
        ]
        if not options:
            options = [discord.SelectOption(label="No template features", value="__none__", default=True)]
        super().__init__(
            placeholder="Select enabled features...",
            min_values=0 if options[0].value != "__none__" else 1,
            max_values=len(options),
            options=options[:25],
            row=0,
        )
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        if "__none__" not in self.values:
            set_feature_flags(self.session, self.values)
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class PanelOverrideModal(discord.ui.Modal, title="Panel Visibility JSON"):
    payload = discord.ui.TextInput(label="panel capability map", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, session: WizardSession):
        super().__init__()
        self.session = session
        panel_overrides = (session.staging_config.get("permissions") or {}).get("panel_overrides") or {}
        current = {
            panel: data.get("required_capability")
            for panel, data in panel_overrides.items()
            if isinstance(data, dict)
        } or PANEL_CAPABILITIES
        self.payload.default = json.dumps(current, indent=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.payload.value)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            set_panel_overrides(self.session, data)
        except Exception as exc:
            await interaction.response.send_message(f"Invalid panel override JSON: {exc}", ephemeral=True)
            return
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class EscalationMatrixModal(discord.ui.Modal, title="Moderation Defaults"):
    payload = discord.ui.TextInput(label="escalation_matrix JSON", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, session: WizardSession):
        super().__init__()
        self.session = session
        self.payload.default = json.dumps(session.staging_config.get("escalation_matrix") or [], indent=2)[:4000]

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.payload.value)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array.")
        except Exception as exc:
            await interaction.response.send_message(f"Invalid escalation matrix JSON: {exc}", ephemeral=True)
            return
        self.session.staging_config["escalation_matrix"] = data
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))


class OnboardingWizardView(ExpirableMixin, discord.ui.View):
    def __init__(self, session: WizardSession):
        super().__init__(timeout=900)
        self.session = session
        self._build_items()

    def _build_items(self) -> None:
        step = self.session.step.key
        if step == "welcome":
            self.add_item(TemplateSelect(self.session))
        elif step == "channels":
            self.add_item(ChannelFieldSelect(self.session))
            self.add_item(WizardChannelSelect(self.session))
        elif step == "logs":
            self.add_item(ChannelFieldSelect(self.session, log_fields=True))
            self.add_item(WizardChannelSelect(self.session, log_fields=True))
        elif step == "permissions":
            self.add_item(PermissionRoleSelect(self.session))
            self.add_item(CapabilityBundleSelect(self.session))
        elif step == "features":
            self.add_item(FeatureFlagSelect(self.session))
        self.previous_step.disabled = self.session.step_index == 0
        self.next_step.disabled = step in {"review", "done"}
        self.apply.disabled = step != "review"

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4)
    async def previous_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        back(self.session)
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, row=4)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key == "review":
            await interaction.response.send_message("Use Apply to finalize this setup.", ephemeral=True)
            return
        errors = advance(self.session, guild=interaction.guild)
        if errors:
            await interaction.response.send_message("\n".join(f"- {error}" for error in errors), ephemeral=True)
            return
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))

    @discord.ui.button(label="Save", style=discord.ButtonStyle.secondary, row=4)
    async def save_progress(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _save_draft(self.session)
        await interaction.response.send_message("Progress saved. Run `/start` again to resume.", ephemeral=True)

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.success, row=4)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "review":
            await interaction.response.send_message("Review the wizard summary before applying.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        finalize_session(bot.data_manager.config, self.session)
        await bot.data_manager.save_config()

        branding = self.session.staging_config.get("_branding") or {}
        branding_error = None
        if branding:
            branding_error = await apply_guild_member_branding(
                interaction.guild,
                display_name=branding.get("display_name", BRANDING_UNSET),
                avatar_url=branding.get("avatar_url", BRANDING_UNSET),
                banner_url=branding.get("modmail_banner_url", BRANDING_UNSET),
                reason=f"/start branding by {interaction.user}",
            )

        sessions = getattr(bot, "start_wizard_sessions", {})
        sessions.pop(self.session.key, None)
        embed = make_confirmation_embed(
            "Setup Complete",
            "> Setup has been applied. Use `/setup` and `/config` for later edits.",
            scope=SCOPE_SYSTEM,
            guild=interaction.guild,
        )
        if branding_error:
            embed.add_field(name="Branding Note", value=branding_error, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=4)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.data_manager.config.pop("_onboarding_draft", None)
        await bot.data_manager.save_config()
        getattr(bot, "start_wizard_sessions", {}).pop(self.session.key, None)
        await interaction.response.edit_message(
            embed=make_embed("Setup Cancelled", "> The saved onboarding draft was removed.", kind="warning", scope=SCOPE_SYSTEM, guild=interaction.guild),
            view=None,
        )

    @discord.ui.button(label="Edit Modmail", style=discord.ButtonStyle.secondary, row=2)
    async def edit_modmail(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "modmail":
            await interaction.response.send_message("Open the Modmail step first.", ephemeral=True)
            return
        await interaction.response.send_modal(ModmailOptionsModal(self.session))

    @discord.ui.button(label="Edit Branding", style=discord.ButtonStyle.secondary, row=2)
    async def edit_branding(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "branding":
            await interaction.response.send_message("Open the Branding step first.", ephemeral=True)
            return
        await interaction.response.send_modal(BrandingModal(self.session))

    @discord.ui.button(label="Edit Permissions JSON", style=discord.ButtonStyle.secondary, row=2)
    async def edit_permissions_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "permissions":
            await interaction.response.send_message("Open the Permission Groups step first.", ephemeral=True)
            return
        await interaction.response.send_modal(PermissionsJsonModal(self.session))

    @discord.ui.button(label="Edit Escalation", style=discord.ButtonStyle.secondary, row=2)
    async def edit_escalation(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "moderation":
            await interaction.response.send_message("Open the Moderation Defaults step first.", ephemeral=True)
            return
        await interaction.response.send_modal(EscalationMatrixModal(self.session))

    @discord.ui.button(label="Toggle Roles Access", style=discord.ButtonStyle.secondary, row=3)
    async def toggle_roles_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "permissions":
            await interaction.response.send_message("Open the Permission Groups step first.", ephemeral=True)
            return
        permissions = self.session.staging_config.setdefault("permissions", default_permission_payload())
        role_caps = permissions.setdefault("role_capabilities", {})
        current = "roles.use" in set(role_caps.get(str(self.session.guild_id)) or [])
        set_roles_use_open_access(self.session, open_access=not current)
        await _save_draft(self.session)
        await interaction.response.edit_message(embed=build_onboarding_embed(interaction.guild, self.session), view=OnboardingWizardView(self.session))

    @discord.ui.button(label="Edit Panels", style=discord.ButtonStyle.secondary, row=3)
    async def edit_panels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.step.key != "panels":
            await interaction.response.send_message("Open the Control Panels step first.", ephemeral=True)
            return
        await interaction.response.send_modal(PanelOverrideModal(self.session))


def build_onboarding_embed(guild: discord.Guild, session: WizardSession) -> discord.Embed:
    step = session.step
    embed = make_embed(
        f"/start Setup - {step.title}",
        f"> Step {session.step_index + 1} of {len(WIZARD_STEPS)}\n> {step.summary}",
        kind="info" if step.key != "done" else "success",
        scope=SCOPE_SYSTEM,
        guild=guild,
    )

    if step.key == "welcome":
        embed.add_field(name="Template", value=f"`{session.template_id or 'Not selected'}`", inline=False)
    elif step.key in {"channels", "logs"}:
        fields = LOG_FIELDS if step.key == "logs" else CHANNEL_FIELDS
        embed.add_field(name="Selected Field", value=f"`{_selected_channel_field(session, log_fields=step.key == 'logs')}`", inline=True)
        embed.add_field(name="Current Values", value=_format_channels(session, fields), inline=False)
    elif step.key == "modmail":
        flags = session.staging_config.get("feature_flags", {})
        embed.add_field(
            name="Defaults",
            value="\n".join([
                f"SLA: `{session.staging_config.get('modmail_sla_minutes', 60)} min`",
                f"DM Cooldown: `{session.staging_config.get('dm_modmail_panel_cooldown_minutes', 30)} min`",
                f"Discussion Threads: `{'On' if session.staging_config.get('modmail_discussion_threads', True) else 'Off'}`",
                f"DM Prompt: `{'On' if flags.get('dm_modmail_prompt', True) else 'Off'}`",
            ]),
            inline=False,
        )
    elif step.key == "branding":
        branding = session.staging_config.get("_branding", {})
        embed.add_field(
            name="Staged Branding",
            value="\n".join([
                f"Display Name: `{branding.get('display_name') or 'Keep current'}`",
                f"Color: `{branding.get('embed_color') or 'Keep current'}`",
                f"Avatar: `{branding.get('avatar_url') or 'Keep current'}`",
                f"Banner: `{branding.get('modmail_banner_url') or 'Keep current'}`",
            ]),
            inline=False,
        )
    elif step.key == "permissions":
        permissions = session.staging_config.get("permissions") or {}
        role_caps = permissions.get("role_capabilities") or {}
        open_roles = "roles.use" in set(role_caps.get(str(session.guild_id)) or [])
        embed.add_field(name="Role Maps", value=str(len(role_caps)), inline=True)
        embed.add_field(name="Self-Service Roles", value="Open to everyone" if open_roles else "Explicit grant required", inline=True)
        selected = session.staging_config.get("_selected_permission_role")
        embed.add_field(name="Selected Role", value=f"<@&{selected}>" if selected else "`None`", inline=False)
    elif step.key == "moderation":
        matrix = session.staging_config.get("escalation_matrix") or []
        embed.add_field(name="Escalation Steps", value=str(len(matrix)), inline=True)
    elif step.key == "features":
        flags = session.staging_config.get("feature_flags") or {}
        enabled = [FEATURE_FLAG_LABELS.get(k, k) for k, v in sorted(flags.items()) if v]
        embed.add_field(name="Enabled Features", value=truncate_text("\n".join(enabled) or "None", 1024), inline=False)
    elif step.key == "panels":
        overrides = (session.staging_config.get("permissions") or {}).get("panel_overrides") or {}
        embed.add_field(name="Panel Overrides", value=str(len(overrides)), inline=True)
    elif step.key in {"review", "done"}:
        embed.add_field(name="Summary", value=truncate_text("\n".join(build_review_lines(session)), 1024), inline=False)
    return embed


async def _save_draft(session: WizardSession) -> None:
    if bot.data_manager is None:
        return
    persist_draft(bot.data_manager.config, session)
    await bot.data_manager.save_config()


def _format_channels(session: WizardSession, fields) -> str:
    lines = []
    for key, label in fields:
        value = session.staging_config.get(key)
        lines.append(f"{label}: {f'<#{value}>' if value else '`Not set`'}")
    return "\n".join(lines)


def _selected_channel_field(session: WizardSession, *, log_fields: bool = False) -> str:
    fields = LOG_FIELDS if log_fields else CHANNEL_FIELDS
    selection_key = "_selected_log_field" if log_fields else "_selected_channel_field"
    selected = session.staging_config.get(selection_key)
    valid = {key for key, _label in fields}
    if selected not in valid:
        selected = fields[0][0]
    return selected


def _validate_channel(guild: discord.Guild, channel) -> Optional[str]:
    me = guild.me if guild else None
    if me is None or not hasattr(channel, "permissions_for"):
        return None
    perms = channel.permissions_for(me)
    if not getattr(perms, "view_channel", False):
        return "The bot cannot view that channel."
    if getattr(channel, "type", None) != discord.ChannelType.category and not getattr(perms, "send_messages", False):
        return "The bot cannot send messages in that channel."
    return None


def _parse_bool(value: str) -> bool:
    text = value.strip().lower()
    if text in {"y", "yes", "true", "on", "1"}:
        return True
    if text in {"n", "no", "false", "off", "0"}:
        return False
    raise ValueError("Use yes or no.")


def _valid_hex_color(value: str) -> bool:
    text = value.strip()
    return len(text) == 7 and text.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in text[1:])


__all__ = ["OnboardingWizardView", "build_onboarding_embed"]
