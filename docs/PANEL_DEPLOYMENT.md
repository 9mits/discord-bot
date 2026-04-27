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
      database/         # bot one's private data
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

Then run:

```bash
./scripts/run_server_1.sh
./scripts/run_server_2.sh
```

Because each process points at a different `database/` folder, config, cases,
modmail, pings, roles, and setup state stay completely separate.

If the host panel does not expose environment variables, edit the `.env` file
in the server file manager instead.
