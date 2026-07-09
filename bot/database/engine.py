from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from bot.config import DATABASE_URL
from bot.database.models import Base

# echo=True будет выводить все SQL-запросы в консоль (удобно для дебага, в продакшене лучше выключить)
engine = create_async_engine(DATABASE_URL, echo=True)

# Фабрика сессий. Через неё мы будем делать запросы к БД
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_models():
    """Создает таблицы в БД, если их еще нет, и заполняет normalized_city."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS normalized_city VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE swipes ADD COLUMN IF NOT EXISTS message TEXT"
        ))

    from bot.database.requests import backfill_normalized_cities
    await backfill_normalized_cities()