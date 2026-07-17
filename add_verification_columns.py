import os
import urllib.parse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("WARNING: python-dotenv not installed. Install it with: pip install python-dotenv")

try:
    import psycopg2
except ImportError:
    raise SystemExit("psycopg2 is required to run this migration. Install it in your environment.")


def _ensure_postgres_ssl(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("postgres://", "postgresql://"):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" not in query:
            query["sslmode"] = ["require"]
        query_string = urllib.parse.urlencode(query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=query_string))
    return url


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set in the environment.")

    database_url = database_url.strip()
    database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url = _ensure_postgres_ssl(database_url)

    print("Connecting to Neon SQL database...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        print("Adding is_verified column if missing...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;")

        print("Adding verified_until column if missing...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_until TIMESTAMP NULL;")

        print("Adding is_vip column if missing...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;")

        print("Adding vip_until column if missing...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_until TIMESTAMP NULL;")

        print("Migration completed successfully.")
    except Exception as exc:
        print(f"Migration failed: {exc}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
