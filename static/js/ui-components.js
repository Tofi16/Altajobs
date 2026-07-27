// ui-components.js
// Vanilla JS UI helpers for AltaJobs: post options, follow optimistic UI,
// compose modal, admin report drawer, timeAgo, skeleton helpers.
(function () {
  'use strict';

  /* Simple toast helper */
  function toast(msg, timeout) {
    timeout = timeout || 1500;
    if (window.showToast && typeof window.showToast === 'function') {
      try { window.showToast(msg, 'success'); return; } catch (e) {}
    }
    var t = document.createElement('div');
    t.className = 'fixed bottom-6 left-1/2 -translate-x-1/2 bg-zinc-800/90 text-white px-4 py-2 rounded-xl z-60 shadow';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, timeout);
  }

  /* timeAgo helper - robust against bad dates */
  function timeAgo(input) {
    if (!input) return '';
    var date = (typeof input === 'number') ? new Date(input) : new Date(String(input));
    if (isNaN(date.getTime())) return '';
    var diff = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diff < 10) return 'just now';
    var intervals = [
      { label: 'y', secs: 31536000 },
      { label: 'mo', secs: 2592000 },
      { label: 'd', secs: 86400 },
      { label: 'h', secs: 3600 },
      { label: 'm', secs: 60 },
      { label: 's', secs: 1 }
    ];
    for (var i = 0; i < intervals.length; i++) {
      var v = Math.floor(diff / intervals[i].secs);
      if (v > 0) return v + intervals[i].label + ' ago';
    }
    return 'just now';
  }

  /* Share helpers */
  function doShare(url) {
    if (navigator.share) {
      navigator.share({ title: document.title, url: url }).catch(function () {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(function () { toast('Link copied'); });
    } else {
      var inp = document.createElement('input'); document.body.appendChild(inp);
      inp.value = url; inp.select(); document.execCommand('copy'); inp.remove(); toast('Link copied');
    }
  }

  function copyToClipboard(url) {
    if (navigator.clipboard) return navigator.clipboard.writeText(url);
    var t = document.createElement('textarea'); t.value = url; document.body.appendChild(t); t.select();
    document.execCommand('copy'); t.remove(); return Promise.resolve();
  }

  /* Post options sheet / desktop popover */
  function openPostOptions(opts) {
    // opts: { postId, postUrl, deleteUrl, buttonRect }
    var overlay = document.getElementById('uiOverlay');
    var sheet = document.getElementById('postOptionsSheet');
    if (!overlay || !sheet) return;
    // Desktop popover if wide
    if (window.innerWidth >= 768 && opts.buttonRect) {
      var pop = document.createElement('div');
      pop.className = 'absolute z-50 bg-zinc-900/95 border border-white/5 rounded-2xl p-2 shadow-lg w-64';
      pop.style.left = Math.min(opts.buttonRect.left, window.innerWidth - 360) + 'px';
      pop.style.top = (opts.buttonRect.bottom + 8) + 'px';
      pop.innerHTML = [
        '<button class="w-full text-left p-3 rounded-2xl hover:bg-white/5 ui-share">Share</button>',
        '<button class="w-full text-left p-3 rounded-2xl hover:bg-white/5 ui-copy">Copy link</button>',
        '<button class="w-full text-left p-3 rounded-2xl hover:bg-white/5 ui-report">Report</button>',
        '<form id="popoverDeleteForm" method="POST" action="' + (opts.deleteUrl || '#') + '"><button class="w-full text-left p-3 rounded-2xl text-red-400 hover:bg-white/5">Delete</button></form>'
      ].join('');
      document.body.appendChild(pop);
      overlay.classList.remove('hidden');
      function cleanup() { pop.remove(); overlay.classList.add('hidden'); }
      overlay.addEventListener('click', cleanup, { once: true });
      pop.querySelector('.ui-share').addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); doShare(opts.postUrl); cleanup(); });
      pop.querySelector('.ui-copy').addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); copyToClipboard(opts.postUrl).then(function(){ toast('Link copied'); }); cleanup(); });
      pop.querySelector('.ui-report').addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); if (opts.reportUrl) { window.location.href = opts.reportUrl; } else { cleanup(); } });
      return;
    }

    // Mobile bottom sheet
    overlay.classList.remove('hidden');
    sheet.classList.remove('translate-y-full');
    sheet.classList.remove('bottom-sheet-active');
    sheet.classList.remove('open');
    sheet.classList.add('translate-y-full');
    // set forms
    var delForm = document.getElementById('sheetDeleteForm');
    var reportForm = document.getElementById('sheetReportForm');
    if (delForm) delForm.action = opts.deleteUrl || '#';
    if (reportForm) {
      reportForm.action = opts.reportUrl || '/submit_report';
      var targetInput = reportForm.querySelector('[name="target_id"]');
      if (targetInput) targetInput.value = opts.postId || '';
    }
    var nativeShareBtn = document.getElementById('nativeShareBtn');
    var copyLinkBtn = document.getElementById('copyLinkBtn');
    var cancelBtn = document.getElementById('postSheetCancel');
    function closeSheet() { sheet.classList.add('translate-y-full'); overlay.classList.add('hidden'); }
    if (nativeShareBtn) { nativeShareBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); doShare(opts.postUrl); closeSheet(); }; }
    if (copyLinkBtn) { copyLinkBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); copyToClipboard(opts.postUrl).then(function(){ toast('Link copied'); }); closeSheet(); }; }
    if (cancelBtn) { cancelBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); closeSheet(); }; }
    overlay.onclick = function (e) { if (e.target === overlay) closeSheet(); };
  }

  /* Compose modal behavior */
  function initCompose() {
    var launcher = document.getElementById('composeLauncher');
    var overlay = document.getElementById('composeModalOverlay');
    var modal = document.getElementById('composeModal');
    var typeInput = document.getElementById('composePostType');
    var typeDesc = document.getElementById('composeTypeDesc');
    if (!launcher || !overlay || !modal || !typeInput) return;

    var typeMessages = {
      general: 'Share an update or story with your network.',
      job: 'Highlight a role and attract the right applicants.',
      skill: 'Showcase a skill or career milestone.',
    };

    var updateTypeSelection = function (selectedType) {
      selectedType = selectedType || 'general';
      document.querySelectorAll('.compose-type-card').forEach(function (card) {
        if (card.dataset.type === selectedType) {
          card.classList.add('active');
        } else {
          card.classList.remove('active');
        }
      });
      typeInput.value = selectedType;
      if (typeDesc) {
        typeDesc.textContent = typeMessages[selectedType] || typeMessages.general;
      }
    };

    var openCompose = function () {
      overlay.classList.remove('hidden');
      overlay.classList.add('flex');
      modal.classList.remove('hidden');
      modal.classList.add('flex');
      setTimeout(function () {
        var textarea = document.getElementById('composeTextarea');
        if (textarea) textarea.focus();
      }, 20);
    };

    var closeCompose = function () {
      overlay.classList.add('hidden');
      overlay.classList.remove('flex');
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    };

    launcher.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      openCompose();
    });

    launcher.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        launcher.click();
      }
    });

    var close = document.getElementById('composeModalClose');
    if (close) {
      close.addEventListener('click', function (e) {
        e.preventDefault();
        closeCompose();
      });
    }

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) {
        closeCompose();
      }
    });

    document.querySelectorAll('.compose-type-card').forEach(function (card) {
      card.addEventListener('click', function (e) {
        e.preventDefault();
        updateTypeSelection(card.dataset.type);
      });
    });

    document.querySelectorAll('.compose-launch-action').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        updateTypeSelection(btn.dataset.type);
        openCompose();
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !overlay.classList.contains('hidden')) {
        closeCompose();
      }
    });
  }

  /* Admin report drawer */
  function openReportDrawer(reportId) {
    var overlay = document.getElementById('uiOverlay');
    var drawer = document.getElementById('reportDrawer');
    if (!overlay || !drawer) return;
    overlay.classList.remove('hidden'); drawer.classList.remove('translate-x-full');
    var body = document.getElementById('reportDrawerBody');
    if (body) body.innerHTML = '<div class="animate-pulse space-y-3"> <div class="h-6 bg-white/6 rounded"></div> <div class="h-40 bg-white/6 rounded"></div> </div>';
    fetch('/api/report/' + reportId).then(function (r) { return r.json(); }).then(function (data) {
      if (!body) return;
      body.innerHTML = '';
      var html = '';
      html += '<div class="space-y-3">';
      html += '<div class="text-sm text-slate-400">Reporter</div>';
      html += '<div class="font-bold">' + escapeHtml(data.reporter.name) + ' (@' + escapeHtml(data.reporter.username) + ')</div>';
      html += '<div class="text-sm text-slate-400 mt-3">Reason</div>';
      html += '<div class="p-3 rounded-xl bg-white/4">' + escapeHtml(data.reason) + '</div>';
      html += '<div class="text-sm text-slate-400 mt-3">Original post</div>';
      html += '<div class="p-3 rounded-xl bg-white/6">' + escapeHtml(data.post.content || '') + '</div>';
      html += '<div class="mt-4 flex gap-2">';
      html += '<button id="banUserBtn" class="flex-1 bg-red-600 py-2 rounded-xl text-white font-bold">Ban User</button>';
      html += '<button id="deletePostBtn" class="flex-1 bg-amber-500 py-2 rounded-xl text-black font-bold">Delete Post</button>';
      html += '<button id="dismissReportBtn" class="flex-1 border py-2 rounded-xl">Dismiss</button>';
      html += '</div></div>';
      body.innerHTML = html;
      document.getElementById('banUserBtn').addEventListener('click', function () { if (!confirm('Ban this user?')) return; fetch('/admin/ban_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:data.post.user_id})}).then(function(){ toast('User banned'); closeDrawer(); }); });
      document.getElementById('deletePostBtn').addEventListener('click', function () { if (!confirm('Delete post?')) return; fetch('/admin/delete_post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:data.post.id})}).then(function(){ toast('Post deleted'); closeDrawer(); }); });
      document.getElementById('dismissReportBtn').addEventListener('click', function () { fetch('/admin/dismiss_report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report_id:reportId})}).then(function(){ toast('Report dismissed'); closeDrawer(); }); });
    }).catch(function () { if (body) body.innerHTML = '<div class="text-red-400">Unable to load report</div>'; });
    function closeDrawer() { drawer.classList.add('translate-x-full'); overlay.classList.add('hidden'); }
    document.getElementById('reportDrawerClose').addEventListener('click', closeDrawer);
    overlay.addEventListener('click', closeDrawer, { once:true });
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { closeDrawer(); document.removeEventListener('keydown', esc); } });
  }

  function escapeHtml(s) { return (s||'').toString().replace(/[&<>\"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]||c; }); }

  /* Skeleton helper - returns element */
  function createSkeleton(lines) {
    lines = lines || 3; var wrap = document.createElement('div'); wrap.className = 'animate-pulse space-y-2';
    for (var i=0;i<lines;i++) { var d = document.createElement('div'); d.className = 'h-3 bg-white/6 rounded'; if (i===0) d.className = 'h-4 bg-white/6 rounded w-3/4'; wrap.appendChild(d); }
    return wrap;
  }

  /* Delegation bindings */
  document.addEventListener('click', function (e) {
    // three-dot menu
    var btn = e.target.closest('.js-post-menu-btn');
    if (btn) {
      if (btn.dataset.useUiPostMenu === 'false') {
        cancelActionClick(e);
        return;
      }
      e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
      var postId = btn.dataset.postId || '';
      var postUrl = btn.dataset.postUrl || (window.location.origin + '/post/' + postId);
      var deleteUrl = btn.dataset.deleteUrl || '#';
      var rect = btn.getBoundingClientRect();
      openPostOptions({ postId: postId, postUrl: postUrl, deleteUrl: deleteUrl, buttonRect: rect });
      return;
    }

    // admin report openers
    var r = e.target.closest('.js-open-report');
    if (r) { e.preventDefault(); e.stopPropagation(); openReportDrawer(r.dataset.reportId); return; }
  }, { passive:false });

  // init compose when DOM ready
  document.addEventListener('DOMContentLoaded', function () { initCompose(); });

  // expose helpers for other scripts
  window.AJUI = window.AJUI || {};
  window.AJUI.timeAgo = timeAgo;
  window.AJUI.createSkeleton = createSkeleton;
  window.AJUI.doShare = doShare;
  window.AJUI.openPostOptions = openPostOptions;
  window.AJUI.openReportDrawer = openReportDrawer;

})();
