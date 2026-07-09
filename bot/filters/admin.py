from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.config import ADMIN_IDS


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and user.id in ADMIN_IDS)
