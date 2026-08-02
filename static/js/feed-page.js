/**
 * AltaJobs — feed-page.js
 * Page-level feed behavior: composer (textarea autosize, photo preview,
 * post-type pills), filter pills (AJAX re-fetch), pagination / infinite
 * scroll, and the post-options bottom sheet (copy link / share / report /
 * delete). Post-card interactions (like/follow/comment/repost/save) live
 * in feed-actions.js — this file only owns page chrome.
 */
(function () {
  'use strict';

  /* ================= Composer ================= */
  (function initComposer() {
    var composerTextarea = document.getElementById('composeTextarea');
    var composerInput = document.getElementById('composePhotoInput');
    var composerPreviewWrap = document.getElementById('composePreviewWrap');
    var composerPreviewImg = document.getElementById('composePreviewImg');
    var composerPreviewRemove = document.getElementById('composePreviewRemove');
    var composePhotoName = document.getElementById('composePhotoName');
    var composePostType = document.getElementById('composePostType');
    var composeCurrentFilter = document.getElementById('composeCurrentFilter');
    var composerForm = document.getElementById('composeForm');
    var composerSubmit = document.getElementById('composeSubmitButton');

    function resizeTextarea() {
      if (!composerTextarea) return;
      composerTextarea.style.height = 'auto';
      composerTextarea.style.height = Math.min(composerTextarea.scrollHeight, 220) + 'px';
    }

    if (composerTextarea) {
      composerTextarea.addEventListener('input', resizeTextarea);
      resizeTextarea();
    }

    document.querySelectorAll('.feed-composer__tool[data-attachment="photo"]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (composerInput) composerInput.click();
      });
    });

    document.querySelectorAll('.feed-composer__tool[data-post-type]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var isActive = btn.classList.contains('active');
        document.querySelectorAll('.feed-composer__tool[data-post-type]').forEach(function (b) { b.classList.remove('active'); });
        if (!isActive) {
          btn.classList.add('active');
          if (composePostType) composePostType.value = btn.dataset.postType === 'job' ? 'job' : 'skill';
        } else if (composePostType) {
          composePostType.value = 'general';
        }
      });
    });

    if (composerInput) {
      composerInput.addEventListener('change', function () {
        var file = composerInput.files && composerInput.files[0];
        if (!file) {
          if (composerPreviewWrap) composerPreviewWrap.hidden = true;
          if (composePhotoName) composePhotoName.hidden = true;
          return;
        }
        if (composePhotoName) {
          composePhotoName.hidden = false;
          composePhotoName.textContent = file.name;
        }
        var reader = new FileReader();
        reader.onload = function (e) {
          if (composerPreviewImg) composerPreviewImg.src = e.target.result;
          if (composerPreviewWrap) composerPreviewWrap.hidden = false;
        };
        reader.readAsDataURL(file);
      });
    }

    if (composerPreviewRemove) {
      composerPreviewRemove.addEventListener('click', function () {
        if (composerInput) composerInput.value = '';
        if (composerPreviewWrap) composerPreviewWrap.hidden = true;
        if (composePhotoName) composePhotoName.hidden = true;
      });
    }

    if (composerForm && composerSubmit) {
      composerForm.addEventListener('submit', function () {
        composerSubmit.disabled = true;
        composerSubmit.textContent = 'Posting…';
      });
    }

    // keep hidden post_type input synced with active filter as a default
    if (composeCurrentFilter && composePostType) {
      var raw = composeCurrentFilter.value || 'all';
      composePostType.value = raw === 'job' ? 'job' : raw === 'experience' ? 'skill' : 'general';
    }
  })();

  /* ================= Filters + pagination ================= */
  (function initFeedList() {
    var wrap = document.getElementById('feedLoadMoreWrap');
    var container = document.getElementById('feedPostsContainer');
    var btn = document.getElementById('feedLoadMoreBtn');
    var spinner = document.getElementById('feedLoadMoreSpinner');
    var filterBar = document.getElementById('feedFilters');
    var emptyMsg = document.getElementById('noFilterResultsMsg');
    var composeCurrentFilter = document.getElementById('composeCurrentFilter');
    var composePostType = document.getElementById('composePostType');
    var sentinel = document.getElementById('feedInfiniteSentinel');
    if (!wrap || !container) return;

    var page = parseInt(wrap.dataset.page || '1', 10);
    var hasNext = wrap.dataset.hasNext === '1';
    var activeType = wrap.dataset.filter || 'all';
    var loading = false;
    var renderedPostIds = new Set();

    container.querySelectorAll('.feed-card[data-post-id]').forEach(function (postNode) {
      if (postNode.dataset.postId) renderedPostIds.add(postNode.dataset.postId.toString());
    });

    function syncComposerType() {
      if (!composePostType || !composeCurrentFilter) return;
      var raw = composeCurrentFilter.value || 'all';
      composePostType.value = raw === 'job' ? 'job' : raw === 'experience' ? 'skill' : 'general';
    }

    function refreshFeedUI() {
      if (window.refreshPostSeeMoreButtons) window.refreshPostSeeMoreButtons();
      if (typeof window.refreshLucideIcons === 'function') window.refreshLucideIcons(container);
    }

    function clearSkeletons() {
      container.querySelectorAll('.feed-skeleton').forEach(function (n) { n.remove(); });
    }

    function renderSkeletons(count, mode) {
      clearSkeletons();
      var fragment = document.createDocumentFragment();
      for (var i = 0; i < count; i += 1) {
        var card = document.createElement('div');
        card.className = 'feed-skeleton';
        card.innerHTML = [
          '<div class="feed-skeleton__row">',
          '  <div class="feed-skeleton__avatar"></div>',
          '  <div class="feed-skeleton__line"></div>',
          '  <div class="feed-skeleton__line short"></div>',
          '</div>',
          '<div class="feed-skeleton__block"></div>',
          '<div class="feed-skeleton__actions">',
          '  <div class="feed-skeleton__icon"></div>',
          '  <div class="feed-skeleton__icon"></div>',
          '  <div class="feed-skeleton__icon"></div>',
          '</div>',
        ].join('');
        fragment.appendChild(card);
      }
      if (mode === 'replace') {
        container.innerHTML = '';
      }
      container.appendChild(fragment);
    }

    function appendUniquePosts(html) {
      if (!html) return;
      var fragment = document.createRange().createContextualFragment(html);
      Array.from(fragment.querySelectorAll('.feed-card')).forEach(function (postNode) {
        var postId = postNode.dataset.postId;
        if (!postId || renderedPostIds.has(postId.toString())) return;
        renderedPostIds.add(postId.toString());
        container.appendChild(postNode);
      });
    }

    function loadNextPage() {
      if (loading || !hasNext) return;
      loading = true;
      renderSkeletons(2, 'append');
      if (btn) btn.hidden = true;
      if (spinner) spinner.hidden = false;

      fetch('/feed/page/' + (page + 1) + '?type=' + encodeURIComponent(activeType), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          clearSkeletons();
          if (data && data.success) {
            if (data.html) {
              appendUniquePosts(data.html);
              refreshFeedUI();
            }
            page = data.page;
            hasNext = !!data.has_next;
          } else {
            hasNext = false;
          }
        })
        .catch(function () {
          clearSkeletons();
          if (typeof window.showToast === 'function') window.showToast('Network issue, retrying…', 'error');
        })
        .finally(function () {
          loading = false;
          if (spinner) spinner.hidden = true;
          if (btn) btn.hidden = !hasNext;
        });
    }

    if (filterBar) {
      filterBar.addEventListener('click', function (e) {
        var pill = e.target.closest('.feed-filter');
        if (!pill || loading) return;

        var newType = pill.dataset.filter || 'all';
        filterBar.querySelectorAll('.feed-filter').forEach(function (p) { p.classList.remove('active'); });
        pill.classList.add('active');
        if (newType === activeType) return;

        activeType = newType;
        if (composeCurrentFilter) composeCurrentFilter.value = activeType;
        syncComposerType();
        loading = true;
        renderSkeletons(3, 'replace');
        if (btn) btn.hidden = true;
        if (spinner) spinner.hidden = false;

        fetch('/feed/page/1?type=' + encodeURIComponent(activeType), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            if (data && data.success) {
              renderedPostIds.clear();
              container.innerHTML = data.html || '';
              container.querySelectorAll('.feed-card[data-post-id]').forEach(function (postNode) {
                if (postNode.dataset.postId) renderedPostIds.add(postNode.dataset.postId.toString());
              });
              page = 1;
              hasNext = !!data.has_next;
              refreshFeedUI();
              if (emptyMsg) emptyMsg.style.display = data.has_posts ? 'none' : 'block';
            }
          })
          .catch(function () {
            if (typeof window.showToast === 'function') window.showToast('Network issue, retrying…', 'error');
          })
          .finally(function () {
            loading = false;
            clearSkeletons();
            if (spinner) spinner.hidden = true;
            if (btn) btn.hidden = !hasNext;
          });
      });
    }

    if (btn) btn.addEventListener('click', loadNextPage);

    if ('IntersectionObserver' in window && sentinel) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) { if (entry.isIntersecting) loadNextPage(); });
      }, { rootMargin: '600px 0px' });
      observer.observe(sentinel);
    }
  })();

  /* ================= Post options sheet ================= */
  (function initPostOptionsSheet() {
    var overlay = document.getElementById('feedBottomSheetOverlay');
    var sheet = document.getElementById('feedPostActionsSheet');
    var copyBtn = document.getElementById('feedCopyLinkBtn');
    var shareBtn = document.getElementById('feedShareBtn');
    var deleteForm = document.getElementById('feedSheetDeleteForm');
    var reportForm = document.getElementById('feedSheetReportForm');
    var reportTarget = document.getElementById('feedSheetReportTargetId');
    var cancelBtn = document.getElementById('feedSheetCancelBtn');
    if (!overlay || !sheet) return;

    var currentPostUrl = null;
    var currentPostId = null;
    var isOpen = false;

    function resetSheetDisplay() {
      [overlay, sheet].forEach(function (el) {
        el.style.display = 'none';
        el.classList.remove('open', 'active');
      });
    }

    document.addEventListener('DOMContentLoaded', resetSheetDisplay);
    window.addEventListener('pageshow', resetSheetDisplay);

    function openSheet(postId, postUrl, deleteUrl, canDelete, canReport) {
      if (!isOpen) {
        try { window.history.pushState({ feedMenuOpen: true }, '', window.location.href); } catch (e) {}
      }
      isOpen = true;
      currentPostId = postId || '';
      currentPostUrl = postUrl || window.location.origin + '/post/' + postId;

      if (deleteForm) {
        deleteForm.action = deleteUrl || '';
        deleteForm.style.display = canDelete ? '' : 'none';
      }
      if (reportForm && reportTarget) {
        reportTarget.value = currentPostId;
        reportForm.style.display = canReport ? '' : 'none';
      }

      sheet.style.display = 'flex';
      overlay.style.display = 'flex';
      sheet.classList.add('open');
      overlay.classList.add('open');
    }

    function closeSheet(skipPop) {
      if (!isOpen) return;
      sheet.classList.remove('open');
      overlay.classList.remove('open');
      sheet.style.display = 'none';
      overlay.style.display = 'none';
      currentPostUrl = null;
      currentPostId = null;
      isOpen = false;
      if (!skipPop && window.history.state && window.history.state.feedMenuOpen) {
        try { window.history.back(); } catch (e) {}
      }
    }

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.js-post-menu-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      openSheet(
        btn.dataset.postId,
        btn.dataset.postUrl,
        btn.dataset.deleteUrl,
        btn.dataset.canDelete === '1' || btn.dataset.canDelete === 'true',
        btn.dataset.canReport === '1' || btn.dataset.canReport === 'true'
      );
    });

    window.addEventListener('popstate', function (e) {
      if (isOpen && !(e.state && e.state.feedMenuOpen)) closeSheet(true);
    });

    if (copyBtn) {
      copyBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!currentPostUrl || !navigator.clipboard) return;
        navigator.clipboard.writeText(currentPostUrl).then(function () {
          copyBtn.innerHTML = '<i class="bx bx-check"></i> Link copied!';
          setTimeout(function () {
            copyBtn.innerHTML = '<i class="bx bx-link-alt"></i> Copy Link';
            closeSheet();
          }, 800);
        });
      });
    }

    if (shareBtn) {
      shareBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!currentPostUrl) return;
        if (navigator.share) {
          navigator.share({ title: document.title, url: currentPostUrl }).catch(function () {});
        } else if (navigator.clipboard) {
          navigator.clipboard.writeText(currentPostUrl);
        }
        closeSheet();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeSheet();
      });
    }

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeSheet();
    });
  })();
})();
