import os
import json
import asyncio
import aiosqlite
from typing import Optional, Dict, Any, List
from config import DB_PATH

class DataManager:
    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

    async def setup(self):
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()
        await self._db.commit()

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                reason TEXT,
                points INTEGER DEFAULT 1,
                duration_hours REAL DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                expires_at REAL DEFAULT NULL,
                case_number INTEGER,
                notes TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                status TEXT DEFAULT 'open'
            );
            CREATE TABLE IF NOT EXISTS tempbans (
                user_id INTEGER PRIMARY KEY,
                expires_at REAL NOT NULL,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS modmail (
                user_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                status TEXT DEFAULT 'open',
                created_at REAL NOT NULL,
                last_message_at REAL,
                sla_alerted INTEGER DEFAULT 0,
                transcript TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS custom_roles (
                user_id INTEGER PRIMARY KEY,
                role_id INTEGER NOT NULL,
                role_name TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mod_stats (
                moderator_id INTEGER PRIMARY KEY,
                warns INTEGER DEFAULT 0,
                timeouts INTEGER DEFAULT 0,
                bans INTEGER DEFAULT 0,
                kicks INTEGER DEFAULT 0,
                cases_closed INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS automod_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rule TEXT NOT NULL,
                message TEXT,
                action_taken TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS onboarding (
                user_id INTEGER PRIMARY KEY,
                step INTEGER DEFAULT 0,
                roles_granted TEXT DEFAULT '[]',
                completed INTEGER DEFAULT 0,
                started_at REAL NOT NULL,
                completed_at REAL DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS message_cache (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                content TEXT,
                created_at REAL NOT NULL
            );
        """)

    # --- Config ---
    async def get_config(self) -> Dict[str, Any]:
        async with self._db.execute("SELECT key, value FROM config") as cur:
            rows = await cur.fetchall()
        result = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except Exception:
                result[row["key"]] = row["value"]
        return result

    async def set_config(self, key: str, value: Any):
        await self._db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
        await self._db.commit()

    async def update_config(self, updates: Dict[str, Any]):
        for key, value in updates.items():
            await self._db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
        await self._db.commit()

    async def provision(self):
        from config import DEFAULT_FEATURE_FLAGS, DEFAULT_ESCALATION_MATRIX, DEFAULT_AUTOMOD_SETTINGS
        config = await self.get_config()
        if not config.get("provisioned"):
            await self.update_config({
                "provisioned": True,
                "feature_flags": DEFAULT_FEATURE_FLAGS,
                "escalation_matrix": DEFAULT_ESCALATION_MATRIX,
                "automod": DEFAULT_AUTOMOD_SETTINGS,
                "next_case_number": 1,
            })

    # --- Punishments / Cases ---
    async def add_punishment(self, user_id: int, moderator_id: int, type: str,
                              reason: str = None, points: int = 1,
                              duration_hours: float = 0) -> int:
        import time
        config = await self.get_config()
        case_number = config.get("next_case_number", 1)
        await self._db.execute(
            """INSERT INTO punishments
               (user_id, moderator_id, type, reason, points, duration_hours, created_at, case_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, moderator_id, type, reason, points, duration_hours, time.time(), case_number)
        )
        await self.set_config("next_case_number", case_number + 1)
        await self._db.commit()
        await self._increment_mod_stat(moderator_id, type)
        return case_number

    async def get_user_punishments(self, user_id: int) -> List[Dict]:
        async with self._db.execute(
            "SELECT * FROM punishments WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_case(self, case_number: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM punishments WHERE case_number = ?", (case_number,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def update_case(self, case_number: int, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [case_number]
        await self._db.execute(f"UPDATE punishments SET {sets} WHERE case_number = ?", vals)
        await self._db.commit()

    async def get_user_points(self, user_id: int) -> int:
        async with self._db.execute(
            "SELECT SUM(points) as total FROM punishments WHERE user_id = ? AND active = 1", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row["total"] or 0 if row else 0

    async def add_case_note(self, case_number: int, author_id: int, note: str):
        import time
        case = await self.get_case(case_number)
        if not case:
            return
        notes = json.loads(case.get("notes", "[]"))
        notes.append({"author_id": author_id, "note": note, "created_at": time.time()})
        await self.update_case(case_number, notes=json.dumps(notes))

    async def search_cases(self, user_id: int = None, moderator_id: int = None,
                           type: str = None, status: str = None) -> List[Dict]:
        conditions = []
        params = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if moderator_id:
            conditions.append("moderator_id = ?")
            params.append(moderator_id)
        if type:
            conditions.append("type = ?")
            params.append(type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with self._db.execute(
            f"SELECT * FROM punishments {where} ORDER BY created_at DESC", params
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- Tempbans ---
    async def add_tempban(self, user_id: int, expires_at: float, reason: str = None):
        await self._db.execute(
            "INSERT OR REPLACE INTO tempbans (user_id, expires_at, reason) VALUES (?, ?, ?)",
            (user_id, expires_at, reason)
        )
        await self._db.commit()

    async def remove_tempban(self, user_id: int):
        await self._db.execute("DELETE FROM tempbans WHERE user_id = ?", (user_id,))
        await self._db.commit()

    async def get_expired_tempbans(self, now: float) -> List[int]:
        async with self._db.execute(
            "SELECT user_id FROM tempbans WHERE expires_at <= ?", (now,)
        ) as cur:
            rows = await cur.fetchall()
        return [r["user_id"] for r in rows]

    # --- Modmail ---
    async def open_ticket(self, user_id: int, channel_id: int) -> bool:
        import time
        existing = await self.get_ticket(user_id)
        if existing and existing["status"] == "open":
            return False
        await self._db.execute(
            "INSERT OR REPLACE INTO modmail (user_id, channel_id, status, created_at) VALUES (?, ?, 'open', ?)",
            (user_id, channel_id, time.time())
        )
        await self._db.commit()
        return True

    async def close_ticket(self, user_id: int):
        await self._db.execute(
            "UPDATE modmail SET status = 'closed' WHERE user_id = ?", (user_id,)
        )
        await self._db.commit()

    async def get_ticket(self, user_id: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM modmail WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_open_tickets(self) -> List[Dict]:
        async with self._db.execute(
            "SELECT * FROM modmail WHERE status = 'open'"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_ticket_sla_alerted(self, user_id: int):
        await self._db.execute(
            "UPDATE modmail SET sla_alerted = 1 WHERE user_id = ?", (user_id,)
        )
        await self._db.commit()

    async def append_ticket_transcript(self, user_id: int, message: Dict):
        import time
        ticket = await self.get_ticket(user_id)
        if not ticket:
            return
        transcript = json.loads(ticket.get("transcript", "[]"))
        transcript.append(message)
        await self._db.execute(
            "UPDATE modmail SET transcript = ?, last_message_at = ? WHERE user_id = ?",
            (json.dumps(transcript), time.time(), user_id)
        )
        await self._db.commit()

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM modmail WHERE channel_id = ? AND status = 'open'", (channel_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # --- Custom Roles ---
    async def set_custom_role(self, user_id: int, role_id: int, role_name: str):
        import time
        await self._db.execute(
            "INSERT OR REPLACE INTO custom_roles (user_id, role_id, role_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role_id, role_name, time.time())
        )
        await self._db.commit()

    async def get_custom_role(self, user_id: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM custom_roles WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def remove_custom_role(self, user_id: int):
        await self._db.execute("DELETE FROM custom_roles WHERE user_id = ?", (user_id,))
        await self._db.commit()

    async def get_all_custom_roles(self) -> Dict[int, Dict]:
        async with self._db.execute("SELECT * FROM custom_roles") as cur:
            rows = await cur.fetchall()
        return {r["user_id"]: dict(r) for r in rows}

    # --- Mod Stats ---
    async def _increment_mod_stat(self, moderator_id: int, action_type: str):
        col_map = {"warn": "warns", "timeout": "timeouts", "ban": "bans", "kick": "kicks"}
        col = col_map.get(action_type)
        if not col:
            return
        await self._db.execute(
            f"INSERT INTO mod_stats (moderator_id, {col}) VALUES (?, 1) "
            f"ON CONFLICT(moderator_id) DO UPDATE SET {col} = {col} + 1",
            (moderator_id,)
        )
        await self._db.commit()

    async def get_mod_stats(self, moderator_id: int) -> Dict:
        async with self._db.execute(
            "SELECT * FROM mod_stats WHERE moderator_id = ?", (moderator_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else {"warns": 0, "timeouts": 0, "bans": 0, "kicks": 0, "cases_closed": 0}

    async def get_all_mod_stats(self) -> List[Dict]:
        async with self._db.execute("SELECT * FROM mod_stats ORDER BY (warns+timeouts+bans+kicks) DESC") as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- Automod ---
    async def log_automod(self, user_id: int, rule: str, message: str, action: str):
        import time
        await self._db.execute(
            "INSERT INTO automod_log (user_id, rule, message, action_taken, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, rule, message, action, time.time())
        )
        await self._db.commit()

    # --- Onboarding ---
    async def get_onboarding(self, user_id: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM onboarding WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def set_onboarding(self, user_id: int, **kwargs):
        import time
        existing = await self.get_onboarding(user_id)
        if not existing:
            await self._db.execute(
                "INSERT INTO onboarding (user_id, started_at) VALUES (?, ?)",
                (user_id, time.time())
            )
            await self._db.commit()
        if kwargs:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [user_id]
            await self._db.execute(f"UPDATE onboarding SET {sets} WHERE user_id = ?", vals)
            await self._db.commit()

    # --- Message Cache ---
    async def cache_message(self, message_id: int, user_id: int, channel_id: int, content: str):
        import time
        await self._db.execute(
            "INSERT OR REPLACE INTO message_cache (message_id, user_id, channel_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, user_id, channel_id, content, time.time())
        )
        # Keep only last 1000 messages
        await self._db.execute(
            "DELETE FROM message_cache WHERE message_id NOT IN (SELECT message_id FROM message_cache ORDER BY created_at DESC LIMIT 1000)"
        )
        await self._db.commit()

    async def get_cached_message(self, message_id: int) -> Optional[Dict]:
        async with self._db.execute(
            "SELECT * FROM message_cache WHERE message_id = ?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def close(self):
        if self._db:
            await self._db.close()
