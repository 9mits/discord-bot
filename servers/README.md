# Server Runtime Folders

This folder is for per-bot runtime files. Shared source code stays at the repo
root.

```text
servers/
  server-1/
    .env
    database/
  server-2/
    .env
    database/
```

Create `.env` from the matching `.env.example` file in each server folder.
Each `.env` should use a different `DISCORD_BOT_TOKEN`.

Runtime database files in `database/` are ignored by git.
