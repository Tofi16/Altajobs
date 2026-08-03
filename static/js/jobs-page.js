/**
 * AltaJobs — jobs-page.js
 * Category filter pills + infinite "Load more" pagination for the Jobs
 * home page. Simple by design — no like/comment/follow machinery, since
 * job listings are informational, not social posts.
 */
(function () {
  'use strict';

  var wrap = document.getElementById('jobsLoadMoreWrap');
  var container = document.getElementById('jobsContainer');
  var btn = document.getElementById('jobsLoadMoreBtn');
  var filterBar = document.getElementById('jobsFilters');
  if (!wrap || !container) return;

  var page = parseInt(wrap.dataset.page || '1', 10);
  var hasNext = wrap.dataset.hasNext === '1';
  var activeCategory = wrap.dataset.category || 'all';
  var queryText = wrap.dataset.query || '';
  var loading = false;

  function buildUrl(targetPage) {
    var params = new URLSearchParams();
    params.set('category', activeCategory);
    if (queryText) params.set('q', queryText);
    return '/jobs/page/' + targetPage + '?' + params.toString();
  }

  function loadNextPage() {
    if (loading || !hasNext) return;
    loading = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

    fetch(buildUrl(page + 1), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data && data.success && data.html) {
          container.insertAdjacentHTML('beforeend', data.html);
          page = data.page;
          hasNext = !!data.has_next;
        } else {
          hasNext = false;
        }
      })
      .catch(function () {})
      .finally(function () {
        loading = false;
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Load more jobs';
          btn.hidden = !hasNext;
        }
      });
  }

  if (btn) btn.addEventListener('click', loadNextPage);

  if (filterBar) {
    filterBar.addEventListener('click', function (e) {
      var pill = e.target.closest('.jobs-filter');
      if (!pill || loading) return;
      var newCategory = pill.dataset.category || 'all';
      if (newCategory === activeCategory) return;

      var url = new URL(window.location.href);
      url.searchParams.set('category', newCategory);
      url.searchParams.delete('page');
      window.location.href = url.toString();
    });
  }
})();
