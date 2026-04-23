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

class ModmailPrioritySelect(discord.ui.Select):
    def __init__(self, panel: "ModmailControlView"):
        self.panel = panel
        ticket = bot.data_manager.modmail.get(panel.user_id, {})
        current = str(ticket.get("priority", "normal")).lower()
        options = [
            discord.SelectOption(label=priority.title(), value=priority, default=priority == current)
            for priority in DEFAULT_TICKET_PRIORITIES
        ]
        super().__init__(placeholder="Choose how urgent this ticket is...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        ticket = bot.data_manager.modmail.get(self.panel.user_id)
        if not ticket:
            await respond_with_error(interaction, "Ticket data not found.", scope=SCOPE_SUPPORT)
            return
        ticket["priority"] = self.values[0]
        await bot.data_manager.save_modmail()
        await refresh_modmail_message(self.panel.message or interaction.message, interaction.guild, self.panel.user_id, self.panel)
        await log_modmail_action(interaction.guild, "Ticket Priority Updated", [
            ("User", f"<@{self.panel.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Priority", self.values[0].title()),
        ])
        await interaction.response.edit_message(
            embed=make_confirmation_embed(
                "Ticket Priority Updated",
                f"> Priority set to **{self.values[0].title()}**.",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            ),
            view=None,
        )

class ModmailPriorityView(discord.ui.View):
    def __init__(self, panel: "ModmailControlView"):
        super().__init__(timeout=120)
        self.add_item(ModmailPrioritySelect(panel))

class ModmailTagsModal(discord.ui.Modal, title="Update Ticket Tags"):
    tags = discord.ui.TextInput(
        label="Tags",
        placeholder="bug, urgent, follow-up",
        max_length=200,
        required=False,
    )

    def __init__(self, panel: "ModmailControlView"):
        super().__init__()
        self.panel = panel
        ticket = bot.data_manager.modmail.get(panel.user_id, {})
        self.tags.default = ", ".join(ticket.get("tags", []))

    async def on_submit(self, interaction: discord.Interaction):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        ticket = bot.data_manager.modmail.get(self.panel.user_id)
        if not ticket:
            await respond_with_error(interaction, "Ticket data not found.", scope=SCOPE_SUPPORT)
            return
        ticket["tags"] = sanitize_tags(_split_case_input(self.tags.value), limit=10)
        await bot.data_manager.save_modmail()
        await refresh_modmail_message(self.panel.message, interaction.guild, self.panel.user_id, self.panel)
        await log_modmail_action(interaction.guild, "Ticket Tags Updated", [
            ("User", f"<@{self.panel.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Tags", ", ".join(ticket["tags"]) or "None"),
        ])
        await interaction.response.send_message(
            embed=make_confirmation_embed("Ticket Tags Updated", "> Ticket tags were updated.", scope=SCOPE_SUPPORT, guild=interaction.guild),
            ephemeral=True,
        )

class CannedReplySelect(discord.ui.Select):
    def __init__(self, panel: "ModmailControlView"):
        self.panel = panel
        replies = bot.data_manager.config.get("modmail_canned_replies", {})
        options = [
            discord.SelectOption(label=key, value=key, description=truncate_text(value, 100))
            for key, value in list(replies.items())[:25]
        ]
        if not options:
            options.append(discord.SelectOption(label="No saved replies", value="__empty__", description="Add reply templates in /config"))
        super().__init__(placeholder="Choose a quick reply...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        if self.values[0] == "__empty__":
            await respond_with_error(interaction, "No saved replies have been set up yet.", scope=SCOPE_SUPPORT)
            return
        ticket = bot.data_manager.modmail.get(self.panel.user_id)
        if not ticket:
            await respond_with_error(interaction, "Ticket data not found.", scope=SCOPE_SUPPORT)
            return
        reply_key = self.values[0]
        reply_body = bot.data_manager.config.get("modmail_canned_replies", {}).get(reply_key, "")
        user = await resolve_modmail_user(self.panel.user_id)
        if user is None:
            await respond_with_error(interaction, "Unable to resolve the user for this ticket.", scope=SCOPE_SUPPORT)
            return
        try:
            embed = make_embed(
                "Staff Reply",
                truncate_text(reply_body, 4096),
                kind="info",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            )
            await user.send(embed=embed)
        except discord.Forbidden:
            await respond_with_error(interaction, "Unable to DM the user with the saved reply.", scope=SCOPE_SUPPORT)
            return
        except discord.HTTPException as exc:
            await respond_with_error(interaction, f"Failed to send the saved reply: {exc}", scope=SCOPE_SUPPORT)
            return

        ticket["last_staff_message_at"] = now_iso()
        await bot.data_manager.save_modmail()
        if isinstance(interaction.channel, discord.Thread):
            await interaction.channel.send(f"Sent quick reply `{reply_key}` to <@{self.panel.user_id}>.")
        await refresh_modmail_message(self.panel.message or interaction.message, interaction.guild, self.panel.user_id, self.panel)
        await log_modmail_action(interaction.guild, "Canned Reply Sent", [
            ("User", f"<@{self.panel.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Template", reply_key),
        ])
        await interaction.response.edit_message(
            embed=make_confirmation_embed("Quick Reply Sent", "> The saved reply was sent to the user.", scope=SCOPE_SUPPORT, guild=interaction.guild),
            view=None,
        )

class CannedReplyView(discord.ui.View):
    def __init__(self, panel: "ModmailControlView"):
        super().__init__(timeout=120)
        self.add_item(CannedReplySelect(panel))

class ModmailControlView(discord.ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.message: Optional[discord.Message] = None
        self.sync_buttons(bot.data_manager.modmail.get(self.user_id, {}))

    def sync_buttons(self, ticket: dict):
        status = ticket.get("status", "open")
        assigned = ticket.get("assigned_moderator")
        self.close_ticket.disabled = status == "closed"
        self.open_ticket.disabled = status != "closed"
        self.claim_ticket.label = "Unclaim Ticket" if assigned else "Claim Ticket"
        self.claim_ticket.style = discord.ButtonStyle.secondary if assigned else discord.ButtonStyle.success

    def _get_ticket(self) -> Optional[dict]:
        return bot.data_manager.modmail.get(self.user_id)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="mm_close", row=0)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return

        self.message = interaction.message
        ticket = self._get_ticket()
        if not ticket or ticket.get("status") == "closed":
            await interaction.response.send_message("Ticket is already closed.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket["status"] = "closed"
        ticket["last_staff_message_at"] = now_iso()
        await bot.data_manager.save_modmail()

        thread = await resolve_modmail_thread(interaction.guild, ticket)

        transcript_file = None
        if isinstance(thread, discord.Thread):
            try:
                transcript_file = await export_modmail_transcript(thread, self.user_id)
            except Exception as exc:
                logger.warning("Failed to export modmail transcript for %s: %s", self.user_id, exc)

        await refresh_modmail_message(interaction.message, interaction.guild, self.user_id, self)

        if isinstance(thread, discord.Thread):
            try:
                await thread.send(f"**Ticket Closed** by {interaction.user.mention}.")
                await thread.edit(locked=True, archived=True)
            except discord.HTTPException as exc:
                logger.warning("Failed to finalize closed thread for %s: %s", self.user_id, exc)

        user = await resolve_modmail_user(self.user_id)
        if user is not None:
            dm_embed = make_embed(
                "Ticket Closed",
                "> Your support ticket has been closed by the staff team.\n> If you need anything else, open a new ticket anytime.",
                kind="danger",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            )
            try:
                await user.send(embed=dm_embed)
            except discord.HTTPException as exc:
                logger.warning("Failed to DM closed-ticket notice to %s: %s", self.user_id, exc)

        log_channel_id = bot.data_manager.config.get("modmail_action_log_channel")
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        if transcript_file and log_channel:
            try:
                await log_channel.send(content=f"Transcript for closed ticket <@{self.user_id}>", file=transcript_file)
            except discord.HTTPException as exc:
                logger.warning("Failed to upload modmail transcript for %s: %s", self.user_id, exc)

        await log_modmail_action(interaction.guild, "Ticket Closed", [
            ("User", f"<@{self.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Priority", str(ticket.get("priority", "normal")).title()),
            ("Ticket ID", str(ticket.get("thread_id", "N/A"))),
        ])
        await interaction.followup.send(
            embed=make_confirmation_embed("Ticket Closed", "> Ticket closed and transcript exported when available.", scope=SCOPE_SUPPORT, guild=interaction.guild),
            ephemeral=True,
        )

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, custom_id="mm_open", disabled=True, row=0)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return

        self.message = interaction.message
        ticket = self._get_ticket()
        if not ticket:
            await interaction.response.send_message("Ticket data not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket["status"] = "open"
        ticket["last_staff_message_at"] = now_iso()
        await bot.data_manager.save_modmail()
        await refresh_modmail_message(interaction.message, interaction.guild, self.user_id, self)

        thread = await resolve_modmail_thread(interaction.guild, ticket)

        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(locked=False, archived=False)
                await thread.send(f"**Ticket Re-opened** by {interaction.user.mention}.")
            except discord.HTTPException as exc:
                logger.warning("Failed to reopen thread for %s: %s", self.user_id, exc)

        user = await resolve_modmail_user(self.user_id)
        if user is not None:
            dm_embed = make_embed(
                "Ticket Re-opened",
                "> Your support ticket has been re-opened. You can continue messaging the staff team.",
                kind="success",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            )
            try:
                await user.send(embed=dm_embed)
            except discord.HTTPException as exc:
                logger.warning("Failed to DM reopened-ticket notice to %s: %s", self.user_id, exc)

        await log_modmail_action(interaction.guild, "Ticket Re-opened", [
            ("User", f"<@{self.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Ticket ID", str(ticket.get("thread_id", "N/A"))),
        ])
        await interaction.followup.send(
            embed=make_confirmation_embed("Ticket Re-opened", "> Ticket reopened successfully.", scope=SCOPE_SUPPORT, guild=interaction.guild),
            ephemeral=True,
        )

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, custom_id="mm_claim", row=0)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return

        self.message = interaction.message
        ticket = self._get_ticket()
        if not ticket:
            await interaction.response.send_message("Ticket data not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        current = ticket.get("assigned_moderator")
        ticket["assigned_moderator"] = None if current == interaction.user.id else interaction.user.id
        ticket["claimed_at"] = now_iso() if ticket.get("assigned_moderator") else None
        await bot.data_manager.save_modmail()
        await refresh_modmail_message(interaction.message, interaction.guild, self.user_id, self)
        await log_modmail_action(interaction.guild, "Ticket Assignment Updated", [
            ("User", f"<@{self.user_id}>"),
            ("Moderator", interaction.user.mention),
            ("Assigned", interaction.user.mention if ticket.get("assigned_moderator") else "Unclaimed"),
        ])
        await interaction.followup.send("Ticket assignment updated.", ephemeral=True)

    @discord.ui.button(label="Urgency", style=discord.ButtonStyle.primary, custom_id="mm_priority", row=1)
    async def priority(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        self.message = interaction.message
        await interaction.response.send_message(
            embed=make_embed("Ticket Urgency", "> Choose how urgent this ticket is for staff.", kind="warning", scope=SCOPE_SUPPORT, guild=interaction.guild),
            view=ModmailPriorityView(self),
            ephemeral=True,
        )

    @discord.ui.button(label="Tags", style=discord.ButtonStyle.primary, custom_id="mm_tags", row=1)
    async def tags(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        self.message = interaction.message
        await interaction.response.send_modal(ModmailTagsModal(self))

    @discord.ui.button(label="Quick Reply", style=discord.ButtonStyle.secondary, custom_id="mm_canned", row=1)
    async def canned_reply(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        self.message = interaction.message
        await interaction.response.send_message(embed=build_canned_replies_embed(interaction.guild), view=CannedReplyView(self), ephemeral=True)

    @discord.ui.button(label="Download Transcript", style=discord.ButtonStyle.secondary, custom_id="mm_export", row=1)
    async def export_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return
        ticket = self._get_ticket()
        thread = await resolve_modmail_thread(interaction.guild, ticket)
        if not isinstance(thread, discord.Thread):
            await respond_with_error(interaction, "Transcript export is only available from the ticket thread.", scope=SCOPE_SUPPORT)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        file = await export_modmail_transcript(thread, self.user_id)
        await interaction.followup.send(
            embed=make_confirmation_embed("Transcript Ready", "> The ticket transcript has been generated.", scope=SCOPE_SUPPORT, guild=interaction.guild),
            file=file,
            ephemeral=True,
        )

class ModmailModal(discord.ui.Modal):
    def __init__(self, category: str):
        super().__init__(title=f"Open {category} Ticket")
        self.category = category
        
        if category == "Report":
            self.add_item(discord.ui.TextInput(label="Reported User (ID or Name)", placeholder="e.g. 123456789...", required=True))
            self.add_item(discord.ui.TextInput(label="Reason", placeholder="Short summary...", required=True))
            self.add_item(discord.ui.TextInput(label="Evidence / Details", style=discord.TextStyle.paragraph, placeholder="Please provide links or detailed explanation...", required=True))
        elif category == "Partnership":
            self.add_item(discord.ui.TextInput(label="Server Name", required=True))
            self.add_item(discord.ui.TextInput(label="Server Link (Permanent)", required=True))
            self.add_item(discord.ui.TextInput(label="Subject", style=discord.TextStyle.paragraph, required=True))
        else:
            # Support
            self.add_item(discord.ui.TextInput(label="Subject", placeholder="Brief title...", required=True))
            self.add_item(discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, placeholder="How can we help?", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = get_context_guild(interaction)
        if guild is None:
            await interaction.followup.send("This server could not be resolved for modmail. Ask an administrator to set the Guild ID in setup.", ephemeral=True)
            return

        existing_ticket = bot.data_manager.modmail.get(str(interaction.user.id))
        if existing_ticket and existing_ticket.get("status") == "open":
            await interaction.followup.send("You already have an open ticket. Keep replying in DM and staff will receive it.", ephemeral=True)
            return
        
        log_channel_id = bot.data_manager.config.get("modmail_inbox_channel")
        if not log_channel_id:
            await interaction.followup.send("Modmail system is not fully configured (Inbox channel missing). Contact admin.", ephemeral=True)
            return
            
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            await interaction.followup.send("Inbox channel not found.", ephemeral=True)
            return

        # Create Log Embed
        embed = make_embed(
            f"New Ticket: {self.category}",
            "> A new ticket has been submitted through the support panel.",
            kind="support",
            scope=SCOPE_SUPPORT,
            guild=guild,
            thumbnail=interaction.user.display_avatar.url,
            author_name=f"{interaction.user.display_name} ({interaction.user.id})",
            author_icon=interaction.user.display_avatar.url,
        )
        
        fields_data = []
        for child in self.children:
            field_label = get_modal_item_label(child)
            embed.add_field(name=field_label, value=f">>> {child.value}", inline=False)
            fields_data.append(f"**{field_label}**: {child.value}")

        ticket_payload = {
            "status": "open",
            "category": self.category,
            "created_at": now_iso(),
            "priority": "normal",
            "tags": [],
            "assigned_moderator": None,
            "claimed_at": None,
            "last_user_message_at": now_iso(),
            "last_staff_message_at": None,
            "last_sla_alert_at": None,
        }
        normalize_modmail_ticket(ticket_payload)
        apply_modmail_ticket_state(embed, ticket_payload, guild)
        
        # Send Log & Create Thread
        try:
            view = ModmailControlView(str(interaction.user.id))
            
            ping_roles = bot.data_manager.config.get("modmail_ping_roles", [])
            if ping_roles:
                pings = " ".join([f"<@&{rid}>" for rid in ping_roles])
            else:
                # Fall back to configured staff roles — only mention roles set for this guild
                r_mod = bot.data_manager.config.get("role_mod")
                r_admin = bot.data_manager.config.get("role_admin")
                r_cm = bot.data_manager.config.get("role_community_manager")
                ping_parts = [f"<@&{r}>" for r in (r_mod, r_admin, r_cm) if r]
                pings = " ".join(ping_parts) if ping_parts else None

            log_msg = await log_channel.send(content=f"New Ticket from {interaction.user.mention} {pings}", embed=embed, view=view)
            thread = await log_msg.create_thread(name=f"ticket-{interaction.user.name}")
            
            # Create Staff Discussion Thread
            if bot.data_manager.config.get("modmail_discussion_threads", True):
                disc_msg = await log_channel.send(f"**Staff Discussion** for {interaction.user.mention} (Ticket #{log_msg.id})")
                await disc_msg.create_thread(name=f"discuss-{interaction.user.name}")
            
            # Save Ticket Data
            ticket_payload["thread_id"] = thread.id
            ticket_payload["log_id"] = log_msg.id
            bot.data_manager.modmail[str(interaction.user.id)] = ticket_payload
            await bot.data_manager.save_modmail()
            
            # Initial Thread Msg
            await send_modmail_thread_intro(thread, interaction.user, self.category, fields_data)
            
            # DM User
            dm_embed = make_embed(
                "Ticket Created",
                f"> Your **{self.category}** ticket has been opened.\n> A staff member will be with you shortly.\n> Reply to this DM to send further details.",
                kind="support",
                scope=SCOPE_SUPPORT,
                guild=interaction.guild,
            )
            await interaction.user.send(embed=dm_embed)
            
            # Log Action
            await log_modmail_action(guild, "Ticket Created", [
                ("User", interaction.user.mention),
                ("Category", self.category),
                ("Ticket ID", str(thread.id))
            ])
            
            await interaction.followup.send("Ticket created successfully! Check your DMs.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"Failed to create ticket: {e}", ephemeral=True)

class ModmailPanelSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=label, description=truncate_text(description, 100))
            for label, description in MODMAIL_PANEL_CATEGORIES
        ]
        super().__init__(
            placeholder="Choose the ticket type you want to open...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="mm_ticket_type_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ModmailModal(self.values[0]))

class ModmailPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ModmailPanelSelect())


__all__ = [
    "ModmailPrioritySelect",
    "ModmailPriorityView",
    "ModmailTagsModal",
    "CannedReplySelect",
    "CannedReplyView",
    "ModmailControlView",
    "ModmailModal",
    "ModmailPanelSelect",
    "ModmailPanelView",
    "build_modmail_panel_embed",
    "build_modmail_settings_embed",
]
