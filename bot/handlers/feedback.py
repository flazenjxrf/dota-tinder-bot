from html import escape

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import add_bug_feedback, get_user_with_settings
from bot.database.models import ProfileStatus
from bot.keyboards.inline import get_feedback_cancel_keyboard
from bot.states.fsm import FeedbackForm
from bot.utils.bot_commands import CMD_FEEDBACK

router = Router()

FEEDBACK_MAX_LENGTH = 1000

FEEDBACK_PROMPT = (
    "🐛 <b>Сообщить о баге</b>\n\n"
    "Опиши, что пошло не так: что делал, что ожидал и что произошло.\n"
    f"Максимум {FEEDBACK_MAX_LENGTH} символов."
)


async def _require_registered_user(message: Message) -> bool:
    user = await get_user_with_settings(message.from_user.id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        await message.answer("Сначала заполни анкету через /start")
        return False
    return True


@router.message(Command(CMD_FEEDBACK))
async def start_feedback(message: Message, state: FSMContext):
    if not await _require_registered_user(message):
        return

    await state.set_state(FeedbackForm.text)
    await message.answer(FEEDBACK_PROMPT, reply_markup=get_feedback_cancel_keyboard())


@router.callback_query(F.data == "feedback_cancel")
async def cancel_feedback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Отправка отменена.")
    await callback.answer()


@router.message(FeedbackForm.text, F.text)
async def submit_feedback(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Опиши баг или нажми «Отмена».")
        return
    if len(text) > FEEDBACK_MAX_LENGTH:
        await message.answer(
            f"Слишком длинное сообщение. Максимум {FEEDBACK_MAX_LENGTH} символов "
            f"(у тебя {len(text)})."
        )
        return

    await state.clear()
    feedback_id = await add_bug_feedback(message.from_user.id, text)

    await message.answer(
        "✅ <b>Спасибо за обратную связь!</b>\n\n"
        "Мы получили твоё сообщение и постараемся разобраться."
    )

    from bot.handlers.admin import notify_admins_new_feedback
    await notify_admins_new_feedback(message.bot, feedback_id, message.from_user.id, text)
