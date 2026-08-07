import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def calc(price):
    price21 = round(price)
    price24 = round((price * 8) / 7)
    price18 = round((price * 6) / 7)

    return price24, price21, price18


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت الحسيني\n\nأرسل سعر الذهب عيار 21."
    )


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text)
    except:
        await update.message.reply_text("❌ أرسل رقم صحيح.")
        return

    p24, p21, p18 = calc(price)

    text = f"""💎 أسعار الذهب

عيار 24 : {p24}
عيار 21 : {p21}
عيار 18 : {p18}
"""

    await update.message.reply_text(text)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive))

    print("Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()
