"""Settings come from environment variables (see .env.example)."""
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.bot_token: str = os.getenv("BOT_TOKEN", "")
        self.bot_username: str = os.getenv("BOT_USERNAME", "whotogo")
        # Public HTTPS address of the Mini App, e.g. https://whotogo.example.ru
        self.webapp_url: str = os.getenv("WEBAPP_URL", "").rstrip("/")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./whotogo.db")
        self.admin_ids: set[int] = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
        self.city: str = os.getenv("CITY", "msk")
        self.timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")
        # DEV=1 lets requests sign in with the X-Dev-User header. Never enable in production.
        self.dev: bool = _bool("DEV")
        self.run_bot: bool = _bool("RUN_BOT", True)
        self.run_jobs: bool = _bool("RUN_JOBS", True)
        self.import_every_hours: float = float(os.getenv("IMPORT_EVERY_HOURS", "3"))
        self.timepad_token: str = os.getenv("TIMEPAD_TOKEN", "")
        self.timepad_city: str = os.getenv("TIMEPAD_CITY", "Москва")
        self.import_days_ahead: int = int(os.getenv("IMPORT_DAYS_AHEAD", "7"))
        self.operator_name: str = os.getenv("OPERATOR_NAME", "")
        self.contact_email: str = os.getenv("CONTACT_EMAIL", "")
        self.init_data_max_age: int = int(os.getenv("INIT_DATA_MAX_AGE", str(24 * 3600)))


settings = Settings()
