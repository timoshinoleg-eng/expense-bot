from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_category_keyboard():
    builder = ReplyKeyboardBuilder()
    categories = [
        "Транспортные расходы",
        "Крепеж",
        "Орг.расходы",
        "Строительные материалы",
        "Прочие траты",
        "Под ЗП",
        "Ввести вручную",
    ]
    for cat in categories:
        builder.add(KeyboardButton(text=cat))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Отмена"))
    return builder.as_markup(resize_keyboard=True)


def get_photo_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Пропустить"))
    return builder.as_markup(resize_keyboard=True)


def get_confirmation_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Сохранить"))
    builder.add(KeyboardButton(text="Отменить"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)
