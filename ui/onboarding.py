import discord
import json

class OnboardingView(discord.ui.View):
    def __init__(self, data, user_id: int, config: dict):
        super().__init__(timeout=None)
        self.data = data
        self.user_id = user_id
        self.config = config

        # Add role buttons from config
        onboarding_roles = config.get("onboarding_roles", [])
        for role_data in onboarding_roles[:5]:  # Max 5 per row
            self.add_item(RoleGrantButton(data, user_id, role_data))

    @discord.ui.button(label="Complete Onboarding", style=discord.ButtonStyle.success, row=4)
    async def complete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This onboarding is not for you.", ephemeral=True)
            return
        await self.data.set_onboarding(self.user_id, completed=1)

        # Grant completion role if configured
        completion_role_id = self.config.get("onboarding_completion_role_id")
        if completion_role_id:
            role = interaction.guild.get_role(int(completion_role_id))
            if role:
                try:
                    await interaction.user.add_roles(role)
                except Exception:
                    pass

        await interaction.response.send_message("Onboarding complete! Welcome!", ephemeral=True)
        button.disabled = True
        await interaction.message.edit(view=self)

class RoleGrantButton(discord.ui.Button):
    def __init__(self, data, user_id: int, role_data: dict):
        super().__init__(
            label=role_data.get("label", "Get Role"),
            style=discord.ButtonStyle.secondary,
            custom_id=f"onboarding_role_{user_id}_{role_data.get('role_id')}"
        )
        self.data = data
        self.user_id = user_id
        self.role_data = role_data

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This onboarding is not for you.", ephemeral=True)
            return

        role_id = self.role_data.get("role_id")
        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return

        await interaction.user.add_roles(role)

        onboarding = await self.data.get_onboarding(self.user_id)
        roles_granted = json.loads(onboarding.get("roles_granted", "[]")) if onboarding else []
        if role_id not in roles_granted:
            roles_granted.append(role_id)
        await self.data.set_onboarding(self.user_id, roles_granted=json.dumps(roles_granted))

        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send(f"Got the **{role.name}** role!", ephemeral=True)
