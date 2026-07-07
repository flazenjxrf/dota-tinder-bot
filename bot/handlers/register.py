from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.fsm import RegisterForm, SearchSettingsForm

# Все необходимые импорты клавиатур собраны здесь
from bot.keyboards.inline import (
    get_positions_keyboard,
    PositionCallback,
    get_confirm_profile_keyboard,
    get_search_positions_keyboard  # <-- Теперь точно импортировано
)

router = Router()


# ================= 1. НАЧАЛО РЕГИСТРАЦИИ =================
@router.callback_query(F.data == "start_registration")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Как тебя зовут? (имя или никнейм)")
    await state.set_state(RegisterForm.name)
    await callback.answer()


# ================= 2. ИМЯ -> ВОЗРАСТ =================
@router.message(RegisterForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterForm.age)


# ================= 3. ВОЗРАСТ -> ГОРОД =================
@router.message(RegisterForm.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (10 <= int(message.text) <= 100):
        await message.answer("Пожалуйста, введи корректный возраст цифрами (например, 20).")
        return
    await state.update_data(age=int(message.text))
    await message.answer("Из какого ты города?")
    await state.set_state(RegisterForm.city)


# ================= 4. ГОРОД -> ПОЗИЦИИ =================
@router.message(RegisterForm.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text, positions=[])
    await message.answer(
        "На каких позициях играешь? Выбери одну или несколько:",
        reply_markup=get_positions_keyboard([])
    )
    await state.set_state(RegisterForm.positions)


# ================= 5. ВЫБОР ПОЗИЦИЙ (КОЛЛБЕКИ) =================
@router.callback_query(RegisterForm.positions, PositionCallback.filter())
async def toggle_position(callback: CallbackQuery, callback_data: PositionCallback, state: FSMContext):
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


# ================= 6. ПОДТВЕРЖДЕНИЕ ПОЗИЦИЙ -> MMR =================
@router.callback_query(RegisterForm.positions, F.data == "confirm_positions")
async def confirm_positions(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("positions"):
        await callback.answer("Выбери хотя бы одну позицию!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Какой у тебя рейтинг? (MMR цифрами)")
    await state.set_state(RegisterForm.mmr)
    await callback.answer()


# ================= 7. MMR -> О СЕБЕ =================
@router.message(RegisterForm.mmr)
async def process_mmr(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи MMR цифрами (например, 3500).")
        return
    await state.update_data(mmr=int(message.text))
    await message.answer("Расскажи о себе (это поможет заинтересовать больше человек):")
    await state.set_state(RegisterForm.bio)


# ================= 8. О СЕБЕ -> ФОТО =================
@router.message(RegisterForm.bio)
async def process_bio(message: Message, state: FSMContext):
    await state.update_data(bio=message.text)
    await message.answer("Загрузи фотографию\n(это может быть твое лицо, аватарка или какой-нибудь мем)")
    await state.set_state(RegisterForm.photo)


# ================= 9. ФОТО -> ПРЕДПРОСМОТР АНКЕТЫ =================
@router.message(RegisterForm.photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_file_id)

    data = await state.get_data()

    # Красивый вывод позиций без цифр
    positions_mapping = {
        1: "Керри",
        2: "Мидер",
        3: "Тройка",
        4: "Саппорт"
    }
    pos_names = [positions_mapping[p] for p in sorted(data['positions'])]
    pos_str = ", ".join(pos_names)

    caption = (
        f"🌟 <b>{data['name']}</b>, {data['age']} | 📍 {data['city']}\n\n"
        f"🎯 Позиции: {pos_str}\n"
        f"🏆 MMR: {data['mmr']}\n\n"
        f"💬 О себе:\n{data['bio']}\n\n"
        f"<i>Вот так тебя смогут увидеть другие пользователи. Всё верно?</i>"
    )

    await message.answer_photo(
        photo=photo_file_id,
        caption=caption,
        reply_markup=get_confirm_profile_keyboard()
    )
    await state.set_state(RegisterForm.confirm)


@router.message(RegisterForm.photo)
async def process_photo_invalid(message: Message):
    await message.answer("Пожалуйста, отправь именно картинку (фотографию).")


# ================= 10. ПОДТВЕРЖДЕНИЕ АНКЕТЫ И ПЕРЕХОД К ПОИСКУ =================
@router.callback_query(RegisterForm.confirm, F.data == "profile_ok")
async def profile_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Отлично, анкета сохранена! 🎉\n\n"
        "Теперь давай настроим поиск.\n"
        "Какую позицию ищешь? (Выбери одну или несколько)",
        reply_markup=get_search_positions_keyboard([])  # Вызываем правильную импортированную клавиатуру
    )
    await state.set_state(SearchSettingsForm.positions)
    await state.update_data(wanted_positions=[])
    await callback.answer()