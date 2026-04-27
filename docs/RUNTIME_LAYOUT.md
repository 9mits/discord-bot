# Runtime Layout

The repository can run two separate bot processes while sharing the same source
code. Runtime files live under `servers/`.

```text
guilda/
  cogs/                 # shared code
  modules/              # shared code
  ui/                   # shared code
  mbx_main.py           # shared entrypoint
  servers/
    server-1/
      .env              # first bot token and data path
      database/         # old/current bot data belongs here
    server-2/
      .env              # second bot token and data path
      database/         # second bot config, cases, modmail, roles, pings
```

Each server folder is private to that bot process. Do not put the same token in
both `.env` files.

The root `database/` folder is only the old fallback location. For the clean
two-server layout, move the old root database into `servers/server-1/database/`.
Run this once if the old files still exist:

```bash
./scripts/move_root_database_to_server_1.sh
```

## Server 1

Create `servers/server-1/.env`:

```env
DISCORD_BOT_TOKEN=first_bot_token
MBX_DATA_DIR=servers/server-1/database
```

Run:

```bash
./scripts/run_server_1.sh
```

## Server 2

Create `servers/server-2/.env`:

```env
DISCORD_BOT_TOKEN=second_bot_token
MBX_DATA_DIR=servers/server-2/database
```

Run:

```bash
./scripts/run_server_2.sh
```

The old root `database/` folder is still the default when no `MBX_DATA_DIR` is
set, but the recommended layout is to always run through the server scripts.
