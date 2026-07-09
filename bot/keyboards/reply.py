from aiogram.types import ReplyKeyboardRemove, Message

REMOVE_KEYBOARD = ReplyKeyboardRemove()


async def hide_reply_keyboard(message: Message, text: str | None = None) -> None:
    """Убирает старую reply-клавиатуру и подсказывает про меню команд."""
    from bot.middleware.keyboard import mark_keyboard_cleared
    from bot.utils.bot_commands import MENU_HINT

    mark_keyboard_cleared(message.from_user.id)
    await message.answer(text or MENU_HINT, reply_markup=REMOVE_KEYBOARD)
