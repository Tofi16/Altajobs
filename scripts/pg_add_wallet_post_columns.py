import os
import sys
import urllib.parse

try:
    import psycopg2
except Exception as e:
    print("psycopg2 is required to run this migration. Install it in your venv.")
    raise


def _normalize_db_url(url):
    if not url:
        return None
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    # ensure sslmode if missing
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("postgres", "postgresql"):
        q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" not in q:
            q["sslmode"] = ["require"]
        qs = urllib.parse.urlencode(q, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=qs))
    return url


SQL_STATEMENTS = [
    "-- Add wallet and token columns to users",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance INTEGER DEFAULT 0;",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS alta_tokens INTEGER DEFAULT 0;",
    "-- Add bank account compatibility column",
    "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name TEXT DEFAULT NULL;",
    "-- Add post engagement tracking columns",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS virality_score REAL DEFAULT 0.0;",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'approved';",
    "-- Initialize any NULLs for safety",
    "UPDATE users SET wallet_balance = COALESCE(wallet_balance, 0), alta_tokens = COALESCE(alta_tokens, 0);",
    "UPDATE posts SET view_count = COALESCE(view_count, 0), virality_score = COALESCE(virality_score, 0.0), status = COALESCE(status, 'approved');",
]


def main():
    raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE")
    db_url = _normalize_db_url(raw)
    if not db_url:
        print("No DATABASE_URL found in environment; aborting migration.")
        sys.exit(1)
    if db_url.startswith("sqlite"):
        print("Detected SQLite database; this migration targets Postgres. Aborting.")
        sys.exit(1)

    print("The following SQL statements will be executed against:", db_url)
    print("---")
    for s in SQL_STATEMENTS:
        print(s)
    print("---")

    confirm = os.environ.get("AUTO_CONFIRM_MIGRATION") or input("Proceed? (yes/no): ")
    if confirm.strip().lower() not in ("y", "yes"):
        print("Migration cancelled by user.")
        sys.exit(0)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    try:
        for s in SQL_STATEMENTS:
            # Skip comment lines
            if s.strip().startswith("--"):
                continue
            cur.execute(s)
        conn.commit()
        print("Migration completed successfully.")
    except Exception as exc:
        conn.rollback()
        print("Migration failed:", exc)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
