window.AltaJobsNotifications = (function () {
  const badgeSelector = '.topbar-icon-wrap .topbar-badge';
  const bellButton = document.getElementById('headerBellToggle');
  let socket = null;

  function getBadge() {
    return document.querySelector(badgeSelector);
  }

  function updateBadge(count) {
    let badge = getBadge();
    if (!badge) {
      if (!bellButton) return;
      badge = document.createElement('span');
      badge.className = 'topbar-badge pulse';
      bellButton.appendChild(badge);
    }
    badge.textContent = count > 9 ? '9+' : String(count);
  }

  function incrementBadge() {
    const badge = getBadge();
    if (!badge) {
      updateBadge(1);
      return;
    }
    const current = parseInt(badge.textContent, 10);
    updateBadge(isNaN(current) ? 1 : current + 1);
  }

  function init() {
    if (typeof io !== 'function') {
      return;
    }
    try {
      socket = io();
      socket.on('connect', () => {
        console.debug('Socket connected', socket.id);
      });
      socket.on('notification_received', function (payload) {
        if (!payload || !payload.type) return;
        incrementBadge();
      });
    } catch (err) {
      console.warn('Socket.IO notification initialization failed', err);
    }
  }

  return {
    init,
  };
})();

document.addEventListener('DOMContentLoaded', function () {
  if (window.AltaJobsNotifications) {
    window.AltaJobsNotifications.init();
  }
});
