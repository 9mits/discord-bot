import discord
import json

class AddNoteModal(discord.ui.Modal, title="Add Case Note"):
    note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, data, case_number: int):
        super().__init__()
        self.data = data
        self.case_number = case_number

    async def on_submit(self, interaction: discord.Interaction):
        await self.data.add_case_note(self.case_number, interaction.user.id, self.note.value)
        await interaction.response.send_message("Note added.", ephemeral=True)

class EditReasonModal(discord.ui.Modal, title="Edit Case Reason"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, data, case_number: int, current_reason: str = ""):
        super().__init__()
        self.data = data
        self.case_number = case_number
        self.reason.default = current_reason

    async def on_submit(self, interaction: discord.Interaction):
        await self.data.update_case(self.case_number, reason=self.reason.value)
        await interaction.response.send_message("Reason updated.", ephemeral=True)

class CaseView(discord.ui.View):
    def __init__(self, data, case: dict):
        super().__init__(timeout=300)
        self.data = data
        self.case = case

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.secondary)
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddNoteModal(self.data, self.case["case_number"]))

    @discord.ui.button(label="Edit Reason", style=discord.ButtonStyle.secondary)
    async def edit_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditReasonModal(self.data, self.case["case_number"], self.case.get("reason", "")))

    @discord.ui.button(label="Close Case", style=discord.ButtonStyle.success)
    async def close_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.data.update_case(self.case["case_number"], status="closed")
        await interaction.response.send_message("Case closed.", ephemeral=True)
        self.close_case.disabled = True
        self.reopen_case.disabled = False
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Reopen Case", style=discord.ButtonStyle.danger, disabled=True)
    async def reopen_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.data.update_case(self.case["case_number"], status="open")
        await interaction.response.send_message("Case reopened.", ephemeral=True)
        self.close_case.disabled = False
        self.reopen_case.disabled = True
        await interaction.message.edit(view=self)
