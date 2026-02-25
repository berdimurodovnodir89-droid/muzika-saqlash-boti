import os
import logging
from dotenv import load_dotenv
from aiohttp import web

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------------ ENV ------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()  # https://xxxx.onrender.com
PORT = int(os.getenv("PORT", "10000"))  # Render shu PORT ni beradi

# Webhook path (Telegram shu yo'lga POST qiladi)
WEBHOOK_PATH = "webhook"  # URL: https://xxxx.onrender.com/webhook

logging.basicConfig(level=logging.INFO)


def check_env():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yo'q. Render -> Environment ga BOT_TOKEN qo'shing.")
    if not WEBHOOK_BASE:
        raise RuntimeError("WEBHOOK_BASE yo'q. Masalan: https://your-app.onrender.com")
    # / bilan tugasa olib tashlaymiz (xatoni oldini oladi)
    while WEBHOOK_BASE.endswith("/"):
        WEBHOOK_BASE = WEBHOOK_BASE[:-1]


# ------------------ BOT DATA ------------------
CATEGORIES = {
    "dam": "🏖 Dam olishda",
    "koch": "🚶 Ko‘chada",
}

# user_id -> {"dam":[song], "koch":[song]}
# song = {"file_id": "...", "title": "...", "type": "audio|document"}
USER_SONGS = {}


def get_user_store(user_id: int):
    if user_id not in USER_SONGS:
        USER_SONGS[user_id] = {"dam": [], "koch": []}
    return USER_SONGS[user_id]


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("📂 Kategoriyalar")]],
        resize_keyboard=True,
    )


def categories_inline_kb(prefix: str):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(CATEGORIES["dam"], callback_data=f"{prefix}:dam")],
            [InlineKeyboardButton(CATEGORIES["koch"], callback_data=f"{prefix}:koch")],
        ]
    )


def category_actions_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🎵 Jami qo‘shiqlar"), KeyboardButton("🔎 Qo‘shiqni qidirish")],
            [KeyboardButton("⬅️ Orqaga")],
        ],
        resize_keyboard=True,
    )


def extract_song_info(msg):
    if msg.audio:
        title = msg.audio.title or msg.audio.file_name or "audio"
        return {"type": "audio", "file_id": msg.audio.file_id, "title": title}

    if msg.document:
        title = msg.document.file_name or "document"
        return {"type": "document", "file_id": msg.document.file_id, "title": title}

    return None


# ------------------ HANDLERS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! 🎧\n\n"
        "Bu bot 2 ta kategoriyaga qo‘shiqlarni saqlaydi:\n"
        f"1) {CATEGORIES['dam']}\n"
        f"2) {CATEGORIES['koch']}\n\n"
        "➕ Qo‘shish uchun menga *musiqa (audio/mp3)* yuboring.\n"
        "Keyin sizdan qaysi kategoriyaga qo‘shishni so‘rayman.\n\n"
        "📂 Kategoriyalarni ko‘rish uchun pastdagi tugmani bosing.",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Yordam:\n"
        "1) Audio yoki mp3 (document) yuboring — saqlab beraman.\n"
        "2) 📂 Kategoriyalar — ichidan tanlab ko‘rasiz.\n"
        "3) 🔎 Qidirish — nom bo‘yicha topadi."
    )


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "📂 Kategoriyalar":
        await update.message.reply_text(
            "Qaysi kategoriyani ochamiz?",
            reply_markup=categories_inline_kb(prefix="view"),
        )
        return

    if text == "🎵 Jami qo‘shiqlar":
        uid = update.effective_user.id
        active_cat = context.user_data.get("active_category")
        if not active_cat:
            await update.message.reply_text("Avval kategoriya tanlang: 📂 Kategoriyalar")
            return

        songs = get_user_store(uid).get(active_cat, [])
        if not songs:
            await update.message.reply_text("Bu kategoriyada hozircha qo‘shiq yo‘q.")
            return

        await update.message.reply_text(f"{CATEGORIES[active_cat]} — jami qo‘shiqlar: {len(songs)} ta")

        for i, s in enumerate(songs, start=1):
            caption = f"{i}) {s['title']}"
            if s["type"] == "audio":
                await update.message.reply_audio(s["file_id"], caption=caption)
            else:
                await update.message.reply_document(s["file_id"], caption=caption)
        return

    if text == "🔎 Qo‘shiqni qidirish":
        active_cat = context.user_data.get("active_category")
        if not active_cat:
            await update.message.reply_text("Avval kategoriya tanlang: 📂 Kategoriyalar")
            return

        context.user_data["awaiting_search"] = True
        await update.message.reply_text(
            "Qo‘shiq nomini yozing.\nMasalan: *love* yoki *shoxrux* yoki *track.mp3*",
            parse_mode="Markdown",
        )
        return

    if text == "⬅️ Orqaga":
        context.user_data.pop("active_category", None)
        context.user_data.pop("awaiting_search", None)
        await update.message.reply_text("Bosh menu.", reply_markup=main_menu_kb())
        return


async def handle_audio_or_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    song = extract_song_info(msg)
    if not song:
        await msg.reply_text("Audio yoki mp3 yuboring 🙂")
        return

    context.user_data["pending_song"] = song

    await msg.reply_text(
        "Qo‘shiq qabul qilindi ✅\nQaysi kategoriyaga qo‘shamiz?",
        reply_markup=categories_inline_kb(prefix="add"),
    )


async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_search"):
        return

    query = (update.message.text or "").strip().lower()
    context.user_data["awaiting_search"] = False

    uid = update.effective_user.id
    active_cat = context.user_data.get("active_category")
    if not active_cat:
        await update.message.reply_text("Avval kategoriya tanlang: 📂 Kategoriyalar")
        return

    songs = get_user_store(uid).get(active_cat, [])
    if not songs:
        await update.message.reply_text("Bu kategoriyada qo‘shiq yo‘q.")
        return

    matches = [s for s in songs if query in (s["title"] or "").lower()]
    if not matches:
        await update.message.reply_text("Hech narsa topilmadi. Yana urinib ko‘ring: 🔎 Qo‘shiqni qidirish")
        return

    await update.message.reply_text(f"Topildi: {len(matches)} ta")
    for i, s in enumerate(matches, start=1):
        caption = f"{i}) {s['title']}"
        if s["type"] == "audio":
            await update.message.reply_audio(s["file_id"], caption=caption)
        else:
            await update.message.reply_document(s["file_id"], caption=caption)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data.startswith("view:"):
        cat_key = data.split(":", 1)[1]
        if cat_key not in CATEGORIES:
            await q.edit_message_text("Noto‘g‘ri kategoriya.")
            return

        context.user_data["active_category"] = cat_key
        context.user_data["awaiting_search"] = False

        await q.message.reply_text(
            f"{CATEGORIES[cat_key]} ochildi.\nQuyidagilardan birini tanlang:",
            reply_markup=category_actions_kb(),
        )
        return

    if data.startswith("add:"):
        cat_key = data.split(":", 1)[1]
        if cat_key not in CATEGORIES:
            await q.edit_message_text("Noto‘g‘ri kategoriya.")
            return

        pending = context.user_data.get("pending_song")
        if not pending:
            await q.message.reply_text("Avval qo‘shiq yuboring.")
            return

        uid = update.effective_user.id
        get_user_store(uid)[cat_key].append(pending)
        context.user_data.pop("pending_song", None)

        await q.message.reply_text(
            f"✅ Saqlandi: *{pending['title']}*\nKategoriya: {CATEGORIES[cat_key]}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )


# ------------------ HEALTH APP (PING) ------------------
def build_health_app():
    aio = web.Application()

    async def ok(request):
        return web.Response(text="OK")

    aio.router.add_get("/", ok)
    aio.router.add_get("/healthz", ok)
    return aio


# ------------------ MAIN ------------------
def main():
    global WEBHOOK_BASE
    check_env()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, handle_audio_or_doc))

    # Search avval ishlasin
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text), group=0)
    # Keyin menu textlar
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu), group=1)

    app.add_handler(CallbackQueryHandler(on_callback))

    health_app = build_health_app()

    # ✅ PORT binding + Webhook
    # Telegram webhook URL: https://xxxx.onrender.com/webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{WEBHOOK_BASE}/{WEBHOOK_PATH}",
        web_app=health_app,
    )


if __name__ == "__main__":
    main()