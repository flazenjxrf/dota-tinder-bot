"""In-memory кэш ID заблокированных пользователей."""

_banned_ids: set[int] = set()


def warm(ids: set[int] | list[int]) -> None:
    _banned_ids.clear()
    _banned_ids.update(ids)


def add(telegram_id: int) -> None:
    _banned_ids.add(telegram_id)


def has(telegram_id: int) -> bool:
    return telegram_id in _banned_ids


def remove(telegram_id: int) -> None:
    _banned_ids.discard(telegram_id)
