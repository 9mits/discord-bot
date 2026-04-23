from __future__ import annotations

import asyncio
import copy
import html
import io
import json
import logging
import re
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.http import Route

from modules.mbx_automod import *
from modules.mbx_cases import *
from modules.mbx_constants import *
from modules.mbx_context import abuse_system, bot, tree
from modules.mbx_embeds import *
from modules.mbx_embeds import (
    _build_footer_text,
    _build_footer_text_with_detail,
    _format_branding_panel_value,
    _get_branding_config,
    _get_footer_icon_url,
    _set_footer_branding,
)
from modules.mbx_formatters import *
from modules.mbx_images import *
from modules.mbx_images import (
    _format_image_size_limit,
    _is_public_image_ip,
    _make_image_data_uri,
    _resolve_image_host_addresses,
)
from modules.mbx_logging import *
from modules.mbx_logging import _send_log_to_channels
from modules.mbx_models import *
from modules.mbx_permissions import *
from modules.mbx_punish import build_punish_embed, execute_punishment
from modules.mbx_roles import *
from modules.mbx_services import *
from modules.mbx_utils import *
from ui.shared import ExpirableMixin
MAX_GUILD_MEMBER_BIO_LENGTH = 190


logger = logging.getLogger("MGXBot")


def _legacy_value(name: str):
    from modules import mbx_legacy

    return getattr(mbx_legacy, name)

def get_valid_duration(*args, **kwargs):
    return _legacy_value("get_valid_duration")(*args, **kwargs)

def build_mod_help_embed(*args, **kwargs):
    return _legacy_value("build_mod_help_embed")(*args, **kwargs)

def build_modmail_panel_embed(*args, **kwargs):
    return _legacy_value("build_modmail_panel_embed")(*args, **kwargs)

def build_modmail_settings_embed(*args, **kwargs):
    return _legacy_value("build_modmail_settings_embed")(*args, **kwargs)

def build_config_dashboard_embed(*args, **kwargs):
    return _legacy_value("build_config_dashboard_embed")(*args, **kwargs)

def build_rules_dashboard_embed(*args, **kwargs):
    return _legacy_value("build_rules_dashboard_embed")(*args, **kwargs)

def build_setup_dashboard_embed(*args, **kwargs):
    return _legacy_value("build_setup_dashboard_embed")(*args, **kwargs)

def build_feature_flags_embed(*args, **kwargs):
    return _legacy_value("build_feature_flags_embed")(*args, **kwargs)

def build_escalation_matrix_embed(*args, **kwargs):
    return _legacy_value("build_escalation_matrix_embed")(*args, **kwargs)

def build_canned_replies_embed(*args, **kwargs):
    return _legacy_value("build_canned_replies_embed")(*args, **kwargs)

def build_setup_validation_embed(*args, **kwargs):
    return _legacy_value("build_setup_validation_embed")(*args, **kwargs)

def build_status_embed(*args, **kwargs):
    return _legacy_value("build_status_embed")(*args, **kwargs)

def get_feature_flag_name(*args, **kwargs):
    return _legacy_value("get_feature_flag_name")(*args, **kwargs)

def send_modmail_thread_intro(*args, **kwargs):
    return _legacy_value("send_modmail_thread_intro")(*args, **kwargs)

def send_modmail_panel_message(*args, **kwargs):
    return _legacy_value("send_modmail_panel_message")(*args, **kwargs)

def maybe_send_dm_modmail_panel(*args, **kwargs):
    return _legacy_value("maybe_send_dm_modmail_panel")(*args, **kwargs)

def log_modmail_action(*args, **kwargs):
    return _legacy_value("log_modmail_action")(*args, **kwargs)

def apply_modmail_ticket_state(*args, **kwargs):
    return _legacy_value("apply_modmail_ticket_state")(*args, **kwargs)

def refresh_modmail_message(*args, **kwargs):
    return _legacy_value("refresh_modmail_message")(*args, **kwargs)

def refresh_modmail_ticket_log(*args, **kwargs):
    return _legacy_value("refresh_modmail_ticket_log")(*args, **kwargs)

def export_modmail_transcript(*args, **kwargs):
    return _legacy_value("export_modmail_transcript")(*args, **kwargs)

def resolve_modmail_user(*args, **kwargs):
    return _legacy_value("resolve_modmail_user")(*args, **kwargs)

def resolve_modmail_thread(*args, **kwargs):
    return _legacy_value("resolve_modmail_thread")(*args, **kwargs)

def _parse_user_id(*args, **kwargs):
    return _legacy_value("_parse_user_id")(*args, **kwargs)

def get_mod_cases(*args, **kwargs):
    return _legacy_value("get_mod_cases")(*args, **kwargs)

def get_staff_stats_embed(*args, **kwargs):
    return _legacy_value("get_staff_stats_embed")(*args, **kwargs)

def build_test_env_embed(*args, **kwargs):
    return _legacy_value("build_test_env_embed")(*args, **kwargs)

def log_case_management_action(*args, **kwargs):
    return _legacy_value("log_case_management_action")(*args, **kwargs)

def _split_case_input(*args, **kwargs):
    return _legacy_value("_split_case_input")(*args, **kwargs)

def get_public_execution_action_label(*args, **kwargs):
    return _legacy_value("get_public_execution_action_label")(*args, **kwargs)

def build_public_execution_embed(*args, **kwargs):
    return _legacy_value("build_public_execution_embed")(*args, **kwargs)

def execute_public_execution_vote(*args, **kwargs):
    return _legacy_value("execute_public_execution_vote")(*args, **kwargs)

def _refresh_branding_panel(*args, **kwargs):
    return _legacy_value("_refresh_branding_panel")(*args, **kwargs)

def apply_guild_member_branding(*args, **kwargs):
    return _legacy_value("apply_guild_member_branding")(*args, **kwargs)

def save_branding_settings(*args, **kwargs):
    return _legacy_value("save_branding_settings")(*args, **kwargs)

def build_branding_error_embed(*args, **kwargs):
    return _legacy_value("build_branding_error_embed")(*args, **kwargs)

def _build_branding_panel_embed(*args, **kwargs):
    return _legacy_value("_build_branding_panel_embed")(*args, **kwargs)

def show_punish_menu(*args, **kwargs):
    return _legacy_value("show_punish_menu")(*args, **kwargs)

def show_history_menu(*args, **kwargs):
    return _legacy_value("show_history_menu")(*args, **kwargs)

def show_case_panel(*args, **kwargs):
    return _legacy_value("show_case_panel")(*args, **kwargs)

def list_commands(*args, **kwargs):
    return _legacy_value("list_commands")(*args, **kwargs)

def _categorise_commands(*args, **kwargs):
    return _legacy_value("_categorise_commands")(*args, **kwargs)

def generate_transcript_html(*args, **kwargs):
    return _legacy_value("generate_transcript_html")(*args, **kwargs)

def is_staff(*args, **kwargs):
    return _legacy_value("is_staff")(*args, **kwargs)

def respond_with_error(*args, **kwargs):
    return _legacy_value("respond_with_error")(*args, **kwargs)

def resolve_member(*args, **kwargs):
    return _legacy_value("resolve_member")(*args, **kwargs)

def fetch_image_bytes(*args, **kwargs):
    return _legacy_value("fetch_image_bytes")(*args, **kwargs)

def fetch_image_data_uri(*args, **kwargs):
    return _legacy_value("fetch_image_data_uri")(*args, **kwargs)

class RuleEditModal(discord.ui.Modal, title="Add/Edit Punishment Rule"):
    rule_name = discord.ui.TextInput(label="Rule Name", placeholder="e.g. Spamming", max_length=50)
    base_dur = discord.ui.TextInput(label="Base Duration (mins)", placeholder="0=Warn, -1=Ban", max_length=10)
    esc_dur = discord.ui.TextInput(label="Escalated Duration (mins)", placeholder="Repeat offense duration", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.rule_name.value.strip()
        if not name:
            await interaction.response.send_message("Rule name cannot be empty.", ephemeral=True)
            return
            
        # Use parse_duration_str to allow "ban", "1d", "30m" etc.
        base = parse_duration_str(self.base_dur.value.strip())
        esc = parse_duration_str(self.esc_dur.value.strip())
            
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        rules[name] = {"base": base, "escalated": esc}
        bot.data_manager.config["punishment_rules"] = rules
        await bot.data_manager.save_config()
        
        # Log
        log_embed = make_embed(
            "Punishment Rule Updated",
            "> An escalation rule was created or overwritten from the rules dashboard.",
            kind="info",
            scope=SCOPE_SYSTEM,
            guild=interaction.guild,
        )
        log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
        log_embed.add_field(name="Rule", value=name, inline=True)
        log_embed.add_field(name="Values", value=f"> Base: {base}m\n> Escalated: {esc}m", inline=True)
        await send_log(interaction.guild, log_embed)
        
        await interaction.response.send_message(f"Rule **{name}** saved successfully.", ephemeral=True)

class ActiveSelect(discord.ui.Select):
    def __init__(self, active_list):
        self.active_list = active_list
        options = []
        for idx, (uid, rec, expiry, case_num, name) in enumerate(active_list[:25]):
            reason = rec.get("reason", "Unknown")
            label = f"{name} ({get_case_label(rec, case_num)})"
            if len(label) > 100: label = label[:100]
            
            dur = rec.get("duration_minutes", 0)
            p_type = rec.get("type", "timeout")
            
            if dur == -1:
                desc = f"Banned • {reason}"
            elif dur > 0:
                remaining = expiry - discord.utils.utcnow()
                if remaining.days > 0:
                    rem_str = f"{remaining.days}d"
                else:
                    hours = remaining.seconds // 3600
                    if hours > 0:
                        rem_str = f"{hours}h"
                    else:
                        rem_str = f"{remaining.seconds // 60}m"
                desc = f"{'Tempban' if p_type=='ban' else 'Timeout'} • Expires in {rem_str}"
            
            if len(desc) > 100: desc = desc[:97] + "..."
            options.append(discord.SelectOption(label=label, description=desc, value=str(idx)))
            
        super().__init__(placeholder="Select active punishment to view details...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        uid, rec, expiry, case_num, name = self.active_list[idx]

        embed = make_embed(
            f"{get_case_label(rec, case_num)} Active Details",
            "> Current punishment state, timing, and staff notes.",
            kind="danger",
            scope=SCOPE_MODERATION,
            guild=interaction.guild,
        )

        embed.add_field(name="User", value=f"<@{uid}> (`{uid}`)", inline=True)

        mod_id = rec.get("moderator")
        embed.add_field(name="Moderator", value=f"<@{mod_id}> (`{mod_id}`)", inline=True)
        embed.add_field(name="Action", value=describe_punishment_record(rec), inline=True)
        embed.add_field(name="Violation", value=format_reason_value(rec.get("reason", "Unknown"), limit=250), inline=False)

        dur = rec.get("duration_minutes")
        if dur == -1:
            exp_str = "Never"
        else:
            exp_str = discord.utils.format_dt(expiry, "F")
        embed.add_field(name="Expires", value=exp_str, inline=True)
        if rec.get("escalated", False):
            embed.add_field(name="Escalated", value="Yes", inline=True)

        note = truncate_text(str(rec.get("note") or "").strip(), 1000)
        if note:
            embed.add_field(name="Internal Note", value=format_log_quote(note, limit=1000), inline=False)

        user_msg = rec.get("user_msg")
        if user_msg:
            embed.add_field(name="Message to User", value=format_log_quote(user_msg, limit=1000), inline=False)

        await interaction.response.edit_message(embed=embed, view=self.view)

class ActiveView(ExpirableMixin, discord.ui.View):
    def __init__(self, active_list):
        super().__init__(timeout=180)
        self.add_item(ActiveSelect(active_list))

class AccessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role to toggle access...", min_values=1, max_values=1)
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]
        rid = role.id
        mod_roles = bot.data_manager.config.get("mod_roles", [])
        
        if rid in mod_roles:
            mod_roles.remove(rid)
            action = "removed from"
        else:
            mod_roles.append(rid)
            action = "added to"
            
        bot.data_manager.config["mod_roles"] = mod_roles
        await bot.data_manager.save_config()
        
        # Log
        log_embed = make_embed(
            "Moderator Access Updated",
            "> The list of roles with moderation access was changed.",
            kind="info",
            scope=SCOPE_SYSTEM,
            guild=interaction.guild,
        )
        log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
        log_embed.add_field(name="Role", value=f"{role.mention} (`{role.id}`)", inline=True)
        log_embed.add_field(name="Action", value=action.capitalize(), inline=True)
        await send_log(interaction.guild, log_embed)
        
        mentions = [f"<@&{r}>" for r in mod_roles]
        desc = "**Allowed Mod Roles:**\n" + ", ".join(mentions) if mentions else "No specific roles configured (Admins & Mods allowed)."
        
        if interaction.message:
            embed = interaction.message.embeds[0]
            embed.description = f"> {desc}"
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(view=self)
            
        await interaction.followup.send(f"Role {role.mention} {action} mod access.", ephemeral=True)

class RuleDeleteSelect(discord.ui.Select):
    def __init__(self):
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        options = [discord.SelectOption(label=r) for r in list(rules.keys())[:25]]
        if not options:
            options = [discord.SelectOption(label="No rules found", value="none")]
        super().__init__(placeholder="Select rule to delete...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No rules to delete.", ephemeral=True)
            return
            
        name = self.values[0]
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        if name in rules:
            del rules[name]
            bot.data_manager.config["punishment_rules"] = rules
            await bot.data_manager.save_config()
            
            # Log
            log_embed = make_embed(
                "Punishment Rule Deleted",
                "> A punishment escalation rule was removed from the dashboard.",
                kind="danger",
                scope=SCOPE_SYSTEM,
                guild=interaction.guild,
            )
            log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
            log_embed.add_field(name="Rule", value=name, inline=True)
            await send_log(interaction.guild, log_embed)
            
            await interaction.response.send_message(f"Rule **{name}** deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("Rule not found.", ephemeral=True)

class RuleDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RuleDeleteSelect())

class RuleSelectForEdit(discord.ui.Select):
    def __init__(self):
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        options = []
        for name in list(rules.keys())[:25]:
            data = rules[name]
            desc = f"{format_duration(data['base'])} -> {format_duration(data['escalated'])}"
            options.append(discord.SelectOption(label=name, value=name, description=desc))
        
        if not options:
            options = [discord.SelectOption(label="No rules found", value="none")]
            
        super().__init__(placeholder="Select rule to edit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No rules to edit.", ephemeral=True)
            return
            
        name = self.values[0]
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        if name in rules:
            data = rules[name]
            modal = RuleEditModal()
            modal.rule_name.default = name
            # Fix: Display "Ban" instead of -1
            modal.base_dur.default = "Ban" if data['base'] == -1 else str(data['base'])
            modal.esc_dur.default = "Ban" if data['escalated'] == -1 else str(data['escalated'])
            
            modal.title = f"Edit Rule: {name}"[:45]
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("Rule not found.", ephemeral=True)

class RuleSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RuleSelectForEdit())

class ArchiveConfirmView(discord.ui.View):
    def __init__(self, channel, target_cat, old_name, new_name, overwrites_save_data, final_overwrites):
        super().__init__(timeout=120)
        self.channel = channel
        self.target_cat = target_cat
        self.old_name = old_name
        self.new_name = new_name
        self.overwrites_save_data = overwrites_save_data
        self.final_overwrites = final_overwrites

    @discord.ui.button(label="Yes, Archive", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable view immediately to prevent double-clicks
        await interaction.response.edit_message(content="> Processing archive request...", view=None)
        
        # Save Config
        if "archived_channels" not in bot.data_manager.config: bot.data_manager.config["archived_channels"] = {}
        bot.data_manager.config["archived_channels"][str(self.channel.id)] = {
            "original_name": self.old_name,
            "category_id": self.channel.category_id,
            "overwrites": self.overwrites_save_data
        }
        await bot.data_manager.save_config()

        try:
            # Combine operations to reduce API calls and avoid rate limits (1 call vs 2)
            await self.channel.edit(
                name=self.new_name,
                category=self.target_cat,
                overwrites=self.final_overwrites,
                reason=f"Archived by {interaction.user}"
            )
                
        except Exception as e:
            await interaction.followup.send(f"Failed to archive channel: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Channel archived successfully to **{self.target_cat.name}**.", ephemeral=True)

        # Log
        log_embed = make_embed(
            "Channel Archived",
            "> A live channel was archived and moved into the configured archive category.",
            kind="info",
            scope=SCOPE_SYSTEM,
            guild=interaction.guild,
        )
        log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
        log_embed.add_field(name="Original Name", value=self.old_name, inline=True)
        log_embed.add_field(name="Archived Name", value=self.new_name, inline=True)
        log_embed.add_field(name="Category", value=f"{self.target_cat.name} (`{self.target_cat.id}`)", inline=False)
        await send_log(interaction.guild, log_embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Archive operation cancelled.", view=None)
        self.stop()

class CloneConfirmView(discord.ui.View):
    def __init__(self, channel, target_cat, old_name, new_name, overwrites_save_data, final_overwrites):
        super().__init__(timeout=120)
        self.channel = channel
        self.target_cat = target_cat
        self.old_name = old_name
        self.new_name = new_name
        self.overwrites_save_data = overwrites_save_data
        self.final_overwrites = final_overwrites

    @discord.ui.button(label="Yes, Clone & Archive", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="> Processing clone & archive request...", view=None)
        
        # 1. Clone the channel
        try:
            new_channel = await self.channel.clone(reason=f"Cloned by {interaction.user}")
            await new_channel.edit(position=self.channel.position)
        except Exception as e:
            await interaction.followup.send(f"Failed to clone channel: {e}", ephemeral=True)
            return

        # 2. Archive the old channel
        if "archived_channels" not in bot.data_manager.config: bot.data_manager.config["archived_channels"] = {}
        bot.data_manager.config["archived_channels"][str(self.channel.id)] = {
            "original_name": self.old_name,
            "category_id": self.channel.category_id,
            "overwrites": self.overwrites_save_data
        }
        await bot.data_manager.save_config()

        try:
            await self.channel.edit(
                name=self.new_name,
                category=self.target_cat,
                overwrites=self.final_overwrites,
                reason=f"Archived (Cloned) by {interaction.user}"
            )
        except Exception as e:
            await interaction.followup.send(f"Channel cloned to {new_channel.mention}, but failed to archive old channel: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Success! Channel cloned to {new_channel.mention} and original archived.", ephemeral=True)
        
        try:
            embed = make_embed(
                "Channel Renewed",
                "> This channel was refreshed from a clean clone while the previous version was archived.",
                kind="success",
                scope=SCOPE_SYSTEM,
                guild=interaction.guild,
            )
            embed.add_field(name="Handled By", value=interaction.user.display_name, inline=True)
            await new_channel.send(embed=embed)
        except Exception:
            pass

        # Log
        log_embed = make_embed(
            "Channel Cloned and Archived",
            "> The original channel was archived and a fresh replacement was created.",
            kind="info",
            scope=SCOPE_SYSTEM,
            guild=interaction.guild,
        )
        log_embed.add_field(name="Actor", value=format_user_ref(interaction.user), inline=True)
        log_embed.add_field(name="Archived Channel", value=f"{self.channel.mention} (`{self.channel.id}`)", inline=True)
        log_embed.add_field(name="Fresh Clone", value=f"{new_channel.mention} (`{new_channel.id}`)", inline=True)
        await send_log(interaction.guild, log_embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Clone operation cancelled.", view=None)
        self.stop()

class RulesDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="List Rules", style=discord.ButtonStyle.primary)
    async def list_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        lines = []
        for name, data in rules.items():
            b = format_duration(data['base'])
            e = format_duration(data['escalated'])
            lines.append(f"**{name}**: {b} -> {e}")

        embed = make_embed(
            "Punishment Rules",
            "> Current automated escalation baselines used by the moderation console.",
            kind="info",
            scope=SCOPE_MODERATION,
            guild=interaction.guild,
        )
        embed.add_field(name="Configured Rules", value=truncate_text("\n".join(lines) or "No rules configured.", 4000), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Add Rule", style=discord.ButtonStyle.success)
    async def add_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RuleEditModal()
        modal.title = "Add New Rule"
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Rule", style=discord.ButtonStyle.secondary)
    async def edit_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select rule to edit:", view=RuleSelectView(), ephemeral=True)

    @discord.ui.button(label="Delete Rule", style=discord.ButtonStyle.danger)
    async def delete_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Select rule to delete:", view=RuleDeleteView(), ephemeral=True)

class ConfigImportModal(discord.ui.Modal, title="Paste Settings Backup"):
    config_json = discord.ui.TextInput(
        label="Settings JSON",
        style=discord.TextStyle.paragraph,
        placeholder='{"feature_flags": {...}}',
        required=True,
        max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            payload = json.loads(self.config_json.value)
            if not isinstance(payload, dict):
                raise ValueError("Config import payload must be a JSON object.")
        except Exception as exc:
            await respond_with_error(interaction, f"Invalid config JSON: {exc}", scope=SCOPE_SYSTEM)
            return

        merged, warnings = import_config_payload(bot.data_manager.config, payload)
        bot.data_manager.config = merged
        bot.data_manager._configure_cache_limits()
        await bot.data_manager.save_config()
        description = "> Settings were imported successfully."
        if warnings:
            description += "\n> " + "\n> ".join(warnings)
        await interaction.response.send_message(
            embed=make_confirmation_embed("Settings Imported", description, scope=SCOPE_SYSTEM, guild=interaction.guild),
            ephemeral=True,
        )

class ConfigDashboardActionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Download Settings", value="export", description="Export a safe JSON backup of the current settings."),
            discord.SelectOption(label="Paste Settings", value="import", description="Import a settings backup from raw JSON."),
            discord.SelectOption(label="Feature Toggles", value="features", description="Turn bot features on or off."),
            discord.SelectOption(label="Punishment Scaling", value="scaling", description="Edit the escalation matrix used by punishments."),
            discord.SelectOption(label="Saved Replies", value="replies", description="Manage canned replies used in modmail."),
        ]
        super().__init__(
            placeholder="Choose a settings action...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "export":
            payload = export_config_payload(bot.data_manager.config)
            buffer = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
            file = discord.File(buffer, filename="mbx-config-export.json")
            await interaction.response.send_message(
                embed=make_confirmation_embed(
                    "Settings Backup Ready",
                    "> A safe settings backup was generated successfully.",
                    scope=SCOPE_SYSTEM,
                    guild=interaction.guild,
                ),
                file=file,
                ephemeral=True,
            )
            return
        if action == "import":
            await interaction.response.send_modal(ConfigImportModal())
            return
        if action == "features":
            await interaction.response.send_message(embed=build_feature_flags_embed(interaction.guild), view=FeatureFlagView(), ephemeral=True)
            return
        if action == "scaling":
            await interaction.response.send_message(embed=build_escalation_matrix_embed(interaction.guild), view=EscalationMatrixView(), ephemeral=True)
            return
        if action == "replies":
            await interaction.response.send_message(embed=build_canned_replies_embed(interaction.guild), view=CannedRepliesView(), ephemeral=True)

class ConfigDashboardView(ExpirableMixin, discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ConfigDashboardActionSelect())

class SetupDashboardActionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Modmail Settings", value="modmail", description="Open the modmail behavior controls."),
            discord.SelectOption(label="Validate Setup", value="validate", description="Run the configuration validation checks."),
        ]
        super().__init__(
            placeholder="Choose another setup action...",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "modmail":
            await interaction.response.send_message(
                embed=build_modmail_settings_embed(interaction.guild),
                view=ModmailSettingsView(),
                ephemeral=True,
            )
            return
        if action == "validate":
            if not get_feature_flag(bot.data_manager.config, "setup_validation", True):
                await respond_with_error(interaction, "The setup check is currently turned off in the feature settings.", scope=SCOPE_SYSTEM)
                return
            me = interaction.guild.me or interaction.guild.get_member(bot.user.id)
            if not me:
                await respond_with_error(interaction, "The bot member object could not be resolved for validation.", scope=SCOPE_SYSTEM)
                return
            findings = validate_guild_configuration(bot.data_manager.config, interaction.guild, me)
            await interaction.response.send_message(embed=build_setup_validation_embed(interaction.guild, findings), ephemeral=True)

class SetupDashboardView(ExpirableMixin, discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ConfigTypeSelect("roles", row=0))
        self.add_item(ConfigTypeSelect("channels", row=1))
        self.add_item(SetupDashboardActionSelect())

class FeatureFlagSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for key, enabled in sorted(bot.data_manager.config.get("feature_flags", {}).items()):
            options.append(
                discord.SelectOption(
                    label=get_feature_flag_name(key),
                    value=key,
                    description=f"Currently {'on' if enabled else 'off'}",
                )
            )
        super().__init__(placeholder="Choose a feature to turn on or off...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        flags = bot.data_manager.config.setdefault("feature_flags", {})
        flags[key] = not bool(flags.get(key, False))
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_feature_flags_embed(interaction.guild), view=FeatureFlagView())

class FeatureFlagView(ExpirableMixin, discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(FeatureFlagSelect())

class EscalationMatrixModal(discord.ui.Modal, title="Edit Punishment Scaling"):
    matrix_json = discord.ui.TextInput(
        label="Punishment Scaling JSON",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    def __init__(self):
        super().__init__()
        self.matrix_json.default = json.dumps(bot.data_manager.config.get("escalation_matrix", DEFAULT_ESCALATION_MATRIX), indent=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            payload = json.loads(self.matrix_json.value)
            if not isinstance(payload, list):
                raise ValueError("Matrix must be a JSON array.")
        except Exception as exc:
            await respond_with_error(interaction, f"Invalid punishment scaling JSON: {exc}", scope=SCOPE_SYSTEM)
            return

        bot.data_manager.config["escalation_matrix"] = payload
        await bot.data_manager.save_config()
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                "Punishment Scaling Saved",
                "> The punishment scaling settings were updated successfully.",
                scope=SCOPE_SYSTEM,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )

class EscalationMatrixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Edit JSON", style=discord.ButtonStyle.primary)
    async def edit_matrix(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EscalationMatrixModal())

    @discord.ui.button(label="Reset Defaults", style=discord.ButtonStyle.secondary)
    async def reset_matrix(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot.data_manager.config["escalation_matrix"] = json.loads(json.dumps(DEFAULT_ESCALATION_MATRIX))
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_escalation_matrix_embed(interaction.guild), view=self)

class CannedReplyModal(discord.ui.Modal, title="Save Quick Reply"):
    template_name = discord.ui.TextInput(label="Template Name", placeholder="Acknowledged", max_length=60)
    reply_body = discord.ui.TextInput(label="Reply Body", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        replies = bot.data_manager.config.setdefault("modmail_canned_replies", {})
        replies[self.template_name.value.strip()] = self.reply_body.value.strip()
        await bot.data_manager.save_config()
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                "Quick Reply Saved",
                "> The saved reply is now available in modmail.",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )

class CannedRepliesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Add or Update Saved Reply", style=discord.ButtonStyle.primary)
    async def add_reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CannedReplyModal())

class ConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, config_key: str, config_name: str):
        super().__init__(placeholder=f"Select {config_name}...", min_values=1, max_values=1)
        self.config_key = config_key
        self.config_name = config_name

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        bot.data_manager.config[self.config_key] = role.id
        await bot.data_manager.save_config()
        await interaction.response.send_message(f"**{self.config_name}** updated to {role.mention}", ephemeral=True)

class MultiConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self, config_key: str, config_name: str):
        super().__init__(placeholder=f"Select {config_name}...", min_values=1, max_values=25)
        self.config_key = config_key
        self.config_name = config_name

    async def callback(self, interaction: discord.Interaction):
        roles = self.values
        role_ids = [r.id for r in roles]
        bot.data_manager.config[self.config_key] = role_ids
        await bot.data_manager.save_config()
        mentions = ", ".join([r.mention for r in roles])
        await interaction.response.send_message(f"**{self.config_name}** updated to: {mentions}", ephemeral=True)

class ConfigChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, config_key: str, config_name: str, channel_types=None):
        super().__init__(placeholder=f"Select {config_name}...", min_values=1, max_values=1, channel_types=channel_types)
        self.config_key = config_key
        self.config_name = config_name

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        channel = interaction.guild.get_channel(selected.id) or await interaction.guild.fetch_channel(selected.id)
        bot.data_manager.config[self.config_key] = channel.id
        if self.config_key == "general_log_channel_id":
            bot.data_manager.config["log_channel_id"] = channel.id
        await bot.data_manager.save_config()
        
        if self.config_key == "modmail_panel_channel":
            await interaction.response.defer(ephemeral=True)
            try:
                await send_modmail_panel_message(channel, interaction.guild)
                await interaction.followup.send(f"**{self.config_name}** updated to {channel.mention} and panel sent.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"**{self.config_name}** updated to {channel.mention}, but failed to send panel: {e}", ephemeral=True)
        else:
            await interaction.response.send_message(f"**{self.config_name}** updated to {channel.mention}", ephemeral=True)

class ConfigTypeSelect(discord.ui.Select):
    def __init__(self, category: str, *, row: Optional[int] = None):
        self.category = category
        options = []
        if category == "roles":
            options = [
                discord.SelectOption(label="Owner Role", value="role_owner", description="Main owner-level bot access role."),
                discord.SelectOption(label="Admin Role", value="role_admin", description="Admin access for bot systems."),
                discord.SelectOption(label="Mod Role", value="role_mod", description="Moderator access role."),
                discord.SelectOption(label="Community Manager", value="role_community_manager", description="Community manager access role."),
                discord.SelectOption(label="Anchor Role", value="role_anchor", description="Placement anchor for custom roles."),
                discord.SelectOption(label="Modmail Ping Roles", value="modmail_ping_roles", description="Roles pinged when a new ticket opens."),
            ]
        elif category == "channels":
            options = [
                discord.SelectOption(label="General Bot Log Channel", value="general_log_channel_id", description="Fallback log channel for general actions."),
                discord.SelectOption(label="Punishment Log Channel", value="punishment_log_channel_id", description="Primary punishment history log channel."),
                discord.SelectOption(label="Appeal Log Channel", value="appeal_channel_id", description="Where punishment appeals should go."),
                discord.SelectOption(label="AutoMod Log Channel", value="automod_log_channel_id", description="Where AutoMod bridge events should be logged."),
                discord.SelectOption(label="AutoMod Report Channel", value="automod_report_channel_id", description="Where user AutoMod reports should be sent."),
                discord.SelectOption(label="Archive Category", value="category_archive", description="Category for archive or storage channels."),
                discord.SelectOption(label="Modmail Inbox", value="modmail_inbox_channel", description="Channel where ticket threads are created."),
                discord.SelectOption(label="Modmail Logs", value="modmail_action_log_channel", description="Channel for modmail action updates."),
                discord.SelectOption(label="Modmail Panel Location", value="modmail_panel_channel", description="Where the public modmail panel is posted."),
            ]
        super().__init__(
            placeholder=f"Select {category[:-1]} to configure...",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        name = next(o.label for o in self.options if o.value == key)
        
        view = discord.ui.View()
        if self.category == "roles":
            if key == "modmail_ping_roles":
                view.add_item(MultiConfigRoleSelect(key, name))
            else:
                view.add_item(ConfigRoleSelect(key, name))
        elif self.category == "channels":
            c_types = [discord.ChannelType.text]
            if "category" in key:
                c_types = [discord.ChannelType.category]
            view.add_item(ConfigChannelSelect(key, name, channel_types=c_types))
            
        await interaction.response.send_message(f"Select the new **{name}** below:", view=view, ephemeral=True)

class ModmailDiscussionThreadSelect(discord.ui.Select):
    def __init__(self):
        enabled = bot.data_manager.config.get("modmail_discussion_threads", True)
        options = [
            discord.SelectOption(
                label="Discussion Threads On",
                value="on",
                description="Create a separate internal discussion thread for each ticket.",
                default=enabled,
            ),
            discord.SelectOption(
                label="Discussion Threads Off",
                value="off",
                description="Keep only the main ticket thread without the extra staff discussion thread.",
                default=not enabled,
            ),
        ]
        super().__init__(
            placeholder="Choose the ticket discussion thread behavior...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        bot.data_manager.config["modmail_discussion_threads"] = self.values[0] == "on"
        await bot.data_manager.save_config()
        await interaction.response.edit_message(embed=build_modmail_settings_embed(interaction.guild), view=ModmailSettingsView())

class ModmailSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ModmailDiscussionThreadSelect())

class BrandingColorModal(discord.ui.Modal, title="Set Embed Color"):
    embed_color = discord.ui.TextInput(
        label="Hex Color (e.g. #FF9900)",
        placeholder="#FF9900",
        required=True,
        max_length=9,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.embed_color.value.strip()
        try:
            int(raw.lstrip("#"), 16)
        except ValueError:
            await interaction.response.send_message(
                embed=make_error_embed("Invalid Color", "> Use hex format like `#FF9900`.", scope=SCOPE_SYSTEM, guild=interaction.guild),
                ephemeral=True,
            )
            return
        color = raw if raw.startswith("#") else f"#{raw}"
        await save_branding_settings(interaction.guild_id, {"embed_color": color})
        await _refresh_branding_panel(interaction)

class BrandingDisplayNameModal(discord.ui.Modal, title="Set Display Name"):
    display_name = discord.ui.TextInput(
        label="Display name for this server",
        placeholder="ModBot",
        required=False,
        max_length=32,
    )

    async def on_submit(self, interaction: discord.Interaction):
        display_name = self.display_name.value.strip()
        error = await apply_guild_member_branding(
            interaction.guild,
            display_name=display_name or None,
            reason=f"Branding display name updated by {interaction.user}",
        )
        if error:
            await interaction.response.send_message(embed=build_branding_error_embed(interaction.guild, error), ephemeral=True)
            return
        await save_branding_settings(interaction.guild_id, {"display_name": display_name or None})
        await _refresh_branding_panel(interaction)

class BrandingAvatarModal(discord.ui.Modal, title="Set Profile Avatar URL"):
    avatar_url = discord.ui.TextInput(
        label="HTTPS URL for server avatar",
        placeholder="https://cdn.discordapp.com/...",
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        avatar_url = self.avatar_url.value.strip()
        error = await apply_guild_member_branding(
            interaction.guild,
            avatar_url=avatar_url or None,
            reason=f"Branding avatar updated by {interaction.user}",
        )
        if error:
            await interaction.response.send_message(embed=build_branding_error_embed(interaction.guild, error), ephemeral=True)
            return
        await save_branding_settings(interaction.guild_id, {"avatar_url": avatar_url or None})
        await _refresh_branding_panel(interaction)

class BrandingBannerModal(discord.ui.Modal, title="Set Profile Banner URL"):
    banner_url = discord.ui.TextInput(
        label="HTTPS URL for server banner",
        placeholder="https://cdn.discordapp.com/...",
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        banner_url = self.banner_url.value.strip()
        error = await apply_guild_member_branding(
            interaction.guild,
            banner_url=banner_url or None,
            reason=f"Branding banner updated by {interaction.user}",
        )
        if error:
            await interaction.response.send_message(embed=build_branding_error_embed(interaction.guild, error), ephemeral=True)
            return
        await save_branding_settings(interaction.guild_id, {"banner_url": banner_url or None})
        await _refresh_branding_panel(interaction)

class BrandingBioModal(discord.ui.Modal, title="Set Profile Bio"):
    profile_bio = discord.ui.TextInput(
        label="Bio for this server",
        style=discord.TextStyle.paragraph,
        placeholder="Support bot for this community.",
        required=False,
        max_length=MAX_GUILD_MEMBER_BIO_LENGTH,
    )

    async def on_submit(self, interaction: discord.Interaction):
        bio = self.profile_bio.value.strip()
        error = await apply_guild_member_branding(
            interaction.guild,
            bio=bio or None,
            reason=f"Branding bio updated by {interaction.user}",
        )
        if error:
            await interaction.response.send_message(embed=build_branding_error_embed(interaction.guild, error), ephemeral=True)
            return
        await save_branding_settings(interaction.guild_id, {"bio": bio or None})
        await _refresh_branding_panel(interaction)

class BrandingModmailBannerModal(discord.ui.Modal, title="Set Modmail Banner URL"):
    banner_url = discord.ui.TextInput(
        label="HTTPS URL for modmail banner",
        placeholder="https://cdn.discordapp.com/...",
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        banner_url = self.banner_url.value.strip()
        await save_branding_settings(interaction.guild_id, {"modmail_banner_url": banner_url or None})
        await _refresh_branding_panel(interaction)

class BrandingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Embed Color", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingColorModal())

    @discord.ui.button(label="Display Name", style=discord.ButtonStyle.primary, row=0)
    async def set_display_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingDisplayNameModal())

    @discord.ui.button(label="Profile Avatar", style=discord.ButtonStyle.primary, row=0)
    async def set_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingAvatarModal())

    @discord.ui.button(label="Profile Banner", style=discord.ButtonStyle.secondary, row=1)
    async def set_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingBannerModal())

    @discord.ui.button(label="Profile Bio", style=discord.ButtonStyle.secondary, row=1)
    async def set_bio(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingBioModal())

    @discord.ui.button(label="Modmail Banner", style=discord.ButtonStyle.secondary, row=1)
    async def set_modmail_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BrandingModmailBannerModal())

    @discord.ui.button(label="Reset All", style=discord.ButtonStyle.danger, row=2)
    async def reset_branding(self, interaction: discord.Interaction, button: discord.ui.Button):
        error = await apply_guild_member_branding(
            interaction.guild,
            display_name=None,
            avatar_url=None,
            banner_url=None,
            bio=None,
            reason=f"Branding reset by {interaction.user}",
        )
        if error:
            await interaction.response.send_message(embed=build_branding_error_embed(interaction.guild, error), ephemeral=True)
            return
        cfg = bot.data_manager._configs.setdefault(interaction.guild_id, {})
        cfg["_branding"] = {}
        bot.data_manager._mark_dirty(interaction.guild_id, "guild_configs")
        await bot.data_manager.save_guild(interaction.guild_id, {"guild_configs"})
        await _refresh_branding_panel(interaction)

class ImmunityModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"{action.capitalize()} Immunity")
        self.action = action
    
    user_id = discord.ui.TextInput(label="User ID", min_length=17, max_length=20)
    
    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_id.value.strip()
        if not uid.isdigit():
            await interaction.response.send_message("Invalid ID.", ephemeral=True)
            return
            
        lst = bot.data_manager.config.get("immunity_list", [])
        
        if self.action == "add":
            if uid not in lst:
                lst.append(uid)
                msg = f"Added <@{uid}> to immunity list."
            else:
                msg = "User is already immune."
        else:
            if uid in lst:
                lst.remove(uid)
                msg = f"Removed <@{uid}> from immunity list."
            else:
                msg = "User not found in immunity list."
        
        bot.data_manager.config["immunity_list"] = lst
        await bot.data_manager.save_config()
        await interaction.response.send_message(msg, ephemeral=True)

class SafetyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Add User", style=discord.ButtonStyle.success)
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImmunityModal("add"))

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.danger)
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImmunityModal("remove"))

    @discord.ui.button(label="View List", style=discord.ButtonStyle.secondary)
    async def view_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        lst = bot.data_manager.config.get("immunity_list", [])
        if not lst:
            await interaction.response.send_message("Immunity list is empty.", ephemeral=True)
        else:
            mentions = [f"<@{uid}>" for uid in lst]
            await interaction.response.send_message(f"**Immune Users:**\n" + ", ".join(mentions), ephemeral=True)

class AntiNukeResolveConfirm2(discord.ui.View):
    def __init__(self, restore_data, origin_message):
        super().__init__(timeout=60)
        self.restore_data = restore_data
        self.origin_message = origin_message

    @discord.ui.button(label="YES, RESTORE PERMISSIONS/ROLES", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Execute Restore
        guild = interaction.guild
        actor_id = self.restore_data.get("actor_id")
        stripped_ids = self.restore_data.get("stripped_roles", [])
        
        # 1. Restore Actor Roles
        actor = guild.get_member(actor_id)
        if not actor:
            try: actor = await guild.fetch_member(actor_id)
            except Exception: pass
        
        if actor and stripped_ids:
            roles_to_add = []
            for rid in stripped_ids:
                r = guild.get_role(rid)
                if r: roles_to_add.append(r)
            if roles_to_add:
                try:
                    await actor.add_roles(*roles_to_add, reason="Anti-Nuke: Action Resolved by Owner")
                except Exception:
                    pass

        # 2. Restore Original Action
        r_type = self.restore_data.get("type")
        if r_type == "role_perm":
            role = guild.get_role(self.restore_data.get("target_id"))
            perms_val = self.restore_data.get("permissions")
            if role and perms_val is not None:
                try:
                    await role.edit(permissions=discord.Permissions(perms_val), reason="Anti-Nuke: Action Resolved by Owner")
                except Exception:
                    pass
        elif r_type == "member_role":
            target = guild.get_member(self.restore_data.get("target_id"))
            role = guild.get_role(self.restore_data.get("extra_id"))
            if target and role:
                try:
                    await target.add_roles(role, reason="Anti-Nuke: Action Resolved by Owner")
                except Exception:
                    pass

        # 3. Disable the button on the original log message to prevent reuse
        if self.origin_message:
            try:
                embed = self.origin_message.embeds[0]
                embed.color = discord.Color.green()
                embed.add_field(name="Status", value="> Resolved by Owner", inline=True)
                brand_embed(embed, guild=guild, scope=SCOPE_SYSTEM)
                await self.origin_message.edit(embed=embed, view=None)
            except Exception:
                pass

        await interaction.response.edit_message(content="**Action Resolved.** Original permissions/roles restored.", view=None)

        embed = make_embed(
            "Security Alert: Anti-Nuke Resolved",
            "> A server owner manually restored the original state after an anti-nuke intervention.",
            kind="success",
            scope=SCOPE_SYSTEM,
            guild=guild,
        )
        embed.add_field(name="Actor", value=f"<@{actor_id}> (`{actor_id}`)", inline=True)
        embed.add_field(name="Resolution", value="Original permissions or roles restored", inline=True)
        await send_log(guild, embed)

class AntiNukeResolveConfirm1(discord.ui.View):
    def __init__(self, restore_data, origin_message):
        super().__init__(timeout=60)
        self.restore_data = restore_data
        self.origin_message = origin_message

    @discord.ui.button(label="Yes, I want to resolve", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="**FINAL WARNING**\n> This will give back the dangerous permissions/roles to the user and restore the moderator's powers.\n> Are you absolutely sure?",
            view=AntiNukeResolveConfirm2(self.restore_data, self.origin_message)
        )

class AntiNukeResolveView(discord.ui.View):
    def __init__(self, restore_data):
        super().__init__(timeout=None)
        self.restore_data = restore_data

    @discord.ui.button(label="Resolve", style=discord.ButtonStyle.success)
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        owner_role = bot.data_manager.config.get("role_owner")
        if not owner_role or not any(r.id == owner_role for r in interaction.user.roles):
            await interaction.response.send_message("Only the Owner can use this.", ephemeral=True)
            return
        
        await interaction.response.send_message(
            "**Resolve Anti-Nuke Action?**\n> This will revert the bot's protection and allow the original action.",
            view=AntiNukeResolveConfirm1(self.restore_data, interaction.message),
            ephemeral=True
        )

class TestEnvView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Toggle Boost Bypass", style=discord.ButtonStyle.primary)
    async def toggle_boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "debug" not in bot.data_manager.config: bot.data_manager.config["debug"] = {}
        current = bot.data_manager.config["debug"].get("bypass_boost", False)
        bot.data_manager.config["debug"]["bypass_boost"] = not current
        await bot.data_manager.save_config()
        embed = build_test_env_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle Cooldown Bypass", style=discord.ButtonStyle.primary)
    async def toggle_cooldown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "debug" not in bot.data_manager.config: bot.data_manager.config["debug"] = {}
        current = bot.data_manager.config["debug"].get("bypass_cooldown", False)
        bot.data_manager.config["debug"]["bypass_cooldown"] = not current
        await bot.data_manager.save_config()
        embed = build_test_env_embed()
        await interaction.response.edit_message(embed=embed, view=self)


__all__ = [
    "RuleEditModal",
    "ActiveSelect",
    "ActiveView",
    "AccessView",
    "RuleDeleteSelect",
    "RuleDeleteView",
    "RuleSelectForEdit",
    "RuleSelectView",
    "ArchiveConfirmView",
    "CloneConfirmView",
    "RulesDashboardView",
    "ConfigImportModal",
    "ConfigDashboardActionSelect",
    "ConfigDashboardView",
    "SetupDashboardActionSelect",
    "SetupDashboardView",
    "FeatureFlagSelect",
    "FeatureFlagView",
    "EscalationMatrixModal",
    "EscalationMatrixView",
    "CannedReplyModal",
    "CannedRepliesView",
    "ConfigRoleSelect",
    "MultiConfigRoleSelect",
    "ConfigChannelSelect",
    "ConfigTypeSelect",
    "ModmailDiscussionThreadSelect",
    "ModmailSettingsView",
    "BrandingColorModal",
    "BrandingDisplayNameModal",
    "BrandingAvatarModal",
    "BrandingBannerModal",
    "BrandingBioModal",
    "BrandingModmailBannerModal",
    "BrandingPanelView",
    "ImmunityModal",
    "SafetyView",
    "AntiNukeResolveConfirm2",
    "AntiNukeResolveConfirm1",
    "AntiNukeResolveView",
    "TestEnvView",
    "build_config_dashboard_embed",
    "build_escalation_matrix_embed",
    "build_feature_flags_embed",
    "build_rules_dashboard_embed",
    "build_setup_dashboard_embed",
    "build_setup_validation_embed",
    "build_modmail_settings_embed",
]
