from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_user_with_settings
from bot.database.models import ProfileStatus
from bot.keyboards.reply import get_main_menu_keyboard

router = Router()

KNOWN_MENU_BUTTONS = {
    "🔍 Смотреть анкеты",
    "👤 Моя анкета",
    "❤️ Мои лайки",
    "💚 Мои мэтчи",
}


@router.message(F.text)
async def restore_menu_on_unknown_text(message: Message, state: FSMContext):
    """Возвращает меню, если пользователь написал текст вне сценария."""
    if await state.get_state():
        return

    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        return

    if message.text in KNOWN_MENU_BUTTONS:
        return

    await message.answer(
        "Используй кнопки меню внизу 👇",
        reply_markup=get_main_menu_keyboard(),
    )
