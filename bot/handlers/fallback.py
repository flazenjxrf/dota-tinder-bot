from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_user_with_settings
from bot.database.models import ProfileStatus
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import MENU_HINT

router = Router()


@router.message(F.text)
async def restore_menu_on_unknown_text(message: Message, state: FSMContext):
    """Подсказывает про меню команд, если пользователь написал текст вне сценария."""
    if await state.get_state():
        return

    if message.text and message.text.startswith("/"):
        return

    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        return

    await message.answer(MENU_HINT, reply_markup=REMOVE_KEYBOARD)
