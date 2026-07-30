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

  /* ─── Like ────────────────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-like-btn, [data-action="like"]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();

    var postId = btn.dataset.postId;
    if (!postId) return;

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

    // Optimistic update
    btn.classList.toggle('following', !wasFollowing);
    if (labelEl) labelEl.textContent = wasFollowing ? followLabel : followingLabel;
    btn.disabled = true;

    post('/api/follow/' + userId)
      .then(function (r) { return r.json(); })
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
      .finally(function () {
        btn.disabled = false;
      });
  });

  /* ─── Comment panel toggle ────────────────────────────────────── */
  function setPanelHeight(panel, open) {
    if (!panel) return;
    if (open) {
      panel.classList.add('open');
      panel.setAttribute('aria-hidden', 'false');
      panel.style.maxHeight = panel.scrollHeight + 64 + 'px'; // +64 for input
      var input = panel.querySelector('input, textarea');
      if (input) setTimeout(function () { input.focus(); }, 80);
    } else {
      panel.style.maxHeight = panel.scrollHeight + 'px';
      requestAnimationFrame(function () {
        panel.style.maxHeight = '0';
        panel.classList.remove('open');
        panel.setAttribute('aria-hidden', 'true');
      });
    }
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.js-comment-toggle');
    if (!btn) return;
    e.preventDefault();
    var postId = btn.dataset.postId;
    var article = document.getElementById('post-' + postId);
    if (!article) return;
    var panel = article.querySelector('.xpost-comment-panel');
    var isOpen = panel && panel.classList.contains('open');
    setPanelHeight(panel, !isOpen);
    btn.setAttribute('aria-expanded', (!isOpen).toString());
  });

  /* ─── Comment submit ──────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    var sendBtn = e.target.closest('.xpost-comment-submit, .comment-send-btn');
    if (!sendBtn) return;
    e.preventDefault();
    var postId = sendBtn.dataset.postId;
    var article = document.getElementById('post-' + postId);
    if (!article) return;
    var input = article.querySelector('.xpost-comment-input');
    if (!input || !input.value.trim()) return;
    var content = input.value.trim();
    input.value = '';
    sendBtn.disabled = true;

    fetch('/post/' + postId + '/comment', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: 'content=' + encodeURIComponent(content),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) throw new Error(data.error || 'failed');
        // Append new comment to panel
        var commentList = article.querySelector('.xpost-comment-list');
        if (!commentList) {
          commentList = document.createElement('div');
          commentList.className = 'xpost-comment-list';
          var row = article.querySelector('.xpost-comment-row');
          if (row) row.parentNode.insertBefore(commentList, row);
        }
        var div = document.createElement('div');
        div.className = 'xpost-comment-item';
        div.innerHTML =
          '<span class="xpost-comment-author">' + escapeHtml(data.author || 'You') + '</span>' +
          '<span class="xpost-comment-text">' + escapeHtml(content) + '</span>';
        commentList.appendChild(div);
        // Update count
        var countEl = article.querySelector('.comment-count, .xpost-comment-summary');
        if (countEl && data.comment_count !== undefined) {
          if (countEl.classList.contains('xpost-comment-summary')) {
            countEl.textContent = data.comment_count + ' comments';
          } else {
            countEl.textContent = data.comment_count;
          }
        }
        // Re-measure panel height
        var panel = article.querySelector('.xpost-comment-panel');
        if (panel && panel.classList.contains('open')) {
          panel.style.maxHeight = panel.scrollHeight + 'px';
        }
      })
      .catch(function () {
        input.value = content; // restore on error
        showToast('Could not post comment. Try again.', 'error');
      })
      .finally(function () {
        sendBtn.disabled = false;
      });
  });

  /* ─── Comment input: send on Enter ───────────────────────────── */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    var input = e.target;
    if (!input.classList.contains('xpost-comment-input')) return;
    e.preventDefault();
    var article = input.closest('article[id^="post-"]');
    if (!article) return;
    var postId = article.id.replace('post-', '');
    var sendBtn = article.querySelector('.xpost-comment-submit[data-post-id="' + postId + '"]');
    if (sendBtn) sendBtn.click();
  });

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
    var content = btn.previousElementSibling;
    if (!content) return;
    var expanded = content.classList.toggle('xpost-clamped');
    // toggle returns true when class was ADDED (i.e. now clamped)
    btn.textContent = expanded
      ? (btn.dataset.seeMore || 'See more')
      : (btn.dataset.seeLess || 'See less');
  });

  window.refreshPostSeeMoreButtons = refreshSeeMoreButtons;
  document.addEventListener('DOMContentLoaded', refreshSeeMoreButtons);

  /* ─── Notifications ───────────────────────────────────────────── */
  var bellBtn = document.getElementById('headerBellToggle');
  var popover = document.getElementById('headerNotifications');

  function loadNotifications() {
    fetch('/api/notifications', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var count = data.unread_count || 0;

        // Update / create the badge on the bell button
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

        // Populate popover list
        var list = popover ? popover.querySelector('.notification-list') : null;
        if (!list) return;
        if (!data.notifications || data.notifications.length === 0) {
          list.innerHTML = '<div class="notification-empty"><i class="bx bx-bell"></i><span>No notifications yet.</span></div>';
          return;
        }
        list.innerHTML = data.notifications.map(function (n) {
          return '<div class="notif-item' + (n.is_read ? '' : ' notif-item--unread') + '">' +
            '<i class="bx ' + (n.icon || 'bx-bell') + ' notif-icon"></i>' +
            '<div class="notif-body">' +
              '<p class="notif-msg">' + escapeHtml(n.message) + '</p>' +
              '<span class="notif-time">' + formatTime(n.created_at) + '</span>' +
            '</div></div>';
        }).join('');
      })
      .catch(function () {
        var list = popover ? popover.querySelector('.notification-list') : null;
        if (list) list.innerHTML = '<div class="notification-empty"><i class="bx bx-error-circle"></i><span>Could not load notifications.</span></div>';
      });
  }

  // Toggle popover open/close on bell click, mark-read on open
  if (bellBtn && popover) {
    bellBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var willOpen = !popover.classList.contains('open');
      // close any other open popovers first
      document.querySelectorAll('.topbar-popover.open').forEach(function (p) { p.classList.remove('open'); });
      popover.classList.toggle('open', willOpen);
      bellBtn.setAttribute('aria-expanded', willOpen.toString());
      if (willOpen) {
        loadNotifications();
        fetch('/api/notifications/mark-read', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        }).then(function () {
          var badge = bellBtn.querySelector('.topbar-badge');
          if (badge) badge.remove();
        }).catch(function () {});
      }
    });

    document.addEventListener('click', function (e) {
      if (popover.classList.contains('open') && !popover.contains(e.target) && e.target !== bellBtn) {
        popover.classList.remove('open');
        bellBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // Initial badge load + poll every 45s (does not mark as read, just refreshes count)
  document.addEventListener('DOMContentLoaded', function () {
    loadNotifications();
    setInterval(loadNotifications, 45000);
  });

  /* ─── Dropdown menus (More options) ──────────────────────────── */
  document.addEventListener('click', function (e) {
    var toggleBtn = e.target.closest('[data-action="toggle-menu"]');
    if (toggleBtn) {
      var dropdown = toggleBtn.closest('[data-dropdown]');
      if (!dropdown) return;
      var menu = dropdown.querySelector('[data-dropdown-menu]');
      if (!menu) return;
      var isOpen = !menu.classList.contains('hidden');
      // Close all others first
      document.querySelectorAll('[data-dropdown-menu]').forEach(function (m) {
        m.classList.add('hidden');
        m.setAttribute('aria-hidden', 'true');
      });
      if (!isOpen) {
        menu.classList.remove('hidden');
        menu.setAttribute('aria-hidden', 'false');
      }
      e.stopPropagation();
      return;
    }
    // Click outside: close all dropdowns
    if (!e.target.closest('[data-dropdown]')) {
      document.querySelectorAll('[data-dropdown-menu]').forEach(function (m) {
        m.classList.add('hidden');
        m.setAttribute('aria-hidden', 'true');
      });
    }
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
