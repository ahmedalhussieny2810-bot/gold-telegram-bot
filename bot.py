import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

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

import requests
import pymysql


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip())
except (TypeError, ValueError):
    ADMIN_ID = 0


# =========================================================
# SETTINGS
# =========================================================

TZ = ZoneInfo("Africa/Cairo")

WEBSITE = "https://link.gettap.co/alhussienyjewelry"
TG_CHANNEL = "https://t.me/alhussienyjewelry"
FACEBOOK = "https://www.facebook.com/alhussienyjewelry"
INSTAGRAM = "https://www.instagram.com/alhussienyjewelry"
MAPS = "https://maps.app.goo.gl/1X6NJrNM4u1azpFR6"
WHATSAPP = "https://wa.me/201067365567"
PHONE = "01067365567"

HISTORY = "gold_history.json"
LATEST = "latest_gold_price.json"


# =========================================================
# DATABASE CONNECTION
# =========================================================

def db():

    if not DATABASE_URL:
        raise Exception("DATABASE_URL is missing")

    u = urlparse(DATABASE_URL)

    return pymysql.connect(
        host=u.hostname,
        port=u.port or 3306,
        user=u.username,
        password=u.password,
        database=u.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


# =========================================================
# DATABASE MIGRATION HELPERS
# =========================================================

def column_exists(cursor, table, column):

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = %s
        AND COLUMN_NAME = %s
        """,
        (table, column),
    )

    row = cursor.fetchone()

    return row["total"] > 0


def add_column_if_missing(
    cursor,
    table,
    column,
    definition,
):

    if not column_exists(
        cursor,
        table,
        column,
    ):

        cursor.execute(
            f"""
            ALTER TABLE `{table}`
            ADD COLUMN `{column}` {definition}
            """
        )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    connection = db()

    try:

        with connection.cursor() as cursor:

            # =================================================
            # CATEGORIES
            # =================================================

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Categories (

                    id BIGINT UNSIGNED
                    AUTO_INCREMENT PRIMARY KEY,

                    parent_id BIGINT UNSIGNED NULL,

                    name VARCHAR(255)
                    NOT NULL,

                    created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                    INDEX(parent_id)

                )
                """
            )

            # -------------------------------------------------
            # IMPORTANT:
            # Old Categories table may exist without parent_id.
            # Add missing columns automatically.
            # -------------------------------------------------

            add_column_if_missing(
                cursor,
                "Categories",
                "parent_id",
                "BIGINT UNSIGNED NULL",
            )

            add_column_if_missing(
                cursor,
                "Categories",
                "name",
                "VARCHAR(255) NOT NULL DEFAULT ''",
            )

            add_column_if_missing(
                cursor,
                "Categories",
                "created_at",
                "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP",
            )

            # =================================================
            # PRODUCTS
            # =================================================

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Products (

                    id BIGINT UNSIGNED
                    AUTO_INCREMENT PRIMARY KEY,

                    category VARCHAR(255) NULL,

                    Photo_id TEXT NOT NULL,

                    category_id BIGINT UNSIGNED NULL,

                    name VARCHAR(255) NULL,

                    code VARCHAR(100) NULL,

                    price DECIMAL(15,2) NULL,

                    description TEXT NULL,

                    INDEX(category_id)

                )
                """
            )

            # -------------------------------------------------
            # Upgrade old Products table
            # -------------------------------------------------

            add_column_if_missing(
                cursor,
                "Products",
                "category",
                "VARCHAR(255) NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "Photo_id",
                "TEXT NOT NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "category_id",
                "BIGINT UNSIGNED NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "name",
                "VARCHAR(255) NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "code",
                "VARCHAR(100) NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "price",
                "DECIMAL(15,2) NULL",
            )

            add_column_if_missing(
                cursor,
                "Products",
                "description",
                "TEXT NULL",
            )

            # =================================================
            # MIGRATE OLD PRODUCTS
            # =================================================

            cursor.execute(
                """
                SELECT DISTINCT category
                FROM Products
                WHERE category IS NOT NULL
                AND TRIM(category) <> ''
                AND (
                    category_id IS NULL
                    OR category_id = 0
                )
                """
            )

            old_categories = cursor.fetchall()

            for row in old_categories:

                old_category = (
                    row["category"]
                    .strip()
                )

                # ---------------------------------------------
                # Find / create main category
                # ---------------------------------------------

                cursor.execute(
                    """
                    SELECT id
                    FROM Categories
                    WHERE parent_id IS NULL
                    AND LOWER(TRIM(name))
                    =
                    LOWER(TRIM(%s))
                    LIMIT 1
                    """,
                    (old_category,),
                )

                main = cursor.fetchone()

                if main:

                    main_id = main["id"]

                else:

                    cursor.execute(
                        """
                        INSERT INTO Categories
                        (parent_id, name)

                        VALUES
                        (NULL, %s)
                        """,
                        (old_category,),
                    )

                    main_id = cursor.lastrowid

                # ---------------------------------------------
                # Find / create default subcategory
                # ---------------------------------------------

                cursor.execute(
                    """
                    SELECT id
                    FROM Categories
                    WHERE parent_id = %s
                    AND LOWER(TRIM(name)) = 'عام'
                    LIMIT 1
                    """,
                    (main_id,),
                )

                sub = cursor.fetchone()

                if sub:

                    sub_id = sub["id"]

                else:

                    cursor.execute(
                        """
                        INSERT INTO Categories
                        (parent_id, name)

                        VALUES
                        (%s, 'عام')
                        """,
                        (main_id,),
                    )

                    sub_id = cursor.lastrowid

                # ---------------------------------------------
                # Move old products to new subcategory
                # ---------------------------------------------

                cursor.execute(
                    """
                    UPDATE Products
                    SET category_id = %s

                    WHERE category = %s

                    AND (
                        category_id IS NULL
                        OR category_id = 0
                    )
                    """,
                    (
                        sub_id,
                        old_category,
                    ),
                )

        print("Database: READY")

    except Exception as e:

        print(
            "Database Initialization Error:",
            e,
        )

        raise

    finally:

        connection.close()


# =========================================================
# DATABASE HELPERS
# =========================================================

def one(
    sql,
    args=(),
):

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                sql,
                args,
            )

            return cursor.fetchone()

    finally:

        connection.close()


def many(
    sql,
    args=(),
):

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                sql,
                args,
            )

            return cursor.fetchall()

    finally:

        connection.close()


# =========================================================
# CATEGORIES
# =========================================================

def add_main(
    name,
):

    name = name.strip()

    if not name:
        return None

    exists = one(
        """
        SELECT id
        FROM Categories
        WHERE parent_id IS NULL
        AND LOWER(TRIM(name))
        =
        LOWER(TRIM(%s))
        LIMIT 1
        """,
        (name,),
    )

    if exists:
        return None

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO Categories
                (parent_id, name)

                VALUES
                (NULL, %s)
                """,
                (name,),
            )

            return cursor.lastrowid

    finally:

        connection.close()


def add_sub(
    parent,
    name,
):

    name = name.strip()

    if not name:
        return None

    exists = one(
        """
        SELECT id
        FROM Categories
        WHERE parent_id = %s
        AND LOWER(TRIM(name))
        =
        LOWER(TRIM(%s))
        LIMIT 1
        """,
        (
            parent,
            name,
        ),
    )

    if exists:
        return None

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO Categories
                (parent_id, name)

                VALUES
                (%s, %s)
                """,
                (
                    parent,
                    name,
                ),
            )

            return cursor.lastrowid

    finally:

        connection.close()


def cats(
    parent=None,
):

    if parent is None:

        return many(
            """
            SELECT
                id,
                name

            FROM Categories

            WHERE parent_id IS NULL

            ORDER BY name
            """
        )

    return many(
        """
        SELECT

            c.id,

            c.name,

            COUNT(p.id)
            AS product_count

        FROM Categories c

        LEFT JOIN Products p
        ON p.category_id = c.id

        WHERE c.parent_id = %s

        GROUP BY
            c.id,
            c.name

        ORDER BY c.name
        """,
        (parent,),
    )


def cat(
    cid,
):

    return one(
        """
        SELECT
            id,
            parent_id,
            name

        FROM Categories

        WHERE id = %s
        """,
        (cid,),
    )


def rename_cat(
    cid,
    name,
):

    name = name.strip()

    if not name:
        return False

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE Categories

                SET name = %s

                WHERE id = %s
                """,
                (
                    name,
                    cid,
                ),
            )

            return cursor.rowcount > 0

    finally:

        connection.close()


def del_cat(
    cid,
):

    product = one(
        """
        SELECT id
        FROM Products

        WHERE category_id = %s

        LIMIT 1
        """,
        (cid,),
    )

    if product:
        return "products"

    children = one(
        """
        SELECT id
        FROM Categories

        WHERE parent_id = %s

        LIMIT 1
        """,
        (cid,),
    )

    if children:
        return "children"

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM Categories

                WHERE id = %s
                """,
                (cid,),
            )

            if cursor.rowcount:
                return "deleted"

            return "missing"

    finally:

        connection.close()


# =========================================================
# PRODUCTS
# =========================================================

def add_product(
    cid,
    photo,
    name,
    code,
    price,
    description,
):

    connection = db()

    try:

        with connection.cursor() as cursor:

            category = cat(cid)

            category_name = (
                category["name"]
                if category
                else ""
            )

            cursor.execute(
                """
                INSERT INTO Products
                (
                    category,
                    Photo_id,
                    category_id,
                    name,
                    code,
                    price,
                    description
                )

                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    category_name,
                    photo,
                    cid,
                    name,
                    code,
                    price,
                    description,
                ),
            )

            return cursor.lastrowid

    finally:

        connection.close()


def products(
    cid,
):

    return many(
        """
        SELECT
            id,
            Photo_id,
            name,
            code,
            price,
            description

        FROM Products

        WHERE category_id = %s

        ORDER BY id DESC
        """,
        (cid,),
    )


def all_products():

    return many(
        """
        SELECT

            p.*,

            c.name AS sub_name,

            m.name AS main_name

        FROM Products p

        LEFT JOIN Categories c
        ON c.id = p.category_id

        LEFT JOIN Categories m
        ON m.id = c.parent_id

        ORDER BY p.id DESC
        """
    )


def del_product(
    pid,
):

    connection = db()

    try:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM Products

                WHERE id = %s
                """,
                (pid,),
            )

            return bool(
                cursor.rowcount
            )

    finally:

        connection.close()


# =========================================================
# GOLD
# =========================================================

def calc(
    price,
):

    return (
        round(
            price * 8 / 7
        ),
        round(price),
        round(
            price * 6 / 7
        ),
    )


def today():

    return datetime.now(
        TZ
    ).strftime(
        "%Y-%m-%d"
    )


def yesterday():

    return (
        datetime.now(TZ)
        - timedelta(days=1)
    ).strftime(
        "%Y-%m-%d"
    )


# =========================================================
# JSON
# =========================================================

def load_json(
    path,
):

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except Exception:

        return {}


def save_json(
    path,
    data,
):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# GOLD HISTORY
# =========================================================

def first_today():

    return load_json(
        HISTORY
    ).get(
        today()
    )


def save_first(
    price,
):

    history = load_json(
        HISTORY
    )

    if today() in history:

        return False

    history[
        today()
    ] = round(
        price
    )

    save_json(
        HISTORY,
        history,
    )

    return True


def latest():

    return load_json(
        LATEST
    ).get(
        "price"
    )


def save_latest(
    price,
):

    save_json(
        LATEST,
        {
            "price": round(
                price
            ),
            "updated_at":
                datetime.now(
                    TZ
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
        },
    )


def comparison(
    price,
):

    old = (
        load_json(
            HISTORY
        ).get(
            yesterday()
        )
    )

    if old is None:
        return None

    difference = round(
        price - old
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


def price_text(
    price,
):

    p24, p21, p18 = calc(
        price
    )

    comp = comparison(
        price
    )

    lines = []

    if comp:

        lines.append(
            comp
        )

        lines.append("")

    lines.extend(
        [
            "💎 أسعار الذهب الآن",
            "",
            f"🟡 عيار 24 : {p24}",
            f"🟡 عيار 21 : {p21}",
            f"🟡 عيار 18 : {p18}",
            "",
            "📍 بورسعيد - شارع أسوان أمام صيدلية جلال",
            "",
            "🌐 " + WEBSITE,
        ]
    )

    return "\n".join(
        lines
    )


# =========================================================
# MENUS
# =========================================================

def home(
    admin=False,
):

    keyboard = [

        [
            InlineKeyboardButton(
                "💎 أسعار الذهب",
                callback_data="gold",
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
                    callback_data="admin",
                )
            ]
        )

    keyboard.extend(
        [

            [
                InlineKeyboardButton(
                    "📢 قناة التليجرام",
                    url=TG_CHANNEL,
                )
            ],

            [
                InlineKeyboardButton(
                    "📍 موقع المحل",
                    url=MAPS,
                ),

                InlineKeyboardButton(
                    "🌐 الموقع",
                    url=WEBSITE,
                ),
            ],

            [
                InlineKeyboardButton(
                    "💬 واتساب",
                    url=WHATSAPP,
                ),

                InlineKeyboardButton(
                    "📞 رقم المحل",
                    callback_data="phone",
                ),
            ],

            [
                InlineKeyboardButton(
                    "📘 فيسبوك",
                    url=FACEBOOK,
                ),

                InlineKeyboardButton(
                    "📸 إنستجرام",
                    url=INSTAGRAM,
                ),
            ],

        ]
    )

    return InlineKeyboardMarkup(
        keyboard
    )


def admin_menu():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "💰 إدارة أسعار الذهب",
                    callback_data="agold",
                )
            ],

            [
                InlineKeyboardButton(
                    "💍 إدارة المنتجات",
                    callback_data="aprod",
                )
            ],

            [
                InlineKeyboardButton(
                    "📂 إدارة الأقسام",
                    callback_data="acat",
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


def cat_menu():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "➕ قسم رئيسي",
                    callback_data="addmain",
                ),

                InlineKeyboardButton(
                    "➕ قسم فرعي",
                    callback_data="addsub",
                ),
            ],

            [
                InlineKeyboardButton(
                    "📋 عرض الأقسام",
                    callback_data="viewcats",
                )
            ],

            [
                InlineKeyboardButton(
                    "✏️ تغيير اسم",
                    callback_data="rename",
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 حذف قسم",
                    callback_data="deletecat",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin",
                )
            ],

        ]
    )


def prod_menu():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "➕ إضافة منتج",
                    callback_data="addprod",
                )
            ],

            [
                InlineKeyboardButton(
                    "📋 عرض المنتجات",
                    callback_data="viewprod",
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 حذف منتج",
                    callback_data="deleteprod",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin",
                )
            ],

        ]
    )


def gold_menu():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "✏️ تحديث السعر",
                    callback_data="updategold",
                )
            ],

            [
                InlineKeyboardButton(
                    "📜 سجل الأسعار",
                    callback_data="history",
                )
            ],

            [
                InlineKeyboardButton(
                    "📢 نشر السعر",
                    callback_data="publish",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ لوحة التحكم",
                    callback_data="admin",
                )
            ],

        ]
    )


def publish_menu():

    return InlineKeyboardMarkup(
        [

            [
                InlineKeyboardButton(
                    "📱 تليجرام + فيسبوك",
                    callback_data="pub_both",
                )
            ],

            [
                InlineKeyboardButton(
                    "📱 تليجرام فقط",
                    callback_data="pub_tg",
                )
            ],

            [
                InlineKeyboardButton(
                    "📘 فيسبوك فقط",
                    callback_data="pub_fb",
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="home",
                )
            ],

        ]
    )


# =========================================================
# HELPERS
# =========================================================

def is_admin(
    update,
):

    return bool(
        update.effective_user
        and
        update.effective_user.id
        == ADMIN_ID
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.message.reply_text(
        "💎 مجوهرات الحسيني\n\n"
        "أهلاً بيك في البوت الرسمي "
        "لمجوهرات الحسيني - بورسعيد ✨\n\n"
        "اختار من القائمة 👇",
        reply_markup=home(
            is_admin(update)
        ),
    )


# =========================================================
# ID
# =========================================================

async def show_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if is_admin(update):

        await update.message.reply_text(
            "🆔 Telegram ID الخاص بالأدمن:\n\n"
            f"{ADMIN_ID}"
        )

    else:

        await update.message.reply_text(
            "❌ الأمر ده متاح للأدمن فقط."
        )


# =========================================================
# FACEBOOK
# =========================================================

async def facebook(
    text,
):

    if not FACEBOOK_PAGE_ID:
        return False

    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        return False

    try:

        response = requests.post(
            (
                "https://graph.facebook.com/"
                "v23.0/"
                f"{FACEBOOK_PAGE_ID}/feed"
            ),
            data={
                "message": text,
                "access_token":
                    FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            timeout=20,
        )

        return (
            response.status_code
            == 200
        )

    except Exception as e:

        print(
            "Facebook Error:",
            e,
        )

        return False


# =========================================================
# TELEGRAM CHANNEL
# =========================================================

async def tg(
    context,
    text,
):

    if not CHANNEL_ID:
        return False

    try:

        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
        )

        return True

    except Exception as e:

        print(
            "Telegram Error:",
            e,
        )

        return False


# =========================================================
# PHOTO
# =========================================================

async def photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):

        await update.message.reply_text(
            "❌ غير مسموح."
        )

        return

    if (
        context.user_data.get(
            "state"
        )
        != "product_photo"
    ):

        await update.message.reply_text(
            "❌ ابدأ إضافة المنتج "
            "من لوحة التحكم."
        )

        return

    cid = context.user_data.get(
        "cid"
    )

    try:

        product_id = add_product(
            cid,
            update.message.photo[-1].file_id,
            context.user_data.get(
                "name"
            ),
            context.user_data.get(
                "code"
            ),
            context.user_data.get(
                "price"
            ),
            context.user_data.get(
                "desc"
            ),
        )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم إضافة المنتج بنجاح.\n\n"
            f"🆔 #{product_id}",
            reply_markup=prod_menu(),
        )

    except Exception as e:

        print(
            "Product Error:",
            e,
        )

        context.user_data.clear()

        await update.message.reply_text(
            "❌ حصل خطأ أثناء حفظ المنتج.",
            reply_markup=prod_menu(),
        )


# =========================================================
# TEXT STATES
# =========================================================

async def text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    t = (
        update.message.text
        or ""
    ).strip()

    state = context.user_data.get(
        "state"
    )

    # =====================================================
    # GOLD
    # =====================================================

    if state == "gold":

        if not is_admin(update):

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        try:

            price = float(t)

            if price <= 0:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ اكتب سعر عيار 21 صحيح.\n\n"
                "مثال:\n"
                "7000"
            )

            return

        save_latest(
            price
        )

        if first_today() is None:

            save_first(
                price
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تحديث السعر.\n\n"
            + price_text(price),
            reply_markup=gold_menu(),
        )

        return

    # =====================================================
    # MAIN CATEGORY
    # =====================================================

    if state == "main":

        if not t:

            await update.message.reply_text(
                "❌ اكتب اسم القسم."
            )

            return

        result = add_main(
            t
        )

        if result is None:

            await update.message.reply_text(
                "⚠️ القسم موجود بالفعل.",
                reply_markup=cat_menu(),
            )

        else:

            await update.message.reply_text(
                "✅ تم إضافة القسم الرئيسي.\n\n"
                f"💍 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()

        return

    # =====================================================
    # SUB CATEGORY
    # =====================================================

    if state == "sub":

        parent = context.user_data.get(
            "parent"
        )

        if not parent or not t:

            await update.message.reply_text(
                "❌ اكتب اسم القسم الفرعي."
            )

            return

        result = add_sub(
            parent,
            t,
        )

        if result is None:

            await update.message.reply_text(
                "⚠️ القسم الفرعي موجود بالفعل.",
                reply_markup=cat_menu(),
            )

        else:

            await update.message.reply_text(
                "✅ تم إضافة القسم الفرعي.\n\n"
                f"🟡 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()

        return

    # =====================================================
    # RENAME
    # =====================================================

    if state == "rename":

        cid = context.user_data.get(
            "cid"
        )

        if cid and t:

            rename_cat(
                cid,
                t,
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تغيير الاسم.",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # PRODUCT NAME
    # =====================================================

    if state == "prod_name":

        context.user_data[
            "name"
        ] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data[
            "state"
        ] = "prod_code"

        await update.message.reply_text(
            "🔖 اكتب كود المنتج.\n\n"
            "أو اكتب:\n"
            "بدون"
        )

        return

    # =====================================================
    # PRODUCT CODE
    # =====================================================

    if state == "prod_code":

        context.user_data[
            "code"
        ] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data[
            "state"
        ] = "prod_price"

        await update.message.reply_text(
            "💰 اكتب سعر المنتج.\n\n"
            "أو اكتب:\n"
            "بدون"
        )

        return

    # =====================================================
    # PRODUCT PRICE
    # =====================================================

    if state == "prod_price":

        if t.lower() == "بدون":

            value = None

        else:

            try:

                value = float(t)

                if value < 0:
                    raise ValueError

            except ValueError:

                await update.message.reply_text(
                    "❌ اكتب رقم صحيح أو:\n"
                    "بدون"
                )

                return

        context.user_data[
            "price"
        ] = value

        context.user_data[
            "state"
        ] = "prod_desc"

        await update.message.reply_text(
            "📝 اكتب وصف المنتج.\n\n"
            "أو اكتب:\n"
            "بدون"
        )

        return

    # =====================================================
    # PRODUCT DESCRIPTION
    # =====================================================

    if state == "prod_desc":

        context.user_data[
            "desc"
        ] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data[
            "state"
        ] = "product_photo"

        await update.message.reply_text(
            "📸 تمام.\n\n"
            "ابعت صورة المنتج الآن."
        )

        return

    # =====================================================
    # OLD DIRECT GOLD PRICE METHOD
    # =====================================================

    try:

        price = float(t)

        numeric = True

    except ValueError:

        numeric = False
        price = None

    if numeric:

        if not is_admin(update):

            await update.message.reply_text(
                "❌ أسعار الذهب متاحة للأدمن فقط."
            )

            return

        context.user_data.update(
            price_text=price_text(
                price
            ),
            price=round(price),
            first=(
                first_today()
                is None
            ),
        )

        await update.message.reply_text(
            f"السعر: {round(price)}\n\n"
            "📢 عايز تنشر الأسعار فين؟",
            reply_markup=publish_menu(),
        )

        return

    # =====================================================
    # UNKNOWN
    # =====================================================

    await update.message.reply_text(
        "❌ مش فاهم طلبك.\n\n"
        "استخدم /start لفتح القائمة.",
        reply_markup=home(
            is_admin(update)
        ),
    )


# =========================================================
# BUTTONS
# =========================================================

async def buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    choice = query.data

    # =====================================================
    # HOME
    # =====================================================

    if choice == "home":

        context.user_data.clear()

        await query.edit_message_text(
            "💎 مجوهرات الحسيني\n\n"
            "اختار من القائمة 👇",
            reply_markup=home(
                is_admin(update)
            ),
        )

        return

    # =====================================================
    # ADMIN PANEL
    # =====================================================

    if choice == "admin":

        if not is_admin(update):

            await query.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        await query.edit_message_text(
            "👑 لوحة التحكم\n\n"
            "اختار العملية:",
            reply_markup=admin_menu(),
        )

        return

    # =====================================================
    # CLIENT PRODUCTS
    # =====================================================

    if choice == "products":

        main_categories = cats()

        if not main_categories:

            await query.edit_message_text(
                "💍 المنتجات\n\n"
                "لا توجد أقسام حالياً.",
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

        for main in main_categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "💍 "
                        + main["name"],
                        callback_data=(
                            f"cm:{main['id']}"
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
            "💍 منتجات مجوهرات الحسيني\n\n"
            "اختار القسم:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # MAIN CATEGORY CLIENT
    # =====================================================

    if choice.startswith(
        "cm:"
    ):

        try:

            main_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        main = cat(
            main_id
        )

        if not main:

            await query.answer(
                "❌ القسم غير موجود.",
                show_alert=True,
            )

            return

        sub_categories = cats(
            main_id
        )

        if not sub_categories:

            await query.edit_message_text(
                f"💍 {main['name']}\n\n"
                "لا توجد أقسام فرعية.",
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

        keyboard = []

        for sub in sub_categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🟡 {sub['name']} "
                        f"({sub['product_count']})",
                        callback_data=(
                            f"cs:{sub['id']}"
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ الأقسام",
                    callback_data="products",
                )
            ]
        )

        await query.edit_message_text(
            f"💍 {main['name']}\n\n"
            "اختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # SUB CATEGORY CLIENT
    # =====================================================

    if choice.startswith(
        "cs:"
    ):

        try:

            sub_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        sub = cat(
            sub_id
        )

        if not sub:

            await query.answer(
                "❌ القسم غير موجود.",
                show_alert=True,
            )

            return

        product_list = products(
            sub_id
        )

        if not product_list:

            await query.edit_message_text(
                f"🟡 {sub['name']}\n\n"
                "لا توجد منتجات.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ رجوع",
                                callback_data=(
                                    f"cm:{sub['parent_id']}"
                                ),
                            )
                        ]
                    ]
                ),
            )

            return

        await query.edit_message_text(
            f"🟡 {sub['name']}\n\n"
            f"عدد المنتجات: "
            f"{len(product_list)}"
        )

        for product in product_list:

            caption_parts = []

            if product["name"]:

                caption_parts.append(
                    f"💍 {product['name']}"
                )

            if product["code"]:

                caption_parts.append(
                    f"🔖 الكود: "
                    f"{product['code']}"
                )

            if product["price"] is not None:

                caption_parts.append(
                    f"💰 السعر: "
                    f"{product['price']} جنيه"
                )

            if product["description"]:

                caption_parts.append(
                    ""
                )

                caption_parts.append(
                    product[
                        "description"
                    ]
                )

            caption = "\n".join(
                caption_parts
            )

            try:

                await query.message.reply_photo(
                    photo=product[
                        "Photo_id"
                    ],
                    caption=(
                        caption
                        if caption
                        else None
                    ),
                )

            except Exception as e:

                print(
                    "Send Product Photo Error:",
                    e,
                )

        return

    # =====================================================
    # ADMIN GOLD
    # =====================================================

    if choice == "agold":

        if not is_admin(update):
            return

        current_price = latest()

        await query.edit_message_text(
            "💰 إدارة أسعار الذهب\n\n"
            + (
                price_text(
                    current_price
                )
                if current_price
                else
                "لا يوجد سعر محفوظ."
            ),
            reply_markup=gold_menu(),
        )

        return

    # =====================================================
    # UPDATE GOLD
    # =====================================================

    if choice == "updategold":

        if not is_admin(update):
            return

        context.user_data.clear()

        context.user_data[
            "state"
        ] = "gold"

        await query.edit_message_text(
            "✏️ ابعت سعر عيار 21 الجديد.\n\n"
            "مثال:\n"
            "7000"
        )

        return

    # =====================================================
    # GOLD HISTORY
    # =====================================================

    if choice == "history":

        if not is_admin(update):
            return

        history = load_json(
            HISTORY
        )

        if history:

            lines = [
                "📜 سجل الأسعار",
                "",
            ]

            for date, price in sorted(
                history.items(),
                reverse=True,
            )[:30]:

                lines.append(
                    f"📅 {date} — "
                    f"{price} جنيه"
                )

            history_text = "\n".join(
                lines
            )

        else:

            history_text = (
                "📜 سجل الأسعار\n\n"
                "لا يوجد سجل."
            )

        await query.edit_message_text(
            history_text,
            reply_markup=gold_menu(),
        )

        return

    # =====================================================
    # PUBLISH GOLD
    # =====================================================

    if choice == "publish":

        if not is_admin(update):
            return

        current_price = latest()

        if not current_price:

            await query.edit_message_text(
                "❌ لا يوجد سعر محفوظ.",
                reply_markup=gold_menu(),
            )

            return

        context.user_data.update(
            price_text=price_text(
                current_price
            ),
            price=round(
                current_price
            ),
            first=False,
        )

        await query.edit_message_text(
            "📢 اختار مكان النشر:",
            reply_markup=publish_menu(),
        )

        return

    # =====================================================
    # ADMIN CATEGORIES
    # =====================================================

    if choice == "acat":

        if not is_admin(update):
            return

        await query.edit_message_text(
            "📂 إدارة الأقسام\n\n"
            "القسم الرئيسي → "
            "القسم الفرعي → "
            "المنتجات",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # ADD MAIN CATEGORY
    # =====================================================

    if choice == "addmain":

        if not is_admin(update):
            return

        context.user_data.clear()

        context.user_data[
            "state"
        ] = "main"

        await query.edit_message_text(
            "➕ اكتب اسم القسم الرئيسي.\n\n"
            "مثال:\n"
            "خواتم"
        )

        return

    # =====================================================
    # ADD SUB CATEGORY
    # =====================================================

    if choice == "addsub":

        if not is_admin(update):
            return

        main_categories = cats()

        if not main_categories:

            await query.edit_message_text(
                "❌ أضف قسم رئيسي أولاً.",
                reply_markup=cat_menu(),
            )

            return

        keyboard = []

        for main in main_categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "💍 "
                        + main["name"],
                        callback_data=(
                            f"sp:{main['id']}"
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await query.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # SELECT MAIN FOR SUB
    # =====================================================

    if choice.startswith(
        "sp:"
    ):

        if not is_admin(update):
            return

        try:

            main_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        main = cat(
            main_id
        )

        if not main:
            return

        context.user_data.clear()

        context.user_data.update(
            state="sub",
            parent=main_id,
        )

        await query.edit_message_text(
            "➕ اكتب القسم الفرعي تحت:\n\n"
            f"💍 {main['name']}\n\n"
            "مثال:\n"
            "خواتم عيار 18"
        )

        return

    # =====================================================
    # VIEW CATEGORIES
    # =====================================================

    if choice == "viewcats":

        if not is_admin(update):
            return

        lines = [
            "📂 الأقسام",
            "",
        ]

        main_categories = cats()

        for main in main_categories:

            lines.append(
                "💍 "
                + main["name"]
            )

            sub_categories = cats(
                main["id"]
            )

            for sub in sub_categories:

                lines.append(
                    "   └ 🟡 "
                    f"{sub['name']} "
                    f"({sub['product_count']} منتج)"
                )

            lines.append("")

        await query.edit_message_text(
            "\n".join(lines)
            if main_categories
            else
            "📂 لا توجد أقسام.",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # RENAME CATEGORY
    # =====================================================

    if choice == "rename":

        if not is_admin(update):
            return

        keyboard = []

        for main in cats():

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "✏️ "
                        + main["name"],
                        callback_data=(
                            f"rp:{main['id']}"
                        ),
                    )
                ]
            )

            for sub in cats(
                main["id"]
            ):

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"   ✏️ "
                            f"{main['name']} → "
                            f"{sub['name']}",
                            callback_data=(
                                f"rp:{sub['id']}"
                            ),
                        )
                    ]
                )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await query.edit_message_text(
            "✏️ اختار القسم:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # SELECT CATEGORY TO RENAME
    # =====================================================

    if choice.startswith(
        "rp:"
    ):

        if not is_admin(update):
            return

        try:

            cid = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        selected = cat(
            cid
        )

        if not selected:
            return

        context.user_data.clear()

        context.user_data.update(
            state="rename",
            cid=cid,
        )

        await query.edit_message_text(
            "✏️ الاسم الحالي:\n\n"
            f"{selected['name']}\n\n"
            "اكتب الاسم الجديد:"
        )

        return

    # =====================================================
    # DELETE CATEGORY
    # =====================================================

    if choice == "deletecat":

        if not is_admin(update):
            return

        keyboard = []

        for main in cats():

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🗑 "
                        + main["name"],
                        callback_data=(
                            f"dc:{main['id']}"
                        ),
                    )
                ]
            )

            for sub in cats(
                main["id"]
            ):

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"   🗑 "
                            f"{main['name']} → "
                            f"{sub['name']}",
                            callback_data=(
                                f"dc:{sub['id']}"
                            ),
                        )
                    ]
                )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await query.edit_message_text(
            "🗑 اختار القسم للحذف:\n\n"
            "⚠️ لا يمكن حذف قسم يحتوي "
            "على منتجات أو أقسام فرعية.",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # DELETE CATEGORY RESULT
    # =====================================================

    if choice.startswith(
        "dc:"
    ):

        if not is_admin(update):
            return

        try:

            cid = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        result = del_cat(
            cid
        )

        messages = {

            "deleted":
                "✅ تم الحذف.",

            "products":
                "⚠️ القسم يحتوي منتجات.\n"
                "احذف المنتجات أولاً.",

            "children":
                "⚠️ القسم يحتوي أقسام فرعية.\n"
                "احذف الأقسام الفرعية أولاً.",

            "missing":
                "⚠️ القسم غير موجود.",

        }

        await query.edit_message_text(
            messages.get(
                result,
                "❌ حصل خطأ."
            ),
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # ADMIN PRODUCTS
    # =====================================================

    if choice == "aprod":

        if not is_admin(update):
            return

        await query.edit_message_text(
            "💍 إدارة المنتجات",
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # ADD PRODUCT
    # =====================================================

    if choice == "addprod":

        if not is_admin(update):
            return

        main_categories = cats()

        if not main_categories:

            await query.edit_message_text(
                "❌ أضف قسم رئيسي أولاً.",
                reply_markup=prod_menu(),
            )

            return

        keyboard = []

        for main in main_categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "💍 "
                        + main["name"],
                        callback_data=(
                            f"pm:{main['id']}"
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="aprod",
                )
            ]
        )

        await query.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # SELECT MAIN FOR PRODUCT
    # =====================================================

    if choice.startswith(
        "pm:"
    ):

        if not is_admin(update):
            return

        try:

            main_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        sub_categories = cats(
            main_id
        )

        if not sub_categories:

            await query.edit_message_text(
                "❌ القسم الرئيسي لا يحتوي "
                "أقسام فرعية.\n\n"
                "أضف قسمًا فرعيًا أولاً.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ رجوع",
                                callback_data="addprod",
                            )
                        ]
                    ]
                ),
            )

            return

        keyboard = []

        for sub in sub_categories:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🟡 "
                        + sub["name"],
                        callback_data=(
                            f"ps:{sub['id']}"
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="addprod",
                )
            ]
        )

        await query.edit_message_text(
            "➕ اختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # SELECT SUB FOR PRODUCT
    # =====================================================

    if choice.startswith(
        "ps:"
    ):

        if not is_admin(update):
            return

        try:

            sub_id = int(
                choice.split(
                    ":",
                    1
                )[1]
            )

        except ValueError:

            return

        selected = cat(
            sub_id
        )

        if not selected:
            return

        context.user_data.clear()

        context.user_data.update(
            state="prod_name",
            cid=sub_id,
        )

        await query.edit_message_text(
            "💎 اكتب اسم المنتج.\n\n"
            "مثال:\n"
            "خاتم ذهب موديل ناعم"
        )

        return

    # =====================================================
    # VIEW PRODUCTS
    # =====================================================

    if choice == "viewprod":

        if not is_admin(update):
            return

        product_list = all_products()

        lines = [
            "📋 المنتجات",
            "",
        ]

        for product in product_list[:50]:

            lines.append(
                f"🆔 #{product['id']} | "
                f"{product['main_name'] or '-'} → "
                f"{product['sub_name'] or '-'}\n"
                f"💎 {product['name'] or 'بدون اسم'} | "
                f"🔖 {product['code'] or '-'}"
            )

        if len(product_list) > 50:

            lines.append("")

            lines.append(
                f"عرض أول 50 من أصل "
                f"{len(product_list)} منتج."
            )

        await query.edit_message_text(
            "\n".join(lines)
            if product_list
            else
            "📋 لا توجد منتجات.",
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # DELETE PRODUCT
    # =====================================================

    if choice == "deleteprod":

        if not is_admin(update):
            return

        product_list = all_products()

        if not product_list:

            await query.edit_message_text(
                "🗑 لا توجد منتجات للحذف.",
                reply_markup=prod_menu(),
            )

            return

        keyboard = []

        for product in product_list[:50]:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🗑 #{product['id']} "
                        f"{product['name'] or 'بدون اسم'}",
                        callback_data=(
                            f"dp:{product['id']}"
                        ),
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="aprod",
                )
            ]
        )

        await query.edit_message_text(
            "🗑 اختار المنتج:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # =====================================================
    # DELETE PRODUCT CONFIRM
    # =====================================================

    if choice.startswith(
        "dp:"
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

            return

        await query.edit_message_text(
            f"⚠️ تأكيد حذف المنتج "
            f"#{product_id}",
            reply_markup=InlineKeyboardMarkup(
                [

                    [
                        InlineKeyboardButton(
                            "✅ احذف",
                            callback_data=(
                                f"cdp:{product_id}"
                            ),
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "❌ إلغاء",
                            callback_data="deleteprod",
                        )
                    ],

                ]
            ),
        )

        return

    # =====================================================
    # CONFIRM DELETE PRODUCT
    # =====================================================

    if choice.startswith(
        "cdp:"
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

            return

        if del_product(
            product_id
        ):

            result = (
                "✅ تم حذف المنتج."
            )

        else:

            result = (
                "⚠️ المنتج غير موجود."
            )

        await query.edit_message_text(
            result,
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # PHONE
    # =====================================================

    if choice == "phone":

        await query.edit_message_text(
            f"📞 مجوهرات الحسيني\n\n"
            f"{PHONE}\n\n"
            "للتواصل المباشر:",
            reply_markup=InlineKeyboardMarkup(
                [

                    [
                        InlineKeyboardButton(
                            "💬 واتساب",
                            url=WHATSAPP,
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "⬅️ الرئيسية",
                            callback_data="home",
                        )
                    ],

                ]
            ),
        )

        return

    # =====================================================
    # CLIENT GOLD
    # =====================================================

    if choice == "gold":

        current_price = latest()

        await query.edit_message_text(
            price_text(
                current_price
            )
            if current_price
            else
            "💎 لم يتم تحديث أسعار الذهب "
            "حتى الآن.",
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
    # PUBLISH
    # =====================================================

    if choice in (
        "pub_both",
        "pub_tg",
        "pub_fb",
    ):

        if not is_admin(update):
            return

        text_to_publish = (
            context.user_data.get(
                "price_text"
            )
        )

        price = (
            context.user_data.get(
                "price"
            )
        )

        if (
            not text_to_publish
            or price is None
        ):

            await query.edit_message_text(
                "❌ السعر انتهى.",
                reply_markup=home(True),
            )

            return

        tg_ok = False
        fb_ok = False

        if choice in (
            "pub_both",
            "pub_tg",
        ):

            tg_ok = await tg(
                context,
                text_to_publish,
            )

        if choice in (
            "pub_both",
            "pub_fb",
        ):

            fb_ok = await facebook(
                text_to_publish
            )

        if tg_ok or fb_ok:

            save_latest(
                price
            )

            if context.user_data.get(
                "first"
            ):

                save_first(
                    price
                )

        context.user_data.clear()

        if choice == "pub_both":

            if tg_ok and fb_ok:

                result = (
                    "✅ تم النشر "
                    "في تليجرام وفيسبوك."
                )

            elif tg_ok:

                result = (
                    "⚠️ تم النشر "
                    "في تليجرام فقط.\n"
                    "❌ فشل فيسبوك."
                )

            elif fb_ok:

                result = (
                    "⚠️ تم النشر "
                    "في فيسبوك فقط.\n"
                    "❌ فشل تليجرام."
                )

            else:

                result = (
                    "❌ فشل النشر."
                )

        elif choice == "pub_tg":

            result = (
                "✅ تم النشر في تليجرام."
                if tg_ok
                else
                "❌ فشل النشر في تليجرام."
            )

        else:

            result = (
                "✅ تم النشر في فيسبوك."
                if fb_ok
                else
                "❌ فشل النشر في فيسبوك."
            )

        await query.edit_message_text(
            result,
            reply_markup=home(True),
        )

        return


# =========================================================
# ERROR HANDLER
# =========================================================

async def error(
    update,
    context,
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

    if not BOT_TOKEN:

        raise Exception(
            "BOT_TOKEN is missing"
        )

    if not ADMIN_ID:

        raise Exception(
            "ADMIN_ID is missing"
        )

    if not DATABASE_URL:

        raise Exception(
            "DATABASE_URL is missing"
        )

    init_db()

    app = (
        Application
        .builder()
        .token(
            BOT_TOKEN
        )
        .build()
    )

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

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo,
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            buttons
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text,
        )
    )

    app.add_error_handler(
        error
    )

    print(
        "Alhussieny Gold Bot Started..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
