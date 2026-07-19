-- ============================================================================
-- Verification System Migration: Blue / Gold Tiers
-- ============================================================================
-- NOTE: app.py already auto-runs the equivalent of this migration on startup
-- (see the `new_columns` dict + backfill block near init_db()). This file is
-- provided so you can also run it by hand against database.db / altajobs.db
-- directly, or apply it to a production database ahead of a deploy.
--
-- SQLite has no native ENUM type, so 'verification_tier' is a TEXT column
-- constrained with CHECK(...) to only ever hold 'none' | 'blue' | 'gold'.
-- ============================================================================

-- 1. Add the new column (safe to re-run: SQLite will error if it already
--    exists, so wrap in your migration runner's "if not exists" check, or
--    just ignore the error if you're pasting this manually).
ALTER TABLE users ADD COLUMN verification_tier TEXT NOT NULL DEFAULT 'none'
    CHECK (verification_tier IN ('none', 'blue', 'gold'));

-- 2. Backfill from the legacy is_verified / is_vip boolean flags.
--    Gold (is_vip) wins if a row somehow has both set.
UPDATE users
   SET verification_tier = 'gold',
       verified_until = COALESCE(verified_until, vip_until)
 WHERE is_vip = 1;

UPDATE users
   SET verification_tier = 'blue'
 WHERE is_verified = 1
   AND verification_tier = 'none';

-- 3. Index for fast "who's verified" lookups (admin dashboard, badge lookups
--    on profile pages, etc.)
CREATE INDEX IF NOT EXISTS idx_users_verification_tier ON users (verification_tier);

-- ----------------------------------------------------------------------------
-- Going forward, verified_until is the ONE expiration timestamp for both
-- tiers (it already existed on your users table — we just reuse it instead
-- of adding a second "gold_until" column). Set both columns together, e.g.:
--
--   UPDATE users
--      SET verification_tier = 'blue', verified_until = '2027-01-19T00:00:00'
--    WHERE id = ?;
--
-- app.py's set_verification_tier(db, user_id, tier, until) helper does this
-- for you and also keeps the legacy is_verified/is_vip/vip_until columns in
-- sync, so any older query elsewhere in the codebase keeps working untouched.
-- ----------------------------------------------------------------------------

-- 4. OPTIONAL cleanup — only run this once you've confirmed nothing else in
--    the codebase reads is_verified / is_vip / vip_until directly. app.py's
--    set_verification_tier() keeps them in sync for now specifically so you
--    don't have to do this right away.
-- ALTER TABLE users DROP COLUMN is_verified;
-- ALTER TABLE users DROP COLUMN is_vip;
-- ALTER TABLE users DROP COLUMN vip_until;
