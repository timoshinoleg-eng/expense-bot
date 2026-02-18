from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_user_menu() -> ReplyKeyboardMarkup:
    """
    Главное меню для обычного сотрудника.
    """
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="Добавить сумму"),
        KeyboardButton(text="Просмотр чека"),
    )
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_admin_menu() -> ReplyKeyboardMarkup:
    """
    Главное меню для администратора.
    """
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="Добавить сумму"),
        KeyboardButton(text="Просмотр чека"),
        KeyboardButton(text="Добавить сотрудника"),
        KeyboardButton(text="Заблокировать"),
        KeyboardButton(text="Статистика"),
        KeyboardButton(text="Список пользователей"),
    )
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура с кнопкой Назад.
    """
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="⬅ Назад"))
    return builder.as_markup(resize_keyboard=True)
