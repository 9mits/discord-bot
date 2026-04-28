import discord
from config import BRAND_COLOR, BRAND_NAME

def success_embed(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"{title}", description=description, color=0x57F287)

def error_embed(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=f"{title}", description=description, color=0xED4245)

def info_embed(title: str, description: str = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=BRAND_COLOR)

async def send_error(interaction: discord.Interaction, message: str, ephemeral: bool = True):
    embed = error_embed("Error", message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
