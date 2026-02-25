import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("Token topilmadi! .env yoki Render Environment ga BOT_TOKEN qo‘shing.")

# ---------------------------
# 1) Render uchun PORT ochib turadigan mini web server
# ---------------------------
def run_web_server():
    port = int(os.environ.get("PORT", "10000"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK - bot is running")

        # Loglarni jim qilish (xohlasang olib tashla)
        def log_message(self, format, *args):
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


# ---------------------------
# 2) Telegram bot handlerlari
# ---------------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum! 🎵\n"
        "Menga xabar yuboring — men qaytarib beraman.\n"
        "Buyruqlar: /start, /help"
    )


def help_cmd(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Yordam:\n"
        "- Oddiy xabar yuboring\n"
        "- /start - boshlash\n"
        "- /help - yordam"
    )


def echo(update: Update, context: CallbackContext):
    # oddiy test uchun: kelgan matnni qaytaradi
    text = update.message.text
    update.message.reply_text(f"Siz yozdingiz: {text}")


def unknown(update: Update, context: CallbackContext):
    update.message.reply_text("Bunday buyruq yo‘q. /help ni bosing.")


# ---------------------------
# 3) Main
# ---------------------------
def main():
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. Render Environment ga BOT_TOKEN qo‘shing.")

    # Web serverni fon rejimida ishga tushiramiz (Render port ko‘rishi uchun)
    threading.Thread(target=run_web_server, daemon=True).start()

    updater = Updater(token=token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_cmd))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    dp.add_handler(MessageHandler(Filters.command, unknown))

    # polling
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()