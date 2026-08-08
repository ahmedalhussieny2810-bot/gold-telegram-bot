import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import requests

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")


def calc(price):
    price21 = round(price)
    price24 = round((price * 8) / 7)
    price18 = round((price * 6) / 7)

    return price24, price21, price18


def create_price_text(p24, p21, p18):
    return f"""💎 أسعار الذهب الآن

🟡 عيار 24 : {p24}
🟡 عيار 21 : {p21}
🟡 عيار 18 : {p18}

📍 مصوغات ومجوهرات الحسيني
بورسعيد - شارع أسوان أمام صيدلية جلال
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك في بوت الحسيني\n\n"
        "أرسل سعر الذهب عيار 21."
    )


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        price = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ أرسل رقم صحيح.")
        return

    p24, p21, p18 = calc(price)

    # نحفظ الأسعار مؤقتاً عشان نستخدمها بعد اختيار مكان النشر
    context.user_data["price_text"] = create_price_text(
        p24, p21, p18
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📱 تليجرام + فيسبوك",
                callback_data="telegram_facebook"
            )
        ],
        [
            InlineKeyboardButton(
                "📱 تليجرام فقط",
                callback_data="telegram_only"
            )
        ],
        [
            InlineKeyboardButton(
                "📘 فيسبوك فقط",
                callback_data="facebook_only"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="cancel"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"السعر: {p21}\n\n"
        "📢 عايز تنشر الأسعار فين؟",
        reply_markup=reply_markup
    )


async def facebook_post(text):

    url = f"https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/feed"

    data = {
        "message": text,
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        return True

    print("Facebook Error:", response.text)
    return False


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    choice = query.data

    if choice == "cancel":
        await query.edit_message_text("❌ تم إلغاء النشر.")
        return

    text = context.user_data.get("price_text")

    if not text:
        await query.edit_message_text(
            "❌ السعر انتهى. ابعت السعر من جديد."
        )
        return

    telegram_success = False
    facebook_success = False

    # تليجرام + فيسبوك
    if choice == "telegram_facebook":

        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text
            )
            telegram_success = True
        except Exception as e:
            print("Telegram Error:", e)

        facebook_success = await facebook_post(text)

    # تليجرام فقط
    elif choice == "telegram_only":

        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text
            )
            telegram_success = True
        except Exception as e:
            print("Telegram Error:", e)

    # فيسبوك فقط
    elif choice == "facebook_only":

        facebook_success = await facebook_post(text)

    # النتيجة
    if choice == "telegram_facebook":

        if telegram_success and facebook_success:
            result = "✅ تم النشر في تليجرام وفيسبوك."

        elif telegram_success:
            result = "⚠️ تم النشر في تليجرام فقط.\n❌ حصل خطأ في فيسبوك."

        elif facebook_success:
            result = "⚠️ تم النشر في فيسبوك فقط.\n❌ حصل خطأ في تليجرام."

        else:
            result = "❌ حصل خطأ في النشر على الاثنين."

    elif choice == "telegram_only":

        if telegram_success:
            result = "✅ تم النشر في تليجرام."
        else:
            result = "❌ حصل خطأ في النشر في تليجرام."

    elif choice == "facebook_only":

        if facebook_success:
            result = "✅ تم النشر في فيسبوك."
        else:
            result = "❌ حصل خطأ في النشر فيسبوك."

    await query.edit_message_text(result)

    # نمسح السعر بعد النشر
    context.user_data.pop("price_text", None)


def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive
        )
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    print("Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()
