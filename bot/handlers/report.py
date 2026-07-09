from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import add_report, add_swipe, get_user_with_settings
from bot.database.models import ActionType, ProfileStatus, ReportReason
from bot.keyboards.inline import (
    ReportCallback,
    ReportReasonCallback,
    get_report_reasons_keyboard,
    REPORT_REASON_LABELS,
)

router = Router()

HIDDEN_PROFILE_MSG = (
    "🔴 <b>Твоя анкета скрыта.</b>\n\n"
    "Чтобы смотреть чужие анкеты, включи её: 👤 Моя анкета → Показать анкету."
)


@router.callback_query(ReportCallback.filter())
async def start_report(callback: CallbackQuery, callback_data: ReportCallback):
    if callback_data.context == "swipe":
        user = await get_user_with_settings(callback.from_user.id)
        if not user or user.status == ProfileStatus.HIDDEN:
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
async def cancel_report(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()


@router.callback_query(ReportReasonCallback.filter())
async def submit_report(callback: CallbackQuery, callback_data: ReportReasonCallback, state: FSMContext):
    from_user_id = callback.from_user.id
    to_user_id = callback_data.to_user_id

    if callback_data.context == "swipe":
        user = await get_user_with_settings(from_user_id)
        if not user or user.status == ProfileStatus.HIDDEN:
            await callback.answer(
                "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
                show_alert=True,
            )
            return

    reason = ReportReason(callback_data.reason)
    created = await add_report(from_user_id, to_user_id, reason)

    await callback.message.delete()

    if created:
        await add_swipe(from_user_id, to_user_id, ActionType.DISLIKE)
        reason_label = REPORT_REASON_LABELS[callback_data.reason]
        await callback.message.answer(
            f"✅ <b>Жалоба отправлена.</b>\n\n"
            f"Причина: {reason_label}\n"
            f"Мы рассмотрим её в ближайшее время."
        )
    else:
        await callback.message.answer(
            "ℹ️ Ты уже жаловался на этого пользователя. Жалоба учтена ранее."
        )

    await callback.answer()

    if callback_data.context == "swipe":
        from bot.handlers.swiping import show_next_profile
        await state.update_data(undo_profile_id=None)
        await show_next_profile(callback, from_user_id, state=state)
    else:
        from bot.handlers.likes import show_pending_like_at_index
        await show_pending_like_at_index(callback, from_user_id, callback_data.index)
