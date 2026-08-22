"""Telegram-уведомления пользователям о лайках и мэтчах."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot

from bot.database.models import User
from bot.database.requests import get_pending_likes_ids, get_user_with_settings
from bot.keyboards.inline import get_webapp_keyboard
from bot.utils.match import get_user_link, send_match_notification

logger = logging.getLogger(__name__)

LIKE_NOTIFY_THRESHOLDS = {1, 3, 7, 12, 20}


def _crossed_threshold(old_count: int, new_count: int) -> int | None:
    for threshold in sorted(LIKE_NOTIFY_THRESHOLDS):
        if old_count < threshold <= new_count:
            return threshold
    return None


def format_pending_likes_notification(count: int) -> str:
    if count == 1:
        likes_text = "1 неотвеченный лайк"
    else:
        likes_text = f"{count} неотвеченных лайков"
    return (
        f"🔔 <b>У тебя {likes_text}!</b>\n\n"
        f"Открой Mini App, чтобы посмотреть анкеты."
    )


def _miniapp_markup(tab: str | None = None):
    return get_webapp_keyboard(tab=tab)


async def notify_match(bot: Bot, from_user_id: int, to_user_id: int, game: str | None = None) -> None:
    me = await get_user_with_settings(from_user_id, game)
    partner = await get_user_with_settings(to_user_id, game)
    if not me or not partner:
        return

    me_link = get_user_link(me.telegram_id, me.name, me.username)
    partner_link = get_user_link(partner.telegram_id, partner.name, partner.username)

    matches_kb = _miniapp_markup("matches")

    try:
        await send_match_notification(
            bot,
            from_user_id,
            f"Вы с {partner_link} лайкнули друг друга!",
            partner,
            partner_link,
            reply_markup=matches_kb,
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
            reply_markup=matches_kb,
        )
    except Exception:
        logger.exception("Не удалось отправить мэтч уведомление %s", to_user_id)


async def notify_like_threshold(bot: Bot, to_user_id: int, from_user_id: int, game: str | None = None) -> None:
    pending_ids = await get_pending_likes_ids(to_user_id, game)
    if from_user_id not in pending_ids:
        return

    new_count = len(pending_ids)
    threshold = _crossed_threshold(new_count - 1, new_count)
    if threshold is None:
        return

    try:
        await bot.send_message(
            to_user_id,
            format_pending_likes_notification(threshold),
            reply_markup=_miniapp_markup("likes"),
        )
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
        f"Открой Mini App, чтобы ответить."
    )
    try:
        await bot.send_message(to_user_id, text, reply_markup=_miniapp_markup("likes"))
    except Exception:
        logger.exception("Не удалось отправить лайк с сообщением %s", to_user_id)


async def process_swipe_notifications(
    bot: Bot,
    from_user_id: int,
    to_user_id: int,
    *,
    is_match: bool,
    like_message: str | None = None,
    game: str | None = None,
) -> None:
    """Уведомления после свайпа: мэтч, порог лайков или лайк с сообщением."""
    if is_match:
        await notify_match(bot, from_user_id, to_user_id, game)
        return

    if like_message:
        sender = await get_user_with_settings(from_user_id, game)
        if sender:
            await notify_like_with_message(bot, to_user_id, sender, like_message)
        return

    await notify_like_threshold(bot, to_user_id, from_user_id, game)
