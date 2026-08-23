from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from html import escape

from bot.database.models import User
from bot.games import game_label, role_labels

POSITIONS_MAPPING = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт",
}


def get_user_link(user_id: int, name: str, username: str | None) -> str:
    safe_name = escape(name)
    if username:
        return f'<a href="https://t.me/{username}">{safe_name}</a>'
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


CONTACT_PRIVACY_NOTE = (
    "<i>*Если написать не получается — у человека могут быть "
    "ограничены настройки приватности в Telegram.</i>"
)


def format_match_profile_caption(user: User) -> str:
    profile = user.display_profile()
    game = profile.game if profile else "dota"
    pos_str = ", ".join(role_labels(game, user.positions) or [POSITIONS_MAPPING[p] for p in sorted(user.positions) if p in POSITIONS_MAPPING])
    rating = " · ".join(profile.ratings_display()) if profile else f"MMR: {user.mmr}"
    name_link = get_user_link(user.telegram_id, user.name, user.username)
    roles_line = f"🎯 Роли: {pos_str}\n" if pos_str else ""
    return (
        f"👤 <b>Анкета напарника ({game_label(game)}):</b>\n\n"
        f"🌟 {name_link}, {user.age} | 📍 {user.city}\n"
        f"{roles_line}"
        f"🏆 {rating}\n\n"
        f"💬 О себе: {user.bio}\n\n"
        f"📩 Написать: {name_link}\n"
        f"{CONTACT_PRIVACY_NOTE}"
    )


def _is_invalid_photo_error(exc: TelegramBadRequest) -> bool:
    message = (exc.message or "").lower()
    return "wrong file identifier" in message or "http url specified" in message


async def _send_profile_to_chat(bot: Bot, chat_id: int, user: User):
    caption = format_match_profile_caption(user)
    try:
        await bot.send_photo(chat_id=chat_id, photo=user.photo_file_id, caption=caption)
    except TelegramBadRequest as exc:
        if not _is_invalid_photo_error(exc):
            raise
        await bot.send_message(
            chat_id=chat_id,
            text=f"{caption}\n\n⚠️ <i>Фото этой анкеты недоступно.</i>",
        )


async def send_match_notification(
    bot: Bot,
    chat_id: int,
    intro_text: str,
    partner: User,
    partner_link: str,
    reply_markup=None,
):
    """Отправляет текст о мэтче и анкету напарника."""
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎉 <b>Новый мэтч!</b>\n\n"
            f"{intro_text}\n"
            f"Нажми на имя, чтобы написать: {partner_link}\n"
            f"{CONTACT_PRIVACY_NOTE}\n\n"
            f"После игры можешь оставить +rep в мэтчах 🎮"
        ),
        reply_markup=reply_markup,
    )
    await _send_profile_to_chat(bot, chat_id, partner)


async def send_match_notification_via_message(
    message: Message,
    intro_text: str,
    partner: User,
    partner_link: str,
):
    """Отправляет текст о мэтче и анкету напарника через объект Message."""
    await send_match_notification(message.bot, message.chat.id, intro_text, partner, partner_link)
