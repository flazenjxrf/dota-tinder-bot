"""Автоматически убирает старую reply-клавиатуру у зарегистрированных пользователей."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.database.models import ProfileStatus
from bot.database.requests import get_user_with_settings
from bot.keyboards.reply import REMOVE_KEYBOARD

_cleared_users: set[int] = set()


def mark_keyboard_cleared(user_id: int) -> None:
    _cleared_users.add(user_id)


async def _is_registered_user(user_id: int) -> bool:
    user = await get_user_with_settings(user_id)
    return bool(user and user.status != ProfileStatus.INCOMPLETE)


def _patch_message_answers(message: Message, user_id: int) -> None:
    if user_id in _cleared_users:
        return

    original_answer = message.answer
    original_answer_photo = message.answer_photo

    async def answer_with_remove(*args, **kwargs):
        if kwargs.get("reply_markup") is None:
            kwargs["reply_markup"] = REMOVE_KEYBOARD
            mark_keyboard_cleared(user_id)
        return await original_answer(*args, **kwargs)

    async def answer_photo_with_remove(*args, **kwargs):
        if kwargs.get("reply_markup") is None:
            kwargs["reply_markup"] = REMOVE_KEYBOARD
            mark_keyboard_cleared(user_id)
        return await original_answer_photo(*args, **kwargs)

    message.answer = answer_with_remove  # type: ignore[method-assign]
    message.answer_photo = answer_photo_with_remove  # type: ignore[method-assign]


async def _send_silent_remove(event: TelegramObject, user_id: int) -> None:
    if user_id in _cleared_users:
        return

    if isinstance(event, Message):
        chat_id = event.chat.id
        bot = event.bot
    elif isinstance(event, CallbackQuery):
        if not event.message:
            return
        chat_id = event.message.chat.id
        bot = event.bot
    else:
        return

    from bot.utils.bot_commands import MENU_HINT

    try:
        await bot.send_message(chat_id, MENU_HINT, reply_markup=REMOVE_KEYBOARD)
        mark_keyboard_cleared(user_id)
    except Exception:
        pass


class RemoveKeyboardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id in _cleared_users:
            return await handler(event, data)

        if not await _is_registered_user(user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            _patch_message_answers(event, user.id)
        elif isinstance(event, CallbackQuery) and event.message:
            _patch_message_answers(event.message, user.id)

        result = await handler(event, data)

        if user.id not in _cleared_users:
            await _send_silent_remove(event, user.id)

        return result
