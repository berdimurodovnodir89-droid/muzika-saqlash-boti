import os
import logging
from dotenv import load_dotenv

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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()  # masalan: https://muzika-saqlash-boti.onrender.com
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)

# 2 ta kategoriya
CATEGORIES = {
    "dam": "🏖 Dam olishda",
    "koch": "🚶 Ko‘chada",
}

# Saqlash: user_id -> { "dam": [song,...], "koch": [song,...] }
# song = {"file_id": "...", "title": "...", "type": "audio|document"}
USER_SONGS = {}


def check_env():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yo'q. Render Environment ga BOT_TOKEN qo'shing.")
    if not WEBHOOK_BASE:
        raise RuntimeError("WEBHOOK_BASE yo'q. Masalan: https://muzika-saqlash-boti.onrender.com")


def get_user_store(user_id: int):
    if user_id not in USER_SONGS:
        USER_SONGS[user_id] = {"dam": [], "koch": []}
    return USER_SONGS[user_id]


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📂 Kategoriyalar")],
        ],
        resize_keyboard=True,
    )


def categories_inline_kb(prefix: str):
    # prefix: "view" yoki "add"
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
    """
    Qabul qilinadi: audio yoki document (mp3)
    """
    if msg.audio:
        title = msg.audio.title or msg.audio.file_name or "audio"
        return {"type": "audio", "file_id": msg.audio.file_id, "title": title}

    if msg.document:
        # mp3 ham document bo'lib kelishi mumkin
        title = msg.document.file_name or "document"
        return {"type": "document", "file_id": msg.document.file_id, "title": title}

    return None


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

    # Kategoriya ichidagi menu
    if text == "🎵 Jami qo‘shiqlar":
        uid = update.effective_user.id
        active_cat = context.user_data.get("active_category")
        if not active_cat:
            await update.message.reply_text("Avval kategoriya tanlang: 📂 Kategoriyalar")
            return

        store = get_user_store(uid)
        songs = store.get(active_cat, [])
        if not songs:
            await update.message.reply_text("Bu kategoriyada hozircha qo‘shiq yo‘q.")
            return

        await update.message.reply_text(f"{CATEGORIES[active_cat]} — jami qo‘shiqlar: {len(songs)} ta")

        # Qo‘shiqlarni bittalab yuboramiz
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
            "Qo‘shiq nomini yozing.\n"
            "Masalan: *love* yoki *shoxrux* yoki *track.mp3*",
            parse_mode="Markdown",
        )
        return

    if text == "⬅️ Orqaga":
        context.user_data.pop("active_category", None)
        context.user_data.pop("awaiting_search", None)
        await update.message.reply_text("Bosh menu.", reply_markup=main_menu_kb())
        return

    # Oddiy text kelsa
    if context.user_data.get("awaiting_search"):
        # bu qismga handle_search_text tushadi, bu yerga kelmasin
        return

    await update.message.reply_text("Menga audio/mp3 yuboring yoki 📂 Kategoriyalar ni bosing.")


async def handle_audio_or_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    song = extract_song_info(msg)
    if not song:
        await msg.reply_text("Audio yoki mp3 yuboring 🙂")
        return

    # vaqtincha saqlab turamiz, keyin kategoriya so'raymiz
    context.user_data["pending_song"] = song

    await msg.reply_text(
        "Qo‘shiq qabul qilindi ✅\n"
        "Qaysi kategoriyaga qo‘shamiz?",
        reply_markup=categories_inline_kb(prefix="add"),
    )


async def handle_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # faqat search rejimida ishlaydi
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

    matches = []
    for s in songs:
        if query in (s["title"] or "").lower():
            matches.append(s)

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
    query = update.callback_query
    await query.answer()

    data = query.data or ""

    # Kategoriya ko'rish
    if data.startswith("view:"):
        cat_key = data.split(":", 1)[1]
        if cat_key not in CATEGORIES:
            await query.edit_message_text("Noto‘g‘ri kategoriya.")
            return

        context.user_data["active_category"] = cat_key
        context.user_data["awaiting_search"] = False

        await query.message.reply_text(
            f"{CATEGORIES[cat_key]} ochildi.\n"
            "Quyidagilardan birini tanlang:",
            reply_markup=category_actions_kb(),
        )
        return

    # Kategoriya qo'shish
    if data.startswith("add:"):
        cat_key = data.split(":", 1)[1]
        if cat_key not in CATEGORIES:
            await query.edit_message_text("Noto‘g‘ri kategoriya.")
            return

        pending = context.user_data.get("pending_song")
        if not pending:
            await query.message.reply_text("Avval qo‘shiq yuboring.")
            return

        uid = update.effective_user.id
        store = get_user_store(uid)
        store[cat_key].append(pending)

        # tozalaymiz
        context.user_data.pop("pending_song", None)

        await query.message.reply_text(
            f"✅ Saqlandi: *{pending['title']}*\n"
            f"Kategoriya: {CATEGORIES[cat_key]}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(),
        )
        return


def main():
    check_env()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # audio/document kelganda
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, handle_audio_or_doc))

    # qidirish uchun oddiy text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_text), group=0)
    # menu textlar
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu), group=1)

    # inline button callback
    app.add_handler(CallbackQueryHandler(on_callback))

    # webhook (Render)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"{WEBHOOK_BASE}/webhook",
    )


if __name__ == "__main__":
    main()