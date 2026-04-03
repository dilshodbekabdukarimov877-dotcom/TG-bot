import asyncio
import io
import sqlite3
import logging
import os
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

# --- SOZLAMALAR ---
TOKEN = "AIzaSyDDVz-r7JoOww4h3yrkYHIfEdv1Hdh1TEI"
GEMINI_KEY = "AIzaSyAY4F5N6RDBffJGNZ_JdXGV75PuzQhzFrA"  # O'z kalitingizni qo'ying
ADMIN_ID = 7806849831

# Gemini sozlamalari
genai.configure(api_key="AIzaSyAY4F5N6RDBffJGNZ_JdXGV75PuzQhzFrA")
model = genai.GenerativeModel('gemini-2.5-flash')

# Logger va Dispatcher
logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
chat_sessions = {}

# --- RENDER UCHUN KEEP-ALIVE SERVER ---
app = Flask('')


@app.route('/')
def home():
    return "Bot is running 24/7!"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


# --- MA'LUMOTLAR BAZASI ---
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


# --- 1. ASOSIY BUYRUQLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(
        f"Assalomu alaykum, {message.from_user.full_name}! 👋\nMen Gemini AI yordamida ishlovchi botman.\n\nYordam uchun: /help")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 **Botdan foydalanish qo'llanmasi:**\n\n"
        "💬 **AI suhbat:** Shunchaki savol yozing, AI javob beradi.\n"
        "🎨 **Rasm chizish:** `/draw [tavsif]` (masalan: `/draw dengiz qirg'og'i`)\n"
        "🖼 **Rasm tahlili:** Botga rasm yuboring, u rasmda nima borligini aytadi.\n"
        "🎙 **Ovozli xabar:** Ovoz yuboring, AI uni eshitib javob qaytaradi.\n"
        "🧹 **Tozalash:** `/clear` - Suhbat xotirasini o'chiradi.\n"
        "📱 **Menu:** `/menu` - Web ilovani ochish.\n"
        "✨ **Inline:** `@bot_nomi savol` deb yozib, boshqa chatlarda ishlating."
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    chat_sessions.pop(message.from_user.id, None)
    await message.answer("🧹 Suhbat tarixi tozalandi!")


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="AI Dashboard (Web App)", web_app=WebAppInfo(url="https://google.com"))]
    ])
    await message.answer("Web ilovani ochish uchun tugmani bosing:", reply_markup=kb)


# --- 2. ADMIN BUYRUQLARI ---

@dp.message(Command("stat"))
async def cmd_stat(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        users = get_all_users()
        await message.answer(f"📊 **Statistika:**\nJami foydalanuvchilar: {len(users)} ta")
    else:
        await message.answer("❌ Bu buyruq faqat admin uchun.")


@dp.message(Command("reklama"))
async def cmd_reklama(message: types.Message, bot: Bot):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/reklama", "").strip()
    if not text:
        return await message.answer("⚠️ Reklama matnini yozing: `/reklama Salom`")

    users = get_all_users()
    count = 0
    msg = await message.answer("📢 Reklama yuborilmoqda...")
    for u_id in users:
        try:
            await bot.send_message(u_id, text)
            count += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await msg.edit_text(f"✅ Reklama yakunlandi: {count} kishiga yuborildi.")


# --- 3. AI FUNKSIYALARI ---

@dp.message(Command("draw"))
async def cmd_draw(message: types.Message, command: CommandObject):
    if not command.args:
        return await message.answer("🎨 Tavsif bering: `/draw koinotdagi kema`")

    wait = await message.answer("🎨 Rasm chizilmoqda, kuting...")
    try:
        res = model.generate_content(f"Create a professional English image prompt for: {command.args}")
        prompt_en = res.text.strip().replace(" ", "%20").replace('"', "").replace("'", "")
        url = f"https://pollinations.ai/p/{prompt_en}?width=1024&height=1024&seed={uuid.uuid4().int}&model=flux"
        await message.reply_photo(url, caption=f"✨ Natija: {command.args}")
        await wait.delete()
    except Exception as e:
        logging.error(f"Draw error: {e}")
        await wait.edit_text("❌ Rasm chizishda xatolik yuz berdi.")


@dp.inline_query()
async def inline_handler(inline_query: types.InlineQuery):
    text = inline_query.query or "Salom"
    try:
        response = model.generate_content(text)
        articles = [InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Gemini AI javobi",
            input_message_content=InputTextMessageContent(message_text=f"🤖 **AI:** {response.text}"),
            description=response.text[:50] + "..."
        )]
        await inline_query.answer(articles, cache_time=1)
    except:
        pass


@dp.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot):
    try:
        v_file = await bot.get_file(message.voice.file_id)
        buf = io.BytesIO()
        await bot.download_file(v_file.file_path, buf)
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message(
            ["Ushbu ovozni eshitib javob ber:", {'mime_type': 'audio/ogg', 'data': buf.getvalue()}])
        await message.reply(resp.text)
    except:
        await message.answer("🎙 Ovozni tushunishda xato.")


@dp.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    try:
        p_file = await bot.get_file(message.photo[-1].file_id)
        buf = io.BytesIO()
        await bot.download_file(p_file.file_path, buf)
        img = Image.open(buf)
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message([message.caption or "Rasmda nima bor?", img])
        await message.reply(resp.text)
    except:
        await message.answer("🖼 Rasmni tahlil qilishda xato.")


@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    add_user(message.from_user.id)
    try:
        chat = chat_sessions.setdefault(message.from_user.id, model.start_chat(history=[]))
        resp = chat.send_message(message.text)
        await message.answer(resp.text)
    except:
        await message.answer("⏳ Limit tugadi yoki xatolik yuz berdi.")


# --- ASOSIY ISHGA TUSHIRISH ---
async def main():
    init_db()
    keep_alive()  # Render uchun portni ochiq tutadi
    bot = Bot(token="8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak")
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Bot barcha funksiyalar bilan Render-da ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
