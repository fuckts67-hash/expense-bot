import asyncio
import os
import re

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
import asyncpg

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
db = None

async def init_db():
    global db
    db = await asyncpg.connect(DATABASE_URL)
    await db.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            description TEXT,
            amount FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("💸 Привет! Отправь расход\n\nНапример:\nкофе 4\nтакси 12.5")

@dp.message(Command("stats"))
async def stats(message: Message):
    rows = await db.fetch('SELECT description, amount FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10', message.from_user.id)
    if not rows:
        await message.answer("Расходов пока нет!")
        return
    text = "📊 Последние расходы:\n\n"
    total = 0
    for row in rows:
        text += f"• {row['description']} — {row['amount']}₽\n"
        total += row['amount']
    text += f"\n💰 Итого: {total}₽"
    await message.answer(text)

@dp.message()
async def add_expense(message: Message):
    match = re.match(r'^(.+?)\s+(\d+\.?\d*)$', message.text.strip())
    if not match:
        await message.answer("❌ Формат: название сумма\n\nНапример: кофе 4")
        return
    description = match.group(1)
    amount = float(match.group(2))
    await db.execute('INSERT INTO transactions (user_id, description, amount) VALUES ($1, $2, $3)',
                     message.from_user.id, description, amount)
    await message.answer(f"✅ Записал: {description} — {amount}₽")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())