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

class ConfirmRevokeView(discord.ui.View):
    def __init__(self, parent_view, target_message):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.target_message = target_message

    @discord.ui.button(label="Yes, Revoke", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        await self.parent_view.finish_revoke(interaction, self.target_message)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Revocation cancelled.", view=None)

class DenyAppealModal(discord.ui.Modal, title="Deny Appeal"):
    reason = discord.ui.TextInput(label="Reason for Denial", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, target_id: int, origin_message: discord.Message, view: discord.ui.View):
        super().__init__()
        self.target_id = target_id
        self.origin_message = origin_message
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        embed = self.origin_message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"> Denied by {interaction.user.mention}\n> Reason: {self.reason.value}", inline=False)
        brand_embed(embed, guild=interaction.guild, scope=SCOPE_MODERATION)
        
        for child in self.view.children:
            child.disabled = True
        
        await self.origin_message.edit(embed=embed, view=self.view)
        
        user = interaction.guild.get_member(self.target_id)
        if not user:
            try: user = await interaction.client.fetch_user(self.target_id)
            except Exception: user = None
            
        if user:
            try:
                dm_embed = make_embed(
                    "Appeal Denied",
                    f"> Your punishment appeal in **{interaction.guild.name}** was reviewed and denied.",
                    kind="danger",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                    thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
                )
                dm_embed.add_field(name="Reason", value=format_reason_value(self.reason.value, limit=1024), inline=False)
                await user.send(embed=dm_embed)
            except Exception:
                pass
        
        await interaction.response.send_message("Appeal denied.", ephemeral=True)

class RevokeAppealView(discord.ui.View):
    def __init__(self, target_id: int, moderator_id: int, duration: int, timestamp: str):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.moderator_id = moderator_id
        self.duration = duration
        self.timestamp = timestamp

    @discord.ui.button(label="Revoke Punishment", style=discord.ButtonStyle.danger, custom_id="revoke_punishment_btn")
    async def start_revoke(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        await interaction.response.send_message("Are you sure you want to revoke this punishment?", view=ConfirmRevokeView(self, interaction.message), ephemeral=True)

    @discord.ui.button(label="Deny Appeal", style=discord.ButtonStyle.secondary, custom_id="deny_appeal_btn")
    async def deny_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        await interaction.response.send_modal(DenyAppealModal(self.target_id, interaction.message, self))

    async def finish_revoke(self, interaction: discord.Interaction, message: discord.Message):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Processing revocation...", view=None)
        
        guild = interaction.guild
        uid = str(self.target_id)
        revoked_record = None
        records = bot.data_manager.punishments.get(uid, [])
        for record in records:
            if record.get("timestamp") == self.timestamp:
                revoked_record = record
                break
        case_label = get_case_label(revoked_record) if revoked_record else "Case"
        
        # 1. Remove from database
        if uid in bot.data_manager.punishments:
            original_len = len(bot.data_manager.punishments[uid])
            bot.data_manager.punishments[uid] = [r for r in bot.data_manager.punishments[uid] if r.get("timestamp") != self.timestamp]
            
            if len(bot.data_manager.punishments[uid]) != original_len:
                await bot.data_manager.save_punishments()

        # 2. Reverse Stats
        mod_id = str(self.moderator_id)
        if "reversals" not in bot.data_manager.mod_stats: bot.data_manager.mod_stats["reversals"] = {}
        bot.data_manager.mod_stats["reversals"][mod_id] = bot.data_manager.mod_stats["reversals"].get(mod_id, 0) + 1
        await bot.data_manager.save_mod_stats()

        # 3. Physical Revocation
        action_taken = "Record removed"
        try:
            if self.duration == -1:
                # Unban
                user_obj = discord.Object(id=self.target_id)
                try:
                    await guild.unban(user_obj, reason=f"Appeal Accepted by {interaction.user}")
                    action_taken = "Unbanned & Record removed"
                except Exception:
                    action_taken = "User not banned (Record removed)"
            elif self.duration > 0:
                # Untimeout
                member = guild.get_member(self.target_id)
                if member:
                    if member.is_timed_out():
                        await member.timeout(None, reason=f"Appeal Accepted by {interaction.user}")
                        action_taken = "Timeout removed & Record removed"
                    else:
                        action_taken = "User not timed out (Record removed)"
                else:
                    action_taken = "User not in server (Record removed)"
            else:
                # Warning
                action_taken = "Warning revoked (Points removed)"
        except Exception as e:
            action_taken = f"Revocation error: {e}"

        # 4. Update Embed
        embed = message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = f"{case_label} Appeal Resolved"
        embed.add_field(name="Status", value=f"> Revoked by {interaction.user.mention}\n> {action_taken}", inline=False)
        brand_embed(embed, guild=guild, scope=SCOPE_MODERATION)
        
        self.children[0].label = "Punishment Revoked"
        for child in self.children:
            child.disabled = True
        await message.edit(embed=embed, view=self)

        # 5. DM User
        user = interaction.guild.get_member(self.target_id)
        if not user:
            try:
                user = await interaction.client.fetch_user(self.target_id)
            except Exception:
                user = None
            
        if user:
            try:
                dm_embed = make_embed(
                    "Punishment Revoked",
                    f"> {case_label} in **{interaction.guild.name}** has been revoked.",
                    kind="success",
                    scope=SCOPE_MODERATION,
                    guild=interaction.guild,
                    thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
                )
                dm_embed.add_field(name="Outcome", value=truncate_text(action_taken, 1024), inline=False)
                await user.send(embed=dm_embed)
            except Exception:
                pass
            
        await interaction.followup.send("Punishment revoked successfully.", ephemeral=True)
        
        # 6. Log to General Logs (if different from current channel)
        target_str = format_user_ref(user) if user else format_user_id_ref(self.target_id, fallback_name=(revoked_record or {}).get("target_name"))
        log_embed = make_action_log_embed(
            f"{case_label} Revoked",
            "A punishment appeal was accepted and the system attempted to reverse the action.",
            guild=guild,
            kind="success",
            scope=SCOPE_MODERATION,
            actor=format_user_ref(interaction.user),
            target=target_str,
            reason="Appeal accepted",
            duration="Revoked",
            expires="N/A",
            notes=[f"Result: {truncate_text(action_taken, 500)}"],
            thumbnail=user.display_avatar.url if user else None,
        )
        await send_punishment_log(guild, log_embed)

class AppealModal(discord.ui.Modal, title="Appeal Punishment"):
    reason = discord.ui.TextInput(label="Why should this be revoked?", style=discord.TextStyle.paragraph, max_length=500)
    
    def __init__(self, guild_id: int, target_id: int, moderator_id: int, duration: int, timestamp: str, original_reason: str):
        super().__init__()
        self.guild_id = guild_id
        self.target_id = target_id
        self.moderator_id = moderator_id
        self.duration = duration
        self.timestamp = timestamp
        self.original_reason = original_reason

    async def on_submit(self, interaction: discord.Interaction):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("Server not found.", ephemeral=True)
            return

        record = next(
            (
                item for item in bot.data_manager.punishments.get(str(self.target_id), [])
                if item.get("timestamp") == self.timestamp
            ),
            None,
        )
        case_label = get_case_label(record) if record else "Case"

        embed = make_action_log_embed(
            f"{case_label} Appeal",
            "A user submitted an appeal for moderator review.",
            guild=guild,
            kind="warning",
            scope=SCOPE_MODERATION,
            actor=format_user_ref(interaction.user),
            target=case_label,
            reason=self.original_reason,
            message=self.reason.value,
            notes=[f"Moderator ID: {self.moderator_id}", f"Original Timestamp: {self.timestamp}"],
            thumbnail=interaction.user.display_avatar.url,
            author_name=f"{interaction.user.display_name} ({interaction.user.id})",
            author_icon=interaction.user.display_avatar.url,
        )
        
        view = RevokeAppealView(self.target_id, self.moderator_id, self.duration, self.timestamp)
        
        # Check for specific appeal channel
        appeal_cid = bot.data_manager.config.get("appeal_channel_id")
        sent = False
        if appeal_cid:
            appeal_chan = guild.get_channel(appeal_cid)
            if appeal_chan:
                try:
                    await appeal_chan.send(embed=embed, view=view)
                    sent = True
                except Exception:
                    pass
        
        # Fallback to General Logs only if Appeal Log failed or isn't set
        if not sent:
            await send_punishment_log(guild, embed, view=view)
            
        await interaction.response.send_message("Your appeal has been sent to the staff team.", ephemeral=True)

class AppealView(ExpirableMixin, discord.ui.View):
    def __init__(self, guild_id: int, target_id: int, moderator_id: int, duration: int, timestamp: str, reason: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.target_id = target_id
        self.moderator_id = moderator_id
        self.duration = duration
        self.timestamp = timestamp
        self.reason = reason

    @discord.ui.button(label="Appeal Punishment", style=discord.ButtonStyle.secondary)
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppealModal(self.guild_id, self.target_id, self.moderator_id, self.duration, self.timestamp, self.reason))

class PunishDetailsModal(discord.ui.Modal):
    def __init__(self, target, moderator, reason, rules, origin_message=None, public=False, reaction_count=None):
        super().__init__(title=f"Punish: {target.display_name}")
        self.target = target
        self.moderator = moderator
        self.reason = reason
        self.rules = rules
        self.origin_message = origin_message
        self.public = public
        self.reaction_count = reaction_count

    mod_note = discord.ui.TextInput(
        label="Moderator Note (Internal)",
        style=discord.TextStyle.paragraph,
        placeholder="Visible only to staff. Required.",
        required=True
    )

    mod_message = discord.ui.TextInput(
        label="Message to User (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Visible to the user. Explain why they are being punished.",
        required=False
    )
    
    duration_override = discord.ui.TextInput(
        label="Duration/Type Override (Optional)",
        placeholder="e.g. 2d, 1w, ban, warn, kick. Leave blank for auto.",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        reason = self.reason
        rules = self.rules
        note = self.mod_note.value
        user_msg = self.mod_message.value
        override = self.duration_override.value.strip().lower()
        
        minutes = 0
        is_escalated = False
        punishment_type = "auto"

        if override:
            if override == "kick":
                punishment_type = "kick"
            elif override == "softban":
                punishment_type = "softban"
            else:
                minutes = parse_duration_str(override)
                if minutes == -1: punishment_type = "ban"
                elif minutes == 0: punishment_type = "warn"
        else:
            # Use advanced calculation
            minutes, is_escalated, tier_info = calculate_smart_punishment(str(self.target.id), reason, rules, bot.data_manager.punishments.get(str(self.target.id), []))
            
            # Append tier info to internal note for context
            if note: note = f"[{tier_info}] {note}"
            else: note = f"[{tier_info}]"
        
        if self.reaction_count:
            embed = build_public_execution_embed(
                interaction.guild,
                target_id=self.target.id,
                target_avatar_url=self.target.display_avatar.url,
                punishment_type=punishment_type,
                reason=reason,
                threshold=self.reaction_count,
                minutes=minutes,
            )
            msg = await interaction.followup.send(embed=embed, view=PublicExecutionApprovalView(), ephemeral=False)
            bot.active_executions[msg.id] = {
                "target_id": self.target.id,
                "count": self.reaction_count,
                "reason": reason,
                "note": note,
                "user_msg": user_msg,
                "moderator_id": self.moderator.id,
                "duration": minutes,
                "type": punishment_type,
                "escalated": is_escalated,
                "target_avatar_url": self.target.display_avatar.url,
                "voters": set(),
            }
            return

        await execute_punishment(interaction, self.target, self.moderator, reason, minutes, note, user_msg, is_escalated, self.origin_message, punishment_type=punishment_type, public=self.public)

class CustomPunishDetailsModal(discord.ui.Modal):
    def __init__(self, target, moderator, p_type, origin_message, public=False, reaction_count=None):
        super().__init__(title=f"Configure {p_type.replace('_', ' ').title()}")
        self.target = target
        self.moderator = moderator
        self.p_type = p_type
        self.origin_message = origin_message
        self.public = public
        self.reaction_count = reaction_count
        
        self.custom_reason = discord.ui.TextInput(
            label="Reason",
            placeholder="e.g. Violation of rules",
            max_length=100,
            required=True
        )
        self.add_item(self.custom_reason)
        
        self.duration_str = None
        if p_type in ["timeout", "ban_temp"]:
            self.duration_str = discord.ui.TextInput(
                label="Duration",
                placeholder="e.g. 1h, 30m, 1d",
                max_length=20,
                required=True
            )
            self.add_item(self.duration_str)
            
        self.mod_note = discord.ui.TextInput(
            label="Moderator Note (Internal)",
            style=discord.TextStyle.paragraph,
            placeholder="Visible only to staff.",
            required=True
        )
        self.add_item(self.mod_note)
        
        self.mod_message = discord.ui.TextInput(
            label="Message to User (Optional)",
            style=discord.TextStyle.paragraph,
            placeholder="Visible to the user.",
            required=False
        )
        self.add_item(self.mod_message)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        minutes = 0
        final_type = self.p_type
        
        if self.p_type == "ban_perm":
            final_type = "ban"
            minutes = -1
        elif self.p_type == "ban_temp":
            final_type = "ban"
            if self.duration_str:
                minutes = parse_duration_str(self.duration_str.value)
                if minutes <= 0:
                    await interaction.followup.send("Invalid duration for temporary ban.", ephemeral=True)
                    return
        elif self.p_type == "timeout":
            final_type = "timeout"
            if self.duration_str:
                minutes = parse_duration_str(self.duration_str.value)
                if minutes <= 0:
                    await interaction.followup.send("Invalid duration for timeout.", ephemeral=True)
                    return
        elif self.p_type == "kick":
            final_type = "kick"
            minutes = 0
        elif self.p_type == "softban":
            final_type = "softban"
            minutes = 0
        elif self.p_type == "warn":
            final_type = "warn"
            minutes = 0

        if self.reaction_count:
            embed = build_public_execution_embed(
                interaction.guild,
                target_id=self.target.id,
                target_avatar_url=self.target.display_avatar.url,
                punishment_type=final_type,
                reason=self.custom_reason.value,
                threshold=self.reaction_count,
                minutes=minutes,
            )
            msg = await interaction.followup.send(embed=embed, view=PublicExecutionApprovalView(), ephemeral=False)
            bot.active_executions[msg.id] = {
                "target_id": self.target.id,
                "count": self.reaction_count,
                "reason": self.custom_reason.value,
                "note": self.mod_note.value,
                "user_msg": self.mod_message.value,
                "moderator_id": self.moderator.id,
                "duration": minutes,
                "type": final_type,
                "escalated": False,
                "target_avatar_url": self.target.display_avatar.url,
                "voters": set(),
            }
            return

        await execute_punishment(
            interaction, 
            self.target, 
            self.moderator, 
            self.custom_reason.value, 
            minutes, 
            self.mod_note.value, 
            self.mod_message.value, 
            False, # Custom punishments don't follow auto-escalation logic
            self.origin_message,
            punishment_type=final_type,
            public=self.public
        )

class CustomTypeSelect(discord.ui.Select):
    def __init__(self, target, moderator, origin_message, public=False, reaction_count=None):
        self.target = target
        self.moderator = moderator
        self.origin_message = origin_message
        self.public = public
        self.reaction_count = reaction_count
        options = [
            discord.SelectOption(label="Timeout", value="timeout", description="Mute user for a duration"),
            discord.SelectOption(label="Kick", value="kick", description="Remove user from server"),
            discord.SelectOption(label="Softban", value="softban", description="Kick + Delete Messages"),
            discord.SelectOption(label="Ban (Temporary)", value="ban_temp", description="Ban for a duration"),
            discord.SelectOption(label="Ban (Permanent)", value="ban_perm", description="Ban indefinitely"),
            discord.SelectOption(label="Warning", value="warn", description="Log a warning")
        ]
        super().__init__(placeholder="Select punishment type...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        p_type = self.values[0]
        await interaction.response.send_modal(CustomPunishDetailsModal(self.target, self.moderator, p_type, self.origin_message, public=self.public, reaction_count=self.reaction_count))

class CustomTypeView(discord.ui.View):
    def __init__(self, target, moderator, origin_message, public=False, reaction_count=None):
        super().__init__(timeout=60)
        self.add_item(CustomTypeSelect(target, moderator, origin_message, public=public, reaction_count=reaction_count))

class PunishSelect(discord.ui.Select):
    def __init__(self, target: discord.User, moderator: discord.Member, public=False, reaction_count=None):
        self.target = target
        self.moderator = moderator
        self.public = public
        self.reaction_count = reaction_count
        rules_config = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        user_history = bot.data_manager.punishments.get(str(target.id), [])
        options = []
        for reason, rules in rules_config.items():
            predicted_minutes, will_escalate, _ = calculate_smart_punishment(
                str(target.id), reason, rules, user_history
            )
            predicted_str = format_duration(predicted_minutes)
            base_str = format_duration(rules["base"])
            esc_str = format_duration(rules["escalated"])
            if will_escalate:
                desc = truncate_text(f"⬆ Escalated → {predicted_str}  (base: {base_str})", 100)
            elif rules["base"] == 0:
                desc = truncate_text(f"1st offense: Warning  •  Repeat: {esc_str}", 100)
            else:
                desc = truncate_text(f"Will apply: {predicted_str}  (escalated: {esc_str})", 100)
            options.append(discord.SelectOption(label=reason, description=desc))
        options.append(discord.SelectOption(label="Custom Punishment", value="custom", description="Define custom reason and duration"))
        super().__init__(placeholder="Select a punishment reason...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom":
            await interaction.response.send_message("Select the type of custom punishment:", view=CustomTypeView(self.target, self.moderator, interaction.message, public=self.public, reaction_count=self.reaction_count), ephemeral=True)
            return
        reason = self.values[0]
        rules_config = bot.data_manager.config.get("punishment_rules", DEFAULT_RULES)
        rules = rules_config.get(reason)
        if not rules:
            return
        await interaction.response.send_modal(PunishDetailsModal(self.target, self.moderator, reason, rules, interaction.message, public=self.public, reaction_count=self.reaction_count))

class FinalConfirmClear(discord.ui.View):
    def __init__(self, target, moderator, origin_message=None):
        super().__init__(timeout=60)
        self.target = target
        self.moderator = moderator
        self.origin_message = origin_message

    @discord.ui.button(label="YES, WIPE EVERYTHING", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        removed_records = await clear_user_history_records(self.target)
        if removed_records:
            attachment = build_history_archive_attachment(
                "history_clear",
                target_user_id=str(self.target.id),
                actor_id=self.moderator.id,
                payload={"action": "history_clear", "records": removed_records},
            )
            log_embed = build_history_cleared_log_embed(interaction.guild, self.moderator, self.target, removed_records)
            await send_punishment_log(interaction.guild, log_embed, attachments=[attachment])

            await interaction.response.edit_message(content="**History has been completely wiped.**", view=None)

            if self.origin_message:
                try:
                    await self.origin_message.edit(embed=build_punish_embed(self.target))
                except Exception:
                    pass
        else:
            await interaction.response.edit_message(content="User has no history to clear.", view=None)

    @discord.ui.button(label="No, Stop", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Clear history canceled.", view=None)

class HistorySelect(discord.ui.Select):
    def __init__(self, page_items: List[dict], panel: "HistoryView"):
        self.panel = panel
        options = []
        for record in page_items:
            case_id = get_case_id(record)
            if case_id is None:
                continue
            reason = record.get("reason", "Unknown")
            dt = iso_to_dt(record.get("timestamp"))
            date_str = dt.strftime("%Y-%m-%d") if dt else "Unknown"
            label = f"{get_case_label(record)}: {truncate_text(reason, 70)}"
            desc = f"{date_str} • {describe_punishment_record(record)}"
            options.append(discord.SelectOption(label=label, description=desc, value=str(case_id)))

        if not options:
            options.append(discord.SelectOption(label="No cases found", value="0", description="There are no valid cases on this page."))

        super().__init__(placeholder="Select a case to view details...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "0":
            await respond_with_error(interaction, "There are no valid cases to open on this page.", scope=SCOPE_MODERATION)
            return

        self.panel.message = interaction.message
        self.panel.selected_case_id = int(self.values[0])
        self.panel.mode = "history"
        self.panel.update_components()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)

class UndoCaseSelect(discord.ui.Select):
    def __init__(self, page_items: List[dict], panel: "HistoryView"):
        self.panel = panel
        options = []
        for record in page_items:
            case_id = get_case_id(record)
            if case_id is None:
                continue
            dt = iso_to_dt(record.get("timestamp"))
            date_str = dt.strftime("%Y-%m-%d") if dt else "Unknown"
            label = f"{get_case_label(record)} ({date_str})"
            desc = truncate_text(f"{describe_punishment_record(record)} • {record.get('reason', 'Unknown')}", 100)
            options.append(
                discord.SelectOption(
                    label=label,
                    description=desc,
                    value=str(case_id),
                    default=case_id == panel.selected_case_id,
                )
            )

        if not options:
            options.append(discord.SelectOption(label="No cases found", value="0", description="There are no valid cases on this page."))

        super().__init__(placeholder="Select punishment to undo...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "0":
            await respond_with_error(interaction, "There are no valid cases to undo on this page.", scope=SCOPE_MODERATION)
            return

        self.panel.message = interaction.message
        self.panel.selected_case_id = int(self.values[0])
        self.panel.update_components()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)

class UndoReasonSelect(discord.ui.Select):
    def __init__(self, panel: "HistoryView"):
        self.panel = panel
        options = [
            discord.SelectOption(
                label=preset["label"],
                value=preset["value"],
                description=truncate_text(preset["description"], 100),
                default=(not panel.custom_undo_reason and preset["value"] == panel.undo_reason_value),
            )
            for preset in UNDO_REASON_PRESETS
        ]
        super().__init__(placeholder="Select an undo reason preset...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.panel.message = interaction.message
        self.panel.undo_reason_value = self.values[0]
        self.panel.custom_undo_reason = None
        self.panel.update_components()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)

class HistoryActionButton(discord.ui.Button):
    def __init__(self, label: str, style: discord.ButtonStyle, action: str, *, row: int, disabled: bool = False):
        super().__init__(label=label, style=style, row=row, disabled=disabled)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: HistoryView = self.view
        await view.handle_action(interaction, self.action)

class HistoryNavButton(discord.ui.Button):
    def __init__(self, label: str, style: discord.ButtonStyle, direction: int, *, row: int, disabled: bool = False):
        super().__init__(label=label, style=style, row=row, disabled=disabled)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: HistoryView = self.view
        view.message = interaction.message
        view.page = max(0, min(view.max_pages - 1, view.page + self.direction))
        if view.mode == "undo":
            page_items = view.get_page_items()
            if page_items:
                view.selected_case_id = get_case_id(page_items[0])
        view.update_components()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

class UndoReasonModal(discord.ui.Modal, title="Custom Undo Reason"):
    reason = discord.ui.TextInput(
        label="Undo Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Explain why this punishment is being undone.",
        max_length=500,
    )

    def __init__(self, panel: "HistoryView"):
        super().__init__()
        self.panel = panel
        if panel.custom_undo_reason:
            self.reason.default = panel.custom_undo_reason

    async def on_submit(self, interaction: discord.Interaction):
        custom_reason = self.reason.value.strip()
        if not custom_reason:
            await respond_with_error(interaction, "The undo reason cannot be empty.", scope=SCOPE_MODERATION)
            return

        self.panel.custom_undo_reason = custom_reason
        await self.panel.refresh_panel_message()
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                "Undo Reason Saved",
                "> The custom undo reason was saved to the panel.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )

class UndoConfirmView(discord.ui.View):
    def __init__(self, panel: "HistoryView"):
        super().__init__(timeout=120)
        self.panel = panel

    @discord.ui.button(label="Confirm Undo", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        record = self.panel.get_selected_record()
        undo_reason = self.panel.get_current_undo_reason_text()
        if not record or not undo_reason:
            await interaction.response.edit_message(content="The selected case is no longer available.", embed=None, view=None)
            return

        await interaction.response.edit_message(content="Processing undo...", embed=None, view=None)
        success, removed_record, action_result = await undo_case_record(
            interaction.guild,
            interaction.user,
            self.panel.user,
            get_case_id(record) or 0,
            undo_reason,
        )
        if not success or not removed_record:
            await interaction.edit_original_response(content=action_result, embed=None, view=None)
            return

        attachment = build_history_archive_attachment(
            "undo_case",
            target_user_id=str(self.panel.user.id),
            actor_id=interaction.user.id,
            payload={
                "action": "undo_case",
                "undo_reason": undo_reason,
                "record": removed_record,
            },
        )
        log_embed = build_punishment_undo_log_embed(interaction.guild, interaction.user, self.panel.user, removed_record, undo_reason, action_result)
        view = RevokeUndoView(self.panel.user.id, removed_record, interaction.user.id)
        await send_punishment_log(interaction.guild, log_embed, view=view, attachments=[attachment])

        await self.panel.refresh_panel_message()
        await interaction.edit_original_response(
            content=f"**{get_case_label(removed_record)}** was undone.\n{action_result}",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Undo canceled.", embed=None, view=None)

class HistoryClearConfirmView(discord.ui.View):
    def __init__(self, panel: "HistoryView"):
        super().__init__(timeout=120)
        self.panel = panel

    @discord.ui.button(label="Yes, Clear History", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Clearing history...", embed=None, view=None)
        removed_records = await clear_user_history_records(self.panel.user)
        if not removed_records:
            await self.panel.refresh_panel_message()
            await interaction.edit_original_response(content="User has no history to clear.", embed=None, view=None)
            return

        attachment = build_history_archive_attachment(
            "history_clear",
            target_user_id=str(self.panel.user.id),
            actor_id=interaction.user.id,
            payload={"action": "history_clear", "records": removed_records},
        )
        log_embed = build_history_cleared_log_embed(interaction.guild, interaction.user, self.panel.user, removed_records)
        await send_punishment_log(interaction.guild, log_embed, attachments=[attachment])

        await self.panel.refresh_panel_message()
        await interaction.edit_original_response(content="**History has been completely wiped.**", embed=None, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Clear history canceled.", embed=None, view=None)

class HistoryView(ExpirableMixin, discord.ui.View):
    def __init__(self, user: discord.Member, *, mode: str = "history", selected_case_id: Optional[int] = None, initial_undo_reason: Optional[str] = None):
        super().__init__(timeout=300)
        self.user = user
        self.mode = mode if mode in {"history", "undo"} else "history"
        self.selected_case_id = selected_case_id
        self.custom_undo_reason = str(initial_undo_reason or "").strip() or None
        self.undo_reason_value = UNDO_REASON_PRESETS[0]["value"]
        self.message: Optional[discord.Message] = None
        self.page = 0
        self.items_per_page = 25
        self.history: List[dict] = []
        self.sorted_history: List[dict] = []
        self.max_pages = 1
        self.reload_history()
        if self.mode == "undo" and not self.selected_case_id and self.sorted_history:
            self.selected_case_id = get_case_id(self.sorted_history[0])
        self.ensure_page_for_selected_case()
        self.update_components()

    def reload_history(self):
        self.history = [record for record in bot.data_manager.punishments.get(str(self.user.id), []) if isinstance(record, dict)]
        self.sorted_history = sorted(
            self.history,
            key=lambda record: (get_case_id(record) or 0, record.get("timestamp", "")),
            reverse=True,
        )
        self.max_pages = max(1, (len(self.sorted_history) + self.items_per_page - 1) // self.items_per_page)
        self.page = max(0, min(self.page, self.max_pages - 1))
        if self.selected_case_id and not any(get_case_id(record) == self.selected_case_id for record in self.sorted_history):
            self.selected_case_id = get_case_id(self.sorted_history[0]) if self.mode == "undo" and self.sorted_history else None

    def ensure_page_for_selected_case(self):
        if not self.selected_case_id:
            self.page = max(0, min(self.page, self.max_pages - 1))
            return
        for index, record in enumerate(self.sorted_history):
            if get_case_id(record) == self.selected_case_id:
                self.page = index // self.items_per_page
                return
        self.page = max(0, min(self.page, self.max_pages - 1))

    def get_page_items(self) -> List[dict]:
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        return self.sorted_history[start:end]

    def get_selected_record(self) -> Optional[dict]:
        if not self.selected_case_id:
            return None
        for record in self.sorted_history:
            if get_case_id(record) == self.selected_case_id:
                return record
        return None

    def get_current_undo_reason_mode(self) -> str:
        return get_undo_reason_details(self.undo_reason_value, self.custom_undo_reason)[0]

    def get_current_undo_reason_text(self) -> str:
        return get_undo_reason_details(self.undo_reason_value, self.custom_undo_reason)[1]

    def build_embed(self) -> discord.Embed:
        if not self.sorted_history:
            return build_no_history_embed(self.user, self.user.guild)
        if self.mode == "undo":
            return build_undo_panel_embed(
                self.user,
                self.history,
                self.get_selected_record(),
                reason_mode=self.get_current_undo_reason_mode(),
                undo_reason=self.get_current_undo_reason_text(),
            )
        selected_record = self.get_selected_record()
        if selected_record:
            return build_history_case_detail_embed(self.user, selected_record)
        return build_history_overview_embed(self.user, self.history)

    async def refresh_panel_message(self):
        self.reload_history()
        if self.mode == "undo" and not self.selected_case_id and self.sorted_history:
            self.selected_case_id = get_case_id(self.sorted_history[0])
        self.ensure_page_for_selected_case()
        if not self.sorted_history:
            self.stop()
            if self.message:
                await self.message.edit(embed=build_no_history_embed(self.user, self.user.guild), view=None)
            return
        self.update_components()
        if self.message:
            await self.message.edit(embed=self.build_embed(), view=self)

    def update_components(self):
        self.clear_items()
        if not self.sorted_history:
            return

        if self.mode == "undo":
            self.add_item(UndoCaseSelect(self.get_page_items(), self))
            self.add_item(UndoReasonSelect(self))
            if self.max_pages > 1:
                self.add_item(HistoryNavButton("Previous", discord.ButtonStyle.primary, -1, row=2, disabled=(self.page == 0)))
                self.add_item(discord.ui.Button(label=f"Page {self.page + 1}/{self.max_pages}", disabled=True, style=discord.ButtonStyle.secondary, row=2))
                self.add_item(HistoryNavButton("Next", discord.ButtonStyle.primary, 1, row=2, disabled=(self.page >= self.max_pages - 1)))
            self.add_item(HistoryActionButton("Back to History", discord.ButtonStyle.secondary, "back_to_history", row=3))
            self.add_item(HistoryActionButton("Custom Reason", discord.ButtonStyle.primary, "custom_reason", row=3))
            self.add_item(HistoryActionButton("Refresh", discord.ButtonStyle.secondary, "refresh", row=3))
            self.add_item(HistoryActionButton("Undo Selected", discord.ButtonStyle.danger, "undo_selected", row=3, disabled=(self.get_selected_record() is None)))
            return

        if self.selected_case_id:
            self.add_item(HistoryActionButton("Back to Overview", discord.ButtonStyle.secondary, "history_overview", row=0))
            self.add_item(HistoryActionButton("Undo This Case", discord.ButtonStyle.danger, "open_undo", row=0))
            self.add_item(HistoryActionButton("Refresh", discord.ButtonStyle.secondary, "refresh", row=0))
            self.add_item(HistoryActionButton("Clear History", discord.ButtonStyle.danger, "clear_history", row=1))
            return

        self.add_item(HistorySelect(self.get_page_items(), self))
        if self.max_pages > 1:
            self.add_item(HistoryNavButton("Previous", discord.ButtonStyle.primary, -1, row=1, disabled=(self.page == 0)))
            self.add_item(discord.ui.Button(label=f"Page {self.page + 1}/{self.max_pages}", disabled=True, style=discord.ButtonStyle.secondary, row=1))
            self.add_item(HistoryNavButton("Next", discord.ButtonStyle.primary, 1, row=1, disabled=(self.page >= self.max_pages - 1)))
        self.add_item(HistoryActionButton("Refresh", discord.ButtonStyle.secondary, "refresh", row=2))
        self.add_item(HistoryActionButton("Undo Punishment", discord.ButtonStyle.danger, "open_undo", row=2))
        self.add_item(HistoryActionButton("Clear History", discord.ButtonStyle.danger, "clear_history", row=2))

    async def handle_action(self, interaction: discord.Interaction, action: str):
        self.message = interaction.message
        if action == "refresh":
            await self.refresh_after_interaction(interaction)
            return

        if action == "history_overview":
            self.mode = "history"
            self.selected_case_id = None
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            return

        if action == "back_to_history":
            self.mode = "history"
            self.ensure_page_for_selected_case()
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            return

        if action == "open_undo":
            self.mode = "undo"
            if not self.selected_case_id:
                page_items = self.get_page_items()
                if page_items:
                    self.selected_case_id = get_case_id(page_items[0])
                elif self.sorted_history:
                    self.selected_case_id = get_case_id(self.sorted_history[0])
            self.ensure_page_for_selected_case()
            self.update_components()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            return

        if action == "custom_reason":
            await interaction.response.send_modal(UndoReasonModal(self))
            return

        if action == "undo_selected":
            record = self.get_selected_record()
            if not record:
                await respond_with_error(interaction, "Select a case to undo first.", scope=SCOPE_MODERATION)
                return

            confirm_embed = make_embed(
                f"Undo {get_case_label(record)}",
                "> Confirm this reversal. The case will be removed from history and the bot will try to reverse any active punishment.",
                kind="danger",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
                thumbnail=self.user.display_avatar.url,
            )
            confirm_embed.add_field(name="Undo Reason", value=format_reason_value(self.get_current_undo_reason_text(), limit=500), inline=False)
            confirm_embed.add_field(name="Case Details", value=format_case_summary_block(record, include_original_reason=True), inline=False)
            await interaction.response.send_message(embed=confirm_embed, view=UndoConfirmView(self), ephemeral=True)
            return

        if action == "clear_history":
            await interaction.response.send_message(
                "**Are you sure you want to clear this user's punishment history?**",
                view=HistoryClearConfirmView(self),
                ephemeral=True,
            )
            return

    async def refresh_after_interaction(self, interaction: discord.Interaction):
        self.reload_history()
        if self.mode == "undo" and not self.selected_case_id and self.sorted_history:
            self.selected_case_id = get_case_id(self.sorted_history[0])
        self.ensure_page_for_selected_case()
        self.update_components()
        if not self.sorted_history:
            self.stop()
            await interaction.response.edit_message(embed=build_no_history_embed(self.user, interaction.guild), view=None)
            return
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

class CaseNoteModal(discord.ui.Modal, title="Add Internal Case Note"):
    note = discord.ui.TextInput(
        label="Internal Note",
        style=discord.TextStyle.paragraph,
        placeholder="Staff-only note for future context.",
        max_length=1000,
    )

    def __init__(self, panel: "CasePanelView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        target_user_id, record = bot.data_manager.get_case(self.panel.case_id)
        if not record or not target_user_id:
            await respond_with_error(interaction, "The selected case no longer exists.", scope=SCOPE_MODERATION)
            return

        notes = record.setdefault("internal_notes", [])
        notes.append(CaseNote(interaction.user.id, self.note.value.strip(), now_iso()).to_dict())
        normalize_case_record(record)
        await bot.data_manager.save_punishments()
        await log_case_management_action(interaction.guild, interaction.user, target_user_id, record, "Internal note added", self.note.value)
        await self.panel.refresh_panel()
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                f"{get_case_label(record)} Saved",
                "> Internal note added to the case record.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )

class CaseLinksModal(discord.ui.Modal, title="Update Evidence and Tags"):
    evidence_links = discord.ui.TextInput(
        label="Evidence Links",
        style=discord.TextStyle.paragraph,
        placeholder="Paste URLs separated by commas or new lines.",
        required=False,
        max_length=1000,
    )
    linked_cases = discord.ui.TextInput(
        label="Related Case IDs",
        placeholder="Example: 101, 118, 204",
        required=False,
        max_length=200,
    )
    tags = discord.ui.TextInput(
        label="Tags",
        placeholder="Example: scam, repeat-offender, escalated",
        required=False,
        max_length=200,
    )

    def __init__(self, panel: "CasePanelView"):
        super().__init__()
        self.panel = panel
        _, record = bot.data_manager.get_case(panel.case_id)
        if record:
            self.evidence_links.default = "\n".join(record.get("evidence_links", []))
            self.linked_cases.default = ", ".join(str(case_id) for case_id in record.get("linked_cases", []))
            self.tags.default = ", ".join(record.get("tags", []))

    async def on_submit(self, interaction: discord.Interaction):
        target_user_id, record = bot.data_manager.get_case(self.panel.case_id)
        if not record or not target_user_id:
            await respond_with_error(interaction, "The selected case no longer exists.", scope=SCOPE_MODERATION)
            return

        record["evidence_links"] = sanitize_evidence_links(_split_case_input(self.evidence_links.value))
        record["linked_cases"] = sanitize_linked_cases(_split_case_input(self.linked_cases.value), current_case_id=record.get("case_id"))
        record["tags"] = sanitize_tags(_split_case_input(self.tags.value))
        normalize_case_record(record)
        await bot.data_manager.save_punishments()
        await log_case_management_action(
            interaction.guild,
            interaction.user,
            target_user_id,
            record,
            "Links and tags updated",
            f"Tags: {', '.join(record['tags']) or 'None'} | Linked: {', '.join(str(case_id) for case_id in record['linked_cases']) or 'None'}",
        )
        await self.panel.refresh_panel()
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                f"{get_case_label(record)} Saved",
                "> Evidence links, linked cases, and tags were updated.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            ephemeral=True,
        )

class CaseStateSelect(discord.ui.Select):
    def __init__(self, panel: "CasePanelView"):
        self.panel = panel
        _, record = bot.data_manager.get_case(panel.case_id)
        current = f"{record.get('status', 'open')}|{record.get('resolution_state', 'pending')}" if record else ""
        options = []
        for status, resolution, label, description in [
            ("open", "pending", "Open - Waiting", "New case that still needs review."),
            ("open", "active", "Open - In Progress", "Staff are actively handling this case."),
            ("review", "pending", "Under Review", "Waiting for staff review."),
            ("appealed", "pending", "Appeal Waiting", "The user appealed and staff still need to decide."),
            ("closed", "resolved", "Closed - Finished", "Handled and fully closed."),
            ("closed", "reversed", "Closed - Reversed", "The action was undone or reversed."),
            ("closed", "expired", "Closed - Expired", "The timed action ended on its own."),
        ]:
            options.append(
                discord.SelectOption(
                    label=label,
                    value=f"{status}|{resolution}",
                    description=description,
                    default=current == f"{status}|{resolution}",
                )
            )
        super().__init__(placeholder="Choose the case status...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_user_id, record = bot.data_manager.get_case(self.panel.case_id)
        if not record or not target_user_id:
            await respond_with_error(interaction, "The selected case no longer exists.", scope=SCOPE_MODERATION)
            return

        status, resolution = self.values[0].split("|", 1)
        record["status"] = status
        record["resolution_state"] = resolution
        normalize_case_record(record)
        await bot.data_manager.save_punishments()
        await log_case_management_action(
            interaction.guild,
            interaction.user,
            target_user_id,
            record,
            "Status updated",
            f"Status: {status} | Resolution: {resolution}",
        )
        await self.panel.refresh_panel()
        await interaction.response.edit_message(
            embed=make_confirmation_embed(
                f"{get_case_label(record)} Updated",
                "> Case status and resolution state were updated.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            view=None,
        )

class CaseStateView(discord.ui.View):
    def __init__(self, panel: "CasePanelView"):
        super().__init__(timeout=120)
        self.add_item(CaseStateSelect(panel))

class CaseSwitchSelect(discord.ui.Select):
    def __init__(self, panel: "CasePanelView"):
        self.panel = panel
        options = []
        for case_id in panel.case_ids[:25]:
            _, record = bot.data_manager.get_case(case_id)
            if not record:
                continue
            label = truncate_text(f"{get_case_label(record)} • {record.get('reason', 'Unknown')}", 100)
            description = truncate_text(f"{describe_punishment_record(record)} • {format_case_status(record)}", 100)
            options.append(
                discord.SelectOption(
                    label=label,
                    description=description,
                    value=str(case_id),
                    default=case_id == panel.case_id,
                )
            )
        if not options:
            options.append(discord.SelectOption(label="No cases found", value="0"))
        super().__init__(placeholder="Open another case...", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "0":
            await respond_with_error(interaction, "No valid cases are available.", scope=SCOPE_MODERATION)
            return
        self.panel.case_id = int(self.values[0])
        self.panel.sync_buttons()
        await interaction.response.edit_message(embed=self.panel.build_embed(), view=self.panel)

class CasePanelView(ExpirableMixin, discord.ui.View):
    def __init__(self, target_user_id: str, case_ids: List[int], target_user: Optional[Union[discord.Member, discord.User]] = None):
        super().__init__(timeout=300)
        self.target_user_id = target_user_id
        self.case_ids = case_ids
        self.case_id = case_ids[0]
        self.target_user = target_user
        self.message: Optional[discord.Message] = None
        if len(self.case_ids) > 1:
            self.add_item(CaseSwitchSelect(self))
        self.sync_buttons()

    def current_record(self) -> Optional[dict]:
        _, record = bot.data_manager.get_case(self.case_id)
        return record

    def build_embed(self) -> discord.Embed:
        record = self.current_record()
        if not record:
            return make_empty_state_embed(
                "Case Not Found",
                "> The selected case could not be loaded.",
                scope=SCOPE_MODERATION,
                guild=self.target_user.guild if isinstance(self.target_user, discord.Member) else None,
            )
        guild = self.target_user.guild if isinstance(self.target_user, discord.Member) else (self.message.guild if self.message else None)
        return build_case_detail_embed(guild, self.target_user_id, record, target_user=self.target_user)

    def sync_buttons(self):
        record = self.current_record() or {}
        assigned = record.get("assigned_moderator")
        self.claim_case.label = "Unclaim Case" if assigned else "Claim Case"
        self.claim_case.style = discord.ButtonStyle.secondary if assigned else discord.ButtonStyle.success

    async def refresh_panel(self):
        self.sync_buttons()
        if self.message:
            await self.message.edit(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=0)
    async def refresh_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        self.sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Claim Case", style=discord.ButtonStyle.success, row=0)
    async def claim_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        record = self.current_record()
        if not record:
            await respond_with_error(interaction, "The selected case could not be loaded.", scope=SCOPE_MODERATION)
            return

        currently_assigned = record.get("assigned_moderator")
        record["assigned_moderator"] = None if currently_assigned == interaction.user.id else interaction.user.id
        normalize_case_record(record)
        await bot.data_manager.save_punishments()
        await log_case_management_action(
            interaction.guild,
            interaction.user,
            self.target_user_id,
            record,
            "Assignment updated",
            "Case claimed by moderator." if record.get("assigned_moderator") else "Case unclaimed.",
        )
        self.sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.primary, row=0)
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        await interaction.response.send_modal(CaseNoteModal(self))

    @discord.ui.button(label="Change Status", style=discord.ButtonStyle.primary, row=0)
    async def case_state(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        await interaction.response.send_message(
            embed=make_embed(
                "Case Status",
                "> Pick the status that best matches what is happening with this case right now.",
                kind="info",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            view=CaseStateView(self),
            ephemeral=True,
        )

    @discord.ui.button(label="Evidence & Tags", style=discord.ButtonStyle.primary, row=1)
    async def links_and_tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.message = interaction.message
        await interaction.response.send_modal(CaseLinksModal(self))

    @discord.ui.button(label="Download Case", style=discord.ButtonStyle.secondary, row=1)
    async def export_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        record = self.current_record()
        if not record:
            await respond_with_error(interaction, "The selected case could not be loaded.", scope=SCOPE_MODERATION)
            return

        payload = export_case_payload(self.target_user_id, record)
        buffer = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))
        file = discord.File(buffer, filename=f"case_{record.get('case_id', 'unknown')}.json")
        await interaction.response.send_message(
            embed=make_confirmation_embed(
                f"{get_case_label(record)} Download Ready",
                "> A case file was generated for this case.",
                scope=SCOPE_MODERATION,
                guild=interaction.guild,
            ),
            file=file,
            ephemeral=True,
        )

class FirstConfirmClear(discord.ui.View):
    def __init__(self, target, moderator, origin_message=None):
        super().__init__(timeout=60)
        self.target = target
        self.moderator = moderator
        self.origin_message = origin_message

    @discord.ui.button(label="Yes, Clear History", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"**WAIT!** Are you **REALLY** sure?\nThis will wipe ALL past violations for {self.target.mention}.\nThey will be treated as a new user for future punishments.",
            view=FinalConfirmClear(self.target, self.moderator, self.origin_message)
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Clear history canceled.", view=None)

class PunishView(ExpirableMixin, discord.ui.View):
    def __init__(self, target, moderator, public=False, reaction_count=None):
        super().__init__(timeout=60)
        self.target = target
        self.moderator = moderator
        self.add_item(PunishSelect(target, moderator, public=public, reaction_count=reaction_count))

    @discord.ui.button(label="Clear History", style=discord.ButtonStyle.danger, row=1)
    async def clear_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "**Are you sure you want to clear this user's punishment history?**", 
            view=FirstConfirmClear(self.target, self.moderator, interaction.message), 
            ephemeral=True
        )

    @discord.ui.button(label="View History", style=discord.ButtonStyle.secondary, row=1)
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = self.target if isinstance(self.target, discord.Member) else await resolve_member(interaction.guild, self.target.id)
        if not member:
            await interaction.response.send_message("This user is no longer in the server, so the interactive history panel is unavailable.", ephemeral=True)
            return

        uid = str(member.id)
        history_data = bot.data_manager.punishments.get(uid, [])
        
        if not history_data:
            await interaction.response.send_message(f"**{member.display_name}** has a clean record (No history found).", ephemeral=True)
            return

        view = HistoryView(member)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

class RevokeUndoView(discord.ui.View):
    def __init__(self, target_id: int, record: dict, actor_id: int):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.record = record
        self.actor_id = actor_id

    @discord.ui.button(label="Revoke Undo", style=discord.ButtonStyle.danger)
    async def revoke_undo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
             await interaction.response.send_message("Access denied.", ephemeral=True)
             return

        await interaction.response.defer()
        
        # Restore record
        uid = str(self.target_id)
        await bot.data_manager.add_punishment(uid, self.record)
        
        # Re-apply physical punishment
        guild = interaction.guild
        target = guild.get_member(self.target_id)
        if not target:
            try: target = await bot.fetch_user(self.target_id)
            except Exception: pass
            
        action_taken = "History Restored"
        p_type = self.record.get("type")
        dur = self.record.get("duration_minutes", 0)
        
        try:
            if p_type == "ban":
                await guild.ban(discord.Object(id=self.target_id), reason="Undo Revoked: Restoring Punishment")
                action_taken += " & User Banned"
            elif p_type == "timeout" and isinstance(target, discord.Member):
                if dur > 0:
                    await target.timeout(get_valid_duration(dur), reason="Undo Revoked: Restoring Punishment")
                    action_taken += " & User Timed Out"
        except Exception as e:
            action_taken += f" (Physical action failed: {e})"

        embed = interaction.message.embeds[0]
        embed.color = EMBED_PALETTE["warning"]
        embed.add_field(name="Update", value=f"> **Undo Revoked** by {interaction.user.mention}\n> {action_taken}", inline=False)
        
        button.disabled = True
        button.label = "Undo Revoked"
        await interaction.edit_original_response(embed=embed, view=self)

class PublicExecutionApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=86400)

    @discord.ui.button(label="Approve Action", style=discord.ButtonStyle.danger)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message is None or interaction.guild is None:
            await interaction.response.send_message("This execution vote is no longer active.", ephemeral=True)
            return

        data = bot.active_executions.get(interaction.message.id)
        if not data:
            await interaction.response.send_message("This execution vote is no longer active.", ephemeral=True)
            return

        voters = data.setdefault("voters", set())
        if interaction.user.id in voters:
            await interaction.response.send_message("You already approved this action.", ephemeral=True)
            return

        voters.add(interaction.user.id)
        approvals = len(voters)
        updated_embed = build_public_execution_embed(
            interaction.guild,
            target_id=data["target_id"],
            target_avatar_url=data.get("target_avatar_url"),
            punishment_type=data["type"],
            reason=data["reason"],
            threshold=data["count"],
            minutes=data["duration"],
            approvals=approvals,
        )

        if approvals >= data["count"]:
            bot.active_executions.pop(interaction.message.id, None)
            button.disabled = True
            await interaction.response.edit_message(embed=updated_embed, view=self)
            await execute_public_execution_vote(interaction.channel, interaction.guild, data)
            return

        await interaction.response.edit_message(embed=updated_embed, view=self)


__all__ = [
    "ConfirmRevokeView",
    "DenyAppealModal",
    "RevokeAppealView",
    "AppealModal",
    "AppealView",
    "PunishDetailsModal",
    "CustomPunishDetailsModal",
    "CustomTypeSelect",
    "CustomTypeView",
    "PunishSelect",
    "FinalConfirmClear",
    "HistorySelect",
    "UndoCaseSelect",
    "UndoReasonSelect",
    "HistoryActionButton",
    "HistoryNavButton",
    "UndoReasonModal",
    "UndoConfirmView",
    "HistoryClearConfirmView",
    "HistoryView",
    "CaseNoteModal",
    "CaseLinksModal",
    "CaseStateSelect",
    "CaseStateView",
    "CaseSwitchSelect",
    "CasePanelView",
    "FirstConfirmClear",
    "PunishView",
    "RevokeUndoView",
    "PublicExecutionApprovalView",
    "build_active_punishments_embed",
    "build_case_detail_embed",
    "build_history_overview_embed",
    "build_mod_help_embed",
]
