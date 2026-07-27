// Delegated click handler for feed interactions: dropdown toggles and outside clicks
(function(){
  var activeDropdownMenu = null;
  var backdropId = 'postDropdownBackdrop';

  function getBackdrop(){
    return document.getElementById(backdropId);
  }

  function closeDropdown(){
    if(activeDropdownMenu){
      activeDropdownMenu.classList.add('hidden');
      activeDropdownMenu.setAttribute('aria-hidden', 'true');
      activeDropdownMenu = null;
    }
    var backdrop = getBackdrop();
    if(backdrop){ backdrop.classList.add('hidden'); }
  }

  function openDropdown(menu){
    closeDropdown();
    menu.classList.remove('hidden');
    menu.setAttribute('aria-hidden', 'false');
    activeDropdownMenu = menu;
    var backdrop = getBackdrop();
    if(backdrop){ backdrop.classList.remove('hidden'); }
  }

  document.addEventListener('click', function(e){
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
      document.querySelectorAll('[data-dropdown] [data-dropdown-menu]').forEach(function(m){
        if(m !== menu){
          m.classList.add('hidden');
          m.setAttribute('aria-hidden', 'true');
        }
      });
      if(isHidden){
        openDropdown(menu);
      } else {
        closeDropdown();
      }
      return;
    }

    var openMenu = document.querySelector('[data-dropdown] [data-dropdown-menu]:not(.hidden)');
    if(openMenu && !e.target.closest('[data-dropdown]')){
      closeDropdown();
    }
  }, false);

  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape'){
      closeDropdown();
    }
  });

  document.addEventListener('click', function(e){
    if(e.target.id === backdropId){
      closeDropdown();
    }
  });
})();
