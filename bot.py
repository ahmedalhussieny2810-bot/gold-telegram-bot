import os
import json
import re
import asyncio
from datetime import datetime, timedelta, date, time as dtime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, quote

import requests
import pymysql
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
    BotCommandScopeChat, BotCommandScopeDefault,
)
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
VERSION = "ALHUSSIENY_SHOP_SYSTEM_2026_08_13_V48"

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

# =========================================================
# SHOP IDENTITY — all configurable via Railway env vars, so a new
# client's shop can be deployed by copying this same file and
# setting different env vars (no code edits needed per shop).
# Defaults keep this exact deployment (مجوهرات الحسيني) working
# unchanged even if these vars are never set.
# =========================================================
SHOP_NAME = os.getenv("SHOP_NAME", "مجوهرات الحسيني").strip()
SHOP_LOCATION = os.getenv("SHOP_LOCATION", "بورسعيد").strip()
SHOP_FULL_NAME = f"{SHOP_NAME} - {SHOP_LOCATION}" if SHOP_LOCATION else SHOP_NAME

WEBSITE = os.getenv(
    "SHOP_WEBSITE", "https://link.gettap.co/alhussienyjewelry"
).strip()
TG_CHANNEL = os.getenv(
    "SHOP_TG_CHANNEL", "https://t.me/alhussienyjewelry"
).strip()
FACEBOOK = os.getenv(
    "SHOP_FACEBOOK", "https://www.facebook.com/alhussienyjewelry"
).strip()
INSTAGRAM = os.getenv(
    "SHOP_INSTAGRAM", "https://www.instagram.com/alhussienyjewelry"
).strip()
MAPS = os.getenv(
    "SHOP_MAPS", "https://maps.app.goo.gl/1X6NJrNM4u1azpFR6"
).strip()
PHONE = os.getenv("SHOP_PHONE", "01067365567").strip()
WHATSAPP = f"https://wa.me/{os.getenv('SHOP_WHATSAPP_NUMBER', '201067365567').strip()}"
SHOP_ADDRESS = os.getenv(
    "SHOP_ADDRESS", "بورسعيد - شارع أسوان أمام صيدلية جلال"
).strip()

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


def _safe_alter(x, q):
    """Runs a schema-migration ALTER TABLE statement (e.g. ADD COLUMN)
    on startup. These run on every restart, so once a column already
    exists, MySQL raises error 1060 (Duplicate column name) — that's
    expected and gets ignored silently. Any OTHER error (bad
    connection, typo, wrong type, etc.) is a real problem, so it gets
    printed to the logs instead of vanishing silently like before —
    a startup that "succeeds" while quietly missing a column is
    worse than one that logs a clear warning about it.
    """
    try:
        x.execute(q)
    except Exception as e:
        code = e.args[0] if getattr(e, "args", None) else None
        if code != 1060:
            print(f"DB Migration Warning: {q[:60]}... -> {repr(e)}", flush=True)


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
                "ALTER TABLE Users ADD COLUMN last_calc_mode "
                "VARCHAR(20) NULL",
                "ALTER TABLE Users ADD COLUMN last_calc_karat "
                "TINYINT UNSIGNED NULL",
                "ALTER TABLE Users ADD COLUMN last_calc_weight "
                "DECIMAL(10,2) NULL",
                "ALTER TABLE Users ADD COLUMN referred_by "
                "BIGINT NULL",
            ):
                _safe_alter(x, q)

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
                CREATE TABLE IF NOT EXISTS GoldBroadcastMessages(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    price_id BIGINT UNSIGNED NOT NULL,
                    telegram_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(price_id)
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
                CREATE TABLE IF NOT EXISTS SavedNotifications(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    admin_id BIGINT NULL,
                    title VARCHAR(100) NOT NULL,
                    body TEXT NULL,
                    photo_id VARCHAR(255) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS ScheduledNotifications(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    time_str VARCHAR(5) NOT NULL,
                    label VARCHAR(50) NULL,
                    body TEXT NOT NULL,
                    enabled TINYINT(1) NOT NULL DEFAULT 1,
                    last_run_date DATE NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS OccasionReminders(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    label VARCHAR(100) NOT NULL,
                    month TINYINT UNSIGNED NOT NULL,
                    day TINYINT UNSIGNED NOT NULL,
                    last_reminded_year SMALLINT UNSIGNED NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(month, day)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS Investments(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    weight DECIMAL(10,3) NOT NULL,
                    karat TINYINT UNSIGNED NOT NULL,
                    buy_price_per_gram DECIMAL(15,2) NOT NULL,
                    buy_date DATE NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(telegram_id)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS Birthdays(
                    telegram_id BIGINT PRIMARY KEY,
                    month TINYINT UNSIGNED NOT NULL,
                    day TINYINT UNSIGNED NOT NULL,
                    last_wished_year SMALLINT UNSIGNED NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(month, day)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS Favorites(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    product_id BIGINT UNSIGNED NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_fav(telegram_id, product_id),
                    INDEX(telegram_id)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS MonthlyBudget(
                    telegram_id BIGINT PRIMARY KEY,
                    salary DECIMAL(15,2) NOT NULL,
                    month_str VARCHAR(7) NOT NULL,
                    balance DECIMAL(15,2) NOT NULL,
                    last_summary_month VARCHAR(7) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS BudgetTransactions(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    amount DECIMAL(15,2) NOT NULL,
                    ttype ENUM('in','out') NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(telegram_id, created_at)
                )
            """)

            x.execute("""
                CREATE TABLE IF NOT EXISTS LedgerCustomers(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    phone VARCHAR(30) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(telegram_id)
                )
            """)

            for q in (
                "ALTER TABLE LedgerCustomers ADD COLUMN telegram_id "
                "BIGINT NOT NULL DEFAULT 0",
            ):
                _safe_alter(x, q)

            x.execute("""
                CREATE TABLE IF NOT EXISTS LedgerEntries(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    customer_id BIGINT UNSIGNED NOT NULL,
                    amount DECIMAL(15,2) NOT NULL,
                    direction ENUM('lah','alaih') NOT NULL,
                    note VARCHAR(255) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX(customer_id, created_at)
                )
            """)

            x.execute(
                "SELECT id FROM ScheduledNotifications WHERE label=%s",
                ("fajr",),
            )
            if not x.fetchone():
                x.execute("""
                    INSERT INTO ScheduledNotifications
                    (time_str,label,body,enabled)
                    VALUES(%s,%s,%s,1)
                """, (
                    "04:55", "fajr",
                    "🌅 حان الآن موعد آذان الفجر\n\n"
                    "اللهم لك الحمد أنت نور السماوات والأرض، اللهم بلغنا "
                    "هذا اليوم على خير، وارزقنا فيه صلاة خاشعة وقلبًا "
                    "سليمًا ورزقًا حلالًا طيبًا.\n\n"
                    "🤲 صلاة مقبولة ويوم مبارك عليكم جميعًا\n"
                    f"من أسرة {SHOP_NAME} ❤️",
                ))

            x.execute("""
                CREATE TABLE IF NOT EXISTS CallRequests(
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    name VARCHAR(255) NULL,
                    phone VARCHAR(30) NOT NULL,
                    status ENUM('pending','done') NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    done_at TIMESTAMP NULL,
                    INDEX(status, created_at)
                )
            """)

            for q in (
                "ALTER TABLE CallRequests ADD COLUMN rating "
                "TINYINT UNSIGNED NULL",
            ):
                _safe_alter(x, q)

            x.execute("""
                CREATE TABLE IF NOT EXISTS SavingsGoals(
                    telegram_id BIGINT PRIMARY KEY,
                    weight DECIMAL(10,3) NOT NULL,
                    karat TINYINT UNSIGNED NOT NULL,
                    months INT UNSIGNED NOT NULL,
                    target_amount DECIMAL(15,2) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_reminded_month VARCHAR(7) NULL
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
            ORDER BY id
        """)

    return many("""
        SELECT c.id,c.name,COUNT(p.id) product_count
        FROM Categories c
        LEFT JOIN Products p ON p.category_id=c.id
        WHERE c.parent_id=%s
        GROUP BY c.id,c.name
        ORDER BY
            CASE WHEN c.name='سبائك' THEN 0
                 WHEN c.name='عملات' THEN 1
                 ELSE 2 END,
            c.id ASC
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

ZAKAT_NISAB_GRAMS_24K = 85  # nisab threshold, in 24k-equivalent grams
ZAKAT_RATE = 0.025  # 2.5%
ZAKAT_DISCLAIMER = (
    "⚠️ الحساب ده تقديري بسعر النهاردة، وبيفترض إن الذهب فاضل عندك "
    "حول (سنة هجرية) كامل وإنه فايض عن حاجتك الأساسية. فيه خلاف "
    "فقهي حول زكاة الذهب المستخدم كحلي شخصي (زينة)، فالأحوط الرجوع "
    "لجهة دينية موثوقة زي دار الإفتاء لتفصيل حالتك بالظبط."
)

GOLD_CARE_TIPS = [
    "💡 نصيحة اليوم: احفظي الدهب في علبة لوحده، عشان الاحتكاك مع "
    "قطع تانية بيخدشه بمرور الوقت.",
    "💡 نصيحة اليوم: شيلي الدهب قبل ما تستحمي أو تسبحي، لأن الكلور "
    "والصابون بيضعفوا لمعانه على المدى الطويل.",
    "💡 نصيحة اليوم: نضفي دهبك بفرشة أسنان ناعمة ومية دافية وصابون "
    "خفيف، وجففيه كويس قبل ما ترجعيه للعلبة.",
    "💡 نصيحة اليوم: عيار 21 أعلى نقاء من عيار 18، لكن عيار 18 أكتر "
    "متانة في الاستخدام اليومي لأنه مخلوط بمعادن أقوى.",
    "💡 نصيحة اليوم: ابعدي عطرك وكريماتك عن الدهب مباشرة، وحطي "
    "الإكسسوار بعد ما العطر يجف تمامًا.",
    "💡 نصيحة اليوم: افحصي أقفال السلاسل والحلق بتاعتك بين كل فترة "
    "والتانية، عشان تلاحظي أي ضعف قبل ما تفقدي القطعة.",
    "💡 نصيحة اليوم: احتفظي بفاتورة الشراء دايمًا — بتسهل عليكي "
    "أي استبدال أو ضمان في المستقبل.",
    "💡 نصيحة اليوم: الدهب الأصفر بيتحمل الاستخدام اليومي أكتر من "
    "الدهب الأبيض، لأن طلاء الروديوم في الأبيض ممكن يخف مع الوقت.",
    "💡 نصيحة اليوم: لما تشتري قطعة جديدة، افحصي الدمغة (الختم) "
    "اللي بتوضح العيار قبل ما تدفعي — كل قطعة أصلية لازم يكون "
    "عليها.",
    "💡 نصيحة اليوم: متلبسيش أكتر من قطعة دهب في نفس المكان (زي 3 "
    "خواتم في إيد واحدة) عشان تقلّلي الاحتكاك اللي بيخدش السطح.",
    "💡 نصيحة اليوم: لو الدهب بدأ يفقد لمعانه، مبتستخدميش معجون "
    "أسنان أو مواد كاشطة — ده بيخدش السطح مش بينضفه.",
]

# Business hours: every day except Friday 11:30 AM -> 12:30 AM (next day).
# Friday: 1:00 PM -> 12:30 AM (next day). weekday(): Monday=0 ... Friday=4.
SHOP_CLOSE_TIME = dtime(0, 30)
SHOP_OPEN_TIME_FRIDAY = dtime(13, 0)
SHOP_OPEN_TIME_OTHER = dtime(11, 30)


def shop_hours_window(d):
    """Returns (open_dt, close_dt) for the business day starting on date d."""
    open_time = (
        SHOP_OPEN_TIME_FRIDAY if d.weekday() == 4 else SHOP_OPEN_TIME_OTHER
    )
    open_dt = datetime.combine(d, open_time, tzinfo=TZ)
    close_dt = datetime.combine(d + timedelta(days=1), SHOP_CLOSE_TIME, tzinfo=TZ)
    return open_dt, close_dt


def shop_open_status():
    """Returns dict: is_open, next_change (datetime), today's window text."""
    now = datetime.now(TZ)
    today = now.date()

    for d in (today - timedelta(days=1), today):
        open_dt, close_dt = shop_hours_window(d)
        if open_dt <= now <= close_dt:
            return {
                "is_open": True,
                "next_change": close_dt,
                "open_dt": open_dt,
                "close_dt": close_dt,
            }

    # closed now -> next opening is today's window (if before it starts)
    open_dt, close_dt = shop_hours_window(today)
    if now < open_dt:
        next_change = open_dt
    else:
        open_dt2, _ = shop_hours_window(today + timedelta(days=1))
        next_change = open_dt2

    return {
        "is_open": False,
        "next_change": next_change,
        "open_dt": open_dt,
        "close_dt": close_dt,
    }


def fmt_hm(dt):
    h = dt.hour % 12
    if h == 0:
        h = 12
    period = "ص" if dt.hour < 12 else "م"
    return f"{h}:{dt.minute:02d} {period}"


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

def track_user(update, referred_by=None):
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
                         total_interactions,referred_by)
                        VALUES(%s,%s,%s,%s,1,%s)
                    """, (
                        u.id, u.first_name, u.last_name, u.username,
                        referred_by,
                    ))
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


def all_user_ids():
    rows = many("SELECT telegram_id FROM Users")
    return [r["telegram_id"] for r in rows]


def gold_subscriber_count():
    row = one(
        "SELECT COUNT(*) c FROM Users WHERE subscribed_gold=1"
    )
    return (row or {}).get("c", 0)


def referral_leaderboard(limit=20):
    return many("""
        SELECT u.telegram_id, u.first_name, u.username,
               COUNT(r.telegram_id) AS cnt
        FROM Users u
        JOIN Users r ON r.referred_by = u.telegram_id
        GROUP BY u.telegram_id, u.first_name, u.username
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,))


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


def save_last_calc(telegram_id, mode, karat, weight):
    """Remembers the customer's last "احسب دهبك" choice so next time
    they open the calculator we can offer a one-tap repeat instead of
    making them pick buy/sell → karat → type the weight again."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                UPDATE Users
                SET last_calc_mode=%s, last_calc_karat=%s,
                    last_calc_weight=%s
                WHERE telegram_id=%s
            """, (mode, karat, weight, telegram_id))
    finally:
        c.close()


def get_last_calc(telegram_id):
    row = one(
        "SELECT last_calc_mode, last_calc_karat, last_calc_weight "
        "FROM Users WHERE telegram_id=%s",
        (telegram_id,),
    )
    if not row or not row.get("last_calc_mode"):
        return None
    return row


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


def whatsapp_notifications_enabled():
    """
    Admin kill-switch for the WhatsApp subscription flow (separate
    from the wa_slot_* scheduling logic). Defaults to OFF ("0") so a
    fresh deploy never lets customers subscribe to a channel that
    isn't approved by Meta yet — the admin turns it on explicitly
    with the "🟢 تفعيل" button once WhatsApp is live.
    """
    return get_setting("wa_notifications_enabled", "0") == "1"


def sell_discount_per_gram(karat):
    """
    How much per gram (in EGP) the shop deducts from the live gold
    price when quoting what it would PAY the customer to buy their
    gold jewelry back — as opposed to what the customer pays the
    shop, which is the live price with no deduction. Tracked
    separately per karat (21 vs 18) since the margin isn't
    necessarily the same for both, and is admin-configurable (not a
    hardcoded constant) because it shifts with the market and isn't
    the same shop-to-shop. Doesn't apply to 24k bullion or 21k
    coins, which are bought back at the plain per-gram price.
    """
    try:
        return int(get_setting(f"sell_discount_{karat}", "100"))
    except (TypeError, ValueError):
        return 100


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
                return x.lastrowid
        finally:
            c.close()
    except Exception as e:
        print("Gold History Log Error:", repr(e), flush=True)
        return None


def gold_history_range(start_dt, end_dt):
    return many("""
        SELECT price_21,price_24,price_18,admin_id,created_at
        FROM GoldPriceHistory
        WHERE created_at BETWEEN %s AND %s
        ORDER BY created_at ASC
    """, (start_dt, end_dt))


def recent_gold_prices(limit=15):
    return many("""
        SELECT id,price_21,price_24,price_18,created_at
        FROM GoldPriceHistory
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,))


def get_gold_price_entry(pid):
    return one(
        "SELECT id,price_21,price_24,price_18,created_at "
        "FROM GoldPriceHistory WHERE id=%s",
        (pid,),
    )


def delete_gold_price_entry(pid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("DELETE FROM GoldPriceHistory WHERE id=%s", (pid,))
            return bool(x.rowcount)
    finally:
        c.close()


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


def maintenance_mode_on():
    return get_setting("maintenance_mode", "0") == "1"


def try_claim_daily_task(key, value):
    """Atomically claims a one-per-day (or one-per-period) scheduled
    task stored as a Settings flag. Only the first caller to write a
    NEW value for `key` gets True back — a second overlapping process
    (e.g. two instances briefly alive during a Railway restart)
    trying to claim the same key+value gets False and skips sending,
    closing the duplicate-send race that a plain get/set check-then-
    write pattern doesn't."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO Settings(setting_key, setting_value)
                VALUES(%s, %s)
                ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
            """, (key, value))
            # MySQL: 1 row affected = fresh insert, 2 = value actually
            # changed, 0 = value was already this exact value (lost
            # the race to an earlier claim).
            return x.rowcount > 0
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

BOT_LINK = os.getenv("BOT_LINK", "https://t.me/Aalhussieny_bot").strip()


def build_share_text(body):
    """Wraps a calculator result with a shop signature + bot link,
    so when a customer forwards it (e.g. on WhatsApp) whoever
    receives it can try the bot themselves."""
    return (
        body
        + f"\n\n💎 {SHOP_NAME}\n"
        + f"🤖 جرب بنفسك: {BOT_LINK}"
    )

TEMPLATES = {
    "normal": {
        "name": "قالب أسعار عادي",
        "body": (
            "💎 أسعار الذهب الآن\n\n"
            "🟡 عيار 24 : {price_24}\n"
            "🟡 عيار 21 : {price_21}\n"
            "🟡 عيار 18 : {price_18}\n\n"
            "📍 {shop_name}\n"
            "🤖 {bot_link}\n\n"
            "🌐 {website}"
        ),
    },
    "luxury": {
        "name": "قالب فاخر",
        "body": (
            "✨💍 " + SHOP_NAME + " — أسعار الذهب ✨\n\n"
            "📅 {date} — 🕐 {time}\n\n"
            "🟡 عيار 24 : {price_24} جنيه\n"
            "🟡 عيار 21 : {price_21} جنيه\n"
            "🟡 عيار 18 : {price_18} جنيه\n\n"
            "💫 جمال يدوم... يليق بك\n"
            "📍 {shop_name}\n"
            "🤖 {bot_link}\n"
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
            "🤖 {bot_link}\n"
            "🌐 الموقع: {website}\n"
            "💬 واتساب: {whatsapp}\n"
            "📍 الموقع على الخريطة: {maps}"
        ),
    },
    "offer": {
        "name": "قالب عروض",
        "body": (
            "🔥 عرض خاص اليوم في " + SHOP_NAME + " 🔥\n\n"
            "💎 أسعار الذهب:\n"
            "🟡 عيار 24 : {price_24}\n"
            "🟡 عيار 21 : {price_21}\n"
            "🟡 عيار 18 : {price_18}\n\n"
            "زورونا اليوم في {shop_name}\n"
            "🤖 {bot_link}\n"
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
        shop_name=SHOP_FULL_NAME,
        website=WEBSITE,
        whatsapp=WHATSAPP,
        maps=MAPS,
        bot_link=BOT_LINK,
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
    """Atomic claim: only updates (and returns True) if last_run_date
    isn't already date_str, so two overlapping processes can't both
    "win" and send the same scheduled post twice."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledPosts SET last_run_date=%s "
                "WHERE id=%s AND (last_run_date IS NULL OR last_run_date<>%s)",
                (date_str, sid, date_str),
            )
            return x.rowcount > 0
    finally:
        c.close()


# =========================================================
# SCHEDULED CUSTOM NOTIFICATIONS (daily, sent to subscribers)
# =========================================================
# Separate from ScheduledPosts (which posts the gold-price template
# to Telegram/Facebook). These are free-text messages — e.g. Fajr,
# opening, closing greetings — written once and auto-sent every day
# at a fixed time to everyone subscribed to notifications.

def scheduled_notifications():
    return many(
        "SELECT * FROM ScheduledNotifications ORDER BY time_str ASC"
    )


def scheduled_notification(nid):
    return one(
        "SELECT * FROM ScheduledNotifications WHERE id=%s", (nid,)
    )


def add_scheduled_notification(time_str, body, label=None):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO ScheduledNotifications(time_str,body,label)
                VALUES(%s,%s,%s)
            """, (time_str, body, label))
            return x.lastrowid
    finally:
        c.close()


def delete_scheduled_notification(nid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM ScheduledNotifications WHERE id=%s", (nid,)
            )
            return bool(x.rowcount)
    finally:
        c.close()


def toggle_scheduled_notification(nid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledNotifications SET enabled=1-enabled "
                "WHERE id=%s",
                (nid,),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def mark_scheduled_notification_ran(nid, date_str):
    """Atomic claim — see mark_scheduled_post_ran."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE ScheduledNotifications SET last_run_date=%s "
                "WHERE id=%s AND (last_run_date IS NULL OR last_run_date<>%s)",
                (date_str, nid, date_str),
            )
            return x.rowcount > 0
    finally:
        c.close()


# =========================================================
# OCCASION REMINDERS (customer-facing, e.g. birthdays)
# =========================================================
# A customer registers a recurring yearly occasion (month/day only —
# no year, since it repeats). Once a day the tick job checks whether
# today is exactly 7 days before any occasion and, if so, DMs that
# customer a reminder — once per occasion per year.

def add_occasion_reminder(telegram_id, label, month, day):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO OccasionReminders(telegram_id,label,month,day)
                VALUES(%s,%s,%s,%s)
            """, (telegram_id, label, month, day))
            return x.lastrowid
    finally:
        c.close()


def all_occasion_reminders():
    return many("SELECT * FROM OccasionReminders")


def mark_occasion_reminded(rid, year):
    """Atomic claim — see mark_scheduled_post_ran."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE OccasionReminders SET last_reminded_year=%s "
                "WHERE id=%s AND (last_reminded_year IS NULL "
                "OR last_reminded_year<>%s)",
                (year, rid, year),
            )
            return x.rowcount > 0
    finally:
        c.close()


def get_occasion_reminder(rid):
    return one("SELECT * FROM OccasionReminders WHERE id=%s", (rid,))


def update_occasion_reminder_date(rid, month, day):
    """Changes when a reminder next fires (used when the customer
    picks a new date after the first reminder went off), and clears
    last_reminded_year so the tick logic re-evaluates it fresh
    against the new date instead of thinking it already fired."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE OccasionReminders "
                "SET month=%s, day=%s, last_reminded_year=NULL "
                "WHERE id=%s",
                (month, day, rid),
            )
    finally:
        c.close()


def delete_occasion_reminder(rid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("DELETE FROM OccasionReminders WHERE id=%s", (rid,))
            return bool(x.rowcount)
    finally:
        c.close()


# =========================================================
# INVESTMENT TRACKING
# =========================================================

def add_investment(telegram_id, weight, karat, buy_price_per_gram, buy_date):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO Investments
                (telegram_id,weight,karat,buy_price_per_gram,buy_date)
                VALUES(%s,%s,%s,%s,%s)
            """, (telegram_id, weight, karat, buy_price_per_gram, buy_date))
    finally:
        c.close()


def list_investments(telegram_id):
    return many("""
        SELECT id,weight,karat,buy_price_per_gram,buy_date,created_at
        FROM Investments
        WHERE telegram_id=%s
        ORDER BY created_at DESC
    """, (telegram_id,))


def get_investment(iid):
    return one(
        "SELECT id,telegram_id,weight,karat,buy_price_per_gram,buy_date "
        "FROM Investments WHERE id=%s",
        (iid,),
    )


def delete_investment(iid, telegram_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM Investments WHERE id=%s AND telegram_id=%s",
                (iid, telegram_id),
            )
            return bool(x.rowcount)
    finally:
        c.close()


# =========================================================
# BIRTHDAYS
# =========================================================

def set_birthday(telegram_id, month, day):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO Birthdays(telegram_id,month,day)
                VALUES(%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    month=VALUES(month), day=VALUES(day),
                    last_wished_year=NULL
            """, (telegram_id, month, day))
    finally:
        c.close()


def get_birthday(telegram_id):
    return one(
        "SELECT * FROM Birthdays WHERE telegram_id=%s", (telegram_id,)
    )


def all_birthdays():
    return many("SELECT * FROM Birthdays")


def mark_birthday_wished(telegram_id, year):
    """Atomic claim — see mark_scheduled_post_ran."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE Birthdays SET last_wished_year=%s "
                "WHERE telegram_id=%s AND (last_wished_year IS NULL "
                "OR last_wished_year<>%s)",
                (year, telegram_id, year),
            )
            return x.rowcount > 0
    finally:
        c.close()


def delete_birthday(telegram_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM Birthdays WHERE telegram_id=%s", (telegram_id,)
            )
            return bool(x.rowcount)
    finally:
        c.close()


# =========================================================
# FAVORITES (customer wishlist)
# =========================================================

def is_favorite(telegram_id, product_id):
    return bool(one(
        "SELECT id FROM Favorites WHERE telegram_id=%s AND product_id=%s",
        (telegram_id, product_id),
    ))


def add_favorite(telegram_id, product_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT IGNORE INTO Favorites(telegram_id, product_id)
                VALUES(%s, %s)
            """, (telegram_id, product_id))
    finally:
        c.close()


def remove_favorite(telegram_id, product_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM Favorites WHERE telegram_id=%s "
                "AND product_id=%s",
                (telegram_id, product_id),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def list_favorites(telegram_id):
    return many("""
        SELECT p.*
        FROM Favorites f
        JOIN Products p ON p.id = f.product_id
        WHERE f.telegram_id=%s
        ORDER BY f.created_at DESC
    """, (telegram_id,))


# =========================================================
# MONTHLY BUDGET (مصروفك الشهري)
# =========================================================

def get_budget(telegram_id):
    return one(
        "SELECT * FROM MonthlyBudget WHERE telegram_id=%s", (telegram_id,)
    )


def start_budget_month(telegram_id, salary, month_str):
    """Sets/resets the budget cycle: new salary, new month, balance
    reset to the salary. Used both for first-time setup and for
    "غيّر المرتب" (which intentionally starts a fresh cycle)."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO MonthlyBudget
                (telegram_id, salary, month_str, balance,
                 last_summary_month)
                VALUES(%s, %s, %s, %s, NULL)
                ON DUPLICATE KEY UPDATE
                    salary=VALUES(salary), month_str=VALUES(month_str),
                    balance=VALUES(balance), last_summary_month=NULL
            """, (telegram_id, salary, month_str, salary))
    finally:
        c.close()


def apply_budget_transaction(telegram_id, amount, ttype):
    """Adjusts the running balance and logs the transaction. ttype is
    'in' (adds to balance) or 'out' (subtracts)."""
    c = db()
    try:
        with c.cursor() as x:
            op = "+" if ttype == "in" else "-"
            x.execute(f"""
                UPDATE MonthlyBudget
                SET balance = balance {op} %s
                WHERE telegram_id=%s
            """, (amount, telegram_id))
            x.execute("""
                INSERT INTO BudgetTransactions
                (telegram_id, amount, ttype)
                VALUES(%s, %s, %s)
            """, (telegram_id, amount, ttype))
    finally:
        c.close()


def list_budget_transactions(telegram_id, limit=10):
    return many("""
        SELECT amount, ttype, created_at
        FROM BudgetTransactions
        WHERE telegram_id=%s
        ORDER BY created_at DESC
        LIMIT %s
    """, (telegram_id, limit))


def all_active_budgets():
    return many("SELECT * FROM MonthlyBudget")


def mark_budget_summary_sent(telegram_id, month_str):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE MonthlyBudget SET last_summary_month=%s "
                "WHERE telegram_id=%s AND (last_summary_month IS NULL "
                "OR last_summary_month<>%s)",
                (month_str, telegram_id, month_str),
            )
            return x.rowcount > 0
    finally:
        c.close()


# =========================================================
# CUSTOMER LEDGER (دفتر حسابات العملاء — أدمن فقط)
# له = المحل مديون للعميل | عليه = العميل مديون للمحل
# =========================================================

def add_ledger_customer(telegram_id, name, phone=None):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "INSERT INTO LedgerCustomers(telegram_id, name, phone) "
                "VALUES(%s, %s, %s)",
                (telegram_id, name, phone),
            )
            return x.lastrowid
    finally:
        c.close()


def list_ledger_customers(telegram_id, search=None):
    if search:
        return many(
            "SELECT * FROM LedgerCustomers WHERE telegram_id=%s "
            "AND name LIKE %s ORDER BY name ASC",
            (telegram_id, f"%{search}%"),
        )
    return many(
        "SELECT * FROM LedgerCustomers WHERE telegram_id=%s "
        "ORDER BY name ASC",
        (telegram_id,),
    )


def get_ledger_customer(cid, telegram_id):
    return one(
        "SELECT * FROM LedgerCustomers WHERE id=%s AND telegram_id=%s",
        (cid, telegram_id),
    )


def delete_ledger_customer(cid, telegram_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM LedgerEntries WHERE customer_id=%s AND "
                "customer_id IN (SELECT id FROM LedgerCustomers WHERE "
                "id=%s AND telegram_id=%s)",
                (cid, cid, telegram_id),
            )
            x.execute(
                "DELETE FROM LedgerCustomers WHERE id=%s AND telegram_id=%s",
                (cid, telegram_id),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def add_ledger_entry(customer_id, amount, direction, note=None):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO LedgerEntries(customer_id, amount, direction, note)
                VALUES(%s, %s, %s, %s)
            """, (customer_id, amount, direction, note))
    finally:
        c.close()


def ledger_customer_balance(customer_id):
    row = one("""
        SELECT
            COALESCE(SUM(CASE WHEN direction='lah' THEN amount END), 0) AS lah,
            COALESCE(SUM(CASE WHEN direction='alaih' THEN amount END), 0) AS alaih
        FROM LedgerEntries
        WHERE customer_id=%s
    """, (customer_id,))
    lah = float(row["lah"]) if row else 0.0
    alaih = float(row["alaih"]) if row else 0.0
    return lah, alaih, alaih - lah


def list_ledger_entries(customer_id, limit=15):
    return many("""
        SELECT amount, direction, note, created_at
        FROM LedgerEntries
        WHERE customer_id=%s
        ORDER BY created_at DESC
        LIMIT %s
    """, (customer_id, limit))


# =========================================================
# CALL REQUESTS (customer requests a phone call, FIFO queue)
# =========================================================

def add_call_request(telegram_id, name, phone):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO CallRequests(telegram_id,name,phone)
                VALUES(%s,%s,%s)
            """, (telegram_id, name, phone))
            return x.lastrowid
    finally:
        c.close()


def pending_call_requests():
    return many(
        "SELECT * FROM CallRequests WHERE status='pending' "
        "ORDER BY created_at ASC"
    )


def pending_call_count_before(rid):
    row = one(
        "SELECT COUNT(*) AS n FROM CallRequests "
        "WHERE status='pending' AND created_at < "
        "(SELECT created_at FROM CallRequests WHERE id=%s)",
        (rid,),
    )
    return row["n"] if row else 0


def get_call_request(rid):
    return one("SELECT * FROM CallRequests WHERE id=%s", (rid,))


def mark_call_done(rid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE CallRequests SET status='done', "
                "done_at=CURRENT_TIMESTAMP WHERE id=%s",
                (rid,),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def set_call_rating(rid, rating):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE CallRequests SET rating=%s WHERE id=%s",
                (rating, rid),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def call_requests_this_week():
    return many(
        "SELECT * FROM CallRequests WHERE created_at >= "
        "DATE_SUB(NOW(), INTERVAL 7 DAY)"
    )


# =========================================================
# SAVINGS GOALS
# =========================================================

def set_savings_goal(telegram_id, weight, karat, months, target_amount):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO SavingsGoals
                (telegram_id,weight,karat,months,target_amount)
                VALUES(%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    weight=VALUES(weight), karat=VALUES(karat),
                    months=VALUES(months),
                    target_amount=VALUES(target_amount),
                    last_reminded_month=NULL
            """, (telegram_id, weight, karat, months, target_amount))
    finally:
        c.close()


def get_savings_goal(telegram_id):
    return one(
        "SELECT * FROM SavingsGoals WHERE telegram_id=%s", (telegram_id,)
    )


def all_savings_goals():
    return many("SELECT * FROM SavingsGoals")


def delete_savings_goal(telegram_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM SavingsGoals WHERE telegram_id=%s",
                (telegram_id,),
            )
            return bool(x.rowcount)
    finally:
        c.close()


def mark_savings_goal_reminded(telegram_id, month_str):
    """Atomic claim — see mark_scheduled_post_ran."""
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "UPDATE SavingsGoals SET last_reminded_month=%s "
                "WHERE telegram_id=%s AND (last_reminded_month IS NULL "
                "OR last_reminded_month<>%s)",
                (month_str, telegram_id, month_str),
            )
            return x.rowcount > 0
    finally:
        c.close()



# =========================================================
# SAVED (REUSABLE) NOTIFICATIONS
# =========================================================

def saved_notifications():
    return many(
        "SELECT id,title,body,photo_id FROM SavedNotifications "
        "ORDER BY id DESC"
    )


def get_saved_notification(nid):
    return one(
        "SELECT id,title,body,photo_id FROM SavedNotifications WHERE id=%s",
        (nid,),
    )


def add_saved_notification(admin_id, title, body, photo_id=None):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO SavedNotifications(admin_id,title,body,photo_id)
                VALUES(%s,%s,%s,%s)
            """, (admin_id, title.strip(), body, photo_id))
            return x.lastrowid
    finally:
        c.close()


def delete_saved_notification(nid):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("DELETE FROM SavedNotifications WHERE id=%s", (nid,))
            return bool(x.rowcount)
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


def compute_calc_result(mode, karat, weight):
    """
    Shared math + message-formatting for the "🧮 احسب دهبك" calculator
    (buy / sell jewelry / sell bullion). Returns (ok, text, total) so
    every entry point — typing a weight, repeating the last calc, or
    comparing two pieces — produces an identical result and message.
    """
    p21 = latest()
    if not p21:
        return False, "💎 لم يتم تحديث أسعار الذهب حتى الآن.", None

    p24, p21c, p18 = calc(p21)
    per_gram_map = {24: p24, 21: p21c, 18: p18}
    base = per_gram_map.get(karat)
    if base is None:
        return False, "❌ حصل خطأ، جرب تاني.", None

    extra_line = ""
    if mode == "sell":
        discount = sell_discount_per_gram(karat)
        per_gram = base - discount
        price_label = "سعر شراء الجرام"
        total_label = "الإجمالي"
        note = (
            f"⚠️ شامل خصم شراء المحل ({discount} جنيه/جرام). "
            "هذه النسبه متغيره من محل لمحل ومن توقيت لتوقيت اخر. "
            "السعر تقريبي وممكن يختلف بعد فحص القطعة في المحل."
        )
    elif mode == "sell_bullion":
        per_gram = base
        price_label = "سعر شراء الجرام"
        total_label = "الإجمالي"
        note = "⚠️ سعر السبيكة صافي، بدون أي خصم."
    else:  # "buy"
        per_gram = base
        price_label = "سعر الجرام"
        total_label = "الإجمالي"
        note = "⚠️ السعر ذهب صافي، مش شامل المصنعية."

    total = round(per_gram * weight)

    text = (
        "🧮 نتيجة الحساب\n\n"
        f"العيار: {karat}\n"
        f"الوزن: {weight} جرام\n"
        f"{price_label}: {round(per_gram)} جنيه\n\n"
        f"💰 {total_label}: {total} جنيه\n\n"
        + extra_line
        + note
    )
    return True, text, total, per_gram


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
    return record_gold_price(p21, p24, p18, admin_id)


def comparison(p):
    # Only show the vs-yesterday comparison line once a week, on
    # Mondays — not on every price update/screen view.
    if datetime.now(TZ).weekday() != 0:  # Monday == 0
        return None

    old = first_price_on_date(yesterday())
    if old is None:
        return None

    d = round(p - old)

    if d > 0:
        return f"📈 عيار 21 ارتفع {d} جنيه عن أول سعر أمس"
    if d < 0:
        return f"📉 عيار 21 انخفض {abs(d)} جنيه عن أول سعر أمس"
    return "➖ عيار 21 مستقر عن أول سعر أمس"


def latest_update_time():
    row = one(
        "SELECT created_at FROM GoldPriceHistory "
        "ORDER BY created_at DESC LIMIT 1"
    )
    return row["created_at"] if row else None


def price_text(p):
    p24, p21, p18 = calc(p)
    c = comparison(p)

    updated_at = latest_update_time()
    updated_line = None
    if updated_at is not None:
        t_str = (
            updated_at.strftime("%H:%M - %d/%m")
            if hasattr(updated_at, "strftime") else str(updated_at)
        )
        updated_line = f"🕐 آخر تحديث: {t_str}"

    return "\n".join(
        ([c, ""] if c else [])
        + [
            "💎 أسعار الذهب الآن",
            "",
            f"🟡 عيار 24 : {p24}",
            f"🟡 عيار 21 : {p21}",
            f"🟡 عيار 18 : {p18}",
        ]
        + ([updated_line] if updated_line else [])
        + [
            "",
            "📍 " + SHOP_ADDRESS,
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
        [InlineKeyboardButton("🧮 احسب دهبك", callback_data="calcgold")],
        [
            InlineKeyboardButton(
                "🔄 استبدال قديم بجديد", callback_data="calctrade"
            ),
            InlineKeyboardButton(
                "💵 بكام أشتري؟", callback_data="calcbudget"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 آخر 7 أيام", callback_data="pricehist7"
            ),
            InlineKeyboardButton(
                "🎁 ذكرني بمناسبة", callback_data="addoccasion"
            ),
        ],
        [InlineKeyboardButton(
            "🕌 حاسبة الزكاة", callback_data="zakatcalc"
        )],
        [InlineKeyboardButton(
            "⚖️ تحويل عيار", callback_data="karatconvert"
        )],
        [InlineKeyboardButton(
            "💰 تتبع استثمارك", callback_data="invtrack"
        )],
        [InlineKeyboardButton(
            "🔕 إلغاء الاشتراك (واتساب)"
            if wa_subscribed else
            "📱 اشترك في تحديثات السعر (واتساب)",
            callback_data="goldwunsub" if wa_subscribed else "goldwsub",
        )],
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
    ])


def product_display_kb(p, telegram_id, show_favorite_source=None):
    """Buttons shown under a product photo: inquiry, WhatsApp
    (tracked), location, website, and a favorite toggle. Shared
    between the category product listing and the favorites list, so
    both stay in sync automatically.
    """
    status = p.get("status") or "available"
    rows = []

    if status not in ("sold", "hidden"):
        rows.append([InlineKeyboardButton(
            "📩 استعلام عن المنتج", callback_data=f"inq:{p['id']}"
        )])

    is_fav = is_favorite(telegram_id, p["id"])
    fav_source = f":{show_favorite_source}" if show_favorite_source else ""
    rows.append([InlineKeyboardButton(
        "💔 شيل من المفضلة" if is_fav else "⭐ أضف للمفضلة",
        callback_data=f"favtoggle:{p['id']}{fav_source}",
    )])

    rows.append([
        InlineKeyboardButton(
            "💬 واتساب", callback_data=f"prodwa:{p['id']}"
        ),
        InlineKeyboardButton("📍 الموقع", url=MAPS),
    ])
    rows.append([
        InlineKeyboardButton("🌐 الموقع الإلكتروني", url=WEBSITE),
    ])
    return InlineKeyboardMarkup(rows)


def calc_result_kb(telegram_id):
    """Same as gold_screen_kb but with a share button pinned to the
    top — used under calculator RESULT messages only (not menus),
    since the result gets saved to calc_share_text right before this
    keyboard is shown."""
    base = gold_screen_kb(telegram_id)
    rows = [
        [InlineKeyboardButton("📤 شارك النتيجة", callback_data="calcshare")]
    ] + list(base.inline_keyboard)
    return InlineKeyboardMarkup(rows)


def budget_summary_view(b):
    balance = float(b["balance"])
    salary = float(b["salary"])

    text = (
        "📒 مصروفك الشهري\n\n"
        f"💰 المرتب الأساسي: {round(salary)} جنيه\n"
        f"💵 الرصيد المتبقي دلوقتي: {round(balance)} جنيه"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ دخل", callback_data="budgetin"),
            InlineKeyboardButton("➖ مصروف", callback_data="budgetout"),
        ],
        [InlineKeyboardButton(
            "📊 آخر الحركات", callback_data="budgethistory"
        )],
        [InlineKeyboardButton(
            "✏️ غيّر المرتب (شهر جديد)", callback_data="budgetchangesalary"
        )],
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
    ])
    return text, kb


def karat_target_kb():
    karats = [24, 22, 21, 18, 14, 12, 9]
    rows = []
    row = []
    for k in karats:
        row.append(InlineKeyboardButton(str(k), callback_data=f"kctarget:{k}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        "✍️ عيار تاني", callback_data="kctarget:custom"
    )])
    rows.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)


async def send_karat_conversion_result(
    update, context, weight, source_karat, target_karat, edit=False
):
    if not (1 <= target_karat <= 24):
        msg = "❌ العيار لازم يكون رقم من 1 لـ 24."
        if edit:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    target_weight = weight * source_karat / target_karat

    text = (
        "⚖️ تحويل عيار\n\n"
        f"{weight} جرام عيار {source_karat}\n"
        "= يعادل نفس كمية الدهب الخالص في:\n"
        f"👉 {target_weight:.2f} جرام عيار {target_karat}"
    )

    context.user_data["kc_weight"] = weight
    context.user_data["kc_karat"] = source_karat
    context.user_data["calc_share_text"] = build_share_text(text)

    kb_rows = [
        [InlineKeyboardButton(
            "🔁 حوّل لعيار تاني", callback_data="karatconvert_again"
        )]
    ] + list(calc_result_kb(update.effective_user.id).inline_keyboard)
    kb = InlineKeyboardMarkup(kb_rows)

    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


def home(admin=False, subscribed=False):
    k = [
        # تصفح
        [InlineKeyboardButton("💎 أسعار الذهب", callback_data="gold")],
        [InlineKeyboardButton("💍 المنتجات", callback_data="products")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favlist")],

        # أدوات شخصية
        [InlineKeyboardButton(
            "💰 هدف توفير للذهب", callback_data="savegoal"
        )],
        [InlineKeyboardButton(
            "📒 حاسبة مصروفك الشهري", callback_data="budgetmenu"
        )],
        [InlineKeyboardButton(
            "📇 حساباتي (له/عليه)", callback_data="ledgermenu"
        )],
        [InlineKeyboardButton(
            "🎂 سجّل تاريخ ميلادك", callback_data="birthdaymenu"
        )],
        [InlineKeyboardButton(
            "🔗 ادعُ صديق", callback_data="referral"
        )],

        # تواصل واستفسار
        [InlineKeyboardButton(
            "🕐 المحل مفتوح دلوقتي؟", callback_data="shopstatus"
        )],
        [
            InlineKeyboardButton(
                "📞 اطلب مكالمة", callback_data="callrequest"
            ),
            InlineKeyboardButton(
                "✍️ ابعت رسالة", callback_data="contactadmin"
            ),
        ],

        # إشعارات
        [InlineKeyboardButton(
            "🟢 الإشعارات: شغالة (دوس للإيقاف)"
            if subscribed else
            "🔴 الإشعارات: متوقفة (دوس عشان توصلك)",
            callback_data="notifunsub" if subscribed else "notifsub",
        )],
    ]

    if admin:
        k.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")])

    k.append([InlineKeyboardButton(
        "📇 بيانات المحل", callback_data="shopinfo"
    )])
    return InlineKeyboardMarkup(k)


def shop_info_kb():
    return InlineKeyboardMarkup([
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
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
    ])


def admin_menu(owner=False):
    rows = [
        [InlineKeyboardButton("📝 منشور جديد", callback_data="newpost")],
        [InlineKeyboardButton(
            "📢 الإشعارات للمشتركين", callback_data="notifmenu"
        )],
        [InlineKeyboardButton("💰 إدارة أسعار الذهب", callback_data="agold")],
        [InlineKeyboardButton("💍 إدارة المنتجات", callback_data="aprod")],
        [InlineKeyboardButton("📂 إدارة الأقسام", callback_data="acat")],
        [InlineKeyboardButton("⏰ النشر التلقائي", callback_data="schedmenu")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
        [InlineKeyboardButton(
            "🔥 تحليل المنتجات", callback_data="prodanalytics"
        )],
        [InlineKeyboardButton(
            "❌ عمليات فشلت اليوم", callback_data="failedops"
        )],
        [InlineKeyboardButton(
            "🔥 منتج اليوم", callback_data="potdmenu"
        )],
        [InlineKeyboardButton(
            "🔧 وضع الصيانة", callback_data="maintmenu"
        )],
        [InlineKeyboardButton(
            "📞 طلبات المكالمات", callback_data="callqueue"
        )],
        [InlineKeyboardButton(
            "💬 رد على عميل بالآيدي", callback_data="adminreplyid"
        )],
        [InlineKeyboardButton(
            "🏆 قائمة المتصدرين (الدعوات)", callback_data="referralleaderboard"
        )],
    ]
    if owner:
        rows.append(
            [InlineKeyboardButton("👥 إدارة الأدمنز", callback_data="adminlist")]
        )
    rows.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def call_queue_view(owner):
    """Returns (text, keyboard) for the pending call-requests queue,
    shared between the callqueue and calldone handlers."""
    rows = pending_call_requests()
    if not rows:
        return (
            "📞 مفيش طلبات مكالمات دلوقتي.",
            admin_menu(owner=owner),
        )

    text = "📞 طلبات المكالمات (الأقدم فوق)\n\n"
    kb_rows = []
    for i, r in enumerate(rows, start=1):
        ct = r["created_at"]
        ct_str = ct.strftime("%H:%M") if hasattr(ct, "strftime") else ct
        name = r.get("name") or "بدون اسم"
        text += f"{i}. {name} — {r['phone']} ({ct_str})\n"
        kb_rows.append([InlineKeyboardButton(
            f"✅ تم: {name} ({r['phone']})",
            callback_data=f"calldone:{r['id']}",
        )])
    kb_rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin")])
    return text, InlineKeyboardMarkup(kb_rows)


def notif_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✍️ إشعار سريع (يتبعت وخلاص)", callback_data="customnotif"
        )],
        [InlineKeyboardButton(
            "💾 رسائل جاهزة (احفظها وابعتها وقت ما تحب)",
            callback_data="savedlist"
        )],
        [InlineKeyboardButton(
            "⏰ إشعارات مجدولة يومية (فجر / صبح / مسا...)",
            callback_data="schedlist"
        )],
        [InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin")],
    ])


def sched_notif_list_kb():
    rows = scheduled_notifications()
    k = [
        [InlineKeyboardButton(
            f"{'🟢' if r['enabled'] else '🔴'} {r['time_str']} — "
            f"{(r.get('label') or r['body'])[:25]}",
            callback_data=f"schedopen:{r['id']}",
        )]
        for r in rows
    ]
    k.append(
        [InlineKeyboardButton("➕ إضافة إشعار مجدول", callback_data="schedadd")]
    )
    k.append([InlineKeyboardButton("⬅️ رجوع", callback_data="notifmenu")])
    return InlineKeyboardMarkup(k)


def sched_notif_item_kb(nid):
    n = scheduled_notification(nid)
    enabled = bool(n and n.get("enabled"))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔴 إيقاف" if enabled else "🟢 تفعيل",
            callback_data=f"schedtoggle:{nid}",
        )],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"scheddel:{nid}")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="schedlist")],
    ])


def saved_notif_list_kb():
    rows = saved_notifications()
    k = [
        [InlineKeyboardButton(
            f"💾 {r['title']}", callback_data=f"savedopen:{r['id']}"
        )]
        for r in rows
    ]
    k.append([InlineKeyboardButton(
        "➕ حفظ رسالة جديدة", callback_data="savedadd"
    )])
    k.append([InlineKeyboardButton("⬅️ رجوع", callback_data="notifmenu")])
    return InlineKeyboardMarkup(k)


def saved_notif_item_kb(nid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 ابعتها دلوقتي", callback_data=f"savedsend:{nid}")],
        [InlineKeyboardButton("🗑 احذفها", callback_data=f"saveddel:{nid}")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="savedlist")],
    ])


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


def ledger_customer_pick_kb(customers, page, page_size=10):
    """Paginated keyboard for picking a ledger customer from a list."""
    start_i = page * page_size
    chunk = customers[start_i:start_i + page_size]

    k = [
        [InlineKeyboardButton(
            f"👤 {c['name']}", callback_data=f"ledgerc:{c['id']}"
        )]
        for c in chunk
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            "⬅️ السابق", callback_data=f"ledgercp:{page-1}"
        ))
    if start_i + page_size < len(customers):
        nav.append(InlineKeyboardButton(
            "➡️ التالي", callback_data=f"ledgercp:{page+1}"
        ))
    if nav:
        k.append(nav)

    k.append([InlineKeyboardButton(
        "➕ سجّل حساب جديد", callback_data="ledgeraddcustomer"
    )])
    k.append([InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(k)


def ledger_customer_view(cid, telegram_id):
    cust = get_ledger_customer(cid, telegram_id)
    if not cust:
        return None, None

    lah, alaih, net = ledger_customer_balance(cid)

    if net > 0:
        net_line = f"📌 الصافي: هو مديون لك بـ {round(net)} جنيه"
    elif net < 0:
        net_line = f"📌 الصافي: انت مديون له بـ {round(abs(net))} جنيه"
    else:
        net_line = "📌 الصافي: الحساب متزن (مفيش دين لحد)"

    phone_line = f"\n📱 {cust['phone']}" if cust.get("phone") else ""

    text = (
        f"👤 {cust['name']}{phone_line}\n\n"
        f"🟢 له (انت مديون له): {round(lah)} جنيه\n"
        f"🔴 عليه (هو مديون لك): {round(alaih)} جنيه\n\n"
        f"{net_line}"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🟢 سجّل مبلغ له", callback_data=f"ledgerlah:{cid}"
            ),
            InlineKeyboardButton(
                "🔴 سجّل مبلغ عليه", callback_data=f"ledgeralaih:{cid}"
            ),
        ],
        [InlineKeyboardButton(
            "📊 كل الحركات", callback_data=f"ledgerhist:{cid}"
        )],
        [InlineKeyboardButton(
            "🗑 حذف العميل", callback_data=f"ledgerdel:{cid}"
        )],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="ledgermenu")],
    ])
    return text, kb


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
    wa_on = whatsapp_notifications_enabled()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تحديث السعر", callback_data="updategold")],
        [InlineKeyboardButton("📊 أسعار اليوم", callback_data="goldtoday")],
        [InlineKeyboardButton("📅 تاريخ الأسعار", callback_data="histmenu")],
        [InlineKeyboardButton(
            "🗑 حذف سعر غلط", callback_data="delpricelist"
        )],
        [InlineKeyboardButton("🔔 تنبيهات السعر", callback_data="alertmenu")],
        [InlineKeyboardButton("📢 نشر السعر", callback_data="publish")],
        [InlineKeyboardButton(
            "🧪 اختبار إشعار واتساب", callback_data="testwa"
        )],
        [InlineKeyboardButton(
            "🔄 إعادة ضبط جدول واتساب", callback_data="resetwa"
        )],
        [InlineKeyboardButton(
            "🔴 إيقاف الاشتراك في واتساب" if wa_on
            else "🟢 تفعيل الاشتراك في واتساب",
            callback_data="togglewa",
        )],
        [InlineKeyboardButton(
            f"💰 خصم شراء عيار 21: {sell_discount_per_gram(21)} ج/جرام",
            callback_data="setselldiscount:21",
        )],
        [InlineKeyboardButton(
            f"💰 خصم شراء عيار 18: {sell_discount_per_gram(18)} ج/جرام",
            callback_data="setselldiscount:18",
        )],
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

            # Atomic claim FIRST: only one process can win this for a
            # given id+date, closing the double-send race described
            # in mark_scheduled_post_ran's docstring.
            if not mark_scheduled_post_ran(sp["id"], today_str):
                continue

            p = latest()
            if not p:
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
    except Exception as e:
        print("Auto Post Tick Error:", repr(e), flush=True)


async def auto_notification_tick(context):
    """Runs every minute via JobQueue. Fires any due scheduled custom
    notifications (Fajr / opening / closing greetings, etc.) to every
    subscriber — same due-time/duplicate-guard pattern as
    auto_post_tick, but sends free text instead of the price
    template, and to subscribers instead of Telegram/Facebook."""
    try:
        now = datetime.now(TZ)
        hhmm = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")

        for sn in scheduled_notifications():
            if not sn.get("enabled"):
                continue
            if sn.get("time_str") != hhmm:
                continue

            if not mark_scheduled_notification_ran(sn["id"], today_str):
                continue

            sent, failed = await broadcast_custom_notification(
                context, ADMIN_ID, sn.get("body") or ""
            )

            log_action(
                ADMIN_ID, "AUTO_NOTIFICATION_SENT",
                object_type="scheduled_notification", object_id=sn["id"],
                new_value=f"sent={sent} failed={failed}",
            )
    except Exception as e:
        print("Auto Notification Tick Error:", repr(e), flush=True)


async def occasion_tick(context):
    """Runs every minute via JobQueue but only acts at 09:00 daily.
    DMs any customer whose registered occasion (birthday, anniversary,
    etc.) is exactly 7 days away — once per occasion per year."""
    try:
        now = datetime.now(TZ)
        if now.strftime("%H:%M") != "09:00":
            return

        today = now.date()
        this_year = now.year

        for r in all_occasion_reminders():
            try:
                target = date(this_year, r["month"], r["day"])
            except ValueError:
                continue  # e.g. Feb 29 in a non-leap year

            if target - timedelta(days=7) != today:
                continue

            # Atomic claim FIRST — see mark_scheduled_post_ran.
            if not mark_occasion_reminded(r["id"], this_year):
                continue

            try:
                await context.bot.send_message(
                    chat_id=r["telegram_id"],
                    text=(
                        "🎁 تذكير!\n\n"
                        f"باقي أسبوع على \"{r['label']}\" "
                        f"({target.strftime('%d-%m')}).\n"
                        "تقدر تزورنا بدري وتجهز الهدية 💛\n\n"
                        "تحب نفكّرك تاني امتى؟"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "🔁 نفس الميعاد السنة الجاية",
                            callback_data=f"occsame:{r['id']}",
                        )],
                        [InlineKeyboardButton(
                            "📅 حدد ميعاد تاني",
                            callback_data=f"occrenew:{r['id']}",
                        )],
                        [InlineKeyboardButton(
                            "🗑 إلغاء التذكير",
                            callback_data=f"occcancel:{r['id']}",
                        )],
                    ]),
                )
            except Exception as e:
                print(
                    f"Occasion Reminder Failed for {r['telegram_id']}:",
                    repr(e), flush=True,
                )
    except Exception as e:
        print("Occasion Tick Error:", repr(e), flush=True)


async def birthday_tick(context):
    """Runs every minute via JobQueue but only acts at 09:00 daily.
    DMs any customer whose registered birthday is today — once per
    customer per year — with a greeting + shop-visit nudge."""
    try:
        now = datetime.now(TZ)
        if now.strftime("%H:%M") != "09:00":
            return

        today = now.date()
        this_year = now.year

        for r in all_birthdays():
            if (r["month"], r["day"]) != (today.month, today.day):
                continue

            if not mark_birthday_wished(r["telegram_id"], this_year):
                continue

            try:
                await context.bot.send_message(
                    chat_id=r["telegram_id"],
                    text=(
                        "🎂 كل سنة وانت طيب! 🎉\n\n"
                        f"{SHOP_NAME} بتتمنالك سنة حلوة كلها فرح وسعادة ❤️\n\n"
                        "إيه رأيك تزورنا النهاردة وتدلّع نفسك بهدية "
                        "عيد ميلاد؟ 💍✨"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📍 موقع المحل", url=MAPS)],
                    ]),
                )
            except Exception as e:
                print(
                    f"Birthday Greeting Failed for {r['telegram_id']}:",
                    repr(e), flush=True,
                )
    except Exception as e:
        print("Birthday Tick Error:", repr(e), flush=True)


async def tip_tick(context):
    """Runs every minute via JobQueue but only acts once at 12:00
    daily. Broadcasts a rotating gold-care tip to gold subscribers."""
    try:
        now = datetime.now(TZ)
        if now.strftime("%H:%M") != "12:00":
            return

        today_str = now.strftime("%Y-%m-%d")
        if not try_claim_daily_task("last_tip_date", today_str):
            return

        tip = GOLD_CARE_TIPS[now.timetuple().tm_yday % len(GOLD_CARE_TIPS)]
        await broadcast_custom_notification(context, ADMIN_ID, tip)
    except Exception as e:
        print("Tip Tick Error:", repr(e), flush=True)


async def savings_goal_tick(context):
    """Runs every minute via JobQueue but only acts once at 09:00 on
    the 1st of each month. Reminds every customer with an active
    savings goal, with the monthly amount recalculated against the
    live gold price."""
    try:
        now = datetime.now(TZ)
        if now.day != 1 or now.strftime("%H:%M") != "09:00":
            return

        month_str = now.strftime("%Y-%m")

        p21 = latest()
        if not p21:
            return
        p24, _, _ = calc(p21)

        for g in all_savings_goals():
            if not mark_savings_goal_reminded(g["telegram_id"], month_str):
                continue

            now_price = p24 * (g["karat"] / 24)
            current_target = float(g["weight"]) * now_price
            monthly = current_target / g["months"]

            try:
                await context.bot.send_message(
                    chat_id=g["telegram_id"],
                    text=(
                        "💰 تذكير هدف التوفير\n\n"
                        f"هدفك: {float(g['weight'])} جرام عيار "
                        f"{g['karat']} خلال {g['months']} شهر.\n\n"
                        f"بسعر النهاردة، محتاج توفر تقريبًا "
                        f"{round(monthly)} ج الشهر ده عشان تفضل ماشي "
                        "على الخطة."
                    ),
                )
            except Exception as e:
                print(
                    f"Savings Goal Reminder Failed for {g['telegram_id']}:",
                    repr(e), flush=True,
                )
    except Exception as e:
        print("Savings Goal Tick Error:", repr(e), flush=True)


async def budget_month_end_tick(context):
    """Runs every minute via JobQueue but only acts once at 21:00 on
    the last calendar day of the month. Tells every customer with an
    active monthly budget how much they have left, offers the gold-
    equivalent of that amount as a savings nudge, then rolls their
    budget into a fresh cycle for the new month (same salary,
    balance reset)."""
    try:
        now = datetime.now(TZ)
        if now.strftime("%H:%M") != "21:00":
            return
        if (now.date() + timedelta(days=1)).day != 1:
            return  # not the last day of the month

        month_str = now.strftime("%Y-%m")
        next_month_str = (
            now.date() + timedelta(days=1)
        ).strftime("%Y-%m")

        p21 = latest()
        p24 = calc(p21)[0] if p21 else None

        for b in all_active_budgets():
            if not mark_budget_summary_sent(b["telegram_id"], month_str):
                continue

            balance = float(b["balance"])
            salary = float(b["salary"])

            gold_line = ""
            if p24 and balance > 0:
                grams = balance / p24
                gold_line = (
                    f"\n\nلو حبيت تدخر جزء منه في الذهب، الرصيد ده "
                    f"بسعر النهاردة يعادل تقريبًا {grams:.2f} جرام "
                    "عيار 24."
                )

            try:
                await context.bot.send_message(
                    chat_id=b["telegram_id"],
                    text=(
                        "🗓️ آخر يوم في الشهر!\n\n"
                        f"💰 مرتبك: {round(salary)} جنيه\n"
                        f"💵 معاك دلوقتي: {round(balance)} جنيه"
                        f"{gold_line}\n\n"
                        "بدأنا لك شهر جديد بنفس المرتب — لو اتغير "
                        "المرتب، غيّره من 📒 حاسبة مصروفك الشهري."
                    ),
                )
            except Exception as e:
                print(
                    f"Budget Summary Failed for {b['telegram_id']}:",
                    repr(e), flush=True,
                )

            start_budget_month(b["telegram_id"], salary, next_month_str)
    except Exception as e:
        print("Budget Month End Tick Error:", repr(e), flush=True)


async def weekly_summary_tick(context):
    """Runs every minute via JobQueue but only acts once at 20:00 on
    Fridays. Sends the admin a quick activity summary for the week."""
    try:
        now = datetime.now(TZ)
        if now.weekday() != 4 or now.strftime("%H:%M") != "20:00":
            return

        week_str = now.strftime("%Y-W%W")
        if not ADMIN_ID:
            return
        if not try_claim_daily_task("last_weekly_summary", week_str):
            return

        # Housekeeping: broadcast-message tracking rows older than 48h
        # are useless anyway (Telegram refuses to delete messages past
        # that age), so purge them here to keep the table bounded.
        try:
            c = db()
            try:
                with c.cursor() as x:
                    x.execute(
                        "DELETE FROM GoldBroadcastMessages WHERE "
                        "created_at < DATE_SUB(NOW(), INTERVAL 2 DAY)"
                    )
            finally:
                c.close()
        except Exception as e:
            print("Broadcast Messages Cleanup Error:", repr(e), flush=True)

        new_users = one(
            "SELECT COUNT(*) AS n FROM Users WHERE first_seen >= "
            "DATE_SUB(NOW(), INTERVAL 7 DAY)"
        )
        st = gold_period_stats(7)
        calls = call_requests_this_week()
        invs = one(
            "SELECT COUNT(*) AS n FROM Investments WHERE created_at >= "
            "DATE_SUB(NOW(), INTERVAL 7 DAY)"
        )

        price_line = (
            f"أعلى سعر: {st['high']} ج، أقل سعر: {st['low']} ج"
            if st else "لا يوجد بيانات أسعار كافية"
        )

        text = (
            "📊 ملخص الأسبوع\n\n"
            f"👥 مشتركين جدد: {new_users['n'] if new_users else 0}\n"
            f"💎 {price_line}\n"
            f"📞 طلبات مكالمات: {len(calls)}\n"
            f"💰 عمليات استثمار متسجلة: {invs['n'] if invs else 0}"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text)
        except Exception as e:
            print("Weekly Summary Send Failed:", repr(e), flush=True)
    except Exception as e:
        print("Weekly Summary Tick Error:", repr(e), flush=True)


async def potd_tick(context):
    """Runs every minute via JobQueue but only acts once at 10:30
    daily. If the admin hasn't already picked today's "منتج اليوم"
    manually, auto-selects the product with the most combined
    engagement (views + inquiries) and publishes it."""
    try:
        now = datetime.now(TZ)
        if now.strftime("%H:%M") != "10:30":
            return

        today_str = now.strftime("%Y-%m-%d")
        if not try_claim_daily_task("potd_date", today_str):
            return  # already set (manually or by an earlier tick) today

        row = one("""
            SELECT id FROM Products
            WHERE status='available' AND Photo_id IS NOT NULL
            ORDER BY (views_count + inquiries_count) DESC, id DESC
            LIMIT 1
        """)
        if not row:
            return

        await publish_product_of_day(context, row["id"])
    except Exception as e:
        print("POTD Tick Error:", repr(e), flush=True)


def record_gold_broadcast_message(price_id, telegram_id, message_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute("""
                INSERT INTO GoldBroadcastMessages
                (price_id, telegram_id, message_id)
                VALUES(%s, %s, %s)
            """, (price_id, telegram_id, message_id))
    finally:
        c.close()


def get_gold_broadcast_messages(price_id):
    return many(
        "SELECT telegram_id, message_id FROM GoldBroadcastMessages "
        "WHERE price_id=%s",
        (price_id,),
    )


def delete_gold_broadcast_messages(price_id):
    c = db()
    try:
        with c.cursor() as x:
            x.execute(
                "DELETE FROM GoldBroadcastMessages WHERE price_id=%s",
                (price_id,),
            )
    finally:
        c.close()


async def broadcast_gold_update(context, new_price, price_id=None):
    """
    Sends the new gold price to every customer subscribed to
    notifications (🔔 تفعيل الإشعارات on the main menu). Best-effort
    per user — a blocked bot or deactivated account for one
    subscriber never stops the broadcast to the rest. A small delay
    between sends avoids hitting Telegram's flood limits on large
    lists. When price_id is given (the GoldPriceHistory row this
    broadcast is for), every sent message's ID is logged so it can
    later be deleted from customers' chats if the price gets
    corrected/removed (see "🗑 حذف سعر غلط").
    """
    ids = gold_subscriber_ids()
    if not ids:
        return

    txt = "🔔 تحديث سعر الذهب\n\n" + price_text(new_price)
    sent, failed = 0, 0

    for uid in ids:
        try:
            msg = await context.bot.send_message(chat_id=uid, text=txt)
            sent += 1
            if price_id is not None:
                record_gold_broadcast_message(price_id, uid, msg.message_id)
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


async def publish_product_of_day(context, pid):
    """
    Publishes a product as "🔥 منتج اليوم": posts to the Telegram
    channel, DMs every notification subscriber, and publishes to
    Facebook + Instagram (best-effort — a failure on one platform
    never blocks the others). Marks it in Settings so it only fires
    once per calendar day. Returns a dict summarizing what worked.
    """
    p = product(pid)
    if not p:
        return {"ok": False, "message": "المنتج غير موجود."}

    parts = ["🔥 منتج اليوم", ""]
    if p["name"]:
        parts.append(f"💍 {p['name']}")
    if p["code"]:
        parts.append(f"🔖 الكود: {p['code']}")
    parts.append(
        f"💰 السعر: {round(float(p['price']))} جنيه"
        if p["price"] not in (None, "") else "💰 السعر: للاستعلام"
    )
    if p["description"]:
        parts.append(f"\n{p['description']}")
    caption = "\n".join(parts)

    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    set_setting("potd_product_id", str(pid))
    set_setting("potd_date", today_str)

    tg_ok = False
    dm_sent, dm_failed = 0, 0
    fb_result, ig_result = None, None

    if p["Photo_id"]:
        tg_ok = await tg_post(context, caption, p["Photo_id"])

        ids = gold_subscriber_ids()
        for uid in ids:
            try:
                await context.bot.send_photo(
                    chat_id=uid, photo=p["Photo_id"], caption=caption
                )
                dm_sent += 1
            except Exception as e:
                dm_failed += 1
                print(f"POTD DM Failed for {uid}:", repr(e), flush=True)
            await asyncio.sleep(0.05)

        try:
            f = await context.bot.get_file(p["Photo_id"])
            photo_url = (
                f.file_path if f.file_path.startswith("http")
                else f"https://api.telegram.org/file/bot"
                     f"{BOT_TOKEN}/{f.file_path}"
            )
            fb_result = await facebook_photo(caption, photo_url)
            ig_result = await instagram_photo(caption, photo_url)
        except Exception as e:
            print("POTD FB/IG Publish Error:", repr(e), flush=True)

    log_action(
        ADMIN_ID, "PRODUCT_OF_THE_DAY",
        object_type="product", object_id=pid,
        new_value=(
            f"tg={tg_ok} dm_sent={dm_sent} "
            f"fb={bool(fb_result and fb_result.get('ok'))} "
            f"ig={bool(ig_result and ig_result.get('ok'))}"
        ),
    )

    return {
        "ok": True,
        "product": p,
        "tg_ok": tg_ok,
        "dm_sent": dm_sent,
        "fb_ok": bool(fb_result and fb_result.get("ok")),
        "ig_ok": bool(ig_result and ig_result.get("ok")),
    }


async def broadcast_custom_notification(
    context, admin_id, text, photo_id=None, audience="subscribers"
):
    """
    Sends a free-form, admin-written announcement. Separate from —
    and independent of — the automatic gold price / new product
    broadcasts. `audience` is "subscribers" (default: only people
    who opted into gold-price notifications) or "all" (everyone who
    has ever pressed /start on the bot).
    """
    ids = all_user_ids() if audience == "all" else gold_subscriber_ids()
    sent, failed = 0, 0

    for uid in ids:
        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=uid, photo=photo_id, caption=text or None
                )
            else:
                await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"Custom Notification Failed for {uid}:", repr(e), flush=True)
        await asyncio.sleep(0.05)

    log_action(
        admin_id, "ADMIN_CUSTOM_NOTIFICATION",
        new_value=f"sent={sent} failed={failed}: {(text or '')[:200]}",
    )
    return sent, failed


async def whatsapp_send_template(phone_number, p24, p21, p18):
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
        r = await http_request_with_retry(
            requests.post,
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
    every subscribed WhatsApp number — but only twice a day, at two
    fixed windows, instead of on every price change:
      - the FIRST price update after 12:00 PM (afternoon slot)
      - the FIRST price update after 07:00 PM (evening slot)
    Any other price change that day is skipped on WhatsApp (it still
    goes out over Telegram, which has no such limit).

    WHY: our template is categorized "Marketing" by Meta, and
    WhatsApp enforces a hard cap of ~2 marketing messages per unique
    recipient per day (across ALL businesses) — extra sends past
    that are silently dropped (error 131049) and can hurt our
    quality rating. Gold prices can change many times a day, so we
    pick two fixed times instead of just "first N sends".

    Returns a dict describing exactly what happened, so the caller
    can show the admin a clear reason instead of silence:
      {"status": "no_subscribers" | "disabled" | "before_noon"
                 | "already_sent" | "sent",
       "slot": "afternoon"/"evening"/None,
       "sent": int, "failed": int, "details": [str, ...]}
    """
    if not whatsapp_notifications_enabled():
        # Admin switch is off (e.g. still waiting on Meta's review).
        # Numbers keep getting collected in the background, but we
        # don't attempt to actually send until the admin flips it on.
        return {"status": "disabled"}

    numbers = whatsapp_subscriber_numbers()
    if not numbers:
        return {"status": "no_subscribers"}

    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")

    if now.hour >= 19:
        slot = "evening"
    elif now.hour >= 12:
        slot = "afternoon"
    else:
        # Before the afternoon window even opens — nothing to send
        # on WhatsApp yet today.
        return {"status": "before_noon", "slot": None}

    setting_key = f"wa_slot_{slot}_sent_date"

    if get_setting(setting_key) == today_str:
        log_action(
            ADMIN_ID, "GOLD_PRICE_BROADCAST_WHATSAPP",
            status="skipped",
            error=(
                f"'{slot}' slot already sent today — "
                "update sent via Telegram only."
            ),
        )
        return {"status": "already_sent", "slot": slot}

    p24, p21, p18 = calc(new_price)
    sent, failed = 0, 0
    details = []

    for number in numbers:
        result = await whatsapp_send_template(number, p24, p21, p18)
        if result.get("ok"):
            sent += 1
        else:
            failed += 1
            details.append(f"{number}: {result.get('message')}")
            print(
                f"WhatsApp Broadcast Failed for {number}:",
                result.get("message"), flush=True,
            )
        await asyncio.sleep(0.1)

    # Mark this slot as used for today, even if some individual sends
    # failed — we only get one shot at each slot regardless, and we
    # don't want a partial failure to trigger a second attempt later
    # in the same window and risk going over the per-recipient cap.
    if sent or failed:
        set_setting(setting_key, today_str)

    log_action(
        ADMIN_ID, "GOLD_PRICE_BROADCAST_WHATSAPP",
        new_value=f"sent={sent} failed={failed} (slot={slot})",
    )

    return {
        "status": "sent", "slot": slot,
        "sent": sent, "failed": failed, "details": details,
    }


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
    if maintenance_mode_on() and not is_admin(update):
        await update.message.reply_text(
            "🔧 البوت تحت التحديث دلوقتي، هيرجع يشتغل قريب. "
            "حاول تاني بعد شوية 🙏"
        )
        return

    context.user_data.clear()

    referred_by = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                candidate = int(arg[4:])
                if candidate != update.effective_user.id:
                    referred_by = candidate
            except ValueError:
                pass

    track_user(update, referred_by=referred_by)
    await update.message.reply_text(
        "💎 " + SHOP_NAME + "\n\n"
        "أهلاً بيك في البوت الرسمي لـ" + SHOP_FULL_NAME + " ✨\n\n"
        "من غير ما تتصل بينا أو تيجي المحل، تقدر من هنا:\n\n"
        "💎 أسعار الذهب — سعر عيار 21 و24 والسبايك والعملات "
        "لحظة بلحظة، وجوّاها أدوات كتير:\n"
        "  • 🧮 احسب دهبك (هتشتري ولا هتبيع)\n"
        "  • 🔄 استبدال قطعة قديمة بجديدة\n"
        "  • 💵 اعرف تقدر تشتري كام جرام بميزانيتك\n"
        "  • ⚖️ تحويل الوزن من عيار لعيار\n"
        "  • 🕌 حاسبة الزكاة\n"
        "  • 📊 أسعار آخر 7 أيام\n"
        "  • 🎁 تذكير بمناسباتك (خطوبة، جواز... إلخ)\n\n"
        "💍 المنتجات — شوف قطعنا وعروضنا أول بأول.\n\n"
        "🔔 فعّل الإشعارات تحت عشان يوصلك سعر الذهب والمنتجات "
        "الجديدة على طول من غير ما تفتح البوت كل شوية.\n\n"
        "اختار من القائمة 👇",
        reply_markup=home(is_admin(update), is_gold_subscribed(update.effective_user.id)),
    )


async def show_id(update, context):
    u = update.effective_user
    await update.message.reply_text(
        f"🆔 آيدي تليجرام بتاعك:\n\n{u.id}"
    )


async def favorites_command(update, context):
    """/favorites — same list as the ⭐ المفضلة home-menu button, but
    reachable directly from Telegram's "/" command menu."""
    if maintenance_mode_on() and not is_admin(update):
        await update.message.reply_text(
            "🔧 البوت تحت التحديث دلوقتي، هيرجع يشتغل قريب. "
            "حاول تاني بعد شوية 🙏"
        )
        return

    track_user(update)
    favs = list_favorites(update.effective_user.id)

    if not favs:
        await update.message.reply_text(
            "⭐ المفضلة\n\n"
            "مفيش منتجات في المفضلة لسه.\n"
            "تقدر تضيف أي منتج يعجبك من قائمة 💍 المنتجات.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "💍 المنتجات", callback_data="products"
                )],
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    await update.message.reply_text(f"⭐ المفضلة عندك ({len(favs)})")

    for p in favs:
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

        try:
            await update.message.reply_photo(
                photo=p["Photo_id"],
                caption="\n".join(parts) or None,
                reply_markup=product_display_kb(
                    p, update.effective_user.id
                ),
            )
        except Exception as e:
            print("Favorites Command Display Error:", repr(e), flush=True)


async def update_price_shortcut(update, context):
    """
    Admin-only shortcut command that skips straight to "send me the
    new price" instead of going through Gold menu → تحديث السعر.
    Shows up next to /start in Telegram's "/" command menu.
    """
    if not is_admin(update):
        return

    track_user(update)
    context.user_data.clear()
    context.user_data["state"] = "gold"

    await update.message.reply_text(
        "✏️ ابعت سعر عيار 21 الجديد.\nمثال: 7000"
    )


# =========================================================
# FACEBOOK - PUBLIC PUBLISH V12
# =========================================================

async def http_request_with_retry(
    func, *args, max_retries=3, base_delay=2, **kwargs
):
    """
    Runs a blocking `requests` call (get/post/...) in a separate
    thread via asyncio.to_thread, so it never blocks the bot's event
    loop for other users while waiting on Meta's servers.

    Also retries with exponential backoff (2s, 4s, 8s...) on
    timeouts, connection errors, HTTP 429 (rate limit), and 5xx
    (Meta-side server errors) — these are almost always transient.
    Any other status code (4xx auth/validation errors) is returned
    immediately without retrying, since retrying won't fix them.
    """
    last_exc = None
    r = None

    for attempt in range(max_retries):
        try:
            r = await asyncio.to_thread(func, *args, **kwargs)
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_retries - 1:
                await asyncio.sleep(base_delay * (2 ** attempt))
                continue
            raise

        if r.status_code == 429 or r.status_code >= 500:
            if attempt < max_retries - 1:
                await asyncio.sleep(base_delay * (2 ** attempt))
                continue
        return r

    if last_exc:
        raise last_exc
    return r


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


async def fb_request(method, url, *, params=None, data=None, timeout=30):
    if method == "GET":
        r = await http_request_with_retry(
            requests.get, url, params=params, timeout=timeout
        )
    else:
        r = await http_request_with_retry(
            requests.post, url, data=data, timeout=timeout
        )

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
        r = await http_request_with_retry(
            requests.post,
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

        r2 = await http_request_with_retry(
            requests.post,
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
        img = await asyncio.to_thread(requests.get, photo_url, timeout=30)
        img.raise_for_status()
    except requests.RequestException as e:
        return {
            "ok": False,
            "message": f"❌ فشل تحميل الصورة من تليجرام:\n{repr(e)}",
        }

    try:
        r = await http_request_with_retry(
            requests.post,
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

    r, created = await fb_request("POST", media_url, data=data)

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
            sr, sdata = await fb_request(
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

    r2, published = await fb_request(
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
        r, page = await fb_request(
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
        r, created = await fb_request(
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
            r, data = await fb_request(
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
            r, data = await fb_request(
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

            r, data = await fb_request(
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

    if state == "custom_notif":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        audience = context.user_data.get("notif_audience", "subscribers")
        photo_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        context.user_data.clear()

        await update.message.reply_text("⏳ جاري الإرسال...")

        sent, failed = await broadcast_custom_notification(
            context, update.effective_user.id, caption,
            photo_id=photo_id, audience=audience,
        )

        await update.message.reply_text(
            f"✅ اتبعت الإشعار.\n📤 وصل لـ {sent} شخص"
            + (f" (فشل مع {failed})" if failed else "") + ".",
            reply_markup=notif_menu(),
        )
        return

    if state == "saved_notif_body":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        title = context.user_data.get("saved_title", "رسالة")
        photo_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        context.user_data.clear()

        add_saved_notification(
            update.effective_user.id, title, caption, photo_id=photo_id
        )

        await update.message.reply_text(
            f"✅ اتحفظت \"{title}\". تقدر تبعتها وقت ما تحب من "
            "\"💾 رسائل جاهزة\".",
            reply_markup=saved_notif_list_kb(),
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

    if maintenance_mode_on() and not is_admin(update):
        await update.message.reply_text(
            "🔧 البوت تحت التحديث دلوقتي، هيرجع يشتغل قريب. "
            "حاول تاني بعد شوية 🙏"
        )
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

    if s == "sell_discount_input":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        try:
            new_discount = int(float(t))
            if new_discount < 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب رقم صحيح (بالجنيه)، مثال: 100"
            )
            return

        karat = context.user_data.get("discount_karat", 21)
        set_setting(f"sell_discount_{karat}", str(new_discount))
        log_action(
            update.effective_user.id, "ADMIN_CHANGED_SELL_DISCOUNT",
            new_value=f"karat={karat} discount={new_discount}",
        )
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ تم تحديث خصم الشراء لعيار {karat} إلى "
            f"{new_discount} جنيه/جرام.",
            reply_markup=gold_menu(),
        )
        return

    if s == "calc_mc_amount_input":
        try:
            charge = float(t.replace(",", "."))
            if charge < 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب رقم صحيح بالجنيه، مثال: 50 أو 300"
            )
            return

        karat = context.user_data.get("calc_mc_karat")
        weight = context.user_data.get("calc_mc_weight")
        per_gram = context.user_data.get("calc_mc_pergram")
        gold_total = context.user_data.get("calc_mc_total")
        mc_type = context.user_data.get("calc_mc_type")
        context.user_data.clear()

        if None in (karat, weight, per_gram, gold_total, mc_type):
            await update.message.reply_text("❌ حصل خطأ، جرب تاني.")
            return

        if mc_type == "piece":
            final_total = round(gold_total + charge)
            mc_line = f"مصنعية القطعة كلها: {round(charge)} جنيه\n"
        else:  # "gram"
            per_gram_mc = per_gram + charge
            final_total = round(per_gram_mc * weight)
            mc_line = f"مصنعية الجرام: {round(charge)} جنيه\n"

        result_text = (
            "🧮 نتيجة الحساب (شامل المصنعية)\n\n"
            f"العيار: {karat}\n"
            f"الوزن: {weight} جرام\n"
            f"سعر الجرام: {round(per_gram)} جنيه\n"
            f"قيمة الذهب: {gold_total} جنيه\n"
            + mc_line
            + f"\n💰 الإجمالي: {final_total} جنيه\n\n"
            "⚠️ السعر تقريبي، والمصنعية النهائية بتتحدد في المحل."
        )
        context.user_data["calc_share_text"] = build_share_text(result_text)
        await update.message.reply_text(
            result_text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if s == "save_weight_input":
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(\d{1,2})$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ اكتب الوزن والعيار مفصولين بمسافة.\nمثال: 10 21"
            )
            return

        weight = float(m.group(1))
        karat = int(m.group(2))

        if weight <= 0:
            await update.message.reply_text("❌ اكتب وزن أكبر من صفر.")
            return
        if not (1 <= karat <= 24):
            await update.message.reply_text(
                "❌ العيار لازم يكون رقم من 1 لـ 24."
            )
            return

        context.user_data["save_weight"] = weight
        context.user_data["save_karat"] = karat
        context.user_data["state"] = "save_months_input"

        await update.message.reply_text(
            "على مدار كام شهر عايز توفر المبلغ ده؟\nمثال: 6"
        )
        return

    if s == "save_months_input":
        t_clean = t.strip()
        if not t_clean.isdigit() or int(t_clean) <= 0:
            await update.message.reply_text("❌ اكتب عدد شهور صحيح.\nمثال: 6")
            return

        months = int(t_clean)
        weight = context.user_data.get("save_weight")
        karat = context.user_data.get("save_karat")
        if weight is None or karat is None:
            await update.message.reply_text("ابدأ من الأول من القائمة الرئيسية.")
            return

        p21 = latest()
        if not p21:
            await update.message.reply_text(
                "💎 لم يتم تحديث أسعار الذهب حتى الآن."
            )
            return

        p24, _, _ = calc(p21)
        now_price = p24 * (karat / 24)
        target = weight * now_price
        monthly = target / months

        set_savings_goal(
            update.effective_user.id, weight, karat, months, target
        )
        context.user_data.clear()

        await update.message.reply_text(
            "🎯 تمام! هدفك:\n\n"
            f"{weight} جرام عيار {karat} خلال {months} شهر\n"
            f"القيمة بسعر النهاردة: {round(target)} ج\n\n"
            f"يعني محتاج توفر تقريبًا {round(monthly)} ج في الشهر.\n\n"
            "هنفكّرك كل شهر بالمبلغ المحدث حسب سعر الذهب وقتها.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if s == "budget_salary_input":
        t_clean = t.strip().replace(",", "")
        try:
            salary = float(t_clean)
        except ValueError:
            await update.message.reply_text("❌ اكتب رقم بس.\nمثال: 8000")
            return

        if salary <= 0:
            await update.message.reply_text("❌ اكتب مبلغ أكبر من صفر.")
            return

        month_str = datetime.now(TZ).strftime("%Y-%m")
        start_budget_month(update.effective_user.id, salary, month_str)
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ تمام! سجلنا مرتبك ({round(salary)} جنيه).\n\n"
            "دلوقتي كل ما تصرف أو يدخلك فلوس، سجلها من هنا، وآخر "
            "كل شهر هنقولك معاك كام.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📒 افتح حاسبة المصروف", callback_data="budgetmenu"
                )],
            ]),
        )
        return

    if s == "budget_amount_input":
        t_clean = t.strip().replace(",", "")
        try:
            amount = float(t_clean)
        except ValueError:
            await update.message.reply_text("❌ اكتب رقم بس.\nمثال: 500")
            return

        if amount <= 0:
            await update.message.reply_text("❌ اكتب مبلغ أكبر من صفر.")
            return

        ttype = context.user_data.get("budget_type")
        if ttype not in ("in", "out"):
            await update.message.reply_text("ابدأ من قائمة حاسبة المصروف.")
            return

        apply_budget_transaction(update.effective_user.id, amount, ttype)
        context.user_data.clear()

        b = get_budget(update.effective_user.id)
        text, kb = budget_summary_view(b)
        await update.message.reply_text(
            ("✅ اتسجل الدخل.\n\n" if ttype == "in" else "✅ اتسجل المصروف.\n\n")
            + text,
            reply_markup=kb,
        )
        return

    if s == "call_phone_input":
        phone = re.sub(r"[\s\-]", "", t.strip())
        if not re.match(r"^\+?\d{8,15}$", phone):
            await update.message.reply_text(
                "❌ اكتب رقم موبايل صحيح.\nمثال: 01012345678"
            )
            return

        u = update.effective_user
        name = f"{u.first_name or ''} {u.last_name or ''}".strip() or "بدون اسم"

        rid = add_call_request(u.id, name, phone)
        position = pending_call_count_before(rid) + 1
        context.user_data["state"] = None

        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "📞 طلب مكالمة جديد\n\n"
                        f"👤 {name}\n"
                        f"📱 {phone}\n\n"
                        "من لوحة التحكم → 📞 طلبات المكالمات."
                    ),
                )
            except Exception as e:
                print("Call Request Notify Failed:", repr(e), flush=True)

        await update.message.reply_text(
            "✅ اتسجل طلبك، هنكلمك في أقرب وقت.\n\n"
            f"ترتيبك في قائمة الانتظار: {position}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if s == "contact_admin_input":
        context.user_data["state"] = None

        u = update.effective_user
        sender = f"{u.first_name or ''} {u.last_name or ''}".strip() or "بدون اسم"
        username_line = f"@{u.username}" if u.username else "بدون يوزر"

        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "✍️ رسالة جديدة من عميل\n\n"
                        f"👤 {sender} ({username_line})\n"
                        f"🆔 {u.id}\n\n"
                        f"{t}"
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "💬 رد على العميل", callback_data=f"reply:{u.id}"
                        )
                    ]]),
                )
            except Exception as e:
                print("Contact Admin Forward Failed:", repr(e), flush=True)

        await update.message.reply_text(
            "✅ اتبعتت رسالتك للإدارة، هيتم الرد عليك في أقرب وقت.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if s == "birthday_date_input":
        m = re.match(r"^([0-3]?\d)-(0?\d|1[0-2])$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ الصيغة غلط. اكتب التاريخ بصيغة يوم-شهر.\nمثال: 25-12"
            )
            return

        day, month = int(m.group(1)), int(m.group(2))
        try:
            date(2024, month, day)  # validates day fits in month (leap ok)
        except ValueError:
            await update.message.reply_text(
                "❌ التاريخ ده مش موجود. اكتبه تاني.\nمثال: 25-12"
            )
            return

        context.user_data["state"] = None
        set_birthday(update.effective_user.id, month, day)

        await update.message.reply_text(
            f"🎂 تمام! سجلنا ميلادك يوم {t.strip()}، وهنبعتلك تهنئة "
            "كل سنة في يومك 💛",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if s == "inv_weight_input":
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(\d{1,2})$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ اكتب الوزن والعيار مفصولين بمسافة.\nمثال: 20 21"
            )
            return

        weight = float(m.group(1))
        karat = int(m.group(2))

        if weight <= 0:
            await update.message.reply_text("❌ اكتب وزن أكبر من صفر.")
            return
        if not (1 <= karat <= 24):
            await update.message.reply_text(
                "❌ العيار لازم يكون رقم من 1 لـ 24."
            )
            return

        context.user_data["inv_weight"] = weight
        context.user_data["inv_karat"] = karat
        context.user_data["state"] = "inv_price_input"

        await update.message.reply_text(
            "اكتب السعر اللي دفعته في الجرام (تقدر تحط فيه المصنعية "
            "لو حابب).\nمثال: 6800"
        )
        return

    if s == "inv_price_input":
        t_clean = t.strip().replace(",", "")
        try:
            price = float(t_clean)
        except ValueError:
            await update.message.reply_text("❌ اكتب رقم بس.")
            return

        if price <= 0:
            await update.message.reply_text("❌ اكتب سعر أكبر من صفر.")
            return

        weight = context.user_data.get("inv_weight")
        karat = context.user_data.get("inv_karat")
        if weight is None or karat is None:
            await update.message.reply_text("ابدأ التسجيل من الأول من قائمة أسعار الذهب.")
            return

        add_investment(
            update.effective_user.id, weight, karat, price, date.today()
        )
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ اتسجلت: {weight} جرام عيار {karat} بسعر {round(price)} "
            "ج/جرام.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📊 استثماراتي", callback_data="invlist"
                )],
                [InlineKeyboardButton(
                    "➕ سجّل عملية تانية", callback_data="invadd"
                )],
            ]),
        )
        return

    if s == "karat_convert_input":
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(\d{1,2})$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ اكتب الوزن والعيار مفصولين بمسافة.\nمثال: 50 21"
            )
            return

        weight = float(m.group(1))
        karat = int(m.group(2))

        if weight <= 0:
            await update.message.reply_text("❌ اكتب وزن أكبر من صفر.")
            return
        if not (1 <= karat <= 24):
            await update.message.reply_text(
                "❌ العيار لازم يكون رقم من 1 لـ 24."
            )
            return

        context.user_data["kc_weight"] = weight
        context.user_data["kc_karat"] = karat
        context.user_data["state"] = None

        await update.message.reply_text(
            f"القطعة: {weight} جرام عيار {karat}\n\nعايز تحولها لعيار كام؟",
            reply_markup=karat_target_kb(),
        )
        return

    if s == "karat_convert_target_input":
        t_clean = t.strip()
        if not t_clean.isdigit():
            await update.message.reply_text("❌ اكتب رقم العيار بس (1-24).")
            return

        target_karat = int(t_clean)
        weight = context.user_data.get("kc_weight")
        karat = context.user_data.get("kc_karat")

        if weight is None or karat is None:
            await update.message.reply_text("ابدأ التحويل من الأول من قائمة أسعار الذهب.")
            return

        context.user_data["state"] = None
        await send_karat_conversion_result(
            update, context, weight, karat, target_karat, edit=False
        )
        return

    if s == "zakat_piece_input":
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(\d{1,2})$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ اكتب الوزن والعيار مفصولين بمسافة.\nمثال: 50 21"
            )
            return

        weight = float(m.group(1))
        karat = int(m.group(2))

        if weight <= 0:
            await update.message.reply_text("❌ اكتب وزن أكبر من صفر.")
            return
        if not (1 <= karat <= 24):
            await update.message.reply_text(
                "❌ العيار لازم يكون رقم من 1 لـ 24."
            )
            return

        pieces = context.user_data.get("zakat_pieces", [])
        pieces.append((weight, karat))
        context.user_data["zakat_pieces"] = pieces
        context.user_data["state"] = None

        running_total = sum(w * (k / 24) for w, k in pieces)
        await update.message.reply_text(
            f"✅ سجلت: {weight} جرام عيار {karat}.\n\n"
            f"إجمالي الوزن المكافئ لحد دلوقتي: {running_total:.2f} "
            "جرام عيار 24.\n\nعندك قطعة تانية؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ أضف قطعة تانية", callback_data="zakatmore"
                )],
                [InlineKeyboardButton(
                    "✅ خلصت، احسب الزكاة", callback_data="zakatfinish"
                )],
            ]),
        )
        return

    if s == "trade_weight_input":
        try:
            weight = float(t.replace(",", "."))
            if weight <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب وزن صحيح بالجرام، مثال: 5 أو 3.5"
            )
            return

        karat = context.user_data.get("trade_karat")
        mode = context.user_data.get("trade_mode")
        context.user_data.clear()

        ok, _, old_total, _ = compute_calc_result(mode, karat, weight)
        if not ok:
            await update.message.reply_text(
                "💎 لم يتم تحديث أسعار الذهب حتى الآن."
            )
            return

        context.user_data.update(
            state="trade_new_price_input",
            trade_karat=karat, trade_weight=weight, trade_old_total=old_total,
        )
        await update.message.reply_text(
            f"✅ قيمة قطعتك القديمة تقريبًا: {old_total} جنيه.\n\n"
            "دلوقتي اكتب سعر القطعة الجديدة اللي عايز تاخدها (زي ما "
            "قالهولك المحل، شامل المصنعية).\nمثال: 18000"
        )
        return

    if s == "trade_new_price_input":
        try:
            new_price = float(t.replace(",", "."))
            if new_price <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب سعر صحيح بالجنيه، مثال: 18000"
            )
            return

        karat = context.user_data.get("trade_karat")
        weight = context.user_data.get("trade_weight")
        old_total = context.user_data.get("trade_old_total")
        context.user_data.clear()

        if old_total is None:
            await update.message.reply_text("❌ حصل خطأ، ابدأ من الأول.")
            return

        diff = round(new_price - old_total)
        if diff > 0:
            diff_line = f"💰 هتدفع فرق: {diff} جنيه"
        elif diff < 0:
            diff_line = f"🎉 هياخدلك المحل فرق: {abs(diff)} جنيه"
        else:
            diff_line = "✅ مفيش فرق، القيمتين متساويتين!"

        trade_text = (
            "🔄 نتيجة الاستبدال\n\n"
            f"قيمة قطعتك القديمة (عيار {karat}، {weight} جرام): "
            f"{old_total} جنيه\n"
            f"سعر القطعة الجديدة: {round(new_price)} جنيه\n\n"
            + diff_line
        )
        context.user_data["calc_share_text"] = build_share_text(trade_text)
        await update.message.reply_text(
            trade_text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if s == "budget_amount_input":
        try:
            budget = float(t.replace(",", "."))
            if budget <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب مبلغ صحيح بالجنيه، مثال: 5000"
            )
            return

        karat = context.user_data.get("budget_karat")
        context.user_data.clear()

        p21 = latest()
        if not p21:
            await update.message.reply_text(
                "💎 لم يتم تحديث أسعار الذهب حتى الآن."
            )
            return

        p24, p21c, p18 = calc(p21)
        per_gram = {24: p24, 21: p21c, 18: p18}.get(karat)
        grams = budget / per_gram

        budget_text = (
            "💵 بكام أقدر أشتري؟\n\n"
            f"الميزانية: {round(budget)} جنيه\n"
            f"العيار: {karat}\n"
            f"سعر الجرام: {per_gram} جنيه\n\n"
            f"⚖️ تقدر تاخد تقريبًا: {grams:.2f} جرام\n\n"
            "⚠️ ده تقريبي وذهب صافي بس؛ وزن القطعة الفعلي هيقل شوية "
            "عشان يغطي المصنعية."
        )
        context.user_data["calc_share_text"] = build_share_text(budget_text)
        await update.message.reply_text(
            budget_text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if s == "occasion_label_input":
        if not t.strip():
            await update.message.reply_text("❌ اكتب اسم المناسبة.")
            return

        context.user_data["occasion_label"] = t.strip()[:100]
        context.user_data["state"] = "occasion_date_input"

        await update.message.reply_text(
            "📅 اكتب تاريخ المناسبة بصيغة يوم-شهر (DD-MM).\n"
            "مثال: 15-08"
        )
        return

    if s == "occasion_date_input":
        m = re.match(r"^([0-3]?\d)-(0?\d|1[0-2])$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ الصيغة غلط. اكتب التاريخ بصيغة يوم-شهر.\nمثال: 15-08"
            )
            return

        day, month = int(m.group(1)), int(m.group(2))
        try:
            date(2024, month, day)  # validates day fits in month (leap ok)
        except ValueError:
            await update.message.reply_text(
                "❌ التاريخ ده مش موجود. اكتبه تاني.\nمثال: 15-08"
            )
            return

        label = context.user_data.get("occasion_label", "مناسبة")
        context.user_data.clear()

        add_occasion_reminder(update.effective_user.id, label, month, day)

        await update.message.reply_text(
            f"🎉 تمام! هنفكّرك بـ\"{label}\" ({t.strip()}) قبلها بأسبوع.",
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return

    if s == "occasion_renew_date_input":
        m = re.match(r"^([0-3]?\d)-(0?\d|1[0-2])$", t.strip())
        if not m:
            await update.message.reply_text(
                "❌ الصيغة غلط. اكتب التاريخ بصيغة يوم-شهر.\nمثال: 20-11"
            )
            return

        day, month = int(m.group(1)), int(m.group(2))
        try:
            date(2024, month, day)
        except ValueError:
            await update.message.reply_text(
                "❌ التاريخ ده مش موجود. اكتبه تاني.\nمثال: 20-11"
            )
            return

        rid = context.user_data.get("occasion_renew_id")
        context.user_data.clear()

        r = get_occasion_reminder(rid) if rid else None
        if not r or r["telegram_id"] != update.effective_user.id:
            await update.message.reply_text("❌ حصل خطأ، جرب تاني.")
            return

        update_occasion_reminder_date(rid, month, day)

        await update.message.reply_text(
            f"✅ تم تحديث ميعاد تذكير \"{r['label']}\" لـ {t.strip()}.",
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return

    if s == "calc_weight_input":
        try:
            weight = float(t.replace(",", "."))
            if weight <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ اكتب وزن صحيح بالجرام، مثال: 5 أو 3.5"
            )
            return

        mode = context.user_data.get("calc_mode")
        karat = context.user_data.get("calc_karat")
        compare_active = context.user_data.get("calc_compare_active")
        compare_first = context.user_data.get("calc_compare_first")
        context.user_data.clear()

        ok, text, total, per_gram = compute_calc_result(mode, karat, weight)
        if not ok:
            await update.message.reply_text(text)
            return

        # "مقارنة سريعة" step 1: this was the FIRST piece — stash its
        # result and ask for the second piece's karat instead of
        # finalizing anything yet.
        if compare_active and not compare_first:
            context.user_data["calc_compare_active"] = True
            context.user_data["calc_compare_first"] = {
                "mode": mode, "karat": karat,
                "weight": weight, "total": total,
            }
            await update.message.reply_text(
                f"✅ سجلت القطعة الأولى: عيار {karat}، {weight} جرام "
                f"→ {total} جنيه.\n\nدلوقتي اختار عيار القطعة التانية:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "عيار 24", callback_data=f"calccmpk2:{mode}:24"
                    )],
                    [InlineKeyboardButton(
                        "عيار 21", callback_data=f"calccmpk2:{mode}:21"
                    )],
                    [InlineKeyboardButton(
                        "عيار 18", callback_data=f"calccmpk2:{mode}:18"
                    )],
                ]),
            )
            return

        save_last_calc(update.effective_user.id, mode, karat, weight)

        # مقارنة سريعة step 2: show the difference vs the first piece
        # instead of just the plain result.
        if compare_first:
            diff = total - compare_first["total"]
            sign = "+" if diff >= 0 else ""
            cmp_text = (
                "⚖️ مقارنة القطعتين\n\n"
                f"القطعة الأولى: عيار {compare_first['karat']}، "
                f"{compare_first['weight']} جرام → "
                f"{compare_first['total']} جنيه\n"
                f"القطعة التانية: عيار {karat}، {weight} جرام → "
                f"{total} جنيه\n\n"
                f"💰 الفرق: {sign}{diff} جنيه"
            )
            context.user_data["calc_share_text"] = build_share_text(cmp_text)
            await update.message.reply_text(
                cmp_text,
                reply_markup=calc_result_kb(update.effective_user.id),
            )
            return

        # Plain "هتشتري" result (not part of a comparison): offer to
        # add the making charge the shop actually quotes them, since
        # that's set at the counter, not by us.
        if mode == "buy":
            context.user_data.update(
                calc_mc_karat=karat, calc_mc_weight=weight,
                calc_mc_pergram=per_gram, calc_mc_total=total,
            )
            await update.message.reply_text(
                text + "\n\nتحب تضيفلك مصنعية القطعة اللي هيقولهالك المحل؟",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ أضف مصنعية", callback_data="calcmcyes"
                    )],
                    [InlineKeyboardButton(
                        "❌ من غير مصنعية", callback_data="calcmcno"
                    )],
                ]),
            )
            return

        context.user_data["calc_share_text"] = build_share_text(text)
        await update.message.reply_text(
            text, reply_markup=calc_result_kb(update.effective_user.id)
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

        new_price_id = save_latest(p, admin_id=update.effective_user.id)
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
        await broadcast_gold_update(context, p, price_id=new_price_id)

        wa_result = await broadcast_gold_update_whatsapp(context, p)
        wa_status_map = {
            "disabled": (
                "🔒 واتساب: الخدمة متوقفة حاليًا (مش مفعّلة). "
                "الأرقام بتتسجل عادي وهتستقبل التحديثات أول ما تفعّلها."
            ),
            "no_subscribers": "⚠️ واتساب: مفيش مشتركين حالياً.",
            "before_noon": (
                "⏳ واتساب: لسه قبل الساعة 12 الضهر — "
                "أول فترة إرسال بتبدأ بعدها."
            ),
            "already_sent": lambda r: (
                f"⏭️ واتساب: اتخطى — فترة "
                f"({'الظهر' if r['slot'] == 'afternoon' else 'المسا'}) "
                "اتبعتت فعلاً النهاردة."
            ),
            "sent": lambda r: (
                f"✅ واتساب: اتبعت — نجح {r['sent']} وفشل {r['failed']}"
                + (
                    "\n" + "\n".join(f"❌ {d}" for d in r["details"][:5])
                    if r["failed"] else ""
                )
            ),
        }
        wa_status = wa_status_map.get(wa_result.get("status"))
        wa_line = (
            wa_status(wa_result) if callable(wa_status)
            else wa_status or "❓ واتساب: حالة غير معروفة."
        )
        await update.message.reply_text(wa_line)
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

    if s == "admin_reply_id_input":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        t_clean = t.strip()
        if not t_clean.isdigit():
            await update.message.reply_text(
                "❌ اكتب رقم آيدي صحيح بس (أرقام فقط)."
            )
            return

        context.user_data.update(
            state="admin_reply", reply_to=int(t_clean)
        )
        await update.message.reply_text(
            "💬 اكتب ردك على العميل، وهيتبعت له فورًا."
        )
        return

    if s == "ledger_name_input":
        name = t.strip()
        if not name:
            await update.message.reply_text("❌ اكتب اسم صحيح.")
            return

        uid = update.effective_user.id
        cid = add_ledger_customer(uid, name)
        context.user_data.clear()

        text, kb = ledger_customer_view(cid, uid)
        await update.message.reply_text(
            f"✅ اتسجل \"{name}\".\n\n" + text, reply_markup=kb
        )
        return

    if s == "ledger_amount_input":
        t_clean = t.strip().replace(",", "")
        try:
            amount = float(t_clean)
        except ValueError:
            await update.message.reply_text("❌ اكتب رقم بس.\nمثال: 500")
            return

        if amount <= 0:
            await update.message.reply_text("❌ اكتب مبلغ أكبر من صفر.")
            return

        uid = update.effective_user.id
        cid = context.user_data.get("ledger_customer_id")
        direction = context.user_data.get("ledger_direction")
        if not cid or direction not in ("lah", "alaih") \
                or not get_ledger_customer(cid, uid):
            await update.message.reply_text("ابدأ من قائمة حساباتي.")
            return

        add_ledger_entry(cid, amount, direction)
        context.user_data.clear()

        text, kb = ledger_customer_view(cid, uid)
        await update.message.reply_text("✅ اتسجلت الحركة.\n\n" + text, reply_markup=kb)
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
                text=f"💬 رد من {SHOP_NAME}:\n\n{t}",
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

        if not whatsapp_notifications_enabled():
            # Meta hasn't approved WhatsApp messaging yet — we still
            # save the number so this person is already on the list
            # and gets included automatically the moment the admin
            # flips the switch on, but we're upfront that nothing
            # will arrive on WhatsApp just yet.
            soon_text = (
                "✅ تم تسجيل رقمك بنجاح.\n\n"
                "⏳ خدمة تحديثات السعر على واتساب هتكون متاحة قريبًا "
                "(لسه تحت المراجعة من ميتا). هتوصلك التحديثات على "
                "واتساب تلقائي أول ما تتفعل، من غير ما تحتاج تعمل "
                "حاجة تاني.\n\n"
                "لحد وقتها، الإشعارات على تليجرام بتوصل أول بأول."
            )
            if wa_return == "home":
                await update.message.reply_text(
                    soon_text
                    + "\n\n💎 " + SHOP_NAME + "\n\nاختار من القائمة 👇",
                    reply_markup=home(is_admin(update), True),
                )
                return

            p = latest()
            await update.message.reply_text(
                soon_text + "\n\n" + (price_text(p) if p else ""),
                reply_markup=gold_screen_kb(update.effective_user.id),
            )
            return

        wa_note = (
            "\n\nℹ️ ملحوظة: السعر بيتحدث على واتساب مرتين بس في اليوم "
            "(بعد الساعة 12 الضهر، وبعد الساعة 7 بالليل)، بسبب قيود "
            "شركة ميتا على الرسائل الترويجية. لو عايز تحديثات فورية "
            "أكتر، الإشعارات على تليجرام بتوصل أول بأول من غير أي حد."
        )

        if wa_return == "home":
            await update.message.reply_text(
                "✅ تم تفعيل الإشعارات على تليجرام وواتساب."
                + wa_note
                + "\n\n💎 " + SHOP_NAME + "\n\nاختار من القائمة 👇",
                reply_markup=home(is_admin(update), True),
            )
            return

        p = latest()
        await update.message.reply_text(
            "✅ تم الاشتراك في تحديثات واتساب."
            + wa_note
            + "\n\n" + (price_text(p) if p else ""),
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
                    text="👑 تم إضافتك كأدمن في بوت " + SHOP_NAME + ".\n"
                         "استخدم /start عشان تشوف لوحة التحكم.",
                )
            except Exception as e:
                print("Notify New Admin Error:", repr(e), flush=True)

        await update.message.reply_text(
            "✅ تم إضافة الأدمن." if ok
            else "⚠️ الآيدي ده أدمن بالفعل."
        )
        return

    if s == "custom_notif":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        audience = context.user_data.get("notif_audience", "subscribers")
        context.user_data.clear()

        await update.message.reply_text("⏳ جاري الإرسال...")

        sent, failed = await broadcast_custom_notification(
            context, update.effective_user.id, t, audience=audience
        )

        await update.message.reply_text(
            f"✅ اتبعت الإشعار.\n📤 وصل لـ {sent} شخص"
            + (f" (فشل مع {failed})" if failed else "") + ".",
            reply_markup=notif_menu(),
        )
        return

    if s == "saved_notif_title":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not t.strip():
            await update.message.reply_text("❌ اكتب اسم للرسالة.")
            return

        context.user_data["saved_title"] = t.strip()
        context.user_data["state"] = "saved_notif_body"

        await update.message.reply_text(
            "✍️ دلوقتي اكتب محتوى الرسالة نفسها (اللي هيوصل للعملاء).\n\n"
            "- اكتب نص، أو\n"
            "- ابعت صورة (تقدر تحط تعليق عليها كنص الرسالة)"
        )
        return

    if s == "saved_notif_body":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        title = context.user_data.get("saved_title", "رسالة")
        context.user_data.clear()

        add_saved_notification(update.effective_user.id, title, t)

        await update.message.reply_text(
            f"✅ اتحفظت \"{title}\". تقدر تبعتها وقت ما تحب من "
            "\"💾 رسائل جاهزة\".",
            reply_markup=saved_notif_list_kb(),
        )
        return

    if s == "sched_time_input":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", t):
            await update.message.reply_text(
                "❌ الصيغة غلط. اكتب الموعد بصيغة HH:MM.\nمثال: 05:00"
            )
            return

        context.user_data["sched_time"] = t
        context.user_data["state"] = "sched_body_input"

        await update.message.reply_text(
            "✍️ دلوقتي اكتب نص الإشعار اللي هيتبعت تلقائي كل يوم "
            f"الساعة {t}."
        )
        return

    if s == "sched_body_input":
        if not is_admin(update):
            context.user_data.clear()
            await update.message.reply_text("❌ غير مسموح.")
            return

        if not t.strip():
            await update.message.reply_text("❌ اكتب نص الإشعار.")
            return

        time_str = context.user_data.get("sched_time")
        context.user_data.clear()

        nid = add_scheduled_notification(time_str, t.strip())
        log_action(
            update.effective_user.id, "ADMIN_ADDED_SCHEDULED_NOTIF",
            new_value=t.strip()[:200],
            object_type="scheduled_notification", object_id=nid,
        )

        await update.message.reply_text(
            f"✅ تم جدولة الإشعار — هيتبعت تلقائي كل يوم الساعة "
            f"{time_str} لكل المشتركين.",
            reply_markup=sched_notif_list_kb(),
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
    c = q.data

    if maintenance_mode_on() and not is_admin(update):
        await q.answer(
            "🔧 البوت تحت التحديث دلوقتي، حاول تاني بعد شوية 🙏",
            show_alert=True,
        )
        return

    await q.answer()
    track_user(update)

    if c == "home":
        context.user_data.clear()
        await q.edit_message_text(
            "💎 " + SHOP_NAME + "\n\nاختار من القائمة 👇",
            reply_markup=home(is_admin(update), is_gold_subscribed(update.effective_user.id)),
        )
        return

    if c == "shopstatus":
        st = shop_open_status()

        if st["is_open"]:
            text = (
                "🟢 المحل مفتوح دلوقتي\n\n"
                f"هيقفل الساعة {fmt_hm(st['next_change'])}."
            )
        else:
            text = (
                "🔴 المحل مقفول دلوقتي\n\n"
                f"هيفتح الساعة {fmt_hm(st['next_change'])}."
            )

        text += (
            "\n\n🕐 مواعيد العمل:\n"
            "كل يوم من 11:30 ص لـ 12:30 ص (غير الجمعة)\n"
            "الجمعة من 1:00 م لـ 12:30 ص"
        )

        await q.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    if c == "shopinfo":
        await q.edit_message_text(
            f"📇 {SHOP_NAME}\n\nكل طرق التواصل والروابط:",
            reply_markup=shop_info_kb(),
        )
        return

    # ---- تسجيل عيد الميلاد ----

    if c == "birthdaymenu":
        track_user(update)
        existing = get_birthday(update.effective_user.id)
        if existing:
            bday_str = f"{existing['day']:02d}-{existing['month']:02d}"
            await q.edit_message_text(
                f"🎂 تاريخ ميلادك المسجل: {bday_str}\n\n"
                "هنبعتلك تهنئة في يوم ميلادك كل سنة 💛",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✏️ تغيير التاريخ", callback_data="birthdaychange"
                    )],
                    [InlineKeyboardButton(
                        "🗑 إلغاء التسجيل", callback_data="birthdaydelete"
                    )],
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
                ]),
            )
            return

        auto_month, auto_day = None, None
        try:
            chat = await context.bot.get_chat(update.effective_user.id)
            bd = getattr(chat, "birthdate", None)
            if bd:
                auto_month, auto_day = bd.month, bd.day
        except Exception:
            pass

        if auto_month and auto_day:
            set_birthday(update.effective_user.id, auto_month, auto_day)
            await q.edit_message_text(
                "🎂 لقيت تاريخ ميلادك من تليجرام: "
                f"{auto_day:02d}-{auto_month:02d}\n\n"
                "سجلناه، وهنبعتلك تهنئة في يوم ميلادك كل سنة 💛\n\n"
                "لو مش صح، تقدر تغيّره.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✏️ تغيير التاريخ", callback_data="birthdaychange"
                    )],
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
                ]),
            )
            return

        context.user_data["state"] = "birthday_date_input"
        await q.edit_message_text(
            "🎂 سجّل تاريخ ميلادك\n\n"
            "اكتب اليوم والشهر بصيغة يوم-شهر.\nمثال: 25-12"
        )
        return

    if c == "birthdaychange":
        context.user_data["state"] = "birthday_date_input"
        await q.edit_message_text(
            "✏️ اكتب تاريخ ميلادك الجديد بصيغة يوم-شهر.\nمثال: 25-12"
        )
        return

    if c == "birthdaydelete":
        await q.edit_message_text(
            "⚠️ متأكد عايز تلغي تسجيل تاريخ ميلادك؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🗑 اه، الغيه", callback_data="birthdaydeleteconfirm"
                )],
                [InlineKeyboardButton(
                    "❌ لأ، رجعني", callback_data="birthdaymenu"
                )],
            ]),
        )
        return

    if c == "birthdaydeleteconfirm":
        delete_birthday(update.effective_user.id)
        await q.edit_message_text(
            "✅ اتلغى تسجيل تاريخ ميلادك.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    # ---- تواصل مع الإدارة ----

    if c == "contactadmin":
        track_user(update)
        context.user_data.clear()
        context.user_data["state"] = "contact_admin_input"
        await q.edit_message_text(
            "✍️ اكتب رسالتك وهتوصل للإدارة على طول.\n\n"
            "(استفسار، طلب، شكوى... أي حاجة)"
        )
        return

    # ---- طلب مكالمة ----

    if c == "callrequest":
        track_user(update)
        context.user_data.clear()
        context.user_data["state"] = "call_phone_input"
        await q.edit_message_text(
            "📞 اطلب مكالمة\n\n"
            "اكتب رقم موبايلك وهنكلمك عليه في أقرب وقت.\n"
            "مثال: 01012345678"
        )
        return

    if c == "callqueue":
        if not is_admin(update):
            return

        text, kb = call_queue_view(is_owner(update))
        await q.edit_message_text(text, reply_markup=kb)
        return

    if c.startswith("calldone:"):
        if not is_admin(update):
            return

        rid = int(c.split(":")[1])
        req = get_call_request(rid)
        if not req:
            await q.answer("الطلب ده مش موجود.", show_alert=True)
            return

        mark_call_done(rid)
        await q.answer("✅ تمام، اتشال من القائمة.")

        try:
            await context.bot.send_message(
                chat_id=req["telegram_id"],
                text=(
                    "📞 تمام، اتكلمنا معاك دلوقتي.\n\n"
                    "تقيّم المكالمة؟"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⭐" * n, callback_data=f"callrate:{rid}:{n}"
                    ) for n in range(1, 6)
                ]]),
            )
        except Exception as e:
            print("Call Rating Request Failed:", repr(e), flush=True)

        text, kb = call_queue_view(is_owner(update))
        await q.edit_message_text(text, reply_markup=kb)
        return

    if c.startswith("callrate:"):
        _, rid_s, rating_s = c.split(":")
        rid = int(rid_s)
        rating = int(rating_s)

        req = get_call_request(rid)
        if not req or req["telegram_id"] != update.effective_user.id:
            await q.answer("الطلب ده مش موجود.", show_alert=True)
            return

        set_call_rating(rid, rating)
        await q.edit_message_text(
            "🙏 شكرًا لتقييمك! " + ("⭐" * rating)
        )
        return

    # ---- هدف توفير للذهب ----

    if c == "savegoal":
        track_user(update)
        existing = get_savings_goal(update.effective_user.id)
        if existing:
            p21 = latest()
            monthly_line = ""
            if p21:
                p24, _, _ = calc(p21)
                now_price = p24 * (existing["karat"] / 24)
                current_target = float(existing["weight"]) * now_price
                monthly_now = current_target / existing["months"]
                monthly_line = (
                    f"\n\nبسعر النهاردة، محتاج توفر تقريبًا "
                    f"{round(monthly_now)} ج/شهر عشان توصل للهدف في "
                    f"{existing['months']} شهر."
                )

            await q.edit_message_text(
                "💰 هدفك الحالي:\n\n"
                f"{float(existing['weight'])} جرام عيار {existing['karat']} "
                f"خلال {existing['months']} شهر"
                f"{monthly_line}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✏️ تغيير الهدف", callback_data="savegoalchange"
                    )],
                    [InlineKeyboardButton(
                        "🗑 إلغاء الهدف", callback_data="savegoaldelete"
                    )],
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
                ]),
            )
            return

        context.user_data.clear()
        context.user_data["state"] = "save_weight_input"
        await q.edit_message_text(
            "💰 هدف توفير للذهب\n\n"
            "اكتب الوزن والعيار اللي عايز توفر عشانه، مفصولين بمسافة.\n"
            "مثال: 10 21"
        )
        return

    if c == "savegoalchange":
        context.user_data.clear()
        context.user_data["state"] = "save_weight_input"
        await q.edit_message_text(
            "✏️ اكتب الوزن والعيار الجديد مفصولين بمسافة.\nمثال: 10 21"
        )
        return

    if c == "savegoaldelete":
        await q.edit_message_text(
            "⚠️ متأكد عايز تلغي هدف التوفير؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🗑 اه، الغيه", callback_data="savegoaldeleteconfirm"
                )],
                [InlineKeyboardButton(
                    "❌ لأ، رجعني", callback_data="savegoal"
                )],
            ]),
        )
        return

    if c == "savegoaldeleteconfirm":
        delete_savings_goal(update.effective_user.id)
        await q.edit_message_text(
            "✅ اتلغى هدف التوفير.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
        )
        return

    # ---- حاسبة المصروف الشهري ----

    if c == "budgetmenu":
        track_user(update)
        b = get_budget(update.effective_user.id)

        if not b:
            context.user_data.clear()
            context.user_data["state"] = "budget_salary_input"
            await q.edit_message_text(
                "📒 حاسبة مصروفك الشهري\n\n"
                "اكتب مرتبك الشهري، وهنبدأ نتابعلك أي فلوس تدخل أو "
                "تخرج، ونقولك آخر كل شهر معاك كام.\n\nمثال: 8000"
            )
            return

        text, kb = budget_summary_view(b)
        await q.edit_message_text(text, reply_markup=kb)
        return

    if c == "budgetin" or c == "budgetout":
        b = get_budget(update.effective_user.id)
        if not b:
            await q.answer("سجّل مرتبك الأول.", show_alert=True)
            return

        context.user_data["state"] = "budget_amount_input"
        context.user_data["budget_type"] = "in" if c == "budgetin" else "out"

        await q.edit_message_text(
            "اكتب المبلغ" + (" اللي دخل" if c == "budgetin" else " اللي خرج")
            + ".\nمثال: 500"
        )
        return

    if c == "budgethistory":
        rows = list_budget_transactions(update.effective_user.id, 10)
        if not rows:
            await q.edit_message_text(
                "📊 مفيش أي حركات متسجلة لسه.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ رجوع", callback_data="budgetmenu"
                    )],
                ]),
            )
            return

        lines = ["📊 آخر 10 حركات:\n"]
        for r in rows:
            dt = (
                r["created_at"].strftime("%d/%m %H:%M")
                if hasattr(r["created_at"], "strftime")
                else r["created_at"]
            )
            arrow = "🟢 +" if r["ttype"] == "in" else "🔴 -"
            lines.append(f"{arrow}{round(float(r['amount']))} ج — {dt}")

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ رجوع", callback_data="budgetmenu")],
            ]),
        )
        return

    if c == "budgetchangesalary":
        context.user_data.clear()
        context.user_data["state"] = "budget_salary_input"
        await q.edit_message_text(
            "✏️ اكتب مرتبك الشهري الجديد.\n\n"
            "⚠️ ده هيبدأ دورة شهر جديدة من الأول (الرصيد هيترجع "
            "لقيمة المرتب الجديد).\n\nمثال: 8000"
        )
        return

    # ---- ادعُ صديق ----

    if c == "referral":
        track_user(update)
        u = update.effective_user
        link = f"{BOT_LINK}?start=ref_{u.id}"
        count_row = one(
            "SELECT COUNT(*) AS n FROM Users WHERE referred_by=%s",
            (u.id,),
        )
        count = count_row["n"] if count_row else 0

        await q.edit_message_text(
            "🔗 ادعُ صديق\n\n"
            "ابعت الرابط ده لأصحابك، وكل واحد يدخل من خلاله يتسجل "
            "تلقائي إنه جاله منك:\n\n"
            f"{link}\n\n"
            f"👥 عدد اللي دخلوا من رابطك: {count}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
            ]),
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

    if c == "notifmenu":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        await q.edit_message_text(
            "📢 الإشعارات للمشتركين\n\n"
            "اختار النوع:",
            reply_markup=notif_menu(),
        )
        return

    if c == "schedlist":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        rows = scheduled_notifications()
        await q.edit_message_text(
            "⏰ الإشعارات المجدولة اليومية\n\n"
            + (
                "بتتبعت تلقائي كل يوم في ميعادها لكل المشتركين، "
                "من غير ما تكتبها كل مرة."
                if rows else
                "لسه معملتش أي إشعار مجدول. دوس (➕) عشان تضيف واحد "
                "(زي إشعار الفجر أو الصبح أو آخر اليوم)."
            ),
            reply_markup=sched_notif_list_kb(),
        )
        return

    if c == "schedadd":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data["state"] = "sched_time_input"

        await q.edit_message_text(
            "⏰ في أي ساعة يتبعت الإشعار كل يوم؟\n\n"
            "اكتب الوقت بصيغة 24 ساعة (HH:MM)\n"
            "مثال: 05:00 لأذان الفجر، أو 21:00 لآخر اليوم"
        )
        return

    if c.startswith("schedopen:"):
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        nid = int(c.split(":")[1])
        n = scheduled_notification(nid)

        if not n:
            await q.edit_message_text(
                "❌ الإشعار ده مش موجود.", reply_markup=sched_notif_list_kb()
            )
            return

        status = "🟢 مفعّل" if n.get("enabled") else "🔴 متوقف"
        await q.edit_message_text(
            f"⏰ الميعاد: {n['time_str']}\n"
            f"الحالة: {status}\n\n"
            f"النص:\n{n['body']}",
            reply_markup=sched_notif_item_kb(nid),
        )
        return

    if c.startswith("schedtoggle:"):
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        nid = int(c.split(":")[1])
        toggle_scheduled_notification(nid)
        log_action(
            update.effective_user.id, "ADMIN_TOGGLED_SCHEDULED_NOTIF",
            object_type="scheduled_notification", object_id=nid,
        )

        n = scheduled_notification(nid)
        status = "🟢 مفعّل" if n and n.get("enabled") else "🔴 متوقف"
        await q.edit_message_text(
            f"⏰ الميعاد: {n['time_str']}\n"
            f"الحالة: {status}\n\n"
            f"النص:\n{n['body']}",
            reply_markup=sched_notif_item_kb(nid),
        )
        return

    if c.startswith("scheddel:"):
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        nid = int(c.split(":")[1])
        ok = delete_scheduled_notification(nid)
        log_action(
            update.effective_user.id, "ADMIN_DELETED_SCHEDULED_NOTIF",
            object_type="scheduled_notification", object_id=nid,
            status="success" if ok else "failed",
        )

        rows = scheduled_notifications()
        await q.edit_message_text(
            "🗑 تم حذف الإشعار المجدول." if ok else "❌ مقدرتش أحذفه.",
            reply_markup=sched_notif_list_kb(),
        )
        return

    if c == "customnotif":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        sub_count = gold_subscriber_count()
        all_count = one("SELECT COUNT(*) c FROM Users")
        all_count = all_count["c"] if all_count else 0

        await q.edit_message_text(
            "✍️ إشعار سريع\n\nتبعته لمين؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"🔔 المشتركين بس ({sub_count})",
                    callback_data="customnotifaud:subscribers",
                )],
                [InlineKeyboardButton(
                    f"👥 كل مستخدمي البوت ({all_count})",
                    callback_data="customnotifaud:all",
                )],
                [InlineKeyboardButton("❌ إلغاء", callback_data="notifmenu")],
            ]),
        )
        return

    if c.startswith("customnotifaud:"):
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        audience = c.split(":")[1]
        count = (
            one("SELECT COUNT(*) c FROM Users")["c"]
            if audience == "all" else gold_subscriber_count()
        )

        context.user_data.clear()
        context.user_data.update(
            state="custom_notif", notif_audience=audience
        )

        await q.edit_message_text(
            f"✍️ اكتب الإشعار اللي عايز تبعته ({count} شخص).\n\n"
            "- اكتب نص، أو\n"
            "- ابعت صورة (تقدر تحط تعليق عليها كنص الإشعار)\n\n"
            "⚠️ ده هيتبعت فوراً ومش هيتحفظ - منفصل تماماً عن تنبيهات "
            "السعر والمنتجات التلقائية.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="notifmenu")]
            ]),
        )
        return

    if c == "savedlist":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        rows = saved_notifications()
        await q.edit_message_text(
            "💾 الرسائل الجاهزة\n\n"
            + (
                f"عندك {len(rows)} رسالة محفوظة، دوس على أي واحدة "
                "عشان تبعتها أو تحذفها."
                if rows else
                "لسه معملتش رسائل محفوظة. دوس \"➕ حفظ رسالة جديدة\" "
                "عشان تبدأ."
            ),
            reply_markup=saved_notif_list_kb(),
        )
        return

    if c == "savedadd":
        if not is_admin(update):
            await q.answer("❌ غير مسموح.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data["state"] = "saved_notif_title"

        await q.edit_message_text(
            "💾 اكتب اسم قصير للرسالة عشان تعرفها بيه بعدين "
            "(الاسم ده مش هيتبعت للعميل، بس لتسهيل الاختيار عليك).\n\n"
            "مثال: عرض العيد"
        )
        return

    if c.startswith("savedopen:"):
        if not is_admin(update):
            return

        nid = int(c.split(":")[1])
        n = get_saved_notification(nid)

        if not n:
            await q.edit_message_text(
                "⚠️ الرسالة دي مش موجودة (يمكن اتحذفت).",
                reply_markup=saved_notif_list_kb(),
            )
            return

        preview = (n["body"] or "")[:300]
        await q.edit_message_text(
            f"💾 {n['title']}\n\n"
            f"{'📸 فيها صورة\n\n' if n['photo_id'] else ''}"
            f"{preview}",
            reply_markup=saved_notif_item_kb(nid),
        )
        return

    if c.startswith("savedsend:"):
        if not is_admin(update):
            return

        nid = int(c.split(":")[1])
        n = get_saved_notification(nid)

        if not n:
            await q.edit_message_text(
                "⚠️ الرسالة دي مش موجودة.",
                reply_markup=saved_notif_list_kb(),
            )
            return

        await q.edit_message_text("⏳ جاري الإرسال...")

        sent, failed = await broadcast_custom_notification(
            context, update.effective_user.id, n["body"],
            photo_id=n["photo_id"],
        )

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=f"✅ اتبعتت \"{n['title']}\".\n📤 وصلت لـ {sent} شخص"
                 + (f" (فشل مع {failed})" if failed else "") + ".",
            reply_markup=saved_notif_list_kb(),
        )
        return

    if c.startswith("saveddel:"):
        if not is_admin(update):
            return

        nid = int(c.split(":")[1])
        ok = delete_saved_notification(nid)

        if ok:
            log_action(
                update.effective_user.id, "ADMIN_DELETED_SAVED_NOTIFICATION",
                object_type="saved_notification", object_id=nid,
            )

        rows = saved_notifications()
        await q.edit_message_text(
            ("✅ تم الحذف.\n\n" if ok else "⚠️ مش موجودة أصلاً.\n\n")
            + (
                f"عندك {len(rows)} رسالة محفوظة."
                if rows else "لسه معملتش رسائل محفوظة."
            ),
            reply_markup=saved_notif_list_kb(),
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
            "💍 منتجات " + SHOP_NAME + "\n\nاختار القسم:",
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

            buttons_rows = product_display_kb(p, update.effective_user.id)

            try:
                await q.message.reply_photo(
                    photo=p["Photo_id"],
                    caption="\n".join(parts) or None,
                    reply_markup=buttons_rows,
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

    if c == "testwa":
        if not is_admin(update):
            return

        if not WHATSAPP_PHONE_NUMBER_ID:
            await q.edit_message_text(
                "❌ WHATSAPP_PHONE_NUMBER_ID غير موجود في Railway Variables.",
                reply_markup=gold_menu(),
            )
            return

        p21 = latest()
        if not p21:
            await q.edit_message_text(
                "❌ لا يوجد سعر ذهب محفوظ للاختبار بيه.",
                reply_markup=gold_menu(),
            )
            return

        numbers = whatsapp_subscriber_numbers()
        if not numbers:
            await q.edit_message_text(
                "⚠️ مفيش حد مشترك في واتساب حالياً عشان نختبر عليه.\n"
                "اشترك برقمك الأول من القائمة الرئيسية.",
                reply_markup=gold_menu(),
            )
            return

        await q.edit_message_text(
            f"🧪 جاري إرسال اختبار لـ {len(numbers)} رقم "
            "(من غير التقيد بمواعيد 12/7 — ده اختبار يدوي بس)..."
        )

        p24, p21c, p18 = calc(p21)
        lines = []

        for number in numbers:
            result = await whatsapp_send_template(number, p24, p21c, p18)
            if result.get("ok"):
                lines.append(f"✅ {number} — نجح (id: {result.get('post_id')})")
            else:
                lines.append(f"❌ {number} — فشل: {result.get('message')}")

        log_action(
            update.effective_user.id, "ADMIN_TESTED_WHATSAPP",
            new_value="\n".join(lines)[:2000],
        )

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="🧪 نتيجة اختبار واتساب:\n\n" + "\n".join(lines),
            reply_markup=gold_menu(),
        )
        return

    if c == "resetwa":
        if not is_admin(update):
            return

        # Clears today's "already sent" markers for both the
        # afternoon and evening WhatsApp broadcast slots, so the
        # next price update triggers a real send instead of being
        # silently skipped as "already sent today".
        for slot in ("afternoon", "evening"):
            set_setting(f"wa_slot_{slot}_sent_date", "")

        log_action(
            update.effective_user.id, "ADMIN_RESET_WHATSAPP_SLOTS",
        )

        await q.edit_message_text(
            "✅ تم إعادة ضبط جدول واتساب.\n"
            "التحديث الجاي للسعر هيتبعت على واتساب عادي "
            "(حسب فترة الظهر/المسا).",
            reply_markup=gold_menu(),
        )
        return

    if c == "togglewa":
        if not is_admin(update):
            return

        currently_on = whatsapp_notifications_enabled()
        new_state = not currently_on
        set_setting("wa_notifications_enabled", "1" if new_state else "0")

        log_action(
            update.effective_user.id, "ADMIN_TOGGLED_WHATSAPP_SIGNUPS",
            new_value="on" if new_state else "off",
        )

        if new_state:
            # Just turned ON — let existing Telegram subscribers know
            # WhatsApp is live now, since they were told "coming soon"
            # while it was off.
            ids = gold_subscriber_ids()
            sent = 0
            for uid in ids:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=(
                            "🎉 خدمة تحديثات السعر على واتساب اشتغلت "
                            "دلوقتي!\n\n"
                            "تقدر تشترك من قائمة 💎 أسعار الذهب."
                        ),
                    )
                    sent += 1
                except Exception:
                    pass
                await asyncio.sleep(0.05)

            await q.edit_message_text(
                f"🟢 تم تفعيل الاشتراك في واتساب.\n"
                f"اتبعت إعلان لـ {sent} مشترك على تليجرام.",
                reply_markup=gold_menu(),
            )
        else:
            await q.edit_message_text(
                "🔴 تم إيقاف الاشتراك في واتساب.\n"
                "أي عميل هيحاول يشترك هيتقاله إن الخدمة قريبًا.",
                reply_markup=gold_menu(),
            )
        return

    if c.startswith("setselldiscount:"):
        if not is_admin(update):
            return

        karat = int(c.split(":")[1])
        context.user_data.clear()
        context.user_data.update(
            state="sell_discount_input", discount_karat=karat,
        )

        await q.edit_message_text(
            f"💰 اكتب قيمة الخصم الجديدة (بالجنيه للجرام) اللي "
            f"المحل بياخده لما يشتري ذهب عيار {karat} مشغولات من "
            "العميل.\n\n"
            f"القيمة الحالية: {sell_discount_per_gram(karat)} جنيه/جرام\n"
            "مثال: 100"
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

    if c.startswith("prodwa:"):
        pid = int(c.split(":")[1])
        inc_product_counter(pid, "whatsapp_clicks")
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="💬 تواصل معانا على واتساب بخصوص المنتج ده:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("فتح واتساب", url=WHATSAPP)],
            ]),
        )
        return

    # ---- المفضلة ----

    if c.startswith("favtoggle:"):
        parts_c = c.split(":")
        pid = int(parts_c[1])
        p = product(pid)

        if not p:
            await q.answer("المنتج ده مش موجود.", show_alert=True)
            return

        uid = update.effective_user.id
        if is_favorite(uid, pid):
            remove_favorite(uid, pid)
            await q.answer("💔 اتشال من المفضلة.")
        else:
            add_favorite(uid, pid)
            await q.answer("⭐ اتضاف للمفضلة!")

        try:
            await q.edit_message_reply_markup(
                reply_markup=product_display_kb(p, uid)
            )
        except Exception:
            pass
        return

    if c == "favlist":
        track_user(update)
        favs = list_favorites(update.effective_user.id)

        if not favs:
            await q.edit_message_text(
                "⭐ المفضلة\n\n"
                "مفيش منتجات في المفضلة لسه.\n"
                "تقدر تضيف أي منتج يعجبك من قائمة 💍 المنتجات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "💍 المنتجات", callback_data="products"
                    )],
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
                ]),
            )
            return

        await q.edit_message_text(f"⭐ المفضلة عندك ({len(favs)})")

        for p in favs:
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

            try:
                await context.bot.send_photo(
                    chat_id=q.message.chat_id,
                    photo=p["Photo_id"],
                    caption="\n".join(parts) or None,
                    reply_markup=product_display_kb(
                        p, update.effective_user.id
                    ),
                )
            except Exception as e:
                print("Favorites Display Error:", repr(e), flush=True)
        return

    # ---- تحليل المنتجات (Leads + Conversion) ----

    if c == "prodanalytics":
        if not is_admin(update):
            return

        today_leads = many("""
            SELECT object_id AS pid, COUNT(*) AS cnt,
                   MAX(created_at) AS last_at
            FROM AdminLogs
            WHERE action='USER_INQUIRY'
              AND created_at >= CURDATE()
            GROUP BY object_id
            ORDER BY cnt DESC
            LIMIT 5
        """)

        lines = ["🔥 أكتر المنتجات عليها استفسارات النهاردة\n"]
        if today_leads:
            for r in today_leads:
                p = product(r["pid"])
                name = p["name"] if p and p["name"] else f"#{r['pid']}"
                last_time = (
                    r["last_at"].strftime("%H:%M")
                    if hasattr(r["last_at"], "strftime") else r["last_at"]
                )
                lines.append(
                    f"• {name} — {r['cnt']} استفسار (آخرهم {last_time})"
                )
        else:
            lines.append("لا يوجد استفسارات النهاردة لسه.")

        top_funnel = many("""
            SELECT id, name, views_count, inquiries_count, whatsapp_clicks
            FROM Products
            WHERE views_count > 0
            ORDER BY views_count DESC
            LIMIT 5
        """)

        lines.append("\n📊 قمع التحويل (Conversion) — الأكتر مشاهدة\n")
        if top_funnel:
            for p in top_funnel:
                name = p["name"] or f"#{p['id']}"
                v = p["views_count"]
                i = p["inquiries_count"]
                w = p["whatsapp_clicks"]
                i_pct = f"{(i / v * 100):.0f}%" if v else "0%"
                w_pct = f"{(w / v * 100):.0f}%" if v else "0%"
                lines.append(
                    f"• {name}\n"
                    f"  👁 {v} → 📩 {i} ({i_pct}) → 💬 {w} ({w_pct})"
                )
        else:
            lines.append("لا توجد بيانات مشاهدات كافية لسه.")

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    # ---- عمليات فشلت اليوم ----

    if c == "failedops":
        if not is_admin(update):
            return

        rows = many("""
            SELECT platform, error, content_snippet, created_at
            FROM PublishLogs
            WHERE status='failed' AND created_at >= CURDATE()
            ORDER BY created_at DESC
            LIMIT 15
        """)

        if not rows:
            await q.edit_message_text(
                "✅ مفيش عمليات فشلت النهاردة.",
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        PLATFORM_LABELS = {
            "auto_telegram": "📱 تليجرام (تلقائي)",
            "auto_facebook": "📘 فيسبوك (تلقائي)",
            "telegram": "📱 تليجرام",
            "facebook": "📘 فيسبوك",
            "instagram": "📸 إنستجرام",
        }

        lines = [f"❌ عمليات فشلت النهاردة ({len(rows)})\n"]
        for r in rows:
            plat = PLATFORM_LABELS.get(r["platform"], r["platform"])
            t_str = (
                r["created_at"].strftime("%H:%M")
                if hasattr(r["created_at"], "strftime") else r["created_at"]
            )
            snippet = (r["content_snippet"] or "").strip()
            err = (r["error"] or "غير معروف").strip()
            lines.append(
                f"• {plat} — {t_str}\n"
                f"  المحتوى: {snippet[:60] or '-'}\n"
                f"  السبب: {err[:150]}"
            )

        lines.append(
            "\nملحوظة: مفيش زرار \"إعادة محاولة\" تلقائي هنا، لأن "
            "المنشورات (خصوصًا اللي فيها صور) مش متسجلة كاملة "
            "بالتفصيل الكافي للإرسال تاني تلقائيًا. لو عايز تعيد أي "
            "منشور من دول، اعمله يدوي من نفس المكان اللي نشرته منه."
        )

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    # ---- منتج اليوم ----

    if c == "potdmenu":
        if not is_admin(update):
            return

        today_str = datetime.now(TZ).strftime("%Y-%m-%d")
        current_text = "مفيش منتج متحدد النهاردة لسه."
        if get_setting("potd_date") == today_str:
            pid = get_setting("potd_product_id")
            p = product(int(pid)) if pid else None
            if p:
                pname = p["name"] or f"#{p['id']}"
                current_text = f"منتج اليوم الحالي: {pname}"

        await q.edit_message_text(
            f"🔥 منتج اليوم\n\n{current_text}\n\n"
            "كل يوم الساعة 10:30 الصبح، البوت بيختار تلقائي المنتج "
            "الأكتر تفاعلًا وينشره على تليجرام وفيسبوك وإنستجرام "
            "(لو مفيش حد مختار يدوي قبلها).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✏️ اختار منتج يدوي دلوقتي", callback_data="potdpick"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    if c == "potdpick":
        if not is_admin(update):
            return

        ps = [p for p in all_products() if p.get("Photo_id")]
        if not ps:
            await q.edit_message_text(
                "💍 لا توجد منتجات بصور لاختيارها.",
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        await q.edit_message_text(
            "✏️ اختار منتج اليوم:",
            reply_markup=product_pick_kb(ps, 0, "potdset", "potdmenu"),
        )
        return

    if c.startswith("potdsetp:"):
        if not is_admin(update):
            return

        page = int(c.split(":")[1])
        ps = [p for p in all_products() if p.get("Photo_id")]

        await q.edit_message_text(
            "✏️ اختار منتج اليوم:",
            reply_markup=product_pick_kb(ps, page, "potdset", "potdmenu"),
        )
        return

    if c.startswith("potdset:"):
        if not is_admin(update):
            return

        pid = int(c.split(":")[1])
        await q.edit_message_text("⏳ جاري نشر منتج اليوم...")

        result = await publish_product_of_day(context, pid)
        if not result.get("ok"):
            await q.edit_message_text(
                f"❌ {result.get('message', 'حصل خطأ.')}",
                reply_markup=admin_menu(owner=is_owner(update)),
            )
            return

        await q.edit_message_text(
            "✅ اتنشر منتج اليوم:\n\n"
            f"📢 تليجرام (قناة): {'✅' if result['tg_ok'] else '❌'}\n"
            f"📩 رسائل مباشرة: {result['dm_sent']} مشترك\n"
            f"📘 فيسبوك: {'✅' if result['fb_ok'] else '❌'}\n"
            f"📸 إنستجرام: {'✅' if result['ig_ok'] else '❌'}",
            reply_markup=admin_menu(owner=is_owner(update)),
        )
        return

    # ---- وضع الصيانة ----

    if c == "maintmenu":
        if not is_admin(update):
            return

        on = maintenance_mode_on()
        status_line = (
            "🔴 البوت تحت الصيانة دلوقتي — العملاء بيشوفوا رسالة "
            "تحديث بس."
            if on else
            "🟢 البوت شغال عادي دلوقتي."
        )

        await q.edit_message_text(
            f"🔧 وضع الصيانة\n\n{status_line}\n\n"
            "لما تفعّل وضع الصيانة، أي عميل (غيرك انت) هيشوف رسالة "
            "\"البوت تحت التحديث\" بدل أي حاجة تانية، لحد ما توقفه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🟢 رجّع البوت يشتغل" if on else "🔴 وقف البوت مؤقتًا",
                    callback_data="mainttoggle",
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    if c == "mainttoggle":
        if not is_admin(update):
            return

        on = maintenance_mode_on()
        set_setting("maintenance_mode", "0" if on else "1")
        log_action(
            update.effective_user.id, "ADMIN_TOGGLE_MAINTENANCE",
            new_value="off" if on else "on",
        )

        status_line = (
            "🟢 البوت شغال عادي دلوقتي."
            if on else
            "🔴 البوت تحت الصيانة دلوقتي — العملاء بيشوفوا رسالة "
            "تحديث بس."
        )

        await q.edit_message_text(
            f"🔧 وضع الصيانة\n\n{status_line}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🟢 رجّع البوت يشتغل" if not on else "🔴 وقف البوت مؤقتًا",
                    callback_data="mainttoggle",
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    if c == "phone":
        await q.edit_message_text(
            f"📞 {SHOP_NAME}\n\n{PHONE}\n\nللتواصل المباشر:",
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

    # =====================================================
    # "احسب دهبك" — customer-facing buy/sell price calculator
    # =====================================================

    if c == "calcshare":
        text = context.user_data.get("calc_share_text")
        if not text:
            await q.answer(
                "النتيجة انتهت، احسب تاني من فضلك.", show_alert=True
            )
            return

        await context.bot.send_message(chat_id=q.message.chat_id, text=text)
        return

    if c == "calcgold":
        track_user(update)

        last = get_last_calc(update.effective_user.id)
        k = []
        if last:
            mode_label = {
                "buy": "شراء", "sell": "بيع", "sell_bullion": "بيع سبيكة",
            }.get(last["last_calc_mode"], last["last_calc_mode"])
            k.append([InlineKeyboardButton(
                f"🔁 كرر آخر حسبة ({mode_label} - عيار "
                f"{last['last_calc_karat']} - {last['last_calc_weight']} جم)",
                callback_data="calcrepeat",
            )])

        k += [
            [InlineKeyboardButton(
                "🛒 هتشتري", callback_data="calcmode:buy"
            )],
            [InlineKeyboardButton(
                "💰 هتبيع", callback_data="calcmode:sell"
            )],
            [InlineKeyboardButton(
                "⚖️ قارن بين قطعتين", callback_data="calccompare"
            )],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="gold")],
        ]

        await q.edit_message_text(
            "🧮 احسب دهبك\n\nهتشتري ولا هتبيع؟",
            reply_markup=InlineKeyboardMarkup(k),
        )
        return

    if c == "calcrepeat":
        last = get_last_calc(update.effective_user.id)
        if not last:
            await q.answer("مفيش حسبة سابقة.", show_alert=True)
            return

        ok, text, total, per_gram = compute_calc_result(
            last["last_calc_mode"], last["last_calc_karat"],
            float(last["last_calc_weight"]),
        )
        if ok:
            context.user_data["calc_share_text"] = build_share_text(text)
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if c == "calccompare":
        context.user_data.clear()
        context.user_data["calc_compare_active"] = True

        await q.edit_message_text(
            "⚖️ قارن بين قطعتين\n\nالقطعتين شراء ولا بيع؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🛒 هتشتري", callback_data="calcmode:buy"
                )],
                [InlineKeyboardButton(
                    "💰 هتبيع", callback_data="calcmode:sell"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="calcgold")],
            ]),
        )
        return

    # ---- استبدال قطعة قديمة بجديدة ----

    if c == "calctrade":
        track_user(update)
        context.user_data.clear()

        await q.edit_message_text(
            "🔄 استبدال قديم بجديد\n\n"
            "الأول، اختار عيار القطعة القديمة اللي هتديها:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "عيار 24", callback_data="calctradek:24"
                )],
                [InlineKeyboardButton(
                    "عيار 21", callback_data="calctradek:21"
                )],
                [InlineKeyboardButton(
                    "عيار 18", callback_data="calctradek:18"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="gold")],
            ]),
        )
        return

    if c.startswith("calctradek:"):
        karat = int(c.split(":")[1])
        mode = "sell_bullion" if karat == 24 else "sell"

        context.user_data.clear()
        context.user_data.update(
            state="trade_weight_input", trade_karat=karat, trade_mode=mode,
        )
        await q.edit_message_text(
            "⚖️ اكتب وزن القطعة القديمة بالجرام.\nمثال: 5 أو 3.5"
        )
        return

    # ---- بكام أقدر أشتري؟ (حاسبة الميزانية) ----

    if c == "calcbudget":
        track_user(update)
        context.user_data.clear()

        await q.edit_message_text(
            "💵 بكام أقدر أشتري؟\n\nاختار العيار اللي عايز تحسب بيه:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "عيار 24", callback_data="calcbudgetk:24"
                )],
                [InlineKeyboardButton(
                    "عيار 21", callback_data="calcbudgetk:21"
                )],
                [InlineKeyboardButton(
                    "عيار 18", callback_data="calcbudgetk:18"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="gold")],
            ]),
        )
        return

    if c.startswith("calcbudgetk:"):
        karat = int(c.split(":")[1])
        context.user_data.clear()
        context.user_data.update(
            state="budget_amount_input", budget_karat=karat,
        )
        await q.edit_message_text(
            "💰 اكتب الميزانية اللي معاك بالجنيه.\nمثال: 5000"
        )
        return

    # ---- سعر آخر 7 أيام ----

    if c == "pricehist7":
        track_user(update)
        st = gold_period_stats(7)

        if not st:
            await q.edit_message_text(
                "📊 لسه مفيش بيانات كفاية لعرض آخر 7 أيام.",
                reply_markup=gold_screen_kb(update.effective_user.id),
            )
            return

        sign = "+" if st["change"] >= 0 else ""
        arrow = "📈" if st["change"] > 0 else (
            "📉" if st["change"] < 0 else "➡️"
        )

        await q.edit_message_text(
            "📊 حركة سعر عيار 21 آخر 7 أيام\n\n"
            f"أعلى سعر: {st['high']} جنيه\n"
            f"أقل سعر: {st['low']} جنيه\n\n"
            f"سعر بداية الفترة: {st['first']} جنيه\n"
            f"السعر دلوقتي: {st['last']} جنيه\n\n"
            f"{arrow} التغيّر: {sign}{st['change']} جنيه "
            f"({sign}{st['pct']}%)",
            reply_markup=gold_screen_kb(update.effective_user.id),
        )
        return

    # ---- تذكير مناسبة ----

    if c == "addoccasion":
        track_user(update)
        context.user_data.clear()
        context.user_data["state"] = "occasion_label_input"

        await q.edit_message_text(
            "🎁 اكتب اسم المناسبة اللي عايز نفكّرك بيها.\n\n"
            "مثال: عيد ميلاد ماما، خطوبة أختي"
        )
        return

    if c.startswith("occsame:"):
        rid = int(c.split(":")[1])
        r = get_occasion_reminder(rid)

        if not r or r["telegram_id"] != update.effective_user.id:
            await q.answer("التذكير ده مش موجود.", show_alert=True)
            return

        await q.edit_message_text(
            f"👍 تمام، هفكّرك بـ\"{r['label']}\" تاني السنة الجاية "
            f"({r['month']:02d}-{r['day']:02d})."
        )
        return

    if c.startswith("occrenew:"):
        rid = int(c.split(":")[1])
        r = get_occasion_reminder(rid)

        if not r or r["telegram_id"] != update.effective_user.id:
            await q.answer("التذكير ده مش موجود.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data.update(
            state="occasion_renew_date_input", occasion_renew_id=rid,
        )
        await q.edit_message_text(
            f"📅 اكتب الميعاد الجديد لتذكير \"{r['label']}\" "
            "بصيغة يوم-شهر (DD-MM).\nمثال: 20-11"
        )
        return

    if c.startswith("occcancel:"):
        rid = int(c.split(":")[1])
        r = get_occasion_reminder(rid)

        if not r or r["telegram_id"] != update.effective_user.id:
            await q.answer("التذكير ده مش موجود.", show_alert=True)
            return

        delete_occasion_reminder(rid)
        await q.edit_message_text(
            f"🗑 تم إلغاء تذكير \"{r['label']}\"."
        )
        return

    # ---- حاسبة الزكاة ----

    if c == "zakatcalc":
        track_user(update)
        context.user_data.clear()
        context.user_data.update(state="zakat_piece_input", zakat_pieces=[])

        await q.edit_message_text(
            "🕌 حاسبة الزكاة\n\n"
            "اكتب وزن أول قطعة وعيارها مفصولين بمسافة.\n"
            "مثال: 50 21\n\n"
            "(لو عندك قطع بأعيرة مختلفة، تقدر تضيفهم كلهم واحدة "
            "واحدة وهنجمعهم)"
        )
        return

    if c == "zakatmore":
        if "zakat_pieces" not in context.user_data:
            await q.answer("ابدأ حساب الزكاة من الأول.", show_alert=True)
            return

        context.user_data["state"] = "zakat_piece_input"
        await q.edit_message_text(
            "➕ اكتب وزن القطعة التانية وعيارها مفصولين بمسافة.\n"
            "مثال: 20 18"
        )
        return

    if c == "zakatfinish":
        pieces = context.user_data.get("zakat_pieces")
        if not pieces:
            await q.answer("ابدأ حساب الزكاة من الأول.", show_alert=True)
            return

        context.user_data.clear()

        p21 = latest()
        if not p21:
            await q.edit_message_text(
                "💎 لم يتم تحديث أسعار الذهب حتى الآن."
            )
            return

        p24, _, _ = calc(p21)
        total_equiv = sum(w * (k / 24) for w, k in pieces)
        lines = "\n".join(
            f"- {w} جرام عيار {k} → {w * (k / 24):.2f} جرام عيار 24"
            for w, k in pieces
        )

        if total_equiv >= ZAKAT_NISAB_GRAMS_24K:
            value = round(total_equiv * p24)
            zakat = round(value * ZAKAT_RATE)
            result = (
                f"✅ وصلت للنصاب ({ZAKAT_NISAB_GRAMS_24K} جرام عيار 24)\n\n"
                f"قيمة الذهب (بسعر عيار 24: {p24} ج/جرام): "
                f"{value} جنيه\n\n"
                f"🕌 الزكاة المستحقة (2.5%): {zakat} جنيه"
            )
        else:
            result = (
                f"❌ إجمالي وزنك المكافئ أقل من النصاب "
                f"({ZAKAT_NISAB_GRAMS_24K} جرام عيار 24)، "
                "فمفيش زكاة واجبة عليك حاليًا."
            )

        zakat_text = (
            "🕌 حاسبة الزكاة\n\n"
            f"القطع:\n{lines}\n\n"
            f"إجمالي الوزن المكافئ (عيار 24): {total_equiv:.2f} جرام\n\n"
            f"{result}\n\n{ZAKAT_DISCLAIMER}"
        )
        context.user_data["calc_share_text"] = build_share_text(zakat_text)
        await q.edit_message_text(
            zakat_text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    # ---- تحويل عيار ----

    if c == "karatconvert":
        track_user(update)
        context.user_data.clear()
        context.user_data["state"] = "karat_convert_input"

        await q.edit_message_text(
            "⚖️ تحويل عيار\n\n"
            "اكتب الوزن والعيار الحالي مفصولين بمسافة.\n"
            "مثال: 50 21"
        )
        return

    if c.startswith("kctarget:"):
        target_raw = c.split(":")[1]
        weight = context.user_data.get("kc_weight")
        karat = context.user_data.get("kc_karat")

        if weight is None or karat is None:
            await q.answer("ابدأ التحويل من الأول.", show_alert=True)
            return

        if target_raw == "custom":
            context.user_data["state"] = "karat_convert_target_input"
            await q.edit_message_text("✍️ اكتب رقم العيار اللي عايز تحول له (1-24):")
            return

        target_karat = int(target_raw)
        await send_karat_conversion_result(
            update, context, weight, karat, target_karat, edit=True
        )
        return

    if c == "karatconvert_again":
        weight = context.user_data.get("kc_weight")
        karat = context.user_data.get("kc_karat")

        if weight is None or karat is None:
            await q.answer("ابدأ التحويل من الأول.", show_alert=True)
            return

        await q.edit_message_text(
            f"القطعة: {weight} جرام عيار {karat}\n\nعايز تحولها لعيار كام؟",
            reply_markup=karat_target_kb(),
        )
        return

    # ---- تتبع الاستثمار ----

    if c == "invtrack":
        track_user(update)
        await q.edit_message_text(
            "💰 تتبع استثمارك\n\n"
            "سجّل عمليات شرائك للدهب، وتابع قيمتها دلوقتي مقارنة "
            "بيوم ما اشتريتها.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ سجّل عملية شراء", callback_data="invadd"
                )],
                [InlineKeyboardButton(
                    "📊 استثماراتي", callback_data="invlist"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="gold")],
            ]),
        )
        return

    if c == "invadd":
        context.user_data.clear()
        context.user_data["state"] = "inv_weight_input"
        await q.edit_message_text(
            "➕ سجّل عملية شراء\n\n"
            "اكتب الوزن والعيار مفصولين بمسافة.\nمثال: 20 21"
        )
        return

    if c == "invlist":
        rows = list_investments(update.effective_user.id)
        if not rows:
            await q.edit_message_text(
                "مفيش عندك أي عمليات شراء متسجلة لسه.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "➕ سجّل عملية شراء", callback_data="invadd"
                    )],
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="invtrack")],
                ]),
            )
            return

        p21 = latest()
        if not p21:
            await q.edit_message_text(
                "💎 لم يتم تحديث أسعار الذهب حتى الآن."
            )
            return
        p24, _, _ = calc(p21)

        blocks = []
        total_cost = 0
        total_now = 0
        kb_rows = []
        for r in rows:
            weight = float(r["weight"])
            karat = r["karat"]
            buy_price = float(r["buy_price_per_gram"])
            now_price = p24 * (karat / 24)

            cost = weight * buy_price
            now_val = weight * now_price
            diff = now_val - cost
            pct = (diff / cost * 100) if cost else 0
            total_cost += cost
            total_now += now_val

            bd = r["buy_date"]
            bd_str = bd.strftime("%Y-%m-%d") if hasattr(bd, "strftime") else bd

            arrow = "📈" if diff >= 0 else "📉"
            blocks.append(
                f"🔸 {weight} جرام عيار {karat} — اشتريتها {bd_str}\n"
                f"سعر الشراء: {round(buy_price)} ج/جرام "
                f"({round(cost)} ج)\n"
                f"القيمة دلوقتي: {round(now_price)} ج/جرام "
                f"({round(now_val)} ج)\n"
                f"{arrow} {'ربح' if diff >= 0 else 'خسارة'}: "
                f"{round(abs(diff))} ج ({pct:+.1f}%)"
            )
            kb_rows.append([InlineKeyboardButton(
                f"🗑 حذف: {weight}جم عيار{karat} ({bd_str})",
                callback_data=f"invdel:{r['id']}",
            )])

        total_diff = total_now - total_cost
        total_pct = (total_diff / total_cost * 100) if total_cost else 0
        summary = (
            f"\n\n———————————\n"
            f"الإجمالي: اشتريت بـ {round(total_cost)} ج، "
            f"بتساوي دلوقتي {round(total_now)} ج\n"
            f"{'📈 ربح' if total_diff >= 0 else '📉 خسارة'} إجمالي: "
            f"{round(abs(total_diff))} ج ({total_pct:+.1f}%)"
        )

        text = "📊 استثماراتك في الدهب\n\n" + "\n\n".join(blocks) + summary
        kb_rows.append([InlineKeyboardButton(
            "➕ سجّل عملية شراء", callback_data="invadd"
        )])
        kb_rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="invtrack")])

        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))
        return

    if c.startswith("invdel:"):
        iid = int(c.split(":")[1])
        entry = get_investment(iid)
        if not entry or entry["telegram_id"] != update.effective_user.id:
            await q.answer("العملية دي مش موجودة.", show_alert=True)
            return

        await q.edit_message_text(
            f"⚠️ متأكد عايز تحذف: {float(entry['weight'])} جرام "
            f"عيار {entry['karat']}؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🗑 اه، احذفها", callback_data=f"invdelconfirm:{iid}"
                )],
                [InlineKeyboardButton("❌ لأ، رجعني", callback_data="invlist")],
            ]),
        )
        return

    if c.startswith("invdelconfirm:"):
        iid = int(c.split(":")[1])
        entry = get_investment(iid)
        if not entry or entry["telegram_id"] != update.effective_user.id:
            await q.answer("العملية دي مش موجودة.", show_alert=True)
            return

        delete_investment(iid, update.effective_user.id)
        await q.edit_message_text(
            "✅ اتحذفت.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 استثماراتي", callback_data="invlist")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="invtrack")],
            ]),
        )
        return

    # ---- حذف سعر غلط ----

    if c == "delpricelist":
        if not is_admin(update):
            return

        rows = recent_gold_prices(15)
        if not rows:
            await q.edit_message_text(
                "لا يوجد أي أسعار مسجلة.", reply_markup=gold_menu()
            )
            return

        kb_rows = []
        for r in rows:
            dt = (
                r["created_at"].strftime("%Y-%m-%d %H:%M")
                if hasattr(r["created_at"], "strftime")
                else r["created_at"]
            )
            label = f"{dt} — {round(float(r['price_21']))} ج"
            kb_rows.append([InlineKeyboardButton(
                label, callback_data=f"delprice:{r['id']}"
            )])
        kb_rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="agold")])

        await q.edit_message_text(
            "🗑 حذف سعر غلط\n\n"
            "دوس على السعر اللي عايز تحذفه من آخر 15 سعر متسجلين "
            "(الأحدث فوق):",
            reply_markup=InlineKeyboardMarkup(kb_rows),
        )
        return

    if c.startswith("delprice:"):
        if not is_admin(update):
            return

        pid = int(c.split(":")[1])
        entry = get_gold_price_entry(pid)
        if not entry:
            await q.answer("السعر ده مش موجود (يمكن اتحذف قبل كده).", show_alert=True)
            return

        dt = (
            entry["created_at"].strftime("%Y-%m-%d %H:%M")
            if hasattr(entry["created_at"], "strftime")
            else entry["created_at"]
        )

        await q.edit_message_text(
            "⚠️ متأكد عايز تحذف السعر ده؟\n\n"
            f"📅 {dt}\n"
            f"عيار 21: {round(float(entry['price_21']))} ج\n"
            f"عيار 24: {round(float(entry['price_24']))} ج\n"
            f"عيار 18: {round(float(entry['price_18']))} ج\n\n"
            "الحذف ده نهائي ومش هينفع ترجعه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🗑 اه، احذفه", callback_data=f"delpriceconfirm:{pid}"
                )],
                [InlineKeyboardButton(
                    "❌ لأ، رجعني", callback_data="delpricelist"
                )],
            ]),
        )
        return

    if c.startswith("delpriceconfirm:"):
        if not is_admin(update):
            return

        pid = int(c.split(":")[1])
        entry = get_gold_price_entry(pid)
        if not entry:
            await q.answer("السعر ده مش موجود (يمكن اتحذف قبل كده).", show_alert=True)
            return

        broadcast_msgs = get_gold_broadcast_messages(pid)

        ok = delete_gold_price_entry(pid)
        log_action(
            update.effective_user.id, "ADMIN_DELETE_GOLD_PRICE",
            new_value=str(round(float(entry["price_21"]))),
        )

        deleted_count, delete_failed = 0, 0
        for m in broadcast_msgs:
            try:
                await context.bot.delete_message(
                    chat_id=m["telegram_id"], message_id=m["message_id"]
                )
                deleted_count += 1
            except Exception as e:
                delete_failed += 1
                print(
                    f"Broadcast Message Delete Failed for {m['telegram_id']}:",
                    repr(e), flush=True,
                )
            await asyncio.sleep(0.05)

        delete_gold_broadcast_messages(pid)

        if ok:
            msg_line = ""
            if broadcast_msgs:
                msg_line = (
                    f"\n📨 اتشال الإشعار من {deleted_count} شات"
                    + (f" (فشل مع {delete_failed})" if delete_failed else "")
                    + "."
                )
                if delete_failed:
                    msg_line += (
                        "\n(الفشل بيحصل عادة لو العميل حذف الشات أو "
                        "الرسالة قديمة أكتر من 48 ساعة — تليجرام بيمنع "
                        "حذف رسائل قديمة أوي.)"
                    )

            await q.edit_message_text(
                "✅ اتحذف السعر الغلط."
                + msg_line
                + "\n\nملحوظة: لو السعر ده كان آخر سعر متسجل، البوت هيرجع "
                "يعتبر آخر سعر قبله هو السعر الحالي.",
                reply_markup=gold_menu(),
            )
        else:
            await q.edit_message_text(
                "❌ حصل خطأ، السعر ده يمكن اتحذف قبل كده.",
                reply_markup=gold_menu(),
            )
        return

    if c.startswith("calcmode:"):
        mode = c.split(":")[1]  # "buy" | "sell"
        back_cb = "calcgold"

        await q.edit_message_text(
            "🧮 اختار العيار:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "عيار 24", callback_data=f"calck:{mode}:24"
                )],
                [InlineKeyboardButton(
                    "عيار 21", callback_data=f"calck:{mode}:21"
                )],
                [InlineKeyboardButton(
                    "عيار 18", callback_data=f"calck:{mode}:18"
                )],
                [InlineKeyboardButton("⬅️ رجوع", callback_data=back_cb)],
            ]),
        )
        return

    if c.startswith("calck:"):
        _, mode, karat_s = c.split(":")
        karat = int(karat_s)
        compare_active = context.user_data.get("calc_compare_active")
        compare_first = context.user_data.get("calc_compare_first")

        # Selling 24k gold means it's bullion — bought back at the
        # plain per-gram price, no discount (same math as buying).
        if mode == "sell" and karat == 24:
            context.user_data.clear()
            context.user_data.update(
                state="calc_weight_input",
                calc_mode="sell_bullion", calc_karat=24,
            )
            if compare_active:
                context.user_data["calc_compare_active"] = True
                if compare_first:
                    context.user_data["calc_compare_first"] = compare_first
            await q.edit_message_text(
                "⚖️ اكتب وزن السبيكة بالجرام.\nمثال: 5 أو 3.5"
            )
            return

        # Selling 21k splits into "coins" (fixed, known weights —
        # bought back at the plain price) vs "مشغولات" (jewelry,
        # weighed and bought back at a discount).
        if mode == "sell" and karat == 21:
            await q.edit_message_text(
                "💰 هتبيع عملات ولا مشغولات؟",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "🪙 عملات", callback_data="calc21type:coins"
                    )],
                    [InlineKeyboardButton(
                        "💍 مشغولات", callback_data="calc21type:jewelry"
                    )],
                    [InlineKeyboardButton(
                        "⬅️ رجوع", callback_data="calcmode:sell"
                    )],
                ]),
            )
            return

        context.user_data.clear()
        context.user_data.update(
            state="calc_weight_input", calc_mode=mode, calc_karat=karat,
        )
        if compare_active:
            context.user_data["calc_compare_active"] = True
            if compare_first:
                context.user_data["calc_compare_first"] = compare_first
        await q.edit_message_text(
            "⚖️ اكتب وزن القطعة بالجرام.\nمثال: 5 أو 3.5"
        )
        return

    if c == "calc21type:jewelry":
        compare_active = context.user_data.get("calc_compare_active")
        compare_first = context.user_data.get("calc_compare_first")
        context.user_data.clear()
        context.user_data.update(
            state="calc_weight_input", calc_mode="sell", calc_karat=21,
        )
        if compare_active:
            context.user_data["calc_compare_active"] = True
            if compare_first:
                context.user_data["calc_compare_first"] = compare_first
        await q.edit_message_text(
            "⚖️ اكتب وزن القطعة بالجرام.\nمثال: 5 أو 3.5"
        )
        return

    if c.startswith("calccmpk2:"):
        _, mode, karat_s = c.split(":")
        karat = int(karat_s)
        compare_first = context.user_data.get("calc_compare_first")

        if not compare_first:
            await q.answer("حصل خطأ، ابدأ المقارنة من الأول.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data.update(
            state="calc_weight_input", calc_mode=mode, calc_karat=karat,
            calc_compare_active=True, calc_compare_first=compare_first,
        )
        await q.edit_message_text(
            "⚖️ اكتب وزن القطعة التانية بالجرام.\nمثال: 5 أو 3.5"
        )
        return

    if c == "calcmcno":
        karat = context.user_data.get("calc_mc_karat")
        weight = context.user_data.get("calc_mc_weight")
        total = context.user_data.get("calc_mc_total")
        context.user_data.clear()

        final_text = (
            f"العيار: {karat}\n"
            f"الوزن: {weight} جرام\n"
            f"💰 الإجمالي: {total} جنيه\n\n"
            "⚠️ السعر ذهب صافي، مش شامل المصنعية."
        ) if karat is not None else "✅ تمام."

        await q.edit_message_text(
            f"✅ تمام، من غير مصنعية.\n\n{final_text}"
            if karat is not None else final_text,
        )

        if karat is not None:
            context.user_data["calc_share_text"] = build_share_text(
                final_text
            )
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text="اختار من القائمة 👇",
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if c == "calcmcyes":
        if "calc_mc_karat" not in context.user_data:
            await q.answer("حصل خطأ، احسب القطعة تاني.", show_alert=True)
            return

        await q.edit_message_text(
            "المصنعية اللي هيقولهالك المحل، على القطعة كلها ولا "
            "على الجرام؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🧾 على القطعة كلها", callback_data="calcmctype:piece"
                )],
                [InlineKeyboardButton(
                    "⚖️ على الجرام", callback_data="calcmctype:gram"
                )],
            ]),
        )
        return

    if c.startswith("calcmctype:"):
        mc_type = c.split(":")[1]  # "piece" | "gram"

        if "calc_mc_karat" not in context.user_data:
            await q.answer("حصل خطأ، احسب القطعة تاني.", show_alert=True)
            return

        context.user_data["calc_mc_type"] = mc_type
        context.user_data["state"] = "calc_mc_amount_input"

        await q.edit_message_text(
            "💰 اكتب قيمة المصنعية بالجنيه اللي قالهالك المحل.\n\n"
            + (
                "مثال: 300 (على القطعة كلها)"
                if mc_type == "piece" else
                "مثال: 50 (للجرام)"
            )
        )
        return

    if c == "calc21type:coins":
        k = [
            [InlineKeyboardButton(label, callback_data=f"calccoin:{i}")]
            for i, (label, _) in enumerate(GOLD_COINS)
        ]
        k.append(
            [InlineKeyboardButton("⬅️ رجوع", callback_data="calck:sell:21")]
        )
        await q.edit_message_text(
            "🪙 اختار العملة:", reply_markup=InlineKeyboardMarkup(k)
        )
        return

    if c.startswith("calccoin:"):
        idx = int(c.split(":")[1])
        if idx < 0 or idx >= len(GOLD_COINS):
            return

        label, weight = GOLD_COINS[idx]
        p21 = latest()

        if not p21:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="💎 لم يتم تحديث أسعار الذهب حتى الآن.",
            )
            return

        _, p21c, _ = calc(p21)
        total = round(weight * p21c)

        coin_text = (
            f"🧮 نتيجة الحساب\n\n"
            f"{label}\n"
            f"سعر شراء الجرام: {p21c} جنيه\n\n"
            f"💰 الإجمالي: {total} جنيه\n\n"
            "⚠️ سعر العملة صافي، بدون أي خصم."
        )
        context.user_data["calc_share_text"] = build_share_text(coin_text)
        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=coin_text,
            reply_markup=calc_result_kb(update.effective_user.id),
        )
        return

    if c == "notifsub":
        track_user(update)
        set_gold_subscription(update.effective_user.id, True)

        wa_subscribed = is_whatsapp_subscribed(update.effective_user.id)

        if wa_subscribed:
            await q.edit_message_text(
                "💎 " + SHOP_NAME + "\n\n"
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
            "💎 " + SHOP_NAME + "\n\n"
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

    if c == "adminreplyid":
        if not is_admin(update):
            return

        context.user_data.clear()
        context.user_data["state"] = "admin_reply_id_input"
        await q.edit_message_text(
            "💬 رد على عميل بالآيدي\n\n"
            "اكتب آيدي التليجرام بتاع العميل (هتلاقيه في أي رسالة "
            "وصلتك منه، رقم زي 7087485592).",
        )
        return

    if c == "referralleaderboard":
        if not is_admin(update):
            return

        rows = referral_leaderboard(20)
        if not rows:
            await q.edit_message_text(
                "🏆 قائمة المتصدرين\n\n"
                "مفيش أي دعوات ناجحة متسجلة لسه.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
                ]),
            )
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = ["🏆 قائمة المتصدرين (الأكتر دعوات)\n"]
        for i, r in enumerate(rows, start=1):
            medal = medals.get(i, f"{i}.")
            name = r.get("first_name") or "بدون اسم"
            uname = f" (@{r['username']})" if r.get("username") else ""
            lines.append(f"{medal} {name}{uname} — {r['cnt']} دعوة")

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin")],
            ]),
        )
        return

    # ---- حساباتي الشخصية (له/عليه) — لأي مستخدم للبوت ----

    if c == "ledgermenu":
        track_user(update)
        uid = update.effective_user.id
        customers = list_ledger_customers(uid)

        if not customers:
            await q.edit_message_text(
                "📇 حساباتي\n\n"
                "سجّل هنا أي حد بتتعامل معاه (شغل، ديون، أي حاجة)، "
                "وتابع له كام وعليه كام بسهولة.\n\n"
                "مفيش حسابات متسجلة لسه.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "➕ سجّل حساب جديد", callback_data="ledgeraddcustomer"
                    )],
                    [InlineKeyboardButton("⬅️ الرئيسية", callback_data="home")],
                ]),
            )
            return

        await q.edit_message_text(
            "📇 حساباتي\n\nاختار حساب:",
            reply_markup=ledger_customer_pick_kb(customers, 0),
        )
        return

    if c.startswith("ledgercp:"):
        uid = update.effective_user.id
        page = int(c.split(":")[1])
        customers = list_ledger_customers(uid)
        await q.edit_message_text(
            "📇 حساباتي\n\nاختار حساب:",
            reply_markup=ledger_customer_pick_kb(customers, page),
        )
        return

    if c == "ledgeraddcustomer":
        context.user_data.clear()
        context.user_data["state"] = "ledger_name_input"
        await q.edit_message_text("✏️ اكتب اسم الشخص أو الجهة:")
        return

    if c.startswith("ledgerc:"):
        uid = update.effective_user.id
        cid = int(c.split(":")[1])
        text, kb = ledger_customer_view(cid, uid)
        if not text:
            await q.answer("الحساب ده مش موجود.", show_alert=True)
            return
        await q.edit_message_text(text, reply_markup=kb)
        return

    if c.startswith("ledgerlah:") or c.startswith("ledgeralaih:"):
        uid = update.effective_user.id
        direction = "lah" if c.startswith("ledgerlah:") else "alaih"
        cid = int(c.split(":")[1])

        if not get_ledger_customer(cid, uid):
            await q.answer("الحساب ده مش موجود.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data.update(
            state="ledger_amount_input",
            ledger_customer_id=cid,
            ledger_direction=direction,
        )

        label = "له (انت مديون له)" if direction == "lah" \
            else "عليه (هو مديون لك)"
        await q.edit_message_text(f"💰 اكتب المبلغ {label}.\nمثال: 500")
        return

    if c.startswith("ledgerhist:"):
        uid = update.effective_user.id
        cid = int(c.split(":")[1])

        if not get_ledger_customer(cid, uid):
            await q.answer("الحساب ده مش موجود.", show_alert=True)
            return

        rows = list_ledger_entries(cid, 15)

        if not rows:
            await q.edit_message_text(
                "📊 مفيش أي حركات متسجلة لسه.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "⬅️ رجوع", callback_data=f"ledgerc:{cid}"
                    )],
                ]),
            )
            return

        lines = ["📊 آخر الحركات:\n"]
        for r in rows:
            dt = (
                r["created_at"].strftime("%d/%m/%y %H:%M")
                if hasattr(r["created_at"], "strftime")
                else r["created_at"]
            )
            arrow = "🟢 له" if r["direction"] == "lah" else "🔴 عليه"
            note = f" — {r['note']}" if r.get("note") else ""
            lines.append(f"{arrow} {round(float(r['amount']))} ج{note} ({dt})")

        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⬅️ رجوع", callback_data=f"ledgerc:{cid}"
                )],
            ]),
        )
        return

    if c.startswith("ledgerdel:"):
        uid = update.effective_user.id
        cid = int(c.split(":")[1])
        cust = get_ledger_customer(cid, uid)
        if not cust:
            await q.answer("الحساب ده مش موجود.", show_alert=True)
            return

        await q.edit_message_text(
            f"⚠️ متأكد عايز تحذف \"{cust['name']}\" وكل حركاته؟\n\n"
            "الحذف نهائي ومش هينفع ترجعه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🗑 اه، احذفه", callback_data=f"ledgerdelconfirm:{cid}"
                )],
                [InlineKeyboardButton(
                    "❌ لأ، رجعني", callback_data=f"ledgerc:{cid}"
                )],
            ]),
        )
        return

    if c.startswith("ledgerdelconfirm:"):
        uid = update.effective_user.id
        cid = int(c.split(":")[1])
        delete_ledger_customer(cid, uid)
        await q.edit_message_text(
            "✅ اتحذف الحساب وكل حركاته.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📇 حساباتي", callback_data="ledgermenu"
                )],
            ]),
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
            new_price_id = save_latest(p, admin_id=update.effective_user.id)

            if context.user_data.get("first"):
                save_first(p)

            await maybe_send_gold_alert(context, prev_p, p)
            await broadcast_gold_update(context, p, price_id=new_price_id)
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
    person closes and reopens the chat. /updateprice is scoped to
    admin chats only — regular customers never see it."""
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "🏠 القائمة الرئيسية"),
                BotCommand("favorites", "⭐ المفضلة"),
            ],
            scope=BotCommandScopeDefault(),
        )

        admin_commands = [
            BotCommand("start", "🏠 القائمة الرئيسية"),
            BotCommand("favorites", "⭐ المفضلة"),
            BotCommand("updateprice", "✏️ تحديث سعر الذهب"),
        ]
        for admin_id in all_admin_ids():
            try:
                await app.bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except Exception as e:
                print(
                    f"Set Admin Commands Error ({admin_id}):",
                    repr(e), flush=True,
                )
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
    app.add_handler(CommandHandler("favorites", favorites_command))
    app.add_handler(CommandHandler("updateprice", update_price_shortcut))

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
        app.job_queue.run_repeating(
            auto_notification_tick, interval=60, first=15,
            name="auto_notification_tick",
        )
        app.job_queue.run_repeating(
            occasion_tick, interval=60, first=20, name="occasion_tick",
        )
        app.job_queue.run_repeating(
            birthday_tick, interval=60, first=25, name="birthday_tick",
        )
        app.job_queue.run_repeating(
            tip_tick, interval=60, first=30, name="tip_tick",
        )
        app.job_queue.run_repeating(
            savings_goal_tick, interval=60, first=35,
            name="savings_goal_tick",
        )
        app.job_queue.run_repeating(
            budget_month_end_tick, interval=60, first=37,
            name="budget_month_end_tick",
        )
        app.job_queue.run_repeating(
            weekly_summary_tick, interval=60, first=40,
            name="weekly_summary_tick",
        )
        app.job_queue.run_repeating(
            potd_tick, interval=60, first=45, name="potd_tick",
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
