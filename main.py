@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "👋 <b>Привет! Я — твой личный финансовый помощник.</b>\n\n"
        "Я помогу тебе:\n"
        "💸 Отслеживать расходы\n"
        "💰 Записывать доходы\n"
        "📊 Смотреть статистику\n"
        "🧠 Анализировать траты с помощью AI\n\n"
        "Нажми кнопку ниже чтобы узнать больше 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Что умеет бот?", callback_data="about")],
            [InlineKeyboardButton(text="🚀 Начать", callback_data="go")],
        ])
    )


@dp.callback_query(F.data == "about")
async def about_callback(callback: CallbackQuery):
    await callback.message.answer(
        "🤖 <b>Что умеет этот бот?</b>\n\n"
        "📝 <b>Записывать расходы</b>\n"
        "Просто напиши: <code>шаурма 100</code>\n"
        "Бот сам определит категорию 🧠\n\n"
        "💰 <b>Записывать доходы</b>\n"
        "Напиши: <code>+зарплата 50000</code>\n\n"
        "📊 <b>Статистика</b>\n"
        "За день, неделю или месяц\n"
        "Показывает расходы по категориям\n\n"
        "🏷 <b>Категории</b>\n"
        "🍔 Еда · 🚕 Транспорт · ⛽ Авто\n"
        "💊 Здоровье · 🎬 Подписки · 🎮 Игры\n"
        "👕 Одежда · 💻 Техника · ⚖️ Штрафы\n\n"
        "📋 <b>История</b>\n"
        "Последние 10 записей\n\n"
        "🗑 <b>Удаление</b>\n"
        "Удали последнюю запись если ошибся",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать", callback_data="go")],
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "go")
async def go_callback(callback: CallbackQuery):
    await callback.message.answer(
        "✅ <b>Отлично! Ты готов.</b>\n\n"
        "Напиши свой первый расход:\n"
        "<code>кофе 150</code>\n\n"
        "Или используй кнопки 👇",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    await callback.answer()