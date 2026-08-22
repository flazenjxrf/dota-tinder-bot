import logging
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from bot.database.engine import session_maker
from bot.database.models import (
    User, SearchSettings, ProfileStatus, UserConsent, ProfileDeletion,
    GameProfile, GameRating,
)
from bot.games import DEFAULT_GAME, clamp_rating, normalize_game, rating_kinds, valid_roles
from bot.utils.city import normalize_city, get_normalized_city


def _user_load_options():
    return (
        selectinload(User.game_profiles).selectinload(GameProfile.ratings),
        selectinload(User.game_profiles).selectinload(GameProfile.settings),
    )


def _attach_view(user: User | None, game: str | None) -> User | None:
    if user is not None:
        user._view_game = normalize_game(game or user.last_active_game)
    return user


def is_person_registered(user: User | None) -> bool:
    return bool(user and user.status != ProfileStatus.INCOMPLETE)


def is_game_searching(user: User | None, game: str | None = None) -> bool:
    if not is_person_registered(user):
        return False
    profile = user.display_profile(game)
    return bool(profile and profile.status == ProfileStatus.ACTIVE and profile.is_complete())


def _ratings_from_data(game: str, data: dict) -> list[tuple[str, int]]:
    raw = data.get("ratings")
    pairs: list[tuple[str, int]] = []
    known = set(rating_kinds(game))
    if raw:
        for item in raw:
            kind = item.get("kind") if isinstance(item, dict) else None
            value = item.get("value") if isinstance(item, dict) else None
            if not kind or kind not in known or value is None:
                continue
            try:
                pairs.append((kind, clamp_rating(game, kind, int(value))))
            except (TypeError, ValueError):
                continue
    elif data.get("mmr") is not None and game == "dota":
        pairs.append(("mmr", clamp_rating(game, "mmr", int(data["mmr"]))))
    return pairs


async def _upsert_game_profile(session, user: User, game: str, data: dict) -> GameProfile:
    """Создаёт/обновляет игровую анкету.

    Важно: при cascade delete-orphan объект нужно сначала привязать к
    relationship-коллекции, и только потом flush — иначе SQLAlchemy
    удаляет только что вставленный профиль/рейтинг как «сироту».
    """
    from sqlalchemy.orm.attributes import flag_modified

    game = normalize_game(game)
    # relationship всегда даёт коллекцию у persistent User; не подменяем её list()
    profile = next((item for item in user.game_profiles if item.game == game), None)
    if profile is None:
        profile = GameProfile(user_id=user.telegram_id, game=game)
        user.game_profiles.append(profile)
        await session.flush()

    roles = valid_roles(game, data.get("roles") or data.get("positions") or profile.roles)
    if roles:
        profile.roles = list(roles)
        flag_modified(profile, "roles")
    if "bio" in data:
        profile.bio = data.get("bio") or ""
    photo = data.get("photo_id") or data.get("photo_file_id")
    if photo:
        profile.photo_file_id = photo
    profile.status = data.get("game_status") or ProfileStatus.ACTIVE

    ratings = _ratings_from_data(game, data)
    if ratings:
        current_ratings = list(profile.ratings or [])
        existing = {item.kind: item for item in current_ratings}
        keep = set()
        for kind, value in ratings:
            keep.add(kind)
            if kind in existing:
                existing[kind].value = value
            else:
                profile.ratings.append(GameRating(kind=kind, value=value))
        for kind, item in list(existing.items()):
            if kind not in keep:
                profile.ratings.remove(item)

    if profile.settings is None:
        profile.settings = SearchSettings(game_profile_id=profile.id)

    settings = profile.settings
    if "wanted_roles" in data or "wanted_positions" in data:
        wanted = data.get("wanted_roles") if "wanted_roles" in data else data.get("wanted_positions")
        settings.wanted_roles = wanted or None
    if "min_age" in data:
        settings.min_age = data.get("min_age")
    if "max_age" in data:
        settings.max_age = data.get("max_age")
    if "wanted_rating_kind" in data:
        settings.wanted_rating_kind = data.get("wanted_rating_kind")
    if "min_skill" in data or "min_mmr" in data:
        settings.min_skill = data.get("min_skill", data.get("min_mmr"))
    if "max_skill" in data or "max_mmr" in data:
        settings.max_skill = data.get("max_skill", data.get("max_mmr"))
    if not settings.wanted_rating_kind:
        kinds = [kind for kind, _ in ratings] or rating_kinds(game)
        settings.wanted_rating_kind = kinds[0] if kinds else None
    return profile


async def save_user_and_settings(telegram_id: int, username: str | None, data: dict):
    """Сохраняет человека и игровую анкету (по умолчанию Dota)."""
    if await is_user_banned(telegram_id):
        logging.warning("Заблокированный пользователь %s попытался сохранить анкету.", telegram_id)
        raise PermissionError("Аккаунт заблокирован")
    game = normalize_game(data.get("game"))
    async with session_maker() as session:
        try:
            stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if user is None:
                name = (data.get("name") or "").strip()
                age = data.get("age")
                city = (data.get("city") or "").strip()
                if not name or age is None or not city:
                    raise ValueError("Для новой анкеты нужны имя, возраст и город")
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    name=name,
                    age=int(age),
                    city=city,
                    normalized_city=normalize_city(city),
                    status=ProfileStatus.ACTIVE,
                    last_active_game=game,
                )
                session.add(user)
                await session.flush()
            else:
                if username is not None:
                    user.username = username
                if data.get("name"):
                    user.name = data["name"]
                if data.get("age") is not None:
                    user.age = data["age"]
                if data.get("city"):
                    user.city = data["city"]
                    user.normalized_city = normalize_city(data["city"])
                if user.status != ProfileStatus.BANNED:
                    user.status = ProfileStatus.ACTIVE
                user.last_active_game = game

            profile = await _upsert_game_profile(session, user, game, data)
            await session.commit()
            logging.info(
                "Пользователь %s сохранён (%s), complete=%s, ratings=%s",
                telegram_id,
                game,
                profile.is_complete(),
                len(profile.ratings or []),
            )
        except Exception as e:
            await session.rollback()
            logging.error("Ошибка при сохранении в БД: %s", e)
            raise


async def copy_game_card(
    telegram_id: int,
    from_game: str,
    to_games: list[str] | None = None,
    *,
    copy_bio: bool = True,
    copy_photo: bool = True,
) -> int:
    """Копирует фото/описание из одной анкеты в другие. Возвращает число обновлённых."""
    from_game = normalize_game(from_game)
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return 0
        source = user.profile_for(from_game)
        if not source:
            return 0
        targets = [
            profile for profile in (user.game_profiles or [])
            if profile.game != from_game and (not to_games or profile.game in to_games)
        ]
        updated = 0
        for profile in targets:
            if copy_bio:
                profile.bio = source.bio
            if copy_photo:
                profile.photo_file_id = source.photo_file_id
            updated += 1
        await session.commit()
        return updated


async def delete_game_profile(telegram_id: int, game: str) -> bool:
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return False
        profile = user.profile_for(game)
        if not profile:
            return False
        await session.delete(profile)
        remaining = [item.game for item in (user.game_profiles or []) if item.game != game]
        if remaining and user.last_active_game == game:
            user.last_active_game = remaining[0]
        await session.commit()
        return True

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


async def get_user_with_settings(telegram_id: int, game: str | None = None) -> User | None:
    """Получает пользователя вместе с игровыми анкетами, рейтингами и фильтрами."""
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return _attach_view(result.scalar_one_or_none(), game)


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

_GAME_CARD_FIELDS = {"mmr", "positions", "roles", "bio", "photo_file_id"}
_SETTINGS_ALIASES = {
    "wanted_positions": "wanted_roles",
    "min_mmr": "min_skill",
    "max_mmr": "max_skill",
}


async def update_user_field(telegram_id: int, field_name: str, value, game: str | None = None):
    """Обновляет поле человека или текущей игровой анкеты."""
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return

        if field_name == "city":
            user.city = value
            user.normalized_city = normalize_city(value)
            await session.commit()
            return

        if field_name == "status" and value in (ProfileStatus.ACTIVE, ProfileStatus.HIDDEN):
            profile = user.display_profile(game)
            if profile:
                profile.status = value
            await session.commit()
            return

        if field_name in _GAME_CARD_FIELDS:
            resolved = normalize_game(game or user.last_active_game)
            data = {field_name: value}
            if field_name == "mmr":
                data = {"ratings": [{"kind": "mmr", "value": value}]}
            elif field_name == "positions":
                data = {"roles": value}
            await _upsert_game_profile(session, user, resolved, data)
            await session.commit()
            return

        setattr(user, field_name, value)
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

async def update_settings_field(telegram_id: int, field_name: str, value, game: str | None = None):
    """Обновляет фильтр поиска текущей игровой анкеты."""
    field_name = _SETTINGS_ALIASES.get(field_name, field_name)
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == telegram_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return
        profile = user.display_profile(game)
        if not profile:
            return
        if profile.settings is None:
            profile.settings = SearchSettings(game_profile_id=profile.id)
            session.add(profile.settings)
        setattr(profile.settings, field_name, value)
        await session.commit()


from sqlalchemy import select, and_, not_, exists, func
from bot.database.models import (
    SearchSettings, Swipe, ActionType, Report, ReportReason, ReportStatus,
    BugFeedback, FeedbackStatus, BannedUser, BanHistory, UnbanRequest, UnbanRequestStatus,
    TeammateRating,
)
from datetime import datetime

DAILY_LIKE_MESSAGE_LIMIT = 5
LIKE_MESSAGE_MAX_LENGTH = 300


def _apply_search_filters(stmt, settings: SearchSettings | None, candidate, my_kinds: list[str] | None = None):
    if settings:
        if settings.min_age is not None:
            stmt = stmt.where(User.age >= settings.min_age)
        if settings.max_age is not None:
            stmt = stmt.where(User.age <= settings.max_age)
        if settings.wanted_roles:
            stmt = stmt.where(candidate.roles.overlap(settings.wanted_roles))
        kind = settings.wanted_rating_kind
        if kind:
            rating_conds = [
                GameRating.profile_id == candidate.id,
                GameRating.kind == kind,
            ]
            if settings.min_skill is not None:
                rating_conds.append(GameRating.value >= settings.min_skill)
            if settings.max_skill is not None:
                rating_conds.append(GameRating.value <= settings.max_skill)
            stmt = stmt.where(exists().where(and_(*rating_conds)))
            return stmt
    if my_kinds:
        stmt = stmt.where(exists().where(
            GameRating.profile_id == candidate.id,
            GameRating.kind.in_(my_kinds),
        ))
    return stmt


async def get_next_profile(user_id: int, game: str | None = None) -> User | None:
    """Ищет следующую анкету той же игры: сначала свой город, затем остальные."""
    async with session_maker() as session:
        stmt_user = select(User).options(*_user_load_options()).where(User.telegram_id == user_id)
        current_user = (await session.execute(stmt_user)).scalar_one_or_none()
        if not current_user:
            return None

        game = normalize_game(game or current_user.last_active_game)
        my_profile = current_user.profile_for(game)
        settings = my_profile.settings if my_profile else None
        my_kinds = [item.kind for item in (my_profile.ratings or [])] if my_profile else []
        candidate = aliased(GameProfile)

        swipe_exists = exists().where(
            and_(
                Swipe.from_user_id == user_id,
                Swipe.to_user_id == User.telegram_id,
                Swipe.game == game,
            )
        )

        def build_query(same_city: bool = False):
            stmt = (
                select(User)
                .options(*_user_load_options())
                .join(candidate, candidate.user_id == User.telegram_id)
                .where(
                    User.telegram_id != user_id,
                    User.status != ProfileStatus.BANNED,
                    candidate.game == game,
                    candidate.status == ProfileStatus.ACTIVE,
                    not_(swipe_exists),
                )
            )
            if same_city:
                normalized = get_normalized_city(current_user.city, current_user.normalized_city)
                if normalized:
                    stmt = stmt.where(User.normalized_city == normalized)
            stmt = _apply_search_filters(stmt, settings, candidate, my_kinds)
            return stmt.order_by(func.random()).limit(1)

        for same_city in (True, False):
            if same_city and not get_normalized_city(current_user.city, current_user.normalized_city):
                continue
            result = await session.execute(build_query(same_city=same_city))
            profile = result.scalar_one_or_none()
            if profile:
                return _attach_view(profile, game)

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
    game: str | None = None,
) -> bool:
    """
    Сохраняет свайп в БД.
    Возвращает True, если произошел взаимный мэтч (лайк в ответ на лайк).
    """
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = select(Swipe).where(
            Swipe.from_user_id == from_user_id,
            Swipe.to_user_id == to_user_id,
            Swipe.game == game,
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
                game=game,
                action=action,
                message=message if action == ActionType.LIKE else None,
            )
            session.add(swipe)

        is_match = False

        if action == ActionType.LIKE:
            reverse_stmt = select(Swipe).where(
                Swipe.from_user_id == to_user_id,
                Swipe.to_user_id == from_user_id,
                Swipe.game == game,
                Swipe.action == ActionType.LIKE,
            )
            reverse_swipe = (await session.execute(reverse_stmt)).scalar_one_or_none()

            if reverse_swipe:
                is_match = True
                swipe.is_mutual = True
                reverse_swipe.is_mutual = True

        await session.commit()
        return is_match


async def undo_swipe(from_user_id: int, to_user_id: int, game: str | None = None) -> bool:
    """Отменяет свайп. Возвращает True, если запись была удалена."""
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = select(Swipe).where(
            Swipe.from_user_id == from_user_id,
            Swipe.to_user_id == to_user_id,
            Swipe.game == game,
        )
        swipe = (await session.execute(stmt)).scalar_one_or_none()
        if not swipe:
            return False

        if swipe.is_mutual:
            reverse_stmt = select(Swipe).where(
                Swipe.from_user_id == to_user_id,
                Swipe.to_user_id == from_user_id,
                Swipe.game == game,
            )
            reverse_swipe = (await session.execute(reverse_stmt)).scalar_one_or_none()
            if reverse_swipe:
                reverse_swipe.is_mutual = False

        await session.delete(swipe)
        await session.commit()
        return True


def _pending_likes_conditions(user_id: int, game: str):
    """Условия для неотвеченных входящих лайков (ещё не просмотренных в «Мои лайки»)."""
    responded_subq = select(Swipe.to_user_id).where(
        Swipe.from_user_id == user_id,
        Swipe.game == game,
    )
    return (
        Swipe.to_user_id == user_id,
        Swipe.game == game,
        Swipe.action == ActionType.LIKE,
        Swipe.is_mutual == False,
        User.status != ProfileStatus.BANNED,
        not_(User.telegram_id.in_(responded_subq)),
    )


async def get_pending_likes_count(user_id: int, game: str | None = None) -> int:
    """Считает количество неотвеченных входящих лайков."""
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(User)
            .join(Swipe, Swipe.from_user_id == User.telegram_id)
            .where(*_pending_likes_conditions(user_id, game))
        )
        return (await session.execute(stmt)).scalar_one()


async def get_pending_likes_data(user_id: int, game: str | None = None) -> list[tuple[int, str | None]]:
    """Возвращает (telegram_id, message) неотвеченных лайков (сначала новые)."""
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = (
            select(User.telegram_id, Swipe.message)
            .join(Swipe, Swipe.from_user_id == User.telegram_id)
            .where(*_pending_likes_conditions(user_id, game))
            .order_by(Swipe.created_at.desc())
        )
        return list((await session.execute(stmt)).all())


async def get_pending_likes_ids(user_id: int, game: str | None = None) -> list[int]:
    """Возвращает ID пользователей с неотвеченными лайками (сначала новые)."""
    return [liker_id for liker_id, _ in await get_pending_likes_data(user_id, game)]


async def get_next_pending_like(user_id: int, game: str | None = None) -> User | None:
    """Получает первого пользователя из списка неотвеченных лайков."""
    user, _, _ = await get_pending_like_at_index(user_id, 0, game)
    return user


async def get_pending_like_at_index(
    user_id: int, index: int, game: str | None = None,
) -> tuple[User | None, int, str | None]:
    """Возвращает анкету по индексу, общее количество и сообщение к лайку (если есть)."""
    game = normalize_game(game)
    pending = await get_pending_likes_data(user_id, game)
    total = len(pending)
    if total == 0:
        return None, 0, None

    index = min(max(index, 0), total - 1)
    liker_id, message = pending[index]
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == liker_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        return _attach_view(user, game), total, message


async def add_report(
    from_user_id: int,
    to_user_id: int,
    reason: ReportReason,
    comment: str | None = None,
) -> int | None:
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
            comment=comment,
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


async def get_match_partner_ids(user_id: int, game: str | None = None) -> list[int]:
    """Возвращает ID напарников с взаимными лайками (сначала новые)."""
    game = normalize_game(game)
    reverse_swipe = aliased(Swipe)
    async with session_maker() as session:
        stmt = (
            select(Swipe.to_user_id)
            .join(User, User.telegram_id == Swipe.to_user_id)
            .join(
                reverse_swipe,
                (Swipe.to_user_id == reverse_swipe.from_user_id)
                & (Swipe.from_user_id == reverse_swipe.to_user_id)
                & (reverse_swipe.game == Swipe.game),
            )
            .where(
                Swipe.from_user_id == user_id,
                Swipe.game == game,
                Swipe.action == ActionType.LIKE,
                reverse_swipe.action == ActionType.LIKE,
            )
            .order_by(Swipe.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_match_at_index(user_id: int, index: int, game: str | None = None) -> tuple[User | None, int]:
    """Возвращает анкету мэтча по индексу и общее количество мэтчей."""
    game = normalize_game(game)
    partner_ids = await get_match_partner_ids(user_id, game)
    total = len(partner_ids)
    if total == 0:
        return None, 0

    index = min(max(index, 0), total - 1)
    async with session_maker() as session:
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id == partner_ids[index])
        user = (await session.execute(stmt)).scalar_one_or_none()
        return _attach_view(user, game), total


async def are_users_matched(user_a: int, user_b: int, game: str | None = None) -> bool:
    """Проверяет, есть ли взаимный лайк между пользователями."""
    partner_ids = await get_match_partner_ids(user_a, game)
    return user_b in partner_ids


async def get_teammate_rating(from_user_id: int, to_user_id: int, game: str | None = None) -> tuple[bool, bool]:
    """Возвращает (has_aura, has_vibe), поставленные from_user_id для to_user_id."""
    game = normalize_game(game)
    async with session_maker() as session:
        stmt = select(TeammateRating).where(
            TeammateRating.from_user_id == from_user_id,
            TeammateRating.to_user_id == to_user_id,
            TeammateRating.game == game,
        )
        rating = (await session.execute(stmt)).scalar_one_or_none()
        if not rating:
            return False, False
        return rating.has_aura, rating.has_vibe


async def get_reputation_counts(user_id: int, game: str | None = None) -> tuple[int, int]:
    """Возвращает (aura_count, vibe_count) — сколько раз пользователя оценили."""
    game = normalize_game(game)
    async with session_maker() as session:
        aura_stmt = select(func.count()).select_from(TeammateRating).where(
            TeammateRating.to_user_id == user_id,
            TeammateRating.game == game,
            TeammateRating.has_aura.is_(True),
        )
        vibe_stmt = select(func.count()).select_from(TeammateRating).where(
            TeammateRating.to_user_id == user_id,
            TeammateRating.game == game,
            TeammateRating.has_vibe.is_(True),
        )
        aura_count = (await session.execute(aura_stmt)).scalar_one()
        vibe_count = (await session.execute(vibe_stmt)).scalar_one()
        return aura_count, vibe_count


async def add_teammate_rating(
    from_user_id: int,
    to_user_id: int,
    *,
    aura: bool = False,
    vibe: bool = False,
    game: str | None = None,
) -> str | None:
    """
    Добавляет aura и/или vibe от мэтча. Можно дополнить вторую оценку позже.
    Возвращает None при успехе или текст ошибки.
    """
    if from_user_id == to_user_id:
        return "Нельзя оценить самого себя."

    game = normalize_game(game)
    if not await are_users_matched(from_user_id, to_user_id, game):
        return "Оценить можно только мэтчей."

    if not aura and not vibe:
        return "Нужно выбрать хотя бы одну оценку."

    async with session_maker() as session:
        stmt = select(TeammateRating).where(
            TeammateRating.from_user_id == from_user_id,
            TeammateRating.to_user_id == to_user_id,
            TeammateRating.game == game,
        )
        rating = (await session.execute(stmt)).scalar_one_or_none()

        if not rating:
            rating = TeammateRating(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                game=game,
                has_aura=aura,
                has_vibe=vibe,
            )
            session.add(rating)
            await session.commit()
            return None

        if aura:
            if rating.has_aura:
                return "Ты уже поставил 🔥 Aura этому игроку."
            rating.has_aura = True
        if vibe:
            if rating.has_vibe:
                return "Ты уже поставил 💜 Vibe этому игроку."
            rating.has_vibe = True

        rating.updated_at = datetime.utcnow()
        await session.commit()
        return None


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
        user = await session.get(User, telegram_id)
        if user and user.status == ProfileStatus.BANNED:
            ban_cache.add(telegram_id)
            return True
        return False


async def get_all_banned_ids() -> list[int]:
    async with session_maker() as session:
        from_table = set((await session.execute(select(BannedUser.telegram_id))).scalars().all())
        from_status = set((await session.execute(
            select(User.telegram_id).where(User.status == ProfileStatus.BANNED)
        )).scalars().all())
        return list(from_table | from_status)


async def ban_user(telegram_id: int, banned_by: int, reason: str | None = None) -> bool:
    from bot.services import ban_cache
    async with session_maker() as session:
        if await session.get(BannedUser, telegram_id):
            return False

        history_count = (await session.execute(
            select(func.count()).select_from(BanHistory).where(BanHistory.telegram_id == telegram_id)
        )).scalar_one()
        violation_number = history_count + 1

        session.add(BanHistory(
            telegram_id=telegram_id,
            banned_by=banned_by,
            reason=reason,
            violation_number=violation_number,
        ))
        session.add(BannedUser(
            telegram_id=telegram_id,
            banned_by=banned_by,
            reason=reason,
            violation_number=violation_number,
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
        logging.info(
            "Пользователь %s заблокирован админом %s (нарушение #%d).",
            telegram_id, banned_by, violation_number,
        )
        return True


async def get_banned_users_count() -> int:
    async with session_maker() as session:
        stmt = select(func.count()).select_from(BannedUser)
        return (await session.execute(stmt)).scalar_one()


async def get_banned_user_at_index(index: int) -> tuple[BannedUser | None, User | None, int]:
    async with session_maker() as session:
        total = (await session.execute(select(func.count()).select_from(BannedUser))).scalar_one()
        if total == 0:
            return None, None, 0

        index = min(max(index, 0), total - 1)
        stmt = (
            select(BannedUser)
            .order_by(BannedUser.banned_at.desc())
            .offset(index)
            .limit(1)
        )
        banned = (await session.execute(stmt)).scalar_one_or_none()
        if not banned:
            return None, None, total

        user = await session.get(User, banned.telegram_id)
        return banned, user, total


async def unban_user(telegram_id: int) -> bool:
    from bot.services import ban_cache
    async with session_maker() as session:
        banned = await session.get(BannedUser, telegram_id)
        if not banned:
            return False

        history_entry = (await session.execute(
            select(BanHistory)
            .where(
                BanHistory.telegram_id == telegram_id,
                BanHistory.unbanned_at.is_(None),
            )
            .order_by(BanHistory.banned_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if history_entry:
            history_entry.unbanned_at = datetime.utcnow()

        await session.delete(banned)

        user = await session.get(User, telegram_id)
        if user and user.status == ProfileStatus.BANNED:
            user.status = ProfileStatus.ACTIVE

        await session.commit()
        ban_cache.remove(telegram_id)
        logging.info("Пользователь %s разблокирован.", telegram_id)
        return True


async def get_ban_history(telegram_id: int) -> list[BanHistory]:
    async with session_maker() as session:
        stmt = (
            select(BanHistory)
            .where(BanHistory.telegram_id == telegram_id)
            .order_by(BanHistory.banned_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_current_ban(telegram_id: int) -> BannedUser | None:
    async with session_maker() as session:
        return await session.get(BannedUser, telegram_id)


async def has_been_banned_before(telegram_id: int) -> bool:
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(BanHistory)
            .where(
                BanHistory.telegram_id == telegram_id,
                BanHistory.unbanned_at.is_not(None),
            )
        )
        return (await session.execute(stmt)).scalar_one() > 0


async def add_unban_request(user_id: int, message: str) -> int | None:
    async with session_maker() as session:
        pending = (await session.execute(
            select(UnbanRequest).where(
                UnbanRequest.user_id == user_id,
                UnbanRequest.status == UnbanRequestStatus.PENDING,
            )
        )).scalar_one_or_none()
        if pending:
            return None

        request = UnbanRequest(user_id=user_id, message=message)
        session.add(request)
        await session.commit()
        await session.refresh(request)
        return request.id


async def has_pending_unban_request(user_id: int) -> bool:
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(UnbanRequest)
            .where(
                UnbanRequest.user_id == user_id,
                UnbanRequest.status == UnbanRequestStatus.PENDING,
            )
        )
        return (await session.execute(stmt)).scalar_one() > 0


async def get_pending_unban_requests_count() -> int:
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(UnbanRequest)
            .where(UnbanRequest.status == UnbanRequestStatus.PENDING)
        )
        return (await session.execute(stmt)).scalar_one()


async def get_pending_unban_request_ids() -> list[int]:
    async with session_maker() as session:
        stmt = (
            select(UnbanRequest.id)
            .where(UnbanRequest.status == UnbanRequestStatus.PENDING)
            .order_by(UnbanRequest.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_unban_request_by_id(request_id: int) -> UnbanRequest | None:
    async with session_maker() as session:
        return await session.get(UnbanRequest, request_id)


async def approve_unban_request(request_id: int, admin_id: int) -> bool:
    async with session_maker() as session:
        request = await session.get(UnbanRequest, request_id)
        if not request or request.status != UnbanRequestStatus.PENDING:
            return False

        banned = await session.get(BannedUser, request.user_id)
        if banned:
            history_entry = (await session.execute(
                select(BanHistory)
                .where(
                    BanHistory.telegram_id == request.user_id,
                    BanHistory.unbanned_at.is_(None),
                )
                .order_by(BanHistory.banned_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if history_entry:
                history_entry.unbanned_at = datetime.utcnow()
            await session.delete(banned)

            user = await session.get(User, request.user_id)
            if user and user.status == ProfileStatus.BANNED:
                user.status = ProfileStatus.ACTIVE

        request.status = UnbanRequestStatus.APPROVED
        request.resolved_at = datetime.utcnow()
        request.resolved_by = admin_id
        await session.commit()

        from bot.services import ban_cache
        ban_cache.remove(request.user_id)
        return True


async def reject_unban_request(request_id: int, admin_id: int) -> bool:
    async with session_maker() as session:
        request = await session.get(UnbanRequest, request_id)
        if not request or request.status != UnbanRequestStatus.PENDING:
            return False
        request.status = UnbanRequestStatus.REJECTED
        request.resolved_at = datetime.utcnow()
        request.resolved_by = admin_id
        await session.commit()
        return True


async def get_profile_stats() -> dict[str, int]:
    async with session_maker() as session:
        user_rows = (await session.execute(
            select(User.status, func.count()).group_by(User.status)
        )).all()
        user_counts = {status.value: count for status, count in user_rows}
        game_rows = (await session.execute(
            select(GameProfile.status, func.count()).group_by(GameProfile.status)
        )).all()
        game_counts = {status.value: count for status, count in game_rows}
        banned = user_counts.get(ProfileStatus.BANNED.value, 0)
        active = game_counts.get(ProfileStatus.ACTIVE.value, 0)
        hidden = game_counts.get(ProfileStatus.HIDDEN.value, 0)
        incomplete = game_counts.get(ProfileStatus.INCOMPLETE.value, 0)
        registered = user_counts.get(ProfileStatus.ACTIVE.value, 0) + banned
        return {
            "active": active,
            "hidden": hidden,
            "banned": banned,
            "incomplete": incomplete,
            "registered": registered,
            "total": registered + user_counts.get(ProfileStatus.INCOMPLETE.value, 0),
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
        stmt = select(User).options(*_user_load_options()).where(User.telegram_id.in_(user_ids))
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


async def add_bug_feedback(user_id: int, text: str) -> int:
    async with session_maker() as session:
        feedback = BugFeedback(user_id=user_id, text=text, status=FeedbackStatus.PENDING)
        session.add(feedback)
        await session.commit()
        await session.refresh(feedback)
        return feedback.id


async def get_pending_feedback_count() -> int:
    async with session_maker() as session:
        stmt = (
            select(func.count())
            .select_from(BugFeedback)
            .where(BugFeedback.status == FeedbackStatus.PENDING)
        )
        return (await session.execute(stmt)).scalar_one()


async def get_pending_feedback_ids() -> list[int]:
    async with session_maker() as session:
        stmt = (
            select(BugFeedback.id)
            .where(BugFeedback.status == FeedbackStatus.PENDING)
            .order_by(BugFeedback.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def get_feedback_by_id(feedback_id: int) -> BugFeedback | None:
    async with session_maker() as session:
        return await session.get(BugFeedback, feedback_id)


async def mark_feedback_read(feedback_id: int) -> bool:
    async with session_maker() as session:
        feedback = await session.get(BugFeedback, feedback_id)
        if not feedback or feedback.status != FeedbackStatus.PENDING:
            return False
        feedback.status = FeedbackStatus.READ
        await session.commit()
        return True