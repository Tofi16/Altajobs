/**
 * AltaJobs — feed-actions.js
 * Handles: Like (AJAX), Follow (AJAX), Comment (inline expand + submit),
 *          Notification bell fetch + badge, See-more toggle.
 * Drop-in replacement — references /api/like/:id and /api/follow/:id
 * which already exist in app.py and return JSON.
 */
(function () {
  'use strict';

  /* ─── Utility ─────────────────────────────────────────────────── */
  function post(url) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    });
  }

  function postJson(url) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
      credentials: 'same-origin',
    }).then(function (r) {
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('application/json') === -1) return r.json().catch(function(){ return {} });
      return r.json();
    });
  }

  function showToast(msg, type) {
    var t = document.createElement('div');
    t.className = 'aj-toast aj-toast--' + (type || 'info');
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('aj-toast--show'); });
    setTimeout(function () {
      t.classList.remove('aj-toast--show');
      setTimeout(function () { t.remove(); }, 350);
    }, 2200);
  }

  window.showToast = showToast;

  /* ─── Like ────────────────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-like-btn, [data-action="like"]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    var postId = btn.dataset.postId;
    if (!postId) return;

    // prevent duplicate rapid clicks
    if (btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';

    // Optimistic update
    var wasLiked = btn.classList.contains('liked');
    var countEl = btn.querySelector('.like-count, .count');
    var currentCount = parseInt((countEl && countEl.textContent) || '0', 10) || 0;
    btn.classList.toggle('liked', !wasLiked);
    if (countEl) countEl.textContent = wasLiked ? Math.max(0, currentCount - 1) : currentCount + 1;

    post('/api/like/' + postId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        btn.classList.toggle('liked', !!data.liked);
        if (countEl) countEl.textContent = data.like_count;
        // sync heart icon fill
        var icon = btn.querySelector('[data-lucide]');
        if (icon) {
          icon.setAttribute('data-lucide', data.liked ? 'heart' : 'heart');
          icon.style.fill = data.liked ? 'currentColor' : 'none';
        }
      })
      .catch(function () {
        // revert optimistic update
        btn.classList.toggle('liked', wasLiked);
        if (countEl) countEl.textContent = currentCount;
        showToast('Could not update like. Try again.', 'error');
      })
      .finally(function () {
        delete btn.dataset.inflight;
      });
  });

  /* ─── Follow ──────────────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-follow-btn, [data-action="follow"]');
    if (!btn) return;
    // skip if inside a <form> — let the form handle it (follow_suggestions page)
    if (btn.closest('form')) return;
    e.preventDefault();
    e.stopPropagation();

    var userId = btn.dataset.userId;
    if (!userId) return;

    var labelEl = btn.querySelector('.follow-label') || btn;
    var wasFollowing = btn.classList.contains('following');
    var followLabel = btn.dataset.followLabel || 'Follow';
    var followingLabel = btn.dataset.followingLabel || 'Unfollow';

    // prevent duplicate requests
    if (btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';

    // Optimistic update
    btn.classList.toggle('following', !wasFollowing);
    if (labelEl) labelEl.textContent = wasFollowing ? followLabel : followingLabel;
    btn.disabled = true;

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
        btn.classList.toggle('following', !!data.following);
        if (labelEl) labelEl.textContent = data.following ? followingLabel : followLabel;

        // Update follower count on profile page if present
        var followerCountEl = document.querySelector('[data-followers-count]');
        if (followerCountEl && typeof data.followers_count !== 'undefined') {
          followerCountEl.textContent = data.followers_count;
        }
        // Update all follow buttons for the same user across the page
        document.querySelectorAll('.js-follow-btn[data-user-id="' + userId + '"], [data-action="follow"][data-user-id="' + userId + '"]').forEach(function (b) {
          b.classList.toggle('following', !!data.following);
          var lbl = b.querySelector('.follow-label') || b;
          if (lbl) lbl.textContent = data.following ? followingLabel : followLabel;
        });
      })
      .catch(function () {
        btn.classList.toggle('following', wasFollowing);
        if (labelEl) labelEl.textContent = wasFollowing ? followingLabel : followLabel;
        showToast('Could not update follow. Try again.', 'error');
      })
      .catch(function () {
        btn.classList.toggle('following', wasFollowing);
        if (labelEl) labelEl.textContent = wasFollowing ? followingLabel : followLabel;
        showToast('Could not update follow. Try again.', 'error');
      })
      .finally(function () {
        btn.disabled = false;
        delete btn.dataset.inflight;
      });
  });

  /* ─── Comment drawer ─────────────────────────────────────────── */
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
    document.body.style.overflow = open ? 'hidden' : '';
  }

  function renderCommentsSkeletons() {
    if (!commentsList) return;
    commentsList.innerHTML = [
      '<div class="feed-comment-skeleton"><div class="feed-skeleton-avatar"></div><div style="flex:1"><div class="feed-skeleton-line"></div><div class="feed-skeleton-line short"></div></div></div>',
      '<div class="feed-comment-skeleton"><div class="feed-skeleton-avatar"></div><div style="flex:1"><div class="feed-skeleton-line"></div><div class="feed-skeleton-line short"></div></div></div>'
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
      html += '<div class="feed-comment-item"><div class="feed-comment-avatar">' + escapeHtml(initials || 'Y') + '</div><div class="feed-comment-body"><div class="feed-comment-meta"><strong>' + escapeHtml(name) + '</strong><span>' + escapeHtml(when || '') + '</span></div><p>' + escapeHtml(comment.content || '') + '</p></div></div>';
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
          if (commentsSubtitle) commentsSubtitle.textContent = (data.comments.length || 0) + ' comment' + ((data.comments.length === 1) ? '' : 's');
        } else {
          renderEmptyComments();
          if (commentsSubtitle) commentsSubtitle.textContent = 'No comments yet';
        }
      })
      .catch(function () {
        renderEmptyComments();
        if (commentsSubtitle) commentsSubtitle.textContent = 'Unable to load comments';
        showToast('Could not load comments right now.', 'error');
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

  if (commentsSendBtn) {
    commentsSendBtn.addEventListener('click', function () {
      if (!activeCommentPostId || !commentsInput || !commentsInput.value.trim()) return;
      var content = commentsInput.value.trim();
      commentsInput.value = '';
      commentsSendBtn.disabled = true;
      fetch('/api/v1/posts/' + activeCommentPostId + '/comments', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ content: content })
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (!data || !data.success) throw new Error('failed');
          var commentItem = document.createElement('div');
          commentItem.className = 'feed-comment-item';
          var initials = 'YO';
          commentItem.innerHTML = '<div class="feed-comment-avatar">' + escapeHtml(initials) + '</div><div class="feed-comment-body"><div class="feed-comment-meta"><strong>You</strong><span>just now</span></div><p>' + escapeHtml(content) + '</p></div>';
          if (commentsList) {
            if (!commentsList.querySelector('.feed-comment-item')) {
              commentsList.innerHTML = '';
            }
            commentsList.insertBefore(commentItem, commentsList.firstChild);
          }
          var countEl = document.querySelector('.js-comment-toggle[data-post-id="' + activeCommentPostId + '"] .comment-count');
          if (countEl && data.comment_count !== undefined) {
            countEl.textContent = data.comment_count;
          }
          if (commentsSubtitle) commentsSubtitle.textContent = (data.comment_count || 0) + ' comment' + ((data.comment_count === 1) ? '' : 's');
        })
        .catch(function () {
          showToast('Could not post comment. Try again.', 'error');
        })
        .finally(function () {
          commentsSendBtn.disabled = false;
        });
    });
  }

  if (commentsInput) {
    commentsInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (commentsSendBtn) commentsSendBtn.click();
      }
    });
  }

  /* ─── See More / See Less ─────────────────────────────────────── */
  function refreshSeeMoreButtons() {
    document.querySelectorAll('.js-xpost-content').forEach(function (el) {
      var btn = el.nextElementSibling;
      if (!btn || !btn.classList.contains('js-xpost-seemore')) return;
      if (el.scrollHeight > el.clientHeight + 2) {
        btn.classList.remove('hidden');
      } else {
        btn.classList.add('hidden');
      }
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-xpost-seemore');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var content = btn.previousElementSibling;
    if (!content) return;
    var expanded = content.classList.toggle('xpost-clamped');
    btn.textContent = expanded
      ? (btn.dataset.seeMore || 'See more')
      : (btn.dataset.seeLess || 'See less');
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-save-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var postId = btn.dataset.postId;
    if (!postId) return;
    // guard rapid clicks
    if (btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';
    var wasSaved = btn.classList.contains('saved');
    btn.classList.toggle('saved', !wasSaved);
    btn.disabled = true;
    fetch('/post/' + postId + '/save', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    }).then(function (r) {
      if (!r.ok) throw new Error('network');
      // server returns redirect; assume success on 2xx
    }).catch(function () {
      btn.classList.toggle('saved', wasSaved);
      showToast('Could not update save state.', 'error');
    }).finally(function () {
      btn.disabled = false;
      delete btn.dataset.inflight;
    });
  });

  /* ─── Repost (share) handler (AJAX) ───────────────────────────── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-repost-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var postId = btn.dataset.postId;
    if (!postId) return;
    if (btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';
    btn.disabled = true;
    // optimistic: increment any nearby share count element
    var countEl = btn.querySelector('.count') || document.querySelector('.js-share-count[data-post-id="' + postId + '"]');
    var current = parseInt((countEl && countEl.textContent) || '0', 10) || 0;
    if (countEl) countEl.textContent = current + 1;
    postJson('/api/post/' + postId + '/repost')
      .then(function (data) {
        if (!data || !data.success) throw new Error('failed');
        if (countEl && typeof data.share_count !== 'undefined') countEl.textContent = data.share_count;
        showToast('Reposted', 'info');
      })
      .catch(function () {
        if (countEl) countEl.textContent = current;
        showToast('Could not repost. Try again.', 'error');
      })
      .finally(function () {
        btn.disabled = false;
        delete btn.dataset.inflight;
      });
  });

  /* ─── Share button: open native share where available, and log via repost API ───────────────── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-share-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    var postId = btn.dataset.postId;
    if (!postId) return;
    if (btn.dataset.inflight === '1') return;
    btn.dataset.inflight = '1';
    btn.disabled = true;
    // attempt navigator.share
    var shareUrl = window.location.origin + '/post/' + postId;
    var sharePromise = Promise.resolve();
    if (navigator.share) {
      sharePromise = navigator.share({ title: document.title, url: shareUrl }).catch(function () {});
    }
    sharePromise.then(function () {
      // log share/repost server-side
      return postJson('/api/post/' + postId + '/repost');
    }).then(function (data) {
      showToast('Thanks for sharing!', 'info');
      // update counts if returned
      var cnt = data && data.share_count ? data.share_count : undefined;
      var countEl = document.querySelector('.js-share-count[data-post-id="' + postId + '"]');
      if (countEl && typeof cnt !== 'undefined') countEl.textContent = cnt;
    }).catch(function () {
      showToast('Could not complete share.', 'error');
    }).finally(function () {
      btn.disabled = false;
      delete btn.dataset.inflight;
    });
  });

  window.refreshPostSeeMoreButtons = refreshSeeMoreButtons;
  document.addEventListener('DOMContentLoaded', refreshSeeMoreButtons);

  /* ─── Notifications badge ───────────────────────────────────── */
  var bellBtn = document.getElementById('headerBellToggle');

  function loadNotifications() {
    // ensure we have a reference to the header bell button (might be null if script ran early)
    var _bellBtn = bellBtn || document.getElementById('headerBellToggle');
    fetch('/api/notifications', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var count = data.unread_count || 0;
        var badge = _bellBtn ? _bellBtn.querySelector('.topbar-badge') : null;
        if (count > 0) {
          if (!badge && _bellBtn) {
            badge = document.createElement('span');
            badge.className = 'topbar-badge pulse';
            _bellBtn.appendChild(badge);
          }
          if (badge) badge.textContent = count > 9 ? '9+' : count;
        } else if (badge) {
          badge.remove();
        }
      })
      .catch(function () {});
  }

  // Initial badge load + poll every 45s (does not mark as read, just refreshes count)
  document.addEventListener('DOMContentLoaded', function () {
    // make loader callable from other scripts/tests and run immediately
    window.loadNotifications = loadNotifications;
    loadNotifications();
    setInterval(loadNotifications, 45000);
  });

  /* ─── Dropdown menus (More options) ──────────────────────────── */
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
      document.querySelectorAll('.xpost-menu.open').forEach(function (openMenu) {
        openMenu.classList.remove('open');
        openMenu.setAttribute('aria-hidden', 'true');
      });
      document.querySelectorAll('[data-action="toggle-menu"]').forEach(function (btn) {
        btn.setAttribute('aria-expanded', 'false');
      });
      if (!isOpen) {
        menu.classList.add('open');
        menu.setAttribute('aria-hidden', 'false');
        toggleBtn.setAttribute('aria-expanded', 'true');
      }
      return;
    }

    if (!e.target.closest('[data-dropdown]')) {
      document.querySelectorAll('.xpost-menu.open').forEach(function (menu) {
        menu.classList.remove('open');
        menu.setAttribute('aria-hidden', 'true');
      });
      document.querySelectorAll('[data-action="toggle-menu"]').forEach(function (btn) {
        btn.setAttribute('aria-expanded', 'false');
      });
    }
  });

  document.addEventListener('click', function (e) {
    var copyBtn = e.target.closest('.js-post-copy-link');
    if (!copyBtn) return;
    e.preventDefault();
    e.stopPropagation();
    var url = copyBtn.dataset.postUrl || '';
    if (!url) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () {
        showToast('Link copied', 'success');
      }).catch(function () {
        showToast('Could not copy link', 'error');
      });
    } else {
      showToast('Could not copy link', 'error');
    }
    document.querySelectorAll('.xpost-menu.open').forEach(function (menu) {
      menu.classList.remove('open');
      menu.setAttribute('aria-hidden', 'true');
    });
  });

  document.addEventListener('click', function (e) {
    var reportBtn = e.target.closest('[data-action="report-post"]');
    if (!reportBtn) return;
    e.preventDefault();
    e.stopPropagation();
    if (window.openReportDrawer) {
      window.openReportDrawer('post', reportBtn.dataset.postId);
    }
    document.querySelectorAll('.xpost-menu.open').forEach(function (menu) {
      menu.classList.remove('open');
      menu.setAttribute('aria-hidden', 'true');
    });
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
    } catch (e) { return ''; }
  }

  /* ─── Lucide icon refresh helper ─────────────────────────────── */
  window.refreshLucideIcons = function (root) {
    try {
      if (typeof lucide !== 'undefined') {
        lucide.createIcons({ root: root || document });
      }
    } catch (e) {}
  };

})();
