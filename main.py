import os
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
BOT_TOKEN = os.getenv("BOT_TOKEN")


CATEGORIES = {"dam": "🏖 Dam olishda", "koch": "🚶 Kochada"}


USER_SONGS = {}


def get_user_store(user_id):
    if user_id not in USER_SONGS:
        USER_SONGS[user_id] = {"dam": [], "koch": []}
    return USER_SONGS[user_id]


def main_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📂 Kategoriyalar")]], resize_keyboard=True
    )


def categories_keyboard(prefix):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏖 Dam olishda", callback_data=f"{prefix}:dam")],
            [InlineKeyboardButton("🚶 Kochada", callback_data=f"{prefix}:koch")],
        ]
    )


def category_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🎵 Jami qoshiqlar")], [KeyboardButton("⬅️ Orqaga")]],
        resize_keyboard=True,
    )


def get_song(msg):

    if msg.audio:
        return {
            "type": "audio",
            "file_id": msg.audio.file_id,
            "title": msg.audio.title or "audio",
        }

    if msg.document:
        return {
            "type": "document",
            "file_id": msg.document.file_id,
            "title": msg.document.file_name or "file",
        }

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "🎧 Musiqa saqlash botiga xush kelibsiz\n\n"
        "Bu bot orqali siz qo‘shiqlarni kategoriyalarga saqlashingiz mumkin.\n\n"
        "1️⃣ Audio yoki mp3 yuboring\n"
        "2️⃣ Kategoriyani tanlang\n"
        "3️⃣ Keyin kategoriyadan qo‘shiqlarni ko‘rishingiz mumkin\n\n"
        "📂 Kategoriyalar tugmasini bosing"
    )

    await update.message.reply_text(text, reply_markup=main_menu())


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📂 Kategoriyalar":
        await update.message.reply_text(
            "Kategoriya tanlang", reply_markup=categories_keyboard("view")
        )

        return

    if text == "🎵 Jami qoshiqlar":
        user_id = update.effective_user.id
        cat = context.user_data.get("category")

        if not cat:
            await update.message.reply_text("Avval kategoriya tanlang")
            return

        songs = get_user_store(user_id)[cat]

        if not songs:
            await update.message.reply_text("Bu kategoriyada qo‘shiq yo‘q")
            return

        for s in songs:
            if s["type"] == "audio":
                await update.message.reply_audio(audio=s["file_id"], caption=s["title"])

            else:
                await update.message.reply_document(
                    document=s["file_id"], caption=s["title"]
                )

        return

    if text == "⬅️ Orqaga":
        context.user_data.clear()

        await update.message.reply_text("Bosh menu", reply_markup=main_menu())


async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    song = get_song(update.message)

    if not song:
        return

    context.user_data["song"] = song

    await update.message.reply_text(
        "Qaysi kategoriyaga saqlaymiz?", reply_markup=categories_keyboard("add")
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("view:"):
        cat = data.split(":")[1]
        context.user_data["category"] = cat

        await query.message.reply_text(
            "Kategoriya ochildi", reply_markup=category_menu()
        )

        return

    if data.startswith("add:"):
        cat = data.split(":")[1]
        song = context.user_data.get("song")

        if not song:
            await query.message.reply_text("Avval audio yuboring")
            return

        user_id = update.effective_user.id

        get_user_store(user_id)[cat].append(song)

        context.user_data.pop("song")

        await query.message.reply_text("✅ Qoshiq saqlandi", reply_markup=main_menu())


def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.ALL, audio_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("Bot ishga tushdi...")

    app.run_polling()


if __name__ == "__main__":
    main()
