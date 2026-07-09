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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_consent_log (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                username VARCHAR,
                consented_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_user_consent_log_telegram_id "
            "ON user_consent_log (telegram_id)"
        ))
        old_consents = await conn.execute(text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = 'user_consents'"
            ")"
        ))
        if old_consents.scalar():
            await conn.execute(text("""
                INSERT INTO user_consent_log (telegram_id, username, consented_at)
                SELECT o.telegram_id, o.username, COALESCE(o.consented_at, NOW())
                FROM user_consents o
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_consent_log n
                    WHERE n.telegram_id = o.telegram_id
                      AND n.consented_at = COALESCE(o.consented_at, NOW())
                )
            """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS profile_deletions (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                deleted_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_profile_deletions_telegram_id "
            "ON profile_deletions (telegram_id)"
        ))

    from bot.database.requests import backfill_normalized_cities
    await backfill_normalized_cities()