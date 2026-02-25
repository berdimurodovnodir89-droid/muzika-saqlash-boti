import os
import json
from datetime import datetime

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

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # masalan: https://your-app.onrender.com
PORT = int(os.getenv("PORT", "10000"))

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # "12345,67890"
ADMIN_IDS = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yo'q. Render Env ga BOT_TOKEN qo'ying.")

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# =========================
# FILE STORAGE
# =========================
USERS_FILE = "users.json"
SONGS_FILE = "songs.json"
STATE_FILE = "state.json"

CAT_REST = "dam_olishda"
CAT_STREET = "kochada"
CAT_TITLE = {CAT_REST: "Dam olishda", CAT_STREET: "Ko‘chada"}

# user states
ACT_NONE = "none"
ACT_PICK_CATEGORY_FOR_UPLOAD = "pick_cat_for_upload"
ACT_PICK_CATEGORY_FOR_MENU = "pick_cat_for_menu"
ACT_AWAIT_SEARCH_TEXT = "await_search_text"
ACT_AWAIT_BROADCAST_TEXT = "await_broadcast_text"

# callbacks
CB_CAT_REST = "cat:dam"
CB_CAT_STREET = "cat:koch"
CB_BACK_CATS = "back:cats"
CB_MENU_ALL = "menu:all"
CB_MENU_SEARCH = "menu:search"

# admin callbacks
CB_ADM_STATS = "adm:stats"
CB_ADM_USERS = "adm:users"
CB_ADM_BCAST = "adm:bcast"
CB_ADM_CANCEL = "adm:cancel"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_users():
    return load_json(USERS_FILE, {})

def save_users(users):
    save_json(USERS_FILE, users)

def get_songs():
    # format: { "dam_olishda": [song, ...], "kochada": [song, ...] }
    return load_json(SONGS_FILE, {CAT_REST: [], CAT_STREET: []})

def save_songs(songs):
    # ensure keys exist
    if CAT_REST not in songs:
        songs[CAT_REST] = []
    if CAT_STREET not in songs:
        songs[CAT_STREET] = []
    save_json(SONGS_FILE, songs)

def get_state_all():
    # format: { "<user_id>": {action, category, pending_song, updated_at} }
    return load_json(STATE_FILE, {})

def save_state_all(state):
    save_json(STATE_FILE, state)

def get_state(uid: int):
    st = get_state_all()
    return st.get(str(uid), {"action": ACT_NONE})

def set_state(uid: int, action: str, category=None, pending_song=None):
    st = get_state_all()
    st[str(uid)] = {
        "action": action,
        "category": category,
        "pending_song": pending_song,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    save_state_all(st)

def clear_state(uid: int):
    set_state(uid, ACT_NONE, None, None)

def track_user(update: Update):
    u = update.effective_user
    if not u:
        return
    users = get_users()
    users[str(u.id)] = {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "last_seen": datetime.utcnow().isoformat() + "Z",
        "seen_count": int(users.get(str(u.id), {}).get("seen_count", 0)) + 1,
    }
    save_users(users)

# =========================
# TELEGRAM CORE
# =========================
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# =========================
# UI
# =========================
def kb_main(uid: int):
    rows = [[KeyboardButton("📂 Kategoriyalar")]]
    if is_admin(uid):
        rows.append([KeyboardButton("🛠 Admin panel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def ikb_categories(for_what: str):
    # for_what: "upload" yoki "menu"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏖 Dam olishda", callback_data=f"{CB_CAT_REST}|{for_what}"),
            InlineKeyboardButton("🚶‍♂️ Ko‘chada", callback_data=f"{CB_CAT_STREET}|{for_what}"),
        ]
    ])

def ikb_category_menu(category: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Jami qo‘shiqlar", callback_data=f"{CB_MENU_ALL}|{category}")],
        [InlineKeyboardButton("🔎 Qo‘shiqni qidirish", callback_data=f"{CB_MENU_SEARCH}|{category}")],
        [InlineKeyboardButton("⬅️ Kategoriyalarga qaytish", callback_data=CB_BACK_CATS)],
    ])

def ikb_admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data=CB_ADM_STATS)],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data=CB_ADM_USERS)],
        [InlineKeyboardButton("📢 Broadcast", callback_data=CB_ADM_BCAST)],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=CB_ADM_CANCEL)],
    ])

# =========================
# COMMANDS
# =========================
def start(update, context):
    track_user(update)
    uid = update.effective_user.id
    update.message.reply_text(
        "Assalom aleykum! 🎵\n\n"
        "Kategoriyalar:\n"
        "🏖 Dam olishda\n"
        "🚶‍♂️ Ko‘chada\n\n"
        "Qo‘shiq qo‘shish uchun menga music/audio yuboring.\n"
        "Keyin qaysi kategoriyaga saqlashni so‘rayman ✅",
        reply_markup=kb_main(uid)
    )

def categories_btn(update, context):
    track_user(update)
    uid = update.effective_user.id
    update.message.reply_text("Kategoriyani tanlang:", reply_markup=ikb_categories(for_what="menu"))
    update.message.reply_text("Menu:", reply_markup=kb_main(uid))

def admin_btn(update, context):
    track_user(update)
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    clear_state(uid)
    update.message.reply_text("🛠 Admin panel:", reply_markup=ikb_admin_panel())

def admin_cmd(update, context):
    track_user(update)
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    clear_state(uid)
    update.message.reply_text("🛠 Admin panel:", reply_markup=ikb_admin_panel())

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("admin", admin_cmd))
dispatcher.add_handler(MessageHandler(Filters.regex(r"^📂 Kategoriyalar$"), categories_btn))
dispatcher.add_handler(MessageHandler(Filters.regex(r"^🛠 Admin panel$"), admin_btn))

# =========================
# AUDIO HANDLER (save flow)
# =========================
def handle_audio(update, context):
    track_user(update)
    uid = update.effective_user.id
    msg = update.message

    # accept audio or voice
    file_id = None
    title = None
    performer = None

    if msg.audio:
        a = msg.audio
        file_id = a.file_id
        title = a.title
        performer = a.performer
    elif msg.voice:
        v = msg.voice
        file_id = v.file_id
        title = "Voice"
        performer = None
    else:
        return

    pending_song = {
        "file_id": file_id,
        "title": title,
        "performer": performer,
        "added_by": uid,
        "added_at": datetime.utcnow().isoformat() + "Z",
    }

    set_state(uid, ACT_PICK_CATEGORY_FOR_UPLOAD, category=None, pending_song=pending_song)

    update.message.reply_text(
        "Qaysi kategoriyaga qo‘shamiz? 👇",
        reply_markup=ikb_categories(for_what="upload")
    )

dispatcher.add_handler(MessageHandler(Filters.audio | Filters.voice, handle_audio))

# =========================
# CALLBACK ROUTER
# =========================
def callback_router(update, context):
    track_user(update)
    q = update.callback_query
    data = (q.data or "").strip()
    q.answer()

    uid = q.from_user.id

    # ---- ADMIN CALLBACKS ----
    if data in (CB_ADM_STATS, CB_ADM_USERS, CB_ADM_BCAST, CB_ADM_CANCEL):
        if not is_admin(uid):
            q.answer("Ruxsat yo'q", show_alert=True)
            return

        if data == CB_ADM_CANCEL:
            clear_state(uid)
            q.message.reply_text("Bekor qilindi ✅", reply_markup=kb_main(uid))
            return

        if data == CB_ADM_STATS:
            users = get_users()
            songs = get_songs()
            total_users = len(users)
            total_songs = len(songs.get(CAT_REST, [])) + len(songs.get(CAT_STREET, []))
            q.message.reply_text(
                "📊 Statistika:\n"
                f"👥 Users: {total_users}\n"
                f"🎵 Qo‘shiqlar: {total_songs}\n\n"
                f"🏖 Dam olishda: {len(songs.get(CAT_REST, []))}\n"
                f"🚶‍♂️ Ko‘chada: {len(songs.get(CAT_STREET, []))}",
                reply_markup=kb_main(uid)
            )
            return

        if data == CB_ADM_USERS:
            users = list(get_users().values())
            users.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
            users = users[:20]
            if not users:
                q.message.reply_text("Userlar yo‘q.", reply_markup=kb_main(uid))
                return

            lines = ["👥 Oxirgi 20 ta foydalanuvchi:"]
            for u in users:
                name = ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip() or "NoName"
                username = u.get("username")
                tag = f"@{username}" if username else f"id:{u.get('id')}"
                lines.append(f"- {name} ({tag}) | seen:{u.get('seen_count', 0)} | last:{u.get('last_seen','')}")
            text = "\n".join(lines)
            if len(text) > 3900:
                text = text[:3900] + "\n... (qisqartirildi)"
            q.message.reply_text(text, reply_markup=kb_main(uid))
            return

        if data == CB_ADM_BCAST:
            set_state(uid, ACT_AWAIT_BROADCAST_TEXT, category=None, pending_song=None)
            q.message.reply_text(
                "📢 Broadcast matnini yozing.\n"
                "Misol: Bugun yangi qo‘shiqlar qo‘shildi!\n\n"
                "Bekor qilish: Admin panel → ❌ Bekor qilish"
            )
            return

    # ---- BACK TO CATEGORIES ----
    if data == CB_BACK_CATS:
        q.message.reply_text("Kategoriyani tanlang:", reply_markup=ikb_categories(for_what="menu"))
        return

    # ---- CATEGORY PICK ----
    if data.startswith("cat:"):
        parts = data.split("|")
        cat_part = parts[0]       # cat:dam / cat:koch
        for_what = parts[1] if len(parts) > 1 else "menu"

        category = CAT_REST if cat_part == CB_CAT_REST else CAT_STREET

        if for_what == "upload":
            st = get_state(uid)
            if st.get("action") != ACT_PICK_CATEGORY_FOR_UPLOAD:
                q.message.reply_text("Holat topilmadi. Qaytadan qo‘shiq yuboring 🙂", reply_markup=kb_main(uid))
                clear_state(uid)
                return

            pending = st.get("pending_song")
            if not pending or not pending.get("file_id"):
                q.message.reply_text("Qo‘shiq topilmadi. Qaytadan yuboring 🙂", reply_markup=kb_main(uid))
                clear_state(uid)
                return

            songs = get_songs()
            songs.setdefault(CAT_REST, [])
            songs.setdefault(CAT_STREET, [])
            songs[category].append(pending)
            save_songs(songs)

            clear_state(uid)

            q.message.reply_text(
                f"✅ Saqlandi: {CAT_TITLE[category]}\n"
                f"Bu kategoriyada jami: {len(songs[category])} ta qo‘shiq bor.",
                reply_markup=kb_main(uid)
            )
            return

        if for_what == "menu":
            set_state(uid, ACT_PICK_CATEGORY_FOR_MENU, category=category, pending_song=None)
            q.message.reply_text(
                f"Kategoriya: {CAT_TITLE[category]}\nMenu tanlang:",
                reply_markup=ikb_category_menu(category)
            )
            return

    # ---- MENU ACTIONS ----
    if data.startswith("menu:"):
        parts = data.split("|")
        menu_part = parts[0]  # menu:all / menu:search
        category = parts[1] if len(parts) > 1 else None

        if category not in (CAT_REST, CAT_STREET):
            q.message.reply_text("Kategoriya topilmadi. Qaytadan tanlang.", reply_markup=ikb_categories(for_what="menu"))
            return

        if menu_part == CB_MENU_ALL:
            songs = get_songs()
            cat_songs = songs.get(category, [])
            total = len(cat_songs)

            if total == 0:
                q.message.reply_text("Bu kategoriyada hozircha qo‘shiq yo‘q 🙂", reply_markup=kb_main(uid))
                return

            # show last 20
            last = cat_songs[-20:][::-1]

            q.message.reply_text(
                f"🎵 {CAT_TITLE[category]} — jami {total} ta.\n"
                f"Quyida oxirgi {len(last)} tasi (top 20):"
            )

            for s in last:
                cap = ""
                if s.get("title"):
                    cap += str(s.get("title"))
                if s.get("performer"):
                    cap += f" — {s.get('performer')}"
                if not cap:
                    cap = "Qo‘shiq"

                try:
                    bot.send_audio(chat_id=q.message.chat_id, audio=s["file_id"], caption=cap)
                except Exception:
                    bot.send_message(chat_id=q.message.chat_id, text=cap)

            q.message.reply_text("✅ Tayyor", reply_markup=kb_main(uid))
            return

        if menu_part == CB_MENU_SEARCH:
            set_state(uid, ACT_AWAIT_SEARCH_TEXT, category=category, pending_song=None)
            q.message.reply_text(
                "Qidirish uchun nom yozing.\n"
                "Misol: Shazam yoki Konsta (artist ham bo‘ladi)"
            )
            return

dispatcher.add_handler(CallbackQueryHandler(callback_router))

# =========================
# TEXT HANDLER (search + broadcast)
# =========================
def handle_text(update, context):
    track_user(update)
    uid = update.effective_user.id
    text = (update.message.text or "").strip()

    st = get_state(uid)
    action = st.get("action", ACT_NONE)
    category = st.get("category")

    # --- admin broadcast ---
    if action == ACT_AWAIT_BROADCAST_TEXT and is_admin(uid):
        if not text:
            update.message.reply_text("Matn yozing 🙂")
            return

        clear_state(uid)
        users = get_users()
        ids = [int(v["id"]) for v in users.values() if "id" in v]

        sent = 0
        fail = 0
        for chat_id in ids:
            try:
                bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except Exception:
                fail += 1

        update.message.reply_text(
            f"📢 Broadcast yakunlandi ✅\nYuborildi: {sent}\nXato: {fail}",
            reply_markup=kb_main(uid)
        )
        return

    # --- search ---
    if action == ACT_AWAIT_SEARCH_TEXT and category in (CAT_REST, CAT_STREET):
        if not text:
            update.message.reply_text("Nom yozing 🙂")
            return

        songs = get_songs()
        cat_songs = songs.get(category, [])

        q = text.lower()
        results = []
        for s in cat_songs[::-1]:
            title = (s.get("title") or "").lower()
            perf = (s.get("performer") or "").lower()
            if q in title or q in perf:
                results.append(s)
            if len(results) >= 20:
                break

        clear_state(uid)

        if not results:
            update.message.reply_text("Hech narsa topilmadi 😕", reply_markup=kb_main(uid))
            return

        update.message.reply_text(f"🔎 Natijalar ({CAT_TITLE[category]}): {len(results)} ta (top 20)")
        for s in results:
            cap = ""
            if s.get("title"):
                cap += str(s.get("title"))
            if s.get("performer"):
                cap += f" — {s.get('performer')}"
            if not cap:
                cap = "Qo‘shiq"

            try:
                bot.send_audio(chat_id=update.message.chat_id, audio=s["file_id"], caption=cap)
            except Exception:
                bot.send_message(chat_id=update.message.chat_id, text=cap)

        update.message.reply_text("✅ Tayyor", reply_markup=kb_main(uid))
        return

    # boshqa textlarni e'tiborsiz

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

# =========================
# FLASK WEBHOOK
# =========================
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
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)