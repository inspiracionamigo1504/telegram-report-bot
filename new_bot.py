import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_SHEETS_CREDS = os.getenv('GOOGLE_SHEETS_CREDS') or 'credentials.json'
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
ADMIN_CHAT_IDS = list(map(int, os.getenv('ADMIN_CHAT_IDS', '').split(',')))

if not all([BOT_TOKEN, GOOGLE_SHEETS_CREDS, SPREADSHEET_ID, ADMIN_CHAT_IDS]):
    logger.error("Не все обязательные переменные окружения заданы!")
    raise ValueError("Проверьте .env файл")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
scheduler = AsyncIOScheduler()

from oauth2client.service_account import ServiceAccountCredentials

def init_google_sheets():
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        creds = ServiceAccountCredentials.from_json_keyfile_name(
            os.getenv("GOOGLE_SHEETS_CREDS"),
            scope
        )

        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID)

    except Exception as e:
        logger.error(f"Google Sheets initialization error: {str(e)}")
        raise




async def get_report_data():
    try:
        sheet = init_google_sheets().sheet1
        data = sheet.get_all_values()

        if not data:
            logger.warning("Google Sheets вернул пустые данные")
            return "Данные не найдены"

        current_date = datetime.now().strftime('%d.%m.%Y')

        headers = data[0]
        date_index = next((i for i, cell in enumerate(headers) if current_date in cell), None)

        if date_index is None:
            return f"Дата {current_date} не найдена в таблице"

        revenue_col = date_index
        plan_col = date_index + 1
        percent_col = date_index + 2

        report_lines = [
            f"📊 Отчет за {current_date}",
            "```",
            f"{'Филиал':<32}│{'Выручка':>10}│{'План':>10}│{'% Вып.':>9}",
            "─" * 66
        ]

        total_name = ""
        total_revenue = "-"
        total_plan = "-"
        total_percent = "-"

        for row in data[1:]:
            if not any(cell.strip() for cell in row):
                break

            name = row[0] if len(row) > 0 else "-"
            revenue = row[revenue_col] if len(row) > revenue_col else "-"
            plan = row[plan_col] if len(row) > plan_col else "-"
            percent = row[percent_col] if len(row) > percent_col else "-"

            if "итог" in name.lower():
                total_name = name
                total_revenue = revenue
                total_plan = plan
                total_percent = percent
                continue

            report_lines.append(f"{name:<32}│{revenue:>10}│{plan:>10}│{percent:>9}")

        report_lines.append("─" * 66)
        report_lines.append(f"{total_name:<32}│{total_revenue:>10}│{total_plan:>10}│{total_percent:>9}")
        report_lines.append("```")

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"Ошибка при формировании отчета: {str(e)}")
        return f"Ошибка: {str(e)}"

async def send_report():
    try:
        report = await get_report_data()
        for chat_id in ADMIN_CHAT_IDS:
            await bot.send_message(chat_id, report, parse_mode='Markdown')
        logger.info(f"Отчет за {datetime.now().strftime('%d.%m.%Y')} успешно отправлен")
    except Exception as e:
        logger.error(f"Ошибка при отправке отчета: {str(e)}")

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Бот для отчетов запущен. Используйте /report для получения сегодняшнего отчета.")



@dp.message_handler(commands=['report'])
async def cmd_report(message: types.Message):
    if message.from_user.id not in ADMIN_CHAT_IDS:
        await message.answer("У вас нет прав для выполнения этой команды")
        return
    await message.answer("Формирую отчет...")
    await send_report()

async def on_startup(dp):
    scheduler.add_job(
        send_report,
        'cron',
        hour=22,
        minute=10,
        misfire_grace_time=120  # До 2 минут задержки допустимы
    )
    scheduler.start()
    logger.info("Бот запущен. Ожидает команды или расписания...")

if __name__ == '__main__':
    import os, asyncio

    # Если запуск из GitHub Actions — просто отправляем отчёт и выходим
    if os.getenv("GITHUB_ACTIONS") == "true":
        asyncio.run(send_report())
    else:
        # Обычный режим — бот работает постоянно
        from aiogram import executor
        executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

