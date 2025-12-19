from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from keyboards.main_menu import get_user_menu, get_admin_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, is_admin: bool, user_first_name: str):
    """
    Стартовое сообщение + показ основного меню.
    """
    role = "Администратор" if is_admin else "Сотрудник"

    text = (
        f"Привет, {user_first_name}!\n"
        f"Ваша роль: {role}\n\n"
        "Используйте кнопки внизу для работы с ботом.\n"
        "Команду /getid можно ввести вручную при необходимости."
    )

    keyboard = get_admin_menu() if is_admin else get_user_menu()
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("getid"))
async def get_my_id(message: Message):
    """
    Вывод Telegram ID и базовых данных пользователя.
    """
    user = message.from_user
    text = (
        "Ваши данные:\n\n"
        f"Telegram ID: {user.id}\n"
        f"Имя: {user.first_name or 'не указано'}\n"
        f"Фамилия: {user.last_name or 'не указано'}\n"
        f"Username: @{user.username or 'не указан'}\n\n"
        "Передайте этот ID администратору при необходимости."
    )
    await message.answer(text)
