from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text, inspect, select
from bot.config import DATABASE_URL
from bot.database.models import Base, User
from bot.utils.city_normalizer import normalize_city

# echo=True будет выводить все SQL-запросы в консоль (удобно для дебага, в продакшене лучше выключить)
engine = create_async_engine(DATABASE_URL, echo=False)

# Фабрика сессий. Через неё мы будем делать запросы к БД
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def init_models():
    """Создает таблицы в БД, если их еще нет, и добавляет недостающие колонки"""
    async with engine.begin() as conn:
        # Создаем таблицы если их нет
        await conn.run_sync(Base.metadata.create_all)
        
        # Проверяем и добавляем колонку normalized_city если её нет
        column_added = await conn.run_sync(_add_normalized_city_if_missing)
        
        # Если колонка была добавлена, нормализуем существующие данные
        if column_added:
            print("Нормализуем существующие города...")
            await _migrate_existing_cities(conn)
            print("Миграция завершена")


def _add_normalized_city_if_missing(connection):
    """Добавляет колонку normalized_city если она не существует (синхронная функция для run_sync)"""
    inspector = inspect(connection)
    
    # Проверяем существование таблицы users
    if 'users' not in inspector.get_table_names():
        return False
    
    # Получаем существующие колонки
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Если колонки normalized_city нет - добавляем её
    if 'normalized_city' not in columns:
        print("Добавляем колонку normalized_city...")
        connection.execute(text("""
            ALTER TABLE users 
            ADD COLUMN normalized_city VARCHAR(50)
        """))
        
        # Создаем индекс
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_users_normalized_city 
            ON users (normalized_city)
        """))
        
        print("Колонка normalized_city и индекс успешно добавлены")
        return True
    
    return False


async def _migrate_existing_cities(connection):
    """Нормализует города для существующих пользователей"""
    # Получаем всех пользователей
    result = await connection.execute(select(User))
    users = result.scalars().all()
    
    updated_count = 0
    for user in users:
        if user.city and not user.normalized_city:
            normalized = normalize_city(user.city)
            await connection.execute(
                text("UPDATE users SET normalized_city = :normalized WHERE telegram_id = :user_id"),
                {"normalized": normalized, "user_id": user.telegram_id}
            )
            updated_count += 1
    
    await connection.commit()
    print(f"Обновлено {updated_count} пользователей")