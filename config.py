import os

def _load_env():
    env_file = os.environ.get("ENV_FILE", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
BOT_OWNER_IDS = frozenset(
    int(x) for x in os.environ.get("BOT_OWNER_IDS", "").split(",") if x.strip().isdigit()
)
DB_PATH = os.environ.get("DB_PATH", "database/bot.db")

BRAND_NAME = "Guilda"
BRAND_COLOR = 0x5865F2

DEFAULT_FEATURE_FLAGS = {
    "advanced_case_panel": True,
    "advanced_modmail": True,
    "role_cleanup": False,
    "automod_enabled": False,
    "onboarding_enabled": False,
}

DEFAULT_ESCALATION_MATRIX = [
    {"points": 3,  "action": "timeout", "duration_hours": 1},
    {"points": 5,  "action": "timeout", "duration_hours": 24},
    {"points": 8,  "action": "timeout", "duration_hours": 168},
    {"points": 10, "action": "ban",     "duration_hours": 0},
]

DEFAULT_AUTOMOD_SETTINGS = {
    "spam_threshold": 5,
    "spam_window_seconds": 10,
    "banned_words": [],
    "link_filter": False,
    "mention_limit": 10,
}
