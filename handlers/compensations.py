"""
Хендлеры для системы компенсаций.
"""
import logging  # ДОБАВЛЕНО

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from keyboards.main_menu import get_admin_menu, get_user_menu, get_back_keyboard
from utils.decorators import role_required, ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT, ROLE_EMPLOYEE
from utils.sheets_extended import (
    get_expenses_by_status,
    update_compensation_status,
    get_employee_expenses,
    # ДОБАВЛЕНО: функции баланса
    get_employee_balance,
    check_negative_balance,
    create_compensation_request,
)
from utils.states import CompensationStates
from utils.google_sheets import get_employees_from_sheet

router = Router()
logger = logging.getLogger(__name__)  # ДОБАВЛЕНО


# ============ СПИСОК КОМПЕНСАЦИЙ ============

@router.message(Command("compensations"))
async def list_compensations(message: Message, state: FSMContext):
    """Показать список компенсаций с фильтрами."""
    user_id = message.from_user.id
    employees = get_employees_from_sheet()
    user_data = employees.get(user_id, {})
    user_role = user_data.get("role", ROLE_EMPLOYEE)
    
    # Фильтр по роли
    if user_role == ROLE_EMPLOYEE:
        # Подотчётник видит только свои
        expenses = get_employee_expenses(user_id, status_filter="all")
    else:
        # Главбух и владелец видят все
        expenses = get_expenses_by_status("all")
    
    if not expenses:
        await message.answer(
            "📋 Компенсации не найдены.",
            reply_markup=get_user_menu() if user_role == ROLE_EMPLOYEE else get_admin_menu()
        )
        return
    
    # Группируем по статусу
    pending = [e for e in expenses if e.get("compensation_status") == "ожидает"]
    approved = [e for e in expenses if e.get("compensation_status") == "одобрено"]
    rejected = [e for e in expenses if e.get("compensation_status") == "отклонено"]
    
    text = "📋 Компенсации:\n\n"
    text += f"⏳ Ожидают: {len(pending)}\n"
    text += f"✅ Одобрены: {len(approved)}\n"
    text += f"❌ Отклонены: {len(rejected)}\n\n"
    
    if pending and user_role in [ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT]:
        text += "🚨 Требуют вашего внимания: ожидающие компенсации\n"
    
    # Клавиатура с фильтрами
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Ожидают", callback_data="filter_pending")],
        [InlineKeyboardButton(text="✅ Одобрены", callback_data="filter_approved")],
        [InlineKeyboardButton(text="❌ Отклонены", callback_data="filter_rejected")],
    ])
    
    await message.answer(text, reply_markup=keyboard)


# ============ ТИПЫ КОМПЕНСАЦИИ (ДОБАВЛЕНО) ============

class CompensationType:
    """Типы компенсации."""
    EXPENSE_BASED = "по_факту"  # По факту расходов
    ADVANCE = "аванс"  # Аванс


# ============ ЗАПРОС КОМПЕНСАЦИИ ============

@router.message(Command("request_compensation"))
@role_required([ROLE_EMPLOYEE])
async def request_compensation_start(message: Message, state: FSMContext, user_role: str = None):
    """Начать запрос компенсации."""
    # ДОБАВЛЕНО: Выбор типа компенсации
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 По факту расходов", callback_data="comp_type_expense")],
        [InlineKeyboardButton(text="💰 Аванс", callback_data="comp_type_advance")],
    ])
    
    await state.set_state(CompensationStates.selecting_expense)
    await message.answer(
        "Выберите тип компенсации:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("comp_type_"))
async def process_compensation_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа компенсации."""
    comp_type = callback.data.replace("comp_type_", "")
    await state.update_data(compensation_type=comp_type)
    
    user_id = callback.from_user.id
    
    if comp_type == "advance":
        # Аванс - запрашиваем сумму сразу
        await state.set_state(CompensationStates.entering_amount)
        await callback.message.edit_text(
            "💰 <b>Запрос аванса</b>\n\n"
            "Введите сумму аванса (в рублях):",
            parse_mode="HTML"
        )
    else:
        # По факту расходов - показываем список расходов
        employees = get_employees_from_sheet()
        user_data = employees.get(user_id, {})
        
        # Получаем расходы пользователя без компенсации
        expenses = get_employee_expenses(user_id, status_filter="no_compensation")
        
        if not expenses:
            await callback.message.edit_text(
                "📋 Нет расходов, требующих компенсации.\n"
                "Все ваши расходы уже компенсированы или ожидают решения."
            )
            await state.clear()
            return
        
        # Формируем список для выбора
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for exp in expenses[:10]:  # Первые 10
            btn_text = f"{exp['date']} | {exp['amount']} руб | {exp['category']}"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=btn_text, callback_data=f"comp_req_{exp['row_idx']}")
            ])
        
        await callback.message.edit_text(
            "Выберите расход для компенсации:",
            reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("comp_req_"))
async def process_expense_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора расхода."""
    row_idx = callback.data.replace("comp_req_", "")
    await state.update_data(expense_row=row_idx)
    await state.set_state(CompensationStates.entering_amount)
    
    await callback.message.edit_text(
        "Введите запрашиваемую сумму компенсации (в рублях):"
    )


@router.message(CompensationStates.entering_amount)
async def process_compensation_amount(message: Message, state: FSMContext):
    """Получить сумму компенсации."""
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите положительное число")
        return
    
    await state.update_data(compensation_amount=amount)
    await state.set_state(CompensationStates.entering_method)
    
    # Клавиатура со способами оплаты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта", callback_data="method_card")],
        [InlineKeyboardButton(text="💵 Наличные", callback_data="method_cash")],
        [InlineKeyboardButton(text="🏦 Перевод", callback_data="method_transfer")],
    ])
    
    await message.answer(
        "Выберите предпочтительный способ получения:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("method_"))
async def process_payment_method(callback: CallbackQuery, state: FSMContext):
    """Сохранить запрос компенсации."""
    method = callback.data.replace("method_", "")
    method_names = {
        "card": "💳 Карта",
        "cash": "💵 Наличные",
        "transfer": "🏦 Перевод"
    }
    
    data = await state.get_data()
    row_idx = data.get("expense_row")
    amount = data.get("compensation_amount")
    comp_type = data.get("compensation_type", "expense")  # ДОБАВЛЕНО: тип компенсации
    
    user_id = callback.from_user.id
    
    # ДОБАВЛЕНО: Создаём запрос в листе Компенсации
    from utils.sheets_extended import create_compensation_request
    
    comp_type_ru = "по_факту" if comp_type == "expense" else "аванс"
    comment = f"Способ: {method_names.get(method, method)}"
    if row_idx:
        comment += f", Расход ID: {row_idx}"
    
    success = await create_compensation_request(
        employee_id=user_id,
        amount=amount,
        request_type=comp_type_ru,
        comment=comment
    )
    
    # Обновляем статус в таблице расходов если есть row_idx
    if row_idx:
        update_compensation_status(
            row_idx=int(row_idx),
            status="ожидает",
            amount=amount,
            method=method_names.get(method, method)
        )
    
    await state.clear()
    
    if success:
        type_text = "по факту расходов" if comp_type == "expense" else "аванс"
        await callback.message.edit_text(
            f"✅ Запрос на компенсацию создан!\n\n"
            f"Тип: {type_text}\n"
            f"Сумма: {amount} руб\n"
            f"Способ: {method_names.get(method, method)}\n\n"
            f"Ожидайте решения главбуха."
        )
        
        # Уведомляем главбуха и владельца
        await notify_approvers_about_compensation(callback.from_user, amount, comp_type)
    else:
        await callback.message.edit_text("❌ Ошибка при создании запроса")


# ============ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ============

@router.callback_query(F.data.startswith("comp_approve_"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def approve_compensation(callback: CallbackQuery, user_role: str = None):
    """Одобрить компенсацию."""
    row_idx = callback.data.replace("comp_approve_", "")
    
    success = update_compensation_status(
        row_idx=int(row_idx),
        status="одобрено"
    )
    
    if success:
        await callback.message.edit_text("✅ Компенсация одобрена")
        # Уведомляем сотрудника
        await notify_employee_about_decision(row_idx, "одобрено")
    else:
        await callback.message.edit_text("❌ Ошибка")


@router.callback_query(F.data.startswith("comp_reject_"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def reject_compensation_start(callback: CallbackQuery, state: FSMContext):
    """Начать отклонение компенсации."""
    row_idx = callback.data.replace("comp_reject_", "")
    await state.update_data(reject_row=row_idx)
    await state.set_state(CompensationStates.entering_reject_reason)
    
    await callback.message.edit_text("Введите причину отклонения:")


@router.message(CompensationStates.entering_reject_reason)
async def reject_compensation_finish(message: Message, state: FSMContext):
    """Завершить отклонение."""
    reason = message.text.strip()
    data = await state.get_data()
    row_idx = data.get("reject_row")
    
    success = update_compensation_status(
        row_idx=int(row_idx),
        status="отклонено",
        comment=reason
    )
    
    await state.clear()
    
    if success:
        await message.answer(f"❌ Компенсация отклонена\nПричина: {reason}")
        # Уведомляем сотрудника
        await notify_employee_about_decision(row_idx, "отклонено", reason)
    else:
        await message.answer("❌ Ошибка")


# ============ УВЕДОМЛЕНИЯ ============

async def notify_approvers_about_compensation(employee, amount: float, comp_type: str = "expense"):
    """Уведомить главбуха и владельца о новом запросе."""
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    
    bot = Bot(TELEGRAM_TOKEN)
    employees = get_employees_from_sheet()
    
    type_text = "по факту расходов" if comp_type == "expense" else "аванс"
    
    text = (
        f"🚨 <b>Новый запрос на компенсацию</b>\n\n"
        f"Сотрудник: {employee.first_name} {employee.last_name}\n"
        f"Тип: {type_text}\n"
        f"Сумма: {amount} руб\n\n"
        f"Для одобрения: /approve_compensation"
    )
    
    for emp_id, emp_data in employees.items():
        if emp_data.get("role") in [ROLE_CHIEF_ACCOUNTANT, ROLE_OWNER]:
            try:
                await bot.send_message(chat_id=emp_id, text=text, parse_mode="HTML")
            except Exception:
                pass
    
    await bot.session.close()


async def notify_employee_about_decision(row_idx: str, decision: str, comment: str = ""):
    """Уведомить сотрудника о решении."""
    # TODO: Реализовать получение employee_id по row_idx
    pass


# ============ УВЕДОМЛЕНИЯ ПРИ ОТРИЦАТЕЛЬНОМ БАЛАНСЕ (ДОБАВЛЕНО) ============

async def notify_low_balance(employee_id: int, balance: float, bot=None):
    """
    Отправить уведомление сотруднику и главбуху при балансе ≤ 0.
    
    Args:
        employee_id: ID сотрудника
        balance: Текущий баланс
        bot: Экземпляр бота (если None, создаётся новый)
    """
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    from utils.google_sheets import get_employees_from_sheet
    
    if bot is None:
        bot = Bot(TELEGRAM_TOKEN)
        close_bot = True
    else:
        close_bot = False
    
    employees = get_employees_from_sheet()
    emp_data = employees.get(employee_id, {})
    emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
    
    # Уведомление сотруднику
    try:
        text = (
            f"⚠️ <b>Внимание! Отрицательный баланс</b>\n\n"
            f"Ваш текущий баланс: {balance:.2f}₽\n"
            f"Автоматически создан запрос на компенсацию.\n\n"
            f"Ожидайте выплаты от главбуха."
        )
        await bot.send_message(chat_id=employee_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Не удалось отправить уведомление сотруднику {employee_id}: {e}")
    
    # Уведомление главбуху и владельцу
    text_admin = (
        f"🚨 <b>Требуется компенсация!</b>\n\n"
        f"Сотрудник: {emp_name} (ID: {employee_id})\n"
        f"Баланс: {balance:.2f}₽\n"
        f"Статус: Автоматический запрос на компенсацию создан\n\n"
        f"Проверьте: /compensations"
    )
    
    for emp_id, emp in employees.items():
        if emp.get("role") in [ROLE_CHIEF_ACCOUNTANT, ROLE_OWNER]:
            try:
                await bot.send_message(chat_id=emp_id, text=text_admin, parse_mode="HTML")
            except Exception as e:
                logger.error(f"❌ Не удалось отправить уведомление админу {emp_id}: {e}")
    
    if close_bot:
        await bot.session.close()


async def notify_employee_about_decision(row_idx: str, decision: str, comment: str = ""):
    """
    Уведомить сотрудника о решении по компенсации.
    
    Args:
        row_idx: Номер строки расхода
        decision: "одобрено" или "отклонено"
        comment: Комментарий (при отклонении)
    """
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    from utils.google_sheets import get_employees_from_sheet
    from utils.sheets_extended import get_expenses_by_status
    
    try:
        # Получаем расход по row_idx
        expenses = get_expenses_by_status("all")
        expense = None
        for e in expenses:
            if str(e['row_idx']) == str(row_idx):
                expense = e
                break
        
        if not expense:
            logger.warning(f"⚠️ Расход с row_idx={row_idx} не найден")
            return
        
        # Находим employee_id по имени
        employees = get_employees_from_sheet()
        employee_id = None
        for emp_id, emp_data in employees.items():
            full_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
            if full_name == expense['name']:
                employee_id = emp_id
                break
        
        if not employee_id:
            logger.warning(f"⚠️ Сотрудник {expense['name']} не найден")
            return
        
        bot = Bot(TELEGRAM_TOKEN)
        
        if decision == "одобрено":
            text = (
                f"✅ <b>Компенсация одобрена!</b>\n\n"
                f"Сумма: {expense['amount']} руб\n"
                f"Статья: {expense['category']}\n\n"
                f"Ожидайте выплаты в ближайшее время."
            )
        else:
            text = (
                f"❌ <b>Компенсация отклонена</b>\n\n"
                f"Сумма: {expense['amount']} руб\n"
                f"Статья: {expense['category']}\n"
            )
            if comment:
                text += f"\nПричина: {comment}"
        
        await bot.send_message(chat_id=employee_id, text=text, parse_mode="HTML")
        await bot.session.close()
        
    except Exception as e:
        logger.error(f"❌ Ошибка уведомления сотрудника: {e}")


# ============ КОМАНДА /approve_compensation (ДОБАВЛЕНО) ============

@router.message(Command("approve_compensation"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def approve_compensation_command(message: Message, state: FSMContext, user_role: str = None):
    """Команда для одобрения компенсации. Показывает список ожидающих запросов."""
    from utils.sheets_extended import get_compensation_requests
    
    # Получаем ожидающие запросы
    requests = await get_compensation_requests(status_filter="ожидает")
    
    if not requests:
        await message.answer(
            "✅ Нет ожидающих запросов на компенсацию.",
            reply_markup=get_admin_menu()
        )
        return
    
    employees = get_employees_from_sheet()
    
    # Формируем список
    text_lines = [f"📋 <b>Ожидают компенсации ({len(requests)})</b>\n"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for req in requests[:10]:  # Первые 10
        emp_data = employees.get(req['employee_id'], {})
        emp_name = f"{emp_data.get('first_name', '')} {emp_data.get('last_name', '')}".strip()
        
        text_lines.append(
            f"• {emp_name}: {req['amount']:.2f}₽ ({req['type']})\n"
            f"  Дата: {req['date_request']}"
        )
        
        # Кнопки для одобрения/отклонения
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"✅ Одобрить {req['amount']:.0f}₽",
                callback_data=f"comp_approve_req_{req['id']}"
            ),
            InlineKeyboardButton(
                text=f"❌ Отклонить",
                callback_data=f"comp_reject_req_{req['id']}"
            )
        ])
    
    if len(requests) > 10:
        text_lines.append(f"\n... и ещё {len(requests) - 10} запросов")
    
    await message.answer(
        "\n".join(text_lines),
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("comp_approve_req_"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def approve_compensation_request(callback: CallbackQuery, user_role: str = None):
    """Одобрить запрос на компенсацию из списка."""
    from utils.sheets_extended import (
        get_compensation_requests,
        update_compensation_status_sheet,
        update_employee_balance
    )
    
    req_id = callback.data.replace("comp_approve_req_", "")
    
    # Получаем данные запроса
    requests = await get_compensation_requests(status_filter="ожидает")
    request = None
    for r in requests:
        if r['id'] == req_id:
            request = r
            break
    
    if not request:
        await callback.message.edit_text("❌ Запрос не найден или уже обработан.")
        return
    
    # Обновляем статус
    success = await update_compensation_status_sheet(
        req_id=req_id,
        status="выплачено",
        paid_date=datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    )
    
    if success:
        # Увеличиваем баланс сотрудника
        await update_employee_balance(request['employee_id'], request['amount'], "compensation")
        
        # Получаем новый баланс
        from utils.sheets_extended import get_employee_balance
        new_balance = await get_employee_balance(request['employee_id'])
        
        # Уведомляем сотрудника
        await notify_compensation_paid(
            request['employee_id'],
            request['amount'],
            new_balance
        )
        
        await callback.message.edit_text(
            f"✅ Компенсация одобрена и выплачена!\n\n"
            f"Сумма: {request['amount']:.2f}₽\n"
            f"Сотрудник ID: {request['employee_id']}"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при обработке запроса.")


@router.callback_query(F.data.startswith("comp_reject_req_"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def reject_compensation_request(callback: CallbackQuery, state: FSMContext):
    """Начать отклонение запроса на компенсацию."""
    req_id = callback.data.replace("comp_reject_req_", "")
    await state.update_data(reject_req_id=req_id)
    await state.set_state(CompensationStates.entering_reject_reason)
    
    await callback.message.edit_text("Введите причину отклонения:")


@router.message(CompensationStates.entering_reject_reason)
async def finish_reject_compensation(message: Message, state: FSMContext):
    """Завершить отклонение компенсации."""
    from utils.sheets_extended import update_compensation_status_sheet
    
    reason = message.text.strip()
    data = await state.get_data()
    req_id = data.get("reject_req_id")
    
    if not req_id:
        await message.answer("❌ Ошибка: запрос не найден.")
        await state.clear()
        return
    
    success = await update_compensation_status_sheet(
        req_id=req_id,
        status="отклонено",
        comment=reason
    )
    
    await state.clear()
    
    if success:
        await message.answer(f"❌ Компенсация отклонена.\nПричина: {reason}")
    else:
        await message.answer("❌ Ошибка при отклонении.")


# ============ УВЕДОМЛЕНИЕ О ВЫПЛАТЕ (ДОБАВЛЕНО) ============

async def notify_compensation_paid(employee_id: int, amount: float, new_balance: float):
    """
    Уведомить сотрудника о выплате компенсации.
    Формат: '✅ Выплачено {сумма}₽. Текущий баланс: {баланс}₽'
    
    Args:
        employee_id: ID сотрудника
        amount: Сумма выплаты
        new_balance: Новый баланс после выплаты
    """
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    
    try:
        bot = Bot(TELEGRAM_TOKEN)
        
        text = (
            f"✅ <b>Выплачено {amount:.2f}₽</b>\n\n"
            f"💳 Текущий баланс: {new_balance:.2f}₽\n\n"
            f"Спасибо за работу!"
        )
        
        await bot.send_message(chat_id=employee_id, text=text, parse_mode="HTML")
        await bot.session.close()
        
        logger.info(f"✅ Уведомление о выплате отправлено сотруднику {employee_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления о выплате: {e}")


# ============ ОБНОВЛЕНИЕ СТАТУСА В ЛИСТЕ КОМПЕНСАЦИЙ ============

async def update_compensation_status_sheet(
    req_id: str,
    status: str,
    paid_date: str = "",
    comment: str = ""
) -> bool:
    """
    Обновить статус компенсации в листе 'Компенсации'.
    
    Args:
        req_id: ID запроса
        status: Новый статус
        paid_date: Дата выплаты
        comment: Комментарий
    
    Returns:
        bool: Успешно ли обновление
    """
    try:
        from utils.google_sheets import get_sheets_client
        from utils.sheets_extended import SHEET_COMPENSATIONS
        from config.settings import SPREADSHEET_ID
        
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_COMPENSATIONS)
        
        # Ищем запрос по ID
        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            if row[0] == req_id:
                # Обновляем статус (колонка E - 5)
                sheet.update_cell(idx, 5, status)
                
                # Обновляем дату выплаты (колонка G - 7)
                if paid_date:
                    sheet.update_cell(idx, 7, paid_date)
                
                # Обновляем комментарий (колонка H - 8)
                if comment:
                    current_comment = sheet.cell(idx, 8).value or ""
                    new_comment = f"{current_comment}; {comment}".strip("; ")
                    sheet.update_cell(idx, 8, new_comment)
                
                logger.info(f"✅ Статус компенсации {req_id} обновлен на '{status}'")
                return True
        
        logger.warning(f"⚠️ Запрос на компенсацию {req_id} не найден")
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления статуса компенсации: {e}")
        return False
