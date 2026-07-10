from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.config import ADMIN_IDS
from bot.database.requests import is_user_banned
from bot.services import ban_cache
from bot.states.fsm import FeedbackForm, UnbanRequestForm, EditProfile

from bot.utils.bot_commands import CMD_PROFILE, CMD_FEEDBACK

BAN_MESSAGE = (
    "🚫 <b>Твой аккаунт заблокирован</b> за нарушение правил.\n\n"
    "Ты можешь отредактировать анкету или подать запрос на разбан — /profile"
)

_BANNED_FSM_PREFIXES = (
    FeedbackForm.__name__,
    UnbanRequestForm.__name__,
    EditProfile.__name__,
)

_BANNED_CALLBACK_EXACT = {
    "back_to_profile", "menu_edit_profile", "confirm_positions",
    "banned_request_unban", "banned_unban_pending", "unban_request_cancel",
    "feedback_cancel",
}

_BANNED_CALLBACK_PREFIXES = ("pos:", "edit_field_")


def _is_banned_callback_allowed(data: str) -> bool:
    if data in _BANNED_CALLBACK_EXACT:
        return True
    return any(data.startswith(prefix) for prefix in _BANNED_CALLBACK_PREFIXES)


def _is_exempt(event: TelegramObject, user_id: int, current_state: str | None = None) -> bool:
    if user_id in ADMIN_IDS:
        return True

    if current_state and current_state.startswith(_BANNED_FSM_PREFIXES):
        return True

    if isinstance(event, Message):
        text = event.text or ""
        if text.startswith("/admin") or text.startswith(f"/{CMD_FEEDBACK}"):
            return True
        if text.startswith(f"/{CMD_PROFILE}"):
            return True

    if isinstance(event, CallbackQuery):
        data = event.data or ""
        if data.startswith("adm"):
            return True
        if _is_banned_callback_allowed(data):
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

        state = data.get("state")
        current_state = await state.get_state() if state else None

        if _is_exempt(event, user.id, current_state):
            return await handler(event, data)

        if ban_cache.has(user.id) or await is_user_banned(user.id):
            if isinstance(event, Message):
                from bot.handlers.banned import send_banned_user_menu
                await send_banned_user_menu(event)
                return None

            if isinstance(event, CallbackQuery):
                await event.answer("Аккаунт заблокирован.", show_alert=True)
                return None

        return await handler(event, data)
