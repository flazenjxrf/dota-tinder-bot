from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_user_with_settings, has_user_consented, record_user_consent
from bot.database.models import ProfileStatus
from bot.keyboards.inline import (
    get_consent_keyboard,
    get_webapp_keyboard,
)
from bot.keyboards.reply import hide_reply_keyboard, REMOVE_KEYBOARD
from bot.middleware.consent import CONSENT_GATE_SHOWN, CONSENT_TEXT
from bot.services.consent_resume import resume_pending_menu_action
from bot.utils.bot_commands import CMD_RESTART, CMD_RULES

router = Router()

MINIAPP_TEXT = "📱 Mini App"

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


async def send_miniapp_prompt(message: Message):
    kb = get_webapp_keyboard()
    if kb:
        await message.answer(MINIAPP_TEXT, reply_markup=kb)
    else:
        await message.answer(MINIAPP_TEXT)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user_with_settings(message.from_user.id)

    if user and user.status != ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer(CONSENT_TEXT, reply_markup=get_consent_keyboard())
            return
        kb = get_webapp_keyboard()
        await message.answer(MINIAPP_TEXT, reply_markup=kb or REMOVE_KEYBOARD)
        from bot.middleware.keyboard import mark_keyboard_cleared
        mark_keyboard_cleared(message.from_user.id)
        return

    if await has_user_consented(message.from_user.id):
        await send_miniapp_prompt(message)
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
        await send_miniapp_prompt(callback.message)
        await resume_pending_menu_action(callback, state)
        await hide_reply_keyboard(callback.message)
        return

    await send_miniapp_prompt(callback.message)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        if not await has_user_consented(message.from_user.id):
            await message.answer("Сначала прими соглашение через /start")
            return
        await send_miniapp_prompt(message)
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
