# Dependency Map: what touches `posts` / `products` in app.py

## Routes that are PURELY feed/marketplace (safe to delete entirely)
- feed(), feed_load_more(), home_html(), api_feed(), api_v1_feed(), api_v1_search()
- api_v1_create_post(), api_v1_get_post(), api_v1_like_post(), api_v1_get_post_comments(),
  api_v1_create_post_comment(), api_v1_delete_post()
- home(), new_post(), post_detail(), like_post(), api_toggle_like(), comment_post(),
  share_post(), api_repost_post(), api_followers_list(), api_send_post_to_follower()
- delete_post(), log_post_view(), save_post(), saved_jobs()
- coming_soon() -- generic, but only linked from feed; check usage first
- cv_maker() [dead code, already handled separately]
- marketplace(), marketplace_toggle_favorite(), marketplace_buy()
- admin_products(), admin_approve_product(), admin_reject_product(),
  admin_delete_marketplace_item(), admin_delete_marketplace_order()
- admin_moderation(), dismiss_report(), delete_reported_post() [post-specific; report
  system itself is more general -- KEEP reports table/route, just remove post-specific
  moderation UI pieces]

## Routes that TOUCH posts but serve JOBS (must be preserved, ported to `jobs` table)
- apply_to_job(post_id) -- becomes apply_to_job(job_id)
- view_applicants(post_id) -- becomes view_applicants(job_id)
- job_applications table already has post_id FK -- rename to job_id, point at jobs.id

## Shared systems that reference posts.id but must NOT be deleted (keep tables, adjust FK usage)
- gifts.post_id -- REPOINTED to jobs.id (renamed gifts.job_id). Gift sending stays,
  now tied to job listings (tip/support the job poster from a job listing page)
  instead of feed posts. Column rename: post_id -> job_id, FK -> jobs(id) ON DELETE SET NULL.
- reports.target_type/target_id -- generic (works for 'post', 'user', 'job', etc).
  KEEP reports system as-is; 'post' target_type simply won't be created anymore.
  Admin moderation UI for posts goes away with admin_moderation().
- notifications -- generic message table, not FK'd to posts. No change needed.
- token_transactions / Alta Token Economy -- ENTIRE SYSTEM REMOVED per decision:
  tokens_page(), api_daily_checkin(), api_complete_task(), award_task_reward(),
  daily_task_tokens_earned(), has_completed_task(), checkin_status(),
  is_profile_complete(), CHECKIN_REWARDS, TASK_REWARDS, DAILY_TASK_CAP constants,
  token_transactions table, and users.alta_tokens/last_checkin/current_streak columns
  (columns can stay unused in DB -- SQLite/Postgres ALTER DROP COLUMN is messy and
  not worth the risk; just stop reading/writing them). Any wallet page reference to
  "Alta Tokens" balance display should be removed too (api_wallet_balance still
  returns alta_tokens for backward compat but the UI won't show it).
- verification badges (verification_badge_svg, get_verification_tier) -- rendered
  inside post cards but ALSO on profile pages, job posts, channels. NOT feed-specific.
  KEEP entirely.
- channels/channel_messages -- fully independent system, not FK'd to posts. No change.
- admin_panel() overview stats -- references pending_products_count, gift_earnings
  (fine, gifts stay), does NOT reference posts directly for its core stats. Minor
  edit: remove pending_products_count references since products table goes away.
- admin_revenue() -- references marketplace_revenue (SUM of products.price). Remove
  that line; keep verification_revenue, gift_earnings, subscription_revenue.
- profile(user_id) -- displays a user's posts on their profile page. This entire
  "posts by this user" section is removed from the profile template; profile keeps
  ratings, portfolio_items, experiences, education (none of which touch posts).
- _get_table_columns / _table_exists / _table_has_column -- generic helpers, no change.

## Database schema changes
### DROP (or stop creating) entirely:
- posts, likes, comments, saved_posts, post_views, product_photos, product_favorites,
  offers, products

### KEEP as-is:
- users, wallets, wallet_transactions, bank_accounts, gifts, follows, notifications,
  announcements, announcement_views, reports, ratings, channels, channel_members,
  channel_messages, channel_message_reactions, token_transactions, challenge_*,
  winner_trust, payments, restricted_words, portfolio_items, experiences, education,
  skill_endorsements, cv_documents, admin_revenue_withdrawals

### NEW:
- jobs (replaces posts for job listings; no likes/comments; has apply flow)
- job_applications gets its FK renamed post_id -> job_id (pointing at jobs.id)

## Additional routes REMOVED (Alta Token Economy)
- tokens_page(), api_daily_checkin(), api_complete_task()

## Routes MODIFIED (not removed) — gift system repointed at jobs
- send_gift() -- receiver_id stays user-based; post_id param renamed job_id,
  now validates against jobs table instead of posts
- Gift UI (post_detail.html gift box) moves to job_detail.html

## Navigation / template references to fix
- base.html: any nav link to url_for('feed'), url_for('marketplace') -> remove or
  repoint to url_for('jobs_home')
- login()/register(): redirect(url_for('feed')) -> redirect(url_for('jobs_home'))
- login_required wrapper comment about "Home/Feed" -> update wording only, no functional change
- new_post()/daily_limit_required decorator -- only used by new_post(); removed together
