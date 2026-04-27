# Multi-Instance Runtime

The same checkout can run multiple bot tokens at the same time. Each process
should use a different token and operational data directory. Fleet status is
written to a separate shared SQLite file so `/status` can show totals across
all running instances.

## Example

Terminal 1:

```bash
MBX_INSTANCE_ID=guild-1 \
MBX_TOKEN_ENV_VAR=PRIMARY_BOT_TOKEN \
PRIMARY_BOT_TOKEN="..." \
MBX_DATA_DIR=database/instances/guild-1 \
MBX_FLEET_DB_FILE=database/shared/fleet_status.db \
python3 mbx_main.py
```

Terminal 2:

```bash
MBX_INSTANCE_ID=guild-2 \
MBX_TOKEN_ENV_VAR=SECONDARY_BOT_TOKEN \
SECONDARY_BOT_TOKEN="..." \
MBX_DATA_DIR=database/instances/guild-2 \
MBX_FLEET_DB_FILE=database/shared/fleet_status.db \
python3 mbx_main.py
```

Or use the launcher scripts:

```bash
./scripts/run_guild_1.sh
./scripts/run_guild_2.sh
```

## Environment Variables

- `MBX_TOKEN_ENV_VAR`: name of the environment variable that holds this
  process's Discord token. This is optional when you use one of the built-in
  names: `DISCORD_BOT_TOKEN`, `MBX_BOT_TOKEN`, `PRIMARY_BOT_TOKEN`, or
  `SECONDARY_BOT_TOKEN`.
- `MBX_DATA_DIR`: per-instance data directory. This controls legacy JSON paths
  and defaults the per-instance SQLite DB to `<MBX_DATA_DIR>/saori.db`.
- `MBX_DB_FILE`: optional explicit per-instance SQLite DB path.
- `MBX_INSTANCE_ID`: stable display/key for this bot process in the fleet DB.
  If unset, the bot user ID is used after login.
- `MBX_FLEET_DB_FILE`: shared aggregate status DB path. Point every instance at
  the same file if `/status` should show fleet totals.

Do not point two bot tokens at the same `MBX_DATA_DIR` or `MBX_DB_FILE` unless
you intentionally want them to share moderation/config state.

See `database/README.md` for the folder map.
