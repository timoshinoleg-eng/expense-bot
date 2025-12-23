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
from utils.states import ExpenseStates

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
    await state.set_state(ExpenseStates.waiting_for_object)
    await message.answer("Введите объект/проект:", reply_markup=ReplyKeyboardRemove())


@router.message(ExpenseStates.waiting_for_category)
async def process_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(ExpenseStates.waiting_for_object)
    await message.answer("Введите объект/проект:", reply_markup=ReplyKeyboardRemove())


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
    data = await state.get_data()
    text = (
        "Проверьте данные:\n\n"
        f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
        f"Сумма: {data['amount']} руб\n"
        f"Дата: {data['date']} {data['time']}\n"
        f"Статья: {data['category']}\n"
        f"Объект: {data['object']}\n"
        "Чек: прикреплен\n\n"
        "Всё верно?"
    )
    await state.set_state(ExpenseStates.waiting_for_confirmation)
    await message.answer(text, reply_markup=get_confirmation_keyboard())


@router.message(ExpenseStates.waiting_for_photo, F.text == "Пропустить")
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id="")
    data = await state.get_data()
    text = (
        "Проверьте данные:\n\n"
        f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
        f"Сумма: {data['amount']} руб\n"
        f"Дата: {data['date']} {data['time']}\n"
        f"Статья: {data['category']}\n"
        f"Объект: {data['object']}\n"
        "Чек: не прикреплен\n\n"
        "Всё верно?"
    )
    await state.set_state(ExpenseStates.waiting_for_confirmation)
    await message.answer(text, reply_markup=get_confirmation_keyboard())


@router.message(ExpenseStates.waiting_for_photo)
async def invalid_photo_input(message: Message):
    await message.answer("Отправьте фото или нажмите Пропустить")


@router.message(ExpenseStates.waiting_for_confirmation, F.text == "Сохранить")
async def save_expense(message: Message, state: FSMContext, is_admin: bool):
    data = await state.get_data()
    timestamp = f"{data['date']} {data['time']}"
    file_id = data.get("photo_file_id", "") or "Нет чека"
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
    ok = append_expense_row(row)

    if ok:
        await message.answer(
            f"Данные сохранены!\n\n"
            f"Сотрудник: {data['user_first_name']} {data['user_last_name']}\n"
            f"Сумма: {data['amount']} руб\n"
            f"Статья: {data['category']}"
        )
    else:
        await message.answer("Ошибка при сохранении")

    await state.clear()

    # Возврат в главное меню
keyboard = get_user_menu()    await message.answer("Выберите дальнейшее действие:", reply_markup=keyboard)


@router.message(ExpenseStates.waiting_for_confirmation, F.text == "Отменить")
async def cancel_expense(message: Message, state: FSMContext, is_admin: bool):
    await state.clear()
    await message.answer("Запись отменена", reply_markup=ReplyKeyboardRemove())

    # Возв
keyboard = get_user_menu()    await message.answer("Выберите дальнейшее действие:", reply_markup=keyboard)
