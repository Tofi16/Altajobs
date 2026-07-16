# ---------------------------------------------------------------------------
# ADD inside migrate_db(), anywhere after the existing `new_columns` block for
# `users` (i.e. right after the wallet_balance/is_verified/... ALTER loop).
# This is additive-only, uses "IF NOT EXISTS" style existing-column checks
# exactly like the rest of migrate_db(), and never touches existing data.
# ---------------------------------------------------------------------------

    # priority_badge: set for users whose most recent CV purchase was the
    # VIP tier (spec: "priority job seeker badge displayed to employers")
    user_cols_for_cv = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    if "priority_badge" not in user_cols_for_cv:
        db.execute("ALTER TABLE users ADD COLUMN priority_badge INTEGER DEFAULT 0")
    db.commit()

    # cv_documents: add tiered-pricing / template / cover letter columns
    cv_cols = {row[1] for row in db.execute("PRAGMA table_info(cv_documents)")}
    cv_new_columns = {
        "tier": "TEXT DEFAULT 'standard'",
        "template_key": "TEXT DEFAULT 'classic'",
        "cover_letter": "TEXT DEFAULT NULL",
        "priority_badge": "INTEGER DEFAULT 0",
    }
    for col, coltype in cv_new_columns.items():
        if col not in cv_cols:
            db.execute(f"ALTER TABLE cv_documents ADD COLUMN {col} {coltype}")
    db.commit()
