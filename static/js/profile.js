(function(){
  'use strict';
  function el(sel, ctx){ return (ctx||document).querySelector(sel); }
  function create(tag, cls){ var d=document.createElement(tag); if(cls) d.className=cls; return d; }

  document.addEventListener('DOMContentLoaded', function(){
    var root = document.getElementById('profileRoot'); if(!root) return;
    var username = root.dataset.username;
    var api = '/api/v1/users/' + encodeURIComponent(username);
    fetch(api).then(function(r){ return r.json() }).then(function(res){ if(!res || !res.success) return; renderProfile(res.data); }).catch(function(){ /* ignore */ });

    function renderProfile(data){
      var u = data.user;
      el('#profileFullName').textContent = u.full_name || u.username;
      el('#profileHeadline').textContent = u.headline || '';
      var avatar = el('#profileAvatar');
      if(u.avatar){ avatar.innerHTML = '<img src="'+u.avatar+'" alt="avatar">'; }
      var cover = el('#coverImage'); if(cover && u.cover_image_url) cover.style.backgroundImage = 'url('+u.cover_image_url+')';
      el('#followersCount').textContent = data.followers_count || 0;
      el('#followingCount').textContent = data.following_count || 0;
      if(data.is_owner){ el('#viewsCountWrap').style.display='inline-block'; el('#viewsCount').textContent = (u.profile_views||0); }

      // Actions
      var actions = el('#profileActions'); actions.innerHTML = '';
      if(data.is_owner){
        var edit = create('button','btn'); edit.textContent='Edit Profile'; actions.appendChild(edit);
        var add = create('button','btn'); add.style.marginLeft='6px'; add.textContent='+ Add Project'; actions.appendChild(add);
        var share = create('button','btn'); share.style.marginLeft='6px'; share.textContent='Share Profile (QR)'; actions.appendChild(share);
      } else {
        var follow = create('button','btn'); follow.textContent = data.is_following ? 'Unfollow' : 'Follow'; follow.addEventListener('click', function(){ toggleFollow(data.user.id, follow); }); actions.appendChild(follow);
        var msg = create('button','btn'); msg.textContent='Message'; msg.style.marginLeft='6px'; actions.appendChild(msg);
        var hire = create('button','btn'); hire.textContent='Hire Me / Job Offer'; hire.style.marginLeft='6px'; actions.appendChild(hire);
        if(u.cv_url){ var dl = create('a','btn'); dl.href = u.cv_url; dl.textContent = 'Download Resume (PDF)'; dl.style.marginLeft='6px'; dl.setAttribute('download',''); actions.appendChild(dl); }
      }

      // Default to feed tab
      loadTab('feed', data);
      document.querySelectorAll('.profile-tabs .tab').forEach(function(b){ b.addEventListener('click', function(){ document.querySelectorAll('.profile-tabs .tab').forEach(function(x){ x.classList.remove('active') }); b.classList.add('active'); loadTab(b.dataset.tab, data); }); });
    }

    function loadTab(tab, data){
      var container = el('#tabContent'); container.innerHTML = '';
      if(tab === 'feed'){
        var w = create('div'); w.textContent = 'Loading posts…'; container.appendChild(w);
        // Fetch user's posts (simple)
        fetch('/feed/user/'+encodeURIComponent(data.user.username)).then(function(r){ return r.text(); }).then(function(html){ container.innerHTML = html; }).catch(function(){ container.innerHTML = '<div class="feed-empty-state">No posts yet.</div>'; });
      } else if(tab === 'portfolio'){
        var grid = create('div','portfolio-grid'); data.portfolio.forEach(function(p){ var card = create('div','portfolio-card'); card.innerHTML = '<div style="height:140px;background-size:cover;background-position:center;background-image:url('+ (p.image_path||p.image_url||'') +')"></div><h4>'+ (p.title||'Untitled') +'</h4><p>'+ (p.description||'') +'</p><a href="'+ (p.project_url||'#') +'" target="_blank" class="btn">View Live Project</a>'; grid.appendChild(card); }); if(data.is_owner){ var add = create('button','btn'); add.textContent='+ Add Portfolio Project'; add.style.display='block'; add.style.marginTop='12px'; container.appendChild(add); } container.appendChild(grid);
      } else if(tab === 'skills'){
        var wrap = create('div');
        var skills = data.user.skills || [];
        var skwrap = create('div'); skills.forEach(function(s){ var pill = create('button','skill-pill'); pill.textContent = s; pill.addEventListener('click', function(){ endorseSkill(data.user.id, s, pill); }); skwrap.appendChild(pill); }); wrap.appendChild(skwrap);
        // Timeline
        var t = create('div','timeline'); data.experiences.forEach(function(e){ var item = create('div'); item.innerHTML = '<strong>'+e.role+'</strong> @ '+e.company_name+' <div class="text-sm">'+(e.start_date||'')+' - '+(e.end_date||'')+'</div><p>'+ (e.description||'') +'</p>'; t.appendChild(item); }); wrap.appendChild(t);
        // Education
        var ed = create('div'); ed.innerHTML = '<h4>Education</h4>'; data.education.forEach(function(edr){ ed.innerHTML += '<div><strong>'+edr.degree+'</strong> - '+edr.institution+' ('+(edr.start_year||'')+' - '+(edr.end_year||'')+')</div>'; }); wrap.appendChild(ed);
        // Contact & Socials
        var contact = create('div'); contact.innerHTML = '<h4>Contact</h4>' + (data.user.phone_number ? '<div>Phone: '+data.user.phone_number+'</div>' : '') + (data.user.social_links ? '<div>Socials: '+ JSON.stringify(data.user.social_links) +'</div>' : ''); wrap.appendChild(contact);
        container.appendChild(wrap);
      }
    }

    function toggleFollow(targetId, btn){
      fetch('/follow/'+targetId, {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}}).then(function(r){ return r.json(); }).then(function(res){ if(res && res.success){ btn.textContent = res.following ? 'Unfollow' : 'Follow'; el('#followersCount').textContent = res.count || el('#followersCount').textContent; } });
    }

    function endorseSkill(userId, skillName, btn){
      fetch('/api/v1/skills/endorse', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user_id:userId, skill_name:skillName})}).then(function(r){ return r.json(); }).then(function(res){ if(res && res.success){ btn.textContent = skillName + ' ('+res.count+')'; } });
    }
  });
})();
