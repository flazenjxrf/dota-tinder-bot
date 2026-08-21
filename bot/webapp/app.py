"""FastAPI-приложение Mini App: API + статика."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bot.config import BOT_TOKEN
from bot.database.engine import init_models
from bot.webapp.api import router as api_router

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    *,
    bot: Bot | None = None,
    init_db: bool = True,
) -> FastAPI:
    """
    bot — общий экземпляр из процесса бота (Railway: один контейнер).
    Если bot не передан, создаётся свой (режим python -m bot.webapp).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_bot = False
        if bot is not None:
            app.state.bot = bot
        else:
            if not BOT_TOKEN:
                raise RuntimeError("BOT_TOKEN не задан")
            if init_db:
                logger.info("Инициализация БД для Mini App...")
                await init_models()
            app.state.bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode="HTML"),
            )
            owns_bot = True
            logger.info("Mini App API готов (standalone)")

        try:
            yield
        finally:
            if owns_bot:
                await app.state.bot.session.close()

    app = FastAPI(title="FeedEther Mini App", lifespan=lifespan)
    app.include_router(api_router)

    @app.get("/health")
    async def health():
        return {"ok": True}

    if STATIC_DIR.is_dir():
        assets = STATIC_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        index_file = STATIC_DIR / "index.html"

        @app.get("/")
        async def index():
            return FileResponse(index_file)

    return app


# Для uvicorn bot.webapp.app:app и python -m bot.webapp
app = create_app()
