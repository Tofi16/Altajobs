-- ============================================================================
-- FINAL Migration: Drop legacy verification columns from `users`
-- ============================================================================
-- Run this ONLY after confirming:
--   1. Every row that matters has already been backfilled into
--      verification_tier / verified_until (this was done in an earlier
--      migration pass — see the previous migration.sql).
--   2. The deployed app.py no longer reads or writes is_verified, is_vip,
--      or vip_until anywhere (this version of app.py has been fully swept —
--      see the accompanying summary for the full list of call sites that
--      were updated).
--   3. You have a fresh backup of database.db / altajobs.db.
--
-- SQLite note: DROP COLUMN requires SQLite >= 3.35.0 (2021-03-12). If your
-- runtime is older than that, use the "manual rebuild" fallback at the
-- bottom of this file instead.
-- ============================================================================

-- Sanity check first — confirms nothing meaningful is stranded on the old
-- columns before you remove them. Expect 0 rows back (any row here would
-- mean legacy data that never made it into verification_tier).
SELECT id, username, is_verified, is_vip, vip_until, verification_tier, verified_until
  FROM users
 WHERE (is_verified = 1 OR is_vip = 1)
   AND (verification_tier IS NULL OR verification_tier = 'none');

-- If the query above returned rows, backfill them first:
-- UPDATE users SET verification_tier = 'gold', verified_until = COALESCE(verified_until, vip_until)
--  WHERE is_vip = 1 AND (verification_tier IS NULL OR verification_tier = 'none');
-- UPDATE users SET verification_tier = 'blue'
--  WHERE is_verified = 1 AND (verification_tier IS NULL OR verification_tier = 'none');

-- ----------------------------------------------------------------------------
-- Drop the legacy columns (SQLite 3.35+ / PostgreSQL)
-- ----------------------------------------------------------------------------
ALTER TABLE users DROP COLUMN is_verified;
ALTER TABLE users DROP COLUMN is_vip;
ALTER TABLE users DROP COLUMN vip_until;

-- ----------------------------------------------------------------------------
-- Fallback for SQLite < 3.35 (no native DROP COLUMN support): rebuild the
-- table without the three columns, copying everything else across.
-- Only use this block if the ALTER TABLE DROP COLUMN statements above fail.
-- ----------------------------------------------------------------------------
-- BEGIN TRANSACTION;
--
-- CREATE TABLE users_new AS
--   SELECT id, username, email, password_hash, full_name, user_type, phone,
--          skills, experience, bio, avatar, is_admin, created_at, plan,
--          paid_until, email_verified, email_verification_code,
--          password_reset_code, password_reset_expires, email_verified_at,
--          wallet_balance, verified_until, verification_tier, is_banned,
--          referral_code, alta_tokens, last_checkin, current_streak,
--          banned_until, ban_reason, strikes, trust_score, is_suspended,
--          is_trusted_seller, balance, wallet_id, points, activity_badge
--   FROM users;
--
-- DROP TABLE users;
-- ALTER TABLE users_new RENAME TO users;
--
-- -- Recreate whatever indexes/constraints your original users table had,
-- -- e.g.:
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
-- CREATE INDEX IF NOT EXISTS idx_users_verification_tier ON users(verification_tier);
--
-- COMMIT;
-- ----------------------------------------------------------------------------

-- Note: this file intentionally does NOT touch channels.is_verified /
-- channels.verified_until — that's a separate feature (group/channel Blue
-- Tick) unrelated to the user-account tier system and was out of scope.
