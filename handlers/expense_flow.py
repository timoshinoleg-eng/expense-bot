"""
Хендлеры для добавления расходов с поддержкой проектов и лимитов.
"""
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, PhotoSize, ReplyKeyboardRemove

from keyboards.expense_kb import (
    get_cancel_keyboard,
    get_category_keyboard,
    get_confirmation_keyboard,
    get_photo_keyboard,
)
from keyboards.main_menu import get_user_menu, get_admin_menu
from utils.google_sheets import append_expense_row
from utils.sheets_extended import (
    get_active_projects, 
    check_limit_status, 
    append_expense_row_extended,
    get_employees_from_sheet,
    # ДОБАВЛЕНО: функции баланса
    process_expense_with_balance,
    get_employee_balance,
    # ДОБАВЛЕНО: уведомления о лимитах
    notify_limit_warning,
    notify_limit_exceeded,
)
from handlers.compensations import notify_low_balance  # ДОБАВЛЕНО: уведомление при низком балансе
from utils.states import ExpenseStates
from utils.decorators import ROLE_CHIEF_ACCOUNTANT, ROLE_OWNER

router = Router()


@router.message(Command("add"))
async def start_expense_flow(
    message: Message, state: FSMContext, user_first_name: str, user_last_name: str
):
    await state.update_data(user_first_name=user_first_name, user_last_name=user_last_name)
    await state.set_state(ExpenseStates.waiting_for_amount)
    await message.answer(
        f"Сотрудник: {user_first_name} {user_last_name}\n\n"
        "Введите сумму расходов в рублях:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ExpenseStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Неверный формат! Введите число, например: 1500")
        return

    # 🔥 ПРОВЕРКА ЛИМИТА перед продолжением
    user_id = message.from_user.id
    limit_exceeded, percentage, status = check_limit_status(user_id, amount)
    
    # ДОБАВЛЕНО: Получаем текущие значения лимита для уведомлений
    from utils.sheets_extended import get_employee_limit, get_expenses_for_period
    limit, period = get_employee_limit(user_id)
    current_expenses = get_expenses_for_period(user_id, period)
    total_with_new = current_expenses + amount
    
    if status == "limit_exceeded":
        await message.answer(
            f"⚠️ <b>Превышен лимит!</b>\n\n"
            f"Текущий расход: {percentage:.1f}% от лимита\n"
            f"Для добавления требуется подтверждение главбуха.",
            parse_mode="HTML"
        )
        # Сохраняем флаг для дальнейшей обработки
        await state.update_data(limit_approval_required=True)
        
        # ДОБАВЛЕНО: Отправляем уведомление о превышении лимита
        await notify_limit_exceeded(user_id, total_with_new, limit, amount)
        
    elif status == "warning_80":
        await message.answer(
            f"⚡ <b>Внимание:</b> расход составляет {percentage:.1f}% от лимита.",
            parse_mode="HTML"
        )
        # ДОБАВЛЕНО: Отправляем предупреждение о приближении к лимиту
        await notify_limit_warning(user_id, percentage, total_with_new, limit)
    
    now = datetime.now()
    await state.update_data(
        amount=str(amount),
        date=now.strftime("%d.%m.%Y"),
        time=now.strftime("%H:%M:%S"),
    )
    await state.set_state(ExpenseStates.waiting_for_category)
    await message.answer("Выберите статью расходов:", reply_markup=get_category_keyboard())


@router.message(ExpenseStates.waiting_for_category, F.text == "Ввести вручную")
async def request_manual_category(message: Message, state: FSMContext):
    await state.set_state(ExpenseStates.waiting_for_category_manual)
    await message.answer("Введите название статьи расходов:", reply_markup=get_cancel_keyboard())


@router.message(ExpenseStates.waiting_for_category_manual, F.text == "Отмена")
async def cancel_manual_category(message: Message, state: FSMContext):
    await state.set_state(ExpenseStates.waiting_for_category)
    await message.answer("Выберите статью расходов:", reply_markup=get_category_keyboard())


@router.message(ExpenseStates.waiting_for_category_manual)
async def process_manual_category(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Название не может быть пустым!")
        return

    await state.update_data(category=message.text.strip())
    await state.set_state(ExpenseStates.waiting_for_project)
    await show_project_selection(message, state)


@router.message(ExpenseStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(ExpenseStates.waiting_for_project)
    await show_project_selection(message, state)


async def show_project_selection(message: Message, state: FSMContext):
    """Показать список активных проектов для выбора."""
    projects = get_active_projects()
    
    # ДОБАВЛЕНО: Проверка наличия активных проектов
    if not projects:
        # Если нет активных проектов — информируем и пропускаем выбор
        await state.update_data(project_id="", project_name="")
        await state.set_state(ExpenseStates.waiting_for_object)
        await message.answer(
            "❌ Нет активных проектов. Обратитесь к администратору.\n\n"
            "Введите объект/проект (вручную):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    
    # Формируем клавиатуру с проектами
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    keyboard_buttons = []
    for proj in projects:
        keyboard_buttons.append([KeyboardButton(text=f"📁 {proj['name']}")])
    keyboard_buttons.append([KeyboardButton(text="📝 Ввести вручную")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )
    
    await message.answer(
        "Выберите проект или введите вручную:",
        reply_markup=keyboard,
    )


@router.message(ExpenseStates.waiting_for_project, F.text.startswith("📁 "))
async def process_project_selection(message: Message, state: FSMContext):
    """Обработка выбора проекта."""
    project_name = message.text.replace("📁 ", "").strip()
    projects = get_active_projects()
    
    project_id = ""
    for proj in projects:
        if proj['name'] == project_name:
            project_id = proj['id']
            break
    
    await state.update_data(project_id=project_id, project_name=project_name)
    await state.set_state(ExpenseStates.waiting_for_object)
    await message.answer(
        f"Проект: {project_name}\n\nВведите дополнительное описание (объект/место):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ExpenseStates.waiting_for_project, F.text == "📝 Ввести вручную")
async def process_project_manual(message: Message, state: FSMContext):
    """Ручной ввод проекта/объекта."""
    await state.update_data(project_id="", project_name="")
    await state.set_state(ExpenseStates.waiting_for_object)
    await message.answer(
        "Введите объект/проект:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ExpenseStates.waiting_for_object)
async def process_object_request_photo(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Описание не может быть пустым!")
        return

    await state.update_data(object=message.text.strip())
    await state.set_state(ExpenseStates.waiting_for_photo)
    await message.answer(
        "Прикрепите фото чека или нажмите Пропустить",
        reply_markup=get_photo_keyboard(),
    )


@router.message(ExpenseStates.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo: PhotoSize = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    await show_confirmation(message, state)


@router.message(ExpenseStates.waiting_for_photo, F.text == "Пропустить")
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id="")
    await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext):
    """Показать сводку для подтверждения."""
    data = await state.get_data()
    
    project_text = f"Проект: {data.get('project_name', 'не указан')}\n" if data.get('project_name') else ""
    limit_warning = ""
    if data.get('limit_approval_required'):
        limit_warning = "\n⚠️ <b>Требуется подтверждение главбуха (превышен лимит)</b>\n"
    
    text = (
        "Проверьте данные:\n\n"
        f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
        f"Сумма: {data['amount']} руб\n"
        f"Дата: {data['date']} {data['time']}\n"
        f"Статья: {data['category']}\n"
        f"{project_text}"
        f"Объект: {data['object']}\n"
        f"Чек: {'прикреплен' if data.get('photo_file_id') else 'не прикреплен'}\n"
        f"{limit_warning}\n"
        "Всё верно?"
    )
    await state.set_state(ExpenseStates.waiting_for_confirmation)
    await message.answer(text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")


@router.message(ExpenseStates.waiting_for_photo)
async def invalid_photo_input(message: Message):
    await message.answer("Отправьте фото или нажмите Пропустить")


@router.message(ExpenseStates.waiting_for_confirmation, F.text == "Сохранить")
async def save_expense(message: Message, state: FSMContext, is_admin: bool):
    data = await state.get_data()
    user_id = message.from_user.id
    amount = float(data['amount'])
    
    # 🔥 ПРОВЕРКА ЛИМИТА перед сохранением
    if data.get('limit_approval_required') and not is_admin:
        # Не админ пытается сохранить при превышении лимита
        # Отправляем уведомление главбуху и владельцу
        await notify_approvers(message, data)
        await message.answer(
            "⏳ Расход отправлен на согласование главбуху.\n"
            "После подтверждения он будет добавлен в систему."
        )
        await state.clear()
        keyboard = get_admin_menu() if is_admin else get_user_menu()
        await message.answer("Выберите дальнейшее действие:", reply_markup=keyboard)
        return
    
    timestamp = f"{data['date']} {data['time']}"
    file_id = data.get("photo_file_id", "") or "Нет чека"
    
    # Базовые данные для старого формата (обратная совместимость)
    row = [
        data["user_first_name"],
        data["user_last_name"],
        timestamp,
        data["amount"],
        data["category"],
        data["object"],
        file_id,
    ]

    await message.answer("Сохраняю данные...", reply_markup=ReplyKeyboardRemove())
    
    # 🔥 ДОБАВЛЕНО: Обрабатываем расход с учётом баланса
    result = await process_expense_with_balance(
        user_id=user_id,
        amount=amount,
        expense_data=row,
        project_id=data.get('project_id', '')
    )

    if result['success']:
        # Формируем сообщение о результате
        balance_text = f"\n💳 Текущий баланс: {result['new_balance']:.2f}₽"
        
        await message.answer(
            f"✅ Данные сохранены!\n\n"
            f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
            f"Сумма: {data['amount']} руб\n"
            f"Статья: {data['category']}"
            f"{balance_text}"
        )
        
        # 🔥 ДОБАВЛЕНО: Уведомление при отрицательном балансе
        if result['notification_needed']:
            await notify_low_balance(user_id, result['new_balance'])
            await message.answer(
                f"⚠️ <b>Внимание!</b>\n\n"
                f"Ваш баланс стал отрицательным: {result['new_balance']:.2f}₽\n"
                f"Автоматически создан запрос на компенсацию.",
                parse_mode="HTML"
            )
        
        # 🔥 УВЕДОМЛЕНИЕ КОНТРОЛЁРУ при превышении 80% лимита
        if result.get('limit_status') in ["warning_80", "limit_exceeded"]:
            await notify_controllers(message, data, result.get('limit_percentage', 0))
    else:
        await message.answer("❌ Ошибка при сохранении. Попробуйте позже.")

    await state.clear()

    # Возврат в главное меню
    keyboard = get_admin_menu() if is_admin else get_user_menu()
    await message.answer("Выберите дальнейшее действие:", reply_markup=keyboard)


@router.message(ExpenseStates.waiting_for_confirmation, F.text == "Отменить")
async def cancel_expense(message: Message, state: FSMContext, is_admin: bool):
    await state.clear()
    await message.answer("Запись отменена", reply_markup=ReplyKeyboardRemove())

    # Возврат в главное меню
    keyboard = get_admin_menu() if is_admin else get_user_menu()
    await message.answer("Выберите дальнейшее действие:", reply_markup=keyboard)


# ============ УВЕДОМЛЕНИЯ ============

async def notify_approvers(message: Message, data: dict):
    """Уведомить главбуха и владельца о необходимости согласования."""
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    
    bot = Bot(TELEGRAM_TOKEN)
    employees = get_employees_from_sheet()
    
    text = (
        f"🚨 <b>Требуется согласование расхода</b>\n\n"
        f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
        f"Сумма: {data['amount']} руб\n"
        f"Статья: {data['category']}\n"
        f"Проект: {data.get('project_name', 'не указан')}\n\n"
        f"Причина: превышен лимит"
    )
    
    for emp_id, emp_data in employees.items():
        if emp_data.get('role') in [ROLE_CHIEF_ACCOUNTANT, ROLE_OWNER]:
            try:
                await bot.send_message(
                    chat_id=emp_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление {emp_id}: {e}")
    
    await bot.session.close()


async def notify_controllers(message: Message, data: dict, percentage: float):
    """Уведомить контролёров о превышении 80% лимита."""
    from aiogram import Bot
    from config.settings import TELEGRAM_TOKEN
    
    bot = Bot(TELEGRAM_TOKEN)
    employees = get_employees_from_sheet()
    
    text = (
        f"⚡ <b>Уведомление о лимите</b>\n\n"
        f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
        f"Использовано: {percentage:.1f}% от лимита\n\n"
        f"Последний расход: {data['amount']} руб"
    )
    
    for emp_id, emp_data in employees.items():
        if emp_data.get('role') == "контролер":
            try:
                await bot.send_message(
                    chat_id=emp_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление {emp_id}: {e}")
    
    await bot.session.close()
