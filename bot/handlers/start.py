from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

# Импортируем запросы к БД, статусы и клавиатуры
from bot.database.requests import get_user_with_settings
from bot.database.models import ProfileStatus
from bot.keyboards.inline import get_start_keyboard
from bot.keyboards.reply import get_main_menu_keyboard

# Объявляем роутер, который искал Python
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Проверяем, зарегистрирован ли уже пользователь
    user = await get_user_with_settings(message.from_user.id)

    if user and user.status != ProfileStatus.INCOMPLETE:
        # Если юзер уже есть в системе, просто даем ему главное меню
        await message.answer(
            "Привет! С возвращением в Dota Tinder!",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Если юзер новый — запускаем стандартное приветствие и кнопку регистрации
    text = (
        "Привет!\n"
        "Я сделал этого бота, чтобы ты мог найти себе друзей в доте 🎮\n\n"
        "Мой тгк: @flazenjxrf\n"
        "Мой ютуб: youtube.com/@flazenjxrf"
    )
    await message.answer(text, reply_markup=get_start_keyboard())