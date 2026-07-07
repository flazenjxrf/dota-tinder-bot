from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import DATABASE_URL
from bot.database.models import Base

# echo=True будет выводить все SQL-запросы в консоль (удобно для дебага, в продакшене лучше выключить)
engine = create_async_engine(DATABASE_URL, echo=True)

# Фабрика сессий. Через неё мы будем делать запросы к БД
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_models():
    """Создает таблицы в БД, если их еще нет"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)