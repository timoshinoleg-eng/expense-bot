"""
Хендлеры для управления проектами.
Доступ: владелец, главбух
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from keyboards.main_menu import get_admin_menu, get_back_keyboard
from utils.decorators import role_required, ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT
from utils.sheets_extended import (
    get_active_projects, get_all_projects, add_project, update_project_status
)
from utils.states import ProjectStates

router = Router()


# ============ СПИСОК ПРОЕКТОВ ============

@router.message(Command("projects"))
@router.message(F.text == "📁 Проекты")
async def show_projects(message: Message, state: FSMContext):
    """Показать список проектов."""
    projects = get_all_projects()
    
    if not projects:
        await message.answer(
            "📁 Проекты не найдены.\n\n"
            "Добавить проект: /add_project",
            reply_markup=get_admin_menu()
        )
        return
    
    text = "📁 Список проектов:\n\n"
    for proj in projects:
        status_emoji = "🟢" if proj["status"] == "активный" else "🔴" if proj["status"] == "завершенный" else "🟡"
        text += f"{status_emoji} {proj['name']}\n"
        text += f"   ID: {proj['id']} | Статус: {proj['status']}\n"
        if proj["budget"]:
            text += f"   Бюджет: {proj['budget']} руб.\n"
        text += "\n"
    
    # Клавиатура с действиями
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить проект", callback_data="add_project")],
        [InlineKeyboardButton(text="✏️ Изменить статус", callback_data="change_project_status")],
    ])
    
    await message.answer(text, reply_markup=keyboard)


# ============ ДОБАВЛЕНИЕ ПРОЕКТА ============

@router.message(Command("add_project"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def add_project_start(message: Message, state: FSMContext, user_role: str = None):
    """Начать добавление проекта."""
    await state.set_state(ProjectStates.waiting_for_name)
    await message.answer(
        "➕ Добавление нового проекта\n\n"
        "Введите название проекта:",
        reply_markup=get_back_keyboard(),
    )


@router.message(ProjectStates.waiting_for_name)
async def add_project_name(message: Message, state: FSMContext):
    """Получить название проекта."""
    if message.text == "⬅ Назад":
        await back_to_projects(message, state)
        return
    
    if not message.text or not message.text.strip():
        await message.answer("Название проекта не может быть пустым")
        return
    
    await state.update_data(project_name=message.text.strip())
    await state.set_state(ProjectStates.waiting_for_budget)
    
    await message.answer(
        "Введите бюджет проекта (в рублях) или отправьте '-' чтобы пропустить:",
        reply_markup=get_back_keyboard(),
    )


@router.message(ProjectStates.waiting_for_budget)
async def add_project_budget(message: Message, state: FSMContext):
    """Получить бюджет проекта."""
    if message.text == "⬅ Назад":
        await back_to_projects(message, state)
        return
    
    budget = ""
    if message.text and message.text.strip() != "-":
        try:
            budget = str(float(message.text.strip()))
        except ValueError:
            await message.answer("Введите число или '-' для пропуска")
            return
    
    await state.update_data(project_budget=budget)
    await state.set_state(ProjectStates.waiting_for_dates)
    
    await message.answer(
        "Введите даты проекта в формате:\n"
        "ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n\n"
        "Или отправьте '-' чтобы пропустить:",
        reply_markup=get_back_keyboard(),
    )


@router.message(ProjectStates.waiting_for_dates)
async def add_project_dates(message: Message, state: FSMContext):
    """Получить даты и сохранить проект."""
    if message.text == "⬅ Назад":
        await back_to_projects(message, state)
        return
    
    start_date = ""
    end_date = ""
    
    if message.text and message.text.strip() != "-":
        dates = message.text.strip().split("-")
        if len(dates) == 2:
            start_date = dates[0].strip()
            end_date = dates[1].strip()
        else:
            await message.answer("Неверный формат. Используйте: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ")
            return
    
    data = await state.get_data()
    project_name = data["project_name"]
    project_budget = data.get("project_budget", "")
    
    # Сохраняем проект
    success = add_project(
        name=project_name,
        status="активный",
        budget=project_budget,
        start_date=start_date,
        end_date=end_date
    )
    
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ Проект '{project_name}' успешно создан!\n\n"
            f"Статус: активный\n"
            f"Бюджет: {project_budget or 'не указан'} руб.\n"
            f"Период: {start_date or 'не указан'} - {end_date or 'не указан'}",
            reply_markup=get_admin_menu(),
        )
    else:
        await message.answer(
            "❌ Ошибка при создании проекта",
            reply_markup=get_admin_menu(),
        )


# ============ ИЗМЕНЕНИЕ СТАТУСА ПРОЕКТА ============

@router.callback_query(F.data == "change_project_status")
async def change_status_callback(callback: CallbackQuery, state: FSMContext):
    """Показать список проектов для изменения статуса."""
    projects = get_all_projects()
    
    if not projects:
        await callback.message.edit_text("Нет доступных проектов")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for proj in projects:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{proj['name']} ({proj['status']})",
                callback_data=f"project_status_{proj['id']}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="back_to_projects")
    ])
    
    await callback.message.edit_text(
        "Выберите проект для изменения статуса:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("project_status_"))
async def select_new_status(callback: CallbackQuery, state: FSMContext):
    """Показать варианты статуса."""
    project_id = callback.data.replace("project_status_", "")
    await state.update_data(project_id=project_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Активный", callback_data="set_status_активный")],
        [InlineKeyboardButton(text="🟡 Приостановленный", callback_data="set_status_приостановленный")],
        [InlineKeyboardButton(text="🔴 Завершенный", callback_data="set_status_завершенный")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="change_project_status")],
    ])
    
    await callback.message.edit_text(
        "Выберите новый статус:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("set_status_"))
async def apply_status(callback: CallbackQuery, state: FSMContext):
    """Применить новый статус."""
    new_status = callback.data.replace("set_status_", "")
    data = await state.get_data()
    project_id = data.get("project_id")
    
    success = update_project_status(project_id, new_status)
    
    if success:
        await callback.message.edit_text(
            f"✅ Статус проекта изменен на: {new_status}"
        )
    else:
        await callback.message.edit_text("❌ Ошибка при изменении статуса")
    
    await state.clear()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def back_to_projects(message: Message, state: FSMContext):
    """Вернуться к списку проектов."""
    await state.clear()
    await show_projects(message, state)


@router.callback_query(F.data == "back_to_projects")
async def back_to_projects_callback(callback: CallbackQuery, state: FSMContext):
    """Вернуться к списку проектов из callback."""
    await state.clear()
    await callback.message.delete()
    await show_projects(callback.message, state)


@router.callback_query(F.data == "add_project")
async def add_project_callback(callback: CallbackQuery, state: FSMContext):
    """Начать добавление проекта из callback."""
    await callback.message.delete()
    await add_project_start(callback.message, state)


# ============ КОМАНДА /toggle_project (ДОБАВЛЕНО) ============

@router.message(Command("toggle_project"))
@role_required([ROLE_OWNER, ROLE_CHIEF_ACCOUNTANT])
async def toggle_project_command(message: Message, state: FSMContext):
    """Command to toggle project status (active/inactive)."""
    projects = get_all_projects()
    
    if not projects:
        await message.answer(
            "📁 Нет доступных проектов.\n"
            "Создайте проект: /add_project"
        )
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for proj in projects:
        status_emoji = "🟢" if proj["status"] == "активный" else "🔴"
        new_status = "завершенный" if proj["status"] == "активный" else "активный"
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {proj['name']} → {new_status}",
                callback_data=f"toggle_proj_{proj['id']}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="back_to_projects")
    ])
    
    await message.answer(
        "🔄 <b>Переключение статуса проекта</b>\n\n"
        "Выберите проект для смены статуса:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("toggle_proj_"))
async def process_toggle_project(callback: CallbackQuery):
    """Process project status toggle."""
    project_id = callback.data.replace("toggle_proj_", "")
    
    # Получаем текущий проект
    projects = get_all_projects()
    project = None
    for p in projects:
        if p['id'] == project_id:
            project = p
            break
    
    if not project:
        await callback.answer("❌ Проект не найден")
        return
    
    # Определяем новый статус
    current_status = project['status']
    new_status = "завершенный" if current_status == "активный" else "активный"
    
    # Обновляем статус
    success = update_project_status(project_id, new_status)
    
    if success:
        status_emoji = "🔴" if new_status == "завершенный" else "🟢"
        await callback.answer(f"✅ Статус изменен на: {new_status}")
        
        # Обновляем список
        await toggle_project_command(callback.message, None)
        await callback.message.delete()
    else:
        await callback.answer("❌ Ошибка при изменении статуса")
