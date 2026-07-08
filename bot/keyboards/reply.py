from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Смотреть анкеты")],
            [
                KeyboardButton(text="👤 Моя анкета"),
                KeyboardButton(text="❤️ Мои лайки"),
            ],
            [KeyboardButton(text="💚 Мои мэтчи")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


async def refresh_main_menu(message: Message, title: str | None = None):
    """Отправляет актуальную reply-клавиатуру (Telegram сам её не обновляет)."""
    await message.answer(
        title or "Меню обновлено 👇",
        reply_markup=get_main_menu_keyboard(),
    )