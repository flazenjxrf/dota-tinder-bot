"""Зависимости FastAPI: текущий пользователь Telegram и Bot."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from fastapi import Depends, Header, HTTPException, Request, status

from bot.webapp.auth import validate_webapp_init_data


@dataclass(frozen=True)
class WebAppUser:
    id: int
    username: str | None
    first_name: str | None


def _extract_init_data(
    authorization: str | None,
    x_telegram_init_data: str | None,
) -> str:
    if authorization and authorization.lower().startswith("tma "):
        return authorization[4:].strip()
    if x_telegram_init_data:
        return x_telegram_init_data.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Открой приложение из Telegram",
    )


async def get_webapp_user(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> WebAppUser:
    init_data = _extract_init_data(authorization, x_telegram_init_data)
    tg_user = validate_webapp_init_data(init_data)
    return WebAppUser(
        id=int(tg_user["id"]),
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )


async def get_bot(request: Request) -> Bot:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot не инициализирован",
        )
    return bot


CurrentUser = Depends(get_webapp_user)
CurrentBot = Depends(get_bot)
