"""Main bot entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config.settings import TELEGRAM_TOKEN
from handlers import start, expense_flow, admin, projects, compensations, reports  # ДОБАВЛЕНО: reports
from middlewares.auth import AuthMiddleware
from middlewares.fsm_timeout import FSMTimeoutMiddleware
from utils.google_sheets import get_employees_from_sheet
from utils.sheets_extended import ensure_sheets_exist
from services.scheduler import ReportScheduler  # ДОБАВЛЕНО: планировщик


async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    logger.info("🚀 Запуск бота...")

    # 🔥 СОЗДАНИЕ ЛИСТОВ ПРИ СТАРТЕ
    logger.info("🔄 Проверка и создание листов Google Sheets...")
    try:
        ensure_sheets_exist()
        logger.info("✅ Листы проверены/созданы")
    except Exception as e:
        logger.error(f"❌ Ошибка создания листов: {e}")

    # 🔥 ЗАГРУЗКА WHITELIST ПРИ СТАРТЕ
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

    # Подключаем middlewares (важен порядок!)
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(FSMTimeoutMiddleware(timeout_minutes=5))

    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(expense_flow.router)
    dp.include_router(admin.router)
    dp.include_router(projects.router)  # Новый модуль проектов
    dp.include_router(compensations.router)  # Новый модуль компенсаций
    dp.include_router(reports.router)  # ДОБАВЛЕНО: модуль отчётов

    # ДОБАВЛЕНО: Запуск планировщика авто-отчётов
    logger.info("🔄 Запуск планировщика отчётов...")
    scheduler = ReportScheduler(bot)
    scheduler.start()
    logger.info("✅ Планировщик запущен")

    logger.info("✅ Бот запущен и готов к работе")

    # Запуск polling
    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем планировщик при завершении
        scheduler.stop()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Бот остановлен пользователем")
