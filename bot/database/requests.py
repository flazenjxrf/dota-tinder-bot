import logging
from sqlalchemy import select, or_
from bot.database.engine import session_maker
from bot.database.models import User, SearchSettings, ProfileStatus
from bot.utils.city import normalize_city, get_normalized_city


async def save_user_and_settings(telegram_id: int, username: str | None, data: dict):
    """
    Сохраняет или обновляет анкету пользователя и его настройки поиска.
    data - это словарь со всеми ответами из машины состояний (FSM).
    """
    async with session_maker() as session:
        try:
            # 1. Создаем или обновляем пользователя
            user = User(
                telegram_id=telegram_id,
                username=username,
                name=data['name'],
                age=data['age'],
                city=data['city'],
                normalized_city=normalize_city(data['city']),
                mmr=data['mmr'],
                positions=data['positions'],
                bio=data['bio'],
                photo_file_id=data['photo_id'],
                status=ProfileStatus.ACTIVE
            )

            # Используем merge для обновления, если пользователь решил пересоздать анкету
            session.add(await session.merge(user))

            # 2. Создаем или обновляем настройки поиска
            settings = SearchSettings(
                user_id=telegram_id,
                wanted_positions=data.get('wanted_positions') or None,  # Если пустой список, в БД будет NULL
                min_age=data.get('min_age'),
                max_age=data.get('max_age'),
                min_mmr=data.get('min_mmr'),
                max_mmr=data.get('max_mmr')
            )

            session.add(await session.merge(settings))

            # Подтверждаем изменения
            await session.commit()
            logging.info(f"Пользователь {telegram_id} успешно сохранен в БД.")
        except Exception as e:
            await session.rollback()
            logging.error(f"Ошибка при сохранении в БД: {e}")

from sqlalchemy.orm import selectinload

async def get_user_with_settings(telegram_id: int) -> User | None:
    """Получает пользователя вместе с его настройками поиска (1-к-1)"""
    async with session_maker() as session:
        stmt = select(User).options(selectinload(User.settings)).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

async def update_user_field(telegram_id: int, field_name: str, value):
    """Обновляет одно конкретное поле в таблице users"""
    async with session_maker() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            setattr(user, field_name, value)
            if field_name == "city":
                user.normalized_city = normalize_city(value)
            await session.commit()

async def update_settings_field(telegram_id: int, field_name: str, value):
    """Обновляет одно конкретное поле в таблице search_settings"""
    async with session_maker() as session:
        stmt = select(SearchSettings).where(SearchSettings.user_id == telegram_id)
        result = await session.execute(stmt)
        settings = result.scalar_one_or_none()
        if settings:
            setattr(settings, field_name, value)
            await session.commit()


from sqlalchemy import select, and_, not_, exists, func
from bot.database.models import SearchSettings, Swipe, ActionType, Report, ReportReason


def _apply_search_filters(stmt, settings: SearchSettings | None):
    if not settings:
        return stmt
    if settings.min_age is not None:
        stmt = stmt.where(User.age >= settings.min_age)
    if settings.max_age is not None:
        stmt = stmt.where(User.age <= settings.max_age)
    if settings.min_mmr is not None:
        stmt = stmt.where(User.mmr >= settings.min_mmr)
    if settings.max_mmr is not None:
        stmt = stmt.where(User.mmr <= settings.max_mmr)
    if settings.wanted_positions:
        stmt = stmt.where(User.positions.overlap(settings.wanted_positions))
    return stmt


async def get_next_profile(user_id: int) -> User | None:
    """Ищет следующую подходящую анкету: сначала из того же города, затем остальные. Порядок случайный."""
    async with session_maker() as session:
        stmt_user = select(User).where(User.telegram_id == user_id)
        current_user = (await session.execute(stmt_user)).scalar_one_or_none()

        stmt_settings = select(SearchSettings).where(SearchSettings.user_id == user_id)
        settings = (await session.execute(stmt_settings)).scalar_one_or_none()

        swipe_exists = exists().where(
            and_(
                Swipe.from_user_id == user_id,
                Swipe.to_user_id == User.telegram_id
            )
        )

        def build_query(same_city: bool = False):
            stmt = select(User).where(
                User.status == ProfileStatus.ACTIVE,
                User.telegram_id != user_id,
                not_(swipe_exists),
            )
            if same_city and current_user:
                normalized = get_normalized_city(current_user.city, current_user.normalized_city)
                if normalized:
                    stmt = stmt.where(User.normalized_city == normalized)
            stmt = _apply_search_filters(stmt, settings)
            return stmt.order_by(func.random()).limit(1)

        for same_city in (True, False):
            if same_city and not get_normalized_city(
                current_user.city if current_user else None,
                current_user.normalized_city if current_user else None,
            ):
                continue
            result = await session.execute(build_query(same_city=same_city))
            profile = result.scalar_one_or_none()
            if profile:
                return profile

        return None


async def add_swipe(from_user_id: int, to_user_id: int, action: ActionType) -> bool:
    """
    Сохраняет свайп в БД.
    Возвращает True, если произошел взаимный мэтч (лайк в ответ на лайк).
    """
    async with session_maker() as session:
        # Записываем свайп
        swipe = Swipe(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            action=action
        )
        await session.merge(swipe)

        is_match = False

        # Если это лайк, проверяем, лайкал ли этот человек нас ранее
        if action == ActionType.LIKE:
            stmt = select(Swipe).where(
                Swipe.from_user_id == to_user_id,
                Swipe.to_user_id == from_user_id,
                Swipe.action == ActionType.LIKE
            )
            res = await session.execute(stmt)
            reverse_swipe = res.scalar_one_or_none()

            if reverse_swipe:
                is_match = True
                # Помечаем оба свайпа взаимными
                swipe.is_mutual = True
                reverse_swipe.is_mutual = True
                await session.merge(reverse_swipe)

        await session.commit()
        return is_match


def _pending_likes_conditions(user_id: int):
    """Условия для неотвеченных входящих лайков (ещё не просмотренных в «Мои лайки»)."""
    responded_subq = select(Swipe.to_user_id).where(Swipe.from_user_id == user_id)
    return (
        Swipe.to_user_id == user_id,
        Swipe.action == ActionType.LIKE,
        Swipe.is_mutual == False,
        User.status.in_([ProfileStatus.ACTIVE, ProfileStatus.HIDDEN]),
        not_(User.telegram_id.in_(responded_subq)),
    )


async def get_pending_likes_count(user_id: int) -> int:
    """Считает количество неотвеченных входящих лайков."""
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(User)
            .join(Swipe, Swipe.from_user_id == User.telegram_id)
            .where(*_pending_likes_conditions(user_id))
        )
        return (await session.execute(stmt)).scalar_one()


async def get_pending_likes_ids(user_id: int) -> list[int]:
    """Возвращает ID пользователей с неотвеченными лайками (сначала новые)."""
    async with session_maker() as session:
        stmt = (
            select(User.telegram_id)
            .join(Swipe, Swipe.from_user_id == User.telegram_id)
            .where(*_pending_likes_conditions(user_id))
            .order_by(Swipe.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_next_pending_like(user_id: int) -> User | None:
    """Получает первого пользователя из списка неотвеченных лайков."""
    return await get_pending_like_at_index(user_id, 0)


async def get_pending_like_at_index(user_id: int, index: int) -> tuple[User | None, int]:
    """Возвращает анкету по индексу и общее количество неотвеченных лайков."""
    liker_ids = await get_pending_likes_ids(user_id)
    total = len(liker_ids)
    if total == 0:
        return None, 0

    index = min(max(index, 0), total - 1)
    async with session_maker() as session:
        stmt = select(User).where(User.telegram_id == liker_ids[index])
        user = (await session.execute(stmt)).scalar_one_or_none()
        return user, total


async def add_report(from_user_id: int, to_user_id: int, reason: ReportReason) -> bool:
    """Сохраняет жалобу. Возвращает True, если жалоба создана, False — если уже была."""
    async with session_maker() as session:
        stmt = select(Report).where(
            Report.from_user_id == from_user_id,
            Report.to_user_id == to_user_id,
        )
        if (await session.execute(stmt)).scalar_one_or_none():
            return False

        session.add(Report(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            reason=reason,
        ))
        await session.commit()
        return True


async def backfill_normalized_cities() -> int:
    """Заполняет normalized_city у пользователей, у которых поле пустое."""
    async with session_maker() as session:
        stmt = select(User).where(
            User.city.isnot(None),
            User.city != "",
            or_(User.normalized_city.is_(None), User.normalized_city == ""),
        )
        users = (await session.execute(stmt)).scalars().all()
        updated = 0
        for user in users:
            user.normalized_city = normalize_city(user.city)
            updated += 1
        if updated:
            await session.commit()
            logging.info(f"Заполнено normalized_city для {updated} пользователей.")
        return updated


async def get_match_partner_ids(user_id: int) -> list[int]:
    """Возвращает ID напарников с взаимными лайками (сначала новые)."""
    async with session_maker() as session:
        stmt = (
            select(Swipe.to_user_id)
            .where(
                Swipe.from_user_id == user_id,
                Swipe.action == ActionType.LIKE,
                Swipe.is_mutual == True,
            )
            .order_by(Swipe.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_match_at_index(user_id: int, index: int) -> tuple[User | None, int]:
    """Возвращает анкету мэтча по индексу и общее количество мэтчей."""
    partner_ids = await get_match_partner_ids(user_id)
    total = len(partner_ids)
    if total == 0:
        return None, 0

    index = min(max(index, 0), total - 1)
    async with session_maker() as session:
        stmt = select(User).where(User.telegram_id == partner_ids[index])
        user = (await session.execute(stmt)).scalar_one_or_none()
        return user, total