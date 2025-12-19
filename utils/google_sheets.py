"""Google Sheets integration utilities."""
from typing import Dict, List, Optional
import gspread
import json
import os
import logging
from google.oauth2.service_account import Credentials
from config.settings import SPREADSHEET_ID

logger = logging.getLogger(__name__)

def get_sheets_client():
    """
    Получить авторизованный клиент Google Sheets.
    Поддерживает авторизацию через JSON из переменной окружения или файл.
    """
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        
        # Приоритет 1: JSON из переменной окружения (для Bothost)
        credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        
        if credentials_json:
            logger.info("✅ Используется GOOGLE_SHEETS_CREDENTIALS_JSON из переменной окружения")
            try:
                creds_dict = json.loads(credentials_json)
                credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
                return gspread.authorize(credentials)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка парсинга JSON credentials: {e}")
                raise
        
        # Приоритет 2: Файл (для локальной разработки)
        credentials_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")
        
        if os.path.exists(credentials_file):
            logger.info(f"✅ Используется файл credentials: {credentials_file}")
            credentials = Credentials.from_service_account_file(credentials_file, scopes=scopes)
            return gspread.authorize(credentials)
        
        logger.error("❌ Не найдены credentials (ни JSON, ни файл)")
        raise ValueError("Google Sheets credentials не найдены")
        
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации Google Sheets: {type(e).__name__}: {e}")
        raise


def get_employees_from_sheet() -> Dict[int, dict]:
    """
    Загружает список сотрудников из листа "Сотрудники".
    
    Returns:
        dict: {telegram_id: {"first_name": "Имя", "last_name": "Фамилия", "status": "Активен", "role": "Админ"}}
    """
    try:
        logger.info("🔄 Загрузка whitelist из Google Sheets...")
        
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        logger.info(f"✅ Таблица открыта: {SPREADSHEET_ID}")
        
        try:
            sheet = doc.worksheet("Сотрудники")
            logger.info("✅ Лист 'Сотрудники' найден")
        except gspread.WorksheetNotFound:
            logger.error("❌ Лист 'Сотрудники' не найден!")
            logger.info(f"Доступные листы: {[ws.title for ws in doc.worksheets()]}")
            
            # Создаём лист если его нет
            sheet = doc.add_worksheet(title="Сотрудники", rows=100, cols=5)
            sheet.update("A1:E1", [["ID", "Имя", "Фамилия", "Статус", "Роль"]])
            logger.warning("⚠️ Лист 'Сотрудники' создан. Добавьте сотрудников вручную!")
            return {}
        
        # Читаем данные (пропускаем заголовок)
        rows = sheet.get_all_values()[1:]
        logger.info(f"✅ Прочитано {len(rows)} строк")
        
        employees = {}
        for idx, row in enumerate(rows, start=2):
            if len(row) < 5:
                logger.warning(f"⚠️ Строка {idx} пропущена (недостаточно столбцов): {row}")
                continue
            
            try:
                emp_id = int(row[0])
                emp_data = {
                    "first_name": row[1].strip(),
                    "last_name": row[2].strip(),
                    "status": row[3].strip(),
                    "role": row[4].strip(),
                }
                
                employees[emp_id] = emp_data
                logger.info(f"  ✅ {emp_id} - {emp_data['first_name']} {emp_data['last_name']} ({emp_data['role']}, {emp_data['status']})")
                
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ Строка {idx} пропущена (ошибка парсинга): {row}, ошибка: {e}")
                continue
        
        logger.info(f"✅ Whitelist загружен: {len(employees)} пользователей")
        logger.info(f"📋 ID пользователей: {list(employees.keys())}")
        
        return employees
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки whitelist: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}


def append_expense_row(data: list) -> bool:
    """Добавить строку расходов в первый лист таблицы."""
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        sheet.append_row(data, value_input_option="USER_ENTERED")
        logger.info(f"✅ Расход добавлен: {data}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка записи расхода: {e}")
        return False


def get_all_expenses() -> Optional[List[List[str]]]:
    """Получить все расходы из первого листа."""
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        return sheet.get_all_values()[1:]  # Пропускаем заголовок
    except Exception as e:
        logger.error(f"❌ Ошибка чтения расходов: {e}")
        return None


def check_photo_ownership(file_id: str, first_name: str, last_name: str) -> bool:
    """Проверить владельца фото по file_id."""
    expenses = get_all_expenses()
    if not expenses:
        return False
    
    for row in expenses:
        if len(row) >= 7 and row[6] == file_id and row[0] == first_name and row[1] == last_name:
            return True
    
    return False


def add_employee_to_sheet(telegram_id: int, first_name: str, last_name: str, role: str = "Сотрудник") -> bool:
    """Добавить сотрудника в лист 'Сотрудники'."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        
        try:
            sheet = doc.worksheet("Сотрудники")
        except gspread.WorksheetNotFound:
            sheet = doc.add_worksheet(title="Сотрудники", rows=100, cols=5)
            sheet.update("A1:E1", [["ID", "Имя", "Фамилия", "Статус", "Роль"]])
        
        sheet.append_row([str(telegram_id), first_name, last_name, "Активен", role], value_input_option="USER_ENTERED")
        logger.info(f"✅ Сотрудник добавлен: {telegram_id} - {first_name} {last_name} ({role})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка добавления сотрудника: {e}")
        return False


def block_employee(telegram_id: int) -> bool:
    """Заблокировать сотрудника (установить статус 'Заблокирован')."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet("Сотрудники")
        
        cell = sheet.find(str(telegram_id))
        if cell:
            sheet.update_cell(cell.row, 4, "Заблокирован")
            logger.info(f"✅ Сотрудник {telegram_id} заблокирован")
            return True
        
        logger.warning(f"⚠️ Сотрудник {telegram_id} не найден")
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка блокировки сотрудника: {e}")
        return False
