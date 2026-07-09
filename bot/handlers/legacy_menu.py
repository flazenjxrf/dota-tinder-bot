from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

router = Router()

LEGACY_MENU_TEXTS = {
    "🔍 Смотреть анкеты",
    "👤 Моя анкета",
    "❤️ Мои лайки",
    "💚 Мои мэтчи",
    "📜 Правила",
}


@router.message(F.text.in_(LEGACY_MENU_TEXTS))
async def handle_legacy_menu(message: Message, state: FSMContext):
    """Старые reply-кнопки — перенаправляем на те же действия, что и команды."""
    from bot.handlers.swiping import start_swiping
    from bot.handlers.profile import show_my_profile
    from bot.handlers.likes import start_viewing_likes
    from bot.handlers.matches import start_viewing_matches
    from bot.handlers.start import show_rules
    from bot.keyboards.reply import hide_reply_keyboard

    handlers = {
        "🔍 Смотреть анкеты": start_swiping,
        "👤 Моя анкета": show_my_profile,
        "❤️ Мои лайки": start_viewing_likes,
        "💚 Мои мэтчи": start_viewing_matches,
        "📜 Правила": show_rules,
    }
    await hide_reply_keyboard(message)
    await handlers[message.text](message, state)
