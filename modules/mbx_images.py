"""Image fetch, validate, and data-URI helpers.

Extracted from mbx_legacy. Self-contained — only depends on aiohttp, asyncio,
and the bot proxy (for the HTTP session).
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

import aiohttp

from modules.mbx_context import bot


ROLE_ICON_MAX_BYTES = 256000
PROFILE_BRANDING_MAX_BYTES = 8 * 1024 * 1024
MODMAIL_RELAY_MAX_FILES = 5
MODMAIL_RELAY_MAX_FILE_BYTES = 8 * 1024 * 1024
MODMAIL_RELAY_MAX_TOTAL_BYTES = 20 * 1024 * 1024


async def _resolve_image_host_addresses(hostname: str) -> Tuple[List[str], Optional[str]]:
    try:
        return [str(ipaddress.ip_address(hostname))], None
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return [], "Image host could not be resolved."
    except Exception:
        return [], "Image host could not be validated."

    addresses: List[str] = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        return [], "Image host could not be resolved."
    return addresses, None


def _is_public_image_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


async def validate_image_fetch_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    candidate = str(url or "").strip()
    parsed = urlsplit(candidate)

    if parsed.scheme.lower() != "https":
        return None, "Image URLs must use HTTPS."
    if parsed.username or parsed.password:
        return None, "Image URLs with embedded credentials are not allowed."
    if not parsed.hostname:
        return None, "Image URL must include a hostname."

    addresses, error = await _resolve_image_host_addresses(parsed.hostname)
    if error:
        return None, error
    if any(not _is_public_image_ip(address) for address in addresses):
        return None, "Image URLs must use a public host."
    return candidate, None


def _format_image_size_limit(max_bytes: int) -> str:
    if max_bytes % (1024 * 1024) == 0:
        return f"{max_bytes // (1024 * 1024)}MB"
    if max_bytes % 1000 == 0:
        return f"{max_bytes // 1000}KB"
    return f"{max_bytes} bytes"


async def fetch_image_asset(
    url: str,
    timeout: int = 10,
    max_bytes: int = ROLE_ICON_MAX_BYTES,
) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    if not bot.session:
        return None, None, "Image download is unavailable right now."

    validated_url, error = await validate_image_fetch_url(url)
    if error:
        return None, None, error

    try:
        request_timeout = aiohttp.ClientTimeout(total=timeout)
        async with bot.session.get(
            validated_url,
            timeout=request_timeout,
            allow_redirects=False,
            headers={"Accept": "image/*"},
        ) as resp:
            if 300 <= resp.status < 400:
                return None, None, "Image URLs cannot redirect."
            if resp.status != 200:
                return None, None, "Failed to download image. Check the URL."

            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if not content_type.startswith("image/"):
                return None, None, "URL did not return an image."

            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return None, None, f"Image too big! Max size is {_format_image_size_limit(max_bytes)}."
                except ValueError:
                    pass

            payload = bytearray()
            async for chunk in resp.content.iter_chunked(16384):
                payload.extend(chunk)
                if len(payload) > max_bytes:
                    return None, None, f"Image too big! Max size is {_format_image_size_limit(max_bytes)}."
            return bytes(payload), content_type, None
    except asyncio.TimeoutError:
        return None, None, "Image download timed out."
    except aiohttp.ClientError:
        return None, None, "Failed to download image. Check the URL."
    except Exception:
        return None, None, "Failed to download image. Check the URL."


async def fetch_image_bytes(
    url: str,
    timeout: int = 10,
    max_bytes: int = ROLE_ICON_MAX_BYTES,
) -> Tuple[Optional[bytes], Optional[str]]:
    payload, _content_type, error = await fetch_image_asset(url, timeout=timeout, max_bytes=max_bytes)
    return payload, error


def _make_image_data_uri(payload: bytes, content_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def fetch_image_data_uri(
    url: str,
    timeout: int = 10,
    max_bytes: int = PROFILE_BRANDING_MAX_BYTES,
) -> Tuple[Optional[str], Optional[str]]:
    payload, content_type, error = await fetch_image_asset(url, timeout=timeout, max_bytes=max_bytes)
    if error or payload is None or content_type is None:
        return None, error or "Failed to download image. Check the URL."
    return _make_image_data_uri(payload, content_type), None


async def prepare_modmail_relay_attachments(attachments) -> Tuple[list, Optional[str]]:
    import discord

    files = []
    skipped_extra = 0
    skipped_oversized = 0
    skipped_total_limit = 0
    total_bytes = 0

    for attachment in attachments:
        if len(files) >= MODMAIL_RELAY_MAX_FILES:
            skipped_extra += 1
            continue

        size = int(getattr(attachment, "size", 0) or 0)
        if size > MODMAIL_RELAY_MAX_FILE_BYTES:
            skipped_oversized += 1
            continue
        if total_bytes + size > MODMAIL_RELAY_MAX_TOTAL_BYTES:
            skipped_total_limit += 1
            continue

        files.append(await attachment.to_file())
        total_bytes += size

    notices = []
    if skipped_extra:
        notices.append(f"Skipped {skipped_extra} attachment(s) after the first {MODMAIL_RELAY_MAX_FILES}.")
    if skipped_oversized:
        notices.append("Skipped attachment(s) over 8 MiB.")
    if skipped_total_limit:
        notices.append("Skipped attachment(s) to stay under 20 MiB total.")
    if notices:
        return files, "Some attachments were not relayed. " + " ".join(notices)
    return files, None
