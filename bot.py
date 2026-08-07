import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")


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
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صحيح.")
        return

    p24, p21, p18 = calc(price)

    text = f"""💎 أسعار الذهب اليوم

🟡 عيار 24 : {p24}
🟡 عيار 21 : {p21}
🟡 عيار 18 : {p18}

📍 مصوغات ومجوهرات الحسيني
بورسعيد - شارع أسوان أمام صيدلية جلال
"""

    # إرسال للقناة
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=text
    )

    # تأكيد للمستخدم
    await update.message.reply_text("✅ تم نشر الأسعار في القناة.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive))

    print("Bot Started...")
    app.run_polling()


if __name__ == "__main__":
    main()
