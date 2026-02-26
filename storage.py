import os
import logging
import asyncio
from dotenv import load_dotenv
from aiohttp import web

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from storage import make_storage

# ------------------ ENV ------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()  # https://xxxx.onrender.com
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_PATH = "webhook"  # /webhook

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("musicbot")

CATEGORIES = {"dam": "🏖 Dam olishda", "koch": "🚶 Ko‘chada"}

def check_env():
    global WEBHOOK_BASE
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yo'q (Render -> Environment).")
    if not WEBHOOK_BASE:
        raise RuntimeError("WEBHOOK_BASE yo'q. Masalan: https://your-app.onrender.com")
    WEBHOOK_BASE = WEBHOOK_BASE.rstrip("/")

def main_menu_kb():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📂 Kategoriyalar")], [KeyboardButton("ℹ️ Yordam")]],
        resize_keyboard=True
    )

def categories_inline_kb(prefix: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(CATEGORIES["dam"], callback_data=f"{prefix}:dam")],
        [InlineKeyboardButton(CATEGORIES["koch"], callback_data=f"{prefix}:koch")],
    ])

def category_actions_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎵 Jami qo‘shiqlar"), KeyboardButton("🔎 Qo‘shiqni qidirish")],
            [KeyboardButton("⬅️ Orqaga")]
        ],
        resize_keyboard=True
    )

def extract_song_info(msg):
    if msg.audio:
        title = msg.audio.title or msg.audio.performer or msg.audio.file_name or "audio"
        return {"type": "audio", "file_id": msg.audio.file_id, "title": title}

    if msg.document:
        name = (msg.document.file_name or "").lower()
        mime = (msg.document.mime_type or "").lower()
        is_audio = mime.startswith("audio/") or name.endswith((".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"))
        if not is_audio:
            return None
        return {"type": "document", "file_id": msg.document.file_id, "title": msg.document.file_name or "mp3"}

    return None

STORE = None

# ------------------ BOT HANDLERS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Assalomu alaykum! 🎧\n\n"
        f"• {CATEGORIES['dam']}\n• {CATEGORIES['koch']}\n\n"
        "Audio/mp3 yuboring — saqlayman. Keyin kategoriya tanlaysiz.\n"
        "📂 Kategoriyalar tugmasini bosing.",
        reply_markup=main_menu_kb(),
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "1) Audio/mp3 yuboring\n"
        "2) 📂 Kategoriyalar\n"
        "3) 🎵 Jami qo‘shiqlar\n"
        "4) 🔎 Qidirish\n\n"
        "Ping uchun: /healthz (OK)"
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = (update.message.text or "").strip()

    if t == "ℹ️ Yordam":
        await help_cmd(update, context)
        return

    if t == "📂 Kategoriyalar":
        await update.message.reply_text("Kategoriyani tanlang:", reply_markup=categories_inline_kb("view"))
        return

    if t == "⬅️ Orqaga":
        context.user_data.pop("active_category", None)
        context.user_data.pop("awaiting_search", None)
        await update.message.reply_text("Bosh menu.", reply_markup=main_menu_kb())
        return

    if t == "🎵 Jami qo‘shiqlar":
        cat = context.user_data.get("active_category")
        if not cat:
            await update.message.reply_text("Avval 📂 Kategoriyalar")
            return

        rows = STORE.list_songs(update.effective_user.id, cat)
        if not rows:
            await update.message.reply_text("Bu kategoriyada qo‘shiq yo‘q.")
            return

        await update.message.reply_text(f"{CATEGORIES[cat]} — {len(rows)} ta")

        for i, (file_id, title, ftype) in enumerate(rows[:30], start=1):
            cap = f"{i}) {title}"
            try:
                if ftype == "audio":
                    await update.message.reply_audio(file_id, caption=cap)
                else:
                    await update.message.reply_document(file_id, caption=cap)
            except Exception:
                await update.message.reply_text(f"⚠️ Yuborilmadi: {title}")

        if len(rows) > 30:
            await update.message.reply_text("⚠️ Juda ko‘p: 30 tasi ko‘rsatildi.")
        return

    if t == "🔎 Qo‘shiqni qidirish":
        cat = context.user_data.get("active_category")
        if not cat:
            await update.message.reply_text("Avval 📂 Kategoriyalar")
            return
        context.user_data["awaiting_search"] = True
        await update.message.reply_text("Qo‘shiq nomini yozing:")
        return

async def handle_audio_or_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    song = extract_song_info(update.message)
    if not song:
        await update.message.reply_text("Faqat audio/mp3 yuboring 🙂")
        return
    context.user_data["pending_song"] = song
    await update.message.reply_text("Qaysi kategoriyaga qo‘shamiz?", reply_markup=categories_inline_kb("add"))

async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_search"):
        return

    context.user_data["awaiting_search"] = False
    cat = context.user_data.get("active_category")
    if not cat:
        await update.message.reply_text("Avval 📂 Kategoriyalar")
        return

    q = (update.message.text or "").strip().lower()
    rows = STORE.search_songs(update.effective_user.id, cat, q)
    if not rows:
        await update.message.reply_text("Topilmadi.")
        return

    await update.message.reply_text(f"Topildi: {len(rows)} ta")
    for i, (file_id, title, ftype) in enumerate(rows[:30], start=1):
        cap = f"{i}) {title}"
        try:
            if ftype == "audio":
                await update.message.reply_audio(file_id, caption=cap)
            else:
                await update.message.reply_document(file_id, caption=cap)
        except Exception:
            await update.message.reply_text(f"⚠️ Yuborilmadi: {title}")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data.startswith("view:"):
        cat = data.split(":", 1)[1]
        context.user_data["active_category"] = cat
        context.user_data["awaiting_search"] = False
        await q.message.reply_text(f"{CATEGORIES.get(cat, 'Kategoriya')} ochildi.", reply_markup=category_actions_kb())
        return

    if data.startswith("add:"):
        cat = data.split(":", 1)[1]
        pending = context.user_data.get("pending_song")
        if not pending:
            await q.message.reply_text("Avval qo‘shiq yuboring.")
            return

        STORE.add_song(update.effective_user.id, cat, pending["file_id"], pending["title"], pending["type"])
        context.user_data.pop("pending_song", None)
        await q.message.reply_text("✅ Saqlandi.", reply_markup=main_menu_kb())

# ------------------ AIOHTTP SERVER ------------------
async def create_web_app(tg_app: Application):
    aio = web.Application()

    async def root(request):
        return web.Response(text="OK")

    async def healthz(request):
        return web.Response(text="OK")

    async def webhook(request):
        data = await request.json()
        update = Update.de_json(data, tg_app.bot)
        await tg_app.process_update(update)
        return web.Response(text="OK")

    aio.router.add_get("/", root)
    aio.router.add_get("/healthz", healthz)
    aio.router.add_post(f"/{WEBHOOK_PATH}", webhook)
    return aio

async def main_async():
    global STORE
    check_env()

    STORE = make_storage()
    STORE.init()

    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("help", help_cmd))
    tg_app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, handle_audio_or_doc))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text), group=0)
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu), group=1)
    tg_app.add_handler(CallbackQueryHandler(on_callback))

    await tg_app.initialize()
    await tg_app.start()

    webhook_url = f"{WEBHOOK_BASE}/{WEBHOOK_PATH}"
    await tg_app.bot.set_webhook(webhook_url)
    log.info("Webhook set to: %s", webhook_url)

    aio_app = await create_web_app(tg_app)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("HTTP server running on port %s", PORT)

    # Doimiy ishlasin
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main_async())