"""
Скрипт для миграции существующих данных: нормализация городов в базе данных.

Запуск:
python migrate_existing_cities.py
"""

import asyncio
import logging
from sqlalchemy import select, update
from bot.database.engine import session_maker
from bot.database.models import User
from bot.utils.city_normalizer import normalize_city

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def migrate_cities():
    """Нормализует города для всех существующих пользователей в базе данных."""
    async with session_maker() as session:
        try:
            # Получаем всех пользователей
            stmt = select(User)
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            logger.info(f"Найдено {len(users)} пользователей для миграции")
            
            updated_count = 0
            skipped_count = 0
            
            for user in users:
                if not user.city:
                    skipped_count += 1
                    continue
                
                # Нормализуем город
                normalized = normalize_city(user.city)
                
                # Если normalized_city уже совпадает с нормализованным значением, пропускаем
                if user.normalized_city == normalized:
                    skipped_count += 1
                    continue
                
                # Обновляем normalized_city
                user.normalized_city = normalized
                updated_count += 1
                
                logger.info(f"Обновлен пользователь {user.telegram_id}: '{user.city}' -> '{normalized}'")
            
            # Коммитим изменения
            await session.commit()
            
            logger.info(f"Миграция завершена успешно!")
            logger.info(f"Обновлено: {updated_count}")
            logger.info(f"Пропущено: {skipped_count}")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при миграции: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(migrate_cities())
