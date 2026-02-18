from aiogram.fsm.state import State, StatesGroup


class ExpenseStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()
    waiting_for_category_manual = State()
    waiting_for_object = State()
    waiting_for_project = State()  # Новое: выбор проекта
    waiting_for_photo = State()
    waiting_for_confirmation = State()


class AdminStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_employee_first_name = State()
    waiting_for_employee_last_name = State()
    waiting_for_remove_id = State()
    waiting_for_employee_role = State()  # Новое: выбор роли
    waiting_for_employee_limit = State()  # Новое: установка лимита


class ViewStates(StatesGroup):
    waiting_for_file_id = State()


# ============ НОВЫЕ СОСТОЯНИЯ ============

class ProjectStates(StatesGroup):
    """Состояния для управления проектами."""
    waiting_for_name = State()
    waiting_for_budget = State()
    waiting_for_dates = State()


class LimitStates(StatesGroup):
    """Состояния для управления лимитами."""
    waiting_for_employee = State()
    waiting_for_limit_amount = State()
    waiting_for_limit_period = State()


class CompensationStates(StatesGroup):
    """Состояния для компенсаций."""
    selecting_expense = State()
    entering_amount = State()
    entering_method = State()
    entering_reject_reason = State()


# ДОБАВЛЕНО: Состояния для отчётов
class ReportStates(StatesGroup):
    """Состояния для генерации отчётов."""
    selecting_period = State()
    selecting_employee = State()
    selecting_project = State()
    selecting_report_type = State()
