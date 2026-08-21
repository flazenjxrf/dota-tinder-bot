"""Пуш-уведомления из Mini App через Bot API (мэтчи, лайки)."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot

from bot.database.models import User
from bot.database.requests import get_pending_likes_ids, get_user_with_settings
from bot.utils.match import get_user_link, send_match_notification

logger = logging.getLogger(__name__)

LIKE_NOTIFY_THRESHOLDS = {1, 5, 20}


def _crossed_threshold(old_count: int, new_count: int) -> int | None:
    for threshold in sorted(LIKE_NOTIFY_THRESHOLDS):
        if old_count < threshold <= new_count:
            return threshold
    return None


async def notify_match(bot: Bot, from_user_id: int, to_user_id: int) -> None:
    me = await get_user_with_settings(from_user_id)
    partner = await get_user_with_settings(to_user_id)
    if not me or not partner:
        return

    me_link = get_user_link(me.telegram_id, me.name, me.username)
    partner_link = get_user_link(partner.telegram_id, partner.name, partner.username)

    try:
        await send_match_notification(
            bot,
            from_user_id,
            f"Вы с {partner_link} лайкнули друг друга!",
            partner,
            partner_link,
        )
    except Exception:
        logger.exception("Не удалось отправить мэтч уведомление %s", from_user_id)

    try:
        await send_match_notification(
            bot,
            to_user_id,
            f"Вы с {me_link} лайкнули друг друга!",
            me,
            me_link,
        )
    except Exception:
        logger.exception("Не удалось отправить мэтч уведомление %s", to_user_id)


async def notify_like_threshold(bot: Bot, to_user_id: int, from_user_id: int) -> None:
    pending_ids = await get_pending_likes_ids(to_user_id)
    if from_user_id not in pending_ids:
        return

    new_count = len(pending_ids)
    # Порог считаем как «только что появился этот лайк» → old = new - 1
    threshold = _crossed_threshold(new_count - 1, new_count)
    if threshold is None:
        return

    if new_count == 1:
        likes_text = "1 неотвеченный лайк"
    else:
        likes_text = f"{new_count} неотвеченных лайков"

    text = (
        f"🔔 <b>У тебя {likes_text}!</b>\n\n"
        f"Открой Mini App или /likes, чтобы посмотреть анкеты."
    )
    try:
        await bot.send_message(to_user_id, text)
    except Exception:
        logger.exception("Не удалось отправить уведомление о лайках %s", to_user_id)


async def notify_like_with_message(
    bot: Bot,
    to_user_id: int,
    sender: User,
    message_text: str,
) -> None:
    text = (
        f"💌 <b>{escape(sender.name)}</b> отправил(а) тебе лайк с сообщением:\n\n"
        f"<i>«{escape(message_text)}»</i>\n\n"
        f"Открой Mini App или /likes, чтобы ответить."
    )
    try:
        await bot.send_message(to_user_id, text)
    except Exception:
        logger.exception("Не удалось отправить лайк с сообщением %s", to_user_id)
