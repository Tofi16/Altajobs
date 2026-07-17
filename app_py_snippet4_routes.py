# ---------------------------------------------------------------------------
# REPLACE the entire existing:
#     @app.route("/cv-maker", methods=["GET", "POST"])
#     @login_required
#     def cv_maker(): ...
# function with the version below, and ADD the new
# cv_headshot_studio() route directly after it.
# ---------------------------------------------------------------------------

@app.route("/cv-maker", methods=["GET", "POST"])
@login_required
def cv_maker():
    payload = None
    user = get_current_user()

    tier = request.values.get("tier", "standard")
    if tier not in CV_TIERS:
        tier = "standard"
    template_key = request.values.get("template_key", "classic")
    if template_key not in CV_TEMPLATES:
        template_key = "classic"

    if request.method == "POST":
        tier = request.form.get("tier", "standard")
        if tier not in CV_TIERS:
            tier = "standard"
        template_key = request.form.get("template_key", "classic")
        if template_key not in CV_TEMPLATES:
            template_key = "classic"

        tier_info = CV_TIERS[tier]
        price = tier_info["price"]

        if user["wallet_balance"] < price:
            flash(f"Insufficient wallet balance - the {tier_info['label']} costs {price} ETB.")
            return redirect(url_for("wallet"))

        # a photo already uploaded via the Headshot Studio step is passed
        # through as a hidden field so we don't require re-uploading it here
        existing_photo_field = (request.form.get("existing_photo") or "").strip()
        uploaded_photo = save_cv_photo(request.files.get("photo"))
        photo = uploaded_photo or existing_photo_field or None

        payload = _generate_cv_payload(
            request.form, photo=photo, want_cover_letter=tier_info["cover_letter"]
        )
        payload["tier"] = tier
        payload["tier_label"] = tier_info["label"]
        payload["template_key"] = template_key
        payload["priority_badge"] = tier_info["priority_badge"]

        db = get_db()
        if getattr(db, "is_sqlite", False):
            db.execute("BEGIN IMMEDIATE")
        try:
            # Conditional UPDATE keeps this atomic/race-safe, same pattern
            # used everywhere else wallet balances are debited.
            cur = db.execute(
                "UPDATE users SET wallet_balance = wallet_balance - ? "
                "WHERE id = ? AND wallet_balance >= ?",
                (price, user["id"], price),
            )
            if cur.rowcount == 0:
                db.rollback()
                flash(f"Insufficient wallet balance - the {tier_info['label']} costs {price} ETB.")
                return redirect(url_for("wallet"))

            db.execute(
                """INSERT INTO cv_documents
                   (user_id, full_name, target_role, summary, experience,
                    achievements, skills, photo, tier, template_key,
                    cover_letter, priority_badge, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user["id"], payload["full_name"], payload["target_role"],
                    payload["summary"], payload["experience"],
                    "\n".join(payload["achievements"]), ", ".join(payload["skills"]),
                    photo, tier, template_key, payload["cover_letter"],
                    1 if tier_info["priority_badge"] else 0,
                    datetime.datetime.utcnow().isoformat(),
                ),
            )

            if tier_info["priority_badge"]:
                db.execute("UPDATE users SET priority_badge = 1 WHERE id = ?", (user["id"],))

            db.commit()
            flash(f"{tier_info['label']} generated! Your wallet balance has been updated.")
        except Exception:
            db.rollback()
            raise

    return render_template(
        "cv_maker.html",
        payload=payload,
        cv_tiers=CV_TIERS,
        cv_templates=CV_TEMPLATES,
        selected_tier=tier,
        selected_template=template_key,
        gemini_enabled=bool(GEMINI_API_KEY),
    )


@app.route("/cv-maker/headshot", methods=["POST"])
@login_required
def cv_headshot_studio():
    """AI Headshot Studio upload step. NOTE: this currently just stores the
    photo as-is - it does NOT yet perform background removal/replacement.
    That requires wiring up a real image-editing service (e.g. remove.bg or
    a Gemini image-editing model); until that's configured this endpoint is
    a plain upload+preview step so the rest of the flow works end-to-end."""
    file_storage = request.files.get("photo")
    if not file_storage or file_storage.filename == "":
        return {"error": "no_photo"}, 400
    photo = save_cv_photo(file_storage)
    if not photo:
        return {"error": "invalid_photo"}, 400
    return {
        "photo": photo,
        "photo_url": photo_url(photo),
        "background_replaced": False,
    }
