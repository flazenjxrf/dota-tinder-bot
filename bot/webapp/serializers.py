"""Сериализация анкет для JSON API Mini App."""
from __future__ import annotations

from urllib.parse import quote

from bot.database.models import User
from bot.utils.city import format_city_display

POSITIONS = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт",
}


def position_labels(positions: list[int] | None) -> list[str]:
    return [POSITIONS[p] for p in sorted(positions or []) if p in POSITIONS]


def photo_url(file_id: str) -> str:
    return f"/api/photos/{quote(file_id, safe='')}"


def serialize_profile(
    user: User,
    *,
    aura: int = 0,
    vibe: int = 0,
    include_settings: bool = False,
    contact: bool = False,
) -> dict:
    data = {
        "telegram_id": user.telegram_id,
        "name": user.name,
        "age": user.age,
        "city": format_city_display(user),
        "mmr": user.mmr,
        "positions": list(user.positions or []),
        "position_labels": position_labels(user.positions),
        "bio": user.bio or "",
        "photo_file_id": user.photo_file_id,
        "photo_url": photo_url(user.photo_file_id),
        "status": user.status.value if user.status else None,
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
    if include_settings and user.settings:
        settings = user.settings
        data["settings"] = {
            "wanted_positions": list(settings.wanted_positions or []),
            "min_age": settings.min_age,
            "max_age": settings.max_age,
            "min_mmr": settings.min_mmr,
            "max_mmr": settings.max_mmr,
        }
    return data
