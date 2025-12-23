"""Main bot entry point."""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from config.settings import TELEGRAM_TOKEN
from handlers import start, expense_flow, admin
from middlewares.auth import AuthMiddleware
from utils.google_sheets import get_employees_from_sheet

async def main():
    # Настройка логирования
    from middlewares.fsm_timeout import FSMTimeoutMiddleware
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Запуск бота...")
    
    # 🔥 ЗАГРУЗКА WHITELIST ПРИ СТАРТЕ (для прогрева кэша)
    logger.info("🔄 Загрузка whitelist из Google Sheets при старте...")
    try:
        whitelist = get_employees_from_sheet()
        if whitelist:
            logger.info(f"✅ Whitelist загружен успешно: {len(whitelist)} пользователей")
            logger.info(f"📋 ID в whitelist: {list(whitelist.keys())}")
        else:
            logger.error("❌ Whitelist пуст! Проверьте подключение к Google Sheets.")
            logger.warning("⚠️ Бот запустится, но никто не сможет получить доступ.")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки whitelist при старте: {e}")
        logger.warning("⚠️ Бот запустится, но могут быть проблемы с доступом.")
    
    # Инициализация бота
    bot = Bot(TELEGRAM_TOKEN)
    dp = Dispatcher()
    
    # Подключаем middleware
    dp.message.middleware(AuthMiddleware())
    
    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(expense_flow.router)
        dp.message.middleware(FSMTimeoutMiddleware(timeout_minutes=5))
    dp.include_router(admin.router)
    
    logger.info("✅ Бот запущен и готов к работе")
    
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Бот остановлен пользователем")
