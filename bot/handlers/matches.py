from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.requests import (
    get_match_at_index,
    get_teammate_rating,
    add_teammate_rating,
    get_reputation_counts,
)
from bot.keyboards.inline import get_match_keyboard, MatchNavCallback, MatchRateCallback
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import CMD_MATCHES
from bot.utils.profile_display import send_profile_card
from bot.utils.city import format_city_display
from bot.utils.match import CONTACT_PRIVACY_NOTE, get_user_link
from bot.utils.reputation import (
    format_reputation_line_from_counts,
    AURA_EMOJI,
    VIBE_EMOJI,
    AURA_LABEL,
    VIBE_LABEL,
)
from bot.handlers.banned import reject_banned_message, reject_banned_callback

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
            "Открой Mini App."
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
    aura_count, vibe_count = await get_reputation_counts(partner.telegram_id)
    reputation = format_reputation_line_from_counts(aura_count, vibe_count)
    has_aura, has_vibe = await get_teammate_rating(user_id, partner.telegram_id)
    caption = (
        f"💚 <b>Мэтч</b> ({actual_index + 1}/{total}):\n\n"
        f"🌟 {contact}, {partner.age} | {format_city_display(partner)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {partner.mmr}{reputation}\n\n"
        f"💬 О себе: {partner.bio}\n\n"
        f"📩 Написать: {contact}\n"
        f"{CONTACT_PRIVACY_NOTE}\n\n"
        f"<i>После игры можешь оценить тиммейта 👇</i>"
    )

    keyboard = get_match_keyboard(
        actual_index,
        total,
        partner.telegram_id,
        has_aura=has_aura,
        has_vibe=has_vibe,
    )
    await send_profile_card(
        message_or_callback,
        partner.photo_file_id,
        caption,
        keyboard,
    )


@router.message(Command(CMD_MATCHES))
async def start_viewing_matches(message: Message, state: FSMContext):
    if await reject_banned_message(message):
        return

    await state.clear()
    await show_match_at_index(message, message.from_user.id, index=0)


@router.callback_query(MatchNavCallback.filter())
async def navigate_matches(callback: CallbackQuery, callback_data: MatchNavCallback):
    if await reject_banned_callback(callback):
        return

    await show_match_at_index(callback, callback.from_user.id, callback_data.index)
    await callback.answer()


@router.callback_query(MatchRateCallback.filter())
async def rate_match_partner(callback: CallbackQuery, callback_data: MatchRateCallback):
    if await reject_banned_callback(callback):
        return

    aura = callback_data.action == "aura"
    vibe = callback_data.action == "vibe"
    if not aura and not vibe:
        await callback.answer()
        return

    error = await add_teammate_rating(
        callback.from_user.id,
        callback_data.partner_id,
        aura=aura,
        vibe=vibe,
    )
    if error:
        await callback.answer(error, show_alert=True)
        return

    label = f"{AURA_EMOJI} {AURA_LABEL}" if aura else f"{VIBE_EMOJI} {VIBE_LABEL}"
    await callback.answer(f"{label} поставлена!")
    await show_match_at_index(callback, callback.from_user.id, callback_data.index)


@router.callback_query(F.data == "matches_counter")
async def matches_counter_noop(callback: CallbackQuery):
    await callback.answer()
