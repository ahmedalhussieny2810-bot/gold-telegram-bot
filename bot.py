import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

import requests
import pymysql


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_PAGE_TOKEN"
)

DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = int(
    os.getenv("ADMIN_ID", "0")
)


# =========================================================
# SETTINGS
# =========================================================

TIMEZONE = ZoneInfo("Africa/Cairo")

WEBSITE_LINK = (
    "https://link.gettap.co/alhussienyjewelry"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL is missing"
        )

    url = urlparse(DATABASE_URL)

    return pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_database():

    connection = None

    try:

        connection = get_db_connection()

        with connection.cursor() as cursor:

            # -------------------------
            # PRODUCTS
            # -------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Products (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    category VARCHAR(255) NOT NULL,
                    Photo_id TEXT NOT NULL,
                    PRIMARY KEY (id)
                )
            """)

            # -------------------------
            # GOLD HISTORY
            # -------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Gold_history (
                    Date DATE NOT NULL,
                    Price INT NOT NULL
                )
            """)

        print("Database: READY")

    except Exception as e:

        print(
            "Database Initialization Error:",
            e
        )

    finally:

        if connection:
            connection.close()


# =========================================================
# PRODUCT FUNCTIONS
# =========================================================

def add_product(
    category,
    photo_id
):

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO Products
                (category, Photo_id)
                VALUES (%s, %s)
                """,
                (
                    category,
                    photo_id
                )
            )

        print(
            f"Product added: {category}"
        )

    finally:

        connection.close()


def get_products(category):

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    category,
                    Photo_id
                FROM Products
                WHERE LOWER(TRIM(category))
                    = LOWER(TRIM(%s))
                ORDER BY id DESC
                """,
                (category,)
            )

            return cursor.fetchall()

    finally:

        connection.close()


def get_categories():

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT DISTINCT category
                FROM Products
                ORDER BY category
                """
            )

            return [
                row["category"]
                for row in cursor.fetchall()
            ]

    finally:

        connection.close()


# =========================================================
# GOLD CALCULATION
# =========================================================

def calc(price):

    price21 = round(price)

    price24 = round(
        (price * 8) / 7
    )

    price18 = round(
        (price * 6) / 7
    )

    return (
        price24,
        price21,
        price18
    )


# =========================================================
# DATE
# =========================================================

def today_date():

    return datetime.now(
        TIMEZONE
    ).strftime("%Y-%m-%d")


def yesterday_date():

    yesterday = (
        datetime.now(TIMEZONE)
        - timedelta(days=1)
    )

    return yesterday.strftime(
        "%Y-%m-%d"
    )


# =========================================================
# GOLD HISTORY
# =========================================================

def get_today_first_price():

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT Price
                FROM Gold_history
                WHERE Date = %s
                LIMIT 1
                """,
                (
                    today_date(),
                )
            )

            row = cursor.fetchone()

            if row:

                return row["Price"]

            return None

    finally:

        connection.close()


def get_yesterday_first_price():

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT Price
                FROM Gold_history
                WHERE Date = %s
                LIMIT 1
                """,
                (
                    yesterday_date(),
                )
            )

            row = cursor.fetchone()

            if row:

                return row["Price"]

            return None

    finally:

        connection.close()


def save_first_price_of_today(
    price
):

    connection = get_db_connection()

    try:

        with connection.cursor() as cursor:

            # -------------------------
            # CHECK IF TODAY EXISTS
            # -------------------------

            cursor.execute(
                """
                SELECT Price
                FROM Gold_history
                WHERE Date = %s
                LIMIT 1
                """,
                (
                    today_date(),
                )
            )

            existing = cursor.fetchone()

            # السعر موجود بالفعل
            # ممنوع تغييره
            if existing:

                print(
                    "Gold History: "
                    "Today's price already exists"
                )

                return False

            # -------------------------
            # SAVE FIRST PRICE
            # -------------------------

            cursor.execute(
                """
                INSERT INTO Gold_history
                (Date, Price)
                VALUES (%s, %s)
                """,
                (
                    today_date(),
                    round(price)
                )
            )

            print(
                f"Gold History Saved: "
                f"{today_date()} = "
                f"{round(price)}"
            )

            return True

    finally:

        connection.close()


# =========================================================
# COMPARISON
# =========================================================

def create_comparison_line(
    current_price
):

    yesterday_price = (
        get_yesterday_first_price()
    )

    if yesterday_price is None:

        return None

    difference = round(
        current_price
        - yesterday_price
    )

    if difference > 0:

        return (
            f"📈 عيار 21 ارتفع "
            f"{difference} جنيه "
            f"عن أول سعر أمس"
        )

    elif difference < 0:

        return (
            f"📉 عيار 21 انخفض "
            f"{abs(difference)} جنيه "
            f"عن أول سعر أمس"
        )

    return (
        "➖ عيار 21 مستقر "
        "عن أول سعر أمس"
    )


# =========================================================
# PRICE TEXT
# =========================================================

def create_price_text(
    p24,
    p21,
    p18,
    comparison=None
):

    lines = []

    # المقارنة أول سطر
    if comparison:

        lines.append(
            comparison
        )

        lines.append("")

    lines.append(
        "💎 أسعار الذهب الآن"
    )

    lines.append("")

    lines.append(
        f"🟡 عيار 24 : {p24}"
    )

    lines.append(
        f"🟡 عيار 21 : {p21}"
    )

    lines.append(
        f"🟡 عيار 18 : {p18}"
    )

    lines.append("")

    lines.append(
        "📍 بورسعيد - شارع أسوان "
        "أمام صيدلية جلال"
    )

    lines.append(
        WEBSITE_LINK
    )

    return "\n".join(lines)


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 أهلاً بك في بوت الحسيني\n\n"
        "💎 يمكنك إرسال اسم القسم "
        "لرؤية المنتجات.\n\n"
        "مثال:\n"
        "خواتم\n"
        "سلاسل\n"
        "غوايش\n"
        "أطقم\n\n"
        "ولو عايز تعرف أسعار الذهب، "
        "أرسل سعر عيار 21."
    )


# =========================================================
# ADMIN PHOTO
# =========================================================

async def receive_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    # ---------------------------------
    # ADMIN ONLY
    # ---------------------------------

    if user_id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مسموح لك بإضافة منتجات."
        )

        return

    photo = update.message.photo[-1]

    photo_id = photo.file_id

    category = (
        update.message.caption
        or ""
    ).strip()

    if not category:

        await update.message.reply_text(
            "❌ اكتب اسم القسم في "
            "Caption الصورة.\n\n"
            "مثال:\n"
            "خواتم"
        )

        return

    try:

        add_product(
            category,
            photo_id
        )

        await update.message.reply_text(
            f"✅ تم حفظ الصورة.\n\n"
            f"📂 القسم: {category}"
        )

    except Exception as e:

        print(
            "Add Product Error:",
            e
        )

        await update.message.reply_text(
            "❌ حصل خطأ أثناء حفظ الصورة."
        )


# =========================================================
# SHOW PRODUCTS
# =========================================================

async def show_products(
    update: Update,
    category
):

    try:

        products = get_products(
            category
        )

    except Exception as e:

        print(
            "Get Products Error:",
            e
        )

        await update.message.reply_text(
            "❌ حصل خطأ في قاعدة البيانات."
        )

        return

    if not products:

        await update.message.reply_text(
            f"❌ مفيش منتجات مسجلة في قسم:\n"
            f"{category}"
        )

        return

    await update.message.reply_text(
        f"💎 منتجات قسم {category}\n"
        f"عدد الصور: {len(products)}"
    )

    for product in products:

        try:

            await update.message.reply_photo(
                photo=product["Photo_id"]
            )

        except Exception as e:

            print(
                "Send Photo Error:",
                e
            )


# =========================================================
# RECEIVE TEXT
# =========================================================

async def receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        update.message.text
        or ""
    ).strip()

    # =====================================================
    # CHECK IF PRICE
    # =====================================================

    try:

        price = float(text)

        is_price = True

    except ValueError:

        is_price = False


    # =====================================================
    # IF NOT PRICE → PRODUCT CATEGORY
    # =====================================================

    if not is_price:

        try:

            categories = (
                get_categories()
            )

            found_category = None

            for category in categories:

                if (
                    category.strip().lower()
                    == text.strip().lower()
                ):

                    found_category = category

                    break

            if found_category:

                await show_products(
                    update,
                    found_category
                )

                return

        except Exception as e:

            print(
                "Category Search Error:",
                e
            )

        await update.message.reply_text(
            "❌ مش فاهم طلبك.\n\n"
            "اكتب اسم قسم موجود مثل:\n"
            "خواتم\n"
            "سلاسل\n"
            "غوايش\n"
            "أطقم"
        )

        return


    # =====================================================
    # GOLD PRICE ADMIN ONLY
    # =====================================================

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:

        await update.message.reply_text(
            "❌ أسعار الذهب متاحة للأدمن فقط."
        )

        return


    # =====================================================
    # CALCULATE GOLD
    # =====================================================

    p24, p21, p18 = calc(
        price
    )


    # =====================================================
    # CHECK FIRST PRICE OF TODAY
    # =====================================================

    today_first_price = (
        get_today_first_price()
    )

    is_first_post_today = (
        today_first_price is None
    )


    # =====================================================
    # COMPARISON
    # =====================================================

    comparison = None

    if is_first_post_today:

        comparison = (
            create_comparison_line(
                price
            )
        )


    # =====================================================
    # CREATE MESSAGE
    # =====================================================

    price_text = create_price_text(
        p24,
        p21,
        p18,
        comparison
    )


    # =====================================================
    # SAVE TEMPORARY DATA
    # =====================================================

    context.user_data[
        "price_text"
    ] = price_text

    context.user_data[
        "price"
    ] = round(price)

    context.user_data[
        "is_first_post_today"
    ] = is_first_post_today


    # =====================================================
    # BUTTONS
    # =====================================================

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


    reply_markup = (
        InlineKeyboardMarkup(
            keyboard
        )
    )


    await update.message.reply_text(
        f"السعر: {round(price)}\n\n"
        "📢 عايز تنشر الأسعار فين؟",
        reply_markup=reply_markup
    )


# =========================================================
# FACEBOOK
# =========================================================

async def facebook_post(
    text
):

    url = (
        "https://graph.facebook.com/v23.0/"
        f"{FACEBOOK_PAGE_ID}/feed"
    )

    data = {

        "message": text,

        "access_token":
            FACEBOOK_PAGE_ACCESS_TOKEN
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        if response.status_code == 200:

            print(
                "Facebook: SUCCESS"
            )

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


# =========================================================
# TELEGRAM
# =========================================================

async def telegram_post(
    context,
    text
):

    try:

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text
        )

        print(
            "Telegram: SUCCESS"
        )

        return True

    except Exception as e:

        print(
            "Telegram Error:",
            e
        )

        return False


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    choice = query.data


    # =====================================================
    # CANCEL
    # =====================================================

    if choice == "cancel":

        context.user_data.clear()

        await query.edit_message_text(
            "❌ تم إلغاء النشر."
        )

        return


    # =====================================================
    # GET TEMP DATA
    # =====================================================

    text = context.user_data.get(
        "price_text"
    )

    price = context.user_data.get(
        "price"
    )

    is_first_post_today = (
        context.user_data.get(
            "is_first_post_today",
            False
        )
    )


    if (
        not text
        or price is None
    ):

        await query.edit_message_text(
            "❌ السعر انتهى. "
            "ابعت السعر من جديد."
        )

        return


    # =====================================================
    # RESULTS
    # =====================================================

    telegram_success = False

    facebook_success = False


    # =====================================================
    # TELEGRAM + FACEBOOK
    # =====================================================

    if choice == "telegram_facebook":

        telegram_success = (
            await telegram_post(
                context,
                text
            )
        )

        facebook_success = (
            await facebook_post(
                text
            )
        )


    # =====================================================
    # TELEGRAM ONLY
    # =====================================================

    elif choice == "telegram_only":

        telegram_success = (
            await telegram_post(
                context,
                text
            )
        )


    # =====================================================
    # FACEBOOK ONLY
    # =====================================================

    elif choice == "facebook_only":

        facebook_success = (
            await facebook_post(
                text
            )
        )


    # =====================================================
    # CHECK SUCCESS
    # =====================================================

    successful_post = (
        telegram_success
        or facebook_success
    )


    # =====================================================
    # SAVE FIRST PRICE
    # =====================================================

    if (
        successful_post
        and is_first_post_today
    ):

        try:

            save_first_price_of_today(
                price
            )

        except Exception as e:

            print(
                "Gold History Save Error:",
                e
            )


    # =====================================================
    # RESULT MESSAGE
    # =====================================================

    if choice == "telegram_facebook":

        if (
            telegram_success
            and facebook_success
        ):

            result = (
                "✅ تم النشر "
                "في تليجرام وفيسبوك."
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


    else:

        result = (
            "❌ اختيار غير معروف."
        )


    # =====================================================
    # SHOW RESULT
    # =====================================================

    await query.edit_message_text(
        result
    )


    # =====================================================
    # CLEAR TEMP DATA
    # =====================================================

    context.user_data.clear()


# =========================================================
# MAIN
# =========================================================

def main():

    # ---------------------------------
    # DATABASE
    # ---------------------------------

    init_database()


    # ---------------------------------
    # TELEGRAM APP
    # ---------------------------------

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # ---------------------------------
    # START
    # ---------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    # ---------------------------------
    # ADMIN PHOTO
    # ---------------------------------

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo
        )
    )


    # ---------------------------------
    # TEXT
    # ---------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            receive
        )
    )


    # ---------------------------------
    # BUTTONS
    # ---------------------------------

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )


    print(
        "Bot Started..."
    )


    # ---------------------------------
    # START POLLING
    # ---------------------------------

    app.run_polling()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
