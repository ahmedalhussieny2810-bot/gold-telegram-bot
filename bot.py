import os
import json
import re
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, quote

import requests
import pymysql
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
VERSION = "ALHUSSIENY_SHOP_SYSTEM_2026_08_13_V39"

# =========================================================
# ENV
# =========================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "").strip()
INSTAGRAM_BUSINESS_ID = os.getenv("INSTAGRAM_BUSINESS_ID", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
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
                "ALTER TABLE Products ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'available'",
                "ALTER TABLE Products ADD COLUMN views_count INT UNSIGNED NOT NULL DEFAULT 0",
                "ALTER TABLE Products ADD COLUMN inquiries_count INT UNSIGNED NOT NULL DEFAULT 0",
                "ALTER TABLE Products ADD COLUMN whatsapp_clicks INT UNSIGNED NOT NULL DEFAULT 0",
                "ALTER TABLE Products ADD COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP",
                "ALTER TABLE Products ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
                "ALTER TABLE Products ADD INDEX(status)",
                "ALTER TABLE Products ADD INDEX(code)",
            ]

            for q in upgrades:
                try:
                    x.execute(q)
                except Exception:
                    pass

            # Backfill any NULL status rows created before this migration
            try:
                x.execute(
                    "UPDATE Products SET status='available' "
                    "WHERE status IS NULL OR TRIM(status)=''"
                )
            except Exception:
                pass

            x.execute("""
                CREATE TABLE IF NOT EXISTS Users(
                    telegram_id BIGINT NOT NULL PRIMARY KEY,
                    first_name VARCHAR(255) NULL,
                    last_name VARCHAR(255) NULL,
                    username VARCHAR(255) NULL,
                    first_seen TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    total_interactions INT UNSIGNED NOT NULL DEFAULT 0,
                    inquiries_count INT UNSIGNED NOT NULL DEFAULT 0,
                    subscribed_gold TINYINT(1) NOT NULL DEFAULT 0,
                    whatsapp_number VARCHAR(20) NULL,
                    subscribed_gold_whatsapp TINYINT(1) NOT NULL DEFAULT 0
                )
            """)

            for q in (
                "ALTER TABLE Users ADD COLUMN total_interactions "
                "INT UNSIGNED NOT NULL DEFAULT 0",
                "ALTER TABLE Users ADD COLUMN inquiries_count "
                "INT UNSIGNED NOT NULL DEFAULT 0",
                "ALTER TABLE Users ADD COLUMN subscribed_gold "
                "TINYINT(1) NOT NULL DEFAULT 0",
                "ALTER TABLE Users ADD COLUMN whatsapp_number "
                "VARCHAR(20) NULL",
                "ALTER TABLE Users ADD COLUMN subscribed_gold_whatsapp "
                "TINYINT(1) NOT NULL DEFAULT 0",
            ):
                try:
                    x.execute(q)
                except Exception:
                    pass

            x.execute("""
                CREATE TABLE IF NOT EXISTS GoldPriceHistory(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    price_21 DECIMAL(15,2) NOT NULL,
                    price_24 DECIMAL(15,2) NOT NULL,
                    price_18 DECIMAL(15,2) NOT NULL,
                    admin_id BIGINT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(created_at)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS AdminLogs(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    admin_id BIGINT NULL,
                    action VARCHAR(100) NOT NULL,
                    old_value TEXT NULL,
                    new_value TEXT NULL,
                    object_type VARCHAR(50) NULL,
                    object_id BIGINT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'success',
                    error TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(action),
                    INDEX(created_at)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS PublishLogs(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    platform VARCHAR(20) NOT NULL,
                    post_id VARCHAR(255) NULL,
                    permalink TEXT NULL,
                    status VARCHAR(20) NOT NULL,
                    error TEXT NULL,
                    content_snippet VARCHAR(255) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(platform),
                    INDEX(created_at)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS Settings(
                    setting_key VARCHAR(100) NOT NULL PRIMARY KEY,
                    setting_value TEXT NULL
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS ScheduledPosts(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    time_str VARCHAR(5) NOT NULL,
                    label VARCHAR(50) NULL,
                    platforms VARCHAR(50) NOT NULL DEFAULT 'tg,fb',
                    template_key VARCHAR(50) NOT NULL DEFAULT 'normal',
                    enabled TINYINT(1) NOT NULL DEFAULT 1,
                    last_run_date DATE NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

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

            # Seed the two fixed top-level categories every time the
            # bot starts, in case they were ever removed or this is
            # a fresh database. add_main() already no-ops if a
            # category with that name already exists.
            x.execute("""
                SELECT id FROM Categories
                WHERE parent_id IS NULL AND LOWER(TRIM(name))='ذهب'
                LIMIT 1
            """)
            gold_row = x.fetchone()
            if not gold_row:
                x.execute(
                    "INSERT INTO Categories(parent_id,name) VALUES(NULL,'ذهب')"
                )
                gold_id = x.lastrowid
            else:
                gold_id = gold_row["id"]

            x.execute("""
                SELECT id FROM Categories
                WHERE parent_id IS NULL AND LOWER(TRIM(name))='فضة'
                LIMIT 1
            """)
            if not x.fetchone():
                x.execute(
                    "INSERT INTO Categories(parent_id,name) VALUES(NULL,'فضة')"
                )

            # Seed the fixed "سبائك" and "عملات" leaf categories under
            # "ذهب" — their prices are computed live from the gold
            # price (weight × price/gram), not stored per-product.
            for fixed_name in ("سبائك", "عملات"):
                x.execute("""
                    SELECT id FROM Categories
                    WHERE parent_id=%s AND LOWER(TRIM(name))=%s
                    LIMIT 1
                """, (gold_id, fixed_name))
                if not x.fetchone():
                    x.execute(
                        "INSERT INTO Categories(parent_id,name) VALUES(%s,%s)",
                        (gold_id, fixed_name),
                    )
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


def flatten_categories(parent=None, depth=0):
    """Recursively lists the whole category tree as
    [(category_dict, depth), ...] regardless of how many levels
    deep it goes."""
    out = []
    for c in cats(parent):
        out.append((c, depth))
        out.extend(flatten_categories(c["id"], depth + 1))
    return out


def cat(cid):
    return one(
        "SELECT id,parent_id,name FROM Categories WHERE id=%s",
        (cid,),
    )


PROTECTED_ROOT_CATEGORIES = {"ذهب", "فضة"}
PROTECTED_FIXED_CATEGORIES = {"سبائك", "عملات"}


def is_protected_root_category(cid):
    c = cat(cid)
    if not c:
        return False
    name = c["name"].strip()
    if c["parent_id"] is None and name in PROTECTED_ROOT_CATEGORIES:
        return True
    if name in PROTECTED_FIXED_CATEGORIES:
        return True
    return False


# Bars are 24-karat; (label, weight_in_grams)
GOLD_BARS = [
    ("سبيكة 0.25 جرام", 0.25),
    ("سبيكة 0.5 جرام", 0.5),
    ("سبيكة 1 جرام", 1),
    ("سبيكة 2.5 جرام", 2.5),
    ("سبيكة 5 جرام", 5),
    ("سبيكة 10 جرام", 10),
    ("سبيكة 20 جرام", 20),
    ("سبيكة 31.1 جرام (أونصة)", 31.1),
    ("سبيكة 50 جرام", 50),
]

# Coins are 21-karat; (label, weight_in_grams)
GOLD_COINS = [
    ("جنيه ذهب (8 جرام)", 8),
    ("نص جنيه (4 جرام)", 4),
    ("ربع جنيه (2 جرام)", 2),
    ("تمن جنيه (1 جرام)", 1),
]

GOLD_PURITY_DISCLAIMER = "⚠️ السعر ذهب صافي، مش شامل المصنعية."


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
    if is_protected_root_category(cid):
        return "protected"

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


def product(pid):
    return one("""
        SELECT id,Photo_id,name,code,price,description,
               status,views_count,inquiries_count,whatsapp_clicks,
               category_id
        FROM Products
        WHERE id=%s
    """, (pid,))


STATUS_LABELS = {
    "available": "🟢 متاح",
    "reserved": "🟡 محجوز",
    "sold": "🔴 مباع",
    "hidden": "⚪ مخفي",
}

STATUS_ORDER = ["available", "reserved", "sold", "hidden"]

EDITABLE_FIELDS = {
    "name": "name",
    "code": "code",
    "price": "price",
    "desc": "description",
}


def set_product_status(pid, status):
    if status not in STATUS_LABELS:
        return False
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE Products SET status=%s WHERE id=%s",
                (status, pid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def update_product_field(pid, field, value):
    column = EDITABLE_FIELDS.get(field)
    if not column:
        return False
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                f"UPDATE Products SET {column}=%s WHERE id=%s",
                (value, pid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def update_product_photo(pid, photo_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE Products SET Photo_id=%s WHERE id=%s",
                (photo_id, pid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def move_product_category(pid, cid):
    c = db()
    try:
        with c.cursor() as x:
            parent = cat(cid)
            x.execute(
                "UPDATE Products SET category_id=%s,category=%s WHERE id=%s",
                (cid, parent["name"] if parent else "", pid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def inc_product_counter(pid, field):
    if field not in ("views_count", "inquiries_count", "whatsapp_clicks"):
        return
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                f"UPDATE Products SET {field}={field}+1 WHERE id=%s",
                (pid,),
            )
    except Exception as e:
        print("Counter Error:", repr(e), flush=True)
    finally:
        c.close()


def search_products(query, limit=200):
    q = f"%{query.strip()}%"
    return many("""
        SELECT p.*,c.name sub_name,m.name main_name
        FROM Products p
        LEFT JOIN Categories c ON c.id=p.category_id
        LEFT JOIN Categories m ON m.id=c.parent_id
        WHERE p.code LIKE %s
           OR p.name LIKE %s
           OR c.name LIKE %s
           OR m.name LIKE %s
        ORDER BY p.id DESC
        LIMIT %s
    """, (q, q, q, q, limit))


def customer_products(cid):
    """Products visible to customers (hidden ones excluded)."""
    return many("""
        SELECT id,Photo_id,name,code,price,description,status
        FROM Products
        WHERE category_id=%s AND status<>'hidden'
        ORDER BY id DESC
    """, (cid,))


# =========================================================
# USERS
# =========================================================

def track_user(update):
    u = update.effective_user
    if not u:
        return
    try:
        c = db()
        try:
            with c.cursor() as x:
                x.execute(
                    "SELECT telegram_id FROM Users WHERE telegram_id=%s",
                    (u.id,),
                )
                if x.fetchone():
                    x.execute("""
                        UPDATE Users
                        SET first_name=%s, last_name=%s, username=%s,
                            total_interactions=total_interactions+1
                        WHERE telegram_id=%s
                    """, (u.first_name, u.last_name, u.username, u.id))
                else:
                    x.execute("""
                        INSERT INTO Users
                        (telegram_id,first_name,last_name,username,
                         total_interactions)
                        VALUES(%s,%s,%s,%s,1)
                    """, (u.id, u.first_name, u.last_name, u.username))
        finally:
            c.close()
    except Exception as e:
        print("Track User Error:", repr(e), flush=True)


def inc_user_inquiries(telegram_id):
    try:
        c = db()
        try:
            with c.cursor() as x:
                x.execute(
                    "UPDATE Users SET inquiries_count=inquiries_count+1 "
                    "WHERE telegram_id=%s",
                    (telegram_id,),
                )
        finally:
            c.close()
    except Exception as e:
        print("User Inquiry Count Error:", repr(e), flush=True)


def set_gold_subscription(telegram_id, subscribed):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE Users SET subscribed_gold=%s WHERE telegram_id=%s",
                (1 if subscribed else 0, telegram_id),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def is_gold_subscribed(telegram_id):
    row = one(
        "SELECT subscribed_gold FROM Users WHERE telegram_id=%s",
        (telegram_id,),
    )
    return bool(row and row.get("subscribed_gold"))


def gold_subscriber_ids():
    rows = many(
        "SELECT telegram_id FROM Users WHERE subscribed_gold=1"
    )
    return [r["telegram_id"] for r in rows]


def gold_subscriber_count():
    row = one(
        "SELECT COUNT(*) c FROM Users WHERE subscribed_gold=1"
    )
    return (row or {}).get("c", 0)


def set_whatsapp_subscription(telegram_id, phone_number, subscribed):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                UPDATE Users
                SET whatsapp_number=%s, subscribed_gold_whatsapp=%s
                WHERE telegram_id=%s
            """, (phone_number, 1 if subscribed else 0, telegram_id))
            return bool(x.rowcount)
    finally:
        c.close()


def unsubscribe_whatsapp(telegram_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE Users SET subscribed_gold_whatsapp=0 "
                "WHERE telegram_id=%s",
                (telegram_id,),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def is_whatsapp_subscribed(telegram_id):
    row = one(
        "SELECT subscribed_gold_whatsapp FROM Users WHERE telegram_id=%s",
        (telegram_id,),
    )
    return bool(row and row.get("subscribed_gold_whatsapp"))


def whatsapp_subscriber_numbers():
    rows = many(
        "SELECT whatsapp_number FROM Users "
        "WHERE subscribed_gold_whatsapp=1 AND whatsapp_number IS NOT NULL"
    )
    return [r["whatsapp_number"] for r in rows]


def whatsapp_subscriber_count():
    row = one(
        "SELECT COUNT(*) c FROM Users WHERE subscribed_gold_whatsapp=1"
    )
    return (row or {}).get("c", 0)


# =========================================================
# LOGS
# =========================================================

def log_action(admin_id, action, old_value=None, new_value=None,
                object_type=None, object_id=None, status="success",
                error=None):
    try:
        c = db()
        try:
            with c.cursor() as x:
                x.execute("""
                    INSERT INTO AdminLogs
                    (admin_id,action,old_value,new_value,
                     object_type,object_id,status,error)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    admin_id, action,
                    None if old_value is None else str(old_value)[:2000],
                    None if new_value is None else str(new_value)[:2000],
                    object_type, object_id, status,
                    None if error is None else str(error)[:2000],
                ))
        finally:
            c.close()
    except Exception as e:
        print("Log Action Error:", repr(e), flush=True)


def log_publish(platform, post_id=None, permalink=None,
                 status="success", error=None, content=""):
    try:
        c = db()
        try:
            with c.cursor() as x:
                x.execute("""
                    INSERT INTO PublishLogs
                    (platform,post_id,permalink,status,error,content_snippet)
                    VALUES(%s,%s,%s,%s,%s,%s)
                """, (
                    platform, post_id, permalink, status,
                    None if error is None else str(error)[:2000],
                    (content or "")[:255],
                ))
        finally:
            c.close()
    except Exception as e:
        print("Log Publish Error:", repr(e), flush=True)


def record_gold_price(p21, p24, p18, admin_id=None):
    try:
        c = db()
        try:
            with c.cursor() as x:
                x.execute("""
                    INSERT INTO GoldPriceHistory
                    (price_21,price_24,price_18,admin_id)
                    VALUES(%s,%s,%s,%s)
                """, (p21, p24, p18, admin_id))
        finally:
            c.close()
    except Exception as e:
        print("Gold History Log Error:", repr(e), flush=True)


def gold_history_range(start_dt, end_dt):
    return many("""
        SELECT price_21,price_24,price_18,admin_id,created_at
        FROM GoldPriceHistory
        WHERE created_at BETWEEN %s AND %s
        ORDER BY created_at ASC
    """, (start_dt, end_dt))


def gold_period_stats(days_back):
    """days_back=0 -> today, 1 -> yesterday only, N -> last N days incl today."""
    now = datetime.now(TZ)

    if days_back == 0:
        start = now.strftime("%Y-%m-%d 00:00:00")
        end = now.strftime("%Y-%m-%d 23:59:59")
    elif days_back == 1:
        y = now - timedelta(days=1)
        start = y.strftime("%Y-%m-%d 00:00:00")
        end = y.strftime("%Y-%m-%d 23:59:59")
    else:
        start = (now - timedelta(days=days_back - 1)).strftime(
            "%Y-%m-%d 00:00:00"
        )
        end = now.strftime("%Y-%m-%d 23:59:59")

    rows = gold_history_range(start, end)
    if not rows:
        return None

    prices = [float(r["price_21"]) for r in rows]
    first_p = prices[0]
    last_p = prices[-1]
    change = last_p - first_p
    pct = (change / first_p * 100) if first_p else 0

    return {
        "first": round(first_p),
        "last": round(last_p),
        "high": round(max(prices)),
        "low": round(min(prices)),
        "change": round(change),
        "pct": round(pct, 2),
        "count": len(prices),
        "rows": rows,
    }


# =========================================================
# SETTINGS
# =========================================================

def get_setting(key, default=None):
    try:
        row = one(
            "SELECT setting_value FROM Settings WHERE setting_key=%s",
            (key,),
        )
        return row["setting_value"] if row else default
    except Exception as e:
        print("Get Setting Error:", repr(e), flush=True)
        return default


def set_setting(key, value):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO Settings(setting_key,setting_value)
                VALUES(%s,%s)
                ON DUPLICATE KEY UPDATE setting_value=%s
            """, (key, value, value))
    finally:
        c.close()


def gold_alert_threshold():
    v = get_setting("gold_alert_threshold", "0")
    try:
        return float(v)
    except Exception:
        return 0


def get_extra_admins():
    v = get_setting("extra_admins", "")
    ids = []
    for part in (v or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def add_extra_admin(uid):
    ids = get_extra_admins()
    if uid in ids or uid == ADMIN_ID:
        return False
    ids.append(uid)
    set_setting("extra_admins", ",".join(str(i) for i in ids))
    return True


def remove_extra_admin(uid):
    ids = get_extra_admins()
    if uid not in ids:
        return False
    ids.remove(uid)
    set_setting("extra_admins", ",".join(str(i) for i in ids))
    return True


def all_admin_ids():
    ids = get_extra_admins()
    if ADMIN_ID and ADMIN_ID not in ids:
        ids.append(ADMIN_ID)
    return ids


# =========================================================
# POST TEMPLATES
# =========================================================

TEMPLATES = {
    "normal": {
        "name": "قالب أسعار عادي",
        "body": (
            "💎 أسعار الذهب الآن\n\n"
            "🟡 عيار 24 : {price_24}\n"
            "🟡 عيار 21 : {price_21}\n"
            "🟡 عيار 18 : {price_18}\n\n"
            "📍 {shop_name}\n\n"
            "🌐 {website}"
        ),
    },
    "luxury": {
        "name": "قالب فاخر",
        "body": (
            "✨💍 مجوهرات الحسيني — أسعار الذهب ✨\n\n"
            "📅 {date} — 🕐 {time}\n\n"
            "🟡 عيار 24 : {price_24} جنيه\n"
            "🟡 عيار 21 : {price_21} جنيه\n"
            "🟡 عيار 18 : {price_18} جنيه\n\n"
            "💫 جمال يدوم... يليق بك\n"
            "📍 {shop_name}\n"
            "💬 {whatsapp}"
        ),
    },
    "short": {
        "name": "قالب مختصر",
        "body": (
            "💰 عيار 21: {price_21} | "
            "عيار 24: {price_24} | "
            "عيار 18: {price_18}"
        ),
    },
    "links": {
        "name": "قالب أسعار + روابط المحل",
        "body": (
            "💎 أسعار الذهب الآن\n\n"
            "🟡 عيار 24 : {price_24}\n"
            "🟡 عيار 21 : {price_21}\n"
            "🟡 عيار 18 : {price_18}\n\n"
            "📍 {shop_name}\n"
            "🌐 الموقع: {website}\n"
            "💬 واتساب: {whatsapp}\n"
            "📍 الموقع على الخريطة: {maps}"
        ),
    },
    "offer": {
        "name": "قالب عروض",
        "body": (
            "🔥 عرض خاص اليوم في مجوهرات الحسيني 🔥\n\n"
            "💎 أسعار الذهب:\n"
            "🟡 عيار 24 : {price_24}\n"
            "🟡 عيار 21 : {price_21}\n"
            "🟡 عيار 18 : {price_18}\n\n"
            "زورونا اليوم في {shop_name}\n"
            "🌐 {website}"
        ),
    },
}


def render_template(key, price21):
    tpl = TEMPLATES.get(key, TEMPLATES["normal"])
    p24, p21, p18 = calc(price21)
    now = datetime.now(TZ)

    return tpl["body"].format(
        price_24=p24,
        price_21=p21,
        price_18=p18,
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        shop_name="مجوهرات الحسيني - بورسعيد",
        website=WEBSITE,
        whatsapp=WHATSAPP,
        maps=MAPS,
    )


def template_pick_menu():
    k = [
        [InlineKeyboardButton(t["name"], callback_data=f"tpl:{key}")]
        for key, t in TEMPLATES.items()
    ]
    k.append([InlineKeyboardButton("⬅️ رجوع", callback_data="agold")])
    return InlineKeyboardMarkup(k)


# =========================================================
# SCHEDULED AUTO-POSTING
# =========================================================

def scheduled_posts():
    return many(
        "SELECT * FROM ScheduledPosts ORDER BY time_str ASC"
    )


def scheduled_post(sid):
    return one(
        "SELECT * FROM ScheduledPosts WHERE id=%s", (sid,)
    )


def add_scheduled_post(time_str, platforms="tg,fb", template_key="normal"):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO ScheduledPosts(time_str,platforms,template_key)
                VALUES(%s,%s,%s)
            """, (time_str, platforms, template_key))
            return x.lastrowid
    finally:
        c.close()


def delete_scheduled_post(sid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("DELETE FROM ScheduledPosts WHERE id=%s", (sid,))
            return bool(x.rowcount)
    finally:
        c.close()


def toggle_scheduled_post(sid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledPosts SET enabled=1-enabled WHERE id=%s",
                (sid,),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def set_scheduled_post_platforms(sid, platforms):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledPosts SET platforms=%s WHERE id=%s",
                (platforms, sid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def set_scheduled_post_template(sid, template_key):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledPosts SET template_key=%s WHERE id=%s",
                (template_key, sid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def mark_scheduled_post_ran(sid, date_str):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledPosts SET last_run_date=%s WHERE id=%s",
                (date_str, sid),
            )
    finally:
        c.close()


def gold_today_stats():
    rows = gold_history_range(
        datetime.now(TZ).strftime("%Y-%m-%d 00:00:00"),
        datetime.now(TZ).strftime("%Y-%m-%d 23:59:59"),
    )
    if not rows:
        return None

    prices = [float(r["price_21"]) for r in rows]
    first_p = prices[0]
    last_p = prices[-1]
    change = last_p - first_p
    pct = (change / first_p * 100) if first_p else 0

    return {
        "first": round(first_p),
        "last": round(last_p),
        "high": round(max(prices)),
        "low": round(min(prices)),
        "change": round(change),
        "pct": round(pct, 2),
        "count": len(prices),
    }


# =========================================================
# ANALYTICS
# =========================================================

def top_viewed_products(limit=10):
    return many("""
        SELECT id,name,code,views_count
        FROM Products
        WHERE views_count > 0
        ORDER BY views_count DESC
        LIMIT %s
    """, (limit,))


def top_inquired_products(limit=10):
    return many("""
        SELECT id,name,code,inquiries_count
        FROM Products
        WHERE inquiries_count > 0
        ORDER BY inquiries_count DESC
        LIMIT %s
    """, (limit,))


def top_viewed_categories(limit=10):
    return many("""
        SELECT m.name main_name, c.name sub_name,
               COALESCE(SUM(p.views_count),0) total_views
        FROM Categories c
        LEFT JOIN Categories m ON m.id=c.parent_id
        LEFT JOIN Products p ON p.category_id=c.id
        WHERE c.parent_id IS NOT NULL
        GROUP BY c.id, m.name, c.name
        HAVING total_views > 0
        ORDER BY total_views DESC
        LIMIT %s
    """, (limit,))


def product_totals():
    row = one("""
        SELECT
            COUNT(*) total,
            SUM(status='available') available,
            SUM(status='reserved') reserved,
            SUM(status='sold') sold,
            SUM(status='hidden') hidden,
            COALESCE(SUM(views_count),0) views,
            COALESCE(SUM(inquiries_count),0) inquiries
        FROM Products
    """)
    return row or {}


def user_totals():
    row = one("""
        SELECT
            COUNT(*) total,
            SUM(last_seen >= NOW() - INTERVAL 7 DAY) active_7d,
            COALESCE(SUM(inquiries_count),0) inquiries
        FROM Users
    """)
    return row or {}


def top_inquiring_users(limit=10):
    return many("""
        SELECT telegram_id,first_name,username,inquiries_count
        FROM Users
        WHERE inquiries_count > 0
        ORDER BY inquiries_count DESC
        LIMIT %s
    """, (limit,))


def publish_totals():
    row = one("""
        SELECT
            COUNT(*) total,
            SUM(status='success') success,
            SUM(status='failed') failed
        FROM PublishLogs
    """)
    return row or {}


def recent_admin_logs(limit=20, offset=0):
    return many("""
        SELECT action,old_value,new_value,object_type,object_id,
               status,error,created_at
        FROM AdminLogs
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))


def admin_logs_count():
    row = one("SELECT COUNT(*) c FROM AdminLogs")
    return (row or {}).get("c", 0)


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


def first_price_on_date(date_str):
    row = one("""
        SELECT price_21 FROM GoldPriceHistory
        WHERE DATE(created_at) = %s
        ORDER BY created_at ASC
        LIMIT 1
    """, (date_str,))
    return float(row["price_21"]) if row else None


def first_today():
    """First recorded price of today. Derived from GoldPriceHistory
    (persisted in MySQL) instead of a local JSON file, so it survives
    every code deploy/redeploy — Railway's filesystem is ephemeral
    and wipes local files on each redeploy, but the database is a
    separate, persistent service."""
    return first_price_on_date(today())


def save_first(p):
    """Kept as a no-op for backward compatibility with existing call
    sites. The 'first price of the day' is now derived automatically
    from GoldPriceHistory (every price update already gets logged
    there via record_gold_price), so there is nothing left to save
    separately."""
    return False


def latest():
    """Most recently recorded gold price (عيار 21). Derived from
    GoldPriceHistory in MySQL — see first_today() docstring for why
    this replaced the old local-JSON-file approach."""
    row = one(
        "SELECT price_21 FROM GoldPriceHistory "
        "ORDER BY created_at DESC LIMIT 1"
    )
    return float(row["price_21"]) if row else None


def save_latest(p, admin_id=None):
    p24, p21, p18 = calc(p)
    record_gold_price(p21, p24, p18, admin_id)


def comparison(p):
    old = first_price_on_date(yesterday())
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

def gold_screen_kb(telegram_id):
    wa_subscribed = is_whatsapp_subscribed(telegram_id)

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔕 إلغاء الاشتراك (واتساب)"
            if wa_subscribed else
            "📱 اشترك في تحديثات السعر (واتساب)",
            callback_data="goldwunsub" if wa_subscribed else "goldwsub",
        )],
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
    ])


def home(admin=False, subscribed=False):
    k = [
        [InlineKeyboardButton("💎 أسعار الذهب", callback_data="gold")],
        [InlineKeyboardButton("💍 المنتجات", callback_data="products")],
        [InlineKeyboardButton(
            "🔕 إيقاف الإشعارات" if subscribed else "🔔 تفعيل الإشعارات",
            callback_data="notifunsub" if subscribed else "notifsub",
        )],
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


def admin_menu(owner=False):
    rows = [
        [InlineKeyboardButton("📝 منشور جديد", callback_data="newpost")],
        [InlineKeyboardButton("💰 إدارة أسعار الذهب", callback_data="agold")],
        [InlineKeyboardButton("💍 إدارة المنتجات", callback_data="aprod")],
        [InlineKeyboardButton("📂 إدارة الأقسام", callback_data="acat")],
        [InlineKeyboardButton("⏰ النشر التلقائي", callback_data="schedmenu")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
    ]
    if owner:
        rows.append(
            [InlineKeyboardButton("👥 إدارة الأدمنز", callback_data="adminlist")]
        )
    rows.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def scheduler_menu():
    rows = scheduled_posts()

    k = []
    for sp in rows:
        onoff = "🟢" if sp["enabled"] else "⏸"
        k.append([InlineKeyboardButton(
            f"{onoff} {sp['time_str']} ({sp['platforms']})",
            callback_data=f"schedopen:{sp['id']}"
        )])

    k.append([InlineKeyboardButton("➕ إضافة موعد", callback_data="schedadd")])
    k.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")])
    return InlineKeyboardMarkup(k)


def scheduler_item_menu(sid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏯ تشغيل/إيقاف", callback_data=f"schedtoggle:{sid}")],
        [InlineKeyboardButton("📢 المنصات", callback_data=f"schedplat:{sid}")],
        [InlineKeyboardButton("🎨 القالب", callback_data=f"schedtpl:{sid}")],
        [InlineKeyboardButton("🗑 حذف الموعد", callback_data=f"scheddel:{sid}")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="schedmenu")],
    ])


def scheduler_platform_menu(sid, current_platforms):
    plats = current_platforms.split(",")
    tg_mark = "✅" if "tg" in plats else "◻️"
    fb_mark = "✅" if "fb" in plats else "◻️"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{tg_mark} تليجرام", callback_data=f"schedplatt:{sid}:tg"
        )],
        [InlineKeyboardButton(
            f"{fb_mark} فيسبوك", callback_data=f"schedplatt:{sid}:fb"
        )],
        [InlineKeyboardButton("⬅️ رجوع", callback_data=f"schedopen:{sid}")],
    ])


def scheduler_template_menu(sid):
    k = [
        [InlineKeyboardButton(t["name"], callback_data=f"schedtplset:{sid}:{key}")]
        for key, t in TEMPLATES.items()
    ]
    k.append([InlineKeyboardButton("⬅️ رجوع", callback_data=f"schedopen:{sid}")])
    return InlineKeyboardMarkup(k)


def stats_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔥 أكثر المنتجات مشاهدة", callback_data="statsview"
        )],
        [InlineKeyboardButton(
            "🔥 أكثر المنتجات استعلامات", callback_data="statsinq"
        )],
        [InlineKeyboardButton(
            "📂 أكثر الأقسام مشاهدة", callback_data="statscat"
        )],
        [InlineKeyboardButton(
            "👥 أكثر العملاء استعلامات", callback_data="statsusers"
        )],
        [InlineKeyboardButton("📋 سجل العمليات", callback_data="logsp:0")],
        [InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")],
    ])


def cat_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ قسم رئيسي جديد", callback_data="addmain")],
        [InlineKeyboardButton(
            "➕ قسم فرعي (أي مستوى)", callback_data="addsub"
        )],
        [InlineKeyboardButton("📋 عرض الأقسام", callback_data="viewcats")],
        [InlineKeyboardButton("✏️ تغيير اسم", callback_data="rename")],
        [InlineKeyboardButton("🗑 حذف قسم", callback_data="deletecat")],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def products_paused():
    return get_setting("products_paused", "0") == "1"


def set_products_paused(paused):
    set_setting("products_paused", "1" if paused else "0")


def find_category_by_name(name, parent=None):
    row = one(
        "SELECT id FROM Categories WHERE LOWER(TRIM(name))=%s "
        + ("AND parent_id=%s" if parent is not None else "AND parent_id IS NULL"),
        (name,) if parent is None else (name, parent),
    )
    return row["id"] if row else None


def products_paused_kb():
    gold_id = find_category_by_name("ذهب")
    k = []

    if gold_id:
        bars_id = find_category_by_name("سبائك", gold_id)
        coins_id = find_category_by_name("عملات", gold_id)
        if bars_id:
            k.append([InlineKeyboardButton(
                "🧱 سبائك", callback_data=f"cm:{bars_id}"
            )])
        if coins_id:
            k.append([InlineKeyboardButton(
                "🪙 عملات", callback_data=f"cm:{coins_id}"
            )])

    k.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(k)


def prod_menu():
    paused = products_paused()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة منتج", callback_data="addprod")],
        [InlineKeyboardButton("📋 عرض المنتجات", callback_data="viewprod")],
        [InlineKeyboardButton("✏️ تعديل منتج", callback_data="editprod:0")],
        [InlineKeyboardButton("🔎 بحث عن منتج", callback_data="searchprod")],
        [InlineKeyboardButton("🗑 حذف منتج", callback_data="deleteprod")],
        [InlineKeyboardButton(
            "▶️ تفعيل عرض المنتجات للعملاء" if paused
            else "⏸️ إيقاف عرض المنتجات مؤقتاً",
            callback_data="toggleprodpause"
        )],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def product_pick_kb(ps, page, callback_prefix, back_cb, page_size=10):
    """Paginated keyboard for picking a product from a list."""
    start_i = page * page_size
    chunk = ps[start_i:start_i + page_size]

    k = [
        [InlineKeyboardButton(
            f"{STATUS_LABELS.get(p.get('status') or 'available', '')} "
            f"#{p['id']} {p['name'] or 'بدون اسم'}",
            callback_data=f"{callback_prefix}:{p['id']}"
        )]
        for p in chunk
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "⬅️ السابق", callback_data=f"{callback_prefix}p:{page-1}"
        ))
    if start_i + page_size < len(ps):
        nav.append(InlineKeyboardButton(
            "➡️ التالي", callback_data=f"{callback_prefix}p:{page+1}"
        ))
    if nav:
        k.append(nav)

    k.append([InlineKeyboardButton("🏠 رجوع", callback_data=back_cb)])
    return InlineKeyboardMarkup(k)


def product_edit_menu(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ الاسم", callback_data=f"ef:name:{pid}")],
        [InlineKeyboardButton("💰 السعر", callback_data=f"ef:price:{pid}")],
        [InlineKeyboardButton("🔖 الكود", callback_data=f"ef:code:{pid}")],
        [InlineKeyboardButton("📝 الوصف", callback_data=f"ef:desc:{pid}")],
        [InlineKeyboardButton("📸 الصورة", callback_data=f"ef:photo:{pid}")],
        [InlineKeyboardButton("🔄 الحالة", callback_data=f"stat:{pid}")],
        [InlineKeyboardButton("📂 القسم", callback_data=f"movecat:{pid}")],
        [InlineKeyboardButton(
            "⬅️ رجوع لقائمة المنتجات", callback_data="editprod:0"
        )],
        [InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")],
    ])


def status_pick_kb(pid):
    k = [
        [InlineKeyboardButton(
            label, callback_data=f"sset:{pid}:{key}"
        )]
        for key, label in STATUS_LABELS.items()
    ]
    k.append([InlineKeyboardButton(
        "⬅️ رجوع", callback_data=f"editprod_open:{pid}"
    )])
    return InlineKeyboardMarkup(k)


def gold_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تحديث السعر", callback_data="updategold")],
        [InlineKeyboardButton("📊 أسعار اليوم", callback_data="goldtoday")],
        [InlineKeyboardButton("📅 تاريخ الأسعار", callback_data="histmenu")],
        [InlineKeyboardButton("🔔 تنبيهات السعر", callback_data="alertmenu")],
        [InlineKeyboardButton("📢 نشر السعر", callback_data="publish")],
        [InlineKeyboardButton("⬅️ لوحة التحكم", callback_data="admin")],
    ])


def hist_period_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اليوم", callback_data="histp:0")],
        [InlineKeyboardButton("أمس", callback_data="histp:1")],
        [InlineKeyboardButton("آخر 7 أيام", callback_data="histp:7")],
        [InlineKeyboardButton("آخر 30 يوم", callback_data="histp:30")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="agold")],
    ])


def alert_menu():
    current = gold_alert_threshold()
    status = f"الحد الحالي: {int(current)} جنيه" if current else "متوقفة"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ℹ️ {status}", callback_data="alertmenu")],
        [InlineKeyboardButton("10 جنيه", callback_data="alertset:10")],
        [InlineKeyboardButton("20 جنيه", callback_data="alertset:20")],
        [InlineKeyboardButton("50 جنيه", callback_data="alertset:50")],
        [InlineKeyboardButton("100 جنيه", callback_data="alertset:100")],
        [InlineKeyboardButton("⏸ إيقاف التنبيهات", callback_data="alertset:0")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="agold")],
    ])


def publish_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 تليجرام + فيسبوك", callback_data="pub_both")],
        [InlineKeyboardButton("📱 تليجرام فقط", callback_data="pub_tg")],
        [InlineKeyboardButton("📘 فيسبوك فقط", callback_data="pub_fb")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="home")],
    ])


def newpost_menu(has_photo=False):
    if has_photo:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🌐 الكل (تليجرام + فيسبوك + انستجرام)",
                callback_data="npub_all"
            )],
            [InlineKeyboardButton("📱 تليجرام فقط", callback_data="npub_tg")],
            [InlineKeyboardButton("📘 فيسبوك فقط", callback_data="npub_fb")],
            [InlineKeyboardButton("📸 انستجرام فقط", callback_data="npub_ig")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin")],
        ])

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 تليجرام + فيسبوك", callback_data="npub_both")],
        [InlineKeyboardButton("📱 تليجرام فقط", callback_data="npub_tg")],
        [InlineKeyboardButton("📘 فيسبوك فقط", callback_data="npub_fb")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="admin")],
    ])


# =========================================================
# HELPERS
# =========================================================

def is_admin(update):
    return bool(
        update.effective_user
        and update.effective_user.id in all_admin_ids()
    )


def is_owner(update):
    return bool(
        update.effective_user
        and ADMIN_ID
        and update.effective_user.id == ADMIN_ID
    )


async def auto_post_tick(context):
    """Runs every minute via JobQueue. Fires any due scheduled posts,
    guarded against duplicate sends after a restart."""
    try:
        now = datetime.now(TZ)
        hhmm = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        for sp in scheduled_posts():
            if not sp.get("enabled"):
                continue
            if sp.get("time_str") != hhmm:
                continue

            last_run = sp.get("last_run_date")
            last_run_str = (
                last_run.strftime("%Y-%m-%d")
                if hasattr(last_run, "strftime") else last_run
            )
            if last_run_str == today_str:
                continue

            p = latest()
            if not p:
                mark_scheduled_post_ran(sp["id"], today_str)
                continue

            txt = render_template(sp.get("template_key") or "normal", p)
            platforms = (sp.get("platforms") or "tg,fb").split(",")

            tg_ok = False
            fb_result = None

            if "tg" in platforms:
                tg_ok = await tg(context, txt)

            if "fb" in platforms:
                fb_result = await facebook(txt)

            fb_ok = bool(fb_result and fb_result.get("ok"))

            log_publish(
                "auto_telegram", status="success" if tg_ok else "failed",
                content=txt,
            ) if "tg" in platforms else None
            log_publish(
                "auto_facebook",
                post_id=(fb_result or {}).get("post_id"),
                permalink=(fb_result or {}).get("permalink"),
                status="success" if fb_ok else "failed",
                error=None if fb_ok else (fb_result or {}).get("message"),
                content=txt,
            ) if "fb" in platforms else None

            log_action(
                ADMIN_ID, "AUTO_POST_SENT",
                object_type="schedule", object_id=sp["id"],
                new_value=f"tg={tg_ok} fb={fb_ok}",
            )

            mark_scheduled_post_ran(sp["id"], today_str)
    except Exception as e:
        print("Auto Post Tick Error:", repr(e), flush=True)


async def broadcast_gold_update(context, new_price):
    """
    Sends the new gold price to every customer subscribed to
    notifications (🔔 تفعيل الإشعارات on the main menu). Best-effort
    per user — a blocked bot or deactivated account for one
    subscriber never stops the broadcast to the rest. A small delay
    between sends avoids hitting Telegram's flood limits on large
    lists.
    """
    ids = gold_subscriber_ids()
    if not ids:
        return

    txt = "🔔 تحديث سعر الذهب\n\n" + price_text(new_price)
    sent, failed = 0, 0

    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=txt)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"Gold Broadcast Failed for {uid}:", repr(e), flush=True)
        await asyncio.sleep(0.05)

    log_action(
        ADMIN_ID, "GOLD_PRICE_BROADCAST",
        new_value=f"sent={sent} failed={failed}",
    )


async def broadcast_new_product(context, photo_id, name, code, price, desc):
    """
    Sends a "new product" notification to every customer subscribed
    to notifications (same subscriber list as gold price updates —
    the 🔔 button is a single general notifications toggle).
    """
    ids = gold_subscriber_ids()
    if not ids:
        return

    parts = ["✨ منتج جديد وصل!", ""]
    if name:
        parts.append(f"💍 {name}")
    if code:
        parts.append(f"🔖 الكود: {code}")
    parts.append(
        f"💰 السعر: {round(float(price))} جنيه"
        if price not in (None, "") else "💰 السعر: للاستعلام"
    )
    if desc:
        parts.append(f"\n{desc}")

    caption = "\n".join(parts)
    sent, failed = 0, 0

    for uid in ids:
        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=uid, photo=photo_id, caption=caption
                )
            else:
                await context.bot.send_message(chat_id=uid, text=caption)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"New Product Broadcast Failed for {uid}:", repr(e), flush=True)
        await asyncio.sleep(0.05)

    log_action(
        ADMIN_ID, "NEW_PRODUCT_BROADCAST",
        new_value=f"sent={sent} failed={failed}",
    )


def whatsapp_send_template(phone_number, p24, p21, p18):
    """
    Sends the approved 'gold_price_update' WhatsApp template to a
    single phone number via the WhatsApp Cloud API. WhatsApp only
    allows business-initiated messages through pre-approved
    templates — free-form text is not allowed outside a customer's
    own 24h reply window. Returns {"ok": bool, "message"/"post_id"}.
    """
    if not WHATSAPP_PHONE_NUMBER_ID:
        return {
            "ok": False,
            "message": "❌ WHATSAPP_PHONE_NUMBER_ID غير موجود في Railway.",
        }

    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        return {
            "ok": False,
            "message": "❌ FACEBOOK_PAGE_TOKEN غير موجود في Railway.",
        }

    template_name = os.getenv(
        "WHATSAPP_GOLD_TEMPLATE", "gold_price_update"
    ).strip()
    template_lang = os.getenv(
        "WHATSAPP_TEMPLATE_LANG", "ar_EG"
    ).strip()

    graph_version = os.getenv("FACEBOOK_GRAPH_VERSION", "v26.0").strip()
    if not graph_version.startswith("v"):
        graph_version = "v" + graph_version

    url = (
        f"https://graph.facebook.com/{graph_version}"
        f"/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p24)},
                    {"type": "text", "text": str(p21)},
                    {"type": "text", "text": str(p18)},
                ],
            }],
        },
    }

    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {FACEBOOK_PAGE_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        try:
            data = r.json()
        except Exception:
            data = {}

        print(f"WA SEND STATUS ({phone_number}): {r.status_code}", flush=True)
        print(f"WA SEND RESPONSE: {r.text}", flush=True)

        if r.status_code >= 300:
            return {"ok": False, "message": fb_error_text(data)}

        msg_id = (
            (data.get("messages") or [{}])[0].get("id")
            if data.get("messages") else None
        )
        return {"ok": True, "post_id": msg_id}

    except requests.RequestException as e:
        return {"ok": False, "message": repr(e)}


async def broadcast_gold_update_whatsapp(context, new_price):
    """
    Sends the approved WhatsApp template with the new gold price to
    every subscribed WhatsApp number. Best-effort per number, with a
    short delay between sends to stay well under WhatsApp's rate
    limits.
    """
    numbers = whatsapp_subscriber_numbers()
    if not numbers:
        return

    p24, p21, p18 = calc(new_price)
    sent, failed = 0, 0

    for number in numbers:
        result = whatsapp_send_template(number, p24, p21, p18)
        if result.get("ok"):
            sent += 1
        else:
            failed += 1
            print(
                f"WhatsApp Broadcast Failed for {number}:",
                result.get("message"), flush=True,
            )
        await asyncio.sleep(0.1)

    log_action(
        ADMIN_ID, "GOLD_PRICE_BROADCAST_WHATSAPP",
        new_value=f"sent={sent} failed={failed}",
    )


async def maybe_send_gold_alert(context, prev_price, new_price):
    threshold = gold_alert_threshold()
    if not threshold or prev_price is None:
        return

    diff = round(new_price - prev_price)
    if abs(diff) < threshold:
        return

    arrow = "📈" if diff > 0 else "📉"
    sign = "+" if diff > 0 else ""

    try:
        text = (
            f"🔔 تغير سعر الذهب\n\n"
            f"عيار 21:\n"
            f"السابق: {round(prev_price)}\n"
            f"الجديد: {round(new_price)}\n\n"
            f"التغير:\n{arrow} {sign}{diff} جنيه"
        )
        for admin_id in all_admin_ids():
            try:
                await context.bot.send_message(chat_id=admin_id, text=text)
            except Exception as e:
                print(
                    f"Gold Alert Send Error ({admin_id}):", repr(e), flush=True
                )
        log_action(
            ADMIN_ID, "GOLD_ALERT_TRIGGERED",
            old_value=round(prev_price), new_value=round(new_price),
        )
    except Exception as e:
        print("Gold Alert Error:", repr(e), flush=True)


async def start(update, context):
    context.user_data.clear()
    track_user(update)
    await update.message.reply_text(
        "💎 مجوهرات الحسيني\n\n"
        "أهلاً بيك في البوت الرسمي لمجوهرات الحسيني - بورسعيد ✨\n\n"
        "اختار من القائمة 👇",
        reply_markup=home(is_admin(update), is_gold_subscribed(update.effective_user.id)),
    )


async def show_id(update, context):
    u = update.effective_user
    await update.message.reply_text(
        f"🆔 آيدي تليجرام بتاعك:\n\n{u.id}"
    )


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


async def facebook_story(image_bytes, base, graph_version):
    """
    Publishes the given image bytes to the Facebook Page Story.
    Two-step flow: upload an unpublished photo to get a photo_id,
    then attach that photo_id to /{page_id}/photo_stories.
    Best-effort — failures here never affect the main feed post.
    """
    photos_url = f"{base}/{FACEBOOK_PAGE_ID}/photos"
    story_url = f"{base}/{FACEBOOK_PAGE_ID}/photo_stories"

    try:
        r = requests.post(
            photos_url,
            data={
                "published": "false",
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            files={"source": ("story.jpg", image_bytes, "image/jpeg")},
            timeout=30,
        )
        try:
            uploaded = r.json()
        except Exception:
            uploaded = {}

        print(f"FB STORY UPLOAD STATUS: {r.status_code}", flush=True)
        print(f"FB STORY UPLOAD RESPONSE: {r.text}", flush=True)

        if r.status_code >= 300 or not uploaded.get("id"):
            return {"ok": False, "message": fb_error_text(uploaded)}

        r2 = requests.post(
            story_url,
            data={
                "photo_id": uploaded["id"],
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        try:
            published = r2.json()
        except Exception:
            published = {}

        print(f"FB STORY PUBLISH STATUS: {r2.status_code}", flush=True)
        print(f"FB STORY PUBLISH RESPONSE: {r2.text}", flush=True)

        if r2.status_code >= 300:
            return {"ok": False, "message": fb_error_text(published)}

        return {"ok": True, "post_id": published.get("post_id")}

    except requests.RequestException as e:
        return {"ok": False, "message": repr(e)}


async def facebook_photo(text, photo_url):
    """
    Publishes a photo post to the Facebook Page feed, then
    best-effort publishes the same image to the Facebook Page Story.

    IMPORTANT: We download the image bytes ourselves and upload them
    directly (multipart/form-data) instead of passing a Telegram URL
    for Facebook to fetch server-side. Meta's server-side fetcher
    frequently fails to reach api.telegram.org's CDN ("Missing or
    invalid image file" / code 324), so downloading locally and
    uploading the bytes is far more reliable.
    """

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
    photos_url = f"{base}/{FACEBOOK_PAGE_ID}/photos"

    try:
        img = requests.get(photo_url, timeout=30)
        img.raise_for_status()
    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ فشل تحميل الصورة من تليجرام:\n{repr(e)}",
        }

    try:
        r = requests.post(
            photos_url,
            data={
                "caption": text or "",
                "published": "true",
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            files={"source": ("photo.jpg", img.content, "image/jpeg")},
            timeout=30,
        )

        try:
            created = r.json()
        except Exception:
            created = {}

        print(f"FB PHOTO STATUS: {r.status_code}", flush=True)
        print(f"FB PHOTO RESPONSE: {r.text}", flush=True)

        if r.status_code >= 300:
            return {
                "ok": False,
                "message": (
                    "❌ فشل نشر الصورة على Facebook.\n\n"
                    + fb_error_text(created)
                ),
            }

        post_id = created.get("post_id") or created.get("id")

        out = {
            "ok": True,
            "message": "✅ تم نشر الصورة على Facebook (فيد).",
            "post_id": post_id,
        }

        story_result = await facebook_story(img.content, base, graph_version)
        out["story_ok"] = story_result.get("ok", False)
        out["story_message"] = (
            "✅ اتنشرت في ستوري فيسبوك كمان."
            if story_result.get("ok") else
            "⚠️ الفيد اتنشر، بس ستوري فيسبوك فشل: "
            + story_result.get("message", "")
        )

        return out

    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ خطأ شبكة أثناء نشر الصورة على Facebook:\n{repr(e)}",
        }


async def _ig_container_publish(base, data, timeout_polls=10):
    """
    Shared helper: creates an Instagram media container, waits for
    Instagram to finish processing it (status_code == FINISHED),
    then publishes it. Returns (ok, result_dict).
    Used for both feed photos and Instagram Stories — they use the
    exact same container flow, only the media_type differs.
    """
    media_url = f"{base}/{INSTAGRAM_BUSINESS_ID}/media"
    publish_url = f"{base}/{INSTAGRAM_BUSINESS_ID}/media_publish"

    r, created = fb_request("POST", media_url, data=data)

    print(f"IG MEDIA STATUS: {r.status_code}", flush=True)
    print(f"IG MEDIA RESPONSE: {r.text}", flush=True)

    if r.status_code >= 300 or not created.get("id"):
        return False, {"message": fb_error_text(created)}

    creation_id = created["id"]
    status_url = f"{base}/{creation_id}"

    ready = False
    last_status = None
    for _ in range(timeout_polls):
        try:
            sr, sdata = fb_request(
                "GET",
                status_url,
                params={
                    "fields": "status_code",
                    "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
                },
            )
            last_status = sdata.get("status_code")
            print(f"IG CONTAINER STATUS: {last_status}", flush=True)

            if last_status == "FINISHED":
                ready = True
                break
            if last_status in ("ERROR", "EXPIRED"):
                break
        except requests.RequestException:
            pass

        await asyncio.sleep(2)

    if not ready and last_status not in (None, "IN_PROGRESS"):
        return False, {
            "message": f"الحالة: {last_status or 'غير معروفة'}"
        }

    r2, published = fb_request(
        "POST",
        publish_url,
        data={
            "creation_id": creation_id,
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        },
    )

    print(f"IG PUBLISH STATUS: {r2.status_code}", flush=True)
    print(f"IG PUBLISH RESPONSE: {r2.text}", flush=True)

    if r2.status_code >= 300:
        return False, {"message": fb_error_text(published)}

    return True, {"post_id": published.get("id")}


async def instagram_photo(text, photo_url):
    """
    Publishes a photo post to Instagram using the two-step
    Graph API flow: create a media container, then publish it.
    Requires an Instagram professional account connected to the
    Facebook Page, and INSTAGRAM_BUSINESS_ID set in env vars.

    Instagram needs a few seconds to download and process the image
    into the container before it can be published — we poll the
    container's status_code until it's FINISHED (or a short timeout
    passes) instead of publishing immediately, which otherwise fails
    with "Media ID is not available" (code 9007).

    After the feed post succeeds, this also best-effort publishes
    the same image to the Instagram Story. A story failure does NOT
    make the overall result fail — the feed post already succeeded —
    but is reported back via the "story_message" key.
    """

    if not INSTAGRAM_BUSINESS_ID:
        return {
            "ok": False,
            "message": "❌ INSTAGRAM_BUSINESS_ID غير موجود في Railway Variables.",
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

    try:
        ok, result = await _ig_container_publish(base, {
            "image_url": photo_url,
            "caption": text or "",
            "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
        })

        if not ok:
            return {
                "ok": False,
                "message": (
                    "❌ فشل نشر الصورة على Instagram.\n\n"
                    + result.get("message", "")
                ),
            }

        out = {
            "ok": True,
            "message": "✅ تم النشر على Instagram (فيد).",
            "post_id": result.get("post_id"),
        }

        # Best-effort: also publish the same image as an Instagram
        # Story. Stories don't take a caption via the API.
        try:
            story_ok, story_result = await _ig_container_publish(base, {
                "image_url": photo_url,
                "media_type": "STORIES",
                "access_token": FACEBOOK_PAGE_ACCESS_TOKEN,
            })
            out["story_ok"] = story_ok
            out["story_message"] = (
                "✅ اتنشرت في الستوري كمان."
                if story_ok else
                "⚠️ الفيد اتنشر، بس الستوري فشل: "
                + story_result.get("message", "")
            )
        except Exception as e:
            out["story_ok"] = False
            out["story_message"] = f"⚠️ الفيد اتنشر، بس الستوري فشل: {repr(e)}"

        return out

    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ خطأ شبكة أثناء النشر على Instagram:\n{repr(e)}",
        }


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


async def tg_post(context, text, photo_id=None):
    if not CHANNEL_ID:
        return False

    try:
        if photo_id:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_id,
                caption=text or None,
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=text,
            )
        return True
    except Exception as e:
        print("Telegram Post Error:", repr(e), flush=True)
        return False


# =========================================================
# PHOTO
# =========================================================

async def photo(update, context):
    if not is_admin(update):
        await update.message.reply_text("❌ غير مسموح.")
        return

    state = context.user_data.get("state")

    if state == "edit_photo":
        pid = context.user_data.get("edit_pid")

        if not pid:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ حصل خطأ، ابدأ التعديل من جديد.",
                reply_markup=prod_menu(),
            )
            return

        ok = update_product_photo(pid, update.message.photo[-1].file_id)

        if ok:
            log_action(
                update.effective_user.id, "ADMIN_UPDATED_PRODUCT",
                new_value="photo changed",
                object_type="product", object_id=pid,
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تغيير الصورة." if ok else "⚠️ المنتج غير موجود.",
            reply_markup=product_edit_menu(pid),
        )
        return

    if state == "new_post":
        context.user_data["post_text"] = update.message.caption or ""
        context.user_data["post_photo"] = update.message.photo[-1].file_id
        context.user_data["state"] = None

        await update.message.reply_text(
            "📝 المنشور جاهز.\nاختار مكان النشر:",
            reply_markup=newpost_menu(has_photo=True),
        )
        return

    if state != "product_photo":
        await update.message.reply_text(
            "❌ ابدأ إضافة المنتج من لوحة التحكم."
        )
        return

    cid = context.user_data.get("cid")
    name = context.user_data.get("name")
    code = context.user_data.get("code")
    price = context.user_data.get("price")
    desc = context.user_data.get("desc")
    photo_id = update.message.photo[-1].file_id

    try:
        pid = add_product(cid, photo_id, name, code, price, desc)

        context.user_data.clear()

        log_action(
            update.effective_user.id, "ADMIN_CREATED_PRODUCT",
            object_type="product", object_id=pid,
        )

        await update.message.reply_text(
            f"✅ تم إضافة المنتج بنجاح.\n🆔 #{pid}",
            reply_markup=prod_menu(),
        )

        await broadcast_new_product(context, photo_id, name, code, price, desc)
    except Exception as e:
        print("Product error:", repr(e), flush=True)
        log_action(
            update.effective_user.id, "ADMIN_CREATED_PRODUCT",
            status="failed", error=repr(e),
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

    t = (update.message.text or "").strip()
    s = context.user_data.get("state")

    if s == "new_post":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not t:
            await update.message.reply_text(
                "❌ اكتب نص المنشور، أو ابعت صورة."
            )
            return

        context.user_data["post_text"] = t
        context.user_data["post_photo"] = None
        context.user_data["state"] = None

        await update.message.reply_text(
            "📝 المنشور جاهز.\nاختار مكان النشر:",
            reply_markup=newpost_menu(),
        )
        return

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

        prev_p = latest()

        save_latest(p, admin_id=update.effective_user.id)
        log_action(
            update.effective_user.id, "ADMIN_CHANGED_GOLD_PRICE",
            old_value=prev_p, new_value=f"price_21={round(p)}",
        )

        if first_today() is None:
            save_first(p)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم تحديث السعر.\n\n" + price_text(p),
            reply_markup=gold_menu(),
        )
        await maybe_send_gold_alert(context, prev_p, p)
        await broadcast_gold_update(context, p)
        await broadcast_gold_update_whatsapp(context, p)
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

    if s == "edit_field":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        pid = context.user_data.get("edit_pid")
        field = context.user_data.get("edit_field")

        if not pid or not field:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ حصل خطأ، ابدأ التعديل من جديد.",
                reply_markup=prod_menu(),
            )
            return

        old = product(pid) or {}

        if field == "price":
            if t.lower() == "بدون":
                value = None
            else:
                try:
                    value = float(t)
                    if value < 0:
                        raise ValueError
                except Exception:
                    await update.message.reply_text(
                        "❌ اكتب رقم صحيح أو: بدون"
                    )
                    return
        else:
            value = None if t.lower() == "بدون" else t

        ok = update_product_field(pid, field, value)

        if ok and is_admin(update):
            log_action(
                update.effective_user.id, "ADMIN_UPDATED_PRODUCT",
                old_value=old.get(EDITABLE_FIELDS.get(field, field)),
                new_value=value,
                object_type="product", object_id=pid,
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم التعديل بنجاح." if ok else "⚠️ المنتج غير موجود.",
            reply_markup=product_edit_menu(pid),
        )
        return

    if s == "search_query":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not t:
            await update.message.reply_text("❌ اكتب كلمة البحث.")
            return

        ps = search_products(t)
        context.user_data.clear()
        context.user_data["search_results"] = ps

        if not ps:
            await update.message.reply_text(
                f"🔎 لا توجد نتائج لـ: {t}",
                reply_markup=prod_menu(),
            )
            return

        await update.message.reply_text(
            f"🔎 نتائج البحث ({len(ps)} منتج):",
            reply_markup=product_pick_kb(
                ps, 0, "searchprodo", "aprod"
            ),
        )
        return

    if s == "admin_reply":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        target_id = context.user_data.get("reply_to")
        context.user_data.clear()

        if not target_id:
            await update.message.reply_text(
                "❌ حصل خطأ، جرب تدوس على زرار الرد تاني."
            )
            return

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💬 رد من مجوهرات الحسيني:\n\n{t}",
            )
            log_action(
                update.effective_user.id, "ADMIN_REPLIED_TO_CUSTOMER",
                object_type="user", object_id=target_id, new_value=t,
            )
            await update.message.reply_text("✅ اتبعت الرد للعميل.")
        except Exception as e:
            print("Admin Reply Error:", repr(e), flush=True)
            log_action(
                update.effective_user.id, "ADMIN_REPLIED_TO_CUSTOMER",
                object_type="user", object_id=target_id,
                status="failed", error=repr(e),
            )
            await update.message.reply_text(
                "❌ مقدرتش أبعت الرد (يمكن العميل عمل Block للبوت)."
            )
        return

    if s == "wa_phone_input":
        digits = re.sub(r"\D", "", t)

        if not re.match(r"^20\d{9,10}$", digits):
            await update.message.reply_text(
                "❌ الرقم مش صحيح. اكتبه بالكود الدولي 20 من غير علامة +.\n"
                "مثال: 201012345678"
            )
            return

        wa_return = context.user_data.get("wa_return", "gold")
        set_whatsapp_subscription(update.effective_user.id, digits, True)
        context.user_data.clear()

        if wa_return == "home":
            await update.message.reply_text(
                "✅ تم تفعيل الإشعارات على تليجرام وواتساب.\n\n"
                "💎 مجوهرات الحسيني\n\nاختار من القائمة 👇",
                reply_markup=home(is_admin(update), True),
            )
            return

        p = latest()
        await update.message.reply_text(
            "✅ تم الاشتراك في تحديثات واتساب.\n\n"
            + (price_text(p) if p else ""),
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return

    if s == "admin_add":
        if not is_owner(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not t.strip().isdigit():
            await update.message.reply_text(
                "❌ اكتب آيدي تليجرام صحيح (أرقام بس)."
            )
            return

        uid = int(t.strip())
        context.user_data.clear()

        ok = add_extra_admin(uid)

        if ok:
            log_action(
                update.effective_user.id, "OWNER_ADDED_ADMIN",
                object_type="user", object_id=uid,
            )
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="👑 تم إضافتك كأدمن في بوت مجوهرات الحسيني.\n"
                         "استخدم /start عشان تشوف لوحة التحكم.",
                )
            except Exception as e:
                print("Notify New Admin Error:", repr(e), flush=True)

        await update.message.reply_text(
            "✅ تم إضافة الأدمن." if ok
            else "⚠️ الآيدي ده أدمن بالفعل."
        )
        return

    if s == "sched_time":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", t):
            await update.message.reply_text(
                "❌ الصيغة غلط. اكتب الموعد بصيغة HH:MM.\nمثال: 18:00"
            )
            return

        sid = add_scheduled_post(t, platforms="tg,fb", template_key="normal")
        log_action(
            update.effective_user.id, "ADMIN_ADDED_SCHEDULE",
            new_value=t, object_type="schedule", object_id=sid,
        )

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ تم إضافة موعد النشر التلقائي: {t}\n"
            "(هينشر بأسعار الذهب على تليجرام + فيسبوك بالقالب العادي)",
            reply_markup=scheduler_menu(),
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
        reply_markup=home(is_admin(update), is_gold_subscribed(update.effective_user.id)),
    )


# =========================================================
# BUTTONS
# =========================================================

async def buttons(update, context):
    q = update.callback_query
    await q.answer()
    c = q.data
    track_user(update)

    if c == "home":
        context.user_data.clear()
        await q.edit_message_text(
            "💎 مجوهرات الحسيني\n\nاختار من القائمة 👇",
            reply_markup=home(is_admin(update), is_gold_subscribed(update.effective_user.id)),
        )
        return

    if c == "admin":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        context.user_data.clear()
        await q.edit_message_text(
            "👑 لوحة التحكم\n\nاختار العملية:",
            reply_markup=admin_menu(owner=is_owner(update)),
        )
        return

    if c == "newpost":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data["state"] = "new_post"

        await q.edit_message_text(
            "📝 ابعت المنشور:\n\n"
            "- اكتب نص، أو\n"
            "- ابعت صورة (تقدر تحط تعليق عليها كنص المنشور)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="admin")]
            ]),
        )
        return

    if c == "products":
        if products_paused():
            await q.edit_message_text(
                "🚧 المنتجات غير متاحة حالياً، وسيتم التحديث قريبًا.\n\n"
                "الأسعار المحسوبة (سبائك وعملات) لسه متاحة عادي:",
                reply_markup=products_paused_kb(),
            )
            return

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

    if c.startswith("bar:") or c.startswith("coin:"):
        is_bars = c.startswith("bar:")
        idx = int(c.split(":")[1])
        items = GOLD_BARS if is_bars else GOLD_COINS

        if idx < 0 or idx >= len(items):
            return

        label, weight = items[idx]
        p21 = latest()

        if not p21:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="💎 لم يتم تحديث أسعار الذهب حتى الآن.",
            )
            return

        p24, p21_calc, p18 = calc(p21)
        per_gram = p24 if is_bars else p21_calc
        price = round(weight * per_gram)

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=(
                f"💰 سعر {label}: {price} جنيه\n\n"
                f"{GOLD_PURITY_DISCLAIMER}"
            ),
        )
        return

    if c.startswith("cm:") or c.startswith("cs:"):
        cid = int(c.split(":")[1])
        cur = cat(cid)
        children = cats(cid)

        back_cb = (
            f"cm:{cur['parent_id']}" if cur["parent_id"] else "products"
        )

        # Regular product browsing can be paused by the admin (e.g.
        # while re-stocking) without affecting the "سبائك"/"عملات"
        # computed-price catalogs, which stay open to customers.
        if (
            cur["name"].strip() not in PROTECTED_FIXED_CATEGORIES
            and products_paused()
        ):
            await q.edit_message_text(
                "🚧 المنتجات غير متاحة حالياً، وسيتم التحديث قريبًا.\n\n"
                "الأسعار المحسوبة (سبائك وعملات) لسه متاحة عادي:",
                reply_markup=products_paused_kb(),
            )
            return

        # "سبائك" and "عملات" are fixed, price-computed catalogs, not
        # regular browsable/product categories — show their weight
        # menu no matter what (even if someone accidentally added a
        # child category under them).
        if cur["name"].strip() in PROTECTED_FIXED_CATEGORIES:
            is_bars = cur["name"].strip() == "سبائك"
            items = GOLD_BARS if is_bars else GOLD_COINS
            prefix = "bar" if is_bars else "coin"

            k = [
                [InlineKeyboardButton(label, callback_data=f"{prefix}:{i}")]
                for i, (label, _) in enumerate(items)
            ]
            k.append([InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)])

            await q.edit_message_text(
                f"💰 {cur['name']}\n\nاختار الوزن:",
                reply_markup=InlineKeyboardMarkup(k),
            )
            return

        if children:
            k = [
                [InlineKeyboardButton(
                    f"🟡 {ch['name']} ({ch['product_count']})",
                    callback_data=f"cm:{ch['id']}"
                )]
                for ch in children
            ]
            k.append([InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)])

            await q.edit_message_text(
                f"💍 {cur['name']}\n\nاختار القسم الفرعي:",
                reply_markup=InlineKeyboardMarkup(k),
            )
            return

        # Leaf category — show its products directly.
        ps = customer_products(cid)

        if not ps:
            await q.edit_message_text(
                f"🟡 {cur['name']}\n\nلا توجد منتجات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)]
                ]),
            )
            return

        await q.edit_message_text(
            f"🟡 {cur['name']}\n\nعدد المنتجات: {len(ps)}"
        )

        for p in ps:
            parts = []

            if p["name"]:
                parts.append(f"💍 {p['name']}")
            if p["code"]:
                parts.append(f"🔖 الكود: {p['code']}")

            parts.append(
                f"💰 السعر: {round(float(p['price']))} جنيه"
                if p.get("price") not in (None, "")
                else "💰 السعر: للاستعلام"
            )

            status = p.get("status") or "available"
            if status != "available":
                parts.append(STATUS_LABELS.get(status, ""))

            if p["description"]:
                parts.append(f"\n{p['description']}")

            buttons_rows = []
            if status not in ("sold", "hidden"):
                buttons_rows.append([InlineKeyboardButton(
                    "📩 استعلام عن المنتج",
                    callback_data=f"inq:{p['id']}"
                )])

            buttons_rows.append([
                InlineKeyboardButton("💬 واتساب", url=WHATSAPP),
                InlineKeyboardButton("📍 الموقع", url=MAPS),
            ])
            buttons_rows.append([
                InlineKeyboardButton("🌐 الموقع الإلكتروني", url=WEBSITE),
            ])

            try:
                await q.message.reply_photo(
                    photo=p["Photo_id"],
                    caption="\n".join(parts) or None,
                    reply_markup=InlineKeyboardMarkup(buttons_rows),
                )
                inc_product_counter(p["id"], "views_count")
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

    if c == "goldtoday":
        if not is_admin(update):
            return

        st = gold_today_stats()

        if not st:
            await q.edit_message_text(
                "📊 لا يوجد سعر مسجل اليوم حتى الآن.",
                reply_markup=gold_menu(),
            )
            return

        txt = (
            "📊 أسعار اليوم (عيار 21)\n\n"
            f"🟢 أول سعر: {st['first']}\n"
            f"🔵 آخر سعر: {st['last']}\n"
            f"⬆️ أعلى سعر: {st['high']}\n"
            f"⬇️ أقل سعر: {st['low']}\n"
            f"📈 مقدار التغير: {st['change']:+d} جنيه\n"
            f"📊 نسبة التغير: {st['pct']:+.2f}%\n"
            f"🔄 عدد مرات التحديث: {st['count']}"
        )

        await q.edit_message_text(txt, reply_markup=gold_menu())
        return

    if c == "histmenu":
        if not is_admin(update):
            return

        await q.edit_message_text(
            "📅 اختار الفترة:",
            reply_markup=hist_period_menu(),
        )
        return

    if c.startswith("histp:"):
        if not is_admin(update):
            return

        days = int(c.split(":")[1])
        period_names = {0: "اليوم", 1: "أمس", 7: "آخر 7 أيام", 30: "آخر 30 يوم"}
        st = gold_period_stats(days)

        if not st:
            await q.edit_message_text(
                f"📅 {period_names.get(days, '')}\n\n"
                "لا يوجد سعر مسجل في الفترة دي.",
                reply_markup=hist_period_menu(),
            )
            return

        lines = [
            f"📅 {period_names.get(days, '')} (عيار 21)",
            "",
            f"🟢 أول سعر: {st['first']}",
            f"🔵 آخر سعر: {st['last']}",
            f"⬆️ أعلى سعر: {st['high']}",
            f"⬇️ أقل سعر: {st['low']}",
            f"📈 مقدار التغير: {st['change']:+d} جنيه",
            f"📊 نسبة التغير: {st['pct']:+.2f}%",
            f"🔄 عدد مرات التحديث: {st['count']}",
        ]

        if days in (0, 1):
            lines.append("")
            lines.append("🕐 آخر 10 تحديثات:")
            for r in st["rows"][-10:]:
                ts = r["created_at"]
                ts_str = (
                    ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)
                )
                lines.append(f"   {ts_str} — {round(float(r['price_21']))}")

        await q.edit_message_text(
            "\n".join(lines), reply_markup=hist_period_menu()
        )
        return

    if c == "alertmenu":
        if not is_admin(update):
            return

        await q.edit_message_text(
            "🔔 تنبيهات تغيّر سعر الذهب\n\n"
            "اختار الحد اللي عايز تتنبه لما السعر يتغير بيه أو أكتر:",
            reply_markup=alert_menu(),
        )
        return

    if c.startswith("alertset:"):
        if not is_admin(update):
            return

        val = c.split(":")[1]
        set_setting("gold_alert_threshold", val)

        log_action(
            update.effective_user.id, "ADMIN_SET_GOLD_ALERT",
            new_value=val,
        )

        msg = (
            "⏸ تم إيقاف تنبيهات السعر." if val == "0"
            else f"✅ تم ضبط التنبيه على {val} جنيه."
        )

        await q.edit_message_text(msg, reply_markup=alert_menu())
        return

    if c == "history":
        st = gold_period_stats(30)
        txt = "📜 سجل الأسعار (آخر 30 يوم)\n\n"

        if st:
            txt += "\n".join(
                f"📅 {r['created_at'].strftime('%Y-%m-%d %H:%M') if hasattr(r['created_at'], 'strftime') else r['created_at']}"
                f" — {round(float(r['price_21']))} جنيه"
                for r in reversed(st["rows"][-30:])
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

        context.user_data["pending_price"] = round(p)

        await q.edit_message_text(
            "🎨 اختار قالب المنشور:",
            reply_markup=template_pick_menu(),
        )
        return

    if c.startswith("tpl:"):
        if not is_admin(update):
            return

        key = c.split(":")[1]
        p = context.user_data.get("pending_price")

        if p is None:
            await q.edit_message_text(
                "❌ السعر انتهى، جرب تاني.",
                reply_markup=gold_menu(),
            )
            return

        context.user_data.update(
            price_text=render_template(key, p),
            price=p,
            first=False,
        )

        await q.edit_message_text(
            "📢 اختار مكان النشر:",
            reply_markup=publish_menu(),
        )
        return

    if c == "schedmenu":
        if not is_admin(update):
            return

        rows = scheduled_posts()
        txt = (
            "⏰ النشر التلقائي\n\n"
            + (f"عدد المواعيد: {len(rows)}" if rows else "لا توجد مواعيد بعد.")
        )

        await q.edit_message_text(txt, reply_markup=scheduler_menu())
        return

    if c == "schedadd":
        if not is_admin(update):
            return

        context.user_data.clear()
        context.user_data["state"] = "sched_time"

        await q.edit_message_text(
            "⏰ اكتب الموعد بصيغة HH:MM (بتوقيت القاهرة).\n"
            "مثال: 09:30"
        )
        return

    if c.startswith("schedopen:"):
        if not is_admin(update):
            return

        sid = int(c.split(":")[1])
        sp = scheduled_post(sid)

        if not sp:
            await q.edit_message_text(
                "⚠️ الموعد غير موجود.",
                reply_markup=scheduler_menu(),
            )
            return

        tpl_name = TEMPLATES.get(
            sp.get("template_key") or "normal", TEMPLATES["normal"]
        )["name"]

        txt = (
            f"⏰ الموعد: {sp['time_str']}\n"
            f"📢 المنصات: {sp['platforms']}\n"
            f"🎨 القالب: {tpl_name}\n"
            f"الحالة: {'🟢 شغال' if sp['enabled'] else '⏸ متوقف'}"
        )

        await q.edit_message_text(
            txt, reply_markup=scheduler_item_menu(sid)
        )
        return

    if c.startswith("schedtoggle:"):
        if not is_admin(update):
            return

        sid = int(c.split(":")[1])
        toggle_scheduled_post(sid)
        log_action(
            update.effective_user.id, "ADMIN_TOGGLED_SCHEDULE",
            object_type="schedule", object_id=sid,
        )

        sp = scheduled_post(sid)
        await q.edit_message_text(
            "✅ تم تحديث حالة الموعد.",
            reply_markup=scheduler_item_menu(sid) if sp else scheduler_menu(),
        )
        return

    if c.startswith("scheddel:"):
        if not is_admin(update):
            return

        sid = int(c.split(":")[1])
        ok = delete_scheduled_post(sid)

        if ok:
            log_action(
                update.effective_user.id, "ADMIN_DELETED_SCHEDULE",
                object_type="schedule", object_id=sid,
            )

        await q.edit_message_text(
            "✅ تم حذف الموعد." if ok else "⚠️ الموعد غير موجود.",
            reply_markup=scheduler_menu(),
        )
        return

    if c.startswith("schedplatt:"):
        if not is_admin(update):
            return

        _, sid, plat = c.split(":")
        sid = int(sid)
        sp = scheduled_post(sid)

        if not sp:
            await q.edit_message_text(
                "⚠️ الموعد غير موجود.", reply_markup=scheduler_menu()
            )
            return

        plats = set((sp["platforms"] or "").split(","))
        plats.discard("")

        if plat in plats:
            if len(plats) > 1:
                plats.discard(plat)
        else:
            plats.add(plat)

        new_platforms = ",".join(sorted(plats)) or "tg"
        set_scheduled_post_platforms(sid, new_platforms)

        log_action(
            update.effective_user.id, "ADMIN_UPDATED_SCHEDULE",
            new_value=new_platforms, object_type="schedule", object_id=sid,
        )

        await q.edit_message_text(
            "📢 اختار المنصات (تقدر تختار أكتر من واحدة):",
            reply_markup=scheduler_platform_menu(sid, new_platforms),
        )
        return

    if c.startswith("schedplat:"):
        if not is_admin(update):
            return

        sid = int(c.split(":")[1])
        sp = scheduled_post(sid)

        if not sp:
            await q.edit_message_text(
                "⚠️ الموعد غير موجود.", reply_markup=scheduler_menu()
            )
            return

        await q.edit_message_text(
            "📢 اختار المنصات (تقدر تختار أكتر من واحدة):",
            reply_markup=scheduler_platform_menu(sid, sp["platforms"]),
        )
        return

    if c.startswith("schedtplset:"):
        if not is_admin(update):
            return

        _, sid, key = c.split(":")
        sid = int(sid)
        set_scheduled_post_template(sid, key)

        log_action(
            update.effective_user.id, "ADMIN_UPDATED_SCHEDULE",
            new_value=f"template={key}",
            object_type="schedule", object_id=sid,
        )

        sp = scheduled_post(sid)
        await q.edit_message_text(
            "✅ تم تغيير القالب.",
            reply_markup=scheduler_item_menu(sid) if sp else scheduler_menu(),
        )
        return

    if c.startswith("schedtpl:"):
        if not is_admin(update):
            return

        sid = int(c.split(":")[1])
        sp = scheduled_post(sid)

        if not sp:
            await q.edit_message_text(
                "⚠️ الموعد غير موجود.", reply_markup=scheduler_menu()
            )
            return

        await q.edit_message_text(
            "🎨 اختار القالب:",
            reply_markup=scheduler_template_menu(sid),
        )
        return

    if c == "adminlist":
        if not is_owner(update):
            return

        ids = get_extra_admins()
        lines = ["👥 إدارة الأدمنز", "", f"👑 المالك: {ADMIN_ID}"]

        k = []
        if ids:
            lines.append("")
            lines.append("الأدمنز الإضافيين:")
            for uid in ids:
                lines.append(f"• {uid}")
                k.append([InlineKeyboardButton(
                    f"🗑 حذف {uid}", callback_data=f"admindel:{uid}"
                )])
        else:
            lines.append("")
            lines.append("لا يوجد أدمنز إضافيين.")

        k.append([InlineKeyboardButton(
            "➕ إضافة أدمن", callback_data="adminadd"
        )])
        k.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")])

        await q.edit_message_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(k)
        )
        return

    if c == "adminadd":
        if not is_owner(update):
            return

        context.user_data.clear()
        context.user_data["state"] = "admin_add"

        await q.edit_message_text(
            "➕ ابعتلي آيدي تليجرام بتاع الشخص اللي عايز تضيفه أدمن.\n\n"
            "لو معرفش الآيدي بتاعه، خليه يبعتلك أي رسالة للبوت ويستخدم "
            "أمر /id عشان يجيبه."
        )
        return

    if c.startswith("admindel:"):
        if not is_owner(update):
            return

        uid = int(c.split(":")[1])
        ok = remove_extra_admin(uid)

        if ok:
            log_action(
                update.effective_user.id, "OWNER_REMOVED_ADMIN",
                object_type="user", object_id=uid,
            )

        await q.edit_message_text(
            "✅ تم حذف الأدمن." if ok else "⚠️ مش موجود أصلاً.",
        )
        ids = get_extra_admins()
        lines = ["👥 إدارة الأدمنز", "", f"👑 المالك: {ADMIN_ID}"]
        k = []
        if ids:
            lines.append("")
            lines.append("الأدمنز الإضافيين:")
            for i in ids:
                lines.append(f"• {i}")
                k.append([InlineKeyboardButton(
                    f"🗑 حذف {i}", callback_data=f"admindel:{i}"
                )])
        else:
            lines.append("")
            lines.append("لا يوجد أدمنز إضافيين.")
        k.append([InlineKeyboardButton(
            "➕ إضافة أدمن", callback_data="adminadd"
        )])
        k.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")])
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="\n".join(lines),
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c == "stats":
        if not is_admin(update):
            return

        pt = product_totals()
        ut = user_totals()
        pubt = publish_totals()

        txt = (
            "📊 الإحصائيات العامة\n\n"
            f"👥 إجمالي المستخدمين: {ut.get('total') or 0}\n"
            f"🟢 نشطون آخر 7 أيام: {ut.get('active_7d') or 0}\n"
            f"🔔 مشتركين في الإشعارات (تليجرام): {gold_subscriber_count()}\n"
            f"📱 مشتركين في تحديث السعر (واتساب): {whatsapp_subscriber_count()}\n"
            f"📩 إجمالي الاستعلامات: {ut.get('inquiries') or 0}\n\n"
            f"💍 إجمالي المنتجات: {pt.get('total') or 0}\n"
            f"🟢 متاحة: {pt.get('available') or 0}\n"
            f"🟡 محجوزة: {pt.get('reserved') or 0}\n"
            f"🔴 مباعة: {pt.get('sold') or 0}\n"
            f"⚪ مخفية: {pt.get('hidden') or 0}\n"
            f"👁 إجمالي مشاهدات المنتجات: {pt.get('views') or 0}\n\n"
            f"📢 عمليات النشر: {pubt.get('total') or 0} "
            f"(✅ {pubt.get('success') or 0} / ❌ {pubt.get('failed') or 0})"
        )

        await q.edit_message_text(txt, reply_markup=stats_menu())
        return

    if c == "statsview":
        if not is_admin(update):
            return

        rows = top_viewed_products()
        lines = ["🔥 أكثر المنتجات مشاهدة", ""]

        if rows:
            for i, r in enumerate(rows, 1):
                lines.append(
                    f"{i}. #{r['id']} {r['name'] or 'بدون اسم'} "
                    f"({r['code'] or '-'}) — 👁 {r['views_count']}"
                )
        else:
            lines.append("لا توجد بيانات حتى الآن.")

        await q.edit_message_text("\n".join(lines), reply_markup=stats_menu())
        return

    if c == "statsinq":
        if not is_admin(update):
            return

        rows = top_inquired_products()
        lines = ["🔥 أكثر المنتجات عليها استعلامات", ""]

        if rows:
            for i, r in enumerate(rows, 1):
                lines.append(
                    f"{i}. #{r['id']} {r['name'] or 'بدون اسم'} "
                    f"({r['code'] or '-'}) — 📩 {r['inquiries_count']}"
                )
        else:
            lines.append("لا توجد بيانات حتى الآن.")

        await q.edit_message_text("\n".join(lines), reply_markup=stats_menu())
        return

    if c == "statscat":
        if not is_admin(update):
            return

        rows = top_viewed_categories()
        lines = ["📂 أكثر الأقسام مشاهدة", ""]

        if rows:
            for i, r in enumerate(rows, 1):
                lines.append(
                    f"{i}. {r['main_name'] or '-'} → {r['sub_name'] or '-'} "
                    f"— 👁 {int(r['total_views'])}"
                )
        else:
            lines.append("لا توجد بيانات حتى الآن.")

        await q.edit_message_text("\n".join(lines), reply_markup=stats_menu())
        return

    if c == "statsusers":
        if not is_admin(update):
            return

        rows = top_inquiring_users()
        lines = ["👥 أكثر العملاء استعلامات", ""]

        if rows:
            for i, r in enumerate(rows, 1):
                uname = f"@{r['username']}" if r["username"] else "بدون يوزر"
                lines.append(
                    f"{i}. {r['first_name'] or '-'} ({uname}) "
                    f"— 📩 {r['inquiries_count']}"
                )
        else:
            lines.append("لا توجد بيانات حتى الآن.")

        await q.edit_message_text("\n".join(lines), reply_markup=stats_menu())
        return

    if c.startswith("logsp:"):
        if not is_admin(update):
            return

        page = int(c.split(":")[1])
        page_size = 15
        total = admin_logs_count()
        rows = recent_admin_logs(limit=page_size, offset=page * page_size)

        lines = [f"📋 سجل العمليات ({total} إجمالي)", ""]

        if not rows:
            lines.append("لا توجد سجلات.")
        else:
            for r in rows:
                ts = r["created_at"]
                ts_str = (
                    ts.strftime("%m-%d %H:%M")
                    if hasattr(ts, "strftime") else str(ts)
                )
                mark = "✅" if r["status"] == "success" else "❌"
                obj = (
                    f" [{r['object_type']}#{r['object_id']}]"
                    if r["object_type"] else ""
                )
                lines.append(f"{mark} {ts_str} — {r['action']}{obj}")
                if r["status"] != "success" and r["error"]:
                    lines.append(f"   ⚠️ {r['error'][:120]}")

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                "⬅️ أحدث", callback_data=f"logsp:{page-1}"
            ))
        if (page + 1) * page_size < total:
            nav.append(InlineKeyboardButton(
                "➡️ أقدم", callback_data=f"logsp:{page+1}"
            ))

        kb_rows = ([nav] if nav else []) + [
            [InlineKeyboardButton("⬅️ رجوع للإحصائيات", callback_data="stats")]
        ]

        await q.edit_message_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows)
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

        if not ms:
            await q.edit_message_text(
                "➕ لازم تضيف قسم رئيسي الأول.",
                reply_markup=cat_menu(),
            )
            return

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
            "➕ اختار القسم اللي عايز تضيف تحته قسم فرعي جديد:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("sp:"):
        pid = int(c.split(":")[1])
        parent = cat(pid)
        children = cats(pid)

        k = [
            [InlineKeyboardButton(
                "💍 " + ch["name"],
                callback_data=f"sp:{ch['id']}"
            )]
            for ch in children
        ]
        k.append([InlineKeyboardButton(
            f"➕ أضف هنا تحت: {parent['name']}",
            callback_data=f"spnew:{pid}"
        )])
        k.append([
            InlineKeyboardButton("⬅️ رجوع", callback_data="addsub")
        ])

        await q.edit_message_text(
            f"➕ {parent['name']}\n\n"
            "اختار قسم فرعي موجود عشان تنزل تحته أكتر، "
            "أو دوس \"أضف هنا\" عشان تضيف قسم جديد في المستوى ده:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("spnew:"):
        pid = int(c.split(":")[1])
        parent = cat(pid)

        if parent["name"].strip() in PROTECTED_FIXED_CATEGORIES:
            await q.edit_message_text(
                f"🔒 \"{parent['name']}\" قسم ثابت، مينفعش يتضاف تحته "
                "أقسام فرعية.",
                reply_markup=cat_menu(),
            )
            return

        context.user_data.clear()
        context.user_data.update(state="sub", parent=pid)

        await q.edit_message_text(
            f"➕ اكتب اسم القسم الفرعي الجديد تحت:\n{parent['name']}\n\n"
            "مثال: عيار 18"
        )
        return

    if c == "viewcats":
        rows = flatten_categories()
        lines = ["📂 الأقسام", ""]

        for cat_row, depth in rows:
            indent = "   " * depth
            marker = "💍" if depth == 0 else "🟡"
            extra = (
                f" ({cat_row['product_count']} منتج)"
                if depth > 0 else ""
            )
            lines.append(f"{indent}{'└ ' if depth else ''}{marker} {cat_row['name']}{extra}")

        await q.edit_message_text(
            "\n".join(lines) if rows else "📂 لا توجد أقسام.",
            reply_markup=cat_menu(),
        )
        return

    if c == "rename":
        rows = flatten_categories()

        k = [
            [InlineKeyboardButton(
                ("   " * depth) + "✏️ " + cat_row["name"],
                callback_data=f"rp:{cat_row['id']}"
            )]
            for cat_row, depth in rows
        ]

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

        if is_protected_root_category(cid):
            await q.edit_message_text(
                "🔒 القسم ده أساسي وثابت في البوت، مينفعش يتغير اسمه.",
                reply_markup=cat_menu(),
            )
            return

        context.user_data.clear()
        context.user_data.update(state="rename", cid=cid)

        await q.edit_message_text(
            f"✏️ الاسم الحالي: {cat(cid)['name']}\n\n"
            "اكتب الاسم الجديد:"
        )
        return

    if c == "deletecat":
        rows = flatten_categories()

        k = [
            [InlineKeyboardButton(
                ("   " * depth) + "🗑 " + cat_row["name"],
                callback_data=f"dc:{cat_row['id']}"
            )]
            for cat_row, depth in rows
        ]

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
            "protected": "🔒 القسم ده أساسي وثابت في البوت، مينفعش يتحذف.",
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

        if not ms:
            await q.edit_message_text(
                "➕ لازم تضيف قسم رئيسي الأول من (📂 إدارة الأقسام).",
                reply_markup=prod_menu(),
            )
            return

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
            "➕ اختار القسم:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("pm:"):
        cid = int(c.split(":")[1])
        cur = cat(cid)
        children = cats(cid)

        if cur["name"].strip() in PROTECTED_FIXED_CATEGORIES:
            await q.edit_message_text(
                f"🔒 \"{cur['name']}\" قسم أسعار محسوبة تلقائيًا من سعر "
                "الذهب، مينفعش يتضاف فيه منتجات يدوي.",
                reply_markup=prod_menu(),
            )
            return

        if children:
            k = [
                [InlineKeyboardButton(
                    "🟡 " + ch["name"],
                    callback_data=f"pm:{ch['id']}"
                )]
                for ch in children
            ]
            k.append([
                InlineKeyboardButton("⬅️ رجوع", callback_data="addprod")
            ])

            await q.edit_message_text(
                f"➕ {cat(cid)['name']}\n\nاختار القسم الفرعي:",
                reply_markup=InlineKeyboardMarkup(k),
            )
            return

        # Leaf category — products live here.
        context.user_data.clear()
        context.user_data.update(
            state="prod_name",
            cid=cid,
        )

        await q.edit_message_text(
            "💎 اكتب اسم المنتج.\nمثال: خاتم ذهب موديل ناعم"
        )
        return

    if c == "toggleprodpause":
        if not is_admin(update):
            return

        new_state = not products_paused()
        set_products_paused(new_state)

        log_action(
            update.effective_user.id,
            "ADMIN_PAUSED_PRODUCTS" if new_state else "ADMIN_RESUMED_PRODUCTS",
        )

        await q.edit_message_text(
            (
                "⏸️ تم إيقاف عرض المنتجات للعملاء مؤقتاً.\n"
                "(سبائك وعملات هتفضل شغالة عادي، وإنت كأدمن هتقدر "
                "تضيف/تعدل منتجات براحتك)"
                if new_state else
                "▶️ تم تفعيل عرض المنتجات للعملاء تاني."
            ),
            reply_markup=prod_menu(),
        )
        return

    if c == "viewprod":
        ps = all_products()
        lines = ["📋 المنتجات", ""]

        for p in ps[:50]:
            status = p.get("status") or "available"
            lines.append(
                f"{STATUS_LABELS.get(status, '')} 🆔 #{p['id']} | "
                f"{p['main_name'] or '-'} → {p['sub_name'] or '-'}\n"
                f"💎 {p['name'] or 'بدون اسم'} | "
                f"🔖 {p['code'] or '-'} | "
                f"👁 {p.get('views_count', 0)} 📩 {p.get('inquiries_count', 0)}"
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
        ok = del_product(pid)

        if ok and is_admin(update):
            log_action(
                update.effective_user.id, "ADMIN_DELETED_PRODUCT",
                object_type="product", object_id=pid,
            )

        await q.edit_message_text(
            "✅ تم حذف المنتج." if ok
            else "⚠️ المنتج غير موجود.",
            reply_markup=prod_menu(),
        )
        return

    # =====================================================
    # PRODUCT EDIT (single-field, no full re-entry)
    # =====================================================
    if c.startswith("editprod:") or c.startswith("editprodp:"):
        if not is_admin(update):
            return

        page = int(c.split(":")[1])
        ps = all_products()

        if not ps:
            await q.edit_message_text(
                "💍 لا توجد منتجات لتعديلها.",
                reply_markup=prod_menu(),
            )
            return

        await q.edit_message_text(
            f"✏️ اختار المنتج للتعديل (صفحة {page+1}):",
            reply_markup=product_pick_kb(
                ps, page, "editprodo", "aprod"
            ),
        )
        return

    if c.startswith("editprodop:"):
        page = int(c.split(":")[1])
        ps = all_products()

        await q.edit_message_text(
            f"✏️ اختار المنتج للتعديل (صفحة {page+1}):",
            reply_markup=product_pick_kb(
                ps, page, "editprodo", "aprod"
            ),
        )
        return

    if c.startswith("editprodo:") or c.startswith("editprod_open:"):
        pid = int(c.split(":")[1])
        p = product(pid)

        if not p:
            await q.edit_message_text(
                "⚠️ المنتج غير موجود.",
                reply_markup=prod_menu(),
            )
            return

        status = p.get("status") or "available"
        lines = [
            f"✏️ تعديل المنتج #{pid}",
            "",
            f"💎 الاسم: {p['name'] or '-'}",
            f"🔖 الكود: {p['code'] or '-'}",
            f"💰 السعر: {p['price'] if p['price'] is not None else '-'}",
            f"📝 الوصف: {p['description'] or '-'}",
            f"📊 الحالة: {STATUS_LABELS.get(status, status)}",
            f"👁 المشاهدات: {p.get('views_count', 0)}",
            f"📩 الاستعلامات: {p.get('inquiries_count', 0)}",
            "",
            "اختار الحقل اللي عايز تعدله:",
        ]

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=product_edit_menu(pid),
        )
        return

    if c.startswith("ef:"):
        if not is_admin(update):
            return

        _, field, pid = c.split(":")
        pid = int(pid)

        if field == "photo":
            context.user_data.clear()
            context.user_data.update(state="edit_photo", edit_pid=pid)
            await q.edit_message_text(
                "📸 ابعت الصورة الجديدة للمنتج."
            )
            return

        prompts = {
            "name": "💎 اكتب الاسم الجديد للمنتج:",
            "price": "💰 اكتب السعر الجديد (أو اكتب: بدون):",
            "code": "🔖 اكتب الكود الجديد (أو اكتب: بدون):",
            "desc": "📝 اكتب الوصف الجديد (أو اكتب: بدون):",
        }

        context.user_data.clear()
        context.user_data.update(
            state="edit_field", edit_field=field, edit_pid=pid
        )

        await q.edit_message_text(prompts.get(field, "اكتب القيمة الجديدة:"))
        return

    if c.startswith("stat:"):
        if not is_admin(update):
            return

        pid = int(c.split(":")[1])
        await q.edit_message_text(
            "🔄 اختار الحالة الجديدة للمنتج:",
            reply_markup=status_pick_kb(pid),
        )
        return

    if c.startswith("sset:"):
        if not is_admin(update):
            return

        _, pid, status = c.split(":")
        pid = int(pid)
        p = product(pid)
        old_status = (p or {}).get("status") or "available"

        ok = set_product_status(pid, status)

        if ok:
            log_action(
                update.effective_user.id, "ADMIN_UPDATED_PRODUCT",
                old_value=old_status, new_value=status,
                object_type="product", object_id=pid,
            )

        await q.edit_message_text(
            "✅ تم تغيير الحالة." if ok else "⚠️ المنتج غير موجود.",
            reply_markup=product_edit_menu(pid),
        )
        return

    if c.startswith("movecat:"):
        if not is_admin(update):
            return

        pid = int(c.split(":")[1])
        ms = cats()

        k = [
            [InlineKeyboardButton(
                "💍 " + m["name"], callback_data=f"movecatm:{pid}:{m['id']}"
            )]
            for m in ms
        ]
        k.append([InlineKeyboardButton(
            "⬅️ رجوع", callback_data=f"editprodo:{pid}"
        )])

        await q.edit_message_text(
            "📂 اختار القسم الجديد:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("movecatm:"):
        if not is_admin(update):
            return

        _, pid, cid = c.split(":")
        pid, cid = int(pid), int(cid)
        children = cats(cid)

        if not children:
            ok = move_product_category(pid, cid)

            if ok:
                log_action(
                    update.effective_user.id, "ADMIN_UPDATED_PRODUCT",
                    new_value=f"category_id={cid}",
                    object_type="product", object_id=pid,
                )

            await q.edit_message_text(
                "✅ تم نقل المنتج للقسم الجديد." if ok
                else "⚠️ المنتج غير موجود.",
                reply_markup=product_edit_menu(pid),
            )
            return

        k = [
            [InlineKeyboardButton(
                "🟡 " + ch["name"],
                callback_data=f"movecatm:{pid}:{ch['id']}"
            )]
            for ch in children
        ]
        k.append([InlineKeyboardButton(
            f"✅ اختار هنا: {cat(cid)['name']}",
            callback_data=f"movecathere:{pid}:{cid}"
        )])
        k.append([InlineKeyboardButton(
            "⬅️ رجوع", callback_data=f"movecat:{pid}"
        )])

        await q.edit_message_text(
            f"📂 {cat(cid)['name']}\n\nاختار القسم الفرعي، أو اختار نفس "
            "القسم ده لو مفيهوش تصنيف أدق:",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c.startswith("movecathere:"):
        if not is_admin(update):
            return

        _, pid, cid = c.split(":")
        pid, cid = int(pid), int(cid)

        ok = move_product_category(pid, cid)

        if ok:
            log_action(
                update.effective_user.id, "ADMIN_UPDATED_PRODUCT",
                new_value=f"category_id={cid}",
                object_type="product", object_id=pid,
            )

        await q.edit_message_text(
            "✅ تم نقل المنتج للقسم الجديد." if ok
            else "⚠️ المنتج غير موجود.",
            reply_markup=product_edit_menu(pid),
        )
        return

    if c == "searchprod":
        if not is_admin(update):
            return

        context.user_data.clear()
        context.user_data["state"] = "search_query"

        await q.edit_message_text(
            "🔎 اكتب كلمة البحث (اسم المنتج، الكود، أو اسم القسم):"
        )
        return

    if c.startswith("searchprodop:") or c.startswith("searchp:"):
        page = int(c.split(":")[-1])
        ps = context.user_data.get("search_results") or []

        if not ps:
            await q.edit_message_text(
                "🔎 لا توجد نتائج بحث محفوظة، ابحث تاني.",
                reply_markup=prod_menu(),
            )
            return

        await q.edit_message_text(
            f"🔎 نتائج البحث ({len(ps)} منتج) - صفحة {page+1}:",
            reply_markup=product_pick_kb(
                ps, page, "searchprodo", "aprod"
            ),
        )
        return

    if c.startswith("searchprodo:"):
        pid = int(c.split(":")[1])
        p = product(pid)

        if not p:
            await q.edit_message_text(
                "⚠️ المنتج غير موجود.",
                reply_markup=prod_menu(),
            )
            return

        status = p.get("status") or "available"
        lines = [
            f"✏️ تعديل المنتج #{pid}",
            "",
            f"💎 الاسم: {p['name'] or '-'}",
            f"🔖 الكود: {p['code'] or '-'}",
            f"💰 السعر: {p['price'] if p['price'] is not None else '-'}",
            f"📝 الوصف: {p['description'] or '-'}",
            f"📊 الحالة: {STATUS_LABELS.get(status, status)}",
            f"👁 المشاهدات: {p.get('views_count', 0)}",
            f"📩 الاستعلامات: {p.get('inquiries_count', 0)}",
            "",
            "اختار الحقل اللي عايز تعدله:",
        ]

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=product_edit_menu(pid),
        )
        return

    if c.startswith("inq:"):
        pid = int(c.split(":")[1])
        p = product(pid)

        if not p:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="⚠️ المنتج غير متاح حاليًا.",
            )
            return

        u = update.effective_user
        uname = f"@{u.username}" if u.username else "بدون يوزر"

        parts = [
            "📩 استعلام جديد عن منتج",
            "",
            f"👤 العميل: {u.full_name}",
            f"🔗 اليوزر: {uname}",
            f"🆔 آيدي تليجرام: {u.id}",
            "",
        ]

        if p["name"]:
            parts.append(f"💍 {p['name']}")

        try:
            reply_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💬 رد على العميل", callback_data=f"reply:{u.id}"
                )
            ]])
            for admin_id in all_admin_ids():
                try:
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=p["Photo_id"],
                        caption="\n".join(parts),
                        reply_markup=reply_kb,
                    )
                except Exception as e:
                    print(
                        f"Inquiry Notify Error ({admin_id}):",
                        repr(e), flush=True,
                    )
        except Exception as e:
            print("Inquiry Notify Error:", repr(e), flush=True)

        inc_product_counter(pid, "inquiries_count")
        inc_user_inquiries(u.id)
        log_action(
            u.id, "USER_INQUIRY",
            object_type="product", object_id=pid,
            new_value=p.get("name"),
        )

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=(
                "✅ تم إرسال طلب الاستعلام.\n"
                "هيتم التواصل معاك في أقرب وقت."
            ),
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
        track_user(update)

        # Sent as a brand-new message (not an edit of the menu the
        # customer tapped) so the price stays visible as its own
        # message in the chat history.
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=price_text(p) if p
            else "💎 لم يتم تحديث أسعار الذهب حتى الآن.",
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return

    if c == "notifsub":
        track_user(update)
        set_gold_subscription(update.effective_user.id, True)

        wa_subscribed = is_whatsapp_subscribed(update.effective_user.id)

        if wa_subscribed:
            await q.edit_message_text(
                "💎 مجوهرات الحسيني\n\n"
                "✅ تم تفعيل الإشعارات، هيوصلك تلقائي أي منتج جديد "
                "أو تغيير في سعر الذهب على تليجرام وواتساب.\n\n"
                "اختار من القائمة 👇",
                reply_markup=home(is_admin(update), True),
            )
            return

        await q.edit_message_text(
            "✅ تم تفعيل الإشعارات على تليجرام.\n\n"
            "عايز تستقبلها على واتساب كمان؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📱 أضف رقم واتساب", callback_data="notifwa"
                )],
                [InlineKeyboardButton(
                    "⏭ لأ، تليجرام بس", callback_data="home"
                )],
            ]),
        )
        return

    if c == "notifwa":
        track_user(update)
        context.user_data.clear()
        context.user_data.update(state="wa_phone_input", wa_return="home")

        await q.edit_message_text(
            "📱 اكتب رقم واتساب بتاعك عشان تستقبل الإشعارات عليه.\n\n"
            "مثال: 201012345678 (بالكود الدولي 20، من غير علامة +)"
        )
        return

    if c == "notifunsub":
        track_user(update)
        set_gold_subscription(update.effective_user.id, False)
        unsubscribe_whatsapp(update.effective_user.id)

        await q.edit_message_text(
            "💎 مجوهرات الحسيني\n\n"
            "🔕 تم إيقاف الإشعارات (تليجرام وواتساب).\n\n"
            "اختار من القائمة 👇",
            reply_markup=home(is_admin(update), False),
        )
        return

    if c.startswith("reply:"):
        if not is_admin(update):
            return

        target_id = int(c.split(":")[1])
        context.user_data.clear()
        context.user_data.update(state="admin_reply", reply_to=target_id)

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="💬 اكتب ردك على العميل، وهيتبعت له فورًا.",
        )
        return

    if c == "goldwsub":
        track_user(update)
        context.user_data.clear()
        context.user_data["state"] = "wa_phone_input"

        await q.edit_message_text(
            "📱 اكتب رقم واتساب بتاعك عشان تستقبل تحديثات السعر.\n\n"
            "مثال: 201012345678 (بالكود الدولي 20، من غير علامة +)"
        )
        return

    if c == "goldwunsub":
        track_user(update)
        unsubscribe_whatsapp(update.effective_user.id)

        p = latest()
        await q.edit_message_text(
            "🔕 تم إلغاء الاشتراك من تحديثات واتساب.\n\n"
            + (price_text(p) if p else ""),
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return
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
                reply_markup=home(True, is_gold_subscribed(update.effective_user.id)),
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
            prev_p = latest()
            save_latest(p, admin_id=update.effective_user.id)

            if context.user_data.get("first"):
                save_first(p)

            await maybe_send_gold_alert(context, prev_p, p)
            await broadcast_gold_update(context, p)
            await broadcast_gold_update_whatsapp(context, p)

        log_publish(
            "telegram", status="success" if tg_ok else "failed",
            content=txt,
        ) if c in ("pub_both", "pub_tg") else None
        log_publish(
            "facebook",
            post_id=(fb_result or {}).get("post_id"),
            permalink=(fb_result or {}).get("permalink"),
            status="success" if fb_ok else "failed",
            error=None if fb_ok else (fb_result or {}).get("message"),
            content=txt,
        ) if c in ("pub_both", "pub_fb") else None

        context.user_data.clear()

        if c == "pub_fb":
            await q.edit_message_text(
                fb_result.get(
                    "message",
                    "❌ فشل النشر على Facebook."
                ) if fb_result
                else "❌ لم يتم تنفيذ النشر على Facebook.",
                reply_markup=home(True, is_gold_subscribed(update.effective_user.id)),
            )
            return

        if c == "pub_tg":
            await q.edit_message_text(
                "✅ تم النشر في تليجرام."
                if tg_ok
                else "❌ فشل النشر في تليجرام.",
                reply_markup=home(True, is_gold_subscribed(update.effective_user.id)),
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
            reply_markup=home(True, is_gold_subscribed(update.effective_user.id)),
        )
        return

    # =====================================================
    # NEW POST PUBLISH (general text/photo post)
    # =====================================================
    if c in ("npub_all", "npub_both", "npub_tg", "npub_fb", "npub_ig"):
        if not is_admin(update):
            return

        txt = context.user_data.get("post_text") or ""
        photo_id = context.user_data.get("post_photo")

        if not txt and not photo_id:
            await q.edit_message_text(
                "❌ المنشور غير موجود، ابدأ من جديد.",
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        want_tg = c in ("npub_all", "npub_both", "npub_tg")
        want_fb = c in ("npub_all", "npub_both", "npub_fb")
        want_ig = c in ("npub_all", "npub_ig")

        tg_ok = False
        fb_result = None
        ig_result = None

        photo_url = None
        if photo_id and (want_fb or want_ig):
            try:
                f = await context.bot.get_file(photo_id)
                photo_url = (
                    f.file_path if f.file_path.startswith("http")
                    else f"https://api.telegram.org/file/bot"
                         f"{BOT_TOKEN}/{f.file_path}"
                )
            except Exception as e:
                print("Get File Error:", repr(e), flush=True)

        if want_tg:
            tg_ok = await tg_post(context, txt, photo_id)

        if want_fb:
            if photo_id:
                fb_result = (
                    await facebook_photo(txt, photo_url)
                    if photo_url
                    else {
                        "ok": False,
                        "message": "❌ فشل تجهيز الصورة للنشر على Facebook.",
                    }
                )
            else:
                fb_result = await facebook(txt)

        if want_ig:
            if not photo_id:
                ig_result = {
                    "ok": False,
                    "message": "❌ Instagram محتاج صورة، مينفعش نص بس.",
                }
            elif not photo_url:
                ig_result = {
                    "ok": False,
                    "message": "❌ فشل تجهيز الصورة للنشر على Instagram.",
                }
            else:
                ig_result = await instagram_photo(txt, photo_url)

        fb_ok = bool(fb_result and fb_result.get("ok"))
        ig_ok = bool(ig_result and ig_result.get("ok"))

        context.user_data.clear()

        # Single-platform selections: show that platform's own message
        if c == "npub_fb":
            lines = [fb_result.get("message", "❌ فشل النشر على Facebook.")]
            if fb_ok and "story_message" in fb_result:
                lines.append(fb_result["story_message"])
            await q.edit_message_text(
                "\n".join(lines),
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        if c == "npub_tg":
            await q.edit_message_text(
                "✅ تم النشر في تليجرام."
                if tg_ok
                else "❌ فشل النشر في تليجرام.",
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        if c == "npub_ig":
            lines = [ig_result.get("message", "❌ فشل النشر على Instagram.")]
            if ig_ok and "story_message" in ig_result:
                lines.append(ig_result["story_message"])
            await q.edit_message_text(
                "\n".join(lines),
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        # Multi-platform selections: summary report
        result_lines = []

        if want_tg:
            result_lines.append(
                "✅ Telegram: تم النشر." if tg_ok
                else "❌ Telegram: فشل النشر."
            )

        if want_fb:
            result_lines.append(
                "✅ Facebook: تم النشر." if fb_ok
                else "❌ Facebook: " + (
                    fb_result.get("message", "فشل النشر.")
                    if fb_result else "لم يتم التنفيذ."
                )
            )
            if fb_ok and fb_result and "story_message" in fb_result:
                result_lines.append("   " + fb_result["story_message"])

        if want_ig:
            result_lines.append(
                "✅ Instagram: تم النشر." if ig_ok
                else "❌ Instagram: " + (
                    ig_result.get("message", "فشل النشر.")
                    if ig_result else "لم يتم التنفيذ."
                )
            )
            if ig_ok and ig_result and "story_message" in ig_result:
                result_lines.append("   " + ig_result["story_message"])

        await q.edit_message_text(
            "\n".join(result_lines),
            reply_markup=admin_menu(owner=is_owner(update)),
        )
        return


# =========================================================
# ERROR
# =========================================================

async def error(update, context):
    print("=" * 60, flush=True)
    print("BOT ERROR:", repr(context.error), flush=True)
    print("=" * 60, flush=True)

    admin_id_hint = None
    try:
        if isinstance(update, Update) and update.effective_user:
            admin_id_hint = update.effective_user.id
    except Exception:
        pass

    log_action(
        admin_id_hint or ADMIN_ID or None,
        "BOT_ERROR",
        status="failed",
        error=repr(context.error),
    )

    # Never leave the user stuck mid-conversation because of a crash.
    try:
        if context.user_data is not None:
            context.user_data.clear()
    except Exception:
        pass

    # Best-effort friendly message to whoever triggered the error.
    try:
        if isinstance(update, Update) and update.effective_chat:
            is_the_admin = (
                update.effective_user
                and update.effective_user.id == ADMIN_ID
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "❌ حصل خطأ غير متوقع، جرب تاني.\n"
                    "استخدم /start للرجوع للقائمة الرئيسية."
                    if not is_the_admin else
                    "❌ حصل خطأ غير متوقع.\n\n"
                    f"التفاصيل: {repr(context.error)[:300]}\n\n"
                    "استخدم /start للرجوع للقائمة الرئيسية."
                ),
            )
    except Exception as e:
        print("Error Notify Failed:", repr(e), flush=True)


# =========================================================
# MAIN
# =========================================================

async def setup_bot_commands(app):
    """Registers the persistent command menu (the '/' button next to
    the message box) so /start is always one tap away, even after the
    person closes and reopens the chat."""
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "🏠 القائمة الرئيسية"),
        ])
    except Exception as e:
        print("Set Commands Error:", repr(e), flush=True)


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
        .post_init(setup_bot_commands)
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

    if app.job_queue is not None:
        app.job_queue.run_repeating(
            auto_post_tick, interval=60, first=10, name="auto_post_tick"
        )
        print("Auto-posting scheduler started (checks every 60s).", flush=True)
    else:
        print(
            "WARNING: JobQueue unavailable (install "
            "python-telegram-bot[job-queue]) — auto-posting disabled, "
            "everything else works normally.",
            flush=True,
        )

    print("Alhussieny Gold Bot Started...", flush=True)
    print(f"READY VERSION: {VERSION}", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
