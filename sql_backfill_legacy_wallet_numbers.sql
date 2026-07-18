-- One-time safe backfill for legacy users with missing wallet/account numbers.
-- Run this once in the Neon SQL Editor or any PostgreSQL-compatible client.
-- It updates only rows where the value is NULL or empty string and leaves existing values unchanged.

BEGIN;

UPDATE users
SET wallet_id = COALESCE(wallet_id, '')
WHERE id IS NOT NULL;

UPDATE users
SET wallet_id = CASE
    WHEN wallet_id IS NULL OR TRIM(wallet_id) = '' THEN 'WAL' || LPAD(CAST(id AS TEXT), 6, '0')
    ELSE wallet_id
END
WHERE id IS NOT NULL;

UPDATE users
SET wallet_id = CASE
    WHEN wallet_id IS NULL OR TRIM(wallet_id) = '' THEN 'WAL' || LPAD(CAST(id AS TEXT), 6, '0')
    ELSE wallet_id
END
WHERE id IS NOT NULL;

-- If you also want to backfill a legacy numeric account field in a custom table, add it here.
-- Example (only if such a column exists):
-- UPDATE users
-- SET card_no = CASE
--   WHEN card_no IS NULL OR TRIM(card_no) = '' THEN LPAD(CAST(id AS TEXT), 16, '0')
--   ELSE card_no
-- END
-- WHERE id IS NOT NULL;

COMMIT;
