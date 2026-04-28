import os

os.environ.setdefault("MBX_ENV_FILE", "servers/server-1/.env")

from mbx_main import ensure_runtime_dependencies, load_env_file, use_legacy_token_alias


if __name__ == "__main__":
    load_env_file()
    use_legacy_token_alias("PRIMARY_BOT_TOKEN")
    ensure_runtime_dependencies()
    from modules.mbx_bot import run

    run()
