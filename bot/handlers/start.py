from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_user_with_settings, has_user_consented, record_user_consent
from bot.database.models import ProfileStatus
from bot.keyboards.inline import (
    get_consent_keyboard,
    get_webapp_keyboard,
    get_miniapp_invite_keyboard,
)
from bot.keyboards.reply import hide_reply_keyboard, REMOVE_KEYBOARD
from bot.middleware.consent import CONSENT_GATE_SHOWN, EXISTING_USER_CONSENT_TEXT
from bot.services.consent_resume import resume_pending_menu_action
from bot.utils.bot_commands import CMD_RESTART, CMD_RULES

router = Router()

CONSENT_TEXT = (
    "Привет!\n"
    "Я сделал этого бота, чтобы ты мог найти себе друзей в доте 🎮\n\n"
    "Перед стартом:\n"
    "• подпишись на мой тгк — там новости и обновления\n"
    "• дай согласие на обработку и отображение данных анкеты "
    "другим игрокам для поиска тиммейтов\n\n"
    "Мой тгк: @flazenjxrf\n"
    "Мой ютуб: youtube.com/@flazenjxrf"
)

MINIAPP_INVITE_TEXT = (
    "Дальше удобнее в Mini App — там анкета, поиск напарников и мэтчи 🎮\n\n"
    "Открой приложение кнопкой ниже."
)

MINIAPP_INVITE_REGISTERED_TEXT = (
    "Спасибо! Можешь продолжать в Mini App или через команды в чате 👇"
)

RETURNING_USER_TEXT = "Привет! Рады снова видеть тебя в FeedEther 🎮"

RULES_TEXT = (
    "📌 <b>Правила бота</b>\n\n"
    "1. Запрещена реклама сторонних каналов, турниров, сервисов и любых внешних ресурсов\n\n"
    "2. Запрещены оскорбления, агрессия и травля\n\n"
    "3. Запрещен NSFW-контент\n\n"
    "4. Запрещены политические высказывания, провокации и разжигание ненависти\n\n"
    "5. За нарушение правил — бан без предупреждения\n\n"
    "6. Администратор оставляет за собой право блокировать пользователей, "
    "чьи действия противоречат духу проекта\n\n"
    "7. Все вопросы и апелляции — в личные сообщения тгк @flazenjxrf\n\n"
    "Спасибо, что делаешь комьюнити чище ❤️"
)


async def send_registration_prompt(message: Message):
    await message.answer(MINIAPP_INVITE_TEXT, reply_markup=get_miniapp_invite_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user_with_settings(message.from_user.id)

    if user and user.status != ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer(EXISTING_USER_CONSENT_TEXT, reply_markup=get_consent_keyboard())
            return
        await message.answer(
            RETURNING_USER_TEXT,
            reply_markup=REMOVE_KEYBOARD,
        )
        webapp_kb = get_webapp_keyboard()
        if webapp_kb:
            await message.answer("Можешь пользоваться ботом в чате или открыть Mini App 👇", reply_markup=webapp_kb)
        from bot.middleware.keyboard import mark_keyboard_cleared
        mark_keyboard_cleared(message.from_user.id)
        return

    if await has_user_consented(message.from_user.id):
        await send_registration_prompt(message)
        return

    await message.answer(CONSENT_TEXT, reply_markup=get_consent_keyboard())


@router.callback_query(F.data == "accept_consent")
async def accept_consent(callback: CallbackQuery, state: FSMContext):
    await record_user_consent(callback.from_user.id, callback.from_user.username)
    await state.update_data(**{CONSENT_GATE_SHOWN: False})

    # Исходное сообщение с согласием оставляем — только убираем кнопки
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("Спасибо!")

    user = await get_user_with_settings(callback.from_user.id)
    is_registered = user and user.status != ProfileStatus.INCOMPLETE

    if is_registered:
        webapp_kb = get_webapp_keyboard()
        await callback.message.answer(
            MINIAPP_INVITE_REGISTERED_TEXT,
            reply_markup=webapp_kb or REMOVE_KEYBOARD,
        )
        await resume_pending_menu_action(callback, state)
        await hide_reply_keyboard(callback.message)
        return

    await callback.message.answer(
        MINIAPP_INVITE_TEXT,
        reply_markup=get_miniapp_invite_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer("Сначала прими соглашение через /start")
            return
        await message.answer("Сначала заполни анкету через /start")
        return
    await hide_reply_keyboard(message)


@router.message(Command(CMD_RULES))
async def show_rules(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(RULES_TEXT)


@router.message(Command(CMD_RESTART))
async def cmd_restart(message: Message):
    await hide_reply_keyboard(
        message,
        "Готово, меню перезапущено ✅\n"
        "Если снизу оставались старые кнопки, они скрыты.\n"
        "Пользуйся командами кнопку меню",
    )
