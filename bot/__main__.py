import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.config import BOT_TOKEN
from bot.database.engine import init_models
from bot.database.requests import get_all_consented_ids
from bot.middleware.consent import ConsentMiddleware
from bot.services import consent_cache

# Импортируем все наши обработчики (хэндлеры)
from bot.handlers import start, register, settings, profile, swiping, likes, report, matches, fallback


async def main():
    # 1. Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота...")

    # 2. Инициализация базы данных
    logger.info("Подключение к PostgreSQL и инициализация таблиц...")
    try:
        await init_models()
        logger.info("База данных успешно инициализирована!")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        return

    consent_ids = await get_all_consented_ids()
    consent_cache.warm(consent_ids)
    logger.info("Кэш согласий загружен: %d пользователей", len(consent_ids))

    # 3. Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()
    dp.message.middleware(ConsentMiddleware())
    dp.callback_query.middleware(ConsentMiddleware())

    # 4. Подключение роутеров к диспетчеру (порядок важен)
    dp.include_router(start.router)
    dp.include_router(register.router)
    dp.include_router(settings.router)
    dp.include_router(profile.router)
    dp.include_router(swiping.router)
    dp.include_router(likes.router)
    dp.include_router(matches.router)
    dp.include_router(report.router)
    dp.include_router(fallback.router)

    # 5. Запуск опроса серверов Telegram (polling)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот начал принимать сообщения (Polling запущен) 🚀")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот был принудительно остановлен.")
