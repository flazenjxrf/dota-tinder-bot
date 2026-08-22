"""REST API для Telegram Mini App."""
from __future__ import annotations

import logging

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from bot.config import BOT_TOKEN
from bot.database.models import ActionType, ProfileStatus, ReportReason
from bot.database.requests import (
    DAILY_LIKE_MESSAGE_LIMIT,
    LIKE_MESSAGE_MAX_LENGTH,
    add_bug_feedback,
    add_report,
    add_swipe,
    add_teammate_rating,
    delete_user_profile,
    get_like_messages_remaining_today,
    get_match_at_index,
    get_pending_like_at_index,
    get_pending_likes_count,
    get_reputation_counts,
    get_teammate_rating,
    get_user_with_settings,
    has_user_consented,
    is_user_banned,
    record_user_consent,
    save_user_and_settings,
    undo_swipe,
    update_settings_field,
    update_user_field,
    get_next_profile,
)
from bot.webapp.deps import CurrentBot, CurrentUser, WebAppUser
from bot.webapp.notifications import notify_like_threshold, notify_like_with_message, notify_match
from bot.webapp.schemas import (
    FeedbackBody,
    ProfileUpdateBody,
    RateBody,
    RegisterBody,
    ReportBody,
    SettingsUpdateBody,
    StatusUpdateBody,
    SwipeBody,
    UndoBody,
)
from bot.webapp.serializers import photo_url, serialize_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _require_active_user(user_id: int):
    if await is_user_banned(user_id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    if not await has_user_consented(user_id):
        raise HTTPException(status_code=403, detail="Нужно принять согласие")
    user = await get_user_with_settings(user_id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        raise HTTPException(status_code=400, detail="Сначала заполни анкету")
    return user


@router.get("/me")
async def get_me(user: WebAppUser = CurrentUser):
    banned = await is_user_banned(user.id)
    consented = await has_user_consented(user.id)
    profile = await get_user_with_settings(user.id)
    registered = bool(profile and profile.status != ProfileStatus.INCOMPLETE)

    payload = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "banned": banned,
        "consented": consented,
        "registered": registered,
        "needs_consent": not consented,
        "needs_registration": consented and not registered,
        "pending_likes": 0,
        "profile": None,
    }

    if banned:
        return payload

    if registered and profile:
        aura, vibe = await get_reputation_counts(user.id)
        payload["profile"] = serialize_profile(
            profile,
            aura=aura,
            vibe=vibe,
            include_settings=True,
        )
        payload["pending_likes"] = await get_pending_likes_count(user.id)
        payload["like_messages_remaining"] = await get_like_messages_remaining_today(user.id)
        payload["like_message_limit"] = DAILY_LIKE_MESSAGE_LIMIT
        payload["like_message_max_length"] = LIKE_MESSAGE_MAX_LENGTH

    return payload


@router.post("/consent")
async def accept_consent(user: WebAppUser = CurrentUser):
    if await is_user_banned(user.id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    await record_user_consent(user.id, user.username)
    return {"ok": True}


@router.get("/browse/next")
async def browse_next(user: WebAppUser = CurrentUser):
    me = await _require_active_user(user.id)
    if me.status == ProfileStatus.HIDDEN:
        raise HTTPException(
            status_code=400,
            detail="Анкета скрыта. Покажи её в профиле, чтобы смотреть других.",
        )

    profile = await get_next_profile(user.id)
    if not profile:
        return {"profile": None, "undo_available": False}

    aura, vibe = await get_reputation_counts(profile.telegram_id)
    return {
        "profile": serialize_profile(profile, aura=aura, vibe=vibe),
        "like_messages_remaining": await get_like_messages_remaining_today(user.id),
    }


@router.post("/swipe")
async def swipe(
    body: SwipeBody,
    user: WebAppUser = CurrentUser,
    bot: Bot = CurrentBot,
):
    me = await _require_active_user(user.id)
    if me.status == ProfileStatus.HIDDEN:
        raise HTTPException(status_code=400, detail="Анкета скрыта")

    if body.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя свайпнуть себя")

    target = await get_user_with_settings(body.to_user_id)
    if not target or target.status != ProfileStatus.ACTIVE:
        raise HTTPException(status_code=404, detail="Анкета недоступна")

    message = (body.message or "").strip() or None
    if message:
        if body.action != "like":
            raise HTTPException(status_code=400, detail="Сообщение только с лайком")
        if len(message) > LIKE_MESSAGE_MAX_LENGTH:
            raise HTTPException(status_code=400, detail="Сообщение слишком длинное")
        remaining = await get_like_messages_remaining_today(user.id)
        if remaining <= 0:
            raise HTTPException(status_code=400, detail="Лимит лайков с сообщением на сегодня исчерпан")

    action = ActionType.LIKE if body.action == "like" else ActionType.DISLIKE
    is_match = await add_swipe(user.id, body.to_user_id, action, message)

    if action == ActionType.LIKE and not is_match:
        if message:
            await notify_like_with_message(bot, body.to_user_id, me, message)
        else:
            await notify_like_threshold(bot, body.to_user_id, user.id)
    elif is_match:
        await notify_match(bot, user.id, body.to_user_id)

    return {
        "ok": True,
        "is_match": is_match,
        "match_profile": serialize_profile(target, contact=True) if is_match else None,
    }


@router.post("/swipe/undo")
async def swipe_undo(body: UndoBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    ok = await undo_swipe(user.id, body.to_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Нечего отменять")
    return {"ok": True}


@router.get("/likes")
async def get_likes(index: int = 0, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    liker, total, like_message = await get_pending_like_at_index(user.id, index)
    if not liker:
        return {"profile": None, "total": 0, "index": 0, "message": None}

    actual = min(max(index, 0), total - 1)
    aura, vibe = await get_reputation_counts(liker.telegram_id)
    return {
        "profile": serialize_profile(liker, aura=aura, vibe=vibe),
        "total": total,
        "index": actual,
        "message": like_message,
    }


@router.get("/matches")
async def get_matches(index: int = 0, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    partner, total = await get_match_at_index(user.id, index)
    if not partner:
        return {"profile": None, "total": 0, "index": 0, "rating": None}

    actual = min(max(index, 0), total - 1)
    aura, vibe = await get_reputation_counts(partner.telegram_id)
    has_aura, has_vibe = await get_teammate_rating(user.id, partner.telegram_id)
    return {
        "profile": serialize_profile(partner, aura=aura, vibe=vibe, contact=True),
        "total": total,
        "index": actual,
        "rating": {"has_aura": has_aura, "has_vibe": has_vibe},
    }


@router.post("/matches/rate")
async def rate_match(body: RateBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    error = await add_teammate_rating(
        user.id,
        body.to_user_id,
        aura=body.kind == "aura",
        vibe=body.kind == "vibe",
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    has_aura, has_vibe = await get_teammate_rating(user.id, body.to_user_id)
    return {"ok": True, "rating": {"has_aura": has_aura, "has_vibe": has_vibe}}


@router.post("/report")
async def report_user(body: ReportBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    reason = ReportReason(body.reason)
    report_id = await add_report(user.id, body.to_user_id, reason, body.comment)
    await add_swipe(user.id, body.to_user_id, ActionType.DISLIKE)
    if report_id is None:
        return {"ok": True, "duplicate": True}
    return {"ok": True, "id": report_id}


@router.post("/feedback")
async def feedback(body: FeedbackBody, user: WebAppUser = CurrentUser):
    if await is_user_banned(user.id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    feedback_id = await add_bug_feedback(user.id, body.text.strip())
    return {"ok": True, "id": feedback_id}


@router.patch("/profile")
async def update_profile(body: ProfileUpdateBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    data = body.model_dump(exclude_unset=True)
    if "positions" in data and data["positions"] is not None:
        positions = [p for p in data["positions"] if p in (1, 2, 3, 4)]
        if not positions:
            raise HTTPException(status_code=400, detail="Выбери хотя бы одну роль")
        data["positions"] = positions

    for field, value in data.items():
        await update_user_field(user.id, field, value)

    profile = await get_user_with_settings(user.id)
    aura, vibe = await get_reputation_counts(user.id)
    return serialize_profile(profile, aura=aura, vibe=vibe, include_settings=True)


@router.patch("/profile/settings")
async def update_settings(body: SettingsUpdateBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    data = body.model_dump(exclude_unset=True)
    if "wanted_positions" in data and data["wanted_positions"] is not None:
        data["wanted_positions"] = [p for p in data["wanted_positions"] if p in (1, 2, 3, 4)] or None

    for field, value in data.items():
        await update_settings_field(user.id, field, value)

    profile = await get_user_with_settings(user.id)
    aura, vibe = await get_reputation_counts(user.id)
    return serialize_profile(profile, aura=aura, vibe=vibe, include_settings=True)


@router.post("/profile/status")
async def set_profile_status(body: StatusUpdateBody, user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    new_status = ProfileStatus.ACTIVE if body.status == "active" else ProfileStatus.HIDDEN
    await update_user_field(user.id, "status", new_status)
    return {"ok": True, "status": new_status.value}


@router.delete("/profile")
async def remove_profile(user: WebAppUser = CurrentUser):
    await _require_active_user(user.id)
    ok = await delete_user_profile(user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Анкета не найдена")
    return {"ok": True}


@router.post("/register")
async def register(body: RegisterBody, user: WebAppUser = CurrentUser):
    if await is_user_banned(user.id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    if not await has_user_consented(user.id):
        raise HTTPException(status_code=403, detail="Нужно принять согласие")

    positions = [p for p in body.positions if p in (1, 2, 3, 4)]
    if not positions:
        raise HTTPException(status_code=400, detail="Выбери хотя бы одну роль")

    wanted = [p for p in (body.wanted_positions or []) if p in (1, 2, 3, 4)]

    await save_user_and_settings(
        user.id,
        user.username,
        {
            "name": body.name.strip(),
            "age": body.age,
            "city": body.city.strip(),
            "mmr": body.mmr,
            "positions": positions,
            "bio": (body.bio or "").strip(),
            "photo_id": body.photo_file_id,
            "wanted_positions": wanted,
            "min_age": body.min_age,
            "max_age": body.max_age,
            "min_mmr": body.min_mmr,
            "max_mmr": body.max_mmr,
        },
    )
    profile = await get_user_with_settings(user.id)
    return serialize_profile(profile, include_settings=True)


@router.post("/photos/upload")
async def upload_photo(
    user: WebAppUser = CurrentUser,
    bot: Bot = CurrentBot,
    file: UploadFile = File(...),
):
    if await is_user_banned(user.id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    if not await has_user_consented(user.id):
        raise HTTPException(status_code=403, detail="Нужно принять согласие")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл больше 10 МБ")

    filename = file.filename or "photo.jpg"
    try:
        message = await bot.send_photo(
            chat_id=user.id,
            photo=BufferedInputFile(content, filename=filename),
            caption="📷 Фото для анкеты загружено в FeedEther",
        )
    except Exception as exc:
        logger.exception("upload_photo failed for %s", user.id)
        raise HTTPException(
            status_code=400,
            detail="Не удалось загрузить фото. Открой Mini App через бота.",
        ) from exc

    if not message.photo:
        raise HTTPException(status_code=500, detail="Telegram не вернул photo")

    file_id = message.photo[-1].file_id
    return {
        "photo_file_id": file_id,
        "photo_url": photo_url(file_id),
    }


@router.get("/photos/{file_id:path}")
async def proxy_photo(file_id: str):
    """Проксирует фото из Telegram Bot API по file_id."""
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен")

    async with httpx.AsyncClient(timeout=30.0) as client:
        meta = await client.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": file_id},
        )
        data = meta.json()
        if not data.get("ok"):
            raise HTTPException(status_code=404, detail="Фото недоступно")

        file_path = data["result"]["file_path"]
        image = await client.get(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        )
        if image.status_code != 200:
            raise HTTPException(status_code=404, detail="Фото недоступно")

    content_type = image.headers.get("content-type", "image/jpeg")
    return Response(
        content=image.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/rules")
async def rules():
    return {
        "text": (
            "1. Запрещена реклама сторонних каналов, турниров, сервисов\n"
            "2. Запрещены оскорбления, агрессия и травля\n"
            "3. Запрещен NSFW-контент\n"
            "4. Запрещены политические высказывания и разжигание ненависти\n"
            "5. За нарушение — бан без предупреждения\n"
            "6. Вопросы и апелляции — в тгк @flazenjxrf"
        )
    }
