// Delegated click handler for feed interactions: follow, like, comment, share
(function(){
  function jsonFetch(url, opts){
    opts = opts || {};
    opts.headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});
    return fetch(url, opts).then(function(r){ return r.json().catch(function(){ return r; }); });
  }

  document.addEventListener('click', async function(e){
    var followBtn = e.target.closest('[data-action="follow"]');
    if(followBtn){
      e.preventDefault();
      var userId = followBtn.dataset.userId;
      if(!userId) return;
      followBtn.disabled = true;
      try{
        var data = await jsonFetch('/api/follow/' + encodeURIComponent(userId), { method: 'POST' });
        if(data && data.following !== undefined){
          followBtn.textContent = data.following ? (followBtn.dataset.followingLabel || 'Following') : (followBtn.dataset.followLabel || 'Follow');
          followBtn.classList.toggle('bg-blue-600', !!data.following);
          followBtn.classList.toggle('text-white', !!data.following);
        }
      }catch(err){
        console.error('follow error', err);
      }finally{ followBtn.disabled = false; }
      return;
    }

    var likeBtn = e.target.closest('[data-action="like"]');
    if(likeBtn){
      e.preventDefault();
      var postId = likeBtn.dataset.postId;
      if(!postId) return;
      likeBtn.disabled = true;
      try{
        var data = await jsonFetch('/api/like/' + encodeURIComponent(postId), { method: 'POST' });
        if(data && data.liked !== undefined){
          var countEl = likeBtn.querySelector('.like-count');
          if(countEl) countEl.textContent = data.like_count;
          likeBtn.classList.toggle('text-pink-400', !!data.liked);
        }
      }catch(err){ console.error('like error', err);}finally{ likeBtn.disabled = false; }
      return;
    }

    // Toggle dropdown menus
    var menuToggle = e.target.closest('[data-action="toggle-menu"]');
    if(menuToggle){
      e.preventDefault();
      var root = menuToggle.closest('[data-dropdown]');
      if(!root) return;
      var menu = root.querySelector('[data-dropdown-menu]');
      if(!menu) return;
      var isHidden = menu.classList.contains('hidden');
      document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){ if(m !== menu) m.classList.add('hidden'); });
      if(isHidden){ menu.classList.remove('hidden'); } else { menu.classList.add('hidden'); }
      return;
    }

    // Close dropdown when clicking outside
    var openMenu = document.querySelector('[data-dropdown] [data-dropdown-menu]:not(.hidden)');
    if(openMenu && !e.target.closest('[data-dropdown]')){
      openMenu.classList.add('hidden');
    }

  }, false);

  // Close menus on ESC
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape'){ document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){ m.classList.add('hidden'); }); } });
})();
