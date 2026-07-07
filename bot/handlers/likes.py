from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_next_pending_like, add_swipe, get_user_with_settings
from bot.database.models import ActionType
from bot.keyboards.inline import get_likeback_keyboard, LikeBackCallback

router = Router()

positions_mapping = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт"
}


def get_user_link(user_id: int, name: str, username: str | None) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


async def show_next_pending_like_profile(message_or_callback, user_id: int):
    """Показывает следующего человека, который лайкнул нашего юзера"""
    next_user = await get_next_pending_like(user_id)

    if not next_user:
        text = "🎯 <b>Все входящие лайки просмотрены!</b>\n\nПока новых лайков нет. Но ты можешь поискать напарников во вкладке 🔍 Смотреть анкеты."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text)
        else:
            await message_or_callback.answer(text)
        return

    pos_names = [positions_mapping[p] for p in sorted(next_user.positions)]
    pos_str = ", ".join(pos_names)
    caption = (
        f"🔥 <b>Ты понравился этому игроку:</b>\n\n"
        f"🌟 <b>{next_user.name}</b>, {next_user.age} | 📍 {next_user.city}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {next_user.mmr}\n\n"
        f"💬 О себе:\n{next_user.bio}"
    )

    if isinstance(message_or_callback, CallbackQuery):
        media = InputMediaPhoto(media=next_user.photo_file_id, caption=caption, parse_mode="HTML")
        await message_or_callback.message.edit_media(
            media=media,
            reply_markup=get_likeback_keyboard(next_user.telegram_id)
        )
    else:
        await message_or_callback.answer_photo(
            photo=next_user.photo_file_id,
            caption=caption,
            reply_markup=get_likeback_keyboard(next_user.telegram_id)
        )


# ================= КНОПКА "МОИ ЛАЙКИ" В ГЛАВНОМ МЕНЮ =================
@router.message(F.text == "❤️ Мои лайки")
async def start_viewing_likes(message: Message, state: FSMContext):
    await state.clear()
    await show_next_pending_like_profile(message, message.from_user.id)


# ================= ОБРАБОТКА ВЗАИМНОГО ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(LikeBackCallback.filter())
async def process_likeback(callback: CallbackQuery, callback_data: LikeBackCallback):
    from_user_id = callback.from_user.id
    to_user_id = callback_data.from_user_id  # Тот, кто лайкнул нас изначально
    action = ActionType.LIKE if callback_data.action == "like" else ActionType.DISLIKE

    # 1. Записываем наш ответный свайп
    is_match = await add_swipe(from_user_id, to_user_id, action)

    # 2. Если взаимно (всегда True при выборе Like в ответ)
    if is_match and action == ActionType.LIKE:
        me = await get_user_with_settings(from_user_id)
        other = await get_user_with_settings(to_user_id)

        my_link = get_user_link(from_user_id, me.name, callback.from_user.username)
        other_link = get_user_link(to_user_id, other.name, other.username)

        await callback.message.answer(
            f"🎉 <b>Взаимная симпатия!</b>\n\n"
            f"Ты ответил взаимностью игроку {other_link}!\n"
            f"Свяжитесь и тащите катки! 🎮"
        )

        try:
            await callback.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"🎉 <b>Взаимная симпатия!</b>\n\n"
                    f"Игрок {my_link} ответил тебе взаимностью в 'Моих лайках'!\n"
                    f"Напиши ему прямо сейчас! 🎮"
                )
            )
        except Exception:
            pass

    await callback.answer()

    # Показываем следующий входящий лайк
    await show_next_pending_like_profile(callback, from_user_id)