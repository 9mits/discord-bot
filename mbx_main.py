import os
import sys
from importlib.util import find_spec
from pathlib import Path


REQUIRED_PACKAGES = {
    "aiosqlite": "aiosqlite",
    "discord": "discord.py",
}


def _resolve_path(base_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def _has_token() -> bool:
    return bool(os.getenv("DISCORD_BOT_TOKEN") or os.getenv("MBX_BOT_TOKEN"))


def use_legacy_token_alias(alias: str):
    """Map an old per-server token name to the normal runtime token key."""
    if _has_token():
        return
    token = os.getenv(alias)
    if token:
        os.environ["DISCORD_BOT_TOKEN"] = token


def ensure_runtime_dependencies():
    missing = [package for module, package in REQUIRED_PACKAGES.items() if find_spec(module) is None]
    if not missing:
        return

    install_list = " ".join(missing)
    print(
        "[Startup]: Missing required Python package(s): "
        f"{install_list}\n"
        "[Startup]: Install dependencies with: "
        f"{sys.executable} -m pip install -r requirements.txt\n"
        "[Startup]: If your hosting panel has a package list, add: "
        "discord.py aiosqlite aiohttp",
        file=sys.stderr,
    )
    raise SystemExit(1)


def load_env_file():
    base_dir = Path(__file__).resolve().parent
    configured_env = os.getenv("MBX_ENV_FILE")
    if configured_env:
        candidates = [Path(configured_env).expanduser()]
    else:
        candidates = [
            base_dir / ".env",
            base_dir / "servers" / "server-1" / ".env",
        ]

    env_path = None
    for candidate in candidates:
        candidate = _resolve_path(base_dir, candidate)
        if candidate.exists():
            env_path = candidate
            break
    if env_path is None:
        checked = ", ".join(str(_resolve_path(base_dir, candidate)) for candidate in candidates)
        print(f"[Startup]: No .env file found. Checked: {checked}", file=sys.stderr)
        return

    print(f"[Startup]: Loading environment from {env_path}", file=sys.stderr)
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


if __name__ == "__main__":
    load_env_file()
    use_legacy_token_alias("PRIMARY_BOT_TOKEN")
    ensure_runtime_dependencies()
    from modules.mbx_bot import run

    run()
