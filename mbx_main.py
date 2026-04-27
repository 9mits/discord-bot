import os
import sys
from importlib.util import find_spec
from pathlib import Path


REQUIRED_PACKAGES = {
    "aiosqlite": "aiosqlite",
    "discord": "discord.py",
}


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
    env_path = Path(configured_env).expanduser() if configured_env else base_dir / ".env"
    if not env_path.is_absolute():
        env_path = base_dir / env_path
    if not env_path.exists():
        return
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
    ensure_runtime_dependencies()
    from modules.mbx_bot import run

    run()
