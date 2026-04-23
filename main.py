import os, subprocess, sys, asyncio, io, sqlite3, logging, uuid
from threading import Thread
from PIL import Image
from flask import Flask

# --- KUTUBXONALARNI MAJBURIY O'RNATISH ---
def install_packages():
    packages = ["aiogram", "google-generativeai", "Pillow", "flask"]
    for p in packages:
        try: subprocess.check_call([sys.executable, "-m", "pip", "install", p])
        except: pass

install_packages()

import google.generativeai as genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton

# --- SOZLAMALAR ---
TOKEN = "8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak"
GEMINI_KEY = "AIzaSyByFX3e2Esr33QuWrI8nd4FRE3QSsPDN94" 
ADMIN_ID = 5122557577

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
app = Flask('')

# --- MA'LUMOTLAR BAZASI ---
DB_NAME = 'bot_memory.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)')
    conn.commit(); conn.close()

def add_user(u_id):
    conn = sqlite3.connect(DB_NAME); conn.execute('INSERT OR IGNORE INTO users VALUES (?)', (u_id,)); conn.commit(); conn.close()

def save_chat(u_id, role, text):
    conn = sqlite3.connect(DB_NAME)
    conn.execute('INSERT INTO history VALUES (?, ?, ?)', (u_id, role, text))
    conn.execute('DELETE FROM history WHERE rowid NOT IN (SELECT rowid FROM history WHERE user_id = ? ORDER BY rowid DESC LIMIT 10) AND user_id = ?', (u_id, u_id))
    conn.commit(); conn.close()

def get_chat(u_id):
    conn = sqlite3.connect(DB_NAME); rows = conn.execute('SELECT role, content FROM history WHERE user_id = ? ORDER BY rowid ASC', (u_id,)).fetchall(); conn.close()
    return [{"role": r[0], "parts": [r[1]]} for r in rows]

# --- ASOSIY BUYRUQLAR (START, HELP, CLEAR) ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    add_user(m.from_user.id)
    await m.answer(f"Assalomu alaykum, {m.from_user.full_name}! 👋\nMen Gemini 1.5 Pro asosida ishlovchi aqlli botman.\n\nSavolingizni yozing yoki rasm/video/pdf yuboring!")

@dp.message(Command("help"))
async def cmd_help(m: types.Message):
    help_text = (
        "📖 **Bot imkoniyatlari:**\n\n"
        "💬 **AI Suhbat:** Shunchaki savol yozing, bot oldingi gaplaringizni eslab qoladi.\n"
        "🖼 **Media tahlil:** Rasm, Video yoki PDF yuboring, bot ularni o'qib tushuntirib beradi.\n"
        "🧹 **Tozalash:** `/clear` - Suhbat tarixini o'chirish.\n"
        "✨ **Inline:** Istalgan guruhda `@bot_nomi savol` deb yozing.\n\n"
        "👨‍💻 **Admin uchun:** `/stat`, `/reklama`."
    )
    await m.answer(help_text, parse_mode="Markdown")

@dp.message(Command("clear"))
async def cmd_clear(m: types.Message):
    conn = sqlite3.connect(DB_NAME); conn.execute('DELETE FROM history WHERE user_id = ?', (m.from_user.id,)); conn.commit(); conn.close()
    await m.answer("🧹 Suhbat tarixi tozalandi!")

# --- ADMIN BUYRUQLARI ---
@dp.message(Command("stat"))
async def cmd_stat(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_NAME); count = conn.execute('SELECT count(*) FROM users').fetchone()[0]; conn.close()
    await m.answer(f"📊 Jami foydalanuvchilar: {count} ta")

@dp.message(Command("reklama"))
async def cmd_reklama(m: types.Message, bot: Bot):
    if m.from_user.id != ADMIN_ID: return
    text = m.text.replace("/reklama", "").strip()
    if not text: return await m.answer("Reklama matnini yozing.")
    conn = sqlite3.connect(DB_NAME); users = conn.execute('SELECT user_id FROM users').fetchall(); conn.close()
    for u in users:
        try: await bot.send_message(u[0], text); await asyncio.sleep(0.05)
        except: continue
    await m.answer("✅ Reklama barchaga yuborildi.")

# --- FAYLLAR (PDF, VIDEO, RASM) ---
@dp.message(F.document | F.video | F.photo)
async def handle_media(m: types.Message, bot: Bot):
    wait = await m.answer("🔍 Fayl tahlil qilinmoqda, biroz kuting...")
    try:
        f_id = m.document.file_id if m.document else (m.video.file_id if m.video else m.photo[-1].file_id)
        f_path = await bot.get_file(f_id)
        f_data = await bot.download_file(f_path.file_path)
        mime = m.document.mime_type if m.document else ("video/mp4" if m.video else "image/jpeg")
        
        resp = model.generate_content([m.caption or "Ushbu faylni tahlil qil:", {"mime_type": mime, "data": f_data.read()}])
        await wait.edit_text(resp.text)
    except Exception as e: await wait.edit_text(f"❌ Xatolik yuz berdi. Fayl juda katta bo'lishi mumkin.")

# --- INLINE MODE ---
@dp.inline_query()
async def inline_handler(q: types.InlineQuery):
    if not q.query: return
    try:
        res = model.generate_content(q.query)
        results = [InlineQueryResultArticle(id=str(uuid.uuid4()), title="Gemini AI javobi", input_message_content=InputTextMessageContent(message_text=f"🤖 **AI:** {res.text}"))]
        await q.answer(results, cache_time=1)
    except: pass

# --- MATNLI SUHBAT ---
@dp.message(F.text)
async def handle_text(m: types.Message):
    if m.text.startswith("/"): return
    add_user(m.from_user.id)
    history = get_chat(m.from_user.id)
    try:
        chat = model.start_chat(history=history)
        resp = chat.send_message(m.text)
        save_chat(m.from_user.id, "user", m.text)
        save_chat(m.from_user.id, "model", resp.text)
        await m.answer(resp.text)
    except: await m.answer("⏳ Serverda yuqori yuklama. Birozdan so'ng qayta urinib ko'ring.")

# --- RENDER KEEPALIVE ---
@app.route('/')
def home(): return "Bot is Online 🚀"
def run(): port = int(os.environ.get("PORT", 8080)); app.run(host='0.0.0.0', port=port)

async def main():
    init_db(); Thread(target=run).start(); bot = Bot(token="8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
