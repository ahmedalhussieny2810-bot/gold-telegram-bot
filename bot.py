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

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

CHANNEL_ID = os.getenv(
    "CHANNEL_ID",
    ""
).strip()

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
        os.getenv(
            "ADMIN_ID",
            "0"
        ).strip()
    )
except ValueError:
    ADMIN_ID = 0


# =========================================================
# SETTINGS
# =========================================================

TIMEZONE = ZoneInfo(
    "Africa/Cairo"
)

WEBSITE_LINK = (
    "https://link.gettap.co/alhussienyjewelry"
)

TELEGRAM_CHANNEL_LINK = (
    "https://t.me/alhussienyjewelry"
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

WHATSAPP_LINK = (
    "https://wa.me/201067365567"
)

PHONE_NUMBER = (
    "01067365567"
)

HISTORY_FILE = (
    "gold_history.json"
)

LATEST_PRICE_FILE = (
    "latest_gold_price.json"
)


# =========================================================
# STARTUP CHECK
# =========================================================

def check_environment():

    print("================================")
    print("Starting Alhussieny Gold Bot")
    print("================================")

    if not BOT_TOKEN:
        raise Exception(
            "BOT_TOKEN is missing"
        )

    if ADMIN_ID == 0:
        raise Exception(
            "ADMIN_ID is missing or invalid"
        )

    print(
        f"ADMIN_ID = {ADMIN_ID}"
    )

    if DATABASE_URL:
        print(
            "DATABASE_URL = FOUND"
        )
    else:
        print(
            "DATABASE_URL = MISSING"
        )

    if FACEBOOK_PAGE_ID:
        print(
            "FACEBOOK_PAGE_ID = FOUND"
        )
    else:
        print(
            "FACEBOOK_PAGE_ID = MISSING"
        )

    if FACEBOOK_PAGE_ACCESS_TOKEN:
        print(
            "FACEBOOK_PAGE_TOKEN = FOUND"
        )
    else:
        print(
            "FACEBOOK_PAGE_TOKEN = MISSING"
        )


# =========================================================
# DATABASE CONNECTION
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


# =========================================================
# DATABASE INIT
# =========================================================

def init_database():

    try:

        connection = (
            get_db_connection()
        )

        with connection.cursor() as cursor:

            # PRODUCTS
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Products (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    category VARCHAR(255) NOT NULL,
                    Photo_id TEXT NOT NULL,
                    created_at DATETIME NULL,
                    PRIMARY KEY (id)
                )
                """
            )

            # CATEGORIES
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Categories (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    name VARCHAR(255) NOT NULL,
                    created_at DATETIME NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY unique_category_name (name)
                )
                """
            )

            # USERS
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Users (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    telegram_id BIGINT NOT NULL,
                    username VARCHAR(255) NULL,
                    first_name VARCHAR(255) NULL,
                    last_name VARCHAR(255) NULL,
                    started_at DATETIME NULL,
                    last_seen DATETIME NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY unique_telegram_id (telegram_id)
                )
                """
            )

            # MIGRATE OLD CATEGORIES
            cursor.execute(
                """
                SELECT DISTINCT category
                FROM Products
                WHERE category IS NOT NULL
                AND TRIM(category) != ''
                """
            )

            old_categories = cursor.fetchall()

            for row in old_categories:

                try:

                    cursor.execute(
                        """
                        INSERT IGNORE INTO Categories
                        (name, created_at)
                        VALUES (%s, %s)
                        """,
                        (
                            row["category"],
                            datetime.now(
                                TIMEZONE
                            ),
                        ),
                    )

                except Exception as e:

                    print(
                        "Category Migration Error:",
                        e,
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
# USERS
# =========================================================

def register_user(
    user,
):

    if not user:
        return

    connection = (
        get_db_connection()
    )

    try:

        now = datetime.now(
            TIMEZONE
        ).replace(
            tzinfo=None
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO Users
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    started_at,
                    last_seen
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                ON DUPLICATE KEY UPDATE
                    username = VALUES(username),
                    first_name = VALUES(first_name),
                    last_name = VALUES(last_name),
                    last_seen = VALUES(last_seen)
                """,
                (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    now,
                    now,
                ),
            )

    finally:

        connection.close()


def get_users_count():

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM Users
                """
            )

            row = cursor.fetchone()

            return row["total"]

    finally:

        connection.close()


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

        now = datetime.now(
            TIMEZONE
        ).replace(
            tzinfo=None
        )

        with connection.cursor() as cursor:

            # Ensure category exists
            cursor.execute(
                """
                INSERT IGNORE INTO Categories
                (name, created_at)
                VALUES (%s, %s)
                """,
                (
                    category,
                    now,
                ),
            )

            cursor.execute(
                """
                INSERT INTO Products
                (
                    category,
                    Photo_id,
                    created_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    category,
                    photo_id,
                    now,
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
                SELECT
                    id,
                    category,
                    Photo_id,
                    created_at
                FROM Products
                WHERE LOWER(TRIM(category))
                =
                LOWER(TRIM(%s))
                ORDER BY id DESC
                """,
                (
                    category,
                ),
            )

            return cursor.fetchall()

    finally:

        connection.close()


def get_all_products():

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    category,
                    Photo_id,
                    created_at
                FROM Products
                ORDER BY id DESC
                """
            )

            return cursor.fetchall()

    finally:

        connection.close()


def get_products_count():

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM Products
                """
            )

            row = cursor.fetchone()

            return row["total"]

    finally:

        connection.close()


def delete_product(
    product_id,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM Products
                WHERE id = %s
                """,
                (
                    product_id,
                ),
            )

            return cursor.rowcount > 0

    finally:

        connection.close()


# =========================================================
# CATEGORIES
# =========================================================

def get_categories():

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    name
                FROM Categories
                ORDER BY name
                """
            )

            return cursor.fetchall()

    finally:

        connection.close()


def get_categories_count():

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM Categories
                """
            )

            row = cursor.fetchone()

            return row["total"]

    finally:

        connection.close()


def get_category_by_id(
    category_id,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id, name
                FROM Categories
                WHERE id = %s
                """,
                (
                    category_id,
                ),
            )

            return cursor.fetchone()

    finally:

        connection.close()


def category_exists(
    category,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM Categories
                WHERE LOWER(TRIM(name))
                =
                LOWER(TRIM(%s))
                """,
                (
                    category,
                ),
            )

            row = cursor.fetchone()

            return row["total"] > 0

    finally:

        connection.close()


def add_category(
    category,
):

    connection = (
        get_db_connection()
    )

    try:

        now = datetime.now(
            TIMEZONE
        ).replace(
            tzinfo=None
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO Categories
                (name, created_at)
                VALUES (%s, %s)
                """,
                (
                    category,
                    now,
                ),
            )

            return True

    except pymysql.IntegrityError:

        return False

    finally:

        connection.close()


def rename_category(
    category_id,
    new_name,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT name
                FROM Categories
                WHERE id = %s
                """,
                (
                    category_id,
                ),
            )

            row = cursor.fetchone()

            if not row:
                return False

            old_name = row["name"]

            cursor.execute(
                """
                UPDATE Categories
                SET name = %s
                WHERE id = %s
                """,
                (
                    new_name,
                    category_id,
                ),
            )

            cursor.execute(
                """
                UPDATE Products
                SET category = %s
                WHERE LOWER(TRIM(category))
                =
                LOWER(TRIM(%s))
                """,
                (
                    new_name,
                    old_name,
                ),
            )

            return True

    except pymysql.IntegrityError:

        return False

    finally:

        connection.close()


def delete_category(
    category_id,
):

    connection = (
        get_db_connection()
    )

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT name
                FROM Categories
                WHERE id = %s
                """,
                (
                    category_id,
                ),
            )

            category = cursor.fetchone()

            if not category:
                return "not_found"

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM Products
                WHERE LOWER(TRIM(category))
                =
                LOWER(TRIM(%s))
                """,
                (
                    category["name"],
                ),
            )

            row = cursor.fetchone()

            if row["total"] > 0:

                return "has_products"

            cursor.execute(
                """
                DELETE FROM Categories
                WHERE id = %s
                """,
                (
                    category_id,
                ),
            )

            return "deleted"

    finally:

        connection.close()


# =========================================================
# CATEGORY LOOKUP FOR PUBLIC MENU
# =========================================================

def get_category_from_callback(
    callback_data,
):

    try:

        category_id = int(
            callback_data.split(
                ":",
                1
            )[1]
        )

    except Exception:

        return None

    return get_category_by_id(
        category_id
    )


# =========================================================
# GOLD CALCULATION
# =========================================================

def calc(
    price,
):

    price21 = round(
        price
    )

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
        datetime.now(
            TIMEZONE
        )
        - timedelta(
            days=1
        )
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

            return json.load(
                file
            )

    except Exception as e:

        print(
            "History Load Error:",
            e,
        )

        return {}


def save_history(
    history,
):

    try:

        temp_file = (
            HISTORY_FILE
            + ".tmp"
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
# LATEST GOLD PRICE
# =========================================================

def get_latest_gold_price():

    if not os.path.exists(
        LATEST_PRICE_FILE
    ):

        return None

    try:

        with open(
            LATEST_PRICE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        return data.get(
            "price"
        )

    except Exception as e:

        print(
            "Latest Price Load Error:",
            e,
        )

        return None


def get_latest_price_updated_at():

    if not os.path.exists(
        LATEST_PRICE_FILE
    ):

        return None

    try:

        with open(
            LATEST_PRICE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        return data.get(
            "updated_at"
        )

    except Exception:

        return None


def save_latest_gold_price(
    price,
):

    try:

        with open(
            LATEST_PRICE_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                {
                    "price": round(
                        price
                    ),
                    "updated_at": datetime.now(
                        TIMEZONE
                    ).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

        print(
            f"Latest gold price saved: "
            f"{round(price)}"
        )

    except Exception as e:

        print(
            "Latest Price Save Error:",
            e,
        )


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
        "📍 بورسعيد - شارع أسوان "
        "أمام صيدلية جلال"
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
# MAIN MENU
# =========================================================

def main_menu(
    admin=False,
):

    keyboard = [

        [
            InlineKeyboardButton(
                "💎 أسعار الذهب",
                callback_data="gold_prices",
            )
        ],

        [
            InlineKeyboardButton(
                "💍 المنتجات",
                callback_data="products",
            )
        ],
    ]

    if admin:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "👑 لوحة التحكم",
                    callback_data="admin_panel",
                )
            ]
        )

    keyboard.extend(
        [

            [
                InlineKeyboardButton(
                    "📢 قناة التليجرام",
                    url=TELEGRAM_CHANNEL_LINK,
                )
            ],

            [
                InlineKeyboardButton(
                    "📍 موقع المحل",
                    url=MAPS_LINK,
                ),

                InlineKeyboardButton(
                    "🌐 الموقع",
                    url=WEBSITE_LINK,
                ),
            ],

            [
                InlineKeyboardButton(
                    "💬 واتساب",
                    url=WHATSAPP_LINK,
                ),

                InlineKeyboardButton(
                    "📞 رقم المحل",
                    callback_data="phone",
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
    )

    return InlineKeyboardMarkup(
        keyboard
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

def admin_panel_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "📊 الإحصائيات",
                    callback_data="admin_stats",
                )
            ],

            [
                InlineKeyboardButton(
                    "💰 إدارة أسعار الذهب",
                    callback_data="admin_gold",
                )
            ],

            [
                InlineKeyboardButton(
                    "💍 إدارة المنتجات",
                    callback_data="admin_products",
                )
            ],

            [
                InlineKeyboardButton(
                    "📂 إدارة الأقسام",
                    callback_data="admin_categories",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ الرئيسية",
                    callback_data="home",
                )
            ],

        ]
    )


# =========================================================
# ADMIN GOLD MENU
# =========================================================

def admin_gold_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "✏️ تحديث السعر",
                    callback_data="admin_update_gold",
                )
            ],

            [
                InlineKeyboardButton(
                    "📜 سجل الأسعار",
                    callback_data="admin_gold_history",
                )
            ],

            [
                InlineKeyboardButton(
                    "📢 نشر السعر",
                    callback_data="admin_publish_gold",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin_panel",
                )
            ],

        ]
    )


# =========================================================
# ADMIN PRODUCTS MENU
# =========================================================

def admin_products_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "➕ إضافة منتج",
                    callback_data="admin_add_product",
                )
            ],

            [
                InlineKeyboardButton(
                    "📋 عرض المنتجات",
                    callback_data="admin_view_products",
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 حذف منتج",
                    callback_data="admin_delete_product",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin_panel",
                )
            ],

        ]
    )


# =========================================================
# ADMIN CATEGORIES MENU
# =========================================================

def admin_categories_keyboard():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "➕ إضافة قسم",
                    callback_data="admin_add_category",
                )
            ],

            [
                InlineKeyboardButton(
                    "📋 عرض الأقسام",
                    callback_data="admin_view_categories",
                )
            ],

            [
                InlineKeyboardButton(
                    "✏️ تغيير اسم قسم",
                    callback_data="admin_rename_category",
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 حذف قسم",
                    callback_data="admin_delete_category",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin_panel",
                )
            ],

        ]
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

    context.user_data.clear()

    try:

        register_user(
            update.effective_user
        )

    except Exception as e:

        print(
            "Register User Error:",
            e,
        )

    text = (
        "💎 مجوهرات الحسيني\n\n"
        "أهلاً بيك في البوت الرسمي "
        "لمجوهرات الحسيني - بورسعيد ✨\n\n"
        "من هنا تقدر تعرف أحدث أسعار الذهب، "
        "وتتصفح منتجاتنا وتتواصل معانا مباشرة.\n\n"
        "اختار من القائمة 👇"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu(
            admin=is_admin(update)
        ),
    )


# =========================================================
# ID - ADMIN ONLY
# =========================================================

async def show_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not is_admin(update):

        await update.message.reply_text(
            "❌ الأمر ده متاح للأدمن فقط."
        )

        return

    await update.message.reply_text(
        "🆔 Telegram ID الخاص بالأدمن:\n\n"
        f"{ADMIN_ID}"
    )


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(
    update: Update,
):

    if not update.effective_user:
        return False

    return (
        update.effective_user.id
        == ADMIN_ID
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

    action = context.user_data.get(
        "admin_action"
    )

    # =====================================================
    # ADD PRODUCT
    # =====================================================

    if action == "awaiting_product_photo":

        category = context.user_data.get(
            "product_category"
        )

        if not category:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ حصل خطأ.\n"
                "ابدأ من لوحة التحكم من جديد.",
                reply_markup=admin_products_keyboard(),
            )

            return

        photo = (
            update.message.photo[-1]
        )

        try:

            add_product(
                category,
                photo.file_id,
            )

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم إضافة المنتج بنجاح.\n\n"
                f"📂 القسم: {category}",
                reply_markup=admin_products_keyboard(),
            )

        except Exception as e:

            print(
                "Add Product Error:",
                e,
            )

            context.user_data.clear()

            await update.message.reply_text(
                "❌ حصل خطأ أثناء حفظ المنتج.",
                reply_markup=admin_products_keyboard(),
            )

        return

    # =====================================================
    # OLD METHOD
    # =====================================================

    photo = (
        update.message.photo[-1]
    )

    category = (
        update.message.caption
        or ""
    ).strip()

    if not category:

        await update.message.reply_text(
            "❌ اكتب اسم القسم في Caption الصورة.\n\n"
            "مثال:\n"
            "خواتم"
        )

        return

    try:

        add_product(
            category,
            photo.file_id,
        )

        await update.message.reply_text(
            "✅ تم حفظ المنتج.\n\n"
            f"📂 القسم: {category}"
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
# PUBLIC PRODUCTS MENU
# =========================================================

async def show_products_menu(
    query,
):

    try:

        categories = (
            get_categories()
        )

    except Exception as e:

        print(
            "Categories Error:",
            e,
        )

        await query.edit_message_text(
            "❌ حصل خطأ في قاعدة البيانات.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ الرئيسية",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )

        return

    if not categories:

        await query.edit_message_text(
            "💎 المنتجات\n\n"
            "لا توجد منتجات مضافة حاليًا.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ الرئيسية",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )

        return

    keyboard = []

    for category in categories:

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"💎 {category['name']}",
                    callback_data=(
                        "category:"
                        + str(category["id"])
                    ),
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "⬅️ الرئيسية",
                callback_data="home",
            )
        ]
    )

    await query.edit_message_text(
        "💎 منتجات مجوهرات الحسيني\n\n"
        "اختار القسم:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# SEND PRODUCTS
# =========================================================

async def send_products(
    query,
    category,
):

    try:

        products = get_products(
            category["name"]
        )

    except Exception as e:

        print(
            "Get Products Error:",
            e,
        )

        await query.message.reply_text(
            "❌ حصل خطأ في قاعدة البيانات."
        )

        return

    if not products:

        await query.edit_message_text(
            f"📂 {category['name']}\n\n"
            "لا توجد منتجات في هذا القسم.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ المنتجات",
                            callback_data="products",
                        )
                    ]
                ]
            ),
        )

        return

    await query.message.reply_text(
        f"💎 منتجات قسم {category['name']}\n"
        f"عدد الصور: {len(products)}"
    )

    for product in products:

        try:

            await query.message.reply_photo(
                photo=product["Photo_id"]
            )

        except Exception as e:

            print(
                "Send Photo Error:",
                e,
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

    print(
        f"Message received | "
        f"USER_ID={user_id} | "
        f"TEXT={text}"
    )

    # =====================================================
    # REGISTER USER
    # =====================================================

    try:

        register_user(
            update.effective_user
        )

    except Exception as e:

        print(
            "Register User Error:",
            e,
        )

    admin_action = context.user_data.get(
        "admin_action"
    )

    # =====================================================
    # ADMIN UPDATE GOLD
    # =====================================================

    if admin_action == "awaiting_gold_price":

        if user_id != ADMIN_ID:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        try:

            price = float(text)

            if price <= 0:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ السعر غير صحيح.\n\n"
                "اكتب سعر عيار 21 فقط.\n"
                "مثال:\n"
                "7000"
            )

            return

        p24, p21, p18 = calc(
            price
        )

        save_latest_gold_price(
            price
        )

        if get_today_first_price() is None:

            save_first_price_of_today(
                price
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تحديث سعر الذهب بنجاح.\n\n"
            f"🟡 عيار 24: {p24} جنيه\n"
            f"🟡 عيار 21: {p21} جنيه\n"
            f"🟡 عيار 18: {p18} جنيه\n\n"
            "تقدر دلوقتي تنشر السعر.",
            reply_markup=admin_gold_keyboard(),
        )

        return

    # =====================================================
    # ADMIN ADD CATEGORY
    # =====================================================

    if admin_action == "awaiting_category_name":

        if user_id != ADMIN_ID:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        category = text.strip()

        if not category:

            await update.message.reply_text(
                "❌ اكتب اسم القسم."
            )

            return

        if category_exists(category):

            context.user_data.clear()

            await update.message.reply_text(
                "⚠️ القسم موجود بالفعل.",
                reply_markup=admin_categories_keyboard(),
            )

            return

        if add_category(category):

            context.user_data.clear()

            await update.message.reply_text(
                "✅ تم إنشاء القسم بنجاح.\n\n"
                f"📂 {category}\n\n"
                "تقدر دلوقتي تضيف منتجات بداخله.",
                reply_markup=admin_categories_keyboard(),
            )

        else:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ حصل خطأ أو القسم موجود بالفعل.",
                reply_markup=admin_categories_keyboard(),
            )

        return

    # =====================================================
    # ADMIN ADD PRODUCT - CATEGORY
    # =====================================================

    if admin_action == "awaiting_product_category":

        if user_id != ADMIN_ID:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        category = text.strip()

        if not category:

            await update.message.reply_text(
                "❌ اكتب اسم القسم."
            )

            return

        if not category_exists(category):

            await update.message.reply_text(
                "❌ القسم غير موجود.\n\n"
                "اكتب اسم قسم موجود أو أضفه من إدارة الأقسام."
            )

            return

        context.user_data[
            "product_category"
        ] = category

        context.user_data[
            "admin_action"
        ] = "awaiting_product_photo"

        await update.message.reply_text(
            "📸 تمام.\n\n"
            f"📂 القسم: {category}\n\n"
            "ابعت صورة المنتج الآن."
        )

        return

    # =====================================================
    # ADMIN RENAME CATEGORY
    # =====================================================

    if admin_action == "awaiting_category_rename":

        if user_id != ADMIN_ID:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        category_id = context.user_data.get(
            "rename_category_id"
        )

        new_name = text.strip()

        if not category_id:

            context.user_data.clear()

            return

        if not new_name:

            await update.message.reply_text(
                "❌ اكتب الاسم الجديد."
            )

            return

        if category_exists(new_name):

            await update.message.reply_text(
                "⚠️ الاسم ده مستخدم بالفعل.\n"
                "اكتب اسم مختلف."
            )

            return

        try:

            success = rename_category(
                category_id,
                new_name,
            )

            context.user_data.clear()

            if success:

                await update.message.reply_text(
                    "✅ تم تغيير اسم القسم بنجاح.\n\n"
                    f"📂 الاسم الجديد: {new_name}",
                    reply_markup=admin_categories_keyboard(),
                )

            else:

                await update.message.reply_text(
                    "❌ حصل خطأ أثناء تغيير الاسم.",
                    reply_markup=admin_categories_keyboard(),
                )

        except Exception as e:

            print(
                "Rename Category Error:",
                e,
            )

            context.user_data.clear()

            await update.message.reply_text(
                "❌ حصل خطأ أثناء تغيير اسم القسم.",
                reply_markup=admin_categories_keyboard(),
            )

        return

    # =====================================================
    # CHECK PRICE
    # =====================================================

    try:

        price = float(text)

        is_price = True

    except ValueError:

        is_price = False
        price = None

    # =====================================================
    # OLD GOLD PRICE METHOD
    # =====================================================

    if is_price:

        if user_id != ADMIN_ID:

            await update.message.reply_text(
                "❌ أسعار الذهب متاحة "
                "للأدمن فقط."
            )

            return

        p24, p21, p18 = calc(
            price
        )

        is_first_post_today = (
            get_today_first_price()
            is None
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
                    callback_data="telegram_facebook",
                )
            ],

            [
                InlineKeyboardButton(
                    "📱 تليجرام فقط",
                    callback_data="telegram_only",
                )
            ],

            [
                InlineKeyboardButton(
                    "📘 فيسبوك فقط",
                    callback_data="facebook_only",
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
    # CATEGORY TEXT SEARCH
    # =====================================================

    try:

        categories = get_categories()

        found_category = None

        for category in categories:

            if (
                category["name"].strip().lower()
                == text.strip().lower()
            ):

                found_category = category
                break

        if found_category:

            await send_products(
                update,
                found_category,
            )

            return

    except Exception as e:

        print(
            "Category Search Error:",
            e,
        )

    await update.message.reply_text(
        "❌ مش فاهم طلبك.\n\n"
        "استخدم /start لفتح القائمة.",
        reply_markup=main_menu(
            admin=is_admin(update)
        ),
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
# ADMIN STATS
# =========================================================

async def show_admin_stats(
    query,
):

    try:

        users_count = get_users_count()

        products_count = get_products_count()

        categories_count = get_categories_count()

        latest_price = get_latest_gold_price()

        updated_at = get_latest_price_updated_at()

    except Exception as e:

        print(
            "Stats Error:",
            e,
        )

        await query.edit_message_text(
            "❌ حصل خطأ أثناء تحميل الإحصائيات.",
            reply_markup=admin_panel_keyboard(),
        )

        return

    if latest_price is None:

        gold_text = (
            "لا يوجد سعر محفوظ"
        )

    else:

        p24, p21, p18 = calc(
            latest_price
        )

        gold_text = (
            f"🟡 24: {p24}\n"
            f"🟡 21: {p21}\n"
            f"🟡 18: {p18}"
        )

    text = (
        "📊 إحصائيات مجوهرات الحسيني\n\n"

        f"👥 المستخدمين: "
        f"{users_count}\n\n"

        f"💍 المنتجات: "
        f"{products_count}\n\n"

        f"📂 الأقسام: "
        f"{categories_count}\n\n"

        "💰 آخر أسعار الذهب:\n"
        f"{gold_text}\n\n"
    )

    if updated_at:

        text += (
            f"🕐 آخر تحديث:\n"
            f"{updated_at}"
        )

    else:

        text += (
            "🕐 لم يتم تحديث السعر بعد."
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 تحديث",
                        callback_data="admin_stats",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ لوحة التحكم",
                        callback_data="admin_panel",
                    )
                ],
            ]
        ),
    )


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

    print(
        f"Button pressed: {choice}"
    )

    # =====================================================
    # HOME
    # =====================================================

    if choice == "home":

        context.user_data.clear()

        await query.edit_message_text(
            "💎 مجوهرات الحسيني\n\n"
            "أهلاً بيك في البوت الرسمي "
            "لمجوهرات الحسيني - بورسعيد ✨\n\n"
            "اختار من القائمة 👇",
            reply_markup=main_menu(
                admin=is_admin(update)
            ),
        )

        return

    # =====================================================
    # ADMIN PANEL
    # =====================================================

    if choice == "admin_panel":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        await query.edit_message_text(
            "👑 لوحة تحكم مجوهرات الحسيني\n\n"
            "من هنا تقدر تدير البوت بالكامل 👇",
            reply_markup=admin_panel_keyboard(),
        )

        return

    # =====================================================
    # ADMIN STATS
    # =====================================================

    if choice == "admin_stats":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        await show_admin_stats(
            query
        )

        return

    # =====================================================
    # ADMIN GOLD
    # =====================================================

    if choice == "admin_gold":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        latest_price = (
            get_latest_gold_price()
        )

        updated_at = (
            get_latest_price_updated_at()
        )

        if latest_price is None:

            text = (
                "💰 إدارة أسعار الذهب\n\n"
                "🟡 لا يوجد سعر محفوظ حاليًا.\n\n"
                "اختار العملية:"
            )

        else:

            p24, p21, p18 = calc(
                latest_price
            )

            text = (
                "💰 إدارة أسعار الذهب\n\n"
                f"🟡 عيار 24: {p24} جنيه\n"
                f"🟡 عيار 21: {p21} جنيه\n"
                f"🟡 عيار 18: {p18} جنيه\n\n"
            )

            if updated_at:

                text += (
                    f"🕐 آخر تحديث:\n"
                    f"{updated_at}\n\n"
                )

            text += (
                "اختار العملية:"
            )

        await query.edit_message_text(
            text,
            reply_markup=admin_gold_keyboard(),
        )

        return

    # =====================================================
    # ADMIN UPDATE GOLD
    # =====================================================

    if choice == "admin_update_gold":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        context.user_data[
            "admin_action"
        ] = "awaiting_gold_price"

        await query.edit_message_text(
            "✏️ تحديث سعر الذهب\n\n"
            "ابعت سعر عيار 21 الجديد فقط.\n\n"
            "مثال:\n"
            "7000\n\n"
            "❌ للإلغاء اكتب /start",
        )

        return

    # =====================================================
    # ADMIN GOLD HISTORY
    # =====================================================

    if choice == "admin_gold_history":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        history = load_history()

        if not history:

            text = (
                "📜 سجل أسعار الذهب\n\n"
                "لا يوجد سجل حتى الآن."
            )

        else:

            sorted_history = sorted(
                history.items(),
                reverse=True,
            )

            lines = [
                "📜 سجل أسعار الذهب",
                "",
            ]

            for date, price in sorted_history[:30]:

                lines.append(
                    f"📅 {date} — "
                    f"{price} جنيه"
                )

            text = "\n".join(
                lines
            )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ إدارة الأسعار",
                            callback_data="admin_gold",
                        )
                    ]
                ]
            ),
        )

        return

    # =====================================================
    # ADMIN PUBLISH GOLD
    # =====================================================

    if choice == "admin_publish_gold":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        latest_price = (
            get_latest_gold_price()
        )

        if latest_price is None:

            await query.edit_message_text(
                "❌ لا يوجد سعر محفوظ للنشر.\n\n"
                "حدّث السعر أولاً.",
                reply_markup=admin_gold_keyboard(),
            )

            return

        p24, p21, p18 = calc(
            latest_price
        )

        comparison = (
            create_comparison_line(
                latest_price
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
        ] = round(
            latest_price
        )

        context.user_data[
            "is_first_post_today"
        ] = False

        keyboard = [

            [
                InlineKeyboardButton(
                    "📱 تليجرام + فيسبوك",
                    callback_data="telegram_facebook",
                )
            ],

            [
                InlineKeyboardButton(
                    "📱 تليجرام فقط",
                    callback_data="telegram_only",
                )
            ],

            [
                InlineKeyboardButton(
                    "📘 فيسبوك فقط",
                    callback_data="facebook_only",
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ],
        ]

        await query.edit_message_text(
            "📢 نشر أسعار الذهب\n\n"
            "اختار مكان النشر:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # ADMIN PRODUCTS
    # =====================================================

    if choice == "admin_products":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        await query.edit_message_text(
            "💍 إدارة المنتجات\n\n"
            "اختار العملية:",
            reply_markup=admin_products_keyboard(),
        )

        return

    # =====================================================
    # ADMIN ADD PRODUCT
    # =====================================================

    if choice == "admin_add_product":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        context.user_data[
            "admin_action"
        ] = "awaiting_product_category"

        await query.edit_message_text(
            "➕ إضافة منتج\n\n"
            "اكتب اسم القسم الموجود.\n\n"
            "مثال:\n"
            "خواتم",
        )

        return

    # =====================================================
    # ADMIN VIEW PRODUCTS
    # =====================================================

    if choice == "admin_view_products":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        try:

            products = (
                get_all_products()
            )

        except Exception as e:

            print(
                "View Products Error:",
                e,
            )

            await query.edit_message_text(
                "❌ حصل خطأ في قاعدة البيانات.",
                reply_markup=admin_products_keyboard(),
            )

            return

        if not products:

            await query.edit_message_text(
                "📋 المنتجات\n\n"
                "لا توجد منتجات حاليًا.",
                reply_markup=admin_products_keyboard(),
            )

            return

        lines = [
            "📋 المنتجات الموجودة",
            "",
        ]

        for product in products[:50]:

            lines.append(
                f"🆔 {product['id']} — "
                f"{product['category']}"
            )

        if len(products) > 50:

            lines.append("")

            lines.append(
                f"إجمالي المنتجات: "
                f"{len(products)}"
            )

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_products_keyboard(),
        )

        return

    # =====================================================
    # ADMIN DELETE PRODUCT
    # =====================================================

    if choice == "admin_delete_product":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        products = get_all_products()

        if not products:

            await query.edit_message_text(
                "🗑 حذف منتج\n\n"
                "لا توجد منتجات للحذف.",
                reply_markup=admin_products_keyboard(),
            )

            return

        keyboard = []

        for product in products[:50]:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {product['category']} "
                        f"#{product['id']}",
                        callback_data=(
                            "admin_delprod:"
                            + str(product["id"])
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ إدارة المنتجات",
                    callback_data="admin_products",
                )
            ]
        )

        await query.edit_message_text(
            "🗑 حذف منتج\n\n"
            "اختار المنتج:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # DELETE PRODUCT SELECTED
    # =====================================================

    if choice.startswith(
        "admin_delprod:"
    ):

        if not is_admin(update):
            return

        try:

            product_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            await query.edit_message_text(
                "❌ رقم المنتج غير صحيح.",
                reply_markup=admin_products_keyboard(),
            )

            return

        await query.edit_message_text(
            "⚠️ تأكيد حذف المنتج\n\n"
            f"🆔 رقم المنتج: {product_id}\n\n"
            "هل أنت متأكد؟",
            reply_markup=InlineKeyboardMarkup(
                [

                    [
                        InlineKeyboardButton(
                            "✅ نعم، احذف",
                            callback_data=(
                                "admin_confirm_del:"
                                + str(product_id)
                            ),
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "❌ إلغاء",
                            callback_data="admin_products",
                        )
                    ],

                ]
            ),
        )

        return

    # =====================================================
    # CONFIRM DELETE
    # =====================================================

    if choice.startswith(
        "admin_confirm_del:"
    ):

        if not is_admin(update):
            return

        try:

            product_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

            deleted = delete_product(
                product_id
            )

        except Exception as e:

            print(
                "Delete Product Error:",
                e,
            )

            await query.edit_message_text(
                "❌ حصل خطأ أثناء الحذف.",
                reply_markup=admin_products_keyboard(),
            )

            return

        context.user_data.clear()

        if deleted:

            result = (
                "✅ تم حذف المنتج بنجاح."
            )

        else:

            result = (
                "⚠️ المنتج غير موجود."
            )

        await query.edit_message_text(
            result,
            reply_markup=admin_products_keyboard(),
        )

        return

    # =====================================================
    # ADMIN CATEGORIES
    # =====================================================

    if choice == "admin_categories":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        await query.edit_message_text(
            "📂 إدارة الأقسام\n\n"
            "اختار العملية:",
            reply_markup=admin_categories_keyboard(),
        )

        return

    # =====================================================
    # ADD CATEGORY
    # =====================================================

    if choice == "admin_add_category":

        if not is_admin(update):
            return

        context.user_data.clear()

        context.user_data[
            "admin_action"
        ] = "awaiting_category_name"

        await query.edit_message_text(
            "➕ إضافة قسم جديد\n\n"
            "اكتب اسم القسم.\n\n"
            "مثال:\n"
            "أساور",
        )

        return

    # =====================================================
    # VIEW CATEGORIES
    # =====================================================

    if choice == "admin_view_categories":

        if not is_admin(update):
            return

        try:

            categories = get_categories()

        except Exception as e:

            print(
                "View Categories Error:",
                e,
            )

            await query.edit_message_text(
                "❌ حصل خطأ في قاعدة البيانات.",
                reply_markup=admin_categories_keyboard(),
            )

            return

        if not categories:

            text = (
                "📂 الأقسام\n\n"
                "لا توجد أقسام حاليًا."
            )

        else:

            lines = [
                "📂 الأقسام الموجودة",
                "",
            ]

            for category in categories:

                products = get_products(
                    category["name"]
                )

                lines.append(
                    f"📂 {category['name']} "
                    f"— {len(products)} منتج"
                )

            text = "\n".join(
                lines
            )

        await query.edit_message_text(
            text,
            reply_markup=admin_categories_keyboard(),
        )

        return

    # =====================================================
    # RENAME CATEGORY MENU
    # =====================================================

    if choice == "admin_rename_category":

        if not is_admin(update):
            return

        categories = get_categories()

        if not categories:

            await query.edit_message_text(
                "❌ لا توجد أقسام حاليًا.",
                reply_markup=admin_categories_keyboard(),
            )

            return

        keyboard = []

        for category in categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {category['name']}",
                        callback_data=(
                            "admin_rename:"
                            + str(category["id"])
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ إدارة الأقسام",
                    callback_data="admin_categories",
                )
            ]
        )

        await query.edit_message_text(
            "✏️ تغيير اسم قسم\n\n"
            "اختار القسم:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # RENAME CATEGORY SELECTED
    # =====================================================

    if choice.startswith(
        "admin_rename:"
    ):

        if not is_admin(update):
            return

        try:

            category_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        category = get_category_by_id(
            category_id
        )

        if not category:

            await query.edit_message_text(
                "❌ القسم غير موجود.",
                reply_markup=admin_categories_keyboard(),
            )

            return

        context.user_data.clear()

        context.user_data[
            "admin_action"
        ] = "awaiting_category_rename"

        context.user_data[
            "rename_category_id"
        ] = category_id

        await query.edit_message_text(
            "✏️ تغيير اسم القسم\n\n"
            f"القسم الحالي:\n"
            f"{category['name']}\n\n"
            "اكتب الاسم الجديد:",
        )

        return

    # =====================================================
    # DELETE CATEGORY MENU
    # =====================================================

    if choice == "admin_delete_category":

        if not is_admin(update):
            return

        categories = get_categories()

        if not categories:

            await query.edit_message_text(
                "❌ لا توجد أقسام حاليًا.",
                reply_markup=admin_categories_keyboard(),
            )

            return

        keyboard = []

        for category in categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {category['name']}",
                        callback_data=(
                            "admin_delete_cat:"
                            + str(category["id"])
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ إدارة الأقسام",
                    callback_data="admin_categories",
                )
            ]
        )

        await query.edit_message_text(
            "🗑 حذف قسم\n\n"
            "⚠️ القسم الذي يحتوي على منتجات "
            "لن يمكن حذفه.\n\n"
            "اختار القسم:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # DELETE CATEGORY SELECTED
    # =====================================================

    if choice.startswith(
        "admin_delete_cat:"
    ):

        if not is_admin(update):
            return

        try:

            category_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        result = delete_category(
            category_id
        )

        if result == "deleted":

            text = (
                "✅ تم حذف القسم بنجاح."
            )

        elif result == "has_products":

            text = (
                "⚠️ لا يمكن حذف القسم.\n\n"
                "القسم يحتوي على منتجات.\n"
                "احذف المنتجات أولاً."
            )

        else:

            text = (
                "❌ القسم غير موجود."
            )

        await query.edit_message_text(
            text,
            reply_markup=admin_categories_keyboard(),
        )

        return

    # =====================================================
    # PUBLIC PRODUCTS
    # =====================================================

    if choice == "products":

        await show_products_menu(
            query
        )

        return

    # =====================================================
    # PUBLIC CATEGORY
    # =====================================================

    if choice.startswith(
        "category:"
    ):

        category = (
            get_category_from_callback(
                choice
            )
        )

        if not category:

            await query.edit_message_text(
                "❌ القسم غير موجود.",
                reply_markup=main_menu(
                    admin=is_admin(update)
                ),
            )

            return

        await send_products(
            query,
            category,
        )

        return

    # =====================================================
    # GOLD PRICES
    # =====================================================

    if choice == "gold_prices":

        latest_price = (
            get_latest_gold_price()
        )

        if latest_price is None:

            await query.edit_message_text(
                "💎 أسعار الذهب\n\n"
                "⏳ لم يتم نشر أسعار الذهب "
                "حتى الآن.\n\n"
                "تابعنا لمعرفة أحدث الأسعار.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ الرئيسية",
                                callback_data="home",
                            )
                        ]
                    ]
                ),
            )

            return

        p24, p21, p18 = calc(
            latest_price
        )

        comparison = (
            create_comparison_line(
                latest_price
            )
        )

        price_text = create_price_text(
            p24,
            p21,
            p18,
            comparison,
        )

        await query.edit_message_text(
            price_text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ الرئيسية",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )

        return

    # =====================================================
    # PHONE
    # =====================================================

    if choice == "phone":

        keyboard = [

            [
                InlineKeyboardButton(
                    "💬 تواصل على واتساب",
                    url=WHATSAPP_LINK,
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ الرئيسية",
                    callback_data="home",
                )
            ],
        ]

        await query.edit_message_text(
            "📞 مجوهرات الحسيني\n\n"
            f"رقم المحل:\n"
            f"{PHONE_NUMBER}\n\n"
            "للتواصل المباشر اضغط واتساب 👇",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # CANCEL
    # =====================================================

    if choice == "cancel":

        context.user_data.clear()

        await query.edit_message_text(
            "❌ تم إلغاء النشر.",
            reply_markup=main_menu(
                admin=is_admin(update)
            ),
        )

        return

    # =====================================================
    # PUBLISH PRICE
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
            False,
        )
    )

    if not text or price is None:

        await query.edit_message_text(
            "❌ السعر انتهى.\n"
            "ابعت السعر من جديد.",
            reply_markup=main_menu(
                admin=is_admin(update)
            ),
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

        return

    # =====================================================
    # SAVE PRICE
    # =====================================================

    successful_post = (
        telegram_success
        or facebook_success
    )

    if successful_post:

        save_latest_gold_price(
            price
        )

        if is_first_post_today:

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
                "❌ حصل خطأ في النشر."
            )

    elif choice == "telegram_only":

        if telegram_success:

            result = (
                "✅ تم النشر في تليجرام."
            )

        else:

            result = (
                "❌ حصل خطأ في تليجرام."
            )

    elif choice == "facebook_only":

        if facebook_success:

            result = (
                "✅ تم النشر في فيسبوك."
            )

        else:

            result = (
                "❌ حصل خطأ في فيسبوك."
            )

    else:

        result = (
            "❌ اختيار غير معروف."
        )

    await query.edit_message_text(
        result,
        reply_markup=main_menu(
            admin=is_admin(update)
        ),
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
        .token(
            BOT_TOKEN
        )
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
    # BUTTONS
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            button_handler
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
