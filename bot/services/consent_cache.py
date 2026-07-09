"""In-memory кэш ID пользователей, давших согласие."""

_consented_ids: set[int] = set()


def warm(ids: set[int] | list[int]) -> None:
    _consented_ids.clear()
    _consented_ids.update(ids)


def add(telegram_id: int) -> None:
    _consented_ids.add(telegram_id)


def has(telegram_id: int) -> bool:
    return telegram_id in _consented_ids


def remove(telegram_id: int) -> None:
    _consented_ids.discard(telegram_id)
