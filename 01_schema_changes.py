# ============================================================================
# PART 1 — SCHEMA CHANGES
# ============================================================================

# ----------------------------------------------------------------------------
# 1A. In init_postgres_db(): DELETE these CREATE TABLE blocks entirely:
#   posts, interactions, comments, likes, saved_posts, product_photos,
#   product_favorites, offers, products
# (job_applications, gifts, reports, token_transactions stay but get column
#  changes below)
#
# ADD this new table (put it where `posts` used to be):
# ----------------------------------------------------------------------------
JOBS_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT DEFAULT 'Addis Ababa',
    category TEXT DEFAULT 'general',
    employment_type TEXT DEFAULT 'full_time',
    salary_range TEXT DEFAULT NULL,
    photo TEXT DEFAULT NULL,
    status TEXT DEFAULT 'open',
    view_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT DEFAULT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# job_applications: change post_id -> job_id (keep everything else identical)
JOB_APPLICATIONS_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS job_applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    applicant_id INTEGER NOT NULL,
    message TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TEXT NOT NULL,
    UNIQUE(job_id, applicant_id),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(applicant_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

# gifts: change post_id -> job_id
GIFTS_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS gifts (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    gift_key TEXT NOT NULL,
    amount INTEGER NOT NULL,
    platform_cut INTEGER NOT NULL,
    job_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
"""

# ----------------------------------------------------------------------------
# 1B. In migrate_db() (SQLite path): DELETE these CREATE TABLE blocks:
#   posts, products
# (comments/likes/saved_posts/announcements etc. blocks that reference posts
#  can stay defined harmlessly if unused, but cleanest is to remove: posts,
#  products. Leave "comments"/"likes" CREATE TABLE statements in place only
#  if you're not fully dropping historical data -- since the decision was
#  full removal, delete those three blocks too: comments, likes, saved_posts
#  are not created elsewhere so just delete their CREATE TABLE statements.)
#
# ADD this new table (SQLite version):
# ----------------------------------------------------------------------------
JOBS_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT DEFAULT 'Addis Ababa',
    category TEXT DEFAULT 'general',
    employment_type TEXT DEFAULT 'full_time',
    salary_range TEXT DEFAULT NULL,
    photo TEXT DEFAULT NULL,
    status TEXT DEFAULT 'open',
    view_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT DEFAULT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

JOB_APPLICATIONS_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    applicant_id INTEGER NOT NULL,
    message TEXT,
    status TEXT DEFAULT 'submitted',
    created_at TEXT NOT NULL,
    UNIQUE(job_id, applicant_id),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(applicant_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

GIFTS_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    gift_key TEXT NOT NULL,
    amount INTEGER NOT NULL,
    platform_cut INTEGER NOT NULL,
    job_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);
"""

# ----------------------------------------------------------------------------
# 1C. Migration safety for EXISTING installs (both SQLite and Postgres):
# Since job_applications and gifts already exist in production with
# post_id columns, a plain CREATE TABLE IF NOT EXISTS won't rename the
# column on an existing table. Add this idempotent migration block
# (put it in ensure_postgres_wallet_columns() for Postgres, and as a new
# block in migrate_db() for SQLite) to handle upgrading existing databases:
# ----------------------------------------------------------------------------

MIGRATION_NOTE = """
For POSTGRES (add inside ensure_postgres_wallet_columns(), in its own
try/except so a failure doesn't abort startup):

    db.execute("ALTER TABLE job_applications ADD COLUMN IF NOT EXISTS job_id INTEGER DEFAULT NULL")
    db.execute("UPDATE job_applications SET job_id = post_id WHERE job_id IS NULL AND post_id IS NOT NULL")
    db.execute("ALTER TABLE gifts ADD COLUMN IF NOT EXISTS job_id INTEGER DEFAULT NULL")
    db.execute("UPDATE gifts SET job_id = post_id WHERE job_id IS NULL AND post_id IS NOT NULL")
    db.commit()

    (Old post_id columns are left in place, unused -- safer than dropping
    columns with live foreign key constraints. They simply stop being read.)

For SQLITE (add inside migrate_db(), same idempotent pattern):

    job_app_cols = {row[1] for row in db.execute("PRAGMA table_info(job_applications)")}
    if "job_id" not in job_app_cols:
        db.execute("ALTER TABLE job_applications ADD COLUMN job_id INTEGER DEFAULT NULL")
        if "post_id" in job_app_cols:
            db.execute("UPDATE job_applications SET job_id = post_id WHERE post_id IS NOT NULL")
    gifts_cols = {row[1] for row in db.execute("PRAGMA table_info(gifts)")}
    if "job_id" not in gifts_cols:
        db.execute("ALTER TABLE gifts ADD COLUMN job_id INTEGER DEFAULT NULL")
        if "post_id" in gifts_cols:
            db.execute("UPDATE gifts SET job_id = post_id WHERE post_id IS NOT NULL")
    db.commit()

IMPORTANT: since job_applications/gifts previously pointed post_id at the
OLD posts.id space, and the new jobs table starts its own id sequence from
1, this backfill (job_id = post_id) is only meaningful if you are doing a
fresh start with no production data to preserve. Given the full-removal
decision, the realistic path is: this is a brand new install or Tofik
accepts that old post_id-linked applications/gifts become orphaned
(job_id NULL) since the posts they pointed to no longer exist anyway.
"""
