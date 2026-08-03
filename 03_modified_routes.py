# ============================================================================
# PART 3 — MODIFIED EXISTING ROUTES (job_id instead of post_id)
# These REPLACE the current apply_to_job(), view_applicants(), send_gift()
# in app.py. Logic is otherwise identical to the originals.
# ============================================================================

@app.route("/jobs/<int:job_id>/apply", methods=["POST"])
@login_required
def apply_to_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job or job["status"] != "open":
        abort(404)
    if job["user_id"] == session["user_id"]:
        return redirect(request.referrer or url_for("jobs_home"))

    message = request.form.get("message", "").strip()
    existing = db.execute(
        "SELECT id FROM job_applications WHERE job_id = ? AND applicant_id = ?",
        (job_id, session["user_id"]),
    ).fetchone()
    if existing:
        flash("already_applied")
    else:
        db.execute(
            """INSERT INTO job_applications (job_id, applicant_id, message, created_at)
               VALUES (?, ?, ?, ?)""",
            (job_id, session["user_id"], message, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        add_notification(
            db, job["user_id"],
            f"You have a new applicant for '{job['title']}'.",
            ntype="info",
        )
        db.commit()
        flash("application_submitted")
    return redirect(request.referrer or url_for("job_detail", job_id=job_id))


@app.route("/jobs/<int:job_id>/applicants")
@login_required
def view_applicants(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        abort(404)
    if job["user_id"] != session["user_id"] and not get_current_user()["is_admin"]:
        abort(403)
    applicants = db.execute(
        """SELECT job_applications.*, users.username, users.full_name, users.avatar,
                  users.verification_tier, users.verified_until
           FROM job_applications JOIN users ON job_applications.applicant_id = users.id
           WHERE job_id = ? ORDER BY job_applications.created_at DESC""",
        (job_id,),
    ).fetchall()
    return render_template("job_applicants.html", job=job, applicants=applicants)


# ----------------------------------------------------------------------------
# Gift sending, repointed at jobs instead of posts. receiver_id logic is
# unchanged (gifts always go to a user); job_id is now optional context
# for "which job listing were you looking at when you sent this gift"
# instead of post_id.
# ----------------------------------------------------------------------------
@app.route("/gift/send", methods=["POST"])
@login_required
def send_gift():
    receiver_id = int(request.form.get("receiver_id"))
    gift_key = request.form.get("gift_key")
    job_id = request.form.get("job_id")
    sender = get_current_user()

    gift = GIFT_CATALOG.get(gift_key)
    if not gift or receiver_id == sender["id"]:
        return redirect(request.referrer or url_for("jobs_home"))

    price = gift["price"]
    platform_cut = round(price * PLATFORM_CUT_PERCENT / 100)
    receiver_share = price - platform_cut

    db = get_db()
    if getattr(db, "is_sqlite", False):
        db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            "UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ? AND wallet_balance >= ?",
            (price, sender["id"], price),
        )
        if cur.rowcount == 0:
            db.rollback()
            flash("insufficient_balance")
            return redirect(request.referrer or url_for("jobs_home"))

        db.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                   (receiver_share, receiver_id))
        db.execute(
            """INSERT INTO gifts (sender_id, receiver_id, gift_key, amount, platform_cut, job_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sender["id"], receiver_id, gift_key, price, platform_cut,
             job_id if job_id else None, datetime.datetime.utcnow().isoformat()),
        )
        db.commit()
        add_notification(
            db, receiver_id,
            f"{sender['full_name'] or sender['username']} sent you a {gift.get('emoji','🎁')} gift ({price} ETB).",
            ntype="gift",
        )
        db.commit()
        flash("gift_sent")
    except Exception:
        db.rollback()
        raise
    return redirect(request.referrer or url_for("jobs_home"))


# ----------------------------------------------------------------------------
# submit_report() itself needs NO changes -- target_type/target_id stay
# generic. Just note that target_type will now be 'job' instead of 'post'
# when reporting a listing (the report form's hidden input value changes
# in job_detail.html, not in the route).
# ----------------------------------------------------------------------------
