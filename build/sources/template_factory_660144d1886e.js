(function () {
  'use strict';

  const MOBILE_NAV_MQ = 900;
  const LS_USER = '311chat.user';
  const LS_LIKES = '311chat.likes';
  const SITE_JSON_URL = (document.currentScript && document.currentScript.getAttribute('data-site')) || 'site.json';

  let SITE_ID = '311chat';
  let site = null;
  let COLORS = ['#0b1c2c', '#1b6b73', '#c0362c', '#2a4a62', '#8a3b32', '#345c6e'];
  let TRENDS = [];
  let PLACES = [];
  let TOPICS = [];
  let NESTS = [];
  let adminNests = [];
  let userNests = [];
  let pendingUserNests = {};
  let currentNest = null;
  var paintedNestSlug = null;
  var memberNestsUnsub = null;
  var nestAddSlugDirty = false;

  // Path segments that must never be a nest. Existing nest slugs are checked live.
  var NEST_RESERVED = {
    '': 1, home: 1, feed: 1, thoughts: 1, following: 1, explore: 1,
    notifications: 1, chat: 1, profile: 1, news: 1, about: 1, terms: 1,
    privacy: 1, api: 1, admin: 1, watchlist: 1, stories: 1, hot: 1, new: 1,
    'index.html': 1, 'terms.html': 1, 'privacy.html': 1, 'factory.js': 1,
    'styles.css': 1, 'site.json': 1, 'robots.txt': 1, 'favicon.svg': 1,
    'favicon.ico': 1, 'apple-touch-icon.png': 1, 'og.png': 1, '404.html': 1,
    'app.js': 1, 'taxonomy.json': 1, cname: 1
  };

  let fbAuth = null;
  let fbDb = null;
  let fbStorage = null;
  let livePosts = [];
  let liveReady = false;
  let liveError = null;
  let replyTo = null;
  let attachedFile = null;
  let pollActive = false;
  let previewObjectUrl = null;
  let siteKilled = false;
  let blockedUids = {};
  let blocksUnsub = null;
  let convsUnsub = null;
  let msgsUnsub = null;
  let dmConversations = [];
  let activeConvId = null;
  let pendingPeer = null;
  let viewingProfile = null;
  const ADMIN_UID = 'o774wL9hUVSi19EkDCgLqQomP8i2';
  const DM_TEXT_MAX = 1000;

  const FB_WEB_CONFIG_URL = 'https://subx-skins.web.app/firebase-web-config.json';

  function initFirebaseFromHostedConfig() {
    return fetch(FB_WEB_CONFIG_URL, { credentials: 'omit' })
      .then(function (res) {
        if (!res.ok) throw new Error('Firebase web config HTTP ' + res.status);
        return res.json();
      })
      .then(function (cfg) {
        if (!cfg || !cfg.apiKey || !cfg.projectId || !cfg.appId) {
          throw new Error('Firebase web config incomplete');
        }
        firebase.initializeApp({
          apiKey: cfg.apiKey,
          authDomain: cfg.authDomain,
          projectId: cfg.projectId,
          storageBucket: cfg.storageBucket,
          messagingSenderId: cfg.messagingSenderId,
          appId: cfg.appId
        });
        fbAuth = firebase.auth();
        var persist = Promise.resolve();
        try {
          persist = fbAuth.setPersistence(firebase.auth.Auth.Persistence.LOCAL) || Promise.resolve();
        } catch (ePersist) { console.warn('auth persistence', ePersist); }
        fbDb = firebase.firestore();
        fbStorage = firebase.storage();
        try {
          if (cfg.appCheckSiteKey) firebase.appCheck().activate(cfg.appCheckSiteKey, true);
        } catch (e2) { console.warn('app-check', e2); }
        return Promise.resolve(persist).catch(function (ePersist) {
          console.warn('auth persistence', ePersist);
        });
      })
      .catch(function (e) { console.warn('subx-skins init', e); });
  }

  var fbReadyPromise = initFirebaseFromHostedConfig();

  function runWithAuth(errEl, fn) {
    var go = function () {
      if (!fbAuth) {
        if (errEl) {
          errEl.textContent = 'Auth is not ready.';
          errEl.classList.add('show');
        }
        return;
      }
      fn();
    };
    if (fbAuth) go();
    else fbReadyPromise.then(go);
  }

  const hamburger = document.getElementById('hamburger');
  const sidebar = document.getElementById('sidebar');

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }
  function saveJSON(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* private mode */ }
  }

  let currentUser = loadJSON(LS_USER, null);
  let likes = loadJSON(LS_LIKES, {});
  let currentTab = 'foryou';

  function initials(name) {
    return String(name || 'M').split(/\s+/).map(function (w) { return w[0]; }).join('').slice(0, 2).toUpperCase() || 'M';
  }
  function colorFor(handle) {
    let n = 0;
    const h = String(handle || 'm');
    for (let i = 0; i < h.length; i++) n = (n + h.charCodeAt(i) * (i + 1)) % COLORS.length;
    return COLORS[n];
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function looksLikeUid(s) {
    return typeof s === 'string' && /^[A-Za-z0-9]{20,36}$/.test(s);
  }
  function humanName(d, uid) {
    var n = (d && d.authorName) || '';
    if (n && n !== uid && !looksLikeUid(n)) return n;
    var h = (d && d.authorHandle) || '';
    if (h && h !== uid && !looksLikeUid(h)) return h;
    return 'Member';
  }
  function humanHandle(d, uid) {
    var h = (d && d.authorHandle) || '';
    if (h && h !== uid && !looksLikeUid(h)) return h;
    var n = humanName(d, uid);
    return String(n).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
  }
  function liveUid() {
    return (fbAuth && fbAuth.currentUser && fbAuth.currentUser.uid) || null;
  }
  function isLiveUser() {
    return !!(fbAuth && fbAuth.currentUser);
  }
  function findPost(id) {
    for (var i = 0; i < livePosts.length; i++) if (livePosts[i].id === id) return livePosts[i];
    return null;
  }

  var deepPostId = '';
  var deepPostDone = false;
  var shareSheetPostId = null;

  function postPermalink(postId) {
    var host = (location.hostname || '').replace(/^www\./i, '') || '311chat.com';
    return 'https://p.' + host + '/status/' + encodeURIComponent(String(postId || ''));
  }

  function shareTextSlice(post) {
    var t = String((post && (post.title || post.text)) || '').replace(/\s+/g, ' ').trim();
    if (!t) t = ((site && site.name) || SITE_ID || '') + ' post';
    if (t.length > 200) t = t.slice(0, 197) + '...';
    return t;
  }

  function closeShareSheet() {
    var ov = document.getElementById('share-sheet');
    if (ov) ov.hidden = true;
    shareSheetPostId = null;
    var preview = document.getElementById('share-sheet-preview');
    if (preview) {
      preview.removeAttribute('src');
      preview.hidden = true;
    }
  }

  function ensureShareSheet() {
    var ov = document.getElementById('share-sheet');
    if (ov) return ov;
    if (!document.getElementById('share-sheet-css')) {
      var st = document.createElement('style');
      st.id = 'share-sheet-css';
      st.textContent =
        '#share-sheet{position:fixed;inset:0;z-index:80;background:rgba(18,24,28,.42);display:flex;align-items:flex-end;justify-content:center;padding:16px;}' +
        '#share-sheet[hidden]{display:none!important;}' +
        '.share-sheet{width:min(420px,100%);background:var(--surface,#fffaf3);color:var(--text,#1a2a30);border:1px solid var(--border,#e4d6c4);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.18);padding:10px;}' +
        '.share-sheet h3{margin:6px 8px 10px;font-size:15px;font-weight:650;}' +
        '.share-sheet button{display:block;width:100%;text-align:left;background:transparent;border:0;border-radius:10px;padding:11px 12px;font:inherit;font-size:14px;cursor:pointer;color:inherit;}' +
        '.share-sheet button:hover{background:rgba(0,0,0,.06);}' +
        '.share-sheet .share-cancel{color:var(--text-muted,#4a5f66);margin-top:4px;}' +
        '.share-sheet-preview{display:block;width:100%;max-height:160px;object-fit:cover;border-radius:10px;margin:0 0 8px;}' +
        '.share-sheet-preview[hidden]{display:none!important;}' +
        '.post.is-deep-post{box-shadow:inset 0 0 0 2px var(--accent,#e07a3d);border-radius:10px;}';
      document.head.appendChild(st);
    }
    ov = document.createElement('div');
    ov.id = 'share-sheet';
    ov.hidden = true;
    ov.innerHTML =
      '<div class="share-sheet" role="dialog" aria-modal="true" aria-label="Share">' +
        '<img class="share-sheet-preview" id="share-sheet-preview" alt="" hidden>' +
        '<h3>Share</h3>' +
        '<button type="button" data-share="copy">Copy link</button>' +
        '<button type="button" data-share="x">Post on X</button>' +
        '<button type="button" data-share="reddit">Post on Reddit</button>' +
        '<button type="button" class="share-cancel" data-share="close">Cancel</button>' +
      '</div>';
    document.body.appendChild(ov);
    ov.addEventListener('click', function (e) {
      if (e.target === ov) { closeShareSheet(); return; }
      var btn = e.target.closest('[data-share]');
      if (!btn) return;
      var act = btn.getAttribute('data-share');
      if (act === 'close') { closeShareSheet(); return; }
      if (!shareSheetPostId) return;
      var post = findPost(shareSheetPostId);
      var permalink = postPermalink(shareSheetPostId);
      var slice = shareTextSlice(post);
      if (act === 'copy') {
        var done = function () { composeErr('Link copied'); closeShareSheet(); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(permalink).then(done).catch(function () {
            try { window.prompt('Copy link', permalink); } catch (e2) {}
            done();
          });
        } else {
          try { window.prompt('Copy link', permalink); } catch (e3) {}
          done();
        }
        return;
      }
      if (act === 'x') {
        var xUrl = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(slice) +
          '&url=' + encodeURIComponent(permalink);
        window.open(xUrl, '_blank', 'noopener,noreferrer');
        closeShareSheet();
        return;
      }
      if (act === 'reddit') {
        var rUrl = 'https://www.reddit.com/submit?url=' + encodeURIComponent(permalink) +
          '&title=' + encodeURIComponent(slice);
        var sr = site && site.redditSr;
        if (sr) rUrl += '&sr=' + encodeURIComponent(String(sr));
        window.open(rUrl, '_blank', 'noopener,noreferrer');
        closeShareSheet();
      }
    });
    return ov;
  }

  function sharePost(postId) {
    if (!postId) return;
    var post = findPost(postId);
    if (!post) {
      composeErr('Could not find that post.');
      return;
    }
    shareSheetPostId = postId;
    var ov = ensureShareSheet();
    var preview = document.getElementById('share-sheet-preview');
    if (preview) {
      if (post.imageUrl) {
        preview.src = post.imageUrl;
        preview.hidden = false;
      } else {
        preview.removeAttribute('src');
        preview.hidden = true;
      }
    }
    ov.hidden = false;
  }

  function highlightDeepPost() {
    if (!deepPostId || deepPostDone || !liveReady) return;
    var feed = document.getElementById('thoughts-feed');
    if (!feed) return;
    var safe = String(deepPostId).replace(/"/g, '');
    var el = feed.querySelector('[data-post-id="' + safe + '"]');
    if (!el) return;
    deepPostDone = true;
    el.classList.add('is-deep-post');
    try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { el.scrollIntoView(); }
  }

  function isEmailVerified() {
    var u = fbAuth && fbAuth.currentUser;
    return !!(u && u.emailVerified);
  }
  function requireVerified(action) {
    function gateErr(msg) {
      if (action === 'chat') chatErr(msg);
      else composeErr(msg);
    }
    if (!isLiveUser()) {
      gateErr('Sign in to ' + (action || 'post') + '. Guest can only browse.');
      openAuth('join');
      return false;
    }
    if (siteKilled) {
      gateErr('This room is paused.');
      return false;
    }
    if (!isEmailVerified()) {
      gateErr('Verify your email before you ' + (action || 'post') + '. Check your inbox, then refresh.');
      var u = fbAuth.currentUser;
      if (u && u.sendEmailVerification) u.sendEmailVerification().catch(function () {});
      return false;
    }
    return true;
  }
  function syncKillBanner() {
    var el = document.getElementById('kill-banner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'kill-banner';
      el.className = 'preview-banner';
      el.setAttribute('role', 'status');
      el.hidden = true;
      var prev = document.querySelector('.preview-banner');
      if (prev && prev.parentNode) prev.parentNode.insertBefore(el, prev.nextSibling);
      else document.body.insertBefore(el, document.body.firstChild);
    }
    if (siteKilled) {
      el.hidden = false;
      el.textContent = 'This room is paused.';
    } else {
      el.hidden = true;
    }
  }
  function listenKillSwitch() {
    if (!fbDb) return;
    fbDb.collection('sites').doc(SITE_ID).onSnapshot(function (snap) {
      var d = snap.exists ? (snap.data() || {}) : {};
      siteKilled = d.killed === true;
      syncKillBanner();
    }, function () {});
  }
  function listenBlocks(uid) {
    if (blocksUnsub) { blocksUnsub(); blocksUnsub = null; }
    blockedUids = {};
    if (!fbDb || !uid) { renderFeed(); return; }
    blocksUnsub = fbDb.collection('users').doc(uid).collection('blocks').onSnapshot(function (snap) {
      blockedUids = {};
      snap.forEach(function (d) { blockedUids[d.id] = true; });
      renderFeed();
      if (dmsOn()) syncChatChrome();
    }, function () {});
  }
  function reportPost(id) {
    if (!requireVerified('report')) return;
    var post = findPost(id);
    if (!post || !fbDb) return;
    fbDb.collection('reports').add({
      siteId: SITE_ID,
      postId: id,
      targetUid: post.authorUid || '',
      reporterUid: liveUid(),
      reason: 'abuse',
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      composeErr('Reported. Thanks.');
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not report.');
    });
  }
  function blockUser(uid) {
    if (!requireVerified('block')) return;
    if (!uid || uid === liveUid() || !fbDb) return;
    fbDb.collection('users').doc(liveUid()).collection('blocks').doc(uid).set({
      siteId: SITE_ID,
      blockerUid: liveUid(),
      targetUid: uid,
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      composeErr('Blocked. Their posts are hidden for you.');
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not block.');
    });
  }
  window.subxKill = function (on) {
    if (!fbAuth || !fbAuth.currentUser || fbAuth.currentUser.uid !== ADMIN_UID) {
      console.warn('subxKill: not admin');
      return Promise.reject(new Error('not admin'));
    }
    return fbDb.collection('sites').doc(SITE_ID).set({
      killed: !!on,
      siteId: SITE_ID,
      updatedAt: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
  };


  function applyTheme(tokens) {
    if (!tokens) return;
    var root = document.documentElement;
    Object.keys(tokens).forEach(function (k) {
      if (k === 'avatarColors') return;
      if (typeof tokens[k] === 'string') root.style.setProperty('--' + k, tokens[k]);
    });
    if (Array.isArray(tokens.avatarColors) && tokens.avatarColors.length) COLORS = tokens.avatarColors.slice();
  }

  function applySiteChrome() {
    if (!site) return;
    var title = site.name || "311chat";
    var tag = site.tagline || 'Non-emergency city help. Find your 311.';
    document.title = tag ? (title + ' — ' + tag) : title;
    var brandTitle = document.querySelector('.brand-title');
    var brandSub = document.querySelector('.brand-sub');
    var brandMark = document.querySelector('.brand-mark');
    if (brandTitle) brandTitle.textContent = title;
    if (brandSub) brandSub.textContent = tag;
    if (brandMark) brandMark.setAttribute('aria-label', title + ' home');
    var profileSub = document.getElementById('profile-topbar-posts');
    if (profileSub) profileSub.textContent = title + ' · ' + tag;
    var authTitle = document.getElementById('auth-title');
    if (authTitle) authTitle.textContent = 'Join ' + title;
    var authNote = document.querySelector('#cv-auth-overlay .conv-modal-note');
    if (authNote) {
      authNote.textContent = site.trustBlurb || ('Unofficial helper. Not a substitute for 911. Links to official city channels. Guest is browse-only. Preview.');
    }
    var input = document.getElementById('thoughts-compose-input');
    if (input && site.composePlaceholder) {
      input.placeholder = site.composePlaceholder;
      input.setAttribute('data-ph', site.composePlaceholder);
    }
    applyRailChrome();
  }

  function railCfg() {
    return (site && site.rail) || {};
  }

  function railKind() {
    return String(railCfg().kind || '');
  }

  function railUsesCwf() {
    return railKind() === 'nws-cwf';
  }

  function railUsesNws() {
    var cfg = railCfg();
    var kind = railKind();
    if (kind === 'nws-cwf' || kind === 'nws-forecast') return true;
    return !!(cfg.forecastUrl || (cfg.lat != null && cfg.lon != null));
  }

  function applyRailChrome() {
    var cfg = railCfg();
    var hasRail = !!(cfg.kind || cfg.porch || (cfg.outbound && cfg.outbound.length));
    var kicker = cfg.kicker || (hasRail ? 'In the room' : '');
    var title = cfg.title || (hasRail ? 'Room Brief' : '');
    var footer = cfg.footer || (hasRail ? 'Room Brief. Not a news ingest.' : '');
    var rk = document.querySelector('.right-panel-kicker');
    var rt = document.querySelector('.right-panel-title');
    var rf = document.querySelector('.right-panel-footer p');
    var nk = document.querySelector('#page-news .page-kicker');
    var nh = document.querySelector('#page-news h1');
    var tab = document.getElementById('right-panel-tab');
    if (kicker) {
      if (rk) rk.textContent = kicker;
      if (nk) nk.textContent = kicker;
    }
    if (title) {
      if (rt) rt.textContent = title;
      if (nh) nh.textContent = title;
    }
    if (footer && rf) rf.textContent = footer;
    if (tab && title) {
      tab.title = 'Toggle ' + title.toLowerCase();
      tab.setAttribute('aria-label', 'Toggle ' + title.toLowerCase());
    }
  }

  function dmsOn() {
    return !!(site && site.dms === true);
  }

  function hideDummyChrome() {
    document.querySelectorAll('[data-soon]').forEach(function (el) {
      if (dmsOn() && (el.id === 'nav-chat' || el.getAttribute('data-social') === 'chat')) {
        el.classList.remove('is-soon');
        var liveBadge = el.querySelector('.nav-soon');
        if (liveBadge) liveBadge.remove();
        return;
      }
      el.classList.add('is-soon');
      if (!el.querySelector('.nav-soon')) {
        var badge = document.createElement('span');
        badge.className = 'nav-soon';
        badge.textContent = 'Soon';
        el.appendChild(badge);
      }
    });
    var notifBadge = document.getElementById('notif-badge');
    if (notifBadge) {
      notifBadge.textContent = '';
      notifBadge.classList.remove('visible');
      notifBadge.hidden = true;
    }
    document.body.classList.toggle('is-live', isLiveUser());
    document.body.classList.toggle('is-guest', !isLiveUser());
    syncEarlyWelcome();
    syncChatChrome();
    syncStoriesTray();
  }

  function earlyWelcomeOn() {
    return !!(site && site.earlyWelcome === true);
  }

  function earlyWelcomeKey(uid) {
    return 'subx.earlyWelcome.v2.' + (SITE_ID || '') + '.' + String(uid || '');
  }

  function earlyWelcomeDismissed(uid) {
    if (!uid) return true;
    try { return localStorage.getItem(earlyWelcomeKey(uid)) === '1'; } catch (e) { return false; }
  }

  function dismissEarlyWelcome() {
    var uid = liveUid();
    if (uid) {
      try { localStorage.setItem(earlyWelcomeKey(uid), '1'); } catch (e) { /* private mode */ }
    }
    var el = document.getElementById('early-welcome');
    if (el) el.hidden = true;
  }

  function ensureEarlyWelcomeCss() {
    if (document.getElementById('early-welcome-css')) return;
    var st = document.createElement('style');
    st.id = 'early-welcome-css';
    st.textContent =
      '.early-welcome[hidden]{display:none!important;}' +
      '.early-welcome{margin:0.7rem 1rem 0.15rem;padding:0.85rem 0.95rem 0.85rem 1.05rem;' +
        'background:var(--surface,#111);color:var(--text,#f4f4f4);' +
        'border:1px solid var(--border,rgba(255,255,255,0.12));border-radius:10px;' +
        'font-size:0.86rem;line-height:1.45;display:flex;gap:0.75rem;align-items:flex-start;}' +
      '.early-welcome-copy{flex:1;}' +
      '.early-welcome-dismiss{flex:0 0 auto;width:1.7rem;height:1.7rem;padding:0;' +
        'border:1px solid var(--border,rgba(255,255,255,0.18));background:transparent;' +
        'color:var(--text-muted,#9a9aa3);border-radius:8px;cursor:pointer;font-size:1.1rem;line-height:1;}' +
      '.early-welcome-dismiss:hover{color:var(--text,#f4f4f4);background:rgba(255,255,255,0.06);}';
    document.head.appendChild(st);
  }

  function syncEarlyWelcome() {
    var uid = liveUid();
    var user = fbAuth && fbAuth.currentUser;
    var show = earlyWelcomeOn() && !!uid && !!(user && !user.isAnonymous) && !earlyWelcomeDismissed(uid);
    var el = document.getElementById('early-welcome');
    if (!show) {
      if (el) el.hidden = true;
      return;
    }
    ensureEarlyWelcomeCss();
    if (!el) {
      el = document.createElement('div');
      el.id = 'early-welcome';
      el.className = 'early-welcome';
      el.setAttribute('role', 'status');
      el.innerHTML =
        '<div class="early-welcome-copy">' + escapeHtml((site && site.earlyWelcomeCopy) || 'You\'re early. This room is live but unfinished.') + '</div>' +
        '<button type="button" class="early-welcome-dismiss" id="early-welcome-dismiss" aria-label="Dismiss">&times;</button>';
      var compose = document.getElementById('thoughts-compose-wrap');
      if (compose && compose.parentNode) compose.parentNode.insertBefore(el, compose.nextSibling);
      else {
        var feed = document.getElementById('thoughts-feed');
        if (feed && feed.parentNode) feed.parentNode.insertBefore(el, feed);
        else return;
      }
      var btn = document.getElementById('early-welcome-dismiss');
      if (btn) btn.addEventListener('click', dismissEarlyWelcome);
    }
    el.hidden = false;
  }

  function applyFbUser(user) {
    if (!user) return;
    var draft = peekCompose();
    var shouldLand = consumeAuthLand();
    const raw = user.displayName || (user.email || 'member').split('@')[0];
    currentUser = {
      uid: user.uid,
      name: raw,
      handle: String(raw).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member',
      bio: '',
      live: true
    };
    saveJSON(LS_USER, currentUser);
    closeAuth();
    renderSidebarAuth();
    hideDummyChrome();
    syncChatChrome();
    syncProfile();
    listenBlocks(user.uid);
    listenMemberNests(user.uid);
    listenConversations();
    restoreCompose(draft);
    if (shouldLand) landInFeedCompose();
    if (!user.emailVerified) {
      composeErr('Verify your email before posting. Check your inbox, then refresh.');
    }
  }

  function mapLive(doc) {
    const d = doc.data() || {};
    const uid = d.authorUid || null;
    const ms = d.createdAt && d.createdAt.toMillis ? d.createdAt.toMillis() : Date.now();
    const likedBy = d.likes || {};
    return {
      id: doc.id,
      authorUid: uid,
      name: humanName(d, uid),
      handle: humanHandle(d, uid),
      text: d.text || '',
      ms: ms,
      hours: Math.max(0, Math.round((Date.now() - ms) / 3600000)),
      likedBy: likedBy,
      likes: Object.keys(likedBy).length || d.likeCount || 0,
      replies: d.replyCount || 0,
      parentId: d.parentId || null,
      live: true,
      imageUrl: d.imageUrl || null,
      poll: d.poll || null,
      nestSlug: d.nestSlug || ''
    };
  }

  function listenLivePosts() {
    if (!fbDb) {
      composeErr('Feed is not connected.');
      return;
    }
    fbDb.collection('posts')
      .where('siteId', '==', SITE_ID)
      .orderBy('createdAt', 'desc')
      .limit(80)
      .onSnapshot(function (snap) {
        liveReady = true;
        if (liveError) composeErr('');
        liveError = null;
        livePosts = snap.docs.map(mapLive);
        renderFeed();
        if (currentUser) syncProfile();
      }, function (err) {
        liveReady = false;
        liveError = err;
        var msg = (err && err.message) ? err.message : 'Could not load live posts.';
        composeErr('Feed: ' + msg + ' A composite index on posts (siteId ASC, createdAt DESC) may be required in Firebase project subx-skins. Do not treat this as a loaded empty room.');
        renderFeed();
      });
  }

  function composeErr(msg) {
    var el = document.getElementById('thoughts-compose-err');
    if (!el) {
      el = document.createElement('div');
      el.id = 'thoughts-compose-err';
      el.setAttribute('role', 'status');
      el.style.cssText = 'padding:8px 16px 0;font-size:13px;color:#c45e28;';
      var box = document.getElementById('thoughts-compose-wrap');
      if (box) box.appendChild(el);
    }
    el.textContent = msg || '';
  }

  function isMobileNav() { return window.innerWidth <= MOBILE_NAV_MQ; }
  function closeMobileNav() {
    document.body.classList.remove('nav-open');
    syncHamburgerAria();
  }
  function syncHamburgerAria() {
    if (!hamburger) return;
    const open = isMobileNav()
      ? document.body.classList.contains('nav-open')
      : !document.body.classList.contains('nav-collapsed');
    hamburger.setAttribute('aria-expanded', open ? 'true' : 'false');
    hamburger.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  }

  function highlightSocial(name) {
    document.querySelectorAll('.nav-social-link').forEach(function (l) { l.classList.remove('active'); });
    const el = document.querySelector('.nav-social-link[data-social="' + name + '"]') || document.querySelector('.nav-social-link[data-nest="' + name + '"]');
    if (el) el.classList.add('active');
  }

  function closeSocialOverlays() {
    ['explore-overlay', 'notif-overlay', 'chat-overlay', 'profile-overlay'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.classList.remove('active', 'thread-open');
    });
  }

  function showContentPage(id) {
    document.querySelectorAll('.page').forEach(function (p) { p.classList.remove('active'); });
    const page = document.getElementById('page-' + id);
    if (page) page.classList.add('active');
    window.scrollTo(0, 0);
  }

  function nestSlugNorm(s) {
    return String(s || '').replace(/^#/, '').trim().toLowerCase();
  }

  function slugifyNestLabel(label) {
    return nestSlugNorm(label)
      .replace(/['’]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40);
  }

  function nestSlugFromPathname(pathname) {
    var parts = String(pathname || '').split('/').filter(Boolean);
    if (!parts.length || parts.length > 1) return '';
    var first = parts[0];
    try { first = decodeURIComponent(first); } catch (e) { /* keep */ }
    first = nestSlugNorm(first);
    if (!first || NEST_RESERVED[first]) return '';
    return first;
  }

  function findNest(slug) {
    var key = nestSlugNorm(slug);
    if (!key) return null;
    for (var i = 0; i < NESTS.length; i++) {
      if (nestSlugNorm(NESTS[i].slug) === key) return NESTS[i];
    }
    return null;
  }

  function nestSlugError(slug) {
    var key = nestSlugNorm(slug);
    if (!key) return 'Add a slug.';
    if (key.indexOf('/') !== -1) return 'One level only.';
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(key)) return 'Use lowercase letters, numbers, and hyphens.';
    if (key.length < 2 || key.length > 40) return 'Slug must be 2–40 characters.';
    if (NEST_RESERVED[key]) return 'That slug is reserved.';
    if (findNest(key)) return 'That room already exists.';
    return '';
  }

  function resolveNestFromPath() {
    return findNest(nestSlugFromPathname(location.pathname));
  }

  function nestHasActivity(slug) {
    var key = nestSlugNorm(slug);
    if (!key) return false;
    for (var i = 0; i < livePosts.length; i++) {
      if (nestSlugNorm(livePosts[i].nestSlug) === key) return true;
    }
    return false;
  }

  function nestNavVisible(nest) {
    if (!nest || !nest.slug) return false;
    if (nest.nav === false) return false;
    if (nestHasActivity(nest.slug)) return true;
    return nest.nav === true;
  }

  function visibleNests() {
    return NESTS.filter(nestNavVisible);
  }

  function nestPath(slug) {
    var nest = findNest(slug);
    return nest ? ('/' + nest.slug) : '/';
  }

  function currentUrl() {
    return location.pathname + location.search + location.hash;
  }

  function setUrl(path, hash) {
    var next = (path || '/') + (location.search || '') + (hash || '');
    if (currentUrl() === next) { applyRoute(); return; }
    history.pushState({ path: path }, '', next);
    applyRoute();
  }

  function restoreBouncedPath() {
    try {
      var raw = sessionStorage.getItem('subx.restorePath');
      if (!raw) return;
      sessionStorage.removeItem('subx.restorePath');
      if (raw.charAt(0) !== '/' || raw.indexOf('//') !== -1) return;
      history.replaceState(null, '', raw);
    } catch (e) { /* private mode */ }
  }

  function mergeNests() {
    var built = [];
    var seen = {};
    function push(n) {
      if (!n || !n.slug) return;
      var key = nestSlugNorm(n.slug);
      if (!key || seen[key]) return;
      seen[key] = true;
      built.push(n);
    }
    adminNests.forEach(push);
    userNests.forEach(push);
    Object.keys(pendingUserNests).forEach(function (k) { push(pendingUserNests[k]); });
    NESTS = built;
    if (currentNest) currentNest = findNest(currentNest.slug) || null;
    if (currentNest || paintedNestSlug) applyNestChrome();
    else renderNestNav();
  }

  function absorbUserNests(list) {
    userNests = list || [];
    var have = {};
    userNests.forEach(function (n) { have[nestSlugNorm(n.slug)] = true; });
    Object.keys(pendingUserNests).forEach(function (k) {
      if (have[k]) delete pendingUserNests[k];
    });
    mergeNests();
  }

  function listenMemberNests(uid) {
    if (memberNestsUnsub) {
      memberNestsUnsub();
      memberNestsUnsub = null;
    }
    userNests = [];
    pendingUserNests = {};
    hideNestAddForm();
    if (!uid || !fbDb || !SITE_ID) {
      mergeNests();
      return;
    }
    memberNestsUnsub = fbDb.collection('sites').doc(SITE_ID)
      .collection('memberNests').doc(uid)
      .collection('rooms')
      .onSnapshot(function (snap) {
        var list = [];
        snap.forEach(function (d) {
          var data = d.data() || {};
          var slug = nestSlugNorm(data.slug || d.id);
          if (!slug) return;
          list.push({
            slug: slug,
            label: String(data.label || slug).slice(0, 40),
            parent: null,
            kind: 'user',
            blurb: typeof data.blurb === 'string' ? data.blurb : '',
            nav: data.nav !== false,
            user: true
          });
        });
        absorbUserNests(list);
      }, function (err) {
        console.warn('member nests', err);
        absorbUserNests([]);
      });
  }

  function createMemberNest(label, slug) {
    var uid = liveUid();
    if (!uid || !fbDb) return Promise.reject(new Error('Sign in to add a room.'));
    var nest = {
      slug: slug,
      label: label,
      parent: null,
      kind: 'user',
      blurb: '',
      nav: true,
      user: true
    };
    pendingUserNests[slug] = nest;
    mergeNests();
    return fbDb.collection('sites').doc(SITE_ID)
      .collection('memberNests').doc(uid)
      .collection('rooms').doc(slug)
      .set({
        siteId: SITE_ID,
        ownerUid: uid,
        slug: slug,
        label: label,
        parent: null,
        kind: 'user',
        blurb: '',
        nav: true,
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      }).then(function () {
        goNest(slug);
      }).catch(function (e) {
        delete pendingUserNests[slug];
        mergeNests();
        if (nestSlugFromPathname(location.pathname) === slug) go('home');
        throw e;
      });
  }

  function nestRailCards(nest) {
    if (!nest) return [];
    var cards = [];
    var room = (site && site.name) || SITE_ID || 'room';
    if (nest.blurb) {
      cards.push({
        tag: nest.kind || 'Nest',
        headline: nest.label || nest.slug,
        snippet: nest.blurb,
        meta: 'Nest · ' + room,
        url: ''
      });
    }
    var ranks = nest.rankings || [];
    for (var r = 0; r < ranks.length; r++) {
      var pack = ranks[r];
      if (!pack) continue;
      var items = pack.items || [];
      var bits = [];
      for (var i = 0; i < items.length && bits.length < 3; i++) {
        var it = items[i];
        if (!it || !it.name) continue;
        bits.push((it.rank != null ? it.rank + '. ' : '') + it.name);
      }
      cards.push({
        tag: 'Ranking',
        headline: pack.title || 'Ranking',
        snippet: bits.join(' · ') || (pack.title || ''),
        meta: (nest.label || nest.slug) + (items[0] && items[0].priceHint ? ' · ' + items[0].priceHint : ''),
        url: (items[0] && items[0].url) || ''
      });
    }
    var reviews = nest.reviews || [];
    for (var v = 0; v < reviews.length; v++) {
      var rev = reviews[v];
      if (!rev) continue;
      cards.push({
        tag: 'Review',
        headline: (rev.stars != null ? String(rev.stars) + '★ ' : '') + (rev.subject || 'Review'),
        snippet: rev.snippet || '',
        meta: [nest.label || nest.slug, rev.region].filter(Boolean).join(' · '),
        url: rev.url || ''
      });
    }
    var pins = nest.railPins || [];
    for (var p = 0; p < pins.length; p++) {
      var pin = pins[p];
      if (!pin || !pin.headline) continue;
      cards.push({
        tag: pin.tag || 'Pin',
        headline: pin.headline,
        snippet: pin.snippet || '',
        meta: pin.meta || (nest.label || nest.slug),
        url: pin.url || ''
      });
    }
    return cards;
  }

  function applyNestRailChrome(nest) {
    var kicker = 'Nest · ' + ((site && site.name) || SITE_ID || 'room');
    var title = nest.label || nest.slug;
    var footer = nest.blurb || 'Nested room. Not a news ingest.';
    var rk = document.querySelector('.right-panel-kicker');
    var rt = document.querySelector('.right-panel-title');
    var rf = document.querySelector('.right-panel-footer p');
    var nk = document.querySelector('#page-news .page-kicker');
    var nh = document.querySelector('#page-news h1');
    if (rk) rk.textContent = kicker;
    if (nk) nk.textContent = kicker;
    if (rt) rt.textContent = title;
    if (nh) nh.textContent = title;
    if (rf) rf.textContent = footer;
  }

  function ensureNestChrome() {
    var el = document.getElementById('nest-chrome');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'nest-chrome';
    el.className = 'nest-chrome';
    el.hidden = true;
    var tabs = document.querySelector('#page-thoughts .thoughts-tabs');
    if (tabs && tabs.parentNode) tabs.parentNode.insertBefore(el, tabs);
    return el;
  }

  function applyNestChrome() {
    var nest = currentNest;
    var title = (site && site.name) || SITE_ID || 'room';
    var tag = (site && site.tagline) || '';
    document.title = nest
      ? ((nest.label || nest.slug) + ' — ' + title)
      : (tag ? (title + ' — ' + tag) : title);
    var brandSub = document.querySelector('.brand-sub');
    if (brandSub) brandSub.textContent = nest ? (nest.label || nest.slug) : tag;
    var input = document.getElementById('thoughts-compose-input');
    if (input) {
      var ph = nest
        ? ('What about ' + (nest.label || nest.slug) + '?')
        : (input.getAttribute('data-ph') || (site && site.composePlaceholder) || '');
      if (ph) input.placeholder = ph;
    }
    var bar = ensureNestChrome();
    if (bar) {
      if (!nest) {
        bar.hidden = true;
        bar.innerHTML = '';
      } else {
        bar.hidden = false;
        bar.innerHTML =
          '<div class="nest-chrome-kicker">Nest</div>' +
          '<div class="nest-chrome-label">' + escapeHtml(nest.label || nest.slug) + '</div>' +
          (nest.blurb ? '<div class="nest-chrome-blurb">' + escapeHtml(nest.blurb) + '</div>' : '') +
          '<a class="nest-chrome-home" href="#home" data-social="home">Back to home room</a>';
      }
    }
    if (nest) {
      abortPorchForNest();
      if (paintedNestSlug !== nest.slug) {
        paintedNestSlug = nest.slug;
        applyNestRailChrome(nest);
        paintRail(nestRailCards(nest));
      }
    } else if (paintedNestSlug) {
      paintedNestSlug = null;
      applyRailChrome();
      seedRail();
      renderTrends(true);
    }
    refreshNestSurfaces();
  }

  function hideNestAddForm() {
    var form = document.getElementById('nav-nest-form');
    if (form) form.hidden = true;
    nestAddSlugDirty = false;
    var label = document.getElementById('nest-add-label');
    var slug = document.getElementById('nest-add-slug');
    var err = document.getElementById('nest-add-err');
    if (label) label.value = '';
    if (slug) slug.value = '';
    if (err) err.textContent = '';
    var btn = document.getElementById('nest-add-save');
    if (btn) btn.disabled = false;
  }

  function ensureNestNav() {
    var nav = document.querySelector('.sidebar nav');
    var list = document.getElementById('nav-nests');
    if (list || !nav) return list;
    list = document.createElement('ul');
    list.id = 'nav-nests';
    list.className = 'nav-nests';
    list.setAttribute('aria-label', 'Nested rooms');
    list.innerHTML =
      '<li class="nav-nests-label"><span>Nests</span>' +
        '<button type="button" class="nav-nest-add" id="nav-nest-add" aria-label="Add a nested room" title="Add a nested room">+</button></li>' +
      '<li class="nav-nest-form" id="nav-nest-form" hidden>' +
        '<label>Label<input type="text" id="nest-add-label" maxlength="40" autocomplete="off" placeholder="Room name"></label>' +
        '<label>Slug<input type="text" id="nest-add-slug" maxlength="40" autocapitalize="none" autocomplete="off" spellcheck="false" placeholder="room-name"></label>' +
        '<p class="nav-nest-form-err" id="nest-add-err" role="status"></p>' +
        '<button type="button" class="nav-nest-save" id="nest-add-save">Add room</button>' +
      '</li>';
    var items = document.createElement('li');
    var inner = document.createElement('ul');
    inner.id = 'nav-nests-items';
    items.appendChild(inner);
    list.appendChild(items);
    var mainUl = nav.querySelector('ul');
    if (mainUl && mainUl.parentNode) mainUl.after(list);
    else nav.insertBefore(list, nav.firstChild);
    wireNestAddForm();
    return list;
  }

  function wireNestAddForm() {
    var label = document.getElementById('nest-add-label');
    var slug = document.getElementById('nest-add-slug');
    if (!label || label.dataset.wired) return;
    label.dataset.wired = '1';
    label.addEventListener('input', function () {
      if (nestAddSlugDirty || !slug) return;
      slug.value = slugifyNestLabel(label.value);
    });
    if (slug) {
      slug.addEventListener('input', function () { nestAddSlugDirty = true; });
      slug.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); submitNestAdd(); }
      });
    }
  }

  function submitNestAdd() {
    var labelEl = document.getElementById('nest-add-label');
    var slugEl = document.getElementById('nest-add-slug');
    var errEl = document.getElementById('nest-add-err');
    var label = labelEl ? labelEl.value.trim() : '';
    var slug = slugifyNestLabel(slugEl ? slugEl.value : '');
    function show(msg) { if (errEl) errEl.textContent = msg || ''; }
    if (!isLiveUser()) { openAuth('join'); return; }
    if (!label || label.length > 40) { show('Add a label (40 characters max).'); return; }
    var slugErr = nestSlugError(slug);
    if (slugErr) { show(slugErr); return; }
    if (!requireVerified('add a room')) {
      if (siteKilled) show('This room is paused.');
      else show('Verify your email before you add a room.');
      return;
    }
    if (!fbDb) { show('Rooms are not connected.'); return; }
    var btn = document.getElementById('nest-add-save');
    if (btn) btn.disabled = true;
    show('');
    createMemberNest(label, slug).then(function () {
      hideNestAddForm();
    }).catch(function (e) {
      if (btn) btn.disabled = false;
      show((e && e.message) ? e.message : 'Could not add that room.');
    });
  }

  // Optional site.nestGroups: [{ label, parents: [...] }] prints sub-headers in the Nests nav.
  // A nest whose parent is another nest's slug is a sub-nest (subsubX): listed right under that parent, indented.
  function nestGroupLabel(n) {
    if (!n) return null;
    if (n.user) return 'Your rooms';
    var groups = (site && Array.isArray(site.nestGroups)) ? site.nestGroups : [];
    for (var g = 0; g < groups.length; g++) {
      var ps = groups[g] && Array.isArray(groups[g].parents) ? groups[g].parents : [];
      if (n.parent && ps.indexOf(n.parent) !== -1) return groups[g].label || null;
    }
    return null;
  }

  function orderedNavNests(shown) {
    var bySlug = {};
    var i;
    for (i = 0; i < shown.length; i++) bySlug[nestSlugNorm(shown[i].slug)] = shown[i];
    var kids = {};
    var top = [];
    for (i = 0; i < shown.length; i++) {
      var n = shown[i];
      var p = n.parent ? nestSlugNorm(n.parent) : '';
      if (p && bySlug[p] && p !== nestSlugNorm(n.slug)) {
        (kids[p] = kids[p] || []).push(n);
      } else {
        top.push(n);
      }
    }
    var out = [];
    for (i = 0; i < top.length; i++) {
      out.push({ nest: top[i], depth: 0 });
      var ch = kids[nestSlugNorm(top[i].slug)] || [];
      for (var c = 0; c < ch.length; c++) out.push({ nest: ch[c], depth: 1 });
    }
    return out;
  }

  function renderNestNav() {
    ensureNestNav();
    var items = document.getElementById('nav-nests-items');
    if (!items) return;
    var rows = orderedNavNests(visibleNests());
    var html = '';
    var lastGroup = null;
    for (var i = 0; i < rows.length; i++) {
      var n = rows[i].nest;
      if (rows[i].depth === 0) {
        var group = nestGroupLabel(n);
        if (group && group !== lastGroup) {
          html += '<li class="nav-nest-group" role="presentation">' + escapeHtml(group) + '</li>';
        }
        lastGroup = group;
      }
      var active = currentNest && currentNest.slug === n.slug ? ' active' : '';
      var child = rows[i].depth ? ' nav-nest-child' : '';
      html += '<li><a class="nav-social-link' + active + child + '" href="' + escapeHtml(nestPath(n.slug)) + '" data-nest="' + escapeHtml(n.slug) + '">' +
        escapeHtml(n.label || n.slug) + '</a></li>';
    }
    items.innerHTML = html;
  }

  function refreshNestSurfaces() {
    renderNestNav();
    ensureExploreNestTab();
  }

  function nestExploreCards() {
    return visibleNests().map(function (n) {
      return {
        tag: n.kind || 'Nest',
        title: n.label || n.slug,
        snippet: n.blurb || ('/' + n.slug),
        slug: n.slug
      };
    });
  }

  function fillExploreNests(pane, list) {
    if (!pane) return;
    var cards = list || nestExploreCards();
    if (!cards.length) {
      pane.innerHTML = '<p class="empty-note">' + (list ? 'No nests matched.' : 'No nests in the nav yet.') + '</p>';
      return;
    }
    pane.innerHTML = cards.map(function (c) {
      return '<a class="explore-card" href="' + escapeHtml(nestPath(c.slug)) + '" data-nest="' + escapeHtml(c.slug) + '">' +
        '<div class="explore-card-tag">' + escapeHtml(c.tag) + '</div>' +
        '<div class="explore-card-title">' + escapeHtml(c.title) + '</div>' +
        '<div class="explore-card-snippet">' + escapeHtml(c.snippet) + '</div></a>';
    }).join('');
  }

  function ensureExploreNestTab() {
    var tabs = document.querySelector('.explore-tabs');
    var pane = document.getElementById('explore-pane-nests');
    var tab = document.querySelector('[data-explore-tab="nests"]');
    var shown = visibleNests();
    if (!shown.length) {
      if (tab) tab.hidden = true;
      if (pane) {
        pane.hidden = true;
        pane.classList.remove('active');
      }
      return null;
    }
    if (!tab && tabs) {
      tab = document.createElement('button');
      tab.className = 'thoughts-tab';
      tab.setAttribute('data-explore-tab', 'nests');
      tab.setAttribute('type', 'button');
      tab.textContent = 'Nests';
      tabs.appendChild(tab);
    }
    if (tab) tab.hidden = false;
    if (!pane) {
      pane = document.createElement('div');
      pane.className = 'explore-pane';
      pane.id = 'explore-pane-nests';
      var topics = document.getElementById('explore-pane-topics');
      if (topics && topics.parentNode) topics.parentNode.appendChild(pane);
    }
    if (pane) pane.hidden = false;
    fillExploreNests(pane);
    return pane;
  }

  function postNestSlug(parentId) {
    if (currentNest) return currentNest.slug;
    if (parentId) {
      var p = findPost(parentId);
      if (p && p.nestSlug) return p.nestSlug;
    }
    return '';
  }

  function normalizeRoute(route) {
    let id = String(route || '').replace(/^#/, '').trim();
    if (!id) id = 'home';
    try { id = decodeURIComponent(id); } catch (e) { /* keep */ }
    return id;
  }
  function routeFromHash() { return normalizeRoute(window.location.hash); }
  function goNest(slug) {
    var nest = findNest(slug);
    if (!nest) { setUrl('/', '#home'); return; }
    setUrl('/' + nest.slug, '#home');
  }
  function goRoom() {
    if (currentNest) goNest(currentNest.slug);
    else go('home');
  }
  function go(route) {
    const id = normalizeRoute(route);
    if (findNest(id)) { goNest(id); return; }
    if (id === 'home' || id === 'feed' || id === 'thoughts') {
      setUrl('/', '#home');
      return;
    }
    var slug = nestSlugFromPathname(location.pathname);
    var path = findNest(slug) ? ('/' + slug) : '/';
    setUrl(path, '#' + id);
  }

  function selectThoughtsTab(tab) {
    currentTab = tab;
    document.querySelectorAll('[data-thoughts-tab]').forEach(function (t) {
      t.classList.toggle('active', t.dataset.thoughtsTab === tab);
    });
    renderFeed();
  }

  function applyRoute() {
    closeMobileNav();
    currentNest = resolveNestFromPath();
    applyNestChrome();
    const raw = routeFromHash();
    var roomHighlight = currentNest ? currentNest.slug : 'home';

    if (raw === 'following') {
      closeSocialOverlays();
      showContentPage('thoughts');
      highlightSocial('following');
      selectThoughtsTab('following');
      return;
    }
    if (raw === 'hot' || raw === 'new') {
      closeSocialOverlays();
      showContentPage('thoughts');
      highlightSocial(roomHighlight);
      selectThoughtsTab(raw);
      return;
    }
    if (raw === 'home' || raw === 'feed' || raw === 'thoughts') {
      closeSocialOverlays();
      showContentPage('thoughts');
      highlightSocial(roomHighlight);
      selectThoughtsTab('foryou');
      return;
    }
    if (raw === 'chat') { openChat(); return; }
    if (raw === 'notifications') { openNotif(); return; }
    if (raw === 'explore') { openExplore(); return; }
    if (raw === 'profile') { openProfile(); return; }
    if (raw === 'news') {
      closeSocialOverlays();
      showContentPage('news');
      highlightSocial('news');
      return;
    }
    closeSocialOverlays();
    showContentPage('thoughts');
    highlightSocial(roomHighlight);
  }

  function renderPostMedia(post) {
    var html = '';
    if (post.imageUrl) {
      html += '<div class="post-image"><img src="' + escapeHtml(post.imageUrl) + '" alt="" loading="lazy"></div>';
    }
    if (post.poll && post.poll.options && post.poll.options.length) {
      var votes = post.poll.votes || {};
      var keys = Object.keys(votes);
      var total = keys.length;
      var voterUid = liveUid();
      html += '<div class="post-poll">';
      post.poll.options.forEach(function (opt, i) {
        var count = 0;
        for (var v = 0; v < keys.length; v++) if (votes[keys[v]] === i) count++;
        var pct = total ? Math.round((count / total) * 100) : 0;
        var voted = voterUid != null && votes[voterUid] === i;
        html += '<div class="post-poll-option' + (voted ? ' voted' : '') + '" data-poll-idx="' + i + '" data-post-id="' + escapeHtml(String(post.id)) + '">' +
          '<div class="post-poll-bar" style="width:' + pct + '%"></div>' +
          '<span class="post-poll-label">' + escapeHtml(opt) + '</span>' +
          '<span class="post-poll-pct">' + count + ' · ' + pct + '%</span>' +
        '</div>';
      });
      html += '<div class="post-poll-meta">' + total + ' vote' + (total === 1 ? '' : 's') + (voterUid ? '' : ' · sign in to vote') + '</div></div>';
    }
    return html;
  }

  function renderPost(post, isReply) {
    const uid = liveUid();
    const liked = !!(uid && post.likedBy && post.likedBy[uid]);
    const likeCount = post.likes || 0;
    const av = initials(post.name);
    const bg = colorFor(post.handle);
    const canDelete = !!(uid && post.authorUid && post.authorUid === uid);
    const replyBtn = isReply
      ? ''
      : '<button class="post-action" data-act="reply" type="button">Reply · ' + (post.replies || 0) + '</button>';
    const delBtn = canDelete
      ? '<button class="post-action post-action-delete" data-act="delete" type="button">Delete</button>'
      : '';
    const other = !!(uid && post.authorUid && post.authorUid !== uid);
    const reportBtn = other
      ? '<button class="post-action" data-act="report" type="button">Report</button>'
      : '';
    const blockBtn = other
      ? '<button class="post-action" data-act="block" type="button">Block</button>'
      : '';
    return (
      '<article class="post' + (isReply ? ' post-reply' : '') + '" data-post-id="' + escapeHtml(post.id) + '"' +
        (post.parentId ? ' data-parent-id="' + escapeHtml(post.parentId) + '"' : '') + '>' +
        '<div class="post-avatar" style="background:' + bg + '">' + av + '</div>' +
        '<div class="post-body">' +
          '<div class="post-meta">' +
            '<span class="post-name' + (dmsOn() && post.authorUid ? ' post-name-link' : '') + '"' +
              (dmsOn() && post.authorUid
                ? ' data-profile-uid="' + escapeHtml(post.authorUid) + '" data-profile-name="' + escapeHtml(post.name) + '" data-profile-handle="' + escapeHtml(post.handle) + '"'
                : '') +
            '>' + escapeHtml(post.name) + '</span>' +
            '<span class="post-handle">@' + escapeHtml(post.handle) + '</span>' +
            '<span class="post-time">· ' + (post.hours != null ? post.hours + 'h' : 'now') + '</span>' +
          '</div>' +
          (post.text ? '<p class="post-text">' + escapeHtml(post.text) + '</p>' : '') +
          renderPostMedia(post) +
          '<div class="post-actions">' +
            replyBtn +
            '<button class="post-action' + (liked ? ' liked' : '') + '" data-act="like" type="button">Like · ' + likeCount + '</button>' +
            '<button class="post-action" data-act="share" type="button">Share</button>' +
            reportBtn + blockBtn +
            delBtn +
          '</div>' +
        '</div>' +
      '</article>'
    );
  }

  function topLevelPosts() {
    return livePosts.filter(function (p) {
      if (p.parentId || (p.authorUid && blockedUids[p.authorUid])) return false;
      if (currentNest) return nestSlugNorm(p.nestSlug) === nestSlugNorm(currentNest.slug);
      return true;
    });
  }

  function repliesFor(parentId) {
    return livePosts.filter(function (p) { return p.parentId === parentId && !(p.authorUid && blockedUids[p.authorUid]); })
      .sort(function (a, b) { return (a.ms || 0) - (b.ms || 0); });
  }

  function renderFeed() {
    const el = document.getElementById('thoughts-feed');
    if (!el) return;

    if (currentTab === 'following') {
      el.innerHTML = '<div class="post-empty soon-panel"><strong>Following — Soon.</strong> There is no follows graph in this preview. The live room is on For You.</div>';
      refreshPorchUi();
      return;
    }

    if (liveError) {
      el.innerHTML = '<div class="post-empty">Live feed could not load. The error is in the compose line above — this is not an empty room.</div>';
      refreshPorchUi();
      return;
    }
    if (!liveReady) {
      el.innerHTML = '<div class="post-empty">Connecting to the live feed…</div>';
      refreshPorchUi();
      return;
    }

    let posts = topLevelPosts().slice();
    if (currentTab === 'hot') posts.sort(function (a, b) { return (b.likes || 0) - (a.likes || 0); });
    if (currentTab === 'new') posts.sort(function (a, b) { return (b.ms || 0) - (a.ms || 0); });

    if (!posts.length) {
      var empty = currentNest
        ? ('No posts in ' + (currentNest.label || currentNest.slug) + ' yet. This nest is live at /' + currentNest.slug + '. Sign in to post the first take.')
        : ((site && site.emptyState) || 'This room is empty. Sign in to post. Guest can browse only.');
      el.innerHTML = '<div class="post-empty">' + escapeHtml(empty) + '</div>';
      refreshPorchUi();
      refreshNestSurfaces();
      return;
    }

    el.innerHTML = posts.map(function (p) {
      var kids = repliesFor(p.id);
      return renderPost(p, false) + kids.map(function (r) { return renderPost(r, true); }).join('');
    }).join('');
    highlightDeepPost();
    refreshPorchUi();
    refreshNestSurfaces();
  }

  var RAIL_MAX = 3;

  function nwsHeaders(accept) {
    var cfg = railCfg();
    var ua = cfg.userAgent || ((site && site.name) || SITE_ID || 'subx') + '/rail (jebb@subx.it)';
    return {
      'Accept': accept || 'application/geo+json',
      'User-Agent': ua
    };
  }

  function nwsTagFor(shortForecast) {
    var s = String(shortForecast || '').toLowerCase();
    if (/\bfog\b/.test(s)) return 'Fog';
    return 'NWS';
  }

  function renderTrendCard(t) {
    const href = t.url || '#explore';
    const extra = t.url ? ' target="_blank" rel="noopener noreferrer"' : '';
    return '<a class="news-item" href="' + escapeHtml(href) + '"' + extra + '>' +
      '<div class="news-item-tag">' + escapeHtml(t.tag) + '</div>' +
      '<div class="news-item-headline">' + escapeHtml(t.headline) + '</div>' +
      '<div class="news-item-snippet">' + escapeHtml(t.snippet) + '</div>' +
      '<div class="news-item-meta">' + escapeHtml(t.meta) + '</div>' +
    '</a>';
  }

  function factCardHtml() {
    var fact = railCfg().fact;
    if (!fact) return '';
    var tag = 'FACT';
    var headline = '';
    var body = '';
    if (typeof fact === 'string') {
      body = fact;
    } else {
      tag = fact.tag || 'FACT';
      headline = fact.headline || '';
      body = fact.body || fact.snippet || '';
    }
    if (!body && !headline) return '';
    return '<div class="news-item news-item-fact">' +
      '<div class="news-item-tag">' + escapeHtml(tag) + '</div>' +
      (headline ? '<div class="news-item-headline">' + escapeHtml(headline) + '</div>' : '') +
      (body ? '<div class="news-item-snippet">' + escapeHtml(body) + '</div>' : '') +
      '<div class="news-item-meta">' + escapeHtml(railCfg().meta || 'Preview · noindex') + '</div>' +
    '</div>';
  }

  function porchCardHtml() {
    var porch = railCfg().porch;
    if (!porch || !porch.options || !porch.options.length) return '';
    var prompt = porch.prompt || 'Your call?';
    var last = lastPorchPick();
    var btns = porch.options.map(function (opt) {
      var picked = last && String(opt) === last ? ' porch-btn-picked' : '';
      var aria = picked ? ' aria-pressed="true"' : ' aria-pressed="false"';
      return '<button type="button" class="porch-btn' + picked + '" data-porch="' + escapeHtml(opt) + '"' + aria + '>' + escapeHtml(opt) + '</button>';
    }).join('');
    return '<div class="news-item news-item-porch">' +
      '<div class="news-item-tag">Porch</div>' +
      '<div class="news-item-headline">' + escapeHtml(prompt) + '</div>' +
      '<div class="news-item-snippet">Pick a side. Posts to this room.</div>' +
      '<div class="porch-btns">' + btns + '</div>' +
      '<div class="porch-tally" aria-live="polite">' + escapeHtml(porchTallyLine()) + '</div>' +
      '<div class="news-item-meta">This room</div>' +
    '</div>';
  }

  function ensureRailCss() {
    if (document.getElementById('rail-porch-css')) return;
    var st = document.createElement('style');
    st.id = 'rail-porch-css';
    st.textContent =
      '.news-item{display:block;padding:1rem 1.4rem;border-bottom:1px solid rgba(255,255,255,0.06);}' +
      'a.news-item{text-decoration:none;cursor:pointer;}' +
      '.porch-btns{display:flex;gap:0.45rem;margin:0.45rem 0 0.2rem;flex-wrap:wrap;}' +
      '.porch-btn{font:inherit;font-size:0.78rem;font-weight:600;padding:0.35rem 0.8rem;border-radius:999px;' +
        'border:1px solid rgba(255,255,255,0.22);background:rgba(255,255,255,0.08);color:#f0f4f7;cursor:pointer;}' +
      '.porch-btn:hover{background:rgba(255,255,255,0.16);}' +
      '.porch-btn-picked{border-color:var(--accent,#e07a3d);background:rgba(224,122,61,0.28);box-shadow:inset 0 0 0 1px var(--accent,#e07a3d);}' +
      '.porch-tally{font-size:0.75rem;line-height:1.4;color:#8aa0b0;margin:0.28rem 0 0.1rem;}' +
      '.news-page-list .news-item{background:var(--surface,#f4f7fa);border:1px solid var(--border,#c9d5de);border-radius:10px;padding:1.05rem 1.15rem;}' +
      '.news-page-list .porch-btn{border-color:var(--border,#c9d5de);background:#fff;color:var(--text,#12202c);}' +
      '.news-page-list .porch-btn:hover{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);}' +
      '.news-page-list .porch-btn-picked{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);background:rgba(192,54,44,0.08);}' +
      '.news-page-list .porch-tally{color:var(--text-muted,#4a5f66);}' +
      '[data-porch-dwell] .news-item-porch{padding-top:1.25rem;padding-bottom:1.25rem;}';
    document.head.appendChild(st);
  }

  function paintRail(items) {
    ensureRailCss();
    var html = factCardHtml() + (items || []).map(renderTrendCard).join('') + porchCardHtml();
    var rail = document.getElementById('news-feed');
    var page = document.getElementById('news-page-list');
    if (rail) rail.innerHTML = html;
    if (page) page.innerHTML = html;
    maybeShowRailOverlay();
  }

  var railOverlayUiReady = false;
  var railOverlayTimer = null;
  var railOverlayDeadline = 0;
  var railOverlayRemaining = 0;
  var railOverlayPrevFocus = null;
  var railOverlayOnKey = null;
  var railOverlayOnClick = null;
  var railOverlayWired = false;

  function overlayCfg() {
    var ov = railCfg().overlay;
    return (ov && typeof ov === 'object') ? ov : null;
  }

  function overlayEnabled() {
    var ov = overlayCfg();
    return !!(ov && ov.enabled);
  }

  function overlayMs() {
    var n = overlayCfg() && parseInt(overlayCfg().ms, 10);
    return (n > 0) ? n : 7000;
  }

  function overlayStorageKey() {
    return 'subx.railOverlay.' + (SITE_ID || '');
  }

  function overlaySeen() {
    try { return sessionStorage.getItem(overlayStorageKey()) === '1'; } catch (e) { return false; }
  }

  function markOverlaySeen() {
    try { sessionStorage.setItem(overlayStorageKey(), '1'); } catch (e) { /* private mode */ }
  }

  function railOfficialUrls() {
    var cfg = railCfg();
    var set = {};
    function add(u) {
      var s = String(u || '').trim();
      if (/^https:\/\//i.test(s)) set[s] = true;
    }
    add(cfg.forecastPage);
    add(cfg.forecastUrl);
    add(cfg.alertsUrl);
    var outbound = cfg.outbound || [];
    for (var i = 0; i < outbound.length; i++) add(outbound[i] && outbound[i].url);
    return set;
  }

  function overlayLinks() {
    var ov = overlayCfg();
    var configured = (ov && ov.links) || [];
    var allow = railOfficialUrls();
    var out = [];
    for (var i = 0; i < configured.length && out.length < 2; i++) {
      var link = configured[i];
      if (!link || !link.url || !link.label) continue;
      var url = String(link.url).trim();
      if (!allow[url]) continue;
      out.push({ label: String(link.label), url: url });
    }
    if (!out.length && railCfg().forecastPage && allow[railCfg().forecastPage]) {
      out.push({ label: 'Official forecast', url: railCfg().forecastPage });
    }
    return out;
  }

  function overlayHeadline() {
    var ov = overlayCfg();
    if (ov && ov.headline) return String(ov.headline);
    var cfg = railCfg();
    if (cfg.meta) return String(cfg.meta);
    if (cfg.kicker) return String(cfg.kicker);
    var first = document.querySelector('#news-feed .news-item-headline');
    if (first && first.textContent) return first.textContent.trim();
    return cfg.title || 'Room Brief';
  }

  function railPanelIsVisible() {
    var panel = document.getElementById('right-panel');
    if (!panel) return false;
    if (document.body.classList.contains('right-collapsed')) return false;
    var cs = window.getComputedStyle(panel);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    var rect = panel.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.right > 8;
  }

  function overlayFadeMs() {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return 0;
    } catch (e) { /* ignore */ }
    return 200;
  }

  function sendPixel(eventName) {
    try {
      var k = 'subx.vid';
      var v = localStorage.getItem(k);
      if (!v) {
        v = Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem(k, v);
      }
      var url = 'https://us-central1-subx-skins.cloudfunctions.net/pixel?s=' +
        encodeURIComponent(SITE_ID) + '&v=' + encodeURIComponent(v);
      if (eventName) url += '&e=' + encodeURIComponent(eventName);
      if (navigator.sendBeacon) navigator.sendBeacon(url);
    } catch (e) { /* best-effort */ }
  }

  function clearOverlayTimer() {
    if (railOverlayTimer) {
      clearTimeout(railOverlayTimer);
      railOverlayTimer = null;
    }
  }

  function pauseOverlayTimer() {
    if (!railOverlayTimer) return;
    railOverlayRemaining = Math.max(0, railOverlayDeadline - Date.now());
    clearOverlayTimer();
  }

  function resumeOverlayTimer() {
    if (railOverlayTimer || !document.getElementById('rail-overlay')) return;
    if (railOverlayRemaining <= 0) {
      dismissRailOverlay('autodismiss');
      return;
    }
    railOverlayDeadline = Date.now() + railOverlayRemaining;
    railOverlayTimer = setTimeout(function () {
      railOverlayTimer = null;
      dismissRailOverlay('autodismiss');
    }, railOverlayRemaining);
  }

  function detachOverlayListeners() {
    if (railOverlayOnKey) {
      document.removeEventListener('keydown', railOverlayOnKey, true);
      railOverlayOnKey = null;
    }
    if (railOverlayOnClick) {
      document.removeEventListener('click', railOverlayOnClick, true);
      railOverlayOnClick = null;
    }
  }

  function restoreOverlayFocus() {
    var prev = railOverlayPrevFocus;
    railOverlayPrevFocus = null;
    if (!prev || typeof prev.focus !== 'function') return;
    try { prev.focus(); } catch (e) { /* ignore */ }
  }

  function dismissRailOverlay(reason) {
    var el = document.getElementById('rail-overlay');
    if (!el || el.getAttribute('data-closing') === '1') return;
    el.setAttribute('data-closing', '1');
    clearOverlayTimer();
    detachOverlayListeners();
    if (reason === 'autodismiss') sendPixel('overlay_autodismiss');
    el.classList.remove('is-in');
    var ms = overlayFadeMs();
    function done() {
      if (el.parentNode) el.parentNode.removeChild(el);
      var panel = document.getElementById('right-panel');
      if (panel) panel.classList.remove('is-overlaying');
      restoreOverlayFocus();
    }
    if (!ms) done();
    else setTimeout(done, ms);
  }

  function showRailOverlay() {
    if (document.getElementById('rail-overlay')) return;
    var panel = document.getElementById('right-panel');
    if (!panel) return;
    var links = overlayLinks();
    var headline = overlayHeadline();
    var kicker = railCfg().title || 'Room Brief';
    var el = document.createElement('div');
    el.id = 'rail-overlay';
    el.className = 'rail-overlay';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-labelledby', 'rail-overlay-headline');
    el.setAttribute('tabindex', '-1');
    var linkHtml = links.map(function (link) {
      return '<a class="rail-overlay-cta" href="' + escapeHtml(link.url) +
        '" target="_blank" rel="noopener noreferrer">' + escapeHtml(link.label) + '</a>';
    }).join('');
    el.innerHTML = '<div class="rail-overlay-card">' +
      '<div class="rail-overlay-kicker">' + escapeHtml(kicker) + '</div>' +
      '<p class="rail-overlay-headline" id="rail-overlay-headline">' + escapeHtml(headline) + '</p>' +
      (linkHtml ? '<div class="rail-overlay-links">' + linkHtml + '</div>' : '') +
      '</div>';
    panel.appendChild(el);
    panel.classList.add('is-overlaying');
    markOverlaySeen();
    sendPixel('overlay_shown');
    railOverlayPrevFocus = document.activeElement;
    railOverlayRemaining = overlayMs();
    resumeOverlayTimer();
    el.addEventListener('pointerenter', pauseOverlayTimer);
    el.addEventListener('pointerleave', resumeOverlayTimer);
    el.addEventListener('click', function (e) {
      var a = e.target.closest ? e.target.closest('a.rail-overlay-cta') : null;
      if (!a) return;
      sendPixel('overlay_click');
      dismissRailOverlay('click');
    });
    railOverlayOnKey = function (e) {
      if (e.key !== 'Escape') return;
      if (!document.getElementById('rail-overlay')) return;
      e.preventDefault();
      dismissRailOverlay('escape');
    };
    railOverlayOnClick = function (e) {
      var card = el.querySelector('.rail-overlay-card');
      if (card && card.contains(e.target)) return;
      dismissRailOverlay('outside');
    };
    document.addEventListener('keydown', railOverlayOnKey, true);
    setTimeout(function () {
      if (!document.getElementById('rail-overlay')) return;
      document.addEventListener('click', railOverlayOnClick, true);
    }, 0);
    requestAnimationFrame(function () {
      el.classList.add('is-in');
      try { el.focus(); } catch (e) { /* ignore */ }
      try { if (el.matches(':hover')) pauseOverlayTimer(); } catch (e2) { /* ignore */ }
    });
  }

  function maybeShowRailOverlay() {
    if (!railOverlayUiReady) return;
    if (!overlayEnabled()) return;
    if (overlaySeen()) return;
    if (document.getElementById('rail-overlay')) return;
    if (!railPanelIsVisible()) return;
    showRailOverlay();
  }

  function syncRailOverlayViewport() {
    if (!overlayEnabled()) return;
    if (!railPanelIsVisible()) {
      dismissRailOverlay('hidden');
      return;
    }
    maybeShowRailOverlay();
  }

  function wireRailOverlay() {
    if (railOverlayWired) return;
    railOverlayWired = true;
    window.addEventListener('resize', syncRailOverlayViewport);
  }

  function nwsCardFromPeriod(period, href, meta) {
    var name = period.name || 'Forecast';
    var short = period.shortForecast || '';
    var temp = (period.temperature != null)
      ? (period.temperature + '°' + (period.temperatureUnit || 'F'))
      : '';
    var snippet = short + (temp ? ' · ' + temp : '');
    return {
      tag: nwsTagFor(short),
      headline: name,
      snippet: snippet,
      meta: meta,
      url: href
    };
  }

  function nwsCardFromAlert(feature, href, meta) {
    var p = (feature && feature.properties) || {};
    var headline = p.headline || p.event || '';
    if (!headline) return null;
    var desc = String(p.description || p.instruction || '').replace(/\s+/g, ' ').trim();
    return {
      tag: 'Alert',
      headline: headline,
      snippet: desc ? desc.slice(0, 160) : (p.event || 'Active NWS alert'),
      meta: meta,
      url: p.web || href
    };
  }

  function resolveForecastUrl(cfg, headers) {
    if (cfg.forecastUrl) return Promise.resolve(cfg.forecastUrl);
    if (cfg.lat == null || cfg.lon == null) return Promise.reject(new Error('no nws point'));
    var points = 'https://api.weather.gov/points/' + cfg.lat + ',' + cfg.lon;
    return fetch(points, { headers: headers }).then(function (res) {
      if (!res.ok) throw new Error('nws points ' + res.status);
      return res.json();
    }).then(function (data) {
      var url = data && data.properties && data.properties.forecast;
      if (!url) throw new Error('nws points missing forecast');
      return url;
    });
  }

  function fetchNwsCards() {
    var cfg = railCfg();
    var headers = nwsHeaders();
    var meta = cfg.meta || 'Live';
    var pageHref = cfg.forecastPage || cfg.forecastUrl || 'https://www.weather.gov/';
    return resolveForecastUrl(cfg, headers).then(function (forecastUrl) {
      if (!cfg.forecastPage && forecastUrl) pageHref = forecastUrl;
      var forecastJob = fetch(forecastUrl, { headers: headers }).then(function (res) {
        if (!res.ok) throw new Error('nws forecast ' + res.status);
        return res.json();
      });
      var alertsUrl = cfg.alertsUrl;
      if (!alertsUrl && cfg.zone) {
        alertsUrl = 'https://api.weather.gov/alerts/active?zone=' + encodeURIComponent(cfg.zone);
      }
      var alertsJob = alertsUrl
        ? fetch(alertsUrl, { headers: headers }).then(function (res) {
            return res.ok ? res.json() : { features: [] };
          }).catch(function () { return { features: [] }; })
        : Promise.resolve({ features: [] });
      return Promise.all([forecastJob, alertsJob]);
    }).then(function (pair) {
      var forecast = pair[0] || {};
      var alerts = pair[1] || {};
      var cards = [];
      var features = alerts.features || [];
      for (var i = 0; i < features.length; i++) {
        var alertCard = nwsCardFromAlert(features[i], pageHref, meta);
        if (alertCard) cards.push(alertCard);
      }
      var periods = (forecast.properties && forecast.properties.periods) || [];
      for (var p = 0; p < periods.length; p++) {
        cards.push(nwsCardFromPeriod(periods[p], pageHref, meta));
      }
      if (!periods.length) throw new Error('nws forecast empty');
      return cards;
    });
  }

  function cwfHeadline(name) {
    return String(name || 'Forecast')
      .toLowerCase()
      .replace(/\b[a-z]/g, function (ch) { return ch.toUpperCase(); })
      .replace(/\bOf\b/g, 'of');
  }

  function cwfSnippet(body) {
    var flat = String(body || '').replace(/\s+/g, ' ').trim();
    if (!flat) return '';
    var wind = /[^.]*(?:\bwind|\bwinds)[^.]*\.?/i.exec(flat);
    var seas = /[^.]*(?:\bseas?\b|\bswell\b)[^.]*\.?/i.exec(flat);
    var bits = [];
    if (wind) bits.push(wind[0].trim().replace(/\.+$/, '') + '.');
    if (seas && (!wind || seas.index !== wind.index)) bits.push(seas[0].trim().replace(/\.+$/, '') + '.');
    if (bits.length) return bits.join(' ');
    return flat.slice(0, 160);
  }

  function cwfTag(productText) {
    return /small craft/i.test(String(productText || '')) ? 'Advisory' : 'Seas';
  }

  function parseCwfPeriods(productText) {
    var text = String(productText || '');
    var cut = text.search(/\n&&(?:\n|$)/);
    if (cut < 0) cut = text.search(/\n\.VAAIGA\b/);
    if (cut > 0) text = text.slice(0, cut);
    var periodRe = /^\.([A-Z][A-Z \-]{1,40})\.{2,}(.*)$/;
    var lines = text.split(/\n/);
    var periods = [];
    var cur = null;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var m = line.match(periodRe);
      if (m) {
        if (cur) periods.push(cur);
        cur = { name: m[1].replace(/\s+/g, ' ').trim(), body: m[2] || '' };
        continue;
      }
      if (cur) {
        if (/^\$\$/.test(line) || /^&&/.test(line)) {
          periods.push(cur);
          cur = null;
          break;
        }
        if (line.trim()) cur.body += ' ' + line;
      }
    }
    if (cur) periods.push(cur);
    return periods.filter(function (p) {
      return p.name && !/^(SYNOPSIS|VAAIGA|PO|ASO)\b/.test(p.name);
    });
  }

  function parseCwfCards(productText, href, meta) {
    var periods = parseCwfPeriods(productText);
    var tag = cwfTag(productText);
    var cards = [];
    var n = Math.min(2, periods.length);
    for (var i = 0; i < n; i++) {
      var snippet = cwfSnippet(periods[i].body);
      if (!snippet) continue;
      cards.push({
        tag: tag,
        headline: cwfHeadline(periods[i].name),
        snippet: snippet,
        meta: meta,
        url: href
      });
    }
    return cards;
  }

  function latestCwfProductId(data) {
    var graph = (data && (data['@graph'] || data.graph)) || [];
    if (!graph.length && data && (data.id || data['@id'])) graph = [data];
    graph = graph.slice().sort(function (a, b) {
      return String((b && b.issuanceTime) || '').localeCompare(String((a && a.issuanceTime) || ''));
    });
    var latest = graph[0];
    if (!latest) return '';
    if (latest.id) return String(latest.id);
    if (latest['@id']) return String(latest['@id']).replace(/^.*\//, '');
    return '';
  }

  function fetchCwfCards() {
    var cfg = railCfg();
    var headers = nwsHeaders('application/ld+json');
    var loc = cfg.productLocation || 'PPG';
    var type = cfg.productType || 'CWF';
    var meta = cfg.meta || 'Live';
    var pageHref = cfg.forecastPage || 'https://www.weather.gov/ppg/marine';
    var listUrl = 'https://api.weather.gov/products/types/' + encodeURIComponent(type) +
      '/locations/' + encodeURIComponent(loc);
    return fetch(listUrl, { headers: headers }).then(function (res) {
      if (!res.ok) throw new Error('nws cwf list ' + res.status);
      return res.json();
    }).then(function (data) {
      var id = latestCwfProductId(data);
      if (!id) throw new Error('nws cwf missing id');
      return fetch('https://api.weather.gov/products/' + encodeURIComponent(id), { headers: headers });
    }).then(function (res) {
      if (!res.ok) throw new Error('nws cwf product ' + res.status);
      return res.json();
    }).then(function (prod) {
      var cards = parseCwfCards(prod && prod.productText, pageHref, meta);
      if (!cards.length) throw new Error('nws cwf parse empty');
      return cards;
    });
  }


  function outboundCards() {
    var list = railCfg().outbound || [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var t = list[i];
      if (!t || !t.headline) continue;
      out.push({
        tag: t.tag || 'Link',
        headline: t.headline,
        snippet: t.snippet || '',
        meta: t.meta || (railCfg().meta || 'This room'),
        url: t.url || ''
      });
    }
    return out;
  }

  function bartCdata(node) {
    if (node == null) return '';
    if (typeof node === 'string') return node;
    if (typeof node === 'number') return String(node);
    return node['#cdata-section'] || node['#text'] || node.description || '';
  }

  function fetchBartCards() {
    var cfg = railCfg();
    var key = cfg.bartKey || 'MW9S-E7SL-26DU-VV8V';
    var url = cfg.bartUrl || ('https://api.bart.gov/api/bsa.aspx?cmd=bsa&json=y&key=' + encodeURIComponent(key));
    var meta = cfg.meta || 'Live · BART';
    var href = cfg.forecastPage || 'https://www.bart.gov/schedules/advisories';
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('bart bsa ' + res.status);
      return res.json();
    }).then(function (data) {
      var root = (data && data.root) || {};
      var raw = root.bsa;
      var list = Array.isArray(raw) ? raw : (raw ? [raw] : []);
      var cards = [];
      for (var i = 0; i < list.length; i++) {
        var item = list[i] || {};
        var desc = String(bartCdata(item.description) || bartCdata(item.sms_text) || '').replace(/\s+/g, ' ').trim();
        if (!desc) continue;
        if (/^no delay/i.test(desc) && list.length > 1) continue;
        var typ = String(item.type || 'Advisory').toLowerCase();
        var tag = /delay/.test(typ) || /delay/.test(desc.toLowerCase()) ? 'Delay' : 'BART';
        var station = item.station && item.station !== 'BART' ? String(item.station) : '';
        cards.push({
          tag: tag,
          headline: station || (tag === 'Delay' ? 'Delay advisory' : 'BART advisory'),
          snippet: desc.slice(0, 180),
          meta: meta,
          url: href
        });
      }
      if (!cards.length) {
        cards.push({
          tag: 'BART',
          headline: 'No delay advisory',
          snippet: 'BART reports no current BSA. Porch still posts into this room.',
          meta: meta,
          url: href
        });
      }
      return cards;
    });
  }

  var F1_SESSION_KEYS = [
    ['FirstPractice', 'FP1'],
    ['SecondPractice', 'FP2'],
    ['ThirdPractice', 'FP3'],
    ['SprintQualifying', 'Sprint Quali'],
    ['Sprint', 'Sprint'],
    ['Qualifying', 'Quali']
  ];
  var F1_SESSION_MS = {
    FP1: 60 * 60 * 1000,
    FP2: 60 * 60 * 1000,
    FP3: 60 * 60 * 1000,
    'Sprint Quali': 60 * 60 * 1000,
    Sprint: 45 * 60 * 1000,
    Quali: 60 * 60 * 1000,
    Race: 2 * 60 * 60 * 1000
  };

  function f1ParseWhen(sess) {
    if (!sess || !sess.date) return null;
    var time = sess.time || '00:00:00Z';
    if (!/Z$/i.test(time)) time += 'Z';
    var d = new Date(sess.date + 'T' + time);
    return isNaN(d.getTime()) ? null : d;
  }

  function f1FormatLocal(d) {
    if (!d) return '';
    return d.toLocaleString('en-US', {
      timeZone: 'America/Denver',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    }) + ' MT';
  }

  function f1Sessions(race) {
    var out = [];
    if (!race) return out;
    for (var i = 0; i < F1_SESSION_KEYS.length; i++) {
      var key = F1_SESSION_KEYS[i][0];
      var label = F1_SESSION_KEYS[i][1];
      var when = f1ParseWhen(race[key]);
      if (when) out.push({ label: label, when: when, ms: when.getTime() });
    }
    var raceWhen = f1ParseWhen({ date: race.date, time: race.time });
    if (raceWhen) out.push({ label: 'Race', when: raceWhen, ms: raceWhen.getTime() });
    out.sort(function (a, b) { return a.ms - b.ms; });
    return out;
  }

  function f1RaceFromPayload(data) {
    var races = data && data.MRData && data.MRData.RaceTable && data.MRData.RaceTable.Races;
    return (races && races[0]) || null;
  }

  function f1CardsFromRace(race, cfg, finished) {
    var circuit = (race && race.Circuit) || {};
    var loc = circuit.Location || {};
    var href = race.url || circuit.url || '';
    var meta = (cfg && cfg.meta) || 'Live · race weekend';
    var cmo = (cfg && cfg.cmo) || {};
    var sessions = f1Sessions(race);
    var now = Date.now();
    var first = sessions[0];
    var last = sessions[sessions.length - 1];
    var lastEnd = last ? last.ms + (F1_SESSION_MS[last.label] || 0) : 0;
    var live = !!(first && last && now >= first.ms && now <= lastEnd);
    var justFinished = !!finished || !!(last && now > lastEnd);
    var place = [loc.locality, loc.country].filter(Boolean).join(', ');
    var circuitLine = [circuit.circuitName, place].filter(Boolean).join(' · ');
    var raceWhen = f1ParseWhen({ date: race.date, time: race.time });
    var cards = [];
    cards.push({
      tag: race.round ? ('R' + race.round) : 'GP',
      headline: cmo.title || race.raceName || 'Grand Prix',
      snippet: circuitLine || 'Race weekend',
      meta: raceWhen ? ('Race · ' + f1FormatLocal(raceWhen)) : meta,
      url: href
    });
    if (sessions.length) {
      cards.push({
        tag: 'Sessions',
        headline: 'Weekend timetable',
        snippet: sessions.map(function (s) { return s.label + ' ' + f1FormatLocal(s.when); }).join(' · '),
        meta: meta,
        url: href
      });
    }
    var nextSess = null;
    for (var s = 0; s < sessions.length; s++) {
      var end = sessions[s].ms + (F1_SESSION_MS[sessions[s].label] || 0);
      if (now < end) { nextSess = sessions[s]; break; }
    }
    var stateSnip;
    if (cmo.next && !justFinished) {
      stateSnip = cmo.next;
    } else if (justFinished) {
      stateSnip = (race.raceName || 'This race') + ' is in the books.';
    } else if (nextSess) {
      stateSnip = (now >= nextSess.ms ? nextSess.label + ' is on · ' : nextSess.label + ' · ') + f1FormatLocal(nextSess.when);
    } else {
      stateSnip = raceWhen ? ('Race · ' + f1FormatLocal(raceWhen)) : 'Race weekend';
    }
    var stateHead = justFinished
      ? 'Just finished'
      : (cmo.state || (live ? 'Weekend is live' : 'Next up'));
    cards.push({
      tag: justFinished ? 'Finished' : (live ? 'Live' : 'Next'),
      headline: stateHead,
      snippet: stateSnip,
      meta: meta,
      url: href
    });
    return cards;
  }

  function fetchF1Json(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('jolpica ' + res.status);
      return res.json();
    });
  }

  function openf1Url(path) {
    var base = String(railCfg().openf1 || 'https://api.openf1.org/v1').replace(/\/+$/, '');
    return base + path;
  }

  function fetchOpenF1Json(path) {
    function once(retried) {
      return fetch(openf1Url(path)).then(function (res) {
        if (res.status === 429 && !retried) {
          return new Promise(function (resolve) {
            setTimeout(function () { resolve(once(true)); }, 1000);
          });
        }
        if (res.status === 401 || res.status === 403) return null;
        if (!res.ok) return null;
        return res.json();
      }).then(function (data) {
        return Array.isArray(data) && data.length ? data : null;
      }).catch(function () {
        return null;
      });
    }
    return once(false);
  }

  function f1ParseIso(s) {
    if (!s) return null;
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  function f1OpenF1Tag(sess) {
    var raw = String((sess && (sess.session_name || sess.session_type)) || '');
    if (/practice\s*1/i.test(raw) || /^fp1$/i.test(raw)) return 'FP1';
    if (/practice\s*2/i.test(raw) || /^fp2$/i.test(raw)) return 'FP2';
    if (/practice\s*3/i.test(raw) || /^fp3$/i.test(raw)) return 'FP3';
    if (/sprint\s*qual/i.test(raw) || /shootout/i.test(raw)) return 'Sprint Quali';
    if (/sprint/i.test(raw)) return 'Sprint';
    if (/qual/i.test(raw)) return 'Quali';
    if (/race/i.test(raw)) return 'Race';
    return raw || 'Session';
  }

  function f1FormatDuration(duration) {
    if (duration == null || duration === '') return '';
    if (Object.prototype.toString.call(duration) === '[object Array]') {
      var last = null;
      var i;
      for (i = duration.length - 1; i >= 0; i--) {
        if (duration[i] != null && duration[i] !== '') { last = duration[i]; break; }
      }
      return f1FormatDuration(last);
    }
    if (typeof duration === 'string') {
      var trimmed = duration.replace(/^\s+|\s+$/g, '');
      if (!trimmed) return '';
      if (/lap/i.test(trimmed)) return trimmed;
      if (trimmed.indexOf(':') !== -1) return trimmed;
      var parsed = parseFloat(trimmed);
      if (isNaN(parsed)) return trimmed;
      duration = parsed;
    }
    if (typeof duration !== 'number' || !isFinite(duration)) return '';
    var sign = duration < 0 ? '-' : '';
    var abs = Math.abs(duration);
    var mins = Math.floor(abs / 60);
    var secs = abs - mins * 60;
    var secStr = secs.toFixed(3);
    if (secs < 10) secStr = '0' + secStr;
    return sign + mins + ':' + secStr;
  }

  function f1FormatGap(gap) {
    if (gap == null || gap === '') return '';
    if (typeof gap === 'string') {
      var g = gap.replace(/^\s+|\s+$/g, '');
      if (!g || /^0+(\.0+)?$/.test(g)) return '';
      if (/lap/i.test(g)) return g.charAt(0) === '+' ? g : ('+' + g);
      if (g.charAt(0) === '+') return g;
      var n = parseFloat(g);
      if (isNaN(n)) return g;
      gap = n;
    }
    if (typeof gap !== 'number' || !isFinite(gap) || gap === 0) return '';
    return (gap < 0 ? '-' : '+') + Math.abs(gap).toFixed(3);
  }

  function f1DriverLabel(drv) {
    if (!drv) return '';
    var acr = String(drv.name_acronym || '').replace(/^\s+|\s+$/g, '');
    if (acr) return acr;
    var last = String(drv.last_name || '').replace(/^\s+|\s+$/g, '');
    if (last) return last;
    if (drv.driver_number != null) return String(drv.driver_number);
    return '';
  }

  function f1Top3Line(results, drivers) {
    var byNum = {};
    var i;
    if (drivers) {
      for (i = 0; i < drivers.length; i++) {
        var d = drivers[i];
        if (d && d.driver_number != null) byNum[String(d.driver_number)] = d;
      }
    }
    var rows = (results || []).slice();
    rows.sort(function (a, b) {
      return (Number(a && a.position) || 99) - (Number(b && b.position) || 99);
    });
    var parts = [];
    for (i = 0; i < rows.length && parts.length < 3; i++) {
      var row = rows[i];
      if (!row) continue;
      var label = f1DriverLabel(byNum[String(row.driver_number)]) || String(row.driver_number || '');
      if (!label) continue;
      if (parts.length === 0) {
        var time = f1FormatDuration(row.duration);
        if (!time) continue;
        parts.push(label + ' ' + time);
      } else {
        var gap = f1FormatGap(row.gap_to_leader);
        if (gap) parts.push(label + ' ' + gap);
        else {
          var fallback = f1FormatDuration(row.duration);
          if (fallback) parts.push(label + ' ' + fallback);
        }
      }
    }
    return parts.join(' · ');
  }

  function overlayOpenF1Cards(cards, cfg) {
    if (!cards || !cards.length) return Promise.resolve(cards);
    return fetchOpenF1Json('/sessions?session_key=latest').then(function (latest) {
      var meetingKey = latest && latest[0] && latest[0].meeting_key;
      if (meetingKey == null) return cards;
      return fetchOpenF1Json('/sessions?meeting_key=' + encodeURIComponent(meetingKey)).then(function (sessions) {
        if (!sessions || !sessions.length) return cards;
        var now = Date.now();
        var list = [];
        var i;
        for (i = 0; i < sessions.length; i++) {
          var s = sessions[i];
          if (!s || s.is_cancelled) continue;
          var start = f1ParseIso(s.date_start);
          var end = f1ParseIso(s.date_end);
          if (!start || !end) continue;
          list.push({
            raw: s,
            tag: f1OpenF1Tag(s),
            start: start,
            startMs: start.getTime(),
            endMs: end.getTime()
          });
        }
        list.sort(function (a, b) { return a.startMs - b.startMs; });
        var completed = null;
        var live = null;
        var upcoming = null;
        for (i = 0; i < list.length; i++) {
          var item = list[i];
          if (item.endMs < now) completed = item;
          else if (item.startMs <= now && item.endMs > now) live = item;
          else if (item.startMs > now && !upcoming) upcoming = item;
        }
        var resultKey = completed && completed.raw.session_key;
        var resultP = resultKey != null
          ? fetchOpenF1Json('/session_result?session_key=' + encodeURIComponent(resultKey))
          : Promise.resolve(null);
        return resultP.then(function (results) {
          var driversP = (resultKey != null && results)
            ? fetchOpenF1Json('/drivers?session_key=' + encodeURIComponent(resultKey))
            : Promise.resolve(null);
          return driversP.then(function (drivers) {
            var out = cards.slice();
            var href = (cards[0] && cards[0].url) || '';
            var meta = (cfg && cfg.meta) || 'Live · race weekend';
            var cmo = (cfg && cfg.cmo) || {};
            if (completed && results && results.length) {
              var line = f1Top3Line(results, drivers);
              if (line) {
                out[1] = {
                  tag: completed.tag,
                  headline: line,
                  snippet: completed.tag + ' result · OpenF1 historical',
                  meta: meta,
                  url: href
                };
              }
            }
            var stateCard;
            if (live) {
              stateCard = {
                tag: 'Live',
                headline: live.tag + ' is on',
                snippet: live.tag + ' is on · ' + f1FormatLocal(live.start),
                meta: meta,
                url: href
              };
            } else if (upcoming) {
              stateCard = {
                tag: 'Next',
                headline: cmo.state || 'Next up',
                snippet: upcoming.tag + ' · ' + f1FormatLocal(upcoming.start),
                meta: meta,
                url: href
              };
            } else {
              var finished = !!(completed && !live && !upcoming);
              var snip = cmo.next
                ? cmo.next
                : (finished ? 'This race is in the books.' : ((out[2] && out[2].snippet) || 'Race weekend'));
              stateCard = {
                tag: finished ? 'Finished' : ((out[2] && out[2].tag) || 'Next'),
                headline: finished ? 'Just finished' : (cmo.state || (out[2] && out[2].headline) || 'Next up'),
                snippet: snip,
                meta: meta,
                url: href
              };
            }
            if (out.length >= 3) out[2] = stateCard;
            else out.push(stateCard);
            return out;
          });
        });
      });
    }).catch(function () {
      return cards;
    });
  }

  function fetchF1Cards() {
    var cfg = railCfg();
    var nextUrl = cfg.endpoint || 'https://api.jolpi.ca/ergast/f1/current/next.json';
    var lastUrl = /\/next\.json/i.test(nextUrl)
      ? nextUrl.replace(/\/next\.json/i, '/last.json')
      : 'https://api.jolpi.ca/ergast/f1/current/last.json';
    function fromLast() {
      return fetchF1Json(lastUrl).then(function (data) {
        var race = f1RaceFromPayload(data);
        if (!race) throw new Error('jolpica last empty');
        return f1CardsFromRace(race, cfg, true);
      });
    }
    return fetchF1Json(nextUrl).then(function (data) {
      var race = f1RaceFromPayload(data);
      if (!race) return fromLast();
      return f1CardsFromRace(race, cfg, false);
    }).catch(function (err) {
      return fromLast().catch(function () { throw err; });
    }).then(function (cards) {
      if (!cards || !cards.length) throw new Error('jolpica empty');
      return overlayOpenF1Cards(cards, cfg);
    });
  }

  function fallbackTrendCards() {
    var extra = outboundCards();
    if (extra.length) return extra.slice(0, 1);
    if (railKind() === 'f1-calendar') return (TRENDS || []).slice(0, railNwsSlots());
    if (railKind() || railCfg().porch) return [];
    return (TRENDS || []).slice(0, 1);
  }

  function railNwsSlots() {
    var porch = railCfg().porch;
    var porchOn = !!(porch && porch.options && porch.options.length);
    var max = parseInt(railCfg().maxCards, 10) || RAIL_MAX;
    if (max < 1) max = RAIL_MAX;
    if (railKind() === 'f1-calendar') {
      var pins = outboundCards().length;
      return 3 + pins;
    }
    return porchOn ? Math.max(1, max - 1) : max;
  }

  var f1RefreshTimer = null;
  var PORCH_DWELL_DEFAULT_MS = 9000;
  var porchDwellActive = false;
  var porchDwellPaused = false;
  var porchDwellTimer = null;
  var porchDwellRemaining = 0;
  var porchDwellTickAt = 0;
  var porchDwellPendingItems = null;
  var porchDwellHoverBound = false;

  function porchDwellMs() {
    var porch = railCfg().porch || {};
    var n = parseInt(porch.dwellMs, 10);
    if (isNaN(n)) n = PORCH_DWELL_DEFAULT_MS;
    return n;
  }

  function porchDwellSessionKey() {
    return 'subx.porchDwell.' + (SITE_ID || 'site');
  }

  function porchDwellDoneThisSession() {
    try { return sessionStorage.getItem(porchDwellSessionKey()) === '1'; } catch (e) { return false; }
  }

  function markPorchDwellDone() {
    try { sessionStorage.setItem(porchDwellSessionKey(), '1'); } catch (e) { /* private mode */ }
  }

  function porchEnabled() {
    var porch = railCfg().porch;
    return !!(porch && porch.options && porch.options.length);
  }

  function shouldPorchDwell() {
    return porchEnabled() && porchDwellMs() > 0 && !porchDwellDoneThisSession();
  }

  function railHasItems() {
    var rail = document.getElementById('news-feed') || document.getElementById('news-page-list');
    return !!(rail && rail.querySelector('.news-item'));
  }

  function setPorchDwellAttr(on) {
    ['news-feed', 'news-page-list', 'right-panel'].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      if (on) el.setAttribute('data-porch-dwell', '1');
      else el.removeAttribute('data-porch-dwell');
    });
  }

  function isPorchDwellHovered() {
    var ids = ['right-panel', 'news-page-list'];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      try { if (el && el.matches(':hover')) return true; } catch (e) {}
    }
    return false;
  }

  function bindPorchDwellHover() {
    if (porchDwellHoverBound) return;
    porchDwellHoverBound = true;
    ['right-panel', 'news-page-list'].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('pointerenter', pausePorchDwell);
      el.addEventListener('pointerleave', resumePorchDwell);
    });
  }

  function seedRail() {
    var extra = outboundCards();
    paintRail(extra.length ? extra.slice(0, railNwsSlots()) : []);
  }

  function commitRail(items) {
    if (currentNest) return;
    if (porchDwellActive) {
      porchDwellPendingItems = items;
      return;
    }
    paintRail(items);
  }

  function abortPorchForNest() {
    if (!porchDwellActive) return;
    porchDwellActive = false;
    porchDwellPaused = false;
    if (porchDwellTimer) {
      clearTimeout(porchDwellTimer);
      porchDwellTimer = null;
    }
    porchDwellPendingItems = null;
    setPorchDwellAttr(false);
  }

  function schedulePorchDwell() {
    if (porchDwellTimer) clearTimeout(porchDwellTimer);
    porchDwellTickAt = Date.now();
    porchDwellTimer = setTimeout(finishPorchDwell, Math.max(0, porchDwellRemaining));
  }

  function pausePorchDwell() {
    if (!porchDwellActive || porchDwellPaused) return;
    porchDwellPaused = true;
    porchDwellRemaining -= (Date.now() - porchDwellTickAt);
    if (porchDwellRemaining < 0) porchDwellRemaining = 0;
    if (porchDwellTimer) {
      clearTimeout(porchDwellTimer);
      porchDwellTimer = null;
    }
  }

  function resumePorchDwell() {
    if (!porchDwellActive || !porchDwellPaused) return;
    porchDwellPaused = false;
    schedulePorchDwell();
  }

  function finishPorchDwell() {
    if (!porchDwellActive) return;
    porchDwellActive = false;
    porchDwellPaused = false;
    if (porchDwellTimer) {
      clearTimeout(porchDwellTimer);
      porchDwellTimer = null;
    }
    setPorchDwellAttr(false);
    var items = porchDwellPendingItems;
    porchDwellPendingItems = null;
    if (items && items.length) paintRail(items);
    else seedRail();
  }

  function startPorchDwell() {
    if (porchDwellActive || !shouldPorchDwell()) return;
    markPorchDwellDone();
    porchDwellActive = true;
    porchDwellPaused = false;
    porchDwellRemaining = porchDwellMs();
    setPorchDwellAttr(true);
    bindPorchDwellHover();
    if (isPorchDwellHovered()) {
      porchDwellPaused = true;
      porchDwellTickAt = Date.now();
      return;
    }
    schedulePorchDwell();
  }

  function renderTrends(quiet) {
    var liveFetch = null;
    if (railUsesCwf()) liveFetch = fetchCwfCards;
    else if (railKind() === 'bart-bsa') liveFetch = fetchBartCards;
    else if (railKind() === 'f1-calendar') liveFetch = fetchF1Cards;
    else if (railUsesNws()) liveFetch = fetchNwsCards;
    if (!liveFetch) {
      if (!quiet && !railHasItems() && shouldPorchDwell()) {
        paintRail([]);
        startPorchDwell();
      }
      commitRail(outboundCards().slice(0, railNwsSlots()));
      return;
    }
    if (!quiet && !railHasItems()) {
      if (shouldPorchDwell()) {
        paintRail([]);
        startPorchDwell();
      } else {
        seedRail();
      }
    }
    liveFetch().then(function (cards) {
      var extra = outboundCards();
      var merged = (cards || []).concat(extra);
      if (merged.length) commitRail(merged.slice(0, railNwsSlots()));
      else commitRail(fallbackTrendCards());
    }).catch(function (err) {
      console.warn(railKind() || 'rail', err);
      commitRail(fallbackTrendCards());
    });
    if (railKind() === 'f1-calendar' && !f1RefreshTimer) {
      f1RefreshTimer = setInterval(function () {
        renderTrends(true);
      }, 5 * 60 * 1000);
    }
  }

  function porchPrompt() {
    return String((railCfg().porch || {}).prompt || 'Porch').trim() || 'Porch';
  }

  function porchPromptStem() {
    return porchPrompt().replace(/[?]+$/, '').trim();
  }

  function porchPickStorageKey() {
    return (SITE_ID || 'room') + ':porchPick';
  }

  function lastPorchPick() {
    try { return sessionStorage.getItem(porchPickStorageKey()) || ''; } catch (e) { return ''; }
  }

  function rememberPorchPick(option) {
    var opt = String(option || '').trim();
    if (!opt) return;
    try { sessionStorage.setItem(porchPickStorageKey(), opt); } catch (e) { /* private mode */ }
  }

  function porchLine(option) {
    var opt = String(option || '').trim().replace(/\.+$/, '');
    if (!opt) return '';
    var prompt = porchPrompt();
    var line = 'Porch · ' + prompt + ' → ' + opt;
    if (line.length > 280) line = line.slice(0, 280);
    return line;
  }

  function porchOptionFromText(text) {
    var raw = String(text || '').replace(/\s+/g, ' ').trim().replace(/\.+$/, '');
    if (!raw) return '';
    var porch = railCfg().porch || {};
    var options = porch.options || [];
    var stem = porchPromptStem().toLowerCase();
    var i;
    for (i = 0; i < options.length; i++) {
      var opt = String(options[i] || '').trim();
      if (!opt) continue;
      var canonical = porchLine(opt).replace(/\.+$/, '');
      if (raw === canonical) return opt;
      var alt = (porchPromptStem() + ': ' + opt).replace(/\s+/g, ' ').trim();
      if (raw.toLowerCase() === alt.toLowerCase()) return opt;
      if (raw === opt) return opt;
    }
    var arrow = raw.indexOf('→');
    if (arrow < 0) arrow = raw.indexOf('->');
    if (arrow >= 0) {
      var left = raw.slice(0, arrow).toLowerCase();
      var right = raw.slice(arrow).replace(/^→\s*|^->\s*/, '').trim();
      if (stem && left.indexOf(stem) !== -1) {
        for (i = 0; i < options.length; i++) {
          if (right === String(options[i] || '').trim()) return options[i];
        }
      }
    }
    return '';
  }

  function porchTallyCounts() {
    var porch = railCfg().porch || {};
    var options = porch.options || [];
    var counts = {};
    var i;
    for (i = 0; i < options.length; i++) counts[options[i]] = 0;
    var posts = livePosts || [];
    for (i = 0; i < posts.length; i++) {
      var post = posts[i];
      if (!post || post.parentId) continue;
      var opt = porchOptionFromText(post.text);
      if (opt && Object.prototype.hasOwnProperty.call(counts, opt)) counts[opt] += 1;
    }
    return counts;
  }

  function porchTallyLine() {
    var porch = railCfg().porch || {};
    var options = porch.options || [];
    var counts = porchTallyCounts();
    return options.map(function (opt) {
      return String(opt) + ' ' + (counts[opt] || 0);
    }).join(' · ');
  }

  function refreshPorchUi() {
    var nodes = document.querySelectorAll('.news-item-porch');
    if (!nodes.length) return;
    var html = porchCardHtml();
    if (!html) return;
    for (var i = 0; i < nodes.length; i++) {
      var wrap = document.createElement('div');
      wrap.innerHTML = html;
      var next = wrap.firstElementChild;
      if (next && nodes[i].parentNode) nodes[i].parentNode.replaceChild(next, nodes[i]);
    }
  }

  function fillCompose(text) {
    var input = document.getElementById('thoughts-compose-input');
    if (!input) return;
    input.value = text;
    input.dispatchEvent(new Event('input'));
    try { input.focus(); } catch (e) {}
  }

  function addRoomTextPost(text) {
    var live = fbAuth && fbAuth.currentUser;
    var disp = (currentUser && currentUser.name) || live.displayName || (live.email || 'member').split('@')[0] || 'Member';
    var handle = (currentUser && currentUser.handle) || String(disp).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
    return fbDb.collection('posts').add({
      siteId: SITE_ID,
      parentId: null,
      authorUid: live.uid,
      authorName: disp,
      authorHandle: handle,
      text: String(text || '').slice(0, 280),
      likes: {},
      likeCount: 0,
      replyCount: 0,
      nestSlug: postNestSlug(null),
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    });
  }

  function porchPick(option) {
    finishPorchDwell();
    var line = porchLine(option);
    if (!line) return;
    rememberPorchPick(option);
    refreshPorchUi();
    if (!isLiveUser()) {
      go('home');
      fillCompose(line);
      composeErr('Sign in to post. Guest can only browse.');
      openAuth('join');
      return;
    }
    if (!requireVerified('post')) return;
    if (!fbDb) { composeErr('Feed is not connected.'); return; }
    composeErr('');
    addRoomTextPost(line).then(function () {
      composeErr('Posted.');
      refreshPorchUi();
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not post.');
    });
  }

  function nestSeatCards() {
    var nests = (site && site.nests) || [];
    return nests.map(function (n) {
      return {
        tag: (n.kind === 'species' ? 'Species' : (n.kind || 'Nest')),
        title: n.label || n.slug || 'Nest',
        snippet: n.blurb || n.body || '',
        url: ''
      };
    });
  }

  function renderExplore() {
    function cards(list) {
      return list.map(function (c) {
        const inner = '<div class="explore-card-tag">' + escapeHtml(c.tag) + '</div>' +
          '<div class="explore-card-title">' + escapeHtml(c.title) + '</div>' +
          '<div class="explore-card-snippet">' + escapeHtml(c.snippet) + '</div>';
        if (c.url) {
          return '<a class="explore-card" href="' + c.url + '" target="_blank" rel="noopener noreferrer">' + inner + '</a>';
        }
        return '<article class="explore-card">' + inner + '</article>';
      }).join('');
    }
    var explainer = document.getElementById('explore-explainer');
    if (explainer) {
      var copy = (site && site.exploreExplainer) || '';
      explainer.textContent = copy;
      explainer.hidden = !copy;
    }
    var seats = nestSeatCards();
    var placeCards = seats.length ? seats : PLACES;
    var places = document.getElementById('explore-pane-places');
    var topics = document.getElementById('explore-pane-topics');
    if (places) places.innerHTML = cards(placeCards);
    if (topics) topics.innerHTML = cards(TOPICS);
  }

  function renderNotifs() {
    const el = document.getElementById('notif-list');
    if (!el) return;
    el.innerHTML = '<div class="soon-panel">' +
      '<strong>Notifications — Soon.</strong>' +
      '<p>No live alerts in this preview. Dummy copy stays in site.json as sample only and is not shown as real activity.</p>' +
      '</div>';
    const badge = document.getElementById('notif-badge');
    if (badge) {
      badge.textContent = '';
      badge.classList.remove('visible');
      badge.hidden = true;
    }
  }

  function dmSiteId() {
    return SITE_ID || '311chat';
  }
  function convIdFor(uidA, uidB) {
    return dmSiteId() + '__' + [String(uidA || ''), String(uidB || '')].sort().join('_');
  }
  function findConv(cid) {
    for (var i = 0; i < dmConversations.length; i++) if (dmConversations[i].id === cid) return dmConversations[i];
    return null;
  }
  function convPeerUid(conv) {
    var me = liveUid();
    var parts = (conv && conv.participants) || [];
    for (var i = 0; i < parts.length; i++) if (parts[i] && parts[i] !== me) return parts[i];
    if (pendingPeer && pendingPeer.uid) return pendingPeer.uid;
    return '';
  }
  function convPeerName(conv) {
    var uid = convPeerUid(conv);
    var names = (conv && conv.participantNames) || {};
    if (names[uid] && String(names[uid]).indexOf('@') === -1) return names[uid];
    if (pendingPeer && pendingPeer.uid === uid && pendingPeer.name) return pendingPeer.name;
    return 'Member';
  }
  function dmDisplayName(raw) {
    var n = String(raw || '').trim();
    if (!n || looksLikeUid(n) || n.indexOf('@') !== -1) return 'Member';
    return n;
  }
  function myDisplayName() {
    return dmDisplayName((currentUser && currentUser.name) || (fbAuth && fbAuth.currentUser && fbAuth.currentUser.displayName) || 'Member');
  }

  function ensureDmCss() {
    if (document.getElementById('dm-css')) return;
    var st = document.createElement('style');
    st.id = 'dm-css';
    st.textContent =
      '.post-name-link{cursor:pointer;}' +
      '.post-name-link:hover{text-decoration:underline;}' +
      '.thread-unread{display:inline-block;margin-left:0.35rem;min-width:1.1rem;padding:0.05rem 0.35rem;border-radius:999px;background:var(--accent,#e10600);color:#fff;font-size:0.68rem;font-weight:700;text-align:center;}' +
      '#chat-compose-err{padding:0.35rem 1rem 0;font-size:0.8rem;color:var(--accent,#e10600);}' +
      '.chat-user-picker{position:absolute;inset:12px;z-index:4;background:var(--surface,#1c1c20);border:1px solid var(--border,#2c2c32);border-radius:12px;display:flex;flex-direction:column;overflow:hidden;}' +
      '.chat-user-picker[hidden]{display:none!important;}' +
      '.chat-user-picker-head{display:flex;align-items:center;justify-content:space-between;padding:0.85rem 1rem;border-bottom:1px solid var(--border,#2c2c32);font-weight:700;}' +
      '.chat-user-picker-head button{background:none;border:0;color:inherit;font-size:1.2rem;cursor:pointer;}' +
      '.chat-picker-item{display:flex;gap:0.7rem;align-items:center;padding:0.75rem 1rem;cursor:pointer;border-bottom:1px solid var(--border,#2c2c32);}' +
      '.chat-picker-item:hover{background:rgba(225,6,0,0.08);}' +
      '#chat-thread-view[hidden],#chat-placeholder[hidden],#chat-user-picker[hidden],#profile-message-btn[hidden]{display:none!important;}';
    document.head.appendChild(st);
  }

  function teardownDms() {
    if (convsUnsub) { convsUnsub(); convsUnsub = null; }
    if (msgsUnsub) { msgsUnsub(); msgsUnsub = null; }
    dmConversations = [];
    activeConvId = null;
    pendingPeer = null;
  }

  function listenConversations() {
    if (convsUnsub) { convsUnsub(); convsUnsub = null; }
    if (!dmsOn() || !fbDb || !isLiveUser()) {
      dmConversations = [];
      renderThreads();
      syncChatChrome();
      return;
    }
    convsUnsub = fbDb.collection('conversations')
      .where('siteId', '==', dmSiteId())
      .where('participants', 'array-contains', liveUid())
      .orderBy('lastMessageAt', 'desc')
      .onSnapshot(function (snap) {
        dmConversations = snap.docs.map(function (doc) {
          var d = doc.data() || {};
          return {
            id: doc.id,
            participants: d.participants || [],
            participantNames: d.participantNames || {},
            lastMessage: d.lastMessage || '',
            lastMessageAt: d.lastMessageAt,
            lastMessageBy: d.lastMessageBy || '',
            unreadCounts: d.unreadCounts || {}
          };
        });
        renderThreads();
        syncChatChrome();
      }, function (err) {
        console.warn('conversations', err);
        chatErr((err && err.message) ? err.message : 'Could not load chats.');
        renderThreads();
      });
  }

  function chatErr(msg) {
    var el = document.getElementById('chat-compose-err');
    if (!el) {
      el = document.createElement('div');
      el.id = 'chat-compose-err';
      el.setAttribute('role', 'status');
      var compose = document.querySelector('#chat-thread-view .chat-compose');
      if (compose && compose.parentNode) compose.parentNode.insertBefore(el, compose);
      else return;
    }
    el.textContent = msg || '';
  }

  function paintChatPlaceholder() {
    var title = document.querySelector('#chat-placeholder .chat-placeholder-title');
    var sub = document.querySelector('#chat-placeholder .chat-placeholder-sub');
    var ph = document.getElementById('chat-placeholder');
    var view = document.getElementById('chat-thread-view');
    if (!dmsOn()) {
      if (title) title.textContent = 'Chat — Soon';
      if (sub) sub.textContent = 'Direct messages are not live in this preview. No DMs graph. Sample thread copy in site.json is not a real inbox.';
      if (ph) ph.hidden = false;
      if (view) view.hidden = true;
      return;
    }
    if (activeConvId) {
      if (ph) ph.hidden = true;
      if (view) view.hidden = false;
      return;
    }
    if (ph) ph.hidden = false;
    if (view) view.hidden = true;
    if (!isLiveUser()) {
      if (title) title.textContent = 'Join to chat';
      if (sub) sub.textContent = 'Sign in to send and receive direct messages. Guest cannot chat.';
    } else if (!dmConversations.length) {
      if (title) title.textContent = 'No messages yet';
      if (sub) sub.textContent = 'Start a DM from another user\'s profile.';
    } else {
      if (title) title.textContent = 'Chat';
      if (sub) sub.textContent = 'Pick a conversation.';
    }
  }

  function syncChatChrome() {
    var newBtn = document.getElementById('chat-new-btn');
    var phNew = document.getElementById('chat-placeholder-new');
    var sendBtn = document.getElementById('chat-send-btn');
    var input = document.getElementById('chat-compose-input');
    var admin = dmsOn() && isLiveUser() && liveUid() === ADMIN_UID;
    var threadOpen = !!activeConvId;
    var peer = pendingPeer && pendingPeer.uid ? pendingPeer.uid : (findConv(activeConvId) ? convPeerUid(findConv(activeConvId)) : '');
    var blocked = !!(peer && blockedUids[peer]);

    if (newBtn) {
      if (!dmsOn()) {
        newBtn.hidden = false;
        newBtn.disabled = true;
        newBtn.textContent = 'Soon';
        newBtn.title = 'DMs coming soon';
      } else if (admin) {
        newBtn.hidden = false;
        newBtn.disabled = false;
        newBtn.textContent = 'New';
        newBtn.title = 'New message';
      } else {
        newBtn.hidden = true;
      }
    }
    if (phNew) {
      if (!dmsOn()) {
        phNew.hidden = false;
        phNew.disabled = true;
        phNew.textContent = 'Soon';
      } else if (!isLiveUser()) {
        phNew.hidden = false;
        phNew.disabled = false;
        phNew.textContent = 'Join';
      } else if (admin && !threadOpen) {
        phNew.hidden = false;
        phNew.disabled = false;
        phNew.textContent = 'New';
      } else {
        phNew.hidden = true;
      }
    }
    if (sendBtn) {
      if (!dmsOn()) {
        sendBtn.disabled = true;
        sendBtn.textContent = 'Soon';
      } else {
        sendBtn.textContent = 'Send';
        sendBtn.disabled = !(dmsOn() && isLiveUser() && threadOpen) || blocked;
      }
    }
    if (input) {
      input.maxLength = DM_TEXT_MAX;
      input.disabled = !dmsOn() || !isLiveUser() || !threadOpen || blocked;
    }
    if (blocked && threadOpen) chatErr('You blocked this user.');
    else if (!blocked) chatErr('');
    paintChatPlaceholder();
  }

  function renderThreads() {
    const el = document.getElementById('chat-thread-list');
    if (!el) return;
    if (!dmsOn()) {
      el.innerHTML = '<div class="soon-panel soon-panel-pad">' +
        '<strong>Chat — Soon.</strong>' +
        '<p>Direct messages are not live. Sample thread copy in site.json is not a real inbox.</p>' +
        '</div>';
      return;
    }
    if (!isLiveUser()) {
      el.innerHTML = '<div class="soon-panel soon-panel-pad">' +
        '<strong>Join to chat.</strong>' +
        '<p>Sign in to send and receive direct messages. Guest cannot chat.</p>' +
        '</div>';
      return;
    }
    var q = ((document.getElementById('chat-search-input') || {}).value || '').trim().toLowerCase();
    var list = dmConversations.filter(function (c) {
      if (!q) return true;
      var name = String(convPeerName(c) || '').toLowerCase();
      var prev = String(c.lastMessage || '').toLowerCase();
      return name.indexOf(q) !== -1 || prev.indexOf(q) !== -1;
    });
    if (!list.length) {
      el.innerHTML = '<div class="soon-panel soon-panel-pad">' +
        '<strong>' + (dmConversations.length ? 'No matches.' : 'No messages yet.') + '</strong>' +
        '</div>';
      return;
    }
    var me = liveUid();
    el.innerHTML = list.map(function (c) {
      var name = convPeerName(c);
      var unread = (c.unreadCounts && me && c.unreadCounts[me]) || 0;
      var handle = String(name).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
      return '<div class="chat-thread-item' + (c.id === activeConvId ? ' active' : '') + '" data-cid="' + escapeHtml(c.id) + '">' +
        '<div class="post-avatar" style="background:' + colorFor(handle) + '">' + initials(name) + '</div>' +
        '<div><div class="thread-name">' + escapeHtml(name) +
          (unread ? '<span class="thread-unread">' + escapeHtml(String(unread)) + '</span>' : '') +
        '</div><div class="thread-preview">' + escapeHtml(c.lastMessage || '') + '</div></div></div>';
    }).join('');
  }

  function markRead(cid) {
    if (!fbDb || !cid || !liveUid() || !dmsOn()) return;
    var me = liveUid();
    var conv = findConv(cid);
    if (conv && conv.unreadCounts && !conv.unreadCounts[me]) return;
    var patch = {};
    patch['unreadCounts.' + me] = 0;
    fbDb.collection('conversations').doc(cid).update(patch).catch(function () {});
  }

  function listenMessages(cid) {
    if (msgsUnsub) { msgsUnsub(); msgsUnsub = null; }
    var el = document.getElementById('chat-messages');
    if (!dmsOn() || !fbDb || !cid || !isLiveUser()) {
      if (el) el.innerHTML = '';
      return;
    }
    msgsUnsub = fbDb.collection('conversations').doc(cid).collection('messages')
      .orderBy('createdAt', 'asc')
      .onSnapshot(function (snap) {
        var me = liveUid();
        if (el) {
          el.innerHTML = snap.docs.map(function (doc) {
            var d = doc.data() || {};
            return '<div class="chat-bubble ' + (d.fromUid === me ? 'me' : 'them') + '">' + escapeHtml(d.text || '') + '</div>';
          }).join('');
          el.scrollTop = el.scrollHeight;
        }
        markRead(cid);
      }, function (err) {
        console.warn('messages', err);
        chatErr((err && err.message) ? err.message : 'Could not load messages.');
      });
  }

  function openThread(cid, opts) {
    opts = opts || {};
    if (!dmsOn() || !cid) return;
    activeConvId = cid;
    var conv = findConv(cid);
    var peerUid = (pendingPeer && pendingPeer.uid) || (conv && convPeerUid(conv)) || '';
    if (peerUid && (!pendingPeer || pendingPeer.uid !== peerUid)) {
      pendingPeer = { uid: peerUid, name: opts.name || (conv && convPeerName(conv)) || 'Member' };
    }
    var nameEl = document.getElementById('chat-active-name');
    if (nameEl) nameEl.textContent = opts.name || (conv ? convPeerName(conv) : (pendingPeer && pendingPeer.name) || 'Chat');
    var overlay = document.getElementById('chat-overlay');
    if (overlay) overlay.classList.add('thread-open');
    syncChatChrome();
    renderThreads();
    listenMessages(cid);
    markRead(cid);
  }

  function startDm(otherUid, otherName) {
    if (!dmsOn()) return;
    if (!isLiveUser()) { openAuth('join'); return; }
    if (!requireVerified('chat')) return;
    otherUid = String(otherUid || '');
    if (!otherUid || otherUid === liveUid()) return;
    if (blockedUids[otherUid]) {
      chatErr('You blocked this user.');
      return;
    }
    pendingPeer = { uid: otherUid, name: dmDisplayName(otherName) };
    if (routeFromHash() !== 'chat') go('chat');
    else openChat();
    openThread(convIdFor(liveUid(), otherUid), { name: pendingPeer.name });
  }

  function sendDm() {
    if (!dmsOn()) return;
    if (!requireVerified('chat')) return;
    var input = document.getElementById('chat-compose-input');
    var text = ((input && input.value) || '').replace(/\s+/g, ' ').trim();
    if (!text) return;
    if (text.length > DM_TEXT_MAX) text = text.slice(0, DM_TEXT_MAX);
    var me = liveUid();
    var conv = findConv(activeConvId);
    var other = (pendingPeer && pendingPeer.uid) || (conv && convPeerUid(conv)) || '';
    if (!me || !other || other === me) return;
    if (blockedUids[other]) {
      chatErr('You blocked this user.');
      return;
    }
    if (!fbDb) { chatErr('Chat is not connected.'); return; }
    var peerName = dmDisplayName((pendingPeer && pendingPeer.name) || (conv && convPeerName(conv)) || 'Member');
    var myName = myDisplayName();
    var cid = convIdFor(me, other);
    var convRef = fbDb.collection('conversations').doc(cid);
    var msgRef = convRef.collection('messages').doc();
    var sendBtn = document.getElementById('chat-send-btn');
    if (sendBtn) sendBtn.disabled = true;
    chatErr('');
    fbDb.runTransaction(function (transaction) {
      return transaction.get(convRef).then(function (snap) {
        var names = {};
        names[me] = myName;
        names[other] = peerName;
        var unread = {};
        unread[me] = 0;
        unread[other] = 1;
        if (snap.exists) {
          var d = snap.data() || {};
          var existingNames = d.participantNames || {};
          names[me] = myName || dmDisplayName(existingNames[me]);
          names[other] = dmDisplayName(existingNames[other]) !== 'Member' ? dmDisplayName(existingNames[other]) : peerName;
          var prev = d.unreadCounts || {};
          unread[other] = (typeof prev[other] === 'number' ? prev[other] : 0) + 1;
          transaction.update(convRef, {
            lastMessage: text,
            lastMessageAt: firebase.firestore.FieldValue.serverTimestamp(),
            lastMessageBy: me,
            unreadCounts: unread,
            participantNames: names
          });
        } else {
          transaction.set(convRef, {
            siteId: dmSiteId(),
            participants: [me, other],
            participantNames: names,
            lastMessage: text,
            lastMessageAt: firebase.firestore.FieldValue.serverTimestamp(),
            lastMessageBy: me,
            unreadCounts: unread,
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
          });
        }
        transaction.set(msgRef, {
          fromUid: me,
          text: text,
          createdAt: firebase.firestore.FieldValue.serverTimestamp(),
          siteId: dmSiteId()
        });
      });
    }).then(function () {
      if (input) {
        input.value = '';
        input.style.height = 'auto';
      }
      activeConvId = cid;
      listenMessages(cid);
      syncChatChrome();
    }).catch(function (e) {
      chatErr((e && e.message) ? e.message : 'Could not send.');
      syncChatChrome();
    });
  }

  function hideDmPicker() {
    var el = document.getElementById('chat-user-picker');
    if (el) el.hidden = true;
  }

  function openAdminPicker() {
    if (!dmsOn()) {
      chatErr('Chat is not enabled on this room.');
      return;
    }
    if (liveUid() !== ADMIN_UID) {
      chatErr('Welcome sends need the factory admin Google (jebb.dykstra@gmail.com). This signed-in account is not that admin.');
      return;
    }
    if (!requireVerified('chat')) return;
    if (!fbDb) { chatErr('Chat is not connected.'); return; }
    ensureDmCss();
    var picker = document.getElementById('chat-user-picker');
    if (!picker) {
      picker = document.createElement('div');
      picker.id = 'chat-user-picker';
      picker.className = 'chat-user-picker';
      picker.innerHTML = '<div class="chat-user-picker-head">New message<button type="button" id="chat-picker-close" aria-label="Close">×</button></div><div id="chat-picker-list"></div>';
      var overlay = document.getElementById('chat-overlay');
      if (overlay) overlay.appendChild(picker);
    }
    var list = document.getElementById('chat-picker-list');
    if (list) list.innerHTML = '<div class="soon-panel">Loading…</div>';
    picker.hidden = false;
    fbDb.collection('users').where('siteId', '==', dmSiteId()).limit(80).get().then(function (snap) {
      var me = liveUid();
      var rows = [];
      snap.forEach(function (doc) {
        if (doc.id === me) return;
        var d = doc.data() || {};
        var name = dmDisplayName(d.displayName);
        rows.push({ uid: doc.id, name: name });
      });
      rows.sort(function (a, b) { return a.name.localeCompare(b.name); });
      if (!list) return;
      if (!rows.length) {
        list.innerHTML = '<div class="soon-panel">No 311chat users yet.</div>';
        return;
      }
      list.innerHTML = rows.map(function (u) {
        var handle = String(u.name).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
        return '<div class="chat-picker-item" data-pick-uid="' + escapeHtml(u.uid) + '" data-pick-name="' + escapeHtml(u.name) + '">' +
          '<div class="post-avatar" style="background:' + colorFor(handle) + '">' + initials(u.name) + '</div>' +
          '<div class="thread-name">' + escapeHtml(u.name) + '</div></div>';
      }).join('');
    }).catch(function (e) {
      if (list) list.innerHTML = '<div class="soon-panel">' + escapeHtml((e && e.message) || 'Could not list users.') + '</div>';
    });
  }

  function onChatNew() {
    if (!dmsOn()) return;
    if (!isLiveUser()) { openAuth('join'); return; }
    if (liveUid() === ADMIN_UID) openAdminPicker();
  }

  function openChat() {
    closeSocialOverlays();
    hideDmPicker();
    document.getElementById('chat-overlay').classList.add('active');
    highlightSocial('chat');
    syncChatChrome();
    renderThreads();
  }
  function openNotif() {
    closeSocialOverlays();
    document.getElementById('notif-overlay').classList.add('active');
    highlightSocial('notifications');
  }
  function openExplore() {
    closeSocialOverlays();
    ensureExploreNestTab();
    document.getElementById('explore-overlay').classList.add('active');
    highlightSocial('explore');
  }
  function openProfile() {
    viewingProfile = null;
    closeSocialOverlays();
    document.getElementById('profile-overlay').classList.add('active');
    highlightSocial('profile');
    syncProfile();
  }

  function openUserProfile(uid, name, handle) {
    if (!uid) return;
    if (liveUid() && uid === liveUid()) { openProfile(); return; }
    viewingProfile = {
      uid: uid,
      name: dmDisplayName(name),
      handle: String(handle || name || 'member').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member'
    };
    closeSocialOverlays();
    document.getElementById('profile-overlay').classList.add('active');
    highlightSocial('profile');
    syncProfile();
  }

  function paintProfile(name, handle, bio, uid) {
    var top = document.getElementById('profile-topbar-name');
    if (top) top.textContent = name;
    var dn = document.getElementById('profile-display-name');
    if (dn) dn.textContent = name;
    var h = document.getElementById('profile-handle');
    if (h) h.textContent = '@' + handle;
    var av = document.getElementById('profile-avatar');
    if (av) av.textContent = initials(name);
    var b = document.getElementById('profile-bio');
    if (b) b.textContent = bio || '';
    const pane = document.getElementById('profile-pane-posts');
    if (!pane) return;
    const mine = livePosts.filter(function (p) { return p.authorUid && p.authorUid === uid; });
    if (!mine.length) {
      pane.innerHTML = '<div class="empty-note" id="profile-posts-empty">No posts yet. Official 311 is the handoff at the top of Home. Sign in to talk with neighbors.</div>';
    } else {
      pane.innerHTML = mine.map(function (p) { return renderPost(p, !!p.parentId); }).join('');
    }
  }

  function syncProfile() {
    const prompt = document.getElementById('profile-signin-prompt');
    const content = document.getElementById('profile-content');
    var editBtn = document.getElementById('profile-edit-btn');
    var msgBtn = document.getElementById('profile-message-btn');
    var other = viewingProfile && viewingProfile.uid && viewingProfile.uid !== liveUid();

    if (other) {
      if (prompt) prompt.hidden = true;
      if (content) content.hidden = false;
      if (editBtn) editBtn.hidden = true;
      if (msgBtn) {
        msgBtn.hidden = !dmsOn();
        msgBtn.disabled = false;
      }
      paintProfile(viewingProfile.name || 'Member', viewingProfile.handle || 'member', '', viewingProfile.uid);
      return;
    }

    if (msgBtn) msgBtn.hidden = true;
    if (editBtn) editBtn.hidden = false;

    if (!isLiveUser() || !currentUser || !currentUser.live) {
      if (prompt) prompt.hidden = false;
      if (content) content.hidden = true;
      var top = document.getElementById('profile-topbar-name');
      if (top) top.textContent = 'Profile';
      return;
    }
    if (prompt) prompt.hidden = true;
    if (content) content.hidden = false;
    paintProfile(
      currentUser.name,
      currentUser.handle,
      currentUser.bio || "Unofficial helper — not a substitute for 911.",
      currentUser.uid
    );
  }

  function renderSidebarAuth() {
    const el = document.getElementById('sidebar-auth');
    const av = document.getElementById('thoughts-compose-avatar');
    if (!el) return;
    if (isLiveUser() && currentUser && currentUser.live) {
      el.innerHTML =
        '<div class="sidebar-auth-user">' +
          '<div class="sidebar-auth-avatar">' + initials(currentUser.name) + '</div>' +
          '<div class="sidebar-auth-name">@' + escapeHtml(currentUser.handle) + '</div>' +
        '</div>' +
        '<button class="sidebar-auth-btn" id="auth-signout" type="button">Sign out</button>';
      if (av) {
        av.textContent = initials(currentUser.name);
        av.style.background = colorFor(currentUser.handle);
      }
    } else if (currentUser && !currentUser.live) {
      el.innerHTML =
        '<div class="sidebar-auth-user">' +
          '<div class="sidebar-auth-avatar">' + initials(currentUser.name || 'G') + '</div>' +
          '<div class="sidebar-auth-name">Guest · browse only</div>' +
        '</div>' +
        '<button class="sidebar-auth-btn primary" id="auth-signin" type="button">Sign in</button>' +
        '<button class="sidebar-auth-btn" id="auth-signout" type="button">Leave guest</button>';
      if (av) {
        av.textContent = initials(currentUser.name || 'G');
        av.style.background = colorFor(currentUser.handle || 'guest');
      }
    } else {
      el.innerHTML = '<button class="sidebar-auth-btn primary" id="auth-signin" type="button">Sign in</button>';
      if (av) {
        av.textContent = "CO";
        av.style.background = '';
      }
    }
  }

  function peekCompose() {
    var el = document.getElementById('thoughts-compose-input');
    return el ? el.value : '';
  }
  function restoreCompose(v) {
    var el = document.getElementById('thoughts-compose-input');
    if (!el || typeof v !== 'string') return;
    if (el.value !== v) {
      el.value = v;
      try { el.dispatchEvent(new Event('input')); } catch (e) {}
    }
  }
  function markAuthLand() {
    try { sessionStorage.setItem('subx.authLand', '1'); } catch (e) { /* private mode */ }
  }
  function consumeAuthLand() {
    try {
      if (sessionStorage.getItem('subx.authLand') === '1') {
        sessionStorage.removeItem('subx.authLand');
        return true;
      }
    } catch (e) { /* private mode */ }
    return false;
  }
  function landInFeedCompose() {
    closeAuth();
    closeSocialOverlays();
    if (normalizeRoute(location.hash) !== 'home') go('home');
    else {
      showContentPage('thoughts');
      highlightSocial(currentNest ? currentNest.slug : 'home');
    }
    setTimeout(function () {
      var input = document.getElementById('thoughts-compose-input');
      if (!input) return;
      try { input.focus(); } catch (e) {}
      try { input.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e2) {}
    }, 60);
  }
  function ensureJoinAuthCss() {
    if (document.getElementById('join-auth-css')) return;
    var st = document.createElement('style');
    st.id = 'join-auth-css';
    st.textContent =
      '.conv-modal-tabs.is-join-hidden{display:none;}' +
      '.conv-email-toggle{width:100%;padding:0.55rem;margin:0.15rem 0 0.35rem;' +
        'background:transparent;border:1px solid var(--border,rgba(0,0,0,0.14));' +
        'border-radius:50px;cursor:pointer;font-size:0.82rem;font-weight:600;' +
        'color:var(--text-muted,#666);}' +
      '.conv-email-toggle:hover{color:var(--text,#111);}' +
      '.cv-email-signin{margin-top:0.2rem;}' +
      '.conv-google-btn{margin-bottom:0.2rem;}';
    document.head.appendChild(st);
  }
  function ageCheckLabel() {
    var box = document.getElementById('cv-google-age');
    if (!box) return null;
    return box.closest('label') || box;
  }
  function fieldWrap(input) {
    if (!input) return null;
    return input.closest('.conv-modal-field') || input;
  }
  function toggleEmailAuth(forceOpen) {
    var box = document.getElementById('cv-email-signin');
    var btn = document.getElementById('cv-use-email-btn');
    if (!box) return;
    var open = forceOpen === true ? true : forceOpen === false ? false : box.hidden;
    box.hidden = !open;
    if (btn) btn.textContent = open ? 'Hide email' : 'Use email';
  }
  function ensureJoinAuthLayout() {
    var panel = document.getElementById('cv-panel-login');
    if (!panel) return;
    ensureJoinAuthCss();
    if (panel.getAttribute('data-join-layout') === '1') return;
    panel.setAttribute('data-join-layout', '1');

    var err = document.getElementById('cv-login-err');
    var ageLab = ageCheckLabel();
    var google = document.getElementById('cv-google-login');
    var divider = panel.querySelector('.conv-modal-divider');
    var guest = document.getElementById('cv-guest-login');
    var emailIn = document.getElementById('cv-login-email');
    var pwIn = document.getElementById('cv-login-pw');
    var loginBtn = document.getElementById('cv-login-btn');

    var emailBox = document.getElementById('cv-email-signin');
    if (!emailBox) {
      emailBox = document.createElement('div');
      emailBox.id = 'cv-email-signin';
      emailBox.className = 'cv-email-signin';
    }
    emailBox.hidden = true;

    var emailField = fieldWrap(emailIn);
    var pwField = fieldWrap(pwIn);
    if (emailField && emailField.parentNode !== emailBox) emailBox.appendChild(emailField);
    if (pwField && pwField.parentNode !== emailBox) emailBox.appendChild(pwField);
    if (loginBtn && loginBtn.parentNode !== emailBox) emailBox.appendChild(loginBtn);

    var gotoReg = document.getElementById('cv-goto-register');
    if (!gotoReg) {
      gotoReg = document.createElement('button');
      gotoReg.id = 'cv-goto-register';
      gotoReg.type = 'button';
      gotoReg.className = 'conv-guest-btn';
      gotoReg.textContent = 'Create an account';
    }
    if (gotoReg.parentNode !== emailBox) emailBox.appendChild(gotoReg);

    var useEmail = document.getElementById('cv-use-email-btn');
    if (!useEmail) {
      useEmail = document.createElement('button');
      useEmail.id = 'cv-use-email-btn';
      useEmail.type = 'button';
      useEmail.className = 'conv-email-toggle';
      useEmail.textContent = 'Use email';
    }

    if (divider) divider.textContent = 'or use email';

    [err, ageLab, google, divider, useEmail, emailBox, guest].forEach(function (n) {
      if (n) panel.appendChild(n);
    });

    var reg = document.getElementById('cv-panel-register');
    if (reg && !document.getElementById('cv-goto-join')) {
      var back = document.createElement('button');
      back.id = 'cv-goto-join';
      back.type = 'button';
      back.className = 'conv-guest-btn';
      back.textContent = 'Continue with Google instead';
      var regErr = document.getElementById('cv-reg-err');
      if (regErr && regErr.nextSibling) reg.insertBefore(back, regErr.nextSibling);
      else if (reg.firstChild) reg.insertBefore(back, reg.firstChild);
      else reg.appendChild(back);
    }
  }
  function openAuth(tab) {
    ensureJoinAuthLayout();
    var draft = peekCompose();
    const ov = document.getElementById('cv-auth-overlay');
    if (!ov) return;
    ov.classList.add('open');
    var mode = tab || 'join';
    if (mode === 'login') mode = 'join';
    var tabs = document.querySelector('#cv-auth-overlay .conv-modal-tabs');
    var login = document.getElementById('cv-panel-login');
    var reg = document.getElementById('cv-panel-register');
    document.querySelectorAll('.conv-modal-tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.tab === (mode === 'join' ? 'login' : mode));
    });
    if (tabs) tabs.classList.add('is-join-hidden');
    if (mode === 'register') {
      if (login) login.style.display = 'none';
      if (reg) reg.style.display = '';
    } else {
      if (login) login.style.display = '';
      if (reg) reg.style.display = 'none';
      toggleEmailAuth(false);
    }
    restoreCompose(draft);
    var google = document.getElementById('cv-google-login');
    var closeBtn = document.getElementById('cv-modal-close');
    if (mode !== 'register' && google) {
      try { google.focus(); } catch (e) {}
    } else if (closeBtn) {
      closeBtn.focus();
    }
  }
  function closeAuth() {
    var draft = peekCompose();
    var ov = document.getElementById('cv-auth-overlay');
    if (ov) ov.classList.remove('open');
    restoreCompose(draft);
  }
  function stubSignIn(name, handle) {
    var draft = peekCompose();
    currentUser = {
      name: name || 'Guest',
      handle: (handle || 'guest311').replace(/^@/, '').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'guest311',
      bio: "Unofficial helper — not a substitute for 911.",
      live: false
    };
    saveJSON(LS_USER, currentUser);
    closeAuth();
    renderSidebarAuth();
    hideDummyChrome();
    syncChatChrome();
    syncProfile();
    restoreCompose(draft);
  }
  function signOut() {
    listenMemberNests(null);
    if (fbAuth && fbAuth.currentUser) fbAuth.signOut();
    currentUser = null;
    saveJSON(LS_USER, null);
    renderSidebarAuth();
    hideDummyChrome();
    teardownDms();
    listenConversations();
    syncProfile();
    renderFeed();
  }

  function syncPostBtn() {
    const input = document.getElementById('thoughts-compose-input');
    const text = (input && input.value || '').trim();
    const pollReady = pollActive && [...document.querySelectorAll('#compose-poll .compose-poll-input')].filter(function (i) { return i.value.trim(); }).length >= 2;
    const btn = document.getElementById('thoughts-post-btn');
    if (btn) btn.disabled = !(text || attachedFile || pollReady);
  }

  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  function isVideoFile(file) {
    var t = (file.type || '').toLowerCase();
    if (t.indexOf('video/') === 0) return true;
    return /\.(mp4|mov|m4v|webm|avi|mkv)$/i.test(file.name || '');
  }
  function isProbablyImage(file) {
    var t = (file.type || '').toLowerCase();
    if (t.indexOf('image/') === 0) return true;
    if (isVideoFile(file)) return false;
    return /\.(jpe?g|png|gif|webp|heic|heif|bmp)$/i.test(file.name || '');
  }
  function showAttachedImage(file) {
    attachedFile = file;
    var img = document.getElementById('compose-preview-img');
    var box = document.getElementById('compose-image-preview');
    if (previewObjectUrl) {
      try { URL.revokeObjectURL(previewObjectUrl); } catch (e) {}
      previewObjectUrl = null;
    }
    previewObjectUrl = URL.createObjectURL(file);
    if (img) {
      img.alt = '';
      img.src = previewObjectUrl;
    }
    if (box) box.hidden = false;
    syncPostBtn();
  }
  function loadImageElement(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('Could not read that image. Try JPEG or PNG.'));
      };
      img.src = url;
    });
  }
  function jpegFromImage(img, maxEdge, quality) {
    var w = img.naturalWidth || img.width;
    var h = img.naturalHeight || img.height;
    if (!w || !h) return Promise.reject(new Error('Could not read that image.'));
    var scale = Math.min(1, maxEdge / Math.max(w, h));
    var cw = Math.max(1, Math.round(w * scale));
    var ch = Math.max(1, Math.round(h * scale));
    var canvas = document.createElement('canvas');
    canvas.width = cw;
    canvas.height = ch;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, cw, ch);
    ctx.drawImage(img, 0, 0, cw, ch);
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (!blob) { reject(new Error('Could not shrink that image.')); return; }
        resolve(new File([blob], 'photo.jpg', { type: 'image/jpeg' }));
      }, 'image/jpeg', quality);
    });
  }
  function fitImageUnderLimit(file) {
    var readyTypes = { 'image/jpeg': 1, 'image/png': 1, 'image/gif': 1, 'image/webp': 1 };
    if (file.size <= MAX_IMAGE_BYTES && file.type && readyTypes[file.type]) {
      return Promise.resolve(file);
    }
    return loadImageElement(file).then(function (img) {
      var edge = 1920;
      var q = 0.82;
      function attempt() {
        return jpegFromImage(img, edge, q).then(function (out) {
          if (out.size <= MAX_IMAGE_BYTES) return out;
          if (q > 0.5) { q = Math.round((q - 0.12) * 100) / 100; return attempt(); }
          if (edge > 640) { edge = Math.round(edge * 0.7); q = 0.74; return attempt(); }
          return Promise.reject(new Error('Could not get that photo under 5 MB.'));
        });
      }
      return attempt();
    });
  }
  function setImagePreview(file) {
    if (!file) return;
    if (isVideoFile(file)) {
      composeErr('Images only. No video yet.');
      return;
    }
    if (!isProbablyImage(file)) {
      composeErr('Images only. No video.');
      return;
    }
    composeErr(file.size > MAX_IMAGE_BYTES ? 'Shrinking photo…' : '');
    fitImageUnderLimit(file).then(function (ready) {
      composeErr('');
      showAttachedImage(ready);
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not attach that photo.');
    });
  }

  function uploadImage(file, uid) {
    if (!fbStorage) return Promise.reject(new Error('Storage not ready'));
    const ext = (file.name.split('.').pop() || 'jpg').toLowerCase().replace(/[^a-z0-9]/g, '') || 'jpg';
    const path = 'posts/' + SITE_ID + '/' + uid + '/' + Date.now() + '.' + ext;
    const ref = fbStorage.ref(path);
    const bar = document.getElementById('compose-upload-bar');
    const fill = document.getElementById('compose-upload-fill');
    if (bar) bar.hidden = false;
    if (fill) fill.style.width = '0%';
    return new Promise(function (resolve, reject) {
      const task = ref.put(file, { contentType: file.type || 'image/jpeg' });
      task.on('state_changed',
        function (snap) { if (fill) fill.style.width = (snap.bytesTransferred / snap.totalBytes * 100) + '%'; },
        function (err) { if (bar) bar.hidden = true; reject(err); },
        function () { if (bar) bar.hidden = true; task.snapshot.ref.getDownloadURL().then(resolve).catch(reject); }
      );
    });
  }

  function resetComposeExtras() {
    attachedFile = null;
    pollActive = false;
    var preview = document.getElementById('compose-image-preview');
    if (preview) preview.hidden = true;
    var img = document.getElementById('compose-preview-img');
    if (img) img.src = '';
    var imgIn = document.getElementById('compose-image-input');
    if (imgIn) imgIn.value = '';
    var gifIn = document.getElementById('compose-gif-input');
    if (gifIn) gifIn.value = '';
    var poll = document.getElementById('compose-poll');
    if (poll) {
      poll.hidden = true;
      var opts = poll.querySelectorAll('.compose-poll-option');
      opts.forEach(function (el, i) {
        if (i < 2) {
          var inp = el.querySelector('.compose-poll-input');
          if (inp) inp.value = '';
        } else el.remove();
      });
    }
    var dur = document.getElementById('compose-poll-duration');
    if (dur) dur.value = '3';
    var pollBtn = document.getElementById('compose-btn-poll');
    if (pollBtn) pollBtn.style.color = '';
    var wrap2 = document.getElementById('compose-emoji-wrap');
    if (wrap2) wrap2.remove();
    if (previewObjectUrl) {
      try { URL.revokeObjectURL(previewObjectUrl); } catch (e) {}
      previewObjectUrl = null;
    }
  }

  function maybePost() {
    const input = document.getElementById('thoughts-compose-input');
    const text = (input.value || '').trim();
    const pollReady = pollActive && [...document.querySelectorAll('#compose-poll .compose-poll-input')].filter(function (i) { return i.value.trim(); }).length >= 2;
    if (!(text || attachedFile || pollReady)) return;
    const live = fbAuth && fbAuth.currentUser;
    if (!live) { composeErr('Sign in to post. Guest can only browse.'); openAuth('join'); return; }
    if (!requireVerified('post')) return;
    if (!fbDb) { composeErr('Feed is not connected.'); return; }
    const parentId = replyTo;
    replyTo = null;
    composeErr('');
    const btn = document.getElementById('thoughts-post-btn');
    btn.disabled = true;
    const start = attachedFile ? uploadImage(attachedFile, live.uid) : Promise.resolve(null);
    start.then(function (imageUrl) {
      const disp = (currentUser && currentUser.name) || live.displayName || (live.email || 'member').split('@')[0] || 'Member';
      const handle = (currentUser && currentUser.handle) || String(disp).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
      const doc = {
        siteId: SITE_ID,
        parentId: parentId,
        authorUid: live.uid,
        authorName: disp,
        authorHandle: handle,
        text: text.slice(0, 280),
        likes: {},
        likeCount: 0,
        replyCount: 0,
        nestSlug: postNestSlug(parentId),
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      };
      if (imageUrl) doc.imageUrl = imageUrl;
      if (pollActive) {
        const opts = [...document.querySelectorAll('#compose-poll .compose-poll-input')].map(function (i) { return i.value.trim(); }).filter(Boolean);
        if (opts.length >= 2) {
          const duration = parseInt(document.getElementById('compose-poll-duration').value, 10) || 3;
          doc.poll = {
            options: opts,
            votes: {},
            duration: duration,
            endsAt: firebase.firestore.Timestamp.fromMillis(Date.now() + duration * 86400000)
          };
        }
      }
      return fbDb.collection('posts').add(doc);
    }).then(function () {
      input.value = '';
      input.placeholder = input.getAttribute('data-ph') || input.placeholder;
      resetComposeExtras();
      syncPostBtn();
      if (parentId) {
        fbDb.collection('posts').doc(parentId).update({
          replyCount: firebase.firestore.FieldValue.increment(1)
        }).catch(function (e) {
          composeErr((e && e.message) ? ('Posted, but reply count did not update: ' + e.message) : 'Posted, but reply count did not update.');
        });
      }
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not post.');
      console.warn('post', e);
      syncPostBtn();
    });
  }

  function deleteOwnPost(id) {
    var post = findPost(id);
    if (!post) return;
    var uid = liveUid();
    if (!uid || post.authorUid !== uid) {
      composeErr('You can only delete your own posts.');
      return;
    }
    if (!fbDb) { composeErr('Feed is not connected.'); return; }
    composeErr('');
    var chain = Promise.resolve();
    if (post.imageUrl && fbStorage) {
      chain = fbStorage.refFromURL(post.imageUrl).delete().catch(function (e) {
        console.warn('storage delete', e);
      });
    }
    chain.then(function () {
      return fbDb.collection('posts').doc(id).delete();
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not delete post.');
    });
  }

  function votePoll(postId, idx) {
    var uid = liveUid();
    if (!requireVerified('vote')) return;
    if (!uid) {
      composeErr('Sign in to vote. Guest cannot vote.');
      openAuth('join');
      return;
    }
    if (!fbDb || !postId) return;
    var patch = {};
    patch['poll.votes.' + uid] = idx;
    fbDb.collection('posts').doc(postId).update(patch).catch(function (err) {
      composeErr((err && err.message) ? ('Vote: ' + err.message) : 'Could not save vote.');
      console.warn('poll vote', err);
    });
  }

  function toggleLike(postId) {
    var uid = liveUid();
    if (!requireVerified('like')) return;
    if (!uid) {
      composeErr('Sign in to like. Guest cannot like.');
      openAuth('join');
      return;
    }
    if (!fbDb || !postId) return;
    var post = findPost(postId);
    var likedBy = (post && post.likedBy) || {};
    var patch = {};
    if (likedBy[uid]) {
      patch['likes.' + uid] = firebase.firestore.FieldValue.delete();
    } else {
      patch['likes.' + uid] = true;
    }
    fbDb.collection('posts').doc(postId).update(patch).catch(function (err) {
      composeErr((err && err.message) ? ('Like: ' + err.message) : 'Could not save like.');
      console.warn('like', err);
    });
  }

  function wireComposeToolbar() {
    var imgBtn = document.getElementById('compose-btn-image');
    var gifBtn = document.getElementById('compose-btn-gif');
    var imgIn = document.getElementById('compose-image-input');
    var gifIn = document.getElementById('compose-gif-input');
    if (imgBtn && imgIn) imgBtn.addEventListener('click', function () { imgIn.click(); });
    if (gifBtn && gifIn) gifBtn.addEventListener('click', function () { gifIn.click(); });
    if (imgIn) imgIn.addEventListener('change', function (e) { if (e.target.files[0]) setImagePreview(e.target.files[0]); });
    if (gifIn) gifIn.addEventListener('change', function (e) { if (e.target.files[0]) setImagePreview(e.target.files[0]); });
    var remove = document.getElementById('compose-image-remove');
    if (remove) remove.addEventListener('click', function () {
      attachedFile = null;
      document.getElementById('compose-image-preview').hidden = true;
      document.getElementById('compose-preview-img').src = '';
      document.getElementById('compose-preview-img').alt = '';
      if (previewObjectUrl) {
        try { URL.revokeObjectURL(previewObjectUrl); } catch (e2) {}
        previewObjectUrl = null;
      }
      if (imgIn) imgIn.value = '';
      if (gifIn) gifIn.value = '';
      syncPostBtn();
    });
    var wrap = document.getElementById('thoughts-compose-wrap');
    if (wrap) {
      wrap.addEventListener('dragover', function (e) { e.preventDefault(); wrap.classList.add('drag-over'); });
      wrap.addEventListener('dragleave', function () { wrap.classList.remove('drag-over'); });
      wrap.addEventListener('drop', function (e) {
        e.preventDefault(); wrap.classList.remove('drag-over');
        var files = e.dataTransfer && e.dataTransfer.files;
        if (!files) return;
        for (var i = 0; i < files.length; i++) {
          if (files[i].type && files[i].type.indexOf('image/') === 0) { setImagePreview(files[i]); break; }
        }
      });
    }

    function takeClipboardImage(e) {
      var cd = e.clipboardData || (e.originalEvent && e.originalEvent.clipboardData);
      if (!cd) return false;
      var items = cd.items;
      if (items && items.length) {
        for (var i = 0; i < items.length; i++) {
          var it = items[i];
          if (it && it.kind === 'file' && it.type && it.type.indexOf('image/') === 0) {
            var f = it.getAsFile();
            if (f) { setImagePreview(f); return true; }
          }
        }
      }
      var files = cd.files;
      if (files && files.length) {
        for (var j = 0; j < files.length; j++) {
          if (files[j] && files[j].type && files[j].type.indexOf('image/') === 0) {
            setImagePreview(files[j]);
            return true;
          }
        }
      }
      return false;
    }
    function onComposePaste(e) {
      if (takeClipboardImage(e)) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
    if (wrap) wrap.addEventListener('paste', onComposePaste, true);

    var pollPanel = document.getElementById('compose-poll');
    var pollBtn = document.getElementById('compose-btn-poll');
    if (pollBtn && pollPanel) {
      pollBtn.addEventListener('click', function () {
        pollActive = !pollActive;
        pollPanel.hidden = !pollActive;
        pollBtn.style.color = pollActive ? 'var(--accent)' : '';
        syncPostBtn();
      });
    }
    var pollAdd = document.getElementById('compose-poll-add');
    if (pollAdd && pollPanel) {
      pollAdd.addEventListener('click', function () {
        var options = pollPanel.querySelectorAll('.compose-poll-option');
        if (options.length >= 4) return;
        var idx = options.length;
        var div = document.createElement('div');
        div.className = 'compose-poll-option';
        div.innerHTML = '<input class="compose-poll-input" placeholder="Choice ' + (idx + 1) + '" maxlength="60" data-poll-opt="' + idx + '"><button type="button" class="compose-poll-remove" title="Remove">×</button>';
        var rm = div.querySelector('.compose-poll-remove');
        if (rm) rm.addEventListener('click', function () { div.remove(); syncPostBtn(); });
        pollPanel.querySelector('.compose-poll-footer').before(div);
        syncPostBtn();
      });
    }
    if (pollPanel) pollPanel.addEventListener('input', syncPostBtn);
    var emojiBtn = document.getElementById('compose-btn-emoji');
    if (emojiBtn) emojiBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var wrap2 = document.getElementById('compose-emoji-wrap');
      if (wrap2) { wrap2.remove(); return; }
      wrap2 = document.createElement('div');
      wrap2.id = 'compose-emoji-wrap';
      wrap2.className = 'compose-emoji-wrap';
      var picker = document.createElement('emoji-picker');
      wrap2.appendChild(picker);
      document.body.appendChild(wrap2);
      var btnRect = e.currentTarget.getBoundingClientRect();
      wrap2.style.top = (btnRect.top - 315) + 'px';
      wrap2.style.left = Math.max(4, btnRect.left - 120) + 'px';
      var composeInput = document.getElementById('thoughts-compose-input');
      picker.addEventListener('emoji-click', function (ev) {
        var em = ev.detail.unicode;
        var pos = composeInput.selectionStart || composeInput.value.length;
        composeInput.value = composeInput.value.slice(0, pos) + em + composeInput.value.slice(pos);
        composeInput.dispatchEvent(new Event('input'));
        composeInput.focus();
        wrap2.remove();
      });
      var close = function (ev) {
        if (!wrap2.contains(ev.target) && ev.target !== e.currentTarget) {
          wrap2.remove();
          document.removeEventListener('click', close);
        }
      };
      setTimeout(function () { document.addEventListener('click', close); }, 20);
    });
  }

  function wireEvents() {
    document.addEventListener('click', function (e) {
      if (e.target.closest('#nav-nest-add')) {
        e.preventDefault();
        if (!isLiveUser()) { openAuth('join'); return; }
        var form = document.getElementById('nav-nest-form');
        if (!form) return;
        if (!form.hidden) { hideNestAddForm(); return; }
        form.hidden = false;
        nestAddSlugDirty = false;
        var nestLabel = document.getElementById('nest-add-label');
        var nestSlugInput = document.getElementById('nest-add-slug');
        var nestErr = document.getElementById('nest-add-err');
        if (nestLabel) nestLabel.value = '';
        if (nestSlugInput) nestSlugInput.value = '';
        if (nestErr) nestErr.textContent = '';
        if (nestLabel) nestLabel.focus();
        return;
      }
      if (e.target.closest('#nest-add-save')) {
        e.preventDefault();
        submitNestAdd();
        return;
      }
      const nestLink = e.target.closest('a[data-nest]');
      if (nestLink) {
        e.preventDefault();
        goNest(nestLink.getAttribute('data-nest'));
        return;
      }
      const social = e.target.closest('[data-social]');
      if (social) {
        e.preventDefault();
        go(social.dataset.social);
        return;
      }
      if (e.target.closest('#auth-signin') || e.target.closest('#profile-signin-prompt-btn')) {
        openAuth('join');
        return;
      }
      if (e.target.closest('#cv-use-email-btn')) {
        toggleEmailAuth();
        return;
      }
      if (e.target.closest('#cv-goto-register')) {
        openAuth('register');
        return;
      }
      if (e.target.closest('#cv-goto-join')) {
        openAuth('join');
        return;
      }
      if (e.target.closest('#auth-signout')) { signOut(); return; }

      if (e.target.closest('#profile-message-btn')) {
        if (!dmsOn()) return;
        if (!isLiveUser()) { openAuth('join'); return; }
        if (viewingProfile && viewingProfile.uid) startDm(viewingProfile.uid, viewingProfile.name);
        return;
      }
      const profileWho = e.target.closest('[data-profile-uid]');
      if (profileWho && dmsOn() && !e.target.closest('[data-act]')) {
        e.preventDefault();
        openUserProfile(
          profileWho.getAttribute('data-profile-uid'),
          profileWho.getAttribute('data-profile-name'),
          profileWho.getAttribute('data-profile-handle')
        );
        return;
      }
      const threadItem = e.target.closest('[data-cid]');
      if (threadItem && dmsOn()) {
        var opened = findConv(threadItem.getAttribute('data-cid'));
        pendingPeer = opened ? { uid: convPeerUid(opened), name: convPeerName(opened) } : pendingPeer;
        openThread(threadItem.getAttribute('data-cid'));
        return;
      }
      const pickItem = e.target.closest('[data-pick-uid]');
      if (pickItem) {
        hideDmPicker();
        startDm(pickItem.getAttribute('data-pick-uid'), pickItem.getAttribute('data-pick-name'));
        return;
      }
      if (e.target.closest('#chat-picker-close')) {
        hideDmPicker();
        return;
      }

      const porchBtn = e.target.closest('[data-porch]');
      if (porchBtn) {
        e.preventDefault();
        porchPick(porchBtn.getAttribute('data-porch'));
        return;
      }

      const pollOpt = e.target.closest('[data-poll-idx]');
      if (pollOpt) {
        votePoll(pollOpt.dataset.postId, parseInt(pollOpt.dataset.pollIdx, 10));
        return;
      }

      const tab = e.target.closest('[data-thoughts-tab]');
      if (tab) {
        const t = tab.dataset.thoughtsTab;
        if (t === 'following') go('following');
        else if (t === 'hot') go('hot');
        else if (t === 'new') go('new');
        else goRoom();
        return;
      }

      const likeBtn = e.target.closest('[data-act="like"]');
      if (likeBtn) {
        const post = likeBtn.closest('[data-post-id]');
        if (!post) return;
        toggleLike(post.dataset.postId);
        return;
      }
      if (e.target.closest('[data-act="delete"]')) {
        const post = e.target.closest('[data-post-id]');
        if (!post) return;
        deleteOwnPost(post.dataset.postId);
        return;
      }
      if (e.target.closest('[data-act="reply"]')) {
        if (!isLiveUser()) { composeErr('Sign in to reply. Guest can only browse.'); openAuth('join'); return; }
        const post = e.target.closest('[data-post-id]');
        if (!post) return;
        replyTo = post.dataset.parentId || post.dataset.postId;
        const input = document.getElementById('thoughts-compose-input');
        if (!input.getAttribute('data-ph')) input.setAttribute('data-ph', input.placeholder);
        input.placeholder = 'Reply to this post…';
        input.focus();
        return;
      }
      if (e.target.closest('[data-act="share"]')) {
        const post = e.target.closest('[data-post-id]');
        if (!post) return;
        sharePost(post.dataset.postId);
        return;
      }
      if (e.target.closest('[data-act="report"]')) {
        const post = e.target.closest('[data-post-id]');
        if (!post) return;
        reportPost(post.dataset.postId);
        return;
      }
      if (e.target.closest('[data-act="block"]')) {
        const post = e.target.closest('[data-post-id]');
        if (!post) return;
        const p = findPost(post.dataset.postId);
        if (p && p.authorUid) blockUser(p.authorUid);
        return;
      }

      const etab = e.target.closest('[data-explore-tab]');
      if (etab) {
        document.querySelectorAll('[data-explore-tab]').forEach(function (t) {
          t.classList.toggle('active', t === etab);
        });
        var which = etab.dataset.exploreTab;
        document.querySelectorAll('.explore-pane').forEach(function (p) {
          p.classList.toggle('active', p.id === 'explore-pane-' + which);
        });
        return;
      }

      if (isMobileNav() && document.body.classList.contains('nav-open')
          && sidebar && !sidebar.contains(e.target) && hamburger && !hamburger.contains(e.target)) {
        closeMobileNav();
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var nestForm = document.getElementById('nav-nest-form');
      if (nestForm && !nestForm.hidden) { e.preventDefault(); hideNestAddForm(); return; }
      if (closeStoriesViewer()) { e.preventDefault(); return; }
      if (closeStoriesComposer()) { e.preventDefault(); return; }
      const picker = document.getElementById('chat-user-picker');
      if (picker && !picker.hidden) { e.preventDefault(); hideDmPicker(); return; }
      const shareOv = document.getElementById('share-sheet');
      if (shareOv && !shareOv.hidden) { e.preventDefault(); closeShareSheet(); return; }
      const ov = document.getElementById('cv-auth-overlay');
      if (ov && ov.classList.contains('open')) { e.preventDefault(); closeAuth(); return; }
      if (isMobileNav() && document.body.classList.contains('nav-open')) closeMobileNav();
    });

    hamburger.addEventListener('click', function () {
      if (isMobileNav()) document.body.classList.toggle('nav-open');
      else document.body.classList.toggle('nav-collapsed');
      syncHamburgerAria();
    });
    window.addEventListener('resize', syncHamburgerAria);
    document.getElementById('nav-overlay').addEventListener('click', closeMobileNav);
    document.getElementById('right-panel-tab').addEventListener('click', function () {
      document.body.classList.toggle('right-collapsed');
    });
    document.getElementById('sidebar-search-btn').addEventListener('click', function () { go('explore'); });
    document.getElementById('sidebar-post-btn').addEventListener('click', function () {
      goRoom();
      setTimeout(function () {
        const input = document.getElementById('thoughts-compose-input');
        if (input) { input.focus(); input.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      }, 120);
    });

    ['profile-back', 'notif-back', 'explore-back'].forEach(function (id) {
      document.getElementById(id).addEventListener('click', function () { goRoom(); });
    });
    var markRead = document.getElementById('notif-mark-read');
    if (markRead) markRead.addEventListener('click', function () { /* soon: no live notifs */ });

    var chatNew = document.getElementById('chat-new-btn');
    if (chatNew) chatNew.addEventListener('click', onChatNew);
    var chatPlaceholderNew = document.getElementById('chat-placeholder-new');
    if (chatPlaceholderNew) chatPlaceholderNew.addEventListener('click', onChatNew);
    var chatSend = document.getElementById('chat-send-btn');
    if (chatSend) chatSend.addEventListener('click', sendDm);
    var chatInput = document.getElementById('chat-compose-input');
    if (chatInput) {
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendDm();
        }
      });
    }
    var chatSearch = document.getElementById('chat-search-input');
    if (chatSearch) chatSearch.addEventListener('input', renderThreads);

    document.getElementById('profile-edit-btn').addEventListener('click', function () {
      openAuth('register');
    });

    const compose = document.getElementById('thoughts-compose-input');
    const postBtn = document.getElementById('thoughts-post-btn');
    compose.addEventListener('input', function () {
      compose.style.height = 'auto';
      compose.style.height = Math.min(compose.scrollHeight, 200) + 'px';
      syncPostBtn();
    });
    postBtn.addEventListener('click', maybePost);
    wireComposeToolbar();

    document.getElementById('cv-modal-close').addEventListener('click', function (e) {
      e.preventDefault();
      closeAuth();
    });
    document.getElementById('cv-auth-overlay').addEventListener('click', function (e) {
      if (e.target.id === 'cv-auth-overlay') closeAuth();
    });
    document.querySelectorAll('.conv-modal-tab').forEach(function (t) {
      t.addEventListener('click', function () { openAuth(t.dataset.tab); });
    });
    document.getElementById('cv-login-btn').addEventListener('click', function () {
      const err = document.getElementById('cv-login-err');
      runWithAuth(err, function () {
        const email = (document.getElementById('cv-login-email').value || '').trim();
        const pw = document.getElementById('cv-login-pw').value || '';
        err.textContent = '';
        markAuthLand();
        fbAuth.signInWithEmailAndPassword(email, pw).catch(function (e) {
          err.textContent = (e && e.message) ? e.message : 'Sign-in failed.';
          err.classList.add('show');
        });
      });
    });
    document.getElementById('cv-reg-btn').addEventListener('click', function () {
      const err = document.getElementById('cv-reg-err');
      runWithAuth(err, function () {
        const name = (document.getElementById('cv-reg-name').value || '').trim();
        const email = (document.getElementById('cv-reg-email').value || '').trim();
        const pw = document.getElementById('cv-reg-pw').value || '';
        const age = document.getElementById('cv-reg-age');
        if (!age || !age.checked) {
          err.textContent = 'Confirm you are 13 or older and agree to the preview Terms and Privacy pages.';
          err.classList.add('show');
          return;
        }
        if (!email || pw.length < 6) { err.textContent = 'Email and a password of at least 6 characters.'; err.classList.add('show'); return; }
        err.textContent = '';
        markAuthLand();
        fbAuth.createUserWithEmailAndPassword(email, pw).then(function (cred) {
          const disp = name || email.split('@')[0];
          cred.user.sendEmailVerification().catch(function () {});
          return cred.user.updateProfile({ displayName: disp }).then(function () {
            if (fbDb) {
              return fbDb.collection('users').doc(cred.user.uid).set({
                displayName: disp,
                              siteId: SITE_ID,
                createdAt: firebase.firestore.FieldValue.serverTimestamp()
              }, { merge: true });
            }
          }).then(function () {
            composeErr('Account created. Verify your email before posting.');
          });
        }).catch(function (e) {
          err.textContent = (e && e.message) ? e.message : 'Could not create account.';
          err.classList.add('show');
        });
      });
    });
    document.getElementById('cv-google-login').addEventListener('click', function () {
      var err = document.getElementById('cv-login-err');
      runWithAuth(err, function () {
      var age = document.getElementById('cv-google-age');
      if (!age || !age.checked) {
        err.textContent = 'Confirm you are 13 or older and agree to the preview Terms and Privacy pages.';
        err.classList.add('show');
        return;
      }
      err.textContent = '';
      err.classList.remove('show');
      markAuthLand();
      var provider = new firebase.auth.GoogleAuthProvider();
      var ua = navigator.userAgent || '';
      var isiOS = /iP(hone|od|ad)/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      var isSafari = /Safari/i.test(ua) && !/Chrome|CriOS|FxiOS|Android/i.test(ua);
      function finishGoogle(cred) {
        var u = cred && cred.user;
        if (fbDb && u) {
          var disp = u.displayName || (u.email || 'member').split('@')[0];
          return fbDb.collection('users').doc(u.uid).set({
            displayName: disp,
            siteId: SITE_ID,
            provider: 'google',
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
          }, { merge: true });
        }
      }
      function failGoogle(e) {
        var msg;
        if (e && e.code === 'auth/operation-not-allowed') {
          msg = 'Google is not enabled on subx-skins yet.';
        } else if (e && e.code === 'auth/popup-closed-by-user') {
          msg = 'Google sign-in cancelled.';
        } else {
          msg = (e && e.message) ? e.message : 'Google sign-in failed.';
        }
        err.textContent = msg;
        err.classList.add('show');
      }
      if (isiOS || isSafari) {
        fbAuth.signInWithRedirect(provider).catch(failGoogle);
      } else {
        fbAuth.signInWithPopup(provider).then(finishGoogle).catch(function (e) {
          if (e && (e.code === 'auth/popup-blocked' || e.code === 'auth/cancelled-popup-request')) {
            return fbAuth.signInWithRedirect(provider);
          }
          failGoogle(e);
        });
      }
      });
    });
    document.getElementById('cv-guest-login').addEventListener('click', function () { stubSignIn('Guest', 'guest'); });

    const search = document.getElementById('explore-search-input');
    search.addEventListener('input', function () {
      const q = search.value.trim().toLowerCase();
      function filt(list) {
        if (!q) return list;
        return list.filter(function (c) {
          return (c.title + ' ' + c.snippet + ' ' + c.tag).toLowerCase().indexOf(q) !== -1;
        });
      }
      function cards(list) {
        if (!list.length) return '<p class="empty-note">Nothing in this room matched that.</p>';
        return list.map(function (c) {
          return '<article class="explore-card"><div class="explore-card-tag">' + escapeHtml(c.tag) +
            '</div><div class="explore-card-title">' + escapeHtml(c.title) +
            '</div><div class="explore-card-snippet">' + escapeHtml(c.snippet) + '</div></article>';
        }).join('');
      }
      var seats = nestSeatCards();
      document.getElementById('explore-pane-places').innerHTML = cards(filt(seats.length ? seats : PLACES));
      document.getElementById('explore-pane-topics').innerHTML = cards(filt(TOPICS));
      ensureExploreNestTab();
      var nestPane = document.getElementById('explore-pane-nests');
      if (nestPane) fillExploreNests(nestPane, filt(nestExploreCards()));
    });
  }

  var STORIES_TTL_MS = 24 * 60 * 60 * 1000;
  var STORIES_PER_DAY = 6;
  var STORIES_TEXT_MAX = 280;
  var STORIES_CAPTION_MAX = 140;
  var liveStories = [];
  var storiesUnsub = null;
  var storiesWired = false;
  var storiesDebugOwnUid = '';
  var storyFile = null;
  var storyFileUrl = null;
  var storyType = 'text';
  var storyViewerList = [];
  var storyViewerIdx = 0;
  var storyViewerTimer = null;
  var storyViewerPrevFocus = null;
  var storyViewerOnKey = null;

  function storiesCfg() {
    return (site && site.stories) || {};
  }
  function storiesOn() {
    return !!(storiesCfg().enabled);
  }
  function storiesComposePlaceholder() {
    return (site && site.composePlaceholder) || "Species note, myth bust, or story?";
  }
  function storiesMaxBytes() {
    var n = parseInt(storiesCfg().maxBytes, 10);
    return n > 0 ? n : 8000000;
  }
  function storiesMaxSeconds() {
    var n = parseInt(storiesCfg().maxSeconds, 10);
    return n > 0 ? n : 15;
  }
  function storiesReduceMotion() {
    try {
      return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    } catch (e) { return false; }
  }
  function storiesLocalHost() {
    var h = (location.hostname || '').toLowerCase();
    return h === 'localhost' || h === '127.0.0.1';
  }
  function storiesSeenKey() {
    return 'subx.storiesSeen.' + (SITE_ID || '');
  }
  function storiesSeenMap() {
    try { return JSON.parse(sessionStorage.getItem(storiesSeenKey()) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function markStoriesSeen(ids) {
    var map = storiesSeenMap();
    (ids || []).forEach(function (id) { if (id) map[id] = 1; });
    try { sessionStorage.setItem(storiesSeenKey(), JSON.stringify(map)); } catch (e) { /* private mode */ }
  }
  function groupHasUnseen(stories) {
    var seen = storiesSeenMap();
    return (stories || []).some(function (s) { return !seen[s.id]; });
  }
  function storiesQuotaKey() {
    var d = new Date();
    var day = d.getUTCFullYear() + '-' + (d.getUTCMonth() + 1) + '-' + d.getUTCDate();
    return 'subx.storiesQuota.' + (SITE_ID || '') + '.' + (liveUid() || 'x') + '.' + day;
  }
  function storiesPostedToday() {
    try { return parseInt(localStorage.getItem(storiesQuotaKey()) || '0', 10) || 0; }
    catch (e) { return 0; }
  }
  function bumpStoriesQuota() {
    try { localStorage.setItem(storiesQuotaKey(), String(storiesPostedToday() + 1)); }
    catch (e) { /* private mode */ }
  }
  function findStory(id) {
    for (var i = 0; i < liveStories.length; i++) if (liveStories[i].id === id) return liveStories[i];
    return null;
  }
  function mapStory(doc) {
    var d = doc.data() || {};
    var uid = d.authorUid || '';
    var created = d.createdAt && d.createdAt.toMillis ? d.createdAt.toMillis() : Date.now();
    var exp = d.expiresAt && d.expiresAt.toMillis ? d.expiresAt.toMillis() : (created + STORIES_TTL_MS);
    return {
      id: doc.id,
      siteId: d.siteId || '',
      authorUid: uid,
      name: humanName(d, uid),
      handle: humanHandle(d, uid),
      type: d.type || 'text',
      text: d.text || '',
      mediaUrl: d.mediaUrl || '',
      mediaContentType: d.mediaContentType || '',
      posterUrl: d.posterUrl || d.thumbUrl || '',
      ms: created,
      expiresAtMs: exp,
      likeCount: d.likeCount || 0,
      likedBy: d.likes || {}
    };
  }
  function latestStory(stories) {
    return (stories && stories.length) ? stories[stories.length - 1] : null;
  }
  function storyIsVideo(story) {
    if (!story) return false;
    if (story.type === 'video') return true;
    return (story.mediaContentType || '').indexOf('video/') === 0;
  }
  function storyIsImage(story) {
    if (!story) return false;
    if (story.type === 'image') return true;
    return (story.mediaContentType || '').indexOf('image/') === 0;
  }
  function storyPosterUrl(story) {
    if (!story) return '';
    return story.posterUrl || story.thumbUrl || '';
  }
  function storyTrayAvatarHtml(story, fallbackName, fallbackHandle) {
    var name = (story && story.name) || fallbackName || 'Me';
    var handle = (story && story.handle) || fallbackHandle || 'me';
    var label = escapeHtml(initials(name));
    var bg = colorFor(handle);
    var url = story && story.mediaUrl;
    var poster = storyPosterUrl(story);
    var mediaSrc = poster || url;
    if (mediaSrc && (storyIsImage(story) || storyIsVideo(story) || poster)) {
      var inner;
      if (storyIsVideo(story) && !poster) {
        inner = '<video class="stories-avatar-media" src="' + escapeHtml(url) +
          '" muted playsinline preload="metadata" aria-hidden="true"></video>';
      } else {
        inner = '<img class="stories-avatar-media" src="' + escapeHtml(mediaSrc) +
          '" alt="" aria-hidden="true">';
      }
      return '<span class="stories-avatar is-media" style="background:' + bg + '">' +
        label + inner + '</span>';
    }
    return '<span class="stories-avatar" style="background:' + bg + '">' + label + '</span>';
  }
  function primeStoryTrayThumbs(root) {
    if (!root) return;
    root.querySelectorAll('img.stories-avatar-media').forEach(function (img) {
      img.addEventListener('error', function () { img.remove(); });
    });
    root.querySelectorAll('video.stories-avatar-media').forEach(function (v) {
      var paint = function () {
        try {
          if (v.readyState < 1) return;
          var t = 0.05;
          if (isFinite(v.duration) && v.duration > 0.25) t = Math.min(0.15, v.duration * 0.08);
          if (Math.abs((v.currentTime || 0) - t) > 0.02) v.currentTime = t;
        } catch (e) {}
      };
      var swapPoster = function () {
        paint();
        var data = '';
        try {
          if (!v.videoWidth) return;
          var c = document.createElement('canvas');
          c.width = 96;
          c.height = 96;
          var ctx = c.getContext('2d');
          if (!ctx) return;
          var side = Math.min(v.videoWidth, v.videoHeight);
          var sx = (v.videoWidth - side) / 2;
          var sy = (v.videoHeight - side) / 2;
          ctx.drawImage(v, sx, sy, side, side, 0, 0, 96, 96);
          data = c.toDataURL('image/jpeg', 0.72);
        } catch (e2) { data = ''; }
        if (data && data.length > 40 && v.parentNode) {
          var img = document.createElement('img');
          img.className = 'stories-avatar-media';
          img.alt = '';
          img.setAttribute('aria-hidden', 'true');
          img.src = data;
          v.parentNode.replaceChild(img, v);
        }
      };
      v.muted = true;
      v.playsInline = true;
      v.addEventListener('loadedmetadata', paint);
      v.addEventListener('loadeddata', swapPoster);
      v.addEventListener('seeked', function onSeek() {
        v.removeEventListener('seeked', onSeek);
        swapPoster();
      });
      v.addEventListener('error', function () { v.remove(); });
      if (v.readyState >= 2) swapPoster();
      else if (v.readyState >= 1) paint();
    });
  }
  function storyGroups() {
    var now = Date.now();
    var byUid = {};
    var order = [];
    liveStories.forEach(function (s) {
      if (s.siteId && s.siteId !== SITE_ID) return;
      if (s.expiresAtMs && s.expiresAtMs <= now) return;
      var uid = s.authorUid || s.id;
      if (!byUid[uid]) {
        byUid[uid] = [];
        order.push(uid);
      }
      byUid[uid].push(s);
    });
    order.forEach(function (uid) {
      byUid[uid].sort(function (a, b) { return (a.ms || 0) - (b.ms || 0); });
    });
    order.sort(function (a, b) {
      var lastA = byUid[a][byUid[a].length - 1].ms || 0;
      var lastB = byUid[b][byUid[b].length - 1].ms || 0;
      return lastB - lastA;
    });
    var me = liveUid() || (storiesLocalHost() ? storiesDebugOwnUid : '');
    if (me && byUid[me]) {
      order = [me].concat(order.filter(function (u) { return u !== me; }));
    }
    return order.map(function (uid) {
      return { uid: uid, stories: byUid[uid] };
    });
  }
  function ensureStoriesTray() {
    var el = document.getElementById('stories-tray');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'stories-tray';
    el.className = 'stories-tray';
    el.setAttribute('role', 'list');
    el.setAttribute('aria-label', 'Stories');
    el.hidden = true;
    var compose = document.getElementById('thoughts-compose-wrap');
    var feed = document.getElementById('thoughts-feed');
    if (compose && compose.parentNode) {
      var after = compose.nextSibling;
      var welcome = document.getElementById('early-welcome');
      if (welcome && welcome.parentNode === compose.parentNode) after = welcome.nextSibling;
      compose.parentNode.insertBefore(el, after);
    } else if (feed && feed.parentNode) {
      feed.parentNode.insertBefore(el, feed);
    } else {
      return el;
    }
    return el;
  }
  function storiesErr(msg) {
    var el = document.getElementById('stories-composer-err');
    if (el) el.textContent = msg || '';
  }
  function revokeStoryFileUrl() {
    if (storyFileUrl) {
      try { URL.revokeObjectURL(storyFileUrl); } catch (e) {}
      storyFileUrl = null;
    }
  }
  function setStoryType(type) {
    storyType = type === 'image' || type === 'video' ? type : 'text';
    document.querySelectorAll('[data-story-type]').forEach(function (btn) {
      btn.classList.toggle('is-on', btn.getAttribute('data-story-type') === storyType);
    });
    var text = document.getElementById('stories-composer-text');
    var caption = document.getElementById('stories-composer-caption');
    var imgIn = document.getElementById('stories-composer-image');
    var vidIn = document.getElementById('stories-composer-video');
    if (text) text.hidden = storyType !== 'text';
    if (caption) caption.hidden = storyType === 'text';
    if (imgIn) imgIn.hidden = storyType !== 'image';
    if (vidIn) vidIn.hidden = storyType !== 'video';
    if (storyType === 'text') {
      storyFile = null;
      revokeStoryFileUrl();
      var prev = document.getElementById('stories-composer-preview');
      if (prev) {
        prev.classList.remove('is-on');
        prev.innerHTML = '';
      }
    }
  }
  function previewStoryFile(file) {
    var prev = document.getElementById('stories-composer-preview');
    if (!prev) return;
    revokeStoryFileUrl();
    storyFileUrl = URL.createObjectURL(file);
    prev.classList.add('is-on');
    if ((file.type || '').indexOf('video/') === 0) {
      prev.innerHTML = '<video src="' + storyFileUrl + '" muted playsinline controls></video>';
    } else {
      prev.innerHTML = '<img src="' + storyFileUrl + '" alt="">';
    }
  }
  function probeStoryVideo(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var v = document.createElement('video');
      v.preload = 'metadata';
      v.onloadedmetadata = function () {
        var dur = v.duration;
        URL.revokeObjectURL(url);
        if (!isFinite(dur) || dur <= 0) {
          reject(new Error('Could not read that clip.'));
          return;
        }
        if (dur > storiesMaxSeconds() + 0.35) {
          reject(new Error('Clips must be ' + storiesMaxSeconds() + ' seconds or shorter.'));
          return;
        }
        resolve(dur);
      };
      v.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('Could not read that clip.'));
      };
      v.src = url;
    });
  }
  function onStoryFileChosen(file) {
    if (!file) return;
    storiesErr('');
    if (file.size > storiesMaxBytes()) {
      storiesErr('Keep the file under ' + Math.round(storiesMaxBytes() / 1000000) + ' MB.');
      return;
    }
    if (storyType === 'image') {
      if (!isProbablyImage(file) || isVideoFile(file)) {
        storiesErr('Use a photo (jpeg, png, gif, or webp).');
        return;
      }
      storyFile = file;
      previewStoryFile(file);
      return;
    }
    if (storyType === 'video') {
      var t = (file.type || '').toLowerCase();
      var okType = t === 'video/mp4' || t === 'video/webm' || /\.(mp4|webm)$/i.test(file.name || '');
      if (!okType) {
        storiesErr('Use a short mp4 or webm clip.');
        return;
      }
      probeStoryVideo(file).then(function () {
        storyFile = file;
        previewStoryFile(file);
      }).catch(function (e) {
        storyFile = null;
        storiesErr((e && e.message) ? e.message : 'Could not use that clip.');
      });
    }
  }
  function ensureStoriesComposer() {
    var ov = document.getElementById('stories-composer');
    if (ov) return ov;
    ov = document.createElement('div');
    ov.id = 'stories-composer';
    ov.className = 'stories-composer-overlay';
    ov.hidden = true;
    ov.innerHTML =
      '<div class="stories-composer" role="dialog" aria-modal="true" aria-labelledby="stories-composer-title">' +
        '<h2 id="stories-composer-title">Add a story</h2>' +
        '<p class="stories-composer-note">Lives 24 hours on this room only. Text, a photo, or a short clip.</p>' +
        '<div class="stories-composer-types">' +
          '<button type="button" data-story-type="text" class="is-on">Text</button>' +
          '<button type="button" data-story-type="image">Photo</button>' +
          '<button type="button" data-story-type="video">Clip</button>' +
        '</div>' +
        '<textarea id="stories-composer-text" maxlength="' + STORIES_TEXT_MAX + '" placeholder="' + escapeHtml(storiesComposePlaceholder()) + '"></textarea>' +
        '<input class="stories-composer-file" id="stories-composer-image" type="file" accept="image/jpeg,image/png,image/gif,image/webp,.jpg,.jpeg,.png,.gif,.webp" hidden>' +
        '<input class="stories-composer-file" id="stories-composer-video" type="file" accept="video/mp4,video/webm,.mp4,.webm" hidden>' +
        '<div class="stories-composer-preview" id="stories-composer-preview"></div>' +
        '<input class="stories-composer-caption" id="stories-composer-caption" maxlength="' + STORIES_CAPTION_MAX + '" placeholder="Caption (optional)" hidden>' +
        '<div class="stories-composer-err" id="stories-composer-err" role="status"></div>' +
        '<div class="stories-composer-bar">' +
          '<button type="button" class="stories-composer-close" id="stories-composer-close">Cancel</button>' +
          '<button type="button" class="stories-composer-post" id="stories-composer-post">Share story</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);
    ov.addEventListener('click', function (e) {
      if (e.target === ov) closeStoriesComposer();
    });
    ov.querySelectorAll('[data-story-type]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setStoryType(btn.getAttribute('data-story-type'));
        storiesErr('');
        if (storyType === 'image') {
          var imgIn = document.getElementById('stories-composer-image');
          if (imgIn) imgIn.hidden = false;
        }
        if (storyType === 'video') {
          var vidIn = document.getElementById('stories-composer-video');
          if (vidIn) vidIn.hidden = false;
        }
      });
    });
    var imgIn = document.getElementById('stories-composer-image');
    var vidIn = document.getElementById('stories-composer-video');
    if (imgIn) imgIn.addEventListener('change', function () { onStoryFileChosen(imgIn.files && imgIn.files[0]); });
    if (vidIn) vidIn.addEventListener('change', function () { onStoryFileChosen(vidIn.files && vidIn.files[0]); });
    var closeBtn = document.getElementById('stories-composer-close');
    if (closeBtn) closeBtn.addEventListener('click', function () { closeStoriesComposer(); });
    var postBtn = document.getElementById('stories-composer-post');
    if (postBtn) postBtn.addEventListener('click', submitStory);
    return ov;
  }
  function openStoriesComposer(force) {
    if (!storiesOn()) return;
    if (!force && !requireVerified('add a story')) return;
    if (!force && storiesPostedToday() >= STORIES_PER_DAY) {
      composeErr('Easy — a few stories a day is enough. Try again tomorrow.');
      return;
    }
    ensureStoriesComposer();
    setStoryType('text');
    storyFile = null;
    revokeStoryFileUrl();
    var text = document.getElementById('stories-composer-text');
    var caption = document.getElementById('stories-composer-caption');
    var imgIn = document.getElementById('stories-composer-image');
    var vidIn = document.getElementById('stories-composer-video');
    if (text) text.value = '';
    if (caption) caption.value = '';
    if (imgIn) imgIn.value = '';
    if (vidIn) vidIn.value = '';
    storiesErr('');
    var ov = document.getElementById('stories-composer');
    if (ov) ov.hidden = false;
  }
  function closeStoriesComposer() {
    var ov = document.getElementById('stories-composer');
    if (!ov || ov.hidden) return false;
    ov.hidden = true;
    storyFile = null;
    revokeStoryFileUrl();
    return true;
  }
  function uploadStoryMedia(file, uid, storyId) {
    if (!fbStorage) return Promise.reject(new Error('Storage not ready'));
    var ext = (file.name.split('.').pop() || (storyType === 'video' ? 'mp4' : 'jpg')).toLowerCase().replace(/[^a-z0-9]/g, '') || 'bin';
    var path = 'stories/' + SITE_ID + '/' + uid + '/' + storyId + '.' + ext;
    var ref = fbStorage.ref(path);
    var ctype = file.type || (storyType === 'video' ? 'video/mp4' : 'image/jpeg');
    return new Promise(function (resolve, reject) {
      var task = ref.put(file, { contentType: ctype });
      task.on('state_changed', function () {}, reject, function () {
        task.snapshot.ref.getDownloadURL().then(resolve).catch(reject);
      });
    });
  }
  function submitStory() {
    if (!requireVerified('add a story')) return;
    if (!fbDb) { storiesErr('Stories are not connected.'); return; }
    if (siteKilled) { storiesErr('This room is paused.'); return; }
    if (storiesPostedToday() >= STORIES_PER_DAY) {
      storiesErr('Easy — a few stories a day is enough.');
      return;
    }
    var live = fbAuth && fbAuth.currentUser;
    if (!live) return;
    var textEl = document.getElementById('stories-composer-text');
    var capEl = document.getElementById('stories-composer-caption');
    var body = ((textEl && textEl.value) || '').trim().slice(0, STORIES_TEXT_MAX);
    var caption = ((capEl && capEl.value) || '').trim().slice(0, STORIES_CAPTION_MAX);
    if (storyType === 'text' && !body) {
      storiesErr('Write a short card, or switch to photo / clip.');
      return;
    }
    if ((storyType === 'image' || storyType === 'video') && !storyFile) {
      storiesErr(storyType === 'video' ? 'Choose a short mp4 or webm clip.' : 'Choose a photo.');
      return;
    }
    var btn = document.getElementById('stories-composer-post');
    if (btn) btn.disabled = true;
    storiesErr(storyFile ? 'Uploading…' : '');
    var docRef = fbDb.collection('stories').doc();
    var wait = (storyType === 'video' && storyFile)
      ? probeStoryVideo(storyFile)
      : Promise.resolve(null);
    wait.then(function () {
      return storyFile ? uploadStoryMedia(storyFile, live.uid, docRef.id) : Promise.resolve('');
    }).then(function (mediaUrl) {
      var disp = (currentUser && currentUser.name) || live.displayName || (live.email || 'member').split('@')[0] || 'Member';
      var handle = (currentUser && currentUser.handle) || String(disp).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 15) || 'member';
      var now = firebase.firestore.Timestamp.now();
      var doc = {
        siteId: SITE_ID,
        authorUid: live.uid,
        authorName: disp,
        authorHandle: handle,
        type: storyType,
        createdAt: now,
        expiresAt: firebase.firestore.Timestamp.fromMillis(now.toMillis() + STORIES_TTL_MS),
        likeCount: 0
      };
      if (storyType === 'text') doc.text = body;
      else if (caption) doc.text = caption;
      if (mediaUrl) {
        doc.mediaUrl = mediaUrl;
        doc.mediaContentType = (storyFile && storyFile.type) || (storyType === 'video' ? 'video/mp4' : 'image/jpeg');
      }
      return docRef.set(doc);
    }).then(function () {
      bumpStoriesQuota();
      if (btn) btn.disabled = false;
      closeStoriesComposer();
      composeErr('Story is up for 24 hours.');
    }).catch(function (e) {
      if (btn) btn.disabled = false;
      storiesErr((e && e.message) ? e.message : 'Could not share that story.');
    });
  }
  function clearStoryViewerTimer() {
    if (storyViewerTimer) {
      clearTimeout(storyViewerTimer);
      storyViewerTimer = null;
    }
  }
  function closeStoriesViewer() {
    var el = document.getElementById('stories-viewer');
    if (!el || el.hidden) return false;
    clearStoryViewerTimer();
    if (storyViewerOnKey) {
      document.removeEventListener('keydown', storyViewerOnKey, true);
      storyViewerOnKey = null;
    }
    var vid = el.querySelector('video');
    if (vid) {
      try { vid.pause(); } catch (e) {}
      vid.removeAttribute('src');
    }
    el.hidden = true;
    document.body.style.overflow = '';
    var prev = storyViewerPrevFocus;
    storyViewerPrevFocus = null;
    if (prev && prev.focus) {
      try { prev.focus(); } catch (e2) {}
    }
    return true;
  }
  function storyAdvanceMs(story) {
    if (storiesReduceMotion()) return 0;
    if (!story || story.type === 'video') return 0;
    return 5500;
  }
  function paintStoryViewer() {
    var el = document.getElementById('stories-viewer');
    if (!el) return;
    var story = storyViewerList[storyViewerIdx];
    if (!story) { closeStoriesViewer(); return; }
    markStoriesSeen([story.id]);
    var segs = storyViewerList.map(function (_, i) {
      var cls = i < storyViewerIdx ? ' is-done' : (i === storyViewerIdx ? ' is-active' : '');
      var dur = storyAdvanceMs(storyViewerList[i]);
      var style = (i === storyViewerIdx && dur) ? ('animation-duration:' + dur + 'ms') : '';
      return '<div class="stories-progress-seg' + cls + '"><span class="stories-progress-fill" style="' + style + '"></span></div>';
    }).join('');
    var ago = Math.max(0, Math.round((Date.now() - (story.ms || Date.now())) / 3600000));
    var when = ago < 1 ? 'now' : (ago + 'h');
    var media = '';
    if (story.type === 'image' && story.mediaUrl) {
      media = '<img src="' + escapeHtml(story.mediaUrl) + '" alt="">';
    } else if (story.type === 'video' && story.mediaUrl) {
      var auto = storiesReduceMotion() ? '' : ' autoplay';
      media = '<video src="' + escapeHtml(story.mediaUrl) + '" playsinline' + auto + ' controls></video>';
    } else {
      media = '<div class="stories-text-card"><p>' + escapeHtml(story.text || '') + '</p></div>';
    }
    var caption = (story.type !== 'text' && story.text)
      ? '<div class="stories-caption">' + escapeHtml(story.text) + '</div>'
      : '';
    var canReport = isLiveUser() && story.authorUid && story.authorUid !== liveUid();
    el.innerHTML =
      '<div class="stories-viewer-card">' +
        '<div class="stories-progress">' + segs + '</div>' +
        '<div class="stories-viewer-top">' +
          '<div class="stories-avatar" style="width:32px;height:32px;font-size:0.65rem;background:' + colorFor(story.handle) + '">' + escapeHtml(initials(story.name)) + '</div>' +
          '<div><div class="stories-viewer-who">' + escapeHtml(story.name) + '</div>' +
          '<div class="stories-viewer-meta">@' + escapeHtml(story.handle) + ' · ' + when + '</div></div>' +
          '<button type="button" class="stories-viewer-close" data-story-ui="close" aria-label="Close">&times;</button>' +
        '</div>' +
        '<div class="stories-stage">' +
          media + caption +
          '<button type="button" class="stories-stage-hit prev" data-story-ui="prev" aria-label="Previous"></button>' +
          '<button type="button" class="stories-stage-hit next" data-story-ui="next" aria-label="Next"></button>' +
        '</div>' +
        '<div class="stories-viewer-actions">' +
          (canReport ? '<button type="button" data-story-ui="report">Report</button>' : '') +
          (story.authorUid === liveUid() ? '<button type="button" data-story-ui="delete">Delete</button>' : '') +
        '</div>' +
      '</div>';
    clearStoryViewerTimer();
    var ms = storyAdvanceMs(story);
    if (ms) {
      storyViewerTimer = setTimeout(function () { stepStoriesViewer(1); }, ms);
    }
    var vid = el.querySelector('video');
    if (vid && !storiesReduceMotion()) {
      vid.addEventListener('ended', function () { stepStoriesViewer(1); });
    }
    syncStoriesTray();
  }
  function stepStoriesViewer(dir) {
    var next = storyViewerIdx + (dir < 0 ? -1 : 1);
    if (next < 0 || next >= storyViewerList.length) {
      closeStoriesViewer();
      syncStoriesTray();
      return;
    }
    storyViewerIdx = next;
    paintStoryViewer();
  }
  function openStoriesViewer(startId) {
    if (!storiesOn()) return;
    var flat = [];
    storyGroups().forEach(function (g) {
      g.stories.forEach(function (s) { flat.push(s); });
    });
    if (!flat.length) return;
    var idx = 0;
    if (startId) {
      for (var i = 0; i < flat.length; i++) if (flat[i].id === startId) { idx = i; break; }
    }
    ensureStoriesViewer();
    storyViewerList = flat;
    storyViewerIdx = idx;
    storyViewerPrevFocus = document.activeElement;
    var el = document.getElementById('stories-viewer');
    el.hidden = false;
    document.body.style.overflow = 'hidden';
    if (!storyViewerOnKey) {
      storyViewerOnKey = function (e) {
        if (e.key === 'ArrowRight') { e.preventDefault(); stepStoriesViewer(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); stepStoriesViewer(-1); }
      };
      document.addEventListener('keydown', storyViewerOnKey, true);
    }
    paintStoryViewer();
  }
  function openStoriesGroup(uid) {
    var groups = storyGroups();
    for (var i = 0; i < groups.length; i++) {
      if (groups[i].uid === uid && groups[i].stories[0]) {
        openStoriesViewer(groups[i].stories[0].id);
        return;
      }
    }
  }
  function reportStory(id) {
    if (!requireVerified('report')) return;
    var story = findStory(id);
    if (!story || !fbDb) return;
    fbDb.collection('reports').add({
      siteId: SITE_ID,
      storyId: id,
      postId: 'story:' + id,
      targetUid: story.authorUid || '',
      reporterUid: liveUid(),
      reason: 'abuse',
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    }).then(function () {
      composeErr('Reported. Thanks.');
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not report.');
    });
  }
  function deleteOwnStory(id) {
    var story = findStory(id);
    if (!story) return;
    var uid = liveUid();
    if (!uid || story.authorUid !== uid) return;
    if (!fbDb) return;
    var chain = Promise.resolve();
    if (story.mediaUrl && fbStorage) {
      chain = fbStorage.refFromURL(story.mediaUrl).delete().catch(function (e) {
        console.warn('story storage delete', e);
      });
    }
    chain.then(function () {
      return fbDb.collection('stories').doc(id).delete();
    }).then(function () {
      closeStoriesViewer();
      composeErr('Story removed.');
    }).catch(function (e) {
      composeErr((e && e.message) ? e.message : 'Could not delete story.');
    });
  }
  function ensureStoriesViewer() {
    var el = document.getElementById('stories-viewer');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'stories-viewer';
    el.className = 'stories-viewer';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('aria-label', 'Story');
    el.hidden = true;
    document.body.appendChild(el);
    el.addEventListener('click', function (e) {
      var act = e.target.closest ? e.target.closest('[data-story-ui]') : null;
      if (!act) return;
      var which = act.getAttribute('data-story-ui');
      var story = storyViewerList[storyViewerIdx];
      if (which === 'close') closeStoriesViewer();
      else if (which === 'next') stepStoriesViewer(1);
      else if (which === 'prev') stepStoriesViewer(-1);
      else if (which === 'report' && story) reportStory(story.id);
      else if (which === 'delete' && story) deleteOwnStory(story.id);
    });
    return el;
  }
  function renderStoriesTray() {
    if (!storiesOn()) {
      var stale = document.getElementById('stories-tray');
      if (stale) stale.hidden = true;
      return;
    }
    var el = ensureStoriesTray();
    var groups = storyGroups();
    var signedIn = isLiveUser() || (storiesLocalHost() && !!storiesDebugOwnUid);
    var me = liveUid() || storiesDebugOwnUid || '';
    var html = '';
    if (signedIn) {
      var mine = groups.filter(function (g) { return g.uid === me; })[0];
      var myLatest = mine ? latestStory(mine.stories) : null;
      var hasMine = !!myLatest;
      var mineSeen = hasMine && !groupHasUnseen(mine.stories);
      var addCls = 'stories-item is-add' + (hasMine ? ' has-story' : '') + (mineSeen ? ' is-seen' : '');
      html +=
        '<button type="button" class="' + addCls + '"' +
          (hasMine ? ' data-story-uid="' + escapeHtml(me) + '"' : ' data-story-add="1"') +
          ' aria-label="' + (hasMine ? 'Your story' : 'Add story') + '">' +
          '<span class="stories-ring">' +
            storyTrayAvatarHtml(myLatest, (currentUser && currentUser.name) || 'Me', (currentUser && currentUser.handle) || 'me') +
            '<span class="stories-add-badge" data-story-add="1">+</span></span>' +
          '<span class="stories-label">' + (hasMine ? 'Your story' : 'Add story') + '</span>' +
        '</button>';
    }
    groups.forEach(function (g) {
      var latest = latestStory(g.stories);
      if (!latest) return;
      if (signedIn && g.uid === me) return;
      var unseen = groupHasUnseen(g.stories);
      html +=
        '<button type="button" class="stories-item' + (unseen ? '' : ' is-seen') + '" data-story-uid="' +
          escapeHtml(g.uid) + '" role="listitem">' +
          '<span class="stories-ring">' + storyTrayAvatarHtml(latest) + '</span>' +
          '<span class="stories-label">' + escapeHtml(latest.name) + '</span>' +
        '</button>';
    });
    el.innerHTML = html;
    primeStoryTrayThumbs(el);
    var emptyGuest = !signedIn && !groups.length;
    el.hidden = emptyGuest;
  }
  function syncStoriesTray() {
    if (!storiesOn()) {
      var el = document.getElementById('stories-tray');
      if (el) el.hidden = true;
      return;
    }
    renderStoriesTray();
  }
  function wireStoriesOnce() {
    if (storiesWired) return;
    storiesWired = true;
    document.addEventListener('click', function (e) {
      var add = e.target.closest ? e.target.closest('[data-story-add]') : null;
      if (add) {
        e.preventDefault();
        openStoriesComposer();
        return;
      }
      var item = e.target.closest ? e.target.closest('[data-story-uid]') : null;
      if (item) {
        e.preventDefault();
        openStoriesGroup(item.getAttribute('data-story-uid'));
      }
    });
  }
  function listenStories() {
    if (storiesUnsub) { storiesUnsub(); storiesUnsub = null; }
    liveStories = [];
    if (!storiesOn() || !fbDb) {
      renderStoriesTray();
      return;
    }
    storiesUnsub = fbDb.collection('stories')
      .where('siteId', '==', SITE_ID)
      .onSnapshot(function (snap) {
        var now = Date.now();
        liveStories = snap.docs.map(mapStory).filter(function (s) {
          return s.expiresAtMs > now && (!s.siteId || s.siteId === SITE_ID);
        });
        renderStoriesTray();
      }, function (err) {
        console.warn('stories', err);
        liveStories = [];
        renderStoriesTray();
      });
  }
  function initStories() {
    if (!storiesOn()) return;
    wireStoriesOnce();
    ensureStoriesTray();
    ensureStoriesViewer();
    renderStoriesTray();
    listenStories();
    if (storiesLocalHost()) {
      window.__storiesDebug = {
        openCreate: function () { openStoriesComposer(true); },
        openViewer: openStoriesViewer,
        showAddTray: function () {
          var el = ensureStoriesTray();
          el.hidden = false;
          el.innerHTML =
            '<button type="button" class="stories-item is-add" data-story-add="1" aria-label="Add story">' +
              '<span class="stories-ring"><span class="stories-avatar" style="background:' + colorFor(SITE_ID || '311chat') + '">' +
              escapeHtml(String(SITE_ID || '311chat').replace(/chat$/i, '').slice(0, 3).toUpperCase() || 'ME') + '</span>' +
              '<span class="stories-add-badge">+</span></span>' +
              '<span class="stories-label">Add story</span></button>';
        },
        setDemo: function (list, ownUid) {
          if (storiesUnsub) { storiesUnsub(); storiesUnsub = null; }
          storiesDebugOwnUid = ownUid || '';
          liveStories = (list || []).map(function (s, i) {
            return {
              id: s.id || ('demo-' + i),
              siteId: SITE_ID,
              authorUid: s.authorUid || ('demo-' + i),
              name: s.name || (site && site.name) || '311chat',
              handle: s.handle || SITE_ID || '311chat',
              type: s.type || 'text',
              text: s.text || '',
              mediaUrl: s.mediaUrl || '',
              mediaContentType: s.mediaContentType || '',
              posterUrl: s.posterUrl || s.thumbUrl || '',
              ms: s.ms || Date.now(),
              expiresAtMs: Date.now() + STORIES_TTL_MS,
              likeCount: 0,
              likedBy: {}
            };
          });
          renderStoriesTray();
        }
      };
    }
  }

  function boot(data) {
    site = data || {};
    SITE_ID = site.siteId || SITE_ID;
    TRENDS = site.trends || [];
    PLACES = site.places || [];
    TOPICS = site.topics || [];
    adminNests = Array.isArray(site.nests) ? site.nests : [];
    mergeNests();
    applyTheme(site.theme);
    applySiteChrome();
    ensureJoinAuthLayout();
    ensureDmCss();
    hideDummyChrome();
    syncChatChrome();

    wireEvents();
    document.addEventListener('subx-auth-land', function () { landInFeedCompose(); });
    renderTrends();
    renderExplore();
    renderNotifs();
    renderThreads();
    renderSidebarAuth();
    renderFeed();
    railOverlayUiReady = true;
    wireRailOverlay();
    maybeShowRailOverlay();

    restoreBouncedPath();
    window.addEventListener('hashchange', applyRoute);
    window.addEventListener('popstate', applyRoute);
    try { deepPostId = new URLSearchParams(location.search).get('p') || ''; } catch (e) { deepPostId = ''; }
    if (!location.hash || location.hash === '#') {
      history.replaceState(null, '', location.pathname + location.search + '#home');
    }
    applyRoute();
    if (deepPostId) {
      closeSocialOverlays();
      showContentPage('thoughts');
      if (!currentNest) highlightSocial('home');
      selectThoughtsTab('foryou');
    }
    syncHamburgerAria();
    try { if (!sessionStorage.getItem('subx.hit.'+SITE_ID)) { sessionStorage.setItem('subx.hit.'+SITE_ID,'1'); sendPixel(); } } catch (e) {}

    fbReadyPromise.then(function () {
      if (fbAuth) {
        fbAuth.getRedirectResult().then(function (cred) {
          var u = cred && cred.user;
          if (fbDb && u) {
            var disp = u.displayName || (u.email || 'member').split('@')[0];
            return fbDb.collection('users').doc(u.uid).set({
              displayName: disp,
              siteId: SITE_ID,
              provider: 'google',
              createdAt: firebase.firestore.FieldValue.serverTimestamp()
            }, { merge: true });
          }
        }).catch(function () {});
        fbAuth.onAuthStateChanged(function (user) {
          if (user) applyFbUser(user);
          else {
            listenBlocks(null);
            if (currentUser && currentUser.live) {
              currentUser = null;
              saveJSON(LS_USER, null);
              renderSidebarAuth();
              hideDummyChrome();
              teardownDms();
              listenConversations();
              syncProfile();
              renderFeed();
            }
          }
        });
      }
      listenKillSwitch();
      listenLivePosts();
      initStories();
    });
  }

  fetch(SITE_JSON_URL)
    .then(function (res) {
      if (!res.ok) throw new Error('Could not load ' + SITE_JSON_URL);
      return res.json();
    })
    .then(boot)
    .catch(function (e) {
      console.warn('site.json', e);
      composeErr((e && e.message) ? e.message : 'Could not load site.json');
      boot({ siteId: "311chat", name: "311chat", tagline: "Non-emergency city help. Find your 311." });
    });
})();
