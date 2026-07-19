-- ============================================================================
-- AltaJobs — Feed performance indexes for Neon (Postgres)
-- Run these in the Neon SQL console (or `psql "$DATABASE_URL" -f neon_indexes.sql`).
--
-- CONCURRENTLY builds the index without locking writes to `posts` — important
-- on a live table. It cannot run inside a transaction block / multi-statement
-- batch, so these are run as separate statements (Neon's SQL editor runs each
-- statement individually, which is what you want here).
-- ============================================================================

-- 1) The feed query does:
--      WHERE status IN ('approved','posted') ORDER BY created_at DESC LIMIT/OFFSET
--    A composite index on (status, created_at DESC) lets Postgres satisfy the
--    filter AND the sort from the index directly, without a separate sort step.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_status_created_at
    ON posts (status, created_at DESC);

-- 2) Author lookups / "posts by this user" queries (profile pages, counts).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_user_id
    ON posts (user_id);

-- 3) Plain created_at index — kept for any query that sorts/filters by date
--    without filtering on status (e.g. admin views).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_posts_created_at
    ON posts (created_at);

-- 4) The feed also joins out to likes/comments per page of post_ids —
--    these keep those lookups indexed instead of doing a seq scan.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_likes_post_id
    ON likes (post_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_likes_user_id
    ON likes (user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_comments_post_id
    ON comments (post_id);

-- 5) Per-user "did I like/save/apply/follow" checks that run for every page.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_saved_posts_user_post
    ON saved_posts (user_id, post_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_job_applications_applicant_post
    ON job_applications (applicant_id, post_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_follows_follower_id
    ON follows (follower_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_follows_followed_id
    ON follows (followed_id);

-- ----------------------------------------------------------------------------
-- Verify the planner is actually using the new composite index:
--
--   EXPLAIN ANALYZE
--   SELECT * FROM posts
--   WHERE status IN ('approved','posted')
--   ORDER BY created_at DESC
--   LIMIT 10 OFFSET 0;
--
-- You want to see "Index Scan using idx_posts_status_created_at" (or
-- "Index Only Scan") in the plan, not "Seq Scan on posts".
-- ----------------------------------------------------------------------------
