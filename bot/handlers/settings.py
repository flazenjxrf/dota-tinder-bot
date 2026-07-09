from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.fsm import SearchSettingsForm
from bot.keyboards.inline import get_search_positions_keyboard, SearchPositionCallback, get_skip_keyboard
from bot.database.requests import save_user_and_settings
from bot.keyboards.reply import REMOVE_KEYBOARD
from bot.utils.bot_commands import MENU_HINT

router = Router()


# ================= 1. ВЫБОР ПОЗИЦИЙ ДЛЯ ПОИСКА =================
@router.callback_query(SearchSettingsForm.positions, SearchPositionCallback.filter())
async def toggle_search_position(callback: CallbackQuery, callback_data: SearchPositionCallback, state: FSMContext):
    data = await state.get_data()
    wanted_positions = data.get("wanted_positions", [])

    pos_id = callback_data.id
    if pos_id in wanted_positions:
        wanted_positions.remove(pos_id)
    else:
        wanted_positions.append(pos_id)

    await state.update_data(wanted_positions=wanted_positions)
    await callback.message.edit_reply_markup(reply_markup=get_search_positions_keyboard(wanted_positions))
    await callback.answer()


# ================= 2. ПОДТВЕРЖДЕНИЕ ПОЗИЦИЙ -> МИН. ВОЗРАСТ =================
@router.callback_query(SearchSettingsForm.positions, F.data == "confirm_search_positions")
async def confirm_search_positions(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Минимальный возраст напарника?",
        reply_markup=get_skip_keyboard("min_age")
    )
    await state.set_state(SearchSettingsForm.min_age)
    await callback.answer()


# ================= 3. МИН. ВОЗРАСТ -> МАКС. ВОЗРАСТ =================
@router.message(SearchSettingsForm.min_age)
async def process_min_age_msg(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введи число или нажми 'Пропустить'.")
        return
    await state.update_data(min_age=int(message.text))
    await ask_max_age(message, state)


@router.callback_query(SearchSettingsForm.min_age, F.data == "skip_min_age")
async def process_min_age_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(min_age=None)
    await ask_max_age(callback.message, state)
    await callback.answer()


async def ask_max_age(message: Message, state: FSMContext):
    await message.answer("Максимальный возраст?", reply_markup=get_skip_keyboard("max_age"))
    await state.set_state(SearchSettingsForm.max_age)


# ================= 4. МАКС. ВОЗРАСТ -> МИН. MMR =================
@router.message(SearchSettingsForm.max_age)
async def process_max_age_msg(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return
    await state.update_data(max_age=int(message.text))
    await ask_min_mmr(message, state)


@router.callback_query(SearchSettingsForm.max_age, F.data == "skip_max_age")
async def process_max_age_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(max_age=None)
    await ask_min_mmr(callback.message, state)
    await callback.answer()


async def ask_min_mmr(message: Message, state: FSMContext):
    await message.answer("Минимальный рейтинг (MMR)?", reply_markup=get_skip_keyboard("min_mmr"))
    await state.set_state(SearchSettingsForm.min_mmr)


# ================= 5. МИН. MMR -> МАКС. MMR =================
@router.message(SearchSettingsForm.min_mmr)
async def process_min_mmr_msg(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return
    await state.update_data(min_mmr=int(message.text))
    await ask_max_mmr(message, state)


@router.callback_query(SearchSettingsForm.min_mmr, F.data == "skip_min_mmr")
async def process_min_mmr_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(min_mmr=None)
    await ask_max_mmr(callback.message, state)
    await callback.answer()


async def ask_max_mmr(message: Message, state: FSMContext):
    await message.answer("Максимальный рейтинг (MMR)?", reply_markup=get_skip_keyboard("max_mmr"))
    await state.set_state(SearchSettingsForm.max_mmr)


# ================= 6. МАКС. MMR -> СОХРАНЕНИЕ В БАЗУ =================
@router.message(SearchSettingsForm.max_mmr)
async def process_max_mmr_msg(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return
    await state.update_data(max_mmr=int(message.text))
    await finish_registration(message.from_user, message, state)


@router.callback_query(SearchSettingsForm.max_mmr, F.data == "skip_max_mmr")
async def process_max_mmr_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(max_mmr=None)
    await finish_registration(callback.from_user, callback.message, state)
    await callback.answer()


async def finish_registration(user, message_obj: Message, state: FSMContext):
    data = await state.get_data()

    await save_user_and_settings(
        telegram_id=user.id,
        username=user.username,
        data=data
    )

    await state.clear()

    await message_obj.answer(
        "✅ Все настройки успешно сохранены!\n\n"
        f"Теперь ты можешь искать тимейтов. {MENU_HINT}",
        reply_markup=REMOVE_KEYBOARD,
    )