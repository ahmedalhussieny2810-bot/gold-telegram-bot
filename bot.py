import os
import requests

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# بيانات فيسبوك
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")


def calc(price):
    price21 = round(price)
    price24 = round((price * 8) / 7)
    price18 = round((price * 6) / 7)

    return price24, price21, price18


def create_text(p24, p21, p18):
    return f"""💎 أسعار الذهب الآن

🟡 عيار 24 : {p24} جنيه
🟡 عيار 21 : {p21} جنيه
🟡 عيار 18 : {p18} جنيه

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
        price = float(update.message.text.replace(",", "").strip())

        if price <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ من فضلك أرسل سعر عيار 21 صحيح.\n\n"
            "مثال:\n6090"
        )
        return

    p24, p21, p18 = calc(price)

    text = create_text(p24, p21, p18)

    # حفظ الأسعار مؤقتًا للمستخدم
    context.user_data["price_text"] = text

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 فيسبوك + تليجرام",
                callback_data="both"
            )
        ],
        [
            InlineKeyboardButton(
                "✈️ تليجرام فقط",
                callback_data="telegram"
            )
        ],
        [
            InlineKeyboardButton(
                "📘 فيسبوك فقط",
                callback_data="facebook"
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text
        + "\n\n"
        + "📌 اختر مكان النشر:",
        reply_markup=reply_markup
    )


async def publish_telegram(context, text):

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=text
    )


def publish_facebook(text):

    if not FACEBOOK_PAGE_TOKEN or not FACEBOOK_PAGE_ID:
        return False, "بيانات فيسبوك غير مضافة في Railway."

    url = f"https://graph.facebook.com/{FACEBOOK_PAGE_ID}/feed"

    data = {
        "message": text,
        "access_token": FACEBOOK_PAGE_TOKEN,
    }

    response = requests.post(url, data=data, timeout=20)

    if response.ok:
        return True, "تم النشر على فيسبوك."

    try:
        error_data = response.json()
        error_message = error_data.get("error", {}).get(
            "message",
            "حدث خطأ غير معروف."
        )
    except Exception:
        error_message = response.text

    return False, error_message


async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    text = context.user_data.get("price_text")

    if not text:
        await query.edit_message_text(
            "❌ انتهت صلاحية الأسعار.\n"
            "أرسل سعر عيار 21 من جديد."
        )
        return

    choice = query.data

    # تليجرام فقط
    if choice == "telegram":

        try:
            await publish_telegram(context, text)

            await query.edit_message_text(
                text
                + "\n\n"
                + "✅ تم النشر في تليجرام فقط."
            )

        except Exception as e:

            await query.edit_message_text(
                f"❌ حصل خطأ أثناء النشر في تليجرام:\n{e}"
            )

        return

    # فيسبوك فقط
    if choice == "facebook":

        success, message = publish_facebook(text)

        if success:

            await query.edit_message_text(
                text
                + "\n\n"
                + "✅ تم النشر في فيسبوك فقط."
            )

        else:

            await query.edit_message_text(
                "❌ لم يتم النشر على فيسبوك.\n\n"
                + message
            )

        return

    # فيسبوك + تليجرام
    if choice == "both":

        telegram_ok = False
        facebook_ok = False

        try:
            await publish_telegram(context, text)
            telegram_ok = True
        except Exception:
            telegram_ok = False

        facebook_ok, facebook_message = publish_facebook(text)

        if telegram_ok and facebook_ok:

            result = "✅ تم النشر على فيسبوك وتليجرام."

        elif telegram_ok and not facebook_ok:

            result = (
                "⚠️ تم النشر في تليجرام، "
                "لكن فيسبوك لم يتم النشر عليه.\n\n"
                + facebook_message
            )

        elif not telegram_ok and facebook_ok:

            result = (
                "⚠️ تم النشر في فيسبوك، "
                "لكن تليجرام لم يتم النشر عليه."
            )

        else:

            result = "❌ لم يتم النشر على أي منصة."

        await query.edit_message_text(
            text
            + "\n\n"
            + result
        )


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
