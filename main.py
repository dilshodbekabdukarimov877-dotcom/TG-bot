import os, subprocess, sys, asyncio, io, sqlite3, logging, uuid, datetime
from threading import Thread
from PIL import Image
from flask import Flask

# --- KUTUBXONALAR ---
def install_packages():
    packages = ["aiogram", "google-generativeai", "Pillow", "flask"]
    for p in packages:
        try: subprocess.check_call([sys.executable, "-m", "pip", "install", p])
        except: pass

install_packages()

import google.generativeai as genai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

# --- SOZLAMALAR ---
TOKEN = "8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak"
GEMINI_KEY = "AIzaSyAO2vkYx9l7nCUp0yS8CbO9Hko7fv5rRQ4" 
ADMIN_ID = 7806849831

genai.configure(api_key="AIzaSyAO2vkYx9l7nCUp0yS8CbO9Hko7fv5rRQ4")
# QIDIRUVSIZ, LEKIN 2.5 FLASH MODELI BILAN
model = genai.GenerativeModel(model_name='gemini-2.5-flash')

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
app = Flask('')

# --- MA'LUMOTLAR BAZASI ---
DB_NAME = 'bot_universe.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE IF NOT EXISTS history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS reminders (user_id INTEGER, time TEXT, task TEXT)')
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

# --- ASOSIY BUYRUQLAR ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    add_user(m.from_user.id)
    welcome_text = (
        f"👋 **Assalomu alaykum, {m.from_user.full_name}!**\n\n"
        "🤖 Men eng kuchli **AI Telegram botman.**\n\n"
        "🚀 Men nimalar qila olaman? Bilish uchun **/help** bosing!"
    )
    await m.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("help"))
async def cmd_help(m: types.Message):
    help_text = (
        "🤖 **Bot imkoniyatlari:**\n\n"
        "💬 **Matn:** Savol bering, AI javob beradi.\n"
        "🖼 **Media:** Rasm, Video va PDF fayllarni tahlil qilaman.\n"
        "🎙 **Ovoz:** Ovozli xabarlarni tushunaman.\n"
        "⏰ **Eslatkich:** `/remind 5 vazifa` - belgilangan vaqtda eslataman.\n"
        "🧹 **Tozalash:** `/clear` - suhbat tarixini o'chiradi.\n\n"
        "👨‍💻 **Admin:** Statitika va Reklama funksiyalari."
    )
    await m.answer(help_text, parse_mode="Markdown")

@dp.message(Command("clear"))
async def cmd_clear(m: types.Message):
    conn = sqlite3.connect(DB_NAME); conn.execute('DELETE FROM history WHERE user_id = ?', (m.from_user.id,)); conn.commit(); conn.close()
    await m.answer("🧹 Suhbat tarixi tozalandi.")

# --- ADMIN PANEL ---

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
    success, fail = 0, 0
    for u in users:
        try: await bot.send_message(u[0], text); success += 1; await asyncio.sleep(0.05)
        except: fail += 1
    await m.answer(f"📢 Natija:\n✅ Yuborildi: {success}\n❌ Yuborilmadi: {fail}")

# --- ESLATKICHLAR (REMINDERS) ---

@dp.message(Command("remind"))
async def cmd_remind(m: types.Message, command: CommandObject):
    if not command.args: return await m.answer("Masalan: `/remind 5 dars`")
    try:
        minutes, task = command.args.split(" ", 1)
        r_time = datetime.datetime.now() + datetime.timedelta(minutes=int(minutes))
        conn = sqlite3.connect(DB_NAME); conn.execute('INSERT INTO reminders VALUES (?, ?, ?)', (m.from_user.id, r_time.isoformat(), task)); conn.commit(); conn.close()
        await m.answer(f"✅ Saqlandi! {minutes} minutdan keyin eslataman.")
    except: await m.answer("❌ Xato format. `/remind 10 vazifa` deb yozing.")

async def check_reminders(bot: Bot):
    while True:
        now = datetime.datetime.now().isoformat()
        conn = sqlite3.connect(DB_NAME); tasks = conn.execute('SELECT rowid, user_id, task FROM reminders WHERE time <= ?', (now,)).fetchall()
        for r_id, u_id, tsk in tasks:
            try: await bot.send_message(u_id, f"🔔 **ESLATMA:** {tsk}")
            except: pass
            conn.execute('DELETE FROM reminders WHERE rowid = ?', (r_id,))
        conn.commit(); conn.close(); await asyncio.sleep(20)

# --- MEDIA TAHLIL (Image, Video, PDF, Voice) ---

@dp.message(F.voice)
async def handle_voice(m: types.Message, bot: Bot):
    wait = await m.answer("🎙 Eshityapman...")
    try:
        f = await bot.get_file(m.voice.file_id); d = await bot.download_file(f.file_path)
        resp = model.generate_content(["Ovozli xabarni tahlil qil va javob ber:", {"mime_type": "audio/ogg", "data": d.read()}])
        await wait.edit_text(resp.text)
    except: await wait.edit_text("🎙 Ovozni tahlil qilishda xatolik.")

@dp.message(F.document | F.video | F.photo)
async def handle_media(m: types.Message, bot: Bot):
    wait = await m.answer("🔍 Faylni tahlil qilyapman...")
    try:
        if m.document:
            f_id = m.document.file_id; mime = m.document.mime_type
        elif m.video:
            f_id = m.video.file_id; mime = "video/mp4"
        else:
            f_id = m.photo[-1].file_id; mime = "image/jpeg"
            
        f_p = await bot.get_file(f_id); f_d = await bot.download_file(f_p.file_path)
        resp = model.generate_content([m.caption or "Ushbu faylni tahlil qil:", {"mime_type": mime, "data": f_d.read()}])
        await wait.edit_text(resp.text)
    except Exception as e:
        await wait.edit_text(f"❌ Fayl tahlilida xatolik: {str(e)}")

# --- INLINE VA MATN ---

@dp.inline_query()
async def inline_handler(q: types.InlineQuery):
    if not q.query: return
    try:
        res = model.generate_content(q.query)
        results = [InlineQueryResultArticle(id=str(uuid.uuid4()), title="Gemini AI", input_message_content=InputTextMessageContent(message_text=res.text))]
        await q.answer(results, cache_time=5)
    except: pass

@dp.message(F.text)
async def handle_text(m: types.Message):
    if m.text.startswith("/"): return
    add_user(m.from_user.id)
    h = get_chat(m.from_user.id)
    try:
        chat = model.start_chat(history=h)
        resp = chat.send_message(m.text)
        save_chat(m.from_user.id, "user", m.text)
        save_chat(m.from_user.id, "model", resp.text)
        await m.answer(resp.text)
    except Exception as e:
        await m.answer("⏳ Serverda yuklama yuqori. Birozdan so'ng urinib ko'ring.")

# --- RENDER KEEPALIVE ---
@app.route('/')
def home(): return "Bot is Running"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

async def main():
    init_db(); Thread(target=run).start(); bot = Bot(token="8376336640:AAGJzxZ2fvN-71gsucdGACqqlhBVv2lFrak")
    asyncio.create_task(check_reminders(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
