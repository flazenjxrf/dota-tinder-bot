import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла (для локальной разработки)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Данные для PostgreSQL
# Приоритет: Railway DATABASE_URL > отдельные переменные > значения по умолчанию
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Если DATABASE_URL не задан (локальная разработка), собираем из отдельных переменных
    PG_USER = os.getenv("POSTGRES_USER", "postgres")
    PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "qwerty")
    PG_DB = os.getenv("POSTGRES_DB", "dota_tinder")
    PG_HOST = os.getenv("POSTGRES_HOST", "db")
    PG_PORT = os.getenv("POSTGRES_PORT", "5432")
    
    DATABASE_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
else:
    # Заменяем postgresql:// на postgresql+asyncpg:// для асинхронного драйвера
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")