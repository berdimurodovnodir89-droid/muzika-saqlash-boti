import os
import json
import threading
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
)

# Render uchun HTTP port (Web Service talab qiladi)
from flask import Flask

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DB_FILE = "music_db.json"

# States
WAIT_AUDIO = 1
WAIT_CATEGORY = 2
WAIT_SEARCH_TEXT = 3


# ===================== DB =====================
def db_load():
    if not os.path.exists(DB_FILE):
        data = {"categories": {"dam_olishda": [], "kochada": []}}
        db_save(data)
        return data
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def db_save(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cat_name(key: str) -> str:
    return "😎 Dam olishda" if key == "dam_olishda" else "🚶 Ko‘chada"


# ===================== KEYBOARDS =====================
def main_menu_kb():
    # Knopkalar doim pastda turishi uchun har safar shu keyboardni yuboramiz
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📁 Categoriyalar")],
            [KeyboardButton("➕ Categoriyaga qo‘shish")],
            [KeyboardButton("🆘 Yordam")],
        ],
        resize_keyboard=True,
    )


def back_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("⬅️ Orqaga")]],
        resize_keyboard=True,
    )


def categories_inline(prefix: str):
    # prefix: OPEN / ADD
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("😎 Dam olishda", callback_data=f"{prefix}:dam_olishda"),
                InlineKeyboardButton("🚶 Ko‘chada", callback_data=f"{prefix}:kochada"),
            ],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="BACK:MAIN")],
        ]
    )


def category_actions_inline(cat_key: str):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📃 Jami qo‘shiqlar", callback_data=f"LIST:{cat_key}")],
            [InlineKeyboardButton("🔎 Qo‘shiqni qidirish", callback_data=f"SEARCH:{cat_key}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="BACK:CATS")],
        ]
    )


def songs_inline(cat_key: str, songs: list, page: int = 0, per_page: int = 10):
    start = page * per_page
    chunk = songs[start : start + per_page]

    rows = []
    for i, s in enumerate(chunk, start=start + 1):
        title = s.get("title", "Nomsiz")
        rows.append([InlineKeyboardButton(f"{i}. {title}", callback_data=f"SEND:{cat_key}:{i-1}")])

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"PAGE:{cat_key}:{page-1}"))
    if start + per_page < len(songs):
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"PAGE:{cat_key}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=f"OPEN:{cat_key}")])
    return InlineKeyboardMarkup(rows)


# ===================== TEXT HANDLERS =====================
def start(update: Update, context: CallbackContext):
    text = (
        "Assalomu alaykum! 🎵\n\n"
        "Bu bot qo‘shiqlarni 2 ta kategoriya bo‘yicha saqlaydi:\n"
        "😎 Dam olishda\n"
        "🚶 Ko‘chada\n\n"
        "➕ Categoriyaga qo‘shish — avval qo‘shiq yuborasiz, keyin kategoriya tanlaysiz.\n"
        "📁 Categoriyalar — kategoriyani tanlab, ro‘yxat yoki qidirish qilasiz.\n"
        "🆘 Yordam — to‘liq qo‘llanma.\n"
    )
    update.message.reply_text(text, reply_markup=main_menu_kb())


def help_cmd(update: Update, context: CallbackContext):
    text = (
        "🆘 Yordam / Qo‘llanma\n\n"
        "1) ➕ Categoriyaga qo‘shish\n"
        "   - Bot sizdan qo‘shiq (audio/music) yuborishni so‘raydi.\n"
        "   - Qo‘shiq yuborgandan keyin: “Qaysi kategoriyaga qo‘shamiz?” deb so‘raydi.\n"
        "   - Kategoriya tanlasangiz, qo‘shiq o‘sha kategoriya ichiga saqlanadi.\n\n"
        "2) 📁 Categoriyalar\n"
        "   - 2 ta kategoriya chiqadi: Dam olishda / Ko‘chada.\n"
        "   - Birini bossangiz 2 ta menyu chiqadi:\n"
        "     📃 Jami qo‘shiqlar — o‘sha kategoriyadagi hamma qo‘shiqlar ro‘yxati.\n"
        "     🔎 Qo‘shiqni qidirish — nom yozib qidirasiz (masalan: “Shoxrux”, “Sevgi”, “Remix”).\n\n"
        "3) ⬅️ Orqaga\n"
        "   - Har joyda ortga qaytish bor.\n"
    )
    update.message.reply_text(text, reply_markup=back_menu_kb())


def main_menu_router(update: Update, context: CallbackContext):
    txt = (update.message.text or "").strip()

    if txt == "📁 Categoriyalar":
        update.message.reply_text("Categoriyalar:", reply_markup=main_menu_kb())
        update.message.reply_text("Tanlang:", reply_markup=categories_inline("OPEN"))
        return ConversationHandler.END

    if txt == "➕ Categoriyaga qo‘shish":
        update.message.reply_text(
            "Menga qo‘shiq yuboring (Audio/Music). 🎶\n"
            "Masalan: telefoningizdan qo‘shiqni yuboring.",
            reply_markup=main_menu_kb()
        )
        return WAIT_AUDIO

    if txt == "🆘 Yordam":
        help_cmd(update, context)
        return ConversationHandler.END

    if txt == "⬅️ Orqaga":
        update.message.reply_text("Bosh menyu ✅", reply_markup=main_menu_kb())
        return ConversationHandler.END

    update.message.reply_text("Menyudan tanlang 🙂", reply_markup=main_menu_kb())
    return ConversationHandler.END


# ===================== ADD FLOW =====================
def receive_audio(update: Update, context: CallbackContext):
    audio = update.message.audio
    if audio is None:
        update.message.reply_text("Audio yuboring 🙂", reply_markup=main_menu_kb())
        return WAIT_AUDIO

    title = audio.title or audio.file_name or "Nomsiz qo‘shiq"
    context.user_data["pending_song"] = {
        "file_id": audio.file_id,
        "title": title,
        "performer": audio.performer or "",
        "duration": audio.duration or 0,
    }

    update.message.reply_text(
        "Qaysi kategoriyaga qo‘shamiz? 👇",
        reply_markup=main_menu_kb()
    )
    update.message.reply_text("Tanlang:", reply_markup=categories_inline("ADD"))
    return WAIT_CATEGORY


def add_choose_category_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()

    data = q.data  # ADD:dam_olishda yoki ADD:kochada
    _, cat_key = data.split(":", 1)

    song = context.user_data.get("pending_song")
    if not song:
        q.message.reply_text("Xatolik: qo‘shiq topilmadi. Qaytadan yuboring.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    db = db_load()
    db["categories"].setdefault(cat_key, [])
    db["categories"][cat_key].append(song)
    db_save(db)

    context.user_data.pop("pending_song", None)

    q.message.reply_text(
        f"✅ Saqlandi: “{song['title']}” -> {cat_name(cat_key)}",
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END


# ===================== BROWSE / SEARCH =====================
def open_category_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    _, cat_key = q.data.split(":", 1)

    q.message.reply_text(
        f"{cat_name(cat_key)} kategoriya menyusi:",
        reply_markup=category_actions_inline(cat_key)
    )


def list_songs_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    _, cat_key = q.data.split(":", 1)

    db = db_load()
    songs = db.get("categories", {}).get(cat_key, [])

    if not songs:
        q.message.reply_text("Bu kategoriyada hali qo‘shiq yo‘q 🙂", reply_markup=category_actions_inline(cat_key))
        return

    q.message.reply_text(
        f"📃 {cat_name(cat_key)} — jami: {len(songs)} ta\n"
        "Pastdan qo‘shiqni tanlang:",
        reply_markup=songs_inline(cat_key, songs, page=0)
    )


def page_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    _, cat_key, page_s = q.data.split(":")
    page = int(page_s)

    db = db_load()
    songs = db.get("categories", {}).get(cat_key, [])
    if not songs:
        q.message.reply_text("Bu kategoriyada hali qo‘shiq yo‘q 🙂")
        return

    q.message.reply_text(
        f"📃 {cat_name(cat_key)} — sahifa {page+1}",
        reply_markup=songs_inline(cat_key, songs, page=page)
    )


def send_song_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    _, cat_key, idx_s = q.data.split(":")
    idx = int(idx_s)

    db = db_load()
    songs = db.get("categories", {}).get(cat_key, [])

    if idx < 0 or idx >= len(songs):
        q.message.reply_text("Topilmadi 😕")
        return

    song = songs[idx]
    title = song.get("title", "Nomsiz")
    performer = song.get("performer", "")

    caption = f"🎵 {title}"
    if performer:
        caption += f"\n👤 {performer}"

    q.message.reply_audio(audio=song["file_id"], caption=caption)


def search_menu_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    _, cat_key = q.data.split(":", 1)

    context.user_data["search_cat"] = cat_key
    q.message.reply_text(
        "🔎 Qo‘shiq nomini yozing.\nMasalan: “Sevgi”, “Shoxrux”, “Remix”",
        reply_markup=main_menu_kb()
    )
    return WAIT_SEARCH_TEXT


def search_text_handler(update: Update, context: CallbackContext):
    text = (update.message.text or "").strip()
    cat_key = context.user_data.get("search_cat")

    if not cat_key:
        update.message.reply_text("Xatolik: kategoriya topilmadi. Qaytadan kirib ko‘ring.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    db = db_load()
    songs = db.get("categories", {}).get(cat_key, [])
    if not songs:
        update.message.reply_text("Bu kategoriyada qo‘shiq yo‘q 🙂", reply_markup=main_menu_kb())
        return ConversationHandler.END

    key = text.lower()
    found = []
    for s in songs:
        title = (s.get("title") or "").lower()
        performer = (s.get("performer") or "").lower()
        if key in title or key in performer:
            found.append(s)

    if not found:
        update.message.reply_text("Hech narsa topilmadi 😕", reply_markup=main_menu_kb())
        return ConversationHandler.END

    update.message.reply_text(
        f"✅ Topildi: {len(found)} ta\nPastdan tanlab yuborishingiz mumkin:",
        reply_markup=songs_inline(cat_key, found, page=0)
    )
    return ConversationHandler.END


# ===================== BACK CALLBACKS =====================
def back_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    data = q.data

    if data == "BACK:MAIN":
        q.message.reply_text("Bosh menyu ✅", reply_markup=main_menu_kb())
        return

    if data == "BACK:CATS":
        q.message.reply_text("Categoriyalar:", reply_markup=categories_inline("OPEN"))
        return


# ===================== RENDER WEB SERVER =====================
app = Flask(__name__)

@app.get("/")
def home():
    return "OK", 200


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)


# ===================== MAIN =====================
def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN topilmadi! Render -> Environment Variables ga BOT_TOKEN qo‘ying.")
        return

    # Render Web Service uchun PORT serverni alohida thread’da ishga tushiramiz
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.text & ~Filters.command, main_menu_router)],
        states={
            WAIT_AUDIO: [MessageHandler(Filters.audio, receive_audio)],
            WAIT_CATEGORY: [CallbackQueryHandler(add_choose_category_callback, pattern=r"^ADD:")],
            WAIT_SEARCH_TEXT: [MessageHandler(Filters.text & ~Filters.command, search_text_handler)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(Filters.regex(r"^⬅️ Orqaga$"), main_menu_router),
        ],
        allow_reentry=True,
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(conv)

    # Browse callbacks
    dp.add_handler(CallbackQueryHandler(open_category_callback, pattern=r"^OPEN:"))
    dp.add_handler(CallbackQueryHandler(list_songs_callback, pattern=r"^LIST:"))
    dp.add_handler(CallbackQueryHandler(search_menu_callback, pattern=r"^SEARCH:"))
    dp.add_handler(CallbackQueryHandler(page_callback, pattern=r"^PAGE:"))
    dp.add_handler(CallbackQueryHandler(send_song_callback, pattern=r"^SEND:"))
    dp.add_handler(CallbackQueryHandler(back_callback, pattern=r"^BACK:"))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
FROM python:3.11.8-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["python", "main.py"]