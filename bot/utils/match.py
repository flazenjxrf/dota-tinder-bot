from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.database.models import User

POSITIONS_MAPPING = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт",
}


def get_user_link(user_id: int, name: str, username: str | None) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def format_match_profile_caption(user: User) -> str:
    pos_names = [POSITIONS_MAPPING[p] for p in sorted(user.positions)]
    pos_str = ", ".join(pos_names)
    return (
        f"👤 <b>Анкета напарника:</b>\n\n"
        f"🌟 <b>{user.name}</b>, {user.age} | 📍 {user.city}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {user.mmr}\n\n"
        f"💬 О себе:\n{user.bio}"
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
):
    """Отправляет текст о мэтче и анкету напарника."""
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎉 <b>Взаимная симпатия!</b>\n\n"
            f"{intro_text}\n"
            f"Свяжись с {partner_link} и соберите пати! 🎮"
        ),
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
