import logging
from sqlalchemy import select
from bot.database.engine import session_maker
from bot.database.models import User, SearchSettings, ProfileStatus


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


from sqlalchemy import select, and_, not_, exists
from bot.database.models import SearchSettings, Swipe, ActionType


async def get_next_profile(user_id: int) -> User | None:
    """Ищет следующую подходящую анкету для пользователя"""
    async with session_maker() as session:
        # 1. Получаем настройки поиска текущего юзера
        stmt_settings = select(SearchSettings).where(SearchSettings.user_id == user_id)
        res_settings = await session.execute(stmt_settings)
        settings = res_settings.scalar_one_or_none()

        # 2. Строим базовый запрос для поиска других активных анкет
        stmt = select(User).where(
            User.status == ProfileStatus.ACTIVE,
            User.telegram_id != user_id
        )

        # Исключаем пользователей, которых текущий юзер уже лайкнул или дизлайкнул
        swipe_exists = exists().where(
            and_(
                Swipe.from_user_id == user_id,
                Swipe.to_user_id == User.telegram_id
            )
        )
        stmt = stmt.where(not_(swipe_exists))

        # 3. Применяем фильтры настроек, если они есть
        if settings:
            if settings.min_age is not None:
                stmt = stmt.where(User.age >= settings.min_age)
            if settings.max_age is not None:
                stmt = stmt.where(User.age <= settings.max_age)
            if settings.min_mmr is not None:
                stmt = stmt.where(User.mmr >= settings.min_mmr)
            if settings.max_mmr is not None:
                stmt = stmt.where(User.mmr <= settings.max_mmr)
            if settings.wanted_positions:
                # В PostgreSQL проверяем пересечение массивов ролей через overlap (&&)
                stmt = stmt.where(User.positions.overlap(settings.wanted_positions))

        # Берем первую попавшуюся анкету
        stmt = stmt.limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


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


async def get_next_pending_like(user_id: int) -> User | None:
    """Получает следующего активного пользователя, который лайкнул нашего юзера"""
    async with session_maker() as session:
        # Ищем пользователей, от которых есть входящий LIKE, но нет взаимности
        stmt = select(User).join(
            Swipe, Swipe.from_user_id == User.telegram_id
        ).where(
            Swipe.to_user_id == user_id,
            Swipe.action == ActionType.LIKE,
            Swipe.is_mutual == False,
            User.status == ProfileStatus.ACTIVE
        )

        # Исключаем тех, кого текущий юзер уже успел свайпнуть (лайкнуть/дизлайкнуть) в ответ
        stmt_exclude = select(Swipe.to_user_id).where(Swipe.from_user_id == user_id)
        stmt = stmt.where(not_(User.telegram_id.in_(stmt_exclude)))

        stmt = stmt.limit(1)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()