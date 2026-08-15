from telethon import TelegramClient
import asyncio
import os
import json
from datetime import datetime
from flask import Flask
import threading

# ==================================================
# FLASK для Render (healthcheck)
# ==================================================
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "🤖 Бот для пересылки работает!"

@flask_app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================================================
# КОНФИГУРАЦИЯ
# ==================================================
API_ID = int(os.getenv("API_ID", 38768855))
API_HASH = os.getenv("API_HASH", "063f9c49fb067c9402fa3e36d8b1355d")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [8370080332, 8559381302, 8924977674]
CONFIG_FILE = "forward_config.json"
SESSION_FILE = "fff.session"  # <-- ТВОЙ ФАЙЛ СЕССИИ

# Telethon клиент с указанием файла сессии
user_client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

# Aiogram бот (для управления)
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ==================================================
# СОСТОЯНИЯ
# ==================================================
class SettingsStates(StatesGroup):
    waiting_source = State()
    waiting_target = State()

# ==================================================
# ЗАГРУЗКА/СОХРАНЕНИЕ НАСТРОЕК
# ==================================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"source": None, "target": None, "is_running": False}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

config = load_config()
is_running = False
forward_task = None

# ==================================================
# КЛАВИАТУРЫ
# ==================================================
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Настройка", callback_data="settings")],
        [InlineKeyboardButton(text="▶️ Запустить", callback_data="start_forward")],
        [InlineKeyboardButton(text="⏹️ Остановить", callback_data="stop_forward")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")]
    ])

def get_status_text():
    source = config.get("source") or "❌ Не задан"
    target = config.get("target") or "❌ Не задан"
    status = "✅ Работает" if is_running else "⏹️ Остановлен"
    return f"""📊 <b>СТАТУС</b>

📥 Источник: {source}
📤 Назначение: {target}
🔄 Состояние: {status}

<b>Инструкция:</b>
1. Настрой каналы (введи ID с -100)
2. Нажми "Запустить"
3. Бот перешлёт ВСЕ сообщения
4. Нажми "Остановить" в любой момент"""

# ==================================================
# ОСНОВНАЯ ЛОГИКА ПЕРЕСЫЛКИ (ЧЕРЕЗ TELEGON)
# ==================================================
# ==================================================
# ОСНОВНАЯ ЛОГИКА ПЕРЕСЫЛКИ (ЧЕРЕЗ TELEGON)
# ==================================================
# ==================================================
# ОСНОВНАЯ ЛОГИКА ПЕРЕСЫЛКИ (ЧЕРЕЗ TELEGON)
# ==================================================
async def forward_all_messages():
    global is_running, forward_task
    
    source = config.get("source")
    target = config.get("target")
    
    if not source or not target:
        await bot.send_message(ADMIN_IDS[0], "❌ Не настроены каналы!")
        return
    
    await bot.send_message(ADMIN_IDS[0], "🔍 Проверяю каналы...")
    
    try:
        # Пробуем получить каналы с таймаутом
        source_entity = await asyncio.wait_for(
            user_client.get_entity(int(source)), 
            timeout=30
        )
        target_entity = await asyncio.wait_for(
            user_client.get_entity(int(target)), 
            timeout=30
        )
        await bot.send_message(
            ADMIN_IDS[0],
            f"✅ Найдены каналы!\n📥 {source_entity.title}\n📤 {target_entity.title}"
        )
    except asyncio.TimeoutError:
        await bot.send_message(ADMIN_IDS[0], "❌ Таймаут! Проверь ID каналов или подключение.")
        return
    except ValueError:
        await bot.send_message(ADMIN_IDS[0], "❌ Неправильный ID! ID должен начинаться с -100")
        return
    except Exception as e:
        await bot.send_message(ADMIN_IDS[0], f"❌ Канал не найден! Проверь ID: {e}")
        return
    
    await bot.send_message(ADMIN_IDS[0], "📋 Собираю все сообщения... (это может занять время)")
    
    messages = []
    try:
        # Получаем сообщения с таймаутом
        async for msg in user_client.iter_messages(source_entity, limit=None):
            messages.append(msg)
            if len(messages) % 100 == 0:
                await bot.send_message(ADMIN_IDS[0], f"📥 Собрано {len(messages)} сообщений...")
    except asyncio.TimeoutError:
        await bot.send_message(ADMIN_IDS[0], "❌ Таймаут при получении сообщений!")
        return
    except Exception as e:
        await bot.send_message(ADMIN_IDS[0], f"❌ Ошибка получения сообщений: {e}")
        return
    
    total = len(messages)
    forwarded = 0
    skipped = 0
    is_running = True
    
    await bot.send_message(ADMIN_IDS[0], f"📋 Найдено {total} сообщений. Начинаю пересылку...")
    
    for i, msg in enumerate(reversed(messages), 1):
        if not is_running:
            await bot.send_message(ADMIN_IDS[0], "⏹️ Пересылка остановлена.")
            return
        
        try:
            if msg.text and msg.text.startswith("/"):
                skipped += 1
                continue
            
            await user_client.forward_messages(target_entity, msg)
            forwarded += 1
            
            if forwarded % 50 == 0:
                await bot.send_message(
                    ADMIN_IDS[0],
                    f"📊 Прогресс: {forwarded}/{total} ({forwarded*100//total}%)"
                )
            
            if forwarded % 10 == 0:
                await asyncio.sleep(10)
            
            if forwarded % 100 == 0:
                await bot.send_message(ADMIN_IDS[0], "⏸️ Большая пауза 3 минуты...")
                await asyncio.sleep(180)
                
        except Exception as e:
            await bot.send_message(ADMIN_IDS[0], f"❌ Ошибка: {e}")
            skipped += 1
            await asyncio.sleep(2)
    
    is_running = False
    await bot.send_message(
        ADMIN_IDS[0],
        f"✅ <b>ПЕРЕСЫЛКА ЗАВЕРШЕНА!</b>\n\n"
        f"📤 Переслано: {forwarded}\n"
        f"⏩ Пропущено: {skipped}\n"
        f"📊 Всего: {total}"
    )
    # ... остальной код
# ==================================================
# ХЭНДЛЕРЫ БОТА (Aiogram)
# ==================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов!")
        return
    await message.answer("🤖 <b>Бот для пересылки</b>", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Источник", callback_data="set_source")],
        [InlineKeyboardButton(text="📤 Назначение", callback_data="set_target")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])
    await callback.message.edit_text(get_status_text(), reply_markup=kb)

@dp.callback_query(F.data == "set_source")
async def set_source(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📥 <b>Введите ID канала-источника</b>\n\n"
        "Пример: -1001234567890",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="settings")]
        ])
    )
    await state.set_state(SettingsStates.waiting_source)

@dp.callback_query(F.data == "set_target")
async def set_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📤 <b>Введите ID канала-назначения</b>\n\n"
        "Пример: -1001234567890",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="settings")]
        ])
    )
    await state.set_state(SettingsStates.waiting_target)

@dp.message(SettingsStates.waiting_source)
async def process_source(message: Message, state: FSMContext):
    config["source"] = message.text.strip()
    save_config(config)
    await state.clear()
    await message.answer(f"✅ Источник: <code>{config['source']}</code>", reply_markup=get_main_keyboard())

@dp.message(SettingsStates.waiting_target)
async def process_target(message: Message, state: FSMContext):
    config["target"] = message.text.strip()
    save_config(config)
    await state.clear()
    await message.answer(f"✅ Назначение: <code>{config['target']}</code>", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "start_forward")
async def start_forward(callback: CallbackQuery):
    global is_running, forward_task
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    
    if is_running:
        await callback.message.edit_text("⏳ Уже запущено!", reply_markup=get_main_keyboard())
        return
    
    if not config.get("source") or not config.get("target"):
        await callback.message.edit_text("❌ Настрой каналы сначала!", reply_markup=get_main_keyboard())
        return
    
    await callback.message.edit_text("▶️ Запускаю пересылку...", reply_markup=get_main_keyboard())
    forward_task = asyncio.create_task(forward_all_messages())

@dp.callback_query(F.data == "stop_forward")
async def stop_forward(callback: CallbackQuery):
    global is_running
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    is_running = False
    await callback.message.edit_text("⏹️ Остановлено.", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "status")
async def show_status(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(get_status_text(), reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("🤖 <b>Бот для пересылки</b>", reply_markup=get_main_keyboard())

# ==================================================
# ЗАПУСК
# ==================================================
async def main():
    print("🚀 ЗАПУСК БОТА...")
    
    # Проверяем, есть ли файл сессии
    if os.path.exists(SESSION_FILE):
        print(f"✅ Файл сессии {SESSION_FILE} найден!")
    else:
        print(f"⚠️ Файл сессии {SESSION_FILE} НЕ НАЙДЕН! Запусти скрипт локально для создания сессии.")
    
    # Запускаем Telethon клиент (с готовой сессией)
    await user_client.start()
    print("✅ Telethon клиент запущен")
    
    # Запускаем Aiogram бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask для Render
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask запущен в фоновом потоке!")
    
    asyncio.run(main())
