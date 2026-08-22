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
    copy_game_card,
    delete_game_profile,
    delete_user_profile,
    get_like_messages_remaining_today,
    get_match_at_index,
    get_pending_like_at_index,
    get_pending_likes_count,
    get_reputation_counts,
    get_teammate_rating,
    get_user_with_settings,
    has_user_consented,
    is_game_searching,
    is_person_registered,
    is_user_banned,
    record_user_consent,
    save_user_and_settings,
    undo_swipe,
    update_settings_field,
    update_user_field,
    get_next_profile,
)
from bot.games import (
    DEFAULT_GAME,
    catalog_payload,
    clamp_rating,
    is_known_game,
    known_game_ids,
    normalize_game,
    rating_kinds,
    rating_spec,
    valid_roles,
)
from bot.webapp.deps import CurrentBot, CurrentUser, WebAppUser
from bot.webapp.notifications import notify_like_threshold, notify_like_with_message, notify_match
from bot.utils.city import format_city_display
from bot.webapp.schemas import (
    CopyCardBody,
    FeedbackBody,
    GameSwitchBody,
    ProfileUpdateBody,
    RateBody,
    RegisterBody,
    ReportBody,
    SettingsUpdateBody,
    StatusUpdateBody,
    SwipeBody,
    UndoBody,
)
from bot.webapp.serializers import photo_url, serialize_me_extras, serialize_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _profile_complete(user, game: str) -> bool:
    if not user:
        return False
    profile = user.profile_for(game)
    return bool(profile and profile.is_complete())


def _best_game_for_user(user) -> str:
    """Игра для холодного старта: last_active, если анкета есть, иначе любая готовая."""
    if not user:
        return DEFAULT_GAME
    preferred = normalize_game(user.last_active_game)
    if _profile_complete(user, preferred):
        return preferred
    for game_id in known_game_ids():
        if _profile_complete(user, game_id):
            return game_id
    # Нет готовых анкет — дописываем черновик, не прыгаем на пустой cs2
    if user.profile_for(preferred):
        return preferred
    for game_id in known_game_ids():
        if user.profile_for(game_id):
            return game_id
    return preferred


async def _resolved_game(user_id: int, game: str | None, *, persist: bool = False) -> str:
    """Резолв текущей игры. persist=True только при явном переключении (POST /me/game)."""
    if game and not is_known_game(game):
        raise HTTPException(status_code=400, detail="Неизвестная игра")
    if game:
        resolved = normalize_game(game)
        if persist:
            await update_user_field(user_id, "last_active_game", resolved)
        return resolved

    person = await get_user_with_settings(user_id)
    resolved = _best_game_for_user(person)
    # Сбрасываем «залипший» last_active без анкеты (например cs2 после тапа на +)
    if person and normalize_game(person.last_active_game) != resolved:
        await update_user_field(user_id, "last_active_game", resolved)
    return resolved


def _normalize_ratings(game: str, ratings: list | None, mmr: int | None = None) -> list[dict]:
    items = []
    if ratings:
        for item in ratings:
            kind = item.kind if hasattr(item, "kind") else item.get("kind")
            value = item.value if hasattr(item, "value") else item.get("value")
            if kind not in rating_kinds(game):
                raise HTTPException(status_code=400, detail=f"Неизвестная шкала: {kind}")
            try:
                if value is None or (isinstance(value, float) and value != value):
                    raise ValueError("empty")
                numeric = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Некорректный рейтинг: {kind}",
                ) from exc
            items.append({"kind": kind, "value": clamp_rating(game, kind, numeric)})
    elif mmr is not None and game == "dota":
        items.append({"kind": "mmr", "value": clamp_rating(game, "mmr", int(mmr))})
    return items


async def _require_person(user_id: int):
    if await is_user_banned(user_id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    if not await has_user_consented(user_id):
        raise HTTPException(status_code=403, detail="Нужно принять согласие")
    user = await get_user_with_settings(user_id)
    if not is_person_registered(user):
        raise HTTPException(status_code=400, detail="Сначала заполни анкету")
    return user


async def _require_game_user(user_id: int, game: str | None, *, searching: bool = False):
    resolved = await _resolved_game(user_id, game)
    user = await _require_person(user_id)
    user = await get_user_with_settings(user_id, resolved)
    profile = user.profile_for(resolved) if user else None
    if not profile or not profile.is_complete():
        raise HTTPException(status_code=400, detail="Сначала заполни анкету этой игры")
    if searching and not is_game_searching(user, resolved):
        raise HTTPException(
            status_code=400,
            detail="Анкета скрыта. Покажи её в профиле, чтобы смотреть других.",
        )
    return user, resolved


@router.get("/catalog")
async def get_catalog():
    return {"games": catalog_payload()}


@router.get("/me")
async def get_me(game: str | None = None, user: WebAppUser = CurrentUser):
    banned = await is_user_banned(user.id)
    consented = await has_user_consented(user.id)
    profile = await get_user_with_settings(user.id)
    current_game = await _resolved_game(user.id, game) if (consented and not banned) else normalize_game(game)
    if profile:
        profile = await get_user_with_settings(user.id, current_game)
    extras = serialize_me_extras(profile, current_game)
    registered = extras["registered"]

    payload = {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "banned": banned,
        "consented": consented,
        "registered": registered,
        "needs_consent": not consented,
        "needs_registration": consented and not registered,
        "needs_game_profile": extras["needs_game_profile"] if consented and not banned else False,
        "has_game_profile": extras["has_game_profile"],
        "catalog": extras["catalog"],
        "games": extras["games"],
        "current_game": current_game,
        "pending_likes": 0,
        "profile": None,
    }

    if banned:
        return payload

    if registered and profile:
        payload["person"] = {
            "name": profile.name,
            "age": profile.age,
            "city": format_city_display(profile),
            "username": profile.username,
        }
        if extras["has_game_profile"]:
            aura, vibe = await get_reputation_counts(user.id, current_game)
            payload["profile"] = serialize_profile(
                profile,
                game=current_game,
                aura=aura,
                vibe=vibe,
                include_settings=True,
            )
            payload["pending_likes"] = await get_pending_likes_count(user.id, current_game)
            payload["like_messages_remaining"] = await get_like_messages_remaining_today(user.id)
            payload["like_message_limit"] = DAILY_LIKE_MESSAGE_LIMIT
            payload["like_message_max_length"] = LIKE_MESSAGE_MAX_LENGTH

    return payload


@router.post("/me/game")
async def switch_game(body: GameSwitchBody, user: WebAppUser = CurrentUser):
    await _require_person(user.id)
    if not is_known_game(body.game):
        raise HTTPException(status_code=400, detail="Неизвестная игра")
    game = await _resolved_game(user.id, body.game, persist=True)
    return await get_me(game=game, user=user)


@router.post("/consent")
async def accept_consent(user: WebAppUser = CurrentUser):
    if await is_user_banned(user.id):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    await record_user_consent(user.id, user.username)
    return {"ok": True}


@router.get("/browse/next")
async def browse_next(game: str | None = None, user: WebAppUser = CurrentUser):
    me, resolved = await _require_game_user(user.id, game, searching=True)
    profile = await get_next_profile(user.id, resolved)
    if not profile:
        return {"profile": None, "undo_available": False, "game": resolved}

    aura, vibe = await get_reputation_counts(profile.telegram_id, resolved)
    return {
        "profile": serialize_profile(profile, game=resolved, aura=aura, vibe=vibe),
        "like_messages_remaining": await get_like_messages_remaining_today(user.id),
        "game": resolved,
    }


@router.post("/swipe")
async def swipe(
    body: SwipeBody,
    user: WebAppUser = CurrentUser,
    bot: Bot = CurrentBot,
):
    me, resolved = await _require_game_user(user.id, body.game, searching=True)

    if body.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя свайпнуть себя")

    target = await get_user_with_settings(body.to_user_id, resolved)
    target_profile = target.profile_for(resolved) if target else None
    if not target or not target_profile or target_profile.status != ProfileStatus.ACTIVE:
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
    is_match = await add_swipe(user.id, body.to_user_id, action, message, resolved)

    if action == ActionType.LIKE and not is_match:
        if message:
            await notify_like_with_message(bot, body.to_user_id, me, message)
        else:
            await notify_like_threshold(bot, body.to_user_id, user.id, resolved)
    elif is_match:
        await notify_match(bot, user.id, body.to_user_id, resolved)

    return {
        "ok": True,
        "is_match": is_match,
        "game": resolved,
        "match_profile": serialize_profile(target, game=resolved, contact=True) if is_match else None,
    }


@router.post("/swipe/undo")
async def swipe_undo(body: UndoBody, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, body.game)
    ok = await undo_swipe(user.id, body.to_user_id, resolved)
    if not ok:
        raise HTTPException(status_code=404, detail="Нечего отменять")
    return {"ok": True}


@router.get("/likes")
async def get_likes(index: int = 0, game: str | None = None, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, game)
    liker, total, like_message = await get_pending_like_at_index(user.id, index, resolved)
    if not liker:
        return {"profile": None, "total": 0, "index": 0, "message": None, "game": resolved}

    actual = min(max(index, 0), total - 1)
    aura, vibe = await get_reputation_counts(liker.telegram_id, resolved)
    return {
        "profile": serialize_profile(liker, game=resolved, aura=aura, vibe=vibe),
        "total": total,
        "index": actual,
        "message": like_message,
        "game": resolved,
    }


@router.get("/matches")
async def get_matches(index: int = 0, game: str | None = None, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, game)
    partner, total = await get_match_at_index(user.id, index, resolved)
    if not partner:
        return {"profile": None, "total": 0, "index": 0, "rating": None, "game": resolved}

    actual = min(max(index, 0), total - 1)
    aura, vibe = await get_reputation_counts(partner.telegram_id, resolved)
    has_aura, has_vibe = await get_teammate_rating(user.id, partner.telegram_id, resolved)
    return {
        "profile": serialize_profile(partner, game=resolved, aura=aura, vibe=vibe, contact=True),
        "total": total,
        "index": actual,
        "rating": {"has_aura": has_aura, "has_vibe": has_vibe},
        "game": resolved,
    }


@router.post("/matches/rate")
async def rate_match(body: RateBody, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, body.game)
    error = await add_teammate_rating(
        user.id,
        body.to_user_id,
        aura=body.kind == "aura",
        vibe=body.kind == "vibe",
        game=resolved,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    has_aura, has_vibe = await get_teammate_rating(user.id, body.to_user_id, resolved)
    return {"ok": True, "rating": {"has_aura": has_aura, "has_vibe": has_vibe}}


@router.post("/report")
async def report_user(body: ReportBody, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, body.game)
    reason = ReportReason(body.reason)
    report_id = await add_report(user.id, body.to_user_id, reason, body.comment)
    await add_swipe(user.id, body.to_user_id, ActionType.DISLIKE, game=resolved)
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
    _me, resolved = await _require_game_user(user.id, body.game)
    payload = body.model_dump(exclude_unset=True)
    payload.pop("game", None)
    roles = valid_roles(resolved, payload.get("roles") or payload.get("positions"))
    if "roles" in payload or "positions" in payload:
        if not roles:
            raise HTTPException(status_code=400, detail="Выбери хотя бы одну роль")
        payload["roles"] = roles
    ratings = _normalize_ratings(resolved, body.ratings, body.mmr)
    if ratings:
        payload["ratings"] = ratings

    person_fields = {key: payload[key] for key in ("name", "age", "city") if key in payload}
    game_fields = {
        key: payload[key]
        for key in ("roles", "ratings", "bio", "photo_file_id", "mmr", "positions")
        if key in payload
    }
    for field, value in person_fields.items():
        await update_user_field(user.id, field, value, resolved)
    if game_fields:
        game_fields["game"] = resolved
        await save_user_and_settings(user.id, user.username, game_fields)

    profile = await get_user_with_settings(user.id, resolved)
    aura, vibe = await get_reputation_counts(user.id, resolved)
    return serialize_profile(profile, game=resolved, aura=aura, vibe=vibe, include_settings=True)


@router.patch("/profile/settings")
async def update_settings(body: SettingsUpdateBody, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, body.game)
    data = body.model_dump(exclude_unset=True)
    data.pop("game", None)
    raw_roles = data.get("wanted_roles") if "wanted_roles" in data else data.get("wanted_positions")
    if raw_roles is not None:
        data["wanted_roles"] = valid_roles(resolved, raw_roles) or None
        data.pop("wanted_positions", None)
    if data.get("wanted_rating_kind") and data["wanted_rating_kind"] not in rating_kinds(resolved):
        raise HTTPException(status_code=400, detail="Неизвестная шкала поиска")
    if "min_mmr" in data and "min_skill" not in data:
        data["min_skill"] = data.pop("min_mmr")
    if "max_mmr" in data and "max_skill" not in data:
        data["max_skill"] = data.pop("max_mmr")
    if "skill_filters" in data:
        cleaned = []
        for item in data.get("skill_filters") or []:
            kind = item.get("kind") if isinstance(item, dict) else None
            if not kind or kind not in rating_kinds(resolved):
                continue
            cleaned.append({
                "kind": kind,
                "min": item.get("min"),
                "max": item.get("max"),
            })
        data["skill_filters"] = cleaned or None
        if cleaned:
            data["wanted_rating_kind"] = cleaned[0]["kind"]
            data["min_skill"] = cleaned[0].get("min")
            data["max_skill"] = cleaned[0].get("max")

    for field, value in data.items():
        await update_settings_field(user.id, field, value, resolved)

    profile = await get_user_with_settings(user.id, resolved)
    aura, vibe = await get_reputation_counts(user.id, resolved)
    return serialize_profile(profile, game=resolved, aura=aura, vibe=vibe, include_settings=True)


@router.post("/profile/status")
async def set_profile_status(body: StatusUpdateBody, user: WebAppUser = CurrentUser):
    _me, resolved = await _require_game_user(user.id, body.game)
    new_status = ProfileStatus.ACTIVE if body.status == "active" else ProfileStatus.HIDDEN
    await update_user_field(user.id, "status", new_status, resolved)
    return {"ok": True, "status": new_status.value, "game": resolved}


@router.post("/profile/copy")
async def copy_profile_card(body: CopyCardBody, user: WebAppUser = CurrentUser):
    await _require_person(user.id)
    if not is_known_game(body.from_game):
        raise HTTPException(status_code=400, detail="Неизвестная игра")
    updated = await copy_game_card(
        user.id,
        body.from_game,
        body.to_games,
        copy_bio=body.bio,
        copy_photo=body.photo,
    )
    return {"ok": True, "updated": updated}


@router.delete("/games/{game}")
async def remove_game_profile(game: str, user: WebAppUser = CurrentUser):
    await _require_person(user.id)
    if not is_known_game(game):
        raise HTTPException(status_code=400, detail="Неизвестная игра")
    ok = await delete_game_profile(user.id, game)
    if not ok:
        raise HTTPException(status_code=404, detail="Анкета этой игры не найдена")
    return {"ok": True}


@router.delete("/profile")
async def remove_profile(user: WebAppUser = CurrentUser):
    await _require_person(user.id)
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
    if not is_known_game(body.game):
        raise HTTPException(status_code=400, detail="Неизвестная игра")

    game = normalize_game(body.game)
    existing = await get_user_with_settings(user.id, game)
    person_exists = is_person_registered(existing)

    name = (body.name or (existing.name if existing else "") or "").strip()
    age = body.age if body.age is not None else (existing.age if existing else None)
    city = (body.city or (existing.city if existing else "") or "").strip()
    if not person_exists and (not name or age is None or not city):
        raise HTTPException(status_code=400, detail="Заполни имя, возраст и город")

    roles = valid_roles(game, body.roles or body.positions)
    if not roles:
        raise HTTPException(status_code=400, detail="Выбери хотя бы одну роль")

    ratings = _normalize_ratings(game, body.ratings, body.mmr)
    if body.copy_card_from and existing:
        source = existing.profile_for(body.copy_card_from)
        if source:
            photo = body.photo_file_id or source.photo_file_id
            bio = body.bio if body.bio else (source.bio or "")
        else:
            photo = body.photo_file_id
            bio = body.bio or ""
    else:
        photo = body.photo_file_id
        bio = body.bio or ""
        if existing:
            current = existing.profile_for(game)
            photo = photo or (current.photo_file_id if current else None)
            bio = bio if body.bio else ((current.bio if current else "") or "")

    if not photo:
        raise HTTPException(status_code=400, detail="Нужно фото")
    if not ratings:
        raise HTTPException(status_code=400, detail="Укажи рейтинг")

    wanted = valid_roles(game, body.wanted_roles or body.wanted_positions)
    wanted_kind = body.wanted_rating_kind or (ratings[0]["kind"] if ratings else None)
    if wanted_kind and wanted_kind not in rating_kinds(game):
        raise HTTPException(status_code=400, detail="Неизвестная шкала поиска")

    try:
        save_data = {
            "game": game,
            "name": name,
            "age": age,
            "city": city,
            "roles": roles,
            "ratings": ratings,
            "bio": bio.strip(),
            "photo_id": photo,
            "photo_file_id": photo,
            "wanted_roles": wanted or None,
            "wanted_rating_kind": wanted_kind,
            "min_age": body.min_age,
            "max_age": body.max_age,
            "min_skill": body.min_skill if body.min_skill is not None else body.min_mmr,
            "max_skill": body.max_skill if body.max_skill is not None else body.max_mmr,
        }
        if body.skill_filters is not None:
            save_data["skill_filters"] = [
                {"kind": item.kind, "min": item.min, "max": item.max}
                for item in body.skill_filters
            ]
        await save_user_and_settings(
            user.id,
            user.username,
            save_data,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("register failed for %s game=%s: %s", user.id, game, exc)
        raise HTTPException(
            status_code=400,
            detail="Не удалось сохранить анкету. Попробуй ещё раз через пару секунд.",
        ) from exc

    await update_user_field(user.id, "last_active_game", game)
    profile = await get_user_with_settings(user.id, game)
    if not profile:
        raise HTTPException(status_code=500, detail="Анкета сохранена, но не прочиталась")
    game_profile = profile.profile_for(game)
    if not game_profile or not game_profile.is_complete():
        logger.error(
            "register incomplete after save user=%s game=%s profile=%s ratings=%s photo=%s roles=%s status=%s",
            user.id,
            game,
            bool(game_profile),
            len(game_profile.ratings or []) if game_profile else 0,
            bool(game_profile.photo_file_id) if game_profile else False,
            list(game_profile.roles or []) if game_profile else [],
            game_profile.status if game_profile else None,
        )
        raise HTTPException(
            status_code=500,
            detail="Анкета сохранилась неполностью. Попробуй ещё раз.",
        )
    return serialize_profile(profile, game=game, include_settings=True)


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
