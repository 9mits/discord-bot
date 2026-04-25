from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from modules.mbx_constants import HOLO_PRIMARY, HOLO_SECONDARY, HOLO_TERTIARY, SCOPE_ROLES
from modules.mbx_context import abuse_system, bot, tree
from modules.mbx_embeds import make_confirmation_embed, make_embed, make_empty_state_embed
from modules.mbx_formatters import hex_valid
from modules.mbx_images import fetch_image_bytes
from modules.mbx_roles import (
    build_role_landing_embed,
    build_role_info_embed,
    build_role_permissions_overview_embed,
    build_role_registry_embed,
    build_role_settings_embed,
    get_custom_role_limit,
)
from modules.mbx_utils import extract_snowflake_id, now_iso, truncate_text
from ui.shared import ExpirableMixin


logger = logging.getLogger("MGXBot")


async def _invoke_role_manage(interaction: discord.Interaction, action: str, target, limit: int) -> None:
    from cogs.roles import role_manage

    await role_manage.callback(interaction, action, target, limit)


class CreateRoleModal(discord.ui.Modal, title="Create your custom role"):
    role_name = discord.ui.TextInput(label="Role name", max_length=100)
    hex_color = discord.ui.TextInput(label="Hex color (Optional)", placeholder="#FF66CC", max_length=7, required=False)
    icon_url = discord.ui.TextInput(label="Icon URL (optional)", required=False, placeholder="https://...")

    def __init__(self, member: discord.Member):
        super().__init__()
        self._member = member

    async def on_submit(self, interaction: discord.Interaction):
        member = self._member
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True)

        allowed = get_custom_role_limit(member)
        if allowed <= 0:
            await interaction.followup.send("You are not authorized to create a custom role.", ephemeral=True)
            return

        current = 1 if str(member.id) in bot.data_manager.roles else 0
        if current >= allowed:
            await interaction.followup.send(f"You are allowed {allowed} role(s) and already have {current}.", ephemeral=True)
            return

        name = self.role_name.value.strip()[:100]
        color_text = self.hex_color.value.strip() if self.hex_color.value else None
        
        if color_text:
            if not hex_valid(color_text):
                await interaction.followup.send("Invalid hex color (use #RRGGBB).", ephemeral=True)
                return
        else:
            color_text = "#000000" # Default

        try:
            color = discord.Color(int(color_text.lstrip("#"), 16))
        except Exception:
            color = discord.Color.default()

        try:
            new_role = await guild.create_role(name=name, color=color, mentionable=True, reason=f"Custom role created by {member}")
        except discord.Forbidden:
            await interaction.followup.send("Bot lacks permissions or role hierarchy prevents creation.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to create role: {e}", ephemeral=True)
            return

        anchor_id = bot.data_manager.config.get("role_anchor")
        anchor = guild.get_role(anchor_id) if anchor_id else None
        if not anchor:
            try: anchor = await guild.fetch_role(anchor_id)
            except Exception: pass
            
        if anchor:
            try:
                target_pos = max(anchor.position - 1, 1)
                await new_role.edit(position=target_pos, reason="Positioning under anchor")
            except Exception:
                pass

        icon_val = self.icon_url.value.strip() if self.icon_url.value else None
        icon_warning = None
        applied_icon_url = None
        if icon_val:
            img, icon_warning = await fetch_image_bytes(icon_val)
            if img:
                try:
                    await new_role.edit(display_icon=img)
                    applied_icon_url = icon_val
                except Exception:
                    icon_warning = "Role created, but Discord rejected the icon."

        try:
            await member.add_roles(new_role, reason="Assigned custom role")
        except Exception:
            pass

        bot.data_manager.roles[str(member.id)] = {
            "role_id": new_role.id,
            "name": name,
            "color": color_text,
            "icon": applied_icon_url,
            "created_at": now_iso()
        }
        await bot.data_manager.save_roles()

        embed = make_embed(
            "Custom Role Created",
            f"> Your role {new_role.mention} has been created successfully.",
            kind="success",
            scope=SCOPE_ROLES,
            guild=guild,
        )
        embed.color = color
        embed.add_field(name="Role", value=f"{new_role.mention}", inline=False)
        embed.add_field(name="Color", value=color_text, inline=True)
        if applied_icon_url:
            embed.set_thumbnail(url=applied_icon_url)
        if icon_warning:
            embed.add_field(name="Icon", value=f"> {truncate_text(icon_warning, 300)}", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

class EditNameModal(discord.ui.Modal, title="Edit role name"):
    new_name = discord.ui.TextInput(label="New role name", max_length=100)
    def __init__(self, member, role):
        super().__init__()
        self.member = member
        self.role = role
    async def on_submit(self, interaction):
        name = self.new_name.value.strip()[:100]
        try:
            await self.role.edit(name=name, reason=f"Renamed by {interaction.user}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)
            return
        rec = bot.data_manager.roles.get(str(self.member.id))
        if rec:
            rec["name"] = name
            await bot.data_manager.save_roles()
        embed = make_embed(
            "Role Renamed",
            f"> The custom role has been renamed to `{name}`.",
            kind="success",
            scope=SCOPE_ROLES,
            guild=interaction.guild,
        )
        embed.color = self.role.color
        await interaction.response.send_message(embed=embed, ephemeral=True)

class EditColorModal(discord.ui.Modal, title="Edit role color"):
    new_color = discord.ui.TextInput(label="Hex color", placeholder="#FF66CC", max_length=7)
    def __init__(self, member, role):
        super().__init__()
        self.member = member
        self.role = role
    async def on_submit(self, interaction):
        c = self.new_color.value.strip()
        if not hex_valid(c):
            await interaction.response.send_message("Invalid hex color.", ephemeral=True)
            return
        try:
            color = discord.Color(int(c.lstrip("#"),16))
            await self.role.edit(color=color, reason=f"Edited by {interaction.user}")
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)
            return
        rec = bot.data_manager.roles.get(str(self.member.id))
        if rec:
            rec["color"] = c
            await bot.data_manager.save_roles()
        embed = make_embed(
            "Role Color Updated",
            f"> The role color has been changed to `{c}`.",
            kind="success",
            scope=SCOPE_ROLES,
            guild=interaction.guild,
        )
        embed.color = color
        await interaction.response.send_message(embed=embed, ephemeral=True)

class GradientModal(discord.ui.Modal, title="Set Gradient Style"):
    secondary = discord.ui.TextInput(label="Secondary Color (Hex)", placeholder="#RRGGBB", min_length=7, max_length=7)

    def __init__(self, member, role):
        super().__init__()
        self.member = member
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        sec_val = self.secondary.value.strip()
        if not hex_valid(sec_val):
            await interaction.response.send_message("Invalid hex color.", ephemeral=True)
            return

        sec_int = int(sec_val.lstrip("#"), 16)
        prim_int = self.role.color.value

        try:
            edited_role = await self.role.edit(
                color=prim_int,
                secondary_color=sec_int,
                tertiary_color=None,
                reason=f"Gradient style update by {interaction.user}",
            )
            if edited_role is not None:
                self.role = edited_role

            rec = bot.data_manager.roles.get(str(self.member.id))
            if rec:
                rec['color'] = f"#{prim_int:06X}"
                rec['secondary_color'] = sec_val
                rec['tertiary_color'] = None
                await bot.data_manager.save_roles()

            await interaction.response.send_message(
                embed=make_confirmation_embed(
                    "Gradient Style Applied",
                    f"> The role now uses Discord's enhanced gradient colors with secondary color `{sec_val}`.",
                    scope=SCOPE_ROLES,
                    guild=interaction.guild,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to update style: {e.status} {e.text}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to update style: {e}", ephemeral=True)

class RoleStyleView(discord.ui.View):
    def __init__(self, member, role):
        super().__init__(timeout=60)
        self.member = member
        self.role = role

    @discord.ui.button(label="Static (Reset)", style=discord.ButtonStyle.secondary)
    async def static_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            edited_role = await self.role.edit(
                color=self.role.color.value,
                secondary_color=None,
                tertiary_color=None,
                reason=f"Style reset by {interaction.user}",
            )
            if edited_role is not None:
                self.role = edited_role

            rec = bot.data_manager.roles.get(str(self.member.id))
            if rec:
                rec['secondary_color'] = None
                rec['tertiary_color'] = None
                await bot.data_manager.save_roles()
            await interaction.response.send_message("Role style reset to Static.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed: {e.status} {e.text}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @discord.ui.button(label="Gradient", style=discord.ButtonStyle.primary)
    async def gradient_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GradientModal(self.member, self.role))

    @discord.ui.button(label="Holographic", style=discord.ButtonStyle.success)
    async def holographic_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            edited_role = await self.role.edit(
                color=HOLO_PRIMARY,
                secondary_color=HOLO_SECONDARY,
                tertiary_color=HOLO_TERTIARY,
                reason=f"Holographic style update by {interaction.user}",
            )
            if edited_role is not None:
                self.role = edited_role

            rec = bot.data_manager.roles.get(str(self.member.id))
            if rec:
                rec['color'] = f"#{HOLO_PRIMARY:06X}"
                rec['secondary_color'] = f"#{HOLO_SECONDARY:06X}"
                rec['tertiary_color'] = f"#{HOLO_TERTIARY:06X}"
                await bot.data_manager.save_roles()

            await interaction.response.send_message(
                embed=make_confirmation_embed(
                    "Holographic Style Applied",
                    "> The role now uses Discord's holographic enhanced role style preset.",
                    scope=SCOPE_ROLES,
                    guild=interaction.guild,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed: {e.status} {e.text}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

class IconURLModal(discord.ui.Modal, title="Set Icon via URL"):
    url = discord.ui.TextInput(label="Image URL", placeholder="https://...", required=True)

    def __init__(self, member, role):
        super().__init__()
        self.member = member
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.url.value.strip()
        
        img, error = await fetch_image_bytes(val)
        if not img:
            await interaction.followup.send(error or "Failed to download image. Check the URL.", ephemeral=True)
            return

        try:
            await self.role.edit(display_icon=img, reason=f"Icon updated by {interaction.user}")
            rec = bot.data_manager.roles.get(str(self.member.id))
            if rec:
                rec["icon"] = val
                await bot.data_manager.save_roles()
            await interaction.followup.send("Icon updated successfully!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to update icon: {e}", ephemeral=True)

class UploadIconView(discord.ui.View):
    def __init__(self, member, role):
        super().__init__(timeout=60)
        self.member = member
        self.role = role

    @discord.ui.button(label="Upload File", style=discord.ButtonStyle.primary)
    async def upload_file(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        await interaction.followup.send(f"{interaction.user.mention}, please reply to this message with your image file now.", ephemeral=True)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.attachments

        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            attachment = msg.attachments[0]
            if attachment.size > 256000:
                await interaction.followup.send("Image too big! Max size is 256KB.", ephemeral=True)
                return
            
            img_data = await attachment.read()
            await self.role.edit(display_icon=img_data, reason=f"Icon updated by {interaction.user}")
            await interaction.followup.send("Icon updated successfully!", ephemeral=True)
            
            rec = bot.data_manager.roles.get(str(self.member.id))
            if rec:
                rec["icon"] = attachment.url
                await bot.data_manager.save_roles()
            
            try: await msg.delete()
            except Exception: pass

        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @discord.ui.button(label="Enter URL", style=discord.ButtonStyle.secondary)
    async def enter_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IconURLModal(self.member, self.role))

class RoleActionSelect(discord.ui.Select):
    def __init__(self, member, role):
        self.member = member
        self.role = role
        options = [
            discord.SelectOption(label="Rename Role", value="name", description="Change the role name."),
            discord.SelectOption(label="Change Color", value="color", description="Update the primary role color."),
            discord.SelectOption(label="Update Icon", value="icon", description="Open the icon upload or URL options."),
            discord.SelectOption(label="Change Style", value="style", description="Pick static, gradient, or holographic style."),
            discord.SelectOption(label="Delete Role", value="delete", description="Remove the custom role permanently."),
        ]
        super().__init__(placeholder="Choose a role action...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "name":
            await interaction.response.send_modal(EditNameModal(self.member, self.role))
            return
        if action == "color":
            await interaction.response.send_modal(EditColorModal(self.member, self.role))
            return
        if action == "icon":
            await interaction.response.send_message("Choose icon method:", view=UploadIconView(self.member, self.role), ephemeral=True)
            return
        if action == "style":
            await interaction.response.send_message("Choose a role style:", view=RoleStyleView(self.member, self.role), ephemeral=True)
            return
        if action == "delete":
            await interaction.response.send_message("Are you sure?", view=ConfirmDelete(self.member, self.role), ephemeral=True)

class EditView(discord.ui.View):
    def __init__(self, member, role):
        super().__init__(timeout=None)
        self.member = member
        self.role = role
        self.add_item(RoleActionSelect(member, role))

    @discord.ui.button(label="Refresh Panel", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        rec = bot.data_manager.roles.get(str(self.member.id))
        role_obj = interaction.guild.get_role(rec.get("role_id")) if rec else None
        if not rec or not role_obj:
            await interaction.response.edit_message(
                embed=make_empty_state_embed(
                    "Custom Role Not Found",
                    "> The tracked custom role could not be loaded. Re-run `/role` to create or reopen it.",
                    scope=SCOPE_ROLES,
                    guild=interaction.guild,
                    thumbnail=self.member.display_avatar.url,
                ),
                view=None,
            )
            return
        self.role = role_obj
        await interaction.response.edit_message(embed=build_role_info_embed(self.member, rec, role_obj, include_tips=True), view=EditView(self.member, role_obj))

class ConfirmDelete(discord.ui.View):
    def __init__(self, member, role):
        super().__init__(timeout=60)
        self.member = member
        self.role = role

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.role.delete(reason=f"Deleted by {interaction.user} (via Menu)")
        except Exception:
            pass
        bot.data_manager.roles.pop(str(self.member.id), None)
        await bot.data_manager.save_roles()
        await interaction.response.edit_message(content="Role deleted.", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Deletion canceled.", embed=None, view=None)
        self.stop()

class RoleSettingsTargetModal(discord.ui.Modal):
    target_value = discord.ui.TextInput(label="Target ID or Mention", placeholder="Paste a user or role ID", max_length=30)
    limit_value = discord.ui.TextInput(label="Role Limit", placeholder="1", required=False, max_length=3)

    def __init__(self, *, title: str, action: str, target_type: str, require_limit: bool = False):
        super().__init__(title=title)
        self.action = action
        self.target_type = target_type
        self.require_limit = require_limit
        self.limit_value.required = require_limit
        if not require_limit:
            self.remove_item(self.limit_value)

    async def on_submit(self, interaction: discord.Interaction):
        target_id = extract_snowflake_id(self.target_value.value)
        if not target_id:
            await interaction.response.send_message("Enter a valid ID or mention.", ephemeral=True)
            return

        if self.target_type == "member":
            target = interaction.guild.get_member(target_id)
            if not target:
                try:
                    target = await interaction.guild.fetch_member(target_id)
                except Exception:
                    target = None
        else:
            target = interaction.guild.get_role(target_id)

        if target is None:
            await interaction.response.send_message("That target could not be found in this server.", ephemeral=True)
            return

        limit = 1
        if self.require_limit:
            try:
                limit = max(1, int(self.limit_value.value or 1))
            except ValueError:
                await interaction.response.send_message("Role limit must be a number.", ephemeral=True)
                return

        await _invoke_role_manage(interaction, self.action, target, limit)

class RoleSettingsManageMemberModal(discord.ui.Modal, title="Open Member Role Panel"):
    member_value = discord.ui.TextInput(label="Member ID or Mention", placeholder="Paste a user ID", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        member_id = extract_snowflake_id(self.member_value.value)
        if not member_id:
            await interaction.response.send_message("Enter a valid member ID or mention.", ephemeral=True)
            return
        member = interaction.guild.get_member(member_id)
        if not member:
            try:
                member = await interaction.guild.fetch_member(member_id)
            except Exception:
                member = None
        if member is None:
            await interaction.response.send_message("That member could not be found in this server.", ephemeral=True)
            return
        await _invoke_role_manage(interaction, "manage_user", member, 1)

class RoleSettingsAccessSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Allow Member", value="whitelist_member", description="Whitelist one member and set a role limit."),
            discord.SelectOption(label="Allow Role", value="whitelist_role", description="Whitelist one role and set a role limit."),
            discord.SelectOption(label="Block Member", value="blacklist_member", description="Block one member from custom role access."),
            discord.SelectOption(label="Block Role", value="blacklist_role", description="Block one role from custom role access."),
            discord.SelectOption(label="Reset Member", value="reset_member", description="Remove one member from all role access lists."),
            discord.SelectOption(label="Reset Role", value="reset_role", description="Remove one role from all role access lists."),
        ]
        super().__init__(placeholder="Choose an access rule action...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "whitelist_member":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Allow Member", action="whitelist", target_type="member", require_limit=True))
            return
        if value == "whitelist_role":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Allow Role", action="whitelist", target_type="role", require_limit=True))
            return
        if value == "blacklist_member":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Block Member", action="blacklist", target_type="member"))
            return
        if value == "blacklist_role":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Block Role", action="blacklist", target_type="role"))
            return
        if value == "reset_member":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Reset Member", action="reset", target_type="member"))
            return
        if value == "reset_role":
            await interaction.response.send_modal(RoleSettingsTargetModal(title="Reset Role", action="reset", target_type="role"))

class RoleSettingsAccessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RoleSettingsAccessSelect())

class RoleSettingsActionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Refresh Overview", value="refresh", description="Reload the counts and dashboard summary."),
            discord.SelectOption(label="Review Access", value="review_access", description="Open the current allow and block lists."),
            discord.SelectOption(label="Tracked Roles", value="tracked_roles", description="Open the current custom role registry."),
            discord.SelectOption(label="Change Access Rules", value="access_rules", description="Open the access rule action menu."),
            discord.SelectOption(label="Manage Member Role", value="manage_member", description="Open one member's custom role panel."),
        ]
        super().__init__(placeholder="Choose a role settings action...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "refresh":
            await interaction.response.edit_message(embed=build_role_settings_embed(interaction.guild), view=RoleSettingsView())
            return
        if action == "review_access":
            await interaction.response.send_message(embed=build_role_permissions_overview_embed(interaction.guild), ephemeral=True)
            return
        if action == "tracked_roles":
            await interaction.response.send_message(embed=build_role_registry_embed(interaction.guild), ephemeral=True)
            return
        if action == "access_rules":
            await interaction.response.send_message(
                embed=build_role_permissions_overview_embed(interaction.guild),
                view=RoleSettingsAccessView(),
                ephemeral=True,
            )
            return
        if action == "manage_member":
            await interaction.response.send_modal(RoleSettingsManageMemberModal())

class RoleSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RoleSettingsActionSelect())


__all__ = [
    "CreateRoleModal",
    "EditNameModal",
    "EditColorModal",
    "GradientModal",
    "RoleStyleView",
    "IconURLModal",
    "UploadIconView",
    "RoleActionSelect",
    "EditView",
    "ConfirmDelete",
    "RoleSettingsTargetModal",
    "RoleSettingsManageMemberModal",
    "RoleSettingsAccessSelect",
    "RoleSettingsAccessView",
    "RoleSettingsActionSelect",
    "RoleSettingsView",
    "build_role_info_embed",
    "build_role_landing_embed",
    "build_role_permissions_overview_embed",
    "build_role_registry_embed",
    "build_role_settings_embed",
]
