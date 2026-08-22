"""Сериализация анкет для JSON API Mini App."""
from __future__ import annotations

from urllib.parse import quote

from bot.database.models import GameProfile, ProfileStatus, User
from bot.games import (
    catalog_payload,
    format_rating,
    format_rating_value,
    game_label,
    known_game_ids,
    normalize_game,
    rating_spec,
    role_labels,
)
from bot.utils.city import format_city_display


def photo_url(file_id: str | None) -> str | None:
    if not file_id:
        return None
    return f"/api/photos/{quote(file_id, safe='')}"


def serialize_ratings(profile: GameProfile | None) -> list[dict]:
    if not profile:
        return []
    items = []
    for rating in profile.ratings or []:
        spec = rating_spec(profile.game, rating.kind)
        items.append({
            "kind": rating.kind,
            "label": spec["label"] if spec else rating.kind,
            "value": rating.value,
            "display": format_rating_value(profile.game, rating.kind, rating.value),
            "text": format_rating(profile.game, rating.kind, rating.value),
        })
    return items


def serialize_settings(profile: GameProfile | None) -> dict | None:
    if not profile or not profile.settings:
        return None
    settings = profile.settings
    return {
        "wanted_roles": list(settings.wanted_roles or []),
        "wanted_positions": list(settings.wanted_roles or []),
        "wanted_rating_kind": settings.wanted_rating_kind,
        "min_age": settings.min_age,
        "max_age": settings.max_age,
        "min_skill": settings.min_skill,
        "max_skill": settings.max_skill,
        "min_mmr": settings.min_skill,
        "max_mmr": settings.max_skill,
    }


def serialize_user_games(user: User | None) -> list[dict]:
    by_id = {item.game: item for item in (user.game_profiles or [])} if user else {}
    items = []
    for game_id in known_game_ids():
        profile = by_id.get(game_id)
        items.append({
            "id": game_id,
            "label": game_label(game_id),
            "has_profile": bool(profile and profile.is_complete()),
            "status": profile.status.value if profile and profile.status else None,
            "photo_url": photo_url(profile.photo_file_id) if profile else None,
            "photo_file_id": profile.photo_file_id if profile else None,
            "bio": (profile.bio or "") if profile else "",
        })
    return items


def serialize_profile(
    user: User,
    *,
    game: str | None = None,
    aura: int = 0,
    vibe: int = 0,
    include_settings: bool = False,
    contact: bool = False,
) -> dict:
    game = normalize_game(game or getattr(user, "_view_game", None) or user.last_active_game)
    profile = user.profile_for(game)
    roles = list(profile.roles or []) if profile else []
    ratings = serialize_ratings(profile)
    mmr = None
    if profile:
        mmr = profile.skill_value("mmr")
        if mmr is None and ratings:
            mmr = ratings[0]["value"]
    labels = role_labels(game, roles)
    data = {
        "telegram_id": user.telegram_id,
        "name": user.name,
        "age": user.age,
        "city": format_city_display(user),
        "game": game,
        "game_label": game_label(game),
        "roles": roles,
        "role_labels": labels,
        "positions": roles,
        "position_labels": labels,
        "ratings": ratings,
        "rating_text": " · ".join(item["text"] for item in ratings),
        "mmr": mmr,
        "bio": (profile.bio or "") if profile else "",
        "photo_file_id": profile.photo_file_id if profile else None,
        "photo_url": photo_url(profile.photo_file_id if profile else None),
        "status": profile.status.value if profile and profile.status else None,
        "account_status": user.status.value if user.status else None,
        "aura": aura,
        "vibe": vibe,
    }
    if contact:
        data["username"] = user.username
        data["tg_link"] = (
            f"https://t.me/{user.username}"
            if user.username
            else f"tg://user?id={user.telegram_id}"
        )
    if include_settings:
        data["settings"] = serialize_settings(profile) or {
            "wanted_roles": [],
            "wanted_positions": [],
            "wanted_rating_kind": None,
            "min_age": None,
            "max_age": None,
            "min_skill": None,
            "max_skill": None,
            "min_mmr": None,
            "max_mmr": None,
        }
    return data


def serialize_me_extras(user: User | None, game: str) -> dict:
    profile = user.profile_for(game) if user else None
    registered = bool(user and user.status != ProfileStatus.INCOMPLETE)
    has_game = bool(profile and profile.is_complete())
    return {
        "catalog": catalog_payload(),
        "games": serialize_user_games(user),
        "current_game": game,
        "registered": registered,
        "has_game_profile": has_game,
        "needs_game_profile": registered and not has_game,
    }
