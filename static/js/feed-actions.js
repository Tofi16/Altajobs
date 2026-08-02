/**
 * AltaJobs — feed-actions.js
 * Handles all feed post interactions: like, follow, comment drawer,
 * repost, share, save, post menu (copy link / share / report / delete),
 * see-more/less, and the notification badge poll.
 *
 * Talks to the existing JSON endpoints in app.py:
 *   POST /api/like/:id
 *   POST /api/follow/:id
 *   GET  /api/v1/posts/:id/comments
 *   POST /api/v1/posts/:id/comments
 *   POST /api/post/:id/repost
 *   POST /post/:id/save
 *   GET  /api/notifications
 *
 * This file is the single source of truth for feed interaction JS —
 * it replaces the previously duplicated handlers that lived inline in
 * feed.html.
 */
(function () {
  'use strict';

  /* ─── Fetch helpers ───────────────────────────────────────────── */

  function post(url) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    });
  }

  function postJson(url, body) {
    var opts = {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function (r) {
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('application/json') === -1) return {};
      return r.json();
    });
  }

  /* ─── Toast (shared with feed.js; safe if feed.js loads first or not at all) ─── */

  function ensureToastContainer() {
    var el = document.getElementById('toastContainer');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toastContainer';
      document.body.appendChild(el);
    }
    return el;
  }

  function showToast(message, type) {
    var container = ensureToastContainer();
    var t = document.createElement('div');
    t.className = 'toast ' + (type === 'error' ? 'error' : 'success');
    var accent = document.createElement('div');
    accent.className = 'toast-accent';
    var content = document.createElement('div');
    content.style.flex = '1';
    content.textContent = message;
    t.appendChild(accent);
    t.appendChild(content);
    container.appendChild(t);
    requestAnimationFrame(function () { t.style.opacity = '1'; t.style.transform = 'translateY(0)'; });
    setTimeout(function () {
      t.classList.add('hide');
      setTimeout(function () { t.remove(); }, 320);
    }, 2600);
    return t;
  }

  if (!window.showToast) window.showToast = showToast;
  window.show_toast = window.showToast;

  /* ─── Like ────────────────────────────────────────────────────── */

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-like-btn, [data-action="like"]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    var postId = btn.dataset.postId;
    if (!postId || btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';

    post('/api/like/' + postId)
      .then(function (r) {
        if (!r.ok) throw new Error('like_request_failed');
        return r.json();
      })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        btn.classList.toggle('liked', !!data.liked);
        btn.setAttribute('aria-pressed', String(!!data.liked));
        var countEl = btn.querySelector('.like-count, .count');
        if (countEl) countEl.textContent = data.like_count;
        if (data.liked) {
          btn.classList.add('just-liked');
          setTimeout(function () { btn.classList.remove('just-liked'); }, 420);
        }
      })
      .catch(function () {
        window.showToast('Could not update like. Try again.', 'error');
      })
      .finally(function () {
        delete btn.dataset.inflight;
      });
  });

  /* ─── Follow ──────────────────────────────────────────────────── */

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-follow-btn, [data-action="follow"]');
    if (!btn) return;
    e.preventDefault();
    if (btn.closest('form')) return; // let plain <form> follow buttons submit normally
    e.stopPropagation();

    var scrollX = window.scrollX;
    var scrollY = window.scrollY;
    btn.blur();
    window.scrollTo(scrollX, scrollY);
    requestAnimationFrame(function () { window.scrollTo(scrollX, scrollY); });

    var userId = btn.dataset.userId;
    if (!userId || btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';
    btn.disabled = true;

    var labelEl = btn.querySelector('.follow-label') || btn;
    var wasFollowing = btn.classList.contains('following');
    var followLabel = btn.dataset.followLabel || 'Follow';
    var followingLabel = btn.dataset.followingLabel || 'Unfollow';

    post('/api/follow/' + userId)
      .then(function (r) {
        if (!r.ok) throw new Error('network');
        var ct = r.headers.get('content-type') || '';
        if (ct.indexOf('application/json') === -1) {
          return r.text().then(function () { throw new Error('invalid_response'); });
        }
        return r.json();
      })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        var isFollowing = !!data.following;

        var followerCountEl = document.querySelector('[data-followers-count]');
        if (followerCountEl && typeof data.followers_count !== 'undefined') {
          followerCountEl.textContent = data.followers_count;
        }

        // Sync every follow button for this user across the page (feed can
        // show the same author multiple times).
        document.querySelectorAll(
          '.js-follow-btn[data-user-id="' + userId + '"], [data-action="follow"][data-user-id="' + userId + '"]'
        ).forEach(function (b) {
          b.classList.toggle('following', isFollowing);
          b.setAttribute('aria-pressed', String(isFollowing));
          var lbl = b.querySelector('.follow-label') || b;
          lbl.textContent = isFollowing ? followingLabel : followLabel;
        });
      })
      .catch(function () {
        btn.classList.toggle('following', wasFollowing);
        labelEl.textContent = wasFollowing ? followingLabel : followLabel;
        window.showToast('Could not update follow. Try again.', 'error');
      })
      .finally(function () {
        btn.disabled = false;
        delete btn.dataset.inflight;
      });
  });

  /* ─── Save ────────────────────────────────────────────────────── */

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-save-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    var postId = btn.dataset.postId;
    if (!postId || btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';
    btn.disabled = true;

    var wasSaved = btn.classList.contains('saved');

    post('/post/' + postId + '/save')
      .then(function (r) {
        if (!r.ok) throw new Error('network');
        btn.classList.toggle('saved', !wasSaved);
        btn.setAttribute('aria-pressed', String(!wasSaved));
      })
      .catch(function () {
        btn.classList.toggle('saved', wasSaved);
        btn.setAttribute('aria-pressed', String(wasSaved));
        window.showToast('Could not update save state.', 'error');
      })
      .finally(function () {
        btn.disabled = false;
        delete btn.dataset.inflight;
      });
  });

  /* ─── Repost ──────────────────────────────────────────────────── */
  /* The .js-repost-btn click is handled by app.js, which opens the
     "Send to chat / followers" modal (#repostModal) — a richer flow than
     a plain instant-increment counter. feed-actions.js intentionally does
     not bind a competing handler here. */

  /* ─── Share ───────────────────────────────────────────────────── */
  /* The .js-share-btn click is handled by app.js, which opens the
     "Copy Link / Send to Follower list" bottom sheet (#shareActionsSheet).
     feed-actions.js intentionally does not bind a competing handler here. */

  /* ─── Post menu (copy link / share / report / delete) ───────────── */

  document.addEventListener('pointerdown', function (e) {
    var toggle = e.target.closest('[data-action="toggle-menu"]');
    if (toggle) toggle.blur();
  }, true);

  document.addEventListener('click', function (e) {
    var toggleBtn = e.target.closest('[data-action="toggle-menu"]');
    if (toggleBtn) {
      e.preventDefault();
      e.stopPropagation();
      var dropdown = toggleBtn.closest('[data-dropdown]');
      if (!dropdown) return;
      var menu = dropdown.querySelector('[data-dropdown-menu]');
      if (!menu) return;
      var isOpen = menu.classList.contains('open');
      closeAllPostMenus();
      if (!isOpen) {
        menu.classList.add('open');
        menu.setAttribute('aria-hidden', 'false');
        toggleBtn.setAttribute('aria-expanded', 'true');
      }
      return;
    }
    if (!e.target.closest('[data-dropdown]')) {
      closeAllPostMenus();
    }
  });

  function closeAllPostMenus() {
    document.querySelectorAll('.feed-card__menu.open').forEach(function (menu) {
      menu.classList.remove('open');
      menu.setAttribute('aria-hidden', 'true');
    });
    document.querySelectorAll('[data-action="toggle-menu"]').forEach(function (btn) {
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  document.addEventListener('click', function (e) {
    var copyBtn = e.target.closest('.js-post-copy-link');
    if (!copyBtn) return;
    e.preventDefault();
    e.stopPropagation();
    var url = copyBtn.dataset.postUrl || '';
    if (!url || !navigator.clipboard) {
      window.showToast('Could not copy link', 'error');
      return;
    }
    navigator.clipboard.writeText(url)
      .then(function () { window.showToast('Link copied', 'success'); })
      .catch(function () { window.showToast('Could not copy link', 'error'); });
    closeAllPostMenus();
  });

  document.addEventListener('click', function (e) {
    var reportBtn = e.target.closest('[data-action="report-post"]');
    if (!reportBtn) return;
    e.preventDefault();
    e.stopPropagation();
    if (window.openReportDrawer) window.openReportDrawer('post', reportBtn.dataset.postId);
    closeAllPostMenus();
  });

  /* ─── Comments drawer ─────────────────────────────────────────── */

  var commentsDrawer = document.getElementById('feedCommentsDrawer');
  var commentsBackdrop = document.getElementById('feedCommentsBackdrop');
  var commentsList = document.getElementById('feedCommentsList');
  var commentsInput = document.getElementById('feedCommentsInput');
  var commentsSendBtn = document.getElementById('feedCommentsSendBtn');
  var commentsSubtitle = document.getElementById('feedCommentsSubtitle');
  var commentsCloseBtn = document.getElementById('feedCommentsCloseBtn');
  var activeCommentPostId = null;

  function setCommentsDrawerOpen(open) {
    if (!commentsDrawer || !commentsBackdrop) return;
    commentsDrawer.classList.toggle('open', !!open);
    commentsDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    commentsBackdrop.hidden = !open;
    document.body.classList.toggle('no-scroll', !!open);
  }

  function renderCommentsSkeletons() {
    if (!commentsList) return;
    commentsList.innerHTML = [
      '<div class="feed-comment-skeleton"><div class="feed-skeleton__avatar"></div><div style="flex:1"><div class="feed-skeleton__line"></div><div class="feed-skeleton__line short"></div></div></div>',
      '<div class="feed-comment-skeleton"><div class="feed-skeleton__avatar"></div><div style="flex:1"><div class="feed-skeleton__line"></div><div class="feed-skeleton__line short"></div></div></div>',
    ].join('');
  }

  function renderEmptyComments() {
    if (!commentsList) return;
    commentsList.innerHTML = '<div class="feed-empty-state" style="padding:1rem;">No comments yet. Start the conversation.</div>';
  }

  function renderCommentsList(comments) {
    if (!commentsList) return;
    if (!comments || !comments.length) {
      renderEmptyComments();
      return;
    }
    var html = '';
    comments.forEach(function (comment) {
      var name = comment.full_name || comment.username || 'You';
      var initials = (name || 'Y').split(/\s+/).slice(0, 2).map(function (part) { return part.charAt(0).toUpperCase(); }).join('');
      var when = formatTime(comment.created_at);
      html += '<div class="feed-comment"><div class="feed-comment__avatar">' + escapeHtml(initials || 'Y') + '</div>' +
        '<div class="feed-comment__body"><div class="feed-comment__meta"><strong>' + escapeHtml(name) + '</strong><span>' + escapeHtml(when || '') + '</span></div>' +
        '<p>' + escapeHtml(comment.content || '') + '</p></div></div>';
    });
    commentsList.innerHTML = html;
  }

  function openCommentsDrawer(postId) {
    if (!commentsDrawer || !commentsBackdrop || !postId) return;
    activeCommentPostId = postId;
    setCommentsDrawerOpen(true);
    if (commentsSubtitle) commentsSubtitle.textContent = 'Loading comments…';
    renderCommentsSkeletons();
    if (commentsInput) commentsInput.value = '';

    fetch('/api/v1/posts/' + postId + '/comments?limit=20', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.comments) {
          renderCommentsList(data.comments);
          if (commentsSubtitle) {
            var n = data.comments.length || 0;
            commentsSubtitle.textContent = n + ' comment' + (n === 1 ? '' : 's');
          }
        } else {
          renderEmptyComments();
          if (commentsSubtitle) commentsSubtitle.textContent = 'No comments yet';
        }
      })
      .catch(function () {
        renderEmptyComments();
        if (commentsSubtitle) commentsSubtitle.textContent = 'Unable to load comments';
        window.showToast('Could not load comments right now.', 'error');
      });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-comment-toggle');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    openCommentsDrawer(btn.dataset.postId);
  });

  if (commentsCloseBtn) {
    commentsCloseBtn.addEventListener('click', function () {
      setCommentsDrawerOpen(false);
      activeCommentPostId = null;
    });
  }

  if (commentsBackdrop) {
    commentsBackdrop.addEventListener('click', function () {
      setCommentsDrawerOpen(false);
      activeCommentPostId = null;
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && commentsDrawer && commentsDrawer.classList.contains('open')) {
      setCommentsDrawerOpen(false);
      activeCommentPostId = null;
    }
  });

  function submitComment() {
    if (!activeCommentPostId || !commentsInput || !commentsInput.value.trim()) return;
    var content = commentsInput.value.trim();
    commentsInput.value = '';
    if (commentsSendBtn) commentsSendBtn.disabled = true;

    fetch('/api/v1/posts/' + activeCommentPostId + '/comments', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ content: content }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.success) throw new Error('failed');
        var commentItem = document.createElement('div');
        commentItem.className = 'feed-comment';
        commentItem.innerHTML = '<div class="feed-comment__avatar">YO</div>' +
          '<div class="feed-comment__body"><div class="feed-comment__meta"><strong>You</strong><span>just now</span></div>' +
          '<p>' + escapeHtml(content) + '</p></div>';
        if (commentsList) {
          if (!commentsList.querySelector('.feed-comment')) commentsList.innerHTML = '';
          commentsList.insertBefore(commentItem, commentsList.firstChild);
        }
        var countEl = document.querySelector('.js-comment-toggle[data-post-id="' + activeCommentPostId + '"] .comment-count');
        if (countEl && data.comment_count !== undefined) countEl.textContent = data.comment_count;
        if (commentsSubtitle && data.comment_count !== undefined) {
          commentsSubtitle.textContent = data.comment_count + ' comment' + (data.comment_count === 1 ? '' : 's');
        }
      })
      .catch(function () {
        window.showToast('Could not post comment. Try again.', 'error');
      })
      .finally(function () {
        if (commentsSendBtn) commentsSendBtn.disabled = false;
      });
  }

  if (commentsSendBtn) commentsSendBtn.addEventListener('click', submitComment);
  if (commentsInput) {
    commentsInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitComment();
      }
    });
  }

  /* ─── See more / see less ─────────────────────────────────────── */

  function refreshSeeMoreButtons() {
    document.querySelectorAll('.js-xpost-content').forEach(function (el) {
      var btn = el.nextElementSibling;
      if (!btn || !btn.classList.contains('js-xpost-seemore')) return;
      btn.classList.toggle('hidden', el.scrollHeight <= el.clientHeight + 2);
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-xpost-seemore');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var content = btn.previousElementSibling;
    if (!content) return;
    var expanded = content.classList.toggle('feed-card__content--clamped');
    btn.textContent = expanded ? (btn.dataset.seeMore || 'See more') : (btn.dataset.seeLess || 'See less');
  });

  window.refreshPostSeeMoreButtons = refreshSeeMoreButtons;
  document.addEventListener('DOMContentLoaded', refreshSeeMoreButtons);

  /* ─── Notifications badge ────────────────────────────────────── */

  function loadNotifications() {
    var bellBtn = document.getElementById('headerBellToggle');
    fetch('/api/notifications', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var count = data.unread_count || 0;
        var badge = bellBtn ? bellBtn.querySelector('.topbar-badge') : null;
        if (count > 0) {
          if (!badge && bellBtn) {
            badge = document.createElement('span');
            badge.className = 'topbar-badge pulse';
            bellBtn.appendChild(badge);
          }
          if (badge) badge.textContent = count > 9 ? '9+' : count;
        } else if (badge) {
          badge.remove();
        }
      })
      .catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.loadNotifications = loadNotifications;
    loadNotifications();
    setInterval(loadNotifications, 45000);
  });

  /* ─── Helpers ─────────────────────────────────────────────────── */

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatTime(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      var diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60) return 'just now';
      if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
      return Math.floor(diff / 86400) + 'd ago';
    } catch (e) {
      return '';
    }
  }

  window.refreshLucideIcons = function (root) {
    try {
      if (typeof lucide !== 'undefined') lucide.createIcons({ root: root || document });
    } catch (e) {}
  };
})();
