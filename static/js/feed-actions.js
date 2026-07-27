// Delegated click handler for feed interactions: dropdown toggles and outside clicks
(function(){
  var activeDropdownMenu = null;
  document.addEventListener('click', function(e){
    // Toggle dropdown menus
    var menuToggle = e.target.closest('[data-action="toggle-menu"]');
    if(menuToggle){
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      var root = menuToggle.closest('[data-dropdown]');
      if(!root) return;
      var menu = root.querySelector('[data-dropdown-menu]');
      if(!menu) return;
      var isHidden = menu.classList.contains('hidden');
      document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){ if(m !== menu) m.classList.add('hidden'); });
      if(isHidden){
        menu.classList.remove('hidden');
        activeDropdownMenu = menu;
      } else {
        menu.classList.add('hidden');
        activeDropdownMenu = null;
      }
      return;
    }

    // Close dropdown when clicking outside
    var openMenu = document.querySelector('[data-dropdown] [data-dropdown-menu]:not(.hidden)');
    if(openMenu && !e.target.closest('[data-dropdown]')){
      openMenu.classList.add('hidden');
      activeDropdownMenu = null;
    }
  }, false);

  // Close menus on ESC
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape'){
      document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){ m.classList.add('hidden'); });
    }
  });
})();
