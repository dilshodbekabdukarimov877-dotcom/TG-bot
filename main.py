import os
import subprocess
import sys

# --- 1. KUTUBXONALARNI MAJBURIY O'RNATISH (Render xatosi uchun) ---
def install_packages():
    packages = ["aiogram", "google-generativeai", "Pillow", "flask"]
    for package in packages:
        try:
            # Kutubxona bor-yo'qligini tekshirish va o'rnatish
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        except Exception as e:
            print(f"Error installing {package}: {e}")

install_packages()

# --- 2. ASOSIY IMPORTLAR ---
import asyncio
import io
import sqlite3
import logging
import uuid
from threading import Thread
import google.generativeai as genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    WebAppInfo
)
from PIL import Image
from flask import Flask

# --- 3. SOZLAMALAR ---
TOKEN = "8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak"
GEMINI_KEY = "AIzaSyAxr3tGTGBSjN2gzx8Q2ed5oDuQJ453d3A" # O'z kalitingizni shu yerga qo'ying
ADMIN_ID = 708000

genai.configure(api_key="AIzaSyAxr3tGTGBSjN2gzx8Q2ed5oDuQJ453d3A")
model = genai.GenerativeModel('gemini-2.5-flash')

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
chat_sessions = {}

# --- 4. RENDER UCHUN FLASK SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is active and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- 5. MA'LUMOTLAR BAZASI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'users_base.db')

def init_db():
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(db_path)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(db_path)
    users = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    return [u[0] for u in users]

# --- 6. BUYRUQLAR (HELP, START, CLEAR, MENU) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(f"Assalomu alaykum, {message.from_user.full_name}! 👋\nBot ishga tushdi.\n\nYordam: /help")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 **Bot qo'llanmasi:**\n\n"
        "💬 **AI suhbat:** Shunchaki savol yozing.\n"
        "🎨 **Rasm chizish:** `/draw [tavsif]`\n"
        "🖼 **Rasm tahlili:** Botga rasm yuboring.\n"
        "🎙 **Ovozli xabar:** AI ovozni tushunadi.\n"
        "🧹 **Tozalash:** `/clear` - Xotirani o'chirish.\n"
        "📱 **Menu:** `/menu` - Web App.\n"
        "✨ **Inline:** `@bot_nomi savol` deb yozing."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    chat_sessions.pop(message.from_user.id, None)
    await message.answer("🧹 Suhbat tarixi tozalandi!")

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AI Dashboard", web_app=WebAppInfo(url="https://google.com"))]
    ])
    await message.answer("Web ilovani ochish:", reply_markup=kb)

# --- 7. ADMIN PANEL ---

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        users = get_all_users()
        await message.answer(f"📊 Statistika: {len(users)} ta foydalanuvchi.")
    else:
        await message.answer("❌ Admin emassiz.")

@dp.message(Command("reklama"))
async def cmd_reklama(message: types.Message, bot: Bot):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/reklama", "").strip()
    if not text: return await message.answer("Xabarni yozing.")
    
    users = get_all_users()
    for u_id in users:
        try:
            await bot.send_message(u_id, text)
            await asyncio.sleep(0.05)
        except: continue
    await message.answer("✅ Reklama tarqatildi.")

# --- 8. AI FUNKSIYALARI ---

@dp.message(Command("draw"))
async def cmd_draw(message: types.Message, command: CommandObject):
    if not command.args: return await message.answer("Tavsif bering: `/draw kema`")
    wait = await message.answer("🎨 Chizilmoqda...")
    try:
        res = model.generate_content(f"English prompt: {command.args}")
        p = res.text.strip().replace(" ", "%20").replace('"', "").replace("'", "")
        url = f"https://pollinations.ai/p/{p}?width=1024&height=1024&seed={uuid.uuid4().int}"
        await message.reply_photo(url, caption=f"✨ Natija: {command.args}")
        await wait.delete()
    except: await wait.edit_text("❌ Xatolik.")

@dp.inline_query()
async def inline_handler(inline_query: types.InlineQuery):
    text = inline_query.query or "Salom"
    try:
        response = model.generate_content(text)
        articles = [InlineQueryResultArticle(
            id=str(uuid.uuid4()), title="Gemini AI",
            input_message_content=InputTextMessageContent(message_text=f"🤖 AI: {response.text}")
        )]
        await inline_query.answer(articles, cache_time=1)
    except: pass

@dp.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    try:
        v_file = await bot.get_file(message.voice.file_id)
        buf = io.BytesIO(); await bot.download_file(v_file.file_path, buf)
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message(["Eshiting:", {'mime_type': 'audio/ogg', 'data': buf.getvalue()}])
        await message.reply(resp.text)
    except: await message.answer("🎙 Xato.")

@dp.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    try:
        p_file = await bot.get_file(message.photo[-1].file_id)
        buf = io.BytesIO(); await bot.download_file(p_file.file_path, buf)
        img = Image.open(buf)
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message([message.caption or "Rasmda nima bor?", img])
        await message.reply(resp.text)
    except: await message.answer("🖼 Xato.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    add_user(message.from_user.id)
    try:
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message(message.text)
        await message.answer(resp.text)
    except: await message.answer("⏳ Xatolik.")

# --- 9. ISHGA TUSHIRISH ---
async def main():
    init_db()
    keep_alive() # Render uchun port
    bot = Bot(token="8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak")
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Bot Render-da ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
