from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.requests import add_report, add_swipe, get_user_with_settings
from bot.database.models import ActionType, ProfileStatus, ReportReason
from bot.keyboards.inline import (
    ReportCallback,
    ReportReasonCallback,
    ReportSkipCommentCallback,
    get_report_reasons_keyboard,
    get_report_comment_keyboard,
    REPORT_REASON_LABELS,
)
from bot.states.fsm import ReportForm

router = Router()

REPORT_COMMENT_MAX_LENGTH = 500

HIDDEN_PROFILE_MSG = (
    "🔴 <b>Твоя анкета скрыта.</b>\n\n"
    "Чтобы смотреть чужие анкеты, включи её: 👤 Моя анкета → Показать анкету."
)


async def _check_hidden_profile(user_id: int, context: str) -> bool:
    if context != "swipe":
        return True
    user = await get_user_with_settings(user_id)
    return bool(user and user.status != ProfileStatus.HIDDEN)


async def _continue_after_report(
    message_or_callback: Message | CallbackQuery,
    from_user_id: int,
    context: str,
    index: int,
    state: FSMContext,
    report_id: int | None,
    to_user_id: int,
):
    if context == "swipe":
        from bot.handlers.swiping import show_next_profile, set_undo_profile
        if report_id:
            await set_undo_profile(state, to_user_id)
        await show_next_profile(message_or_callback, from_user_id, state=state)
    else:
        from bot.handlers.likes import show_pending_like_at_index
        await show_pending_like_at_index(message_or_callback, from_user_id, index)


async def _finalize_report(
    message_or_callback: Message | CallbackQuery,
    state: FSMContext,
    from_user_id: int,
    comment: str | None,
):
    data = await state.get_data()
    to_user_id = data.get("report_to_user_id")
    context = data.get("report_context", "swipe")
    index = data.get("report_index", 0)
    reason_key = data.get("report_reason")

    await state.clear()

    if not to_user_id or not reason_key:
        return

    if not await _check_hidden_profile(from_user_id, context):
        target = (
            message_or_callback.message
            if isinstance(message_or_callback, CallbackQuery)
            else message_or_callback
        )
        await target.answer(HIDDEN_PROFILE_MSG)
        return

    reason = ReportReason(reason_key)
    report_id = await add_report(from_user_id, to_user_id, reason, comment=comment)

    target = (
        message_or_callback.message
        if isinstance(message_or_callback, CallbackQuery)
        else message_or_callback
    )

    if report_id:
        await add_swipe(from_user_id, to_user_id, ActionType.DISLIKE)
        reason_label = REPORT_REASON_LABELS[reason_key]
        text = (
            f"✅ <b>Жалоба отправлена.</b>\n\n"
            f"Причина: {reason_label}"
        )
        if comment:
            text += f"\nКомментарий: <i>{escape(comment)}</i>"
        text += "\nМы рассмотрим её в ближайшее время."
        await target.answer(text)

        from bot.handlers.admin import notify_admins_new_report
        await notify_admins_new_report(
            target.bot,
            report_id,
            from_user_id,
            to_user_id,
            reason_key,
            comment,
        )
    else:
        await target.answer(
            "ℹ️ Ты уже жаловался на этого пользователя. Жалоба учтена ранее."
        )

    await _continue_after_report(
        target, from_user_id, context, index, state, report_id, to_user_id,
    )


@router.callback_query(ReportCallback.filter())
async def start_report(callback: CallbackQuery, callback_data: ReportCallback):
    if not await _check_hidden_profile(callback.from_user.id, callback_data.context):
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True,
        )
        return

    await callback.message.answer(
        "🚨 <b>Подача жалобы</b>\n\nВыбери причину:",
        reply_markup=get_report_reasons_keyboard(
            callback_data.to_user_id,
            callback_data.context,
            callback_data.index,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "report_cancel")
async def cancel_report(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer()


@router.callback_query(ReportReasonCallback.filter())
async def ask_report_comment(
    callback: CallbackQuery,
    callback_data: ReportReasonCallback,
    state: FSMContext,
):
    if not await _check_hidden_profile(callback.from_user.id, callback_data.context):
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True,
        )
        return

    await state.set_state(ReportForm.comment)
    await state.update_data(
        report_to_user_id=callback_data.to_user_id,
        report_context=callback_data.context,
        report_index=callback_data.index,
        report_reason=callback_data.reason,
    )

    await callback.message.delete()
    await callback.message.answer(
        "✍️ <b>Комментарий к жалобе</b>\n\n"
        f"Причина: {REPORT_REASON_LABELS[callback_data.reason]}\n\n"
        f"Можешь описать нарушение подробнее (до {REPORT_COMMENT_MAX_LENGTH} символов) "
        "или пропустить этот шаг.",
        reply_markup=get_report_comment_keyboard(),
    )
    await callback.answer()


@router.callback_query(ReportSkipCommentCallback.filter())
async def skip_report_comment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _finalize_report(callback, state, callback.from_user.id, comment=None)


@router.message(ReportForm.comment, F.text)
async def submit_report_comment(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Комментарий не может быть пустым. Напиши текст или нажми «Пропустить».")
        return
    if len(text) > REPORT_COMMENT_MAX_LENGTH:
        await message.answer(
            f"Слишком длинный комментарий. Максимум {REPORT_COMMENT_MAX_LENGTH} символов "
            f"(у тебя {len(text)})."
        )
        return

    await _finalize_report(message, state, message.from_user.id, comment=text)
