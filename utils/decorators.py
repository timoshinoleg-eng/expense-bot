"""
Декораторы для проверки ролей пользователей.
"""
from functools import wraps
from typing import List

from aiogram.types import Message

from utils.google_sheets import get_employees_from_sheet


# Константы ролей
ROLE_OWNER = "владелец"
ROLE_CHIEF_ACCOUNTANT = "главбух"
ROLE_CONTROLLER = "контролер"
ROLE_EMPLOYEE = "подотчетник"

# Уровни доступа
ACCESS_LEVELS = {
    ROLE_OWNER: 4,
    ROLE_CHIEF_ACCOUNTANT: 3,
    ROLE_CONTROLLER: 2,
    ROLE_EMPLOYEE: 1,
}


def get_user_role(telegram_id: int) -> str:
    """Получить роль пользователя по Telegram ID."""
    employees = get_employees_from_sheet()
    user_data = employees.get(telegram_id, {})
    return user_data.get("role", ROLE_EMPLOYEE)


def has_role(user_role: str, required_roles: List[str]) -> bool:
    """Проверить, имеет ли пользователь одну из требуемых ролей."""
    if user_role in required_roles:
        return True
    # Контролер может читать данные главбуха
    if ROLE_CONTROLLER in required_roles and user_role == ROLE_CONTROLLER:
        return True
    return False


def role_required(required_roles: List[str]):
    """
    Декоратор для проверки роли пользователя.
    
    Args:
        required_roles: Список допустимых ролей
    """
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            user_id = message.from_user.id
            user_role = get_user_role(user_id)
            
            if not has_role(user_role, required_roles):
                await message.answer(
                    "⛔ У вас нет прав для выполнения этой операции.\n"
                    f"Требуется одна из ролей: {', '.join(required_roles)}"
                )
                return
            
            # Добавляем роль в kwargs для использования в хендлере
            kwargs["user_role"] = user_role
            return await handler(message, *args, **kwargs)
        
        return wrapper
    return decorator


def min_access_level(level: int):
    """
    Декоратор для проверки минимального уровня доступа.
    
    Args:
        level: Минимальный требуемый уровень (1-4)
    """
    def decorator(handler):
        @wraps(handler)
        async def wrapper(message: Message, *args, **kwargs):
            user_id = message.from_user.id
            user_role = get_user_role(user_id)
            user_level = ACCESS_LEVELS.get(user_role, 0)
            
            if user_level < level:
                await message.answer(
                    "⛔ Недостаточно прав для выполнения этой операции."
                )
                return
            
            kwargs["user_role"] = user_role
            kwargs["access_level"] = user_level
            return await handler(message, *args, **kwargs)
        
        return wrapper
    return decorator
