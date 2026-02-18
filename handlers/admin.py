from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from keyboards.main_menu import get_admin_menu, get_user_menu, get_back_keyboard
from utils.google_sheets import (
    add_employee_to_sheet,
    block_employee,
    check_photo_ownership,
    get_all_expenses,
    get_employees_from_sheet,
)
from utils.sheets_extended import set_employee_limit
from utils.states import AdminStates, ViewStates, LimitStates
from utils.decorators import role_required, ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT

router = Router()


# ===== КНОПКИ ГЛАВНОГО МЕНЮ =====


@router.message(F.text == "Добавить сумму")
async def add_from_button(message: Message, state: FSMContext, user_first_name: str, user_last_name: str):
    """
    Кнопка 'Добавить сумму' вызывает тот же сценарий, что и /add.
    Сам сценарий реализован в handlers/expense_flow.py, здесь только прокси.
    """
    # Импорт делается локально, чтобы избежать циклических импортов
    from handlers.expense_flow import start_expense_flow

    await start_expense_flow(message, state, user_first_name, user_last_name)


@router.message(F.text == "Просмотр чека")
async def view_from_button(message: Message, state: FSMContext):
    """
    Кнопка 'Просмотр чека' вызывает сценарий /view.
    """
    await view_start(message, state)


@router.message(F.text == "Добавить сотрудника")
async def add_employee_from_button(message: Message, is_admin: bool, state: FSMContext):
    await add_employee_start(message, is_admin, state)


@router.message(F.text == "Заблокировать")
async def remove_employee_from_button(message: Message, is_admin: bool, state: FSMContext):
    await remove_employee_start(message, is_admin, state)


@router.message(F.text == "Статистика")
async def stats_from_button(message: Message, is_admin: bool):
    await show_stats(message, is_admin)


@router.message(F.text == "Список пользователей")
async def users_from_button(message: Message, is_admin: bool):
    await show_users(message, is_admin)


# ===== ДОБАВЛЕНИЕ СОТРУДНИКА =====


@router.message(Command("add_employee"))
async def add_employee_start(message: Message, is_admin: bool, state: FSMContext):
    if not is_admin:
        await message.answer("Команда доступна только администраторам")
        return
    await state.set_state(AdminStates.waiting_for_employee_id)
    await message.answer(
        "Введите ID Telegram сотрудника:",
        reply_markup=get_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_employee_id)
async def add_employee_get_id(message: Message, state: FSMContext):
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return

    try:
        emp_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число — Telegram ID сотрудника")
        return
    await state.update_data(employee_id=emp_id)
    await state.set_state(AdminStates.waiting_for_employee_first_name)
    await message.answer("Введите Имя сотрудника:", reply_markup=get_back_keyboard())


@router.message(AdminStates.waiting_for_employee_first_name)
async def add_employee_get_first_name(message: Message, state: FSMContext):
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return

    if not message.text or not message.text.strip():
        await message.answer("Имя не может быть пустым")
        return
    await state.update_data(first_name=message.text.strip())
    await state.set_state(AdminStates.waiting_for_employee_last_name)
    await message.answer("Введите Фамилию сотрудника:", reply_markup=get_back_keyboard())


@router.message(AdminStates.waiting_for_employee_last_name)
async def add_employee_finish(message: Message, state: FSMContext):
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return

    if not message.text or not message.text.strip():
        await message.answer("Фамилия не может быть пустой")
        return

    data = await state.get_data()
    emp_id = data["employee_id"]
    first_name = data["first_name"]
    last_name = message.text.strip()

    ok = add_employee_to_sheet(emp_id, first_name, last_name, role="Сотрудник")

    await state.clear()
    if ok:
        await message.answer(
            f"Сотрудник добавлен!\n\n"
            f"ID: {emp_id}\n"
            f"Имя: {first_name}\n"
            f"Фамилия: {last_name}\n\n"
            "Доступ появится через несколько минут.",
            reply_markup=get_admin_menu(),
        )
    else:
        await message.answer("Ошибка при добавлении сотрудника", reply_markup=get_admin_menu())


# ===== БЛОКИРОВКА СОТРУДНИКА =====


@router.message(Command("remove_employee"))
async def remove_employee_start(message: Message, is_admin: bool, state: FSMContext):
    if not is_admin:
        await message.answer("Команда доступна только администраторам")
        return
    await state.set_state(AdminStates.waiting_for_remove_id)
    await message.answer(
        "Введите ID сотрудника для блокировки:",
        reply_markup=get_back_keyboard(),
    )


@router.message(AdminStates.waiting_for_remove_id)
async def remove_employee_finish(message: Message, state: FSMContext):
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return

    try:
        emp_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число")
        return

    ok = block_employee(emp_id)
    await state.clear()

    if ok:
        await message.answer(
            f"Сотрудник {emp_id} заблокирован.\n\nДоступ закроется через несколько минут.",
            reply_markup=get_admin_menu(),
        )
    else:
        await message.answer("Ошибка: сотрудник не найден", reply_markup=get_admin_menu())


# ===== СТАТИСТИКА И СПИСОК ПОЛЬЗОВАТЕЛЕЙ =====


@router.message(Command("stats"))
async def show_stats(message: Message, is_admin: bool):
    if not is_admin:
        await message.answer("Команда доступна только администраторам")
        return

    expenses = get_all_expenses()
    if not expenses:
        await message.answer("Пока нет данных")
        return

    total = 0.0
    count = len(expenses)
    cats = {}

    for row in expenses:
        if len(row) < 5:
            continue
        try:
            amt = float(row[3])
            total += amt
        except ValueError:
            continue
        cat = row[4]
        cats[cat] = cats.get(cat, 0) + 1

    avg = total / count if count else 0.0
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join(f"{c}: {n}" for c, n in top) or "нет"

    await message.answer(
        f"Статистика расходов:\n\n"
        f"Всего записей: {count}\n"
        f"Общая сумма: {total:.2f} руб.\n"
        f"Средний чек: {avg:.2f} руб.\n\n"
        f"Топ категорий:\n{top_text}"
    )


@router.message(Command("users"))
async def show_users(message: Message, is_admin: bool):
    if not is_admin:
        await message.answer("Команда доступна только администраторам")
        return

    employees = get_employees_from_sheet()

    admins = []
    active_emps = []
    blocked = []

    for emp_id, data in employees.items():
        name = f"{data['first_name']} {data['last_name']}"
        if data["role"] == "Админ":
            admins.append(f"{emp_id} ({name})")
        elif data["status"] == "Заблокирован":
            blocked.append(f"{emp_id} ({name})")
        else:
            active_emps.append(f"{emp_id} ({name})")

    text = "Пользователи:\n\n"
    text += f"Админы ({len(admins)}):\n" + "\n".join(admins or ["нет"]) + "\n\n"
    text += f"Активные ({len(active_emps)}):\n" + "\n".join(active_emps or ["нет"]) + "\n\n"
    text += f"Заблокированные ({len(blocked)}):\n" + "\n".join(blocked or ["нет"])

    await message.answer(text)


# ===== ПРОСМОТР ЧЕКА =====


@router.message(Command("view"))
async def view_start(message: Message, state: FSMContext):
    await state.set_state(ViewStates.waiting_for_file_id)
    await message.answer(
        "Отправьте File ID чека одной строкой",
        reply_markup=get_back_keyboard(),
    )


@router.message(ViewStates.waiting_for_file_id)
async def view_process_file_id(
    message: Message,
    state: FSMContext,
    is_admin: bool,
    user_first_name: str,
    user_last_name: str,
):
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin)
        return

    file_id = (message.text or "").strip()
    await state.clear()

    if not file_id:
        await message.answer("File ID не может быть пустым")
        return
    if file_id == "Нет чека":
        await message.answer("Для этой записи чек не прикреплен")
        return

    if not is_admin:
        if not check_photo_ownership(file_id, user_first_name, user_last_name):
            await message.answer("Вы можете просматривать только свои чеки")
            return

    try:
        caption = "Чек (админ)" if is_admin else "Ваш чек"
        await message.answer_photo(photo=file_id, caption=caption, reply_markup=get_admin_menu() if is_admin else get_user_menu())
    except Exception:
        await message.answer("Не удалось загрузить фото. File ID некорректен или устарел")


# ===== УПРАВЛЕНИЕ ЛИМИТАМИ =====

@router.message(Command("set_limit"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def set_limit_start(message: Message, state: FSMContext, user_role: str = None):
    """Начать установку лимита сотруднику."""
    await state.set_state(LimitStates.waiting_for_employee)
    await message.answer(
        "Введите Telegram ID сотрудника для установки лимита:",
        reply_markup=get_back_keyboard(),
    )


@router.message(LimitStates.waiting_for_employee)
async def set_limit_employee(message: Message, state: FSMContext):
    """Получить ID сотрудника."""
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return
    
    try:
        emp_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число — Telegram ID")
        return
    
    # Проверяем что сотрудник существует
    employees = get_employees_from_sheet()
    if emp_id not in employees:
        await message.answer("Сотрудник с таким ID не найден")
        return
    
    await state.update_data(employee_id=emp_id)
    await state.set_state(LimitStates.waiting_for_limit_amount)
    await message.answer(
        f"Сотрудник: {employees[emp_id]['first_name']} {employees[emp_id]['last_name']}\n\n"
        "Введите сумму лимита (в рублях):",
        reply_markup=get_back_keyboard(),
    )


@router.message(LimitStates.waiting_for_limit_amount)
async def set_limit_amount(message: Message, state: FSMContext):
    """Получить сумму лимита."""
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return
    
    try:
        limit = float(message.text.replace(",", ".").replace(" ", ""))
        if limit < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число")
        return
    
    await state.update_data(limit_amount=limit)
    await state.set_state(LimitStates.waiting_for_limit_period)
    
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="день")],
            [KeyboardButton(text="неделя")],
            [KeyboardButton(text="месяц")],
            [KeyboardButton(text="⬅ Назад")],
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Выберите период лимита:",
        reply_markup=keyboard,
    )


@router.message(LimitStates.waiting_for_limit_period)
async def set_limit_period(message: Message, state: FSMContext):
    """Получить период и сохранить лимит."""
    if message.text == "⬅ Назад":
        await back_to_menu(message, state, is_admin=True)
        return
    
    period = message.text.strip().lower()
    if period not in ["день", "неделя", "месяц"]:
        await message.answer("Выберите: день, неделя или месяц")
        return
    
    data = await state.get_data()
    emp_id = data["employee_id"]
    limit = data["limit_amount"]
    
    success = set_employee_limit(emp_id, limit, period)
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ Лимит установлен!\n\n"
            f"Сотрудник ID: {emp_id}\n"
            f"Лимит: {limit:.2f} руб.\n"
            f"Период: {period}",
            reply_markup=get_admin_menu(),
        )
    else:
        await message.answer(
            "❌ Ошибка при установке лимита",
            reply_markup=get_admin_menu(),
        )


# ===== КНОПКА НАЗАД =====


async def back_to_menu(message: Message, state: FSMContext, is_admin: bool):
    """
    Универсальный возврат в главное меню.
    """
    await state.clear()
    keyboard = get_admin_menu() if is_admin else get_user_menu()
    await message.answer("Главное меню.", reply_markup=keyboard)
