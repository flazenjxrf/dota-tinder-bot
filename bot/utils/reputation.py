from bot.database.requests import get_reputation_counts

AURA_EMOJI = "🔥"
VIBE_EMOJI = "💜"
AURA_LABEL = "Aura"
VIBE_LABEL = "Vibe"


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
