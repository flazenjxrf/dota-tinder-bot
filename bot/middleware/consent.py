import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.database.requests import get_consent_gate_status
from bot.services import consent_cache
from bot.keyboards.inline import get_consent_keyboard
from bot.states.fsm import RegisterForm, SearchSettingsForm

logger = logging.getLogger(__name__)

CONSENT_PENDING_MESSAGE = "consent_pending_message"
CONSENT_GATE_SHOWN = "consent_gate_shown"

EXISTING_USER_CONSENT_TEXT = (
    "Продолжая пользоваться ботом, ты соглашаешься на обработку и отображение "
    "информации из своей анкеты другим пользователям для поиска игроков."
)

_REGISTRATION_STATE_PREFIXES = (
    RegisterForm.__name__,
    SearchSettingsForm.__name__,
)


def _is_registration_state(state: str | None) -> bool:
    if not state:
        return False
    return state.startswith(_REGISTRATION_STATE_PREFIXES)


def _is_exempt(event: TelegramObject, state: str | None) -> bool:
    if _is_registration_state(state):
        return True

    if isinstance(event, Message):
        text = event.text or ""
        if text.startswith("/start"):
            return True

    if isinstance(event, CallbackQuery):
        if event.data in {"accept_consent", "start_registration"}:
            return True

    return False


async def _send_consent_prompt(event: TelegramObject, state_data: dict) -> None:
    keyboard = get_consent_keyboard()
    already_shown = state_data.get(CONSENT_GATE_SHOWN)

    if isinstance(event, Message):
        if not already_shown:
            await event.answer(EXISTING_USER_CONSENT_TEXT, reply_markup=keyboard)
        return

    if isinstance(event, CallbackQuery):
        if not already_shown:
            await event.message.answer(EXISTING_USER_CONSENT_TEXT, reply_markup=keyboard)
        await event.answer("Сначала прими соглашение", show_alert=True)


class ConsentMiddleware(BaseMiddleware):
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

        if _is_exempt(event, current_state):
            return await handler(event, data)

        if consent_cache.has(user.id):
            return await handler(event, data)

        gate_status = await get_consent_gate_status(user.id)
        if gate_status == "consented":
            return await handler(event, data)
        if gate_status != "needs_gate":
            return await handler(event, data)

        state_data = await state.get_data() if state else {}

        if state:
            update: dict[str, Any] = {CONSENT_GATE_SHOWN: True}
            if isinstance(event, Message) and event.text:
                update[CONSENT_PENDING_MESSAGE] = event.text
            await state.update_data(**update)

        await _send_consent_prompt(event, state_data)
        return None
