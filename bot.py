import os
import sqlite3
from datetime import datetime, date

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

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN")

DB_FILE = "gold_prices.db"


# =========================
# قاعدة البيانات
# =========================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price21 INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def get_first_price_of_day(day):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT price21
        FROM daily_prices
        WHERE DATE(created_at) = ?
        ORDER BY created_at ASC
        LIMIT 1
    """, (day,))

    result = cursor.fetchone()

    conn.close()

    return result[0] if result else None


def save_first_price_of_day(price21):
    today = date.today().isoformat()

    existing = get_first_price_of_day(today)

    if existing is not None:
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO daily_prices (price21, created_at)
        VALUES (?, ?)
    """, (
        price21,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    return True


# =========================
# حساب الأسعار
# =========================

def calc(price):
    price21 = round(price)
    price24 = round((price * 8) / 7)
    price18 = round((price * 6) / 7)

    return price24, price21, price18


# =========================
# المقارنة
# =========================

def get_comparison(price21):
    today = date.today()

    # أول سعر أمس
    previous_day = date.fromordinal(today.toordinal() - 1)

    yesterday_price = get_first_price_of_day(
        previous_day.isoformat()
    )

    if yesterday_price is None:
        return None

    difference = price21 - yesterday_price

    if difference > 0:
        return f"📈 مقارنة بأول سعر أمس:\nعيار 21 ↑ {difference} جنيه"

    elif difference < 0:
        return f"📉 مقارنة بأول سعر أمس:\nعيار 21 ↓ {abs(difference)} جنيه"

    else:
        return "➖ مقارنة بأول سعر أمس:\nعيار 21 ثابت بدون تغيير"


# =========================
# إنشاء المنشور
# =========================

def create_price_text(p24, p21, p18, comparison=None):

    text = ""

    if comparison:
        text += comparison + "\n\n"

    text += f"""💎 أسعار الذهب الآن

🟡 عيار 24 : {p24} جنيه
🟡 عيار 21 : {p21} جنيه
🟡 عيار 18 : {p18} جنيه

✨ أسعار محدثة باستمرار

📍 بورسعيد – شارع أسوان
أمام صيدلية جلال

📩 للاستفسار والطلب تواصل معنا

https://link.gettap.co/alhussienyjewelry"""

    return text


# =========================
# Start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 أهلاً بك في بوت الحسيني\n\n"
        "أرسل سعر الذهب عيار 21."
    )


# =========================
# استقبال السعر
# =========================

async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        price = float(
            update.message.text.replace(",", "").strip()
        )

        if price <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ أرسل سعر عيار 21 صحيح.\n\n"
            "مثال:\n6100"
        )

        return

    p24, p21, p18 = calc(price)

    today = date.today().isoformat()

    # هل تم نشر أول سعر اليوم بالفعل؟
    first_price_today = get_first_price_of_day(today)

    comparison = None

    if first_price_today is None:

        comparison = get_comparison(p21)

    text = create_price_text(
        p24,
        p21,
        p18,
        comparison
    )

    # نحفظ المنشور مؤقتًا
    context.user_data["price_text"] = text
    context.user_data["price21"] = p21
    context.user_data["is_first_today"] = (
        first_price_today is None
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

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    await update.message.reply_text(
        "📋 معاينة المنشور:\n\n"
        + text
        + "\n\n"
        "📢 اختر مكان النشر:",
        reply_markup=reply_markup
    )


# =========================
# Facebook
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

            return True

        print(
            "Facebook Error:",
            response.text
        )

        return False

    except Exception as e:

        print(
            "Facebook Connection Error:",
            e
        )

        return False


# =========================
# أزرار النشر
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    choice = query.data

    # إلغاء
    if choice == "cancel":

        context.user_data.pop(
            "price_text",
            None
        )

        context.user_data.pop(
            "price21",
            None
        )

        context.user_data.pop(
            "is_first_today",
            None
        )

        await query.edit_message_text(
            "❌ تم إلغاء النشر."
        )

        return

    text = context.user_data.get(
        "price_text"
    )

    price21 = context.user_data.get(
        "price21"
    )

    is_first_today = context.user_data.get(
        "is_first_today",
        False
    )

    if not text or price21 is None:

        await query.edit_message_text(
            "❌ انتهت صلاحية السعر.\n"
            "ابعت السعر من جديد."
        )

        return

    telegram_success = False
    facebook_success = False

    # =====================
    # Telegram + Facebook
    # =====================

    if choice == "telegram_facebook":

        try:

            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text
            )

            telegram_success = True

        except Exception as e:

            print(
                "Telegram Error:",
                e
            )

        facebook_success = await facebook_post(
            text
        )

    # =====================
    # Telegram فقط
    # =====================

    elif choice == "telegram_only":

        try:

            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text
            )

            telegram_success = True

        except Exception as e:

            print(
                "Telegram Error:",
                e
            )

    # =====================
    # Facebook فقط
    # =====================

    elif choice == "facebook_only":

        facebook_success = await facebook_post(
            text
        )

    # =====================
    # حفظ أول سعر في اليوم
    # =====================

    # نسجل السعر فقط إذا كان هذا أول منشور اليوم
    # وتم النشر بنجاح على منصة واحدة على الأقل

    if (
        is_first_today
        and (
            telegram_success
            or facebook_success
        )
    ):

        save_first_price_of_day(
            price21
        )

    # =====================
    # رسالة النتيجة
    # =====================

    if choice == "telegram_facebook":

        if telegram_success and facebook_success:

            result = (
                "✅ تم النشر في "
                "تليجرام وفيسبوك."
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
                "❌ حصل خطأ في النشر "
                "على الاثنين."
            )

    elif choice == "telegram_only":

        if telegram_success:

            result = (
                "✅ تم النشر في تليجرام."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر "
                "في تليجرام."
            )

    elif choice == "facebook_only":

        if facebook_success:

            result = (
                "✅ تم النشر في فيسبوك."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر "
                "في فيسبوك."
            )

    await query.edit_message_text(
        result
    )

    # تنظيف البيانات المؤقتة

    context.user_data.pop(
        "price_text",
        None
    )

    context.user_data.pop(
        "price21",
        None
    )

    context.user_data.pop(
        "is_first_today",
        None
    )


# =========================
# Main
# =========================

def main():

    init_db()

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
            filters.TEXT
            & ~filters.COMMAND,
            receive
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    print(
        "Bot Started..."
    )

    app.run_polling()


if __name__ == "__main__":

    main()
