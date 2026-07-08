from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

# ================= 1. ФАБРИКИ КОЛЛБЕКОВ =================

# Для выбора ролей при регистрации
class PositionCallback(CallbackData, prefix="pos"):
    id: int

# Для выбора ролей при настройке поиска
class SearchPositionCallback(CallbackData, prefix="search_pos"):
    id: int

# Для обычных свайпов
class SwipeCallback(CallbackData, prefix="sw"):
    action: str  # "like" или "dislike"
    to_user_id: int

# Для ответа на входящие лайки
class LikeBackCallback(CallbackData, prefix="lb"):
    action: str  # "like" или "dislike"
    from_user_id: int
    index: int = 0

class LikeNavCallback(CallbackData, prefix="ln"):
    index: int

# Для подачи жалобы
class ReportCallback(CallbackData, prefix="rep"):
    to_user_id: int
    context: str  # "swipe" или "likes"
    index: int = 0

class ReportReasonCallback(CallbackData, prefix="rep_r"):
    to_user_id: int
    context: str
    reason: str
    index: int = 0


# ================= 2. КЛАВИАТУРЫ РЕГИСТРАЦИИ И ПОИСКА =================

def get_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заполнить анкету", callback_data="start_registration")
    return builder.as_markup()

def get_positions_keyboard(selected_positions: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    positions = {1: "Керри", 2: "Мидер", 3: "Тройка", 4: "Саппорт"}
    for pos_id, name in positions.items():
        mark = "✅ " if pos_id in selected_positions else ""
        builder.button(text=f"{mark}{name}", callback_data=PositionCallback(id=pos_id).pack())
    builder.button(text="➡️ Подтвердить выбор", callback_data="confirm_positions")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_profile_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё супер, оставить так", callback_data="profile_ok")
    builder.button(text="🔄 Заполнить заново", callback_data="start_registration")
    builder.adjust(1)
    return builder.as_markup()

def get_search_positions_keyboard(selected_positions: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    positions = {1: "Керри", 2: "Мидер", 3: "Тройка", 4: "Саппорт"}
    for pos_id, name in positions.items():
        mark = "✅ " if pos_id in selected_positions else ""
        builder.button(text=f"{mark}{name}", callback_data=SearchPositionCallback(id=pos_id).pack())
    builder.button(text="➡️ Подтвердить и продолжить", callback_data="confirm_search_positions")
    builder.adjust(1)
    return builder.as_markup()

def get_skip_keyboard(step: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить (Не важно)", callback_data=f"skip_{step}")
    return builder.as_markup()


# ================= 3. КЛАВИАТУРЫ ПРОФИЛЯ И РЕДАКТИРОВАНИЯ =================

def get_profile_menu_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать анкету", callback_data="menu_edit_profile")
    builder.button(text="⚙️ Фильтры поиска", callback_data="menu_edit_settings")
    # Кнопка скрыть/показать профиль
    status_text = "⏸ Скрыть анкету" if is_active else "▶️ Показать в поиске"
    builder.button(text=status_text, callback_data="profile_toggle_status")
    builder.adjust(1)
    return builder.as_markup()

def get_edit_profile_fields_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Имя", callback_data="edit_field_name")
    builder.button(text="Возраст", callback_data="edit_field_age")
    builder.button(text="Город", callback_data="edit_field_city")
    builder.button(text="Роли (Дота)", callback_data="edit_field_positions")
    builder.button(text="MMR", callback_data="edit_field_mmr")
    builder.button(text="О себе", callback_data="edit_field_bio")
    builder.button(text="Фото", callback_data="edit_field_photo")
    builder.button(text="⬅️ Назад к анкете", callback_data="back_to_profile")
    builder.adjust(2, 2, 2, 1, 1) # Разметка кнопок по сетке
    return builder.as_markup()

def get_edit_settings_fields_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Роли поиска", callback_data="edit_filter_positions")
    builder.button(text="Мин. возраст", callback_data="edit_filter_min_age")
    builder.button(text="Макс. возраст", callback_data="edit_filter_max_age")
    builder.button(text="Мин. MMR", callback_data="edit_filter_min_mmr")
    builder.button(text="Макс. MMR", callback_data="edit_filter_max_mmr")
    builder.button(text="⬅️ Назад к анкете", callback_data="back_to_profile")
    builder.adjust(1, 2, 2, 1)
    return builder.as_markup()


# ================= 4. КЛАВИАТУРЫ СВАЙПОВ И ЛАЙКОВ =================

REPORT_REASON_LABELS = {
    "inappropriate_photo": "📷 Неприемлемое фото",
    "spam": "📢 Спам / реклама",
    "offensive": "💬 Оскорбления в анкете",
    "fake": "🎭 Фейковая анкета",
    "other": "❓ Другое",
}


def get_swipe_keyboard(to_user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👎 Дизлайк", callback_data=SwipeCallback(action="dislike", to_user_id=to_user_id).pack())
    builder.button(text="❤️ Лайк", callback_data=SwipeCallback(action="like", to_user_id=to_user_id).pack())
    builder.button(text="🚨 Жалоба", callback_data=ReportCallback(to_user_id=to_user_id, context="swipe").pack())
    builder.adjust(2, 1)
    return builder.as_markup()

def get_likeback_keyboard(from_user_id: int, index: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav_count = 0
    if total > 1:
        if index > 0:
            builder.button(text="⬅️", callback_data=LikeNavCallback(index=index - 1).pack())
            nav_count += 1
        builder.button(text=f"{index + 1}/{total}", callback_data="likes_counter")
        nav_count += 1
        if index < total - 1:
            builder.button(text="➡️", callback_data=LikeNavCallback(index=index + 1).pack())
            nav_count += 1
    builder.button(
        text="👎 Дизлайк",
        callback_data=LikeBackCallback(action="dislike", from_user_id=from_user_id, index=index).pack(),
    )
    builder.button(
        text="❤️ Лайк в ответ",
        callback_data=LikeBackCallback(action="like", from_user_id=from_user_id, index=index).pack(),
    )
    builder.button(
        text="🚨 Жалоба",
        callback_data=ReportCallback(to_user_id=from_user_id, context="likes", index=index).pack(),
    )
    if total > 1:
        builder.adjust(nav_count, 2, 1)
    else:
        builder.adjust(2, 1)
    return builder.as_markup()


def get_report_reasons_keyboard(to_user_id: int, context: str, index: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reason_key, label in REPORT_REASON_LABELS.items():
        builder.button(
            text=label,
            callback_data=ReportReasonCallback(
                to_user_id=to_user_id,
                context=context,
                reason=reason_key,
                index=index,
            ).pack(),
        )
    builder.button(text="⬅️ Отмена", callback_data="report_cancel")
    builder.adjust(1)
    return builder.as_markup()