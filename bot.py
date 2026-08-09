import os, json
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
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_PAGE_TOKEN", ""
).strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

try:
    ADMIN_ID = int(
        os.getenv("ADMIN_ID", "0").strip()
    )
except:
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
# DATABASE
# =========================================================

def db():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL is missing"
        )

    u = urlparse(
        DATABASE_URL
    )

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


def init_db():

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                CREATE TABLE IF NOT EXISTS Categories(

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

            x.execute(
                """
                CREATE TABLE IF NOT EXISTS Products(

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

            for q in [

                """
                ALTER TABLE Products
                ADD COLUMN category_id
                BIGINT UNSIGNED NULL
                """,

                """
                ALTER TABLE Products
                ADD COLUMN name
                VARCHAR(255) NULL
                """,

                """
                ALTER TABLE Products
                ADD COLUMN code
                VARCHAR(100) NULL
                """,

                """
                ALTER TABLE Products
                ADD COLUMN price
                DECIMAL(15,2) NULL
                """,

                """
                ALTER TABLE Products
                ADD COLUMN description
                TEXT NULL
                """,

            ]:

                try:
                    x.execute(q)
                except:
                    pass

            # -------------------------------------------------
            # Migrate old products
            # -------------------------------------------------

            x.execute(
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

            for r in x.fetchall():

                name = r["category"].strip()

                x.execute(
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

                m = x.fetchone()

                if not m:

                    x.execute(
                        """
                        INSERT INTO Categories
                        (parent_id, name)

                        VALUES
                        (NULL, %s)
                        """,
                        (name,),
                    )

                    mid = x.lastrowid

                else:

                    mid = m["id"]

                x.execute(
                    """
                    SELECT id

                    FROM Categories

                    WHERE parent_id = %s

                    AND LOWER(TRIM(name))
                    = 'عام'

                    LIMIT 1
                    """,
                    (mid,),
                )

                s = x.fetchone()

                if not s:

                    x.execute(
                        """
                        INSERT INTO Categories
                        (parent_id, name)

                        VALUES
                        (%s, 'عام')
                        """,
                        (mid,),
                    )

                    sid = x.lastrowid

                else:

                    sid = s["id"]

                x.execute(
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
                        sid,
                        name,
                    ),
                )

    finally:

        c.close()


def one(
    sql,
    args=(),
):

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                sql,
                args,
            )

            return x.fetchone()

    finally:

        c.close()


def many(
    sql,
    args=(),
):

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                sql,
                args,
            )

            return x.fetchall()

    finally:

        c.close()


# =========================================================
# CATEGORIES
# =========================================================

def add_main(name):

    if one(
        """
        SELECT id

        FROM Categories

        WHERE parent_id IS NULL

        AND LOWER(TRIM(name))
        =
        LOWER(TRIM(%s))
        """,
        (name,),
    ):

        return None

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                INSERT INTO Categories
                (parent_id, name)

                VALUES
                (NULL, %s)
                """,
                (name.strip(),),
            )

            return x.lastrowid

    finally:

        c.close()


def add_sub(
    parent,
    name,
):

    if one(
        """
        SELECT id

        FROM Categories

        WHERE parent_id = %s

        AND LOWER(TRIM(name))
        =
        LOWER(TRIM(%s))
        """,
        (
            parent,
            name,
        ),
    ):

        return None

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                INSERT INTO Categories
                (parent_id, name)

                VALUES
                (%s, %s)
                """,
                (
                    parent,
                    name.strip(),
                ),
            )

            return x.lastrowid

    finally:

        c.close()


def cats(parent=None):

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
            COUNT(p.id) product_count

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


def cat(cid):

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

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                UPDATE Categories

                SET name = %s

                WHERE id = %s
                """,
                (
                    name.strip(),
                    cid,
                ),
            )

    finally:

        c.close()


def del_cat(cid):

    if one(
        """
        SELECT id

        FROM Products

        WHERE category_id = %s

        LIMIT 1
        """,
        (cid,),
    ):

        return "products"

    if one(
        """
        SELECT id

        FROM Categories

        WHERE parent_id = %s

        LIMIT 1
        """,
        (cid,),
    ):

        return "children"

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                DELETE FROM Categories

                WHERE id = %s
                """,
                (cid,),
            )

            return (
                "deleted"
                if x.rowcount
                else
                "missing"
            )

    finally:

        c.close()


# =========================================================
# PRODUCTS
# =========================================================

def add_product(
    cid,
    photo,
    name,
    code,
    price,
    desc,
):

    c = db()

    try:

        with c.cursor() as x:

            parent = cat(cid)

            x.execute(
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
                    parent["name"]
                    if parent
                    else "",
                    photo,
                    cid,
                    name,
                    code,
                    price,
                    desc,
                ),
            )

            return x.lastrowid

    finally:

        c.close()


def products(cid):

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
            c.name sub_name,
            m.name main_name

        FROM Products p

        LEFT JOIN Categories c
        ON c.id = p.category_id

        LEFT JOIN Categories m
        ON m.id = c.parent_id

        ORDER BY p.id DESC
        """
    )


def del_product(pid):

    c = db()

    try:

        with c.cursor() as x:

            x.execute(
                """
                DELETE FROM Products

                WHERE id = %s
                """,
                (pid,),
            )

            return bool(
                x.rowcount
            )

    finally:

        c.close()


# =========================================================
# GOLD
# =========================================================

def calc(p):

    return (
        round(p * 8 / 7),
        round(p),
        round(p * 6 / 7),
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


def load_json(path):

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    except:

        return {}


def save_json(
    path,
    data,
):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def first_today():

    return load_json(
        HISTORY
    ).get(
        today()
    )


def save_first(p):

    h = load_json(
        HISTORY
    )

    if today() not in h:

        h[
            today()
        ] = round(p)

        save_json(
            HISTORY,
            h,
        )

        return True

    return False


def latest():

    return load_json(
        LATEST
    ).get(
        "price"
    )


def save_latest(p):

    save_json(
        LATEST,
        {
            "price": round(p),
            "updated_at":
                datetime.now(
                    TZ
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
        },
    )


def comparison(p):

    old = load_json(
        HISTORY
    ).get(
        yesterday()
    )

    if old is None:
        return None

    d = round(
        p - old
    )

    if d > 0:

        return (
            f"📈 عيار 21 ارتفع "
            f"{d} جنيه عن أول سعر أمس"
        )

    if d < 0:

        return (
            f"📉 عيار 21 انخفض "
            f"{abs(d)} جنيه عن أول سعر أمس"
        )

    return (
        "➖ عيار 21 مستقر "
        "عن أول سعر أمس"
    )


def price_text(p):

    p24, p21, p18 = calc(p)

    c = comparison(p)

    return "\n".join(
        (
            ([c, ""] if c else [])
            +
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
    )


# =========================================================
# MENUS
# =========================================================

def home(admin=False):

    k = [

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

        k += [
            [
                InlineKeyboardButton(
                    "👑 لوحة التحكم",
                    callback_data="admin",
                )
            ]
        ]

    k += [

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

    return InlineKeyboardMarkup(k)


def admin_menu():

    return InlineKeyboardMarkup([

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

    ])


def cat_menu():

    return InlineKeyboardMarkup([

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

    ])


def prod_menu():

    return InlineKeyboardMarkup([

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

    ])


def gold_menu():

    return InlineKeyboardMarkup([

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

    ])


def publish_menu():

    return InlineKeyboardMarkup([

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

    ])


# =========================================================
# BOT HELPERS
# =========================================================

def is_admin(u):

    return bool(
        u.effective_user
        and
        u.effective_user.id
        == ADMIN_ID
    )


async def start(
    update,
    context,
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


async def show_id(
    update,
    context,
):

    if is_admin(update):

        await update.message.reply_text(
            f"🆔 Telegram ID الخاص بالأدمن:\n\n"
            f"{ADMIN_ID}"
        )

    else:

        await update.message.reply_text(
            "❌ الأمر ده متاح للأدمن فقط."
        )


# =========================================================
# FACEBOOK - DEBUG VERSION
# =========================================================

async def facebook(text):

    print("")
    print("========================================")
    print("FACEBOOK PUBLISH START")
    print("========================================")

    # -----------------------------------------------------
    # Check variables
    # -----------------------------------------------------

    if not FACEBOOK_PAGE_ID:

        print(
            "FACEBOOK ERROR: "
            "FACEBOOK_PAGE_ID is missing"
        )

        return {
            "ok": False,
            "message":
                "FACEBOOK_PAGE_ID غير موجود في Variables.",
        }

    if not FACEBOOK_PAGE_ACCESS_TOKEN:

        print(
            "FACEBOOK ERROR: "
            "FACEBOOK_PAGE_TOKEN is missing"
        )

        return {
            "ok": False,
            "message":
                "FACEBOOK_PAGE_TOKEN غير موجود في Variables.",
        }

    print(
        "Facebook Page ID:",
        FACEBOOK_PAGE_ID
    )

    print(
        "Facebook Token:",
        "FOUND"
    )

    # -----------------------------------------------------
    # Publish
    # -----------------------------------------------------

    url = (
        "https://graph.facebook.com/"
        "v23.0/"
        f"{FACEBOOK_PAGE_ID}/feed"
    )

    payload = {
        "message": text,
        "access_token":
            FACEBOOK_PAGE_ACCESS_TOKEN,
    }

    try:

        response = requests.post(
            url,
            data=payload,
            timeout=30,
        )

        print(
            "Facebook HTTP Status:",
            response.status_code
        )

        print(
            "Facebook Raw Response:",
            response.text
        )

        # -------------------------------------------------
        # Try JSON
        # -------------------------------------------------

        try:

            data = response.json()

        except:

            data = {
                "raw":
                    response.text
            }

        # -------------------------------------------------
        # Facebook Error
        # -------------------------------------------------

        if response.status_code != 200:

            error_data = (
                data.get(
                    "error",
                    {}
                )
                if isinstance(
                    data,
                    dict
                )
                else {}
            )

            error_message = (
                error_data.get(
                    "message"
                )
                or
                data.get(
                    "message"
                )
                or
                response.text
            )

            error_type = (
                error_data.get(
                    "type",
                    ""
                )
            )

            error_code = (
                error_data.get(
                    "code",
                    ""
                )
            )

            error_subcode = (
                error_data.get(
                    "error_subcode",
                    ""
                )
            )

            final_message = (
                "❌ Facebook رفض النشر.\n\n"
                f"الرسالة: {error_message}\n"
                f"Type: {error_type}\n"
                f"Code: {error_code}\n"
                f"Subcode: {error_subcode}"
            )

            print(
                "FACEBOOK ERROR:",
                final_message
            )

            print(
                "========================================"
            )

            return {
                "ok": False,
                "message":
                    final_message,
            }

        # -------------------------------------------------
        # Get Post ID
        # -------------------------------------------------

        post_id = None

        if isinstance(
            data,
            dict
        ):

            post_id = data.get(
                "id"
            )

            if not post_id:

                post_id = data.get(
                    "post_id"
                )

        print(
            "Facebook Post ID:",
            post_id
        )

        # -------------------------------------------------
        # Verify post
        # -------------------------------------------------

        verify_data = None

        if post_id:

            verify_url = (
                "https://graph.facebook.com/"
                "v23.0/"
                f"{post_id}"
            )

            verify_params = {

                "fields":
                    "id,message,from,created_time,permalink_url",

                "access_token":
                    FACEBOOK_PAGE_ACCESS_TOKEN,
            }

            try:

                verify_response = requests.get(
                    verify_url,
                    params=verify_params,
                    timeout=30,
                )

                print(
                    "Facebook Verify Status:",
                    verify_response.status_code
                )

                print(
                    "Facebook Verify Response:",
                    verify_response.text
                )

                try:

                    verify_data = (
                        verify_response.json()
                    )

                except:

                    verify_data = None

            except Exception as e:

                print(
                    "Facebook Verify Error:",
                    repr(e)
                )

        # -------------------------------------------------
        # Build result
        # -------------------------------------------------

        permalink = None

        if isinstance(
            verify_data,
            dict
        ):

            permalink = (
                verify_data.get(
                    "permalink_url"
                )
            )

        if post_id:

            result_text = (
                "✅ Facebook قبل النشر.\n\n"
                f"🆔 Post ID:\n{post_id}"
            )

            if permalink:

                result_text += (
                    "\n\n🔗 رابط المنشور:\n"
                    f"{permalink}"
                )

            result_text += (
                "\n\n"
                "📌 راجع الرابط ده؛ "
                "ده نفس المنشور اللي رجعته Meta."
            )

        else:

            result_text = (
                "⚠️ Facebook رجع نجاح "
                "لكن لم يرجع Post ID.\n\n"
                f"Response:\n{response.text}"
            )

        print(
            "FACEBOOK FINAL RESULT:",
            result_text
        )

        print(
            "========================================"
        )

        return {
            "ok": True,
            "message":
                result_text,
            "post_id":
                post_id,
            "permalink":
                permalink,
        }

    except Exception as e:

        error_text = (
            "❌ حصل Exception أثناء "
            "الاتصال بـ Facebook.\n\n"
            f"{repr(e)}"
        )

        print(
            "FACEBOOK EXCEPTION:",
            error_text
        )

        print(
            "========================================"
        )

        return {
            "ok": False,
            "message":
                error_text,
        }


# =========================================================
# TELEGRAM
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
            repr(e)
        )

        return False


# =========================================================
# PHOTO
# =========================================================

async def photo(
    update,
    context,
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

        pid = add_product(
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
            f"✅ تم إضافة المنتج بنجاح.\n"
            f"🆔 #{pid}",
            reply_markup=prod_menu(),
        )

    except Exception as e:

        print(
            "Product error:",
            repr(e)
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
    update,
    context,
):

    if not update.message:
        return

    t = (
        update.message.text
        or ""
    ).strip()

    s = context.user_data.get(
        "state"
    )

    # -----------------------------------------------------
    # GOLD
    # -----------------------------------------------------

    if s == "gold":

        if not is_admin(update):

            context.user_data.clear()

            await update.message.reply_text(
                "❌ غير مسموح."
            )

            return

        try:

            p = float(t)

            if p <= 0:
                raise ValueError

        except:

            await update.message.reply_text(
                "❌ اكتب سعر عيار 21 صحيح.\n"
                "مثال: 7000"
            )

            return

        save_latest(p)

        if first_today() is None:

            save_first(p)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تحديث السعر.\n\n"
            + price_text(p),
            reply_markup=gold_menu(),
        )

        return

    # -----------------------------------------------------
    # MAIN CATEGORY
    # -----------------------------------------------------

    if s == "main":

        if not t:

            await update.message.reply_text(
                "❌ اكتب اسم القسم."
            )

            return

        if add_main(t) is None:

            await update.message.reply_text(
                "⚠️ القسم موجود بالفعل.",
                reply_markup=cat_menu(),
            )

        else:

            await update.message.reply_text(
                f"✅ تم إضافة القسم الرئيسي:\n"
                f"💍 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()

        return

    # -----------------------------------------------------
    # SUB CATEGORY
    # -----------------------------------------------------

    if s == "sub":

        pid = context.user_data.get(
            "parent"
        )

        if not pid or not t:

            await update.message.reply_text(
                "❌ اكتب اسم القسم الفرعي."
            )

            return

        if add_sub(pid, t) is None:

            await update.message.reply_text(
                "⚠️ القسم الفرعي موجود بالفعل.",
                reply_markup=cat_menu(),
            )

        else:

            await update.message.reply_text(
                f"✅ تم إضافة القسم الفرعي:\n"
                f"🟡 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()

        return

    # -----------------------------------------------------
    # RENAME
    # -----------------------------------------------------

    if s == "rename":

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

    # -----------------------------------------------------
    # PRODUCT NAME
    # -----------------------------------------------------

    if s == "prod_name":

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
            "🔖 اكتب كود المنتج، "
            "أو اكتب: بدون"
        )

        return

    # -----------------------------------------------------
    # PRODUCT CODE
    # -----------------------------------------------------

    if s == "prod_code":

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
            "💰 اكتب سعر المنتج، "
            "أو اكتب: بدون"
        )

        return

    # -----------------------------------------------------
    # PRODUCT PRICE
    # -----------------------------------------------------

    if s == "prod_price":

        if t.lower() == "بدون":

            v = None

        else:

            try:

                v = float(t)

                if v < 0:
                    raise ValueError

            except:

                await update.message.reply_text(
                    "❌ اكتب رقم صحيح أو: بدون"
                )

                return

        context.user_data[
            "price"
        ] = v

        context.user_data[
            "state"
        ] = "prod_desc"

        await update.message.reply_text(
            "📝 اكتب وصف المنتج، "
            "أو اكتب: بدون"
        )

        return

    # -----------------------------------------------------
    # PRODUCT DESCRIPTION
    # -----------------------------------------------------

    if s == "prod_desc":

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
            "📸 تمام، ابعت صورة المنتج الآن."
        )

        return

    # -----------------------------------------------------
    # DIRECT GOLD PRICE
    # -----------------------------------------------------

    try:

        p = float(t)

        numeric = True

    except:

        numeric = False
        p = None

    if numeric:

        if not is_admin(update):

            await update.message.reply_text(
                "❌ أسعار الذهب متاحة "
                "للأدمن فقط."
            )

            return

        context.user_data.update(
            price_text=price_text(p),
            price=round(p),
            first=(
                first_today()
                is None
            ),
        )

        await update.message.reply_text(
            f"السعر: {round(p)}\n\n"
            "📢 عايز تنشر الأسعار فين؟",
            reply_markup=publish_menu(),
        )

        return

    await update.message.reply_text(
        "❌ مش فاهم طلبك.\n"
        "استخدم /start لفتح القائمة.",
        reply_markup=home(
            is_admin(update)
        ),
    )


# =========================================================
# BUTTONS
# =========================================================

async def buttons(
    update,
    context,
):

    q = update.callback_query

    await q.answer()

    c = q.data

    # =====================================================
    # HOME
    # =====================================================

    if c == "home":

        context.user_data.clear()

        await q.edit_message_text(
            "💎 مجوهرات الحسيني\n\n"
            "اختار من القائمة 👇",
            reply_markup=home(
                is_admin(update)
            ),
        )

        return

    # =====================================================
    # ADMIN
    # =====================================================

    if c == "admin":

        if not is_admin(update):

            await q.answer(
                "❌ غير مسموح.",
                show_alert=True,
            )

            return

        context.user_data.clear()

        await q.edit_message_text(
            "👑 لوحة التحكم\n\n"
            "اختار العملية:",
            reply_markup=admin_menu(),
        )

        return

    # =====================================================
    # CLIENT PRODUCTS
    # =====================================================

    if c == "products":

        ms = cats()

        if not ms:

            await q.edit_message_text(
                "💍 المنتجات\n\n"
                "لا توجد أقسام حالياً.",
                reply_markup=
                InlineKeyboardMarkup(
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

        k = [

            [
                InlineKeyboardButton(
                    "💍 " + m["name"],
                    callback_data=
                    f"cm:{m['id']}",
                )
            ]

            for m in ms

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ الرئيسية",
                    callback_data="home",
                )
            ]
        )

        await q.edit_message_text(
            "💍 منتجات مجوهرات الحسيني\n\n"
            "اختار القسم:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # MAIN CATEGORY
    # =====================================================

    if c.startswith("cm:"):

        mid = int(
            c.split(":")[1]
        )

        m = cat(mid)

        ss = cats(mid)

        if not ss:

            await q.edit_message_text(
                f"💍 {m['name']}\n\n"
                "لا توجد أقسام فرعية.",
                reply_markup=
                InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ المنتجات",
                                callback_data=
                                "products",
                            )
                        ]
                    ]
                ),
            )

            return

        k = [

            [
                InlineKeyboardButton(
                    f"🟡 {s['name']} "
                    f"({s['product_count']})",
                    callback_data=
                    f"cs:{s['id']}",
                )
            ]

            for s in ss

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ الأقسام",
                    callback_data="products",
                )
            ]
        )

        await q.edit_message_text(
            f"💍 {m['name']}\n\n"
            "اختار القسم الفرعي:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SUB CATEGORY
    # =====================================================

    if c.startswith("cs:"):

        sid = int(
            c.split(":")[1]
        )

        s = cat(sid)

        ps = products(sid)

        if not ps:

            await q.edit_message_text(
                f"🟡 {s['name']}\n\n"
                "لا توجد منتجات.",
                reply_markup=
                InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ رجوع",
                                callback_data=
                                f"cm:{s['parent_id']}",
                            )
                        ]
                    ]
                ),
            )

            return

        await q.edit_message_text(
            f"🟡 {s['name']}\n\n"
            f"عدد المنتجات: {len(ps)}"
        )

        for p in ps:

            cap = "\n".join(
                [
                    x
                    for x in [

                        (
                            f"💍 {p['name']}"
                            if p["name"]
                            else ""
                        ),

                        (
                            f"🔖 الكود: "
                            f"{p['code']}"
                            if p["code"]
                            else ""
                        ),

                        (
                            f"💰 السعر: "
                            f"{p['price']} جنيه"
                            if p["price"]
                            is not None
                            else ""
                        ),

                        (
                            f"\n{p['description']}"
                            if p["description"]
                            else ""
                        ),

                    ]
                    if x
                ]
            )

            try:

                await q.message.reply_photo(
                    photo=p["Photo_id"],
                    caption=
                    cap
                    or None,
                )

            except Exception as e:

                print(
                    "Product Photo Error:",
                    repr(e)
                )

        return

    # =====================================================
    # ADMIN GOLD
    # =====================================================

    if c == "agold":

        if not is_admin(update):
            return

        p = latest()

        await q.edit_message_text(
            "💰 إدارة أسعار الذهب\n\n"
            +
            (
                price_text(p)
                if p
                else
                "لا يوجد سعر محفوظ."
            ),
            reply_markup=gold_menu(),
        )

        return

    # =====================================================
    # UPDATE GOLD
    # =====================================================

    if c == "updategold":

        if not is_admin(update):
            return

        context.user_data.clear()

        context.user_data[
            "state"
        ] = "gold"

        await q.edit_message_text(
            "✏️ ابعت سعر عيار 21 الجديد.\n"
            "مثال: 7000"
        )

        return

    # =====================================================
    # HISTORY
    # =====================================================

    if c == "history":

        h = load_json(
            HISTORY
        )

        txt = (
            "📜 سجل الأسعار\n\n"
            +
            (
                "\n".join(
                    f"📅 {d} — {p} جنيه"
                    for d, p
                    in sorted(
                        h.items(),
                        reverse=True,
                    )[:30]
                )
                if h
                else
                "لا يوجد سجل."
            )
        )

        await q.edit_message_text(
            txt,
            reply_markup=gold_menu(),
        )

        return

    # =====================================================
    # PUBLISH MENU
    # =====================================================

    if c == "publish":

        if not is_admin(update):
            return

        p = latest()

        if not p:

            await q.edit_message_text(
                "❌ لا يوجد سعر محفوظ.",
                reply_markup=gold_menu(),
            )

            return

        context.user_data.update(
            price_text=price_text(p),
            price=round(p),
            first=False,
        )

        await q.edit_message_text(
            "📢 اختار مكان النشر:",
            reply_markup=publish_menu(),
        )

        return

    # =====================================================
    # ADMIN CATEGORIES
    # =====================================================

    if c == "acat":

        if not is_admin(update):
            return

        await q.edit_message_text(
            "📂 إدارة الأقسام\n\n"
            "القسم الرئيسي → "
            "القسم الفرعي → "
            "المنتجات",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # ADD MAIN
    # =====================================================

    if c == "addmain":

        context.user_data.clear()

        context.user_data[
            "state"
        ] = "main"

        await q.edit_message_text(
            "➕ اكتب اسم القسم الرئيسي.\n"
            "مثال: خواتم"
        )

        return

    # =====================================================
    # ADD SUB
    # =====================================================

    if c == "addsub":

        ms = cats()

        k = [

            [
                InlineKeyboardButton(
                    "💍 " + m["name"],
                    callback_data=
                    f"sp:{m['id']}",
                )
            ]

            for m in ms

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT MAIN
    # =====================================================

    if c.startswith("sp:"):

        mid = int(
            c.split(":")[1]
        )

        context.user_data.clear()

        context.user_data.update(
            state="sub",
            parent=mid,
        )

        await q.edit_message_text(
            "➕ اكتب القسم الفرعي تحت:\n"
            f"{cat(mid)['name']}\n\n"
            "مثال: عيار 18"
        )

        return

    # =====================================================
    # VIEW CATEGORIES
    # =====================================================

    if c == "viewcats":

        lines = [
            "📂 الأقسام",
            "",
        ]

        for m in cats():

            lines.append(
                "💍 " + m["name"]
            )

            for s in cats(
                m["id"]
            ):

                lines.append(
                    f"   └ 🟡 "
                    f"{s['name']} "
                    f"({s['product_count']} منتج)"
                )

            lines.append("")

        await q.edit_message_text(
            "\n".join(lines)
            if len(lines) > 2
            else
            "📂 لا توجد أقسام.",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # RENAME
    # =====================================================

    if c == "rename":

        k = []

        for m in cats():

            k.append(
                [
                    InlineKeyboardButton(
                        "✏️ " + m["name"],
                        callback_data=
                        f"rp:{m['id']}",
                    )
                ]
            )

            for s in cats(
                m["id"]
            ):

                k.append(
                    [
                        InlineKeyboardButton(
                            f"   ✏️ "
                            f"{m['name']} → "
                            f"{s['name']}",
                            callback_data=
                            f"rp:{s['id']}",
                        )
                    ]
                )

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await q.edit_message_text(
            "✏️ اختار القسم:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT RENAME
    # =====================================================

    if c.startswith("rp:"):

        cid = int(
            c.split(":")[1]
        )

        context.user_data.clear()

        context.user_data.update(
            state="rename",
            cid=cid,
        )

        await q.edit_message_text(
            f"✏️ الاسم الحالي: "
            f"{cat(cid)['name']}\n\n"
            "اكتب الاسم الجديد:"
        )

        return

    # =====================================================
    # DELETE CATEGORY
    # =====================================================

    if c == "deletecat":

        k = []

        for m in cats():

            k.append(
                [
                    InlineKeyboardButton(
                        "🗑 " + m["name"],
                        callback_data=
                        f"dc:{m['id']}",
                    )
                ]
            )

            for s in cats(
                m["id"]
            ):

                k.append(
                    [
                        InlineKeyboardButton(
                            f"   🗑 "
                            f"{m['name']} → "
                            f"{s['name']}",
                            callback_data=
                            f"dc:{s['id']}",
                        )
                    ]
                )

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="acat",
                )
            ]
        )

        await q.edit_message_text(
            "🗑 اختار القسم للحذف:\n\n"
            "⚠️ لا يمكن حذف قسم يحتوي "
            "منتجات أو أقسام فرعية.",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # DELETE CATEGORY RESULT
    # =====================================================

    if c.startswith("dc:"):

        cid = int(
            c.split(":")[1]
        )

        r = del_cat(cid)

        msg = {

            "deleted":
                "✅ تم الحذف.",

            "products":
                "⚠️ القسم يحتوي منتجات، "
                "احذفها أولاً.",

            "children":
                "⚠️ القسم يحتوي أقسام فرعية، "
                "احذفها أولاً.",

            "missing":
                "⚠️ القسم غير موجود.",

        }[r]

        await q.edit_message_text(
            msg,
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # ADMIN PRODUCTS
    # =====================================================

    if c == "aprod":

        if not is_admin(update):
            return

        await q.edit_message_text(
            "💍 إدارة المنتجات",
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # ADD PRODUCT
    # =====================================================

    if c == "addprod":

        ms = cats()

        k = [

            [
                InlineKeyboardButton(
                    "💍 " + m["name"],
                    callback_data=
                    f"pm:{m['id']}",
                )
            ]

            for m in ms

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="aprod",
                )
            ]
        )

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT MAIN FOR PRODUCT
    # =====================================================

    if c.startswith("pm:"):

        mid = int(
            c.split(":")[1]
        )

        ss = cats(mid)

        k = [

            [
                InlineKeyboardButton(
                    "🟡 " + s["name"],
                    callback_data=
                    f"ps:{s['id']}",
                )
            ]

            for s in ss

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="addprod",
                )
            ]
        )

        await q.edit_message_text(
            "➕ اختار القسم الفرعي:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT SUB FOR PRODUCT
    # =====================================================

    if c.startswith("ps:"):

        sid = int(
            c.split(":")[1]
        )

        context.user_data.clear()

        context.user_data.update(
            state="prod_name",
            cid=sid,
        )

        await q.edit_message_text(
            "💎 اكتب اسم المنتج.\n"
            "مثال: خاتم ذهب موديل ناعم"
        )

        return

    # =====================================================
    # VIEW PRODUCTS
    # =====================================================

    if c == "viewprod":

        ps = all_products()

        lines = [
            "📋 المنتجات",
            "",
        ]

        for p in ps[:50]:

            lines.append(
                f"🆔 #{p['id']} | "
                f"{p['main_name'] or '-'} → "
                f"{p['sub_name'] or '-'}\n"
                f"💎 {p['name'] or 'بدون اسم'} | "
                f"🔖 {p['code'] or '-'}"
            )

        await q.edit_message_text(
            "\n".join(lines)
            if ps
            else
            "📋 لا توجد منتجات.",
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # DELETE PRODUCT
    # =====================================================

    if c == "deleteprod":

        ps = all_products()

        k = [

            [
                InlineKeyboardButton(
                    f"🗑 #{p['id']} "
                    f"{p['name'] or 'بدون اسم'}",
                    callback_data=
                    f"dp:{p['id']}",
                )
            ]

            for p in ps[:50]

        ]

        k.append(
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="aprod",
                )
            ]
        )

        await q.edit_message_text(
            "🗑 اختار المنتج:",
            reply_markup=
            InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # DELETE PRODUCT CONFIRM
    # =====================================================

    if c.startswith("dp:"):

        pid = int(
            c.split(":")[1]
        )

        await q.edit_message_text(
            f"⚠️ تأكيد حذف المنتج #{pid}",
            reply_markup=
            InlineKeyboardMarkup(
                [

                    [
                        InlineKeyboardButton(
                            "✅ احذف",
                            callback_data=
                            f"cdp:{pid}",
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "❌ إلغاء",
                            callback_data=
                            "deleteprod",
                        )
                    ],

                ]
            ),
        )

        return

    # =====================================================
    # DELETE PRODUCT
    # =====================================================

    if c.startswith("cdp:"):

        pid = int(
            c.split(":")[1]
        )

        await q.edit_message_text(
            "✅ تم حذف المنتج."
            if del_product(pid)
            else
            "⚠️ المنتج غير موجود.",
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # PHONE
    # =====================================================

    if c == "phone":

        await q.edit_message_text(
            f"📞 مجوهرات الحسيني\n\n"
            f"{PHONE}\n\n"
            "للتواصل المباشر:",
            reply_markup=
            InlineKeyboardMarkup(
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

    if c == "gold":

        p = latest()

        await q.edit_message_text(
            price_text(p)
            if p
            else
            "💎 لم يتم تحديث أسعار الذهب "
            "حتى الآن.",
            reply_markup=
            InlineKeyboardMarkup(
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

    if c in (
        "pub_both",
        "pub_tg",
        "pub_fb",
    ):

        if not is_admin(update):
            return

        txt = context.user_data.get(
            "price_text"
        )

        p = context.user_data.get(
            "price"
        )

        if not txt or p is None:

            await q.edit_message_text(
                "❌ السعر انتهى.",
                reply_markup=home(True),
            )

            return

        tg_ok = False
        fb_result = None

        # -------------------------------------------------
        # Telegram
        # -------------------------------------------------

        if c in (
            "pub_both",
            "pub_tg",
        ):

            tg_ok = await tg(
                context,
                txt,
            )

        # -------------------------------------------------
        # Facebook
        # -------------------------------------------------

        if c in (
            "pub_both",
            "pub_fb",
        ):

            fb_result = await facebook(
                txt
            )

        fb_ok = (
            fb_result is not None
            and
            fb_result.get(
                "ok",
                False
            )
        )

        # -------------------------------------------------
        # Save price only if at least
        # one platform succeeded
        # -------------------------------------------------

        if tg_ok or fb_ok:

            save_latest(p)

            if context.user_data.get(
                "first"
            ):

                save_first(p)

        context.user_data.clear()

        # -------------------------------------------------
        # FACEBOOK ONLY
        # -------------------------------------------------

        if c == "pub_fb":

            if fb_ok:

                await q.edit_message_text(
                    fb_result.get(
                        "message",
                        "✅ تم النشر على Facebook."
                    ),
                    reply_markup=
                    home(True),
                )

            else:

                await q.edit_message_text(
                    fb_result.get(
                        "message",
                        "❌ فشل النشر على Facebook."
                    )
                    if fb_result
                    else
                    "❌ لم يتم تنفيذ النشر على Facebook.",
                    reply_markup=
                    home(True),
                )

            return

        # -------------------------------------------------
        # TELEGRAM ONLY
        # -------------------------------------------------

        if c == "pub_tg":

            await q.edit_message_text(
                "✅ تم النشر في تليجرام."
                if tg_ok
                else
                "❌ فشل النشر في تليجرام.",
                reply_markup=home(True),
            )

            return

        # -------------------------------------------------
        # BOTH
        # -------------------------------------------------

        result_lines = []

        if tg_ok:

            result_lines.append(
                "✅ Telegram: تم النشر."
            )

        else:

            result_lines.append(
                "❌ Telegram: فشل النشر."
            )

        if fb_ok:

            result_lines.append(
                "✅ Facebook: تم النشر."
            )

            if fb_result.get(
                "post_id"
            ):

                result_lines.append(
                    "\n🆔 Post ID:"
                )

                result_lines.append(
                    str(
                        fb_result[
                            "post_id"
                        ]
                    )
                )

            if fb_result.get(
                "permalink"
            ):

                result_lines.append(
                    "\n🔗 رابط المنشور:"
                )

                result_lines.append(
                    fb_result[
                        "permalink"
                    ]
                )

        else:

            result_lines.append(
                "\n"
                +
                (
                    fb_result.get(
                        "message",
                        "❌ Facebook: فشل النشر."
                    )
                    if fb_result
                    else
                    "❌ Facebook: فشل النشر."
                )
            )

        await q.edit_message_text(
            "\n".join(
                result_lines
            ),
            reply_markup=home(True),
        )

        return


# =========================================================
# ERROR
# =========================================================

async def error(
    update,
    context,
):

    print(
        "========================================"
    )

    print(
        "BOT ERROR:",
        repr(context.error)
    )

    print(
        "========================================"
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
