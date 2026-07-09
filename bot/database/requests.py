import logging
from sqlalchemy import select, or_
from bot.database.engine import session_maker
from bot.database.models import User, SearchSettings, ProfileStatus, UserConsent, ProfileDeletion
from bot.utils.city import normalize_city, get_normalized_city


async def save_user_and_settings(telegram_id: int, username: str | None, data: dict):
    """
    Сохраняет или обновляет анкету пользователя и его настройки поиска.
    data - это словарь со всеми ответами из машины состояний (FSM).
    """
    if await is_user_banned(telegram_id):
        logging.warning("Заблокированный пользователь %s попытался сохранить анкету.", telegram_id)
        return
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

from sqlalchemy.orm import selectinload, aliased
from sqlalchemy import func


async def _get_latest_consent_at(session, telegram_id: int):
    stmt = (
        select(func.max(UserConsent.consented_at))
        .where(UserConsent.telegram_id == telegram_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _get_latest_deletion_at(session, telegram_id: int):
    stmt = (
        select(func.max(ProfileDeletion.deleted_at))
        .where(ProfileDeletion.telegram_id == telegram_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _has_valid_consent(session, telegram_id: int) -> bool:
    """Согласие действует, если последнее согласие новее последнего удаления анкеты."""
    latest_consent = await _get_latest_consent_at(session, telegram_id)
    if not latest_consent:
        return False
    latest_deletion = await _get_latest_deletion_at(session, telegram_id)
    if latest_deletion is None:
        return True
    return latest_consent > latest_deletion


async def get_user_with_settings(telegram_id: int) -> User | None:
    """Получает пользователя вместе с его настройками поиска (1-к-1)"""
    async with session_maker() as session:
        stmt = select(User).options(selectinload(User.settings)).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def has_user_consented(telegram_id: int) -> bool:
    """Есть ли у пользователя действующее согласие на обработку данных."""
    from bot.services import consent_cache
    if consent_cache.has(telegram_id):
        return True
    async with session_maker() as session:
        if await _has_valid_consent(session, telegram_id):
            consent_cache.add(telegram_id)
            return True
        return False


async def get_all_consented_ids() -> list[int]:
    """ID пользователей с действующим согласием (для прогрева кэша)."""
    async with session_maker() as session:
        consent_stmt = (
            select(UserConsent.telegram_id, func.max(UserConsent.consented_at).label("last_consent"))
            .group_by(UserConsent.telegram_id)
        )
        consent_rows = (await session.execute(consent_stmt)).all()

        deletion_stmt = (
            select(
                ProfileDeletion.telegram_id,
                func.max(ProfileDeletion.deleted_at).label("last_deletion"),
            )
            .group_by(ProfileDeletion.telegram_id)
        )
        deletions = {
            row.telegram_id: row.last_deletion
            for row in (await session.execute(deletion_stmt)).all()
        }

        valid_ids: list[int] = []
        for row in consent_rows:
            last_deletion = deletions.get(row.telegram_id)
            if last_deletion is None or row.last_consent > last_deletion:
                valid_ids.append(row.telegram_id)
        return valid_ids


async def get_consent_gate_status(telegram_id: int) -> str:
    """
    consented — действующее согласие есть;
    needs_gate — зарегистрированный пользователь без действующего согласия;
    exempt — новый или незавершивший регистрацию.
    """
    from bot.services import consent_cache
    if consent_cache.has(telegram_id):
        return "consented"

    async with session_maker() as session:
        user_stmt = select(User.status).where(User.telegram_id == telegram_id)
        status = (await session.execute(user_stmt)).scalar_one_or_none()

        if status is None or status == ProfileStatus.INCOMPLETE:
            return "exempt"

        if await _has_valid_consent(session, telegram_id):
            consent_cache.add(telegram_id)
            return "consented"

        return "needs_gate"


async def record_user_consent(telegram_id: int, username: str | None) -> None:
    """Фиксирует новое согласие пользователя (каждое нажатие — отдельная запись)."""
    if await is_user_banned(telegram_id):
        return
    from bot.services import consent_cache
    async with session_maker() as session:
        session.add(UserConsent(telegram_id=telegram_id, username=username))
        await session.commit()
        consent_cache.add(telegram_id)
        logging.info(f"Зафиксировано согласие пользователя {telegram_id}.")

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


async def delete_user_profile(telegram_id: int) -> bool:
    """Удаляет анкету и связанные данные. Записи согласий сохраняются в журнале."""
    from bot.services import consent_cache
    async with session_maker() as session:
        user = await session.get(User, telegram_id)
        if not user:
            return False

        session.add(ProfileDeletion(telegram_id=telegram_id))
        await session.delete(user)
        await session.commit()
        consent_cache.remove(telegram_id)
        logging.info(f"Профиль пользователя {telegram_id} удалён, требуется новое согласие.")
        return True

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
from bot.database.models import SearchSettings, Swipe, ActionType, Report, ReportReason, ReportStatus, BannedUser
from datetime import datetime

DAILY_LIKE_MESSAGE_LIMIT = 5
LIKE_MESSAGE_MAX_LENGTH = 300


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


async def get_like_messages_remaining_today(user_id: int) -> int:
    """Сколько лайков с сообщением осталось на сегодня."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(Swipe)
            .where(
                Swipe.from_user_id == user_id,
                Swipe.message.isnot(None),
                Swipe.created_at >= today_start,
            )
        )
        used = (await session.execute(stmt)).scalar_one()
        return max(0, DAILY_LIKE_MESSAGE_LIMIT - used)


async def add_swipe(
    from_user_id: int,
    to_user_id: int,
    action: ActionType,
    message: str | None = None,
) -> bool:
    """
    Сохраняет свайп в БД.
    Возвращает True, если произошел взаимный мэтч (лайк в ответ на лайк).
    """
    async with session_maker() as session:
        stmt = select(Swipe).where(
            Swipe.from_user_id == from_user_id,
            Swipe.to_user_id == to_user_id,
        )
        swipe = (await session.execute(stmt)).scalar_one_or_none()
        if swipe:
            had_message = swipe.message is not None
            swipe.action = action
            swipe.is_mutual = False
            swipe.message = message if action == ActionType.LIKE else None
            if message and action == ActionType.LIKE and not had_message:
                swipe.created_at = datetime.utcnow()
        else:
            swipe = Swipe(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                action=action,
                message=message if action == ActionType.LIKE else None,
            )
            session.add(swipe)

        is_match = False

        if action == ActionType.LIKE:
            reverse_stmt = select(Swipe).where(
                Swipe.from_user_id == to_user_id,
                Swipe.to_user_id == from_user_id,
                Swipe.action == ActionType.LIKE,
            )
            reverse_swipe = (await session.execute(reverse_stmt)).scalar_one_or_none()

            if reverse_swipe:
                is_match = True
                swipe.is_mutual = True
                reverse_swipe.is_mutual = True

        await session.commit()
        return is_match


async def undo_swipe(from_user_id: int, to_user_id: int) -> bool:
    """Отменяет свайп. Возвращает True, если запись была удалена."""
    async with session_maker() as session:
        stmt = select(Swipe).where(
            Swipe.from_user_id == from_user_id,
            Swipe.to_user_id == to_user_id,
        )
        swipe = (await session.execute(stmt)).scalar_one_or_none()
        if not swipe:
            return False

        if swipe.is_mutual:
            reverse_stmt = select(Swipe).where(
                Swipe.from_user_id == to_user_id,
                Swipe.to_user_id == from_user_id,
            )
            reverse_swipe = (await session.execute(reverse_stmt)).scalar_one_or_none()
            if reverse_swipe:
                reverse_swipe.is_mutual = False

        await session.delete(swipe)
        await session.commit()
        return True


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


async def get_pending_likes_data(user_id: int) -> list[tuple[int, str | None]]:
    """Возвращает (telegram_id, message) неотвеченных лайков (сначала новые)."""
    async with session_maker() as session:
        stmt = (
            select(User.telegram_id, Swipe.message)
            .join(Swipe, Swipe.from_user_id == User.telegram_id)
            .where(*_pending_likes_conditions(user_id))
            .order_by(Swipe.created_at.desc())
        )
        return list((await session.execute(stmt)).all())


async def get_pending_likes_ids(user_id: int) -> list[int]:
    """Возвращает ID пользователей с неотвеченными лайками (сначала новые)."""
    return [liker_id for liker_id, _ in await get_pending_likes_data(user_id)]


async def get_next_pending_like(user_id: int) -> User | None:
    """Получает первого пользователя из списка неотвеченных лайков."""
    return await get_pending_like_at_index(user_id, 0)


async def get_pending_like_at_index(
    user_id: int, index: int,
) -> tuple[User | None, int, str | None]:
    """Возвращает анкету по индексу, общее количество и сообщение к лайку (если есть)."""
    pending = await get_pending_likes_data(user_id)
    total = len(pending)
    if total == 0:
        return None, 0, None

    index = min(max(index, 0), total - 1)
    liker_id, message = pending[index]
    async with session_maker() as session:
        stmt = select(User).where(User.telegram_id == liker_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        return user, total, message


async def add_report(from_user_id: int, to_user_id: int, reason: ReportReason) -> int | None:
    """Сохраняет жалобу. Возвращает ID новой жалобы или None, если уже была."""
    async with session_maker() as session:
        stmt = select(Report).where(
            Report.from_user_id == from_user_id,
            Report.to_user_id == to_user_id,
        )
        if (await session.execute(stmt)).scalar_one_or_none():
            return None

        report = Report(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            reason=reason,
            status=ReportStatus.PENDING,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report.id


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
    reverse_swipe = aliased(Swipe)
    async with session_maker() as session:
        stmt = (
            select(Swipe.to_user_id)
            .join(User, User.telegram_id == Swipe.to_user_id)
            .join(
                reverse_swipe,
                (Swipe.to_user_id == reverse_swipe.from_user_id)
                & (Swipe.from_user_id == reverse_swipe.to_user_id),
            )
            .where(
                Swipe.from_user_id == user_id,
                Swipe.action == ActionType.LIKE,
                reverse_swipe.action == ActionType.LIKE,
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


# ================= Админ-панель и баны =================


async def is_user_banned(telegram_id: int) -> bool:
    from bot.services import ban_cache
    if ban_cache.has(telegram_id):
        return True
    async with session_maker() as session:
        banned = await session.get(BannedUser, telegram_id)
        if banned:
            ban_cache.add(telegram_id)
            return True
        return False


async def get_all_banned_ids() -> list[int]:
    async with session_maker() as session:
        stmt = select(BannedUser.telegram_id)
        return list((await session.execute(stmt)).scalars().all())


async def ban_user(telegram_id: int, banned_by: int, reason: str | None = None) -> bool:
    from bot.services import ban_cache
    async with session_maker() as session:
        if await session.get(BannedUser, telegram_id):
            return False

        session.add(BannedUser(
            telegram_id=telegram_id,
            banned_by=banned_by,
            reason=reason,
        ))

        user = await session.get(User, telegram_id)
        if user:
            user.status = ProfileStatus.BANNED

        pending_reports = (await session.execute(
            select(Report).where(
                Report.to_user_id == telegram_id,
                Report.status == ReportStatus.PENDING,
            )
        )).scalars().all()
        for report in pending_reports:
            report.status = ReportStatus.RESOLVED

        await session.commit()
        ban_cache.add(telegram_id)
        logging.info("Пользователь %s заблокирован админом %s.", telegram_id, banned_by)
        return True


async def get_profile_stats() -> dict[str, int]:
    async with session_maker() as session:
        stmt = (
            select(User.status, func.count())
            .group_by(User.status)
        )
        rows = (await session.execute(stmt)).all()
        counts = {status.value: count for status, count in rows}
        active = counts.get(ProfileStatus.ACTIVE.value, 0)
        hidden = counts.get(ProfileStatus.HIDDEN.value, 0)
        banned = counts.get(ProfileStatus.BANNED.value, 0)
        incomplete = counts.get(ProfileStatus.INCOMPLETE.value, 0)
        return {
            "active": active,
            "hidden": hidden,
            "banned": banned,
            "incomplete": incomplete,
            "registered": active + hidden + banned,
            "total": sum(counts.values()),
        }


async def get_pending_reports_count() -> int:
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(Report)
            .where(Report.status == ReportStatus.PENDING)
        )
        return (await session.execute(stmt)).scalar_one()


async def get_pending_report_ids() -> list[int]:
    async with session_maker() as session:
        stmt = (
            select(Report.id)
            .where(Report.status == ReportStatus.PENDING)
            .order_by(Report.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_report_by_id(report_id: int) -> Report | None:
    async with session_maker() as session:
        return await session.get(Report, report_id)


async def get_users_by_ids(user_ids: list[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    async with session_maker() as session:
        stmt = select(User).where(User.telegram_id.in_(user_ids))
        users = (await session.execute(stmt)).scalars().all()
        return {user.telegram_id: user for user in users}


async def reject_report(report_id: int) -> bool:
    async with session_maker() as session:
        report = await session.get(Report, report_id)
        if not report or report.status != ReportStatus.PENDING:
            return False
        report.status = ReportStatus.REJECTED
        await session.commit()
        return True