import asyncio
import logging
from aiogram import Bot, Dispatcher

from config.settings import TELEGRAM_TOKEN
from handlers import start, expense_flow, admin
from middlewares.auth import AuthMiddleware


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    bot = Bot(TELEGRAM_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(AuthMiddleware())

    dp.include_router(start.router)
    dp.include_router(expense_flow.router)
    dp.include_router(admin.router)

    logging.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
