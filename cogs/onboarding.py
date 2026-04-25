"""Onboarding slash command."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from modules.mbx_context import bot, tree
from modules.mbx_onboarding import create_session, persist_draft
from modules.mbx_permissions import require_capability
from ui.onboarding import OnboardingWizardView, build_onboarding_embed


@tree.command(name="start", description="Run the step-by-step server setup wizard")
@app_commands.default_permissions(manage_guild=True)
@require_capability("setup.run")
async def start_cmd(interaction: discord.Interaction):
    if not interaction.guild or not bot.data_manager:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    sessions = getattr(bot, "start_wizard_sessions", None)
    if sessions is None:
        bot.start_wizard_sessions = {}
        sessions = bot.start_wizard_sessions

    key = (interaction.guild.id, interaction.user.id)
    session = sessions.get(key)
    if session is None or session.expired():
        session = create_session(interaction.guild.id, interaction.user.id, bot.data_manager.config)
        sessions[key] = session

    persist_draft(bot.data_manager.config, session)
    await bot.data_manager.save_config()
    await interaction.response.send_message(
        embed=build_onboarding_embed(interaction.guild, session),
        view=OnboardingWizardView(session),
        ephemeral=True,
    )


async def setup(bot_instance: commands.Bot) -> None:
    bot_instance.tree.add_command(start_cmd)
