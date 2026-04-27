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

Each cloned bot folder/server should have its own `.env` file with one token:

```env
DISCORD_BOT_TOKEN=your_token_here
```

Do not reuse the same `.env` between clones. To run a second bot, clone or copy
the whole repository into a second server/folder and put that bot's different
token in that clone's `.env`.

Example layout:

```text
bot-one/
  .env                  # DISCORD_BOT_TOKEN for bot one
  database/             # bot one's private data
  mbx_main.py

bot-two/
  .env                  # DISCORD_BOT_TOKEN for bot two
  database/             # bot two's private data
  mbx_main.py
```

Because each clone has its own `database/` folder, config, cases, modmail,
pings, roles, and setup state stay completely separate.

If the host panel does not expose environment variables, edit the `.env` file
in the server file manager instead.
