from aiogram.fsm.state import State, StatesGroup


class ExpenseStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()
    waiting_for_category_manual = State()
    waiting_for_object = State()
    waiting_for_photo = State()
    waiting_for_confirmation = State()


class AdminStates(StatesGroup):
    waiting_for_employee_id = State()
    waiting_for_employee_first_name = State()
    waiting_for_employee_last_name = State()
    waiting_for_remove_id = State()


class ViewStates(StatesGroup):
    waiting_for_file_id = State()
