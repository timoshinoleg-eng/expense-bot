from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from keyboards.main_menu import get_user_menu, get_admin_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, is_admin: bool = False, user_first_name: str = None, user_role: str = None):
    """
    Стартовое сообщение + показ основного меню.
    """
    # Если пользователь не прошел через middleware (не в whitelist)
    if user_first_name is None:
        user_first_name = message.from_user.first_name or "Пользователь"
        await message.answer(
            "❌ Доступ запрещён.\n\n"
            "Этот бот доступен только сотрудникам компании.\n\n"
            "Для получения доступа:\n"
            "1. Отправьте /getid\n"
            "2. Передайте ваш ID администратору\n"
            "3. Дождитесь добавления в систему"
        )
        return
    
    # Отображаем реальную роль из таблицы
    role_display = user_role if user_role else "Сотрудник"

    text = (
        f"Привет, {user_first_name}!\n"
        f"Ваша роль: {role_display}\n\n"
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
