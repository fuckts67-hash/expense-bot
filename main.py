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
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📋 История", callback_data="history")],
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
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        await db.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'другое'")
    except:
        pass


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "💸 Привет! Я помогу отслеживать расходы.\n\n"
        "Просто напиши:\n<b>кофе 4</b> или <b>шаурма 100</b>\n\n"
        "Я сам определю категорию 🧠",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    await show_stats(message.from_user.id, message)


@dp.callback_query(F.data == "stats")
async def stats_callback(callback: CallbackQuery):
    await show_stats(callback.from_user.id, callback.message)
    await callback.answer()


@dp.callback_query(F.data == "history")
async def history_callback(callback: CallbackQuery):
    rows = await db.fetch(
        'SELECT description, amount, category, created_at FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10',
        callback.from_user.id
    )
    if not rows:
        await callback.message.answer("Расходов пока нет!")
        await callback.answer()
        return
    text = "📋 <b>Последние 10 расходов:</b>\n\n"
    for row in rows:
        emoji = CATEGORY_EMOJI.get(row['category'], "📦")
        date = row['created_at'].strftime("%d.%m %H:%M")
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


async def show_stats(user_id: int, message: Message):
    rows = await db.fetch(
        'SELECT category, SUM(amount) as total FROM transactions WHERE user_id=$1 GROUP BY category ORDER BY total DESC',
        user_id
    )
    if not rows:
        await message.answer("Расходов пока нет!")
        return
    total_all = sum(row['total'] for row in rows)
    text = "📊 <b>Статистика по категориям:</b>\n\n"
    for row in rows:
        emoji = CATEGORY_EMOJI.get(row['category'], "📦")
        percent = (row['total'] / total_all) * 100
        text += f"{emoji} {row['category'].capitalize()} — {row['total']:.1f}₽ ({percent:.0f}%)\n"
    text += f"\n💰 <b>Всего: {total_all:.1f}₽</b>"
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())


@dp.message()
async def add_expense(message: Message):
    match = re.match(r'^(.+?)\s+(\d+\.?\d*)$', message.text.strip())
    if not match:
        await message.answer(
            "❌ Не понял. Напиши так:\n<b>кофе 4</b> или <b>такси 12.5</b>",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
        return
    description = match.group(1)
    amount = float(match.group(2))

    thinking_msg = await message.answer("🧠 Определяю категорию...")
    category = await get_category_ai(description)
    await thinking_msg.delete()

    emoji = CATEGORY_EMOJI.get(category, "📦")
    await db.execute(
        'INSERT INTO transactions (user_id, description, amount, category) VALUES ($1, $2, $3, $4)',
        message.from_user.id, description, amount, category
    )
    await message.answer(
        f"✅ Записал: {description} — {amount}₽\n{emoji} Категория: {category}",
        reply_markup=main_keyboard()
    )


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())