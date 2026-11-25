import os

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

IS_VERCEL = bool(os.environ.get("VERCEL"))


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        if IS_VERCEL:
            raise RuntimeError("DATABASE_URL is not set. Add your Neon connection string in Vercel > Settings > Environment Variables.")
        os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
        return "sqlite:///" + os.path.join(BASE_DIR, "instance", "invites.db").replace("\\", "/")
    # Neon / Heroku style URLs -> SQLAlchemy + psycopg (v3) driver
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "").strip() or "dev-only-secret-change-me"
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {
        **({"poolclass": NullPool} if IS_VERCEL else {"pool_pre_ping": True, "pool_recycle": 280}),
        # no server-side prepared statements (safe with Neon's pooled / PgBouncer endpoints), fail fast on bad networks
        **({"connect_args": {"prepare_threshold": None, "connect_timeout": 15}}
           if SQLALCHEMY_DATABASE_URI.startswith("postgresql") else {}),
    }
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    ALLOW_SIGNUP = _flag("ALLOW_SIGNUP", "true")
    BASE_URL = os.environ.get("BASE_URL", "").strip().rstrip("/")
    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    APP_NAME = os.environ.get("APP_NAME", "Invitation Studio")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_VERCEL
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 30
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = IS_VERCEL
    WTF_CSRF_TIME_LIMIT = None
