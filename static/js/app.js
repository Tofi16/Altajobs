// AltaJobs - shared frontend interactions

window.openTab = function (tabName) {
  document.querySelectorAll('.tab-content').forEach(function (el) {
    el.style.display = 'none';
  });
  document.querySelectorAll('.tab-link').forEach(function (btn) {
    btn.classList.remove('active');
  });
  const target = document.getElementById(tabName);
  if (target) {
    target.style.display = 'block';
  }
  document.querySelectorAll('.tab-link').forEach(function (btn) {
    if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes("'" + tabName + "'")) {
      btn.classList.add('active');
    }
  });
};

function cancelActionClick(e) {
  if (!e) return;
  e.preventDefault();
  e.stopPropagation();
  if (typeof e.stopImmediatePropagation === 'function') {
    e.stopImmediatePropagation();
  }
}

function syncFollowButtons(userId, isFollowing, followLabel, followingLabel) {
  document.querySelectorAll(`.js-follow-btn[data-user-id="${userId}"]`).forEach(function (button) {
    const labelEl = button.querySelector('.follow-label');
    button.classList.toggle('following', isFollowing);
    button.setAttribute('aria-pressed', isFollowing ? 'true' : 'false');
    button.disabled = false;
    if (labelEl) {
      labelEl.textContent = isFollowing ? followingLabel : followLabel;
    } else {
      button.textContent = isFollowing ? followingLabel : followLabel;
    }
  });
}

function updateFollowCounters(data) {
  if (!data) return;
  if (data.followers_count !== undefined) {
    document.querySelectorAll('#profileFollowersCount, .js-followers-count').forEach(function (el) {
      el.textContent = data.followers_count;
    });
  }
  if (data.your_following_count !== undefined) {
    document.querySelectorAll('#profileFollowingCount, .js-following-count').forEach(function (el) {
      el.textContent = data.your_following_count;
    });
  }
}

// ---------- AJAX Follow button (instant, no reload) ----------
document.addEventListener("click", async function (e) {
  const btn = e.target.closest(".js-follow-btn");
  if (!btn) return;
  cancelActionClick(e);

  const userId = btn.dataset.userId;
  const followLabel = btn.dataset.followLabel || "Follow";
  const followingLabel = btn.dataset.followingLabel || "Following";
  if (!userId) return;

  document.querySelectorAll(`.js-follow-btn[data-user-id="${userId}"]`).forEach(function (button) {
    button.disabled = true;
  });

  try {
    const res = await fetch(`/api/follow/${userId}`, { method: "POST" });
    if (!res.ok) {
      throw new Error(`Follow request failed with status ${res.status}`);
    }
    const data = await res.json();
    if (data.error) {
      throw new Error(data.error);
    }
    if (data.following !== undefined) {
      syncFollowButtons(userId, !!data.following, followLabel, followingLabel);
      updateFollowCounters(data);
    }
  } catch (err) {
    console.error("Follow toggle failed", err);
    document.querySelectorAll(`.js-follow-btn[data-user-id="${userId}"]`).forEach(function (button) {
      button.disabled = false;
    });
  }
});

// ---------- AJAX Like button (instant, no reload, no scroll jump) ----------
async function togglePostLike(btn, options) {
  if (!btn) return;
  const postId = btn.dataset.postId;
  const likeLabel = btn.dataset.likeLabel || "Like";
  const likedLabel = btn.dataset.likedLabel || "Liked";
  const icon = btn.querySelector(".bx");
  const countEl = btn.querySelector(".like-count");
  const textEl = btn.querySelector(".like-text");
  const card = btn.closest(".post-card");
  const socialCount = card ? card.querySelector(".social-proof-count") : null;

  if (!postId) {
    btn.disabled = false;
    return;
  }
  btn.disabled = true;
  try {
    const res = await fetch(`/api/like/${postId}`, { method: "POST" });
    if (!res.ok) {
      throw new Error(`Like request failed with status ${res.status}`);
    }
    const data = await res.json();
    if (data.error) {
      throw new Error(data.error);
    }
    document.querySelectorAll(`.js-like-btn[data-post-id="${postId}"]`).forEach(function (button) {
      const iconEl = button.querySelector('.bx');
      const countEl2 = button.querySelector('.like-count');
      const textEl2 = button.querySelector('.like-text');
      const card2 = button.closest('.post-card');
      const socialCount2 = card2 ? card2.querySelector('.social-proof-count') : null;
      if (countEl2) countEl2.textContent = data.like_count;
      if (socialCount2 && typeof data.like_count === "number") {
        socialCount2.textContent = `${Math.max(data.like_count - 1, 0)} others`;
      }
      button.classList.toggle('liked', !!data.liked);
      if (data.liked) {
        if (iconEl) { iconEl.classList.remove("bx-heart"); iconEl.classList.add("bxs-heart"); }
        if (textEl2) textEl2.textContent = likedLabel;
      } else {
        if (iconEl) { iconEl.classList.remove("bxs-heart"); iconEl.classList.add("bx-heart"); }
        if (textEl2) textEl2.textContent = likeLabel;
      }
    });
    if (options && options.fromDoubleTap) {
      const overlay = card ? card.querySelector(".double-tap-heart") : null;
      if (overlay) {
        overlay.classList.remove("active");
        void overlay.offsetWidth;
        overlay.classList.add("active");
        setTimeout(() => overlay.classList.remove("active"), 420);
      }
    }
  } catch (err) {
    console.error("Like toggle failed", err);
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("click", function (e) {
  const btn = e.target.closest(".js-like-btn");
  if (!btn) return;
  cancelActionClick(e);
  togglePostLike(btn);
});

document.addEventListener("dblclick", function (e) {
  const media = e.target.closest(".post-media");
  if (!media) return;
  const card = media.closest(".post-card");
  const btn = card ? card.querySelector(".js-like-btn") : null;
  if (!btn) return;
  e.preventDefault();
  togglePostLike(btn, { fromDoubleTap: true });
});

document.addEventListener("submit", async function (e) {
  const form = e.target.closest('.js-comment-form');
  if (!form) return;
  e.preventDefault();

  const postId = form.dataset.postId;
  const submitBtn = form.querySelector('button[type="submit"]');
  if (!postId || !submitBtn) return;

  submitBtn.disabled = true;
  const formData = new FormData(form);
  try {
    const res = await fetch(form.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: formData,
    });
    if (!res.ok) {
      throw new Error('Comment request failed');
    }
    const data = await res.json();
    if (data.comment_count !== undefined) {
      const countEl = document.getElementById('postCommentsCount');
      if (countEl) countEl.textContent = data.comment_count;
      const commentBadge = form.closest('article, .post-card')?.querySelector('.comment-count');
      if (commentBadge) commentBadge.textContent = data.comment_count;
      form.reset();
    }
  } catch (err) {
    console.error('Comment submission failed', err);
  } finally {
    submitBtn.disabled = false;
  }
});

// ---------- Compact compose box: expand on focus/typing ----------
document.addEventListener("DOMContentLoaded", function () {
  const shell = document.getElementById("feedSkeletonShell");
  if (shell) {
    window.setTimeout(function () {
      shell.classList.add("is-hidden");
    }, 450);
  }

  const textarea = document.getElementById("composeTextarea");
  const actions = document.getElementById("composeActions");
  const photoInput = document.getElementById("composePhotoInput");
  const photoName = document.getElementById("composePhotoName");
  const composeForm = document.getElementById("composeForm");
  const composeSubmit = document.getElementById("composeSubmitButton");
  const photoButton = document.querySelector('.compose-media-icon');
  if (!textarea) return;

  const updateComposeSubmitState = function () {
    const hasText = textarea.value.trim().length > 0;
    const hasPhoto = photoInput && photoInput.files && photoInput.files.length > 0;
    if (composeSubmit) {
      const enabled = hasText || hasPhoto;
      composeSubmit.disabled = !enabled;
      composeSubmit.classList.toggle('btn-disabled', !enabled);
    }
  };

  const expand = function () {
    actions.classList.remove("compose-actions-collapsed");
    autoGrow();
    updateComposeSubmitState();
  };
  const autoGrow = function () {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 220) + "px";
  };

  textarea.addEventListener("focus", expand);
  textarea.addEventListener("input", function () {
    expand();
    autoGrow();
    updateComposeSubmitState();
  });

  if (composeForm) {
    composeForm.addEventListener('submit', function (e) {
      var hasPhoto = photoInput && photoInput.files && photoInput.files.length > 0;
      if (textarea.value.trim().length === 0 && !hasPhoto) {
        e.preventDefault();
        textarea.focus();
      }
    });
  }

  if (photoInput && photoName) {
    photoInput.addEventListener("change", function () {
      expand();
      photoName.textContent = photoInput.files && photoInput.files[0] ? photoInput.files[0].name : "";
      updateComposeSubmitState();
    });
  }

  if (photoInput && photoButton) {
    photoButton.addEventListener('click', function (e) {
      if (photoInput) {
        photoInput.click();
      }
    });
  }

  updateComposeSubmitState();
});

// NOTE: the Jobs Only / Experiences / All feed filter pills are now handled
// by the backend-enforced AJAX logic inlined in feed.html (see the script
// next to #feedLoadMoreWrap), which re-queries /feed/page/1?type=... so
// filtering is a real server-side query rather than a client-side CSS hide.

// ---------- Premium header: search, notifications, and slide-in menu ----------
document.addEventListener("DOMContentLoaded", function () {
  const searchToggle = document.getElementById("headerSearchToggle");
  const searchPanel = document.getElementById("headerSearchPanel");
  const searchInput = document.getElementById("headerSearchInput");
  const searchClear = document.getElementById("headerSearchClear");
  const searchStatus = document.getElementById("headerSearchStatus");
  const bellToggle = document.getElementById("headerBellToggle");
  const bellPopover = document.getElementById("headerNotifications");
  const avatarToggle = document.getElementById("headerSidebarToggle");
  const sidebarDrawer = document.getElementById("headerSidebarDrawer");
  const sidebarOverlay = document.getElementById("headerSidebarOverlay");

  const closeSearch = function () {
    if (searchPanel) {
      searchPanel.classList.remove("open");
      searchPanel.setAttribute("aria-hidden", "true");
    }
  };

  const closePopover = function () {
    if (bellPopover) bellPopover.classList.remove("open");
  };

  const lockState = { modal: false, drawer: false };

  const syncScrollLock = function () {
    const locked = lockState.modal || lockState.drawer;
    if (locked) {
      const scrollY = window.scrollY || window.pageYOffset || 0;
      document.body.dataset.scrollY = scrollY;
      document.body.style.top = `-${scrollY}px`;
    } else {
      const storedY = parseInt(document.body.dataset.scrollY || "0", 10);
      document.body.style.top = "";
      window.scrollTo(0, storedY);
      delete document.body.dataset.scrollY;
    }
    document.body.classList.toggle("no-scroll", locked);
    document.documentElement.classList.toggle("no-scroll", locked);
  };

  const closeSidebar = function () {
    if (sidebarDrawer) {
      sidebarDrawer.classList.remove("open");
      sidebarDrawer.setAttribute("aria-hidden", "true");
    }
    if (sidebarOverlay) sidebarOverlay.classList.remove("open");
    document.body.classList.remove("drawer-open");
    lockState.drawer = false;
    syncScrollLock();
  };

  if (searchToggle && searchPanel) {
    searchToggle.addEventListener("click", function () {
      const isOpen = searchPanel.classList.toggle("open");
      searchPanel.setAttribute("aria-hidden", isOpen ? "false" : "true");
      if (isOpen && searchInput) { searchInput.focus(); }
    });
  }

  if (bellToggle && bellPopover) {
    bellToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      const isOpen = bellPopover.classList.toggle("open");
      if (isOpen) {
        closeSearch();
        closeSidebar();
        loadNotifications();
      }
    });
  }

  // ---------- Real notifications (replaces static mock content) ----------
  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatNotificationTime(iso) {
    if (!iso) return "";
    const raw = String(iso).trim();
    if (!raw) return "";

    let then = new Date(raw.replace(" ", "T"));
    if (Number.isNaN(then.getTime())) {
      then = new Date(raw);
    }
    if (Number.isNaN(then.getTime())) {
      return raw;
    }

    const diffMs = Date.now() - then.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return mins + "m ago";

    const hours = Math.floor(mins / 60);
    if (hours < 24) return hours + "h ago";

    const days = Math.floor(hours / 24);
    if (days < 7) {
      return days + "d ago";
    }

    return then.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  function renderNotifications(list) {
    if (!bellPopover) return;
    let body = bellPopover.querySelector(".notification-list");
    if (!body) {
      body = document.createElement("div");
      body.className = "notification-list";
      bellPopover.appendChild(body);
    }

    body.innerHTML = "";

    if (!list || list.length === 0) {
      body.innerHTML =
        '<div class="notification-empty">' +
        '<i class="bx bx-bell-off"></i>' +
        '<span>No new notifications</span>' +
        "</div>";
      return;
    }

    list.forEach(function (n) {
      const item = document.createElement("div");
      item.className = "notification-item" + (n.is_read ? "" : " unread");

      const icon = document.createElement("span");
      icon.className = "notification-icon";
      icon.innerHTML = '<i class="bx ' + escapeHtml(n.icon || 'bx-bell') + '"></i>';

      const bodyWrap = document.createElement("div");
      bodyWrap.className = "notification-body";

      const message = document.createElement("div");
      message.className = "notification-message";
      message.textContent = n.message || "";

      const time = document.createElement("div");
      time.className = "notification-time";
      time.textContent = formatNotificationTime(n.created_at);

      bodyWrap.appendChild(message);
      bodyWrap.appendChild(time);
      item.appendChild(icon);
      item.appendChild(bodyWrap);
      body.appendChild(item);
    });
  }

  function loadNotifications() {
    fetch("/api/notifications")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderNotifications(data.notifications || []);
        updateBellBadge(data.unread_count || 0);
        // Mark as read shortly after opening, so the badge clears without
        // the messages visually disappearing out from under the user.
        if (data.unread_count > 0) {
          setTimeout(function () {
            fetch("/api/notifications/mark-read", { method: "POST" }).then(function () {
              updateBellBadge(0);
            });
          }, 1500);
        }
      })
      .catch(function () {
        renderNotifications([]);
      });
  }

  function updateBellBadge(count) {
    if (!bellToggle) return;
    let badge = bellToggle.querySelector(".notification-badge");
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "notification-badge";
        bellToggle.appendChild(badge);
      }
      badge.textContent = count > 9 ? "9+" : String(count);
      badge.style.display = "";
    } else if (badge) {
      badge.style.display = "none";
    }
  }

  // Load once on page load too, so the badge count is correct before the
  // user ever opens the bell.
  if (bellToggle && bellPopover) {
    fetch("/api/notifications")
      .then(function (r) { return r.json(); })
      .then(function (data) { updateBellBadge(data.unread_count || 0); })
      .catch(function () {});
  }

  if (avatarToggle && sidebarDrawer && sidebarOverlay) {
    avatarToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      const isOpen = sidebarDrawer.classList.toggle("open");
      sidebarDrawer.setAttribute("aria-hidden", isOpen ? "false" : "true");
      sidebarOverlay.classList.toggle("open", isOpen);
      document.body.classList.toggle("drawer-open", isOpen);
      lockState.drawer = isOpen ? 1 : 0;
      syncScrollLock();
      if (isOpen) {
        closeSearch();
        closePopover();
      }
    });
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", closeSidebar);
  }

  document.addEventListener("click", function (e) {
    const clickedInsideSearch = searchPanel && searchPanel.contains(e.target);
    const clickedSearchToggle = searchToggle && searchToggle.contains(e.target);
    const clickedBell = bellPopover && bellPopover.contains(e.target);
    const clickedBellToggle = bellToggle && bellToggle.contains(e.target);
    const clickedDrawer = sidebarDrawer && sidebarDrawer.contains(e.target);
    const clickedAvatar = avatarToggle && avatarToggle.contains(e.target);

    if (!clickedInsideSearch && !clickedSearchToggle) closeSearch();
    if (!clickedBell && !clickedBellToggle) closePopover();
    if (!clickedDrawer && !clickedAvatar) closeSidebar();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeSearch();
      closePopover();
      closeSidebar();
    }
  });

  // Modal helpers: open/close and scroll lock
  window.openModal = function (id) {
    const backdrop = document.getElementById('modalBackdrop');
    const modal = document.getElementById(id);
    if (backdrop) backdrop.classList.add('open');
    if (modal) {
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }
    lockState.modal = true;
    syncScrollLock();
  }
  window.closeModal = function (id) {
    const backdrop = document.getElementById('modalBackdrop');
    const modal = document.getElementById(id);
    if (backdrop) backdrop.classList.remove('open');
    if (modal) {
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
    }
    lockState.modal = false;
    syncScrollLock();
  }
  window.closeAllModals = function () {
    const backdrop = document.getElementById('modalBackdrop');
    if (backdrop) backdrop.classList.remove('open');
    document.querySelectorAll('.modal.open').forEach(function (modal) {
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
    });
    lockState.modal = false;
    syncScrollLock();
  }

  const modalBackdrop = document.getElementById('modalBackdrop');
  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', function (e) {
      if (e.target === modalBackdrop) {
        window.closeAllModals();
      }
    });
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-modal-target]');
    if (!btn) return;
    const target = btn.getAttribute('data-modal-target');
    if (!target) return;
    if (typeof window.openModal === 'function') {
      e.preventDefault();
      window.openModal(target);
    }
  });

  // Auto-open modal when redirected with ?action=deposit|withdraw|transfer
  try {
    const params = new URLSearchParams(window.location.search);
    const action = params.get('action');
    if (action === 'deposit' && typeof window.openModal === 'function') {
      window.openModal('depositModal');
    } else if (action === 'withdraw' && typeof window.openModal === 'function') {
      window.openModal('withdrawModal');
    } else if (action === 'transfer' && typeof window.openModal === 'function') {
      window.openModal('transferModal');
    }
  } catch (e) {}

  const depositBankSelect = document.getElementById('depositBankSelect');
  const depositBankDetails = document.getElementById('depositBankDetails');
  const depositBankName = document.getElementById('depositBankName');
  const depositAccountName = document.getElementById('depositAccountName');
  const depositAccountNumber = document.getElementById('depositAccountNumber');

  const withdrawBankSelect = document.getElementById('withdrawBankSelection');
  const withdrawBankDetails = document.getElementById('withdrawBankDetails');
  const withdrawBankName = document.getElementById('withdrawBankName');
  const withdrawAccountName = document.getElementById('withdrawAccountName');
  const withdrawAccountNumber = document.getElementById('withdrawAccountNumber');
  const withdrawBankManualWrap = document.getElementById('withdrawBankManualWrap');
  const withdrawBankManual = document.getElementById('withdrawBankManual');

  const updateDepositBankDetails = function () {
    if (!depositBankSelect || !depositBankDetails) return;
    const option = depositBankSelect.selectedOptions[0];
    const bankName = option ? option.dataset.bankName || '' : '';
    const accountName = option ? option.dataset.accountName || '' : '';
    const accountNumber = option ? option.dataset.accountNumber || '' : '';

    if (bankName && accountName && accountNumber) {
      depositBankName.textContent = bankName;
      depositAccountName.textContent = accountName;
      depositAccountNumber.textContent = accountNumber;
      depositBankDetails.classList.remove('hidden');
    } else {
      depositBankDetails.classList.add('hidden');
    }
  };

  const updateWithdrawBankDetails = function () {
    if (!withdrawBankSelect || !withdrawBankDetails || !withdrawBankManualWrap || !withdrawBankManual) return;
    const option = withdrawBankSelect.selectedOptions[0];
    const bankName = option ? option.dataset.bankName || '' : '';
    const accountName = option ? option.dataset.accountName || '' : '';
    const accountNumber = option ? option.dataset.accountNumber || '' : '';
    const selectedValue = (withdrawBankSelect.value || '').toString().trim().toLowerCase();
    const showManual = selectedValue === 'other';

    withdrawBankManualWrap.style.display = showManual ? 'block' : 'none';
    withdrawBankManual.required = showManual;
    if (!showManual) {
      withdrawBankManual.value = '';
    }

    if (bankName && accountNumber) {
      withdrawBankName.textContent = bankName;
      withdrawAccountName.textContent = accountName || '—';
      withdrawAccountNumber.textContent = accountNumber;
      withdrawBankDetails.classList.remove('hidden');
    } else {
      withdrawBankDetails.classList.add('hidden');
    }
  };

  if (depositBankSelect) {
    depositBankSelect.addEventListener('change', updateDepositBankDetails);
    updateDepositBankDetails();
  }
  if (withdrawBankSelect) {
    withdrawBankSelect.addEventListener('change', updateWithdrawBankDetails);
    updateWithdrawBankDetails();
  }

  // Ensure any stale scroll-lock state is cleared when the page loads.
  lockState.modal = false;
  lockState.drawer = false;
  syncScrollLock();

  // Wallet: animate balance count on wallet page
  try {
    const balEl = document.querySelector('.wallet-balance') || document.querySelector('.wallet-balance-amount');
    if (balEl) {
      const raw = balEl.textContent.replace(/[^0-9\.\-]/g, '') || '0';
      const target = parseFloat(raw);
      if (!isNaN(target)) {
        let start = 0;
        const duration = 900;
        const startTime = performance.now();
        const step = (now) => {
          const t = Math.min(1, (now - startTime) / duration);
          const eased = t < 0.5 ? 2*t*t : -1 + (4 - 2*t)*t; // easeInOutQuad-like
          const current = Math.floor(start + (target - start) * eased);
          balEl.textContent = current + ' ETB';
          if (t < 1) requestAnimationFrame(step);
        };
        // Start from 0
        balEl.textContent = '0 ETB';
        requestAnimationFrame(step);
      }
    }
  } catch (e) {}

  if (searchInput) {
    let debounceTimer = null;
    const filterFeedCards = function () {
      const query = (searchInput.value || "").trim().toLowerCase();
      const cards = document.querySelectorAll(".post-card[data-post-type], .xpost[data-post-type]");
      let visibleCount = 0;
      cards.forEach(function (card) {
        const text = (card.textContent || "").toLowerCase();
        const show = !query || text.includes(query);
        card.style.display = show ? "" : "none";
        if (show) visibleCount++;
      });

      if (searchStatus) {
        if (!query) {
          searchStatus.textContent = "Search products in the feed";
        } else if (visibleCount > 0) {
          searchStatus.textContent = visibleCount + " product" + (visibleCount === 1 ? "" : "s") + " match your search";
        } else {
          searchStatus.textContent = "No products match this search yet";
        }
      }
    };

    const updateSearchClear = function () {
      if (!searchClear) return;
      searchClear.style.display = searchInput.value.trim().length > 0 ? "inline-flex" : "none";
    };

    searchInput.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(filterFeedCards, 180);
      updateSearchClear();
    });

    searchClear.addEventListener("click", function () {
      searchInput.value = "";
      filterFeedCards();
      updateSearchClear();
      searchInput.focus();
    });

    updateSearchClear();
  }
});

// ---------- Repost (instant AJAX, optimistic) + modal "send to chat/followers" ----------
(function () {
  let currentRepostPostId = null;
  let followersCache = null;

  function fetchFollowers() {
    if (followersCache) return Promise.resolve(followersCache);
    return fetch("/api/followers-list")
      .then((r) => r.json())
      .then((data) => {
        followersCache = data.followers || [];
        return followersCache;
      })
      .catch(() => []);
  }

  function renderFollowerList(container, postId, closeAfterSend) {
    container.innerHTML = '<div class="sheet-empty-note">Loading your followers…</div>';
    fetchFollowers().then((followers) => {
      if (!followers.length) {
        container.innerHTML = '<div class="sheet-empty-note">You have no followers yet to send this to.</div>';
        return;
      }
      container.innerHTML = "";
      followers.forEach((f) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "sheet-follower-row";
        row.innerHTML =
          (f.avatar
            ? `<img class="sheet-follower-avatar" src="${f.avatar}" alt="">`
            : `<span class="sheet-follower-avatar">${(f.name || "?")[0].toUpperCase()}</span>`) +
          `<span>${f.name}</span>`;
        row.addEventListener("click", function () {
          row.disabled = true;
          fetch(`/api/post/${postId}/send-to-follower`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ follower_id: f.id }),
          })
            .then((r) => r.json())
            .then((data) => {
              if (data.success) {
                row.classList.add("sent");
                row.innerHTML += ' <i class="bx bx-check" style="margin-left:auto"></i>';
                if (closeAfterSend) setTimeout(closeAfterSend, 700);
              } else {
                row.disabled = false;
              }
            })
            .catch(() => {
              row.disabled = false;
            });
        });
        container.appendChild(row);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const overlay = document.getElementById("repostModalOverlay");
    const modal = document.getElementById("repostModal");
    const quickBtn = document.getElementById("repostQuickBtn");
    const followerListEl = document.getElementById("repostFollowerList");
    if (!overlay || !modal) return;

    function closeRepostModal() {
      overlay.style.display = "none";
      modal.style.display = "none";
    }

    document.addEventListener("click", function (e) {
      const btn = e.target.closest(".js-repost-btn");
      if (btn) {
        cancelActionClick(e);
        currentRepostPostId = btn.dataset.postId;
        overlay.style.display = "flex";
        modal.style.display = "block";
        renderFollowerList(followerListEl, currentRepostPostId, closeRepostModal);
        return;
      }
      if (e.target.closest(".js-repost-modal-close") || e.target === overlay) {
        cancelActionClick(e);
        closeRepostModal();
      }
    });

    if (quickBtn) {
      quickBtn.addEventListener("click", function (e) {
        cancelActionClick(e);
        if (!currentRepostPostId) return;
        quickBtn.disabled = true;
        fetch(`/api/post/${currentRepostPostId}/repost`, { method: "POST" })
          .then((r) => r.json())
          .then((data) => {
            if (data.success) {
              const countEl = document.querySelector(
                `.js-repost-btn[data-post-id="${currentRepostPostId}"] .repost-count`
              );
              if (countEl) countEl.textContent = data.share_count;
              quickBtn.innerHTML = '<i class="bx bx-check"></i> Reposted!';
              setTimeout(closeRepostModal, 600);
            }
          })
          .finally(() => {
            quickBtn.disabled = false;
          });
      });
    }
  });

  // ---------- Share sheet: Copy Link / Send to Follower list ----------
  document.addEventListener("DOMContentLoaded", function () {
    const overlay = document.getElementById("bottomSheetOverlay");
    const sheet = document.getElementById("shareActionsSheet");
    const mainPanel = document.getElementById("shareSheetMain");
    const followersPanel = document.getElementById("shareSheetFollowers");
    const followerListEl = document.getElementById("shareFollowerList");
    const copyBtn = document.getElementById("sheetCopyLinkBtn");
    const sendBtn = document.getElementById("sheetSendToFollowerBtn");

    let currentSharePostId = null;
    let currentShareUrl = null;

    function doShareUrl(url) {
      if (!url) return;
      if (window.AJUI && typeof window.AJUI.doShare === "function") {
        window.AJUI.doShare(url);
        return;
      }
      if (navigator.share) {
        navigator.share({ title: document.title, url: url }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(url).catch(function () {});
      }
    }

    function closeShareSheet() {
      if (!sheet || !overlay) return;
      sheet.classList.remove("open");
      overlay.classList.remove("open");
      if (mainPanel) mainPanel.style.display = "";
      if (followersPanel) followersPanel.style.display = "none";
    }

    document.addEventListener("click", function (e) {
      const btn = e.target.closest(".js-share-btn");
      if (!btn) return;
      cancelActionClick(e);
      currentSharePostId = btn.dataset.postId;
      currentShareUrl = btn.dataset.postUrl || (currentSharePostId ? window.location.origin + "/post/" + currentSharePostId : null);
      if (!currentShareUrl) return;
      if (overlay && sheet) {
        if (mainPanel) mainPanel.style.display = "";
        if (followersPanel) followersPanel.style.display = "none";
        sheet.classList.add("open");
        overlay.classList.add("open");
      } else {
        doShareUrl(currentShareUrl);
      }
    });

    function isSheetOpen() {
      return sheet && sheet.classList.contains("open");
    }

    document.addEventListener("click", function (e) {
      if (e.target.closest(".js-share-sheet-close")) {
        cancelActionClick(e);
        closeShareSheet();
        return;
      }
      if (e.target === overlay && isSheetOpen()) {
        cancelActionClick(e);
        closeShareSheet();
      }
    });

    if (copyBtn) {
      copyBtn.addEventListener("click", function (e) {
        cancelActionClick(e);
        if (!currentShareUrl) return;
        navigator.clipboard
          .writeText(currentShareUrl)
          .then(() => {
            copyBtn.innerHTML = '<i class="bx bx-check"></i> Link copied!';
            setTimeout(() => {
              copyBtn.innerHTML = '<i class="bx bx-link-alt"></i> Copy Link';
              closeShareSheet();
            }, 700);
          })
          .catch(() => {});
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener("click", function (e) {
        cancelActionClick(e);
        if (mainPanel) mainPanel.style.display = "none";
        if (followersPanel) followersPanel.style.display = "";
        if (followerListEl) {
          renderFollowerList(followerListEl, currentSharePostId, closeShareSheet);
        }
      });
    }
  });
})();

// NOTE: the "three-dot" post options bottom sheet (#postActionsSheet) is
// wired up once in _feed_posts.html (guarded by window.__xpostMenuBound),
// which is the single source of truth for open/close + populating the
// Delete/Report forms. A second, now-removed handler used to live here and
// conflicted with it: both listened on the same document 'click' event for
// .js-post-menu-btn, and this one ran second and force-hid the Delete/Report
// buttons (checking data-can-delete / data-can-report attributes the button
// never actually set), which is exactly why the sheet appeared to "cut off
// at Cancel". Do not re-add a second handler here.

// ---------- Reels: view-once tracking + tap-to-unmute audio ----------
function disableMediaSessionNotifications() {
  if ('mediaSession' in navigator) {
    try {
      navigator.mediaSession.playbackState = 'none';
      navigator.mediaSession.metadata = null;
      ['play', 'pause', 'seekto', 'previoustrack', 'nexttrack'].forEach(function (action) {
        try { navigator.mediaSession.setActionHandler(action, null); } catch (e) {}
      });
    } catch (err) {
      console.warn('MediaSession handlers could not be cleared', err);
    }
  }
}

document.addEventListener("DOMContentLoaded", function () {
  disableMediaSessionNotifications();

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      document.querySelectorAll('video, audio').forEach(function (media) {
        try { media.pause(); } catch (err) {}
      });
    }
  });

  document.querySelectorAll('video').forEach(function (video) {
    video.disablePictureInPicture = true;
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');
    if (!video.hasAttribute('controlsList')) {
      video.setAttribute('controlsList', 'nodownload');
    }

    video.addEventListener('click', function (event) {
      if (event.target.closest('a, button, form, .js-like-btn, .js-follow-btn, .reel-side-icons')) {
        return;
      }
      event.stopPropagation();
      if (video.paused) {
        video.play().catch(function () {});
      } else {
        video.pause();
      }
    });
  });

  const reelVideos = document.querySelectorAll(".reel-slide video[data-post-id]");
  if (!reelVideos.length) return;

  const loadVideoIfNeeded = (video) => {
    const src = video.dataset.src;
    if (!src || video.getAttribute('src') === src) return;
    video.src = src;
    video.load();
  };

  const videoObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      const video = entry.target;
      if (entry.isIntersecting) {
        loadVideoIfNeeded(video);
        observer.unobserve(video);
      }
    });
  }, { rootMargin: '300px 0px' });

  reelVideos.forEach((video) => videoObserver.observe(video));

  // Browsers block autoplay-with-sound, so every reel starts muted; a tap
  // on the video unmutes it (and toggles play/pause on subsequent taps),
  // matching the platform's native short-video player behavior.
  reelVideos.forEach((video) => {
    // Start muted so autoplay is allowed; unmute on user gesture.
    video.muted = true;

    // Clicking directly on the video toggles mute/play as a fallback.
    video.addEventListener("click", function (e) {
      e.stopPropagation();
      if (video.muted) {
        video.muted = false;
        video.play().catch(() => {});
      } else if (video.paused) {
        video.play().catch(() => {});
      } else {
        video.pause();
      }
    });

    // Also allow tapping anywhere on the slide (except interactive controls)
    // to toggle audio/play. This handles overlay elements that sit above
    // the <video> and would otherwise block the video click.
    const slide = video.closest('.reel-slide');
    if (slide) {
      slide.addEventListener('click', function (ev) {
        // Ignore clicks on interactive elements (links, buttons, forms)
        if (ev.target.closest('a, button, form, .js-like-btn, .js-follow-btn')) return;
        if (video.muted) {
          video.muted = false;
          video.play().catch(() => {});
        } else if (video.paused) {
          video.play().catch(() => {});
        } else {
          video.pause();
        }
      });
    }

    // Wire up the visible unmute button and volume slider (one set per slide)
    const unmuteBtn = slide ? slide.querySelector('.reel-unmute-btn') : null;
    const volSlider = slide ? slide.querySelector('.reel-volume-slider') : null;
    if (unmuteBtn) {
      const icon = unmuteBtn.querySelector('.bx');
      const updateIcon = () => {
        if (!icon) return;
        icon.className = 'bx ' + ((video.muted || video.volume === 0) ? 'bx-volume-mute' : (video.volume > 0.5 ? 'bx-volume-full' : 'bx-volume-low'));
      };
      // initialize
      updateIcon();

      unmuteBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        // toggle mute state
        if (video.muted || video.volume === 0) {
          video.muted = false;
          if (video.paused) video.play().catch(() => {});
          // restore slider value if available
          if (volSlider && Number(volSlider.value) === 0) volSlider.value = 1;
        } else {
          video.muted = true;
        }
        updateIcon();
      });

      if (volSlider) {
        // ensure slider reflects current volume
        volSlider.value = video.volume || 1;
        volSlider.addEventListener('input', function (ev) {
          const v = parseFloat(ev.target.value);
          video.volume = v;
          video.muted = v === 0;
          updateIcon();
        });
        // On mobile, touching the slider should unmute the video
        volSlider.addEventListener('touchstart', function () { video.muted = false; updateIcon(); });
      }
    }
  });

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const video = entry.target;
        const postId = video.dataset.postId;
        if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
          loadVideoIfNeeded(video);
          video.play().catch(() => {});
          fetch(`/post/${postId}/view`, { method: "POST" }).finally(() => {
            observer.unobserve(video);
          });
        } else {
          video.pause();
        }
      });
    },
    { threshold: [0.6] }
  );

  reelVideos.forEach((v) => observer.observe(v));
});
