import asyncio
import os
import re
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
import asyncpg
from categories import CATEGORY_EMOJI, get_category_local

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
db = None


async def get_category_ai(description: str) -> str:
    local = get_category_local(description)
    if local:
        return local

    if GEMINI_API_KEY:
        prompt = f"""Ты определяешь категорию трат для финансового бота в России.
Расход: "{description}"
Категории: еда, транспорт, авто, жкх, здоровье, одежда, техника, игры, подписки, образование, штрафы, банк, подарки, другое
Ответь ТОЛЬКО одним словом — название категории."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    result = data["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
                    for category in CATEGORY_EMOJI.keys():
                        if category in result:
                            return category
        except:
            pass

    return "другое"


def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Доход", callback_data="add_income"),
            InlineKeyboardButton(text="➖ Расход", callback_data="add_expense"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
            InlineKeyboardButton(text="📋 История", callback_data="history"),
        ],
        [
            InlineKeyboardButton(text="📅 За день", callback_data="stats_day"),
            InlineKeyboardButton(text="📅 За неделю", callback_data="stats_week"),
            InlineKeyboardButton(text="📅 За месяц", callback_data="stats_month"),
        ],
        [InlineKeyboardButton(text="🗑 Удалить последнее", callback_data="delete_last")],
    ])


async def init_db():
    global db
    db = await asyncpg.connect(DATABASE_URL)
    await db.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            description TEXT,
            amount FLOAT,
            category TEXT DEFAULT 'другое',
            type TEXT DEFAULT 'expense',
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        await db.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'другое'")
        await db.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'expense'")
    except:
        pass


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "💸 <b>Привет! Я твой финансовый помощник.</b>\n\n"
        "Чтобы добавить расход напиши:\n<b>шаурма 100</b>\n\n"
        "Чтобы добавить доход напиши:\n<b>+зарплата 50000</b>\n\n"
        "Или используй кнопки ниже 👇",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "add_income")
async def add_income_prompt(callback: CallbackQuery):
    await callback.message.answer(
        "💰 Напиши доход в формате:\n<b>+зарплата 50000</b>\n\nИли просто:\n<b>+50000</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "add_expense")
async def add_expense_prompt(callback: CallbackQuery):
    await callback.message.answer(
        "💸 Напиши расход в формате:\n<b>шаурма 100</b> или <b>такси 250</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "stats")
async def stats_callback(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message, period="all")
    await callback.answer()


@dp.callback_query(F.data == "stats_day")
async def stats_day_callback(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message, period="day")
    await callback.answer()


@dp.callback_query(F.data == "stats_week")
async def stats_week_callback(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message, period="week")
    await callback.answer()


@dp.callback_query(F.data == "stats_month")
async def stats_month_callback(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message, period="month")
    await callback.answer()


@dp.callback_query(F.data == "history")
async def history_callback(callback: CallbackQuery):
    rows = await db.fetch(
        'SELECT description, amount, category, type, created_at FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10',
        callback.from_user.id
    )
    if not rows:
        await callback.message.answer("Записей пока нет!")
        await callback.answer()
        return
    text = "📋 <b>Последние 10 записей:</b>\n\n"
    for row in rows:
        emoji = CATEGORY_EMOJI.get(row['category'], "📦")
        date = row['created_at'].strftime("%d.%m %H:%M")
        if row['type'] == 'income':
            text += f"💰 +{row['amount']}₽ {row['description']} <i>({date})</i>\n"
        else:
            text += f"{emoji} {row['description']} — {row['amount']}₽ <i>({date})</i>\n"
    await callback.message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "delete_last")
async def delete_last_callback(callback: CallbackQuery):
    row = await db.fetchrow(
        'SELECT id, description, amount FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1',
        callback.from_user.id
    )
    if not row:
        await callback.message.answer("Нечего удалять!")
        await callback.answer()
        return
    await db.execute('DELETE FROM transactions WHERE id=$1', row['id'])
    await callback.message.answer(
        f"🗑 Удалено: {row['description']} — {row['amount']}₽",
        reply_markup=main_keyboard()
    )
    await callback.answer()


async def show_stats(user_id: int, message: Message, period: str = "all"):
    if period == "day":
        time_filter = "AND created_at >= NOW() - INTERVAL '1 day'"
        period_name = "за сегодня"
    elif period == "week":
        time_filter = "AND created_at >= NOW() - INTERVAL '7 days'"
        period_name = "за неделю"
    elif period == "month":
        time_filter = "AND created_at >= NOW() - INTERVAL '30 days'"
        period_name = "за месяц"
    else:
        time_filter = ""
        period_name = "за всё время"

    expenses = await db.fetch(
        f'SELECT category, SUM(amount) as total FROM transactions WHERE user_id=$1 AND type=$2 {time_filter} GROUP BY category ORDER BY total DESC',
        user_id, 'expense'
    )
    income = await db.fetchval(
        f'SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id=$1 AND type=$2 {time_filter}',
        user_id, 'income'
    )

    if not expenses and not income:
        await message.answer(f"Записей {period_name} нет!")
        return

    total_expenses = sum(row['total'] for row in expenses)
    balance = income - total_expenses

    text = f"📊 <b>Статистика {period_name}:</b>\n\n"

    if income > 0:
        text += f"💰 <b>Доходы: {income:.0f}₽</b>\n\n"

    if expenses:
        text += "💸 <b>Расходы по категориям:</b>\n"
        for row in expenses:
            emoji = CATEGORY_EMOJI.get(row['category'], "📦")
            percent = (row['total'] / total_expenses * 100) if total_expenses > 0 else 0
            text += f"{emoji} {row['category'].capitalize()} — {row['total']:.0f}₽ ({percent:.0f}%)\n"
        text += f"\n💸 <b>Итого расходов: {total_expenses:.0f}₽</b>\n"

    if income > 0:
        if balance >= 0:
            text += f"\n✅ <b>Остаток: {balance:.0f}₽</b>"
        else:
            text += f"\n⚠️ <b>Перерасход: {abs(balance):.0f}₽</b>"

    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())


@dp.message()
async def handle_message(message: Message):
    text = message.text.strip()

    # Доход: +зарплата 50000 или +50000
    income_match = re.match(r'^\+(.+?)\s+(\d+\.?\d*)$', text) or re.match(r'^\+(\d+\.?\d*)$', text)
    if income_match:
        if len(income_match.groups()) == 2:
            description = income_match.group(1)
            amount = float(income_match.group(2))
        else:
            description = "доход"
            amount = float(income_match.group(1))

        await db.execute(
            'INSERT INTO transactions (user_id, description, amount, category, type) VALUES ($1, $2, $3, $4, $5)',
            message.from_user.id, description, amount, "доход", "income"
        )
        await message.answer(
            f"💰 Записал доход: {description} — {amount:.0f}₽",
            reply_markup=main_keyboard()
        )
        return

    # Расход: шаурма 100
    expense_match = re.match(r'^(.+?)\s+(\d+\.?\d*)$', text)
    if expense_match:
        description = expense_match.group(1)
        amount = float(expense_match.group(2))

        thinking_msg = await message.answer("🧠 Определяю категорию...")
        category = await get_category_ai(description)
        await thinking_msg.delete()

        emoji = CATEGORY_EMOJI.get(category, "📦")
        await db.execute(
            'INSERT INTO transactions (user_id, description, amount, category, type) VALUES ($1, $2, $3, $4, $5)',
            message.from_user.id, description, amount, category, "expense"
        )
        await message.answer(
            f"✅ Записал: {description} — {amount:.0f}₽\n{emoji} Категория: {category}",
            reply_markup=main_keyboard()
        )
        return

    await message.answer(
        "❌ Не понял. Напиши:\n<b>шаурма 100</b> — расход\n<b>+зарплата 50000</b> — доход",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())