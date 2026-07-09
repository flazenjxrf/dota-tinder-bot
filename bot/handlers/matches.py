from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import get_match_at_index
from bot.keyboards.inline import get_match_keyboard, MatchNavCallback
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import CMD_MATCHES
from bot.utils.profile_display import send_profile_card
from bot.utils.city import format_city_display
from bot.utils.match import get_user_link

router = Router()

POSITIONS_MAPPING = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт",
}


async def show_match_at_index(message_or_callback, user_id: int, index: int = 0):
    """Показывает мэтч по индексу в списке."""
    partner, total = await get_match_at_index(user_id, index)

    if not partner:
        text = (
            "💚 <b>У тебя пока нет мэтчей.</b>\n\n"
            "Лайкай анкеты через /browse или отвечай на входящие через /likes!"
        )
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.delete()
            await message_or_callback.message.answer(text, reply_markup=REMOVE_KEYBOARD)
        else:
            await message_or_callback.answer(text, reply_markup=REMOVE_KEYBOARD)
        return

    actual_index = min(max(index, 0), total - 1)
    pos_names = [POSITIONS_MAPPING[p] for p in sorted(partner.positions)]
    pos_str = ", ".join(pos_names)
    contact = get_user_link(partner.telegram_id, partner.name, partner.username)
    caption = (
        f"💚 <b>Мэтч</b> ({actual_index + 1}/{total}):\n\n"
        f"🌟 <b>{partner.name}</b>, {partner.age} | {format_city_display(partner)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {partner.mmr}\n\n"
        f"💬 О себе:\n{partner.bio}\n\n"
        f"📩 Написать: {contact}"
    )

    keyboard = get_match_keyboard(actual_index, total) if total > 1 else None
    await send_profile_card(
        message_or_callback,
        partner.photo_file_id,
        caption,
        keyboard,
    )


@router.message(Command(CMD_MATCHES))
async def start_viewing_matches(message: Message, state: FSMContext):
    await state.clear()
    await show_match_at_index(message, message.from_user.id, index=0)


@router.callback_query(MatchNavCallback.filter())
async def navigate_matches(callback: CallbackQuery, callback_data: MatchNavCallback):
    await show_match_at_index(callback, callback.from_user.id, callback_data.index)
    await callback.answer()


@router.callback_query(F.data == "matches_counter")
async def matches_counter_noop(callback: CallbackQuery):
    await callback.answer()
