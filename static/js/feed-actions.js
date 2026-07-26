// Delegated click handler for feed interactions: dropdown toggles and outside clicks
(function(){
  document.addEventListener('click', function(e){
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
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape'){
      document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){ m.classList.add('hidden'); });
    }
  });
})();
