import discord

class CreateRoleModal(discord.ui.Modal, title="Create Custom Role"):
    name = discord.ui.TextInput(label="Role name", max_length=100)
    color = discord.ui.TextInput(label="Color (hex, e.g. #FF0000)", max_length=7, required=False, default="#000000")

    def __init__(self, data, user: discord.Member):
        super().__init__()
        self.data = data
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await self.data.get_config()
        existing = await self.data.get_custom_role(self.user.id)
        if existing:
            await interaction.followup.send("User already has a custom role.", ephemeral=True)
            return
        try:
            hex_color = int(self.color.value.strip("#"), 16)
        except ValueError:
            hex_color = 0

        anchor_role_id = config.get("anchor_role_id")
        anchor_role = interaction.guild.get_role(int(anchor_role_id)) if anchor_role_id else None

        role = await interaction.guild.create_role(
            name=self.name.value,
            color=discord.Color(hex_color),
            reason=f"Custom role for {self.user}"
        )
        if anchor_role:
            try:
                await interaction.guild.edit_role_positions({role: anchor_role.position})
            except Exception:
                pass
        await self.user.add_roles(role)
        await self.data.set_custom_role(self.user.id, role.id, self.name.value)
        await interaction.followup.send(f"Created role **{self.name.value}** for {self.user.mention}", ephemeral=True)
