"""Валидация Telegram WebApp initData."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, status

from bot.config import BOT_TOKEN

# initData считается устаревшим через 24 часа
MAX_AUTH_AGE_SECONDS = 86400


def validate_webapp_init_data(init_data: str) -> dict:
    """
    Проверяет подпись initData и возвращает объект user из Telegram.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_TOKEN не настроен",
        )
    if not init_data or not init_data.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нет данных авторизации Telegram",
        )

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректные данные авторизации",
        )

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Подпись initData неверна",
        )

    auth_date_raw = parsed.get("auth_date")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный auth_date",
        ) from None

    if time.time() - auth_date > MAX_AUTH_AGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия Mini App устарела — переоткрой приложение",
        )

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В initData нет пользователя",
        )

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный объект user",
        ) from exc

    if "id" not in user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В user нет id",
        )

    return user
