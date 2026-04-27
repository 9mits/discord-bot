#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export MBX_INSTANCE_ID="guild-2"
export MBX_TOKEN_ENV_VAR="SECONDARY_BOT_TOKEN"
export MBX_DATA_DIR="database/instances/guild-2"
export MBX_FLEET_DB_FILE="database/shared/fleet_status.db"

exec python3 mbx_main.py
