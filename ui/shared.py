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

class ExpirableMixin:
    """
    Mixin for discord.ui.View subclasses.
    When the view's timeout fires, disables all components and edits the message
    so users see "This menu has expired" rather than silent non-responsive buttons.
    """
    async def on_timeout(self) -> None:
        message = getattr(self, "message", None)
        if message is None:
            return
        for item in self.children:
            item.disabled = True
        try:
            await message.edit(content="-# This menu has expired — re-run the command to continue.", view=self)
        except Exception:
            pass

class CommandCategorySelect(discord.ui.Select):
    def __init__(self, guild: Optional[discord.Guild]):
        self.guild = guild
        self._buckets = _categorise_commands()
        options = [
            discord.SelectOption(label=cat, description=f"{len(cmds)} command(s)", value=cat)
            for cat, cmds in self._buckets.items()
        ]
        super().__init__(placeholder="Browse a command category…", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        lines = self._buckets.get(cat, [])
        embed = make_embed(
            f"Commands — {cat}",
            "\n".join(lines) or "> No commands.",
            kind="info",
            scope=SCOPE_SYSTEM,
            guild=self.guild,
        )
        await interaction.response.edit_message(embed=embed, view=self.view)

class CommandBrowserView(ExpirableMixin, discord.ui.View):
    def __init__(self, guild: Optional[discord.Guild]):
        super().__init__(timeout=120)
        self.add_item(CommandCategorySelect(guild))

class ModCasesSelect(discord.ui.Select):
    def __init__(self, cases, guild):
        self.cases = cases
        # Sort by timestamp desc
        self.cases.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
        
        options = []
        for i, (uid, rec) in enumerate(self.cases[:25]):
            ts = iso_to_dt(rec.get("timestamp"))
            date_str = ts.strftime("%Y-%m-%d") if ts else "?"
            reason = truncate_text(rec.get("reason", "Unknown"), 60)
            action = rec.get("type") or ("ban" if rec.get("duration_minutes", 0) == -1 else ("warn" if rec.get("duration_minutes", 0) == 0 else "timeout"))

            label = truncate_text(f"{get_case_label(rec, i + 1)} • {action.title()}", 100)
            member = guild.get_member(int(uid)) if guild else None
            user_display = member.name if member else uid
            desc = truncate_text(f"{date_str} • {user_display} • {reason}", 100)
            options.append(discord.SelectOption(label=label, description=desc, value=str(i)))
            
        if not options:
            options.append(discord.SelectOption(label="No cases found", value="-1"))
            
        super().__init__(placeholder="Select a case to view details...", min_values=1, max_values=1, options=options, disabled=not options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "-1":
            return
            
        idx = int(self.values[0])
        uid, rec = self.cases[idx]

        case_label = get_case_label(rec, idx + 1)
        embed = make_embed(
            f"{case_label} Details",
            "> Full case metadata for this moderator-issued action.",
            kind="warning",
            scope=SCOPE_ANALYTICS,
            guild=interaction.guild,
        )

        # User Info
        user_obj = interaction.guild.get_member(int(uid))
        user_name = user_obj.name if user_obj else "Unknown (Left Server)"
        user_field = f"**Name:** {user_name}\n**Mention:** <@{uid}>\n**ID:** `{uid}`"
        embed.add_field(name="User", value=f"> {user_field.replace(chr(10), chr(10)+'> ')}", inline=True)
        
        # Moderator Info
        mod_id = rec.get("moderator")
        mod_field = f"**Mention:** <@{mod_id}>\n**ID:** `{mod_id}`"
        embed.add_field(name="Moderator", value=f"> {mod_field.replace(chr(10), chr(10)+'> ')}", inline=True)
        
        # Action Info
        mins = rec.get("duration_minutes", 0)
        if mins == -1:
            type_str = "Ban"
            dur_str = "Ban"
        elif mins == 0:
            type_str = "Warning"
            dur_str = "N/A"
        else:
            type_str = "Timeout"
            dur_str = format_duration(mins)
            
        action_field = f"**Type:** {type_str}\n**Duration:** {dur_str}"
        embed.add_field(name="Action", value=f"> {action_field.replace(chr(10), chr(10)+'> ')}", inline=True)
        embed.add_field(name="Status", value="> Active" if is_record_active(rec) else "> Closed", inline=True)
        
        # Timestamps
        ts = iso_to_dt(rec.get("timestamp"))
        if ts:
            ts_field = f"**Issued:** {discord.utils.format_dt(ts, 'F')} ({discord.utils.format_dt(ts, 'R')})"
            if mins > 0:
                expiry = ts + timedelta(minutes=mins)
                ts_field += f"\n**Expired:** {discord.utils.format_dt(expiry, 'F')}"
            embed.add_field(name="Timeline", value=f"> {ts_field.replace(chr(10), chr(10)+'> ')}", inline=False)
            
        # Reason & Notes
        embed.add_field(name="Violation Reason", value=f"> {truncate_text(rec.get('reason', 'Unknown'), 1024)}", inline=False)
        
        note = truncate_text(str(rec.get("note") or "").strip(), 1000)
        if note:
            embed.add_field(name="Internal Note", value=format_log_quote(note, limit=1000), inline=False)
        
        user_msg = rec.get("user_msg")
        if user_msg:
            embed.add_field(name="Message to User", value=format_log_quote(user_msg, limit=1000), inline=False)
            
        is_esc = rec.get("escalated", False)
        if is_esc:
            embed.add_field(name="Escalated", value="Yes", inline=True)
        
        # Keep the view (which has this select) so they can pick another case
        await interaction.response.edit_message(embed=embed, view=self.view)

class StaffProfileView(discord.ui.View):
    def __init__(self, target, cases, staff_members, directory_embed, stats_embed, guild):
        super().__init__(timeout=180)
        self.target = target
        self.cases = cases
        self.staff_members = staff_members
        self.directory_embed = directory_embed
        self.stats_embed = stats_embed
        
        self.add_item(ModCasesSelect(cases, guild))
        
        if not staff_members or not directory_embed:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.label == "Back to Directory":
                    self.remove_item(child)
                    break

    @discord.ui.button(label="Back to Stats", style=discord.ButtonStyle.secondary, row=1)
    async def back_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.stats_embed, view=self)

    @discord.ui.button(label="Back to Directory", style=discord.ButtonStyle.primary, row=1)
    async def back_dir(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = StaffView(self.staff_members)
        await interaction.response.edit_message(embed=self.directory_embed, view=view)

class StaffSelect(discord.ui.Select):
    def __init__(self, staff_members):
        self.staff_members = staff_members
        options = []
        for m in staff_members[:25]:
            options.append(discord.SelectOption(label=m.display_name, value=str(m.id)))
        super().__init__(placeholder="Select a staff member to view stats...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        target = interaction.guild.get_member(target_id)
        if target:
            uid = str(target.id)
            cases = get_mod_cases(uid)
            reversals = bot.data_manager.mod_stats.get("reversals", {}).get(uid, 0)
            
            stats_embed = get_staff_stats_embed(target, cases, reversals)
            directory_embed = interaction.message.embeds[0]
            
            view = StaffProfileView(target, cases, self.staff_members, directory_embed, stats_embed, interaction.guild)
            await interaction.response.edit_message(embed=stats_embed, view=view)
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)

class StaffView(discord.ui.View):
    def __init__(self, staff_members):
        super().__init__(timeout=180)
        self.add_item(StaffSelect(staff_members))


__all__ = [
    "ExpirableMixin",
    "CommandCategorySelect",
    "CommandBrowserView",
    "ModCasesSelect",
    "StaffProfileView",
    "StaffSelect",
    "StaffView",
    "brand_embed",
    "format_log_quote",
    "format_reason_value",
    "make_confirmation_embed",
    "make_embed",
    "make_empty_state_embed",
    "make_error_embed",
]
