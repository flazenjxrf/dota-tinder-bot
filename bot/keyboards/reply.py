from aiogram.types import ReplyKeyboardRemove, Message

REMOVE_KEYBOARD = ReplyKeyboardRemove()


async def hide_reply_keyboard(message: Message, text: str | None = None) -> None:
    """Убирает старую reply-клавиатуру."""
    from bot.middleware.keyboard import mark_keyboard_cleared

    mark_keyboard_cleared(message.from_user.id)
    if text:
        await message.answer(text, reply_markup=REMOVE_KEYBOARD)
    else:
        sent = await message.answer("\u200b", reply_markup=REMOVE_KEYBOARD)
        try:
            await message.bot.delete_message(message.chat.id, sent.message_id)
        except Exception:
            pass
