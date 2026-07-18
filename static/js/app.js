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
  if (!textarea || !actions) return;

  const expand = function () {
    actions.classList.remove("compose-actions-collapsed");
    autoGrow();
  };
  const autoGrow = function () {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 220) + "px";
  };

  textarea.addEventListener("focus", expand);
  textarea.addEventListener("input", function () {
    expand();
    autoGrow();
  });

  if (photoInput && photoName) {
    photoInput.addEventListener("change", function () {
      expand();
      photoName.textContent = photoInput.files && photoInput.files[0] ? photoInput.files[0].name : "";
    });
  }
});

// ---------- Quick feed filters (pill bar) ----------
document.addEventListener("DOMContentLoaded", function () {
  const bar = document.getElementById("feedFilters");
  if (!bar) return;

  const posts = document.querySelectorAll(".post-card[data-post-type]");
  const emptyMsg = document.getElementById("noFilterResultsMsg");

  bar.addEventListener("click", function (e) {
    const pill = e.target.closest(".filter-pill");
    if (!pill) return;

    bar.querySelectorAll(".filter-pill").forEach((p) => p.classList.remove("active"));
    pill.classList.add("active");

    const filter = pill.dataset.filter;
    const allowed = filter === "all" ? null : filter.split(",");

    let visibleCount = 0;
    posts.forEach((card) => {
      const type = card.dataset.postType;
      const show = !allowed || allowed.includes(type);
      card.style.display = show ? "" : "none";
      if (show) visibleCount++;
    });

    if (emptyMsg) {
      emptyMsg.style.display = (posts.length > 0 && visibleCount === 0) ? "block" : "none";
    }
  });
});

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

  const lockState = { modal: 0, drawer: 0 };

  const syncScrollLock = function () {
    const locked = lockState.modal > 0 || lockState.drawer > 0;
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
    lockState.drawer = 0;
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
    if (modal) modal.classList.add('open');
    lockState.modal += 1;
    syncScrollLock();
  }
  window.closeModal = function (id) {
    const backdrop = document.getElementById('modalBackdrop');
    const modal = document.getElementById(id);
    if (backdrop) backdrop.classList.remove('open');
    if (modal) modal.classList.remove('open');
    lockState.modal = Math.max(0, lockState.modal - 1);
    syncScrollLock();
  }
  window.closeAllModals = function () {
    const backdrop = document.getElementById('modalBackdrop');
    if (backdrop) backdrop.classList.remove('open');
    document.querySelectorAll('.modal.open').forEach(function (modal) {
      modal.classList.remove('open');
    });
    lockState.modal = 0;
    syncScrollLock();
  }

  // Wallet: animate balance count on wallet page
  try {
    const balEl = document.querySelector('.wallet-balance');
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
