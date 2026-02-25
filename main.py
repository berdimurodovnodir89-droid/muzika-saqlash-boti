import os
import json
from datetime import datetime
from typing import Dict, List, Any

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

# ===================== ENV =====================
# Localda .env o'qiydi, Render'da ENV o'zidan keladi
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! (.env yoki Render ENV ga BOT_TOKEN qo'ying)")

# ===================== SETTINGS =====================
DB_FILE = "music_db.json"  # Render free'da doimiy emas (restart bo'lsa o'chishi mumkin)

# Buttons
BTN_CATEGORIES = "📂 Kategoriyalar"
BTN_BACK = "⬅️ Orqaga"
BTN_CANCEL = "❌ Bekor qilish"

# Categories
CAT_ISHDA = "Ishda"
CAT_KOCHADA = "Ko'chada"
CAT_DAM = "Dam olishda"
CATEGORIES = [CAT_ISHDA, CAT_KOCHADA, CAT_DAM]

# Conversation states
WAITING_CATEGORY = 1
BROWSE_SELECT_CATEGORY = 2
BROWSE_SELECT_AUDIO = 3


# ===================== DB (JSON) =====================
def empty_db() -> Dict[str, List[Dict[str, Any]]]:
    return {c: [] for c in CATEGORIES}


def load_db() -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(DB_FILE):
        return empty_db()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in CATEGORIES:
            data.setdefault(c, [])
        return data
    except Exception:
        return empty_db()


def save_db(db: Dict[str, List[Dict[str, Any]]]) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


DB = load_db()


# ===================== Keyboards =====================
def kb_main() -> ReplyKeyboardMarkup:
    # Faqat Kategoriyalar tugmasi qoldi
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CATEGORIES)]],
        resize_keyboard=True,
    )


def kb_categories(with_back: bool = False, one_time: bool = True) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(CAT_ISHDA)],
        [KeyboardButton(CAT_KOCHADA)],
        [KeyboardButton(CAT_DAM)],
    ]
    if with_back:
        rows.append([KeyboardButton(BTN_BACK)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=one_time)


def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def kb_audio_list(items: List[Dict[str, Any]]) -> ReplyKeyboardMarkup:
    rows = []
    for i, it in enumerate(items, start=1):
        title = it.get("title", "Audio")
        if len(title) > 30:
            title = title[:27] + "..."
        rows.append([KeyboardButton(f"{i}. {title}")])
    rows.append([KeyboardButton(BTN_BACK)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# ===================== Commands =====================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalom aleykum! 🎵\n\n"
        "Men — musiqa saqlaydigan botman.\n\n"
        "✅ Qanday ishlaydi?\n"
        "1) Menga *audio* yuborasiz (musiqa fayl).\n"
        "2) Men sizdan kategoriya so‘rayman:\n"
        f"   • {CAT_ISHDA}\n"
        f"   • {CAT_KOCHADA}\n"
        f"   • {CAT_DAM}\n"
        "3) Tanlaganingizdan keyin musiqa saqlanadi.\n\n"
        "🎧 Keyin eshitish uchun:\n"
        f"• {BTN_CATEGORIES} tugmasini bosing → kategoriya tanlang → ro‘yxatdan musiqani tanlang.\n\n"
        "🧠 Maslahat:\n"
        "• Audio yuborishda nom (title) bo‘lsa, ro‘yxatda chiroyli ko‘rinadi.\n"
        "• Bekor qilish: /cancel yoki “❌ Bekor qilish”.\n\n"
        "Boshlash uchun menga hoziroq bitta audio yuboring ✅",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )


def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Qo'llanma:\n"
        "• Audio yuboring → kategoriya tanlang → saqlanadi\n"
        f"• {BTN_CATEGORIES} → kategoriya → ro‘yxatdan tanlab eshitasiz\n\n"
        "Buyruqlar:\n"
        "/start - botni qayta boshlash\n"
        "/help - yordam\n"
        "/cancel - bekor qilish\n",
        reply_markup=kb_main(),
    )


def cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.message.reply_text("Bekor qilindi ✅", reply_markup=kb_main())
    return ConversationHandler.END


# ===================== Save Flow (Audio -> category) =====================
def audio_received(update: Update, context: CallbackContext):
    audio = update.message.audio
    if not audio:
        update.message.reply_text("Audio topilmadi. Audio yuboring 🎵", reply_markup=kb_main())
        return ConversationHandler.END

    title = audio.title or audio.file_name or "Audio"
    context.user_data["pending_file_id"] = audio.file_id
    context.user_data["pending_title"] = title

    update.message.reply_text(
        "Musiqani qaysi kategoriyaga saqlaymiz? 👇",
        reply_markup=kb_categories(with_back=False),
    )
    return WAITING_CATEGORY


def choose_category(update: Update, context: CallbackContext):
    cat = (update.message.text or "").strip()
    if cat not in CATEGORIES:
        update.message.reply_text(
            "Iltimos, 3 ta kategoriyadan birini tanlang 👇",
            reply_markup=kb_categories(with_back=False),
        )
        return WAITING_CATEGORY

    file_id = context.user_data.get("pending_file_id")
    title = context.user_data.get("pending_title", "Audio")

    if not file_id:
        update.message.reply_text("Audio ma'lumoti yo'qoldi. Qaytadan audio yuboring.", reply_markup=kb_main())
        return ConversationHandler.END

    DB.setdefault(cat, [])
    DB[cat].append(
        {
            "file_id": file_id,
            "title": title,
            "saved_at": datetime.utcnow().isoformat() + "Z",
        }
    )
    save_db(DB)

    context.user_data.pop("pending_file_id", None)
    context.user_data.pop("pending_title", None)

    update.message.reply_text(f"✅ Saqlandi: *{title}* → *{cat}*", parse_mode="Markdown", reply_markup=kb_main())
    return ConversationHandler.END


# ===================== Browse Flow (Categories -> pick -> play) =====================
def open_categories(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Qaysi kategoriyani ochamiz? 👇",
        reply_markup=kb_categories(with_back=True),
    )
    return BROWSE_SELECT_CATEGORY


def browse_choose_category(update: Update, context: CallbackContext):
    txt = (update.message.text or "").strip()
    if txt == BTN_BACK:
        update.message.reply_text("Bosh menyu 👇", reply_markup=kb_main())
        return ConversationHandler.END

    if txt not in CATEGORIES:
        update.message.reply_text("Kategoriya tanlang 👇", reply_markup=kb_categories(with_back=True))
        return BROWSE_SELECT_CATEGORY

    items = DB.get(txt, [])
    context.user_data["browse_category"] = txt

    if not items:
        update.message.reply_text(f"📭 *{txt}* ichida hozircha musiqa yo‘q.", parse_mode="Markdown",
                                 reply_markup=kb_categories(with_back=True))
        return BROWSE_SELECT_CATEGORY

    update.message.reply_text(
        f"🎧 *{txt}* ichidan musiqani tanlang:",
        parse_mode="Markdown",
        reply_markup=kb_audio_list(items),
    )
    return BROWSE_SELECT_AUDIO


def browse_play_audio(update: Update, context: CallbackContext):
    txt = (update.message.text or "").strip()

    if txt == BTN_BACK:
        update.message.reply_text("Qaysi kategoriyani ochamiz?", reply_markup=kb_categories(with_back=True))
        return BROWSE_SELECT_CATEGORY

    cat = context.user_data.get("browse_category")
    if cat not in CATEGORIES:
        update.message.reply_text("Avval kategoriya tanlang 👇", reply_markup=kb_categories(with_back=True))
        return BROWSE_SELECT_CATEGORY

    items = DB.get(cat, [])

    try:
        num = int(txt.split(".", 1)[0].strip())
        idx = num - 1
    except Exception:
        update.message.reply_text("Ro‘yxatdan musiqani tanlang 👇")
        return BROWSE_SELECT_AUDIO

    if idx < 0 or idx >= len(items):
        update.message.reply_text("Noto‘g‘ri tanlov. Ro‘yxatdan tanlang 👇")
        return BROWSE_SELECT_AUDIO

    it = items[idx]
    file_id = it.get("file_id")
    title = it.get("title", "Audio")

    if not file_id:
        update.message.reply_text("File topilmadi (file_id yo‘q).")
        return BROWSE_SELECT_AUDIO

    update.message.reply_text(f"▶️ *{title}*", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    update.message.reply_audio(audio=file_id)

    update.message.reply_text("Yana birini tanlashingiz mumkin 👇", reply_markup=kb_audio_list(items))
    return BROWSE_SELECT_AUDIO


# ===================== MAIN =====================
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("cancel", cancel))

    # Save conversation: audio -> choose category (audio yuborilganda avtomatik ishlaydi)
    save_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.audio, audio_received)],
        states={
            WAITING_CATEGORY: [MessageHandler(Filters.text & ~Filters.command, choose_category)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(Filters.regex(f"^{BTN_CANCEL}$"), cancel),
        ],
    )
    dp.add_handler(save_conv)

    # Browse conversation: categories -> pick -> play
    browse_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex(f"^{BTN_CATEGORIES}$"), open_categories)],
        states={
            BROWSE_SELECT_CATEGORY: [MessageHandler(Filters.text & ~Filters.command, browse_choose_category)],
            BROWSE_SELECT_AUDIO: [MessageHandler(Filters.text & ~Filters.command, browse_play_audio)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(Filters.regex(f"^{BTN_CANCEL}$"), cancel),
        ],
    )
    dp.add_handler(browse_conv)

    print("Bot ishga tushdi...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()