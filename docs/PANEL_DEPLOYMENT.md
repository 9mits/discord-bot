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

For the multi-instance launchers, run one process with:

```bash
./scripts/run_guild_1.sh
```

and the other with:

```bash
./scripts/run_guild_2.sh
```
