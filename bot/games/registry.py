"""Реестр игр: роли, шкалы рейтинга, подписи. Новая игра = запись сюда."""
from __future__ import annotations

from typing import Any

DEFAULT_GAME = "dota"

COMPETITIVE_RANKS = {
    1: "Silver I",
    2: "Silver II",
    3: "Silver III",
    4: "Silver IV",
    5: "Silver Elite",
    6: "Silver Elite Master",
    7: "Gold Nova I",
    8: "Gold Nova II",
    9: "Gold Nova III",
    10: "Gold Nova Master",
    11: "Master Guardian I",
    12: "Master Guardian II",
    13: "Master Guardian Elite",
    14: "Distinguished Master Guardian",
    15: "Legendary Eagle",
    16: "Legendary Eagle Master",
    17: "Supreme Master First Class",
    18: "The Global Elite",
}

GAMES: dict[str, dict[str, Any]] = {
    "dota": {
        "id": "dota",
        "label": "Dota 2",
        "short": "Dota",
        "roles": {
            1: "Керри",
            2: "Мидер",
            3: "Тройка",
            4: "Саппорт",
        },
        "ratings": [
            {
                "kind": "mmr",
                "label": "MMR",
                "min": 0,
                "max": 20000,
                "step": 100,
                "default": 3000,
            },
        ],
        "ratings_required": 1,
        "multi_rating": False,
    },
    "cs2": {
        "id": "cs2",
        "label": "CS2",
        "short": "CS2",
        "roles": {
            1: "Entry",
            2: "AWPer",
            3: "Support",
            4: "Lurker",
            5: "IGL",
        },
        "ratings": [
            {
                "kind": "premier",
                "label": "Premier",
                "min": 0,
                "max": 40000,
                "step": 1000,
                "default": 10000,
            },
            {
                "kind": "faceit",
                "label": "Faceit",
                "min": 1,
                "max": 10,
                "step": 1,
                "default": 5,
            },
            {
                "kind": "competitive",
                "label": "Звание",
                "min": 1,
                "max": 18,
                "step": 1,
                "default": 10,
                "options": COMPETITIVE_RANKS,
            },
        ],
        "ratings_required": 1,
        "multi_rating": True,
    },
}


def known_game_ids() -> tuple[str, ...]:
    return tuple(GAMES.keys())


def is_known_game(game: str | None) -> bool:
    return bool(game) and game in GAMES


def normalize_game(game: str | None) -> str:
    if game and game in GAMES:
        return game
    return DEFAULT_GAME


def game_spec(game: str | None) -> dict[str, Any]:
    return GAMES[normalize_game(game)]


def game_label(game: str | None) -> str:
    return game_spec(game)["label"]


def role_map(game: str | None) -> dict[int, str]:
    return dict(game_spec(game)["roles"])


def role_labels(game: str | None, roles: list[int] | None) -> list[str]:
    mapping = role_map(game)
    return [mapping[role] for role in sorted(roles or []) if role in mapping]


def valid_roles(game: str | None, roles: list[int] | None) -> list[int]:
    mapping = role_map(game)
    return sorted({role for role in (roles or []) if role in mapping})


def rating_spec(game: str | None, kind: str) -> dict[str, Any] | None:
    for item in game_spec(game)["ratings"]:
        if item["kind"] == kind:
            return item
    return None


def rating_kinds(game: str | None) -> list[str]:
    return [item["kind"] for item in game_spec(game)["ratings"]]


def format_rating_value(game: str | None, kind: str, value: int) -> str:
    spec = rating_spec(game, kind)
    if not spec:
        return str(value)
    options = spec.get("options")
    if options:
        return options.get(value, str(value))
    if kind == "faceit":
        return f"lvl {value}"
    return f"{value:,}".replace(",", " ")


def format_rating(game: str | None, kind: str, value: int) -> str:
    spec = rating_spec(game, kind)
    label = spec["label"] if spec else kind
    return f"{label} {format_rating_value(game, kind, value)}"


def clamp_rating(game: str | None, kind: str, value: int) -> int:
    spec = rating_spec(game, kind)
    if not spec:
        raise ValueError(f"Неизвестная шкала: {kind}")
    lo, hi = spec["min"], spec["max"]
    return max(lo, min(hi, int(value)))


def catalog_payload() -> list[dict[str, Any]]:
    items = []
    for game_id, spec in GAMES.items():
        items.append({
            "id": game_id,
            "label": spec["label"],
            "short": spec["short"],
            "roles": [{"id": role_id, "label": label} for role_id, label in spec["roles"].items()],
            "ratings": [
                {
                    "kind": item["kind"],
                    "label": item["label"],
                    "min": item["min"],
                    "max": item["max"],
                    "step": item["step"],
                    "default": item.get("default", item["min"]),
                    "options": [
                        {"id": opt_id, "label": opt_label}
                        for opt_id, opt_label in (item.get("options") or {}).items()
                    ],
                }
                for item in spec["ratings"]
            ],
            "ratings_required": spec["ratings_required"],
            "multi_rating": spec["multi_rating"],
        })
    return items
