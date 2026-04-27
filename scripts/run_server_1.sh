#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export MBX_ENV_FILE="servers/server-1/.env"

exec python3 mbx_main.py
