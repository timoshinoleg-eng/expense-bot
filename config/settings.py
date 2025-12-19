import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в .env")
if not SPREADSHEET_ID:
    raise ValueError("SPREADSHEET_ID не найден в .env")

print("Конфигурация загружена")
print("Whitelist загружается из Google Sheets")
