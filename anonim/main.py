import asyncio
import aiohttp
import logging
import csv
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InputFile
from aiogram.types import FSInputFile

BOT_TOKEN = "7304557291:AAFaKrQLPfbOhfewiwKSKVDtk84Klj1smp8"
ADMIN_ID = 639331153
CSV_FILE = "data.csv"

# --- Стан анкети ---
class Form(StatesGroup):
    gender = State()
    age = State()

# --- Дані чату ---
waiting_users: list[int] = []
active_chats: dict[int, int] = {}
last_messages: dict[int, int] = {}  # user_id -> message_id

# --- CSV ---
def is_user_registered(user_id: int) -> bool:
    if not os.path.isfile(CSV_FILE):
        return False
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "user_id" not in reader.fieldnames:
            return False
        for row in reader:
            if str(user_id) == row["user_id"]:
                return True
    return False

def save_user_data(user_id: int, username: str, gender: str, age: int):
    file_exists = os.path.isfile(CSV_FILE)
    if not file_exists:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["user_id", "username", "gender", "age"])

    existing_ids = set()
    if file_exists:
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(int(row["user_id"]))

    if user_id in existing_ids:
        return

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([user_id, username or "", gender, age])

# --- Ініціалізація ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- Кнопки чату ---
chat_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Следующий", callback_data="next_chat"),
            InlineKeyboardButton(text="⛔ Стоп", callback_data="stop_chat")
        ]
    ]
)

search_stop_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Стоп", callback_data="stop_chat")]
    ]
)

# --- Відправка повідомлення про знайдений чат ---
async def send_chat_found(user_id: int):
    msg = await bot.send_message(user_id, "🔗 Найден собеседник! Начните общение.", reply_markup=chat_kb)
    last_messages[user_id] = msg.message_id

# --- Пошук нового співрозмовника ---
async def search_new_chat(user_id: int):
    if user_id in active_chats:
        await bot.send_message(user_id, "ℹ️ Вы уже в чате.")
        return

    if user_id in waiting_users:
        await bot.send_message(user_id, "🔎 Поиск собеседника уже запущен...", reply_markup=search_stop_kb)
        return

    waiting_users.append(user_id)
    msg = await bot.send_message(user_id, "🔎 Ищем собеседника...", reply_markup=search_stop_kb)
    last_messages[user_id] = msg.message_id

    for other_id in waiting_users:
        if other_id != user_id:
            waiting_users.remove(user_id)
            waiting_users.remove(other_id)
            active_chats[user_id] = other_id
            active_chats[other_id] = user_id
            await send_chat_found(user_id)
            await send_chat_found(other_id)
            return

# --- Callback кнопка "Найти нового" ---
@dp.callback_query(lambda c: c.data == "search_new")
async def search_new_callback(callback: CallbackQuery):
    await callback.answer()
    await search_new_chat(callback.from_user.id)

# --- Завершення чату та пошуку ---
async def end_chat(user_id: int, action: str = "stop"):
    # Якщо користувач у активному чаті
    if user_id in active_chats:
        partner_id = active_chats.pop(user_id)
        active_chats.pop(partner_id, None)

        for uid in (user_id, partner_id):
            if uid in last_messages:
                try:
                    await bot.edit_message_reply_markup(chat_id=uid, message_id=last_messages[uid], reply_markup=None)
                except:
                    pass
                last_messages.pop(uid, None)

        new_search_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Найти нового", callback_data="search_new")]
            ]
        )

        if action == "stop":
            await bot.send_message(user_id, "❌ Вы завершили чат.")
            await bot.send_message(partner_id, "⚠️ Собеседник завершил чат.", reply_markup=new_search_kb)
        elif action == "next":
            await bot.send_message(user_id, "❌ Вы завершили чат. Ищем нового собеседника...")
            await bot.send_message(partner_id, "⚠️ Собеседник завершил чат.", reply_markup=new_search_kb)

        if action == "next" and user_id not in waiting_users:
            waiting_users.append(user_id)
            await search_new_chat(user_id)

    # Якщо користувач у черзі пошуку
    if user_id in waiting_users:
        waiting_users.remove(user_id)
        if action == "stop":
            await bot.send_message(user_id, "❌ Поиск отменен.")

# --- /start ---
@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    if is_user_registered(message.from_user.id):
        await message.answer("✅ Вы уже зарегистрированы!\nНапишите /search, чтобы найти собеседника.")
        return

    gender_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Парень", callback_data="gender_paren"),
                InlineKeyboardButton(text="Девушка", callback_data="gender_devushka")
            ]
        ]
    )
    await message.answer("Привет! Давайте начнем.\n\nУкажите ваш пол:", reply_markup=gender_kb)
    await state.set_state(Form.gender)

# --- Обробка гендеру ---
@dp.callback_query(Form.gender)
async def process_gender_callback(callback: CallbackQuery, state: FSMContext):
    gender = None
    if callback.data == "gender_paren":
        gender = "Парень"
    elif callback.data == "gender_devushka":
        gender = "Девушка"

    if not gender:
        await callback.answer("Выберите пол кнопкой.")
        return

    await state.update_data(gender=gender)
    await callback.message.edit_text(f"✅ Вы выбрали: {gender}\nТеперь укажите ваш возраст:")
    await state.set_state(Form.age)
    await callback.answer()

# --- Введення віку ---
@dp.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if not (10 <= age <= 120):
            raise ValueError
    except ValueError:
        await message.answer("Введите корректный возраст (10-120).")
        return

    data = await state.get_data()
    gender = data.get("gender")
    user_id = message.from_user.id
    username = message.from_user.username

    save_user_data(user_id, username, gender, age)

    await bot.send_message(
        ADMIN_ID,
        f"👤 <b>Новий користувач:</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Username: @{username or 'немає'}\n"
        f"👫 Стать: {gender}\n"
        f"🎂 Вік: {age}"
    )

    await message.answer("✅ Спасибо! Данные сохранены.\nНапишите /search, чтобы найти собеседника.")
    await state.clear()

# --- /search ---
@dp.message(Command("search"))
async def search_cmd(message: Message):
    await search_new_chat(message.from_user.id)

# --- /stop ---
@dp.message(Command("stop"))
async def stop_cmd(message: Message):
    await end_chat(message.from_user.id, action="stop")

# --- /next ---
@dp.message(Command("next"))
async def next_cmd(message: Message):
    await end_chat(message.from_user.id, action="next")

# --- Callback кнопки ---
@dp.callback_query(lambda c: c.data == "next_chat")
async def next_callback(callback: CallbackQuery):
    await end_chat(callback.from_user.id, action="next")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "stop_chat")
async def stop_callback(callback: CallbackQuery):
    await end_chat(callback.from_user.id, action="stop")
    await callback.answer()

# --- Повідомлення чату ---

# --- Адмінські команди --- повинні бути першими
@dp.message(Command("get_csv"))
async def get_csv_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ви не є адміном.")
        return

    if not os.path.isfile(CSV_FILE):
        await message.answer("❌ Файл CSV ще не створений.")
        return

    csv_file = FSInputFile(CSV_FILE)
    await message.answer_document(csv_file, caption="📁 Ось файл CSV з усіма користувачами")

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Ви не є адміном.")
        return

    if not os.path.isfile(CSV_FILE):
        await message.answer("❌ Файл CSV ще не створений.")
        return

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        count = sum(1 for _ in f) - 1  # віднімаємо заголовок
    await message.answer(f"👥 Зареєстровано користувачів: {count}")

@dp.message(F.text)
async def message_handler(message: Message):
    # Пропускаємо адміністраторські команди
    if message.from_user.id == ADMIN_ID and message.text.startswith(("/", "!")):
        return

    user_id = message.from_user.id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        try:
            await bot.send_message(partner_id, message.text or "")
        except:
            await message.answer("❗ Не удалось доставить сообщение.")
    else:
        await message.answer("ℹ️ Вы не в чате. Напишите /search чтобы начать.")




# --- Запуск ---
if __name__ == "__main__":
    try:
        asyncio.run(dp.start_polling(bot))
    except (KeyboardInterrupt, SystemExit):
        print("Бот зупинено")

