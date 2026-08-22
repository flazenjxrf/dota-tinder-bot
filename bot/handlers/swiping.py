from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from contextlib import suppress

from bot.database.requests import (
    get_next_profile,
    add_swipe,
    undo_swipe,
    get_user_with_settings,
    get_like_messages_remaining_today,
    get_reputation_counts,
    is_game_searching,
    DAILY_LIKE_MESSAGE_LIMIT,
    LIKE_MESSAGE_MAX_LENGTH,
)
from bot.database.models import ActionType, User
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
from bot.utils.reputation import format_reputation_line_from_counts
from bot.webapp.notifications import process_swipe_notifications
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


def build_browse_caption(profile: User, reputation: str = "") -> str:
    game_profile = profile.display_profile()
    pos_names = game_profile.role_labels() if game_profile else [positions_mapping[p] for p in sorted(profile.positions) if p in positions_mapping]
    rating = " · ".join(game_profile.ratings_display()) if game_profile else f"MMR: {profile.mmr}"
    pos_str = ", ".join(pos_names)
    return (
        f"🎮 <b>Напарник найден:</b>\n\n"
        f"🌟 <b>{profile.name}</b>, {profile.age} | {format_city_display(profile)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 {rating}{reputation}\n\n"
        f"💬 : {profile.bio}"
    )


async def show_browse_profile(
    message_or_callback,
    profile: User,
    can_undo: bool = False,
    viewer: User | None = None,
):
    remaining = DAILY_LIKE_MESSAGE_LIMIT
    if viewer:
        remaining = await get_like_messages_remaining_today(viewer.telegram_id)

    aura_count, vibe_count = await get_reputation_counts(profile.telegram_id)
    reputation = format_reputation_line_from_counts(aura_count, vibe_count)
    await send_profile_card(
        message_or_callback,
        profile.photo_file_id,
        build_browse_caption(profile, reputation),
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
            # Старое сообщение может быть уже недоступно для удаления (например, при повторном тапе).
            # В таком случае все равно отправляем уведомление о конце свайпов.
            with suppress(Exception):
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

    await _start_swiping_flow(message, message.from_user.id, state)


@router.callback_query(F.data == "start_browse")
async def start_swiping_from_button(callback: CallbackQuery, state: FSMContext):
    if await reject_banned_callback(callback):
        return

    await _start_swiping_flow(callback.message, callback.from_user.id, state)
    await callback.answer()


async def _start_swiping_flow(message: Message, user_id: int, state: FSMContext):
    await state.clear()

    # Сначала проверяем, есть ли у самого юзера анкета
    user = await get_user_with_settings(user_id)
    if not user:
        await message.answer("Сначала заполни свою анкету!")
        return

    if not is_game_searching(user):
        await message.answer(HIDDEN_PROFILE_MSG, reply_markup=REMOVE_KEYBOARD)
        return

    await show_next_profile(message, user_id, state=state)


# ================= ОБРАБОТКА ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(SwipeCallback.filter())
async def process_swipe(callback: CallbackQuery, callback_data: SwipeCallback, state: FSMContext):
    if await reject_banned_callback(callback):
        return

    from_user_id = callback.from_user.id
    user = await get_user_with_settings(from_user_id)
    if not user or not is_game_searching(user):
        await callback.answer(
            "Твоя анкета скрыта. Включи её, чтобы смотреть анкеты.",
            show_alert=True
        )
        return

    to_user_id = callback_data.to_user_id
    action = ActionType.LIKE if callback_data.action == "like" else ActionType.DISLIKE

    # 1. Записываем свайп в БД
    is_match = await add_swipe(from_user_id, to_user_id, action)

    await process_swipe_notifications(
        callback.bot,
        from_user_id,
        to_user_id,
        is_match=is_match,
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
    if not user or not is_game_searching(user):
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
    if not profile or not is_game_searching(profile):
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
    if not user or not is_game_searching(user):
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

    await process_swipe_notifications(
        message.bot,
        from_user_id,
        to_user_id,
        is_match=is_match,
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
