# Hosting Panel Deployment

Some Discord bot panels install only the package names configured in the
panel UI. If the panel logs only show `Checking package: discord.py`, it is
not installing this repository's full `requirements.txt`.

## Required Packages

Configure the panel's Python package list as one of these:

```text
-r requirements.txt
```

If the panel does not support `-r requirements.txt`, use:

```text
discord.py aiosqlite aiohttp
```

`aiosqlite` is required before startup because the bot stores guild data in
SQLite. Without it, the bot exits with `ModuleNotFoundError: No module named
'aiosqlite'`.

## Startup File

Set the bot file/startup target to:

```text
mbx_main.py
```

## Token Variables

For a normal single bot, set this panel environment variable:

```text
DISCORD_BOT_TOKEN=your_token_here
```

For the two-folder setup, use separate variables so each panel server is clear.

Guild 1:

```text
PRIMARY_BOT_TOKEN=your_first_token_here
MBX_INSTANCE_ID=guild-1
MBX_DATA_DIR=database/instances/guild-1
MBX_FLEET_DB_FILE=database/shared/fleet_status.db
```

Guild 2:

```text
SECONDARY_BOT_TOKEN=your_second_token_here
MBX_INSTANCE_ID=guild-2
MBX_DATA_DIR=database/instances/guild-2
MBX_FLEET_DB_FILE=database/shared/fleet_status.db
```

If your panel supports custom env vars reliably, you can also set
`MBX_TOKEN_ENV_VAR` to the token variable name for that instance. The bot now
accepts `PRIMARY_BOT_TOKEN` and `SECONDARY_BOT_TOKEN` directly too, so that
extra setting is optional.

For the multi-instance launchers, run one process with:

```bash
./scripts/run_guild_1.sh
```

and the other with:

```bash
./scripts/run_guild_2.sh
```
