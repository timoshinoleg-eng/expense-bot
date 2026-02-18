"""
Scheduler service for automated reports.
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from config.settings import TELEGRAM_TOKEN
from utils.google_sheets import get_employees_from_sheet
from utils.sheets_extended import (
    get_expenses_by_employee_and_period,
    get_employee_balance,
    get_all_expenses,
    get_negative_balances,
    get_expenses_by_project,
    get_employees_with_subscription,
)
from utils.reports_templates import (
    EMPLOYEE_WEEKLY_TEMPLATE,
    EMPLOYEE_MONTHLY_TEMPLATE,
    ADMIN_DAILY_TEMPLATE,
    ADMIN_WEEKLY_TEMPLATE,
    ADMIN_MONTHLY_TEMPLATE,
    LOW_BALANCE_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Константы ролей
ROLE_OWNER = "владелец"
ROLE_CHIEF_ACCOUNTANT = "главбух"
ROLE_CONTROLLER = "контролер"
ROLE_EMPLOYEE = "подотчетник"


class ReportScheduler:
    """Manages scheduled report delivery."""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    
    def start(self):
        """Start the scheduler."""
        logger.info("🚀 Запуск планировщика отчётов...")
        
        # Подотчётники: понедельник 9:00
        self.scheduler.add_job(
            self.send_weekly_employee_report,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_employee",
            replace_existing=True
        )
        
        # Подотчётники: 1-го числа 9:00
        self.scheduler.add_job(
            self.send_monthly_employee_report,
            CronTrigger(day=1, hour=9, minute=0),
            id="monthly_employee",
            replace_existing=True
        )
        
        # Финансист/Директор: ежедневно 8:00
        self.scheduler.add_job(
            self.send_daily_admin_report,
            CronTrigger(hour=8, minute=0),
            id="daily_admin",
            replace_existing=True
        )
        
        # Финансист/Директор: понедельник 8:00
        self.scheduler.add_job(
            self.send_weekly_admin_report,
            CronTrigger(day_of_week="mon", hour=8, minute=0),
            id="weekly_admin",
            replace_existing=True
        )
        
        # Финансист/Директор: 1-го числа 8:00
        self.scheduler.add_job(
            self.send_monthly_admin_report,
            CronTrigger(day=1, hour=8, minute=0),
            id="monthly_admin",
            replace_existing=True
        )
        
        # Проверка нулевого баланса каждые 2 часа
        self.scheduler.add_job(
            self.check_zero_balances,
            CronTrigger(hour="*/2"),
            id="check_balances",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("✅ Планировщик отчётов запущен")
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("🛑 Планировщик остановлен")
    
    # ============ ОТЧЁТЫ ДЛЯ ПОДОТЧЁТНИКОВ ============
    
    async def send_weekly_employee_report(self):
        """Отправить недельный отчёт подотчётникам (Пн 9:00)."""
        logger.info("📊 Отправка недельных отчётов сотрудникам...")
        
        try:
            # Получаем сотрудников с подпиской
            subscribers = await get_employees_with_subscription('weekly')
            
            now = datetime.now()
            start_date = now - timedelta(days=now.weekday() + 7)  # Прошлый понедельник
            end_date = start_date + timedelta(days=6)
            
            for emp_id in subscribers:
                try:
                    await self._send_employee_period_report(
                        emp_id, start_date, end_date, 'weekly'
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки отчёта сотруднику {emp_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в send_weekly_employee_report: {e}")
    
    async def send_monthly_employee_report(self):
        """Отправить месячный отчёт подотчётникам (1-е число 9:00)."""
        logger.info("📊 Отправка месячных отчётов сотрудникам...")
        
        try:
            # Получаем сотрудников с подпиской
            subscribers = await get_employees_with_subscription('monthly')
            
            now = datetime.now()
            # Первое число прошлого месяца
            if now.month == 1:
                start_date = now.replace(year=now.year - 1, month=12, day=1)
            else:
                start_date = now.replace(month=now.month - 1, day=1)
            
            end_date = now.replace(day=1) - timedelta(days=1)
            
            for emp_id in subscribers:
                try:
                    await self._send_employee_period_report(
                        emp_id, start_date, end_date, 'monthly'
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки отчёта сотруднику {emp_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в send_monthly_employee_report: {e}")
    
    async def _send_employee_period_report(self, emp_id: int, start_date: datetime, end_date: datetime, period_type: str):
        """Отправить отчёт сотруднику за период."""
        try:
            # Получаем расходы
            expenses = await get_expenses_by_employee_and_period(emp_id, start_date, end_date)
            
            if not expenses:
                logger.info(f"ℹ️ Нет расходов для сотрудника {emp_id}")
                return
            
            # Считаем статистику
            total_count = len(expenses)
            total_amount = sum(e['amount'] for e in expenses)
            balance = await get_employee_balance(emp_id)
            
            # Группируем по категориям
            categories = {}
            for e in expenses:
                cat = e['category']
                categories[cat] = categories.get(cat, 0) + e['amount']
            
            categories_text = "\n".join([
                f"  • {cat}: {amount:.2f}₽"
                for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            ])
            
            # Предупреждение о балансе
            warning = ""
            if balance < 0:
                warning = f"\n⚠️ Внимание! Отрицательный баланс: {balance:.2f}₽"
            
            # Формируем текст
            if period_type == 'weekly':
                text = EMPLOYEE_WEEKLY_TEMPLATE.format(
                    start_date=start_date.strftime("%d.%m.%Y"),
                    end_date=end_date.strftime("%d.%m.%Y"),
                    total_count=total_count,
                    total_amount=total_amount,
                    balance=balance,
                    categories=categories_text,
                    warning=warning
                )
            else:
                pending = sum(e['amount'] for e in expenses if e.get('compensation_status') == "ожидает")
                text = EMPLOYEE_MONTHLY_TEMPLATE.format(
                    month=end_date.strftime("%B"),
                    year=end_date.year,
                    total_count=total_count,
                    total_amount=total_amount,
                    balance=balance,
                    pending=pending,
                    categories=categories_text,
                    warning=warning
                )
            
            await self.bot.send_message(chat_id=emp_id, text=text, parse_mode="HTML")
            logger.info(f"✅ Отчёт отправлен сотруднику {emp_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка формирования отчёта для {emp_id}: {e}")
    
    async def check_zero_balances(self):
        """Проверить нулевые/отрицательные балансы и отправить уведомления."""
        try:
            # Получаем сотрудников с подпиской на уведомления о балансе
            subscribers = await get_employees_with_subscription('balance_alert')
            
            for emp_id in subscribers:
                try:
                    balance = await get_employee_balance(emp_id)
                    
                    # Если баланс <= 0, отправляем уведомление
                    if balance <= 0:
                        # Получаем расходы за последние 7 дней
                        now = datetime.now()
                        start_date = now - timedelta(days=7)
                        expenses = await get_expenses_by_employee_and_period(emp_id, start_date, now)
                        
                        total_expenses = sum(e['amount'] for e in expenses)
                        
                        text = LOW_BALANCE_TEMPLATE.format(
                            balance=balance,
                            expenses=f"{total_expenses:.2f}₽"
                        )
                        
                        await self.bot.send_message(chat_id=emp_id, text=text, parse_mode="HTML")
                        logger.info(f"⚠️ Уведомление о нулевом балансе отправлено {emp_id}")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки баланса {emp_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка в check_zero_balances: {e}")
    
    # ============ ОТЧЁТЫ ДЛЯ АДМИНИСТРАЦИИ ============
    
    async def send_daily_admin_report(self):
        """Отправить ежедневный отчёт финансистам/директорам (8:00)."""
        logger.info("📊 Отправка ежедневного отчёта администрации...")
        
        try:
            # Получаем сотрудников с подпиской
            subscribers = await get_employees_with_subscription('daily_admin')
            
            # Вчерашние расходы
            yesterday = datetime.now() - timedelta(days=1)
            start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = yesterday.replace(hour=23, minute=59, second=59)
            
            # Получаем все расходы
            all_expenses = await get_all_expenses_extended()
            yesterday_expenses = []
            
            for exp in all_expenses:
                try:
                    exp_date = datetime.strptime(exp['date'].split()[0], "%d.%m.%Y")
                    if start_date.date() <= exp_date.date() <= end_date.date():
                        yesterday_expenses.append(exp)
                except:
                    continue
            
            if not yesterday_expenses:
                logger.info("ℹ️ Нет расходов за вчера")
                return
            
            # Считаем статистику
            total_count = len(yesterday_expenses)
            total_amount = sum(e['amount'] for e in yesterday_expenses)
            
            # Уникальные сотрудники
            employees = set(e['employee_name'] for e in yesterday_expenses)
            
            # По проектам
            projects = {}
            for e in yesterday_expenses:
                proj = e.get('project', 'Без проекта')
                projects[proj] = projects.get(proj, 0) + e['amount']
            
            projects_text = "\n".join([
                f"  • {proj}: {amount:.2f}₽"
                for proj, amount in sorted(projects.items(), key=lambda x: x[1], reverse=True)[:5]
            ])
            
            # Проверяем отрицательные балансы
            negative = await get_negative_balances()
            alerts = f"{len(negative)} сотрудников с отриц. балансом" if negative else "Нет"
            
            text = ADMIN_DAILY_TEMPLATE.format(
                date=yesterday.strftime("%d.%m.%Y"),
                total_count=total_count,
                total_amount=total_amount,
                employee_count=len(employees),
                projects=projects_text,
                alerts=alerts
            )
            
            for admin_id in subscribers:
                try:
                    await self.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки отчёта админу {admin_id}: {e}")
            
            logger.info(f"✅ Ежедневный отчёт отправлен {len(subscribers)} администраторам")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в send_daily_admin_report: {e}")
    
    async def send_weekly_admin_report(self):
        """Отправить недельный отчёт администрации (Пн 8:00)."""
        logger.info("📊 Отправка недельного отчёта администрации...")
        
        try:
            subscribers = await get_employees_with_subscription('weekly_admin')
            
            now = datetime.now()
            start_date = now - timedelta(days=now.weekday() + 7)
            end_date = start_date + timedelta(days=6)
            
            text = await self._generate_admin_period_report(start_date, end_date, 'weekly')
            
            for admin_id in subscribers:
                try:
                    await self.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки отчёта админу {admin_id}: {e}")
            
            logger.info(f"✅ Недельный отчёт отправлен {len(subscribers)} администраторам")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в send_weekly_admin_report: {e}")
    
    async def send_monthly_admin_report(self):
        """Отправить месячный отчёт администрации (1-е число 8:00)."""
        logger.info("📊 Отправка месячного отчёта администрации...")
        
        try:
            subscribers = await get_employees_with_subscription('monthly_admin')
            
            now = datetime.now()
            if now.month == 1:
                start_date = now.replace(year=now.year - 1, month=12, day=1)
            else:
                start_date = now.replace(month=now.month - 1, day=1)
            
            end_date = now.replace(day=1) - timedelta(days=1)
            
            text = await self._generate_admin_period_report(start_date, end_date, 'monthly')
            
            for admin_id in subscribers:
                try:
                    await self.bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки отчёта админу {admin_id}: {e}")
            
            logger.info(f"✅ Месячный отчёт отправлен {len(subscribers)} администраторам")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в send_monthly_admin_report: {e}")
    
    async def _generate_admin_period_report(self, start_date: datetime, end_date: datetime, period_type: str) -> str:
        """Сгенерировать отчёт администрации за период."""
        try:
            # Получаем все расходы за период
            all_expenses = await get_all_expenses_extended()
            period_expenses = []
            
            for exp in all_expenses:
                try:
                    exp_date = datetime.strptime(exp['date'].split()[0], "%d.%m.%Y")
                    if start_date.date() <= exp_date.date() <= end_date.date():
                        period_expenses.append(exp)
                except:
                    continue
            
            if not period_expenses:
                return f"📊 <b>Нет данных за период</b>\n{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
            
            total_count = len(period_expenses)
            total_amount = sum(e['amount'] for e in period_expenses)
            
            # По сотрудникам
            by_employee = {}
            for e in period_expenses:
                emp = e['employee_name']
                by_employee[emp] = by_employee.get(emp, {'count': 0, 'amount': 0})
                by_employee[emp]['count'] += 1
                by_employee[emp]['amount'] += e['amount']
            
            employee_text = "\n".join([
                f"  • {emp}: {data['count']} чеков, {data['amount']:.2f}₽"
                for emp, data in sorted(by_employee.items(), key=lambda x: x[1]['amount'], reverse=True)[:5]
            ])
            
            # По проектам
            by_project = {}
            for e in period_expenses:
                proj = e.get('project', 'Без проекта')
                by_project[proj] = by_project.get(proj, 0) + e['amount']
            
            project_text = "\n".join([
                f"  • {proj}: {amount:.2f}₽"
                for proj, amount in sorted(by_project.items(), key=lambda x: x[1], reverse=True)[:5]
            ])
            
            if period_type == 'weekly':
                template = ADMIN_WEEKLY_TEMPLATE
            else:
                template = ADMIN_MONTHLY_TEMPLATE
            
            return template.format(
                start_date=start_date.strftime("%d.%m.%Y"),
                end_date=end_date.strftime("%d.%m.%Y"),
                total_count=total_count,
                total_amount=total_amount,
                employees=employee_text,
                projects=project_text
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации админ отчёта: {e}")
            return "❌ Ошибка формирования отчёта"


async def get_all_expenses_extended() -> list:
    """
    Получить все расходы с расширенной информацией.
    
    Returns:
        list: [{date, amount, category, employee_name, project, compensation_status}, ...]
    """
    try:
        from utils.google_sheets import get_sheets_client
        from utils.sheets_extended import SHEET_EXPENSES
        from config.settings import SPREADSHEET_ID
        
        client = get_sheets_client()
        doc = client.open_by_key(SPREADSHEET_ID)
        sheet = doc.worksheet(SHEET_EXPENSES)
        
        rows = sheet.get_all_values()[1:]
        expenses = []
        
        for row in rows:
            if len(row) >= 7:
                # Получаем название проекта
                project_name = ""
                if len(row) > 7 and row[7]:
                    from utils.sheets_extended import get_all_projects
                    projects = get_all_projects()
                    for p in projects:
                        if p['id'] == row[7]:
                            project_name = p['name']
                            break
                
                expenses.append({
                    'date': row[2],
                    'amount': float(row[3]) if row[3] else 0.0,
                    'category': row[4],
                    'employee_name': f"{row[0]} {row[1]}",
                    'project': project_name or row[5],
                    'compensation_status': row[8] if len(row) > 8 else ""
                })
        
        return expenses
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения расходов: {e}")
        return []
