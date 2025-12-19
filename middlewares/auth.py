from typing import Any, Awaitable, Callable, Dict
from datetime import datetime, timedelta

from aiogram import BaseMiddleware
from aiogram.types import Message

from utils.google_sheets import get_employees_from_sheet


class AuthMiddleware(BaseMiddleware):
    _cache = {}
    _cache_time = None
    _cache_duration = timedelta(minutes=5)

    @classmethod
    def _get_cached_employees(cls):
        now = datetime.now()
        if cls._cache_time is None or (now - cls._cache_time) > cls._cache_duration:
            cls._cache = get_employees_from_sheet()
            cls._cache_time = now
            print(f"Whitelist обновлен: {len(cls._cache)} пользователей")
        return cls._cache

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ):
        user_id = event.from_user.id

        if event.text and event.text.startswith("/getid"):
            return await handler(event, data)

        employees = self._get_cached_employees()

        if user_id not in employees:
            await event.answer(
                "Доступ запрещен.\n\n"
                "Этот бот доступен только сотрудникам компании.\n\n"
                "Для доступа:\n"
                "1. Отправьте /getid\n"
                "2. Передайте ID администратору\n"
                "3. Дождитесь добавления"
            )
            return

        emp_data = employees[user_id]

        if emp_data.get("status") == "Заблокирован":
            await event.answer(
                "Ваш доступ заблокирован.\n"
                "Обратитесь к администратору."
            )
            return

        data["is_admin"] = emp_data.get("role") == "Админ"
        data["user_id"] = user_id
        data["user_first_name"] = emp_data.get("first_name", "Пользователь")
        data["user_last_name"] = emp_data.get("last_name", "")

        return await handler(event, data)
