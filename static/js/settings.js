// Settings page JS: fetch and persist preferences, handle theme toggle and password change
(function(){
  'use strict';
  function el(s){ return document.querySelector(s); }
  function elAll(s){ return Array.from(document.querySelectorAll(s)); }
  function show(msg, type){ try{ if(window.showToast) window.showToast(msg, type); else alert(msg); }catch(e){console.log(msg);} }

  document.addEventListener('DOMContentLoaded', function(){
    if (!el('.settings-shell')) return;
    // fetch settings
    fetch('/api/v1/settings').then(r=>r.json()).then(function(res){ if(!res || !res.success) return; init(res.settings); }).catch(()=>{});

    function init(s){
      // language display
      var langTitle = document.querySelector('.settings-row-title');
      // theme toggle
      var themeToggle = document.getElementById('themeToggle');
      var thumb = document.getElementById('themeThumb');
      if(themeToggle){
        var current = localStorage.getItem('theme_mode') || s.theme_mode || 'dark';
        themeToggle.checked = current !== 'light';
        document.documentElement.classList.toggle('light-mode', current === 'light');
        if(thumb) thumb.style.transform = themeToggle.checked ? 'translateX(0)' : 'translateX(20px)';
        themeToggle.addEventListener('change', function(){
          var dark = themeToggle.checked;
          document.documentElement.classList.toggle('light-mode', !dark);
          var mode = dark ? 'dark' : 'light';
          localStorage.setItem('theme_mode', mode);
          if(thumb) thumb.style.transform = dark ? 'translateX(0)' : 'translateX(20px)';
          // persist
          fetch('/api/v1/settings/preferences', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({theme_mode: mode})});
        });
      }

      // Notification toggles (if later added)
      var jobAlerts = document.getElementById('jobAlertsToggle');
      if(jobAlerts){ jobAlerts.checked = !!s.notifications_job_alerts; jobAlerts.addEventListener('change', function(){ fetch('/api/v1/settings/preferences', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({notifications_job_alerts: jobAlerts.checked})}); }); }

      var msgAlerts = document.getElementById('messageAlertsToggle');
      if(msgAlerts){ msgAlerts.checked = !!s.notifications_messages; msgAlerts.addEventListener('change', function(){ fetch('/api/v1/settings/preferences', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({notifications_messages: msgAlerts.checked})}); }); }

      // language modal actions — persist via settings API then reload
      elAll('#langModal a').forEach(function(a){ a.addEventListener('click', function(ev){ ev.preventDefault(); var href = a.getAttribute('href'); try{ var m = href.match(/lang=|set_language\/(\w+)/); var lang = null; if(m){ lang = m[1] || null; } if(!lang){ // try query param
            var parts = href.split('?'); if(parts.length>1){ var params = new URLSearchParams(parts[1]); lang = params.get('lang'); }
          }
          if(!lang){ // fallback to href path last segment
            var seg = href.split('/').pop(); if(seg) lang = seg;
          }
          if(lang){
            fetch('/api/v1/settings/preferences', { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ language: lang }) }).then(function(r){ return r.json(); }).then(function(res){ if(res && res.success) location.reload(); else location.reload(); }).catch(function(){ location.reload(); });
            return false;
          }
        }catch(e){ /* ignore and fallback */ }
        fetch(href).then(function(){ location.reload(); }); return false; }); });

      // change password form (if present)
      var pwdForm = document.getElementById('changePasswordForm');
      if(pwdForm){ pwdForm.addEventListener('submit', function(e){ e.preventDefault(); var old = pwdForm.querySelector('[name=old_password]').value; var nw = pwdForm.querySelector('[name=new_password]').value; fetch('/api/v1/auth/change-password', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({old_password: old, new_password: nw})}).then(r=>r.json()).then(function(res){ if(res && res.success){ show('Password changed', 'success'); pwdForm.reset(); } else { show(res && res.error ? res.error : 'Failed', 'error'); } }).catch(function(){ show('Request failed', 'error'); }); }); }

      // logout all devices
      var logoutAllBtn = document.getElementById('logoutAllBtn');
      if(logoutAllBtn){ logoutAllBtn.addEventListener('click', function(){ if(!confirm('Logout from all other devices?')) return; fetch('/api/v1/auth/logout-all-devices', {method:'POST'}).then(r=>r.json()).then(function(res){ if(res && res.success){ show('All sessions revoked'); setTimeout(function(){ location.href = '/'; }, 600); } else show('Failed to logout other devices', 'error'); }); }); }
    }
  });
})();
