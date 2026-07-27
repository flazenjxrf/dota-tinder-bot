from bot.database.requests import get_reputation_counts


async def format_reputation_line(user_id: int) -> str:
    """Форматирует строку репутации для карточки анкеты. Пустая, если оценок нет."""
    aura_count, vibe_count = await get_reputation_counts(user_id)
    parts: list[str] = []
    if aura_count > 0:
        parts.append(f"✨ {aura_count}")
    if vibe_count > 0:
        parts.append(f"💬 {vibe_count}")
    if not parts:
        return ""
    return "\n" + " · ".join(parts)
