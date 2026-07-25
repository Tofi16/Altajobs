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

// ---------- AJAX Follow button (instant, no reload) ----------
document.addEventListener("click", async function (e) {
  const btn = e.target.closest(".js-follow-btn");
  if (!btn) return;
  e.preventDefault();

  const userId = btn.dataset.userId;
  const followLabel = btn.dataset.followLabel || "Follow";
  const followingLabel = btn.dataset.followingLabel || "Following";

  btn.disabled = true;
  try {
    const res = await fetch(`/api/follow/${userId}`, { method: "POST" });
    const data = await res.json();
    if (data.following) {
      btn.classList.add("following");
      btn.textContent = followingLabel;
    } else {
      btn.classList.remove("following");
      btn.textContent = followLabel;
    }
  } catch (err) {
    console.error("Follow toggle failed", err);
  } finally {
    btn.disabled = false;
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

  btn.disabled = true;
  try {
    const res = await fetch(`/api/like/${postId}`, { method: "POST" });
    const data = await res.json();
    if (countEl) countEl.textContent = data.like_count;
    if (socialCount && typeof data.like_count === "number") {
      socialCount.textContent = `${Math.max(data.like_count - 1, 0)} others`;
    }
    if (data.liked) {
      btn.classList.add("liked", "just-liked");
      if (icon) { icon.classList.remove("bx-heart"); icon.classList.add("bxs-heart"); }
      if (textEl) textEl.textContent = likedLabel;
      setTimeout(() => btn.classList.remove("just-liked"), 400);
    } else {
      btn.classList.remove("liked");
      if (icon) { icon.classList.remove("bxs-heart"); icon.classList.add("bx-heart"); }
      if (textEl) textEl.textContent = likeLabel;
    }
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
  e.preventDefault();
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
  if (!textarea || !actions) return;

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
      }
    });
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
      const cards = document.querySelectorAll(".post-card[data-post-type]");
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

    searchInput.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(filterFeedCards, 180);
    });

    searchClear.addEventListener("click", function () {
      searchInput.value = "";
      filterFeedCards();
      searchInput.focus();
    });
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
        e.preventDefault();
        currentRepostPostId = btn.dataset.postId;
        overlay.style.display = "flex";
        modal.style.display = "block";
        renderFollowerList(followerListEl, currentRepostPostId, closeRepostModal);
        return;
      }
      if (e.target.closest(".js-repost-modal-close") || e.target === overlay) {
        closeRepostModal();
      }
    });

    if (quickBtn) {
      quickBtn.addEventListener("click", function () {
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
    if (!overlay || !sheet) return;

    let currentSharePostId = null;
    let currentShareUrl = null;

    function closeShareSheet() {
      sheet.classList.remove("open");
      overlay.classList.remove("open");
      mainPanel.style.display = "";
      followersPanel.style.display = "none";
    }

    document.addEventListener("click", function (e) {
      const btn = e.target.closest(".js-share-btn");
      if (btn) {
        e.preventDefault();
        currentSharePostId = btn.dataset.postId;
        currentShareUrl = btn.dataset.postUrl;
        mainPanel.style.display = "";
        followersPanel.style.display = "none";
        sheet.classList.add("open");
        overlay.classList.add("open");
        return;
      }
      if (e.target.closest(".js-share-sheet-close")) {
        closeShareSheet();
        return;
      }
      // Overlay is shared with the post-options sheet; only close this one
      // if this sheet is the one currently open.
      if (e.target === overlay && sheet.classList.contains("open")) {
        closeShareSheet();
      }
    });

    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
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
      sendBtn.addEventListener("click", function () {
        mainPanel.style.display = "none";
        followersPanel.style.display = "";
        renderFollowerList(followerListEl, currentSharePostId, closeShareSheet);
      });
    }
  });
})();

// ---------- Three-dot post menu -> animated bottom sheet ----------
document.addEventListener("DOMContentLoaded", function () {
  const overlay = document.getElementById("bottomSheetOverlay");
  const sheet = document.getElementById("postActionsSheet");
  const deleteForm = document.getElementById("sheetDeleteForm");
  const reportForm = document.getElementById("sheetReportForm");
  const reportTargetId = document.getElementById("sheetReportTargetId");
  const cancelBtn = document.getElementById("sheetCancelBtn");
  if (!overlay || !sheet) return;

  const closeSheet = function () {
    sheet.classList.remove("open");
    overlay.classList.remove("open");
  };

  const openSheet = function (btn) {
    const postId = btn.dataset.postId;
    const canDelete = btn.dataset.canDelete === "1";
    const canReport = btn.dataset.canReport === "1";

    deleteForm.style.display = canDelete ? "block" : "none";
    deleteForm.action = `/post/${postId}/delete`;

    reportForm.style.display = canReport ? "block" : "none";
    if (reportTargetId) reportTargetId.value = postId;

    sheet.classList.add("open");
    overlay.classList.add("open");
  };

  document.addEventListener("click", function (e) {
    const trigger = e.target.closest(".js-post-menu-btn");
    if (trigger) {
      e.preventDefault();
      openSheet(trigger);
      return;
    }
    if (e.target === overlay || e.target === cancelBtn) {
      closeSheet();
    }
  });
});

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
