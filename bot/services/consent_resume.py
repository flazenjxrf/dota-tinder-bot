import importlib
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.middleware.consent import CONSENT_PENDING_MESSAGE

_MENU_HANDLERS: dict[str, tuple[str, str]] = {
    "🔍 Смотреть анкеты": ("bot.handlers.swiping", "start_swiping"),
    "👤 Моя анкета": ("bot.handlers.profile", "show_my_profile"),
    "❤️ Мои лайки": ("bot.handlers.likes", "start_viewing_likes"),
    "💚 Мои мэтчи": ("bot.handlers.matches", "start_viewing_matches"),
}


class _MessageProxy:
    """Прокси Message для повторного вызова хендлера меню после согласия."""

    def __init__(self, callback: CallbackQuery, text: str):
        self._callback = callback
        self.from_user = callback.from_user
        self.text = text
        self.chat = callback.message.chat
        self.bot = callback.bot

    async def answer(self, *args, **kwargs):
        return await self._callback.message.answer(*args, **kwargs)

    async def answer_photo(self, *args, **kwargs):
        return await self._callback.message.answer_photo(*args, **kwargs)

    async def delete(self):
        return await self._callback.message.delete()


async def resume_pending_menu_action(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pending = data.pop(CONSENT_PENDING_MESSAGE, None)
    if pending:
        await state.set_data(data)

    if not pending or pending not in _MENU_HANDLERS:
        return

    module_name, func_name = _MENU_HANDLERS[pending]
    module = importlib.import_module(module_name)
    handler = getattr(module, func_name)
    proxy = _MessageProxy(callback, pending)
    await handler(proxy, state)
