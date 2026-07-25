# AltaJobs — Vanilla JS / Jinja2 Conversion

Plain HTML + vanilla JS versions of the 3 components you asked for (Follow,
Post Options/Share, Modal). No React, no build step, no dependencies.

## Files

```
snippets/1_feed_posts.html           → diffs to paste into _feed_posts.html
snippets/2_postcard_feed_item.html   → diffs to paste into _postcard_feed_item.html
snippets/3_feed_compose_modal.html   → diffs to paste into feed.html
snippets/4_admin_moderation.html     → paste into admin_moderation.html
static/js/altajobs-ui.js             → all the JS logic, one file
```

## Setup (one line)

Add this in `base.html`, right after your existing `app.js` script tag:

```html
<script src="{{ url_for('static', filename='js/app.js') }}" defer></script>
<script src="{{ url_for('static', filename='js/altajobs-ui.js') }}" defer></script>
```

Then apply the four snippets to their matching templates. Each snippet file
has inline comments explaining exactly what to replace vs. what to add.

## What's actually fixed, and why

**Follow button scroll-jump + "loses state on refresh"**
The jump is almost always a `<button>` with no `type` attribute sitting
inside (or next to) a `<form>`/`<a href="#">` — it silently becomes
`type="submit"` or a navigating link. Every click handler in
`altajobs-ui.js` calls `e.preventDefault()` / `e.stopPropagation()` *before*
anything else. The "loses state on refresh" part was never a bug in the
button — it was updating a CSS class locally without ever calling
`POST /api/follow/<id>`, so refreshing just showed the real (unchanged)
server state. It's fixed by actually calling that endpoint and trusting its
JSON response.

**Post menu "Cancel doesn't close it"**
This bug's signature is *two* event listeners fighting over the same
sheet — typically one inline `<script>` left in a partial, and another copy
in `app.js`. `altajobs-ui.js` is the single source of truth for
open/close; **delete the inline `<script>` block currently at the bottom of
`_feed_posts.html`** (see the note in `snippets/1_feed_posts.html`) so
there's only one.

**Native Share**
`navigator.share()` is tried first; where it's unsupported (most desktop
browsers, or plain http in dev), the code falls back to the
`#shareActionsSheet` your app already defines in `feed.html` /
`post_detail.html` — no new sheet markup needed, just wiring up the
previously-inert `#sheetCopyLinkBtn` to actually copy.

**Compose modal**
`new_post()` in `app.py` does a normal redirect (not JSON), so the modal
form is a real `<form method="POST">` — no fetch/AJAX layer was invented
where the backend doesn't have one. The three cards just set a hidden
`post_type` input before the existing multipart submit happens.

**Admin report drawer**
`/admin/report/<id>/dismiss`, `/delete-post`, and `/admin/user/<id>/ban` all
`return redirect(...)` server-side too, so the drawer's action buttons are
real forms, not fetch calls. Each report row carries its own data in a
hidden `<template>` (report content, reporter, reason, photo) so opening
the drawer needs zero extra requests.

## One thing I couldn't verify

Your last message named `admin_dashboard.html`, but `app.py`'s
`admin_moderation()` route renders `admin_moderation.html`. I built the
snippet against the real query/route in your uploaded `app.py` — if your
actual reports UI lives in a differently-named template, just paste
snippet 4 into that file instead.

Your message also cut off at point "3." — happy to keep going if there was
a third thing you wanted (the date/skeleton-loader fixes from the earlier
React pass could use a vanilla-JS version too, if that's it).
