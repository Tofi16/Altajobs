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
document.addEventListener("click", async function (e) {
  const btn = e.target.closest(".js-like-btn");
  if (!btn) return;
  e.preventDefault();

  const postId = btn.dataset.postId;
  const likeLabel = btn.dataset.likeLabel || "Like";
  const likedLabel = btn.dataset.likedLabel || "Liked";
  const icon = btn.querySelector(".bx");
  const countEl = btn.querySelector(".like-count");
  const textEl = btn.querySelector(".like-text");

  btn.disabled = true;
  try {
    const res = await fetch(`/api/like/${postId}`, { method: "POST" });
    const data = await res.json();
    if (countEl) countEl.textContent = data.like_count;
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
  } catch (err) {
    console.error("Like toggle failed", err);
  } finally {
    btn.disabled = false;
  }
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
          video.play().catch(() => {});
          // Count the view exactly once per post per page load, then stop
          // observing this element so scrolling back and forth can't
          // re-trigger it.
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
