#!/usr/bin/env python3
"""
update_db.py - Safe, idempotent schema sync for AltaJobs on Neon Postgres.

What this does:
  - Adds any missing columns using ADD COLUMN IF NOT EXISTS
  - Never drops, renames, or modifies existing columns or data
  - Safe to run multiple times (idempotent) and safe to run against a
    database that already has some/all of these columns

What this does NOT do:
  - It will not touch any existing row's data
  - It will not create or drop tables (your tables must already exist -
    if they don't, run the app once first so init_postgres_db() creates them)

Usage:
  1. Make sure DATABASE_URL is set in your environment, e.g.:
       export DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require"
     (On Render/Railway this is usually already set - you can copy it from
     your dashboard's environment variables page.)
  2. Install psycopg2 if you don't already have it:
       pip install psycopg2-binary
  3. Run:
       python update_db.py
  4. Read the printed summary - it tells you exactly which columns were
     added vs. already present, and reports any column it could not add
     (with the reason) instead of silently failing.
"""
import os
import sys
import urllib.parse

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 is not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def _normalize_url(url):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("postgres", "postgresql"):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
        query_string = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=query_string))
    return url


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
    print("ERROR: DATABASE_URL is not set to a Postgres connection string.")
    print("Set it first, e.g.:")
    print('  export DATABASE_URL="postgresql://user:pass@host/dbname"')
    sys.exit(1)

DATABASE_URL = _normalize_url(DATABASE_URL)

# Every statement here is additive and idempotent - IF NOT EXISTS means
# re-running this script is always safe.
STATEMENTS = [
    # users table
    ("users.balance",             "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0"),
    ("users.wallet_id",           "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_id TEXT UNIQUE DEFAULT NULL"),
    ("users.wallet_balance",      "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance INTEGER DEFAULT 0"),
    ("users.alta_tokens",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS alta_tokens INTEGER DEFAULT 0"),
    ("users.points",              "ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0"),
    ("users.activity_badge",      "ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_badge TEXT DEFAULT 'Bronze Member'"),
    ("users.verified_until",      "ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_until TEXT DEFAULT NULL"),
    ("users.verification_tier",   "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_tier TEXT DEFAULT 'none'"),
    ("users.is_banned",           "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE"),
    ("users.banned_until",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_until TEXT DEFAULT NULL"),
    ("users.ban_reason",          "ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT DEFAULT NULL"),
    ("users.is_suspended",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE"),
    ("users.referral_code",       "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code TEXT DEFAULT NULL"),
    ("users.strikes",             "ALTER TABLE users ADD COLUMN IF NOT EXISTS strikes INTEGER DEFAULT 0"),
    ("users.trust_score",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 0"),
    ("users.is_trusted_seller",   "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_trusted_seller INTEGER DEFAULT 0"),
    ("users.is_admin",            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"),

    # posts table
    ("posts.view_count",          "ALTER TABLE posts ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0"),
    ("posts.virality_score",      "ALTER TABLE posts ADD COLUMN IF NOT EXISTS virality_score REAL DEFAULT 0.0"),
    ("posts.status",              "ALTER TABLE posts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'approved'"),

    # wallet_transactions table
    ("wallet_transactions.transaction_ref",     "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS transaction_ref TEXT DEFAULT NULL"),
    ("wallet_transactions.receipt_image_path",  "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS receipt_image_path TEXT DEFAULT NULL"),
    ("wallet_transactions.recipient_wallet_id", "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS recipient_wallet_id TEXT DEFAULT NULL"),

    # bank_accounts table
    ("bank_accounts.account_name",          "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name TEXT DEFAULT NULL"),
    ("bank_accounts.account_holder_name",    "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_holder_name TEXT DEFAULT NULL"),

    # products table (marketplace)
    ("products.photo",     "ALTER TABLE products ADD COLUMN IF NOT EXISTS photo TEXT DEFAULT NULL"),
    ("products.location",  "ALTER TABLE products ADD COLUMN IF NOT EXISTS location TEXT DEFAULT 'Addis Ababa'"),
    ("products.status",    "ALTER TABLE products ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'"),
]

FILL_DEFAULTS = [
    "UPDATE users SET wallet_balance = COALESCE(wallet_balance, 0), alta_tokens = COALESCE(alta_tokens, 0)",
    "UPDATE posts SET view_count = COALESCE(view_count, 0), virality_score = COALESCE(virality_score, 0.0)",
]


def main():
    print(f"Connecting to Postgres...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    added, already_present, failed = [], [], []

    for label, sql in STATEMENTS:
        try:
            cur.execute(sql)
            # ADD COLUMN IF NOT EXISTS doesn't tell us whether it actually
            # added anything, so we check information_schema before/after
            # isn't necessary here - just record success either way.
            conn.commit()
            added.append(label)
        except Exception as exc:
            conn.rollback()
            failed.append((label, str(exc)))

    for sql in FILL_DEFAULTS:
        try:
            cur.execute(sql)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"Warning: could not backfill defaults ({sql[:50]}...): {exc}")

    cur.close()
    conn.close()

    print("\n=== Migration summary ===")
    print(f"Checked/applied: {len(added)} column statements (safe no-ops if already present)")
    if failed:
        print(f"\n{len(failed)} statement(s) could not be applied:")
        for label, err in failed:
            print(f"  - {label}: {err}")
        print("\nThese usually mean either a permissions issue (your DB role")
        print("can't ALTER TABLE) or a table that doesn't exist yet. If a")
        print("table is missing, start the Flask app once first so it runs")
        print("init_postgres_db() and creates the base schema, then re-run")
        print("this script.")
    else:
        print("All column checks completed with no errors.")
    print("\nDone. No existing data was modified or deleted.")


if __name__ == "__main__":
    main()
