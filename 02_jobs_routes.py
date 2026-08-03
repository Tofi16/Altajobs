# ============================================================================
# PART 2 — NEW JOBS ROUTES
# Replaces: feed(), feed_load_more(), home_html(), api_feed(), api_v1_feed(),
# api_v1_search(), api_v1_create_post(), api_v1_get_post(), api_v1_like_post(),
# api_v1_get_post_comments(), api_v1_create_post_comment(), api_v1_delete_post(),
# home(), new_post(), post_detail(), like_post(), api_toggle_like(),
# comment_post(), share_post(), api_repost_post(), api_followers_list(),
# api_send_post_to_follower(), delete_post(), log_post_view(), save_post(),
# saved_jobs(), marketplace(), marketplace_toggle_favorite(), marketplace_buy(),
# admin_products(), admin_approve_product(), admin_reject_product(),
# admin_delete_marketplace_item(), admin_delete_marketplace_order(),
# admin_moderation(), dismiss_report(), delete_reported_post()
#
# KEPT AS-IS (not touched by this file): apply_to_job(), view_applicants()
# get small signature changes only (post_id -> job_id) — shown at the bottom.
# ============================================================================

JOBS_PAGE_SIZE = 12


def _normalize_job_category(category_value):
    if category_value is None:
        return None
    normalized = category_value.strip().lower()
    if normalized in ("all", "any", ""):
        return None
    return normalized


def _load_jobs_page(db, user, page, page_size=JOBS_PAGE_SIZE, category_filter=None, query_text=None):
    """Fetch one LIMIT/OFFSET page of open job listings. Mirrors the shape
    of the old _load_feed_page() (shared by the page load and the JSON
    'load more' endpoint) but without any like/comment/follow machinery --
    jobs are informational listings with an Apply action, not social posts."""
    offset = (page - 1) * page_size
    where_parts = ["status = 'open'"]
    params = []

    if category_filter:
        where_parts.append("category = ?")
        params.append(category_filter)

    if query_text:
        where_parts.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(location) LIKE ?)")
        like_term = f"%{query_text.lower()}%"
        params.extend([like_term, like_term, like_term])

    where_clause = "WHERE " + " AND ".join(where_parts)

    try:
        rows = db.execute(
            f"""SELECT jobs.*, users.username, users.full_name, users.avatar,
                       users.verification_tier, users.verified_until
                FROM jobs
                JOIN users ON jobs.user_id = users.id
                {where_clause}
                ORDER BY jobs.created_at DESC
                LIMIT ? OFFSET ?""",
            tuple(params + [page_size, offset]),
        ).fetchall()
    except Exception as exc:
        print(f"Warning: could not load jobs page: {exc}")
        rows = []

    job_ids = [r["id"] for r in rows]
    applied_ids = set()
    if user and job_ids:
        try:
            placeholders = ", ".join("?" for _ in job_ids)
            applied_ids = {
                r["job_id"]
                for r in db.execute(
                    f"SELECT job_id FROM job_applications WHERE applicant_id = ? AND job_id IN ({placeholders})",
                    tuple([user["id"]] + job_ids),
                ).fetchall()
            }
        except Exception:
            applied_ids = set()

    jobs_data = []
    for r in rows:
        row = dict(r)
        row.setdefault("full_name", row.get("username") or "Unknown")
        row.setdefault("avatar", None)
        row.setdefault("verification_tier", "none")
        jobs_data.append({
            "job": row,
            "poster_name": row.get("full_name") or row.get("username") or "Unknown",
            "applied": row.get("id") in applied_ids,
            "is_owner": bool(user and row.get("user_id") == user.get("id")),
        })

    has_next = len(rows) == page_size
    return jobs_data, has_next


@app.route("/home")
@login_required
def home():
    """Old bookmark/link compatibility: /home used to redirect into the
    feed. Now it just redirects to the jobs home page."""
    return redirect(url_for("jobs_home"))


@app.route("/")
@login_required
def jobs_home():
    """The app's landing page after login. Replaces the old social feed
    entirely -- this is a straightforward job-listing browse page with
    category filters and search, no likes/comments/social mechanics."""
    db = get_db()
    user = get_current_user()

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except Exception:
        page = 1

    category_filter = _normalize_job_category(request.args.get("category", "all"))
    query_text = (request.args.get("q") or "").strip()

    try:
        jobs_data, has_next = _load_jobs_page(db, user, page, JOBS_PAGE_SIZE, category_filter, query_text)
    except Exception as exc:
        print(f"Warning: jobs home load failed: {exc}")
        flash("There was a problem loading jobs. Please try again in a moment.")
        jobs_data, has_next = [], False

    return render_template(
        "jobs_home.html",
        jobs_data=jobs_data,
        has_jobs=len(jobs_data) > 0,
        page=page,
        page_size=JOBS_PAGE_SIZE,
        has_next=has_next,
        active_category=category_filter or "all",
        query_text=query_text,
        days_left=trial_days_left(user) if user else 0,
        show_trial_banner=bool(user and not _get_row_value(user, "paid_until")),
    )


@app.route("/jobs/page/<int:page>")
@login_required
def jobs_load_more(page):
    """JSON fragment endpoint for infinite-scroll/'Load more' on the jobs
    home page. Mirrors the old feed_load_more() shape."""
    if page < 1:
        page = 1
    db = get_db()
    user = get_current_user()
    category_filter = _normalize_job_category(request.args.get("category", "all"))
    query_text = (request.args.get("q") or "").strip()
    jobs_data, has_next = _load_jobs_page(db, user, page, JOBS_PAGE_SIZE, category_filter, query_text)
    html = render_template("_job_cards.html", jobs_data=jobs_data)
    return jsonify({
        "success": True,
        "html": html,
        "has_next": has_next,
        "has_jobs": len(jobs_data) > 0,
        "page": page,
    })


@app.route("/jobs/new", methods=["GET", "POST"])
@login_required
def new_job():
    """Posting a job listing. GET renders the form; POST creates it.
    No daily post limit here (that limiter existed to throttle social feed
    spam -- job postings are a core paid-value action, not something to
    rate-limit the same way)."""
    if request.method == "GET":
        return render_template("job_new.html")

    title = _sanitize_text(request.form.get("title", "")).strip()
    description = _sanitize_text(request.form.get("description", "")).strip()
    location = _sanitize_text(request.form.get("location", "Addis Ababa")).strip() or "Addis Ababa"
    category = _sanitize_text(request.form.get("category", "general")).strip() or "general"
    employment_type = _sanitize_text(request.form.get("employment_type", "full_time")).strip() or "full_time"
    salary_range = _sanitize_text(request.form.get("salary_range", "")).strip() or None

    photo_file = request.files.get("photo")
    if photo_file and photo_file.filename and not allowed_file(photo_file.filename):
        flash("Unsupported image format. Please upload PNG, JPG, JPEG, GIF, or WEBP.")
        return redirect(url_for("new_job"))
    photo = save_photo(photo_file) if photo_file and photo_file.filename else None

    if not title:
        flash("Please add a job title.")
        return redirect(url_for("new_job"))

    db = get_db()
    user = get_current_user()
    blocked_word = contains_restricted_word(f"{title} {description}", db)
    if blocked_word:
        db.execute(
            "INSERT INTO reports (reporter_id, target_type, target_id, reason, status, created_at) VALUES (?, 'job', 0, ?, 'pending', ?)",
            (user["id"], f"Blocked: contains restricted word '{blocked_word}'", datetime.datetime.utcnow().isoformat()),
        )
        add_notification(db, user["id"], f"Your job post was blocked because it contains the restricted word '{blocked_word}'.", ntype="warning")
        db.commit()
        flash("Your job post was blocked for policy review.")
        return redirect(url_for("jobs_home"))

    try:
        created_at = datetime.datetime.utcnow().isoformat()
        db.execute(
            """INSERT INTO jobs (user_id, title, description, location, category,
               employment_type, salary_range, photo, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (user["id"], title, description, location, category, employment_type,
             salary_range, photo, created_at),
        )
        db.commit()
        try:
            db.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id = ?", (10, user["id"]))
            db.commit()
        except Exception as points_exc:
            print(f"Warning: could not award job-post points: {points_exc}")
        flash("Your job listing is live.")
    except Exception as exc:
        db.rollback()
        print(f"New job post failed: {exc}")
        flash("Could not publish your job listing right now. Please try again.")
        return redirect(url_for("new_job"))

    return redirect(url_for("jobs_home"))


@app.route("/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    db = get_db()
    user = get_current_user()

    job = db.execute(
        """SELECT jobs.*, users.username, users.full_name, users.avatar,
                  users.verification_tier, users.verified_until
           FROM jobs JOIN users ON jobs.user_id = users.id
           WHERE jobs.id = ?""",
        (job_id,),
    ).fetchone()
    if not job:
        abort(404)

    try:
        db.execute("UPDATE jobs SET view_count = view_count + 1 WHERE id = ?", (job_id,))
        db.commit()
    except Exception:
        pass

    applied = db.execute(
        "SELECT 1 FROM job_applications WHERE job_id = ? AND applicant_id = ?",
        (job_id, user["id"]),
    ).fetchone() is not None

    is_owner = job["user_id"] == user["id"]

    return render_template(
        "job_detail.html",
        job=job,
        applied=applied,
        is_owner=is_owner,
    )


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
def delete_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)
    user = get_current_user()
    can_delete = bool(user and (job["user_id"] == user.get("id") or user.get("is_admin", False)))
    if not can_delete:
        abort(403)
    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    flash("Job listing removed.")
    return redirect(url_for("jobs_home"))


@app.route("/jobs/<int:job_id>/close", methods=["POST"])
@login_required
def close_job(job_id):
    """Mark a job as filled/closed without deleting it -- keeps the listing
    and its application history around, just hides it from active browsing."""
    db = get_db()
    job = db.execute("SELECT user_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)
    user = get_current_user()
    if job["user_id"] != user["id"] and not user.get("is_admin", False):
        abort(403)
    db.execute("UPDATE jobs SET status = 'closed' WHERE id = ?", (job_id,))
    db.commit()
    flash("Job listing closed.")
    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/my-jobs")
@login_required
def my_jobs():
    """Jobs the current user has posted -- replaces the old profile 'posts'
    tab with a jobs-focused equivalent."""
    db = get_db()
    user = get_current_user()
    jobs = db.execute(
        "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return render_template("my_jobs.html", jobs=jobs)


@app.route("/applied-jobs")
@login_required
def applied_jobs():
    """Jobs the current user has applied to."""
    db = get_db()
    user = get_current_user()
    rows = db.execute(
        """SELECT jobs.*, job_applications.status AS application_status,
                  job_applications.created_at AS applied_at
           FROM job_applications
           JOIN jobs ON job_applications.job_id = jobs.id
           WHERE job_applications.applicant_id = ?
           ORDER BY job_applications.created_at DESC""",
        (user["id"],),
    ).fetchall()
    return render_template("applied_jobs.html", applications=rows)
