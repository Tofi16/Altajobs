// Feed media grid, lightbox, bottom-sheet, and toast controller
(function(){
  'use strict';

  // Simple glassmorphic toast controller
  var toastContainer = null;
  function ensureToastContainer(){
    if (toastContainer) return toastContainer;
    toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'toastContainer';
      document.body.appendChild(toastContainer);
    }
    return toastContainer;
  }

  function showToast(message, type){
    var container = ensureToastContainer();
    var t = document.createElement('div');
    t.className = 'toast ' + (type === 'error' ? 'error' : 'success');
    var accent = document.createElement('div'); accent.className = 'toast-accent';
    var content = document.createElement('div'); content.style.flex = '1'; content.textContent = message;
    t.appendChild(accent); t.appendChild(content);
    container.appendChild(t);
    // auto-dismiss
    setTimeout(function(){ t.classList.add('hide'); setTimeout(function(){ t.remove(); }, 320); }, 3000);
    return t;
  }

  // Expose globally
  window.showToast = showToast;
  // compatibility alias
  window.show_toast = showToast;
  if (!window.toast) window.toast = showToast;

  // Lightbox creation
  var lbOverlay = null;
  function ensureLightbox(){
    if (lbOverlay) return lbOverlay;
    lbOverlay = document.createElement('div');
    lbOverlay.className = 'feed-lightbox-overlay';
    lbOverlay.innerHTML = '<div class="feed-lightbox-content"><img src="" alt="preview"/></div><button class="feed-lightbox-close" aria-label="Close">✕</button>';
    document.body.appendChild(lbOverlay);

    lbOverlay.addEventListener('click', function(e){
      if (e.target === lbOverlay) closeLightbox();
    });
    var closeBtn = lbOverlay.querySelector('.feed-lightbox-close');
    closeBtn.addEventListener('click', closeLightbox);
    document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeLightbox(); });
    return lbOverlay;
  }
  function openLightbox(src){
    var box = ensureLightbox();
    var img = box.querySelector('img');
    img.src = src || '';
    box.classList.add('open');
  }
  function closeLightbox(){
    if (!lbOverlay) return;
    lbOverlay.classList.remove('open');
    var img = lbOverlay.querySelector('img'); if (img) img.src = '';
  }

  // Bottom sheet helper: toggle class on element with .bottom-sheet
  function openBottomSheet(sheet){ if (!sheet) return; sheet.classList.add('bottom-sheet-active'); }
  function closeBottomSheet(sheet){ if (!sheet) return; sheet.classList.remove('bottom-sheet-active'); }
  function closeAllBottomSheets(){
    document.querySelectorAll('.bottom-sheet.bottom-sheet-active').forEach(function(s){ s.classList.remove('bottom-sheet-active'); s.classList.add('translate-y-full'); });
    document.querySelectorAll('.bottom-sheet.open').forEach(function(s){ s.classList.remove('open'); s.classList.add('translate-y-full'); });
    var bo = document.getElementById('feedBottomSheetOverlay'); if (bo) { bo.classList.remove('open'); bo.classList.add('hidden'); bo.style.display = 'none'; }
    var feedSheet = document.getElementById('feedPostActionsSheet'); if (feedSheet) { feedSheet.classList.remove('open'); feedSheet.classList.add('hidden'); feedSheet.style.display = 'none'; }
    var ui = document.getElementById('uiOverlay'); if (ui) { ui.classList.remove('open'); ui.classList.add('hidden'); }
  }

  // Delegate clicks for media items and post menus
  document.addEventListener('click', function(e){
    var img = e.target.closest('.media-item img, .xpost-photo, .pc-media img');
    if (img) {
      e.preventDefault();
      var src = img.getAttribute('data-full') || img.src || img.getAttribute('src');
      openLightbox(src);
      return;
    }

    // open post options as bottom sheet if element targets it
    var sheetBtn = e.target.closest('.js-post-menu-btn');
    if (sheetBtn) {
      // follow existing ui-components logic by dispatching click that will open sheet
      return; // allow existing handler in ui-components to run
    }
  }, false);

  // Init: attach dataset for media grids to handle +N overlays
  document.addEventListener('DOMContentLoaded', function(){
    try { if (typeof window.closeAllModals === 'function') window.closeAllModals(); } catch(e){}
    try { closeAllBottomSheets(); } catch(e){}
    // Enhance media containers: add click cursor and data-full attributes
    document.querySelectorAll('.media-grid img, .xpost-photo, .pc-media img').forEach(function(img){
      img.style.cursor = 'zoom-in';
      // ensure high-res preview if data attribute absent
      if (!img.getAttribute('data-full')) img.setAttribute('data-full', img.src);
    });

    // Wire close for any bottom-sheet overlay elements (uiOverlay used by ui-components)
    var overlay = document.getElementById('uiOverlay');
    if (overlay) {
      overlay.addEventListener('click', function(ev){
        if (ev.target !== overlay) return;
        closeAllBottomSheets();
      });
    }
  });

  // Pull-to-refresh for mobile: touch handlers on feed container
  document.addEventListener('DOMContentLoaded', function(){
    var container = document.getElementById('feedPostsContainer');
    var pagerWrap = document.getElementById('feedLoadMoreWrap');
    if (!container) return;
    var isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    if (!isTouch) return;

    var startY = 0, curY = 0, pulling = false, indicator = null;
    var threshold = 70;

    function createIndicator(){
      if (indicator) return indicator;
      indicator = document.createElement('div');
      indicator.className = 'pull-indicator';
      indicator.style.cssText = 'width:100%;display:flex;align-items:center;justify-content:center;color:var(--text-secondary);height:0;overflow:visible;transition:height 0.18s ease,transform 0.12s ease;';
      indicator.innerHTML = '<div class="pi-content" style="padding:8px 12px;border-radius:999px;background:rgba(255,255,255,0.02);font-weight:700;">Pull to refresh</div>';
      container.parentNode.insertBefore(indicator, container);
      return indicator;
    }

    function onTouchStart(e){
      if ((document.scrollingElement || document.documentElement).scrollTop > 0) return;
      startY = e.touches ? e.touches[0].clientY : e.clientY;
      curY = startY;
      pulling = false;
    }

    function onTouchMove(e){
      curY = e.touches ? e.touches[0].clientY : e.clientY;
      var dy = curY - startY;
      if (dy > 5 && (document.scrollingElement || document.documentElement).scrollTop <= 0) {
        // begin pulling
        e.preventDefault();
        pulling = true;
        var ind = createIndicator();
        var pullH = Math.min(dy * 0.6, 140);
        ind.style.height = pullH + 'px';
        ind.style.transform = 'translateY(' + (pullH/2) + 'px)';
        var text = ind.querySelector('.pi-content');
        if (pullH > threshold) text.textContent = 'Release to refresh'; else text.textContent = 'Pull to refresh';
      }
    }

    function onTouchEnd(e){
      if (!pulling) return;
      var dy = curY - startY;
      var ind = indicator;
      if (ind) {
        ind.style.height = '0px';
        ind.style.transform = '';
      }
      pulling = false;
      if (dy * 0.6 > threshold) {
        // perform refresh
        var activeType = (pagerWrap && pagerWrap.dataset && pagerWrap.dataset.filter) ? pagerWrap.dataset.filter : 'all';
        try { showToast('Refreshing…'); } catch(e) {}
        fetch('/feed/page/1?type=' + encodeURIComponent(activeType), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
          .then(function(r){ return r.json(); })
          .then(function(data){
            if (data && data.success && data.html) {
              container.innerHTML = data.html;
              if (typeof refreshLucideIcons === 'function') refreshLucideIcons(container);
              if (typeof refreshPostSeeMoreButtons === 'function') refreshPostSeeMoreButtons();
            } else {
              showToast('Refresh failed', 'error');
            }
          }).catch(function(){ try{ showToast('Refresh failed', 'error'); }catch(e){} });
      }
      // cleanup indicator
      if (indicator) { setTimeout(function(){ if (indicator && indicator.parentNode) indicator.parentNode.removeChild(indicator); indicator = null; }, 220); }
    }

    container.addEventListener('touchstart', onTouchStart, { passive: true });
    container.addEventListener('touchmove', onTouchMove, { passive: false });
    container.addEventListener('touchend', onTouchEnd);
  });

  // Accessibility helpers, empty states, and offline/online indicators
  function ensureAriaLabels(){
    var mapping = {
      'js-like-btn': 'Like',
      'js-comment-btn': 'Comment',
      'js-share-btn': 'Share',
      'js-save-btn': 'Save',
      'postSheetCancel': 'Cancel',
      'reportDrawerClose': 'Close'
    };
    Object.keys(mapping).forEach(function(cls){
      document.querySelectorAll('.' + cls).forEach(function(el){ if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', mapping[cls]); });
    });
    // Generic icon buttons without labels
    document.querySelectorAll('button.topbar-icon-btn, button.icon-only, button[aria-label=""] ').forEach(function(b){
      if (!b.hasAttribute('aria-label')) {
        var i = b.querySelector('i');
        if (i && i.className) {
          var cls = i.className.replace(/[^a-zA-Z0-9\- ]/g, '');
          b.setAttribute('aria-label', cls);
        }
      }
    });
  }

  function renderEmptyState(type){
    var container = document.getElementById('feedPostsContainer');
    if (!container) return;
    var wrapper = document.createElement('div');
    wrapper.className = 'feed-empty-state';
    if (type === 'search'){
      wrapper.innerHTML = '<div class="empty-illustration">🔎</div><h3>No results found matching your query</h3><p>Try different keywords or clear your search.</p><div style="margin-top:12px"><button class="btn btn-primary" id="clearSearchBtn">Clear Search</button></div>';
    } else {
      wrapper.innerHTML = '<div class="empty-illustration">📭</div><h3>No jobs posted yet in this category</h3><p>Check back soon for new opportunities.</p><div style="margin-top:12px"><button class="btn btn-primary" id="checkBackBtn">Check Back Soon</button></div>';
    }
    container.innerHTML = '';
    container.appendChild(wrapper);
    // wire buttons
    var clearBtn = document.getElementById('clearSearchBtn'); if (clearBtn) clearBtn.addEventListener('click', function(){ try{ var input = document.getElementById('headerSearchInput'); if (input) { input.value = ''; var ev = new Event('input'); input.dispatchEvent(ev); } window.location = window.location.pathname; }catch(e){} });
    var cb = document.getElementById('checkBackBtn'); if (cb) cb.addEventListener('click', function(){ showToast('We will notify you when new jobs are posted'); });
  }

  function showOfflineBanner(){
    var id = 'offlineBanner';
    if (document.getElementById(id)) return;
    var b = document.createElement('div'); b.id = id; b.setAttribute('role','status'); b.className = 'offline-banner'; b.textContent = 'You are offline — some features may be unavailable';
    document.body.appendChild(b);
  }
  function hideOfflineBanner(){ var el = document.getElementById('offlineBanner'); if (el) el.remove(); }

  window.addEventListener('offline', function(){ try{ showOfflineBanner(); showToast('You are offline', 'error'); }catch(e){} });
  window.addEventListener('online', function(){ try{ hideOfflineBanner(); showToast('Back online'); }catch(e){} });

  // Ensure a11y labels on initial load
  document.addEventListener('DOMContentLoaded', function(){ try{ ensureAriaLabels(); }catch(e){} });

  // Intercept navigation clicks and fetch to ensure modals are closed before navigation or network activity
  document.addEventListener('click', function(ev){
    try{
      var a = ev.target.closest && ev.target.closest('a');
      if (a && a.getAttribute('href') && !a.getAttribute('data-no-close')){
        try{ if (typeof window.closeAllModals === 'function') window.closeAllModals(); }catch(e){}
        try{ closeAllBottomSheets(); }catch(e){}
      }
      var f = ev.target.closest && ev.target.closest('form');
      if (f && !f.getAttribute('data-no-close')){
        try{ if (typeof window.closeAllModals === 'function') window.closeAllModals(); }catch(e){}
        try{ closeAllBottomSheets(); }catch(e){}
      }
    }catch(e){}
  }, true);

  // Monkeypatch fetch to close modals before network calls
  if (window.fetch && !window._fetch_with_modal_guard) {
    window._fetch_with_modal_guard = true;
    const _origFetch = window.fetch.bind(window);
    window.fetch = function(){ try{ if (typeof window.closeAllModals === 'function') window.closeAllModals(); }catch(e){} try{ closeAllBottomSheets(); }catch(e){} return _origFetch.apply(this, arguments); };
  }

})();
