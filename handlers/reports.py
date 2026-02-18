"""
Хендлеры для генерации отчётов.
"""
import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from keyboards.main_menu import get_admin_menu, get_user_menu
from utils.decorators import role_required, ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT, ROLE_CONTROLLER, ROLE_EMPLOYEE
from utils.google_sheets import get_employees_from_sheet
from utils.sheets_extended import (
    get_employee_expenses,
    get_expenses_by_employee_and_period,
    get_expenses_by_project,
    get_negative_balances,
    get_all_employee_balances,
    get_all_projects,
)
from utils.reports_excel import generate_expense_report, cleanup_temp_file
from utils.states import ReportStates

router = Router()
logger = logging.getLogger(__name__)


# ============ КОМАНДА /my_report (для подотчётника) ============

@router.message(Command("my_report"))
async def my_report(message: Message, state: FSMContext):
    """Отчёт по своим расходам за период."""
    # Показываем выбор периода
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Эта неделя", callback_data="report_period_week")],
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data="report_period_month")],
        [InlineKeyboardButton(text="📅 Этот квартал", callback_data="report_period_quarter")],
        [InlineKeyboardButton(text="📅 Всё время", callback_data="report_period_all")],
    ])
    
    await state.set_state(ReportStates.selecting_period)
    await message.answer(
        "📊 <b>Мой отчёт по расходам</b>\n\n"
        "Выберите период:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("report_period_"), ReportStates.selecting_period)
async def process_report_period(callback, state: FSMContext):
    """Обработка выбора периода для отчёта."""
    period = callback.data.replace("report_period_", "")
    user_id = callback.from_user.id
    
    # Определяем даты периода
    now = datetime.now()
    if period == "week":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        period_name = "эту неделю"
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_name = "этот месяц"
    elif period == "quarter":
        quarter = (now.month - 1) // 3
        start_date = now.replace(month=quarter * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        period_name = "этот квартал"
    else:  # all
        start_date = datetime(2000, 1, 1)  # С начала времен
        period_name = "всё время"
    
    end_date = now
    
    await callback.message.edit_text(f"⏳ Формирую отчёт за {period_name}...")
    
    # Получаем расходы
    expenses = await get_expenses_by_employee_and_period(user_id, start_date, end_date)
    
    if not expenses:
        await callback.message.edit_text(
            f"📊 <b>Мой отчёт за {period_name}</b>\n\n"
            f"Расходов не найдено.",
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    # Формируем данные для отчёта
    total = sum(e['amount'] for e in expenses)
    
    # Получаем текущий баланс
    from utils.sheets_extended import get_employee_balance
    balance = await get_employee_balance(user_id)
    
    # Формируем таблицу
    report_data = []
    for e in expenses:
        status_emoji = {
            "ожидает": "⏳",
            "одобрено": "✅",
            "отклонено": "❌",
            "выплачено": "💰",
            "не_требуется": "✓"
        }.get(e['compensation_status'], "❓")
        
        report_data.append({
            'Дата': e['date'].split()[0] if ' ' in e['date'] else e['date'],
            'Сумма': e['amount'],
            'Статья': e['category'],
            'Проект': e['project'] or "-",
            'Статус': f"{status_emoji} {e['compensation_status'] or 'не указан'}"
        })
    
    # Генерируем отчёт
    filename = f"my_report_{user_id}_{period}_{now.strftime('%Y%m%d')}"
    report_path = await generate_expense_report(report_data, filename)
    
    # Формируем текст итогов
    summary_text = (
        f"📊 <b>Мой отчёт за {period_name}</b>\n\n"
        f"💰 Всего расходов: {len(expenses)}\n"
        f"💵 Общая сумма: {total:.2f}₽\n"
        f"💳 Текущий баланс: {balance:.2f}₽\n"
    )
    
    if report_path:
        # Отправляем Excel файл
        await callback.message.delete()
        await callback.message.answer_document(
            FSInputFile(report_path),
            caption=summary_text,
            parse_mode="HTML"
        )
        # Очищаем временный файл
        await cleanup_temp_file(report_path)
    else:
        # Выводим текстом (если мало данных)
        table_text = "\n".join([
            f"{e['Дата']} | {e['Сумма']:.0f}₽ | {e['Статья'][:15]} | {e['Статус']}"
            for e in report_data[:20]  # Первые 20 записей
        ])
        
        await callback.message.edit_text(
            f"{summary_text}\n"
            f"<pre>Дата       | Сумма  | Статья          | Статус</pre>\n"
            f"<pre>{'-' * 50}</pre>\n"
            f"<pre>{table_text}</pre>",
            parse_mode="HTML"
        )
    
    await state.clear()


# ============ КОМАНДА /report (для руководства) ============

@router.message(Command("report"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT, ROLE_CONTROLLER])
async def report_menu(message: Message, user_role: str = None):
    """Меню отчётов для руководства."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 По подотчётникам", callback_data="report_type_employees")],
        [InlineKeyboardButton(text="📁 По проектам", callback_data="report_type_projects")],
        [InlineKeyboardButton(text="💸 Долги и компенсации", callback_data="report_type_debts")],
        [InlineKeyboardButton(text="💰 Балансы сотрудников", callback_data="report_type_balances")],
    ])
    
    await message.answer(
        "📊 <b>Меню отчётов</b>\n\n"
        "Выберите тип отчёта:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "report_type_employees")
async def report_by_employees(callback):
    """Отчёт по подотчётникам."""
    employees = get_employees_from_sheet()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for emp_id, emp_data in employees.items():
        if emp_data.get("role") == ROLE_EMPLOYEE:
            name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=f"👤 {name}", callback_data=f"report_emp_{emp_id}")
            ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="report_back")
    ])
    
    await callback.message.edit_text(
        "📊 <b>Отчёт по подотчётнику</b>\n\n"
        "Выберите сотрудника:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("report_emp_"))
async def report_employee_detail(callback):
    """Детальный отчёт по сотруднику."""
    emp_id = int(callback.data.replace("report_emp_", ""))
    employees = get_employees_from_sheet()
    emp_data = employees.get(emp_id, {})
    emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
    
    await callback.message.edit_text(f"⏳ Формирую отчёт для {emp_name}...")
    
    # Получаем расходы за месяц
    now = datetime.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    expenses = await get_expenses_by_employee_and_period(emp_id, start_date, now)
    
    # Получаем баланс
    balance = await get_employee_balance(emp_id)
    
    total = sum(e['amount'] for e in expenses)
    pending = sum(e['amount'] for e in expenses if e['compensation_status'] == "ожидает")
    
    text = (
        f"📊 <b>Отчёт: {emp_name}</b>\n\n"
        f"📅 Период: {start_date.strftime('%d.%m.%Y')} - {now.strftime('%d.%m.%Y')}\n"
        f"💰 Всего расходов: {len(expenses)}\n"
        f"💵 Общая сумма: {total:.2f}₽\n"
        f"⏳ Ожидает компенсации: {pending:.2f}₽\n"
        f"💳 Текущий баланс: {balance:.2f}₽\n"
    )
    
    if balance < 0:
        text += f"\n⚠️ <b>Требуется компенсация!</b>"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="report_type_employees")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "report_type_projects")
async def report_by_projects(callback):
    """Отчёт по проектам."""
    projects = get_all_projects()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for proj in projects:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"📁 {proj['name']}", callback_data=f"report_proj_{proj['id']}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="report_back")
    ])
    
    await callback.message.edit_text(
        "📊 <b>Отчёт по проекту</b>\n\n"
        "Выберите проект:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("report_proj_"))
async def report_project_detail(callback):
    """Детальный отчёт по проекту."""
    project_id = callback.data.replace("report_proj_", "")
    projects = get_all_projects()
    
    project_name = ""
    for p in projects:
        if p['id'] == project_id:
            project_name = p['name']
            break
    
    await callback.message.edit_text(f"⏳ Формирую отчёт по проекту '{project_name}'...")
    
    # Получаем расходы по проекту за месяц
    now = datetime.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    expenses = await get_expenses_by_project(project_id, start_date, now)
    
    total = sum(e['amount'] for e in expenses)
    
    # Группируем по категориям
    by_category = {}
    for e in expenses:
        cat = e['category']
        by_category[cat] = by_category.get(cat, 0) + e['amount']
    
    category_text = "\n".join([
        f"  • {cat}: {amount:.2f}₽"
        for cat, amount in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    ])
    
    text = (
        f"📊 <b>Отчёт по проекту: {project_name}</b>\n\n"
        f"📅 Период: {start_date.strftime('%d.%m.%Y')} - {now.strftime('%d.%m.%Y')}\n"
        f"💰 Всего расходов: {len(expenses)}\n"
        f"💵 Общая сумма: {total:.2f}₽\n\n"
        f"📋 По категориям:\n{category_text or 'Нет данных'}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="report_type_projects")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "report_type_debts")
async def report_debts(callback):
    """Отчёт по долгам и компенсациям."""
    await callback.message.edit_text("⏳ Формирую отчёт по долгам...")
    
    # Получаем все запросы на компенсацию в статусе "ожидает"
    from utils.sheets_extended import get_compensation_requests
    requests = await get_compensation_requests(status_filter="ожидает")
    
    total_pending = sum(r['amount'] for r in requests)
    
    employees = get_employees_from_sheet()
    
    text_lines = [f"💸 <b>Ожидают компенсации ({len(requests)})</b>\n"]
    
    for r in requests[:10]:  # Первые 10
        emp_data = employees.get(r['employee_id'], {})
        emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
        text_lines.append(f"  • {emp_name}: {r['amount']:.2f}₽ ({r['date_request']})")
    
    if len(requests) > 10:
        text_lines.append(f"  ... и ещё {len(requests) - 10}")
    
    text_lines.append(f"\n💵 Общая сумма к выплате: {total_pending:.2f}₽")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="report_back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "report_type_balances")
async def report_balances(callback):
    """Отчёт по балансам сотрудников."""
    await callback.message.edit_text("⏳ Формирую сводку по балансам...")
    
    balances = await get_all_employee_balances()
    
    # Сортируем: сначала отрицательные, потом по убыванию
    balances.sort(key=lambda x: (x['balance'] >= 0, -x['balance'] if x['balance'] < 0 else x['balance']))
    
    negative = [b for b in balances if b['balance'] < 0]
    positive = [b for b in balances if b['balance'] >= 0]
    
    text_lines = [
        f"💰 <b>Сводка по балансам</b>\n",
        f"⚠️ Отрицательных: {len(negative)}",
        f"✅ Положительных: {len(positive)}\n"
    ]
    
    if negative:
        text_lines.append("<b>Требуют компенсации:</b>")
        for b in negative[:15]:  # Первые 15
            text_lines.append(f"  • {b['name']}: {b['balance']:.2f}₽")
        if len(negative) > 15:
            text_lines.append(f"  ... и ещё {len(negative) - 15}")
    
    total_negative = sum(b['balance'] for b in negative)
    text_lines.append(f"\n📉 Общий долг: {total_negative:.2f}₽")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="report_back")]
    ])
    
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "report_back")
async def report_back(callback):
    """Возврат в меню отчётов."""
    await report_menu(callback.message)


# ============ КОМАНДА /balance ============

@router.message(Command("balance"))
async def balance_summary(message: Message):
    """Сводка по балансам."""
    user_id = message.from_user.id
    employees = get_employees_from_sheet()
    user_data = employees.get(user_id, {})
    user_role = user_data.get("role", ROLE_EMPLOYEE)
    
    if user_role == ROLE_EMPLOYEE:
        # Подотчётник видит только свой баланс
        balance = await get_employee_balance(user_id)
        
        # Получаем статус компенсаций
        expenses = await get_expenses_by_employee_and_period(
            user_id,
            datetime.now() - timedelta(days=30),
            datetime.now()
        )
        pending = sum(e['amount'] for e in expenses if e['compensation_status'] == "ожидает")
        
        text = (
            f"💳 <b>Ваш баланс</b>\n\n"
            f"Текущий баланс: {balance:.2f}₽\n"
        )
        
        if balance < 0:
            text += f"\n⚠️ <b>Ваш баланс отрицательный!</b>\nЗапрос на компенсацию отправлен."
        
        if pending > 0:
            text += f"\n⏳ Ожидает компенсации: {pending:.2f}₽"
        
        await message.answer(text, parse_mode="HTML")
    
    else:
        # Руководство видит все отрицательные балансы
        await balance_summary_management(message)


async def balance_summary_management(message: Message):
    """Сводка по балансам для руководства."""
    negative = await get_negative_balances()
    
    if not negative:
        await message.answer(
            "💰 <b>Сводка по балансам</b>\n\n"
            "✅ Все балансы положительные. Отрицательных балансов нет.",
            parse_mode="HTML"
        )
        return
    
    text_lines = [
        f"💰 <b>Сводка по балансам</b>\n",
        f"⚠️ Сотрудников с отрицательным балансом: {len(negative)}\n"
    ]
    
    total_debt = 0
    for b in negative[:20]:  # Первые 20
        text_lines.append(f"  • {b['name']}: {b['balance']:.2f}₽")
        total_debt += b['balance']
    
    if len(negative) > 20:
        text_lines.append(f"  ... и ещё {len(negative) - 20}")
    
    text_lines.append(f"\n📉 Общий долг: {total_debt:.2f}₽")
    
    await message.answer(
        "\n".join(text_lines),
        parse_mode="HTML"
    )


# ============ УПРАВЛЕНИЕ ПОДПИСКАМИ (ДОБАВЛЕНО) ============

@router.message(Command("subscriptions"))
async def manage_subscriptions(message: Message):
    """Manage report subscriptions."""
    user_id = message.from_user.id
    employees = get_employees_from_sheet()
    user_data = employees.get(user_id, {})
    user_role = user_data.get("role", ROLE_EMPLOYEE)
    
    # Получаем текущие подписки
    from utils.sheets_extended import get_employee_subscriptions
    subscriptions = await get_employee_subscriptions(user_id)
    
    # Определяем доступные подписки в зависимости от роли
    if user_role == ROLE_EMPLOYEE:
        available = ['weekly', 'monthly', 'balance_alert']
        text_lines = ["📬 <b>Управление подписками на отчёты</b>\n"]
    else:
        available = ['daily_admin', 'weekly_admin', 'monthly_admin', 'balance_alert']
        text_lines = ["📬 <b>Управление подписками (админ)</b>\n"]
    
    # Формируем кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    sub_names = {
        'weekly': ('📊 Недельный отчёт', 'еженедельная'),
        'monthly': ('📈 Месячный отчёт', 'ежемесячная'),
        'daily_admin': ('📅 Ежедневная сводка', 'админ_ежедневная'),
        'weekly_admin': ('📊 Недельная сводка', 'админ_еженедельная'),
        'monthly_admin': ('📈 Месячная сводка', 'админ_ежемесячная'),
        'balance_alert': ('⚠️ Уведомления о балансе', 'баланс'),
    }
    
    for sub_type in available:
        name, short_name = sub_names.get(sub_type, (sub_type, sub_type))
        enabled = subscriptions.get(sub_type, False)
        status = "✅" if enabled else "❌"
        
        text_lines.append(f"{status} {name}")
        
        action = "выкл" if enabled else "вкл"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {name}",
                callback_data=f"toggle_sub_{sub_type}_{action}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Готово", callback_data="subscriptions_done")
    ])
    
    await message.answer(
        "\n".join(text_lines),
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("toggle_sub_"))
async def toggle_subscription(callback: CallbackQuery):
    """Toggle subscription on/off."""
    # Парсим данные: toggle_sub_{type}_{action}
    parts = callback.data.split("_")
    if len(parts) >= 4:
        sub_type = parts[2]
        action = parts[3]
        enabled = action == "вкл"
    else:
        await callback.answer("❌ Ошибка данных")
        return
    
    user_id = callback.from_user.id
    
    # Обновляем подписку
    from utils.sheets_extended import update_subscription
    success = await update_subscription(user_id, sub_type, enabled)
    
    if success:
        status_text = "включена" if enabled else "выключена"
        await callback.answer(f"✅ Подписка {status_text}")
        
        # Обновляем сообщение
        await manage_subscriptions(callback.message)
        await callback.message.delete()
    else:
        await callback.answer("❌ Ошибка обновления подписки")


@router.callback_query(F.data == "subscriptions_done")
async def subscriptions_done(callback: CallbackQuery):
    """Закрыть меню подписок."""
    await callback.message.edit_text(
        "✅ Настройки подписок сохранены!\n\n"
        "Отчёты будут отправляться автоматически по расписанию."
    )
