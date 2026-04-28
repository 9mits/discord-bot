import os

os.environ.setdefault("MBX_ENV_FILE", "servers/server-2/.env")

from mbx_main import ensure_runtime_dependencies, load_env_file


if __name__ == "__main__":
    load_env_file()
    ensure_runtime_dependencies()
    from modules.mbx_bot import run

    run()
