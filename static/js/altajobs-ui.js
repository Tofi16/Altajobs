/**
 * static/js/altajobs-ui.js
 * ---------------------------------------------------------------------------
 * Vanilla JS for: Follow button, Post Options menu + native Share, the
 * Compose modal, and the Admin report drawer. Loaded once via base.html
 * (`<script src="{{ url_for('static', filename='js/app.js') }}" defer>`,
 * or add a second <script> tag for this file right after it).
 *
 * Everything here uses EVENT DELEGATION on `document` and is guarded so it
 * only binds once per page load, no matter how many times posts get
 * re-inserted by the feed's "Load More" AJAX handler. This is the same
 * pattern already used for the existing bottom-sheet code in
 * _feed_posts.html — consolidated here so there's exactly one listener per
 * behavior, which is what actually fixes bugs like "Cancel doesn't close
 * the menu" (that bug is almost always two competing listeners, not one
 * missing one).
 */
(function () {
  "use strict";

  /* ===========================================================================
     1. FOLLOW BUTTON
     ---------------------------------------------------------------------------
     BUG FIX — scroll jumps to top on click:
     Caused by the follow button being a bare <button> with no type inside a
     <form>-adjacent DOM (or an <a href="#">). A no-type <button> inside a
     <form> defaults to type="submit"; an <a href="#"> jumps to the top of
     the page. Fix: every follow chip below is type="button" AND we call
     e.preventDefault() + e.stopPropagation() before anything else, so a
     click can't bubble up to a wrapping <a href="/profile/...">  either
     (post cards commonly wrap the whole header in a profile link).

     BUG FIX — "loses state on refresh":
     This was never really a client bug: the old code updated a CSS class
     locally but never called the server, so a refresh re-rendered the true
     (unchanged) server state and looked like a "reset". The fix is that the
     click handler below calls the real endpoint
     (POST /api/follow/<user_id> -> {following: bool}) and only trusts its
     response — refreshing the page now shows the same state because the
     state was actually persisted.
     ========================================================================= */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-follow-btn");
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    if (btn.classList.contains("pending")) return;

    var userId = btn.dataset.userId;
    var followLabel = btn.dataset.followLabel || "Follow";
    var followingLabel = btn.dataset.followingLabel || "Following";
    var wasFollowing = btn.classList.contains("following");
    var nextFollowing = !wasFollowing;

    applyFollowState(btn, nextFollowing, followLabel, followingLabel);
    btn.classList.add("pending");

    fetch("/api/follow/" + userId, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("follow request failed: " + res.status);
        return res.json();
      })
      .then(function (data) {
        applyFollowState(btn, !!data.following, followLabel, followingLabel);
      })
      .catch(function (err) {
        // Roll back — don't leave the UI claiming a state the server rejected.
        applyFollowState(btn, wasFollowing, followLabel, followingLabel);
        console.error("Follow toggle failed:", err);
      })
      .finally(function () {
        btn.classList.remove("pending");
      });
  });

  function applyFollowState(btn, following, followLabel, followingLabel) {
    btn.classList.toggle("following", following);
    var labelEl = btn.querySelector(".follow-chip-label");
    var text = following ? followingLabel : followLabel;
    if (labelEl) {
      labelEl.textContent = text;
    } else {
      // Fallback for markup without a dedicated label span.
      btn.textContent = text;
    }
    btn.setAttribute("aria-pressed", following ? "true" : "false");
  }

  /* ===========================================================================
     2. POST OPTIONS MENU (⋯) — bottom sheet, single source of truth for open/close
     ---------------------------------------------------------------------------
     BUG FIX — Cancel doesn't close the menu:
     Root cause is almost always duplicate bindings (an inline <script> in a
     partial AND a copy in app.js both wiring up #sheetCancelBtn, each with
     its own stale reference to the sheet). Fix: ONE closeSheet() function,
     bound ONCE via delegation, used by Cancel, the overlay click, and
     Escape — see the notes in snippets/1_feed_posts.html about deleting the
     old inline <script> so this is the only copy left.
     ========================================================================= */
  var bottomSheetOverlay = null;
  var postActionsSheet = null;

  function openPostActionsSheet(btn) {
    bottomSheetOverlay = document.getElementById("bottomSheetOverlay");
    postActionsSheet = document.getElementById("postActionsSheet");
    var deleteForm = document.getElementById("sheetDeleteForm");
    var reportTargetId = document.getElementById("sheetReportTargetId");
    if (!bottomSheetOverlay || !postActionsSheet) return;

    if (deleteForm) deleteForm.action = btn.dataset.deleteUrl || "#";
    if (reportTargetId) reportTargetId.value = btn.dataset.postId || "";

    bottomSheetOverlay.classList.add("open");
    postActionsSheet.classList.add("open");
    document.body.classList.add("sheet-open");
  }

  function closePostActionsSheet() {
    if (bottomSheetOverlay) bottomSheetOverlay.classList.remove("open");
    if (postActionsSheet) postActionsSheet.classList.remove("open");
    document.body.classList.remove("sheet-open");
  }

  document.addEventListener("click", function (e) {
    var menuBtn = e.target.closest(".js-post-menu-btn");
    if (menuBtn) {
      openPostActionsSheet(menuBtn);
      return;
    }
    // Cancel button — this is the fix. One function, called directly.
    if (e.target.closest("#sheetCancelBtn")) {
      closePostActionsSheet();
      return;
    }
    // Clicking the dimmed backdrop also closes it.
    if (e.target.id === "bottomSheetOverlay") {
      closePostActionsSheet();
      return;
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closePostActionsSheet();
  });

  // Closing after a real form submit (delete/report) prevents a flash of an
  // open sheet while the page navigates away.
  document.addEventListener("submit", function (e) {
    if (e.target && (e.target.id === "sheetDeleteForm" || e.target.id === "sheetReportForm")) {
      closePostActionsSheet();
    }
  });

  /* ===========================================================================
     3. NATIVE SHARE — navigator.share() with clipboard-copy fallback
     ---------------------------------------------------------------------------
     Tries the OS share sheet first (mobile Safari/Chrome, some desktop
     browsers). Where it's unavailable (most desktop browsers, or non-https
     in dev), reuses the app's EXISTING #shareActionsSheet bottom sheet
     (Copy Link / Send to Follower) that feed.html and post_detail.html
     already define — no new markup required for the fallback path.
     ========================================================================= */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-native-share-btn");
    if (!btn) return;

    var url = btn.dataset.postUrl;
    var title = btn.dataset.postTitle || "AltaJobs";

    if (navigator.share) {
      navigator
        .share({ title: title, text: title, url: url })
        .catch(function (err) {
          // AbortError just means the user dismissed the native sheet.
          if (err && err.name !== "AbortError") console.error("Share failed:", err);
        });
      return;
    }

    openShareFallbackSheet(url);
  });

  function openShareFallbackSheet(url) {
    var sheet = document.getElementById("shareActionsSheet");
    if (!sheet) return;
    sheet.dataset.activeUrl = url;
    sheet.classList.add("open");
    document.body.classList.add("sheet-open");
  }

  // Wire the existing "Copy Link" button inside #shareActionsSheet to
  // actually copy (with a brief "Copied!" confirmation) instead of a no-op.
  document.addEventListener("click", function (e) {
    var copyBtn = e.target.closest("#sheetCopyLinkBtn");
    if (!copyBtn) return;
    var sheet = document.getElementById("shareActionsSheet");
    var url = sheet ? sheet.dataset.activeUrl : "";
    if (!url) return;

    navigator.clipboard
      .writeText(url)
      .then(function () {
        var original = copyBtn.innerHTML;
        copyBtn.innerHTML = "<i class='bx bx-check'></i> Copied!";
        setTimeout(function () {
          copyBtn.innerHTML = original;
          if (sheet) sheet.classList.remove("open");
          document.body.classList.remove("sheet-open");
        }, 900);
      })
      .catch(function (err) {
        console.error("Clipboard copy failed:", err);
      });
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest(".js-share-sheet-close")) {
      var sheet = document.getElementById("shareActionsSheet");
      if (sheet) sheet.classList.remove("open");
      document.body.classList.remove("sheet-open");
    }
  });

  /* ===========================================================================
     4. COMPOSE MODAL — replaces the native <select name="post_type">
     ========================================================================= */
  var COMPOSE_COPY = {
    general: "Share an update or story with your network.",
    job: "Describe the role, requirements, and how to apply.",
    skill: "What can you do? What are you looking for?",
  };
  var COMPOSE_PLACEHOLDER = {
    general: "Share an update or story...",
    job: "Describe the role, requirements, and how to apply...",
    skill: "What can you do? What are you looking for?",
  };

  function openComposeModal() {
    var overlay = document.getElementById("composeModalOverlay");
    var modal = document.getElementById("composeModal");
    if (!overlay || !modal) return;
    overlay.style.display = "block";
    modal.style.display = "block";
    document.body.classList.add("sheet-open");
    var textarea = document.getElementById("composeTextarea");
    if (textarea) textarea.focus();
  }

  function closeComposeModal() {
    var overlay = document.getElementById("composeModalOverlay");
    var modal = document.getElementById("composeModal");
    if (overlay) overlay.style.display = "none";
    if (modal) modal.style.display = "none";
    document.body.classList.remove("sheet-open");
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest("#composeTrigger")) {
      openComposeModal();
      return;
    }
    if (e.target.id === "composeModalOverlay" || e.target.closest("#composeModalClose")) {
      closeComposeModal();
      return;
    }
    var typeCard = e.target.closest(".compose-type-card");
    if (typeCard) {
      document.querySelectorAll(".compose-type-card").forEach(function (c) {
        c.classList.remove("active");
      });
      typeCard.classList.add("active");
      var type = typeCard.dataset.type;
      var hiddenInput = document.getElementById("composePostType");
      var desc = document.getElementById("composeTypeDesc");
      var textarea = document.getElementById("composeTextarea");
      if (hiddenInput) hiddenInput.value = type;
      if (desc) desc.textContent = COMPOSE_COPY[type] || "";
      if (textarea) textarea.placeholder = COMPOSE_PLACEHOLDER[type] || "";
      return;
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeComposeModal();
  });

  // Enable/disable submit + show selected filename, and auto-grow textarea —
  // same UX as the original compose box, just scoped to the modal now.
  document.addEventListener("input", function (e) {
    if (e.target.id === "composeTextarea") {
      var submitBtn = document.getElementById("composeSubmitButton");
      var hasPhoto = document.getElementById("composePhotoInput");
      var hasText = e.target.value.trim().length > 0;
      var hasFile = hasPhoto && hasPhoto.files && hasPhoto.files.length > 0;
      if (submitBtn) {
        submitBtn.disabled = !(hasText || hasFile);
        submitBtn.classList.toggle("btn-disabled", !(hasText || hasFile));
      }
    }
  });

  document.addEventListener("change", function (e) {
    if (e.target.id === "composePhotoInput") {
      var nameEl = document.getElementById("composePhotoName");
      var submitBtn = document.getElementById("composeSubmitButton");
      var file = e.target.files && e.target.files[0];
      if (nameEl) nameEl.textContent = file ? file.name : "";
      if (submitBtn && file) {
        submitBtn.disabled = false;
        submitBtn.classList.remove("btn-disabled");
      }
    }
  });

  /* ===========================================================================
     5. ADMIN REPORT DRAWER
     ---------------------------------------------------------------------------
     /admin/report/<id>/dismiss, /delete-post, and /admin/user/<id>/ban all
     `return redirect(...)` server-side — they are NOT JSON endpoints. So the
     three action buttons below are real <form> submits (the browser
     navigates/reloads on success), and the JS here only handles opening the
     drawer with the right report's data and the ban-confirm micro-interaction.
     ========================================================================= */
  document.addEventListener("click", function (e) {
    var row = e.target.closest(".js-report-row");
    if (row) {
      openReportDrawer(row.dataset.reportId);
      return;
    }
    if (e.target.id === "reportDrawerOverlay" || e.target.closest("#reportDrawerClose")) {
      closeReportDrawer();
      return;
    }
    if (e.target.closest("#reportBanTrigger")) {
      var confirmBox = document.getElementById("reportBanConfirm");
      if (confirmBox) confirmBox.style.display = "block";
      return;
    }
    if (e.target.closest("#reportBanCancel")) {
      var confirmBox2 = document.getElementById("reportBanConfirm");
      if (confirmBox2) confirmBox2.style.display = "none";
      return;
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeReportDrawer();
  });

  function openReportDrawer(reportId) {
    var template = document.querySelector(
      '.js-report-data[data-report-id="' + reportId + '"]'
    );
    if (!template) return;
    var content = template.content || template; // <template> support fallback

    var get = function (field) {
      var el = content.querySelector('[data-field="' + field + '"]');
      return el ? el.textContent.trim() : "";
    };

    document.getElementById("reportDrawerId").textContent = reportId;
    document.getElementById("reportDrawerReporter").textContent = "@" + get("reporter");
    document.getElementById("reportDrawerDate").textContent = formatAdminDate(get("reported_at"));
    document.getElementById("reportDrawerReason").textContent = get("reason");
    document.getElementById("reportDrawerAuthor").textContent = get("post_author") || "unknown";

    var hasPost = get("has_post") === "1";
    var contentEl = document.getElementById("reportDrawerContent");
    var noPostEl = document.getElementById("reportDrawerNoPost");
    var photoEl = document.getElementById("reportDrawerPhoto");

    if (hasPost) {
      contentEl.style.display = "block";
      contentEl.textContent = get("post_content") || "(no text content)";
      noPostEl.style.display = "none";
    } else {
      contentEl.style.display = "none";
      noPostEl.style.display = "block";
    }

    var photoUrl = get("post_photo");
    if (photoUrl) {
      photoEl.src = photoUrl;
      photoEl.style.display = "block";
    } else {
      photoEl.style.display = "none";
    }

    document.getElementById("reportDismissForm").action = "/admin/report/" + reportId + "/dismiss";
    var deleteForm = document.getElementById("reportDeleteForm");
    deleteForm.action = "/admin/report/" + reportId + "/delete-post";
    document.getElementById("reportDeleteBtn").disabled = !hasPost;

    var authorId = get("author_id");
    document.getElementById("reportBanForm").action = authorId ? "/admin/user/" + authorId + "/ban" : "#";
    document.getElementById("reportBanUsername").textContent = "@" + (get("post_author") || "user");
    var banWrap = document.getElementById("reportBanWrap");
    banWrap.style.display = authorId ? "block" : "none";
    document.getElementById("reportBanConfirm").style.display = "none";

    document.getElementById("reportDrawerOverlay").style.display = "block";
    document.getElementById("reportDrawer").style.display = "block";
    document.body.classList.add("sheet-open");
  }

  function closeReportDrawer() {
    var overlay = document.getElementById("reportDrawerOverlay");
    var drawer = document.getElementById("reportDrawer");
    if (overlay) overlay.style.display = "none";
    if (drawer) drawer.style.display = "none";
    document.body.classList.remove("sheet-open");
  }

  function formatAdminDate(value) {
    if (!value) return "";
    var normalized = /\dT\d/.test(value) ? value : value.replace(" ", "T");
    if (!/Z$/.test(normalized)) normalized += "Z";
    var d = new Date(normalized);
    if (isNaN(d.getTime())) return value;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
})();
