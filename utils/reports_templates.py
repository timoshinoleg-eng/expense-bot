"""
Шаблоны для автоматических отчётов.
"""

# ============ ШАБЛОНЫ ДЛЯ ПОДОТЧЁТНИКОВ ============

EMPLOYEE_WEEKLY_TEMPLATE = """
📊 <b>Ваш недельный отчёт</b>

📅 Период: {start_date} - {end_date}

📝 Всего расходов: {total_count}
💰 Общая сумма: {total_amount:.2f}₽
💳 Текущий баланс: {balance:.2f}₽

📋 По категориям:
{categories}
{warning}
"""

EMPLOYEE_MONTHLY_TEMPLATE = """
📊 <b>Ваш месячный отчёт</b>

📅 Период: {month} {year}

📝 Всего расходов: {total_count}
💰 Общая сумма: {total_amount:.2f}₽
💳 Текущий баланс: {balance:.2f}₽
⏳ Ожидает компенсации: {pending:.2f}₽

📋 Топ категорий:
{categories}
{warning}
"""

LOW_BALANCE_TEMPLATE = """
⚠️ <b>Внимание! Баланс обнулён</b>

💳 Текущий баланс: {balance:.2f}₽
📝 Ваши расходы за последние 7 дней: {expenses}

Автоматически создан запрос на компенсацию.
Ожидайте выплаты от главбуха.
"""

# ============ ШАБЛОНЫ ДЛЯ АДМИНИСТРАЦИИ ============

ADMIN_DAILY_TEMPLATE = """
📊 <b>Отчёт за {date}</b>

📝 Всего расходов: {total_count}
💰 Общая сумма: {total_amount:.2f}₽
👥 Сотрудников: {employee_count}

📁 По проектам:
{projects}

⚠️ Требуют внимания: {alerts}
"""

ADMIN_WEEKLY_TEMPLATE = """
📊 <b>Недельная сводка</b>

📅 Период: {start_date} - {end_date}

📝 Всего расходов: {total_count}
💰 Общая сумма: {total_amount:.2f}₽

👥 По сотрудникам:
{employees}

📁 По проектам:
{projects}
"""

ADMIN_MONTHLY_TEMPLATE = """
📊 <b>Месячная сводка</b>

📅 Период: {start_date} - {end_date}

📝 Всего расходов: {total_count}
💰 Общая сумма: {total_amount:.2f}₽

👥 По сотрудникам:
{employees}

📁 По проектам:
{projects}
"""

# ============ ШАБЛОНЫ УВЕДОМЛЕНИЙ ============

LIMIT_WARNING_TEMPLATE = """
⚡ <b>Приближение к лимиту</b>

Вы использовали {percentage:.1f}% от вашего лимита.
Текущие расходы: {current:.2f}₽ из {limit:.2f}₽

Будьте внимательны при добавлении новых расходов.
"""

LIMIT_EXCEEDED_TEMPLATE = """
🚫 <b>Лимит превышен!</b>

Ваши расходы ({current:.2f}₽) превышают установленный лимит ({limit:.2f}₽).
Новый расход ({amount:.2f}₽) требует подтверждения главбуха.

Ожидайте решения.
"""

COMPENSATION_APPROVED_TEMPLATE = """
✅ <b>Компенсация одобрена!</b>

Сумма: {amount:.2f}₽
Тип: {type}

Ваш баланс пополнен.
Текущий баланс: {balance:.2f}₽
"""

COMPENSATION_REJECTED_TEMPLATE = """
❌ <b>Компенсация отклонена</b>

Сумма: {amount:.2f}₽

Причина: {reason}

При возникновении вопросов обратитесь к главбуху.
"""
