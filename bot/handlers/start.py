from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_user_with_settings, has_user_consented, record_user_consent
from bot.database.models import ProfileStatus
from bot.keyboards.inline import get_consent_keyboard, get_start_keyboard
from bot.keyboards.reply import get_main_menu_keyboard, refresh_main_menu
from bot.middleware.consent import CONSENT_GATE_SHOWN, EXISTING_USER_CONSENT_TEXT
from bot.services.consent_resume import resume_pending_menu_action

router = Router()

CONSENT_TEXT = (
    "Привет!\n"
    "Я сделал этого бота, чтобы ты мог найти себе друзей в доте 🎮\n\n"
    "Продолжая пользоваться ботом, ты соглашаешься на обработку и отображение информации "
    "из своей анкеты другим пользователям для поиска игроков.\n\n"
    "Мой тгк: @flazenjxrf\n"
    "Мой ютуб: youtube.com/@flazenjxrf"
)

AFTER_CONSENT_TEXT = (
    "Отлично! Теперь заполни анкету — так другие игроки смогут тебя найти 🎮"
)


async def send_registration_prompt(message: Message):
    await message.answer(AFTER_CONSENT_TEXT, reply_markup=get_start_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user_with_settings(message.from_user.id)

    if user and user.status != ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer(EXISTING_USER_CONSENT_TEXT, reply_markup=get_consent_keyboard())
            return
        await message.answer(
            "Привет! С возвращением в Dota Tinder!",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if await has_user_consented(message.from_user.id):
        await send_registration_prompt(message)
        return

    await message.answer(CONSENT_TEXT, reply_markup=get_consent_keyboard())


@router.callback_query(F.data == "accept_consent")
async def accept_consent(callback: CallbackQuery, state: FSMContext):
    await record_user_consent(callback.from_user.id, callback.from_user.username)
    await state.update_data(**{CONSENT_GATE_SHOWN: False})

    user = await get_user_with_settings(callback.from_user.id)
    is_registered = user and user.status != ProfileStatus.INCOMPLETE

    if is_registered:
        await callback.message.edit_text("✅ Спасибо! Можешь продолжать пользоваться ботом.")
        await callback.answer()
        await resume_pending_menu_action(callback, state)
        await refresh_main_menu(callback.message)
        return

    await callback.message.edit_text(AFTER_CONSENT_TEXT, reply_markup=get_start_keyboard())
    await callback.answer()


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer("Сначала прими соглашение через /start")
            return
        await message.answer("Сначала заполни анкету через /start")
        return
    await refresh_main_menu(message, "Главное меню 👇")
