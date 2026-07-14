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
from functools import wraps
from email.message import EmailMessage
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, request, session, redirect, url_for,
    render_template, g, flash, abort, send_from_directory
)

from translations import get_translator, DEFAULT_LANG, TRANSLATIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DATA_DIR points at a persistent volume/disk in production (e.g. Render Disk
# mounted at /var/data, Railway Volume mounted at /data). Falls back to
# BASE_DIR for local development, where the source folder is fine to use.
# See render.yaml / railway.json for how DATA_DIR is set per platform.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE = os.path.join(DATA_DIR, "altajobs.db")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
CV_PHOTO_FOLDER = os.path.join(UPLOAD_FOLDER, "cv_photos")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

FREE_TRIAL_DAYS = 30
MONTHLY_PRICE = 1500
YEARLY_PRICE = 7000

# --- Wallet / Verification / Gifts settings -------------------------------
TELEBIRR_WALLET_NUMBER = "0960602675"     # ገንዘብ የሚላክበት ቴሌብር ቁጥር
VERIFICATION_MONTHLY_PRICE = 300          # የ Blue Tick ወርሃዊ ዋጋ (ብር) - ከዋሌት ሲቀነስ
CHANNEL_VERIFICATION_MONTHLY_PRICE = 500  # የ channel/group Blue Tick ወርሃዊ ዋጋ (ብር)
CHANNEL_VERIFICATION_WARNING_DAYS = 7      # ማብቂያው ከመድረሱ ስንት ቀን በፊት ማስጠንቀቂያ እንደሚታይ
VIP_MONTHLY_PRICE = 800                   # የ VIP ወርሃዊ ዋጋ (ብር) - ከዋሌት ሲቀነስ
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
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15MB (photo/receipt/CV-photo uploads only, no video)
app.config["PREFERRED_URL_SCHEME"] = os.environ.get("PREFERRED_URL_SCHEME", "https")
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@altajobs.app")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CV_PHOTO_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            user_type TEXT NOT NULL DEFAULT 'worker',  -- 'worker' or 'employer'
            phone TEXT,
            skills TEXT,
            experience TEXT,
            bio TEXT,
            avatar TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            plan TEXT DEFAULT NULL,          -- 'monthly' / 'yearly' / NULL
            paid_until TEXT DEFAULT NULL,
            email_verified INTEGER DEFAULT 0,
            email_verification_code TEXT DEFAULT NULL,
            password_reset_code TEXT DEFAULT NULL,
            password_reset_expires TEXT DEFAULT NULL,
            email_verified_at TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT,
            photo TEXT,
            post_type TEXT DEFAULT 'general',  -- 'general' / 'job' / 'skill'
            share_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(post_id, user_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            employer_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(employer_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,   -- 'post' or 'user'
            target_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(reporter_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS saved_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, post_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            applicant_id INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'submitted',   -- submitted / reviewed
            created_at TEXT NOT NULL,
            UNIQUE(post_id, applicant_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(applicant_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            initiated_by INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',     -- pending / accepted / blocked
            created_at TEXT NOT NULL,
            UNIQUE(user1_id, user2_id),
            FOREIGN KEY(user1_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(user2_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            seen_at TEXT,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS post_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(post_id, user_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,          -- 'checkin' / 'profile_completion' / 'share_job'
            amount INTEGER NOT NULL,
            streak_day INTEGER,          -- only set for kind='checkin'
            post_id INTEGER,             -- only set for kind='share_job' (1 reward per post)
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            channel_type TEXT NOT NULL DEFAULT 'group',  -- 'group' or 'channel'
            creator_id INTEGER NOT NULL,
            avatar TEXT,
            is_verified INTEGER DEFAULT 0,
            verified_until TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(creator_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',  -- 'owner' or 'member'
            joined_at TEXT NOT NULL,
            UNIQUE(channel_id, user_id),
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT,
            photo TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS channel_message_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(message_id, user_id, emoji),
            FOREIGN KEY(message_id) REFERENCES channel_messages(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            followed_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(follower_id, followed_id),
            FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(followed_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(referrer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(referred_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challenge_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challenge_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier_amount INTEGER NOT NULL,
            month TEXT NOT NULL,               -- 'YYYY-MM'
            status TEXT DEFAULT 'open',        -- open / judging / closed
            platform_fee_percent INTEGER DEFAULT 10,
            prize_pool INTEGER DEFAULT 0,
            winner_entry_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(tier_amount, month)
        );

        CREATE TABLE IF NOT EXISTS challenge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount_paid INTEGER NOT NULL,
            pitch_text TEXT NOT NULL,
            ai_score REAL,
            admin_score REAL,
            engagement_bonus REAL DEFAULT 0,
            final_score REAL,
            status TEXT DEFAULT 'submitted',   -- submitted / winner / not_selected
            created_at TEXT NOT NULL,
            UNIQUE(pool_id, user_id),
            FOREIGN KEY(pool_id) REFERENCES challenge_pools(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS winner_trust (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            transaction_ref TEXT NOT NULL,
            status TEXT DEFAULT 'pending', -- pending / approved / rejected
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL,          -- 'deposit' or 'withdrawal'
            amount INTEGER NOT NULL,
            transaction_ref TEXT,
            bank TEXT DEFAULT NULL,
            note TEXT DEFAULT NULL,
            receipt_photo TEXT DEFAULT NULL,
            account_number TEXT DEFAULT NULL,
            account_name TEXT DEFAULT NULL,
            status TEXT DEFAULT 'pending',  -- pending / approved / rejected
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            account_holder_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cv_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            full_name TEXT,
            target_role TEXT,
            summary TEXT,
            experience TEXT,
            achievements TEXT,      -- newline-joined list
            skills TEXT,            -- comma-joined list
            photo TEXT DEFAULT NULL,
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

        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()
    migrate_db()


def migrate_db():
    """አስቀድሞ ለተፈጠረ altajobs.db አዲስ columns በደህና ይጨምራል (idempotent)."""
    db = sqlite3.connect(DATABASE)
    existing_cols = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    new_columns = {
        "wallet_balance": "INTEGER DEFAULT 0",
        "is_verified": "INTEGER DEFAULT 0",
        "verified_until": "TEXT DEFAULT NULL",
        "is_vip": "INTEGER DEFAULT 0",
        "vip_until": "TEXT DEFAULT NULL",
        "is_banned": "INTEGER DEFAULT 0",
        "referral_code": "TEXT DEFAULT NULL",
        "alta_tokens": "INTEGER DEFAULT 0",
        "last_checkin": "TEXT DEFAULT NULL",
        "current_streak": "INTEGER DEFAULT 0",
    }
    for col, coltype in new_columns.items():
        if col not in existing_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
    db.commit()

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
    }
    for col, coltype in post_new_columns.items():
        if col not in post_cols:
            db.execute(f"ALTER TABLE posts ADD COLUMN {col} {coltype}")
    db.commit()

    # token_transactions table: add post_id (ties share_job rewards to a
    # specific post so the same post can't be repeatedly rewarded)
    tx_cols = {row[1] for row in db.execute("PRAGMA table_info(token_transactions)")}
    if "post_id" not in tx_cols:
        db.execute("ALTER TABLE token_transactions ADD COLUMN post_id INTEGER DEFAULT NULL")
    db.commit()

    db.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    db.commit()

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
        "bank": "TEXT DEFAULT NULL",
        "note": "TEXT DEFAULT NULL",
        "receipt_photo": "TEXT DEFAULT NULL",
        "account_number": "TEXT DEFAULT NULL",
        "account_name": "TEXT DEFAULT NULL",
    }
    for col, coltype in wallet_new_columns.items():
        if col not in wallet_cols:
            db.execute(f"ALTER TABLE wallet_transactions ADD COLUMN {col} {coltype}")
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
    }.items():
        if col not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coltype}")
    db.commit()

    try:
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_ci ON users (lower(username))")
        db.commit()
    except Exception as exc:
        print(f"Warning: could not create case-insensitive username index: {exc}")
    db.close()


def ensure_database_schema():
    """Ensure the SQLite schema exists and is upgraded safely on startup."""
    try:
        if hasattr(app, "extensions") and "sqlalchemy" in app.extensions:
            db = app.extensions["sqlalchemy"]
            db.create_all()
        else:
            init_db()
    except Exception as exc:
        print(f"Warning: database schema initialization failed: {exc}")
        try:
            migrate_db()
        except Exception as migrate_exc:
            print(f"Warning: database schema migration fallback failed: {migrate_exc}")


with app.app_context():
    ensure_database_schema()


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
        db = get_db()
        row = db.execute("SELECT is_banned FROM users WHERE id = ?", (uid,)).fetchone()
        if row and row["is_banned"]:
            session.pop("user_id", None)
            flash("account_banned")


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
    if user:
        db = get_db()
        row = db.execute(
            """SELECT COUNT(*) c FROM messages
               JOIN conversations ON messages.conversation_id = conversations.id
               WHERE conversations.status = 'accepted'
                 AND messages.sender_id != ?
                 AND messages.seen_at IS NULL
                 AND (conversations.user1_id = ? OR conversations.user2_id = ?)""",
            (user["id"], user["id"], user["id"]),
        ).fetchone()
        unread_count = row["c"]
    return {
        "t": get_translator(lang),
        "current_lang": lang,
        "current_user": user,
        "unread_message_count": unread_count,
        "trial_days_left": trial_days_left(user) if user else 0,
        "suggested_channels": db.execute(
            """SELECT channels.*, (SELECT COUNT(*) FROM channel_members WHERE channel_id = channels.id) as member_count
               FROM channels ORDER BY channels.created_at DESC LIMIT 5"""
        ).fetchall() if user else [],
    }


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


# Endpoints a signed-in-but-not-yet-verified user is still allowed to reach.
# Keep this list minimal - anything not in it will bounce an unverified
# user straight to the verification page, even if they type the URL
# directly instead of following a redirect.
_VERIFICATION_EXEMPT_ENDPOINTS = {"verify_email_page", "resend_verification"}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))

        db = get_db()
        user = db.execute(
            "SELECT is_banned, email_verified, email_verification_code FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        if not user:
            # session points at an account that no longer exists
            session.pop("user_id", None)
            return redirect(url_for("login"))

        if user["is_banned"]:
            session.pop("user_id", None)
            flash("account_banned")
            return redirect(url_for("login"))

        # STRICT OTP ENFORCEMENT: a session cookie alone is no longer enough
        # to reach the rest of the app. Previously, registration set
        # session["user_id"] immediately and only the login *form* checked
        # email_verified - so a newly-registered, unverified user could just
        # type "/" (or any other URL) in the address bar and skip the OTP
        # step entirely. Checking it here, on every request, closes that.
        if (
            user["email_verification_code"]
            and not user["email_verified"]
            and f.__name__ not in _VERIFICATION_EXEMPT_ENDPOINTS
        ):
            flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_required"])
            return redirect(url_for("verify_email_page"))

        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not user["is_admin"]:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def subscription_active(user):
    """ተጠቃሚው ነጻ ጊዜ ውስጥ ነው ወይስ ከፍሏል የሚለውን ይመልሳል"""
    if not user:
        return False
    created = datetime.datetime.fromisoformat(user["created_at"])
    trial_end = created + datetime.timedelta(days=FREE_TRIAL_DAYS)
    if datetime.datetime.utcnow() <= trial_end:
        return True
    if user["paid_until"]:
        paid_until = datetime.datetime.fromisoformat(user["paid_until"])
        if datetime.datetime.utcnow() <= paid_until:
            return True
    return False


def trial_days_left(user):
    created = datetime.datetime.fromisoformat(user["created_at"])
    trial_end = created + datetime.timedelta(days=FREE_TRIAL_DAYS)
    delta = trial_end - datetime.datetime.utcnow()
    return max(delta.days, 0)


def subscription_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user and user["is_admin"]:
            return f(*args, **kwargs)
        if not subscription_active(user):
            return redirect(url_for("subscribe"))
        return f(*args, **kwargs)
    return wrapper


DAILY_POST_LIMIT = 1   # standard posts per day once the free trial has ended


def _daily_post_count(db, user_id, kind="standard"):
    """kind is always 'standard' now that Reels has been removed; the
    parameter is kept so any remaining callers don't need to change."""
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
            if user["is_admin"] or subscription_active(user):
                return f(*args, **kwargs)

            db = get_db()
            count = _daily_post_count(db, user["id"])
            if count >= DAILY_POST_LIMIT:
                flash("daily_post_limit_reached")
                return redirect(url_for("feed"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def is_currently_verified(user):
    """ተጠቃሚው አሁን ላይ Blue Tick አለው ወይስ የለውም የሚለውን ይመልሳል"""
    if not user or not user["is_verified"]:
        return False
    if not user["verified_until"]:
        return False
    return datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(user["verified_until"])


def is_currently_vip(user):
    """ተጠቃሚው አሁን ላይ VIP ነው ወይስ አይደለም የሚለውን ይመልሳል"""
    if not user or not user["is_vip"]:
        return False
    if not user["vip_until"]:
        return False
    return datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(user["vip_until"])


def channel_is_verified(channel):
    """ቻናሉ/ቡድኑ አሁን ላይ Blue Tick አለው ወይስ የለውም የሚለውን ይመልሳል።
    ይህ በራሱ ጊዜው ካለፈ በኋላ Blue Tick ን በራስሰር 'ያነሳል' - cron ሳያስፈልግ፣
    ልክ እንደ ተጠቃሚ verification ተመሳሳይ በሆነ መንገድ በእያንዳንዱ ጭነት ላይ ይሰላል።"""
    if not channel or not channel["is_verified"] or not channel["verified_until"]:
        return False
    return datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(channel["verified_until"])


def channel_verification_days_left(channel):
    if not channel or not channel["verified_until"]:
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


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


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
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], unique))
    return unique


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
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return url_for("uploaded_file", filename=value)


def get_setting(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


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
    return db.execute(
        "SELECT * FROM bank_accounts WHERE is_active = 1 ORDER BY bank_name"
    ).fetchall()


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
    except sqlite3.IntegrityError:
        return False  # already viewed by this user before - not counted again


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.datetime.utcnow().isoformat()


def _generate_code(length=6):
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def _normalize_username(username):
    return (username or "").strip().casefold()


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
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as server:
            if app.config["MAIL_USE_TLS"]:
                server.starttls()
            if app.config["MAIL_USERNAME"]:
                server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return False


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        normalized_username = _normalize_username(username)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        user_type = request.form.get("user_type", "worker")
        phone = request.form.get("phone", "").strip()

        if not email:
            flash(get_translator(session.get("lang", DEFAULT_LANG))["email_required"])
            return redirect(url_for("register"))

        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute(
                "SELECT id FROM users WHERE lower(username) = ?", (normalized_username,)
            ).fetchone()
            if existing:
                db.rollback()
                flash("This username is already taken. Please choose another one.")
                return redirect(url_for("register"))

            verification_code = _generate_code()
            db.execute(
                """INSERT INTO users
                   (username, email, password_hash, full_name, user_type, phone, created_at, referral_code,
                    email_verified, email_verification_code)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    username, email, generate_password_hash(password),
                    full_name, user_type, phone,
                    _now_iso(),
                    f"{username[:6].upper()}{secrets.token_hex(3).upper()}",
                    generate_password_hash(verification_code),
                ),
            )
            db.commit()
            new_user = db.execute(
                "SELECT id, username, email FROM users WHERE lower(username) = ?", (normalized_username,)
            ).fetchone()
            session["user_id"] = new_user["id"]

            try:
                email_sent = _send_email(
                    "Verify your AltaJobs account",
                    new_user["email"],
                    f"Hello {new_user['username']},\n\nYour verification code is: {verification_code}\n\nUse it on the Verify Email page to complete signup.",
                )
            except Exception as exc:
                print(f"[auth] verification email failed: {exc}")
                email_sent = False

            if not email_sent:
                print(f"[auth] verification email could not be delivered for {new_user['email']}")
                flash("Your account was created, but the verification email could not be sent right now. You can verify later.")
            else:
                flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_sent"])

            # if the person signed up through a referral link, credit the referrer
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
                    except sqlite3.IntegrityError:
                        pass

            return redirect(url_for("verify_email_page"))
        except sqlite3.IntegrityError as exc:
            db.rollback()
            print(f"[auth] registration failed due to integrity error: {exc}")
            flash("This username is already taken. Please choose another one.")
            return redirect(url_for("register"))

    ref_code = request.args.get("ref", "")
    return render_template("register.html", ref_code=ref_code)


@app.route("/verify-email", methods=["GET", "POST"])
@login_required
def verify_email_page():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    if user["email_verified"] or not user["email_verification_code"]:
        return redirect(url_for("feed"))
    if request.method == "POST":
        code = request.form.get("verification_code", "").strip()
        if not code:
            flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_required"])
            return redirect(url_for("verify_email_page"))
        if user and user["email_verification_code"] and check_password_hash(user["email_verification_code"], code):
            db = get_db()
            db.execute(
                "UPDATE users SET email_verified = 1, email_verification_code = NULL, email_verified_at = ? WHERE id = ?",
                (_now_iso(), user["id"]),
            )
            db.commit()
            flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_success"])
            return redirect(url_for("feed"))
        flash(get_translator(session.get("lang", DEFAULT_LANG))["invalid_verification_code"])
        return redirect(url_for("verify_email_page"))

    return render_template("verify_email.html", user=user)


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    user = get_current_user()
    if not user or not user["email"]:
        flash(get_translator(session.get("lang", DEFAULT_LANG))["email_required"])
        return redirect(url_for("verify_email_page"))
    code = _generate_code()
    db = get_db()
    db.execute(
        "UPDATE users SET email_verification_code = ? WHERE id = ?",
        (generate_password_hash(code), user["id"]),
    )
    db.commit()
    try:
        email_sent = _send_email(
            "Verify your AltaJobs account",
            user["email"],
            f"Your new verification code is: {code}",
        )
    except Exception as exc:
        print(f"[auth] resend verification email failed: {exc}")
        email_sent = False

    if not email_sent:
        flash("We could not send the verification email right now, but your code is still available for later verification.")
    else:
        flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_sent"])
    return redirect(url_for("verify_email_page"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash(get_translator(session.get("lang", DEFAULT_LANG))["email_required"])
            return redirect(url_for("forgot_password"))
        db = get_db()
        user = db.execute("SELECT id, username, email FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            code = _generate_code()
            db.execute(
                "UPDATE users SET password_reset_code = ?, password_reset_expires = ? WHERE id = ?",
                (
                    generate_password_hash(code),
                    (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat(),
                    user["id"],
                ),
            )
            db.commit()
            try:
                email_sent = _send_email(
                    "Reset your AltaJobs password",
                    user["email"],
                    f"Hello {user['username']},\n\nYour reset code is: {code}\n\nIt expires in 15 minutes.",
                )
            except Exception as exc:
                print(f"[auth] password reset email failed: {exc}")
                email_sent = False
        flash(get_translator(session.get("lang", DEFAULT_LANG))["password_reset_sent"])
        return redirect(url_for("reset_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("reset_code", "").strip()
        new_password = request.form.get("new_password", "")
        if not email or not code or not new_password:
            flash(get_translator(session.get("lang", DEFAULT_LANG))["invalid_reset_code"])
            return redirect(url_for("reset_password"))
        db = get_db()
        user = db.execute(
            "SELECT id, password_reset_code, password_reset_expires FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not user:
            flash(get_translator(session.get("lang", DEFAULT_LANG))["email_required"])
            return redirect(url_for("reset_password"))
        expires = user["password_reset_expires"]
        if not user["password_reset_code"] or not expires or datetime.datetime.utcnow() > datetime.datetime.fromisoformat(expires):
            flash(get_translator(session.get("lang", DEFAULT_LANG))["invalid_reset_code"])
            return redirect(url_for("reset_password"))
        if not check_password_hash(user["password_reset_code"], code):
            flash(get_translator(session.get("lang", DEFAULT_LANG))["invalid_reset_code"])
            return redirect(url_for("reset_password"))
        db.execute(
            "UPDATE users SET password_hash = ?, password_reset_code = NULL, password_reset_expires = NULL WHERE id = ?",
            (generate_password_hash(new_password), user["id"]),
        )
        db.commit()
        flash(get_translator(session.get("lang", DEFAULT_LANG))["password_reset_success"])
        return redirect(url_for("login"))
    return render_template("reset_password.html")


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
            if user["is_banned"]:
                flash("account_banned")
                return redirect(url_for("login"))
            session["user_id"] = user["id"]
            if user["email_verification_code"] and not user["email_verified"]:
                flash(get_translator(session.get("lang", DEFAULT_LANG))["verification_required"])
                return redirect(url_for("verify_email_page"))
            return redirect(url_for("feed"))
        flash(get_translator(session.get("lang", DEFAULT_LANG))["login_failed"])
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Feed / Posts
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def feed():
    db = get_db()
    user = get_current_user()

    posts = db.execute(
        """SELECT posts.*, users.username, users.full_name, users.avatar, users.user_type,
                  users.is_verified, users.verified_until, users.is_vip, users.vip_until
           FROM posts JOIN users ON posts.user_id = users.id
           ORDER BY posts.created_at DESC LIMIT 100"""
    ).fetchall()

    channel_posts = []

    liked_ids = set()
    saved_ids = set()
    following_ids = set()
    applied_ids = set()
    if user:
        rows = db.execute(
            "SELECT post_id FROM likes WHERE user_id = ?", (user["id"],)
        ).fetchall()
        liked_ids = {r["post_id"] for r in rows}
        srows = db.execute(
            "SELECT post_id FROM saved_posts WHERE user_id = ?", (user["id"],)
        ).fetchall()
        saved_ids = {r["post_id"] for r in srows}
        frows = db.execute(
            "SELECT followed_id FROM follows WHERE follower_id = ?", (user["id"],)
        ).fetchall()
        following_ids = {r["followed_id"] for r in frows}
        arows = db.execute(
            "SELECT post_id FROM job_applications WHERE applicant_id = ?", (user["id"],)
        ).fetchall()
        applied_ids = {r["post_id"] for r in arows}

    def build_post_payload(rows):
        payload = []
        for p in rows:
            like_count = db.execute(
                "SELECT COUNT(*) c FROM likes WHERE post_id = ?", (p["id"],)
            ).fetchone()["c"]
            comment_count = db.execute(
                "SELECT COUNT(*) c FROM comments WHERE post_id = ?", (p["id"],)
            ).fetchone()["c"]
            payload.append({
                "post": p,
                "author_name": p["full_name"] or p["username"] or "Unknown",
                "like_count": like_count,
                "comment_count": comment_count,
                "liked": p["id"] in liked_ids,
                "saved": p["id"] in saved_ids,
                "following": p["user_id"] in following_ids,
                "applied": p["id"] in applied_ids,
            })
        return payload

    posts_data = build_post_payload(posts)
    channel_posts_data = build_post_payload(channel_posts)

    return render_template(
        "feed.html",
        posts_data=posts_data,
        posts=posts_data,
        channel_posts=channel_posts_data,
        days_left=trial_days_left(user) if user else 0,
        show_trial_banner=user and not user["paid_until"],
    )


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
    photo = save_photo(request.files.get("photo"))

    if not content and not photo:
        return redirect(url_for("feed"))

    db = get_db()
    db.execute(
        """INSERT INTO posts (user_id, content, photo, post_type, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session["user_id"], content, photo, post_type,
         datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return redirect(url_for("feed"))


@app.route("/post/<int:post_id>")
@login_required
def post_detail(post_id):
    db = get_db()
    record_unique_view(db, post_id, session["user_id"])
    post = db.execute(
        """SELECT posts.*, users.username, users.full_name, users.avatar,
                  users.is_verified, users.verified_until, users.is_vip, users.vip_until
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
    if post and (post["user_id"] == user["id"] or user["is_admin"]):
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
                  users.is_verified, users.verified_until
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
                  users.is_verified, users.verified_until, users.is_vip, users.vip_until
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

    posts = db.execute(
        """SELECT posts.*, users.username, users.full_name, users.avatar, users.user_type,
                  users.is_verified, users.verified_until, users.is_vip, users.vip_until
           FROM posts JOIN users ON posts.user_id = users.id
           WHERE posts.user_id = ?
           ORDER BY posts.created_at DESC""",
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

    return render_template(
        "profile.html", profile_user=profile_user, posts=posts,
        ratings=ratings, avg_stars=avg_row["avg_stars"], rating_count=avg_row["cnt"],
        followers_count=followers_count, following_count=following_count,
        posts_count=posts_count, is_following=is_following,
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
    if user["wallet_balance"] < CHANNEL_VERIFICATION_MONTHLY_PRICE:
        flash("insufficient_balance")
        return redirect(url_for("channel_view", channel_id=channel_id))

    new_balance = user["wallet_balance"] - CHANNEL_VERIFICATION_MONTHLY_PRICE
    base = datetime.datetime.utcnow()
    if channel_is_verified(channel):
        base = datetime.datetime.fromisoformat(channel["verified_until"])
    verified_until = base + datetime.timedelta(days=30)

    db.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_balance, user["id"]))
    db.execute(
        "UPDATE channels SET is_verified = 1, verified_until = ? WHERE id = ?",
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
# AI-Assisted CV Maker
# ---------------------------------------------------------------------------
@app.route("/cv-maker", methods=["GET", "POST"])
@login_required
def cv_maker():
    payload = None
    user = get_current_user()

    if request.method == "POST":
        if user["wallet_balance"] < CV_PREMIUM_PRICE:
            flash(f"Insufficient wallet balance - generating a premium CV costs {CV_PREMIUM_PRICE} ETB.")
            return redirect(url_for("wallet"))

        photo = save_cv_photo(request.files.get("photo"))
        payload = _generate_cv_payload(request.form, photo=photo)

        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            # Conditional UPDATE (balance >= price) makes this atomic and
            # race-safe - the same pattern used by buy_verification/buy_vip -
            # so the CV can never be charged for twice or charged past zero.
            cur = db.execute(
                "UPDATE users SET wallet_balance = wallet_balance - ? "
                "WHERE id = ? AND wallet_balance >= ?",
                (CV_PREMIUM_PRICE, user["id"], CV_PREMIUM_PRICE),
            )
            if cur.rowcount == 0:
                db.rollback()
                flash(f"Insufficient wallet balance - generating a premium CV costs {CV_PREMIUM_PRICE} ETB.")
                return redirect(url_for("wallet"))

            db.execute(
                """INSERT INTO cv_documents
                   (user_id, full_name, target_role, summary, experience,
                    achievements, skills, photo, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user["id"], payload["full_name"], payload["target_role"],
                    payload["summary"], payload["experience"],
                    "\n".join(payload["achievements"]), ", ".join(payload["skills"]),
                    photo, datetime.datetime.utcnow().isoformat(),
                ),
            )
            db.commit()
            flash("Premium CV generated! Your wallet balance has been updated.")
        except Exception:
            db.rollback()
            raise

    return render_template("cv_maker.html", payload=payload, cv_price=CV_PREMIUM_PRICE)


# ---------------------------------------------------------------------------
# Wallet (deposit / withdraw)
# ---------------------------------------------------------------------------
@app.route("/wallet")
@login_required
def wallet():
    db = get_db()
    user = get_current_user()
    history = db.execute(
        """SELECT * FROM wallet_transactions WHERE user_id = ?
           ORDER BY created_at DESC LIMIT 30""",
        (user["id"],),
    ).fetchall()
    gifts_received = db.execute(
        "SELECT COALESCE(SUM(amount - platform_cut), 0) total FROM gifts WHERE receiver_id = ?",
        (user["id"],),
    ).fetchone()["total"]

    current_month = datetime.datetime.utcnow().strftime("%Y-%m")
    challenge_status = db.execute(
        """SELECT ce.*, cp.tier_amount, cp.prize_pool, cp.status AS pool_status
           FROM challenge_entries ce
           JOIN challenge_pools cp ON ce.pool_id = cp.id
           WHERE ce.user_id = ? AND cp.month = ?""",
        (user["id"], current_month),
    ).fetchone()

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
    )


@app.route("/wallet/transfer", methods=["POST"])
@login_required
def wallet_transfer():
    amount = int(request.form.get("amount", 0) or 0)
    recipient_identifier = (request.form.get("recipient_identifier") or "").strip()
    if amount <= 0 or not recipient_identifier:
        flash("Please enter a valid amount and recipient")
        return redirect(url_for("wallet"))

    db = get_db()
    sender = get_current_user()
    if sender["wallet_balance"] < amount:
        flash("Insufficient wallet balance")
        return redirect(url_for("wallet"))

    recipient = db.execute(
        "SELECT * FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?) OR lower(phone) = lower(?)",
        (recipient_identifier, recipient_identifier, recipient_identifier),
    ).fetchone()
    if not recipient or recipient["id"] == sender["id"]:
        flash("Recipient could not be found")
        return redirect(url_for("wallet"))

    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ?", (amount, sender["id"]))
        db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?", (amount, recipient["id"]))
        db.execute(
            "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'transfer', ?, ?, 'approved', ?)",
            (sender["id"], amount, f"Sent to {recipient['username']}", datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("P2P transfer sent")
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("wallet"))


@app.route("/wallet/deposit", methods=["POST"])
@login_required
def wallet_deposit():
    amount = int(request.form.get("amount", 0) or 0)
    bank = request.form.get("bank", "").strip()
    ref = request.form.get("transaction_ref", "").strip()
    note = request.form.get("note", "").strip()
    receipt_photo = save_photo(request.files.get("receipt_photo"))

    # Only accept a bank name that's currently active in the admin-managed
    # list, so users can't submit a deposit against a bank that was removed
    # or never existed.
    active_bank_names = {b["bank_name"] for b in get_active_banks()}
    if amount > 0 and bank and bank in active_bank_names and ref:
        db = get_db()
        db.execute(
            """INSERT INTO wallet_transactions
               (user_id, tx_type, amount, transaction_ref, bank, note, receipt_photo, created_at)
               VALUES (?, 'deposit', ?, ?, ?, ?, ?, ?)""",
            (session["user_id"], amount, ref, bank, note, receipt_photo, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("payment_pending")
    else:
        flash("Please select a valid bank, amount, and transaction reference.")
    return redirect(url_for("wallet"))


def _submit_withdrawal_request(user_id, amount, bank_name, account_number, account_name):
    amount = int(amount or 0)
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
    db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? "
            "WHERE id = ? AND wallet_balance >= ?",
            (amount, user_id, amount),
        )
        if cur.rowcount == 0:
            db.rollback()
            return False, "insufficient_balance"

        note = f"Account: {account_name} | Account Number: {account_number}"
        db.execute(
            """INSERT INTO wallet_transactions
               (user_id, tx_type, amount, bank, note, account_number, account_name, created_at)
               VALUES (?, 'withdrawal', ?, ?, ?, ?, ?, ?)""",
            (user_id, amount, bank_name, note, account_number, account_name, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        return True, None
    except Exception:
        db.rollback()
        raise


@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw_request():
    amount = request.form.get("amount", 0)
    bank_name = request.form.get("bankName", "")
    account_number = request.form.get("accountNumber", "")
    account_name = request.form.get("accountName", "")

    success, error = _submit_withdrawal_request(
        session["user_id"], amount, bank_name, account_number, account_name
    )
    if not success:
        flash(error or "invalid_withdrawal_request")
    else:
        flash("payment_pending")
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
    if user["wallet_balance"] >= VERIFICATION_MONTHLY_PRICE:
        db.execute("BEGIN IMMEDIATE")
        try:
            new_balance = user["wallet_balance"] - VERIFICATION_MONTHLY_PRICE
            base = datetime.datetime.utcnow()
            if is_currently_verified(user):
                base = datetime.datetime.fromisoformat(user["verified_until"])
            verified_until = base + datetime.timedelta(days=30)
            db.execute(
                """UPDATE users SET wallet_balance = ?, is_verified = 1, verified_until = ?
                   WHERE id = ?""",
                (new_balance, verified_until.isoformat(), user["id"]),
            )
            admin_user = db.execute(
                "SELECT * FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            if admin_user:
                db.execute(
                    "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                    (VERIFICATION_MONTHLY_PRICE, admin_user["id"]),
                )
            db.execute(
                "INSERT INTO wallet_transactions (user_id, tx_type, amount, note, status, created_at) VALUES (?, 'verification', ?, ?, 'approved', ?)",
                (user["id"], VERIFICATION_MONTHLY_PRICE, "Blue Tick purchase", datetime.datetime.utcnow().isoformat()),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        flash("insufficient_balance")
    return redirect(url_for("wallet"))


# ---------------------------------------------------------------------------
# VIP Membership
# ---------------------------------------------------------------------------
@app.route("/vip/buy", methods=["POST"])
@login_required
def buy_vip():
    db = get_db()
    user = get_current_user()
    if user["wallet_balance"] >= VIP_MONTHLY_PRICE:
        new_balance = user["wallet_balance"] - VIP_MONTHLY_PRICE
        base = datetime.datetime.utcnow()
        if is_currently_vip(user):
            base = datetime.datetime.fromisoformat(user["vip_until"])
        vip_until = base + datetime.timedelta(days=30)
        db.execute(
            """UPDATE users SET wallet_balance = ?, is_vip = 1, vip_until = ?
               WHERE id = ?""",
            (new_balance, vip_until.isoformat(), user["id"]),
        )
        db.commit()
    else:
        flash("insufficient_balance")
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
    if sender["wallet_balance"] < price:
        flash("insufficient_balance")
        return redirect(request.referrer or url_for("feed"))

    platform_cut = round(price * PLATFORM_CUT_PERCENT / 100)
    receiver_share = price - platform_cut

    db = get_db()
    db.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ?",
               (price, sender["id"]))
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
            ORDER BY is_verified DESC, is_vip DESC, created_at DESC LIMIT 15""",
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
                "SELECT * FROM challenge_entries WHERE pool_id = ? AND user_id = ?",
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
        if user["wallet_balance"] < tier:
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
@app.route("/admin/settings/telebirr", methods=["POST"])
@login_required
@admin_required
def admin_update_telebirr():
    number = (request.form.get("telebirr_number") or "").strip()
    if number:
        set_setting("telebirr_wallet_number", number)
    return redirect(request.referrer or url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Admin - Dynamic Bank Access (accepted deposit payment methods)
# ---------------------------------------------------------------------------
@app.route("/admin/banks")
@login_required
@admin_required
def admin_banks():
    db = get_db()
    banks = db.execute(
        "SELECT * FROM bank_accounts ORDER BY is_active DESC, bank_name"
    ).fetchall()
    return render_template("admin_banks.html", banks=banks)


@app.route("/admin/banks/add", methods=["POST"])
@login_required
@admin_required
def admin_banks_add():
    bank_name = (request.form.get("bank_name") or "").strip()
    account_number = (request.form.get("account_number") or "").strip()
    account_holder_name = (request.form.get("account_holder_name") or "").strip()

    if not bank_name or not account_number or not account_holder_name:
        flash("Please fill in the bank name, account number, and account holder name.")
        return redirect(url_for("admin_banks"))

    db = get_db()
    db.execute(
        """INSERT INTO bank_accounts
           (bank_name, account_number, account_holder_name, is_active, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (bank_name, account_number, account_holder_name, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    flash("Bank account added.")
    return redirect(url_for("admin_banks"))


@app.route("/admin/banks/<int:bank_id>/edit", methods=["POST"])
@login_required
@admin_required
def admin_banks_edit(bank_id):
    bank_name = (request.form.get("bank_name") or "").strip()
    account_number = (request.form.get("account_number") or "").strip()
    account_holder_name = (request.form.get("account_holder_name") or "").strip()

    if not bank_name or not account_number or not account_holder_name:
        flash("Please fill in the bank name, account number, and account holder name.")
        return redirect(url_for("admin_banks"))

    db = get_db()
    db.execute(
        """UPDATE bank_accounts
           SET bank_name = ?, account_number = ?, account_holder_name = ?
           WHERE id = ?""",
        (bank_name, account_number, account_holder_name, bank_id),
    )
    db.commit()
    flash("Bank account updated.")
    return redirect(url_for("admin_banks"))


@app.route("/admin/banks/<int:bank_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_banks_toggle(bank_id):
    """Soft enable/disable instead of deleting, so historical deposit
    tickets that reference this bank name keep making sense in the admin
    dashboard even after it's retired."""
    db = get_db()
    db.execute(
        "UPDATE bank_accounts SET is_active = 1 - is_active WHERE id = ?",
        (bank_id,),
    )
    db.commit()
    return redirect(url_for("admin_banks"))


@app.route("/admin/banks/<int:bank_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_banks_delete(bank_id):
    db = get_db()
    db.execute("DELETE FROM bank_accounts WHERE id = ?", (bank_id,))
    db.commit()
    flash("Bank account deleted.")
    return redirect(url_for("admin_banks"))


@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    db = get_db()
    pending_payments = db.execute(
        """SELECT payments.*, users.username FROM payments
           JOIN users ON payments.user_id = users.id
           WHERE payments.status = 'pending' ORDER BY payments.created_at DESC"""
    ).fetchall()
    reports = db.execute(
        """SELECT reports.*, users.username as reporter FROM reports
           JOIN users ON reports.reporter_id = users.id
           WHERE reports.status = 'pending'
           ORDER BY reports.created_at DESC"""
    ).fetchall()
    pending_wallet_tx = db.execute(
        """SELECT wallet_transactions.*, users.username, users.phone FROM wallet_transactions
           JOIN users ON wallet_transactions.user_id = users.id
           WHERE wallet_transactions.status = 'pending'
           ORDER BY wallet_transactions.created_at DESC"""
    ).fetchall()
    gift_earnings = db.execute(
        "SELECT COALESCE(SUM(platform_cut), 0) total FROM gifts"
    ).fetchone()["total"]
    verified_users_count = db.execute(
        "SELECT COUNT(*) c FROM users WHERE is_verified = 1"
    ).fetchone()["c"]
    vip_users_count = db.execute(
        "SELECT COUNT(*) c FROM users WHERE is_vip = 1"
    ).fetchone()["c"]
    subscription_revenue = db.execute(
        "SELECT COALESCE(SUM(amount), 0) total FROM payments WHERE status = 'approved'"
    ).fetchone()["total"]
    total_revenue = subscription_revenue + gift_earnings

    return render_template(
        "admin.html", pending_payments=pending_payments, reports=reports,
        pending_wallet_tx=pending_wallet_tx, gift_earnings=gift_earnings,
        verified_users_count=verified_users_count,
        vip_users_count=vip_users_count,
        subscription_revenue=subscription_revenue,
        total_revenue=total_revenue,
        verification_price=VERIFICATION_MONTHLY_PRICE,
        vip_price=VIP_MONTHLY_PRICE,
    )


# ---------------------------------------------------------------------------
# Admin Dashboard - standalone deposit-approval view
# (additive only - does not touch admin_panel() or approve_wallet_tx() above)
# ---------------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
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
           ORDER BY wallet_transactions.created_at DESC"""
    ).fetchall()
    pending_withdrawals = db.execute(
        """SELECT wallet_transactions.id,
                  users.username,
                  wallet_transactions.amount,
                  wallet_transactions.created_at
           FROM wallet_transactions
           JOIN users ON wallet_transactions.user_id = users.id
           WHERE wallet_transactions.status = 'pending'
             AND wallet_transactions.tx_type = 'withdrawal'
           ORDER BY wallet_transactions.created_at DESC"""
    ).fetchall()
    return render_template(
        "admin_dashboard.html",
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        telebirr_number=get_setting("telebirr_wallet_number", TELEBIRR_WALLET_NUMBER),
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
    db.execute("BEGIN IMMEDIATE")
    try:
        tx = _claim_pending_transaction(db, tx_id, "deposit", "approved")
        if tx:
            db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                (tx["amount"], tx["user_id"]),
            )
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
    db.execute("BEGIN IMMEDIATE")
    try:
        # Nothing was ever deducted for a deposit request, so rejecting it
        # is just a status change - no balance change needed.
        _claim_pending_transaction(db, tx_id, "deposit", "rejected")
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
    db.execute("BEGIN IMMEDIATE")
    try:
        # Funds were already reserved (deducted) when the withdrawal was
        # requested in wallet_withdraw() - approving just finalizes status.
        _claim_pending_transaction(db, tx_id, "withdrawal", "approved")
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
    db.execute("BEGIN IMMEDIATE")
    try:
        tx = _claim_pending_transaction(db, tx_id, "withdrawal", "rejected")
        if tx:
            # Refund the reserved funds back to the user's wallet.
            db.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                (tx["amount"], tx["user_id"]),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/wallet/<int:tx_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_wallet_tx(tx_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        tx = db.execute("SELECT * FROM wallet_transactions WHERE id = ?", (tx_id,)).fetchone()
        if not tx or tx["status"] != "pending":
            db.rollback()
            return redirect(url_for("admin_panel"))

        if tx["tx_type"] == "deposit":
            claimed = _claim_pending_transaction(db, tx_id, "deposit", "approved")
            if claimed:
                db.execute(
                    "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                    (claimed["amount"], claimed["user_id"]),
                )
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
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target and not target["is_admin"]:
        db.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
        db.commit()
    return redirect(request.referrer or url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/unban", methods=["POST"])
@login_required
@admin_required
def unban_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
    db.commit()
    return redirect(request.referrer or url_for("admin_panel"))
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    with app.app_context():
        ensure_database_schema()
    app.run(debug=True, host="0.0.0.0", port=5000)
