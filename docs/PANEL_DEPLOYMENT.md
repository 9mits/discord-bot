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

For server 1, set the bot file/startup target to:

```text
run_server_1.py
```

For server 2, use:

```text
run_server_2.py
```

If your panel can only run `mbx_main.py`, it will auto-load
`servers/server-1/.env` when root `.env` is missing.

## Token Variables

For one bot process, use one `.env` file with one token:

```env
DISCORD_BOT_TOKEN=your_token_here
```

For two bots sharing the same source code, keep the source at the repo root and
put each bot's private runtime files under `servers/`.

Example layout:

```text
guilda/
  mbx_main.py
  modules/
  cogs/
  ui/
  servers/
    server-1/
      .env              # DISCORD_BOT_TOKEN for bot one
      database/         # old/current bot data belongs here
    server-2/
      .env              # DISCORD_BOT_TOKEN for bot two
      database/         # bot two's private data
```

`servers/server-1/.env` should contain:

```env
DISCORD_BOT_TOKEN=first_bot_token
MBX_DATA_DIR=servers/server-1/database
```

`servers/server-2/.env` should contain:

```env
DISCORD_BOT_TOKEN=second_bot_token
MBX_DATA_DIR=servers/server-2/database
```

The older names still work as a fallback when using the matching startup file:
`PRIMARY_BOT_TOKEN` for `run_server_1.py` and `SECONDARY_BOT_TOKEN` for
`run_server_2.py`. New installs should use `DISCORD_BOT_TOKEN`.

Then run:

```bash
./scripts/run_server_1.sh
./scripts/run_server_2.sh
```

Because each process points at a different `database/` folder, config, cases,
modmail, pings, roles, and setup state stay completely separate.

If this install already has data in the old root `database/` folder, move it to
server 1 once:

```bash
./scripts/move_root_database_to_server_1.sh
```

If the host panel does not expose environment variables, edit the `.env` file
in the server file manager instead.
