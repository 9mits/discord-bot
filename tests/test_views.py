"""Tests for UI views and core module functions."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

import modules.mbx_automod
import modules.mbx_branding
import modules.mbx_embeds
import modules.mbx_images
import modules.mbx_modmail
import ui.moderation
import ui.config
from modules.mbx_images import (
    fetch_image_bytes,
    prepare_modmail_relay_attachments,
    validate_image_fetch_url,
)
from modules.mbx_embeds import (
    _build_footer_text,
    _format_branding_panel_value,
)
from modules.mbx_logging import normalize_log_embed
from modules.mbx_constants import SCOPE_MODERATION, SCOPE_SYSTEM, BRAND_NAME
from modules.mbx_branding import _build_branding_panel_embed, apply_guild_member_branding
from modules.mbx_modmail import send_modmail_thread_intro


def make_interaction():
    response = SimpleNamespace(
        send_message=AsyncMock(),
        edit_message=AsyncMock(),
        defer=AsyncMock(),
        is_done=Mock(return_value=False),
    )
    followup = SimpleNamespace(send=AsyncMock())
    return SimpleNamespace(
        response=response,
        followup=followup,
        user=SimpleNamespace(id=42, mention="<@42>", display_name="Moderator"),
        guild=SimpleNamespace(name="Guild", icon=None),
        message=SimpleNamespace(embeds=[]),
        client=SimpleNamespace(fetch_user=AsyncMock()),
    )


class FakeContent:
    def __init__(self, chunks=None):
        self._chunks = chunks or []

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


class FakeResponse:
    def __init__(self, status, *, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {}
        self.content = FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def get(self, *_args, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class FakeAttachment:
    def __init__(self, filename, size):
        self.filename = filename
        self.size = size
        self.calls = 0

    async def to_file(self):
        self.calls += 1
        return self.filename


# ---------------------------------------------------------------------------
# Auth guard tests — UI views must reject non-staff interactions
# ---------------------------------------------------------------------------

class ViewAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_revoke_appeal_entrypoint_rejects_non_staff(self):
        interaction = make_interaction()
        view = ui.moderation.RevokeAppealView(
            target_id=1, moderator_id=2, duration=0,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        with patch.object(ui.moderation, "is_staff", return_value=False):
            await view.children[0].callback(interaction)
        interaction.response.send_message.assert_awaited_once_with("Access denied.", ephemeral=True)

    async def test_confirm_revoke_view_rejects_non_staff(self):
        interaction = make_interaction()
        parent_view = SimpleNamespace(finish_revoke=AsyncMock())
        view = ui.moderation.ConfirmRevokeView(parent_view, SimpleNamespace())
        with patch.object(ui.moderation, "is_staff", return_value=False):
            await view.children[0].callback(interaction)
        interaction.response.send_message.assert_awaited_once_with("Access denied.", ephemeral=True)
        parent_view.finish_revoke.assert_not_awaited()

    async def test_deny_appeal_modal_rejects_non_staff(self):
        interaction = make_interaction()
        modal = ui.moderation.DenyAppealModal(
            target_id=1,
            origin_message=SimpleNamespace(embeds=[SimpleNamespace()]),
            view=SimpleNamespace(children=[]),
        )
        with patch.object(ui.moderation, "is_staff", return_value=False):
            await modal.on_submit(interaction)
        interaction.response.send_message.assert_awaited_once_with("Access denied.", ephemeral=True)

    async def test_finish_revoke_rejects_non_staff(self):
        interaction = make_interaction()
        view = ui.moderation.RevokeAppealView(
            target_id=1, moderator_id=2, duration=0,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        with patch.object(ui.moderation, "is_staff", return_value=False):
            await view.finish_revoke(interaction, SimpleNamespace(embeds=[SimpleNamespace()]))
        interaction.response.send_message.assert_awaited_once_with("Access denied.", ephemeral=True)

    async def test_apply_automod_report_response_rejects_non_staff(self):
        interaction = make_interaction()
        with (
            patch.object(modules.mbx_automod, "is_staff", return_value=False),
            patch.object(modules.mbx_automod, "respond_with_error", AsyncMock()) as mock_error,
        ):
            success = await modules.mbx_automod.apply_automod_report_response(
                interaction,
                guild_id=1,
                reporter_id=2,
                warning_id="warn-1",
                rule_name="Rule",
                response_key="acknowledge",
                response_text="Thanks",
                source_message=None,
            )
        self.assertFalse(success)
        mock_error.assert_awaited_once_with(
            interaction, "Access denied.", scope=SCOPE_MODERATION
        )


# ---------------------------------------------------------------------------
# Image fetch / validation tests
# ---------------------------------------------------------------------------

class ImageFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_validate_image_fetch_url_rejects_non_https(self):
        _, error = await validate_image_fetch_url("http://example.com/image.png")
        self.assertEqual(error, "Image URLs must use HTTPS.")

    async def test_validate_image_fetch_url_rejects_credentials(self):
        _, error = await validate_image_fetch_url("https://user:pass@example.com/image.png")
        self.assertEqual(error, "Image URLs with embedded credentials are not allowed.")

    async def test_validate_image_fetch_url_rejects_private_host(self):
        with patch.object(
            modules.mbx_images, "_resolve_image_host_addresses",
            AsyncMock(return_value=(["127.0.0.1"], None)),
        ):
            _, error = await validate_image_fetch_url("https://localhost/image.png")
        self.assertEqual(error, "Image URLs must use a public host.")

    async def test_fetch_image_bytes_rejects_redirects(self):
        session = FakeSession(FakeResponse(302))
        with (
            patch.object(
                modules.mbx_images, "validate_image_fetch_url",
                AsyncMock(return_value=("https://cdn.example/image.png", None)),
            ),
            patch.object(
                modules.mbx_images, "_active_bot",
                return_value=SimpleNamespace(session=session),
            ),
        ):
            payload, error = await fetch_image_bytes("https://cdn.example/image.png")
        self.assertIsNone(payload)
        self.assertEqual(error, "Image URLs cannot redirect.")
        self.assertFalse(session.last_kwargs["allow_redirects"])


# ---------------------------------------------------------------------------
# Modmail attachment / threading tests
# ---------------------------------------------------------------------------

class ModmailTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_modmail_relay_attachments_skips_oversized_and_extra_files(self):
        mib = 1024 * 1024
        attachments = [
            FakeAttachment("keep-1.png", mib),
            FakeAttachment("too-big.png", 9 * mib),
            FakeAttachment("keep-2.png", mib),
            FakeAttachment("keep-3.png", mib),
            FakeAttachment("keep-4.png", mib),
            FakeAttachment("keep-5.png", mib),
            FakeAttachment("extra.png", mib),
        ]
        files, notice = await prepare_modmail_relay_attachments(attachments)
        self.assertEqual(files, ["keep-1.png", "keep-2.png", "keep-3.png", "keep-4.png", "keep-5.png"])
        self.assertIn("first 5", notice)
        self.assertIn("over 8 MiB", notice)
        self.assertEqual(attachments[1].calls, 0)
        self.assertEqual(attachments[-1].calls, 0)

    async def test_prepare_modmail_relay_attachments_enforces_total_size_limit(self):
        mib = 1024 * 1024
        attachments = [
            FakeAttachment("keep-1.png", 8 * mib),
            FakeAttachment("keep-2.png", 8 * mib),
            FakeAttachment("skip-total.png", 5 * mib),
        ]
        files, notice = await prepare_modmail_relay_attachments(attachments)
        self.assertEqual(files, ["keep-1.png", "keep-2.png"])
        self.assertIn("20 MiB total", notice)
        self.assertEqual(attachments[-1].calls, 0)

    async def test_send_modmail_thread_intro_disables_mentions(self):
        thread = SimpleNamespace(send=AsyncMock())
        user = SimpleNamespace(mention="<@123>")
        await send_modmail_thread_intro(thread, user, "Report", ["**Subject**: @everyone"])
        allowed_mentions = thread.send.await_args.kwargs["allowed_mentions"]
        self.assertIsInstance(allowed_mentions, discord.AllowedMentions)
        self.assertFalse(allowed_mentions.everyone)
        self.assertFalse(allowed_mentions.roles)
        self.assertFalse(allowed_mentions.users)


# ---------------------------------------------------------------------------
# Embed / branding helper tests
# ---------------------------------------------------------------------------

class EmbedBrandingTests(unittest.IsolatedAsyncioTestCase):
    def test_format_branding_panel_value_uses_inline_code_for_empty_values(self):
        self.assertEqual(_format_branding_panel_value(None), "`Not set`")
        self.assertEqual(_format_branding_panel_value(""), "`Not set`")

    def test_build_footer_text_uses_guild_name_first(self):
        guild = SimpleNamespace(name="Cool Server")
        footer_text = _build_footer_text(SCOPE_SYSTEM, guild)
        self.assertEqual(footer_text, "Cool Server • Control Center")

    def test_build_footer_text_falls_back_to_brand_name_without_guild(self):
        footer_text = _build_footer_text(SCOPE_SYSTEM, None)
        self.assertEqual(footer_text, f"{BRAND_NAME} • {SCOPE_SYSTEM}")

    def test_normalize_log_embed_rebrands_footer_with_guild_icon(self):
        embed = discord.Embed(title="Test", description="Body")
        embed.set_footer(text="Wrong Footer", icon_url="https://cdn.example/old.png")
        guild = SimpleNamespace(
            name="Cool Server",
            icon=SimpleNamespace(url="https://cdn.example/server.png"),
        )
        normalized = normalize_log_embed(embed, guild=guild)
        self.assertEqual(normalized.footer.text, "Wrong Footer")
        self.assertEqual(str(normalized.footer.icon_url), "https://cdn.example/server.png")

    def test_build_branding_panel_embed_formats_unset_values_consistently(self):
        guild = SimpleNamespace(
            id=123,
            name="Cool Server",
            icon=SimpleNamespace(url="https://cdn.example/server.png"),
            me=SimpleNamespace(
                display_name="Cool Bot",
                display_avatar=SimpleNamespace(url="https://cdn.example/avatar.png"),
                guild_banner=None,
                guild_avatar=None,
            ),
            get_member=lambda _user_id: None,
        )
        fake_bot = SimpleNamespace(user=SimpleNamespace(name="Cool Bot"))
        with (
            patch.object(modules.mbx_branding, "_active_bot", return_value=fake_bot),
            patch.object(modules.mbx_embeds, "_get_branding_config", return_value={}),
        ):
            embed = _build_branding_panel_embed(guild)
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["Profile Bio"], "`Not set`")
        self.assertEqual(fields["Profile Avatar"], "`Not set`")
        self.assertEqual(fields["Profile Banner"], "`Not set`")
        self.assertEqual(fields["Modmail Banner"], "`Not set`")
        self.assertEqual(fields["Footer Icon"], "`Server icon`")

    async def test_branding_modal_labels_fit_discord_limit(self):
        modals = [
            ui.config.BrandingDisplayNameModal(),
            ui.config.BrandingAvatarModal(),
            ui.config.BrandingBannerModal(),
            ui.config.BrandingBioModal(),
            ui.config.BrandingModmailBannerModal(),
        ]
        for modal in modals:
            for child in modal.children:
                label = child.to_component_dict()["label"]
                self.assertLessEqual(len(label), 45, label)

    async def test_apply_guild_member_branding_uses_current_member_route_payload(self):
        request = AsyncMock()
        guild = SimpleNamespace(id=123)
        fake_bot = SimpleNamespace(http=SimpleNamespace(request=request))
        with (
            patch.object(
                modules.mbx_branding, "fetch_image_data_uri",
                AsyncMock(side_effect=[
                    ("data:image/png;base64,AAA", None),
                    ("data:image/png;base64,BBB", None),
                ]),
            ),
            patch.object(modules.mbx_branding, "_active_bot", return_value=fake_bot),
        ):
            error = await apply_guild_member_branding(
                guild,
                display_name="Server Bot",
                avatar_url="https://cdn.example/avatar.png",
                banner_url="https://cdn.example/banner.png",
                bio="Guild bio",
                reason="test update",
            )
        self.assertIsNone(error)
        request.assert_awaited_once()
        payload = request.await_args.kwargs["json"]
        self.assertEqual(payload["nick"], "Server Bot")
        self.assertEqual(payload["avatar"], "data:image/png;base64,AAA")
        self.assertEqual(payload["banner"], "data:image/png;base64,BBB")
        self.assertEqual(payload["bio"], "Guild bio")
        self.assertEqual(request.await_args.kwargs["reason"], "test update")


if __name__ == "__main__":
    unittest.main()
