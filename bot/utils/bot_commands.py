from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands

CMD_BROWSE = "browse"
CMD_PROFILE = "profile"
CMD_LIKES = "likes"
CMD_MATCHES = "matches"
CMD_RULES = "rules"
CMD_FEEDBACK = "feedback"

BOT_COMMANDS = [
    BotCommand(command=CMD_BROWSE, description="🔍 Смотреть анкеты"),
    BotCommand(command=CMD_PROFILE, description="👤 Моя анкета"),
    BotCommand(command=CMD_LIKES, description="❤️ Мои лайки"),
    BotCommand(command=CMD_MATCHES, description="💚 Мои мэтчи"),
    BotCommand(command=CMD_RULES, description="📜 Правила"),
    BotCommand(command=CMD_FEEDBACK, description="🐛 Сообщить о баге"),
]

def normalize_command(text: str | None) -> str | None:
    if not text or not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lower()


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
