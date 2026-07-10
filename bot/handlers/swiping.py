from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from html import escape

from bot.database.requests import (
    get_next_profile,
    add_swipe,
    undo_swipe,
    get_user_with_settings,
    get_pending_likes_ids,
    get_like_messages_remaining_today,
    DAILY_LIKE_MESSAGE_LIMIT,
    LIKE_MESSAGE_MAX_LENGTH,
)
from bot.database.models import ActionType, ProfileStatus, User
from bot.keyboards.inline import (
    get_swipe_keyboard,
    SwipeCallback,
    UndoSwipeCallback,
    LikeWithMessageCallback,
    LikeMessageCancelCallback,
    get_like_message_cancel_keyboard,
)
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import CMD_BROWSE
from bot.utils.profile_display import send_profile_card
from bot.utils.city import format_city_display
from bot.utils.match import get_user_link, send_match_notification_via_message, send_match_notification
from bot.states.fsm import SwipingForm
from bot.handlers.banned import reject_banned_message, reject_banned_callback

router = Router()

positions_mapping = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт"
}

HIDDEN_PROFILE_MSG = (
    "🔴 <b>Твоя анкета скрыта.</b>\n\n"
    "Чтобы смотреть чужие анкеты, включи её: 👤 Моя анкета → Показать анкету."
)

LIKE_NOTIFY_THRESHOLDS = {1, 5, 20}
UNDO_PROFILE_KEY = "undo_profile_id"


async def get_undo_profile_id(state: FSMContext) -> int | None:
    return (await state.get_data()).get(UNDO_PROFILE_KEY)


async def set_undo_profile(state: FSMContext, profile_id: int | None) -> None:
    await state.update_data(**{UNDO_PROFILE_KEY: profile_id})


async def clear_like_message_state(state: FSMContext) -> None:
    """Сбрасывает ввод лайка с сообщением, сохраняя возможность вернуться после дизлайка."""
    data = await state.get_data()
    undo_profile_id = data.get(UNDO_PROFILE_KEY)
    await state.set_state(None)
    await state.update_data(like_message_to_user_id=None, **{UNDO_PROFILE_KEY: undo_profile_id})


def format_pending_likes_notification(count: int) -> str:
    if count == 1:
        likes_text = "1 неотвеченный лайк"
    else:
        likes_text = f"{count} неотвеченных лайков"
    return (
        f"🔔 <b>У тебя {likes_text}!</b>\n\n"
        f"Загляни в /likes, чтобы посмотреть анкеты."
    )


def _crossed_like_notify_threshold(old_count: int, new_count: int) -> int | None:
    """Возвращает порог (1, 5 или 20), если количество лайков его только что пересекло."""
    for threshold in sorted(LIKE_NOTIFY_THRESHOLDS):
        if old_count < threshold <= new_count:
            return threshold
    return None


def build_browse_caption(profile: User) -> str:
    pos_names = [positions_mapping[p] for p in sorted(profile.positions)]
    pos_str = ", ".join(pos_names)
    return (
        f"🎮 <b>Напарник найден:</b>\n\n"
        f"🌟 <b>{profile.name}</b>, {profile.age} | {format_city_display(profile)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {profile.mmr}\n\n"
        f"💬 О себе:\n{profile.bio}"
    )


def format_like_with_message_notification(sender_name: str, message_text: str) -> str:
    return (
        f"💌 <b>{sender_name}</b> отправил(а) тебе лайк с сообщением:\n\n"
        f"<i>«{escape(message_text)}»</i>\n\n"
        f"Загляни в /likes, чтобы ответить."
    )


async def _notify_pending_likes_threshold(
    bot,
    to_user_id: int,
    from_user_id: int,
) -> None:
    """Уведомляет только при пересечении порога 1, 5 или 20 неотвеченных лайков."""
    pending_ids = await get_pending_likes_ids(to_user_id)
    if from_user_id not in pending_ids:
        return

    new_count = len(pending_ids)
    threshold = _crossed_like_notify_threshold(new_count - 1, new_count)
    if not threshold:
        return

    try:
        await bot.send_message(
            chat_id=to_user_id,
            text=format_pending_likes_notification(threshold),
        )
    except Exception:
        pass


async def process_like_notifications(
    bot,
    viewer_message: Message,
    from_user_id: int,
    to_user_id: int,
    is_match: bool,
    from_username: str | None = None,
    like_message: str | None = None,
):
    """Уведомления после лайка: мэтч, пороги неотвеченных лайков или лайк с сообщением."""
    if is_match:
        me = await get_user_with_settings(from_user_id)
        other = await get_user_with_settings(to_user_id)

        my_link = get_user_link(from_user_id, me.name, from_username)
        other_link = get_user_link(to_user_id, other.name, other.username)

        await send_match_notification_via_message(
            viewer_message,
            f"Ты понравился игроку {other_link} в ответ!",
            other,
            other_link,
        )

        try:
            await send_match_notification(
                bot,
                to_user_id,
                f"Игрок {my_link} ответил тебе взаимностью!",
                me,
                my_link,
            )
        except Exception:
            pass
    elif like_message:
        me = await get_user_with_settings(from_user_id)
        try:
            await bot.send_message(
                chat_id=to_user_id,
                text=format_like_with_message_notification(me.name, like_message),
            )
        except Exception:
            pass
    else:
        await _notify_pending_likes_threshold(bot, to_user_id, from_user_id)


async def show_browse_profile(
    message_or_callback,
    profile: User,
    can_undo: bool = False,
    viewer: User | None = None,
):
    remaining = DAILY_LIKE_MESSAGE_LIMIT
    if viewer:
        remaining = await get_like_messages_remaining_today(viewer.telegram_id)

    await send_profile_card(
        message_or_callback,
        profile.photo_file_id,
        build_browse_caption(profile),
        get_swipe_keyboard(
            profile.telegram_id,
            can_undo=can_undo,
            like_messages_remaining=remaining,
        ),
    )


async def show_next_profile(message_or_callback, user_id: int, state: FSMContext | None = None):
    """Ищет следующую анкету и показывает её. Если анкет нет — выводит сообщение."""
    next_user = await get_next_profile(user_id)

    if not next_user:
        text = "🎯 <b>Подходящие анкеты закончились!</b>\n\nПопробуй расширить фильтры поиска в меню 👤 Моя анкета -> Фильтры поиска."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text, reply_markup=REMOVE_KEYBOARD)
        else:
            await message_or_callback.answer(text, reply_markup=REMOVE_KEYBOARD)
        return

    can_undo = False
    viewer = None
    if state:
        can_undo = (await get_undo_profile_id(state)) is not None
    viewer = await get_user_with_settings(user_id)

    await show_browse_profile(message_or_callback, next_user, can_undo=can_undo, viewer=viewer)


# ================= КНОПКА "СМОТРЕТЬ АНКЕТЫ" В ГЛАВНОМ МЕНЮ =================
@router.message(Command(CMD_BROWSE))
async def start_swiping(message: Message, state: FSMContext):
    if await reject_banned_message(message):
        return

    await state.clear()

    # Сначала проверяем, есть ли у самого юзера анкета
    user = await get_user_with_settings(message.from_user.id)
    if not user:
        await message.answer("Сначала заполни свою анкету!")
        return

    if user.status == ProfileStatus.HIDDEN:
        await message.answer(HIDDEN_PROFILE_MSG, reply_markup=REMOVE_KEYBOARD)
        return

    await show_next_profile(message, message.from_user.id, state=state)


# ================= ОБРАБОТКА ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(SwipeCallback.filter())
async def process_swipe(callback: CallbackQuery, callback_data: SwipeCallback, state: FSMContext):
    if await reject_banned_callback(callback):
        return

    from_user_id = callback.from_user.id
    user = await get_user_with_settings(from_user_id)
    if not user or user.status == ProfileStatus.HIDDEN:
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True
        )
        return

    to_user_id = callback_data.to_user_id
    action = ActionType.LIKE if callback_data.action == "like" else ActionType.DISLIKE

    # 1. Записываем свайп в БД
    is_match = await add_swipe(from_user_id, to_user_id, action)

    await process_like_notifications(
        callback.bot,
        callback.message,
        from_user_id,
        to_user_id,
        is_match,
        from_username=callback.from_user.username,
    )

    if action == ActionType.DISLIKE:
        await set_undo_profile(state, to_user_id)
    else:
        await set_undo_profile(state, None)
    await callback.answer()

    # 3. Автоматически показываем следующего человека
    await show_next_profile(callback, from_user_id, state=state)


# ================= ВОЗВРАТ К ПРЕДЫДУЩЕЙ АНКЕТЕ =================
@router.callback_query(UndoSwipeCallback.filter())
async def undo_last_swipe(callback: CallbackQuery, state: FSMContext):
    if await reject_banned_callback(callback):
        return

    from_user_id = callback.from_user.id
    user = await get_user_with_settings(from_user_id)
    if not user or user.status == ProfileStatus.HIDDEN:
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True,
        )
        return

    undo_profile_id = await get_undo_profile_id(state)
    if not undo_profile_id:
        await callback.answer("Нет анкеты для возврата.", show_alert=True)
        return

    if not await undo_swipe(from_user_id, undo_profile_id):
        await set_undo_profile(state, None)
        await callback.answer("Не удалось вернуть анкету.", show_alert=True)
        return

    await set_undo_profile(state, None)

    profile = await get_user_with_settings(undo_profile_id)
    if not profile or profile.status != ProfileStatus.ACTIVE:
        await callback.answer("Анкета больше недоступна.", show_alert=True)
        await show_next_profile(callback, from_user_id, state=state)
        return

    viewer = await get_user_with_settings(from_user_id)
    await callback.answer("Вернули предыдущую анкету")
    await show_browse_profile(callback, profile, can_undo=False, viewer=viewer)


# ================= ЛАЙК С СООБЩЕНИЕМ =================
@router.callback_query(LikeWithMessageCallback.filter())
async def start_like_with_message(
    callback: CallbackQuery,
    callback_data: LikeWithMessageCallback,
    state: FSMContext,
):
    if await reject_banned_callback(callback):
        return

    from_user_id = callback.from_user.id
    user = await get_user_with_settings(from_user_id)
    if not user or user.status == ProfileStatus.HIDDEN:
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True,
        )
        return

    remaining = await get_like_messages_remaining_today(from_user_id)
    if remaining <= 0:
        await callback.answer(
            f"Лимит исчерпан ({DAILY_LIKE_MESSAGE_LIMIT} в сутки). Попробуй завтра!",
            show_alert=True,
        )
        return

    await state.set_state(SwipingForm.like_message)
    await state.update_data(like_message_to_user_id=callback_data.to_user_id)
    await callback.answer()
    await callback.message.answer(
        f"✍️ Напиши сообщение для этого игрока "
        f"(до {LIKE_MESSAGE_MAX_LENGTH} символов, осталось сегодня: {remaining}):",
        reply_markup=get_like_message_cancel_keyboard(callback_data.to_user_id),
    )


@router.callback_query(LikeMessageCancelCallback.filter())
async def cancel_like_with_message(
    callback: CallbackQuery,
    callback_data: LikeMessageCancelCallback,
    state: FSMContext,
):
    if await reject_banned_callback(callback):
        return

    data = await state.get_data()
    can_undo = data.get(UNDO_PROFILE_KEY) is not None
    await clear_like_message_state(state)
    await callback.answer("Отменено")

    profile = await get_user_with_settings(callback_data.to_user_id)
    if not profile:
        return

    viewer = await get_user_with_settings(callback.from_user.id)
    await show_browse_profile(callback, profile, can_undo=can_undo, viewer=viewer)


@router.message(SwipingForm.like_message, F.text)
async def finish_like_with_message(message: Message, state: FSMContext):
    if await reject_banned_message(message):
        return

    from_user_id = message.from_user.id
    data = await state.get_data()
    to_user_id = data.get("like_message_to_user_id")
    if not to_user_id:
        await state.clear()
        return

    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Напиши текст или нажми «Отмена».")
        return
    if len(text) > LIKE_MESSAGE_MAX_LENGTH:
        await message.answer(
            f"Слишком длинное сообщение. Максимум {LIKE_MESSAGE_MAX_LENGTH} символов "
            f"(у тебя {len(text)})."
        )
        return

    remaining = await get_like_messages_remaining_today(from_user_id)
    if remaining <= 0:
        await state.clear()
        await message.answer(
            f"Лимит лайков с сообщением на сегодня исчерпан ({DAILY_LIKE_MESSAGE_LIMIT} в сутки).",
            reply_markup=REMOVE_KEYBOARD,
        )
        return

    is_match = await add_swipe(from_user_id, to_user_id, ActionType.LIKE, message=text)
    await set_undo_profile(state, None)
    await clear_like_message_state(state)

    await process_like_notifications(
        message.bot,
        message,
        from_user_id,
        to_user_id,
        is_match,
        from_username=message.from_user.username,
        like_message=text,
    )

    new_remaining = await get_like_messages_remaining_today(from_user_id)
    await message.answer(
        f"💌 Лайк с сообщением отправлен! Осталось сегодня: {new_remaining}",
        reply_markup=REMOVE_KEYBOARD,
    )
    await show_next_profile(message, from_user_id, state=state)


@router.message(SwipingForm.like_message)
async def finish_like_with_message_invalid(message: Message):
    await message.answer(
        "Отправь текстовое сообщение или нажми «Отмена» под предыдущим сообщением."
    )
