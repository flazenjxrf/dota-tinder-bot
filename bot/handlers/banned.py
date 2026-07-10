from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import (
    is_user_banned,
    get_user_with_settings,
    add_unban_request,
    has_pending_unban_request,
)
from bot.database.models import ProfileStatus
from bot.keyboards.inline import get_unban_request_cancel_keyboard, get_banned_profile_menu_keyboard
from bot.states.fsm import UnbanRequestForm

router = Router()

UNBAN_REQUEST_MAX_LENGTH = 1000

BAN_MENU_TEXT = (
    "🚫 <b>Твой аккаунт заблокирован</b> за нарушение правил.\n\n"
    "Ты можешь отредактировать анкету или подать запрос на разбан.\n"
    "Используй /profile или кнопки ниже."
)

UNBAN_REQUEST_PROMPT = (
    "📝 <b>Запрос на разбан</b>\n\n"
    "Опиши, почему считаешь, что блокировка была ошибочной, "
    "или что ты готов соблюдать правила.\n"
    f"Максимум {UNBAN_REQUEST_MAX_LENGTH} символов."
)


async def send_banned_user_menu(message: Message) -> None:
    from bot.handlers.profile import send_my_profile_message

    user = await get_user_with_settings(message.from_user.id)
    if user and user.status != ProfileStatus.INCOMPLETE:
        await send_my_profile_message(message, message.from_user.id)
        return

    has_pending = await has_pending_unban_request(message.from_user.id)
    await message.answer(
        BAN_MENU_TEXT,
        reply_markup=get_banned_profile_menu_keyboard(has_pending),
    )


async def reject_banned_message(message: Message) -> bool:
    """Возвращает True, если пользователь забанен и действие нужно прервать."""
    if await is_user_banned(message.from_user.id):
        await send_banned_user_menu(message)
        return True
    return False


async def reject_banned_callback(callback: CallbackQuery) -> bool:
    """Возвращает True, если пользователь забанен и действие нужно прервать."""
    if await is_user_banned(callback.from_user.id):
        await callback.answer("Аккаунт заблокирован.", show_alert=True)
        return True
    return False


@router.callback_query(F.data == "banned_unban_pending")
async def banned_unban_pending(callback: CallbackQuery):
    await callback.answer("Твой запрос уже на рассмотрении. Ожидай ответа.", show_alert=True)


@router.callback_query(F.data == "banned_request_unban")
async def start_unban_request(callback: CallbackQuery, state: FSMContext):
    if not await is_user_banned(callback.from_user.id):
        await callback.answer()
        return

    if await has_pending_unban_request(callback.from_user.id):
        await callback.answer("У тебя уже есть запрос на рассмотрении.", show_alert=True)
        return

    await state.set_state(UnbanRequestForm.message)
    await callback.message.answer(
        UNBAN_REQUEST_PROMPT,
        reply_markup=get_unban_request_cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "unban_request_cancel")
async def cancel_unban_request(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Запрос на разбан отменён.")
    await callback.answer()


@router.message(UnbanRequestForm.message, F.text)
async def submit_unban_request(message: Message, state: FSMContext):
    if not await is_user_banned(message.from_user.id):
        await state.clear()
        return

    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Напиши текст или нажми «Отмена».")
        return
    if len(text) > UNBAN_REQUEST_MAX_LENGTH:
        await message.answer(
            f"Слишком длинное сообщение. Максимум {UNBAN_REQUEST_MAX_LENGTH} символов "
            f"(у тебя {len(text)})."
        )
        return

    await state.clear()
    request_id = await add_unban_request(message.from_user.id, text)

    if request_id:
        await message.answer(
            "✅ <b>Запрос на разбан отправлен.</b>\n\n"
            "Мы рассмотрим его в ближайшее время."
        )
        from bot.handlers.admin import notify_admins_new_unban_request
        await notify_admins_new_unban_request(
            message.bot, request_id, message.from_user.id, text,
        )
    else:
        await message.answer(
            "ℹ️ У тебя уже есть запрос на рассмотрении. Дождись ответа."
        )
