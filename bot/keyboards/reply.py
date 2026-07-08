from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

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
        resize_keyboard=True, # Кнопки будут аккуратными, а не на пол-экрана
        one_time_keyboard=False
    )