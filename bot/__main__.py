import asyncio
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.config import BOT_TOKEN, WEBAPP_URL
from bot.database.engine import init_models
from bot.database.requests import get_all_consented_ids, get_all_banned_ids
from bot.middleware.consent import ConsentMiddleware
from bot.middleware.ban import BanMiddleware
from bot.middleware.keyboard import RemoveKeyboardMiddleware
from bot.services import consent_cache, ban_cache
from bot.utils.bot_commands import setup_bot_commands
from bot.webapp.app import create_app

# Импортируем все наши обработчики (хэндлеры)
from bot.handlers import start, legacy_menu, register, settings, profile, swiping, likes, report, matches, feedback, banned, admin, fallback


def _http_port() -> int:
    # Railway всегда задаёт PORT; локально по умолчанию 8080
    return int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "8080")


async def main():
    # 1. Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота + Mini App...")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан. Добавь переменную окружения в Railway.")
        return

    # 2. Инициализация базы данных (с повторами — БД на Railway может подниматься чуть дольше)
    logger.info("Подключение к PostgreSQL и инициализация таблиц...")
    db_ready = False
    for attempt in range(1, 11):
        try:
            await init_models()
            db_ready = True
            break
        except Exception as e:
            if attempt == 10:
                logger.error("Не удалось подключиться к БД после 10 попыток: %s", e)
                return
            logger.warning(
                "БД недоступна (попытка %d/10), повтор через 3 сек: %s",
                attempt,
                e,
            )
            await asyncio.sleep(3)

    if not db_ready:
        return

    logger.info("База данных успешно инициализирована!")

    consent_ids = await get_all_consented_ids()
    consent_cache.warm(consent_ids)
    logger.info("Кэш согласий загружен: %d пользователей", len(consent_ids))

    banned_ids = await get_all_banned_ids()
    ban_cache.warm(banned_ids)
    logger.info("Кэш банов загружен: %d пользователей", len(banned_ids))

    # 3. Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()
    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())
    dp.message.middleware(ConsentMiddleware())
    dp.callback_query.middleware(ConsentMiddleware())
    dp.message.middleware(RemoveKeyboardMiddleware())
    dp.callback_query.middleware(RemoveKeyboardMiddleware())

    # 4. Подключение роутеров к диспетчеру (порядок важен)
    dp.include_router(start.router)
    dp.include_router(legacy_menu.router)
    dp.include_router(register.router)
    dp.include_router(settings.router)
    dp.include_router(profile.router)
    dp.include_router(swiping.router)
    dp.include_router(likes.router)
    dp.include_router(matches.router)
    dp.include_router(report.router)
    dp.include_router(feedback.router)
    dp.include_router(banned.router)
    dp.include_router(admin.router)
    dp.include_router(fallback.router)

    # 5. Mini App (HTTP) + polling в одном процессе — удобно для Railway
    port = _http_port()
    web_app = create_app(bot=bot, init_db=False)
    uv_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(uv_config)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        try:
            await setup_bot_commands(bot)
            if WEBAPP_URL:
                logger.info("Mini App URL: %s", WEBAPP_URL)
            else:
                logger.warning(
                    "WEBAPP_URL пуст: задай публичный домен в Railway "
                    "(Generate Domain) или переменную WEBAPP_URL"
                )
            logger.info("Меню команд Telegram настроено")
        except Exception as e:
            logger.warning("Не удалось настроить меню команд: %s", e)

        logger.info("HTTP Mini App на порту %s, polling запущен 🚀", port)
        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот был принудительно остановлен.")
