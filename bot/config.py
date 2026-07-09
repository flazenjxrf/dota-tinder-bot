import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

DB_ECHO = os.getenv("DB_ECHO", "").lower() in ("1", "true", "yes")


def _normalize_database_url(url: str) -> str:
    """Приводит URL к формату postgresql+asyncpg:// и настраивает SSL для Railway."""
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    if "sslmode" in query:
        del query["sslmode"]
        query.setdefault("ssl", ["require"])

    host = parsed.hostname or ""
    is_railway_public = ("railway.app" in host or "rlwy.net" in host) and "railway.internal" not in host
    if is_railway_public and "ssl" not in query:
        query["ssl"] = ["require"]

    new_query = urlencode({key: values[0] for key, values in query.items()})
    return urlunparse(parsed._replace(query=new_query))


def _build_database_url() -> str:
    # Railway: приоритет у приватного URL внутри проекта
    for env_name in ("DATABASE_PRIVATE_URL", "DATABASE_URL"):
        database_url = os.getenv(env_name)
        if database_url:
            return _normalize_database_url(database_url)

    pg_user = os.getenv("POSTGRES_USER") or os.getenv("PGUSER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD", "qwerty")
    pg_db = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE", "dota_tinder")
    pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST", "db")
    pg_port = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT", "5432")

    return _normalize_database_url(
        f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    )


DATABASE_URL = _build_database_url()


def _parse_admin_ids() -> frozenset[int]:
    raw = os.getenv("ADMIN_IDS", "")
    if not raw.strip():
        return frozenset()
    return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())


ADMIN_IDS = _parse_admin_ids()
