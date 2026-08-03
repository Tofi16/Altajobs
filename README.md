# AltaJobs — Feed & Marketplace Removal, Jobs-First Rebuild

## What this delivery does
- **Removes entirely**: social feed (posts, likes, comments, saved posts), Marketplace
  (products, offers, favorites), Alta Token Economy (daily check-in, task-to-earn)
- **Keeps unchanged**: Wallet, Gifts, Blue/Gold Verification, Channels, Chat/Messages,
  Business Challenges, Reports, Notifications, Admin (minus product/moderation panels),
  CV Maker
- **Adds new**: a `jobs` table and a Jobs-only home page — this becomes the app's
  landing page after login, replacing the feed

⚠️ **This is a bigger, riskier change than the feed redesign.** Read
`DEPENDENCY_MAP.md` first — it explains exactly what touches `posts`/`products`
and why each decision was made (e.g. why gifts now attach to jobs instead of posts).

## Files in this delivery

| File | What it is |
|---|---|
| `DEPENDENCY_MAP.md` | Read this first. Full map of what depends on posts/products. |
| `01_schema_changes.py` | New `jobs` table SQL (SQLite + Postgres), plus `job_applications`/`gifts` column rename (`post_id` → `job_id`) |
| `02_jobs_routes.py` | All new Jobs routes — this is the replacement for feed/marketplace routes |
| `03_modified_routes.py` | `apply_to_job`, `view_applicants`, `send_gift` — updated to use `job_id` |
| `04_deletions_and_edits.py` | Exact list of functions to delete, plus small edits to `admin_panel()`/`admin_revenue()`/`profile()` |
| `05_base_html_nav_diff.py` | Nav bar changes for `base.html` |
| `templates/*.html` | New templates: `jobs_home.html`, `_job_cards.html`, `job_new.html`, `job_detail.html`, `job_applicants.html`, `my_jobs.html`, `applied_jobs.html` |
| `templates/jobs.css` | Styling for all new jobs pages |
| `templates/jobs-page.js` | Filter pills + "Load more" pagination |

## Deploy order (follow exactly — order matters)

1. **Backup first.** You already know this drill from the feed redesign —
   `git checkout -b backup-before-jobs-rebuild && git push origin backup-before-jobs-rebuild`

2. **Schema changes** (`01_schema_changes.py`):
   - Add the new `jobs` table to both `init_postgres_db()` and `migrate_db()`
   - Add the `job_applications`/`gifts` column migration blocks
   - Remove the old `posts`/`products` CREATE TABLE blocks from both functions

3. **Delete functions** (`04_deletions_and_edits.py` — `FUNCTIONS_TO_DELETE` list).
   Delete every function listed, in `app.py`.

4. **Add new routes** (`02_jobs_routes.py`) — paste in as a block, ideally where
   the old feed routes used to be.

5. **Replace modified routes** (`03_modified_routes.py`) — this REPLACES the
   existing `apply_to_job()`, `view_applicants()`, `send_gift()` (don't just
   add — delete the old versions of these three first).

6. **Small edits** (`04_deletions_and_edits.py` — `ADMIN_PANEL_DIFF`,
   `ADMIN_REVENUE_DIFF`, `REDIRECT_DIFF`, `PROFILE_DIFF` sections).

7. **Constants**: remove `FEED_PAGE_SIZE`, `MARKETPLACE_PAGE_SIZE`,
   `CHECKIN_REWARDS`, `TASK_REWARDS`, `DAILY_TASK_CAP` from the top of `app.py`.

8. **Templates**: copy everything in `templates/` into your `templates/` folder.
   Copy `jobs.css` to `static/css/`, `jobs-page.js` to `static/js/`. Then delete
   the old templates listed at the bottom of `05_base_html_nav_diff.py`.

9. **base.html nav**: apply the diff in `05_base_html_nav_diff.py`. **Then
   search your FULL templates folder** (not just what I've seen) for any
   remaining `url_for('feed')` / `url_for('marketplace')` / `url_for('tokens_page')`
   — the search command is at the bottom of that file.

10. **Test locally before pushing**:
    - Fresh login → should land on Jobs home, not a 404
    - Post a job → appears in the list
    - Apply to a job → applicant shows up on `view_applicants`
    - Send a gift from a job detail page → wallet balances update correctly
    - Wallet, Verification purchase, Channels, Chat — all still work untouched
    - Admin panel loads without errors (no more `products` references)

11. Push, let Render deploy, smoke-test on the live URL.

## Known gap — you'll need to decide this
The old `posts` table also fed **profile pages** (a "Posts" tab showing what a
user shared). That's removed per your decision. If you want a "Jobs Posted"
section on public profiles later, `my_jobs()`'s query pattern is the template
to reuse — just say the word and I'll wire it into `profile.html`.

## If something breaks after deploy
```
git checkout main
git reset --hard backup-before-jobs-rebuild
git push origin main --force
```
