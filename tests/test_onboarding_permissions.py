from __future__ import annotations

import unittest
from types import SimpleNamespace

import discord

import modules.mbx_permissions as mbx_permissions
import ui.onboarding as onboarding_ui
from modules.mbx_onboarding import (
    CHANNEL_FIELDS,
    WizardSession,
    advance,
    finalize_session,
    set_channel,
    set_template,
)
from modules.mbx_permission_engine import default_permission_payload, evaluate_command_access
from modules.mbx_templates import apply_template


class PermissionOverrideTests(unittest.TestCase):
    def test_evaluate_command_access_applies_deny_before_capability(self):
        config = {
            "permissions": default_permission_payload(),
        }
        config["permissions"]["role_capabilities"] = {"10": ["mod.punish"]}
        config["permissions"]["command_overrides"] = {
            "mod punish": {"deny_users": [7]},
        }
        member = SimpleNamespace(
            id=7,
            roles=[SimpleNamespace(id=10)],
            guild_permissions=discord.Permissions.none(),
        )
        self.assertFalse(evaluate_command_access(member, "mod punish", "mod.punish", config))

    def test_evaluate_command_access_allows_override_role(self):
        config = {
            "permissions": default_permission_payload(),
        }
        config["permissions"]["command_overrides"] = {
            "mod punish": {"allow_roles": [20]},
        }
        member = SimpleNamespace(
            id=8,
            roles=[SimpleNamespace(id=20)],
            guild_permissions=discord.Permissions.none(),
        )
        self.assertTrue(evaluate_command_access(member, "mod punish", "mod.punish", config))

    def test_evaluate_command_access_required_capability_override(self):
        config = {
            "permissions": default_permission_payload(),
        }
        config["permissions"]["command_overrides"] = {
            "setup import": {"required_capability": "permissions.edit"},
        }
        perms = discord.Permissions.none()
        perms.manage_guild = True
        member = SimpleNamespace(id=8, roles=[], guild_permissions=perms)
        self.assertTrue(evaluate_command_access(member, "setup import", "config.import", config))

    def test_can_use_panel_applies_panel_override(self):
        config = {
            "permissions": default_permission_payload(),
        }
        config["permissions"]["panel_overrides"] = {
            "features": {"allow_roles": [20]},
            "modmail": {"deny_users": [7]},
        }
        original_bot = mbx_permissions.bot
        mbx_permissions.bot = SimpleNamespace(data_manager=SimpleNamespace(_configs={1: config}))
        try:
            interaction = SimpleNamespace(
                guild_id=1,
                guild=SimpleNamespace(owner_id=99),
                user=SimpleNamespace(
                    id=7,
                    roles=[SimpleNamespace(id=20)],
                    guild_permissions=discord.Permissions.none(),
                ),
            )
            self.assertTrue(mbx_permissions.can_use_panel(interaction, "features", "config.edit"))
            self.assertFalse(mbx_permissions.can_use_panel(interaction, "modmail", "modmail.settings"))
        finally:
            mbx_permissions.bot = original_bot


class TemplateApplicationTests(unittest.TestCase):
    def test_apply_template_stamps_metadata_and_permissions(self):
        config = {"feature_flags": {"advanced_case_panel": False}}
        apply_template(config, "support-heavy")
        self.assertEqual(config["_setup_metadata"]["last_applied_template"], "support-heavy")
        self.assertIn("permissions", config)
        self.assertIn("modmail.reply", config["permissions"]["discord_permission_capabilities"]["manage_messages"])


class WizardSessionTests(unittest.TestCase):
    def test_wizard_requires_template_before_advancing(self):
        session = WizardSession(guild_id=1, user_id=2, started_at=discord.utils.utcnow())
        self.assertEqual(advance(session), ["Choose a setup template before continuing."])
        set_template(session, "blank")
        self.assertEqual(advance(session), [])
        self.assertEqual(session.step.key, "channels")

    def test_wizard_channel_step_and_finalize(self):
        session = WizardSession(guild_id=1, user_id=2, started_at=discord.utils.utcnow())
        set_template(session, "balanced")
        advance(session)
        for index, (key, _label) in enumerate(CHANNEL_FIELDS, start=100):
            set_channel(session, key, index)
        self.assertEqual(advance(session), [])
        config = {"_branding": {"display_name": "Keep"}}
        finalize_session(config, session)
        self.assertTrue(config["_setup_complete"])
        self.assertEqual(config["_branding"]["display_name"], "Keep")
        self.assertIn("permissions", config)

    def test_log_channel_selection_ignores_channel_step_field(self):
        session = WizardSession(guild_id=1, user_id=2, started_at=discord.utils.utcnow())
        session.staging_config["_selected_channel_field"] = "category_archive"
        self.assertEqual(onboarding_ui._selected_channel_field(session, log_fields=True), "general_log_channel_id")


if __name__ == "__main__":
    unittest.main()
