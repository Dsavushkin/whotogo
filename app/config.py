"""Settings come from environment variables (see .env.example)."""
import os


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.bot_token: str = os.getenv("BOT_TOKEN", "").strip()
        # Telegram is not reachable from many Russian data centres. Either a relay that forwards to
        # https://api.telegram.org (TELEGRAM_API_BASE=https://relay.example.com) or a proxy
        # (TELEGRAM_PROXY=http://user:pass@host:port).
        self.telegram_api_base: str = os.getenv("TELEGRAM_API_BASE", "").strip().rstrip("/")
        self.telegram_proxy: str = os.getenv("TELEGRAM_PROXY", "").strip()
        self.bot_username: str = os.getenv("BOT_USERNAME", "whotogobot")
        # Public HTTPS address of the Mini App, e.g. https://whotogo.example.ru
        self.webapp_url: str = os.getenv("WEBAPP_URL", "").rstrip("/")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./whotogo.db")
        # Anything that is not a number is ignored, so a typo here cannot stop the service.
        self.admin_ids: set[int] = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",")
                                    if x.isdigit()}
        self.admin_emails: set[str] = {x.strip().lower() for x in os.getenv("ADMIN_EMAILS", "").split(",") if x.strip()}
        self.city: str = os.getenv("CITY", "msk")
        self.timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")
        # DEV=1 lets requests sign in with the X-Dev-User header. Never enable in production.
        self.dev: bool = _bool("DEV")
        self.run_bot: bool = _bool("RUN_BOT", True)
        self.run_jobs: bool = _bool("RUN_JOBS", True)
        self.import_every_hours: float = _number("IMPORT_EVERY_HOURS", 3)
        self.timepad_token: str = os.getenv("TIMEPAD_TOKEN", "").strip()
        self.timepad_city: str = os.getenv("TIMEPAD_CITY", "Москва")
        self.import_days_ahead: int = int(_number("IMPORT_DAYS_AHEAD", 7))
        self.operator_name: str = os.getenv("OPERATOR_NAME", "")
        self.contact_email: str = os.getenv("CONTACT_EMAIL", "")
        self.init_data_max_age: int = int(_number("INIT_DATA_MAX_AGE", 24 * 3600))


    def is_admin(self, user) -> bool:
        return bool((user.tg_id and user.tg_id in self.admin_ids) or
                    (user.email and user.email.lower() in self.admin_emails))


settings = Settings()
