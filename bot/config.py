import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Данные для PostgreSQL
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "qwerty")
PG_DB = os.getenv("POSTGRES_DB", "dota_tinder")
PG_HOST = os.getenv("POSTGRES_HOST", "db")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")

# Формируем URL для подключения через asyncpg
DATABASE_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"


def _parse_admin_ids() -> frozenset[int]:
    raw = os.getenv("ADMIN_IDS", "")
    if not raw.strip():
        return frozenset()
    return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())


ADMIN_IDS = _parse_admin_ids()