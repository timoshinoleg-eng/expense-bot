"""
Утилиты для генерации Excel-отчётов.
Использует pandas + openpyxl.
"""
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# Константа: если строк больше этого числа — генерируем Excel
EXCEL_THRESHOLD = 50

# Директория для временных файлов
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_reports")


def ensure_temp_dir():
    """Создать директорию для временных файлов если не существует."""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
        logger.info(f"✅ Создана директория для отчётов: {TEMP_DIR}")


async def generate_expense_report(data: List[Dict], filename: str) -> Optional[str]:
    """
    Создать Excel-файл отчёта.
    
    Args:
        data: Список словарей с данными [{колонка: значение}, ...]
        filename: Имя файла без расширения
    
    Returns:
        str: Путь к созданному файлу или None (если данных мало — возвращаем None для текстового вывода)
    """
    try:
        # Если данных мало — возвращаем None, пусть выводят текстом
        if len(data) <= EXCEL_THRESHOLD:
            logger.info(f"📊 Данных мало ({len(data)}), выводим текстом")
            return None
        
        # Создаём DataFrame
        df = pd.DataFrame(data)
        
        # Форматируем числовые колонки
        for col in df.columns:
            if df[col].dtype in ['float64', 'int64']:
                # Форматируем как деньги если название колонки содержит "Сумма" или "сумма"
                if 'сумма' in col.lower() or 'amount' in col.lower() or 'balance' in col.lower():
                    df[col] = df[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
        
        # Создаём директорию если нужно
        ensure_temp_dir()
        
        # Формируем путь к файлу
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(TEMP_DIR, f"{filename}_{timestamp}.xlsx")
        
        # Создаём Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Отчёт')
            
            # Получаем workbook и worksheet для форматирования
            workbook = writer.book
            worksheet = writer.sheets['Отчёт']
            
            # Автоподбор ширины колонок
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                
                adjusted_width = min(max_length + 2, 50)  # Максимум 50 символов
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"✅ Excel отчёт создан: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания Excel отчёта: {e}")
        return None


async def generate_project_report(
    project_name: str,
    expenses: List[Dict],
    start_date: datetime,
    end_date: datetime,
    filename: str
) -> Optional[str]:
    """
    Создать отчёт по проекту.
    
    Args:
        project_name: Название проекта
        expenses: Список расходов
        start_date: Начало периода
        end_date: Конец периода
        filename: Имя файла
    
    Returns:
        str: Путь к файлу или None
    """
    try:
        if not expenses:
            return None
        
        # Создаём DataFrame
        df_expenses = pd.DataFrame(expenses)
        
        # Создаём сводную таблицу по категориям
        if 'category' in df_expenses.columns:
            summary = df_expenses.groupby('category')['amount'].agg(['sum', 'count']).reset_index()
            summary.columns = ['Категория', 'Сумма', 'Количество']
        else:
            summary = pd.DataFrame()
        
        ensure_temp_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(TEMP_DIR, f"{filename}_{timestamp}.xlsx")
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Лист с деталями
            df_expenses.to_excel(writer, index=False, sheet_name='Детали')
            
            # Лист со сводкой
            if not summary.empty:
                summary.to_excel(writer, index=False, sheet_name='Сводка')
            
            # Форматируем
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"✅ Отчёт по проекту создан: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания отчёта по проекту: {e}")
        return None


async def generate_balance_report(
    balances: List[Dict],
    filename: str
) -> Optional[str]:
    """
    Создать отчёт по балансам сотрудников.
    
    Args:
        balances: Список балансов [{telegram_id, name, balance, role}, ...]
        filename: Имя файла
    
    Returns:
        str: Путь к файлу или None
    """
    try:
        if not balances:
            return None
        
        df = pd.DataFrame(balances)
        
        # Переименовываем колонки
        df = df.rename(columns={
            'name': 'Сотрудник',
            'balance': 'Баланс',
            'role': 'Роль'
        })
        
        # Убираем telegram_id из вывода
        if 'telegram_id' in df.columns:
            df = df.drop(columns=['telegram_id'])
        
        # Сортируем по балансу (отрицательные первыми)
        df = df.sort_values('Баланс')
        
        ensure_temp_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(TEMP_DIR, f"{filename}_{timestamp}.xlsx")
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Балансы')
            
            # Форматируем
            worksheet = writer.sheets['Балансы']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"✅ Отчёт по балансам создан: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания отчёта по балансам: {e}")
        return None


async def cleanup_temp_file(filepath: str):
    """
    Удалить временный файл после отправки.
    
    Args:
        filepath: Путь к файлу
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"🗑️ Временный файл удалён: {filepath}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить временный файл {filepath}: {e}")


async def cleanup_old_reports(max_age_hours: int = 24):
    """
    Очистить старые временные файлы отчётов.
    
    Args:
        max_age_hours: Максимальный возраст файла в часах
    """
    try:
        if not os.path.exists(TEMP_DIR):
            return
        
        now = datetime.now()
        count = 0
        
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                age_hours = (now - file_time).total_seconds() / 3600
                
                if age_hours > max_age_hours:
                    os.remove(filepath)
                    count += 1
        
        if count > 0:
            logger.info(f"🗑️ Удалено {count} старых отчётов")
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки старых отчётов: {e}")
