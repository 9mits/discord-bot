"""
mbx_data.py — DataManager (per-guild SQLite), AntiAbuseSystem, path constants, I/O helpers.

Multi-server architecture:
- All guild data is stored in database/saori.db (aiosqlite / SQLite with WAL).
- DataManager exposes the same public attribute names as before (config, punishments,
  roles, modmail, pings, lockdown, mod_stats, message_cache, etc.) as Python properties
  that transparently route to the correct guild's in-memory shard based on
  _current_guild_id.  The interaction middleware in mgx_bot.py sets _current_guild_id
  before every slash command; background tasks set it explicitly.
- On first startup, existing JSON files are migrated into SQLite automatically and
  renamed to *.json.migrated (not deleted, for safety).
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import aiosqlite
import discord

from modules.mbx_constants import (
    DEFAULT_GUILD_ID,
    DEFAULT_MAX_UNREAD_PINGS,
    DEFAULT_MESSAGE_CACHE_LIMIT,
    DEFAULT_MESSAGE_CACHE_RETENTION_DAYS,
    DEFAULT_ROLE_ADMIN,
    DEFAULT_ANCHOR_ROLE_ID,
    DEFAULT_ROLE_COMMUNITY_MANAGER,
    DEFAULT_ROLE_MOD,
    DEFAULT_ROLE_OWNER,
    DEFAULT_RULES,
    DEFAULT_SPAM_ROLE_ID,
    DEFAULT_ARCHIVE_CAT_ID,
    TOKEN_ENV_VARS,
)
from modules.mbx_services import (
    DEFAULT_CANNED_REPLIES,
    DEFAULT_NATIVE_AUTOMOD_SETTINGS,
    DEFAULT_SCHEMA_VERSION,
    normalize_case_record,
    run_schema_migrations,
    ticket_needs_sla_alert,
)

logger = logging.getLogger("MGXBot")

# ----------------- PATHS -----------------
BASE_DIR = Path(__file__).resolve().parent.parent


def _configured_path(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


DB_DIR = _configured_path("MBX_DATA_DIR", BASE_DIR / "database")
ROLES_FILE = DB_DIR / "roles.json"
CONFIG_FILE = DB_DIR / "config.json"
PUNISHMENTS_FILE = DB_DIR / "punishments.json"
MOD_STATS_FILE = DB_DIR / "mod_stats.json"
MESSAGE_CACHE_FILE = DB_DIR / "message_cache.json"
PINGS_FILE = DB_DIR / "pings.json"
LOCKDOWN_FILE = DB_DIR / "lockdown.json"
MODMAIL_FILE = DB_DIR / "modmail.json"
SAORI_DB = _configured_path("MBX_DB_FILE", DB_DIR / "saori.db")
# -----------------------------------------


def read_json_file(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", path.name, exc)
    return default


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def resolve_bot_token() -> str:
    bootstrap_config = read_json_file(CONFIG_FILE, {})
    env_var_order: List[str] = []

    forced_env_var = os.getenv("MBX_TOKEN_ENV_VAR")
    if forced_env_var:
        env_var_order.append(forced_env_var.strip())

    configured_env_var = bootstrap_config.get("token_env_var")
    if isinstance(configured_env_var, str) and configured_env_var.strip():
        env_var_order.append(configured_env_var.strip())

    for env_var in TOKEN_ENV_VARS:
        if env_var not in env_var_order:
            env_var_order.append(env_var)

    for env_var in env_var_order:
        token = os.getenv(env_var)
        if token:
            return token.strip()

    raise RuntimeError(
        "Discord bot token is not configured. Set one of the supported environment variables "
        f"({', '.join(env_var_order)})."
    )


# ----------------- Storage helpers -----------------
class DataManager:
    def __init__(self, bot):
        self.bot = bot

        # Per-guild sharded in-memory storage (guild_id → data)
        self._configs: Dict[int, dict] = {}
        self._punishments: Dict[int, dict] = {}
        self._roles: Dict[int, dict] = {}
        self._modmail: Dict[int, dict] = {}
        self._mod_stats: Dict[int, dict] = {}
        self._message_caches: Dict[int, deque] = {}
        self._message_cache_indexes: Dict[int, Dict[int, dict]] = {}
        self._message_cache_retention: Dict[int, int] = {}
        self._pings: Dict[int, dict] = {}
        self._lockdowns: Dict[int, dict] = {}
        self._case_indexes: Dict[int, Dict] = {}
        self._modmail_threads_map: Dict[int, Dict[int, str]] = {}

        # Dirty tracking: guild_id → set of SQLite table names that need saving
        self._dirty: Dict[int, Set[str]] = {}

        # Set by interaction middleware before every slash command.
        # Background tasks set it explicitly per guild before calling helpers.
        self._current_guild_id: Optional[int] = None

        self._save_lock = asyncio.Lock()
        self._db: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------ #
    #  Guild context helper                                                #
    # ------------------------------------------------------------------ #

    def _get_cg(self) -> int:
        """Return the current guild context ID, falling back to first loaded guild."""
        gid = self._current_guild_id
        if gid is not None:
            return gid
        if self._configs:
            return next(iter(self._configs))
        return DEFAULT_GUILD_ID

    def _mark_dirty(self, guild_id: int, table: str) -> None:
        self._dirty.setdefault(guild_id, set()).add(table)

    # ------------------------------------------------------------------ #
    #  Backward-compatible property shims                                  #
    #  Legacy callers access these names directly; they route to the       #
    #  current guild's shard.                                              #
    # ------------------------------------------------------------------ #

    @property
    def config(self) -> dict:
        return self._configs.setdefault(self._get_cg(), {})

    @config.setter
    def config(self, v: dict) -> None:
        gid = self._get_cg()
        self._configs[gid] = v
        self._mark_dirty(gid, "guild_configs")

    @property
    def punishments(self) -> dict:
        return self._punishments.setdefault(self._get_cg(), {})

    @punishments.setter
    def punishments(self, v: dict) -> None:
        gid = self._get_cg()
        self._punishments[gid] = v
        self._mark_dirty(gid, "guild_punishments")

    @property
    def roles(self) -> dict:
        return self._roles.setdefault(self._get_cg(), {})

    @roles.setter
    def roles(self, v: dict) -> None:
        gid = self._get_cg()
        self._roles[gid] = v
        self._mark_dirty(gid, "guild_roles")

    @property
    def modmail(self) -> dict:
        return self._modmail.setdefault(self._get_cg(), {})

    @modmail.setter
    def modmail(self, v: dict) -> None:
        gid = self._get_cg()
        self._modmail[gid] = v
        self._mark_dirty(gid, "guild_modmail")

    @property
    def mod_stats(self) -> dict:
        return self._mod_stats.setdefault(self._get_cg(), {})

    @mod_stats.setter
    def mod_stats(self, v: dict) -> None:
        gid = self._get_cg()
        self._mod_stats[gid] = v
        self._mark_dirty(gid, "guild_mod_stats")

    @property
    def pings(self) -> dict:
        return self._pings.setdefault(self._get_cg(), {})

    @pings.setter
    def pings(self, v: dict) -> None:
        gid = self._get_cg()
        self._pings[gid] = v
        self._mark_dirty(gid, "guild_pings")

    @property
    def lockdown(self) -> dict:
        return self._lockdowns.setdefault(self._get_cg(), {})

    @lockdown.setter
    def lockdown(self, v: dict) -> None:
        gid = self._get_cg()
        self._lockdowns[gid] = v
        self._mark_dirty(gid, "guild_lockdown")

    @property
    def message_cache(self) -> deque:
        gid = self._get_cg()
        if gid not in self._message_caches:
            self._message_caches[gid] = deque(maxlen=DEFAULT_MESSAGE_CACHE_LIMIT)
        return self._message_caches[gid]

    @message_cache.setter
    def message_cache(self, v: deque) -> None:
        gid = self._get_cg()
        self._message_caches[gid] = v
        self._mark_dirty(gid, "guild_message_cache")

    @property
    def message_cache_index(self) -> Dict[int, dict]:
        return self._message_cache_indexes.setdefault(self._get_cg(), {})

    @message_cache_index.setter
    def message_cache_index(self, v: dict) -> None:
        self._message_cache_indexes[self._get_cg()] = v

    @property
    def message_cache_retention_days(self) -> int:
        return self._message_cache_retention.get(self._get_cg(), DEFAULT_MESSAGE_CACHE_RETENTION_DAYS)

    @message_cache_retention_days.setter
    def message_cache_retention_days(self, v: int) -> None:
        self._message_cache_retention[self._get_cg()] = v

    @property
    def case_index(self) -> Dict[int, Tuple[str, dict]]:
        return self._case_indexes.setdefault(self._get_cg(), {})

    @case_index.setter
    def case_index(self, v: dict) -> None:
        self._case_indexes[self._get_cg()] = v

    @property
    def modmail_threads(self) -> Dict[int, str]:
        return self._modmail_threads_map.setdefault(self._get_cg(), {})

    @modmail_threads.setter
    def modmail_threads(self, v: dict) -> None:
        self._modmail_threads_map[self._get_cg()] = v

    # ------------------------------------------------------------------ #
    #  Low-level helpers (unchanged logic, now route through properties)  #
    # ------------------------------------------------------------------ #

    def _normalize_positive_int(self, value: Any, default: int, *, minimum: int = 1, maximum: Optional[int] = None) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = default
        if maximum is not None:
            normalized = min(normalized, maximum)
        return max(minimum, normalized)

    def _configure_cache_limits(self):
        cache_limit = self._normalize_positive_int(
            self.config.get("message_cache_limit", DEFAULT_MESSAGE_CACHE_LIMIT),
            DEFAULT_MESSAGE_CACHE_LIMIT,
            minimum=100,
            maximum=50000,
        )
        if self.message_cache.maxlen != cache_limit:
            self.message_cache = deque(list(self.message_cache)[-cache_limit:], maxlen=cache_limit)
        self.message_cache_retention_days = self._normalize_positive_int(
            self.config.get("message_cache_retention_days", DEFAULT_MESSAGE_CACHE_RETENTION_DAYS),
            DEFAULT_MESSAGE_CACHE_RETENTION_DAYS,
            minimum=1,
            maximum=90,
        )
        self._rebuild_message_cache_index()

    def _parse_optional_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalize_message_cache_record(self, record: Any) -> Optional[dict]:
        if not isinstance(record, dict):
            return None
        normalized = dict(record)
        message_id = self._parse_optional_int(normalized.get("id"))
        if message_id is None:
            return None
        normalized["id"] = message_id
        author_id = self._parse_optional_int(normalized.get("author_id"))
        if author_id is not None:
            normalized["author_id"] = author_id
        channel_id = self._parse_optional_int(normalized.get("channel_id"))
        if channel_id is not None:
            normalized["channel_id"] = channel_id
        created_at = normalized.get("created_at")
        if not isinstance(created_at, datetime):
            normalized["created_at"] = parse_iso_datetime(created_at) or discord.utils.utcnow()
        attachments = normalized.get("attachments", [])
        normalized["attachments"] = attachments if isinstance(attachments, list) else []
        stickers = normalized.get("stickers", [])
        normalized["stickers"] = stickers if isinstance(stickers, list) else []
        normalized["deleted"] = bool(normalized.get("deleted", False))
        normalized["edited"] = bool(normalized.get("edited", False))
        return normalized

    def _rebuild_message_cache_index(self):
        self.message_cache_index = {}
        for record in self.message_cache:
            record_id = self._parse_optional_int(record.get("id"))
            if record_id is not None:
                record["id"] = record_id
                self.message_cache_index[record_id] = record

    def _rebuild_modmail_index(self):
        self.modmail_threads = {}
        for user_id, ticket in self.modmail.items():
            thread_id = self._parse_optional_int(ticket.get("thread_id"))
            if thread_id is not None:
                self.modmail_threads[thread_id] = user_id

    def _rebuild_case_index(self):
        self.case_index = {}
        for user_id, records in self.punishments.items():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                self._index_case_record(user_id, record)

    def _index_case_record(self, user_id: str, record: dict):
        case_id = record.get("case_id")
        if isinstance(case_id, int) and case_id > 0:
            self.case_index[case_id] = (user_id, record)

    def _prune_message_cache(self):
        cutoff = discord.utils.utcnow() - timedelta(days=self.message_cache_retention_days)
        pruned = False
        while self.message_cache:
            oldest = self.message_cache[0]
            created_at = oldest.get("created_at")
            if not isinstance(created_at, datetime):
                created_at = parse_iso_datetime(created_at) or discord.utils.utcnow()
                oldest["created_at"] = created_at
            if created_at >= cutoff:
                break
            removed = self.message_cache.popleft()
            self.message_cache_index.pop(removed.get("id"), None)
            pruned = True
        if pruned:
            self._mark_dirty(self._get_cg(), "guild_message_cache")

    def _append_message_record(self, record: dict, *, mark_dirty: bool = True):
        normalized = self._normalize_message_cache_record(record)
        if normalized is None:
            if mark_dirty:
                self._mark_dirty(self._get_cg(), "guild_message_cache")
            return
        if len(self.message_cache) >= self.message_cache.maxlen:
            removed = self.message_cache.popleft()
            self.message_cache_index.pop(removed.get("id"), None)
        self.message_cache.append(normalized)
        record_id = normalized["id"]
        if record_id is not None:
            self.message_cache_index[record_id] = normalized
        self._prune_message_cache()
        if mark_dirty:
            self._mark_dirty(self._get_cg(), "guild_message_cache")

    def _serialize_message_cache(self) -> List[dict]:
        serializable = []
        for msg in list(self.message_cache):
            msg_copy = msg.copy()
            if isinstance(msg_copy.get("created_at"), datetime):
                msg_copy["created_at"] = msg_copy["created_at"].isoformat()
            serializable.append(msg_copy)
        return serializable

    def _ensure_dict(self, value: Any, path: Path) -> dict:
        if isinstance(value, dict):
            return value
        logger.warning("Expected %s to contain a JSON object. Resetting to defaults.", path.name)
        return {}

    def _ensure_list(self, value: Any, path: Path) -> list:
        if isinstance(value, list):
            return value
        logger.warning("Expected %s to contain a JSON array. Resetting to defaults.", path.name)
        return []

    def _normalize_punishments(self):
        if not isinstance(self.punishments, dict):
            self.punishments = {}
            self._mark_dirty(self._get_cg(), "guild_punishments")
            return

        highest_case_id = self._normalize_positive_int(self.config.get("case_counter", 0), 0, minimum=0)
        changed = False
        now = discord.utils.utcnow()

        for uid, records in list(self.punishments.items()):
            if not isinstance(records, list):
                self.punishments[uid] = []
                changed = True
                continue

            normalized_records = []
            for record in records:
                if not isinstance(record, dict):
                    changed = True
                    continue

                case_id = record.get("case_id")
                if isinstance(case_id, int) and case_id > 0:
                    highest_case_id = max(highest_case_id, case_id)
                else:
                    highest_case_id += 1
                    record["case_id"] = highest_case_id
                    changed = True

                record_type = record.get("type")
                if record_type == "ban":
                    duration = record.get("duration_minutes", 0)
                    if duration == -1:
                        active = True
                    elif duration > 0:
                        issued_at = parse_iso_datetime(record.get("timestamp"))
                        active = bool(issued_at and issued_at + timedelta(minutes=duration) > now)
                    else:
                        active = False
                    if record.get("active") != active:
                        record["active"] = active
                        changed = True

                if normalize_case_record(record):
                    changed = True

                normalized_records.append(record)

            self.punishments[uid] = normalized_records

        if self.config.get("case_counter") != highest_case_id:
            self.config["case_counter"] = highest_case_id
            self._mark_dirty(self._get_cg(), "guild_configs")

        self._rebuild_case_index()
        if changed:
            self._mark_dirty(self._get_cg(), "guild_punishments")

    # ------------------------------------------------------------------ #
    #  Defaults                                                            #
    # ------------------------------------------------------------------ #

    def _make_defaults(self) -> dict:
        return {
            "min_boosts_for_role": 0, "whitelist": {}, "punishment_rules": DEFAULT_RULES,
            "mod_roles": [], "stats": {"total_issued": 0, "cases_cleared": 0},
            "locked_channels": {}, "archived_channels": {},
            "cr_whitelist_users": {}, "cr_whitelist_roles": {}, "cr_blacklist_users": [], "cr_blacklist_roles": [],
            "security": {"max_actions_per_min": 10},
            "smart_automod": {
                "duplicate_window_seconds": 20,
                "duplicate_threshold": 4,
                "max_caps_ratio": 0.75,
                "caps_min_length": 12,
                "blocked_patterns": [],
                "exempt_channels": [],
                "exempt_roles": [],
            },
            "native_automod": DEFAULT_NATIVE_AUTOMOD_SETTINGS,
            "immunity_list": [], "debug": {},
            "token_env_var": "DISCORD_BOT_TOKEN",
            "case_counter": 0,
            "schema_version": DEFAULT_SCHEMA_VERSION,
            "message_cache_limit": DEFAULT_MESSAGE_CACHE_LIMIT,
            "message_cache_retention_days": DEFAULT_MESSAGE_CACHE_RETENTION_DAYS,
            "max_unread_pings_per_user": DEFAULT_MAX_UNREAD_PINGS,
            "feature_flags": {},
            "modmail_canned_replies": DEFAULT_CANNED_REPLIES,
            "modmail_sla_minutes": 60,
            "dm_modmail_panel_cooldown_minutes": 30,
            "escalation_matrix": [],
            "guild_id": DEFAULT_GUILD_ID,
            "general_log_channel_id": 0,
            "punishment_log_channel_id": 0,
            "automod_log_channel_id": 0,
            "automod_report_channel_id": 0,
            "role_owner": DEFAULT_ROLE_OWNER,
            "role_admin": DEFAULT_ROLE_ADMIN,
            "role_mod": DEFAULT_ROLE_MOD,
            "role_community_manager": DEFAULT_ROLE_COMMUNITY_MANAGER,
            "role_anchor": DEFAULT_ANCHOR_ROLE_ID,
            "category_archive": DEFAULT_ARCHIVE_CAT_ID,
            "role_mention_spam_target": DEFAULT_SPAM_ROLE_ID,
        }

    # ------------------------------------------------------------------ #
    #  SQLite init                                                         #
    # ------------------------------------------------------------------ #

    async def _init_db(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        SAORI_DB.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(SAORI_DB)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id   INTEGER PRIMARY KEY,
                data       TEXT    NOT NULL DEFAULT '{}',
                branding   TEXT    NOT NULL DEFAULT '{}',
                active     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guild_punishments (
                guild_id INTEGER NOT NULL,
                user_id  TEXT    NOT NULL,
                data     TEXT    NOT NULL DEFAULT '[]',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS guild_roles (
                guild_id INTEGER NOT NULL,
                user_id  TEXT    NOT NULL,
                data     TEXT    NOT NULL DEFAULT '{}',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS guild_modmail (
                guild_id INTEGER NOT NULL,
                user_id  TEXT    NOT NULL,
                data     TEXT    NOT NULL DEFAULT '{}',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS guild_mod_stats (
                guild_id INTEGER PRIMARY KEY,
                data     TEXT    NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS guild_message_cache (
                guild_id INTEGER PRIMARY KEY,
                data     TEXT    NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS guild_pings (
                guild_id INTEGER NOT NULL,
                user_id  TEXT    NOT NULL,
                data     TEXT    NOT NULL DEFAULT '[]',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS guild_lockdown (
                guild_id INTEGER PRIMARY KEY,
                data     TEXT    NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS bot_blacklist (
                guild_id       INTEGER PRIMARY KEY,
                blacklisted_at TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bot_whitelist (
                guild_id       INTEGER PRIMARY KEY,
                whitelisted_at TEXT    NOT NULL
            );
        """)
        await self._db.commit()

    # ------------------------------------------------------------------ #
    #  Load / provision / archive                                          #
    # ------------------------------------------------------------------ #

    async def load_all(self) -> None:
        await self._init_db()
        await self._migrate_from_json_if_needed()
        self._configs.clear()
        self._punishments.clear()
        self._roles.clear()
        self._modmail.clear()
        self._mod_stats.clear()
        self._message_caches.clear()
        self._message_cache_indexes.clear()
        self._message_cache_retention.clear()
        self._pings.clear()
        self._lockdowns.clear()
        self._case_indexes.clear()
        self._modmail_threads_map.clear()
        self._dirty.clear()

        for guild_id in await self.get_all_active_guild_ids():
            await self.load_guild(guild_id)

    async def load_guild(self, guild_id: int) -> None:
        """Load all data for one guild from SQLite into memory."""
        prev = self._current_guild_id
        self._current_guild_id = guild_id
        try:
            async with self._db.execute(
                "SELECT data, branding FROM guild_configs WHERE guild_id=? AND active=1",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()

            if row is None:
                await self.provision_guild(guild_id)
                return

            config = json.loads(row["data"] or "{}")
            config["_branding"] = json.loads(row["branding"] or "{}")

            had_general_log = "general_log_channel_id" in config
            legacy_log = config.get("log_channel_id")

            defaults = self._make_defaults()
            for k, v in defaults.items():
                if k not in config:
                    config[k] = copy.deepcopy(v)
                    self._mark_dirty(guild_id, "guild_configs")

            if not had_general_log and legacy_log:
                config["general_log_channel_id"] = legacy_log
                self._mark_dirty(guild_id, "guild_configs")

            self._configs[guild_id] = config
            self._configure_cache_limits()

            # punishments
            punishments: dict = {}
            async with self._db.execute(
                "SELECT user_id, data FROM guild_punishments WHERE guild_id=?", (guild_id,)
            ) as cur:
                async for r in cur:
                    punishments[r["user_id"]] = json.loads(r["data"] or "[]")
            self._punishments[guild_id] = punishments
            self._normalize_punishments()

            # roles
            roles: dict = {}
            async with self._db.execute(
                "SELECT user_id, data FROM guild_roles WHERE guild_id=?", (guild_id,)
            ) as cur:
                async for r in cur:
                    roles[r["user_id"]] = json.loads(r["data"] or "{}")
            self._roles[guild_id] = roles

            # modmail
            modmail: dict = {}
            async with self._db.execute(
                "SELECT user_id, data FROM guild_modmail WHERE guild_id=?", (guild_id,)
            ) as cur:
                async for r in cur:
                    modmail[r["user_id"]] = json.loads(r["data"] or "{}")
            self._modmail[guild_id] = modmail

            # mod_stats
            async with self._db.execute(
                "SELECT data FROM guild_mod_stats WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
            self._mod_stats[guild_id] = json.loads(row["data"] if row else "{}")

            # pings
            pings: dict = {}
            async with self._db.execute(
                "SELECT user_id, data FROM guild_pings WHERE guild_id=?", (guild_id,)
            ) as cur:
                async for r in cur:
                    pings[r["user_id"]] = json.loads(r["data"] or "[]")
            self._pings[guild_id] = pings

            # lockdown
            async with self._db.execute(
                "SELECT data FROM guild_lockdown WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
            self._lockdowns[guild_id] = json.loads(row["data"] if row else "{}")

            # message cache
            async with self._db.execute(
                "SELECT data FROM guild_message_cache WHERE guild_id=?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
            raw_msgs = json.loads(row["data"] if row else "[]")
            if guild_id not in self._message_caches:
                self._message_caches[guild_id] = deque(maxlen=DEFAULT_MESSAGE_CACHE_LIMIT)
            self._message_caches[guild_id].clear()
            self._message_cache_indexes[guild_id] = {}
            for msg in raw_msgs:
                self._append_message_record(msg, mark_dirty=False)
            self._prune_message_cache()

            # schema migrations
            migrated, migration_notes = run_schema_migrations(self.config, self.punishments, self.modmail)
            if migrated:
                self._mark_dirty(guild_id, "guild_configs")
                self._mark_dirty(guild_id, "guild_punishments")
                self._mark_dirty(guild_id, "guild_modmail")
                for note in migration_notes:
                    logger.info("Migration guild %s: %s", guild_id, note)

            self._rebuild_case_index()
            self._rebuild_modmail_index()

        finally:
            self._current_guild_id = prev

    async def ensure_guild_loaded(self, guild_id: int) -> None:
        """Load guild data if not already in memory (called by interaction middleware)."""
        if guild_id not in self._configs:
            await self.load_guild(guild_id)

    async def provision_guild(self, guild_id: int) -> None:
        """Insert a default config row for a new guild and initialise all in-memory shards."""
        now = discord.utils.utcnow().isoformat()
        config = self._make_defaults()
        config["guild_id"] = guild_id
        data_json = json.dumps(config, ensure_ascii=False)
        await self._db.execute(
            """INSERT OR IGNORE INTO guild_configs
               (guild_id, data, branding, active, created_at, updated_at)
               VALUES (?, ?, '{}', 1, ?, ?)""",
            (guild_id, data_json, now, now),
        )
        await self._db.commit()

        self._configs[guild_id] = config
        self._punishments[guild_id] = {}
        self._roles[guild_id] = {}
        self._modmail[guild_id] = {}
        self._mod_stats[guild_id] = {}
        self._pings[guild_id] = {}
        self._lockdowns[guild_id] = {}
        self._message_caches[guild_id] = deque(maxlen=DEFAULT_MESSAGE_CACHE_LIMIT)
        self._message_cache_indexes[guild_id] = {}
        self._case_indexes[guild_id] = {}
        self._modmail_threads_map[guild_id] = {}
        logger.info("Provisioned new guild: %s", guild_id)

    async def archive_guild(self, guild_id: int) -> None:
        """Mark a guild as inactive and evict its data from memory."""
        if self._db:
            await self._db.execute(
                "UPDATE guild_configs SET active=0, updated_at=? WHERE guild_id=?",
                (discord.utils.utcnow().isoformat(), guild_id),
            )
            await self._db.commit()
        for store in (
            self._configs, self._punishments, self._roles, self._modmail,
            self._mod_stats, self._pings, self._lockdowns, self._message_caches,
            self._message_cache_indexes, self._case_indexes, self._modmail_threads_map,
            self._message_cache_retention, self._dirty,
        ):
            store.pop(guild_id, None)
        logger.info("Archived guild: %s", guild_id)

    # ------------------------------------------------------------------ #
    #  SQLite queries                                                      #
    # ------------------------------------------------------------------ #

    async def get_all_active_guild_ids(self) -> List[int]:
        async with self._db.execute(
            "SELECT guild_id FROM guild_configs WHERE active=1"
        ) as cur:
            return [row[0] async for row in cur]

    async def get_blacklisted_guilds(self) -> Set[int]:
        async with self._db.execute("SELECT guild_id FROM bot_blacklist") as cur:
            return {row[0] async for row in cur}

    async def blacklist_guild(self, guild_id: int) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO bot_blacklist (guild_id, blacklisted_at) VALUES (?, ?)",
            (guild_id, discord.utils.utcnow().isoformat()),
        )
        await self._db.commit()

    async def unblacklist_guild(self, guild_id: int) -> None:
        await self._db.execute("DELETE FROM bot_blacklist WHERE guild_id=?", (guild_id,))
        await self._db.commit()

    async def get_whitelisted_guilds(self) -> Set[int]:
        async with self._db.execute("SELECT guild_id FROM bot_whitelist") as cur:
            return {row[0] async for row in cur}

    async def whitelist_guild(self, guild_id: int) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO bot_whitelist (guild_id, whitelisted_at) VALUES (?, ?)",
            (guild_id, discord.utils.utcnow().isoformat()),
        )
        await self._db.commit()

    async def unwhitelist_guild(self, guild_id: int) -> None:
        await self._db.execute("DELETE FROM bot_whitelist WHERE guild_id=?", (guild_id,))
        await self._db.commit()

    # ------------------------------------------------------------------ #
    #  Save                                                                #
    # ------------------------------------------------------------------ #

    async def save_guild(self, guild_id: int, tables: Optional[Set[str]] = None) -> None:
        """Persist dirty (or specified) tables for one guild to SQLite."""
        async with self._save_lock:
            dirty = self._dirty.get(guild_id, set())
            to_save = tables if tables is not None else dirty
            now = discord.utils.utcnow().isoformat()

            if "guild_configs" in to_save and guild_id in self._configs:
                cfg = dict(self._configs[guild_id])
                branding = cfg.pop("_branding", {})
                await self._db.execute(
                    """INSERT INTO guild_configs (guild_id, data, branding, active, created_at, updated_at)
                       VALUES (?, ?, ?, 1, ?, ?)
                       ON CONFLICT(guild_id) DO UPDATE SET
                           data=excluded.data, branding=excluded.branding,
                           updated_at=excluded.updated_at""",
                    (guild_id, json.dumps(cfg, ensure_ascii=False),
                     json.dumps(branding, ensure_ascii=False), now, now),
                )

            if "guild_punishments" in to_save and guild_id in self._punishments:
                await self._db.execute(
                    "DELETE FROM guild_punishments WHERE guild_id=?", (guild_id,)
                )
                for uid, records in self._punishments[guild_id].items():
                    await self._db.execute(
                        "INSERT INTO guild_punishments (guild_id, user_id, data) VALUES (?, ?, ?)",
                        (guild_id, uid, json.dumps(records, ensure_ascii=False)),
                    )

            if "guild_roles" in to_save and guild_id in self._roles:
                await self._db.execute(
                    "DELETE FROM guild_roles WHERE guild_id=?", (guild_id,)
                )
                for uid, record in self._roles[guild_id].items():
                    await self._db.execute(
                        "INSERT INTO guild_roles (guild_id, user_id, data) VALUES (?, ?, ?)",
                        (guild_id, uid, json.dumps(record, ensure_ascii=False)),
                    )

            if "guild_modmail" in to_save and guild_id in self._modmail:
                await self._db.execute(
                    "DELETE FROM guild_modmail WHERE guild_id=?", (guild_id,)
                )
                for uid, ticket in self._modmail[guild_id].items():
                    await self._db.execute(
                        "INSERT INTO guild_modmail (guild_id, user_id, data) VALUES (?, ?, ?)",
                        (guild_id, uid, json.dumps(ticket, ensure_ascii=False)),
                    )

            if "guild_mod_stats" in to_save and guild_id in self._mod_stats:
                await self._db.execute(
                    """INSERT INTO guild_mod_stats (guild_id, data) VALUES (?, ?)
                       ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data""",
                    (guild_id, json.dumps(self._mod_stats[guild_id], ensure_ascii=False)),
                )

            if "guild_message_cache" in to_save and guild_id in self._message_caches:
                prev = self._current_guild_id
                self._current_guild_id = guild_id
                serialized = self._serialize_message_cache()
                self._current_guild_id = prev
                await self._db.execute(
                    """INSERT INTO guild_message_cache (guild_id, data) VALUES (?, ?)
                       ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data""",
                    (guild_id, json.dumps(serialized, ensure_ascii=False)),
                )

            if "guild_pings" in to_save and guild_id in self._pings:
                await self._db.execute(
                    "DELETE FROM guild_pings WHERE guild_id=?", (guild_id,)
                )
                for uid, pings_list in self._pings[guild_id].items():
                    await self._db.execute(
                        "INSERT INTO guild_pings (guild_id, user_id, data) VALUES (?, ?, ?)",
                        (guild_id, uid, json.dumps(pings_list, ensure_ascii=False)),
                    )

            if "guild_lockdown" in to_save and guild_id in self._lockdowns:
                await self._db.execute(
                    """INSERT INTO guild_lockdown (guild_id, data) VALUES (?, ?)
                       ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data""",
                    (guild_id, json.dumps(self._lockdowns[guild_id], ensure_ascii=False)),
                )

            await self._db.commit()

            # Clear only the tables we just saved
            remaining = dirty - to_save
            if remaining:
                self._dirty[guild_id] = remaining
            else:
                self._dirty.pop(guild_id, None)

    async def save_all(self, force: bool = False) -> None:
        for guild_id in list(self._configs.keys()):
            dirty = self._dirty.get(guild_id, set())
            if force:
                tables = {
                    "guild_configs", "guild_punishments", "guild_roles", "guild_modmail",
                    "guild_mod_stats", "guild_message_cache", "guild_pings", "guild_lockdown",
                }
                await self.save_guild(guild_id, tables)
            elif dirty:
                await self.save_guild(guild_id, dirty)

    # ------------------------------------------------------------------ #
    #  Convenience save methods (same signatures as before)               #
    # ------------------------------------------------------------------ #

    def mark_config_dirty(self):
        self._mark_dirty(self._get_cg(), "guild_configs")

    async def save_config(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_configs")
        await self.save_guild(gid, {"guild_configs"})

    async def save_roles(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_roles")
        await self.save_guild(gid, {"guild_roles"})

    async def save_punishments(self):
        gid = self._get_cg()
        self._rebuild_case_index()
        self._mark_dirty(gid, "guild_punishments")
        await self.save_guild(gid, {"guild_punishments"})

    async def save_mod_stats(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_mod_stats")
        await self.save_guild(gid, {"guild_mod_stats"})

    async def save_lockdown(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_lockdown")
        await self.save_guild(gid, {"guild_lockdown"})

    async def save_modmail(self):
        gid = self._get_cg()
        self._rebuild_modmail_index()
        self._mark_dirty(gid, "guild_modmail")
        await self.save_guild(gid, {"guild_modmail"})

    async def save_message_cache(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_message_cache")
        await self.save_guild(gid, {"guild_message_cache"})

    async def save_pings(self):
        gid = self._get_cg()
        self._mark_dirty(gid, "guild_pings")
        await self.save_guild(gid, {"guild_pings"})

    # ------------------------------------------------------------------ #
    #  Punishment / case helpers (unchanged signatures)                   #
    # ------------------------------------------------------------------ #

    async def add_punishment(self, uid, record, *, persist: bool = True):
        if uid not in self.punishments:
            self.punishments[uid] = []
        prepared = self.prepare_punishment_record(record)
        self.punishments[uid].append(prepared)
        self._index_case_record(uid, prepared)
        self._mark_dirty(self._get_cg(), "guild_punishments")
        if persist:
            await self.save_guild(self._get_cg(), {"guild_punishments"})
        return prepared

    def cache_message(self, record: dict):
        self._append_message_record(record)

    def get_cached_message(self, message_id: int) -> Optional[dict]:
        return self.message_cache_index.get(message_id)

    def mark_message_deleted(self, message_id: int) -> bool:
        record = self.get_cached_message(message_id)
        if not record:
            return False
        record["deleted"] = True
        self._mark_dirty(self._get_cg(), "guild_message_cache")
        return True

    def update_cached_message(self, message_id: int, **changes) -> bool:
        record = self.get_cached_message(message_id)
        if not record:
            return False
        record.update(changes)
        self._mark_dirty(self._get_cg(), "guild_message_cache")
        return True

    def get_modmail_user_id(self, thread_id: int) -> Optional[str]:
        return self.modmail_threads.get(thread_id)

    def get_case(self, case_id: int) -> Tuple[Optional[str], Optional[dict]]:
        normalized_case_id = self._parse_optional_int(case_id)
        if normalized_case_id is None:
            return None, None
        entry = self.case_index.get(normalized_case_id)
        if entry is not None:
            user_id, record = entry
            if record in self.punishments.get(user_id, []):
                return entry
            self.case_index.pop(normalized_case_id, None)
        self._rebuild_case_index()
        return self.case_index.get(normalized_case_id, (None, None))

    def get_user_cases(self, user_id: int) -> List[dict]:
        records = self.punishments.get(str(user_id), [])
        return sorted(
            [record for record in records if isinstance(record, dict)],
            key=lambda record: record.get("case_id", 0),
            reverse=True,
        )

    def allocate_case_id(self) -> int:
        current = self._normalize_positive_int(self.config.get("case_counter", 0), 0, minimum=0)
        next_case_id = current + 1
        self.config["case_counter"] = next_case_id
        self._mark_dirty(self._get_cg(), "guild_configs")
        return next_case_id

    def prepare_punishment_record(self, record: dict) -> dict:
        from modules.mbx_utils import now_iso
        prepared = dict(record)
        case_id = prepared.get("case_id")
        if not isinstance(case_id, int) or case_id <= 0:
            prepared["case_id"] = self.allocate_case_id()
        if "timestamp" not in prepared:
            prepared["timestamp"] = now_iso()
        if "active" not in prepared:
            prepared["active"] = prepared.get("type") == "ban"
        normalize_case_record(prepared)
        return prepared

    # ------------------------------------------------------------------ #
    #  JSON → SQLite one-time migration                                   #
    # ------------------------------------------------------------------ #

    async def _migrate_from_json_if_needed(self) -> None:
        async with self._db.execute("SELECT COUNT(*) FROM guild_configs") as cur:
            row = await cur.fetchone()
            if row[0] > 0:
                return  # already migrated or fresh install

        if not CONFIG_FILE.exists():
            return  # nothing to migrate

        logger.info("Migrating existing JSON data to SQLite (one-time migration)…")

        raw_config = read_json_file(CONFIG_FILE, {})
        raw_guild_id = raw_config.get("guild_id")
        if not raw_guild_id:
            logger.info("Skipping legacy JSON migration: config.json has no guild_id.")
            return
        guild_id = int(raw_guild_id)

        prev = self._current_guild_id
        self._current_guild_id = guild_id

        await self.provision_guild(guild_id)

        # Overwrite shards with JSON data
        self._configs[guild_id] = raw_config
        self._configs[guild_id].setdefault("_branding", {})
        self._punishments[guild_id] = self._ensure_dict(read_json_file(PUNISHMENTS_FILE, {}), PUNISHMENTS_FILE)
        self._roles[guild_id] = self._ensure_dict(read_json_file(ROLES_FILE, {}), ROLES_FILE)
        self._modmail[guild_id] = self._ensure_dict(read_json_file(MODMAIL_FILE, {}), MODMAIL_FILE)
        self._mod_stats[guild_id] = self._ensure_dict(read_json_file(MOD_STATS_FILE, {}), MOD_STATS_FILE)
        self._pings[guild_id] = self._ensure_dict(read_json_file(PINGS_FILE, {}), PINGS_FILE)
        self._lockdowns[guild_id] = self._ensure_dict(read_json_file(LOCKDOWN_FILE, {}), LOCKDOWN_FILE)

        raw_cache = self._ensure_list(read_json_file(MESSAGE_CACHE_FILE, []), MESSAGE_CACHE_FILE)
        if guild_id not in self._message_caches:
            self._message_caches[guild_id] = deque(maxlen=DEFAULT_MESSAGE_CACHE_LIMIT)
        for msg in raw_cache:
            self._append_message_record(msg, mark_dirty=False)

        tables = {
            "guild_configs", "guild_punishments", "guild_roles", "guild_modmail",
            "guild_mod_stats", "guild_message_cache", "guild_pings", "guild_lockdown",
        }
        for t in tables:
            self._mark_dirty(guild_id, t)
        await self.save_guild(guild_id, tables)

        self._current_guild_id = prev

        # Rename JSON files to *.json.migrated (keep as backup)
        for f in (CONFIG_FILE, PUNISHMENTS_FILE, ROLES_FILE, MODMAIL_FILE,
                  MOD_STATS_FILE, PINGS_FILE, LOCKDOWN_FILE, MESSAGE_CACHE_FILE):
            if f.exists():
                try:
                    f.rename(f.with_suffix(".json.migrated"))
                except Exception as exc:
                    logger.warning("Could not rename %s: %s", f.name, exc)

        logger.info("Migration complete. JSON files renamed to *.json.migrated. Guild: %s", guild_id)

    # ------------------------------------------------------------------ #
    #  Close                                                               #
    # ------------------------------------------------------------------ #

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None


# ----------------- Security -----------------
class AntiAbuseSystem:
    def __init__(self):
        self._tracker = defaultdict(lambda: deque(maxlen=15))
        self.cooldowns: Dict[str, float] = {}
        self.mention_spam_tracker = defaultdict(lambda: deque(maxlen=10))
        self.smart_automod_tracker = defaultdict(lambda: deque(maxlen=8))

    def check_rate_limit(self, user_id: int, config: dict) -> bool:
        now = time.time()
        limit = config.get("security", {}).get("max_actions_per_min", 10)
        while self._tracker[user_id] and now - self._tracker[user_id][0] > 60:
            self._tracker[user_id].popleft()
        self._tracker[user_id].append(now)
        return len(self._tracker[user_id]) > limit
