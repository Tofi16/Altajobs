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
    raise SystemExit("psycopg2 is required to run this script. Install it in your environment.")


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
        # Check if user 'Tofik' exists
        print("Looking for user 'Tofik'...")
        cur.execute("SELECT id, username, is_admin, is_verified, is_vip FROM users WHERE username = %s;", ("Tofik",))
        result = cur.fetchone()
        
        if not result:
            print("❌ User 'Tofik' not found in the database.")
            print("   Please register this user first, then run this script again.")
            cur.close()
            conn.close()
            return
        
        user_id, username, current_admin, current_verified, current_vip = result
        print(f"✓ Found user: {username} (ID: {user_id})")
        print(f"  Current status: Admin={current_admin}, Verified={current_verified}, VIP={current_vip}")
        
        # Update the user to have verified and VIP status (admin already set)
        print("\nUpdating user privileges...")
        cur.execute(
            """
            UPDATE users 
            SET is_verified = TRUE, is_vip = TRUE
            WHERE username = %s;
            """,
            ("Tofik",)
        )
        
        # Verify the update
        cur.execute("SELECT is_admin, is_verified, is_vip FROM users WHERE username = %s;", ("Tofik",))
        updated = cur.fetchone()
        
        if updated:
            admin_status, verified_status, vip_status = updated
            print(f"✓ Update successful!")
            print(f"  New status: Admin={admin_status}, Verified={verified_status}, VIP={vip_status}")
            print(f"\n✓ 'Tofik' is now a Super Admin with Verified & VIP badges!")
        else:
            print("❌ Update verification failed.")
        
    except Exception as exc:
        print(f"❌ Error: {exc}")
        raise
    finally:
        cur.close()
        conn.close()
        print("\n✓ Database connection closed.")


if __name__ == "__main__":
    main()
