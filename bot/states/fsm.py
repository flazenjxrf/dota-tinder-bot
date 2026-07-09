from aiogram.fsm.state import StatesGroup, State

class RegisterForm(StatesGroup):
    name = State()       # Имя
    age = State()        # Возраст
    city = State()       # Город
    positions = State()  # Выбор позиций (инлайн кнопки)
    mmr = State()        # Рейтинг
    bio = State()        # Рассказ о себе
    photo = State()      # Фотография
    confirm = State()    # Подтверждение анкеты

class SearchSettingsForm(StatesGroup):
    positions = State()  # Кого ищем
    min_age = State()
    max_age = State()
    min_mmr = State()
    max_mmr = State()

class EditProfile(StatesGroup):
    name = State()
    age = State()
    city = State()
    positions = State()
    mmr = State()
    bio = State()
    photo = State()

class EditSettings(StatesGroup):
    positions = State()
    min_age = State()
    max_age = State()
    min_mmr = State()
    max_mmr = State()

class SwipingForm(StatesGroup):
    like_message = State()