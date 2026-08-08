import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

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


# =========================
# ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")


# =========================
# SETTINGS
# =========================

TIMEZONE = ZoneInfo("Africa/Cairo")

# ملف حفظ أول سعر في كل يوم
HISTORY_FILE = "gold_history.json"

# رابط الموقع
WEBSITE_LINK = "https://link.gettap.co/alhussienyjewelry"


# =========================
# GOLD CALCULATION
# =========================

def calc(price):

    price21 = round(price)
    price24 = round((price * 8) / 7)
    price18 = round((price * 6) / 7)

    return price24, price21, price18


# =========================
# DATE
# =========================

def today_date():

    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def yesterday_date():

    from datetime import timedelta

    yesterday = datetime.now(TIMEZONE) - timedelta(days=1)

    return yesterday.strftime("%Y-%m-%d")


# =========================
# HISTORY
# =========================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return {}

    try:

        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as e:

        print("History Load Error:", e)

        return {}


def save_history(history):

    try:

        # نحفظ في ملف مؤقت أولاً
        temp_file = HISTORY_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as file:

            json.dump(
                history,
                file,
                ensure_ascii=False,
                indent=2
            )

        # استبدال الملف القديم
        os.replace(temp_file, HISTORY_FILE)

    except Exception as e:

        print("History Save Error:", e)


# =========================
# FIRST PRICE OF DAY
# =========================

def get_today_first_price():

    history = load_history()

    today = today_date()

    return history.get(today)


def get_yesterday_first_price():

    history = load_history()

    yesterday = yesterday_date()

    return history.get(yesterday)


def save_first_price_of_today(price):

    history = load_history()

    today = today_date()

    # مهم جداً:
    # لو فيه سعر مسجل النهارده، ممنوع نغيره
    if today in history:

        return False

    history[today] = round(price)

    save_history(history)

    print(
        f"First price saved for {today}: {round(price)}"
    )

    return True


# =========================
# COMPARISON
# =========================

def create_comparison_line(current_price):

    yesterday_price = get_yesterday_first_price()

    if yesterday_price is None:

        return None

    difference = round(current_price - yesterday_price)

    if difference > 0:

        return (
            f"📈 عيار 21 ارتفع {difference} جنيه "
            f"عن أول سعر أمس"
        )

    elif difference < 0:

        return (
            f"📉 عيار 21 انخفض {abs(difference)} جنيه "
            f"عن أول سعر أمس"
        )

    else:

        return "➖ عيار 21 مستقر عن أول سعر أمس"


# =========================
# PRICE TEXT
# =========================

def create_price_text(p24, p21, p18, comparison=None):

    lines = []

    # المقارنة لازم تكون أول سطر
    if comparison:

        lines.append(comparison)
        lines.append("")

    lines.append("💎 أسعار الذهب الآن")
    lines.append("")
    lines.append(f"🟡 عيار 24 : {p24}")
    lines.append(f"🟡 عيار 21 : {p21}")
    lines.append(f"🟡 عيار 18 : {p18}")
    lines.append("")
    lines.append("📍 بورسعيد - شارع أسوان أمام صيدلية جلال")
    lines.append(WEBSITE_LINK)

    return "\n".join(lines)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 أهلاً بك في بوت الحسيني\n\n"
        "أرسل سعر الذهب عيار 21."
    )


# =========================
# RECEIVE PRICE
# =========================

async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        price = float(update.message.text)

    except ValueError:

        await update.message.reply_text(
            "❌ أرسل رقم صحيح."
        )

        return

    p24, p21, p18 = calc(price)

    # نشوف هل ده أول سعر النهارده
    today_first_price = get_today_first_price()

    is_first_post_today = today_first_price is None

    comparison = None

    # المقارنة تظهر فقط في أول بوست في اليوم
    if is_first_post_today:

        comparison = create_comparison_line(price)

    text = create_price_text(
        p24,
        p21,
        p18,
        comparison
    )

    # نحفظ البيانات مؤقتاً
    context.user_data["price_text"] = text
    context.user_data["price"] = round(price)
    context.user_data["is_first_post_today"] = is_first_post_today

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
        f"السعر: {round(price)}\n\n"
        "📢 عايز تنشر الأسعار فين؟",
        reply_markup=reply_markup
    )


# =========================
# FACEBOOK
# =========================

async def facebook_post(text):

    url = (
        f"https://graph.facebook.com/v23.0/"
        f"{FACEBOOK_PAGE_ID}/feed"
    )

    data = {
        "message": text,
        "access_token": FACEBOOK_PAGE_ACCESS_TOKEN
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        if response.status_code == 200:

            print("Facebook: SUCCESS")

            return True

        print(
            "Facebook Error:",
            response.text
        )

        return False

    except Exception as e:

        print(
            "Facebook Request Error:",
            e
        )

        return False


# =========================
# TELEGRAM
# =========================

async def telegram_post(context, text):

    try:

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text
        )

        print("Telegram: SUCCESS")

        return True

    except Exception as e:

        print(
            "Telegram Error:",
            e
        )

        return False


# =========================
# BUTTON HANDLER
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    choice = query.data

    # -------------------------
    # CANCEL
    # -------------------------

    if choice == "cancel":

        context.user_data.pop(
            "price_text",
            None
        )

        context.user_data.pop(
            "price",
            None
        )

        context.user_data.pop(
            "is_first_post_today",
            None
        )

        await query.edit_message_text(
            "❌ تم إلغاء النشر."
        )

        return

    # -------------------------
    # GET DATA
    # -------------------------

    text = context.user_data.get(
        "price_text"
    )

    price = context.user_data.get(
        "price"
    )

    is_first_post_today = context.user_data.get(
        "is_first_post_today",
        False
    )

    if not text or price is None:

        await query.edit_message_text(
            "❌ السعر انتهى. ابعت السعر من جديد."
        )

        return

    telegram_success = False
    facebook_success = False

    # =========================
    # TELEGRAM + FACEBOOK
    # =========================

    if choice == "telegram_facebook":

        telegram_success = await telegram_post(
            context,
            text
        )

        facebook_success = await facebook_post(
            text
        )

    # =========================
    # TELEGRAM ONLY
    # =========================

    elif choice == "telegram_only":

        telegram_success = await telegram_post(
            context,
            text
        )

    # =========================
    # FACEBOOK ONLY
    # =========================

    elif choice == "facebook_only":

        facebook_success = await facebook_post(
            text
        )

    # =========================
    # IMPORTANT
    # SAVE FIRST PRICE
    # =========================

    # السعر يتحفظ فقط إذا حصل نشر ناجح
    # وممنوع يتغير بعد كده خلال نفس اليوم

    successful_post = (
        telegram_success or facebook_success
    )

    if (
        successful_post
        and is_first_post_today
    ):

        save_first_price_of_today(
            price
        )

    # =========================
    # RESULT
    # =========================

    if choice == "telegram_facebook":

        if telegram_success and facebook_success:

            result = (
                "✅ تم النشر في تليجرام وفيسبوك."
            )

        elif telegram_success:

            result = (
                "⚠️ تم النشر في تليجرام فقط.\n"
                "❌ حصل خطأ في فيسبوك."
            )

        elif facebook_success:

            result = (
                "⚠️ تم النشر في فيسبوك فقط.\n"
                "❌ حصل خطأ في تليجرام."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر على الاثنين."
            )

    elif choice == "telegram_only":

        if telegram_success:

            result = (
                "✅ تم النشر في تليجرام."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر في تليجرام."
            )

    elif choice == "facebook_only":

        if facebook_success:

            result = (
                "✅ تم النشر في فيسبوك."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر فيسبوك."
            )

    else:

        result = "❌ اختيار غير معروف."

    await query.edit_message_text(
        result
    )

    # =========================
    # CLEAR TEMP DATA
    # =========================

    context.user_data.pop(
        "price_text",
        None
    )

    context.user_data.pop(
        "price",
        None
    )

    context.user_data.pop(
        "is_first_post_today",
        None
    )


# =========================
# MAIN
# =========================

def main():

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    print("Bot Started...")

    app.run_polling()


if __name__ == "__main__":

    main()
