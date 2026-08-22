from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from bot.config import DATABASE_URL, DB_ECHO
from bot.database.models import Base

engine = create_async_engine(DATABASE_URL, echo=DB_ECHO)

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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS banned_users (
                telegram_id BIGINT PRIMARY KEY,
                banned_by BIGINT NOT NULL,
                reason TEXT,
                banned_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
            )
        """))
        await conn.execute(text(
            "ALTER TABLE banned_users ADD COLUMN IF NOT EXISTS violation_number INTEGER DEFAULT 1"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ban_history (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                banned_by BIGINT NOT NULL,
                reason TEXT,
                violation_number INTEGER NOT NULL DEFAULT 1,
                banned_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                unbanned_at TIMESTAMP
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_ban_history_telegram_id "
            "ON ban_history (telegram_id)"
        ))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS unban_requests (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                resolved_at TIMESTAMP,
                resolved_by BIGINT
            )
        """))
        await conn.execute(text(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'"
        ))
        await conn.execute(text(
            "UPDATE reports SET status = 'pending' WHERE status IS NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS comment TEXT"
        ))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE reports ALTER COLUMN reason TYPE VARCHAR(50) USING reason::text;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS teammate_ratings (
                id BIGSERIAL PRIMARY KEY,
                from_user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                to_user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                has_aura BOOLEAN NOT NULL DEFAULT FALSE,
                has_vibe BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                CONSTRAINT uq_teammate_rating_from_to UNIQUE (from_user_id, to_user_id)
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_teammate_ratings_to_user_id "
            "ON teammate_ratings (to_user_id)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_game VARCHAR(20) DEFAULT 'dota'"
        ))
        await conn.execute(text(
            "UPDATE users SET last_active_game = 'dota' WHERE last_active_game IS NULL OR last_active_game = ''"
        ))
        await conn.execute(text(
            "ALTER TABLE swipes ADD COLUMN IF NOT EXISTS game VARCHAR(20) DEFAULT 'dota'"
        ))
        await conn.execute(text(
            "UPDATE swipes SET game = 'dota' WHERE game IS NULL OR game = ''"
        ))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE swipes DROP CONSTRAINT IF EXISTS uq_swipe_from_to;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE swipes ADD CONSTRAINT uq_swipe_from_to_game
                UNIQUE (from_user_id, to_user_id, game);
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        await conn.execute(text(
            "ALTER TABLE teammate_ratings ADD COLUMN IF NOT EXISTS game VARCHAR(20) DEFAULT 'dota'"
        ))
        await conn.execute(text(
            "UPDATE teammate_ratings SET game = 'dota' WHERE game IS NULL OR game = ''"
        ))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE teammate_ratings DROP CONSTRAINT IF EXISTS uq_teammate_rating_from_to;
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE teammate_ratings ADD CONSTRAINT uq_teammate_rating_from_to_game
                UNIQUE (from_user_id, to_user_id, game);
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """))
        await _migrate_legacy_dota_profiles(conn)

    from bot.database.requests import backfill_normalized_cities
    await backfill_normalized_cities()


async def _migrate_legacy_dota_profiles(conn) -> None:
    """Переносит mmr/роли/фото/bio и фильтры со старых колонок users в игровые анкеты."""
    users_has_mmr = await conn.execute(text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.columns "
        "  WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'mmr'"
        ")"
    ))
    if not users_has_mmr.scalar():
        return

    await conn.execute(text("""
        INSERT INTO game_profiles (user_id, game, bio, photo_file_id, roles, status)
        SELECT
            u.telegram_id,
            'dota',
            u.bio,
            u.photo_file_id,
            COALESCE(u.positions, ARRAY[]::integer[]),
            CASE
                WHEN u.status::text IN ('HIDDEN', 'hidden') THEN 'HIDDEN'
                WHEN u.status::text IN ('ACTIVE', 'active', 'BANNED', 'banned') THEN 'ACTIVE'
                ELSE 'INCOMPLETE'
            END::profilestatus
        FROM users u
        WHERE COALESCE(u.name, '') <> ''
          AND NOT EXISTS (
              SELECT 1 FROM game_profiles gp
              WHERE gp.user_id = u.telegram_id AND gp.game = 'dota'
          )
    """))
    await conn.execute(text("""
        INSERT INTO game_ratings (profile_id, kind, value)
        SELECT gp.id, 'mmr', COALESCE(u.mmr, 0)
        FROM game_profiles gp
        JOIN users u ON u.telegram_id = gp.user_id
        WHERE gp.game = 'dota'
          AND NOT EXISTS (
              SELECT 1 FROM game_ratings gr
              WHERE gr.profile_id = gp.id AND gr.kind = 'mmr'
          )
    """))

    settings_exists = await conn.execute(text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables "
        "  WHERE table_schema = 'public' AND table_name = 'search_settings'"
        ")"
    ))
    if settings_exists.scalar():
        await conn.execute(text("""
            INSERT INTO game_search_settings (
                game_profile_id, min_age, max_age, wanted_roles,
                wanted_rating_kind, min_skill, max_skill
            )
            SELECT
                gp.id,
                s.min_age,
                s.max_age,
                s.wanted_positions,
                'mmr',
                s.min_mmr,
                s.max_mmr
            FROM search_settings s
            JOIN game_profiles gp ON gp.user_id = s.user_id AND gp.game = 'dota'
            WHERE NOT EXISTS (
                SELECT 1 FROM game_search_settings gss
                WHERE gss.game_profile_id = gp.id
            )
        """))

    await conn.execute(text("""
        UPDATE users
        SET status = 'ACTIVE'::profilestatus
        WHERE status::text IN ('HIDDEN', 'hidden')
    """))