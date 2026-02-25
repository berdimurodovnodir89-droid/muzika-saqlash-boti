import os
from datetime import datetime

import psycopg2
from flask import Flask, request

from telegram import (
    Bot,
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # https://your-app.onrender.com
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PORT = int(os.getenv("PORT", "10000"))

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yo'q (Render Env ga BOT_TOKEN qo'ying).")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL yo'q (Render Postgres URL ni Env ga qo'ying).")

# ================= DB =================
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True

CAT_REST = "dam_olishda"
CAT_STREET = "kochada"

CAT_TITLE = {
    CAT_REST: "Dam olishda",
    CAT_STREET: "Ko‘chada",
}

# callback ids
CB_CAT_REST = "cat:dam"
CB_CAT_STREET = "cat:koch"
CB_MENU_ALL = "menu:all"
CB_MENU_SEARCH = "menu:search"
CB_BACK_CATS = "back:cats"

# user action states
ACT_NONE = "none"
ACT_PICK_CATEGORY_FOR_UPLOAD = "pick_category_for_upload"
ACT_PICK_CATEGORY_FOR_MENU = "pick_category_for_menu"
ACT_AWAIT_SEARCH_TEXT = "await_search_text"

def init_db():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                last_seen TIMESTAMP,
                seen_count INT DEFAULT 1
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                category TEXT NOT NULL,
                title TEXT,
                performer TEXT,
                file_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_id BIGINT PRIMARY KEY,
                action TEXT NOT NULL DEFAULT 'none',
                category TEXT,
                pending_file_id TEXT,
                pending_title TEXT,
                pending_performer TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

def upsert_user(update: Update):
    u = update.effective_user
    if not u:
        return
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (id, username, first_name, last_name, last_seen, seen_count)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON CONFLICT (id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen = EXCLUDED.last_seen,
                seen_count = users.seen_count + 1;
        """, (u.id, u.username, u.first_name, u.last_name, datetime.utcnow()))

def get_state(user_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT action, category, pending_file_id, pending_title, pending_performer FROM user_state WHERE user_id=%s", (user_id,))
        row = cur.fetchone()
    if not row:
        return (ACT_NONE, None, None, None, None)
    return row

def set_state(user_id: int, action: str, category=None, pending_file_id=None, pending_title=None, pending_performer=None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_state (user_id, action, category, pending_file_id, pending_title, pending_performer, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                action = EXCLUDED.action,
                category = EXCLUDED.category,
                pending_file_id = EXCLUDED.pending_file_id,
                pending_title = EXCLUDED.pending_title,
                pending_performer = EXCLUDED.pending_performer,
                updated_at = NOW();
        """, (user_id, action, category, pending_file_id, pending_title, pending_performer))

def clear_state(user_id: int):
    set_state(user_id, ACT_NONE, None, None, None, None)

def insert_song(user_id: int, category: str, file_id: str, title: str, performer: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO songs (user_id, category, title, performer, file_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, category, title, performer, file_id))

def count_songs(category: str):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM songs WHERE category=%s", (category,))
        return int(cur.fetchone()[0])

def list_songs(category: str, limit: int = 20):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, performer, file_id, created_at
            FROM songs
            WHERE category=%s
            ORDER BY created_at DESC
            LIMIT %s
        """, (category, limit))
        return cur.fetchall()

def search_songs(category: str, q: str, limit: int = 20):
    like = f"%{q}%"
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, performer, file_id, created_at
            FROM songs
            WHERE category=%s
              AND (COALESCE(title,'') ILIKE %s OR COALESCE(performer,'') ILIKE %s)
            ORDER BY created_at DESC
            LIMIT %s
        """, (category, like, like, limit))
        return cur.fetchall()

# ================= TELEGRAM CORE =================
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# ================= UI helpers =================
def kb_main():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("📂 Kategoriyalar")]],
        resize_keyboard=True
    )

def ikb_categories(for_what: str):
    # for_what: "upload" yoki "menu"
    # callback: cat:<id>|<for>
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏖 Dam olishda", callback_data=f"{CB_CAT_REST}|{for_what}"),
            InlineKeyboardButton("🚶‍♂️ Ko‘chada", callback_data=f"{CB_CAT_STREET}|{for_what}"),
        ]
    ])

def ikb_category_menu(category: str):
    title = CAT_TITLE.get(category, category)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Jami qo‘shiqlar", callback_data=f"{CB_MENU_ALL}|{category}")],
        [InlineKeyboardButton("🔎 Qo‘shiqni qidirish", callback_data=f"{CB_MENU_SEARCH}|{category}")],
        [InlineKeyboardButton("⬅️ Kategoriyalarga qaytish", callback_data=CB_BACK_CATS)],
    ])

# ================= COMMANDS =================
def start(update, context):
    upsert_user(update)
    txt = (
        "Assalom aleykum! 🎵\n\n"
        "Bu botda qo‘shiqlar 2 ta kategoriya bo‘yicha saqlanadi:\n"
        "🏖 Dam olishda\n"
        "🚶‍♂️ Ko‘chada\n\n"
        "Qo‘shiq qo‘shish uchun menga music/audio yuboring — keyin qaysi kategoriyaga saqlashni so‘rayman."
    )
    update.message.reply_text(txt, reply_markup=kb_main())

def categories_btn(update, context):
    upsert_user(update)
    update.message.reply_text(
        "Kategoriyani tanlang:",
        reply_markup=ikb_categories(for_what="menu")
    )

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.regex(r"^📂 Kategoriyalar$"), categories_btn))

# ================= AUDIO HANDLER =================
def handle_audio(update, context):
    upsert_user(update)
    u = update.effective_user
    msg = update.message

    audio = None
    title = None
    performer = None

    if msg.audio:
        audio = msg.audio
        title = audio.title
        performer = audio.performer
        file_id = audio.file_id
    elif msg.voice:
        # voice ham qabul qilamiz (xohlasa)
        audio = msg.voice
        file_id = audio.file_id
        title = "Voice"
        performer = None
    else:
        return

    set_state(
        u.id,
        ACT_PICK_CATEGORY_FOR_UPLOAD,
        category=None,
        pending_file_id=file_id,
        pending_title=title,
        pending_performer=performer,
    )

    update.message.reply_text(
        "Qaysi kategoriyaga qo‘shamiz? 👇",
        reply_markup=ikb_categories(for_what="upload")
    )

dispatcher.add_handler(MessageHandler(Filters.audio | Filters.voice, handle_audio))

# ================= CALLBACKS =================
def callback_router(update, context):
    upsert_user(update)
    q = update.callback_query
    data = q.data or ""
    q.answer()

    u = q.from_user
    user_id = u.id

    # Back
    if data == CB_BACK_CATS:
        q.message.reply_text("Kategoriyani tanlang:", reply_markup=ikb_categories(for_what="menu"))
        return

    # category pick
    if data.startswith("cat:"):
        parts = data.split("|")
        cat_part = parts[0]     # cat:dam / cat:koch
        for_what = parts[1] if len(parts) > 1 else "menu"

        category = CAT_REST if cat_part == CB_CAT_REST else CAT_STREET

        # upload flow
        if for_what == "upload":
            action, _, pending_file_id, pending_title, pending_performer = get_state(user_id)
            if action != ACT_PICK_CATEGORY_FOR_UPLOAD or not pending_file_id:
                q.message.reply_text("Qo‘shiq topilmadi. Qaytadan music yuboring 🙂", reply_markup=kb_main())
                clear_state(user_id)
                return

            insert_song(
                user_id=user_id,
                category=category,
                file_id=pending_file_id,
                title=pending_title,
                performer=pending_performer,
            )
            clear_state(user_id)

            total = count_songs(category)
            q.message.reply_text(
                f"✅ Saqlandi: {CAT_TITLE[category]}\n"
                f"Bu kategoriyada jami: {total} ta qo‘shiq bor.",
                reply_markup=kb_main()
            )
            return

        # menu flow
        if for_what == "menu":
            set_state(user_id, ACT_PICK_CATEGORY_FOR_MENU, category=category)
            q.message.reply_text(
                f"Kategoriya: {CAT_TITLE[category]}\nMenu tanlang:",
                reply_markup=ikb_category_menu(category)
            )
            return

    # menu actions
    if data.startswith("menu:"):
        parts = data.split("|")
        menu_part = parts[0]  # menu:all / menu:search
        category = parts[1] if len(parts) > 1 else None
        if category not in (CAT_REST, CAT_STREET):
            q.message.reply_text("Kategoriya topilmadi. Qaytadan tanlang.", reply_markup=ikb_categories(for_what="menu"))
            return

        if menu_part == CB_MENU_ALL:
            total = count_songs(category)
            rows = list_songs(category, limit=20)

            if total == 0:
                q.message.reply_text("Bu kategoriyada hozircha qo‘shiq yo‘q 🙂", reply_markup=kb_main())
                return

            q.message.reply_text(
                f"🎵 {CAT_TITLE[category]} — jami {total} ta.\n"
                f"Quyida oxirgi {len(rows)} tasi (top 20):"
            )

            for (_id, title, performer, file_id, created_at) in rows:
                cap = ""
                if title:
                    cap += f"{title}"
                if performer:
                    cap += f" — {performer}"
                if not cap:
                    cap = f"Song #{_id}"

                try:
                    bot.send_audio(chat_id=q.message.chat_id, audio=file_id, caption=cap)
                except Exception:
                    # voice bo‘lsa audio yuborish ishlamasligi mumkin, shunda oddiy message
                    bot.send_message(chat_id=q.message.chat_id, text=cap)

            q.message.reply_text("✅ Tayyor", reply_markup=kb_main())
            return

        if menu_part == CB_MENU_SEARCH:
            set_state(user_id, ACT_AWAIT_SEARCH_TEXT, category=category)
            q.message.reply_text(
                "Qidirish uchun nom yozing.\n"
                "Misol: Shazam yoki Konsta (artist ham bo‘ladi)"
            )
            return

dispatcher.add_handler(CallbackQueryHandler(callback_router))

# ================= TEXT SEARCH HANDLER =================
def handle_text(update, context):
    upsert_user(update)
    u = update.effective_user
    text = (update.message.text or "").strip()

    action, category, _, _, _ = get_state(u.id)
    if action != ACT_AWAIT_SEARCH_TEXT or category not in (CAT_REST, CAT_STREET):
        return  # oddiy text'larni echo qilmaymiz (botingni buzmaslik uchun)

    if not text:
        update.message.reply_text("Nom yozing 🙂")
        return

    rows = search_songs(category, text, limit=20)
    clear_state(u.id)

    if not rows:
        update.message.reply_text("Hech narsa topilmadi 😕", reply_markup=kb_main())
        return

    update.message.reply_text(
        f"🔎 Natijalar ({CAT_TITLE[category]}): {len(rows)} ta (top 20)"
    )
    for (_id, title, performer, file_id, created_at) in rows:
        cap = ""
        if title:
            cap += f"{title}"
        if performer:
            cap += f" — {performer}"
        if not cap:
            cap = f"Song #{_id}"

        try:
            bot.send_audio(chat_id=update.message.chat_id, audio=file_id, caption=cap)
        except Exception:
            bot.send_message(chat_id=update.message.chat_id, text=cap)

    update.message.reply_text("✅ Tayyor", reply_markup=kb_main())

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

# ================= FLASK WEBHOOK =================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK", 200

def set_webhook():
    if not WEBHOOK_URL:
        print("WEBHOOK_URL yo'q. Render Env ga WEBHOOK_URL qo'ying.")
        return
    url = WEBHOOK_URL.rstrip("/") + "/webhook"
    try:
        bot.set_webhook(url=url)
        print("Webhook set:", url)
    except Exception as e:
        print("Webhook set error:", e)

if __name__ == "__main__":
    init_db()
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)