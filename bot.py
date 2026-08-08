import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import requests
import pymysql


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()

FACEBOOK_PAGE_ID = os.getenv(
    "FACEBOOK_PAGE_ID",
    ""
).strip()

FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_PAGE_TOKEN",
    ""
).strip()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    ""
).strip()

try:
    ADMIN_ID = int(
        os.getenv("ADMIN_ID", "0").strip()
    )
except ValueError:
    ADMIN_ID = 0


# =========================================================
# SETTINGS
# =========================================================

TIMEZONE = ZoneInfo("Africa/Cairo")

WEBSITE_LINK = (
    "https://link.gettap.co/alhussienyjewelry"
)

WHATSAPP_NUMBER = "201067365567"

WHATSAPP_LINK = (
    f"https://wa.me/{WHATSAPP_NUMBER}"
)

FACEBOOK_LINK = (
    "https://www.facebook.com/alhussienyjewelry"
)

INSTAGRAM_LINK = (
    "https://www.instagram.com/alhussienyjewelry"
)

MAPS_LINK = (
    "https://maps.app.goo.gl/1X6NJrNM4u1azpFR6"
)

SHOP_ADDRESS = (
    "📍 بورسعيد - شارع أسوان "
    "أمام صيدلية جلال"
)

HISTORY_FILE = "gold_history.json"


# =========================================================
# ENV CHECK
# =========================================================

def check_environment():

    print("================================")
    print("Starting Alhussieny Gold Bot")
    print("================================")

    if not BOT_TOKEN:
        raise Exception(
            "BOT_TOKEN is missing"
        )

    if not CHANNEL_ID:
        print(
            "WARNING: CHANNEL_ID is missing"
        )

    if ADMIN_ID == 0:
        raise Exception(
            "ADMIN_ID is missing or invalid"
        )

    print(
        f"ADMIN_ID = {ADMIN_ID}"
    )

    print(
        "DATABASE_URL = "
        + (
            "FOUND"
            if DATABASE_URL
            else "MISSING"
        )
    )

    print(
        "FACEBOOK_PAGE_ID = "
        + (
            "FOUND"
            if FACEBOOK_PAGE_ID
            else "MISSING"
        )
    )

    print(
        "FACEBOOK_PAGE_TOKEN = "
        + (
            "FOUND"
            if FACEBOOK_PAGE_ACCESS_TOKEN
            else "MISSING"
        )
    )


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL is missing"
        )

    url = urlparse(
        DATABASE_URL
    )

    return pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        database=url.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_database():

    try:

        connection = (
            get_db_connection()
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Products (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    category VARCHAR(255) NOT NULL,
                    Photo_id TEXT NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )

        connection.close()

        print(
            "Database: READY"
        )

    except Exception as e:

        print(
            "Database Initialization Error:",
            e,
        )


# =========================================================
# PRODUCTS
# =========================================================

def add_product(
    category,
    photo_id,
):

    connection = (
        get_db_connection()
    )

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
                    photo_id,
                ),
            )

    finally:

        connection.close()


def get_products(
    category,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id, category, Photo_id
                FROM Products
                WHERE LOWER(TRIM(category))
                = LOWER(TRIM(%s))
                ORDER BY id DESC
                """,
                (category,),
            )

            return cursor.fetchall()

    finally:

        connection.close()


def get_categories():

    connection = (
        get_db_connection()
    )

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
        price18,
    )


# =========================================================
# DATE
# =========================================================

def today_date():

    return datetime.now(
        TIMEZONE
    ).strftime(
        "%Y-%m-%d"
    )


def yesterday_date():

    yesterday = (
        datetime.now(TIMEZONE)
        - timedelta(days=1)
    )

    return yesterday.strftime(
        "%Y-%m-%d"
    )


# =========================================================
# HISTORY
# =========================================================

def load_history():

    if not os.path.exists(
        HISTORY_FILE
    ):
        return {}

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except Exception as e:

        print(
            "History Load Error:",
            e,
        )

        return {}


def save_history(history):

    try:

        temp_file = (
            HISTORY_FILE + ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                history,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_file,
            HISTORY_FILE,
        )

    except Exception as e:

        print(
            "History Save Error:",
            e,
        )


def get_today_first_price():

    history = load_history()

    return history.get(
        today_date()
    )


def get_yesterday_first_price():

    history = load_history()

    return history.get(
        yesterday_date()
    )


def save_first_price_of_today(
    price,
):

    history = load_history()

    today = today_date()

    if today in history:
        return False

    history[today] = round(
        price
    )

    save_history(
        history
    )

    print(
        f"First gold price saved: "
        f"{today} = {round(price)}"
    )

    return True


# =========================================================
# COMPARISON
# =========================================================

def create_comparison_line(
    current_price,
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

    if difference < 0:

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
    comparison=None,
):

    lines = []

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
        SHOP_ADDRESS
    )

    lines.append("")

    lines.append(
        "🌐 "
        + WEBSITE_LINK
    )

    return "\n".join(
        lines
    )


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(update):

    if not update.effective_user:
        return False

    return (
        update.effective_user.id
        == ADMIN_ID
    )


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "💰 أسعار الذهب",
                callback_data="gold_prices",
            )
        ],

        [
            InlineKeyboardButton(
                "💍 المنتجات",
                callback_data="products",
            )
        ],

        [
            InlineKeyboardButton(
                "📍 عنوان المحل",
                callback_data="location",
            )
        ],

        [
            InlineKeyboardButton(
                "🌐 موقعنا الإلكتروني",
                url=WEBSITE_LINK,
            )
        ],

        [
            InlineKeyboardButton(
                "📞 واتساب",
                url=WHATSAPP_LINK,
            ),

            InlineKeyboardButton(
                "📞 اتصال",
                url="tel:+201067365567",
            ),
        ],

        [
            InlineKeyboardButton(
                "📘 فيسبوك",
                url=FACEBOOK_LINK,
            ),

            InlineKeyboardButton(
                "📸 إنستجرام",
                url=INSTAGRAM_LINK,
            ),
        ],

    ]

    return InlineKeyboardMarkup(
        keyboard
    )


# =========================================================
# PRODUCTS MENU
# =========================================================

def products_menu():

    try:

        categories = (
            get_categories()
        )

    except Exception as e:

        print(
            "Categories Menu Error:",
            e,
        )

        categories = []


    keyboard = []

    for category in categories:

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"💍 {category}",
                    callback_data=(
                        "category:"
                        + category
                    ),
                )
            ]
        )


    if not keyboard:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "❌ لا توجد أقسام",
                    callback_data="noop",
                )
            ]
        )


    keyboard.append(
        [
            InlineKeyboardButton(
                "🏠 الرئيسية",
                callback_data="home",
            )
        ]
    )

    return InlineKeyboardMarkup(
        keyboard
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "💎 أهلاً بيك في مجوهرات الحسيني\n\n"
        "✨ كل ما يخص الذهب والمجوهرات في بورسعيد\n\n"
        "اختار من القائمة:",
        reply_markup=main_menu(),
    )


# =========================================================
# SHOW ID - ADMIN ONLY
# =========================================================

async def show_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user_id = (
        update.effective_user.id
    )

    if user_id != ADMIN_ID:

        await update.message.reply_text(
            "❌ الأمر ده متاح للأدمن فقط."
        )

        return

    await update.message.reply_text(
        "🆔 Telegram ID الخاص بك:\n\n"
        f"{user_id}"
    )


# =========================================================
# SHOW GOLD PRICES
# =========================================================

async def show_gold_prices(
    query,
):

    first_price = (
        get_today_first_price()
    )

    if first_price is None:

        await query.edit_message_text(
            "💰 أسعار الذهب\n\n"
            "⏳ لم يتم نشر سعر اليوم حتى الآن.\n\n"
            "تابعنا لمعرفة آخر الأسعار.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🏠 الرئيسية",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )

        return


    p24, p21, p18 = calc(
        first_price
    )

    text = create_price_text(
        p24,
        p21,
        p18,
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 الرئيسية",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


# =========================================================
# SHOW LOCATION
# =========================================================

async def show_location(
    query,
):

    keyboard = [

        [
            InlineKeyboardButton(
                "📍 افتح الموقع على الخريطة",
                url=MAPS_LINK,
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 الرئيسية",
                callback_data="home",
            )
        ],

    ]

    await query.edit_message_text(
        "📍 عنوان مجوهرات الحسيني\n\n"
        f"{SHOP_ADDRESS}\n\n"
        "اضغط على الزر لفتح الموقع:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# SHOW CATEGORY
# =========================================================

async def show_category(
    query,
    category,
):

    try:

        products = get_products(
            category
        )

    except Exception as e:

        print(
            "Category Error:",
            e,
        )

        await query.edit_message_text(
            "❌ حصل خطأ في قاعدة البيانات.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "↩️ المنتجات",
                            callback_data="products",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 الرئيسية",
                            callback_data="home",
                        )
                    ],
                ]
            ),
        )

        return


    if not products:

        await query.edit_message_text(
            f"❌ مفيش منتجات في قسم:\n"
            f"{category}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "↩️ المنتجات",
                            callback_data="products",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 الرئيسية",
                            callback_data="home",
                        )
                    ],
                ]
            ),
        )

        return


    await query.edit_message_text(
        f"💎 قسم {category}\n"
        f"عدد المنتجات: {len(products)}"
    )


    # إرسال الصور
    for product in products:

        try:

            await query.message.reply_photo(
                photo=product["Photo_id"]
            )

        except Exception as e:

            print(
                "Send Product Photo Error:",
                e,
            )


    await query.message.reply_text(
        "اختار من القائمة:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "↩️ المنتجات",
                        callback_data="products",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 الرئيسية",
                        callback_data="home",
                    )
                ],
            ]
        ),
    )


# =========================================================
# ADMIN PHOTO
# =========================================================

async def receive_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not is_admin(update):

        await update.message.reply_text(
            "❌ غير مسموح لك بإضافة منتجات."
        )

        return

    if not update.message.photo:
        return

    photo = (
        update.message.photo[-1]
    )

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
            photo_id,
        )

        await update.message.reply_text(
            f"✅ تم حفظ المنتج.\n\n"
            f"📂 القسم: {category}",
            reply_markup=main_menu(),
        )

    except Exception as e:

        print(
            "Add Product Error:",
            e,
        )

        await update.message.reply_text(
            "❌ حصل خطأ أثناء حفظ الصورة."
        )


# =========================================================
# RECEIVE TEXT
# =========================================================

async def receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user_id = (
        update.effective_user.id
    )

    text = (
        update.message.text
        or ""
    ).strip()


    # =====================================================
    # PRICE
    # =====================================================

    try:

        price = float(text)

        is_price = True

    except ValueError:

        is_price = False
        price = None


    if is_price:

        # ADMIN ONLY
        if user_id != ADMIN_ID:

            await update.message.reply_text(
                "❌ أسعار الذهب متاحة "
                "للأدمن فقط."
            )

            return


        p24, p21, p18 = calc(
            price
        )

        today_first_price = (
            get_today_first_price()
        )

        is_first_post_today = (
            today_first_price is None
        )

        comparison = None

        if is_first_post_today:

            comparison = (
                create_comparison_line(
                    price
                )
            )


        price_text = create_price_text(
            p24,
            p21,
            p18,
            comparison,
        )


        context.user_data[
            "price_text"
        ] = price_text

        context.user_data[
            "price"
        ] = round(price)

        context.user_data[
            "is_first_post_today"
        ] = is_first_post_today


        keyboard = [

            [
                InlineKeyboardButton(
                    "📱 تليجرام + فيسبوك",
                    callback_data=(
                        "telegram_facebook"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "📱 تليجرام فقط",
                    callback_data=(
                        "telegram_only"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "📘 فيسبوك فقط",
                    callback_data=(
                        "facebook_only"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ],

        ]


        await update.message.reply_text(
            f"السعر: {round(price)}\n\n"
            "📢 عايز تنشر الأسعار فين؟",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return


    # =====================================================
    # CATEGORY TEXT
    # =====================================================

    try:

        categories = (
            get_categories()
        )

        for category in categories:

            if (
                category.strip().lower()
                == text.strip().lower()
            ):

                products = (
                    get_products(
                        category
                    )
                )

                if not products:

                    await update.message.reply_text(
                        "❌ مفيش منتجات في القسم."
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
                            e,
                        )

                return

    except Exception as e:

        print(
            "Category Search Error:",
            e,
        )


    await update.message.reply_text(
        "استخدم القائمة الموجودة تحت `/start` 👇",
        reply_markup=main_menu(),
    )


# =========================================================
# FACEBOOK
# =========================================================

async def facebook_post(
    text,
):

    if not FACEBOOK_PAGE_ID:

        print(
            "Facebook Page ID missing"
        )

        return False


    if not FACEBOOK_PAGE_ACCESS_TOKEN:

        print(
            "Facebook Page Token missing"
        )

        return False


    url = (
        "https://graph.facebook.com/v23.0/"
        f"{FACEBOOK_PAGE_ID}/feed"
    )


    data = {

        "message": text,

        "access_token":
            FACEBOOK_PAGE_ACCESS_TOKEN,

    }


    try:

        response = requests.post(
            url,
            data=data,
            timeout=20,
        )


        if response.status_code == 200:

            print(
                "Facebook: SUCCESS"
            )

            return True


        print(
            "Facebook Error:",
            response.status_code,
            response.text,
        )

        return False


    except Exception as e:

        print(
            "Facebook Request Error:",
            e,
        )

        return False


# =========================================================
# TELEGRAM CHANNEL
# =========================================================

async def telegram_post(
    context,
    text,
):

    if not CHANNEL_ID:

        print(
            "CHANNEL_ID missing"
        )

        return False


    try:

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
        )

        print(
            "Telegram Channel: SUCCESS"
        )

        return True


    except Exception as e:

        print(
            "Telegram Channel Error:",
            e,
        )

        return False


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = (
        update.callback_query
    )

    await query.answer()

    choice = query.data


    # =====================================================
    # HOME
    # =====================================================

    if choice == "home":

        await query.edit_message_text(
            "💎 مجوهرات الحسيني\n\n"
            "✨ أهلاً بيك، اختار من القائمة:",
            reply_markup=main_menu(),
        )

        return


    # =====================================================
    # PRODUCTS
    # =====================================================

    if choice == "products":

        await query.edit_message_text(
            "💍 منتجات مجوهرات الحسيني\n\n"
            "اختار القسم:",
            reply_markup=products_menu(),
        )

        return


    # =====================================================
    # GOLD PRICES
    # =====================================================

    if choice == "gold_prices":

        await show_gold_prices(
            query
        )

        return


    # =====================================================
    # LOCATION
    # =====================================================

    if choice == "location":

        await show_location(
            query
        )

        return


    # =====================================================
    # NOOP
    # =====================================================

    if choice == "noop":

        await query.answer(
            "لا توجد أقسام حاليًا."
        )

        return


    # =====================================================
    # CATEGORY
    # =====================================================

    if choice.startswith(
        "category:"
    ):

        category = choice[
            len("category:"):
        ]

        await show_category(
            query,
            category,
        )

        return


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
    # PRICE DATA
    # =====================================================

    text = (
        context.user_data.get(
            "price_text"
        )
    )

    price = (
        context.user_data.get(
            "price"
        )
    )

    is_first_post_today = (
        context.user_data.get(
            "is_first_post_today",
            False,
        )
    )


    if not text or price is None:

        await query.edit_message_text(
            "❌ السعر انتهى. "
            "ابعت السعر من جديد."
        )

        return


    telegram_success = False

    facebook_success = False


    # =====================================================
    # TELEGRAM + FACEBOOK
    # =====================================================

    if choice == "telegram_facebook":

        telegram_success = (
            await telegram_post(
                context,
                text,
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
                text,
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


    else:

        await query.edit_message_text(
            "❌ اختيار غير معروف."
        )

        return


    # =====================================================
    # SAVE FIRST PRICE
    # =====================================================

    successful_post = (
        telegram_success
        or facebook_success
    )


    if (
        successful_post
        and is_first_post_today
    ):

        save_first_price_of_today(
            price
        )


    # =====================================================
    # RESULT
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
                "⚠️ تم النشر "
                "في تليجرام فقط.\n"
                "❌ حصل خطأ في فيسبوك."
            )

        elif facebook_success:

            result = (
                "⚠️ تم النشر "
                "في فيسبوك فقط.\n"
                "❌ حصل خطأ في تليجرام."
            )

        else:

            result = (
                "❌ حصل خطأ في النشر "
                "على الاثنين."
            )


    elif choice == "telegram_only":

        result = (
            "✅ تم النشر في تليجرام."
            if telegram_success
            else
            "❌ حصل خطأ في النشر "
            "في تليجرام."
        )


    elif choice == "facebook_only":

        result = (
            "✅ تم النشر في فيسبوك."
            if facebook_success
            else
            "❌ حصل خطأ في النشر "
            "في فيسبوك."
        )


    await query.edit_message_text(
        result,
        reply_markup=main_menu(),
    )

    context.user_data.clear()


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    print(
        "================================"
    )

    print(
        "BOT ERROR:",
        context.error,
    )

    print(
        "================================"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    check_environment()

    init_database()


    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # =====================================================
    # COMMANDS
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "id",
            show_id,
        )
    )


    # =====================================================
    # PHOTOS
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            receive_photo,
        )
    )


    # =====================================================
    # TEXT
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            receive,
        )
    )


    # =====================================================
    # BUTTONS
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )


    # =====================================================
    # ERRORS
    # =====================================================

    app.add_error_handler(
        error_handler
    )


    # =====================================================
    # START
    # =====================================================

    print(
        "Bot Started..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
