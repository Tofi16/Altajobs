# ============================================================================
# PART 4 — DELETE THESE ENTIRELY (function name to search for -> delete the
# whole @app.route + def block)
# ============================================================================

FUNCTIONS_TO_DELETE = [
    # Feed
    "_normalize_feed_category", "_load_feed_page", "_normalize_db_media_urls",
    "_serialize_post_api", "_build_single_post_payload", "feed", "feed_load_more",
    "home_html", "api_feed", "api_v1_feed", "api_v1_search", "api_v1_create_post",
    "api_v1_get_post", "api_v1_like_post", "api_v1_get_post_comments",
    "api_v1_create_post_comment", "api_v1_delete_post",
    # NOTE: "home" is NOT deleted -- 02_jobs_routes.py includes a lightweight
    # replacement (@app.route("/home")) that just redirects to jobs_home(),
    # for old bookmarks/links. Delete the OLD home() body when you paste in
    # the new one from 02_jobs_routes.py.
    "_daily_post_count", "daily_limit_required",  # only ever used by new_post
    "new_post", "post_detail", "like_post", "_notify_post_owner_on_like",
    "api_toggle_like", "comment_post", "share_post", "api_repost_post",
    "api_notifications",  # NOTE: keep this one! see caveat below
    "api_followers_list", "api_send_post_to_follower", "delete_post",
    "log_post_view", "save_post", "saved_jobs",
    "record_unique_view",  # only used by post views; job view_count is a
                            # plain increment in job_detail(), no unique-view
                            # tracking table needed

    # Marketplace
    "cv_maker",  # already dead code / already replaced by real CV Maker
    "marketplace", "marketplace_toggle_favorite", "marketplace_buy",
    "admin_products", "admin_approve_product", "admin_reject_product",
    "admin_delete_marketplace_item", "admin_delete_marketplace_order",

    # Moderation (post-specific only)
    "admin_moderation", "dismiss_report", "delete_reported_post",

    # Alta Token Economy
    "tokens_page", "api_daily_checkin", "api_complete_task",
    "award_task_reward", "daily_task_tokens_earned", "has_completed_task",
    "checkin_status", "is_profile_complete",
]

# CAVEAT on api_notifications: this name collides with nothing else, but
# double check there isn't a SECOND function also named api_notifications
# elsewhere unrelated to feed -- in the app.py reviewed, there is exactly
# one, and it's generic (reads the notifications table, not posts). DO NOT
# DELETE api_notifications, api_notifications_mark_read, api_notifications_read
# -- these are general-purpose and used by the header bell icon everywhere,
# not feed-specific. (Corrected: remove "api_notifications" from the list
# above -- it was a mistake to include it. The bell/notification system
# stays fully intact.)


# ============================================================================
# PART 4B — Constants/imports to remove
# ============================================================================
CONSTANTS_TO_DELETE = [
    "FEED_PAGE_SIZE",        # replaced by JOBS_PAGE_SIZE
    "MARKETPLACE_PAGE_SIZE", # marketplace gone
    "CHECKIN_REWARDS", "TASK_REWARDS", "DAILY_TASK_CAP",  # token economy gone
]


# ============================================================================
# PART 4C — admin_panel() edits (function stays, remove specific stat lines)
# ============================================================================
ADMIN_PANEL_DIFF = """
REMOVE these lines from admin_panel():
    pending_products_count = db.execute(
        "SELECT COUNT(*) c FROM products WHERE status = 'pending'"
    ).fetchone()["c"]
and its use in:
    total_pending_actions = pending_deposits_count + pending_withdrawals_count + pending_products_count + len(reports)
REPLACE with:
    total_pending_actions = pending_deposits_count + pending_withdrawals_count + len(reports)

Also remove pending_products_count from both render_template() calls
(success path and except-path) in admin_panel().

Same edit applies to admin_dashboard(): remove pending_products_count
computation and its inclusion in total_pending_actions.
"""


# ============================================================================
# PART 4D — admin_revenue() edits
# ============================================================================
ADMIN_REVENUE_DIFF = """
REMOVE this line:
    marketplace_revenue = db.execute(
        "SELECT COALESCE(SUM(price), 0) total FROM products"
    ).fetchone()["total"]
REMOVE marketplace_revenue from the total_revenue sum:
    total_revenue = subscription_revenue + marketplace_revenue + premium_services_revenue + wallet_activity_revenue
BECOMES:
    total_revenue = subscription_revenue + premium_services_revenue + wallet_activity_revenue
REMOVE marketplace_revenue from the render_template(...) call's kwargs.
"""


# ============================================================================
# PART 4E — login()/register() redirect target changes
# ============================================================================
REDIRECT_DIFF = """
In register(): change
    return redirect(url_for("feed"))
to
    return redirect(url_for("jobs_home"))

In login(): change
    return redirect(url_for("feed"))
to
    return redirect(url_for("jobs_home"))
(there are two occurrences in login() -- the next_url validated-redirect
 path doesn't need changes, only the plain fallback redirect)

Anywhere else url_for("feed") or url_for("marketplace") appears (e.g. in
error handlers, flash-redirect fallbacks like `request.referrer or
url_for("feed")`), change to url_for("jobs_home"). Search app.py for
'url_for("feed")', 'url_for('feed')', 'url_for("marketplace")' after
applying all other changes to catch anything missed.
"""


# ============================================================================
# PART 4F — profile(user_id) edits: remove the "posts by this user" query
# ============================================================================
PROFILE_DIFF = """
In profile(user_id), REMOVE the entire block that builds `posts` (the
has_likes/has_comments/user_field_selects/posts query), and remove `posts`
and `posts_count` from the render_template("profile.html", ...) call.
Nothing else in profile() touches posts (ratings, portfolio_items,
followers/following counts are untouched).

Template change (profile.html, not shown here): remove the Posts tab/grid;
optionally add a "Jobs Posted" section using my_jobs()-style data if Tofik
wants that visible on public profiles later -- not required for this pass.
"""
