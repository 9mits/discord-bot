# Database Layout

Use `database/instances/` for separate bot runtimes. Each folder is one bot
token's private config/database/files.

```text
database/
  instances/
    guild-1/
      saori.db
      config.json
      modmail.json
      pings.json
      ...
    guild-2/
      saori.db
      config.json
      modmail.json
      pings.json
      ...
  shared/
    fleet_status.db
```

## What Is Shared

Only `database/shared/fleet_status.db` is shared when both bot processes use
the same `MBX_FLEET_DB_FILE`.

## What Is Not Shared

Everything under `database/instances/guild-1/` and
`database/instances/guild-2/` is private to that bot process:
config, moderation cases, modmail tickets, pings, custom roles, branding,
message cache, lockdowns, and setup state.

## Which Folder Is Which

- `guild-1` uses `PRIMARY_BOT_TOKEN`.
- `guild-2` uses `SECONDARY_BOT_TOKEN`.
- You can rename these folders later, but update the matching launcher script
  and `MBX_DATA_DIR` at the same time.

## Existing Root Files

The JSON/SQLite files directly inside `database/` are the old/default runtime
location. Keep them as backup or migrate them into one instance folder when you
are ready.
