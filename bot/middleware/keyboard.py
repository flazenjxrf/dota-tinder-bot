"""Автоматически убирает старую reply-клавиатуру у зарегистрированных пользователей."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.database.models import ProfileStatus
from bot.database.requests import get_user_with_settings
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import MENU_HINT

logger = logging.getLogger(__name__)

_cleared_users: set[int] = set()


def mark_keyboard_cleared(user_id: int) -> None:
    _cleared_users.add(user_id)


async def _is_registered_user(user_id: int) -> bool:
    user = await get_user_with_settings(user_id)
    return bool(user and user.status != ProfileStatus.INCOMPLETE)


async def _remove_legacy_keyboard(event: TelegramObject, user_id: int) -> None:
    if user_id in _cleared_users:
        return

    if isinstance(event, Message):
        chat_id = event.chat.id
        bot = event.bot
    elif isinstance(event, CallbackQuery) and event.message:
        chat_id = event.message.chat.id
        bot = event.bot
    else:
        return

    try:
        await bot.send_message(chat_id, MENU_HINT, reply_markup=REMOVE_KEYBOARD)
        mark_keyboard_cleared(user_id)
    except Exception as exc:
        logger.warning("Не удалось убрать reply-клавиатуру у %s: %s", user_id, exc)


class RemoveKeyboardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        result = await handler(event, data)

        if user and user.id not in _cleared_users and await _is_registered_user(user.id):
            await _remove_legacy_keyboard(event, user.id)

        return result
