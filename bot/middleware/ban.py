from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.config import ADMIN_IDS
from bot.database.requests import is_user_banned
from bot.services import ban_cache

BAN_MESSAGE = (
    "🚫 <b>Твой аккаунт заблокирован</b> за нарушение правил.\n\n"
    "Повторная регистрация не поможет. По вопросам блокировки: @flazenjxrf"
)


def _is_exempt(event: TelegramObject, user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True

    if isinstance(event, Message):
        text = event.text or ""
        if text.startswith("/admin"):
            return True

    if isinstance(event, CallbackQuery):
        data = event.data or ""
        if data.startswith("adm"):
            return True

    return False


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        if _is_exempt(event, user.id):
            return await handler(event, data)

        if ban_cache.has(user.id) or await is_user_banned(user.id):
            if isinstance(event, Message):
                await event.answer(BAN_MESSAGE)
                return None

            if isinstance(event, CallbackQuery):
                await event.answer("Аккаунт заблокирован.", show_alert=True)
                return None

        return await handler(event, data)
