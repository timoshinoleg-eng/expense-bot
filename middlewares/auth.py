"""Authentication middleware with whitelist caching."""
from typing import Any, Awaitable, Callable, Dict
from datetime import datetime, timedelta
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message
from utils.google_sheets import get_employees_from_sheet

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Middleware для проверки доступа пользователей через whitelist.
    Whitelist кэшируется на 5 минут для снижения нагрузки на Google Sheets API.
    """
    _cache = {}
    _cache_time = None
    _cache_duration = timedelta(minutes=5)

    @classmethod
    def _get_cached_employees(cls):
        """Получить whitelist с автообновлением кэша каждые 5 минут."""
        now = datetime.now()
        
        if cls._cache_time is None or (now - cls._cache_time) > cls._cache_duration:
            logger.info("🔄 Обновление whitelist (кэш истёк или первый запуск)...")
            cls._cache = get_employees_from_sheet()
            cls._cache_time = now
            logger.info(f"✅ Whitelist обновлён: {len(cls._cache)} пользователей")
        else:
            time_left = cls._cache_duration - (now - cls._cache_time)
            logger.debug(f"💾 Используется кэш whitelist (осталось {time_left.seconds}с до обновления)")
        
        return cls._cache

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ):
        user_id = event.from_user.id
        username = event.from_user.username or "без username"
        
        # Команда /getid доступна всем (для получения Telegram ID)
        if event.text and event.text.startswith("/getid"):
            logger.info(f"ℹ️ Команда /getid от {user_id} ({username})")
            return await handler(event, data)
        
        # Команда /start доступна всем (для первого контакта с ботом)
        if event.text and event.text.startswith("/start"):
            logger.info(f"ℹ️ Команда /start от {user_id} ({username})")
            employees = self._get_cached_employees()
            
            if user_id not in employees:
                # Пользователь не в whitelist - пропускаем в handler с минимальными данными
                logger.info(f"ℹ️ /start от пользователя не в whitelist: {user_id}")
                data["is_admin"] = False
                data["user_id"] = user_id
                data["user_first_name"] = event.from_user.first_name or "Пользователь"
                data["user_last_name"] = event.from_user.last_name or ""
                return await handler(event, data)
            else:
                # Пользователь в whitelist - проверяем статус и добавляем данные
                emp_data = employees[user_id]
                
                # Проверяем статус (заблокирован или нет)
                if emp_data.get("status") == "Заблокирован":
                    logger.warning(f"🚫 Доступ запрещён: {user_id} ({username}) - заблокирован")
                    await event.answer(
                        "🚫 Ваш доступ заблокирован.\n"
                        "Обратитесь к администратору для уточнения деталей."
                    )
                    return
                
                # Доступ разрешён - добавляем данные из whitelist
                logger.info(
                    f"✅ Доступ разрешён: {user_id} ({username}) - "
                    f"{emp_data['first_name']} {emp_data['last_name']} ({emp_data['role']})"
                )
                data["is_admin"] = emp_data.get("role") in ["владелец", "главбух", "контролер"]
                data["user_role"] = emp_data.get("role", "подотчетник")
                data["user_id"] = user_id
                data["user_first_name"] = emp_data.get("first_name", "Пользователь")
                data["user_last_name"] = emp_data.get("last_name", "")
                return await handler(event, data)
        
        # Для всех остальных команд проверяем whitelist
        employees = self._get_cached_employees()
        
        if user_id not in employees:
            logger.warning(f"❌ Доступ запрещён: {user_id} ({username}) - не в whitelist")
            await event.answer(
                "❌ Доступ запрещён.\n\n"
                "Этот бот доступен только сотрудникам компании.\n\n"
                "Для получения доступа:\n"
                "1. Отправьте /getid\n"
                "2. Передайте ваш ID администратору\n"
                "3. Дождитесь добавления в систему"
            )
            return
        
        emp_data = employees[user_id]
        
        # Проверяем статус (заблокирован или нет)
        if emp_data.get("status") == "Заблокирован":
            logger.warning(f"🚫 Доступ запрещён: {user_id} ({username}) - заблокирован")
            await event.answer(
                "🚫 Ваш доступ заблокирован.\n"
                "Обратитесь к администратору для уточнения деталей."
            )
            return
        
        # Доступ разрешён
        logger.info(
            f"✅ Доступ разрешён: {user_id} ({username}) - "
            f"{emp_data['first_name']} {emp_data['last_name']} ({emp_data['role']})"
        )
        
        # Добавляем данные пользователя в context
        data["is_admin"] = emp_data.get("role") in ["владелец", "главбух", "контролер"]
        data["user_role"] = emp_data.get("role", "подотчетник")
        data["user_id"] = user_id
        data["user_first_name"] = emp_data.get("first_name", "Пользователь")
        data["user_last_name"] = emp_data.get("last_name", "")
        
        return await handler(event, data)
