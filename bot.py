import os
import json
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, quote

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
VERSION = "ALHUSSIENY_FACEBOOK_PUBLIC_FIX_2026_08_12_V13"

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
                name = (r["category"] or "").strip()
                if not name:
                    continue

                x.execute("""
                    SELECT id FROM Categories
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
                    SELECT id FROM Categories
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
        SELECT id FROM Categories
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
        SELECT id FROM Categories
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
            SELECT id,name FROM Categories
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
    if one("SELECT id FROM Products WHERE category_id=%s LIMIT 1", (cid,)):
        return "products"

    if one("SELECT id FROM Categories WHERE parent_id=%s LIMIT 1", (cid,)):
        return "children"

    c = db()
    try:
        with c.cursor() as x:
            x.execute("DELETE FROM Categories WHERE id=%s", (cid,))
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
                photo, cid, name, code, price, desc,
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
            x.execute("DELETE FROM Products WHERE id=%s", (pid,))
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
    return (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    save_json(LATEST, {
        "price": round(p),
        "updated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
    })


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
        [InlineKeyboardButton("💎 أسعار الذهب", callback_data="gold")],
        [InlineKeyboardButton("💍 المنتجات", callback_data="products")],
    ]

    if admin:
        k.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")])

    k += [
        [InlineKeyboardButton("📢 قناة التليجرام", url=TG_CHANNEL)],
        [
            InlineKeyboardButton("📍 موقع المحل", url=MAPS),
            InlineKeyboardButton("🌐 الموقع", url=WEBSITE),
        ],
        [
            InlineKeyboardButton("💬 واتساب", url=WHATSAPP),
            InlineKeyboardButton("📞 رقم المحل", callback_data="phone"),
        ],
        [
            InlineKeyboardButton("📘 فيسبوك", url=FACEBOOK),
            InlineKeyboardButton("📸 إنستجرام", url=INSTAGRAM),
        ],
    ]
    return InlineKeyboardMarkup(k)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 إدارة أسعار الذهب", callback_data="agold")],
        [InlineKeyboardButton("💍 إدارة المنتجات", callback_data="aprod")],
        [InlineKeyboardButton("📂 إدارة الأقسام", callback_data="acat")],
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
    ])


def cat_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ قسم رئيسي", callback_data="addmain"),
            InlineKeyboardButton("➕ قسم فرعي", callback_data="addsub"),
        ],
        [InlineKeyboardButton("📋 عرض الأقسام", callback_data="viewcats")],
        [InlineKeyboardButton("✏️ تغيير اسم", callback_data="rename")],
        [InlineKeyboardButton("🗑 حذف قسم", callback_data="deletecat")],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def prod_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة منتج", callback_data="addprod")],
        [InlineKeyboardButton("📋 عرض المنتجات", callback_data="viewprod")],
        [InlineKeyboardButton("🗑 حذف منتج", callback_data="deleteprod")],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def gold_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تحديث السعر", callback_data="updategold")],
        [InlineKeyboardButton("📜 سجل الأسعار", callback_data="history")],
        [InlineKeyboardButton("📢 نشر السعر", callback_data="publish")],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def publish_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 تليجرام + فيسبوك", callback_data="pub_both")],
        [InlineKeyboardButton("📱 تليجرام فقط", callback_data="pub_tg")],
        [InlineKeyboardButton("📘 فيسبوك فقط", callback_data="pub_fb")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="home")],
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
        await update.message.reply_text("❌ الأمر ده متاح للأدمن فقط.")


# =========================================================
# FACEBOOK - PUBLIC PUBLISH V12
# =========================================================

def fb_error_text(data, fallback="Unknown Facebook error"):
    if isinstance(data, dict):
        e = data.get("error")
        if isinstance(e, dict):
            return (
                f"{e.get('message', fallback)}\n"
                f"Type: {e.get('type', '')}\n"
                f"Code: {e.get('code', '')}\n"
                f"Subcode: {e.get('error_subcode', '')}"
            )
    return fallback


def fb_request(method, url, *, params=None, data=None, timeout=30):
    if method == "GET":
        r = requests.get(url, params=params, timeout=timeout)
    else:
        r = requests.post(url, data=data, timeout=timeout)

    try:
        payload = r.json()
    except Exception:
        payload = {}

    return r, payload


async def facebook(text):
    """
    V10:
    - Requires PAGE Access Token.
    - Verifies the configured Page before publishing.
    - Publishes through /PAGE_ID/feed with published=true.
    - Reads the exact returned Post ID.
    - Verifies source Page, is_published and is_hidden.
    - Checks the Page itself is published.
    - Retries propagation.
    - NEVER reports success when the post is only an admin/unpublished object.
    """

    print("\n" + "=" * 60, flush=True)
    print("FACEBOOK PUBLIC PUBLISH V12 START", flush=True)
    print(f"VERSION: {VERSION}", flush=True)
    print(f"PAGE_ID: {FACEBOOK_PAGE_ID}", flush=True)
    print(
        f"PAGE_TOKEN PRESENT: {bool(FACEBOOK_PAGE_ACCESS_TOKEN)}",
        flush=True,
    )
    print("=" * 60, flush=True)

    if not FACEBOOK_PAGE_ID:
        return {
            "ok": False,
            "message": "❌ FACEBOOK_PAGE_ID غير موجود في Railway Variables.",
        }

    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        return {
            "ok": False,
            "message": "❌ FACEBOOK_PAGE_TOKEN غير موجود في Railway Variables.",
        }

    graph_version = os.getenv("FACEBOOK_GRAPH_VERSION", "v26.0").strip()
    if not graph_version.startswith("v"):
        graph_version = "v" + graph_version

    base = f"https://graph.facebook.com/{graph_version}"
    page_url = f"{base}/{FACEBOOK_PAGE_ID}"
    feed_url = f"{base}/{FACEBOOK_PAGE_ID}/feed"

    token = FACEBOOK_PAGE_ACCESS_TOKEN

    # -----------------------------------------------------
    # 1. VERIFY PAGE + TOKEN
    # -----------------------------------------------------
    try:
        r, page = fb_request(
            "GET",
            page_url,
            params={
                "fields": "id,name,is_published",
                "access_token": token,
            },
        )

        print(f"PAGE CHECK STATUS: {r.status_code}", flush=True)
        print(f"PAGE CHECK RESPONSE: {r.text}", flush=True)

        if r.status_code >= 300:
            return {
                "ok": False,
                "message": (
                    "❌ Facebook رفض قراءة الصفحة باستخدام التوكن الحالي.\n\n"
                    + fb_error_text(page)
                    + "\n\n"
                    "⚠️ لازم FACEBOOK_PAGE_TOKEN يكون Page Access Token "
                    "لنفس الصفحة."
                ),
            }

        returned_id = str(page.get("id", ""))
        page_name = page.get("name", "غير معروف")
        page_is_published = page.get("is_published")

        if returned_id != str(FACEBOOK_PAGE_ID):
            return {
                "ok": False,
                "message": (
                    "❌ FACEBOOK_PAGE_TOKEN لا يخص نفس الصفحة.\n\n"
                    f"FACEBOOK_PAGE_ID = {FACEBOOK_PAGE_ID}\n"
                    f"Meta returned = {returned_id or 'غير موجود'}"
                ),
            }

        if page_is_published is False:
            return {
                "ok": False,
                "message": (
                    "❌ الصفحة نفسها غير منشورة Public على Facebook.\n\n"
                    f"📘 الصفحة: {page_name}\n"
                    "لا يمكن للبوست أن يظهر للناس بشكل طبيعي "
                    "طالما الصفحة غير منشورة."
                ),
            }

    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ خطأ شبكة أثناء فحص صفحة Facebook:\n{repr(e)}",
        }

    # -----------------------------------------------------
    # 2. CREATE PUBLIC PAGE FEED POST
    # -----------------------------------------------------
    try:
        r, created = fb_request(
            "POST",
            feed_url,
            data={
                "message": text,
                "published": "true",
                "access_token": token,
            },
        )

        print(f"CREATE STATUS: {r.status_code}", flush=True)
        print(f"CREATE RESPONSE: {r.text}", flush=True)

        if r.status_code >= 300:
            return {
                "ok": False,
                "message": (
                    "❌ Facebook رفض إنشاء المنشور.\n\n"
                    + fb_error_text(created, r.text)
                ),
            }

        post_id = created.get("id") or created.get("post_id")

        if not post_id:
            return {
                "ok": False,
                "message": (
                    "⚠️ Facebook رجع نجاح لكن بدون Post ID.\n\n"
                    f"{r.text}"
                ),
            }

        print(f"POST ID: {post_id}", flush=True)

    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ خطأ شبكة أثناء إنشاء منشور Facebook:\n{repr(e)}",
        }

    # -----------------------------------------------------
    # 3. EXACT POST VERIFICATION
    # -----------------------------------------------------
    verify_url = f"{base}/{post_id}"

    fields = ",".join([
        "id",
        "message",
        "from",
        "created_time",
        "permalink_url",
        "is_published",
        "is_hidden",
    ])

    async def read_timeline_visibility():
        """Best-effort read of timeline_visibility.

        Meta may omit/restrict this field on some Page/API combinations, so
        failure here is diagnostic only and must not be treated as proof that
        the post is public.
        """
        try:
            r, data = fb_request(
                "GET",
                verify_url,
                params={
                    "fields": "id,timeline_visibility",
                    "access_token": token,
                },
            )
            print(f"TIMELINE VISIBILITY STATUS: {r.status_code}", flush=True)
            print(f"TIMELINE VISIBILITY RESPONSE: {r.text}", flush=True)
            if r.status_code < 300:
                return data.get("timeline_visibility"), None
            return None, fb_error_text(data, r.text)
        except requests.RequestException as e:
            return None, repr(e)

    def public_web_probe(permalink):
        """Probe Facebook's public post/embed URL without a Page token.

        This is intentionally treated as a secondary signal because Facebook
        can return bot/login/interstitial pages to server-side requests.
        """
        if not permalink or not permalink.startswith("http"):
            return {"status": "unknown", "reason": "missing_permalink"}

        try:
            embed_url = (
                "https://www.facebook.com/plugins/post.php?href="
                + quote(permalink, safe="")
                + "&show_text=true"
            )
            r = requests.get(
                embed_url,
                timeout=20,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                },
            )
            body = (r.text or "").lower()
            final_url = (r.url or "").lower()

            unavailable_markers = [
                "content isn't available",
                "this content isn't available",
                "page isn't available",
                "content not available",
                "post isn't available",
                "login/",
                "/login",
            ]
            if any(m in body or m in final_url for m in unavailable_markers):
                return {
                    "status": "not_public",
                    "http_status": r.status_code,
                    "final_url": r.url,
                }

            if r.status_code == 200:
                return {
                    "status": "public_probe_ok",
                    "http_status": r.status_code,
                    "final_url": r.url,
                }

            return {
                "status": "unknown",
                "http_status": r.status_code,
                "final_url": r.url,
            }
        except requests.RequestException as e:
            return {"status": "unknown", "reason": repr(e)}

    async def read_exact_post():
        try:
            r, data = fb_request(
                "GET",
                verify_url,
                params={
                    "fields": fields,
                    "access_token": token,
                },
            )

            print(
                f"POST VERIFY STATUS: {r.status_code}",
                flush=True,
            )
            print(
                f"POST VERIFY RESPONSE: {r.text}",
                flush=True,
            )

            if r.status_code >= 300:
                return False, {}, fb_error_text(data, r.text)

            return True, data, None

        except requests.RequestException as e:
            return False, {}, repr(e)

    verified = False
    post = {}
    verify_error = None

    # Meta can need several seconds before the object is readable.
    for attempt in range(1, 9):
        verified, post, verify_error = await read_exact_post()

        if verified:
            break

        print(
            f"Waiting for Facebook propagation {attempt}/8...",
            flush=True,
        )
        await asyncio.sleep(2)

    if not verified:
        return {
            "ok": False,
            "message": (
                "🟡 Facebook أنشأ الـPost ID لكن البوت لم يستطع "
                "قراءة نفس الـPost بعد الإنشاء.\n\n"
                f"🆔 Post ID: {post_id}\n\n"
                f"خطأ التحقق:\n{verify_error}\n\n"
                "⚠️ لن أعتبره Public بدون تحقق مباشر."
            ),
            "post_id": post_id,
            "direct_verify": False,
        }

    # -----------------------------------------------------
    # 4. VERIFY SOURCE PAGE
    # -----------------------------------------------------
    source = post.get("from")
    source_id = source.get("id") if isinstance(source, dict) else None

    if source_id and str(source_id) != str(FACEBOOK_PAGE_ID):
        return {
            "ok": False,
            "message": (
                "❌ المنشور تم إنشاؤه لكن مصدره لا يطابق الصفحة المطلوبة.\n\n"
                f"المطلوب: {FACEBOOK_PAGE_ID}\n"
                f"المصدر: {source_id}\n"
                f"Post ID: {post_id}"
            ),
            "post_id": post_id,
            "permalink": post.get("permalink_url"),
            "direct_verify": True,
        }

    # -----------------------------------------------------
    # 5. TRY TO REPAIR UNPUBLISHED/HIDDEN
    # -----------------------------------------------------
    repair_notes = []

    async def repair(**kwargs):
        try:
            payload = dict(kwargs)
            payload["access_token"] = token

            r, data = fb_request(
                "POST",
                verify_url,
                data=payload,
            )

            print(f"REPAIR STATUS: {r.status_code}", flush=True)
            print(f"REPAIR RESPONSE: {r.text}", flush=True)

            if r.status_code < 300:
                return True, data

            return False, data

        except requests.RequestException as e:
            return False, {"error": {"message": repr(e)}}

    if post.get("is_hidden") is True:
        ok, data = await repair(is_hidden="false")
        if ok:
            repair_notes.append("🟢 تم إرسال طلب إظهار المنشور.")
        else:
            repair_notes.append(
                "⚠️ فشل طلب إظهار المنشور: "
                + fb_error_text(data)
            )
        await asyncio.sleep(2)

    if post.get("is_published") is False:
        ok, data = await repair(published="true")
        if ok:
            repair_notes.append("🟢 تم إرسال طلب نشر المنشور.")
        else:
            repair_notes.append(
                "⚠️ فشل طلب نشر المنشور: "
                + fb_error_text(data)
            )
        await asyncio.sleep(2)

    # -----------------------------------------------------
    # 6. FINAL VERIFICATION - MULTIPLE READS
    # -----------------------------------------------------
    for attempt in range(1, 6):
        verified, post2, verify_error = await read_exact_post()

        if verified:
            post = post2

            if (
                post.get("is_published") is True
                and post.get("is_hidden") is not True
            ):
                break

        await asyncio.sleep(2)

    is_published = post.get("is_published")
    is_hidden = post.get("is_hidden")

    # -----------------------------------------------------
    # 7. PUBLIC VISIBILITY DIAGNOSTICS - V13
    # -----------------------------------------------------
    # Meta can return a canonical permalink whose first numeric ID is not the
    # configured Page ID. That permalink is useful as a diagnostic, but it is
    # NOT the URL we use to report the post back to the operator.
    #
    # Build a deterministic Page URL from the verified Page ID + the numeric
    # object ID. Keep Meta's permalink separately for diagnostics.
    meta_permalink = post.get("permalink_url") or ""
    post_part = str(post_id).split("_", 1)[-1]
    constructed_permalink = (
        f"https://www.facebook.com/{FACEBOOK_PAGE_ID}/posts/{post_part}"
    )

    # The object ID must belong to the configured Page.
    post_id_page = str(post_id).split("_", 1)[0] if "_" in str(post_id) else ""
    page_id_match = post_id_page == str(FACEBOOK_PAGE_ID)

    timeline_visibility, timeline_error = await read_timeline_visibility()

    # Probe BOTH URLs. A single Facebook server-side probe is not sufficient
    # proof because Facebook may return login/interstitial/challenge pages.
    constructed_probe = await asyncio.to_thread(
        public_web_probe, constructed_permalink
    )
    meta_probe = (
        await asyncio.to_thread(public_web_probe, meta_permalink)
        if meta_permalink and meta_permalink != constructed_permalink
        else {"status": "not_tested"}
    )

    print(f"POST_ID_PAGE: {post_id_page}", flush=True)
    print(f"PAGE_ID_MATCH: {page_id_match}", flush=True)
    print(f"CONSTRUCTED PERMALINK: {constructed_permalink}", flush=True)
    print(f"META PERMALINK: {meta_permalink}", flush=True)
    print(f"CONSTRUCTED PUBLIC WEB PROBE: {constructed_probe}", flush=True)
    print(f"META PUBLIC WEB PROBE: {meta_probe}", flush=True)
    print(f"TIMELINE_VISIBILITY: {timeline_visibility}", flush=True)

    # Do not label a post "not public" just because the Facebook plugins
    # endpoint rejects one URL. It is a weak/secondary server-side signal.
    # We only call it definitively unavailable when BOTH tested URLs return
    # the explicit unavailable marker.
    both_probes_not_public = (
        constructed_probe.get("status") == "not_public"
        and (
            meta_probe.get("status") in ("not_public", "not_tested")
        )
    )

    if both_probes_not_public:
        web_probe = {
            "status": "not_public",
            "constructed": constructed_probe,
            "meta": meta_probe,
        }
    elif (
        constructed_probe.get("status") == "public_probe_ok"
        or meta_probe.get("status") == "public_probe_ok"
    ):
        web_probe = {
            "status": "public_probe_ok",
            "constructed": constructed_probe,
            "meta": meta_probe,
        }
    else:
        web_probe = {
            "status": "unknown",
            "constructed": constructed_probe,
            "meta": meta_probe,
        }

    # Use the deterministic URL for Telegram. Keep Meta's URL in diagnostics.
    permalink = constructed_permalink

    # Page-token verification proves Meta created a published Page object.
    # The tokenized Graph API cannot by itself prove anonymous public access.
    # We therefore report the two signals separately.
    page_api_ok = (
        verified
        and is_published is True
        and is_hidden is not True
        and page_id_match
        and (not source_id or str(source_id) == str(FACEBOOK_PAGE_ID))
    )

    if not page_api_ok:
        diagnostic = [
            "❌ Facebook: المنشور اتعمل لكن حالة النشر غير سليمة.",
            "",
            f"🆔 Post ID: {post_id}",
        f"🔗 Public link: {constructed_permalink}",
        + (f"🔗 Meta permalink: {meta_permalink}\n" if meta_permalink else ""),
            f"🟢 is_published = {is_published}",
            f"🟢 is_hidden = {is_hidden}",
            f"🆔 Page ID = {FACEBOOK_PAGE_ID}",
            f"🆔 Post belongs to Page ID = {post_id_page}",
            f"🟢 Page ID match = {page_id_match}",
            f"🔗 Meta permalink = {permalink}",
        ]
        if timeline_visibility is not None:
            diagnostic.append(f"🟡 timeline_visibility = {timeline_visibility}")
        if repair_notes:
            diagnostic += ["", "🔧 محاولات الإصلاح:"] + repair_notes
        diagnostic += ["", "⚠️ لن أعتبره منشورًا Public."]
        return {
            "ok": False,
            "message": "\n".join(diagnostic),
            "post_id": post_id,
            "permalink": permalink,
            "is_published": is_published,
            "is_hidden": is_hidden,
            "timeline_visibility": timeline_visibility,
            "public_probe": web_probe,
            "direct_verify": True,
        }

    # If the anonymous/public probe explicitly says unavailable, fail.
    # If it is inconclusive, do NOT lie and call the post Public Success.
    if web_probe.get("status") == "not_public":
        return {
            "ok": False,
            "message": (
                "⚠️ Facebook أنشأ المنشور وGraph API شايفه منشور، "
                "لكن فحصيْن للظهور العام رجعا أن المحتوى غير متاح.\n\n"
                f"🆔 Post ID: {post_id}\n"
                f"🔗 الرابط الحقيقي من Meta:\n{permalink}\n\n"
                f"🟢 is_published = {is_published}\n"
                f"🟢 is_hidden = {is_hidden}\n"
                + (f"🟡 timeline_visibility = {timeline_visibility}\n" if timeline_visibility is not None else "")
                + "\n❌ لن أعتبر النشر Public."
            ),
            "post_id": post_id,
            "permalink": permalink,
            "is_published": is_published,
            "is_hidden": is_hidden,
            "timeline_visibility": timeline_visibility,
            "public_probe": web_probe,
            "direct_verify": True,
        }

    if web_probe.get("status") != "public_probe_ok":
        # Server-side Facebook requests are sometimes blocked/challenged.
        # Keep the result explicit instead of claiming Public Success.
        return {
            "ok": False,
            "message": (
                "🟡 Facebook نشر الـPost وGraph API شايفه منشور، "
                "لكن فحص الويب من السيرفر غير حاسم. هذا ليس دليلًا أن البوست مخفي.\n\n"
                f"🆔 Post ID: {post_id}\n"
                f"🔗 الرابط الحقيقي من Meta:\n{permalink}\n\n"
                f"🟢 is_published = {is_published}\n"
                f"🟢 is_hidden = {is_hidden}\n"
                + (f"🟡 timeline_visibility = {timeline_visibility}\n" if timeline_visibility is not None else "")
                + "\n⚠️ لن أقول Public Success بدون دليل."
            ),
            "post_id": post_id,
            "permalink": permalink,
            "is_published": is_published,
            "is_hidden": is_hidden,
            "timeline_visibility": timeline_visibility,
            "public_probe": web_probe,
            "direct_verify": True,
        }

    result_lines = [
        "✅ Facebook: تم النشر وظهر في فحص Public.",
        "",
        f"📘 الصفحة: {page_name}",
        f"🆔 Page ID: {FACEBOOK_PAGE_ID}",
        f"🆔 Post ID: {post_id}",
        "",
        f"🟢 is_published = {is_published}",
        f"🟢 is_hidden = {is_hidden}",
    ]
    if timeline_visibility is not None:
        result_lines.append(f"🟢 timeline_visibility = {timeline_visibility}")
    result_lines += [
        "",
        "🔗 الرابط الحقيقي من Meta:",
        permalink,
        "",
        "🟢 تم قراءة نفس الـPost ID مباشرة من Meta.",
        "🟢 تم فحص رابط الـPublic بدون Page Access Token.",
    ]

    if repair_notes:
        result_lines += ["", "🔧 إصلاحات:", *repair_notes]

    if post.get("created_time"):
        result_lines += ["", f"🕒 وقت الإنشاء: {post['created_time']}"]

    result = "\n".join(result_lines)

    print("FACEBOOK FINAL PUBLIC SUCCESS V12", flush=True)
    print(result, flush=True)
    print("=" * 60, flush=True)

    return {
        "ok": True,
        "message": result,
        "post_id": post_id,
        "permalink": permalink,
        "is_published": is_published,
        "is_hidden": is_hidden,
        "timeline_visibility": timeline_visibility,
        "public_probe": web_probe,
        "direct_verify": True,
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
        print("Telegram Error:", repr(e), flush=True)
        return False


# =========================================================
# PHOTO
# =========================================================

async def photo(update, context):
    if not is_admin(update):
        await update.message.reply_text("❌ غير مسموح.")
        return

    if context.user_data.get("state") != "product_photo":
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
        print("Product error:", repr(e), flush=True)
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

    t = (update.message.text or "").strip()
    s = context.user_data.get("state")

    if s == "gold":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        try:
            p = float(t)
            if p <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب سعر عيار 21 صحيح، مثال: 7000"
            )
            return

        save_latest(p)

        if first_today() is None:
            save_first(p)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تحديث السعر.\n\n" + price_text(p),
            reply_markup=gold_menu(),
        )
        return

    if s == "main":
        if not t:
            await update.message.reply_text("❌ اكتب اسم القسم.")
            return

        if add_main(t) is None:
            await update.message.reply_text(
                "⚠️ القسم موجود بالفعل.",
                reply_markup=cat_menu(),
            )
        else:
            await update.message.reply_text(
                f"✅ تم إضافة القسم الرئيسي:\n💍 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()
        return

    if s == "sub":
        pid = context.user_data.get("parent")

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
                f"✅ تم إضافة القسم الفرعي:\n🟡 {t}",
                reply_markup=cat_menu(),
            )

        context.user_data.clear()
        return

    if s == "rename":
        cid = context.user_data.get("cid")
        if cid and t:
            rename_cat(cid, t)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تغيير الاسم.",
            reply_markup=cat_menu(),
        )
        return

    if s == "prod_name":
        context.user_data["name"] = None if t.lower() == "بدون" else t
        context.user_data["state"] = "prod_code"

        await update.message.reply_text(
            "🔖 اكتب كود المنتج، أو اكتب: بدون"
        )
        return

    if s == "prod_code":
        context.user_data["code"] = None if t.lower() == "بدون" else t
        context.user_data["state"] = "prod_price"

        await update.message.reply_text(
            "💰 اكتب سعر المنتج، أو اكتب: بدون"
        )
        return

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
        context.user_data["state"] = "prod_desc"

        await update.message.reply_text(
            "📝 اكتب وصف المنتج، أو اكتب: بدون"
        )
        return

    if s == "prod_desc":
        context.user_data["desc"] = None if t.lower() == "بدون" else t
        context.user_data["state"] = "product_photo"

        await update.message.reply_text(
            "📸 تمام، ابعت صورة المنتج الآن."
        )
        return

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
            f"السعر: {round(p)}\n\n📢 عايز تنشر الأسعار فين؟",
            reply_markup=publish_menu(),
        )
        return

    await update.message.reply_text(
        "❌ مش فاهم طلبك.\nاستخدم /start لفتح القائمة.",
        reply_markup=home(is_admin(update)),
    )


# =========================================================
# BUTTONS
# =========================================================

async def buttons(update, context):
    q = update.callback_query
    await q.answer()
    c = q.data

    if c == "home":
        context.user_data.clear()
        await q.edit_message_text(
            "💎 مجوهرات الحسيني\n\nاختار من القائمة 👇",
            reply_markup=home(is_admin(update)),
        )
        return

    if c == "admin":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        context.user_data.clear()
        await q.edit_message_text(
            "👑 لوحة التحكم\n\nاختار العملية:",
            reply_markup=admin_menu(),
        )
        return

    if c == "products":
        ms = cats()

        if not ms:
            await q.edit_message_text(
                "💍 المنتجات\n\nلا توجد أقسام حالياً.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")]
                ]),
            )
            return

        k = [
            [InlineKeyboardButton(
                "💍 " + m["name"],
                callback_data=f"cm:{m['id']}"
            )]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")
        ])

        await q.edit_message_text(
            "💍 منتجات مجوهرات الحسيني\n\nاختار القسم:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("cm:"):
        mid = int(c.split(":")[1])
        m = cat(mid)
        ss = cats(mid)

        if not ss:
            await q.edit_message_text(
                f"💍 {m['name']}\n\nلا توجد أقسام فرعية.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ المنتجات",
                        callback_data="products"
                    )]
                ]),
            )
            return

        k = [
            [InlineKeyboardButton(
                f"🟡 {s['name']} ({s['product_count']})",
                callback_data=f"cs:{s['id']}"
            )]
            for s in ss
        ]

        k.append([
            InlineKeyboardButton("⬅️ الأقسام", callback_data="products")
        ])

        await q.edit_message_text(
            f"💍 {m['name']}\n\nاختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("cs:"):
        sid = int(c.split(":")[1])
        s = cat(sid)
        ps = products(sid)

        if not ps:
            await q.edit_message_text(
                f"🟡 {s['name']}\n\nلا توجد منتجات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data=f"cm:{s['parent_id']}"
                    )]
                ]),
            )
            return

        await q.edit_message_text(
            f"🟡 {s['name']}\n\nعدد المنتجات: {len(ps)}"
        )

        for p in ps:
            parts = []

            if p["name"]:
                parts.append(f"💍 {p['name']}")
            if p["code"]:
                parts.append(f"🔖 الكود: {p['code']}")
            if p["price"] is not None:
                parts.append(f"💰 السعر: {p['price']} جنيه")
            if p["description"]:
                parts.append(f"\n{p['description']}")

            try:
                await q.message.reply_photo(
                    photo=p["Photo_id"],
                    caption="\n".join(parts) or None,
                )
            except Exception as e:
                print("Product Photo Error:", repr(e), flush=True)
        return

    if c == "agold":
        if not is_admin(update):
            return

        p = latest()

        await q.edit_message_text(
            "💰 إدارة أسعار الذهب\n\n" +
            (price_text(p) if p else "لا يوجد سعر محفوظ."),
            reply_markup=gold_menu(),
        )
        return

    if c == "updategold":
        if not is_admin(update):
            return

        context.user_data.clear()
        context.user_data["state"] = "gold"

        await q.edit_message_text(
            "✏️ ابعت سعر عيار 21 الجديد.\nمثال: 7000"
        )
        return

    if c == "history":
        h = load_json(HISTORY)
        txt = "📜 سجل الأسعار\n\n"

        if h:
            txt += "\n".join(
                f"📅 {d} — {p} جنيه"
                for d, p in sorted(h.items(), reverse=True)[:30]
            )
        else:
            txt += "لا يوجد سجل."

        await q.edit_message_text(
            txt,
            reply_markup=gold_menu(),
        )
        return

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

    if c == "acat":
        if not is_admin(update):
            return

        await q.edit_message_text(
            "📂 إدارة الأقسام\n\n"
            "القسم الرئيسي → القسم الفرعي → المنتجات",
            reply_markup=cat_menu(),
        )
        return

    if c == "addmain":
        context.user_data.clear()
        context.user_data["state"] = "main"

        await q.edit_message_text(
            "➕ اكتب اسم القسم الرئيسي.\nمثال: خواتم"
        )
        return

    if c == "addsub":
        ms = cats()

        k = [
            [InlineKeyboardButton(
                "💍 " + m["name"],
                callback_data=f"sp:{m['id']}"
            )]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="acat")
        ])

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("sp:"):
        mid = int(c.split(":")[1])

        context.user_data.clear()
        context.user_data.update(state="sub", parent=mid)

        await q.edit_message_text(
            f"➕ اكتب القسم الفرعي تحت:\n{cat(mid)['name']}\n\n"
            "مثال: عيار 18"
        )
        return

    if c == "viewcats":
        lines = ["📂 الأقسام", ""]

        for m in cats():
            lines.append("💍 " + m["name"])

            for s in cats(m["id"]):
                lines.append(
                    f"   └ 🟡 {s['name']} "
                    f"({s['product_count']} منتج)"
                )

            lines.append("")

        await q.edit_message_text(
            "\n".join(lines) if len(lines) > 2 else "📂 لا توجد أقسام.",
            reply_markup=cat_menu(),
        )
        return

    if c == "rename":
        k = []

        for m in cats():
            k.append([
                InlineKeyboardButton(
                    "✏️ " + m["name"],
                    callback_data=f"rp:{m['id']}"
                )
            ])

            for s in cats(m["id"]):
                k.append([
                    InlineKeyboardButton(
                        f"   ✏️ {m['name']} → {s['name']}",
                        callback_data=f"rp:{s['id']}"
                    )
                ])

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="acat")
        ])

        await q.edit_message_text(
            "✏️ اختار القسم:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("rp:"):
        cid = int(c.split(":")[1])

        context.user_data.clear()
        context.user_data.update(state="rename", cid=cid)

        await q.edit_message_text(
            f"✏️ الاسم الحالي: {cat(cid)['name']}\n\n"
            "اكتب الاسم الجديد:"
        )
        return

    if c == "deletecat":
        k = []

        for m in cats():
            k.append([
                InlineKeyboardButton(
                    "🗑 " + m["name"],
                    callback_data=f"dc:{m['id']}"
                )
            ])

            for s in cats(m["id"]):
                k.append([
                    InlineKeyboardButton(
                        f"   🗑 {m['name']} → {s['name']}",
                        callback_data=f"dc:{s['id']}"
                    )
                ])

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="acat")
        ])

        await q.edit_message_text(
            "🗑 اختار القسم للحذف:\n\n"
            "⚠️ لا يمكن حذف قسم يحتوي منتجات أو أقسام فرعية.",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("dc:"):
        cid = int(c.split(":")[1])
        r = del_cat(cid)

        msg = {
            "deleted": "✅ تم الحذف.",
            "products": "⚠️ القسم يحتوي منتجات، احذفها أولاً.",
            "children": "⚠️ القسم يحتوي أقسام فرعية، احذفها أولاً.",
            "missing": "⚠️ القسم غير موجود.",
        }[r]

        await q.edit_message_text(
            msg,
            reply_markup=cat_menu(),
        )
        return

    if c == "aprod":
        if not is_admin(update):
            return

        await q.edit_message_text(
            "💍 إدارة المنتجات",
            reply_markup=prod_menu(),
        )
        return

    if c == "addprod":
        ms = cats()

        k = [
            [InlineKeyboardButton(
                "💍 " + m["name"],
                callback_data=f"pm:{m['id']}"
            )]
            for m in ms
        ]

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="aprod")
        ])

        await q.edit_message_text(
            "➕ اختار القسم الرئيسي:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("pm:"):
        mid = int(c.split(":")[1])
        ss = cats(mid)

        k = [
            [InlineKeyboardButton(
                "🟡 " + s["name"],
                callback_data=f"ps:{s['id']}"
            )]
            for s in ss
        ]

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="addprod")
        ])

        await q.edit_message_text(
            "➕ اختار القسم الفرعي:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("ps:"):
        sid = int(c.split(":")[1])

        context.user_data.clear()
        context.user_data.update(
            state="prod_name",
            cid=sid,
        )

        await q.edit_message_text(
            "💎 اكتب اسم المنتج.\nمثال: خاتم ذهب موديل ناعم"
        )
        return

    if c == "viewprod":
        ps = all_products()
        lines = ["📋 المنتجات", ""]

        for p in ps[:50]:
            lines.append(
                f"🆔 #{p['id']} | "
                f"{p['main_name'] or '-'} → {p['sub_name'] or '-'}\n"
                f"💎 {p['name'] or 'بدون اسم'} | "
                f"🔖 {p['code'] or '-'}"
            )

        await q.edit_message_text(
            "\n".join(lines) if ps else "📋 لا توجد منتجات.",
            reply_markup=prod_menu(),
        )
        return

    if c == "deleteprod":
        ps = all_products()

        k = [
            [InlineKeyboardButton(
                f"🗑 #{p['id']} {p['name'] or 'بدون اسم'}",
                callback_data=f"dp:{p['id']}"
            )]
            for p in ps[:50]
        ]

        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="aprod")
        ])

        await q.edit_message_text(
            "🗑 اختار المنتج:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("dp:"):
        pid = int(c.split(":")[1])

        await q.edit_message_text(
            f"⚠️ تأكيد حذف المنتج #{pid}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ احذف",
                    callback_data=f"cdp:{pid}"
                )],
                [InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="deleteprod"
                )],
            ]),
        )
        return

    if c.startswith("cdp:"):
        pid = int(c.split(":")[1])

        await q.edit_message_text(
            "✅ تم حذف المنتج." if del_product(pid)
            else "⚠️ المنتج غير موجود.",
            reply_markup=prod_menu(),
        )
        return

    if c == "phone":
        await q.edit_message_text(
            f"📞 مجوهرات الحسيني\n\n{PHONE}\n\nللتواصل المباشر:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 واتساب", url=WHATSAPP)],
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if c == "gold":
        p = latest()

        await q.edit_message_text(
            price_text(p) if p
            else "💎 لم يتم تحديث أسعار الذهب حتى الآن.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")]
            ]),
        )
        return

    # =====================================================
    # PUBLISH
    # =====================================================
    if c in ("pub_both", "pub_tg", "pub_fb"):
        if not is_admin(update):
            return

        txt = context.user_data.get("price_text")
        p = context.user_data.get("price")

        if not txt or p is None:
            await q.edit_message_text(
                "❌ السعر انتهى.",
                reply_markup=home(True),
            )
            return

        tg_ok = False
        fb_result = None

        if c in ("pub_both", "pub_tg"):
            tg_ok = await tg(context, txt)

        if c in ("pub_both", "pub_fb"):
            fb_result = await facebook(txt)

        fb_ok = bool(fb_result and fb_result.get("ok"))

        if tg_ok or fb_ok:
            save_latest(p)

            if context.user_data.get("first"):
                save_first(p)

        context.user_data.clear()

        if c == "pub_fb":
            await q.edit_message_text(
                fb_result.get(
                    "message",
                    "❌ فشل النشر على Facebook."
                ) if fb_result
                else "❌ لم يتم تنفيذ النشر على Facebook.",
                reply_markup=home(True),
            )
            return

        if c == "pub_tg":
            await q.edit_message_text(
                "✅ تم النشر في تليجرام."
                if tg_ok
                else "❌ فشل النشر في تليجرام.",
                reply_markup=home(True),
            )
            return

        result_lines = [
            "✅ Telegram: تم النشر." if tg_ok
            else "❌ Telegram: فشل النشر."
        ]

        if fb_ok:
            result_lines.append("✅ Facebook: تم النشر والتحقق من الظهور العام.")

            if fb_result.get("post_id"):
                result_lines.append(
                    f"\n🆔 Post ID:\n{fb_result['post_id']}"
                )

            if fb_result.get("permalink"):
                result_lines.append(
                    f"\n🔗 رابط المنشور:\n{fb_result['permalink']}"
                )

            result_lines.append(
                "\n🟢 is_published = true"
            )
            result_lines.append(
                "🟢 تم التحقق من نفس الـPost ID مباشرة."
            )
        else:
            result_lines.append(
                "\n" + (
                    fb_result.get(
                        "message",
                        "❌ Facebook: فشل النشر."
                    ) if fb_result
                    else "❌ Facebook: فشل النشر."
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
    print("=" * 60, flush=True)
    print("BOT ERROR:", repr(context.error), flush=True)
    print("=" * 60, flush=True)


# =========================================================
# MAIN
# =========================================================

def main():
    if not BOT_TOKEN:
        raise Exception("BOT_TOKEN is missing")

    if not ADMIN_ID:
        raise Exception("ADMIN_ID is missing")

    if not DATABASE_URL:
        raise Exception("DATABASE_URL is missing")

    print("=" * 60, flush=True)
    print("Alhussieny Gold Bot Starting...", flush=True)
    print(f"BOT VERSION: {VERSION}", flush=True)
    print("=" * 60, flush=True)

    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))

    app.add_handler(
        MessageHandler(filters.PHOTO, photo)
    )

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text,
        )
    )

    app.add_error_handler(error)

    print("Alhussieny Gold Bot Started...", flush=True)
    print(f"READY VERSION: {VERSION}", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
