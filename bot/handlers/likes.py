from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from html import escape

from bot.database.requests import get_pending_like_at_index, add_swipe, get_user_with_settings
from bot.database.models import ActionType
from bot.keyboards.inline import get_likeback_keyboard, LikeBackCallback, LikeNavCallback
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import CMD_LIKES
from bot.utils.profile_display import send_profile_card
from bot.utils.city import format_city_display
from bot.utils.match import get_user_link, send_match_notification_via_message, send_match_notification
from bot.handlers.banned import reject_banned_message, reject_banned_callback

router = Router()

positions_mapping = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт"
}


async def show_pending_like_at_index(message_or_callback, user_id: int, index: int = 0):
    """Показывает входящий лайк по индексу в списке."""
    next_user, total, like_message = await get_pending_like_at_index(user_id, index)

    if not next_user:
        text = (
            "🎯 <b>Все входящие лайки просмотрены!</b>\n\n"
            "Пока новых лайков нет. Поищи напарников через /browse."
        )
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text, reply_markup=REMOVE_KEYBOARD)
        else:
            await message_or_callback.answer(text, reply_markup=REMOVE_KEYBOARD)
        return

    actual_index = min(max(index, 0), total - 1)
    pos_names = [positions_mapping[p] for p in sorted(next_user.positions)]
    pos_str = ", ".join(pos_names)
    caption = (
        f"🔥 <b>Ты понравился этому игроку</b> ({actual_index + 1}/{total}):\n\n"
        f"🌟 <b>{next_user.name}</b>, {next_user.age} | {format_city_display(next_user)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {next_user.mmr}\n\n"
        f"💬 О себе:\n{next_user.bio}"
    )
    if like_message:
        caption += f"\n\n💌 <b>Сообщение к лайку:</b>\n<i>«{escape(like_message)}»</i>"

    await send_profile_card(
        message_or_callback,
        next_user.photo_file_id,
        caption,
        get_likeback_keyboard(next_user.telegram_id, actual_index, total),
    )


# ================= КНОПКА "МОИ ЛАЙКИ" В ГЛАВНОМ МЕНЮ =================
@router.message(Command(CMD_LIKES))
async def start_viewing_likes(message: Message, state: FSMContext):
    if await reject_banned_message(message):
        return

    await state.clear()
    await show_pending_like_at_index(message, message.from_user.id, index=0)


# ================= ЛИСТАНИЕ ЛАЙКОВ =================
@router.callback_query(LikeNavCallback.filter())
async def navigate_likes(callback: CallbackQuery, callback_data: LikeNavCallback):
    if await reject_banned_callback(callback):
        return

    await show_pending_like_at_index(callback, callback.from_user.id, callback_data.index)
    await callback.answer()


@router.callback_query(F.data == "likes_counter")
async def likes_counter_noop(callback: CallbackQuery):
    await callback.answer()


# ================= ОБРАБОТКА ВЗАИМНОГО ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(LikeBackCallback.filter())
async def process_likeback(callback: CallbackQuery, callback_data: LikeBackCallback):
    if await reject_banned_callback(callback):
        return

    from_user_id = callback.from_user.id
    to_user_id = callback_data.from_user_id
    action = ActionType.LIKE if callback_data.action == "like" else ActionType.DISLIKE

    is_match = await add_swipe(from_user_id, to_user_id, action)

    if is_match and action == ActionType.LIKE:
        me = await get_user_with_settings(from_user_id)
        other = await get_user_with_settings(to_user_id)

        my_link = get_user_link(from_user_id, me.name, callback.from_user.username)
        other_link = get_user_link(to_user_id, other.name, other.username)

        try:
            await send_match_notification_via_message(
                callback.message,
                f"Ты ответил взаимностью игроку {other_link}!",
                other,
                other_link,
            )
            await send_match_notification(
                callback.bot,
                to_user_id,
                f"Игрок {my_link} ответил тебе взаимностью в «Моих лайках»!",
                me,
                my_link,
            )
        except Exception:
            pass

    await callback.answer()
    await show_pending_like_at_index(callback, from_user_id, callback_data.index)
