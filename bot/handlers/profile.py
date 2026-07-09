from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.requests import (
    get_user_with_settings,
    update_user_field,
    update_settings_field,
    delete_user_profile,
)
from bot.database.models import ProfileStatus
from bot.states.fsm import EditProfile, EditSettings
from bot.keyboards.inline import (
    get_profile_menu_keyboard,
    get_edit_profile_fields_keyboard,
    get_edit_settings_fields_keyboard,
    get_positions_keyboard,
    PositionCallback,
    get_search_positions_keyboard,
    SearchPositionCallback,
    get_delete_profile_confirm_keyboard,
    get_consent_keyboard,
)
from bot.handlers.start import CONSENT_TEXT
from bot.utils.bot_commands import CMD_PROFILE
from bot.utils.city import format_city_display

router = Router()

positions_mapping = {
    1: "Керри",
    2: "Мидер",
    3: "Тройка",
    4: "Саппорт"
}


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def make_profile_caption(user) -> str:
    """Генерирует красивый текст карточки профиля"""
    pos_names = [positions_mapping[p] for p in sorted(user.positions)]
    pos_str = ", ".join(pos_names)
    status_emoji = "🟢 Активна" if user.status == ProfileStatus.ACTIVE else "🔴 Скрыта"

    caption = (
        f"👤 <b>Твой профиль:</b>\n\n"
        f"🌟 <b>{user.name}</b>, {user.age} | {format_city_display(user)}\n"
        f"🎯 Роли: {pos_str}\n"
        f"🏆 MMR: {user.mmr}\n\n"
        f"💬 О себе:\n{user.bio}\n\n"
        f"📢 Статус анкеты: {status_emoji}\n"
    )
    return caption


async def send_my_profile_message(message: Message, telegram_id: int):
    """Отправляет новую карточку профиля с фото и кнопками меню"""
    user = await get_user_with_settings(telegram_id)
    if not user or user.status == ProfileStatus.INCOMPLETE:
        await message.answer("У тебя еще нет анкеты. Нажми /start, чтобы создать её!")
        return

    caption = make_profile_caption(user)
    is_active = (user.status == ProfileStatus.ACTIVE)

    await message.answer_photo(
        photo=user.photo_file_id,
        caption=caption,
        reply_markup=get_profile_menu_keyboard(is_active)
    )


async def send_my_settings_message(message: Message, telegram_id: int):
    """Отправляет текстовое сообщение с текущими фильтрами и меню настроек"""
    user = await get_user_with_settings(telegram_id)
    s = user.settings

    wanted_positions = "Любые"
    if s.wanted_positions:
        wanted_positions = ", ".join([positions_mapping[p] for p in sorted(s.wanted_positions)])

    filters_text = (
        f"⚙️ <b>Твои фильтры поиска напарников:</b>\n\n"
        f"🎯 Искомые роли: {wanted_positions}\n"
        f"🔞 Возраст: от {s.min_age or 'любого'} до {s.max_age or 'любого'}\n"
        f"🏆 MMR: от {s.min_mmr or 'любого'} до {s.max_mmr or 'любого'}\n\n"
        f"Выберите параметр для изменения:"
    )
    await message.answer(filters_text, reply_markup=get_edit_settings_fields_keyboard())


# ================= ОТОБРАЖЕНИЕ ПРОФИЛЯ =================

@router.message(Command(CMD_PROFILE))
async def show_my_profile(message: Message, state: FSMContext):
    await state.clear()
    await send_my_profile_message(message, message.from_user.id)


# Возврат к меню профиля по инлайн-кнопке (редактируем старое сообщение)
# Возврат к меню профиля по инлайн-кнопке
@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_with_settings(callback.from_user.id)
    is_active = (user.status == ProfileStatus.ACTIVE)
    caption = make_profile_caption(user)

    # Проверяем, есть ли фото в сообщении, с которого пришел клик
    if callback.message.photo:
        # Если это фото-карточка, просто обновляем её описание на месте
        await callback.message.edit_caption(
            caption=caption,
            reply_markup=get_profile_menu_keyboard(is_active)
        )
    else:
        # Если это было текстовое сообщение (после настройки MMR/возраста),
        # мы удаляем его, чтобы не захламлять чат, и присылаем новую фото-карточку
        await callback.message.delete()
        await send_my_profile_message(callback.message, callback.from_user.id)

    await callback.answer()


# ================= СКРЫТЬ/ПОКАЗАТЬ АНКЕТУ =================

@router.callback_query(F.data == "profile_toggle_status")
async def toggle_profile_status(callback: CallbackQuery):
    user = await get_user_with_settings(callback.from_user.id)
    new_status = ProfileStatus.HIDDEN if user.status == ProfileStatus.ACTIVE else ProfileStatus.ACTIVE

    await update_user_field(user.telegram_id, "status", new_status)

    user.status = new_status
    is_active = (new_status == ProfileStatus.ACTIVE)
    await callback.message.edit_caption(
        caption=make_profile_caption(user),
        reply_markup=get_profile_menu_keyboard(is_active)
    )
    await callback.answer(f"Статус изменен на {'Показывается' if is_active else 'Скрыт'}!")


# ================= УДАЛЕНИЕ АНКЕТЫ =================

DELETE_CONFIRM_TEXT = (
    "🗑 <b>Удалить анкету?</b>\n\n"
    "Это необратимо: пропадут мэтчи, лайки, фильтры и все данные профиля.\n\n"
    "Если нужна только пауза — нажми «Отмена» и используй «Скрыть анкету»."
)


@router.callback_query(F.data == "profile_delete")
async def profile_delete_prompt(callback: CallbackQuery):
    await callback.message.edit_caption(
        caption=DELETE_CONFIRM_TEXT,
        reply_markup=get_delete_profile_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "profile_delete_cancel")
async def profile_delete_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_with_settings(callback.from_user.id)
    if not user:
        await callback.answer("Анкета уже удалена.", show_alert=True)
        return

    is_active = user.status == ProfileStatus.ACTIVE
    await callback.message.edit_caption(
        caption=make_profile_caption(user),
        reply_markup=get_profile_menu_keyboard(is_active),
    )
    await callback.answer()


@router.callback_query(F.data == "profile_delete_confirm")
async def profile_delete_confirm(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    if not await delete_user_profile(telegram_id):
        await callback.answer("Анкета уже удалена.", show_alert=True)
        return

    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🗑 <b>Анкета удалена.</b>\n\n"
        "Мэтчи, лайки и все данные профиля удалены.\n"
        "Чтобы создать новую анкету, сначала прими соглашение:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.message.answer(CONSENT_TEXT, reply_markup=get_consent_keyboard())
    await callback.answer()


# ================= МЕНЮ РЕДАКТИРОВАНИЯ =================

@router.callback_query(F.data == "menu_edit_profile")
async def edit_profile_menu(callback: CallbackQuery):
    await callback.message.edit_caption(
        caption="🛠 <b>Что именно ты хочешь изменить в своей анкете?</b>",
        reply_markup=get_edit_profile_fields_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "menu_edit_settings")
async def edit_settings_menu(callback: CallbackQuery):
    user = await get_user_with_settings(callback.from_user.id)
    s = user.settings

    wanted_positions = "Любые"
    if s.wanted_positions:
        wanted_positions = ", ".join([positions_mapping[p] for p in sorted(s.wanted_positions)])

    filters_text = (
        f"⚙️ <b>Твои фильтры поиска напарников:</b>\n\n"
        f"🎯 Искомые роли: {wanted_positions}\n"
        f"🔞 Возраст: от {s.min_age or 'любого'} до {s.max_age or 'любого'}\n"
        f"🏆 MMR: от {s.min_mmr or 'любого'} до {s.max_mmr or 'любого'}\n\n"
        f"Выберите параметр для изменения:"
    )

    await callback.message.edit_caption(
        caption=filters_text,
        reply_markup=get_edit_settings_fields_keyboard()
    )
    await callback.answer()


# ================= ТОЧЕЧНОЕ РЕДАКТИРОВАНИЕ ПОЛЕЙ АНКЕТЫ =================

# --- Изменение Имени ---
@router.callback_query(F.data == "edit_field_name")
async def edit_name_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваше новое имя или никнейм:")
    await state.set_state(EditProfile.name)
    await callback.answer()


@router.message(EditProfile.name)
async def edit_name_finish(message: Message, state: FSMContext):
    await update_user_field(message.from_user.id, "name", message.text)
    await state.clear()
    await message.answer("✅ Имя успешно обновлено!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение Возраста ---
@router.callback_query(F.data == "edit_field_age")
async def edit_age_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Сколько тебе лет?")
    await state.set_state(EditProfile.age)
    await callback.answer()


@router.message(EditProfile.age)
async def edit_age_finish(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (10 <= int(message.text) <= 100):
        await message.answer("Пожалуйста, введи корректный возраст числом.")
        return
    await update_user_field(message.from_user.id, "age", int(message.text))
    await state.clear()
    await message.answer("✅ Возраст успешно обновлен!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение Города ---
@router.callback_query(F.data == "edit_field_city")
async def edit_city_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Из какого ты города?")
    await state.set_state(EditProfile.city)
    await callback.answer()


@router.message(EditProfile.city)
async def edit_city_finish(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введи название города.")
        return
    await update_user_field(message.from_user.id, "city", message.text.strip())
    await state.clear()
    await message.answer("✅ Город успешно обновлен!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение MMR ---
@router.callback_query(F.data == "edit_field_mmr")
async def edit_mmr_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваш новый MMR цифрами:")
    await state.set_state(EditProfile.mmr)
    await callback.answer()


@router.message(EditProfile.mmr)
async def edit_mmr_finish(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введи корректный MMR цифрами.")
        return
    await update_user_field(message.from_user.id, "mmr", int(message.text))
    await state.clear()
    await message.answer("✅ MMR успешно обновлен!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение О себе ---
@router.callback_query(F.data == "edit_field_bio")
async def edit_bio_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Пришлите новый текст 'О себе':")
    await state.set_state(EditProfile.bio)
    await callback.answer()


@router.message(EditProfile.bio)
async def edit_bio_finish(message: Message, state: FSMContext):
    await update_user_field(message.from_user.id, "bio", message.text)
    await state.clear()
    await message.answer("✅ Текст 'О себе' изменен!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение Фото ---
@router.callback_query(F.data == "edit_field_photo")
async def edit_photo_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Загрузите новую фотографию:")
    await state.set_state(EditProfile.photo)
    await callback.answer()


@router.message(EditProfile.photo, F.photo)
async def edit_photo_finish(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await update_user_field(message.from_user.id, "photo_file_id", photo_file_id)
    await state.clear()
    await message.answer("✅ Фото успешно изменено!")
    await send_my_profile_message(message, message.from_user.id)


# --- Изменение Ролей игрока ---
@router.callback_query(F.data == "edit_field_positions")
async def edit_positions_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user_with_settings(callback.from_user.id)
    await state.update_data(positions=user.positions)

    await callback.message.edit_caption(
        caption="Выберите новые роли:",
        reply_markup=get_positions_keyboard(user.positions)
    )
    await state.set_state(EditProfile.positions)
    await callback.answer()


@router.callback_query(EditProfile.positions, PositionCallback.filter())
async def toggle_edit_position(callback: CallbackQuery, callback_data: PositionCallback, state: FSMContext):
    data = await state.get_data()
    positions = data.get("positions", [])

    pos_id = callback_data.id
    if pos_id in positions:
        positions.remove(pos_id)
    else:
        positions.append(pos_id)

    await state.update_data(positions=positions)
    await callback.message.edit_reply_markup(reply_markup=get_positions_keyboard(positions))
    await callback.answer()


@router.callback_query(EditProfile.positions, F.data == "confirm_positions")
async def confirm_edit_positions(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("positions"):
        await callback.answer("Выберите хотя бы одну позицию!", show_alert=True)
        return

    await update_user_field(callback.from_user.id, "positions", data["positions"])
    await state.clear()

    user = await get_user_with_settings(callback.from_user.id)
    caption = make_profile_caption(user)
    is_active = (user.status == ProfileStatus.ACTIVE)

    await callback.message.edit_caption(
        caption=f"✅ Роли успешно изменены!\n\n{caption}",
        reply_markup=get_profile_menu_keyboard(is_active)
    )
    await callback.answer()


# ================= ТОЧЕЧНОЕ РЕДАКТИРОВАНИЕ НАСТРОЕК ПОИСКА (ФИЛЬТРОВ) =================

# Вспомогательный клавиатурный конструктор кнопки "Сбросить"
def get_reset_button(field: str):
    b = InlineKeyboardBuilder()
    b.button(text="❌ Сбросить (Любой)", callback_data=f"reset_filter_{field}")
    return b.as_markup()


# --- Мин. Возраст ---
@router.callback_query(F.data == "edit_filter_min_age")
async def edit_filter_min_age_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите минимальный возраст для поиска напарников:",
        reply_markup=get_reset_button("min_age")
    )
    await state.set_state(EditSettings.min_age)
    await callback.answer()


@router.message(EditSettings.min_age)
async def edit_filter_min_age_finish(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число или нажмите кнопку сброса.")
        return
    await update_settings_field(message.from_user.id, "min_age", int(message.text))
    await state.clear()
    await message.answer("✅ Минимальный возраст поиска обновлен!")
    await send_my_settings_message(message, message.from_user.id)


@router.callback_query(F.data == "reset_filter_min_age", EditSettings.min_age)
async def reset_filter_min_age(callback: CallbackQuery, state: FSMContext):
    await update_settings_field(callback.from_user.id, "min_age", None)
    await state.clear()
    await callback.message.delete()  # Удаляем системное сообщение с кнопкой сброса
    await callback.message.answer("✅ Фильтр минимального возраста сброшен!")
    await send_my_settings_message(callback.message, callback.from_user.id)
    await callback.answer()


# --- Макс. Возраст ---
@router.callback_query(F.data == "edit_filter_max_age")
async def edit_filter_max_age_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите максимальный возраст для поиска напарников:",
        reply_markup=get_reset_button("max_age")
    )
    await state.set_state(EditSettings.max_age)
    await callback.answer()


@router.message(EditSettings.max_age)
async def edit_filter_max_age_finish(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число или нажмите кнопку сброса.")
        return
    await update_settings_field(message.from_user.id, "max_age", int(message.text))
    await state.clear()
    await message.answer("✅ Максимальный возраст поиска обновлен!")
    await send_my_settings_message(message, message.from_user.id)


@router.callback_query(F.data == "reset_filter_max_age", EditSettings.max_age)
async def reset_filter_max_age(callback: CallbackQuery, state: FSMContext):
    await update_settings_field(callback.from_user.id, "max_age", None)
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("✅ Фильтр максимального возраста сброшен!")
    await send_my_settings_message(callback.message, callback.from_user.id)
    await callback.answer()


# --- Мин. MMR ---
@router.callback_query(F.data == "edit_filter_min_mmr")
async def edit_filter_min_mmr_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите минимальный MMR для поиска напарников:",
        reply_markup=get_reset_button("min_mmr")
    )
    await state.set_state(EditSettings.min_mmr)
    await callback.answer()


@router.message(EditSettings.min_mmr)
async def edit_filter_min_mmr_finish(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число или нажмите кнопку сброса.")
        return
    await update_settings_field(message.from_user.id, "min_mmr", int(message.text))
    await state.clear()
    await message.answer("✅ Минимальный MMR поиска обновлен!")
    await send_my_settings_message(message, message.from_user.id)


@router.callback_query(F.data == "reset_filter_min_mmr", EditSettings.min_mmr)
async def reset_filter_min_mmr(callback: CallbackQuery, state: FSMContext):
    await update_settings_field(callback.from_user.id, "min_mmr", None)
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("✅ Фильтр минимального рейтинга сброшен!")
    await send_my_settings_message(callback.message, callback.from_user.id)
    await callback.answer()


# --- Макс. MMR ---
@router.callback_query(F.data == "edit_filter_max_mmr")
async def edit_filter_max_mmr_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите максимальный MMR для поиска напарников:",
        reply_markup=get_reset_button("max_mmr")
    )
    await state.set_state(EditSettings.max_mmr)
    await callback.answer()


@router.message(EditSettings.max_mmr)
async def edit_filter_max_mmr_finish(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число или нажмите кнопку сброса.")
        return
    await update_settings_field(message.from_user.id, "max_mmr", int(message.text))
    await state.clear()
    await message.answer("✅ Максимальный MMR поиска обновлен!")
    await send_my_settings_message(message, message.from_user.id)


@router.callback_query(F.data == "reset_filter_max_mmr", EditSettings.max_mmr)
async def reset_filter_max_mmr(callback: CallbackQuery, state: FSMContext):
    await update_settings_field(callback.from_user.id, "max_mmr", None)
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("✅ Фильтр максимального рейтинга сброшен!")
    await send_my_settings_message(callback.message, callback.from_user.id)
    await callback.answer()


# --- Роли для Поиска ---
@router.callback_query(F.data == "edit_filter_positions")
async def edit_filter_positions_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user_with_settings(callback.from_user.id)
    s = user.settings
    positions = s.wanted_positions or []
    await state.update_data(wanted_positions=positions)

    await callback.message.edit_caption(
        caption="Выберите роли для поиска:",
        reply_markup=get_search_positions_keyboard(positions)
    )
    await state.set_state(EditSettings.positions)
    await callback.answer()


@router.callback_query(EditSettings.positions, SearchPositionCallback.filter())
async def toggle_edit_search_position(callback: CallbackQuery, callback_data: SearchPositionCallback,
                                      state: FSMContext):
    data = await state.get_data()
    positions = data.get("wanted_positions", [])

    pos_id = callback_data.id
    if pos_id in positions:
        positions.remove(pos_id)
    else:
        positions.append(pos_id)

    await state.update_data(wanted_positions=positions)
    await callback.message.edit_reply_markup(reply_markup=get_search_positions_keyboard(positions))
    await callback.answer()


@router.callback_query(EditSettings.positions, F.data == "confirm_search_positions")
async def confirm_edit_search_positions(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    positions_to_save = data.get("wanted_positions") or None  # Если ролей нет, пишем None (ищет любые)

    await update_settings_field(callback.from_user.id, "wanted_positions", positions_to_save)
    await state.clear()

    user = await get_user_with_settings(callback.from_user.id)
    s = user.settings
    wanted_positions = "Любые"
    if s.wanted_positions:
        wanted_positions = ", ".join([positions_mapping[p] for p in sorted(s.wanted_positions)])

    filters_text = (
        f"✅ <b>Роли поиска изменены!</b>\n\n"
        f"⚙️ <b>Твои фильтры поиска напарников:</b>\n\n"
        f"🎯 Искомые роли: {wanted_positions}\n"
        f"🔞 Возраст: от {s.min_age or 'любого'} до {s.max_age or 'любого'}\n"
        f"🏆 MMR: от {s.min_mmr or 'любого'} до {s.max_mmr or 'любого'}\n\n"
        f"Выберите параметр для изменения:"
    )
    await callback.message.edit_caption(caption=filters_text, reply_markup=get_edit_settings_fields_keyboard())
    await callback.answer()