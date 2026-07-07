from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_next_profile, add_swipe, get_user_with_settings
from bot.database.models import ActionType
from bot.keyboards.inline import get_swipe_keyboard, SwipeCallback

router = Router()

positions_mapping = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт"
}


def get_user_link(user_id: int, name: str, username: str | None) -> str:
    """Возвращает кликабельное имя пользователя (через @ или ссылку на ID)"""
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


async def show_next_profile(message_or_callback, user_id: int):
    """Ищет следующую анкету и показывает её. Если анкет нет — выводит сообщение."""
    next_user = await get_next_profile(user_id)

    if not next_user:
        text = "🎯 <b>Подходящие анкеты закончились!</b>\n\nПопробуй расширить фильтры поиска в меню 👤 Моя анкета -> Фильтры поиска."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text)
        else:
            await message_or_callback.answer(text)
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

    if isinstance(message_or_callback, CallbackQuery):
        # Бесшовно меняем фото и текст на новые прямо в том же сообщении!
        media = InputMediaPhoto(media=next_user.photo_file_id, caption=caption, parse_mode="HTML")
        await message_or_callback.message.edit_media(
            media=media,
            reply_markup=get_swipe_keyboard(next_user.telegram_id)
        )
    else:
        # Отправляем новую карточку
        await message_or_callback.answer_photo(
            photo=next_user.photo_file_id,
            caption=caption,
            reply_markup=get_swipe_keyboard(next_user.telegram_id)
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

    await show_next_profile(message, message.from_user.id)


# ================= ОБРАБОТКА ЛАЙКА / ДИЗЛАЙКА =================
@router.callback_query(SwipeCallback.filter())
async def process_swipe(callback: CallbackQuery, callback_data: SwipeCallback):
    from_user_id = callback.from_user.id
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

        await callback.message.answer(
            f"🎉 <b>Взаимная симпатия!</b>\n\n"
            f"Ты понравился игроку {other_link} в ответ!\n"
            f"Свяжись с ним и сыграйте катку! 🎮"
        )

        try:
            await callback.bot.send_message(
                chat_id=to_user_id,
                text=(
                    f"🎉 <b>Взаимная симпатия!</b>\n\n"
                    f"Игрок {my_link} ответил тебе взаимностью!\n"
                    f"Напиши ему и соберите пати! 🎮"
                )
            )
        except Exception:
            pass

    # --- НОВОЕ: Одиночный лайк -> Уведомление напарнику ---
    elif action == ActionType.LIKE:
        try:
            await callback.bot.send_message(
                chat_id=to_user_id,
                text="🔔 <b>У вас новый лайк!</b>\n\nКто-то заинтересовался твоим профилем. Загляни во вкладку <b>❤️ Мои лайки</b>, чтобы узнать кто это!"
            )
        except Exception:
            pass

    await callback.answer()

    # 3. Автоматически показываем следующего человека
    await show_next_profile(callback, from_user_id)