from typing import Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials

from config.settings import GOOGLE_SHEETS_CREDENTIALS, SPREADSHEET_ID


def get_sheets_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS, scopes=scopes
    )
    return gspread.authorize(credentials)


def get_employees_from_sheet():
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)

        try:
            sheet = doc.worksheet("Сотрудники")
        except gspread.WorksheetNotFound:
            sheet = doc.add_worksheet(title="Сотрудники", rows=100, cols=5)
            sheet.update("A1:E1", [["ID", "Имя", "Фамилия", "Статус", "Роль"]])
            print("Лист Сотрудники создан. Добавьте первого админа вручную!")
            return {}

        rows = sheet.get_all_values()[1:]

        employees = {}
        for row in rows:
            if len(row) < 5:
                continue
            try:
                emp_id = int(row[0])
                employees[emp_id] = {
                    "first_name": row[1],
                    "last_name": row[2],
                    "status": row[3],
                    "role": row[4],
                }
            except (ValueError, IndexError):
                continue

        return employees
    except Exception as e:
        print(f"Ошибка чтения сотрудников: {e}")
        return {}


def append_expense_row(data):
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        sheet.append_row(data, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Ошибка записи в Google Sheets: {e}")
        return False


def get_all_expenses():
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        return sheet.get_all_values()[1:]
    except Exception as e:
        print(f"Ошибка чтения из Google Sheets: {e}")
        return None


def check_photo_ownership(file_id, first_name, last_name):
    expenses = get_all_expenses()
    if not expenses:
        return False

    for row in expenses:
        if len(row) >= 7 and row[6] == file_id and row[0] == first_name and row[1] == last_name:
            return True
    return False


def add_employee_to_sheet(telegram_id, first_name, last_name, role="Сотрудник"):
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)

        try:
            sheet = doc.worksheet("Сотрудники")
        except gspread.WorksheetNotFound:
            sheet = doc.add_worksheet(title="Сотрудники", rows=100, cols=5)
            sheet.update("A1:E1", [["ID", "Имя", "Фамилия", "Статус", "Роль"]])

        sheet.append_row([str(telegram_id), first_name, last_name, "Активен", role], value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Ошибка записи сотрудника: {e}")
        return False


def block_employee(telegram_id):
    try:
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet("Сотрудники")

        cell = sheet.find(str(telegram_id))
        if cell:
            sheet.update_cell(cell.row, 4, "Заблокирован")
            return True
        return False
    except Exception as e:
        print(f"Ошибка блокировки сотрудника: {e}")
        return False
