import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import requests
import pymysql
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

# =========================================================
# VERSION
# =========================================================
VERSION = "ALHUSSIENY_FACEBOOK_FINAL_FIX_2026_08_12_V8"

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
except Exception:
    ADMIN_ID = 0

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


def init_db():
    c = db()

    try:
        with c.cursor() as x:

            x.execute("""
                CREATE TABLE IF NOT EXISTS Categories(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    parent_id BIGINT UNSIGNED NULL,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX(parent_id)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS Products(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    category VARCHAR(255) NULL,
                    Photo_id TEXT NOT NULL,
                    category_id BIGINT UNSIGNED NULL,
                    name VARCHAR(255) NULL,
                    code VARCHAR(100) NULL,
                    price DECIMAL(15,2) NULL,
                    description TEXT NULL,
                    INDEX(category_id)
                )
            """)

            upgrades = [
                "ALTER TABLE Products ADD COLUMN category_id BIGINT UNSIGNED NULL",
                "ALTER TABLE Products ADD COLUMN name VARCHAR(255) NULL",
                "ALTER TABLE Products ADD COLUMN code VARCHAR(100) NULL",
                "ALTER TABLE Products ADD COLUMN price DECIMAL(15,2) NULL",
                "ALTER TABLE Products ADD COLUMN description TEXT NULL",
            ]

            for q in upgrades:
                try:
                    x.execute(q)
                except Exception:
                    pass

            x.execute("""
                SELECT DISTINCT category
                FROM Products
                WHERE category IS NOT NULL
                  AND TRIM(category) <> ''
                  AND (category_id IS NULL OR category_id = 0)
            """)

            for r in x.fetchall():

                name = r["category"].strip()

                x.execute("""
                    SELECT id
                    FROM Categories
                    WHERE parent_id IS NULL
                      AND LOWER(TRIM(name)) = LOWER(TRIM(%s))
                    LIMIT 1
                """, (name,))

                m = x.fetchone()

                if not m:
                    x.execute(
                        "INSERT INTO Categories(parent_id,name) VALUES(NULL,%s)",
                        (name,),
                    )
                    mid = x.lastrowid
                else:
                    mid = m["id"]

                x.execute("""
                    SELECT id
                    FROM Categories
                    WHERE parent_id=%s
                      AND LOWER(TRIM(name))='عام'
                    LIMIT 1
                """, (mid,))

                s = x.fetchone()

                if not s:
                    x.execute(
                        "INSERT INTO Categories(parent_id,name) VALUES(%s,'عام')",
                        (mid,),
                    )
                    sid = x.lastrowid
                else:
                    sid = s["id"]

                x.execute("""
                    UPDATE Products
                    SET category_id=%s
                    WHERE category=%s
                      AND (category_id IS NULL OR category_id=0)
                """, (sid, name))

    finally:
        c.close()


def one(sql, args=()):
    c = db()

    try:
        with c.cursor() as x:
            x.execute(sql, args)
            return x.fetchone()

    finally:
        c.close()


def many(sql, args=()):
    c = db()

    try:
        with c.cursor() as x:
            x.execute(sql, args)
            return x.fetchall()

    finally:
        c.close()


# =========================================================
# CATEGORIES
# =========================================================

def add_main(name):

    if one("""
        SELECT id
        FROM Categories
        WHERE parent_id IS NULL
          AND LOWER(TRIM(name))=LOWER(TRIM(%s))
    """, (name,)):
        return None

    c = db()

    try:
        with c.cursor() as x:

            x.execute(
                "INSERT INTO Categories(parent_id,name) VALUES(NULL,%s)",
                (name.strip(),),
            )

            return x.lastrowid

    finally:
        c.close()


def add_sub(parent, name):

    if one("""
        SELECT id
        FROM Categories
        WHERE parent_id=%s
          AND LOWER(TRIM(name))=LOWER(TRIM(%s))
    """, (parent, name)):
        return None

    c = db()

    try:
        with c.cursor() as x:

            x.execute(
                "INSERT INTO Categories(parent_id,name) VALUES(%s,%s)",
                (parent, name.strip()),
            )

            return x.lastrowid

    finally:
        c.close()


def cats(parent=None):

    if parent is None:

        return many("""
            SELECT id,name
            FROM Categories
            WHERE parent_id IS NULL
            ORDER BY name
        """)

    return many("""
        SELECT c.id,c.name,COUNT(p.id) product_count
        FROM Categories c
        LEFT JOIN Products p ON p.category_id=c.id
        WHERE c.parent_id=%s
        GROUP BY c.id,c.name
        ORDER BY c.name
    """, (parent,))


def cat(cid):

    return one(
        "SELECT id,parent_id,name FROM Categories WHERE id=%s",
        (cid,),
    )


def rename_cat(cid, name):

    c = db()

    try:
        with c.cursor() as x:

            x.execute(
                "UPDATE Categories SET name=%s WHERE id=%s",
                (name.strip(), cid),
            )

    finally:
        c.close()


def del_cat(cid):

    if one(
        "SELECT id FROM Products WHERE category_id=%s LIMIT 1",
        (cid,),
    ):
        return "products"

    if one(
        "SELECT id FROM Categories WHERE parent_id=%s LIMIT 1",
        (cid,),
    ):
        return "children"

    c = db()

    try:
        with c.cursor() as x:

            x.execute(
                "DELETE FROM Categories WHERE id=%s",
                (cid,),
            )

            return "deleted" if x.rowcount else "missing"

    finally:
        c.close()


# =========================================================
# PRODUCTS
# =========================================================

def add_product(cid, photo, name, code, price, desc):

    c = db()

    try:
        with c.cursor() as x:

            parent = cat(cid)

            x.execute("""
                INSERT INTO Products
                (category,Photo_id,category_id,name,code,price,description)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
            """, (
                parent["name"] if parent else "",
                photo,
                cid,
                name,
                code,
                price,
                desc,
            ))

            return x.lastrowid

    finally:
        c.close()


def products(cid):

    return many("""
        SELECT id,Photo_id,name,code,price,description
        FROM Products
        WHERE category_id=%s
        ORDER BY id DESC
    """, (cid,))


def all_products():

    return many("""
        SELECT p.*,c.name sub_name,m.name main_name
        FROM Products p
        LEFT JOIN Categories c ON c.id=p.category_id
        LEFT JOIN Categories m ON m.id=c.parent_id
        ORDER BY p.id DESC
    """)


def del_product(pid):

    c = db()

    try:
        with c.cursor() as x:

            x.execute(
                "DELETE FROM Products WHERE id=%s",
                (pid,),
            )

            return bool(x.rowcount)

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

    return datetime.now(TZ).strftime("%Y-%m-%d")


def yesterday():

    return (
        datetime.now(TZ) - timedelta(days=1)
    ).strftime("%Y-%m-%d")


def load_json(path):

    try:

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:

        return {}


def save_json(path, data):

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def first_today():

    return load_json(HISTORY).get(today())


def save_first(p):

    h = load_json(HISTORY)

    if today() not in h:

        h[today()] = round(p)

        save_json(HISTORY, h)

        return True

    return False


def latest():

    return load_json(LATEST).get("price")


def save_latest(p):

    save_json(
        LATEST,
        {
            "price": round(p),
            "updated_at": datetime.now(TZ).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        },
    )


def comparison(p):

    old = load_json(HISTORY).get(yesterday())

    if old is None:
        return None

    d = round(p - old)

    if d > 0:
        return f"📈 عيار 21 ارتفع {d} جنيه عن أول سعر أمس"

    if d < 0:
        return f"📉 عيار 21 انخفض {abs(d)} جنيه عن أول سعر أمس"

    return "➖ عيار 21 مستقر عن أول سعر أمس"


def price_text(p):

    p24, p21, p18 = calc(p)

    c = comparison(p)

    return "\n".join(
        ([c, ""] if c else [])
        + [
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

        k.append([
            InlineKeyboardButton(
                "👑 لوحة التحكم",
                callback_data="admin",
            )
        ])

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
# HELPERS
# =========================================================

def is_admin(update):

    return bool(
        update.effective_user
        and update.effective_user.id == ADMIN_ID
    )


async def start(update, context):

    context.user_data.clear()

    await update.message.reply_text(
        "💎 مجوهرات الحسيني\n\n"
        "أهلاً بيك في البوت الرسمي لمجوهرات الحسيني - بورسعيد ✨\n\n"
        "اختار من القائمة 👇",
        reply_markup=home(is_admin(update)),
    )


async def show_id(update, context):

    if is_admin(update):

        await update.message.reply_text(
            f"🆔 Telegram ID الخاص بالأدمن:\n\n{ADMIN_ID}"
        )

    else:

        await update.message.reply_text(
            "❌ الأمر ده متاح للأدمن فقط."
        )


# =========================================================
# FACEBOOK - FINAL PUBLISH + DIRECT VERIFY
# =========================================================

async def facebook(text):

    """
    FINAL FACEBOOK FLOW

    1) Create a Page feed post using /PAGE_ID/feed.
    2) Get the returned Post ID.
    3) Read THAT SAME Post ID directly.
    4) Verify:
       - id
       - message
       - from
       - created_time
       - permalink_url
       - is_published

    IMPORTANT:
    We DO NOT call /PAGE_ID/posts anymore.

    Reason:
    Meta may reject the Page /posts feed-read endpoint with
    pages_read_engagement / Page Public Content Access even when
    the exact Post ID can be read successfully.

    Therefore /PAGE_ID/posts is NOT used as a publishing success test.
    """

    print("\n========================================", flush=True)
    print("FACEBOOK FINAL PUBLISH START", flush=True)
    print(f"BOT VERSION: {VERSION}", flush=True)
    print("RUNNING FILE: bot.py", flush=True)
    print(
        f"FACEBOOK_PAGE_ID: {FACEBOOK_PAGE_ID}",
        flush=True,
    )
    print(
        "FACEBOOK_PAGE_TOKEN present: "
        f"{bool(FACEBOOK_PAGE_ACCESS_TOKEN)}",
        flush=True,
    )
    print("========================================", flush=True)

    # -----------------------------------------------------
    # CONFIG CHECK
    # -----------------------------------------------------

    if not FACEBOOK_PAGE_ID:

        return {
            "ok": False,
            "message": (
                "❌ FACEBOOK_PAGE_ID غير موجود "
                "في Railway Variables."
            ),
        }

    if not FACEBOOK_PAGE_ACCESS_TOKEN:

        return {
            "ok": False,
            "message": (
                "❌ FACEBOOK_PAGE_TOKEN غير موجود "
                "في Railway Variables."
            ),
        }

    # -----------------------------------------------------
    # GRAPH API VERSION
    # -----------------------------------------------------

    graph_version = os.getenv(
        "FACEBOOK_GRAPH_VERSION",
        "v26.0",
    ).strip()

    if not graph_version.startswith("v"):

        graph_version = "v" + graph_version

    base_url = (
        f"https://graph.facebook.com/{graph_version}"
    )

    feed_url = (
        f"{base_url}/{FACEBOOK_PAGE_ID}/feed"
    )

    print(
        f"Facebook Graph API Version: {graph_version}",
        flush=True,
    )

    print(
        f"Facebook Feed URL: {feed_url}",
        flush=True,
    )

    try:

        # =================================================
        # 1) CREATE POST
        # =================================================

        response = requests.post(
            feed_url,
            data={
                "message": text,
                "published": "true",
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )

        print(
            f"Facebook Create Status: "
            f"{response.status_code}",
            flush=True,
        )

        print(
            f"Facebook Create Response: "
            f"{response.text}",
            flush=True,
        )

        try:
            data = response.json()
        except Exception:
            data = {}

        # -------------------------------------------------
        # CREATE ERROR
        # -------------------------------------------------

        if not (200 <= response.status_code < 300):

            err = (
                data.get("error", {})
                if isinstance(data, dict)
                else {}
            )

            return {
                "ok": False,
                "message": (
                    "❌ Facebook رفض إنشاء المنشور.\n\n"
                    f"الرسالة: "
                    f"{err.get('message', response.text)}\n"
                    f"Type: {err.get('type', '')}\n"
                    f"Code: {err.get('code', '')}\n"
                    f"Subcode: "
                    f"{err.get('error_subcode', '')}"
                ),
            }

        # =================================================
        # 2) GET POST ID
        # =================================================

        post_id = (
            data.get("id")
            or data.get("post_id")
        )

        if not post_id:

            return {
                "ok": False,
                "message": (
                    "⚠️ Facebook رجع نجاح "
                    "لكن لم يرجع Post ID.\n\n"
                    f"Response:\n{response.text}"
                ),
            }

        print(
            f"Facebook Post ID: {post_id}",
            flush=True,
        )

        # =================================================
        # 3) DIRECT POST VERIFICATION
        # =================================================

        verify_url = (
            f"{base_url}/{post_id}"
        )

        verify_fields = (
            "id,"
            "message,"
            "from,"
            "created_time,"
            "permalink_url,"
            "is_published"
        )

        permalink = None
        is_published = None
        verified_message = None
        verified_from = None
        verified_created_time = None

        verify_error = None

        try:

            verify_response = requests.get(
                verify_url,
                params={
                    "fields": verify_fields,
                    "access_token": (
                        FACEBOOK_PAGE_ACCESS_TOKEN
                    ),
                },
                timeout=30,
            )

            print(
                "Facebook Direct Verify Status: "
                f"{verify_response.status_code}",
                flush=True,
            )

            print(
                "Facebook Direct Verify Response: "
                f"{verify_response.text}",
                flush=True,
            )

            try:
                verify_data = (
                    verify_response.json()
                )
            except Exception:
                verify_data = {}

            if verify_response.status_code < 300:

                permalink = verify_data.get(
                    "permalink_url"
                )

                is_published = verify_data.get(
                    "is_published"
                )

                verified_message = verify_data.get(
                    "message"
                )

                verified_from = verify_data.get(
                    "from"
                )

                verified_created_time = (
                    verify_data.get(
                        "created_time"
                    )
                )

            else:

                err = (
                    verify_data.get("error", {})
                    if isinstance(
                        verify_data,
                        dict
                    )
                    else {}
                )

                verify_error = (
                    err.get(
                        "message",
                        verify_response.text,
                    )
                )

        except requests.RequestException as e:

            verify_error = (
                f"Network error: {repr(e)}"
            )

        except Exception as e:

            verify_error = (
                f"Verification exception: "
                f"{repr(e)}"
            )

        # =================================================
        # 4) FALLBACK PERMALINK
        # =================================================

        if not permalink:

            post_part = str(post_id).split(
                "_",
                1,
            )[-1]

            permalink = (
                "https://www.facebook.com/"
                f"{FACEBOOK_PAGE_ID}/posts/"
                f"{post_part}"
            )

        # =================================================
        # 5) DETERMINE FINAL STATUS
        # =================================================

        direct_verify_ok = (
            verify_error is None
            and is_published is True
        )

        # =================================================
        # 6) BUILD DIAGNOSTIC MESSAGE
        # =================================================

        if direct_verify_ok:

            result_lines = [
                "✅ Facebook: تم نشر المنشور بنجاح.",
                "",
                "🆔 Post ID:",
                str(post_id),
                "",
                "🔗 رابط المنشور:",
                permalink,
                "",
                "🟢 Meta قرأت نفس الـPost ID بنجاح.",
                "🟢 is_published = true",
                "",
                "🟢 تم التأكد من المنشور مباشرة.",
                "",
                "⚠️ ملاحظة:",
                "البوت لم يعد يعتمد على Page /posts "
                "كاختبار للنشر.",
            ]

            if verified_from:

                if isinstance(
                    verified_from,
                    dict
                ):

                    from_name = (
                        verified_from.get("name")
                    )

                    from_id = (
                        verified_from.get("id")
                    )

                    if from_name:

                        result_lines.extend([
                            "",
                            f"📘 الصفحة: {from_name}",
                        ])

                    if from_id:

                        result_lines.append(
                            f"🆔 Page ID: {from_id}"
                        )

            if verified_created_time:

                result_lines.extend([
                    "",
                    "🕒 وقت الإنشاء:",
                    str(verified_created_time),
                ])

            result = "\n".join(
                result_lines
            )

            print(
                "FACEBOOK FINAL RESULT:",
                flush=True,
            )

            print(
                result,
                flush=True,
            )

            print(
                "========================================\n",
                flush=True,
            )

            return {
                "ok": True,
                "message": result,
                "post_id": post_id,
                "permalink": permalink,
                "is_published": is_published,
                "direct_verify": True,
                "verified_message": (
                    verified_message
                ),
                "verified_from": (
                    verified_from
                ),
                "verified_created_time": (
                    verified_created_time
                ),
            }

        # =================================================
        # 7) POST CREATED BUT VERIFICATION FAILED
        # =================================================

        if verify_error:

            result = "\n".join([
                "🟡 Facebook أنشأ المنشور.",
                "",
                "🆔 Post ID:",
                str(post_id),
                "",
                "🔗 رابط المنشور:",
                permalink,
                "",
                "⚠️ لكن تعذر قراءة نفس الـPost "
                "مباشرة بعد الإنشاء.",
                "",
                "خطأ التحقق:",
                str(verify_error),
                "",
                "❗ ده ليس فشلًا في إنشاء الـPost.",
            ])

        else:

            result = "\n".join([
                "🟡 Facebook أنشأ المنشور.",
                "",
                "🆔 Post ID:",
                str(post_id),
                "",
                "🔗 رابط المنشور:",
                permalink,
                "",
                "⚠️ Meta لم ترجع "
                "is_published = true "
                "في التحقق المباشر.",
                "",
                f"Published value: "
                f"{is_published}",
            ])

        print(
            "FACEBOOK FINAL RESULT:",
            flush=True,
        )

        print(
            result,
            flush=True,
        )

        print(
            "========================================\n",
            flush=True,
        )

        return {
            "ok": False,
            "message": result,
            "post_id": post_id,
            "permalink": permalink,
            "is_published": is_published,
            "direct_verify": False,
            "verification_error": verify_error,
        }

    # =====================================================
    # NETWORK ERROR
    # =====================================================

    except requests.RequestException as e:

        msg = (
            "❌ خطأ شبكة أثناء الاتصال بـ Facebook:\n"
            f"{repr(e)}"
        )

        print(msg, flush=True)

        return {
            "ok": False,
            "message": msg,
        }

    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as e:

        msg = (
            "❌ Exception أثناء النشر على Facebook:\n"
            f"{repr(e)}"
        )

        print(msg, flush=True)

        return {
            "ok": False,
            "message": msg,
        }


# =========================================================
# TELEGRAM PUBLISH
# =========================================================

async def tg(context, text):

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
            repr(e),
            flush=True,
        )

        return False


# =========================================================
# PHOTO
# =========================================================

async def photo(update, context):

    if not is_admin(update):

        await update.message.reply_text(
            "❌ غير مسموح."
        )

        return

    if context.user_data.get(
        "state"
    ) != "product_photo":

        await update.message.reply_text(
            "❌ ابدأ إضافة المنتج من لوحة التحكم."
        )

        return

    cid = context.user_data.get("cid")

    try:

        pid = add_product(
            cid,
            update.message.photo[-1].file_id,
            context.user_data.get("name"),
            context.user_data.get("code"),
            context.user_data.get("price"),
            context.user_data.get("desc"),
        )

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ تم إضافة المنتج بنجاح.\n🆔 #{pid}",
            reply_markup=prod_menu(),
        )

    except Exception as e:

        print(
            "Product error:",
            repr(e),
            flush=True,
        )

        context.user_data.clear()

        await update.message.reply_text(
            "❌ حصل خطأ أثناء حفظ المنتج.",
            reply_markup=prod_menu(),
        )


# =========================================================
# TEXT STATES
# =========================================================

async def text(update, context):

    if not update.message:
        return

    t = (
        update.message.text
        or ""
    ).strip()

    s = context.user_data.get("state")

    # =====================================================
    # GOLD STATE
    # =====================================================

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

        except Exception:

            await update.message.reply_text(
                "❌ اكتب سعر عيار 21 صحيح، "
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

    # =====================================================
    # MAIN CATEGORY
    # =====================================================

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

    # =====================================================
    # SUB CATEGORY
    # =====================================================

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

    # =====================================================
    # RENAME
    # =====================================================

    if s == "rename":

        cid = context.user_data.get(
            "cid"
        )

        if cid and t:

            rename_cat(cid, t)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تغيير الاسم.",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # PRODUCT NAME
    # =====================================================

    if s == "prod_name":

        context.user_data["name"] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data["state"] = (
            "prod_code"
        )

        await update.message.reply_text(
            "🔖 اكتب كود المنتج، "
            "أو اكتب: بدون"
        )

        return

    # =====================================================
    # PRODUCT CODE
    # =====================================================

    if s == "prod_code":

        context.user_data["code"] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data["state"] = (
            "prod_price"
        )

        await update.message.reply_text(
            "💰 اكتب سعر المنتج، "
            "أو اكتب: بدون"
        )

        return

    # =====================================================
    # PRODUCT PRICE
    # =====================================================

    if s == "prod_price":

        if t.lower() == "بدون":

            v = None

        else:

            try:

                v = float(t)

                if v < 0:
                    raise ValueError

            except Exception:

                await update.message.reply_text(
                    "❌ اكتب رقم صحيح أو: بدون"
                )

                return

        context.user_data["price"] = v

        context.user_data["state"] = (
            "prod_desc"
        )

        await update.message.reply_text(
            "📝 اكتب وصف المنتج، "
            "أو اكتب: بدون"
        )

        return

    # =====================================================
    # PRODUCT DESCRIPTION
    # =====================================================

    if s == "prod_desc":

        context.user_data["desc"] = (
            None
            if t.lower() == "بدون"
            else t
        )

        context.user_data["state"] = (
            "product_photo"
        )

        await update.message.reply_text(
            "📸 تمام، ابعت صورة المنتج الآن."
        )

        return

    # =====================================================
    # NUMERIC GOLD PRICE
    # =====================================================

    try:

        p = float(t)
        numeric = True

    except Exception:

        numeric = False
        p = None

    if numeric:

        if not is_admin(update):

            await update.message.reply_text(
                "❌ أسعار الذهب متاحة للأدمن فقط."
            )

            return

        context.user_data.update(
            price_text=price_text(p),
            price=round(p),
            first=first_today() is None,
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
        reply_markup=home(is_admin(update)),
    )


# =========================================================
# BUTTONS
# =========================================================

async def buttons(update, context):

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
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ الرئيسية",
                            callback_data="home",
                        )
                    ]
                ]),
            )

            return

        k = [
            [
                InlineKeyboardButton(
                    "💍 " + m["name"],
                    callback_data=(
                        f"cm:{m['id']}"
                    ),
                )
            ]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ الرئيسية",
                callback_data="home",
            )
        ])

        await q.edit_message_text(
            "💍 منتجات مجوهرات الحسيني\n\n"
            "اختار القسم:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # MAIN CATEGORY CLIENT
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
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ المنتجات",
                            callback_data="products",
                        )
                    ]
                ]),
            )

            return

        k = [
            [
                InlineKeyboardButton(
                    f"🟡 {s['name']} "
                    f"({s['product_count']})",
                    callback_data=(
                        f"cs:{s['id']}"
                    ),
                )
            ]
            for s in ss
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ الأقسام",
                callback_data="products",
            )
        ])

        await q.edit_message_text(
            f"💍 {m['name']}\n\n"
            "اختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SUB CATEGORY CLIENT
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
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data=(
                                f"cm:{s['parent_id']}"
                            ),
                        )
                    ]
                ]),
            )

            return

        await q.edit_message_text(
            f"🟡 {s['name']}\n\n"
            f"عدد المنتجات: {len(ps)}"
        )

        for p in ps:

            parts = []

            if p["name"]:

                parts.append(
                    f"💍 {p['name']}"
                )

            if p["code"]:

                parts.append(
                    f"🔖 الكود: {p['code']}"
                )

            if p["price"] is not None:

                parts.append(
                    f"💰 السعر: "
                    f"{p['price']} جنيه"
                )

            if p["description"]:

                parts.append(
                    f"\n{p['description']}"
                )

            try:

                await q.message.reply_photo(
                    photo=p["Photo_id"],
                    caption=(
                        "\n".join(parts)
                        or None
                    ),
                )

            except Exception as e:

                print(
                    "Product Photo Error:",
                    repr(e),
                    flush=True,
                )

        return

    # =====================================================
    # GOLD ADMIN
    # =====================================================

    if c == "agold":

        if not is_admin(update):
            return

        p = latest()

        await q.edit_message_text(
            "💰 إدارة أسعار الذهب\n\n"
            + (
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

        context.user_data["state"] = (
            "gold"
        )

        await q.edit_message_text(
            "✏️ ابعت سعر عيار 21 الجديد.\n"
            "مثال: 7000"
        )

        return

    # =====================================================
    # HISTORY
    # =====================================================

    if c == "history":

        h = load_json(HISTORY)

        txt = "📜 سجل الأسعار\n\n"

        if h:

            txt += "\n".join(
                f"📅 {d} — {p} جنيه"
                for d, p in sorted(
                    h.items(),
                    reverse=True,
                )[:30]
            )

        else:

            txt += "لا يوجد سجل."

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
    # CATEGORIES ADMIN
    # =====================================================

    if c == "acat":

        if not is_admin(update):
            return

        await q.edit_message_text(
            "📂 إدارة الأقسام\n\n"
            "القسم الرئيسي → "
            "القسم الفرعي → المنتجات",
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # ADD MAIN CATEGORY
    # =====================================================

    if c == "addmain":

        context.user_data.clear()

        context.user_data["state"] = (
            "main"
        )

        await q.edit_message_text(
            "➕ اكتب اسم القسم الرئيسي.\n"
            "مثال: خواتم"
        )

        return

    # =====================================================
    # ADD SUB CATEGORY
    # =====================================================

    if c == "addsub":

        ms = cats()

        k = [
            [
                InlineKeyboardButton(
                    "💍 " + m["name"],
                    callback_data=(
                        f"sp:{m['id']}"
                    ),
                )
            ]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="acat",
            )
        ])

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT MAIN FOR SUB CATEGORY
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
            f"➕ اكتب القسم الفرعي تحت:\n"
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

            for s in cats(m["id"]):

                lines.append(
                    f"   └ 🟡 {s['name']} "
                    f"({s['product_count']} منتج)"
                )

            lines.append("")

        await q.edit_message_text(
            (
                "\n".join(lines)
                if len(lines) > 2
                else
                "📂 لا توجد أقسام."
            ),
            reply_markup=cat_menu(),
        )

        return

    # =====================================================
    # RENAME CATEGORY
    # =====================================================

    if c == "rename":

        k = []

        for m in cats():

            k.append([
                InlineKeyboardButton(
                    "✏️ " + m["name"],
                    callback_data=(
                        f"rp:{m['id']}"
                    ),
                )
            ])

            for s in cats(m["id"]):

                k.append([
                    InlineKeyboardButton(
                        f"   ✏️ "
                        f"{m['name']} → "
                        f"{s['name']}",
                        callback_data=(
                            f"rp:{s['id']}"
                        ),
                    )
                ])

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="acat",
            )
        ])

        await q.edit_message_text(
            "✏️ اختار القسم:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # RENAME SELECTED CATEGORY
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

            k.append([
                InlineKeyboardButton(
                    "🗑 " + m["name"],
                    callback_data=(
                        f"dc:{m['id']}"
                    ),
                )
            ])

            for s in cats(m["id"]):

                k.append([
                    InlineKeyboardButton(
                        f"   🗑 "
                        f"{m['name']} → "
                        f"{s['name']}",
                        callback_data=(
                            f"dc:{s['id']}"
                        ),
                    )
                ])

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="acat",
            )
        ])

        await q.edit_message_text(
            "🗑 اختار القسم للحذف:\n\n"
            "⚠️ لا يمكن حذف قسم يحتوي "
            "منتجات أو أقسام فرعية.",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # DELETE CATEGORY CONFIRM
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
    # PRODUCTS ADMIN
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
                    callback_data=(
                        f"pm:{m['id']}"
                    ),
                )
            ]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="aprod",
            )
        ])

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # SELECT MAIN PRODUCT CATEGORY
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
                    callback_data=(
                        f"ps:{s['id']}"
                    ),
                )
            ]
            for s in ss
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="addprod",
            )
        ])

        await q.edit_message_text(
            "➕ اختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(k),
        )

        return

    # =====================================================
    # PRODUCT DATA START
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
            (
                "\n".join(lines)
                if ps
                else
                "📋 لا توجد منتجات."
            ),
            reply_markup=prod_menu(),
        )

        return

    # =====================================================
    # DELETE PRODUCT MENU
    # =====================================================

    if c == "deleteprod":

        ps = all_products()

        k = [
            [
                InlineKeyboardButton(
                    f"🗑 #{p['id']} "
                    f"{p['name'] or 'بدون اسم'}",
                    callback_data=(
                        f"dp:{p['id']}"
                    ),
                )
            ]
            for p in ps[:50]
        ]

        k.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="aprod",
            )
        ])

        await q.edit_message_text(
            "🗑 اختار المنتج:",
            reply_markup=InlineKeyboardMarkup(k),
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
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ احذف",
                        callback_data=(
                            f"cdp:{pid}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="deleteprod",
                    )
                ],
            ]),
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
            (
                "✅ تم حذف المنتج."
                if del_product(pid)
                else
                "⚠️ المنتج غير موجود."
            ),
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
            reply_markup=InlineKeyboardMarkup([
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
            ]),
        )

        return

    # =====================================================
    # CLIENT GOLD
    # =====================================================

    if c == "gold":

        p = latest()

        await q.edit_message_text(
            (
                price_text(p)
                if p
                else
                "💎 لم يتم تحديث أسعار "
                "الذهب حتى الآن."
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ الرئيسية",
                        callback_data="home",
                    )
                ]
            ]),
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

        # =================================================
        # TELEGRAM
        # =================================================

        if c in (
            "pub_both",
            "pub_tg",
        ):

            tg_ok = await tg(
                context,
                txt,
            )

        # =================================================
        # FACEBOOK
        # =================================================

        if c in (
            "pub_both",
            "pub_fb",
        ):

            fb_result = await facebook(
                txt
            )

        fb_ok = bool(
            fb_result
            and fb_result.get("ok")
        )

        # =================================================
        # SAVE PRICE ONLY IF AT LEAST ONE
        # PLATFORM SUCCEEDED
        # =================================================

        if tg_ok or fb_ok:

            save_latest(p)

            if context.user_data.get(
                "first"
            ):

                save_first(p)

        context.user_data.clear()

        # =================================================
        # FACEBOOK ONLY
        # =================================================

        if c == "pub_fb":

            await q.edit_message_text(
                (
                    fb_result.get(
                        "message",
                        "❌ فشل النشر على Facebook.",
                    )
                    if fb_result
                    else
                    "❌ لم يتم تنفيذ "
                    "النشر على Facebook."
                ),
                reply_markup=home(True),
            )

            return

        # =================================================
        # TELEGRAM ONLY
        # =================================================

        if c == "pub_tg":

            await q.edit_message_text(
                (
                    "✅ تم النشر في تليجرام."
                    if tg_ok
                    else
                    "❌ فشل النشر في تليجرام."
                ),
                reply_markup=home(True),
            )

            return

        # =================================================
        # BOTH
        # =================================================

        result_lines = []

        result_lines.append(
            "✅ Telegram: تم النشر."
            if tg_ok
            else
            "❌ Telegram: فشل النشر."
        )

        # =================================================
        # FACEBOOK SUCCESS
        # =================================================

        if fb_ok:

            result_lines.append(
                "✅ Facebook: تم النشر."
            )

            if fb_result.get(
                "post_id"
            ):

                result_lines.append(
                    "\n🆔 Post ID:\n"
                    f"{fb_result['post_id']}"
                )

            if fb_result.get(
                "permalink"
            ):

                result_lines.append(
                    "\n🔗 رابط المنشور:\n"
                    f"{fb_result['permalink']}"
                )

            if fb_result.get(
                "is_published"
            ) is not None:

                result_lines.append(
                    "\n🟢 Published: "
                    f"{'نعم' if fb_result.get('is_published') else 'لا'}"
                )

            result_lines.append(
                "\n🟢 تم التحقق من نفس "
                "الـPost ID مباشرة."
            )

        # =================================================
        # FACEBOOK FAILURE
        # =================================================

        else:

            result_lines.append(
                "\n"
                + (
                    fb_result.get(
                        "message",
                        "❌ Facebook: فشل النشر.",
                    )
                    if fb_result
                    else
                    "❌ Facebook: فشل النشر."
                )
            )

        await q.edit_message_text(
            "\n".join(result_lines),
            reply_markup=home(True),
        )

        return


# =========================================================
# ERROR
# =========================================================

async def error(update, context):

    print(
        "========================================",
        flush=True,
    )

    print(
        "BOT ERROR:",
        repr(context.error),
        flush=True,
    )

    print(
        "========================================",
        flush=True,
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

    print(
        "========================================",
        flush=True,
    )

    print(
        "Alhussieny Gold Bot Starting...",
        flush=True,
    )

    print(
        "RUNNING FILE: bot.py",
        flush=True,
    )

    print(
        f"BOT VERSION: {VERSION}",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
    )

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

    app.add_error_handler(error)

    print(
        "Alhussieny Gold Bot Started...",
        flush=True,
    )

    print(
        f"READY VERSION: {VERSION}",
        flush=True,
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
