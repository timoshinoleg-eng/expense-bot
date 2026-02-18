"""
Расширенные утилиты для работы с Google Sheets.
Добавлены: проекты, статьи расходов, лимиты, компенсации.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from utils.google_sheets import get_sheets_client, get_employees_from_sheet
from config.settings import SPREADSHEET_ID

logger = logging.getLogger(__name__)

# Экспортируем get_employees_from_sheet для совместимости
__all__ = [
    'ensure_sheets_exist',
    'SHEET_EMPLOYEES',
    'SHEET_EXPENSES',
    'SHEET_PROJECTS',
    'SHEET_CATEGORIES',
    'SHEET_COMPENSATIONS',
    'get_active_projects',
    'get_all_projects',
    'add_project',
    'update_project_status',
    'get_expense_categories',
    'add_expense_category',
    'get_employee_limit',
    'set_employee_limit',
    'get_expenses_for_period',
    'check_limit_status',
    'append_expense_row_extended',
    'get_employees_from_sheet',
    # ДОБАВЛЕНО: функции балансов и компенсаций
    'update_employee_balance',
    'get_employee_balance',
    'check_negative_balance',
    'process_expense_with_balance',
    'create_compensation_request',
    'get_compensation_requests',
    'update_compensation_status',
    'get_expenses_by_status',
    'get_employee_expenses',
    'get_expenses_by_employee_and_period',
    'get_all_employee_balances',
    'get_negative_balances',
    'add_advance_payment',
    # ДОБАВЛЕНО: уведомления о лимитах
    'notify_limit_warning',
    'notify_limit_exceeded',
    # ДОБАВЛЕНО: подписки на отчёты
    'get_employees_with_subscription',
    'update_subscription',
    'get_employee_subscriptions',
    # ДОБАВЛЕНО: отчёты
    'get_expenses_by_project',
]


# ============ ЛИСТЫ GOOGLE SHEETS ============

SHEET_EMPLOYEES = "Сотрудники"
SHEET_EXPENSES = "Расходы"
SHEET_PROJECTS = "Проекты"
SHEET_CATEGORIES = "Статьи_расходов"
SHEET_COMPENSATIONS = "Компенсации"  # ДОБАВЛЕНО: новый лист для компенсаций


def ensure_sheets_exist():
    """Проверить и создать необходимые листы при запуске."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        existing_sheets = [ws.title for ws in doc.worksheets()]
        
        # Лист "Сотрудники" (расширенный)
        if SHEET_EMPLOYEES not in existing_sheets:
            sheet = doc.add_worksheet(title=SHEET_EMPLOYEES, rows=100, cols=15)
            sheet.update("A1:O1", [[
                "ID", "Имя", "Фамилия", "Статус", "Роль", 
                "Лимит", "Период_лимита", "Баланс",
                # ДОБАВЛЕНО: подписки на отчёты
                "Подписка_ежедневная", "Подписка_еженедельная", "Подписка_ежемесячная",
                "Подписка_админ_ежедневная", "Подписка_админ_еженедельная", 
                "Подписка_админ_ежемесячная", "Подписка_баланс"
            ]])
            logger.info(f"✅ Создан лист '{SHEET_EMPLOYEES}'")
        
        # Лист "Проекты"
        if SHEET_PROJECTS not in existing_sheets:
            sheet = doc.add_worksheet(title=SHEET_PROJECTS, rows=100, cols=6)
            sheet.update("A1:F1", [[
                "ID", "Название", "Статус", "Бюджет", "Дата_начала", "Дата_окончания"
            ]])
            logger.info(f"✅ Создан лист '{SHEET_PROJECTS}'")
        
        # Лист "Статьи_расходов"
        if SHEET_CATEGORIES not in existing_sheets:
            sheet = doc.add_worksheet(title=SHEET_CATEGORIES, rows=100, cols=3)
            sheet.update("A1:C1", [[
                "ID", "Название", "Родительская_категория"
            ]])
            logger.info(f"✅ Создан лист '{SHEET_CATEGORIES}'")
            # Добавляем базовые категории
            default_categories = [
                ["1", "Материалы", ""],
                ["2", "Инструмент", ""],
                ["3", "Транспорт", ""],
                ["4", "Питание", ""],
                ["5", "Прочее", ""],
            ]
            sheet.append_rows(default_categories, value_input_option="USER_ENTERED")
        
        # Проверяем/обновляем лист "Расходы"
        if SHEET_EXPENSES not in existing_sheets:
            sheet = doc.add_worksheet(title=SHEET_EXPENSES, rows=1000, cols=10)
            sheet.update("A1:J1", [[
                "Имя", "Фамилия", "Дата_время", "Сумма", "Статья_расходов",
                "Объект", "File_ID_чека", "project_id", "Статус_компенсации", "Тип_операции"
            ]])
            logger.info(f"✅ Создан лист '{SHEET_EXPENSES}'")
        
        # ДОБАВЛЕНО: Лист "Компенсации"
        if SHEET_COMPENSATIONS not in existing_sheets:
            sheet = doc.add_worksheet(title=SHEET_COMPENSATIONS, rows=1000, cols=8)
            sheet.update("A1:H1", [[
                "ID", "Сотрудник_ID", "Сумма", "Тип", "Статус", 
                "Дата_запроса", "Дата_выплаты", "Комментарий"
            ]])
            logger.info(f"✅ Создан лист '{SHEET_COMPENSATIONS}'")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания листов: {e}")
        return False


# ============ ПРОЕКТЫ ============

def get_active_projects() -> List[Dict]:
    """Получить список активных проектов."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_PROJECTS)
        rows = sheet.get_all_values()[1:]  # Пропускаем заголовок
        
        projects = []
        for row in rows:
            if len(row) >= 3 and row[2] == "активный":
                projects.append({
                    "id": row[0],
                    "name": row[1],
                    "status": row[2],
                    "budget": row[3] if len(row) > 3 else "",
                    "start_date": row[4] if len(row) > 4 else "",
                    "end_date": row[5] if len(row) > 5 else "",
                })
        return projects
    except Exception as e:
        logger.error(f"❌ Ошибка получения проектов: {e}")
        return []


def get_all_projects() -> List[Dict]:
    """Получить все проекты."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_PROJECTS)
        rows = sheet.get_all_values()[1:]
        
        projects = []
        for row in rows:
            if len(row) >= 3:
                projects.append({
                    "id": row[0],
                    "name": row[1],
                    "status": row[2],
                    "budget": row[3] if len(row) > 3 else "",
                    "start_date": row[4] if len(row) > 4 else "",
                    "end_date": row[5] if len(row) > 5 else "",
                })
        return projects
    except Exception as e:
        logger.error(f"❌ Ошибка получения проектов: {e}")
        return []


def add_project(name: str, status: str = "активный", budget: str = "", 
                start_date: str = "", end_date: str = "") -> bool:
    """Добавить новый проект."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_PROJECTS)
        
        # Генерируем ID
        rows = sheet.get_all_values()
        project_id = str(len(rows))
        
        sheet.append_row([
            project_id, name, status, budget, start_date, end_date
        ], value_input_option="USER_ENTERED")
        
        logger.info(f"✅ Проект добавлен: {name} (ID: {project_id})")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления проекта: {e}")
        return False


def update_project_status(project_id: str, status: str) -> bool:
    """Обновить статус проекта."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_PROJECTS)
        
        # Ищем проект по ID
        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == project_id:
                sheet.update_cell(idx, 3, status)
                logger.info(f"✅ Статус проекта {project_id} изменен на {status}")
                return True
        
        logger.warning(f"⚠️ Проект {project_id} не найден")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления проекта: {e}")
        return False


# ============ СТАТЬИ РАСХОДОВ ============

def get_expense_categories() -> List[Dict]:
    """Получить список статей расходов."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_CATEGORIES)
        rows = sheet.get_all_values()[1:]
        
        categories = []
        for row in rows:
            if len(row) >= 2:
                categories.append({
                    "id": row[0],
                    "name": row[1],
                    "parent": row[2] if len(row) > 2 else "",
                })
        return categories
    except Exception as e:
        logger.error(f"❌ Ошибка получения категорий: {e}")
        return []


def add_expense_category(name: str, parent: str = "") -> bool:
    """Добавить новую статью расходов."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_CATEGORIES)
        
        rows = sheet.get_all_values()
        category_id = str(len(rows))
        
        sheet.append_row([category_id, name, parent], value_input_option="USER_ENTERED")
        logger.info(f"✅ Категория добавлена: {name}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка добавления категории: {e}")
        return False


# ============ ЛИМИТЫ ============

def get_employee_limit(telegram_id: int) -> Tuple[float, str]:
    """
    Получить лимит и период лимита сотрудника.
    
    Returns:
        (лимит, период) - период: день/неделя/месяц
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()[1:]
        for row in rows:
            if len(row) >= 1 and row[0] == str(telegram_id):
                limit = float(row[5]) if len(row) > 5 and row[5] else 0.0
                period = row[6] if len(row) > 6 and row[6] else "месяц"
                return limit, period
        
        return 0.0, "месяц"
    except Exception as e:
        logger.error(f"❌ Ошибка получения лимита: {e}")
        return 0.0, "месяц"


def set_employee_limit(telegram_id: int, limit: float, period: str = "месяц") -> bool:
    """Установить лимит сотруднику."""
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == str(telegram_id):
                sheet.update_cell(idx, 6, str(limit))
                sheet.update_cell(idx, 7, period)
                logger.info(f"✅ Лимит для {telegram_id} установлен: {limit} ({period})")
                return True
        
        logger.warning(f"⚠️ Сотрудник {telegram_id} не найден")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка установки лимита: {e}")
        return False


def get_expenses_for_period(telegram_id: int, period: str) -> float:
    """
    Получить сумму расходов сотрудника за период.
    
    Args:
        period: "день", "неделя", "месяц"
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        rows = sheet.get_all_values()[1:]
        
        # Определяем дату начала периода
        now = datetime.now()
        if period == "день":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "неделя":
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # месяц
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        total = 0.0
        for row in rows:
            if len(row) >= 3:
                # Проверяем имя и фамилию (колонки 0 и 1)
                # Получаем имя сотрудника по ID
                pass  # TODO: реализовать проверку по имени
        
        return total
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов за период: {e}")
        return 0.0


def check_limit_status(telegram_id: int, new_amount: float) -> Tuple[bool, float, str]:
    """
    Проверить статус лимита при добавлении нового расхода.
    
    Returns:
        (превышен_ли_лимит, процент_использования, статус)
        статус: "ok", "warning_80", "limit_exceeded"
    """
    limit, period = get_employee_limit(telegram_id)
    
    if limit <= 0:
        # Лимит не установлен
        return False, 0.0, "ok"
    
    current_expenses = get_expenses_for_period(telegram_id, period)
    total_with_new = current_expenses + new_amount
    percentage = (total_with_new / limit) * 100
    
    if total_with_new > limit:
        return True, percentage, "limit_exceeded"
    elif percentage >= 80:
        return False, percentage, "warning_80"
    else:
        return False, percentage, "ok"


# ============ РАСШИРЕННЫЕ РАСХОДЫ ============

def append_expense_row_extended(
    data: List[str],
    project_id: str = "",
    compensation_status: str = "ожидает",
    operation_type: str = "расход"
) -> bool:
    """
    Добавить расход с расширенными полями.
    
    Args:
        data: [Имя, Фамилия, Дата_время, Сумма, Статья_расходов, Объект, File_ID_чека]
        project_id: ID проекта
        compensation_status: ожидает/частично_оплачено/оплачено
        operation_type: расход/аванс/возврат
    """
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_EXPENSES)
        
        extended_data = data + [project_id, compensation_status, operation_type]
        sheet.append_row(extended_data, value_input_option="USER_ENTERED")
        
        logger.info(f"✅ Расход добавлен (проект: {project_id}): {data}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка записи расхода: {e}")
        return False
# ============ СИСТЕМА БАЛАНСОВ (ДОБАВЛЕНО) ============

async def get_employee_balance(telegram_id: int) -> float:
    """
    Получить текущий баланс сотрудника.
    Баланс хранится в колонке H (индекс 7) листа "Сотрудники".
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()[1:]
        for row in rows:
            if len(row) >= 1 and row[0] == str(telegram_id):
                # Баланс в колонке H (индекс 7)
                balance = float(row[7]) if len(row) > 7 and row[7] else 0.0
                return balance
        
        return 0.0
    except Exception as e:
        logger.error(f"❌ Ошибка получения баланса: {e}")
        return 0.0


async def update_employee_balance(telegram_id: int, amount: float, operation: str) -> bool:
    """
    Обновить баланс сотрудника.
    
    Args:
        telegram_id: ID сотрудника
        amount: Сумма операции
        operation: "expense" (уменьшить), "advance" (увеличить), "compensation" (увеличить)
    
    Returns:
        bool: Успешно ли обновление
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == str(telegram_id):
                # Получаем текущий баланс
                current_balance = float(row[7]) if len(row) > 7 and row[7] else 0.0
                
                # Вычисляем новый баланс
                if operation == "expense":
                    new_balance = current_balance - amount
                elif operation in ["advance", "compensation"]:
                    new_balance = current_balance + amount
                else:
                    logger.error(f"❌ Неизвестная операция: {operation}")
                    return False
                
                # Обновляем баланс в колонке H (8-я колонка)
                sheet.update_cell(idx, 8, str(new_balance))
                logger.info(f"✅ Баланс сотрудника {telegram_id} обновлен: {current_balance} -> {new_balance}")
                return True
        
        logger.warning(f"⚠️ Сотрудник {telegram_id} не найден")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления баланса: {e}")
        return False


async def check_negative_balance(telegram_id: int) -> bool:
    """
    Проверить, не стал ли баланс отрицательным.
    
    Returns:
        bool: True если баланс <= 0
    """
    balance = await get_employee_balance(telegram_id)
    return balance <= 0


async def process_expense_with_balance(
    user_id: int, 
    amount: float, 
    expense_data: list,
    project_id: str = "",
    **kwargs
) -> dict:
    """
    Process expense and update balance.
    
    Args:
        user_id: Telegram ID пользователя
        amount: Сумма расхода
        expense_data: [Имя, Фамилия, Дата_время, Сумма, Статья_расходов, Объект, File_ID_чека]
        project_id: ID проекта
    
    Returns: 
        {'success': bool, 'new_balance': float, 'notification_needed': bool}
    """
    try:
        # 1. Проверяем лимит (существующая функция)
        limit_exceeded, percentage, status = check_limit_status(user_id, amount)
        
        # 2. Списываем с баланса
        balance_updated = await update_employee_balance(user_id, amount, "expense")
        if not balance_updated:
            logger.error(f"❌ Не удалось обновить баланс для {user_id}")
            return {'success': False, 'new_balance': 0.0, 'notification_needed': False}
        
        # 3. Получаем новый баланс
        new_balance = await get_employee_balance(user_id)
        
        # 4. Проверяем необходимость уведомления (баланс <= 0)
        notification_needed = new_balance <= 0
        
        # 5. Сохраняем расход
        saved = append_expense_row_extended(
            data=expense_data,
            project_id=project_id,
            compensation_status="ожидает" if notification_needed else "не_требуется",
            operation_type="расход"
        )
        
        if not saved:
            # Откатываем баланс если не удалось сохранить
            await update_employee_balance(user_id, amount, "advance")
            return {'success': False, 'new_balance': new_balance, 'notification_needed': False}
        
        # 6. Если баланс <= 0, создаём запрос на компенсацию
        if notification_needed:
            await create_compensation_request(
                employee_id=user_id,
                amount=abs(new_balance),
                request_type="автоматический",
                comment=f"Автоматический запрос при отрицательном балансе после расхода {amount}"
            )
        
        return {
            'success': True, 
            'new_balance': new_balance, 
            'notification_needed': notification_needed,
            'limit_exceeded': limit_exceeded,
            'limit_percentage': percentage,
            'limit_status': status
        }
    except Exception as e:
        logger.error(f"❌ Ошибка обработки расхода с балансом: {e}")
        return {'success': False, 'new_balance': 0.0, 'notification_needed': False}


async def add_advance_payment(telegram_id: int, amount: float, comment: str = "") -> bool:
    """
    Добавить аванс сотруднику (увеличить баланс).
    
    Args:
        telegram_id: ID сотрудника
        amount: Сумма аванса
        comment: Комментарий
    
    Returns:
        bool: Успешно ли добавление
    """
    try:
        # Обновляем баланс
        success = await update_employee_balance(telegram_id, amount, "advance")
        if not success:
            return False
        
        # Добавляем запись в расходы как операция типа "аванс"
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        # Получаем данные сотрудника
        employees = get_employees_from_sheet()
        emp_data = employees.get(telegram_id, {})
        first_name = emp_data.get("first_name", "")
        last_name = emp_data.get("last_name", "")
        
        now = datetime.now()
        timestamp = now.strftime("%d.%m.%Y %H:%M:%S")
        
        row = [
            first_name,
            last_name,
            timestamp,
            str(amount),
            "Аванс",
            comment or "Пополнение баланса",
            "",
            "",
            "",
            "аванс"
        ]
        
        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"✅ Аванс {amount} добавлен сотруднику {telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка добавления аванса: {e}")
        return False


async def get_all_employee_balances() -> list:
    """
    Получить балансы всех сотрудников.
    
    Returns:
        list: [{telegram_id, name, balance, role}, ...]
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()[1:]
        balances = []
        
        for row in rows:
            if len(row) >= 5:
                try:
                    telegram_id = int(row[0])
                    first_name = row[1] if len(row) > 1 else ""
                    last_name = row[2] if len(row) > 2 else ""
                    role = row[4] if len(row) > 4 else ""
                    balance = float(row[7]) if len(row) > 7 and row[7] else 0.0
                    
                    balances.append({
                        'telegram_id': telegram_id,
                        'name': f"{first_name} {last_name}".strip(),
                        'balance': balance,
                        'role': role
                    })
                except (ValueError, IndexError):
                    continue
        
        return balances
    except Exception as e:
        logger.error(f"❌ Ошибка получения балансов: {e}")
        return []


async def get_negative_balances() -> list:
    """
    Получить список сотрудников с отрицательным балансом.
    
    Returns:
        list: [{telegram_id, name, balance}, ...]
    """
    all_balances = await get_all_employee_balances()
    return [b for b in all_balances if b['balance'] < 0]


# ============ КОМПЕНСАЦИИ (ДОБАВЛЕНО) ============

async def create_compensation_request(
    employee_id: int,
    amount: float,
    request_type: str = "ручной",
    comment: str = ""
) -> bool:
    """
    Создать запрос на компенсацию.
    
    Args:
        employee_id: ID сотрудника
        amount: Сумма компенсации
        request_type: "ручной" или "автоматический"
        comment: Комментарий
    
    Returns:
        bool: Успешно ли создание
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_COMPENSATIONS)
        
        # Генерируем ID
        rows = sheet.get_all_values()
        comp_id = str(len(rows))
        
        now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        row = [
            comp_id,
            str(employee_id),
            str(amount),
            request_type,
            "ожидает",
            now,
            "",  # Дата выплаты пока пустая
            comment
        ]
        
        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"✅ Создан запрос на компенсацию {comp_id} для {employee_id} на сумму {amount}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания запроса на компенсацию: {e}")
        return False


async def get_compensation_requests(
    status_filter: str = "all",
    employee_id: int = None
) -> list:
    """
    Получить запросы на компенсацию.
    
    Args:
        status_filter: "all", "ожидает", "одобрено", "отклонено", "выплачено"
        employee_id: Фильтр по ID сотрудника (None = все)
    
    Returns:
        list: [{id, employee_id, amount, type, status, date_request, date_paid, comment}, ...]
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_COMPENSATIONS)
        
        rows = sheet.get_all_values()[1:]
        requests = []
        
        for row in rows:
            if len(row) >= 5:
                try:
                    req = {
                        'id': row[0],
                        'employee_id': int(row[1]),
                        'amount': float(row[2]),
                        'type': row[3] if len(row) > 3 else "",
                        'status': row[4] if len(row) > 4 else "",
                        'date_request': row[5] if len(row) > 5 else "",
                        'date_paid': row[6] if len(row) > 6 else "",
                        'comment': row[7] if len(row) > 7 else ""
                    }
                    
                    # Фильтр по статусу
                    if status_filter != "all" and req['status'] != status_filter:
                        continue
                    
                    # Фильтр по сотруднику
                    if employee_id is not None and req['employee_id'] != employee_id:
                        continue
                    
                    requests.append(req)
                except (ValueError, IndexError):
                    continue
        
        return requests
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения запросов на компенсацию: {e}")
        return []


def get_expenses_by_status(status_filter: str = "all") -> list:
    """
    Получить расходы по статусу компенсации.
    
    Args:
        status_filter: "all", "ожидает", "одобрено", "отклонено", "no_compensation"
    
    Returns:
        list: [{row_idx, name, date, amount, category, object, compensation_status, project_id}, ...]
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        rows = sheet.get_all_values()[1:]
        expenses = []
        
        for idx, row in enumerate(rows, start=2):
            if len(row) >= 7:
                comp_status = row[8] if len(row) > 8 else ""
                
                # Фильтр по статусу
                if status_filter != "all":
                    if status_filter == "no_compensation":
                        if comp_status in ["", "оплачено", "не_требуется"]:
                            continue
                    elif comp_status != status_filter:
                        continue
                
                expenses.append({
                    'row_idx': idx,
                    'name': f"{row[0]} {row[1]}",
                    'date': row[2],
                    'amount': row[3],
                    'category': row[4],
                    'object': row[5],
                    'file_id': row[6] if len(row) > 6 else "",
                    'compensation_status': comp_status,
                    'project_id': row[7] if len(row) > 7 else ""
                })
        
        return expenses
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов по статусу: {e}")
        return []


def get_employee_expenses(telegram_id: int, status_filter: str = "all") -> list:
    """
    Получить расходы конкретного сотрудника.
    
    Args:
        telegram_id: ID сотрудника
        status_filter: "all", "ожидает", "одобрено", "отклонено", "no_compensation"
    
    Returns:
        list: [{row_idx, name, date, amount, category, object, compensation_status}, ...]
    """
    try:
        # Получаем имя сотрудника
        employees = get_employees_from_sheet()
        emp_data = employees.get(telegram_id, {})
        first_name = emp_data.get("first_name", "")
        last_name = emp_data.get("last_name", "")
        
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        rows = sheet.get_all_values()[1:]
        expenses = []
        
        for idx, row in enumerate(rows, start=2):
            if len(row) >= 7 and row[0] == first_name and row[1] == last_name:
                comp_status = row[8] if len(row) > 8 else ""
                
                # Фильтр по статусу
                if status_filter != "all":
                    if status_filter == "no_compensation":
                        if comp_status in ["", "оплачено", "не_требуется"]:
                            continue
                    elif comp_status != status_filter:
                        continue
                
                expenses.append({
                    'row_idx': idx,
                    'name': f"{row[0]} {row[1]}",
                    'date': row[2],
                    'amount': row[3],
                    'category': row[4],
                    'object': row[5],
                    'file_id': row[6] if len(row) > 6 else "",
                    'compensation_status': comp_status
                })
        
        return expenses
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов сотрудника: {e}")
        return []


def update_compensation_status(
    row_idx: int,
    status: str,
    amount: float = None,
    method: str = None,
    comment: str = None
) -> bool:
    """
    Обновить статус компенсации в листе Расходы.
    
    Args:
        row_idx: Номер строки
        status: Новый статус
        amount: Сумма компенсации (опционально)
        method: Способ оплаты (опционально)
        comment: Комментарий (опционально)
    
    Returns:
        bool: Успешно ли обновление
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        # Обновляем статус в колонке I (9-я колонка)
        sheet.update_cell(row_idx, 9, status)
        
        # Дополнительные поля можно сохранить в комментарии или другом месте
        if comment:
            current_comment = sheet.cell(row_idx, 10).value or ""
            new_comment = f"{current_comment}; {comment}".strip("; ")
            sheet.update_cell(row_idx, 10, new_comment)
        
        logger.info(f"✅ Статус компенсации в строке {row_idx} обновлен на '{status}'")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса компенсации: {e}")
        return False


async def get_expenses_by_employee_and_period(
    telegram_id: int,
    start_date: datetime,
    end_date: datetime
) -> list:
    """
    Получить расходы сотрудника за период.
    
    Args:
        telegram_id: ID сотрудника
        start_date: Начало периода
        end_date: Конец периода
    
    Returns:
        list: [{date, amount, category, project, compensation_status}, ...]
    """
    try:
        # Получаем имя сотрудника
        employees = get_employees_from_sheet()
        emp_data = employees.get(telegram_id, {})
        first_name = emp_data.get("first_name", "")
        last_name = emp_data.get("last_name", "")
        
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        rows = sheet.get_all_values()[1:]
        expenses = []
        
        for row in rows:
            if len(row) >= 7 and row[0] == first_name and row[1] == last_name:
                try:
                    # Парсим дату из строки формата "DD.MM.YYYY HH:MM:SS"
                    date_str = row[2].split()[0] if row[2] else ""
                    row_date = datetime.strptime(date_str, "%d.%m.%Y")
                    
                    # Проверяем попадание в период
                    if start_date <= row_date <= end_date:
                        # Получаем название проекта
                        project_id = row[7] if len(row) > 7 else ""
                        project_name = ""
                        if project_id:
                            projects = get_all_projects()
                            for p in projects:
                                if p['id'] == project_id:
                                    project_name = p['name']
                                    break
                        
                        expenses.append({
                            'date': row[2],
                            'amount': float(row[3]) if row[3] else 0.0,
                            'category': row[4],
                            'project': project_name or row[5],  # Если нет проекта, показываем объект
                            'compensation_status': row[8] if len(row) > 8 else ""
                        })
                except (ValueError, IndexError):
                    continue
        
        return expenses
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов за период: {e}")
        return []


async def get_expenses_by_project(
    project_id: str = None,
    start_date: datetime = None,
    end_date: datetime = None
) -> list:
    """
    Получить расходы по проекту за период.
    
    Args:
        project_id: ID проекта (None = все проекты)
        start_date: Начало периода
        end_date: Конец периода
    
    Returns:
        list: [{employee_name, date, amount, category, project_name}, ...]
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        rows = sheet.get_all_values()[1:]
        expenses = []
        
        for row in rows:
            if len(row) < 7:
                continue
            
            row_project_id = row[7] if len(row) > 7 else ""
            
            # Фильтр по проекту
            if project_id is not None and row_project_id != project_id:
                continue
            
            # Фильтр по дате
            if start_date and end_date and row[2]:
                try:
                    date_str = row[2].split()[0]
                    row_date = datetime.strptime(date_str, "%d.%m.%Y")
                    if not (start_date <= row_date <= end_date):
                        continue
                except ValueError:
                    continue
            
            # Получаем название проекта
            project_name = ""
            if row_project_id:
                projects = get_all_projects()
                for p in projects:
                    if p['id'] == row_project_id:
                        project_name = p['name']
                        break
            
            expenses.append({
                'employee_name': f"{row[0]} {row[1]}",
                'date': row[2],
                'amount': float(row[3]) if row[3] else 0.0,
                'category': row[4],
                'project_name': project_name or row[5]
            })
        
        return expenses
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов по проекту: {e}")
        return []


# ============ УВЕДОМЛЕНИЯ О ЛИМИТАХ (ДОБАВЛЕНО) ============

async def notify_limit_warning(telegram_id: int, percentage: float, current: float, limit: float):
    """
    Отправить уведомление при превышении 80% лимита.
    Уведомление: сотрудник + контролёры + владелец.
    
    Args:
        telegram_id: ID сотрудника
        percentage: Процент использования лимита
        current: Текущая сумма расходов
        limit: Установленный лимит
    """
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    from utils.google_sheets import get_employees_from_sheet
    
    try:
        bot = Bot(TELEGRAM_TOKEN)
        employees = get_employees_from_sheet()
        emp_data = employees.get(telegram_id, {})
        emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
        
        # Уведомление сотруднику
        try:
            text = (
                f"⚡ <b>Внимание! Приближение к лимиту</b>\n\n"
                f"Вы использовали {percentage:.1f}% от вашего лимита.\n"
                f"Текущие расходы: {current:.2f}₽ из {limit:.2f}₽\n\n"
                f"Будьте внимательны при добавлении новых расходов."
            )
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление сотруднику {telegram_id}: {e}")
        
        # Уведомление контролёрам и владельцу
        text_admin = (
            f"⚡ <b>Превышение 80% лимита</b>\n\n"
            f"Сотрудник: {emp_name} (ID: {telegram_id})\n"
            f"Использовано: {percentage:.1f}% ({current:.2f}₽ из {limit:.2f}₽)\n\n"
            f"Рекомендуется проверить расходы."
        )
        
        for emp_id, emp in employees.items():
            if emp.get("role") in [ROLE_CONTROLLER, ROLE_OWNER]:
                try:
                    await bot.send_message(chat_id=emp_id, text=text_admin, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить уведомление {emp_id}: {e}")
        
        await bot.session.close()
        logger.info(f"✅ Уведомление о лимите 80% отправлено для {telegram_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления о лимите: {e}")


async def notify_limit_exceeded(telegram_id: int, current: float, limit: float, amount: float):
    """
    Отправить уведомление при превышении 100% лимита.
    Запрос подтверждения у главбуха + уведомление владельцу.
    
    Args:
        telegram_id: ID сотрудника
        current: Текущая сумма расходов (с новым)
        limit: Установленный лимит
        amount: Сумма нового расхода
    """
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    from utils.google_sheets import get_employees_from_sheet
    
    try:
        bot = Bot(TELEGRAM_TOKEN)
        employees = get_employees_from_sheet()
        emp_data = employees.get(telegram_id, {})
        emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
        
        # Уведомление сотруднику
        try:
            text = (
                f"🚫 <b>Лимит превышен!</b>\n\n"
                f"Ваши расходы ({current:.2f}₽) превышают установленный лимит ({limit:.2f}₽).\n"
                f"Новый расход ({amount:.2f}₽) требует подтверждения главбуха.\n\n"
                f"Ожидайте решения."
            )
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить уведомление сотруднику {telegram_id}: {e}")
        
        # Уведомление главбуху и владельцу с запросом подтверждения
        text_admin = (
            f"🚨 <b>Требуется подтверждение расхода</b>\n\n"
            f"Сотрудник: {emp_name} (ID: {telegram_id})\n"
            f"Новый расход: {amount:.2f}₽\n"
            f"Текущие расходы: {current:.2f}₽\n"
            f"Лимит: {limit:.2f}₽\n"
            f"Превышение: {current - limit:.2f}₽\n\n"
            f"Для одобрения используйте: /approve_expense\n"
            f"Или проверьте: /compensations"
        )
        
        for emp_id, emp in employees.items():
            if emp.get("role") in [ROLE_CHIEF_ACCOUNTANT, ROLE_OWNER]:
                try:
                    await bot.send_message(chat_id=emp_id, text=text_admin, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить уведомление {emp_id}: {e}")
        
        await bot.session.close()
        logger.info(f"✅ Уведомление о превышении лимита отправлено для {telegram_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления о превышении: {e}")


# Константы ролей для использования в этом модуле
ROLE_OWNER = "владелец"
ROLE_CHIEF_ACCOUNTANT = "главбух"
ROLE_CONTROLLER = "контролер"
ROLE_EMPLOYEE = "подотчетник"


# ============ НАСТРОЙКИ ПОДПИСКИ НА ОТЧЁТЫ (ДОБАВЛЕНО) ============

async def get_employees_with_subscription(report_type: str) -> list:
    """
    Получить список сотрудников с активной подпиской на отчёт.
    
    Args:
        report_type: 'daily', 'weekly', 'monthly', 'daily_admin', 
                     'weekly_admin', 'monthly_admin', 'balance_alert'
    
    Returns:
        list: [telegram_id, ...]
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()
        
        # Определяем индекс колонки в зависимости от типа подписки
        # Колонки: I=9, J=10, K=11, L=12, M=13, N=14, O=15
        col_map = {
            'daily': 9,
            'weekly': 10,
            'monthly': 11,
            'daily_admin': 12,
            'weekly_admin': 13,
            'monthly_admin': 14,
            'balance_alert': 15,
        }
        
        col_idx = col_map.get(report_type, 9)
        subscribers = []
        
        for row in rows[1:]:  # Пропускаем заголовок
            if len(row) >= col_idx:
                try:
                    telegram_id = int(row[0])
                    # Проверяем значение подписки (да/1/true)
                    sub_value = row[col_idx - 1].lower().strip() if row[col_idx - 1] else ""
                    if sub_value in ['да', '1', 'true', 'yes', 'вкл']:
                        subscribers.append(telegram_id)
                except (ValueError, IndexError):
                    continue
        
        logger.info(f"✅ Найдено {len(subscribers)} подписчиков для '{report_type}'")
        return subscribers
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения подписчиков: {e}")
        return []


async def update_subscription(telegram_id: int, report_type: str, enabled: bool) -> bool:
    """
    Включить/выключить подписку на отчёт.
    
    Args:
        telegram_id: ID сотрудника
        report_type: Тип отчёта
        enabled: True - включить, False - выключить
    
    Returns:
        bool: Успешно ли обновление
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        # Определяем индекс колонки
        col_map = {
            'daily': 9,
            'weekly': 10,
            'monthly': 11,
            'daily_admin': 12,
            'weekly_admin': 13,
            'monthly_admin': 14,
            'balance_alert': 15,
        }
        
        col_idx = col_map.get(report_type, 9)
        
        # Ищем сотрудника
        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == str(telegram_id):
                # Обновляем значение
                value = "да" if enabled else "нет"
                sheet.update_cell(idx, col_idx, value)
                
                logger.info(f"✅ Подписка '{report_type}' для {telegram_id}: {value}")
                return True
        
        logger.warning(f"⚠️ Сотрудник {telegram_id} не найден")
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления подписки: {e}")
        return False


async def get_employee_subscriptions(telegram_id: int) -> dict:
    """
    Получить статусы всех подписок сотрудника.
    
    Args:
        telegram_id: ID сотрудника
    
    Returns:
        dict: {report_type: enabled, ...}
    """
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EMPLOYEES)
        
        rows = sheet.get_all_values()
        
        for row in rows[1:]:
            if row[0] == str(telegram_id) and len(row) >= 15:
                def is_enabled(val):
                    return val.lower().strip() in ['да', '1', 'true', 'yes', 'вкл'] if val else False
                
                return {
                    'daily': is_enabled(row[8] if len(row) > 8 else ""),
                    'weekly': is_enabled(row[9] if len(row) > 9 else ""),
                    'monthly': is_enabled(row[10] if len(row) > 10 else ""),
                    'daily_admin': is_enabled(row[11] if len(row) > 11 else ""),
                    'weekly_admin': is_enabled(row[12] if len(row) > 12 else ""),
                    'monthly_admin': is_enabled(row[13] if len(row) > 13 else ""),
                    'balance_alert': is_enabled(row[14] if len(row) > 14 else ""),
                }
        
        # По умолчанию - все выключены
        return {
            'daily': False,
            'weekly': False,
            'monthly': False,
            'daily_admin': False,
            'weekly_admin': False,
            'monthly_admin': False,
            'balance_alert': False,
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения подписок: {e}")
        return {}
