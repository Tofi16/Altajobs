# -*- coding: utf-8 -*-
"""
AltaJobs - አሰሪና ሰራተኛን የሚያገናኝ ድህረ ገጽ
Flask + SQLite + Multi-language (am/en/om/ti)

እንዴት ማስኬድ እንደሚቻል README.md ላይ ይመልከቱ
"""
import os
import re
import sqlite3
import secrets
import smtplib
import datetime
import urllib.parse
from functools import wraps
from email.message import EmailMessage
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, request, session, redirect, url_for,
    render_template, g, flash, abort, send_from_directory
)
from flask import jsonify

try:
    from flask_compress import Compress
except ImportError:
    Compress = None

try:
    import psycopg2
    import psycopg2.extras
    PG_INTEGRITY_ERROR = psycopg2.IntegrityError
except ImportError:
    psycopg2 = None
    PG_INTEGRITY_ERROR = sqlite3.IntegrityError

from translations import get_translator, DEFAULT_LANG, TRANSLATIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DATA_DIR points at a persistent volume/disk in production (e.g. Render Disk
# mounted at /var/data, Railway Volume mounted at /data). Falls back to
# a dedicated data directory under the source tree for local development.
# See render.yaml / railway.json for how DATA_DIR is set per platform.
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def _ensure_postgres_ssl(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("postgres", "postgresql"):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
        query_string = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=query_string))
    return url


def _database_preference_score(path):
    if not path or not os.path.exists(path):
        return -1

    conn = None
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        score = 0
        if "users" in tables:
            score += 1000
            try:
                user_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                score += min(user_count, 20) * 6
            except Exception:
                pass
            try:
                user_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)")}
                if "verification_tier" in user_cols:
                    score += 250
                if "verified_until" in user_cols:
                    score += 100
                if "verification_tier" in user_cols:
                    verified_users = cur.execute("SELECT COUNT(*) FROM users WHERE verification_tier IN ('blue', 'gold')").fetchone()[0]
                    score += verified_users * 300
            except Exception:
                pass
        if "posts" in tables:
            score += 500
            try:
                post_count = cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                score += min(post_count, 20) * 8
            except Exception:
                pass
        if "wallets" in tables:
            score += 50
        return score
    except Exception:
        return -1
    finally:
        if conn is not None:
            conn.close()


def _resolve_database_path():
    explicit_path = ""
    if DATABASE_URL.startswith("sqlite:///"):
        explicit_path = DATABASE_URL[len("sqlite:///"):].strip()

    candidates = []
    if explicit_path:
        candidates.append(explicit_path)

    candidates.extend([
        os.path.join(BASE_DIR, "altajobs.db"),
        os.path.join(BASE_DIR, "database.db"),
        os.path.join(DATA_DIR, "database.db"),
    ])

    seen = set()
    ordered = []
    for candidate in candidates:
        if not candidate:
            continue
        normalized = os.path.abspath(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)

    existing = [candidate for candidate in ordered if os.path.exists(candidate)]
    if existing:
        ranked = sorted(existing, key=lambda path: (-_database_preference_score(path), -os.path.getmtime(path)))
        return ranked[0]

    return os.path.join(DATA_DIR, "database.db")


if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
    if DATABASE_URL.startswith("sqlite:///"):
        DATABASE = _resolve_database_path()
        USE_SQLITE = True
    else:
        DATABASE_URL = _ensure_postgres_ssl(DATABASE_URL)
        DATABASE = DATABASE_URL
        USE_SQLITE = False
else:
    DATABASE = _resolve_database_path()
    DATABASE_URL = "sqlite:///" + DATABASE.replace('\\', '/')
    USE_SQLITE = True

UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
CV_PHOTO_FOLDER = os.path.join(UPLOAD_FOLDER, "cv_photos")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

FREE_TRIAL_DAYS = 30
MONTHLY_PRICE = 1500
YEARLY_PRICE = 7000
FEED_PAGE_SIZE = 10  # posts fetched per page/scroll batch on the main feed

# --- Wallet / Verification / Gifts settings -------------------------------
TELEBIRR_WALLET_NUMBER = "0960602675"     # ገንዘብ የሚላክበት ቴሌብር ቁጥር
VERIFICATION_MONTHLY_PRICE = 300          # የ Blue Tick ወርሃዊ ዋጋ (ብር) - ከዋሌት ሲቀነስ
CHANNEL_VERIFICATION_MONTHLY_PRICE = 500  # የ channel/group Blue Tick ወርሃዊ ዋጋ (ብር)
CHANNEL_VERIFICATION_WARNING_DAYS = 7      # ማብቂያው ከመድረሱ ስንት ቀን በፊት ማስጠንቀቂያ እንደሚታይ
VIP_MONTHLY_PRICE = 800                   # የ VIP ወርሃዊ ዋጋ (ብር) - ከዋሌት ሲቀነስ

# --- Blue/Gold verification subscription plans -----------------------------
# Single source of truth for tier pricing: used by /get-verified, /checkout,
# and anywhere else a plan needs to be looked up. Never hardcode these prices
# in a template or route — read them from here so the numbers can't drift.
VERIFICATION_PLANS = {
    "blue": {
        "label": "Blue",
        "audience": "For Talents",
        "durations": [
            {"id": "1m", "months": 1, "price": 1000, "name": "1 Month"},
            {"id": "6m", "months": 6, "price": 4000, "name": "6 Months"},
            {"id": "1y", "months": 12, "price": 7000, "name": "1 Year"},
        ],
    },
    "gold": {
        "label": "Gold",
        "audience": "For Companies",
        "durations": [
            {"id": "1y", "months": 12, "price": 18000, "name": "1 Year"},
        ],
    },
}


def get_verification_plan(tier, duration_id):
    """Look up a single plan (tier + duration) from VERIFICATION_PLANS.
    Returns None if the combination doesn't exist."""
    plan = VERIFICATION_PLANS.get(tier)
    if not plan:
        return None
    for d in plan["durations"]:
        if d["id"] == duration_id:
            return {"tier": tier, "label": plan["label"], **d}
    return None
PLATFORM_CUT_PERCENT = 30                 # ከእያንዳንዱ ጊፍት ላይ ለመድረኩ (ለ Tofik) የሚቆረጠው %
CV_PREMIUM_PRICE = 50                     # "Banana AI" premium CV (with photo) ዋጋ (ብር) - ከዋሌት ሲቀነስ

# --- Monthly Business Challenge settings -----------------------------------
CHALLENGE_TIERS = [50, 100, 200, 500, 1000]     # 5 ደረጃ ያላቸው pools (ETB)
CHALLENGE_PLATFORM_FEE_PERCENT = 10             # ከ pool ላይ ለመድረኩ የሚቆረጠው %
REQUIRED_FOLLOWS = 5                            # ለመግባት አስፈላጊ የ follow ብዛት
REQUIRED_SHARES = 3                             # ለመግባት አስፈላጊ የ share ብዛት
PITCH_WINDOW_HOURS = 72                         # አሸናፊው የቢዝነስ እቅድ የሚያቀርብበት ጊዜ
MILESTONE_1_PERCENT = 50                        # የመጀመሪያው ክፍያ ምጣኔ
MAX_ENGAGEMENT_BONUS = 5                        # ተጨማሪ follow/referral በውድድር ውጤት ላይ የሚጨምረው ከፍተኛ ነጥብ (tie-breaker ብቻ)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# --- Alta Token Economy (Daily Check-in & Task-to-Earn) ---------------------
CHECKIN_REWARDS = {1: 5, 2: 10, 3: 15, 4: 20, 5: 25, 6: 30, 7: 50}
TASK_REWARDS = {
    "profile_completion": 100,   # one-time
    "share_job": 10,             # repeatable
}
DAILY_TASK_CAP = 200

# animated gift catalog: key -> (emoji, price in ETB, css animation class)
GIFT_CATALOG = {
    "rose":    {"emoji": "🌹", "price": 10,  "anim": "gift-bounce"},
    "heart":   {"emoji": "❤️", "price": 25,  "anim": "gift-pulse"},
    "star":    {"emoji": "⭐", "price": 50,  "anim": "gift-spin"},
    "crown":   {"emoji": "👑", "price": 100, "anim": "gift-bounce"},
    "diamond": {"emoji": "💎", "price": 500, "anim": "gift-pulse"},
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "alta-jobs-secret-key-change-in-production"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
print(f"UPLOAD_FOLDER={UPLOAD_FOLDER}")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15MB (photo/receipt/CV-photo uploads only, no video)
app.config["PREFERRED_URL_SCHEME"] = os.environ.get("PREFERRED_URL_SCHEME", "https")
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "True").lower() in ["true", "on", "1"]
app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "False").lower() in ["true", "on", "1"]
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@altajobs.app")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CV_PHOTO_FOLDER, exist_ok=True)

# --- Response compression (Gzip via Flask-Compress) -------------------------
# Shrinks HTML/JSON/CSS/JS payloads before they hit the wire. Images/videos
# are already compressed formats, so they're intentionally excluded.
app.config["COMPRESS_MIMETYPES"] = [
    "text/html", "text/css", "text/xml", "text/plain",
    "application/json", "application/javascript", "application/xml",
]
app.config["COMPRESS_LEVEL"] = 6          # 1 (fast/weak) - 9 (slow/strong); 6 is a good balance
app.config["COMPRESS_MIN_SIZE"] = 500     # don't bother compressing tiny responses
if Compress is not None:
    Compress(app)
else:
    print("Warning: Flask-Compress is not installed. Run `pip install Flask-Compress` "
          "and add it to requirements.txt to enable Gzip compression.")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def is_sqlite_database():
    return globals().get("USE_SQLITE", False)


class DatabaseConnection:
    def __init__(self, conn, is_sqlite):
        self.conn = conn
        self.is_sqlite = is_sqlite

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        if not self.is_sqlite and "?" in sql:
            sql = sql.replace("?", "%s")
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def _validate_postgres_url():
    if not DATABASE_URL or DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("PostgreSQL DATABASE_URL is not configured or resolves to SQLite.")


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        if is_sqlite_database():
            conn = sqlite3.connect(DATABASE, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            db = g._database = DatabaseConnection(conn, is_sqlite=True)
        else:
            _validate_postgres_url()
            if psycopg2 is None:
                raise RuntimeError("psycopg2-binary is required for PostgreSQL DATABASE_URL support")
            conn = psycopg2.connect(DATABASE, cursor_factory=psycopg2.extras.RealDictCursor)
            db = g._database = DatabaseConnection(conn, is_sqlite=False)
    try:
        # Run each statement independently so a failing one doesn't abort the whole sequence
        stmts = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_id TEXT UNIQUE DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS alta_tokens INTEGER DEFAULT 0",
            "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS transaction_ref TEXT DEFAULT NULL",
            "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS receipt_image_path TEXT DEFAULT NULL",
            "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS recipient_wallet_id TEXT DEFAULT NULL",
            "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name TEXT DEFAULT NULL",
            "ALTER TABLE posts ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0",
            "ALTER TABLE posts ADD COLUMN IF NOT EXISTS virality_score REAL DEFAULT 0.0",
            "ALTER TABLE posts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'approved'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_badge TEXT DEFAULT 'Bronze Member'",
        ]
        for s in stmts:
            try:
                db.execute(s)
                db.commit()
            except Exception:
                # ignore individual failures, continue with others
                try:
                    db.rollback()
                except Exception:
                    pass

        # Initialize/fill sensible defaults for existing rows (individually)
        try:
            user_cols = _get_table_columns(db, "users")
            for column_name, definition in {
                "strikes": "INTEGER DEFAULT 0",
                "trust_score": "INTEGER DEFAULT 0",
                "is_suspended": "INTEGER DEFAULT 0",
                "is_trusted_seller": "INTEGER DEFAULT 0",
            }.items():
                if column_name not in user_cols:
                    db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {definition}")
            if not _table_has_column(db, "bank_accounts", "account_holder_name"):
                db.execute("ALTER TABLE bank_accounts ADD COLUMN account_holder_name TEXT DEFAULT NULL")
            if not _table_has_column(db, "bank_accounts", "account_name"):
                db.execute("ALTER TABLE bank_accounts ADD COLUMN account_name TEXT DEFAULT NULL")
            if _table_has_column(db, "bank_accounts", "account_holder_name") and _table_has_column(db, "bank_accounts", "account_name"):
                db.execute("UPDATE bank_accounts SET account_holder_name = COALESCE(account_holder_name, account_name) WHERE account_holder_name IS NULL AND account_name IS NOT NULL")
                db.execute("UPDATE bank_accounts SET account_name = COALESCE(account_name, account_holder_name) WHERE account_name IS NULL AND account_holder_name IS NOT NULL")
            db.execute("UPDATE users SET wallet_balance = COALESCE(wallet_balance, 0), alta_tokens = COALESCE(alta_tokens, 0)")
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        try:
            db.execute("UPDATE posts SET view_count = COALESCE(view_count, 0), virality_score = COALESCE(virality_score, 0.0)")
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    except Exception as exc:
        print(f"Warning: could not ensure PostgreSQL wallet columns: {exc}")
    return db


def _coerce_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    return bool(value)


def _normalize_bank_row(row):
    if row is None:
        return None
    is_active = row.get("is_active") if hasattr(row, "get") else None
    if is_active is None:
        is_active = True
    elif isinstance(is_active, str):
        is_active = _coerce_bool(is_active, default=True)
    elif not isinstance(is_active, bool):
        is_active = bool(is_active)
    return {
        "id": row.get("id") if hasattr(row, "get") else None,
        "bank_name": row.get("bank_name") if hasattr(row, "get") else None,
        "account_name": (row.get("account_name") if hasattr(row, "get") else None) or (row.get("account_holder_name") if hasattr(row, "get") else None),
        "account_number": row.get("account_number") if hasattr(row, "get") else None,
        "account_holder_name": row.get("account_holder_name") if hasattr(row, "get") else None,
        "is_active": is_active,
        "created_at": row.get("created_at") if hasattr(row, "get") else None,
    }


def _safe_fetch_challenge_status(db, user_id):
    try:
        current_month = datetime.datetime.utcnow().strftime("%Y-%m")
        return db.execute(
            """SELECT ce.*, cp.tier_amount, cp.prize_pool, cp.status AS pool_status
               FROM challenge_entries ce
               JOIN challenge_pools cp ON ce.pool_id = cp.id
               WHERE ce.user_id = ? AND cp.month = ?""",
            (user_id, current_month),
        ).fetchone()
    except Exception:
        return None


def init_postgres_db():
    if psycopg2 is None:
        raise RuntimeError("psycopg2-binary is required for PostgreSQL DATABASE_URL support")

    conn = psycopg2.connect(DATABASE, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            user_type TEXT NOT NULL DEFAULT 'worker',
            phone TEXT,
            skills TEXT,
            experience TEXT,
            bio TEXT,
            avatar TEXT,
            balance REAL DEFAULT 0.0,
            points INTEGER DEFAULT 0,
            activity_badge TEXT DEFAULT 'Bronze Member',
            wallet_id TEXT UNIQUE DEFAULT NULL,
            referral_code TEXT DEFAULT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            verified_until TEXT DEFAULT NULL,
            verification_tier TEXT DEFAULT 'none',
            is_banned BOOLEAN DEFAULT FALSE,
            banned_until TEXT DEFAULT NULL,
            ban_reason TEXT DEFAULT NULL,
            is_suspended BOOLEAN DEFAULT FALSE,
            created_at TEXT NOT NULL,
            plan TEXT DEFAULT NULL,
            paid_until TEXT DEFAULT NULL,
            email_verified INTEGER DEFAULT 0,
            email_verification_code TEXT DEFAULT NULL,
            password_reset_code TEXT DEFAULT NULL,
            password_reset_expires TEXT DEFAULT NULL,
            email_verified_at TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            content TEXT,
            photo TEXT,
            post_type TEXT DEFAULT 'general',
            share_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'approved',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS likes (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(post_id, user_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            employer_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(employer_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            reporter_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(reporter_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS saved_posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, post_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_applications (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL,
            applicant_id INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'submitted',
            created_at TEXT NOT NULL,
            UNIQUE(post_id, applicant_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(applicant_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            initiated_by INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            UNIQUE(user1_id, user2_id),
            FOREIGN KEY(user1_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(user2_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            seen_at TEXT,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS post_views (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL,
            user_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(post_id, user_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS token_transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            amount INTEGER NOT NULL,
            streak_day INTEGER,
            post_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channels (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            channel_type TEXT NOT NULL DEFAULT 'group',
            creator_id INTEGER NOT NULL,
            avatar TEXT,
            is_verified INTEGER DEFAULT 0,
            verified_until TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(creator_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_members (
            id SERIAL PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            UNIQUE(channel_id, user_id),
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_messages (
            id SERIAL PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT,
            photo TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_message_reactions (
            id SERIAL PRIMARY KEY,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(message_id, user_id, emoji),
            FOREIGN KEY(message_id) REFERENCES channel_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS follows (
            id SERIAL PRIMARY KEY,
            follower_id INTEGER NOT NULL,
            followed_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(follower_id, followed_id),
            FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(followed_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(referrer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(referred_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challenge_shares (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challenge_pools (
            id SERIAL PRIMARY KEY,
            tier_amount INTEGER NOT NULL,
            month TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            platform_fee_percent INTEGER DEFAULT 10,
            prize_pool INTEGER DEFAULT 0,
            winner_entry_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(tier_amount, month)
        );

        CREATE TABLE IF NOT EXISTS challenge_entries (
            id SERIAL PRIMARY KEY,
            pool_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount_paid INTEGER NOT NULL,
            pitch_text TEXT NOT NULL,
            ai_score REAL,
            admin_score REAL,
            engagement_bonus REAL DEFAULT 0,
            final_score REAL,
            status TEXT DEFAULT 'submitted',
            created_at TEXT NOT NULL,
            UNIQUE(pool_id, user_id),
            FOREIGN KEY(pool_id) REFERENCES challenge_pools(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS winner_trust (
            id SERIAL PRIMARY KEY,
            entry_id INTEGER NOT NULL UNIQUE,
            confirm_deadline TEXT NOT NULL,
            confirmed_at TEXT,
            guarantor_name TEXT,
            guarantor_id_number TEXT,
            guarantor_photo TEXT,
            milestone1_amount INTEGER,
            milestone1_released INTEGER DEFAULT 0,
            proof_photo TEXT,
            proof_submitted_at TEXT,
            milestone2_amount INTEGER,
            milestone2_released INTEGER DEFAULT 0,
            disbursement_status TEXT DEFAULT 'pending_confirmation',
            created_at TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES challenge_entries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            transaction_ref TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            transaction_ref TEXT,
            bank TEXT DEFAULT NULL,
            note TEXT DEFAULT NULL,
            receipt_photo TEXT DEFAULT NULL,
            account_number TEXT DEFAULT NULL,
            account_name TEXT DEFAULT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id SERIAL PRIMARY KEY,
            bank_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            account_holder_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cv_documents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            full_name TEXT,
            target_role TEXT,
            summary TEXT,
            experience TEXT,
            achievements TEXT,
            skills TEXT,
            photo TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS gifts (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            gift_key TEXT NOT NULL,
            amount INTEGER NOT NULL,
            platform_cut INTEGER NOT NULL,
            post_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            id SERIAL PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            balance REAL DEFAULT 0.00,
            escrow_balance REAL DEFAULT 0.00,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            location TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS portfolio_items (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            project_url TEXT DEFAULT NULL,
            image_path TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            wallet_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(wallet_id) REFERENCES wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            offered_price REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY(buyer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(seller_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            is_pinned INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS restricted_words (
            id SERIAL PRIMARY KEY,
            word TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts (user_id)")
        # Composite index matching the feed's WHERE status IN (...) ORDER BY created_at DESC
        cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_status_created_at ON posts (status, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes (post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes (user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_posts_user_post ON saved_posts (user_id, post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_applicant_post ON job_applications (applicant_id, post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_follows_follower_id ON follows (follower_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_follows_followed_id ON follows (followed_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status_type_created_at ON wallet_transactions (status, tx_type, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions (user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status_created_at ON payments (status, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_status_created_at ON reports (status, created_at)")
        conn.commit()
    except Exception as exc:
        print(f"Warning: could not create PostgreSQL indexes: {exc}")
    finally:
        cur.close()
        conn.close()


def _generate_wallet_id(db):
    """Return a unique wallet ID for a new user.

    Generates a random alphanumeric wallet ID and ensures it does not already
    exist in the users table. Raises RuntimeError only if a unique ID cannot be
    generated after several attempts.
    """
    for _ in range(10):
        wallet_id = f"WAL{secrets.randbelow(10**9):09d}"
        existing = db.execute(
            "SELECT id FROM users WHERE wallet_id = ?", (wallet_id,)
        ).fetchone()
        if existing is None:
            return wallet_id
    raise RuntimeError("Unable to generate a unique wallet ID. Please try again.")


def _backfill_missing_wallet_ids(db):
    """Populate wallet IDs for any existing user that is missing one."""
    try:
        rows = db.execute(
            "SELECT id FROM users WHERE wallet_id IS NULL OR wallet_id = ''"
        ).fetchall()
    except Exception:
        return 0

    updated = 0
    for (user_id,) in rows:
        wallet_id = _generate_wallet_id(db)
        db.execute("UPDATE users SET wallet_id = ? WHERE id = ?", (wallet_id, user_id))
        updated += 1

    return updated


def init_db():
    """Initialize local SQLite database schema."""
    if not is_sqlite_database():
        raise RuntimeError("init_db() is only supported for local SQLite databases.")
    migrate_db()


def migrate_db():
    """አስቀድሞ ለተፈጠረ altajobs.db አዲስ columns በደህና ይጨምራል (idempotent)."""
    db = sqlite3.connect(DATABASE)
    db.executescript(
            """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password_hash TEXT,
            full_name TEXT,
            user_type TEXT DEFAULT 'worker',
            phone TEXT,
            created_at TEXT,
            is_admin INTEGER DEFAULT 0,
            balance REAL DEFAULT 0.0,
            wallet_balance INTEGER DEFAULT 0,
            wallet_id TEXT,
            alta_tokens INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            balance REAL DEFAULT 0.0,
            escrow_balance REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL,
            amount REAL NOT NULL,
            transaction_ref TEXT DEFAULT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            account_number TEXT,
            account_holder_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT,
            photo TEXT,
            post_type TEXT DEFAULT 'general',
            share_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'approved',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            gift_key TEXT NOT NULL,
            amount INTEGER NOT NULL,
            platform_cut INTEGER NOT NULL,
            post_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            is_pinned INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ntype TEXT DEFAULT 'info',
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS announcement_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(announcement_id, user_id),
            FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    db.commit()

    # Seed / update the admin account safely without overwriting existing data.
    try:
        user_cols = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        existing_admin = db.execute("SELECT id, username, is_admin FROM users WHERE username = ?", ("Tofik",)).fetchone()
        if existing_admin is None:
            insert_cols = ["username", "password_hash", "is_admin", "created_at"]
            insert_values = ["Tofik", "$2b$10$PlaceholderHashForTofikSecuredPassword123", 1, datetime.datetime.utcnow().isoformat()]
            if "role" in user_cols:
                insert_cols.append("role")
                insert_values.append("admin")
            if "referral_code" in user_cols:
                insert_cols.append("referral_code")
                insert_values.append(None)
            db.execute(
                f"INSERT INTO users ({', '.join(insert_cols)}) VALUES ({', '.join('?' for _ in insert_cols)})",
                insert_values,
            )
        else:
            if "role" in user_cols:
                db.execute("UPDATE users SET role = ?, is_admin = true WHERE username = ?", ("admin", "Tofik"))
            else:
                db.execute("UPDATE users SET is_admin = true WHERE username = ?", ("Tofik",))
        db.commit()
    except Exception as exc:
        print(f"Warning: could not seed admin user: {exc}")

    try:
        admin_user = db.execute("SELECT id FROM users WHERE username = ?", ("Tofik",)).fetchone()
        if admin_user:
            wallet_exists = db.execute("SELECT id FROM wallets WHERE user_id = ?", (admin_user[0],)).fetchone()
            if not wallet_exists:
                db.execute("INSERT INTO wallets (user_id, balance, escrow_balance, created_at) VALUES (?, 0.00, 0.00, ?)", (admin_user[0], datetime.datetime.utcnow().isoformat()))
                db.commit()
    except Exception as exc:
        print(f"Warning: could not initialize admin wallet: {exc}")
    existing_cols = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    new_columns = {
        "wallet_balance": "INTEGER DEFAULT 0",
        "balance": "REAL DEFAULT 0.0",
        "wallet_id": "TEXT DEFAULT NULL",
        "verified_until": "TEXT DEFAULT NULL",
        "verification_tier": "TEXT DEFAULT 'none'",
        "is_banned": "INTEGER DEFAULT 0",
        "referral_code": "TEXT DEFAULT NULL",
        "alta_tokens": "INTEGER DEFAULT 0",
        "last_checkin": "TEXT DEFAULT NULL",
        "current_streak": "INTEGER DEFAULT 0",
        "banned_until": "TEXT DEFAULT NULL",
        "ban_reason": "TEXT DEFAULT NULL",
        "points": "INTEGER DEFAULT 0",
        "activity_badge": "TEXT DEFAULT 'Bronze Member'",
    }
    for col, coltype in new_columns.items():
        if col not in existing_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
    db.commit()

    # NOTE: the legacy is_verified/is_vip/vip_until columns have been dropped
    # from the users table in production. verification_tier/verified_until
    # is now the sole source of truth for verification status - no backfill
    # needed since those columns no longer exist to backfill from.

    wallet_tx_cols = {row[1] for row in db.execute("PRAGMA table_info(wallet_transactions)")}
    for col, coltype in {
        "transaction_ref": "TEXT DEFAULT NULL",
        "receipt_image_path": "TEXT DEFAULT NULL",
        "recipient_wallet_id": "TEXT DEFAULT NULL",
    }.items():
        if col not in wallet_tx_cols:
            db.execute(f"ALTER TABLE wallet_transactions ADD COLUMN {col} {coltype}")
    db.commit()

    bank_cols = {row[1] for row in db.execute("PRAGMA table_info(bank_accounts)")}
    if "account_name" not in bank_cols:
        db.execute("ALTER TABLE bank_accounts ADD COLUMN account_name TEXT DEFAULT NULL")
    db.commit()

    try:
        db.execute("UPDATE users SET balance = COALESCE(balance, wallet_balance, 0.0)")
        db.execute("UPDATE users SET wallet_balance = COALESCE(wallet_balance, balance, 0)")
        _backfill_missing_wallet_ids(db)
        db.commit()
    except Exception as exc:
        print(f"Warning: could not backfill wallet data: {exc}")

    # posts table: view_count backs the generic per-post unique-view counter
    # (record_unique_view / log_post_view). The old "video" and "mentions"
    # columns were only ever used by the Reels feature, which has been
    # removed - they are intentionally no longer added here. Existing
    # databases that already have those columns keep them as unused legacy
    # fields (SQLite ALTER TABLE ... DROP COLUMN is version-dependent, so we
    # don't attempt to drop them automatically); nothing in the app writes
    # to them anymore.
    post_cols = {row[1] for row in db.execute("PRAGMA table_info(posts)")}
    post_new_columns = {
        "view_count": "INTEGER DEFAULT 0",
        "status": "TEXT DEFAULT 'approved'",
    }
    for col, coltype in post_new_columns.items():
        if col not in post_cols:
            db.execute(f"ALTER TABLE posts ADD COLUMN {col} {coltype}")
    db.commit()

    # token_transactions table: add post_id (ties share_job rewards to a
    # specific post so the same post can't be repeatedly rewarded)
    try:
        tx_cols = {row[1] for row in db.execute("PRAGMA table_info(token_transactions)")}
        if "post_id" not in tx_cols:
            db.execute("ALTER TABLE token_transactions ADD COLUMN post_id INTEGER DEFAULT NULL")
        db.commit()
    except Exception:
        # Some test environments or older installs do not have the table yet.
        pass

    db.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.commit()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ntype TEXT DEFAULT 'info',   -- 'info' / 'warning' / 'deposit' / 'withdrawal' / 'ban'
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS announcement_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(announcement_id, user_id),
            FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    db.commit()

    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts (user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_posts_status_created_at ON posts (status, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes (post_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes (user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments (post_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_saved_posts_user_post ON saved_posts (user_id, post_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_applicant_post ON job_applications (applicant_id, post_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_follows_follower_id ON follows (follower_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_follows_followed_id ON follows (followed_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status_type_created_at ON wallet_transactions (status, tx_type, created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions (user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_payments_status_created_at ON payments (status, created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_reports_status_created_at ON reports (status, created_at)")
        db.commit()
    except Exception as exc:
        print(f"Warning: could not create SQLite indexes: {exc}")

    settings_existing = {row[0] for row in db.execute("SELECT key FROM app_settings")}
    if "telebirr_wallet_number" not in settings_existing:
        db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("telebirr_wallet_number", TELEBIRR_WALLET_NUMBER, datetime.datetime.utcnow().isoformat()),
        )
    db.commit()

    # wallet_transactions table: add deposit ticket fields if missing
    wallet_cols = {row[1] for row in db.execute("PRAGMA table_info(wallet_transactions)")}
    wallet_new_columns = {
        "transaction_ref": "TEXT DEFAULT NULL",
        "bank": "TEXT DEFAULT NULL",
        "note": "TEXT DEFAULT NULL",
        "receipt_photo": "TEXT DEFAULT NULL",
        "account_number": "TEXT DEFAULT NULL",
        "account_name": "TEXT DEFAULT NULL",
        "refunded_at": "TEXT DEFAULT NULL",
        "refunded_by": "INTEGER DEFAULT NULL",
    }
    for col, coltype in wallet_new_columns.items():
        if col not in wallet_cols:
            db.execute(f"ALTER TABLE wallet_transactions ADD COLUMN {col} {coltype}")
    db.commit()

    # Admin revenue payout ledger: tracks manual withdrawals of platform
    # revenue (badge sales, platform fees) out to a recipient wallet/user.
    # Available balance is always computed as (total revenue - sum of prior
    # withdrawals) rather than stored as a mutable counter, so it can never
    # drift out of sync with the underlying revenue sources.
    db.execute("""
        CREATE TABLE IF NOT EXISTS admin_revenue_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            recipient_label TEXT NOT NULL,
            recipient_user_id INTEGER DEFAULT NULL,
            admin_id INTEGER NOT NULL,
            note TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(admin_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(recipient_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    db.commit()

    # backfill referral codes for any user who doesn't have one yet
    rows = db.execute(
        "SELECT id, username FROM users WHERE referral_code IS NULL OR referral_code = ''"
    ).fetchall()
    for uid, uname in rows:
        code = f"{(uname or 'user')[:6].upper()}{uid}{secrets.token_hex(2).upper()}"
        db.execute("UPDATE users SET referral_code = ? WHERE id = ?", (code, uid))
    db.commit()

    # add verification and password-reset columns for existing installs safely
    user_cols = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    for col, coltype in {
        "email_verified": "INTEGER DEFAULT 0",
        "email_verification_code": "TEXT DEFAULT NULL",
        "password_reset_code": "TEXT DEFAULT NULL",
        "password_reset_expires": "TEXT DEFAULT NULL",
        "email_verified_at": "TEXT DEFAULT NULL",
        "strikes": "INTEGER DEFAULT 0",
        "trust_score": "INTEGER DEFAULT 0",
        "is_suspended": "INTEGER DEFAULT 0",
        "is_trusted_seller": "INTEGER DEFAULT 0",
    }.items():
        if col not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
    db.commit()

    post_cols = {row[1] for row in db.execute("PRAGMA table_info(posts)")}
    for col, coltype in {"status": "TEXT DEFAULT 'approved'"}.items():
        if col not in post_cols:
            db.execute(f"ALTER TABLE posts ADD COLUMN {col} {coltype}")
    db.commit()

    product_cols = {row[1] for row in db.execute("PRAGMA table_info(products)")}
    for col, coltype in {
        "location": "TEXT DEFAULT 'Addis Ababa'",
        "status": "TEXT DEFAULT 'pending'",
        "photo": "TEXT DEFAULT NULL",
    }.items():
        if col not in product_cols:
            db.execute(f"ALTER TABLE products ADD COLUMN {col} {coltype}")
    db.commit()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            project_url TEXT DEFAULT NULL,
            image_path TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    db.commit()

    try:
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_ci ON users (lower(username))")
        db.commit()
    except Exception as exc:
        print(f"Warning: could not create case-insensitive username index: {exc}")
    db.close()


def ensure_database_schema():
    """Ensure the database schema exists and is upgraded safely on startup."""
    try:
        if hasattr(app, "extensions") and "sqlalchemy" in app.extensions:
            db = app.extensions["sqlalchemy"]
            db.create_all()
        elif is_sqlite_database():
            init_db()
        else:
            init_postgres_db()
    except Exception as exc:
        print(f"Database schema initialization failed: {exc}")
        raise


def ensure_postgres_admin_user():
    if is_sqlite_database():
        return

    try:
        db = get_db()
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")
        db.commit()
    except Exception as exc:
        print(f"Warning: could not ensure PostgreSQL is_admin column: {exc}")

    try:
        db = get_db()
        db.execute("UPDATE users SET is_admin = true WHERE username = ?", ("Tofik",))
        db.commit()
    except Exception as exc:
        print(f"Warning: could not set Tofik as admin in PostgreSQL: {exc}")


def ensure_postgres_boolean_columns():
    if is_sqlite_database():
        return

    try:
        db = get_db()
        boolean_columns = [
            ("users", "is_admin", "FALSE"),
            ("users", "is_banned", "FALSE"),
            ("users", "is_suspended", "FALSE"),
            ("bank_accounts", "is_active", "FALSE"),
        ]
        for table, column, default in boolean_columns:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} BOOLEAN DEFAULT {default}")
                db.commit()
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                print(f"Warning: could not add boolean column {table}.{column}: {exc}")

            try:
                db.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

            try:
                db.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BOOLEAN USING CASE "
                    f"WHEN COALESCE({column}::text, '') IN ('1', 'true', 't', 'yes', 'y', 'on') THEN TRUE "
                    f"ELSE FALSE END"
                )
                db.commit()
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                print(f"Warning: could not cast {table}.{column} to boolean: {exc}")

            try:
                db.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default}")
                db.commit()
            except Exception as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                print(f"Warning: could not set default for {table}.{column}: {exc}")
    except Exception as exc:
        print(f"Warning: could not ensure PostgreSQL boolean columns: {exc}")


def ensure_postgres_wallet_columns():
    if is_sqlite_database():
        return
    try:
        db = get_db()
        # Ensure wallet-related columns exist
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_id TEXT UNIQUE DEFAULT NULL")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance INTEGER DEFAULT 0")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS alta_tokens INTEGER DEFAULT 0")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_until TEXT DEFAULT NULL")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_tier TEXT DEFAULT 'none'")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_until TEXT DEFAULT NULL")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT DEFAULT NULL")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE")
        db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code TEXT DEFAULT NULL")
        db.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS receipt_image_path TEXT DEFAULT NULL")
        db.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS recipient_wallet_id TEXT DEFAULT NULL")
        db.execute("ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name TEXT DEFAULT NULL")
        db.execute("ALTER TABLE bank_accounts ALTER COLUMN is_active TYPE BOOLEAN USING is_active::BOOLEAN")
        # Add posts engagement columns
        db.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0")
        db.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS virality_score REAL DEFAULT 0.0")
        # Initialize/fill sensible defaults for existing rows
        try:
            db.execute("UPDATE users SET wallet_balance = COALESCE(wallet_balance, 0), alta_tokens = COALESCE(alta_tokens, 0)")
            db.execute("UPDATE posts SET view_count = COALESCE(view_count, 0), virality_score = COALESCE(virality_score, 0.0)")
            _backfill_missing_wallet_ids(db)
        except Exception:
            # If the update fails for any reason, ignore to avoid aborting startup
            pass
        db.commit()
    except Exception as exc:
        print(f"Warning: could not ensure PostgreSQL wallet columns: {exc}")

    try:
        db = get_db()
        db.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS photo TEXT DEFAULT NULL")
        db.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS location TEXT DEFAULT 'Addis Ababa'")
        db.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
        db.execute("CREATE TABLE IF NOT EXISTS portfolio_items (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT, project_url TEXT DEFAULT NULL, image_path TEXT DEFAULT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)")
        db.commit()
    except Exception as exc:
        print(f"Warning: could not ensure PostgreSQL product columns: {exc}")


with app.app_context():
    print(f"Resolved DATABASE_URL={DATABASE_URL}")
    print(f"Using SQLite={USE_SQLITE} DATABASE={DATABASE}")
    ensure_database_schema()
    ensure_postgres_admin_user()
    ensure_postgres_boolean_columns()
    ensure_postgres_wallet_columns()
    try:
        db = get_db()
        updated = backfill_verification_flags(db)
        if updated:
            print(f"Backfilled legacy verification flags for {updated} users.")
    except Exception as exc:
        print(f"Warning: could not backfill verification flags on startup: {exc}")


# ---------------------------------------------------------------------------
# Language / i18n
# ---------------------------------------------------------------------------
@app.before_request
def set_language():
    if "lang" not in session:
        session["lang"] = DEFAULT_LANG
    if request.path.startswith("/static") or request.path.startswith("/uploads"):
        return
    if request.path in {"/set_language/en", "/set_language/am"}:
        return


@app.before_request
def check_banned():
    uid = session.get("user_id")
    if uid:
        try:
            db = get_db()
            row = db.execute("SELECT is_banned, banned_until FROM users WHERE id = ?", (uid,)).fetchone()
            if row and row.get("is_banned"):
                banned_until = row.get("banned_until")
                return render_template("banned.html", banned_until=banned_until), 403
        except Exception:
            # If DB check fails, don't block the request.
            pass
@app.route("/set_language/<lang>")
def set_language_route(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("feed"))


@app.context_processor
def inject_translator():
    lang = session.get("lang", DEFAULT_LANG)
    user = get_current_user()
    unread_count = 0
    suggested_channels = []
    if user:
        db = get_db()
        try:
            row = db.execute(
                """SELECT COUNT(*) c FROM messages
                   JOIN conversations ON messages.conversation_id = conversations.id
                   WHERE conversations.status = 'accepted'
                     AND messages.sender_id != ?
                     AND messages.seen_at IS NULL
                     AND (conversations.user1_id = ? OR conversations.user2_id = ?)""",
                (user["id"], user["id"], user["id"]),
            ).fetchone()
            unread_count = int(_get_row_value(row, "c", 0) or 0)
        except Exception:
            unread_count = 0

        try:
            suggested_channels = db.execute(
                """SELECT channels.*, (SELECT COUNT(*) FROM channel_members WHERE channel_id = channels.id) as member_count
                   FROM channels ORDER BY channels.created_at DESC LIMIT 5"""
            ).fetchall()
        except Exception:
            suggested_channels = []
    return {
        "t": get_translator(lang),
        "current_lang": lang,
        "current_user": user,
        "unread_message_count": unread_count,
        "trial_days_left": trial_days_left(user) if user else 0,
        "suggested_channels": suggested_channels,
    }


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _get_row_value(row, key, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            pass
    try:
        return getattr(row, key)
    except Exception:
        return default


def _get_table_columns(db, table_name):
    try:
        if getattr(db, "is_sqlite", False):
            rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
            return {row[1] for row in rows}
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position",
            (table_name,),
        ).fetchall()
        return {row[0] if not hasattr(row, "keys") else (row.get("column_name") or row.get("name")) for row in rows}
    except Exception:
        return set()


def _table_has_column(db, table_name, column_name):
    return column_name in _get_table_columns(db, table_name)


def _table_exists(db, table_name):
    try:
        if getattr(db, "is_sqlite", False):
            rows = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)).fetchall()
            return bool(rows)
        rows = db.execute(
            "SELECT to_regclass(?)",
            (table_name,),
        ).fetchall()
        return bool(rows and rows[0][0])
    except Exception:
        return False


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row is not None else None


def backfill_verification_flags(db):
    """Ensure legacy verified flags are consistent with verification_tier."""
    if not _table_has_column(db, "users", "is_verified") or not _table_has_column(db, "users", "is_vip"):
        return 0
    rows = db.execute(
        "SELECT id, verification_tier FROM users WHERE verification_tier IN ('blue', 'gold')"
    ).fetchall()
    updated = 0
    for row in rows:
        tier = _get_row_value(row, "verification_tier", "none")
        if tier not in ("blue", "gold"):
            continue
        is_vip = 1 if tier == "gold" else 0
        cur = db.execute(
            "UPDATE users SET is_verified = 1, is_vip = ? WHERE id = ?",
            (is_vip, _get_row_value(row, "id")),
        )
        updated += cur.rowcount if hasattr(cur, 'rowcount') else 1
    if updated:
        try:
            db.commit()
        except Exception:
            pass
    return updated


def _credit_wallet_balance(db, user_id, amount):
    """Credit a user wallet in both legacy and modern wallet balance columns."""
    amount = float(amount or 0)
    if amount <= 0:
        return
    if _table_has_column(db, "users", "wallet_balance"):
        db.execute(
            "UPDATE users SET wallet_balance = COALESCE(wallet_balance, 0) + ? WHERE id = ?",
            (amount, user_id),
        )
    if _table_has_column(db, "users", "balance"):
        db.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?",
            (amount, user_id),
        )
    if _table_has_column(db, "users", "wallet_balance") and _table_has_column(db, "users", "balance"):
        db.execute(
            "UPDATE users SET balance = wallet_balance WHERE id = ?",
            (user_id,),
        )


def _get_user_effective_balance(user):
    if not user:
        return 0.0
    wallet_balance_value = float(_get_row_value(user, "wallet_balance", 0) or 0)
    balance_value = float(_get_row_value(user, "balance", 0) or 0)
    return max(wallet_balance_value, balance_value)


def _debit_user_balance(db, user_id, amount):
    amount = float(amount or 0)
    if amount <= 0:
        return True

    if _table_has_column(db, "users", "wallet_balance"):
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ? AND wallet_balance >= ?",
            (amount, user_id, amount),
        )
        if getattr(cur, "rowcount", 0):
            if _table_has_column(db, "users", "balance"):
                db.execute("UPDATE users SET balance = wallet_balance WHERE id = ?", (user_id,))
            return True

    if _table_has_column(db, "users", "balance"):
        cur = db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
            (amount, user_id, amount),
        )
        if getattr(cur, "rowcount", 0):
            if _table_has_column(db, "users", "wallet_balance"):
                db.execute("UPDATE users SET wallet_balance = balance WHERE id = ?", (user_id,))
            return True

    return False


def _get_user_wallet_balance(user):
    if not user:
        return 0.0
    wallet_balance_value = float(_get_row_value(user, "wallet_balance", 0) or 0)
    balance_value = float(_get_row_value(user, "balance", 0) or 0)
    return wallet_balance_value if wallet_balance_value > balance_value else balance_value


def _debit_user_wallet_balance(db, user_id, amount):
    amount = float(amount or 0)
    if amount <= 0:
        return True
    if _table_has_column(db, "users", "wallet_balance"):
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ? AND wallet_balance >= ?",
            (amount, user_id, amount),
        )
        if getattr(cur, "rowcount", 0):
            return True
    if _table_has_column(db, "users", "balance"):
        cur = db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
            (amount, user_id, amount),
        )
        if getattr(cur, "rowcount", 0):
            if _table_has_column(db, "users", "wallet_balance"):
                db.execute("UPDATE users SET wallet_balance = balance WHERE id = ?", (user_id,))
            return True
    return False


@app.before_request
def enforce_maintenance_mode():
    # Allow static assets and admin settings to be reachable for admins.
    path = request.path or ""
    if path.startswith("/static/"):
        return
    # Skip enforcement for the admin settings endpoints so admins can toggle it.
    if request.endpoint in ("admin_settings", "admin_panel", "admin_login", "static"):
        return
    try:
        if get_setting("maintenance_mode", "0") == "1":
            user = None
            try:
                user = get_current_user()
            except Exception:
                user = None
            if not user or not user.get("is_admin"):
                return render_template("maintenance.html"), 503
    except Exception:
        # On any error, fail open (don't block requests)
        return


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))

        db = get_db()
        placeholder = "%s" if not getattr(db, "is_sqlite", False) else "?"
        user = db.execute(
            f"SELECT is_banned, banned_until FROM users WHERE id = {placeholder}",
            (uid,),
        ).fetchone()
        if not user:
            # session points at an account that no longer exists
            session.pop("user_id", None)
            return redirect(url_for("login"))

        if is_currently_banned(user):
            session.pop("user_id", None)
            flash("account_banned")
            return redirect(url_for("login"))

        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not _get_row_value(user, "is_admin", False):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def subscription_active(user):
    """ተጠቃሚው ነጻ ጊዜ ውስጥ ነው ወይስ ከፍሏል የሚለውን ይመልሳል"""
    if not user:
        return False
    try:
        created = datetime.datetime.fromisoformat(_get_row_value(user, "created_at"))
    except Exception:
        return True
    trial_end = created + datetime.timedelta(days=FREE_TRIAL_DAYS)
    if datetime.datetime.utcnow() <= trial_end:
        return True
    paid_until = None
    try:
        paid_until = user.get("paid_until") if hasattr(user, "get") else user["paid_until"]
    except Exception:
        paid_until = None
    if paid_until:
        try:
            paid_until = datetime.datetime.fromisoformat(paid_until)
            if datetime.datetime.utcnow() <= paid_until:
                return True
        except Exception:
            pass
    return False


def trial_days_left(user):
    try:
        created = datetime.datetime.fromisoformat(_get_row_value(user, "created_at"))
    except Exception:
        return 0
    trial_end = created + datetime.timedelta(days=FREE_TRIAL_DAYS)
    delta = trial_end - datetime.datetime.utcnow()
    return max(delta.days, 0)


def subscription_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user and _get_row_value(user, "is_admin", False):
            return f(*args, **kwargs)
        if not subscription_active(user):
            return redirect(url_for("subscribe"))
        return f(*args, **kwargs)
    return wrapper


DAILY_POST_LIMIT = 1   # standard posts per day once the free trial has ended


def _daily_post_count(db, user_id, kind="standard"):
    # kind is always 'standard' now that Reels has been removed; the
    # parameter is kept so any remaining callers don't need to change.
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    row = db.execute(
        """SELECT COUNT(*) c FROM posts
            WHERE user_id = ? AND created_at LIKE ?""",
        (user_id, f"{today}%"),
    ).fetchone()
    return row["c"]


def daily_limit_required(kind="standard"):
    """After the free trial ends, non-subscribers can still use the app but
    are capped at 1 standard post per day instead of being locked out
    entirely. Admins and active subscribers/trial users are never limited."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for("login"))
            if _get_row_value(user, "is_admin", False) or subscription_active(user):
                return f(*args, **kwargs)

            db = get_db()
            count = _daily_post_count(db, user["id"])
            if count >= DAILY_POST_LIMIT:
                flash("daily_post_limit_reached")
                return redirect(url_for("feed"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def is_currently_banned(user):
    """True if the user is permanently banned, or has an active temporary ban."""
    if not user:
        return False
    if _get_row_value(user, "is_banned", False):
        return True
    banned_until = _get_row_value(user, "banned_until")
    if banned_until and datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(banned_until):
        return True
    return False


def add_notification(db, user_id, message, ntype="info"):
    """Insert a notification that shows up in the user's notification feed."""
    db.execute(
        "INSERT INTO notifications (user_id, ntype, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, ntype, message, datetime.datetime.utcnow().isoformat()),
    )


def get_restricted_words(db):
    try:
        rows = db.execute("SELECT word FROM restricted_words ORDER BY word").fetchall()
    except Exception:
        return []
    return [row["word"] for row in rows]


def contains_restricted_word(text, db=None):
    if not text:
        return None
    if db is None:
        db = get_db()
    words = get_restricted_words(db)
    lowered = (text or "").casefold()
    for word in words:
        if word and word.casefold() in lowered:
            return word
    return None


def add_strike(db, user_id, reason="policy_violation"):
    user = db.execute("SELECT id, strikes, is_suspended FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return None
    new_strikes = (user["strikes"] or 0) + 1
    db.execute("UPDATE users SET strikes = ? WHERE id = ?", (new_strikes, user_id))
    if new_strikes >= 3:
        db.execute("UPDATE users SET is_suspended = true WHERE id = ?", (user_id,))
        add_notification(db, user_id, "Your account has been suspended after repeated policy violations.", ntype="ban")
    else:
        add_notification(db, user_id, f"A post was removed for violating community rules. Strike {new_strikes}/3.", ntype="warning")
    return new_strikes


def refresh_trust_status(db, user_id):
    user = db.execute("SELECT id, strikes, is_suspended FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return None
    approved_count = db.execute(
        "SELECT COUNT(*) c FROM posts WHERE user_id = ? AND status = 'approved'",
        (user_id,),
    ).fetchone()["c"]
    trusted = approved_count >= 3 and (user["strikes"] or 0) == 0 and not user["is_suspended"]
    db.execute(
        "UPDATE users SET trust_score = ?, is_trusted_seller = ? WHERE id = ?",
        (100 if trusted else 0, 1 if trusted else 0, user_id),
    )
    return trusted


def review_listing(db, user_id, title, description):
    blocked_word = contains_restricted_word((title or "") + " " + (description or ""), db)
    if blocked_word:
        add_strike(db, user_id, reason=f"blocked_word:{blocked_word}")
        return "rejected"
    user = db.execute("SELECT strikes, is_suspended, is_trusted_seller FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user["is_suspended"]:
        return "rejected"
    if user and user["is_trusted_seller"]:
        return "approved"
    return "pending"


def record_announcement_view(db, user_id, announcement_id):
    if not user_id or not announcement_id:
        return False
    existing = db.execute(
        "SELECT id FROM announcement_views WHERE announcement_id = ? AND user_id = ?",
        (announcement_id, user_id),
    ).fetchone()
    if existing:
        return False
    db.execute(
        "INSERT INTO announcement_views (announcement_id, user_id, created_at) VALUES (?, ?, ?)",
        (announcement_id, user_id, datetime.datetime.utcnow().isoformat()),
    )
    db.execute("UPDATE announcements SET view_count = view_count + 1 WHERE id = ?", (announcement_id,))
    return True


def _field(u, k):
    """Shared row-field accessor: works with dicts, sqlite3.Row, or objects."""
    try:
        if isinstance(u, dict):
            return u.get(k)
        return u[k]
    except Exception:
        return getattr(u, k, None)


@app.template_global()
def get_verification_tier(user):
    """Single source of truth for a user's *effective* verification tier.
    Reads the new verification_tier/verified_until columns, honors expiry,
    and falls back to the legacy is_verified/is_vip flags for any row that
    hasn't been backfilled yet. Always returns 'none', 'blue', or 'gold'."""
    if not user:
        return "none"
    tier = _field(user, "verification_tier") or "none"
    if tier not in ("blue", "gold"):
        # Legacy row that predates the tier column
        if _field(user, "is_vip"):
            tier = "gold"
        elif _field(user, "is_verified"):
            tier = "blue"
        else:
            return "none"
    until = _field(user, "verified_until")
    if not until:
        # No expiry set (e.g. admin-granted or legacy backfilled row) —
        # treat as a permanently active badge instead of hiding it.
        return tier
    try:
        if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(until):
            return "none"
    except Exception:
        # Unparseable date shouldn't silently hide a real badge either.
        return tier
    return tier


def set_verification_tier(db, user_id, tier, until):
    """Write a verification tier + expiry. `until` is a datetime.
    (Legacy is_verified/is_vip/vip_until columns have been dropped from the
    users table - verification_tier/verified_until are now the only source
    of truth.)"""
    until_iso = until.isoformat()
    db.execute(
        "UPDATE users SET verification_tier = ?, verified_until = ? WHERE id = ?",
        (tier, until_iso, user_id),
    )


def is_currently_verified(user):
    """Return True if the user is currently verified (Blue or Gold).

    Uses the effective verification tier logic from get_verification_tier(), so
    legacy rows that still use is_verified/is_vip remain supported.
    """
    return get_verification_tier(user) in ("blue", "gold")


def is_currently_vip(user):
    """Return True if the user is currently VIP/Gold.

    Uses get_verification_tier() so legacy VIP rows continue to work.
    """
    return get_verification_tier(user) == "gold"


def channel_is_verified(channel):
    """ቻናሉ/ቡድኑ አሁን ላይ Blue Tick አለው ወይስ የለውም የሚለውን ይመልሳል።
    ይህ በራሱ ጊዜው ካለፈ በኋላ Blue Tick ን በራስሰር 'ያነሳል' - cron ሳያስፈልግ፣
    ልክ እንደ ተጠቃሚ verification ተመሳሳይ በሆነ መንገድ በእያንዳንዱ ጭነት ላይ ይሰላል።"""
    if not channel:
        return False
    def _field(u, k):
        try:
            if isinstance(u, dict):
                return u.get(k)
            return u[k]
        except Exception:
            return getattr(u, k, None)

    if not _field(channel, "is_verified") or not _field(channel, "verified_until"):
        return False
    return datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(_field(channel, "verified_until"))


def channel_verification_days_left(channel):
    if not channel or not channel.get("verified_until"):
        return None
    delta = datetime.datetime.fromisoformat(channel["verified_until"]) - datetime.datetime.utcnow()
    return max(0, delta.days)


def channel_verification_expiring_soon(channel):
    """ለ 7-ቀን ማስጠንቀቂያ ባነር የሚያገለግል - cron ሳይሆን በእያንዳንዱ ገጽ ጭነት ላይ በቀጥታ ይሰላል"""
    if not channel_is_verified(channel):
        return False
    days_left = channel_verification_days_left(channel)
    return days_left is not None and days_left <= CHANNEL_VERIFICATION_WARNING_DAYS


@app.context_processor
def inject_gift_catalog():
    return {
        "gift_catalog": GIFT_CATALOG,
        "is_verified_now": is_currently_verified,
        "is_vip_now": is_currently_vip,
        "channel_is_verified": channel_is_verified,
        "channel_verification_days_left": channel_verification_days_left,
        "channel_verification_expiring_soon": channel_verification_expiring_soon,
    }


@app.context_processor
def inject_announcements():
    user = get_current_user()
    announcement = None
    dismissed_ids = set(session.get("dismissed_announcements", [])) if session else set()
    if user:
        try:
            db = get_db()
            rows = db.execute(
                "SELECT * FROM announcements WHERE is_pinned = 1 OR id IN (SELECT id FROM announcements ORDER BY created_at DESC LIMIT 10) ORDER BY is_pinned DESC, created_at DESC"
            ).fetchall()
            for row in rows:
                if row["id"] in dismissed_ids:
                    continue
                record_announcement_view(db, user["id"], row["id"])
                announcement = row
                break
        except Exception:
            announcement = None
    return {"active_announcement": announcement}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# --- Optional Cloud Storage (Cloudinary) -------------------------------
# Render's local disk is ephemeral — anything saved to it is wiped on every
# restart/redeploy/sleep cycle. Set these 3 environment variables to persist
# all avatars, post photos, receipts, and reels permanently on Cloudinary:
#   CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")

_cloudinary_enabled = False
if (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET) or CLOUDINARY_URL:
    try:
        import cloudinary
        import cloudinary.uploader
        if CLOUDINARY_URL:
            cloudinary.config(cloudinary_url=CLOUDINARY_URL, secure=True)
        else:
            cloudinary.config(
                cloud_name=CLOUDINARY_CLOUD_NAME,
                api_key=CLOUDINARY_API_KEY,
                api_secret=CLOUDINARY_API_SECRET,
                secure=True,
            )
        _cloudinary_enabled = True
        print("✅ Cloudinary connected — uploads will persist permanently in the cloud.")
    except ImportError:
        print("⚠️  'cloudinary' package not installed (pip install cloudinary). "
              "Falling back to Supabase/local file storage.")
    except Exception as e:
        print(f"⚠️  Could not configure Cloudinary ({e}). Falling back to Supabase/local file storage.")


def _upload_to_cloudinary(file_storage, folder="altajobs"):
    """Uploads a werkzeug FileStorage to Cloudinary and returns the permanent
    HTTPS secure_url, or None if the upload fails."""
    try:
        file_storage.stream.seek(0)
        result = cloudinary.uploader.upload(
            file_storage,
            folder=folder,
            resource_type="auto",  # auto-detects image vs video (needed for reels)
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"⚠️  Cloudinary upload failed ({e}); falling back to next storage option.")
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        return None


# --- Optional Cloud Storage (Supabase) --------------------------------
# Not configured by default -> app keeps working exactly as before with
# local disk storage. Set these 3 environment variables to switch uploads
# (avatars, post photos) to Supabase Storage without touching any other code:
#   SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET (optional, default below)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "altajobs-uploads")

_supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase Storage connected — uploads will be stored in the cloud.")
    except ImportError:
        print("⚠️  'supabase' package not installed (pip install supabase). "
              "Falling back to local file storage.")
    except Exception as e:
        print(f"⚠️  Could not connect to Supabase ({e}). Falling back to local file storage.")


def save_photo(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    unique = f"{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"

    if _cloudinary_enabled:
        url = _upload_to_cloudinary(file_storage, folder="altajobs")
        if url:
            print(f"Cloudinary upload successful: {url}")
            return url
        print("Cloudinary upload returned no URL; falling back to local/Supabase storage.")

    if _supabase_client:
        try:
            file_bytes = file_storage.read()
            content_type = file_storage.mimetype or "application/octet-stream"
            _supabase_client.storage.from_(SUPABASE_BUCKET).upload(
                unique, file_bytes, {"content-type": content_type}
            )
            # Store the full public URL - photo_url() below passes it through as-is
            return _supabase_client.storage.from_(SUPABASE_BUCKET).get_public_url(unique)
        except Exception as e:
            print(f"⚠️  Supabase upload failed ({e}); saving locally instead.")
            file_storage.stream.seek(0)  # rewind so the local save below still works

    # --- Local disk storage (default behaviour, unchanged) ---
    try:
        local_path = os.path.join(app.config["UPLOAD_FOLDER"], unique)
        file_storage.save(local_path)
        print(f"Saved uploaded file locally: {local_path}")
        return unique
    except Exception as exc:
        print(f"Failed to save uploaded file locally: {exc}")
        return None


def save_cv_photo(file_storage):
    """Saves a CV portrait/passport photo to static/uploads/cv_photos/ (or
    Supabase Storage under a cv_photos/ prefix if configured), separately
    from the general post/avatar uploads folder."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    unique = f"{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"

    if _cloudinary_enabled:
        url = _upload_to_cloudinary(file_storage, folder="altajobs/cv_photos")
        if url:
            return url

    if _supabase_client:
        try:
            file_bytes = file_storage.read()
            content_type = file_storage.mimetype or "application/octet-stream"
            storage_key = f"cv_photos/{unique}"
            _supabase_client.storage.from_(SUPABASE_BUCKET).upload(
                storage_key, file_bytes, {"content-type": content_type}
            )
            return _supabase_client.storage.from_(SUPABASE_BUCKET).get_public_url(storage_key)
        except Exception as e:
            print(f"⚠️  Supabase CV photo upload failed ({e}); saving locally instead.")
            file_storage.stream.seek(0)

    file_storage.save(os.path.join(CV_PHOTO_FOLDER, unique))
    # stored value is prefixed so photo_url()/uploaded_file() can tell it
    # apart from a general upload and serve it from the right subfolder
    return f"cv_photos/{unique}"


@app.template_global()
def photo_url(value):
    """Resolve a stored photo value to a servable URL.
    Works transparently whether the file lives locally or on Supabase Storage."""
    if not value:
        return None
    value = str(value).strip().replace("\\", "/")
    if not value:
        return None
    if value.startswith(("http://", "https://", "//")):
        return value
    if os.path.isabs(value):
        uploads_root = os.path.normpath(app.config["UPLOAD_FOLDER"]).replace("\\", "/")
        normalized = os.path.normpath(value).replace("\\", "/")
        if normalized.startswith(uploads_root):
            value = normalized[len(uploads_root):].lstrip("/\\")
        else:
            value = os.path.basename(normalized)
    if value.startswith("/"):
        return value
    if value.startswith("static/"):
        value = value[len("static/"):]
    if value.startswith("uploads/"):
        value = value[len("uploads/"):]
    if value.startswith("/uploads/"):
        value = value[len("/uploads/"):]
    try:
        return url_for("uploaded_file", filename=value)
    except RuntimeError:
        return f"/uploads/{value}"


@app.template_global()
def activity_badge_for(user):
    """Return a human-friendly badge name based on user's points.
    Accepts dict-like or sqlite3.Row objects."""
    def _field(u, k):
        try:
            if isinstance(u, dict):
                return u.get(k)
            return u[k]
        except Exception:
            return getattr(u, k, None)

    points = _field(user, "points") or 0
    try:
        points = int(points)
    except Exception:
        points = 0
    if points >= 501:
        return "Gold Elite"
    if points >= 101:
        return "Silver Expert"
    return "Bronze Member"


@app.template_global()
def verification_days_left(user):
    """Return remaining verification days for the user, or None if not active."""
    until = _field(user, "verified_until")
    if not until:
        return None
    try:
        delta = datetime.datetime.fromisoformat(until) - datetime.datetime.utcnow()
        return max(0, delta.days)
    except Exception:
        return None


from markupsafe import Markup


_VERIFICATION_BADGE_SVG = {
    "blue": '''<span class="verification-badge verification-badge--blue" title="Verified">
            <svg viewBox="0 0 22 22" aria-hidden="true" focusable="false" width="18" height="18">
                <path fill="#1D9BF0" d="M20.396 11c0-1.196-.734-2.222-1.789-2.65.19-1.098-.128-2.301-.947-3.12-.82-.82-2.023-1.137-3.121-.947C14.111 3.228 13.085 2.494 11.89 2.494c-1.197 0-2.223.734-2.651 1.789-1.098-.19-2.301.127-3.12.947-.82.819-1.137 2.022-.947 3.12C4.228 8.778 3.494 9.804 3.494 11c0 1.196.734 2.222 1.789 2.65-.19 1.098.127 2.301.946 3.12.82.82 2.023 1.137 3.121.947.428 1.055 1.454 1.789 2.651 1.789 1.196 0 2.222-.734 2.65-1.789 1.098.19 2.301-.128 3.12-.947.82-.819 1.137-2.022.947-3.12 1.055-.428 1.789-1.454 1.789-2.65z"/>
                <path fill="#fff" d="M9.323 14.416l-3.5-3.5 1.415-1.415 2.085 2.085 4.939-4.939 1.415 1.415z"/>
            </svg>
        </span>''',
    "gold": '''<span class="verification-badge verification-badge--gold" title="Verified Organization">
            <svg viewBox="0 0 22 22" aria-hidden="true" focusable="false" width="18" height="18">
                <defs>
                    <linearGradient id="g_tier_gold" x1="0%" x2="100%" y1="0%" y2="100%">
                        <stop offset="0%" stop-color="#F9D976"/>
                        <stop offset="100%" stop-color="#C9A227"/>
                    </linearGradient>
                </defs>
                <path fill="url(#g_tier_gold)" d="M20.396 11c0-1.196-.734-2.222-1.789-2.65.19-1.098-.128-2.301-.947-3.12-.82-.82-2.023-1.137-3.121-.947C14.111 3.228 13.085 2.494 11.89 2.494c-1.197 0-2.223.734-2.651 1.789-1.098-.19-2.301.127-3.12.947-.82.819-1.137 2.022-.947 3.12C4.228 8.778 3.494 9.804 3.494 11c0 1.196.734 2.222 1.789 2.65-.19 1.098.127 2.301.946 3.12.82.82 2.023 1.137 3.121.947.428 1.055 1.454 1.789 2.651 1.789 1.196 0 2.222-.734 2.65-1.789 1.098.19 2.301-.128 3.12-.947.82-.819 1.137-2.022.947-3.12 1.055-.428 1.789-1.454 1.789-2.65z"/>
                <path fill="#3B2A00" d="M9.323 14.416l-3.5-3.5 1.415-1.415 2.085 2.085 4.939-4.939 1.415 1.415z"/>
            </svg>
        </span>''',
}


@app.template_global()
def verification_badge_svg(tier):
    """THE single source of the Blue/Gold verification checkmark markup.
    Every place that shows a verification badge (feed, profile, comments,
    this pricing page) must call this — never inline a copy of the SVG.
    Accepts a tier string ('none'/'blue'/'gold') OR a user object/row."""
    if tier not in ("none", "blue", "gold"):
        tier = get_verification_tier(tier)
    return Markup(_VERIFICATION_BADGE_SVG.get(tier, ""))


@app.template_global()
def badge_html_for(user):
    """Return small badge HTML reflecting activity badge and verification tier."""
    badge = activity_badge_for(user)
    tier = get_verification_tier(user)
    parts = []
    # Activity badge icon
    if badge.startswith("Gold"):
        parts.append('''<span class="user-badge user-badge--activity-gold" title="{t}">
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <defs>
                        <linearGradient id="g_gold" x1="0%" x2="100%" y1="0%" y2="100%">
                            <stop offset="0%" stop-color="#FFD54A"/>
                            <stop offset="100%" stop-color="#FFB300"/>
                        </linearGradient>
                    </defs>
                    <path fill="url(#g_gold)" d="M12 2l2.7 5.5L20 9l-4 3.6L17 19l-5-2.6L7 19l1-6.4L4 9l5.3-1.5L12 2z" />
                </svg>
            </span>'''.format(t=badge))
    elif badge.startswith("Silver"):
        parts.append('''<span class="user-badge user-badge--activity-silver" title="{t}">
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <defs>
                        <linearGradient id="g_silver" x1="0%" x2="100%" y1="0%" y2="100%">
                            <stop offset="0%" stop-color="#E0E0E0"/>
                            <stop offset="100%" stop-color="#BDBDBD"/>
                        </linearGradient>
                    </defs>
                    <path fill="url(#g_silver)" d="M12 2L4 5v6c0 5 4 9 8 11 4-2 8-6 8-11V5l-8-3z" />
                </svg>
            </span>'''.format(t=badge))
    else:
        parts.append('''<span class="user-badge user-badge--activity-bronze" title="{t}">
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <defs>
                        <linearGradient id="g_bronze" x1="0%" x2="100%" y1="0%" y2="100%">
                            <stop offset="0%" stop-color="#D7A86A"/>
                            <stop offset="100%" stop-color="#B87333"/>
                        </linearGradient>
                    </defs>
                    <circle cx="12" cy="12" r="9" fill="url(#g_bronze)" />
                </svg>
            </span>'''.format(t=badge))
    # Verification tier overlay (Blue/Gold) — delegates to the single
    # verification_badge_svg() source, never inlined here.
    parts.append(str(verification_badge_svg(tier)))

    return Markup(''.join(parts))


def get_setting(key, default=None):
    try:
        db = get_db()
        row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    except Exception:
        return default


@app.template_global()
def get_social_links():
    return {
        "google": (get_setting("social_google_url", "") or "").strip(),
        "telegram": (get_setting("social_telegram_url", "") or "").strip(),
        "discord": (get_setting("social_discord_url", "") or "").strip(),
    }


@app.template_global()
def social_auth_enabled():
    return get_setting("social_auth_enabled", "1") == "1"


def set_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return value


def get_active_banks():
    """Returns all currently-active admin-managed deposit bank accounts,
    for display on the wallet deposit form."""
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM bank_accounts WHERE is_active = ? ORDER BY bank_name", (True,)).fetchall()
    except Exception:
        return []
    return [_normalize_bank_row(row) for row in rows if _normalize_bank_row(row)]


def get_all_banks():
    """Returns all configured admin-managed deposit bank accounts."""
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM bank_accounts ORDER BY bank_name").fetchall()
    except Exception:
        return []
    return [_normalize_bank_row(row) for row in rows if _normalize_bank_row(row)]


def _generate_cv_payload(form_data, photo=None):
    full_name = (form_data.get("full_name") or "").strip() or "Your Name"
    target_role = (form_data.get("target_role") or "").strip() or "Professional"
    summary = (form_data.get("summary") or "").strip()
    experience = (form_data.get("experience") or "").strip() or "3+ years of proven impact"
    achievements = [item.strip() for item in (form_data.get("achievements") or "").split("\n") if item.strip()]
    skills = [item.strip() for item in (form_data.get("skills") or "").split(",") if item.strip()]
    if not achievements:
        achievements = [
            "Led cross-functional execution with measurable measurable outcomes",
            "Built strong stakeholder relationships and reliable delivery",
        ]
    if not skills:
        skills = ["Communication", "Leadership", "Problem solving", "Teamwork"]

    summary_text = (
        f"{full_name} is a {target_role} focused on delivering high-impact work with professionalism, clarity, and measurable results. "
        f"With {experience}, they bring a balanced blend of execution, collaboration, and growth mindset."
        if not summary
        else summary
    )
    return {
        "full_name": full_name,
        "target_role": target_role,
        "summary": summary_text,
        "experience": experience,
        "skills": skills,
        "achievements": achievements,
        "photo": photo,
    }


# ---------------------------------------------------------------------------
# Monthly Business Challenge - helpers
# ---------------------------------------------------------------------------
def score_pitch_ai(pitch_text):
    """የ AI ውጤት ለቢዝነስ ፕላን ጽሑፍ ይሰጣል (0-100)።
    ANTHROPIC_API_KEY environment variable ካልተዘጋጀ፣ ቀላል heuristic scoring ይጠቀማል
    (ስራው እንዲሰራ) - እውነተኛ AI ውጤት ግን በ API key ብቻ ነው የሚገኘው።"""
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": (
                        "Score this business pitch from 0-100 on clarity, "
                        "feasibility, and practicality. Reply with ONLY the "
                        f"number, nothing else.\n\nPitch:\n{pitch_text[:3000]}"
                    ),
                }],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            score = float("".join(c for c in text if c.isdigit() or c == "."))
            return max(0.0, min(100.0, score))
        except Exception as e:
            print(f"⚠️ AI scoring failed ({e}); using fallback heuristic scoring.")

    # --- Fallback heuristic scoring (no API key configured) ---
    words = pitch_text.split()
    word_count = len(words)
    score = min(word_count / 2, 60)  # longer, more detailed pitches score higher, up to 60
    keywords = ["customer", "revenue", "market", "cost", "profit", "plan",
                "ደንበኛ", "ገቢ", "ወጪ", "ትርፍ", "እቅድ", "ገበያ"]
    score += sum(8 for kw in keywords if kw.lower() in pitch_text.lower())
    return round(max(5.0, min(95.0, score)), 1)


def get_or_create_pool(db, tier_amount):
    """የአሁኑን ወር pool ለተጠቀሰው tier ካለ ይመልሳል፣ ከሌለ ይፈጥራል"""
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    pool = db.execute(
        "SELECT * FROM challenge_pools WHERE tier_amount = ? AND month = ?",
        (tier_amount, month),
    ).fetchone()
    if pool:
        return pool
    db.execute(
        """INSERT INTO challenge_pools (tier_amount, month, platform_fee_percent, created_at)
           VALUES (?, ?, ?, ?)""",
        (tier_amount, month, CHALLENGE_PLATFORM_FEE_PERCENT,
         datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return db.execute(
        "SELECT * FROM challenge_pools WHERE tier_amount = ? AND month = ?",
        (tier_amount, month),
    ).fetchone()


def viral_gate_status(db, user_id):
    """ተጠቃሚው ውድድር ለመግባት የሚያስፈልገውን follow/share ደረጃ አሟልቷል ወይስ አላሟላም"""
    follows = db.execute(
        "SELECT COUNT(*) c FROM follows WHERE follower_id = ?", (user_id,)
    ).fetchone()["c"]
    shares = db.execute(
        "SELECT COUNT(*) c FROM challenge_shares WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    return {
        "follows": follows,
        "follows_needed": REQUIRED_FOLLOWS,
        "shares": shares,
        "shares_needed": REQUIRED_SHARES,
        "unlocked": follows >= REQUIRED_FOLLOWS and shares >= REQUIRED_SHARES,
    }


def compute_engagement_bonus(db, user_id):
    """ተጨማሪ follow እና referral (ከሚያስፈልገው በላይ) ትንሽ tie-breaker ጥቅም ይሰጣል።
    ይህ ውጤት በጭራሽ አሸናፊውን በዘፈቀደ አይመርጥም - ከ pitch ውጤት ጋር ተደምሮ ትንሽ ማሻሻያ ብቻ ነው።"""
    follows = db.execute(
        "SELECT COUNT(*) c FROM follows WHERE follower_id = ?", (user_id,)
    ).fetchone()["c"]
    referrals = db.execute(
        "SELECT COUNT(*) c FROM referrals WHERE referrer_id = ?", (user_id,)
    ).fetchone()["c"]
    extra_follows = max(0, follows - REQUIRED_FOLLOWS)
    bonus = min(extra_follows * 0.2 + referrals * 0.5, MAX_ENGAGEMENT_BONUS)
    return round(bonus, 1)


# ---------------------------------------------------------------------------
# Alta Token Economy - helpers
# ---------------------------------------------------------------------------
def is_profile_complete(user):
    """ማንኛውም ተጠቃሚ ሙሉ መገለጫ አለው ወይስ የለውም የሚለውን ይመልሳል (ለ profile_completion task)"""
    if not (user["full_name"] and user["phone"] and user["bio"]):
        return False
    if user["user_type"] == "worker" and not (user["skills"] and user["experience"]):
        return False
    return True


def daily_task_tokens_earned(db, user_id):
    """ዛሬ ከ task ብቻ (ከ check-in ውጪ) የተገኘውን ጠቅላላ ቶክን ይመልሳል"""
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    row = db.execute(
        """SELECT COALESCE(SUM(amount), 0) total FROM token_transactions
           WHERE user_id = ? AND kind != 'checkin' AND created_at LIKE ?""",
        (user_id, f"{today}%"),
    ).fetchone()
    return row["total"]


def has_completed_task(db, user_id, kind):
    return db.execute(
        "SELECT 1 FROM token_transactions WHERE user_id = ? AND kind = ? LIMIT 1",
        (user_id, kind),
    ).fetchone() is not None


def award_task_reward(db, user_id, kind, post_id=None):
    """Awards a task-to-earn reward with anti-abuse rules baked in:
    - 'profile_completion' can only ever be earned once, globally.
    - 'share_job' can only be earned ONCE PER POST (post_id) per user -
      repeatedly sharing the same job post no longer pays out more than
      once, closing the exploit.
    - The combined daily task cap (DAILY_TASK_CAP) still applies on top.
    Returns the reward amount if it was awarded, or None if blocked."""
    if kind not in TASK_REWARDS:
        return None
    if kind == "profile_completion":
        if has_completed_task(db, user_id, kind):
            return None
    elif post_id is not None:
        already = db.execute(
            "SELECT 1 FROM token_transactions WHERE user_id = ? AND kind = ? AND post_id = ?",
            (user_id, kind, post_id),
        ).fetchone()
        if already:
            return None

    reward = TASK_REWARDS[kind]
    already_today = daily_task_tokens_earned(db, user_id)
    if already_today + reward > DAILY_TASK_CAP:
        return None

    now = datetime.datetime.utcnow().isoformat()
    db.execute("UPDATE users SET alta_tokens = alta_tokens + ? WHERE id = ?", (reward, user_id))
    db.execute(
        """INSERT INTO token_transactions (user_id, kind, amount, post_id, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, kind, reward, post_id, now),
    )
    db.commit()
    return reward


def checkin_status(user):
    """ተጠቃሚው አሁን check-in ማድረግ ይችላል ወይስ አይችልም፣ እና ምን ያህል ሰዓት እንደቀረው ይመልሳል"""
    if not user["last_checkin"]:
        return {"can_checkin": True, "hours_remaining": 0}
    last = datetime.datetime.fromisoformat(user["last_checkin"])
    hours_passed = (datetime.datetime.utcnow() - last).total_seconds() / 3600
    if hours_passed >= 24:
        return {"can_checkin": True, "hours_remaining": 0}
    return {"can_checkin": False, "hours_remaining": round(24 - hours_passed, 1)}


def record_unique_view(db, post_id, user_id):
    """አንድ ተጠቃሚ አንድ ፖስት ቢያንስ አንድ ጊዜ ብቻ እንደ 'view' እንዲቆጠር ያደርጋል።
    Returns True if this is a brand-new unique view (so callers can award
    view-based token rewards), False if this user already viewed it before."""
    try:
        db.execute(
            "INSERT INTO post_views (post_id, user_id, created_at) VALUES (?, ?, ?)",
            (post_id, user_id, datetime.datetime.utcnow().isoformat()),
        )
        db.execute("UPDATE posts SET view_count = view_count + 1 WHERE id = ?", (post_id,))
        db.commit()
        return True
    except (sqlite3.IntegrityError, PG_INTEGRITY_ERROR):
        # already viewed by this user before - not counted again. This must
        # catch BOTH sqlite3's and psycopg2's IntegrityError classes: on
        # Postgres, re-visiting a post you've already viewed (e.g. the
        # redirect back to post_detail() right after posting a comment)
        # raises psycopg2's IntegrityError, which is a different class from
        # sqlite3.IntegrityError. Catching only the sqlite3 one meant this
        # exception went uncaught on Postgres and surfaced as a 500 error
        # every single time a post was viewed a second time.
        try:
            db.rollback()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.datetime.utcnow().isoformat()


def _generate_code(length=6):
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def _normalize_username(username):
    return (username or "").strip().casefold()


def _password_meets_policy(password):
    if not password or len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[^A-Za-z0-9]", password):
        return False
    return True


def _send_email(subject, recipient, body):
    if not recipient:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = app.config["MAIL_DEFAULT_SENDER"]
        msg["To"] = recipient
        msg.set_content(body)
        if not app.config["MAIL_SERVER"]:
            print(f"[email] To={recipient}\nSubject={subject}\nBody={body}")
            return False
        if app.config["MAIL_USE_SSL"]:
            server_ctx = smtplib.SMTP_SSL(app.config["MAIL_SERVER"], app.config["MAIL_PORT"])
        else:
            server_ctx = smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"])
        with server_ctx as server:
            if app.config["MAIL_USE_TLS"] and not app.config["MAIL_USE_SSL"]:
                server.starttls()
            if app.config["MAIL_USERNAME"]:
                server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return False


@app.route("/api/check-username")
def check_username():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"available": False, "message": "Username is required."})
    normalized_username = _normalize_username(username)
    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE lower(username) = ?", (normalized_username,)
    ).fetchone()
    available = existing is None
    return jsonify({"available": available, "message": "Username is available." if available else "Username is already taken."})


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        normalized_username = _normalize_username(username)
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        full_name = request.form.get("full_name", "").strip()
        user_type = request.form.get("user_type", "worker")

        if not username or not password:
            flash("Please enter both a username and password.")
            return redirect(url_for("register"))
        if not _password_meets_policy(password):
            flash("Password must be at least 8 characters, include an uppercase letter, a number, and a special character.")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("register"))

        db = get_db()
        try:
            existing = db.execute(
                "SELECT id FROM users WHERE lower(username) = ?", (normalized_username,)
            ).fetchone()
            if existing:
                flash("Registration failed. Username might be taken.")
                return redirect(url_for("register"))

            db.execute(
                """INSERT INTO users
                   (username, password_hash, full_name, created_at, email_verified)
                   VALUES (?, ?, ?, ?, 0)""",
                (
                    username,
                    generate_password_hash(password),
                    full_name,
                    _now_iso(),
                ),
            )
            db.commit()

            new_user = db.execute(
                "SELECT id FROM users WHERE lower(username) = ?", (normalized_username,)
            ).fetchone()
            if not new_user:
                db.rollback()
                flash("Registration failed. Please try again.")
                return redirect(url_for("register"))

            wallet_id = _generate_wallet_id(db)
            db.execute(
                "UPDATE users SET balance = 0.0, wallet_id = ? WHERE id = ?",
                (wallet_id, new_user["id"]),
            )
            db.execute(
                "INSERT INTO wallets (user_id, balance, escrow_balance, created_at) VALUES (?, 0.00, 0.00, ?)",
                (new_user["id"], _now_iso()),
            )
            db.commit()
            session["user_id"] = new_user["id"]
            flash(get_translator(session.get("lang", DEFAULT_LANG))["login"])

            ref_code = request.form.get("ref_code", "").strip()
            if ref_code:
                referrer = db.execute(
                    "SELECT id FROM users WHERE referral_code = ?", (ref_code,)
                ).fetchone()
                if referrer and referrer["id"] != new_user["id"]:
                    try:
                        db.execute(
                            """INSERT INTO referrals (referrer_id, referred_id, created_at)
                               VALUES (?, ?, ?)""",
                            (referrer["id"], new_user["id"], _now_iso()),
                        )
                        db.commit()
                    except Exception:
                        pass

            return redirect(url_for("feed"))
        except (sqlite3.IntegrityError, PG_INTEGRITY_ERROR) as exc:
            db.rollback()
            print(f"[auth] registration integrity error: {exc}", flush=True)
            flash("Registration failed. Username might be taken.")
            return redirect(url_for("register"))
        except Exception as exc:
            db.rollback()
            print(f"[auth] registration INSERT error: {type(exc).__name__}: {exc}", flush=True)
            flash("Registration failed. Please try again.")
            return redirect(url_for("register"))

    ref_code = request.args.get("ref", "")
    return render_template(
        "register.html",
        ref_code=ref_code,
        social_links=get_social_links(),
        social_auth_enabled=social_auth_enabled(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE lower(username) = ?", (_normalize_username(username),)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            if is_currently_banned(user):
                flash("account_banned")
                return redirect(url_for("login"))
            session["user_id"] = user["id"]
            return redirect(url_for("feed"))
        flash(get_translator(session.get("lang", DEFAULT_LANG))["login_failed"])
        return redirect(url_for("login"))

    show_register = request.args.get("mode", "") == "register"
    return render_template(
        "login.html",
        show_register=show_register,
        ref_code=request.args.get("ref", ""),
        social_links=get_social_links(),
        social_auth_enabled=social_auth_enabled(),
    )


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Feed / Posts
# ---------------------------------------------------------------------------
def _load_feed_page(db, user, page, page_size=FEED_PAGE_SIZE):
    """Fetch one LIMIT/OFFSET page of the feed and build the template payload.

    Shared by the server-rendered feed page, the JSON API, and the
    "load more" partial-HTML endpoint so all three stay in sync and only
    one query needs to be tuned/indexed.
    Returns (posts_data, has_next).
    """
    offset = (page - 1) * page_size

    posts = []
    try:
        if not db.is_sqlite:
            try:
                db.execute("SET LOCAL statement_timeout = 3000")
            except Exception:
                pass

        post_statuses = "('approved', 'posted')"
        has_status = _table_has_column(db, "posts", "status")
        has_likes = _table_exists(db, "likes")
        has_comments = _table_exists(db, "comments")

        has_user_avatar = _table_has_column(db, "users", "avatar")
        has_user_type = _table_has_column(db, "users", "user_type")
        has_user_verification_tier = _table_has_column(db, "users", "verification_tier")
        has_user_verified_until = _table_has_column(db, "users", "verified_until")

        user_field_selects = [
            "u.username",
            "u.full_name",
            "u.avatar" if has_user_avatar else "NULL AS avatar",
            "u.user_type" if has_user_type else "NULL AS user_type",
            "u.verification_tier" if has_user_verification_tier else "NULL AS verification_tier",
            "u.verified_until" if has_user_verified_until else "NULL AS verified_until",
        ]
        user_select_fields = ", ".join(user_field_selects)

        latest_posts_where = "WHERE COALESCE(NULLIF(status, ''), 'approved') IN " + post_statuses if has_status else ""
        latest_posts_query = f"""WITH latest_posts AS (
                   SELECT * FROM posts
                   {latest_posts_where}
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?
               )"""

        if has_likes or has_comments:
            like_count_select = "COALESCE(like_counts.like_count, 0) AS like_count" if has_likes else "0 AS like_count"
            comment_count_select = "COALESCE(comment_counts.comment_count, 0) AS comment_count" if has_comments else "0 AS comment_count"
            posts_query = f"""{latest_posts_query}
               SELECT p.*, {user_select_fields},
                      {like_count_select},
                      {comment_count_select}
               FROM latest_posts p
               JOIN users u ON p.user_id = u.id
               {('LEFT JOIN (\n                   SELECT post_id, COUNT(*) AS like_count\n                   FROM likes\n                   WHERE post_id IN (SELECT id FROM latest_posts)\n                   GROUP BY post_id\n               ) like_counts ON like_counts.post_id = p.id' if has_likes else '')}
               {('LEFT JOIN (\n                   SELECT post_id, COUNT(*) AS comment_count\n                   FROM comments\n                   WHERE post_id IN (SELECT id FROM latest_posts)\n                   GROUP BY post_id\n               ) comment_counts ON comment_counts.post_id = p.id' if has_comments else '')}
               ORDER BY p.created_at DESC"""
        else:
            posts_query = f"""{latest_posts_query}
               SELECT p.*, {user_select_fields},
                      0 AS like_count,
                      0 AS comment_count
               FROM latest_posts p
               JOIN users u ON p.user_id = u.id
               ORDER BY p.created_at DESC"""

        posts = db.execute(posts_query, (page_size, offset)).fetchall()
        # Temporary diagnostic: log a small sanitized sample of rows returned
        try:
            sample_rows = []
            for r in (posts or [])[:3]:
                try:
                    row = dict(r) if hasattr(r, 'keys') else dict(r)
                except Exception:
                    # fallback for simple tuples
                    try:
                        row = {i: r[i] for i in range(len(r))}
                    except Exception:
                        row = {}
                sample = {
                    'id': row.get('id'),
                    'user_id': row.get('user_id'),
                    'username': row.get('username') or None,
                    'full_name': row.get('full_name') or None,
                    'verification_tier': row.get('verification_tier') or None,
                    'status': row.get('status') or None,
                    'created_at': row.get('created_at') or None,
                    'content_preview': (row.get('content') or '')[:120].replace('\n', ' '),
                }
                sample_rows.append(sample)
            if sample_rows:
                app.logger.info("Feed sample rows: %s", sample_rows)
        except Exception:
            pass
    except Exception as exc:
        print(f"Warning: could not load feed posts: {exc}")
        posts = []

    post_ids = [p["id"] for p in posts]
    author_ids = list({p["user_id"] for p in posts})
    liked_ids = set()
    saved_ids = set()
    following_ids = set()
    applied_ids = set()

    if user and post_ids:
        try:
            placeholders = ", ".join("?" for _ in post_ids)
            if _table_exists(db, "likes"):
                liked_ids = {
                    r["post_id"]
                    for r in db.execute(
                        f"SELECT post_id FROM likes WHERE user_id = ? AND post_id IN ({placeholders})",
                        tuple([user["id"]] + post_ids),
                    ).fetchall()
                }
            else:
                liked_ids = set()
            if _table_exists(db, "saved_posts"):
                saved_ids = {
                    r["post_id"]
                    for r in db.execute(
                        f"SELECT post_id FROM saved_posts WHERE user_id = ? AND post_id IN ({placeholders})",
                        tuple([user["id"]] + post_ids),
                    ).fetchall()
                }
            else:
                saved_ids = set()
            if _table_exists(db, "job_applications"):
                applied_ids = {
                    r["post_id"]
                    for r in db.execute(
                        f"SELECT post_id FROM job_applications WHERE applicant_id = ? AND post_id IN ({placeholders})",
                        tuple([user["id"]] + post_ids),
                    ).fetchall()
                }
            else:
                applied_ids = set()
            if author_ids and _table_exists(db, "follows"):
                author_placeholders = ", ".join("?" for _ in author_ids)
                following_ids = {
                    r["followed_id"]
                    for r in db.execute(
                        f"SELECT followed_id FROM follows WHERE follower_id = ? AND followed_id IN ({author_placeholders})",
                        tuple([user["id"]] + author_ids),
                    ).fetchall()
                }
            else:
                following_ids = set()
        except Exception as exc:
            print(f"Warning: could not load user feed metadata: {exc}")

    def build_post_payload(rows):
        payload = []
        for p in rows:
            if not hasattr(p, "keys") and not isinstance(p, dict):
                continue
            row = dict(p) if hasattr(p, "keys") else dict(p)
            row.setdefault("id", None)
            row.setdefault("user_id", None)
            row.setdefault("content", "")
            row.setdefault("photo", None)
            row.setdefault("post_type", "general")
            row.setdefault("created_at", "")
            row.setdefault("view_count", 0)
            row.setdefault("full_name", row.get("username") or "Unknown")
            row.setdefault("username", "unknown")
            row.setdefault("avatar", None)
            row.setdefault("like_count", 0)
            row.setdefault("comment_count", 0)
            row.setdefault("verification_tier", "none")
            # Preserve the raw photo value from the row directly. Some rows may
            # come from SQLite/legacy schemas where the field name is not present
            # or is exposed differently, so we normalize it here before rendering.
            if "photo" not in row:
                row["photo"] = None
            if row.get("photo") in (None, ""):
                for alt_key in ("post_photo", "image", "media_url"):
                    if alt_key in row and row.get(alt_key):
                        row["photo"] = row.get(alt_key)
                        break
            row["is_verified"] = row.get("verification_tier") in ("blue", "gold")
            row["is_vip"] = row.get("verification_tier") == "gold"
            payload.append({
                "post": row,
                "author_name": row.get("full_name") or row.get("username") or "Unknown",
                "like_count": row.get("like_count", 0),
                "comment_count": row.get("comment_count", 0),
                "liked": row.get("id") in liked_ids,
                "saved": row.get("id") in saved_ids,
                "following": row.get("user_id") in following_ids,
                "applied": row.get("id") in applied_ids,
            })
        return payload

    posts_data = build_post_payload(posts) or []
    has_next = len(posts) == page_size
    return posts_data, has_next


@app.route("/")
@login_required
def feed():
    db = get_db()
    user = get_current_user()

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1

    try:
        posts_data, has_next = _load_feed_page(db, user, page, FEED_PAGE_SIZE)
    except Exception as exc:
        print(f"Warning: feed page load failed: {exc}")
        flash("There was a problem loading your feed. Please try again in a moment.")
        posts_data, has_next = [], False

    has_posts = len(posts_data) > 0

    db_warning_message = None
    if not has_posts:
        try:
            # try to get a quick posts count to help diagnose empty-feed issues
            posts_count = 0
            try:
                posts_count = db.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"]
            except Exception:
                # fallback for DBs where posts table may be missing
                try:
                    posts_count = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                except Exception:
                    posts_count = 0

            app.logger.info(f"Feed loaded with 0 posts for user={getattr(user,'id',None)}; resolved DATABASE={DATABASE}; is_sqlite={db.is_sqlite}; posts_count={posts_count}")
            if posts_count == 0:
                db_warning_message = f"No posts found in database ({os.path.basename(DATABASE)}). If you expect posts, verify the app's DATABASE setting and that the DB contains posts."
        except Exception:
            # swallow any diagnostics errors
            pass

    return render_template(
        "feed.html",
        posts_data=posts_data,
        has_posts=has_posts,
        page=page,
        page_size=FEED_PAGE_SIZE,
        has_next=has_next,
        days_left=trial_days_left(user) if user else 0,
        show_trial_banner=bool(user and not _get_row_value(user, "paid_until")),
        db_warning_message=db_warning_message,
    )


@app.route("/feed/page/<int:page>")
@login_required
def feed_load_more(page):
    """Returns a rendered HTML fragment of the next batch of posts, plus
    pagination metadata, for the feed's "Load More" / infinite-scroll JS.
    Reuses the exact same partial template as the initial page load so the
    markup (translations, badges, follow state, CSRF-protected forms, etc.)
    never drifts from the server-rendered version.
    """
    if page < 1:
        page = 1
    db = get_db()
    user = get_current_user()
    posts_data, has_next = _load_feed_page(db, user, page, FEED_PAGE_SIZE)
    html = render_template("_feed_posts.html", posts_data=posts_data)
    return jsonify({
        "success": True,
        "html": html,
        "has_next": has_next,
        "has_posts": len(posts_data) > 0,
        "page": page,
    })


@app.route('/__debug/db')
def debug_db():
    """Restricted debug endpoint returning resolved DB path and quick counts.
    Only available when running in debug mode or from localhost to avoid public data leaks.
    """
    allowed_local = request.remote_addr in ("127.0.0.1", "::1")
    if not (app.debug or app.config.get('TESTING') or allowed_local):
        abort(404)

    info = {"resolved_database": DATABASE}
    try:
        db = get_db()
        info['is_sqlite'] = bool(db.is_sqlite)
        # try counts via the configured DB connection
        try:
            r = db.execute("SELECT COUNT(*) as c FROM posts").fetchone()
            info['posts'] = r['c'] if isinstance(r, dict) or hasattr(r, 'keys') else r[0]
        except Exception:
            info['posts'] = None
        try:
            r = db.execute("SELECT COUNT(*) as c FROM users").fetchone()
            info['users'] = r['c'] if isinstance(r, dict) or hasattr(r, 'keys') else r[0]
        except Exception:
            info['users'] = None
        try:
            # table info: DB-neutral attempt; for sqlite -> PRAGMA, for PG -> information_schema
            if db.is_sqlite:
                r = db.execute("PRAGMA table_info(users)").fetchall()
                info['user_columns'] = [row[1] for row in r]
            else:
                r = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'").fetchall()
                info['user_columns'] = [row[0] for row in r]
        except Exception:
            info['user_columns'] = None
    except Exception as exc:
        info['error'] = str(exc)

    return jsonify(info)


@app.route("/home.html")
@login_required
def home_html():
    return feed()


@app.route("/api/feed")
@login_required
def api_feed():
    db = get_db()
    user = get_current_user()

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1

    try:
        posts_data, has_next = _load_feed_page(db, user, page, FEED_PAGE_SIZE)
    except Exception as exc:
        print(f"Warning: could not load feed posts for API: {exc}")
        return jsonify({"success": False, "error": "feed_load_failed"}), 500

    return jsonify({
        "success": True,
        "posts": posts_data,
        "page": page,
        "has_next": has_next,
    })


@app.route("/home")
@login_required
def home():
    return redirect(url_for("feed"))


@app.route("/post/new", methods=["POST"])
@login_required
@daily_limit_required("standard")
def new_post():
    content = request.form.get("content", "").strip()
    post_type = request.form.get("post_type", "general")
    photo_file = request.files.get("photo")
    if photo_file and photo_file.filename and not allowed_file(photo_file.filename):
        flash("Unsupported image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.")
        return redirect(url_for("feed"))

    photo = save_photo(photo_file)
    if not content and not photo:
        return redirect(url_for("feed"))

    db = get_db()
    user = get_current_user()
    blocked_word = contains_restricted_word(content, db)
    if blocked_word:
        user_id = _get_row_value(user, "id", session.get("user_id"))
        username = _get_row_value(user, "username", "unknown")
        db.execute(
            "INSERT INTO reports (reporter_id, target_type, target_id, reason, status, created_at) VALUES (?, 'post', 0, ?, 'pending', ?)",
            (user_id, f"Blocked: contains restricted word '{blocked_word}'", datetime.datetime.utcnow().isoformat()),
        )
        add_notification(db, user_id, f"Your post was blocked because it contains the restricted word '{blocked_word}'.", ntype="warning")
        for admin in db.execute("SELECT id FROM users WHERE is_admin = true").fetchall():
            add_notification(db, admin["id"], f"New post by {username} was blocked for policy review.", ntype="warning")
        db.commit()
        flash("Your post was blocked for policy review.")
        return redirect(url_for("feed"))

    try:
        status = "approved"
        post_columns = _get_table_columns(db, "posts")
        insert_sql = "INSERT INTO posts (user_id, content"
        insert_values = [session["user_id"], content]
        if "photo" in post_columns:
            insert_sql += ", photo"
            insert_values.append(photo)
        if "post_type" in post_columns:
            insert_sql += ", post_type"
            insert_values.append(post_type)
        if "status" in post_columns:
            insert_sql += ", status"
            insert_values.append(status)
        insert_sql += ", created_at) VALUES ("
        insert_sql += ", ".join(["?"] * len(insert_values))
        insert_sql += ", ?)"
        insert_values.append(datetime.datetime.utcnow().isoformat())
        # Temporary diagnostic logging for Render: record DB type and the insert payload (sanitized)
        try:
            short_vals = [str(v)[:200] for v in insert_values]
            app.logger.info("New post insert: DB=%s is_sqlite=%s SQL=%s VALUES=%s", DATABASE, db.is_sqlite, insert_sql, short_vals)
        except Exception:
            pass
        db.execute(insert_sql, tuple(insert_values))
        db.commit()  # commit the post insert on its own before touching anything else
        # Award points for creating a post. This is best-effort and must never be
        # allowed to poison/rollback the post insert above if it fails (e.g. a
        # missing/renamed column) — Postgres aborts the whole transaction on any
        # error, and a later commit() on an aborted transaction silently rolls
        # back instead of raising, which would delete the post with no error.
        try:
            db.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id = ?", (10, session["user_id"]))
            db.commit()
        except Exception as points_exc:
            print(f"Warning: could not award post points: {points_exc}")
            try:
                db.rollback()
            except Exception:
                pass
        try:
            app.logger.info("New post committed: user_id=%s", session.get("user_id"))
        except Exception:
            pass
        refresh_trust_status(db, user["id"])
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"New post submission failed: {exc}")
        flash("Could not publish your post right now. Please try again.")
    return redirect(url_for("feed"))


@app.route("/post/<int:post_id>")
@login_required
def post_detail(post_id):
    db = get_db()
    record_unique_view(db, post_id, session["user_id"])
    post = db.execute(
        """SELECT posts.*, users.username, users.full_name, users.avatar,
                  users.verification_tier, users.verified_until
           FROM posts JOIN users ON posts.user_id = users.id
           WHERE posts.id = ?""", (post_id,)
    ).fetchone()
    if not post:
        abort(404)
    comments = db.execute(
        """SELECT comments.*, users.username, users.full_name
           FROM comments JOIN users ON comments.user_id = users.id
           WHERE post_id = ? ORDER BY comments.created_at ASC""",
        (post_id,),
    ).fetchall()
    like_count = db.execute(
        "SELECT COUNT(*) c FROM likes WHERE post_id = ?", (post_id,)
    ).fetchone()["c"]
    liked = db.execute(
        "SELECT 1 FROM likes WHERE post_id = ? AND user_id = ?",
        (post_id, session["user_id"]),
    ).fetchone() is not None
    is_following = db.execute(
        "SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?",
        (session["user_id"], post["user_id"]),
    ).fetchone() is not None
    applied = db.execute(
        "SELECT 1 FROM job_applications WHERE post_id = ? AND applicant_id = ?",
        (post_id, session["user_id"]),
    ).fetchone() is not None

    return render_template(
        "post_detail.html", post=post, comments=comments,
        like_count=like_count, liked=liked, is_following=is_following, applied=applied,
    )


@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    db = get_db()
    existing = db.execute(
        "SELECT id FROM likes WHERE post_id = ? AND user_id = ?",
        (post_id, session["user_id"]),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM likes WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)",
            (post_id, session["user_id"]),
        )
    db.commit()
    return redirect(request.referrer or url_for("feed"))


@app.route("/api/like/<int:post_id>", methods=["POST"])
@login_required
def api_toggle_like(post_id):
    """JSON version of like_post for the JS-powered instant Like button."""
    db = get_db()
    post = db.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        return {"error": "not found"}, 404
    existing = db.execute(
        "SELECT id FROM likes WHERE post_id = ? AND user_id = ?",
        (post_id, session["user_id"]),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM likes WHERE id = ?", (existing["id"],))
        db.commit()
        liked = False
    else:
        db.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)",
            (post_id, session["user_id"]),
        )
        db.commit()
        liked = True
    like_count = db.execute(
        "SELECT COUNT(*) c FROM likes WHERE post_id = ?", (post_id,)
    ).fetchone()["c"]
    return {"liked": liked, "like_count": like_count}


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def comment_post(post_id):
    content = request.form.get("content", "").strip()
    if content:
        db = get_db()
        db.execute(
            """INSERT INTO comments (post_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (post_id, session["user_id"], content,
             datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/share", methods=["POST"])
@login_required
def share_post(post_id):
    db = get_db()
    db.execute(
        "UPDATE posts SET share_count = share_count + 1 WHERE id = ?", (post_id,)
    )
    db.commit()
    award_task_reward(db, session["user_id"], "share_job", post_id=post_id)
    return redirect(request.referrer or url_for("feed"))


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    user = get_current_user()
    if post and (post["user_id"] == _get_row_value(user, "id") or _get_row_value(user, "is_admin", False)):
        db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        db.commit()
    return redirect(url_for("feed"))


@app.route("/post/<int:post_id>/view", methods=["POST"])
@login_required
def log_post_view(post_id):
    db = get_db()
    record_unique_view(db, post_id, session["user_id"])
    return {"ok": True}


@app.route("/post/<int:post_id>/apply", methods=["POST"])
@login_required
def apply_to_job(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post or post["post_type"] != "job":
        abort(404)
    if post["user_id"] == session["user_id"]:
        return redirect(request.referrer or url_for("feed"))

    message = request.form.get("message", "").strip()
    existing = db.execute(
        "SELECT id FROM job_applications WHERE post_id = ? AND applicant_id = ?",
        (post_id, session["user_id"]),
    ).fetchone()
    if existing:
        flash("already_applied")
    else:
        db.execute(
            """INSERT INTO job_applications (post_id, applicant_id, message, created_at)
               VALUES (?, ?, ?, ?)""",
            (post_id, session["user_id"], message, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("application_submitted")
    return redirect(request.referrer or url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/applicants")
@login_required
def view_applicants(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        abort(404)
    if post["user_id"] != session["user_id"] and not get_current_user()["is_admin"]:
        abort(403)
    applicants = db.execute(
        """SELECT job_applications.*, users.username, users.full_name, users.avatar,
                  users.verification_tier, users.verified_until
           FROM job_applications JOIN users ON job_applications.applicant_id = users.id
           WHERE post_id = ? ORDER BY job_applications.created_at DESC""",
        (post_id,),
    ).fetchall()
    return render_template("job_applicants.html", post=post, applicants=applicants)


# ---------------------------------------------------------------------------
# Chat / Messages - with Message Request gatekeeping
# ---------------------------------------------------------------------------
def _get_or_create_conversation(db, user_a, user_b):
    lo, hi = min(user_a, user_b), max(user_a, user_b)
    convo = db.execute(
        "SELECT * FROM conversations WHERE user1_id = ? AND user2_id = ?", (lo, hi)
    ).fetchone()
    if convo:
        return convo
    db.execute(
        """INSERT INTO conversations (user1_id, user2_id, initiated_by, created_at)
           VALUES (?, ?, ?, ?)""",
        (lo, hi, user_a, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return db.execute(
        "SELECT * FROM conversations WHERE user1_id = ? AND user2_id = ?", (lo, hi)
    ).fetchone()


def _other_user_id(convo, my_id):
    return convo["user2_id"] if convo["user1_id"] == my_id else convo["user1_id"]


@app.route("/chat")
@login_required
def chat_inbox():
    db = get_db()
    uid = session["user_id"]
    rows = db.execute(
        """SELECT conversations.*, users.username, users.full_name, users.avatar
           FROM conversations
           JOIN users ON users.id = CASE WHEN conversations.user1_id = ?
                                          THEN conversations.user2_id ELSE conversations.user1_id END
           WHERE (conversations.user1_id = ? OR conversations.user2_id = ?)
           ORDER BY conversations.created_at DESC""",
        (uid, uid, uid),
    ).fetchall()

    active, requests_in = [], []
    for c in rows:
        last_msg = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
            (c["id"],),
        ).fetchone()
        unread = db.execute(
            """SELECT COUNT(*) c FROM messages WHERE conversation_id = ?
               AND sender_id != ? AND seen_at IS NULL""",
            (c["id"], uid),
        ).fetchone()["c"]
        entry = {"convo": c, "last_msg": last_msg, "unread": unread}
        if c["status"] == "accepted":
            active.append(entry)
        elif c["status"] == "pending" and c["initiated_by"] != uid:
            requests_in.append(entry)
    return render_template("chat_inbox.html", active=active, requests_in=requests_in)


@app.route("/chat/start/<int:user_id>")
@login_required
def chat_start(user_id):
    if user_id == session["user_id"]:
        return redirect(url_for("chat_inbox"))
    db = get_db()
    convo = _get_or_create_conversation(db, session["user_id"], user_id)
    if convo["status"] == "blocked":
        flash("cannot_message_blocked")
        return redirect(url_for("chat_inbox"))
    return redirect(url_for("chat_thread", conversation_id=convo["id"]))


@app.route("/chat/<int:conversation_id>")
@login_required
def chat_thread(conversation_id):
    db = get_db()
    uid = session["user_id"]
    convo = db.execute(
        "SELECT * FROM conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
        (conversation_id, uid, uid),
    ).fetchone()
    if not convo:
        abort(404)

    other_id = _other_user_id(convo, uid)
    other = db.execute("SELECT * FROM users WHERE id = ?", (other_id,)).fetchone()

    # Only mark messages as seen once the conversation has been accepted -
    # previewing a pending request must NOT flip the sender's "seen" status.
    if convo["status"] == "accepted":
        db.execute(
            "UPDATE messages SET seen_at = ? WHERE conversation_id = ? "
            "AND sender_id != ? AND seen_at IS NULL",
            (datetime.datetime.utcnow().isoformat(), conversation_id, uid),
        )
        db.commit()

    messages = db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()

    is_pending_recipient = convo["status"] == "pending" and convo["initiated_by"] != uid
    can_reply = convo["status"] == "accepted" or convo["initiated_by"] == uid

    return render_template(
        "chat_thread.html", convo=convo, other=other, messages=messages,
        is_pending_recipient=is_pending_recipient, can_reply=can_reply,
    )


@app.route("/chat/<int:conversation_id>/send", methods=["POST"])
@login_required
def chat_send(conversation_id):
    db = get_db()
    uid = session["user_id"]
    convo = db.execute(
        "SELECT * FROM conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
        (conversation_id, uid, uid),
    ).fetchone()
    if not convo or convo["status"] == "blocked":
        abort(404)
    if convo["status"] == "pending" and convo["initiated_by"] != uid:
        # recipient must Accept before they can reply
        abort(403)

    content = request.form.get("content", "").strip()
    if content:
        db.execute(
            """INSERT INTO messages (conversation_id, sender_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, uid, content, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    return redirect(url_for("chat_thread", conversation_id=conversation_id))


@app.route("/chat/<int:conversation_id>/accept", methods=["POST"])
@login_required
def chat_accept(conversation_id):
    db = get_db()
    uid = session["user_id"]
    convo = db.execute(
        "SELECT * FROM conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?) "
        "AND initiated_by != ?",
        (conversation_id, uid, uid, uid),
    ).fetchone()
    if convo:
        db.execute("UPDATE conversations SET status = 'accepted' WHERE id = ?", (conversation_id,))
        db.execute(
            "UPDATE messages SET seen_at = ? WHERE conversation_id = ? AND seen_at IS NULL",
            (datetime.datetime.utcnow().isoformat(), conversation_id),
        )
        db.commit()
    return redirect(url_for("chat_thread", conversation_id=conversation_id))


@app.route("/chat/<int:conversation_id>/decline", methods=["POST"])
@login_required
def chat_decline(conversation_id):
    db = get_db()
    uid = session["user_id"]
    convo = db.execute(
        "SELECT * FROM conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?) "
        "AND initiated_by != ?",
        (conversation_id, uid, uid, uid),
    ).fetchone()
    if convo:
        db.execute("UPDATE conversations SET status = 'blocked' WHERE id = ?", (conversation_id,))
        db.commit()
    return redirect(url_for("chat_inbox"))


@app.route("/post/<int:post_id>/save", methods=["POST"])
@login_required
def save_post(post_id):
    db = get_db()
    existing = db.execute(
        "SELECT id FROM saved_posts WHERE post_id = ? AND user_id = ?",
        (post_id, session["user_id"]),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM saved_posts WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            "INSERT INTO saved_posts (user_id, post_id, created_at) VALUES (?, ?, ?)",
            (session["user_id"], post_id, datetime.datetime.utcnow().isoformat()),
        )
    db.commit()
    return redirect(request.referrer or url_for("feed"))


@app.route("/saved")
@login_required
def saved_jobs():
    db = get_db()
    posts = db.execute(
        """SELECT posts.*, users.username, users.full_name, users.avatar,
                  users.verification_tier, users.verified_until
           FROM saved_posts
           JOIN posts ON saved_posts.post_id = posts.id
           JOIN users ON posts.user_id = users.id
           WHERE saved_posts.user_id = ?
           ORDER BY saved_posts.created_at DESC""",
        (session["user_id"],),
    ).fetchall()

    posts_data = []
    for p in posts:
        like_count = db.execute(
            "SELECT COUNT(*) c FROM likes WHERE post_id = ?", (p["id"],)
        ).fetchone()["c"]
        comment_count = db.execute(
            "SELECT COUNT(*) c FROM comments WHERE post_id = ?", (p["id"],)
        ).fetchone()["c"]
        liked = db.execute(
            "SELECT 1 FROM likes WHERE post_id = ? AND user_id = ?",
            (p["id"], session["user_id"]),
        ).fetchone() is not None
        posts_data.append({
            "post": p, "like_count": like_count,
            "comment_count": comment_count, "liked": liked,
        })

    return render_template("saved_jobs.html", posts_data=posts_data)


@app.route("/coming-soon/<feature>")
@login_required
def coming_soon(feature):
    return render_template("coming_soon.html", feature=feature)


# ---------------------------------------------------------------------------
# Profile / Ratings
# ---------------------------------------------------------------------------
@app.route("/profile/<int:user_id>")
@login_required
def profile(user_id):
    db = get_db()
    profile_user = db.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not profile_user:
        abort(404)

    if hasattr(profile_user, "keys"):
        profile_user = dict(profile_user)
    else:
        profile_user = dict(profile_user)
    profile_user.setdefault("avatar", None)
    profile_user.setdefault("verification_tier", profile_user.get("verification_tier") or "none")
    profile_user.setdefault("verified_until", None)
    profile_user.setdefault("bio", "")
    profile_user.setdefault("phone", "")
    profile_user.setdefault("skills", "")
    profile_user.setdefault("experience", "")
    profile_user.setdefault("points", 0)
    profile_user.setdefault("user_type", "worker")
    profile_user.setdefault("full_name", profile_user.get("username") or "User")

    has_likes = _table_exists(db, "likes")
    has_comments = _table_exists(db, "comments")
    has_user_avatar = _table_has_column(db, "users", "avatar")
    has_user_type = _table_has_column(db, "users", "user_type")
    has_user_verification_tier = _table_has_column(db, "users", "verification_tier")
    has_user_verified_until = _table_has_column(db, "users", "verified_until")

    user_field_selects = [
        "users.username",
        "users.full_name",
        "users.avatar" if has_user_avatar else "NULL AS avatar",
        "users.user_type" if has_user_type else "NULL AS user_type",
        "users.verification_tier" if has_user_verification_tier else "NULL AS verification_tier",
        "users.verified_until" if has_user_verified_until else "NULL AS verified_until",
    ]
    user_select_fields = ", ".join(user_field_selects)

    if has_likes or has_comments:
        posts = db.execute(
            (
                "SELECT posts.*, " + user_select_fields + ", "
                + ("(SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count, " if has_likes else "0 AS like_count, ")
                + ("(SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count" if has_comments else "0 AS comment_count")
                + " FROM posts JOIN users ON posts.user_id = users.id"
                + " WHERE posts.user_id = ?"
                + " ORDER BY posts.created_at DESC"
            ),
            (user_id,),
        ).fetchall()
    else:
        posts = db.execute(
            (
                "SELECT posts.*, " + user_select_fields + ", "
                + "0 AS like_count, "
                + "0 AS comment_count"
                + " FROM posts JOIN users ON posts.user_id = users.id"
                + " WHERE posts.user_id = ?"
                + " ORDER BY posts.created_at DESC"
            ),
            (user_id,),
        ).fetchall()

    ratings = db.execute(
        """SELECT ratings.*, users.username as employer_username
           FROM ratings JOIN users ON ratings.employer_id = users.id
           WHERE worker_id = ? ORDER BY ratings.created_at DESC""",
        (user_id,),
    ).fetchall()
    avg_row = db.execute(
        "SELECT AVG(stars) avg_stars, COUNT(*) cnt FROM ratings WHERE worker_id = ?",
        (user_id,),
    ).fetchone()

    followers_count = db.execute(
        "SELECT COUNT(*) c FROM follows WHERE followed_id = ?", (user_id,)
    ).fetchone()["c"]
    following_count = db.execute(
        "SELECT COUNT(*) c FROM follows WHERE follower_id = ?", (user_id,)
    ).fetchone()["c"]
    posts_count = db.execute(
        "SELECT COUNT(*) c FROM posts WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    is_following = False
    if current_uid := session.get("user_id"):
        is_following = db.execute(
            "SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?",
            (current_uid, user_id),
        ).fetchone() is not None

    portfolio_items = db.execute(
        "SELECT * FROM portfolio_items WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()

    return render_template(
        "profile.html", profile_user=profile_user, posts=posts,
        ratings=ratings, avg_stars=avg_row["avg_stars"], rating_count=avg_row["cnt"],
        portfolio_items=portfolio_items,
        followers_count=followers_count, following_count=following_count,
        posts_count=posts_count, is_following=is_following,
    )


def _build_follow_list_entries(db, rows, current_uid):
    """Shared helper for the followers/following lists. For each user row,
    works out both directions of the follow relationship so the template can
    decide between Follow / Unfollow / "Follow Back":
      - viewer_follows: True if the logged-in viewer already follows this user
      - follows_viewer: True if this user already follows the logged-in viewer
    "Follow Back" is shown when follows_viewer is True but viewer_follows is
    False - i.e. they follow you, but you haven't followed them yet.
    """
    entries = []
    user_ids = [r["id"] for r in rows]
    viewer_following_ids = set()
    followers_of_viewer_ids = set()
    if current_uid and user_ids:
        placeholders = ", ".join("?" for _ in user_ids)
        viewer_following_ids = {
            r["followed_id"] for r in db.execute(
                f"SELECT followed_id FROM follows WHERE follower_id = ? AND followed_id IN ({placeholders})",
                tuple([current_uid] + user_ids),
            ).fetchall()
        }
        followers_of_viewer_ids = {
            r["follower_id"] for r in db.execute(
                f"SELECT follower_id FROM follows WHERE followed_id = ? AND follower_id IN ({placeholders})",
                tuple([current_uid] + user_ids),
            ).fetchall()
        }
    for r in rows:
        entries.append({
            "user": r,
            "viewer_follows": r["id"] in viewer_following_ids,
            "follows_viewer": r["id"] in followers_of_viewer_ids,
        })
    return entries


@app.route("/profile/<int:user_id>/followers")
@login_required
def profile_followers(user_id):
    db = get_db()
    profile_user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not profile_user:
        abort(404)
    rows = db.execute(
        """SELECT users.* FROM follows
           JOIN users ON users.id = follows.follower_id
           WHERE follows.followed_id = ?
           ORDER BY follows.created_at DESC""",
        (user_id,),
    ).fetchall()
    entries = _build_follow_list_entries(db, rows, session.get("user_id"))
    return render_template(
        "follow_list.html", profile_user=profile_user, entries=entries,
        list_kind="followers",
    )


@app.route("/profile/<int:user_id>/following")
@login_required
def profile_following(user_id):
    db = get_db()
    profile_user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not profile_user:
        abort(404)
    rows = db.execute(
        """SELECT users.* FROM follows
           JOIN users ON users.id = follows.followed_id
           WHERE follows.follower_id = ?
           ORDER BY follows.created_at DESC""",
        (user_id,),
    ).fetchall()
    entries = _build_follow_list_entries(db, rows, session.get("user_id"))
    return render_template(
        "follow_list.html", profile_user=profile_user, entries=entries,
        list_kind="following",
    )


@app.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html")


@app.route("/create")
@login_required
def create_menu():
    return render_template("create_menu.html")


@app.route("/settings/privacy")
@login_required
def privacy_policy():
    return render_template("privacy.html")


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    db = get_db()
    user = get_current_user()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        skills = request.form.get("skills", "").strip()
        experience = request.form.get("experience", "").strip()
        bio = request.form.get("bio", "").strip()
        avatar = save_photo(request.files.get("avatar"))

        if username and username != user["username"]:
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                flash(get_translator(session.get("lang", DEFAULT_LANG))["username_taken"])
                return redirect(url_for("edit_profile"))
        else:
            username = user["username"]

        if avatar:
            db.execute(
                """UPDATE users SET username=?, full_name=?, phone=?, skills=?, experience=?,
                   bio=?, avatar=? WHERE id=?""",
                (username, full_name, phone, skills, experience, bio, avatar, user["id"]),
            )
        else:
            db.execute(
                """UPDATE users SET username=?, full_name=?, phone=?, skills=?, experience=?,
                   bio=? WHERE id=?""",
                (username, full_name, phone, skills, experience, bio, user["id"]),
            )
        db.commit()
        return redirect(url_for("profile", user_id=user["id"]))

    return render_template("edit_profile.html", user=user)


@app.route("/profile/update-skills", methods=["POST"])
@login_required
def update_profile_skills():
    skills = request.form.get("skills", "").strip()
    db = get_db()
    db.execute("UPDATE users SET skills = ? WHERE id = ?", (skills, session["user_id"]))
    db.commit()
    return redirect(url_for("profile", user_id=session["user_id"]))


@app.route("/profile/<int:user_id>/portfolio/add", methods=["POST"])
@login_required
def add_portfolio_item(user_id):
    if session.get("user_id") != user_id:
        abort(403)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    project_url = request.form.get("project_url", "").strip()
    image_file = request.files.get("image")
    image_path = save_photo(image_file) if image_file and image_file.filename else None

    if image_file and image_file.filename and image_path is None:
        flash("Unsupported portfolio image format. Please upload a valid image.")
        return redirect(url_for("profile", user_id=user_id))

    if not title:
        flash("Please add a project title to save your portfolio item.")
        return redirect(url_for("profile", user_id=user_id))

    db = get_db()
    db.execute(
        "INSERT INTO portfolio_items (user_id, title, description, project_url, image_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, title, description, project_url or None, image_path, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return redirect(url_for("profile", user_id=user_id))


@app.route("/profile/<int:worker_id>/rate", methods=["POST"])
@login_required
def rate_worker(worker_id):
    stars = int(request.form.get("stars", 5))
    comment = request.form.get("comment", "").strip()
    stars = max(1, min(5, stars))

    db = get_db()
    db.execute(
        """INSERT INTO ratings (worker_id, employer_id, stars, comment, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (worker_id, session["user_id"], stars, comment,
         datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return redirect(url_for("profile", user_id=worker_id))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@app.route("/report", methods=["POST"])
@login_required
def submit_report():
    target_type = request.form.get("target_type")
    target_id = int(request.form.get("target_id"))
    reason = request.form.get("reason", "").strip()

    if reason:
        db = get_db()
        db.execute(
            """INSERT INTO reports (reporter_id, target_type, target_id, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], target_type, target_id, reason,
             datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    return redirect(request.referrer or url_for("feed"))


# ---------------------------------------------------------------------------
# Subscription / Payment
# ---------------------------------------------------------------------------
@app.route("/subscribe")
@login_required
def subscribe():
    user = get_current_user()
    return render_template(
        "subscribe.html",
        active=subscription_active(user),
        days_left=trial_days_left(user),
        monthly_price=MONTHLY_PRICE,
        yearly_price=YEARLY_PRICE,
    )


@app.route("/subscribe/pay", methods=["POST"])
@login_required
def submit_payment():
    plan = request.form.get("plan")
    ref = request.form.get("transaction_ref", "").strip()
    amount = MONTHLY_PRICE if plan == "monthly" else YEARLY_PRICE

    if ref:
        db = get_db()
        db.execute(
            """INSERT INTO payments (user_id, plan, amount, transaction_ref, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], plan, amount, ref,
             datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("payment_pending")
    return redirect(url_for("subscribe"))


# ---------------------------------------------------------------------------
# Groups & Channels
# ---------------------------------------------------------------------------
QUICK_REACTIONS = ["👍", "❤️", "😂"]


@app.route("/channels")
@login_required
def channels_directory():
    db = get_db()
    uid = session["user_id"]
    channels = db.execute(
        """SELECT channels.*, users.username as creator_username,
                  (SELECT COUNT(*) FROM channel_members WHERE channel_id = channels.id) as member_count
           FROM channels JOIN users ON channels.creator_id = users.id
           ORDER BY channels.created_at DESC LIMIT 50"""
    ).fetchall()
    my_channel_ids = {r["channel_id"] for r in db.execute(
        "SELECT channel_id FROM channel_members WHERE user_id = ?", (uid,)
    ).fetchall()}
    return render_template("channels_directory.html", channels=channels, my_channel_ids=my_channel_ids)


@app.route("/channels/new", methods=["GET", "POST"])
@login_required
def new_channel():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        channel_type = request.form.get("channel_type", "group")
        if channel_type not in ("group", "channel"):
            channel_type = "group"
        if not name:
            flash("channel_name_required")
            return redirect(url_for("new_channel"))

        avatar = save_photo(request.files.get("avatar"))
        db = get_db()
        now = datetime.datetime.utcnow().isoformat()
        db.execute(
            """INSERT INTO channels (name, description, channel_type, creator_id, avatar, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, description, channel_type, session["user_id"], avatar, now),
        )
        db.commit()
        new_id = db.execute("SELECT id FROM channels WHERE creator_id = ? ORDER BY id DESC LIMIT 1",
                             (session["user_id"],)).fetchone()["id"]
        db.execute(
            "INSERT INTO channel_members (channel_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
            (new_id, session["user_id"], now),
        )
        db.commit()
        return redirect(url_for("channel_view", channel_id=new_id))

    return render_template("channel_new.html")


@app.route("/channels/<int:channel_id>")
@login_required
def channel_view(channel_id):
    db = get_db()
    uid = session["user_id"]
    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        abort(404)

    is_member = db.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?", (channel_id, uid)
    ).fetchone() is not None
    is_owner = channel["creator_id"] == uid
    member_count = db.execute(
        "SELECT COUNT(*) c FROM channel_members WHERE channel_id = ?", (channel_id,)
    ).fetchone()["c"]

    messages = db.execute(
        """SELECT channel_messages.*, users.username, users.full_name, users.avatar
           FROM channel_messages JOIN users ON channel_messages.sender_id = users.id
           WHERE channel_id = ? ORDER BY channel_messages.created_at ASC LIMIT 200""",
        (channel_id,),
    ).fetchall()

    reactions_by_msg = {}
    for m in messages:
        rows = db.execute(
            """SELECT emoji, COUNT(*) c FROM channel_message_reactions
               WHERE message_id = ? GROUP BY emoji""", (m["id"],)
        ).fetchall()
        reactions_by_msg[m["id"]] = {r["emoji"]: r["c"] for r in rows}

    return render_template(
        "channel_view.html", channel=channel, is_member=is_member, is_owner=is_owner,
        member_count=member_count, messages=messages, reactions_by_msg=reactions_by_msg,
        quick_reactions=QUICK_REACTIONS,
        channel_verification_price=CHANNEL_VERIFICATION_MONTHLY_PRICE,
    )


@app.route("/channels/<int:channel_id>/join", methods=["POST"])
@login_required
def join_channel_route(channel_id):
    db = get_db()
    existing = db.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, session["user_id"]),
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO channel_members (channel_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
            (channel_id, session["user_id"], datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    return redirect(url_for("channel_view", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/leave", methods=["POST"])
@login_required
def leave_channel_route(channel_id):
    db = get_db()
    channel = db.execute("SELECT creator_id FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if channel and channel["creator_id"] != session["user_id"]:
        db.execute(
            "DELETE FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, session["user_id"]),
        )
        db.commit()
    return redirect(url_for("channels_directory"))


@app.route("/channels/<int:channel_id>/send", methods=["POST"])
@login_required
def channel_send(channel_id):
    db = get_db()
    uid = session["user_id"]
    is_member = db.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?", (channel_id, uid)
    ).fetchone() is not None
    if not is_member:
        abort(403)

    content = request.form.get("content", "").strip()
    photo = save_photo(request.files.get("photo"))
    if content or photo:
        db.execute(
            """INSERT INTO channel_messages (channel_id, sender_id, content, photo, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (channel_id, uid, content, photo, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    return redirect(url_for("channel_view", channel_id=channel_id))


@app.route("/channel_message/<int:message_id>/react", methods=["POST"])
@login_required
def channel_message_react(message_id):
    emoji = request.form.get("emoji", "")
    if emoji not in QUICK_REACTIONS:
        abort(400)
    db = get_db()
    msg = db.execute("SELECT channel_id FROM channel_messages WHERE id = ?", (message_id,)).fetchone()
    if not msg:
        abort(404)
    is_member = db.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
        (msg["channel_id"], session["user_id"]),
    ).fetchone() is not None
    if not is_member:
        abort(403)

    existing = db.execute(
        "SELECT id FROM channel_message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
        (message_id, session["user_id"], emoji),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM channel_message_reactions WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            """INSERT INTO channel_message_reactions (message_id, user_id, emoji, created_at)
               VALUES (?, ?, ?, ?)""",
            (message_id, session["user_id"], emoji, datetime.datetime.utcnow().isoformat()),
        )
    db.commit()
    return redirect(url_for("channel_view", channel_id=msg["channel_id"]))


@app.route("/channels/<int:channel_id>/buy-verification", methods=["POST"])
@login_required
def buy_channel_verification(channel_id):
    db = get_db()
    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    user = get_current_user()
    if not channel or channel["creator_id"] != session["user_id"]:
        abort(403)
    if not _debit_user_balance(db, user["id"], CHANNEL_VERIFICATION_MONTHLY_PRICE):
        db.rollback()
        flash("insufficient_balance")
        return redirect(url_for("channel_view", channel_id=channel_id))

    base = datetime.datetime.utcnow()
    if channel_is_verified(channel):
        try:
            base = datetime.datetime.fromisoformat(channel["verified_until"])
        except Exception:
            base = datetime.datetime.utcnow()
    verified_until = base + datetime.timedelta(days=30)

    db.execute(
        "UPDATE channels SET is_verified = true, verified_until = ? WHERE id = ?",
        (verified_until.isoformat(), channel_id),
    )
    db.commit()
    return redirect(url_for("channel_view", channel_id=channel_id))


# ---------------------------------------------------------------------------
# Alta Token Economy - Daily Check-in & Task-to-Earn
# ---------------------------------------------------------------------------
@app.route("/tokens")
@login_required
def tokens_page():
    db = get_db()
    user = get_current_user()
    status = checkin_status(user)
    tasks = [
        {
            "key": "profile_completion",
            "reward": TASK_REWARDS["profile_completion"],
            "automatic": False,
            "done": has_completed_task(db, user["id"], "profile_completion"),
            "eligible": is_profile_complete(user),
        },
        {
            "key": "share_job",
            "reward": TASK_REWARDS["share_job"],
            "automatic": True,
        },
    ]
    return render_template(
        "tokens.html",
        checkin_status=status,
        checkin_rewards=CHECKIN_REWARDS,
        tasks=tasks,
        task_tokens_today=daily_task_tokens_earned(db, user["id"]),
        daily_task_cap=DAILY_TASK_CAP,
    )


@app.route("/api/daily-checkin", methods=["POST"])
@login_required
def api_daily_checkin():
    db = get_db()
    user = get_current_user()
    now = datetime.datetime.utcnow()

    if user["last_checkin"]:
        last = datetime.datetime.fromisoformat(user["last_checkin"])
        hours_passed = (now - last).total_seconds() / 3600
        if hours_passed < 24:
            return {
                "error": "too_soon",
                "hours_remaining": round(24 - hours_passed, 1),
            }, 400
        if hours_passed > 48:
            new_streak = 1  # streak broken - missed a day
        else:
            new_streak = 1 if user["current_streak"] >= 7 else user["current_streak"] + 1
    else:
        new_streak = 1  # first ever check-in

    reward = CHECKIN_REWARDS[new_streak]
    new_balance = user["alta_tokens"] + reward

    db.execute(
        "UPDATE users SET alta_tokens = ?, last_checkin = ?, current_streak = ? WHERE id = ?",
        (new_balance, now.isoformat(), new_streak, user["id"]),
    )
    db.execute(
        """INSERT INTO token_transactions (user_id, kind, amount, streak_day, created_at)
           VALUES (?, 'checkin', ?, ?, ?)""",
        (user["id"], reward, new_streak, now.isoformat()),
    )
    db.commit()

    return {
        "success": True,
        "reward": reward,
        "new_streak": new_streak,
        "new_balance": new_balance,
    }


@app.route("/api/complete-task", methods=["POST"])
@login_required
def api_complete_task():
    """Only 'profile_completion' is claimable directly by the client - it's a
    one-time, server-validated action. 'share_job' is NOT accepted here
    anymore: it used to be a free-standing claim button that could be
    clicked repeatedly on the same post for unlimited tokens. It's now
    awarded automatically (via award_task_reward) the moment a genuine
    share happens, tied to that specific post_id, so the same post can
    never pay out twice."""
    data = request.get_json(silent=True) or request.form
    task_type = data.get("task_type")
    if task_type != "profile_completion":
        return {"error": "invalid_task"}, 400

    db = get_db()
    user = get_current_user()

    if has_completed_task(db, user["id"], task_type):
        return {"error": "already_completed"}, 400
    if not is_profile_complete(user):
        return {"error": "profile_incomplete"}, 400

    reward = award_task_reward(db, user["id"], task_type)
    if reward is None:
        return {"error": "daily_cap_reached", "cap": DAILY_TASK_CAP}, 400

    user = get_current_user()  # re-fetch for the updated balance
    return {
        "success": True,
        "reward": reward,
        "new_balance": user["alta_tokens"],
        "earned_today": daily_task_tokens_earned(db, user["id"]),
        "cap": DAILY_TASK_CAP,
    }


# ---------------------------------------------------------------------------
# Marketplace
# ---------------------------------------------------------------------------
@login_required
def cv_maker():
    """Legacy CV route repurposed: accepts the old form POSTs and creates
    a marketplace listing so existing links and tests continue to work.
    GET requests render the lightweight marketplace message template.
    """
    user = get_current_user()
    db = get_db()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        price = request.form.get("price", "0").strip()
        location = (request.form.get("location") or "Addis Ababa").strip()
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename and not allowed_file(photo_file.filename):
            flash("Unsupported image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.")
            return redirect(url_for("cv_maker"))
        photo = save_photo(photo_file)
        if title and price:
            try:
                price_value = float(price)
            except ValueError:
                price_value = 0.0
            status = review_listing(db, user["id"], title, description)
            db.execute(
                """INSERT INTO products (user_id, title, description, price, location, status, photo, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user["id"], title, description, price_value, location, status, photo, datetime.datetime.utcnow().isoformat()),
            )
            # Award points for creating a marketplace listing
            try:
                db.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id = ?", (15, user["id"]))
            except Exception:
                pass
            db.commit()
            flash("Your marketplace listing has been submitted.")
            return redirect(url_for("marketplace"))

    return render_template("cv_maker.html")

@app.route("/marketplace", methods=["GET", "POST"])
@login_required
def marketplace():
    user = get_current_user()
    db = get_db()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        price = request.form.get("price", "0").strip()
        location = (request.form.get("location") or "Addis Ababa").strip()
        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename and not allowed_file(photo_file.filename):
            flash("Unsupported image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.")
            return redirect(url_for("marketplace"))
        photo = save_photo(photo_file)
        if title and price:
            try:
                price_value = float(price)
            except ValueError:
                price_value = 0.0
            try:
                status = review_listing(db, user["id"], title, description)
                db.execute(
                    """INSERT INTO products (user_id, title, description, price, location, status, photo, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user["id"], title, description, price_value, location, status, photo, datetime.datetime.utcnow().isoformat()),
                )
                # Award points for creating a marketplace listing
                try:
                    db.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id = ?", (15, user["id"]))
                except Exception:
                    pass
                db.commit()
                flash("Your marketplace listing has been submitted.")
                return redirect(url_for("marketplace"))
            except Exception as exc:
                db.rollback()
                print(f"Marketplace listing submission failed: {exc}")
                flash("Could not publish your marketplace listing right now. Please try again.")
                return redirect(url_for("marketplace"))

    listings = db.execute(
        """SELECT p.*, u.username, u.full_name, u.verification_tier, u.verified_until
           FROM products p
           JOIN users u ON p.user_id = u.id
           WHERE p.status = 'approved'
           ORDER BY p.created_at DESC LIMIT 50"""
    ).fetchall()
    return render_template("marketplace.html", listings=listings, user=user)


@app.route("/marketplace/buy/<int:product_id>", methods=["POST"])
@login_required
def marketplace_buy(product_id):
    db = get_db()
    buyer = get_current_user()
    product = db.execute(
        "SELECT p.*, u.username, u.full_name FROM products p JOIN users u ON p.user_id = u.id WHERE p.id = ? LIMIT 1",
        (product_id,),
    ).fetchone()
    if not product or product["status"] != "approved":
        flash("This product is not available for purchase.")
        return redirect(url_for("marketplace"))
    if product["user_id"] == buyer["id"]:
        flash("You cannot purchase your own listing.")
        return redirect(url_for("marketplace"))

    price = float(product["price"] or 0)
    if price <= 0:
        flash("This product cannot be purchased at the moment.")
        return redirect(url_for("marketplace"))

    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        if not _debit_user_balance(db, buyer["id"], price):
            db.rollback()
            flash("insufficient_balance")
            return redirect(url_for("wallet"))

        seller_id = product["user_id"]
        _credit_wallet_balance(db, seller_id, price)

        db.execute(
            "UPDATE products SET status = 'sold' WHERE id = ?",
            (product_id,),
        )
        db.execute(
            "INSERT INTO offers (product_id, buyer_id, seller_id, offered_price, status, created_at) VALUES (?, ?, ?, ?, 'approved', ?)",
            (product_id, buyer["id"], seller_id, price, datetime.datetime.utcnow().isoformat()),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'product_purchase', ?, ?, 'approved', ?)",
            (buyer["id"], price, f"Marketplace purchase: {product['title']}", datetime.datetime.utcnow().isoformat()),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'product_sale', ?, ?, 'approved', ?)",
            (seller_id, price, f"Marketplace sale: {product['title']}", datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("Product purchased successfully.")
    except Exception as exc:
        db.rollback()
        print(f"Marketplace purchase failed: {exc}")
        flash("We couldn't complete the purchase right now.")
    return redirect(url_for("marketplace"))

# ---------------------------------------------------------------------------
# Wallet (deposit / withdraw)
# ---------------------------------------------------------------------------
@app.route("/wallet")
@login_required
def wallet():
    db = get_db()
    user = get_current_user()
    try:
        history = db.execute(
            """SELECT * FROM wallet_transactions WHERE user_id = ?
               ORDER BY created_at DESC LIMIT 30""",
            (user["id"],),
        ).fetchall()
    except Exception:
        history = []

    has_pending_withdrawal = bool(db.execute(
        "SELECT id FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' AND status = 'pending' LIMIT 1",
        (user["id"],),
    ).fetchone())

    try:
        gifts_received = db.execute(
            "SELECT COALESCE(SUM(amount - platform_cut), 0) total FROM gifts WHERE receiver_id = ?",
            (user["id"],),
        ).fetchone()["total"]
    except Exception:
        gifts_received = 0

    challenge_status = _safe_fetch_challenge_status(db, user["id"])

    return render_template(
        "wallet.html",
        history=history,
        gifts_received=gifts_received,
        telebirr_number=get_setting("telebirr_wallet_number", TELEBIRR_WALLET_NUMBER),
        verification_price=VERIFICATION_MONTHLY_PRICE,
        verified_now=is_currently_verified(user),
        vip_price=VIP_MONTHLY_PRICE,
        vip_now=is_currently_vip(user),
        challenge_status=challenge_status,
        banks=get_active_banks(),
        has_pending_withdrawal=has_pending_withdrawal,
    )


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "GET":
        return redirect(url_for("wallet", action="deposit"))
    try:
        return wallet_deposit()
    except Exception as exc:
        print(f"Wallet deposit route failed: {exc}")
        flash("We couldn't process your deposit request right now.")
        return redirect(url_for("wallet"))


@app.route("/send", methods=["GET", "POST"])
@login_required
def send_funds():
    if request.method == "GET":
        return redirect(url_for("wallet", action="transfer"))
    try:
        return wallet_transfer()
    except Exception as exc:
        print(f"Wallet transfer route failed: {exc}")
        flash("We couldn't complete that transfer right now.")
        return redirect(url_for("wallet"))


@app.route('/api/wallet/balance')
@login_required
def api_wallet_balance():
    db = get_db()
    # Query the full user row to avoid selecting non-existent columns on older schemas.
    row = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if not row:
        return jsonify({'wallet_balance': 0, 'alta_tokens': 0})
    # Support both sqlite3.Row and psycopg2 RealDictRow
    try:
        wallet_balance = row['wallet_balance'] if 'wallet_balance' in row.keys() else row.get('wallet_balance', 0)
    except Exception:
        wallet_balance = row.get('wallet_balance', 0) if isinstance(row, dict) else 0
    try:
        alta_tokens = row['alta_tokens'] if 'alta_tokens' in row.keys() else row.get('alta_tokens', 0)
    except Exception:
        alta_tokens = row.get('alta_tokens', 0) if isinstance(row, dict) else 0
    return jsonify({'wallet_balance': wallet_balance or 0, 'alta_tokens': alta_tokens or 0})


@app.route("/wallet/transfer", methods=["POST"])
@login_required
def wallet_transfer():
    amount = float(request.form.get("amount", 0) or 0)
    recipient_wallet_id = (request.form.get("recipient_wallet_id") or request.form.get("recipient_identifier") or "").strip()
    if amount <= 0 or not recipient_wallet_id:
        flash("Please enter a valid token amount and recipient wallet number")
        return redirect(url_for("wallet"))

    db = get_db()
    sender = get_current_user()
    sender_id = _get_row_value(sender, "id", session.get("user_id"))
    sender_tokens = float(_get_row_value(sender, "alta_tokens", 0) or 0)

    recipient = db.execute(
        "SELECT * FROM users WHERE wallet_id = ?",
        (recipient_wallet_id,),
    ).fetchone()
    if not recipient or _get_row_value(recipient, "id") == sender_id:
        flash("Recipient wallet number could not be found")
        return redirect(url_for("wallet"))

    recipient_id = _get_row_value(recipient, "id")
    recipient_wallet_number = _get_row_value(recipient, "wallet_id")
    sender_wallet_number = _get_row_value(sender, "wallet_id")

    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        if sender_tokens < amount:
            db.rollback()
            flash("insufficient_tokens")
            return redirect(url_for("wallet"))

        db.execute(
            "UPDATE users SET alta_tokens = alta_tokens - ? WHERE id = ?",
            (amount, sender_id),
        )
        db.execute(
            "UPDATE users SET alta_tokens = alta_tokens + ? WHERE id = ?",
            (amount, recipient_id),
        )

        wallet_columns = _get_table_columns(db, "wallet_transactions")
        send_note = f"Sent tokens to {recipient_wallet_number or recipient_wallet_id}"
        receive_note = f"Received tokens from {sender_wallet_number or 'sender'}"
        tx_columns = ["user_id", "tx_type", "amount", "note", "status", "created_at"]
        tx_values = [sender_id, "transfer", amount, send_note, "approved", datetime.datetime.utcnow().isoformat()]
        if "recipient_wallet_id" in wallet_columns:
            tx_columns.append("recipient_wallet_id")
            tx_values.append(recipient_wallet_number)
        if "recipient_id" in wallet_columns:
            tx_columns.append("recipient_id")
            tx_values.append(recipient_id)

        send_sql = (
            f"INSERT INTO wallet_transactions ({', '.join(tx_columns)}) "
            f"VALUES ({', '.join(['?'] * len(tx_columns))})"
        )
        db.execute(send_sql, tuple(tx_values))

        receive_columns = ["user_id", "tx_type", "amount", "note", "status", "created_at"]
        receive_values = [recipient_id, "transfer", amount, receive_note, "approved", datetime.datetime.utcnow().isoformat()]
        if "recipient_wallet_id" in wallet_columns:
            receive_columns.append("recipient_wallet_id")
            receive_values.append(sender_wallet_number)
        if "recipient_id" in wallet_columns:
            receive_columns.append("recipient_id")
            receive_values.append(sender_id)

        receive_sql = (
            f"INSERT INTO wallet_transactions ({', '.join(receive_columns)}) "
            f"VALUES ({', '.join(['?'] * len(receive_columns))})"
        )
        db.execute(receive_sql, tuple(receive_values))
        db.commit()
        flash("P2P transfer sent")
    except Exception as exc:
        db.rollback()
        print(f"Wallet transfer failed: {exc}")
        flash("We couldn't complete that transfer right now.")
    return redirect(url_for("wallet"))


@app.route('/wallet/lookup')
@login_required
def wallet_lookup():
    """Lookup a user by wallet id (AJAX helper used by wallet send modal).
    Returns JSON: {found: bool, wallet_id: str, username: str, full_name: str}
    """
    db = get_db()
    wallet_id = (request.args.get('wallet_id') or '').strip()
    if not wallet_id:
        return jsonify({'found': False}), 200
    try:
        row = db.execute("SELECT id, username, full_name, wallet_id FROM users WHERE wallet_id = ? LIMIT 1", (wallet_id,)).fetchone()
        if not row:
            return jsonify({'found': False}), 200
        return jsonify({
            'found': True,
            'user_id': _get_row_value(row, 'id'),
            'username': _get_row_value(row, 'username'),
            'full_name': _get_row_value(row, 'full_name') or _get_row_value(row, 'username'),
            'wallet_id': _get_row_value(row, 'wallet_id'),
        })
    except Exception:
        return jsonify({'found': False}), 200


@app.route("/wallet/deposit", methods=["POST"])
@login_required
def wallet_deposit():
    amount = float(request.form.get("amount", 0) or 0)
    bank_id = request.form.get("bank_id") or request.form.get("bankId") or request.form.get("bank")
    ref = request.form.get("transaction_ref", "").strip()
    note = request.form.get("note", "").strip()
    receipt_photo = save_photo(request.files.get("receipt_photo"))

    try:
        bank_id = int(bank_id)
    except (TypeError, ValueError):
        bank_id = None

    if amount <= 0 or not bank_id or not ref:
        flash("Please select a valid bank, amount, and transaction reference.")
        return redirect(url_for("wallet"))

    db = get_db()
    try:
        bank = db.execute(
            "SELECT * FROM bank_accounts WHERE id = ? AND is_active = true",
            (bank_id,),
        ).fetchone()
        if not bank:
            flash("Please select an active bank account.")
            return redirect(url_for("wallet"))

        bank_name = _get_row_value(bank, "bank_name")
        account_number = _get_row_value(bank, "account_number")
        account_name = _get_row_value(bank, "account_holder_name") or _get_row_value(bank, "account_name")
        if not account_name:
            account_name = _get_row_value(bank, "account_name")

        wallet_columns = _get_table_columns(db, "wallet_transactions")
        insert_columns = ["user_id", "tx_type", "amount", "status", "created_at"]
        insert_values = [session["user_id"], "deposit", amount, "pending", datetime.datetime.utcnow().isoformat()]

        if "transaction_ref" in wallet_columns:
            insert_columns.append("transaction_ref")
            insert_values.append(ref)
        if "bank" in wallet_columns:
            insert_columns.append("bank")
            insert_values.append(bank_name)
        if "note" in wallet_columns:
            insert_columns.append("note")
            insert_values.append(note)
        if "receipt_photo" in wallet_columns:
            insert_columns.append("receipt_photo")
            insert_values.append(receipt_photo)
        if "receipt_image_path" in wallet_columns:
            insert_columns.append("receipt_image_path")
            insert_values.append(receipt_photo)
        if "account_number" in wallet_columns:
            insert_columns.append("account_number")
            insert_values.append(account_number)
        if "account_name" in wallet_columns:
            insert_columns.append("account_name")
            insert_values.append(account_name)

        insert_sql = (
            f"INSERT INTO wallet_transactions ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(['?'] * len(insert_columns))})"
        )
        db.execute(insert_sql, tuple(insert_values))
        db.commit()
        flash("Deposit request submitted for review.")
    except Exception as exc:
        db.rollback()
        print(f"Wallet deposit failed: {exc}")
        flash("We couldn't process your deposit request right now.")
    return redirect(url_for("wallet"))


def _submit_withdrawal_request(user_id, amount, bank_name, account_number, account_name):
    amount = float(amount or 0)
    bank_name = (bank_name or "").strip()
    account_number = (account_number or "").strip()
    account_name = (account_name or "").strip()

    if amount < 10:
        return False, "amount_too_small"
    if not bank_name or not account_number or not account_name:
        return False, "missing_withdrawal_details"
    if not re.fullmatch(r"\d+", account_number):
        return False, "invalid_account_number"
    if len(account_name) < 3:
        return False, "invalid_account_name"

    db = get_db()
    user = db.execute("SELECT id, balance, wallet_balance, verification_tier FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return False, "user_not_found"

    balance_value = float(_get_row_value(user, "balance", 0) or 0)
    wallet_balance_value = float(_get_row_value(user, "wallet_balance", 0) or 0)
    balance = balance_value if balance_value > 0 else wallet_balance_value
    is_verified_user = _get_row_value(user, "verification_tier", "none") in ("blue", "gold")
    daily_limit = 50000.0 if not is_verified_user else 500000.0
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' AND status = 'approved' AND created_at >= ?",
        (user_id, today_start),
    ).fetchone()["total"] or 0
    if today_total + amount > daily_limit:
        return False, "daily_limit_exceeded"
    if balance < amount:
        return False, "insufficient_balance"

    pending_exists = db.execute(
        "SELECT id FROM wallet_transactions WHERE user_id = ? AND tx_type = 'withdrawal' AND status = 'pending' LIMIT 1",
        (user_id,),
    ).fetchone()
    if pending_exists:
        return False, "pending_withdrawal_exists"

    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        note = f"Account: {account_name} | Account Number: {account_number}"
        wallet_columns = _get_table_columns(db, "wallet_transactions")
        insert_columns = ["user_id", "tx_type", "amount", "status", "created_at"]
        insert_values = [user_id, "withdrawal", amount, "pending", datetime.datetime.utcnow().isoformat()]
        if "bank" in wallet_columns:
            insert_columns.append("bank")
            insert_values.append(bank_name)
        if "note" in wallet_columns:
            insert_columns.append("note")
            insert_values.append(note)
        if "account_number" in wallet_columns:
            insert_columns.append("account_number")
            insert_values.append(account_number)
        if "account_name" in wallet_columns:
            insert_columns.append("account_name")
            insert_values.append(account_name)

        insert_sql = (
            f"INSERT INTO wallet_transactions ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(['?'] * len(insert_columns))})"
        )
        db.execute(insert_sql, tuple(insert_values))
        db.commit()
        return True, None
    except Exception:
        db.rollback()
        raise


@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw_request():
    amount = request.form.get("amount", 0)
    bank_selection = request.form.get("bank_id") or request.form.get("bankSelection") or ""
    manual_bank_name = (
        request.form.get("bankNameManual")
        or request.form.get("bank_name_manual")
        or ""
    )
    account_number = (
        request.form.get("accountNumber")
        or request.form.get("account_number")
        or ""
    )
    account_name = (
        request.form.get("accountName")
        or request.form.get("account_name")
        or ""
    )

    bank_name = ""
    bank_id = None
    bank_selection_value = str(bank_selection).strip()
    if bank_selection_value and bank_selection_value.lower() not in {"other", "manual", "manual entry"}:
        try:
            bank_id = int(bank_selection_value)
        except (TypeError, ValueError):
            bank_id = None
            bank_name = bank_selection_value

    if bank_id is not None:
        db = get_db()
        bank = db.execute(
            "SELECT * FROM bank_accounts WHERE id = ? AND is_active = true",
            (bank_id,),
        ).fetchone()
        if bank:
            bank_name = _get_row_value(bank, "bank_name") or ""
        else:
            flash("Please select an active bank or enter a bank destination.")
            return redirect(url_for("wallet"))

    if not bank_name:
        bank_name = manual_bank_name.strip()

    if not bank_name:
        flash("Please select an active bank or enter a bank destination.")
        return redirect(url_for("wallet"))

    try:
        success, error = _submit_withdrawal_request(
            session["user_id"], amount, bank_name, account_number, account_name
        )
        if not success:
            if error == "pending_withdrawal_exists":
                flash("You already have a pending withdrawal request. Please wait for admin approval before submitting another.")
            elif error == "insufficient_balance":
                flash("You do not have enough wallet balance to cover this withdrawal.")
            elif error == "amount_too_small":
                flash("Withdrawal amount must be at least 10 ETB.")
            else:
                flash(error or "invalid_withdrawal_request")
        else:
            flash("Withdrawal request submitted and is pending admin approval.")
    except Exception as exc:
        print(f"Withdrawal request failed: {exc}")
        flash("We couldn't process your withdrawal request right now.")
    return redirect(url_for("wallet"))


@app.route("/wallet/withdraw", methods=["POST"])
@login_required
def wallet_withdraw():
    return withdraw_request()


# ---------------------------------------------------------------------------
# Blue Tick Verification
# ---------------------------------------------------------------------------
@app.route("/verify/buy", methods=["POST"])
@login_required
def buy_verification():
    db = get_db()
    user = get_current_user()
    user_id = session.get("user_id")
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        # re-fetch fresh user row inside transaction
        fresh = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        verification_price = float(get_setting("verification_price", VERIFICATION_MONTHLY_PRICE) or VERIFICATION_MONTHLY_PRICE)
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ? AND wallet_balance >= ?",
            (verification_price, user_id, verification_price),
        )
        if cur.rowcount == 0:
            db.rollback()
            flash("insufficient_balance")
            return redirect(url_for("wallet"))

        base = datetime.datetime.utcnow()
        if fresh and is_currently_verified(fresh):
            base = datetime.datetime.fromisoformat(fresh["verified_until"]) if fresh["verified_until"] else base
        verified_until = base + datetime.timedelta(days=30)
        # Don't downgrade an existing gold/VIP tier to blue.
        current_tier = get_verification_tier(fresh)
        new_tier = "gold" if current_tier == "gold" else "blue"
        db.execute(
            "UPDATE users SET verification_tier = ?, verified_until = ? WHERE id = ?",
            (new_tier, verified_until.isoformat(), user_id),
        )
        # Award points for obtaining Blue Tick verification
        try:
            db.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id = ?", (100, user_id))
        except Exception:
            pass
        admin_user = db.execute(
            "SELECT * FROM users WHERE is_admin = true ORDER BY id LIMIT 1"
        ).fetchone()
        if admin_user:
            db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                (verification_price, admin_user["id"]),
            )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'verification', ?, ?, 'approved', ?)",
            (user_id, verification_price, "Blue Tick purchase", datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("wallet"))


# ---------------------------------------------------------------------------
# Blue / Gold Verification Subscription (pricing page + checkout)
# ---------------------------------------------------------------------------
@app.route("/get-verified")
@login_required
def get_verified():
    """Render the Blue/Gold pricing page. Plans come from VERIFICATION_PLANS
    (the single source of truth) — nothing here is hardcoded."""
    user = get_current_user()
    return render_template(
        "verification.html",
        plans=VERIFICATION_PLANS,
        current_tier=get_verification_tier(user),
        current_verified_until=_field(user, "verified_until"),
        verification_days_left=verification_days_left(user),
    )


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    """Checkout screen. Supports viewing the plan via GET and paying from wallet via POST."""
    if request.method == "GET":
        tier = request.args.get("tier", "")
        duration_id = request.args.get("duration", "")
        plan = get_verification_plan(tier, duration_id)
        if not plan:
            flash("That plan isn't available. Please choose a plan again.")
            return redirect(url_for("get_verified"))
        return render_template("checkout.html", plan=plan)

    # POST: pay from wallet and activate verification tier
    tier = request.form.get("tier", "")
    duration_id = request.form.get("duration", "")
    plan = get_verification_plan(tier, duration_id)
    if not plan:
        flash("That plan isn't available. Please choose a plan again.")
        return redirect(url_for("get_verified"))

    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        if not _debit_user_balance(db, session["user_id"], plan["price"]):
            db.rollback()
            flash("insufficient_balance")
            return redirect(url_for("wallet"))

        current_user = get_current_user()
        base = datetime.datetime.utcnow()
        if is_currently_verified(current_user):
            try:
                base = datetime.datetime.fromisoformat(current_user["verified_until"])
            except Exception:
                base = datetime.datetime.utcnow()

        current_tier = get_verification_tier(current_user)
        # Badge tier follows subscription LENGTH, not which plan card was
        # clicked: a 12-month purchase (whether bought as "Blue" or "Gold")
        # grants the Gold tick; a 1-month or 6-month purchase grants the
        # Blue tick. An existing Gold tier is never downgraded by a shorter
        # renewal purchase.
        effective_tier = "gold" if (plan["months"] >= 12 or current_tier == "gold") else "blue"
        verified_until = base + datetime.timedelta(days=30 * plan["months"])

        db.execute(
            "UPDATE users SET verification_tier = ?, verified_until = ? WHERE id = ?",
            (effective_tier, verified_until.isoformat(), session["user_id"]),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'verification', ?, ?, 'approved', ?)",
            (session["user_id"], plan["price"], f"{plan['label']} verification purchase", datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("wallet"))


# ---------------------------------------------------------------------------
# VIP Membership
# ---------------------------------------------------------------------------
@app.route("/vip/buy", methods=["POST"])
@login_required
def buy_vip():
    db = get_db()
    user = get_current_user()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        fresh = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        vip_price = float(get_setting("vip_price", VIP_MONTHLY_PRICE) or VIP_MONTHLY_PRICE)
        if not _debit_user_balance(db, user["id"], vip_price):
            db.rollback()
            flash("insufficient_balance")
            return redirect(url_for("wallet"))

        base = datetime.datetime.utcnow()
        if fresh and is_currently_vip(fresh):
            try:
                base = datetime.datetime.fromisoformat(fresh["verified_until"]) if fresh["verified_until"] else base
            except Exception:
                base = datetime.datetime.utcnow()
        vip_until = base + datetime.timedelta(days=30)
        db.execute(
            "UPDATE users SET verification_tier = 'gold', verified_until = ? WHERE id = ?",
            (vip_until.isoformat(), user["id"]),
        )
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'vip', ?, ?, 'approved', ?)",
            (user["id"], vip_price, "VIP membership purchase", datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("wallet"))


# ---------------------------------------------------------------------------
# Gifts (animated tipping between users)
# ---------------------------------------------------------------------------
@app.route("/gift/send", methods=["POST"])
@login_required
def send_gift():
    receiver_id = int(request.form.get("receiver_id"))
    gift_key = request.form.get("gift_key")
    post_id = request.form.get("post_id")
    sender = get_current_user()

    gift = GIFT_CATALOG.get(gift_key)
    if not gift or receiver_id == sender["id"]:
        return redirect(request.referrer or url_for("feed"))

    price = gift["price"]
    platform_cut = round(price * PLATFORM_CUT_PERCENT / 100)
    receiver_share = price - platform_cut

    db = get_db()
    # transaction-safe: deduct from sender only if they have sufficient balance
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ? AND wallet_balance >= ?",
            (price, sender["id"], price),
        )
        if cur.rowcount == 0:
            db.rollback()
            flash("insufficient_balance")
            return redirect(request.referrer or url_for("feed"))

        db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                   (receiver_share, receiver_id))
        db.execute(
            """INSERT INTO gifts (sender_id, receiver_id, gift_key, amount, platform_cut, post_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sender["id"], receiver_id, gift_key, price, platform_cut,
             post_id if post_id else None, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("gift_sent")
    except Exception:
        db.rollback()
        raise
    return redirect(request.referrer or url_for("feed"))


# ---------------------------------------------------------------------------
# Follow system
# ---------------------------------------------------------------------------
@app.route("/follow/suggestions")
@login_required
def follow_suggestions():
    db = get_db()
    already = db.execute(
        "SELECT followed_id FROM follows WHERE follower_id = ?", (session["user_id"],)
    ).fetchall()
    already_ids = {r["followed_id"] for r in already} | {session["user_id"]}
    placeholders = ",".join("?" * len(already_ids))
    suggestions = db.execute(
        f"""SELECT * FROM users WHERE id NOT IN ({placeholders})
            ORDER BY CASE verification_tier WHEN 'gold' THEN 0 WHEN 'blue' THEN 1 ELSE 2 END,
                     created_at DESC LIMIT 15""",
        tuple(already_ids),
    ).fetchall()
    gate = viral_gate_status(db, session["user_id"])
    return render_template("follow_suggestions.html", suggestions=suggestions, gate=gate)


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def toggle_follow(user_id):
    if user_id == session["user_id"]:
        return redirect(request.referrer or url_for("feed"))
    db = get_db()
    existing = db.execute(
        "SELECT id FROM follows WHERE follower_id = ? AND followed_id = ?",
        (session["user_id"], user_id),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM follows WHERE id = ?", (existing["id"],))
    else:
        db.execute(
            "INSERT INTO follows (follower_id, followed_id, created_at) VALUES (?, ?, ?)",
            (session["user_id"], user_id, datetime.datetime.utcnow().isoformat()),
        )
    db.commit()
    return redirect(request.referrer or url_for("feed"))


@app.route("/api/follow/<int:user_id>", methods=["POST"])
@login_required
def api_toggle_follow(user_id):
    """JSON version of toggle_follow for the JS-powered instant Follow button."""
    if user_id == session["user_id"]:
        return {"error": "cannot follow yourself"}, 400
    db = get_db()
    existing = db.execute(
        "SELECT id FROM follows WHERE follower_id = ? AND followed_id = ?",
        (session["user_id"], user_id),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM follows WHERE id = ?", (existing["id"],))
        db.commit()
        following = False
    else:
        db.execute(
            "INSERT INTO follows (follower_id, followed_id, created_at) VALUES (?, ?, ?)",
            (session["user_id"], user_id, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        following = True
    return {"following": following}


# ---------------------------------------------------------------------------
# Referral / Sharing (viral gate)
# ---------------------------------------------------------------------------
@app.route("/challenge/invite")
@login_required
def challenge_invite():
    db = get_db()
    user = get_current_user()
    gate = viral_gate_status(db, user["id"])
    referral_link = url_for("register", ref=user["referral_code"], _external=True)
    return render_template("challenge_invite.html", gate=gate, referral_link=referral_link)


@app.route("/challenge/share", methods=["POST"])
@login_required
def log_share():
    platform = request.form.get("platform", "other")
    db = get_db()
    existing = db.execute(
        "SELECT id FROM challenge_shares WHERE user_id = ? AND platform = ?",
        (session["user_id"], platform),
    ).fetchone()
    if existing:
        # Avoid duplicate shares to the same platform being counted repeatedly.
        return redirect(request.referrer or url_for("challenge_invite"))
    db.execute(
        "INSERT INTO challenge_shares (user_id, platform, created_at) VALUES (?, ?, ?)",
        (session["user_id"], platform, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return redirect(request.referrer or url_for("challenge_invite"))


# ---------------------------------------------------------------------------
# Monthly Business Challenge - entry & judging
# ---------------------------------------------------------------------------
@app.route("/challenges")
@login_required
def challenges():
    db = get_db()
    user = get_current_user()
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    gate = viral_gate_status(db, user["id"])

    pools = []
    for tier in CHALLENGE_TIERS:
        pool = db.execute(
            "SELECT * FROM challenge_pools WHERE tier_amount = ? AND month = ?",
            (tier, month),
        ).fetchone()
        entry_count = 0
        prize_pool = 0
        my_entry = None
        if pool:
            entry_count = db.execute(
                "SELECT COUNT(*) c FROM challenge_entries WHERE pool_id = ?", (pool["id"],)
            ).fetchone()["c"]
            prize_pool = pool["prize_pool"]
            my_entry = db.execute(
                "SELECT * FROM challenge_entries WHERE pool_id = %s AND user_id = %s",
                (pool["id"], user["id"]),
            ).fetchone()
        pools.append({
            "tier": tier, "pool": pool, "entry_count": entry_count,
            "prize_pool": prize_pool, "my_entry": my_entry,
        })

    return render_template("challenges.html", pools=pools, gate=gate)


@app.route("/challenge/<int:tier>/join", methods=["GET", "POST"])
@login_required
@subscription_required
def join_challenge(tier):
    if tier not in CHALLENGE_TIERS:
        abort(404)
    db = get_db()
    user = get_current_user()
    gate = viral_gate_status(db, user["id"])

    if not gate["unlocked"]:
        flash("viral_gate_locked")
        return redirect(url_for("challenge_invite"))

    if request.method == "POST":
        pitch_text = request.form.get("pitch_text", "").strip()
        if len(pitch_text) < 30:
            flash("pitch_too_short")
            return redirect(url_for("join_challenge", tier=tier))
        if not _debit_user_balance(db, user["id"], tier):
            db.rollback()
            flash("insufficient_balance")
            return redirect(url_for("join_challenge", tier=tier))

        pool = get_or_create_pool(db, tier)
        existing_entry = db.execute(
            "SELECT id FROM challenge_entries WHERE pool_id = ? AND user_id = ?",
            (pool["id"], user["id"]),
        ).fetchone()
        if existing_entry:
            flash("already_entered")
            return redirect(url_for("challenges"))

        ai_score = score_pitch_ai(pitch_text)

        new_balance = user["wallet_balance"] - tier
        db.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_balance, user["id"]))
        db.execute(
            """INSERT INTO challenge_entries
               (pool_id, user_id, amount_paid, pitch_text, ai_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pool["id"], user["id"], tier, pitch_text, ai_score,
             datetime.datetime.utcnow().isoformat()),
        )
        db.execute(
            "UPDATE challenge_pools SET prize_pool = prize_pool + ? WHERE id = ?",
            (tier, pool["id"]),
        )
        db.execute(
            """INSERT INTO wallet_transactions (user_id, tx_type, amount, status, created_at)
               VALUES (?, 'challenge_entry', ?, 'approved', ?)""",
            (user["id"], tier, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("challenge_entry_submitted")
        return redirect(url_for("challenges"))

    return render_template("challenge_join.html", tier=tier)


# ---------------------------------------------------------------------------
# Winner Trust Protocol - escrow, guarantor, milestone disbursement
# ---------------------------------------------------------------------------
@app.route("/challenge/winner/<int:entry_id>")
@login_required
def winner_page(entry_id):
    db = get_db()
    entry = db.execute(
        "SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not entry or (entry["user_id"] != session["user_id"] and not get_current_user()["is_admin"]):
        abort(404)
    trust = db.execute(
        "SELECT * FROM winner_trust WHERE entry_id = ?", (entry_id,)
    ).fetchone()
    pool = db.execute(
        "SELECT * FROM challenge_pools WHERE id = ?", (entry["pool_id"],)
    ).fetchone()
    return render_template(
        "challenge_winner.html", entry=entry, trust=trust, pool=pool,
        milestone1_percent=MILESTONE_1_PERCENT,
    )


@app.route("/challenge/winner/<int:entry_id>/confirm", methods=["POST"])
@login_required
def winner_confirm(entry_id):
    db = get_db()
    entry = db.execute(
        "SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not entry or entry["user_id"] != session["user_id"]:
        abort(404)
    trust = db.execute("SELECT * FROM winner_trust WHERE entry_id = ?", (entry_id,)).fetchone()
    if not trust or trust["confirmed_at"]:
        return redirect(url_for("winner_page", entry_id=entry_id))
    if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(trust["confirm_deadline"]):
        flash("challenge_deadline_passed")
        return redirect(url_for("winner_page", entry_id=entry_id))

    guarantor_name = request.form.get("guarantor_name", "").strip()
    guarantor_id_number = request.form.get("guarantor_id_number", "").strip()
    guarantor_photo = save_photo(request.files.get("guarantor_photo"))

    if not guarantor_name or not guarantor_id_number:
        flash("guarantor_info_required")
        return redirect(url_for("winner_page", entry_id=entry_id))

    db.execute(
        """UPDATE winner_trust SET confirmed_at = ?, guarantor_name = ?,
           guarantor_id_number = ?, guarantor_photo = ?, disbursement_status = 'pending_admin_review'
           WHERE entry_id = ?""",
        (datetime.datetime.utcnow().isoformat(), guarantor_name,
         guarantor_id_number, guarantor_photo, entry_id),
    )
    db.commit()
    return redirect(url_for("winner_page", entry_id=entry_id))


@app.route("/challenge/winner/<int:entry_id>/submit_proof", methods=["POST"])
@login_required
def winner_submit_proof(entry_id):
    db = get_db()
    entry = db.execute(
        "SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not entry or entry["user_id"] != session["user_id"]:
        abort(404)
    trust = db.execute("SELECT * FROM winner_trust WHERE entry_id = ?", (entry_id,)).fetchone()
    if not trust or trust["disbursement_status"] != "escrow_50_released":
        return redirect(url_for("winner_page", entry_id=entry_id))

    proof_photo = save_photo(request.files.get("proof_photo"))
    if not proof_photo:
        flash("proof_photo_required")
        return redirect(url_for("winner_page", entry_id=entry_id))

    db.execute(
        """UPDATE winner_trust SET proof_photo = ?, proof_submitted_at = ?,
           disbursement_status = 'pending_proof_review' WHERE entry_id = ?""",
        (proof_photo, datetime.datetime.utcnow().isoformat(), entry_id),
    )
    db.commit()
    return redirect(url_for("winner_page", entry_id=entry_id))


# ---------------------------------------------------------------------------
# Admin - Challenge judging & escrow approval
# ---------------------------------------------------------------------------
@app.route("/admin/challenges")
@login_required
@admin_required
def admin_challenges():
    db = get_db()
    pools = db.execute(
        "SELECT * FROM challenge_pools ORDER BY created_at DESC"
    ).fetchall()
    pools_data = []
    for pool in pools:
        entries = db.execute(
            """SELECT challenge_entries.*, users.username FROM challenge_entries
               JOIN users ON challenge_entries.user_id = users.id
               WHERE pool_id = ? ORDER BY challenge_entries.final_score DESC,
               challenge_entries.ai_score DESC""",
            (pool["id"],),
        ).fetchall()
        pools_data.append({"pool": pool, "entries": entries})

    winners = db.execute(
        """SELECT challenge_entries.*, users.username, winner_trust.*
           FROM challenge_entries
           JOIN users ON challenge_entries.user_id = users.id
           JOIN winner_trust ON winner_trust.entry_id = challenge_entries.id
           WHERE challenge_entries.status = 'winner'
           ORDER BY winner_trust.created_at DESC"""
    ).fetchall()

    return render_template(
        "admin_challenges.html", pools_data=pools_data, winners=winners,
        pitch_window_hours=PITCH_WINDOW_HOURS, milestone1_percent=MILESTONE_1_PERCENT,
    )


@app.route("/admin/challenge/entry/<int:entry_id>/score", methods=["POST"])
@login_required
@admin_required
def score_entry(entry_id):
    admin_score = float(request.form.get("admin_score", 0) or 0)
    admin_score = max(0.0, min(100.0, admin_score))
    db = get_db()
    entry = db.execute("SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)).fetchone()
    if entry:
        bonus = compute_engagement_bonus(db, entry["user_id"])
        final_score = round((entry["ai_score"] or 0) * 0.5 + admin_score * 0.5 + bonus, 1)
        db.execute(
            """UPDATE challenge_entries SET admin_score = ?, engagement_bonus = ?,
               final_score = ? WHERE id = ?""",
            (admin_score, bonus, final_score, entry_id),
        )
        db.commit()
    return redirect(url_for("admin_challenges"))


@app.route("/admin/challenge/pool/<int:pool_id>/select_winner", methods=["POST"])
@login_required
@admin_required
def select_winner(pool_id):
    db = get_db()
    pool = db.execute("SELECT * FROM challenge_pools WHERE id = ?", (pool_id,)).fetchone()
    if not pool or pool["status"] != "open":
        return redirect(url_for("admin_challenges"))

    entries = db.execute(
        "SELECT * FROM challenge_entries WHERE pool_id = ? ORDER BY "
        "COALESCE(final_score, ai_score) DESC LIMIT 1",
        (pool_id,),
    ).fetchall()
    if not entries:
        return redirect(url_for("admin_challenges"))

    winner_entry = entries[0]
    net_prize = round(pool["prize_pool"] * (100 - pool["platform_fee_percent"]) / 100)
    milestone1 = round(net_prize * MILESTONE_1_PERCENT / 100)
    milestone2 = net_prize - milestone1

    db.execute(
        "UPDATE challenge_entries SET status = 'winner' WHERE id = ?",
        (winner_entry["id"],),
    )
    db.execute(
        "UPDATE challenge_entries SET status = 'not_selected' "
        "WHERE pool_id = ? AND id != ?",
        (pool_id, winner_entry["id"]),
    )
    db.execute(
        "UPDATE challenge_pools SET status = 'closed', winner_entry_id = ? WHERE id = ?",
        (winner_entry["id"], pool_id),
    )
    deadline = datetime.datetime.utcnow() + datetime.timedelta(hours=PITCH_WINDOW_HOURS)
    db.execute(
        """INSERT INTO winner_trust
           (entry_id, confirm_deadline, milestone1_amount, milestone2_amount, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (winner_entry["id"], deadline.isoformat(), milestone1, milestone2,
         datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return redirect(url_for("admin_challenges"))


@app.route("/admin/challenge/winner/<int:entry_id>/approve_guarantor", methods=["POST"])
@login_required
@admin_required
def approve_guarantor(entry_id):
    db = get_db()
    trust = db.execute("SELECT * FROM winner_trust WHERE entry_id = ?", (entry_id,)).fetchone()
    entry = db.execute("SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)).fetchone()
    if trust and entry and trust["disbursement_status"] == "pending_admin_review":
        winner = db.execute("SELECT * FROM users WHERE id = ?", (entry["user_id"],)).fetchone()
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
            (trust["milestone1_amount"], entry["user_id"]),
        )
        db.execute(
            """INSERT INTO wallet_transactions (user_id, tx_type, amount, status, created_at)
               VALUES (?, 'challenge_milestone1', ?, 'approved', ?)""",
            (entry["user_id"], trust["milestone1_amount"], datetime.datetime.utcnow().isoformat()),
        )
        db.execute(
            """UPDATE winner_trust SET milestone1_released = 1,
               disbursement_status = 'escrow_50_released' WHERE entry_id = ?""",
            (entry_id,),
        )
        db.commit()
    return redirect(url_for("admin_challenges"))


@app.route("/admin/challenge/winner/<int:entry_id>/approve_proof", methods=["POST"])
@login_required
@admin_required
def approve_proof(entry_id):
    db = get_db()
    trust = db.execute("SELECT * FROM winner_trust WHERE entry_id = ?", (entry_id,)).fetchone()
    entry = db.execute("SELECT * FROM challenge_entries WHERE id = ?", (entry_id,)).fetchone()
    if trust and entry and trust["disbursement_status"] == "pending_proof_review":
        db.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
            (trust["milestone2_amount"], entry["user_id"]),
        )
        db.execute(
            """INSERT INTO wallet_transactions (user_id, tx_type, amount, status, created_at)
               VALUES (?, 'challenge_milestone2', ?, 'approved', ?)""",
            (entry["user_id"], trust["milestone2_amount"], datetime.datetime.utcnow().isoformat()),
        )
        db.execute(
            """UPDATE winner_trust SET milestone2_released = 1,
               disbursement_status = 'completed' WHERE entry_id = ?""",
            (entry_id,),
        )
        db.commit()
    return redirect(url_for("admin_challenges"))


@app.route("/admin/challenge/winner/<int:entry_id>/forfeit", methods=["POST"])
@login_required
@admin_required
def forfeit_winner(entry_id):
    db = get_db()
    db.execute(
        "UPDATE winner_trust SET disbursement_status = 'forfeited_timeout' WHERE entry_id = ?",
        (entry_id,),
    )
    db.commit()
    return redirect(url_for("admin_challenges"))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@app.route("/admin/products")
@login_required
@admin_required
def admin_products():
    db = get_db()
    listings = db.execute(
        "SELECT p.*, u.username FROM products p JOIN users u ON p.user_id = u.id WHERE p.status = 'pending' ORDER BY p.created_at DESC"
    ).fetchall()
    return render_template("admin_products.html", listings=listings)


@app.route("/admin/products/<int:product_id>/approve", methods=["POST"])
@login_required
@admin_required
def admin_approve_product(product_id):
    db = get_db()
    db.execute("UPDATE products SET status = 'approved' WHERE id = ?", (product_id,))
    # refresh seller trust status
    seller = db.execute("SELECT user_id FROM products WHERE id = ?", (product_id,)).fetchone()
    if seller:
        refresh_trust_status(db, seller["user_id"]) if 'refresh_trust_status' in globals() else None
    db.commit()
    return redirect(request.referrer or url_for("admin_products"))


@app.route("/admin/products/<int:product_id>/reject", methods=["POST"])
@login_required
@admin_required
def admin_reject_product(product_id):
    db = get_db()
    db.execute("UPDATE products SET status = 'rejected' WHERE id = ?", (product_id,))
    # increment strike for the seller
    row = db.execute("SELECT user_id FROM products WHERE id = ?", (product_id,)).fetchone()
    if row:
        add_strike(db, row["user_id"], reason="product_rejected_by_admin")
    db.commit()
    return redirect(request.referrer or url_for("admin_products"))


@app.route("/admin")
@app.route("/admin/overview")
@login_required
@admin_required
def admin_panel():
    try:
        db = get_db()
        if not db.is_sqlite:
            try:
                db.execute("SET LOCAL statement_timeout = 3000")
            except Exception:
                pass
        pending_payments = db.execute(
            """SELECT payments.*, users.username FROM payments
               JOIN users ON payments.user_id = users.id
               WHERE payments.status = 'pending'
               ORDER BY payments.created_at DESC
               LIMIT 50"""
        ).fetchall()
        reports = db.execute(
            """SELECT reports.*, users.username as reporter FROM reports
               JOIN users ON reports.reporter_id = users.id
               WHERE reports.status = 'pending'
               ORDER BY reports.created_at DESC
               LIMIT 50"""
        ).fetchall()
        pending_wallet_tx = db.execute(
            """SELECT wallet_transactions.*, users.username, users.phone FROM wallet_transactions
               JOIN users ON wallet_transactions.user_id = users.id
               WHERE wallet_transactions.status = 'pending'
               ORDER BY wallet_transactions.created_at DESC
               LIMIT 100"""
        ).fetchall()
        total_users = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        pending_unverified_users = db.execute(
            "SELECT COUNT(*) c FROM users WHERE verification_tier IS NULL OR verification_tier = 'none'"
        ).fetchone()["c"]
        pending_deposits_count = db.execute("SELECT COUNT(*) c FROM wallet_transactions WHERE status = 'pending' AND tx_type = 'deposit'").fetchone()["c"]
        pending_withdrawals_count = db.execute("SELECT COUNT(*) c FROM wallet_transactions WHERE status = 'pending' AND tx_type = 'withdrawal'").fetchone()["c"]
        gift_earnings = db.execute(
            "SELECT COALESCE(SUM(platform_cut), 0) total FROM gifts"
        ).fetchone()["total"]
        verified_users_count = db.execute(
            "SELECT COUNT(*) c FROM users WHERE verification_tier IN ('blue', 'gold')"
        ).fetchone()["c"]
        vip_users_count = db.execute(
            "SELECT COUNT(*) c FROM users WHERE verification_tier = 'gold'"
        ).fetchone()["c"]
        subscription_revenue = db.execute(
            "SELECT COALESCE(SUM(amount), 0) total FROM payments WHERE status = 'approved'"
        ).fetchone()["total"]
        total_revenue = subscription_revenue + gift_earnings

        verification_price = float(get_setting("verification_price", VERIFICATION_MONTHLY_PRICE) or VERIFICATION_MONTHLY_PRICE)
        vip_price = float(get_setting("vip_price", VIP_MONTHLY_PRICE) or VIP_MONTHLY_PRICE)
        return render_template(
            "admin.html", pending_payments=pending_payments, reports=reports,
            pending_wallet_tx=pending_wallet_tx, gift_earnings=gift_earnings,
            verified_users_count=verified_users_count,
            vip_users_count=vip_users_count,
            subscription_revenue=subscription_revenue,
            total_revenue=total_revenue,
            verification_price=verification_price,
            vip_price=vip_price,
        )
    except Exception as exc:
        print(f"Admin overview page error: {exc}")
        flash("Could not load admin overview at this time.")
        return render_template(
            "admin.html", pending_payments=[], reports=[], pending_wallet_tx=[],
            gift_earnings=0, verified_users_count=0, vip_users_count=0,
            subscription_revenue=0, total_revenue=0,
            verification_price=float(get_setting("verification_price", VERIFICATION_MONTHLY_PRICE) or VERIFICATION_MONTHLY_PRICE),
            vip_price=float(get_setting("vip_price", VIP_MONTHLY_PRICE) or VIP_MONTHLY_PRICE),
        )


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "save_settings")
        if action == "save_settings":
            maintenance = request.form.get("maintenance_mode") == "1"
            set_setting("maintenance_mode", "1" if maintenance else "0")
            set_setting("verification_price", request.form.get("verification_price", str(VERIFICATION_MONTHLY_PRICE)))
            set_setting("vip_price", request.form.get("vip_price", str(VIP_MONTHLY_PRICE)))
            set_setting("extra_product_fee", request.form.get("extra_product_fee", "0"))
            set_setting("social_auth_enabled", request.form.get("social_auth_enabled") == "1" and "1" or "0")
            set_setting("social_google_url", request.form.get("social_google_url", "").strip())
            set_setting("social_telegram_url", request.form.get("social_telegram_url", "").strip())
            set_setting("social_discord_url", request.form.get("social_discord_url", "").strip())
            flash("Settings updated.")
            return redirect(url_for("admin_settings"))

        if action == "create_bank":
            bank_name = (request.form.get("bank_name") or "").strip()
            account_number = (request.form.get("account_number") or "").strip()
            account_holder_name = (request.form.get("account_holder_name") or "").strip()
            is_active = request.form.get("is_active") == "1"
            if not bank_name or not account_number or not account_holder_name:
                flash("Bank name, account number, and account holder name are required.")
                return redirect(url_for("admin_settings"))
            columns = _get_table_columns(db, "bank_accounts")
            insert_columns = ["bank_name", "account_number"]
            insert_values = [bank_name, account_number]
            if "account_holder_name" in columns:
                insert_columns.append("account_holder_name")
                insert_values.append(account_holder_name)
            elif "account_name" in columns:
                insert_columns.append("account_name")
                insert_values.append(account_holder_name)
            if "is_active" in columns:
                insert_columns.append("is_active")
                insert_values.append(True if is_active else False)
            insert_columns.append("created_at")
            insert_values.append(datetime.datetime.utcnow().isoformat())
            insert_sql = f"INSERT INTO bank_accounts ({', '.join(insert_columns)}) VALUES ({', '.join(['?'] * len(insert_columns))})"
            db.execute(insert_sql, tuple(insert_values))
            db.commit()
            flash("Bank account added.")
            return redirect(url_for("admin_settings"))

        if action == "toggle_bank":
            bank_id = request.form.get("bank_id")
            try:
                bank_id = int(bank_id)
            except (TypeError, ValueError):
                bank_id = None
            if bank_id is None:
                flash("Could not update bank account status.")
                return redirect(url_for("admin_settings"))
            is_active = request.form.get("is_active") == "1"
            db.execute(
                "UPDATE bank_accounts SET is_active = %s WHERE id = %s",
                (True if is_active else False, bank_id),
            )
            db.commit()
            flash("Bank account status updated.")
            return redirect(url_for("admin_settings"))

        if action == "delete_bank":
            bank_id = request.form.get("bank_id")
            try:
                bank_id = int(bank_id)
            except (TypeError, ValueError):
                bank_id = None
            if bank_id is None:
                flash("Could not delete bank account.")
                return redirect(url_for("admin_settings"))
            db.execute("DELETE FROM bank_accounts WHERE id = ?", (bank_id,))
            db.commit()
            flash("Bank account removed.")
            return redirect(url_for("admin_settings"))

    maintenance_mode = get_setting("maintenance_mode", "0") == "1"
    verification_price = float(get_setting("verification_price", VERIFICATION_MONTHLY_PRICE) or VERIFICATION_MONTHLY_PRICE)
    vip_price = float(get_setting("vip_price", VIP_MONTHLY_PRICE) or VIP_MONTHLY_PRICE)
    extra_product_fee = float(get_setting("extra_product_fee", 0) or 0)
    social_auth_on = get_setting("social_auth_enabled", "1") == "1"
    google_url = get_setting("social_google_url", "") or ""
    telegram_url = get_setting("social_telegram_url", "") or ""
    discord_url = get_setting("social_discord_url", "") or ""
    banks = get_all_banks()
    return render_template(
        "admin_settings.html",
        maintenance_mode=maintenance_mode,
        verification_price=verification_price,
        vip_price=vip_price,
        extra_product_fee=extra_product_fee,
        social_auth_on=social_auth_on,
        social_google_url=google_url,
        social_telegram_url=telegram_url,
        social_discord_url=discord_url,
        banks=banks,
    )


# ---------------------------------------------------------------------------
# Admin Dashboard - standalone deposit-approval view
# (additive only - does not touch admin_panel() or approve_wallet_tx() above)
# ---------------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    def _normalize_page(key):
        try:
            page_value = int(request.args.get(key, 1))
            return page_value if page_value >= 1 else 1
        except Exception:
            return 1

    try:
        db = get_db()
        if not db.is_sqlite:
            try:
                db.execute("SET LOCAL statement_timeout = 3000")
            except Exception:
                pass

        deposit_page = _normalize_page("deposit_page")
        withdrawal_page = _normalize_page("withdrawal_page")
        page_size = 20
        deposit_offset = (deposit_page - 1) * page_size
        withdrawal_offset = (withdrawal_page - 1) * page_size

        total_deposits_row = db.execute(
            "SELECT COUNT(*) c FROM wallet_transactions WHERE status = 'pending' AND tx_type = 'deposit'"
        ).fetchone()
        total_withdrawals_row = db.execute(
            "SELECT COUNT(*) c FROM wallet_transactions WHERE status = 'pending' AND tx_type = 'withdrawal'"
        ).fetchone()
        pending_deposit_count = total_deposits_row["c"] if total_deposits_row else 0
        pending_withdrawal_count = total_withdrawals_row["c"] if total_withdrawals_row else 0
        deposit_pages = max(1, (pending_deposit_count + page_size - 1) // page_size)
        withdrawal_pages = max(1, (pending_withdrawal_count + page_size - 1) // page_size)

        pending_deposits = db.execute(
            """SELECT wallet_transactions.id,
                      users.username,
                      wallet_transactions.amount,
                      wallet_transactions.transaction_ref,
                      wallet_transactions.bank,
                      wallet_transactions.note,
                      wallet_transactions.receipt_photo,
                      wallet_transactions.created_at
               FROM wallet_transactions
               JOIN users ON wallet_transactions.user_id = users.id
               WHERE wallet_transactions.status = 'pending'
                 AND wallet_transactions.tx_type = 'deposit'
               ORDER BY wallet_transactions.created_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, deposit_offset),
        ).fetchall()
        pending_withdrawals = db.execute(
            """SELECT wallet_transactions.id,
                      users.username,
                      wallet_transactions.amount,
                      wallet_transactions.bank,
                      wallet_transactions.note,
                      wallet_transactions.created_at
               FROM wallet_transactions
               JOIN users ON wallet_transactions.user_id = users.id
               WHERE wallet_transactions.status = 'pending'
                 AND wallet_transactions.tx_type = 'withdrawal'
               ORDER BY wallet_transactions.created_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, withdrawal_offset),
        ).fetchall()

        # Recent approved transactions across all types, for the 48-hour
        # refund panel. refund_cutoff is computed here (not in the template)
        # so the "is this refundable" check is a single source of truth
        # shared with the server-side enforcement in refund_transaction().
        refund_window_hours = 48
        recent_transactions = db.execute(
            """SELECT wallet_transactions.id,
                      wallet_transactions.tx_type,
                      wallet_transactions.amount,
                      wallet_transactions.status,
                      wallet_transactions.note,
                      wallet_transactions.created_at,
                      users.id AS user_id,
                      users.username
               FROM wallet_transactions
               JOIN users ON wallet_transactions.user_id = users.id
               WHERE wallet_transactions.status = 'approved'
               ORDER BY wallet_transactions.created_at DESC
               LIMIT 30""",
        ).fetchall()
        refund_cutoff_iso = (datetime.datetime.utcnow() - datetime.timedelta(hours=refund_window_hours)).isoformat()

        return render_template(
            "admin_dashboard.html",
            pending_deposits=pending_deposits,
            pending_withdrawals=pending_withdrawals,
            active_bank_count=len(get_active_banks()),
            pending_deposit_count=pending_deposit_count,
            pending_withdrawal_count=pending_withdrawal_count,
            deposit_page=deposit_page,
            withdrawal_page=withdrawal_page,
            deposit_pages=deposit_pages,
            withdrawal_pages=withdrawal_pages,
            page_size=page_size,
            recent_transactions=recent_transactions,
            refund_cutoff_iso=refund_cutoff_iso,
            refund_window_hours=refund_window_hours,
        )
    except Exception as exc:
        print(f"Admin dashboard page error: {exc}")
        flash("Could not load deposit/withdrawal dashboard at this time.", "danger")
        return render_template(
            "admin_dashboard.html",
            pending_deposits=[],
            pending_withdrawals=[],
            active_bank_count=len(get_active_banks()),
            pending_deposit_count=0,
            pending_withdrawal_count=0,
            deposit_page=1,
            withdrawal_page=1,
            deposit_pages=1,
            withdrawal_pages=1,
            page_size=20,
            recent_transactions=[],
            refund_cutoff_iso=(datetime.datetime.utcnow() - datetime.timedelta(hours=48)).isoformat(),
            refund_window_hours=48,
        )


def _claim_pending_transaction(db, tx_id, tx_type, new_status):
    """Atomically move a pending wallet_transactions row to a terminal status.

    Must be called inside a `BEGIN IMMEDIATE` block. The conditional
    `WHERE status = 'pending'` UPDATE means only one caller can ever win the
    transition (rowcount 1) even if two admin clicks race for the same
    transaction - this prevents double-crediting/double-refunding.
    Returns the pre-update row if this call won, else None.
    """
    tx = db.execute(
        "SELECT * FROM wallet_transactions WHERE id = ? AND status = 'pending' AND tx_type = ?",
        (tx_id, tx_type),
    ).fetchone()
    if tx is None:
        return None
    cur = db.execute(
        "UPDATE wallet_transactions SET status = ? WHERE id = ? AND status = 'pending'",
        (new_status, tx_id),
    )
    return tx if cur.rowcount == 1 else None


@app.route("/admin/approve-deposit/<int:tx_id>", methods=["POST"])
@login_required
@admin_required
def approve_deposit(tx_id):
    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = _claim_pending_transaction(db, tx_id, "deposit", "approved")
        if tx:
            _credit_wallet_balance(db, tx["user_id"], tx["amount"])
            add_notification(
                db, tx["user_id"],
                f"Your deposit of {tx['amount']} ETB was approved and credited to your wallet.",
                ntype="deposit",
            )
            flash("Deposit request approved and credited.", "success")
        else:
            flash("Deposit request was already processed or not found.", "warning")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject-deposit/<int:tx_id>", methods=["POST"])
@login_required
@admin_required
def reject_deposit(tx_id):
    db = get_db()
    reason = (request.form.get("reason") or "").strip()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        # Nothing was ever deducted for a deposit request, so rejecting it
        # is just a status change - no balance change needed.
        tx = _claim_pending_transaction(db, tx_id, "deposit", "rejected")
        if tx:
            msg = f"Your deposit of {tx['amount']} ETB was rejected."
            if reason:
                msg += f" Reason: {reason}"
            add_notification(db, tx["user_id"], msg, ntype="deposit")
            flash("Deposit request rejected.", "danger")
        else:
            flash("Deposit request was already processed or not found.", "warning")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/approve-withdrawal/<int:tx_id>", methods=["POST"])
@login_required
@admin_required
def approve_withdrawal(tx_id):
    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = _claim_pending_transaction(db, tx_id, "withdrawal", "approved")
        if tx:
            db.execute(
                "UPDATE users SET balance = balance - ?, wallet_balance = wallet_balance - ? WHERE id = ?",
                (tx["amount"], tx["amount"], tx["user_id"]),
            )
            flash("Withdrawal request approved and funds released.", "success")
        else:
            flash("Withdrawal request was already processed or not found.", "warning")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject-withdrawal/<int:tx_id>", methods=["POST"])
@login_required
@admin_required
def reject_withdrawal(tx_id):
    db = get_db()
    reason = (request.form.get("reason") or "").strip()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = _claim_pending_transaction(db, tx_id, "withdrawal", "rejected")
        if tx:
            db.execute(
                "UPDATE users SET balance = balance + ?, wallet_balance = wallet_balance + ? WHERE id = ?",
                (tx["amount"], tx["amount"], tx["user_id"]),
            )
            msg = f"Your withdrawal request of {tx['amount']} ETB was rejected and the funds were returned to your wallet."
            if reason:
                msg += f" Reason: {reason}"
            add_notification(db, tx["user_id"], msg, ntype="withdrawal")
            flash("Withdrawal request rejected and funds returned.", "danger")
        else:
            flash("Withdrawal request was already processed or not found.", "warning")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/refund-transaction/<int:tx_id>", methods=["POST"])
@login_required
@admin_required
def refund_transaction(tx_id):
    """Refund an approved transaction back to the user's wallet.

    Only allowed within 48 hours of the transaction's created_at timestamp
    (enforced here server-side, not just hidden in the UI, so this can't be
    bypassed by posting directly to the route). Marks the transaction
    'refunded' (a new terminal status distinct from 'approved'/'rejected' so
    revenue totals - which filter on status = 'approved' - automatically
    exclude refunded transactions without any extra bookkeeping). If the
    refunded transaction was a verification or VIP purchase, the user's
    verified badge is revoked as part of the same atomic operation.
    """
    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = db.execute(
            "SELECT * FROM wallet_transactions WHERE id = ? AND status = 'approved'",
            (tx_id,),
        ).fetchone()
        if not tx:
            db.rollback()
            flash("Transaction was already refunded, not approved, or not found.", "warning")
            return redirect(url_for("admin_dashboard"))

        try:
            created = datetime.datetime.fromisoformat(tx["created_at"])
        except Exception:
            created = None
        if created is None or (datetime.datetime.utcnow() - created) > datetime.timedelta(hours=48):
            db.rollback()
            flash("This transaction is older than 48 hours and can no longer be refunded.", "warning")
            return redirect(url_for("admin_dashboard"))

        cur = db.execute(
            "UPDATE wallet_transactions SET status = 'refunded', refunded_at = ?, refunded_by = ? "
            "WHERE id = ? AND status = 'approved'",
            (datetime.datetime.utcnow().isoformat(), session["user_id"], tx_id),
        )
        if not getattr(cur, "rowcount", 0):
            db.rollback()
            flash("Transaction was already processed by another admin action.", "warning")
            return redirect(url_for("admin_dashboard"))

        _credit_wallet_balance(db, tx["user_id"], tx["amount"])

        if tx["tx_type"] in ("verification", "vip"):
            db.execute(
                "UPDATE users SET verification_tier = 'none', verified_until = NULL WHERE id = ?",
                (tx["user_id"],),
            )
            add_notification(
                db, tx["user_id"],
                f"Your payment of {tx['amount']} ETB was refunded to your wallet and your verified badge was removed.",
                ntype="refund",
            )
        else:
            add_notification(
                db, tx["user_id"],
                f"Your payment of {tx['amount']} ETB was refunded to your wallet.",
                ntype="refund",
            )

        flash(f"Refunded {tx['amount']} ETB to the user's wallet.", "success")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/revenue/withdraw", methods=["POST"])
@login_required
@admin_required
def admin_revenue_withdraw():
    """Pay out platform revenue to a recipient username or wallet ID.

    This does not touch any individual user's wallet balance - it only
    records a withdrawal against the platform's own revenue ledger. If the
    recipient resolves to a real user account, that user's wallet is
    credited (e.g. paying a partner or refunding the platform's own cut
    somewhere); otherwise it's recorded as an external payout (e.g. a bank
    transfer done manually outside the app) for bookkeeping purposes only.
    """
    db = get_db()
    amount_raw = (request.form.get("amount") or "").strip()
    recipient = (request.form.get("recipient") or "").strip()
    note = (request.form.get("note") or "").strip()

    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Enter a valid withdrawal amount.", "warning")
        return redirect(url_for("admin_revenue"))
    if amount <= 0:
        flash("Withdrawal amount must be greater than zero.", "warning")
        return redirect(url_for("admin_revenue"))
    if not recipient:
        flash("Enter a recipient username or wallet ID.", "warning")
        return redirect(url_for("admin_revenue"))

    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        available = _admin_revenue_available_balance(db)
        if amount > available:
            db.rollback()
            flash(f"Amount exceeds available revenue balance ({available:.2f} ETB).", "warning")
            return redirect(url_for("admin_revenue"))

        recipient_user = db.execute(
            "SELECT id, username FROM users WHERE username = ? OR wallet_id = ?",
            (recipient, recipient),
        ).fetchone()

        db.execute(
            "INSERT INTO admin_revenue_withdrawals (amount, recipient_label, recipient_user_id, admin_id, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (amount, recipient, recipient_user["id"] if recipient_user else None,
             session["user_id"], note or None, datetime.datetime.utcnow().isoformat()),
        )

        if recipient_user:
            _credit_wallet_balance(db, recipient_user["id"], amount)
            add_notification(
                db, recipient_user["id"],
                f"You received a payout of {amount} ETB from platform revenue.",
                ntype="payout",
            )
            flash(f"Paid out {amount} ETB to @{recipient_user['username']}'s wallet.", "success")
        else:
            flash(f"Recorded a payout of {amount} ETB to '{recipient}'. No matching in-app wallet was found, so credit it manually if this was an external transfer.", "warning")

        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_revenue"))
    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = db.execute("SELECT * FROM wallet_transactions WHERE id = ?", (tx_id,)).fetchone()
        if not tx or tx["status"] != "pending":
            db.rollback()
            return redirect(url_for("admin_panel"))

        if tx["tx_type"] == "deposit":
            claimed = _claim_pending_transaction(db, tx_id, "deposit", "approved")
            if claimed:
                _credit_wallet_balance(db, claimed["user_id"], claimed["amount"])
        elif tx["tx_type"] == "withdrawal":
            # ገንዘቡ ቀድሞ በ /wallet/withdraw ላይ ተይዞ (reserved) ስለሆነ፣ እዚህ ላይ ተጨማሪ
            # ቅናሽ አናደርግም - ደረጃውን ወደ 'approved' ብቻ እንቀይራለን።
            _claim_pending_transaction(db, tx_id, "withdrawal", "approved")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_panel"))


@app.route("/admin/wallet/<int:tx_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_wallet_tx(tx_id):
    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        tx = db.execute("SELECT * FROM wallet_transactions WHERE id = ?", (tx_id,)).fetchone()
        if not tx or tx["status"] != "pending":
            db.rollback()
            return redirect(url_for("admin_panel"))

        if tx["tx_type"] == "withdrawal":
            # ገንዘቡ ቀድሞ ተይዞ ስለነበር፣ ውድቅ ሲደረግ መልሶ ወደ ዋሌት ይመለሳል
            claimed = _claim_pending_transaction(db, tx_id, "withdrawal", "rejected")
            if claimed:
                db.execute(
                    "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                    (claimed["amount"], claimed["user_id"]),
                )
        else:
            _claim_pending_transaction(db, tx_id, "deposit", "rejected")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_panel"))


@app.route("/admin/payment/<int:payment_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_payment(payment_id):
    db = get_db()
    payment = db.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    if payment:
        days = 30 if payment["plan"] == "monthly" else 365
        paid_until = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        db.execute(
            "UPDATE users SET plan = ?, paid_until = ? WHERE id = ?",
            (payment["plan"], paid_until.isoformat(), payment["user_id"]),
        )
        db.execute(
            "UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,)
        )
        db.commit()
    return redirect(url_for("admin_panel"))


@app.route("/admin/report/<int:report_id>/resolve", methods=["POST"])
@login_required
@admin_required
def resolve_report(report_id):
    db = get_db()
    db.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
    db.commit()
    return redirect(url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id):
    """Permanent Ban - instantly and permanently blocks the account."""
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target and not target["is_admin"]:
        db.execute(
            "UPDATE users SET is_banned = true, banned_until = NULL, ban_reason = ? WHERE id = ?",
            (request.form.get("reason") or "Permanently banned by admin.", user_id),
        )
        db.commit()
    return redirect(request.referrer or url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/unban", methods=["POST"])
@login_required
@admin_required
def unban_user(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET is_banned = false, banned_until = NULL, ban_reason = NULL WHERE id = ?",
        (user_id,),
    )
    db.commit()
    return redirect(request.referrer or url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/tempban", methods=["POST"])
@login_required
@admin_required
def temp_ban_user(user_id):
    """Temporary Ban - suspends the account for a custom number of days."""
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    try:
        days = max(1, int(request.form.get("days", 3)))
    except (TypeError, ValueError):
        days = 3
    if target and not target["is_admin"]:
        until = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        reason = request.form.get("reason") or f"Temporarily suspended for {days} day(s)."
        db.execute(
            "UPDATE users SET banned_until = ?, ban_reason = ? WHERE id = ?",
            (until.isoformat(), reason, user_id),
        )
        add_notification(
            db, user_id,
            f"Your account has been suspended for {days} day(s). Reason: {reason}",
            ntype="ban",
        )
        db.commit()
    return redirect(request.referrer or url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/warn", methods=["POST"])
@login_required
@admin_required
def warn_user(user_id):
    """Issue Warning - sends a direct pop-up warning to the user's notifications."""
    db = get_db()
    target = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    message = (request.form.get("message") or "").strip()
    if target and message:
        add_notification(db, user_id, message, ntype="warning")
        db.commit()
    return redirect(request.referrer or url_for("admin_users"))


@app.route("/admin/user/<int:user_id>/generate-password", methods=["POST"])
@login_required
@admin_required
def generate_temp_password(user_id):
    """Account Recovery - generates a secure temporary password and displays
    it once on screen so the admin can share it with the user."""
    db = get_db()
    target = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if target:
        temp_password = secrets.token_urlsafe(9)
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(temp_password), user_id),
        )
        add_notification(
            db, user_id,
            "An admin generated a new temporary password for your account. "
            "Please log in and change it as soon as possible.",
            ntype="info",
        )
        db.commit()
        session["_generated_password_for"] = target["username"]
        session["_generated_password_value"] = temp_password
    return redirect(request.referrer or url_for("admin_users"))


# ---------------------------------------------------------------------------
# Admin - User Directory Hub
# ---------------------------------------------------------------------------
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    try:
        db = get_db()
        q = request.args.get("q", "").strip()
        page = max(1, request.args.get("page", 1, type=int))
        per_page = 20
        offset = (page - 1) * per_page

        where = ""
        params = []
        if q:
            where = "WHERE username LIKE ? OR phone LIKE ? OR full_name LIKE ?"
            like = f"%{q}%"
            params = [like, like, like]

        total = db.execute(f"SELECT COUNT(*) c FROM users {where}", params).fetchone()["c"]
        users = db.execute(
            f"""SELECT id, username, full_name, phone,
                       COALESCE(balance, wallet_balance, 0) AS balance,
                       wallet_id,
                       created_at,
                       is_banned, banned_until, ban_reason, verification_tier, is_admin
                FROM users {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()

        generated_password = None
        generated_for = session.pop("_generated_password_for", None)
        if generated_for:
            generated_password = session.pop("_generated_password_value", None)

        return render_template(
            "admin_users.html",
            users=users, q=q, page=page, per_page=per_page, total=total,
            is_currently_banned=is_currently_banned,
            generated_for=generated_for, generated_password=generated_password,
        )
    except Exception as exc:
        print(f"Admin users page error: {exc}")
        flash("Could not load users list at this time.")
        return render_template(
            "admin_users.html",
            users=[], q="", page=1, per_page=20, total=0,
            is_currently_banned=is_currently_banned,
            generated_for=None, generated_password=None,
        )


# ---------------------------------------------------------------------------
# Admin - Verification & Badge System
# ---------------------------------------------------------------------------
@app.route("/admin/verify")
@app.route("/admin/verification")
@login_required
@admin_required
def admin_verify():
    try:
        db = get_db()
        q = request.args.get("q", "").strip()
        results = []
        if q:
            results = db.execute(
                """SELECT id, username, full_name, verification_tier, verified_until
                   FROM users WHERE username LIKE ? OR full_name LIKE ?
                   ORDER BY username LIMIT 25""",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        verified_users = db.execute(
            """SELECT id, username, full_name, verification_tier, verified_until FROM users
               WHERE verification_tier IN ('blue', 'gold') ORDER BY verified_until DESC LIMIT 50"""
        ).fetchall()
        return render_template(
            "admin_verify.html", q=q, results=results, verified_users=verified_users,
            is_currently_verified=is_currently_verified,
        )
    except Exception as exc:
        print(f"Admin verify page error: {exc}")
        flash("Could not load verification dashboard at this time.")
        return render_template(
            "admin_verify.html", q="", results=[], verified_users=[],
            is_currently_verified=is_currently_verified,
        )


@app.route("/admin/user/<int:user_id>/grant-verified", methods=["POST"])
@login_required
@admin_required
def grant_verified(user_id):
    db = get_db()
    target = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    try:
        days = max(1, int(request.form.get("days", 30)))
    except (TypeError, ValueError):
        days = 30
    tier = request.form.get("tier", "blue")
    if tier not in ("blue", "gold"):
        tier = "blue"
    if target:
        until = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        set_verification_tier(db, user_id, tier, until)
        add_notification(
            db, user_id,
            f"Congratulations! An admin has granted your account a {tier.capitalize()} badge for {days} day(s).",
            ntype="info",
        )
        db.commit()
    return redirect(request.referrer or url_for("admin_verify"))


@app.route("/admin/user/<int:user_id>/revoke-verified", methods=["POST"])
@login_required
@admin_required
def revoke_verified(user_id):
    db = get_db()
    set_verification_tier(db, user_id, "none", datetime.datetime.utcnow())
    db.commit()
    return redirect(request.referrer or url_for("admin_verify"))


# ---------------------------------------------------------------------------
# Admin - Announcements & Policy Hub
# ---------------------------------------------------------------------------
@app.route("/admin/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def admin_announcements():
    db = get_db()

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "add-word":
            word = (request.form.get("word") or "").strip()
            if word:
                db.execute("INSERT INTO restricted_words (word, created_at) VALUES (?, ?) ON CONFLICT (word) DO NOTHING", (word, datetime.datetime.utcnow().isoformat()))
                db.commit()
            return redirect(url_for("admin_announcements"))
        if action == "delete-word":
            word_id = request.form.get("word_id", type=int)
            if word_id:
                db.execute("DELETE FROM restricted_words WHERE id = ?", (word_id,))
                db.commit()
            return redirect(url_for("admin_announcements"))

        title = (request.form.get("title") or "").strip()
        content = request.form.get("content", "")
        is_pinned = 1 if request.form.get("is_pinned") == "on" else 0
        image = save_photo(request.files.get("image"))

        if title and content:
            db.execute(
                """INSERT INTO announcements (title, content, image_url, is_pinned, view_count, created_at)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (title, content, image, is_pinned, datetime.datetime.utcnow().isoformat()),
            )
            db.commit()
            for user in db.execute("SELECT id FROM users").fetchall():
                add_notification(db, user["id"], f"New announcement: {title}", ntype="info")
            db.commit()
        return redirect(url_for("admin_announcements"))

    announcements = db.execute(
        "SELECT * FROM announcements ORDER BY is_pinned DESC, created_at DESC"
    ).fetchall()
    restricted_words = db.execute(
        "SELECT * FROM restricted_words ORDER BY word"
    ).fetchall()
    summary = db.execute(
        "SELECT SUM(view_count) total_views, COUNT(*) c FROM announcements"
    ).fetchone()
    return render_template(
        "admin_announcements.html",
        announcements=announcements,
        restricted_words=restricted_words,
        total_views=summary["total_views"] or 0,
        announcement_count=summary["c"] or 0,
    )


@app.route("/admin/announcement/<int:announcement_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_announcement(announcement_id):
    db = get_db()
    db.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
    db.commit()
    return redirect(url_for("admin_announcements"))


@app.route("/announcement/<int:announcement_id>/dismiss", methods=["POST"])
@login_required
def dismiss_announcement(announcement_id):
    dismissed = session.get("dismissed_announcements", [])
    if announcement_id not in dismissed:
        dismissed.append(announcement_id)
        session["dismissed_announcements"] = dismissed
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Admin - Content Moderation Center
# ---------------------------------------------------------------------------
@app.route("/admin/moderation")
@login_required
@admin_required
def admin_moderation():
    db = get_db()
    reported = db.execute(
        """SELECT reports.id as report_id, reports.reason, reports.target_type,
                  reports.target_id, reports.created_at as reported_at,
                  reporter.username as reporter,
                  posts.id as post_id, posts.content as post_content,
                  posts.photo as post_photo,
                  author.username as post_author, author.id as author_id
           FROM reports
           JOIN users reporter ON reports.reporter_id = reporter.id
           LEFT JOIN posts ON reports.target_type = 'post' AND reports.target_id = posts.id
           LEFT JOIN users author ON posts.user_id = author.id
           WHERE reports.status = 'pending'
           ORDER BY reports.created_at DESC"""
    ).fetchall()
    return render_template("admin_moderation.html", reported=reported)


@app.route("/admin/report/<int:report_id>/dismiss", methods=["POST"])
@login_required
@admin_required
def dismiss_report(report_id):
    db = get_db()
    db.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
    db.commit()
    return redirect(request.referrer or url_for("admin_moderation"))


@app.route("/admin/report/<int:report_id>/delete-post", methods=["POST"])
@login_required
@admin_required
def delete_reported_post(report_id):
    db = get_db()
    report = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if report and report["target_type"] == "post":
        post = db.execute("SELECT id, user_id FROM posts WHERE id = ?", (report["target_id"],)).fetchone()
        if post:
            db.execute("DELETE FROM posts WHERE id = ?", (post["id"],))
            add_strike(db, post["user_id"], reason="post_deleted_for_policy_violation")
    db.execute("UPDATE reports SET status = 'resolved' WHERE id = ?", (report_id,))
    db.commit()
    return redirect(request.referrer or url_for("admin_moderation"))


# ---------------------------------------------------------------------------
# Admin - Platform Revenue Analytics
# ---------------------------------------------------------------------------
def _admin_revenue_wallet_gross(db):
    """Gross revenue that counts toward the Admin Revenue Wallet: Blue
    Tick/VIP badge sales plus the platform's cut of gifts. Deliberately
    narrower than the page's overall `total_revenue` figure (which also
    includes marketplace listings and subscriptions) - this wallet tracks
    money the platform actually collected as fees, which is what can
    legitimately be withdrawn out."""
    verification_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'verification' AND status = 'approved'"
    ).fetchone()["total"]
    vip_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'vip' AND status = 'approved'"
    ).fetchone()["total"]
    gift_earnings = db.execute(
        "SELECT COALESCE(SUM(platform_cut), 0) total FROM gifts"
    ).fetchone()["total"]
    return float(verification_revenue) + float(vip_revenue) + float(gift_earnings)


def _admin_revenue_withdrawn_total(db):
    return float(db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM admin_revenue_withdrawals"
    ).fetchone()["total"])


def _admin_revenue_available_balance(db):
    """Available-to-withdraw balance = gross badge/fee revenue collected so
    far, minus everything already paid out. Computed fresh every time
    instead of stored as a mutable counter, so it can't drift out of sync."""
    return _admin_revenue_wallet_gross(db) - _admin_revenue_withdrawn_total(db)


@app.route("/admin/revenue")
@login_required
@admin_required
def admin_revenue():
    db = get_db()
    subscription_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM payments WHERE status = 'approved'"
    ).fetchone()["total"]
    marketplace_revenue = db.execute(
        "SELECT COALESCE(SUM(price), 0) total FROM products"
    ).fetchone()["total"]
    verification_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'verification' AND status = 'approved'"
    ).fetchone()["total"]
    vip_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'vip' AND status = 'approved'"
    ).fetchone()["total"]
    gift_earnings = db.execute(
        "SELECT COALESCE(SUM(platform_cut), 0) total FROM gifts"
    ).fetchone()["total"]
    challenge_prize_pool_volume = db.execute(
        "SELECT COALESCE(SUM(prize_pool), 0) total FROM challenge_pools"
    ).fetchone()["total"]
    deposit_volume = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'deposit' AND status = 'approved'"
    ).fetchone()["total"]
    withdrawal_volume = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM wallet_transactions WHERE tx_type = 'withdrawal' AND status = 'approved'"
    ).fetchone()["total"]

    premium_services_revenue = verification_revenue + vip_revenue
    wallet_activity_revenue = gift_earnings
    total_revenue = subscription_revenue + marketplace_revenue + premium_services_revenue + wallet_activity_revenue

    admin_wallet_gross = _admin_revenue_wallet_gross(db)
    admin_wallet_withdrawn = _admin_revenue_withdrawn_total(db)
    admin_wallet_available = admin_wallet_gross - admin_wallet_withdrawn
    recent_revenue_withdrawals = db.execute(
        "SELECT w.*, u.username AS admin_username FROM admin_revenue_withdrawals w "
        "LEFT JOIN users u ON u.id = w.admin_id ORDER BY w.created_at DESC LIMIT 20"
    ).fetchall()

    return render_template(
        "admin_revenue.html",
        subscription_revenue=subscription_revenue,
        marketplace_revenue=marketplace_revenue,
        verification_revenue=verification_revenue,
        vip_revenue=vip_revenue,
        premium_services_revenue=premium_services_revenue,
        gift_earnings=gift_earnings,
        wallet_activity_revenue=wallet_activity_revenue,
        deposit_volume=deposit_volume,
        withdrawal_volume=withdrawal_volume,
        challenge_prize_pool_volume=challenge_prize_pool_volume,
        total_revenue=total_revenue,
        admin_wallet_gross=admin_wallet_gross,
        admin_wallet_withdrawn=admin_wallet_withdrawn,
        admin_wallet_available=admin_wallet_available,
        recent_revenue_withdrawals=recent_revenue_withdrawals,
    )


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    safe_name = str(filename).replace("\\", "/").lstrip("/")
    if safe_name.startswith("..") or "/../" in safe_name:
        abort(404)

    search_directories = [app.config["UPLOAD_FOLDER"]]
    legacy_upload_dir = os.path.join(BASE_DIR, "uploads")
    if legacy_upload_dir not in search_directories:
        search_directories.append(legacy_upload_dir)
    data_upload_dir = os.path.join(DATA_DIR, "uploads")
    if data_upload_dir not in search_directories:
        search_directories.append(data_upload_dir)
    static_upload_dir = os.path.join(BASE_DIR, "static", "uploads")
    if static_upload_dir not in search_directories:
        search_directories.append(static_upload_dir)

    for directory in search_directories:
        file_path = os.path.join(directory, safe_name)
        if os.path.isfile(file_path):
            return send_from_directory(directory, safe_name)

    print(f"Upload not found: {safe_name}. Searched: {search_directories}")
    abort(404)


if __name__ == "__main__":
    with app.app_context():
        ensure_database_schema()
    app.run(debug=True, host="0.0.0.0", port=5000)
