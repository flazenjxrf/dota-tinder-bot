from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

router = Router()


@router.message(F.text)
async def ignore_unknown_text(message: Message, state: FSMContext):
    """Игнорирует случайный текст вне сценария — меню команд доступно через Telegram."""
    return
