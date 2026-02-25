import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# Lokal uchun .env o‘qiydi (Render’da ham ishlaydi)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Token topilmadi! .env yoki Render Environment ga BOT_TOKEN qo‘shing.")


# ---------------------------
# Render Web Service uchun PORT ochib turadigan mini server
# ---------------------------
def run_web_server():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK - bot is running")

        def log_message(self, format, *args):
            return

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


# ---------------------------
# Klaviatura (kategoriya tugmalar)
# ---------------------------
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🎵 Musiqa qo‘shish"), KeyboardButton("📂 Mening musiqalarim")],
            [KeyboardButton("🔎 Qidirish"), KeyboardButton("ℹ️ Yordam")],
        ],
        resize_keyboard=True,
    )


# vaqtincha xotira (Render free restart bo‘lsa o‘chadi)
# key: user_id, value: list of {"title":..., "url":...}
USER_MUSIC = {}
USER_STATE = {}  # user_id -> "ADD_WAIT" / "SEARCH_WAIT"


# ---------------------------
# /start
# ---------------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum! 🎧\n\n"
        "Bu botda musiqalaringizni saqlab borasiz.\n\n"
        "Qanday ishlaydi:\n"
        "1) 🎵 Musiqa qo‘shish — nom + link yuborasiz\n"
        "2) 📂 Mening musiqalarim — ro‘yxatni ko‘rasiz\n"
        "3) 🔎 Qidirish — nom bo‘yicha topasiz\n\n"
        "Pastdagi menyudan tanlang 👇",
        reply_markup=main_menu_keyboard(),
    )


def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "ℹ️ Yordam:\n"
        "• 🎵 Musiqa qo‘shish: Avval nom, keyin link yuborasiz.\n"
        "• 📂 Mening musiqalarim: Saqlangan musiqalar ro‘yxati.\n"
        "• 🔎 Qidirish: Nom yozib qidirasiz.\n\n"
        "Eslatma: Render free’da bot restart bo‘lsa, vaqtincha saqlangan ro‘yxat o‘chishi mumkin."
    )


# ---------------------------
# Menyu tugmalari
# ---------------------------
def menu_add(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    USER_STATE[user_id] = "ADD_WAIT"
    update.message.reply_text(
        "🎵 Musiqa qo‘shish:\n"
        "Menga musiqaning NOMIni yuboring.\n\n"
        "Masalan: `Miyagi - Captain`",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


def menu_list(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    items = USER_MUSIC.get(user_id, [])

    if not items:
        update.message.reply_text(
            "📂 Sizda hozircha musiqa yo‘q.\n"
            "🎵 Musiqa qo‘shish ni bosib qo‘shing.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text_lines = ["📂 Mening musiqalarim:\n"]
    for i, m in enumerate(items, 1):
        text_lines.append(f"{i}) {m['title']}\n   {m['url']}")
    update.message.reply_text("\n".join(text_lines), reply_markup=main_menu_keyboard())


def menu_search(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    USER_STATE[user_id] = "SEARCH_WAIT"
    update.message.reply_text(
        "🔎 Qidirish:\nQaysi nomni qidiramiz? (matn yuboring)",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------
# Matn kelganda: state bo‘yicha ishlaydi
# ---------------------------
def on_text(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    # Menyu bosilgan bo‘lsa
    if text == "🎵 Musiqa qo‘shish":
        return menu_add(update, context)
    if text == "📂 Mening musiqalarim":
        return menu_list(update, context)
    if text == "🔎 Qidirish":
        return menu_search(update, context)
    if text == "ℹ️ Yordam":
        return help_cmd(update, context)

    state = USER_STATE.get(user_id)

    # 1) Musiqa qo‘shish jarayoni: avval nom, keyin link
    if state == "ADD_WAIT":
        # nomni contextga saqlaymiz
        context.user_data["pending_title"] = text
        USER_STATE[user_id] = "ADD_WAIT_URL"
        update.message.reply_text(
            "✅ Nom qabul qilindi.\nEndi musiqaning LINKini yuboring (YouTube/Telegram/Drive link bo‘lishi mumkin).",
            reply_markup=main_menu_keyboard(),
        )
        return

    if state == "ADD_WAIT_URL":
        title = (context.user_data.get("pending_title") or "").strip()
        url = text

        if not (url.startswith("http://") or url.startswith("https://")):
            update.message.reply_text(
                "❌ Link noto‘g‘ri.\nIltimos `https://...` ko‘rinishida yuboring.",
                reply_markup=main_menu_keyboard(),
            )
            return

        USER_MUSIC.setdefault(user_id, []).append({"title": title, "url": url})
        USER_STATE[user_id] = None
        context.user_data.pop("pending_title", None)

        update.message.reply_text(
            f"✅ Saqlandi!\n🎵 {title}\n🔗 {url}\n\n"
            "Yana qo‘shasizmi? 🎵 Musiqa qo‘shish ni bosing.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # 2) Qidirish
    if state == "SEARCH_WAIT":
        q = text.lower()
        items = USER_MUSIC.get(user_id, [])
        found = [m for m in items if q in m["title"].lower()]

        if not found:
            update.message.reply_text("❌ Topilmadi. Boshqa nom yozib ko‘ring.", reply_markup=main_menu_keyboard())
            return

        lines = ["🔎 Natijalar:\n"]
        for i, m in enumerate(found, 1):
            lines.append(f"{i}) {m['title']}\n   {m['url']}")
        update.message.reply_text("\n".join(lines), reply_markup=main_menu_keyboard())
        USER_STATE[user_id] = None
        return

    # Hech qanday state bo‘lmasa
    update.message.reply_text(
        "Men sizni tushunmadim 😅\nPastdagi menyudan tanlang.",
        reply_markup=main_menu_keyboard(),
    )


def unknown_command(update: Update, context: CallbackContext):
    update.message.reply_text("Bunday buyruq yo‘q. /start yoki menyudan foydalaning.")


def main():
    # Web serverni fon rejimida ishga tushiramiz (Render port ko‘rishi uchun)
    threading.Thread(target=run_web_server, daemon=True).start()

    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, on_text))
    dp.add_handler(MessageHandler(Filters.command, unknown_command))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()