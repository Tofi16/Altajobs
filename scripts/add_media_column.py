import sqlite3
import sys
DB_PATH = r"C:/Users/medina/Desktop/altajobs/database.db"
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("PRAGMA table_info(posts)")
cols = [r[1] for r in cur.fetchall()]
if 'media_urls' in cols:
    print('media_urls_exists')
    sys.exit(0)
try:
    cur.execute("ALTER TABLE posts ADD COLUMN media_urls TEXT")
    con.commit()
    print('media_urls_added')
except Exception as e:
    print('error', e)
finally:
    con.close()
