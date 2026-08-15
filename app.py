import logging
import asyncio
import os
import json
import threading
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

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
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [8370080332, 8559381302, 8924977674]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ==================================================
# СОСТОЯНИЯ
# ==================================================
class SettingsStates(StatesGroup):
    waiting_source_chat = State()
    waiting_target_chat = State()
    waiting_pause_mode = State()

# ==================================================
# НАСТРОЙКИ
# ==================================================
PAUSE_MODES = {
    "slow": {"name": "🐢 Медленный (10 файлов → 15 сек, 100 → 5 мин)", "pause_10": 15, "pause_100": 300},
    "medium": {"name": "🚶 Средний (10 файлов → 10 сек, 100 → 3 мин)", "pause_10": 10, "pause_100": 180},
    "fast": {"name": "🚀 Быстрый (10 файлов → 5 сек, 100 → 1 мин)", "pause_10": 5, "pause_100": 60},
}

config_file = "forward_config.json"

def load_config():
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            return json.load(f)
    return {"source_chat": None, "target_chat": None, "pause_mode": "medium", "is_running": False}

def save_config(config):
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

config = load_config()
forward_task = None
is_running = False

# ==================================================
# КЛАВИАТУРЫ
# ==================================================
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Настройка пересылки", callback_data="settings")],
        [InlineKeyboardButton(text="▶️ Старт пересылки", callback_data="start_forward")],
        [InlineKeyboardButton(text="⏹️ Остановить", callback_data="stop_forward")],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")]
    ])

def get_settings_keyboard():
    source = config.get("source_chat") or "Не задан"
    target = config.get("target_chat") or "Не задан"
    mode = config.get("pause_mode", "medium")
    mode_name = PAUSE_MODES.get(mode, {}).get("name", "Не задан")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Канал-источник", callback_data="set_source")],
        [InlineKeyboardButton(text="📤 Канал-назначение", callback_data="set_target")],
        [InlineKeyboardButton(text="⏱️ Режим пауз", callback_data="set_pause")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_pause_keyboard():
    buttons = []
    for key, mode in PAUSE_MODES.items():
        is_active = "✅ " if config.get("pause_mode") == key else ""
        buttons.append([InlineKeyboardButton(
            text=f"{is_active}{mode['name']}", 
            callback_data=f"pause_{key}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_status_text():
    source = config.get("source_chat") or "❌ Не задан"
    target = config.get("target_chat") or "❌ Не задан"
    mode = config.get("pause_mode", "medium")
    mode_name = PAUSE_MODES.get(mode, {}).get("name", "Не задан")
    running = "✅ Работает" if config.get("is_running") else "⏹️ Остановлен"
    
    return f"""📊 <b>СТАТУС БОТА</b>

📥 Источник: {source}
📤 Назначение: {target}
⏱️ Режим пауз: {mode_name}
🔄 Состояние: {running}

<b>Инструкция:</b>
1. Настрой каналы
2. Выбери режим пауз
3. Нажми "Старт пересылки"
4. Бот начнёт пересылку всех сообщений
5. Нажми "Остановить" в любой момент"""

# ==================================================
# ХЭНДЛЕРЫ
# ==================================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов!")
        return
    
    await message.answer(
        "🤖 <b>Бот для пересылки медиа между каналами</b>\n\n"
        "Используй кнопки для настройки и управления:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "🤖 <b>Бот для пересылки медиа между каналами</b>\n\n"
        "Используй кнопки для настройки и управления:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        get_status_text(),
        reply_markup=get_settings_keyboard()
    )

@dp.callback_query(F.data == "set_source")
async def set_source(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "📥 <b>Введите ID канала-источника</b>\n\n"
        "Примеры:\n"
        "• -1001234567890 (приватный канал)\n"
        "• @username (публичный канал)\n"
        "• 1234567890 (ID пользователя)\n\n"
        "Отправьте ID или username в чат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="settings")]
        ])
    )
    await state.set_state(SettingsStates.waiting_source_chat)

@dp.callback_query(F.data == "set_target")
async def set_target(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "📤 <b>Введите ID канала-назначения</b>\n\n"
        "Примеры:\n"
        "• -1001234567890 (приватный канал)\n"
        "• @username (публичный канал)\n"
        "• 1234567890 (ID пользователя)\n\n"
        "Отправьте ID или username в чат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="settings")]
        ])
    )
    await state.set_state(SettingsStates.waiting_target_chat)

@dp.callback_query(F.data == "set_pause")
async def set_pause(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "⏱️ <b>Выберите режим пауз</b>\n\n"
        "Паузы нужны чтобы избежать блокировки Telegram:",
        reply_markup=get_pause_keyboard()
    )

@dp.callback_query(F.data.startswith("pause_"))
async def select_pause(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    await callback.answer()
    mode = callback.data.replace("pause_", "")
    config["pause_mode"] = mode
    save_config(config)
    
    await callback.message.edit_text(
        f"✅ Режим пауз изменён на: {PAUSE_MODES[mode]['name']}",
        reply_markup=get_pause_keyboard()
    )

@dp.message(SettingsStates.waiting_source_chat)
async def process_source_chat(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов!")
        return
    
    chat_input = message.text.strip()
    config["source_chat"] = chat_input
    save_config(config)
    await state.clear()
    
    await message.answer(
        f"✅ Канал-источник установлен: <code>{chat_input}</code>",
        reply_markup=get_main_keyboard()
    )

@dp.message(SettingsStates.waiting_target_chat)
async def process_target_chat(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Только для админов!")
        return
    
    chat_input = message.text.strip()
    config["target_chat"] = chat_input
    save_config(config)
    await state.clear()
    
    await message.answer(
        f"✅ Канал-назначение установлен: <code>{chat_input}</code>",
        reply_markup=get_main_keyboard()
    )

# ==================================================
# ОСНОВНАЯ ЛОГИКА ПЕРЕСЫЛКИ
# ==================================================

forward_task = None
is_running = False
total_messages = 0
forwarded_count = 0
skipped_count = 0

async def forward_messages():
    global is_running, total_messages, forwarded_count, skipped_count, forward_task
    
    source = config.get("source_chat")
    target = config.get("target_chat")
    mode = config.get("pause_mode", "medium")
    
    if not source or not target:
        await bot.send_message(ADMIN_IDS[0], "❌ Не настроены каналы!")
        return
    
    try:
        source_entity = await bot.get_chat(source)
        target_entity = await bot.get_chat(target)
        await bot.send_message(
            ADMIN_IDS[0], 
            f"✅ Найдены каналы:\n📥 {source_entity.title} (ID: {source_entity.id})\n📤 {target_entity.title} (ID: {target_entity.id})"
        )
    except Exception as e:
        await bot.send_message(ADMIN_IDS[0], f"❌ Ошибка: {e}")
        return
    
    pause_10 = PAUSE_MODES[mode]["pause_10"]
    pause_100 = PAUSE_MODES[mode]["pause_100"]
    
    await bot.send_message(ADMIN_IDS[0], "📋 Собираю все сообщения из канала-источника...")
    
    messages = []
    offset_id = 0
    while True:
        try:
            batch = await bot.get_chat_history(source_entity.id, limit=100, offset_id=offset_id)
            if not batch:
                break
            messages.extend(batch)
            offset_id = batch[-1].message_id
            await asyncio.sleep(0.5)
        except Exception as e:
            await bot.send_message(ADMIN_IDS[0], f"⚠️ Ошибка получения сообщений: {e}")
            break
    
    total_messages = len(messages)
    forwarded_count = 0
    skipped_count = 0
    is_running = True
    config["is_running"] = True
    save_config(config)
    
    await bot.send_message(
        ADMIN_IDS[0], 
        f"📋 Найдено {total_messages} сообщений. Начинаю пересылку...\n\n⏱️ Режим: {PAUSE_MODES[mode]['name']}"
    )
    
    for i, msg in enumerate(reversed(messages), 1):
        if not is_running:
            await bot.send_message(ADMIN_IDS[0], "⏹️ Пересылка остановлена пользователем.")
            config["is_running"] = False
            save_config(config)
            return
        
        try:
            # Пропускаем служебные сообщения
            if msg.text and msg.text.startswith("/"):
                skipped_count += 1
                continue
            
            await bot.forward_message(target_entity.id, source_entity.id, msg.message_id)
            forwarded_count += 1
            
            if forwarded_count % 50 == 0:
                await bot.send_message(
                    ADMIN_IDS[0],
                    f"📊 Прогресс: {forwarded_count}/{total_messages} ({forwarded_count*100//total_messages}%)"
                )
            
            if forwarded_count % 10 == 0:
                await asyncio.sleep(pause_10)
            
            if forwarded_count % 100 == 0:
                await bot.send_message(ADMIN_IDS[0], f"⏸️ Большая пауза {pause_100//60} минут...")
                await asyncio.sleep(pause_100)
                
        except Exception as e:
            await bot.send_message(ADMIN_IDS[0], f"❌ Ошибка при пересылке {msg.message_id}: {e}")
            skipped_count += 1
            await asyncio.sleep(2)
    
    is_running = False
    config["is_running"] = False
    save_config(config)
    
    await bot.send_message(
        ADMIN_IDS[0],
        f"✅ <b>ПЕРЕСЫЛКА ЗАВЕРШЕНА!</b>\n\n"
        f"📤 Переслано: {forwarded_count}\n"
        f"⏩ Пропущено: {skipped_count}\n"
        f"📊 Всего: {total_messages}"
    )

@dp.callback_query(F.data == "start_forward")
async def start_forward(callback: CallbackQuery):
    global forward_task, is_running
    
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    
    await callback.answer()
    
    if is_running:
        await callback.message.edit_text("⏳ Пересылка уже запущена!", reply_markup=get_main_keyboard())
        return
    
    source = config.get("source_chat")
    target = config.get("target_chat")
    
    if not source or not target:
        await callback.message.edit_text("❌ Сначала настрой оба канала!", reply_markup=get_main_keyboard())
        return
    
    await callback.message.edit_text("▶️ Запускаю пересылку...", reply_markup=get_main_keyboard())
    
    forward_task = asyncio.create_task(forward_messages())

@dp.callback_query(F.data == "stop_forward")
async def stop_forward(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    
    await callback.answer()
    global is_running
    is_running = False
    config["is_running"] = False
    save_config(config)
    await callback.message.edit_text("⏹️ Пересылка остановлена.", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "status")
async def show_status(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов!", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(get_status_text(), reply_markup=get_main_keyboard())

# ==================================================
# ЗАПУСК
# ==================================================
async def main():
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 50)
    print("🚀 БОТ ЗАПУЩЕН!")
    print(f"👥 Админы: {ADMIN_IDS}")
    print("=" * 50)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке для Render
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask запущен в фоновом потоке!")
    
    asyncio.run(main())
