from bot.database.requests import get_reputation_counts

AURA_EMOJI = "🔥"
VIBE_EMOJI = "💜"
AURA_LABEL = "Aura"
VIBE_LABEL = "Vibe"


def people_word(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return "человек"
    rem = count % 10
    if rem == 1:
        return "человек"
    if 2 <= rem <= 4:
        return "человека"
    return "человек"


def count_verb(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "считает"
    return "считают"


def format_reputation_line_from_counts(aura_count: int, vibe_count: int) -> str:
    """Форматирует строку репутации. Пустая, если оценок нет."""
    parts: list[str] = []
    if aura_count > 0:
        parts.append(f"{AURA_EMOJI} {aura_count}")
    if vibe_count > 0:
        parts.append(f"{VIBE_EMOJI} {vibe_count}")
    if not parts:
        return ""
    return "\n" + " · ".join(parts)


async def format_reputation_line(user_id: int) -> str:
    """Форматирует строку репутации для карточки анкеты. Пустая, если оценок нет."""
    aura_count, vibe_count = await get_reputation_counts(user_id)
    return format_reputation_line_from_counts(aura_count, vibe_count)


def format_reputation_info(kind: str, count: int, *, is_self: bool) -> str:
    """Текст всплывашки при тапе по репутации."""
    if kind == "aura":
        title = f"{AURA_EMOJI} Aura — скилл"
        target = "тебя скилловым игроком" if is_self else "этого игрока скилловым"
    else:
        title = f"{VIBE_EMOJI} Vibe — общение"
        target = "тебя приятным в общении" if is_self else "этого игрока приятным в общении"

    body = f"{count} {people_word(count)} {count_verb(count)} {target}."
    if is_self:
        return f"{title}\n\n{body}"
    return (
        f"{title}\n\n{body}\n\n"
        "Ты тоже можешь оставить оценку в /matches после мэтча."
    )
