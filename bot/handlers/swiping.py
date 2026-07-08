from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_next_profile, add_swipe, get_user_with_settings, get_pending_likes_count
from bot.database.models import ActionType, ProfileStatus
from bot.keyboards.inline import get_swipe_keyboard, SwipeCallback
from bot.keyboards.reply import get_main_menu_keyboard
from bot.utils.profile_display import send_profile_card
from bot.utils.match import get_user_link, send_match_notification_via_message, send_match_notification

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


def format_pending_likes_notification(count: int) -> str:
    if count == 1:
        likes_text = "1 неотвеченный лайк"
    else:
        likes_text = f"{count} неотвеченных лайков"
    return (
        f"🔔 <b>У тебя {likes_text}!</b>\n\n"
        f"Загляни во вкладку <b>❤️ Мои лайки</b>, чтобы посмотреть анкеты."
    )


async def show_next_profile(message_or_callback, user_id: int):
    """Ищет следующую анкету и показывает её. Если анкет нет — выводит сообщение."""
    next_user = await get_next_profile(user_id)

    if not next_user:
        text = "🎯 <b>Подходящие анкеты закончились!</b>\n\nПопробуй расширить фильтры поиска в меню 👤 Моя анкета -> Фильтры поиска."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text, reply_markup=get_main_menu_keyboard())
        else:
            await message_or_callback.answer(text, reply_markup=get_main_menu_keyboard())
        return

    # Красиво форматируем анкету напарника
    pos_names = [positions_mapping[p] for p in sorted(next_user.positions)]
    pos_str = ", ".join(pos_names)
    caption = (
        f"🎮 <b>Напарник найден:</b>\n\n"
        f"🌟 <b>{next_user.name}</b>, {next_user.age} | 📍 {next_user.city}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {next_user.mmr}\n\n"
        f"💬 О себе:\n{next_user.bio}"
    )

    await send_profile_card(
        message_or_callback,
        next_user.photo_file_id,
        caption,
        get_swipe_keyboard(next_user.telegram_id),
    )


# ================= КНОПКА "СМОТРЕТЬ АНКЕТЫ" В ГЛАВНОМ МЕНЮ =================
@router.message(F.text == "🔍 Смотреть анкеты")
async def start_swiping(message: Message, state: FSMContext):
    await state.clear()

    # Сначала проверяем, есть ли у самого юзера анкета
    user = await get_user_with_settings(message.from_user.id)
    if not user:
        await message.answer("Сначала заполни свою анкету!")
        return

    if user.status == ProfileStatus.HIDDEN:
        await message.answer(HIDDEN_PROFILE_MSG, reply_markup=get_main_menu_keyboard())
        return

    await show_next_profile(message, message.from_user.id)


# ================= ОБРАБОТКА ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(SwipeCallback.filter())
async def process_swipe(callback: CallbackQuery, callback_data: SwipeCallback):
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

    # 2. Если взаимный лайк — отправляем уведомления
    if is_match:
        me = await get_user_with_settings(from_user_id)
        other = await get_user_with_settings(to_user_id)

        my_link = get_user_link(from_user_id, me.name, callback.from_user.username)
        other_link = get_user_link(to_user_id, other.name, other.username)

        await send_match_notification_via_message(
            callback.message,
            f"Ты понравился игроку {other_link} в ответ!",
            other,
            other_link,
        )

        try:
            await send_match_notification(
                callback.bot,
                to_user_id,
                f"Игрок {my_link} ответил тебе взаимностью!",
                me,
                my_link,
            )
        except Exception:
            pass

    # Одиночный лайк -> уведомление только при 1, 5 и 20 неотвеченных лайках
    elif action == ActionType.LIKE:
        pending_count = await get_pending_likes_count(to_user_id)
        if pending_count in LIKE_NOTIFY_THRESHOLDS:
            try:
                await callback.bot.send_message(
                    chat_id=to_user_id,
                    text=format_pending_likes_notification(pending_count),
                )
            except Exception:
                pass

    await callback.answer()

    # 3. Автоматически показываем следующего человека
    await show_next_profile(callback, from_user_id)