# ============================================================================
# PART 5 — base.html NAV DIFF
# ============================================================================

BASE_HTML_DIFF = """
1) Brand logo link (line ~123):

CHANGE:
    <a href="{{ url_for('feed') }}" class="brand brand-logo" aria-label="AltaJobs home">
TO:
    <a href="{{ url_for('jobs_home') }}" class="brand brand-logo" aria-label="AltaJobs home">


2) Bottom nav "Home" tab (line ~291-293):

CHANGE:
    <a href="{{ url_for('feed') }}" class="nav-tab {{ 'active' if request.path == '/' or request.path.startswith('/post/') or request.path.startswith('/saved') }}">
        <i class='bx {{ "bxs-home" if request.path == "/" else "bx-home" }}'></i>
        <span>{{ t.tab_home }}</span>
TO:
    <a href="{{ url_for('jobs_home') }}" class="nav-tab {{ 'active' if request.path == '/' or request.path.startswith('/jobs') }}">
        <i class='bx {{ "bxs-home" if request.path == "/" else "bx-home" }}'></i>
        <span>{{ t.tab_home }}</span>


3) Bottom nav "Market" tab (line ~302-305) — REPLACE ENTIRELY with a
   "CV Maker" tab, since Marketplace is gone and CV Maker is now a primary
   feature that deserves its own nav slot:

REMOVE:
    <a href="{{ url_for('marketplace') }}" class="nav-tab {{ 'active' if request.path.startswith('/marketplace') }}">
        <i class='bx {{ "bxs-store" if request.path.startswith("/marketplace") else "bx-store" }}'></i>
        <span>Market</span>
    </a>

REPLACE WITH:
    <a href="{{ url_for('cv_maker_page') }}" class="nav-tab {{ 'active' if request.path.startswith('/cv-maker') }}">
        <i class='bx {{ "bxs-file-blank" if request.path.startswith("/cv-maker") else "bx-file-blank" }}'></i>
        <span>CV</span>
    </a>


4) Anywhere else in base.html that references url_for('feed'),
   url_for('marketplace'), url_for('tokens_page'), or url_for('saved_jobs')
   -- search the file after applying the above 3 changes and fix any
   remaining occurrences the same way:
   - feed -> jobs_home
   - marketplace -> (remove, or point at cv_maker_page if it's a stray link)
   - tokens_page -> (remove entirely, Alta Token Economy is gone)
   - saved_jobs -> my_jobs or applied_jobs, whichever fits the link's label
     (the old "Saved" concept doesn't map 1:1 -- if there was a "Saved
     jobs" bookmark-style feature, that's a different concept from "my
     jobs I posted"/"jobs I applied to". Recommend pointing any "Saved"
     link at applied_jobs() since that's the closest equivalent -- a list
     of jobs the user has a relationship with.)


5) IMPORTANT CAVEAT — template coverage:
   I only have direct visibility into base.html, feed.html, post_detail.html,
   _feed_posts.html, and _postcard_feed_item.html from this conversation.
   Your full templates/ folder almost certainly has MORE files that link to
   feed/marketplace/tokens (e.g. tokens.html itself, admin.html, settings.html,
   create_menu.html, coming_soon.html). Before deploying, run this search
   across your ENTIRE templates/ folder and fix every hit the same way as
   above:

       grep -rn "url_for('feed')\\|url_for(\"feed\")\\|url_for('marketplace')\\|url_for(\"marketplace\")\\|url_for('tokens_page')\\|url_for(\"tokens_page\")" templates/

   Also delete these template files entirely (their routes no longer exist):
       templates/feed.html, templates/_feed_posts.html,
       templates/_postcard_feed_item.html, templates/post_detail.html,
       templates/marketplace.html, templates/_marketplace_cards.html,
       templates/tokens.html, templates/admin_products.html,
       templates/admin_moderation.html
"""
