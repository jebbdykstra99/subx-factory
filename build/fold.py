"""Fold gpchat (PR #31 head) features into the master template, function by function.
Input: merged.js (git merge-file template + gpchat with base gpchat@7553762, conflicts resolved by resolve.py).
Output: factory.js (one identical file for every room; room differences come from site.json)."""
import sys, re
sys.path.insert(0, '../tools')
from fnsplit import split
M = split(open('merged.js').read())
T = dict((k, v) for k, v in split(open('template.js').read()) if not k.startswith('#'))
G = dict((k, v) for k, v in split(open('gpchat_pr31.js').read()) if not k.startswith('#'))
Gorder = [k for k, _ in split(open('gpchat_pr31.js').read()) if not k.startswith('#')]
def ed(src, old, new, count=1):
    assert src.count(old) == count, (old[:80], src.count(old))
    return src.replace(old, new)
R = {}
# 1) gpchat behavior wins (template had no change of substance, gpchat added features)
for k in ['findPost', 'requireVerified', 'selectThoughtsTab', 'applyRoute', 'renderFeed', 'porchCardHtml',
          'outboundCards', 'f1CardsFromRace', 'f1FormatGap', 'overlayOpenF1Cards', 'railNwsSlots', 'openThread',
          'startDm', 'sendDm', 'openChat', 'toggleLike', 'syncChatChrome']:
    R[k] = G[k]
# Nest feed. Listeners live in the template. These three functions are still gpchat's,
# so the per-nest query has to be reapplied here or the next rebuild drops it.
# Home stays the newest 80 (siteId + createdAt). A nest view uses nestPosts.
R['findPost'] = ed(G['findPost'],
    "    for (var i = 0; i < livePosts.length; i++) if (livePosts[i].id === id) return livePosts[i];\n",
    "    var i;\n    for (i = 0; i < livePosts.length; i++) if (livePosts[i].id === id) return livePosts[i];\n"
    "    for (i = 0; i < nestPosts.length; i++) if (nestPosts[i].id === id) return nestPosts[i];\n")
R['applyRoute'] = ed(G['applyRoute'],
    "    currentNest = resolveNestFromPath();\n    applyNestChrome();\n",
    "    currentNest = resolveNestFromPath();\n    syncNestFeed();\n    applyNestChrome();\n")
R['renderFeed'] = ed(G['renderFeed'],
    "    var seeds = currentNest ? [] : sessionSeedPosts();\n"
    "    if (liveError && !seeds.length) {\n"
    "      el.innerHTML = '<div class=\"post-empty\">Live feed could not load. The error is in the compose line above — this is not an empty room.</div>';\n"
    "      refreshPorchUi();\n"
    "      return;\n"
    "    }\n"
    "    if (!liveReady && !seeds.length) {\n"
    "      el.innerHTML = '<div class=\"post-empty\">Connecting to the live feed…</div>';\n"
    "      refreshPorchUi();\n"
    "      return;\n"
    "    }\n"
    "\n"
    "    let posts = (liveReady && !liveError) ? topLevelPosts().slice() : [];\n"
    "    if (liveReady && !liveError && currentTab === 'hot') posts.sort(function (a, b) { return (b.likes || 0) - (a.likes || 0); });\n"
    "    if (liveReady && !liveError && currentTab === 'new') posts.sort(function (a, b) { return (b.ms || 0) - (a.ms || 0); });\n",
    "    var nestView = !!currentNest;\n"
    "    var seeds = nestView ? [] : sessionSeedPosts();\n"
    "    var scopeError = nestView ? nestError : liveError;\n"
    "    var scopeReady = nestView ? nestReady : liveReady;\n"
    "    if (scopeError && !seeds.length) {\n"
    "      el.innerHTML = '<div class=\"post-empty\">' + (nestView\n"
    "        ? 'This nest could not load. The error is in the compose line above. This is not an empty room.'\n"
    "        : 'Live feed could not load. The error is in the compose line above. This is not an empty room.') + '</div>';\n"
    "      refreshPorchUi();\n"
    "      return;\n"
    "    }\n"
    "    if (!scopeReady && !seeds.length) {\n"
    "      el.innerHTML = '<div class=\"post-empty\">Connecting to the live feed…</div>';\n"
    "      refreshPorchUi();\n"
    "      return;\n"
    "    }\n"
    "\n"
    "    let posts = (scopeReady && !scopeError) ? topLevelPosts().slice() : [];\n"
    "    if (scopeReady && !scopeError && currentTab === 'hot') posts.sort(function (a, b) { return (b.likes || 0) - (a.likes || 0); });\n"
    "    if (scopeReady && !scopeError && currentTab === 'new') posts.sort(function (a, b) { return (b.ms || 0) - (a.ms || 0); });\n")
R['renderFeed'] = ed(R['renderFeed'],
    "      var empty = currentNest\n"
    "        ? ('No posts in ' + (currentNest.label || currentNest.slug) + ' yet. This nest is live at /' + currentNest.slug + '. Sign in to post the first take.')\n"
    "        : ((site && site.emptyState) || 'This room is empty. Sign in to post. Guest can browse only.');\n",
    "      var empty = nestView\n"
    "        ? (nestScanCapped\n"
    "          ? ('Posts in ' + (currentNest.label || currentNest.slug) + ' could not be reached yet. The nest index is not built, and the fallback scan stopped after ' + NEST_SCAN_CAP + ' newer posts. This is not an empty room.')\n"
    "          : ('No posts in ' + (currentNest.label || currentNest.slug) + ' yet. This nest is live at /' + currentNest.slug + '. Sign in to post the first take.'))\n"
    "        : ((site && site.emptyState) || 'This room is empty. Sign in to post. Guest can browse only.');\n")
R['renderFeed'] = ed(R['renderFeed'],
    "    }).join('');\n    highlightDeepPost();\n",
    "    }).join('') + nestMoreHtml();\n    highlightDeepPost();\n")
# 2) feature flags (site.json "features": {...}); everything gpchat-specific is OFF unless the room opts in
R['followingOn'] = ed(G['followingOn'], 'return !!fbDb;', "return !!fbDb && featureOn('following');")
R['notifsOn'] = ed(G['notifsOn'], 'return !!fbDb;', "return !!fbDb && featureOn('notifs');")
R['renderFollowBtn'] = ed(G['renderFollowBtn'], "  function renderFollowBtn(card) {\n", "  function renderFollowBtn(card) {\n    if (!featureOn('topicFollow')) return '';\n")
R['sessionSeedList'] = ed(G['sessionSeedList'], "  function sessionSeedList() {\n", "  function sessionSeedList() {\n    if (!featureOn('sessionSeeds')) return [];\n")
R['renderWatchlist'] = ed(G['renderWatchlist'], "  function renderWatchlist() {\n    var list = document.getElementById('watchlist-list');\n    if (!list) return;\n",
  "  function renderWatchlist() {\n    var box = document.getElementById('watchlist');\n    if (!featureOn('watchlist')) { if (box) box.hidden = true; return; }\n    if (box) box.hidden = false;\n    var list = document.getElementById('watchlist-list');\n    if (!list) return;\n")
# 3) hand merges
h = G['hideDummyChrome']
h = ed(h, "      if (el.id === 'nav-chat' || el.id === 'nav-following' || el.id === 'nav-notifications') return;\n",
          "      if (el.id === 'nav-chat' || el.id === 'nav-following' || el.id === 'nav-notifications') return;\n"
          "      if (el.getAttribute('data-social') === 'chat' && dmsOn()) { paintNavSoon(el, true); return; }\n")
R['hideDummyChrome'] = h
R['renderTrendCard'] = """  function renderTrendCard(t) {
    const href = t.url || '#';
    const extra = t.url ? ' target="_blank" rel="noopener noreferrer"' : '';
    if (!featureOn('topicFollow')) {
      return '<a class="news-item" href="' + escapeHtml(href) + '"' + extra + '>' +
        '<div class="news-item-tag">' + escapeHtml(t.tag) + '</div>' +
        '<div class="news-item-headline">' + escapeHtml(t.headline) + '</div>' +
        '<div class="news-item-snippet">' + escapeHtml(t.snippet) + '</div>' +
        '<div class="news-item-meta">' + escapeHtml(t.meta) + '</div>' +
      '</a>';
    }
    return '<article class="news-item">' +
      renderFollowBtn(t) +
      '<a class="news-item-main" href="' + escapeHtml(href) + '"' + extra + '>' +
        '<div class="news-item-tag">' + escapeHtml(t.tag) + '</div>' +
        '<div class="news-item-headline">' + escapeHtml(t.headline) + '</div>' +
        '<div class="news-item-snippet">' + escapeHtml(t.snippet) + '</div>' +
        '<div class="news-item-meta">' + escapeHtml(t.meta) + '</div>' +
      '</a>' +
    '</article>';
  }"""
assert T['renderTrendCard'].split('\n')[1].strip().startswith('const href') and G['renderTrendCard'].split('\n')[2].strip().startswith('const extra'), 'renderTrendCard header changed'
css = T['ensureRailCss']
css = ed(css, "    document.head.appendChild(st);\n",
  "    if (featureOn('topicFollow')) {\n      st.textContent +=\n"
  "        '.news-item{padding:1rem 2.8rem 1rem 1.4rem;position:relative;}' +\n"
  "        'a.news-item,.news-item-main{text-decoration:none;cursor:pointer;color:inherit;display:block;padding-right:2.15rem;}' +\n"
  "        '.news-follow-btn{position:absolute;top:0.75rem;right:0.85rem;z-index:2;width:28px;height:28px;padding:0;border-radius:999px;' +\n"
  "          'border:1px solid var(--accent,#e10600);background:transparent;color:var(--accent,#e10600);cursor:pointer;' +\n"
  "          'display:inline-flex;align-items:center;justify-content:center;}' +\n"
  "        '.news-follow-btn:hover{background:rgba(225,6,0,0.14);}' +\n"
  "        '.news-follow-btn:focus-visible{outline:2px solid var(--accent,#e10600);outline-offset:2px;}' +\n"
  "        '.news-follow-btn.is-following{background:var(--accent,#e10600);color:#fff;border-color:var(--accent,#e10600);}' +\n"
  "        '.news-page-list .news-follow-btn{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);}' +\n"
  "        '.news-page-list .news-follow-btn.is-following{background:var(--accent,#c0362c);color:#fff;border-color:var(--accent,#c0362c);}';\n"
  "    }\n    document.head.appendChild(st);\n")
R['ensureRailCss'] = css
R['paintRail'] = ed(T['paintRail'], "(items || []).map(renderTrendCard).join('') + porchCardHtml();", "(items || []).map(renderTrendCard).join('') + (currentNest ? '' : porchCardHtml());")
R['fallbackTrendCards'] = ed(T['fallbackTrendCards'], "if (extra.length) return extra.slice(0, 1);", "if (extra.length) return extra.slice(0, railKind() === 'f1-calendar' ? railNwsSlots() : 1);")
# renderTrends rail merge by rail.kind: f1-calendar = gpchat F1 rail; rail.liveKeep = samochat (forecast/outbound first,
# keep at least one live card; was samochat-only code); nws-forecast (415/808) and bart-bsa (bartchat) = pinned first.
# (These notes used to ship as JS comments; lean trim 2026-10-22 keeps them here, out of factory.js.)
R['renderTrends'] = ed(T['renderTrends'], """      var merged = (cards || []).concat(extra);
      if (merged.length) commitRail(merged.slice(0, railNwsSlots()));""", """      var merged;
      if (railKind() === 'f1-calendar') {
        merged = mergeF1Rail(cards, extra);
      } else if (railCfg().liveKeep === true) {
        var slots = railNwsSlots();
        var liveKeep = Math.max(0, slots - extra.length);
        if (!liveKeep && (cards || []).length) liveKeep = 1;
        merged = railKind() === 'nws-forecast'
          ? (extra || []).concat((cards || []).slice(0, liveKeep))
          : (cards || []).slice(0, liveKeep).concat(extra);
        if (merged.length) { commitRail(merged); return; }
      } else if (railKind() === 'nws-forecast' || railKind() === 'bart-bsa') {
        merged = (extra || []).concat(cards || []);
      } else {
        merged = (cards || []).concat(extra);
      }
      if (merged.length) commitRail(merged.slice(0, railNwsSlots()));""")
# site.json-driven skin strings (no room-specific fallbacks inside factory.js)
a = T['applySiteChrome']
a = ed(a, 'var title = site.name || "311chat";', 'var title = site.name || SITE_ID || \'SubX\';')
a = ed(a, "var tag = site.tagline || 'Non-emergency city help. Find your 311.';", "var tag = site.tagline || '';")
a = ed(a, "authNote.textContent = site.trustBlurb || ('Unofficial helper. Not a substitute for 911. Links to official city channels. Guest is browse-only. Preview.');",
          "authNote.textContent = site.trustBlurb || ('Continue with Google to join ' + title + '. Email is optional. Guest is browse-only.');")
R['applySiteChrome'] = a
R['postPermalink'] = ed(T['postPermalink'], "|| '311chat.com';", "|| ((site && site.domain) || 'subx.it');")
R['dmSiteId'] = ed(T['dmSiteId'], "return SITE_ID || '311chat';", "return SITE_ID;")
# Whole function is the gpchat body (G), not factory/factory.js. The New message
# picker filter lives here; a hand edit in factory/factory.js is not read back.
# build/rebuild.sh refuses to overwrite a committed file that differs.
R['openAdminPicker'] = ed(G['openAdminPicker'], "'<div class=\"soon-panel\">No gpchat users yet.</div>'", "'<div class=\"soon-panel\">No ' + escapeHtml((site && site.name) || SITE_ID) + ' users yet.</div>'")
R['paintProfile'] = ed(T['paintProfile'], "'<div class=\"empty-note\" id=\"profile-posts-empty\">No posts yet. Official 311 is the handoff at the top of Home. Sign in to talk with neighbors.</div>'",
  "'<div class=\"empty-note\" id=\"profile-posts-empty\">' + escapeHtml(skin('profileEmpty', 'No posts yet.')) + '</div>'")
R['syncProfile'] = ed(G['syncProfile'], 'currentUser.bio || "Talking about the city.",', "currentUser.bio || skin('bioDefault', ''),")
R['renderSidebarAuth'] = ed(T['renderSidebarAuth'], 'av.textContent = "CO";', "av.textContent = skin('avatarInitials', String(SITE_ID || 'S').replace(/chat$/i, '').slice(0, 3).toUpperCase());")
s = T['stubSignIn']
s = ed(s, "(handle || 'guest311')", "(handle || 'guest')"); s = ed(s, "|| 'guest311',", "|| 'guest',")
s = ed(s, 'bio: "Unofficial helper, not a substitute for 911.",', "bio: skin('bioDefault', ''),")
R['stubSignIn'] = s
for k in ['syncEarlyWelcome', 'renderExplore', 'storyGroups', 'ensureStoriesComposer', 'renderStoriesTray', 'initStories', 'renderNestNav']:
    R[k] = T[k]
R['initStories'] = R['initStories'].replace("'311chat'", "'room'")
R['storiesComposePlaceholder'] = ed(T['storiesComposePlaceholder'], '|| "Species note, myth bust, or story?";', "|| 'What is happening right now?';")

# wireEvents: template version (runWithAuth, a[data-nest], nest seat cards) + gpchat handlers the merge dropped
Gw = G['wireEvents']
def gblock(start, end):
    i = Gw.index(start); j = Gw.index(end, i)
    return Gw[i:j]
w = R.get('wireEvents') or dict((k, v) for k, v in M if not k.startswith('#'))['wireEvents']
watch = gblock("      if (e.target.closest('#watchlist-add')) {", "      if (e.target.closest('#auth-signin')")
w = ed(w, "      if (e.target.closest('#auth-signin')", watch + "      if (e.target.closest('#auth-signin')")
follow = gblock("      const followBtn = e.target.closest('[data-topic-follow]');", "      const porchBtn = e.target.closest('[data-porch]');")
w = ed(w, "      if (e.target.closest('#chat-picker-close')) {\n        hideDmPicker();\n        return;\n      }\n\n",
          "      if (e.target.closest('#chat-picker-close')) {\n        hideDmPicker();\n        return;\n      }\n\n" + follow)
seed = gblock("        var seedPost = findPost(post.dataset.postId);", "        replyTo = post.dataset.parentId || post.dataset.postId;")
w = ed(w, "        if (!post) return;\n        replyTo = post.dataset.parentId || post.dataset.postId;",
          "        if (!post) return;\n" + seed + "        replyTo = post.dataset.parentId || post.dataset.postId;")
w = ed(w, "    if (chatSend) chatSend.addEventListener('click', sendDm);",
          "    if (chatSend) chatSend.addEventListener('click', function () {\n      if (dmSendInFlight) return;\n      sendDm();\n    });")
w = ed(w, "          e.preventDefault();\n          sendDm();", "          e.preventDefault();\n          if (dmSendInFlight) return;\n          sendDm();")
R['wireEvents'] = w

a = R['applySiteChrome']
a = ed(a, "    if (brandTitle) brandTitle.textContent = title;\n", "    if (brandTitle && !(skin('keepBrandTitle', '') === 'true' && brandTitle.tagName === 'H1')) brandTitle.textContent = title;\n")
a = ed(a, "    var authTitle = document.getElementById('auth-title');\n",
  "    var homeH1 = document.querySelector('#page-thoughts .home-h1');\n    if (homeH1 && tag && skin('taglineH1', '') === 'true') homeH1.textContent = tag;\n"
  "    var regName = document.getElementById('cv-reg-name');\n    if (regName && skin('regNamePlaceholder', '')) regName.setAttribute('placeholder', skin('regNamePlaceholder', ''));\n"
  "    var authTitle = document.getElementById('auth-title');\n")
R['applySiteChrome'] = a
R['stubSignIn'] = R['stubSignIn'].replace("(handle || 'guest')", "(handle || skin('guestHandle', 'guest'))").replace("|| 'guest',", "|| skin('guestHandle', 'guest'),")
R['wireEvents'] = ed(R['wireEvents'], "stubSignIn('Guest', 'guest');", "stubSignIn('Guest', skin('guestHandle', 'guest'));")
R['wireEvents'] = ed(R['wireEvents'], "'<p class=\"empty-note\">Nothing in this room matched that.</p>'", "'<p class=\"empty-note\">' + escapeHtml(skin('exploreEmpty', 'Nothing in this room matched that.')) + '</p>'")
R['wireEvents'] = ed(R['wireEvents'],
    "      const nestLink = e.target.closest('a[data-nest]');\n",
    "      if (e.target.closest('#nest-feed-more')) {\n        e.preventDefault();\n        loadMoreNestPosts();\n        return;\n      }\n      const nestLink = e.target.closest('a[data-nest]');\n")
n = T['nestSeatCards']
n = ed(n, "tag: (n.kind === 'species' ? 'Species' : (n.kind || 'Nest')),", "tag: (n.kind === 'species' ? 'Species' : (n.kind || skin('seatTag', 'Nest'))),")
n = ed(n, "title: n.label || n.slug || 'Nest',", "title: n.label || n.slug || skin('seatTag', 'Nest'),")
R['nestSeatCards'] = n
R['storiesComposePlaceholder'] = """  function storiesComposePlaceholder() {
    return skin('storiesPlaceholder', (site && site.composePlaceholder) || 'What is happening right now?');
  }"""
R['paintProfile'] = ed(R['paintProfile'], "escapeHtml(skin('profileEmpty', 'No posts yet.'))", "escapeHtml(skin('profileEmpty', (site && site.emptyState) || 'No posts yet.'))")
R['sendPixel'] = ed(T['sendPixel'], "  function sendPixel(eventName) {\n", "  function sendPixel(eventName) {\n    if (site && site.pixel === false) return;\n")  # opt-out per room (privacy v1.1 gate); default on as in T0
# ---- assemble
out = []
seen = set()
for k, v in M:
    if not k.startswith('#'):
        seen.add(k)
        v = R.get(k, v)
    out.append(v)
src = '\n'.join(out)
# insert gpchat functions the 3-way merge dropped (template never had them), after their gpchat predecessor
missing = [k for k in Gorder if k not in seen]
for k in missing:
    body = R.get(k, G[k])
    i = Gorder.index(k); anchor = None
    for j in range(i - 1, -1, -1):
        if Gorder[j] in seen: anchor = Gorder[j]; break
    m = re.search(r'\n  (?:async )?function %s\s*\(' % re.escape(anchor), src)
    # end of the anchor function = first line '  }' after it
    e = src.index('\n  }\n', m.start()) + len('\n  }\n')
    src = src[:e] + '\n' + body + '\n' + src[e:]
    seen.add(k)
print('re-inserted', len(missing), missing)
# helpers: features + skin + one identical file for every room
# site.json "features": { watchlist, following, notifs, topicFollow, sessionSeeds } (all default false).
# DMs stay on site.json "dms" (existing). F1 rail stays on rail.kind 'f1-calendar'. Age: site.json "minAge".
# site.json "skin": { bioDefault, avatarInitials, profileEmpty, guestHandle, exploreEmpty, seatTag, storiesPlaceholder,
#   regNamePlaceholder, taglineH1:"true", keepBrandTitle:"true" } (strings). Room copy lives in site.json, never here.
helpers = """
  function featureOn(name) {
    var f = site && site.features;
    return !!(f && f[name] === true);
  }
  function skin(key, fallback) {
    var s = site && site.skin;
    var v = s && typeof s[key] === 'string' ? s[key] : '';
    return v || fallback;
  }
"""
anchor = "  const hamburger = document.getElementById('hamburger');"
src = ed(src, anchor, helpers.lstrip('\n') + '\n' + anchor)
# one file for all rooms: neutral constants; localStorage is per-origin so a fixed prefix is safe.
# The try block is a one-time migration from the per-room keys older stamps used (<room>.user / <room>.likes).
src = ed(src, "  const LS_USER = '311chat.user';\n  const LS_LIKES = '311chat.likes';\n",
"""  const LS_USER = 'subx.user';
  const LS_LIKES = 'subx.likes';
  try {
    if (!localStorage.getItem(LS_USER) || !localStorage.getItem(LS_LIKES)) {
      for (var lsI = 0; lsI < localStorage.length; lsI++) {
        var lsK = localStorage.key(lsI) || '';
        if (!localStorage.getItem(LS_USER) && /^[a-z0-9-]+\\.user$/.test(lsK) && lsK !== LS_USER) localStorage.setItem(LS_USER, localStorage.getItem(lsK));
        if (!localStorage.getItem(LS_LIKES) && /^[a-z0-9-]+\\.likes$/.test(lsK) && lsK !== LS_LIKES) localStorage.setItem(LS_LIKES, localStorage.getItem(lsK));
      }
    }
  } catch (eLs) {}
""")
src = ed(src, "  let site = null;\n", "  let site = null;\n  const LS_TOPIC_FOLLOWS = 'subx.topicFollows';\n  let dmSendInFlight = false;\n  let focusedTopicId = '';\n  let watchlistPickerOpen = false;\n  let watchlistQuery = '';\n")
src = ed(src, "  let SITE_ID = '311chat';", "  let SITE_ID = '';  // set from site.json siteId in boot()")
banner = """/* SubX factory.js (subx-factory master). DO NOT EDIT IN A ROOM REPO.
 * Source: github.com/jebbdykstra99/subx-factory  (version + sha256 in the room's FACTORY.lock)
 * Room differences belong in site.json (features, skin, rail, nests, minAge) or in EXCEPTIONS.md. */
"""
src = ed(src, 'boot({ siteId: "311chat", name: "311chat", tagline: "Non-emergency city help. Find your 311." });',
  "boot({ siteId: (location.hostname || 'room').replace(/^www\\./, '').replace(/\\.[a-z]+$/, ''), name: (location.hostname || 'SubX').replace(/^www\\./, ''), tagline: '', imageUploads: false });")
src = src.replace("name: 'Grid', symbolPrefix", "name: 'Topics', symbolPrefix").replace("tax.name || 'Grid'", "tax.name || 'Topics'").replace("(taxName || 'Grid')", "(taxName || 'Topics')").replace("'Not on the Grid'", "'Not in this room'").replace("That topic is not on the Grid.", "That topic is not in this room.")
# SubX rule (2026-10-22): no 13+ anywhere. A room without site.json minAge gets the 18+ gate.
src = ed(src, "    if (!isFinite(n) || n < 1) return 13;\n", "    if (!isFinite(n) || n < 1) return 18;\n")
# Accounts gate (2026-10-22). Ported from gpchat accountsOpen()/applyAccountsGate(). Re-scoped the same day after SubX's
# "anyone can sign up" call: a room is CLOSED only when site.json says accountsOpen:false or accounts:'closed'. A missing
# flag is OPEN. preview:true is the banner only (static index.html markup) and never closes sign-ups. New rooms can't
# land without a decision: tools/stamp.py requires an explicit rooms.json accountsOpen. Closed: no Register / Google join,
# no users/{uid} profile write, no post/story/like/vote/DM from non-admin. Admin UID keeps writing.
# localStorage subx.steward=1 shows the Google button (admin sign-in only; any other uid is signed out).
# Works on factory markup (note injected) and gpchat markup (static #cv-accounts-closed: hidden when open, reused when
# closed). The once-guard is the injected style id (acc-gate-css), so a static note never skips the hiding CSS.
src = ed(src, "  function isAdminUser() {\n    return liveUid() === ADMIN_UID;\n  }\n", """  function isAdminUser() {
    return liveUid() === ADMIN_UID;
  }
  var ACC_CLOSED = 'Accounts are not open yet. You can read the room as a guest.';
  function accountsOpen() {
    return !(site && (site.accountsOpen === false || site.accounts === 'closed'));
  }
  function applyAccountsGate() {
    var d = document.documentElement, o = accountsOpen(), stew = false, n = document.getElementById('cv-accounts-closed');
    try { stew = localStorage.getItem('subx.steward') === '1'; } catch (e) {}
    d.classList.toggle('acc-closed', !o);
    d.classList.toggle('acc-stew', stew);
    if (n) n.style.display = o ? 'none' : '';
    if (o || document.getElementById('acc-gate-css')) return;
    var g = document.getElementById('cv-google-age'), c = '.acc-closed:not(.acc-stew) ';
    g = g && g.closest('label');
    if (g) g.classList.add('acc-g');
    var st = document.createElement('style');
    st.id = 'acc-gate-css';
    st.textContent = '.acc-closed [data-tab="register"],.acc-closed #cv-panel-register,.acc-closed #cv-goto-register,.acc-closed #cv-goto-join,' +
      c + '#cv-google-login,' + c + '.acc-g,' + c + '[for=cv-google-dob],' + c + '#cv-panel-login .conv-modal-divider{display:none!important}';
    document.head.appendChild(st);
    var p = document.getElementById('cv-panel-login'), t = document.getElementById('auth-title');
    if (t) t.textContent = 'Sign in to ' + (site && site.name || 'this room');
    if (n || !p) return;
    n = document.createElement('p');
    n.className = 'conv-modal-note';
    n.id = 'cv-accounts-closed';
    n.textContent = ACC_CLOSED;
    p.insertBefore(n, p.firstChild);
  }
""")
src = ed(src, "    if (!fbDb || !user) return Promise.resolve();\n",
  "    if (!fbDb || !user) return Promise.resolve();\n    if (!accountsOpen() && user.uid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));\n")
src = ed(src, "  function guardedPostWrite(doc) {\n",
  "  function guardedPostWrite(doc) {\n    if (!accountsOpen() && doc.authorUid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));\n")
src = ed(src, "      else composeErr(msg);\n    }\n    if (!isLiveUser()) {\n",
  "      else composeErr(msg);\n    }\n    if (!accountsOpen() && !isAdminUser() && action !== 'report' && action !== 'block') {\n      gateErr(ACC_CLOSED);\n      return false;\n    }\n    if (!isLiveUser()) {\n")
src = ed(src, "    var mode = tab || 'join';\n", "    var mode = tab || 'join';\n    if (mode === 'register' && !accountsOpen()) mode = 'join';\n")
src = ed(src, "        const age = document.getElementById('cv-reg-age');\n",
  "        const age = document.getElementById('cv-reg-age');\n        if (!accountsOpen()) { err.textContent = ACC_CLOSED; err.classList.add('show'); return; }\n")
src = ed(src, "      var age = document.getElementById('cv-google-age');\n",
  "      if (!accountsOpen() && !document.documentElement.classList.contains('acc-stew')) { err.textContent = ACC_CLOSED; err.classList.add('show'); return; }\n      var age = document.getElementById('cv-google-age');\n")
src = ed(src, "      function finishGoogle(cred) {\n        var u = cred && cred.user;\n",
  "      function finishGoogle(cred) {\n        var u = cred && cred.user;\n        if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut().then(function () { throw new Error(ACC_CLOSED); });\n")
src = ed(src, "        fbAuth.getRedirectResult().then(function (cred) {\n          var u = cred && cred.user;\n",
  "        fbAuth.getRedirectResult().then(function (cred) {\n          var u = cred && cred.user;\n          if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut();\n")
src = ed(src, "    wireEvents();\n    document.addEventListener('subx-auth-land'",
  "    wireEvents();\n    applyAccountsGate();\n    document.addEventListener('subx-auth-land'")
# Share menu (port gpchat PR #73 @ 1638eb69, 2026-10-22): x.com Web Intent, neutral labels.
src = ed(src, "data-share=\"x\">Post on X</button>", "data-share=\"x\">Share to x.com</button>")
src = ed(src, "data-share=\"reddit\">Post on Reddit</button>", "data-share=\"reddit\">Share to Reddit</button>")
src = ed(src, "'https://twitter.com/intent/tweet?text='", "'https://x.com/intent/post?text='")
# ---- lean trim (2026-10-22): same code, fewer bytes. No behavior change; see the trim PR for grep evidence.
# Comments that came in from the template / gpchat merge. Their content (kept here for the record):
#   NEST_RESERVED = path segments that must never be a nest; existing nest slugs are checked live.
#   PREVIEW-LIFT block (guards/privacy/steward): a room joins guardedSite only after its factory.js carries
#     guardedPostWrite + the DM lastMsgAt batch.
#   requireVerified: chat/DM replies need signed-in + not killed; Google members can send without emailVerified;
#     post/like/vote/report/block still gate.
#   nestGroupLabel: optional site.nestGroups [{ label, parents }] prints Nests-nav sub-headers; a nest whose parent is
#     another nest's slug is a sub-nest (subsubX), listed under that parent, indented.
#   taxonomyCatalog: Grid taxonomy lives on site.taxonomy (same catalog as taxonomy.json); left-nav nests come from
#     site.nests plus the user's Firestore rooms; taxonomyNestsDraft is not a nav source; topic nestSlug does not drive
#     the watchlist click.
#   SITE_ID is set from site.json siteId in boot().
for c in ["  // Path segments that must never be a nest. Existing nest slugs are checked live.\n",
          "  // ===== PREVIEW-LIFT (guards/privacy/steward) =====\n"
          "  // Port this block plus the call sites named in the PR. A room joins guardedSite\n"
          "  // only after its factory.js carries guardedPostWrite + the DM lastMsgAt batch.\n",
          "  // ===== END PREVIEW-LIFT (guards/privacy/steward) =====\n",
          "    // Chat/DM replies: signed-in + not killed is enough. Google members\n"
          "    // can send without emailVerified. Post/like/vote/report/block still gate.\n",
          "  // Optional site.nestGroups: [{ label, parents: [...] }] prints sub-headers in the Nests nav.\n"
          "  // A nest whose parent is another nest's slug is a sub-nest (subsubX): listed right under that parent, indented.\n",
          "  // Grid taxonomy lives on site.taxonomy (same catalog as taxonomy.json).\n"
          "  // Left-nav nests come from site.nests plus this user's Firestore rooms.\n"
          "  // taxonomyNestsDraft is not a nav source. Topic nestSlug does not drive the watchlist click.\n"]:
    src = ed(src, c, '')
src = ed(src, "  let SITE_ID = '';  // set from site.json siteId in boot()\n", "  let SITE_ID = '';\n")
# Dead: `likes` (template) is read from localStorage once and never used (likes state lives in the posts + LS_LIKES writes).
src = ed(src, "  let likes = loadJSON(LS_LIKES, {});\n", '')
# Duplicate helper: nestSlugNorm(s) has the same body as nestKey(s) in the @nest-feed block. Call nestKey.
src = ed(src, "  function nestSlugNorm(s) {\n    return String(s || '').replace(/^#/, '').trim().toLowerCase();\n  }\n\n", '')
assert len(re.findall(r'\bnestSlugNorm\b', src)) == 16, len(re.findall(r'\bnestSlugNorm\b', src))
src = re.sub(r'\bnestSlugNorm\(', 'nestKey(', src)
assert 'nestSlugNorm' not in src
# ---- Notifications + reports write real docs in every room (2026-10-22, SubX: "make sure notifications and reports
# are created and exist"). Root cause: only replies wrote users/{to}/notifications, and only where site.json
# features.notifs was on (and only if the bell listener had not errored). Like/follow/mention were rendered by
# notifLine() but never written. Reports carried no status, and report errors went to the compose box, which can be
# off-screen or missing, so a refused report looked like nothing happened.
ORIG_REPLY = "  function writeReplyNotif(parentId, text) {\n    var me = liveUid();\n    if (!me || !fbDb || !notifsOn() || notifsError || !isEmailVerified() || !parentId) return;\n    var send = function (authorUid) {\n      if (!authorUid || authorUid === me) return;\n      var payload = {\n        toUid: authorUid,\n        fromUid: me,\n        type: 'reply',\n        siteId: SITE_ID,\n        postId: parentId,\n        read: false,\n        createdAt: firebase.firestore.FieldValue.serverTimestamp()\n      };\n      var snippet = String(text || '').trim().slice(0, 180);\n      if (snippet) payload.text = snippet;\n      fbDb.collection('users').doc(authorUid).collection('notifications').add(payload).catch(function (e) {\n        console.warn('reply notif', e);\n      });\n    };\n    var parent = findPost(parentId);\n    if (parent && parent.authorUid) { send(parent.authorUid); return; }\n    fbDb.collection('posts').doc(parentId).get().then(function (snap) {\n      var d = snap.exists ? (snap.data() || {}) : {};\n      send(d.authorUid || '');\n    }).catch(function (e) { console.warn('reply notif parent', e); });\n  }\n"
# sendNotif(): one writer for reply/like/follow/mention. Writes do not depend on features.notifs (the bell UI still
# does), so every room's members get docs. Like/follow use a fixed doc id: a repeat is an update, which the rules
# refuse (only 'read' may change), so unlike/relike or unfollow/refollow cannot spam the inbox.
# Mentions resolve @handle against authors already loaded in this room's feed (users/{uid} is private by rules),
# at most 5 people per post, and never the parent author who already gets the reply notif for that post.
# writeReplyNotif() runs for every new post: it resolves the parent author (if any), sends the reply notif, then mentions.
src = ed(src, ORIG_REPLY, """  function sendNotif(to, type, postId, text, id) {
    var me = liveUid();
    if (!me || !fbDb || !to || to === me || !isEmailVerified()) return Promise.resolve(false);
    var p = { toUid: to, fromUid: me, type: type, siteId: SITE_ID, read: false, createdAt: firebase.firestore.FieldValue.serverTimestamp() };
    if (postId) p.postId = postId;
    text = String(text || '').trim().slice(0, 180);
    if (text) p.text = text;
    var c = fbDb.collection('users').doc(to).collection('notifications');
    return (id ? c.doc(id).set(p) : c.add(p)).then(function () { return true; }).catch(function (e) { console.warn(type + ' notif', e); return false; });
  }
  function writeMentionNotifs(text, postId, skip) {
    var seen = {}, n = 0;
    seen[liveUid()] = seen[skip] = 1;
    String(text || '').replace(/@([a-z0-9_]{2,15})/gi, function (m, h) {
      h = h.toLowerCase();
      for (var i = 0; i < livePosts.length && n < 5; i++) {
        var u = livePosts[i].authorUid;
        if (u && !seen[u] && String(livePosts[i].handle || '').toLowerCase() === h) { seen[u] = 1; n++; sendNotif(u, 'mention', postId, text); break; }
      }
    });
  }
  function writeReplyNotif(parentId, text, postId) {
    if (!liveUid() || !fbDb || !isEmailVerified()) return;
    var done = function (a) {
      if (parentId) sendNotif(a, 'reply', parentId, text);
      writeMentionNotifs(text, postId, a);
    };
    var parent = parentId && findPost(parentId);
    if (!parentId || (parent && parent.authorUid)) return done(parent && parent.authorUid);
    fbDb.collection('posts').doc(parentId).get().then(function (snap) {
      done(snap.exists ? (snap.data() || {}).authorUid : '');
    }).catch(function (e) { console.warn('reply notif parent', e); done(''); });
  }
""")
src = ed(src, "    }).then(function () {\n      input.value = '';\n",
  "    }).then(function (ref) {\n      writeReplyNotif(parentId, text, ref && ref.id);\n      input.value = '';\n")
src = ed(src, "        writeReplyNotif(parentId, text);\n", "")
src = ed(src, "      patch['likes.' + uid] = true;\n    }\n    fbDb.collection('posts').doc(postId).update(patch).catch(function (err) {\n",
  "      patch['likes.' + uid] = true;\n    }\n    fbDb.collection('posts').doc(postId).update(patch).then(function () {\n      if (!likedBy[uid] && post) sendNotif(post.authorUid, 'like', postId, '', 'like_' + postId + '_' + uid);\n    }).catch(function (err) {\n")
src = ed(src, "    op.then(done).catch(function (e) {\n",
  "    op.then(function () {\n      if (!on) sendNotif(target, 'follow', '', '', 'follow_' + me);\n      done();\n    }).catch(function (e) {\n")
# Reports: status 'open' on create (admin panel + report_watch.cjs treat missing status as open, so old docs still count);
# outcome shown as a toast, not only in the compose box; a refused write says why instead of "Post blocked".
src = ed(src, "    for (i = 0; i < reportItems.length; i++) if (!reportItems[i].status) n++;",
  "    for (i = 0; i < reportItems.length; i++) if (!reportItems[i].status || reportItems[i].status === 'open') n++;")
src = ed(src, "      reason: 'abuse',\n      createdAt: firebase.firestore.FieldValue.serverTimestamp()\n",
  "      reason: 'abuse',\n      status: 'open',\n      createdAt: firebase.firestore.FieldValue.serverTimestamp()\n", 2)
src = ed(src, "      composeErr('Reported. Thanks.');\n", "      toast('Reported. Thanks.');\n", 2)
src = ed(src, "      composeErr(guardPublicErr(e, 'Could not report.'));\n", "      toast(reportErr(e));\n")
src = ed(src, "      composeErr((e && e.message) ? e.message : 'Could not report.');\n", "      toast(reportErr(e));\n")
src = ed(src, "    if (alreadyReported(id)) { composeErr('You already reported this post.'); return; }",
  "    if (alreadyReported(id)) { toast('You already reported this post.'); return; }")
src = ed(src, "      else composeErr(msg);\n",
  "      else composeErr(msg);\n      var ce = document.getElementById('thoughts-compose-err');\n      if ((action === 'report' || action === 'block') && !(ce && ce.offsetParent)) toast(msg);\n")
src = ed(src, "  function composeErr(msg) {\n", """  function toast(m) {
    var t = document.createElement('div');
    t.setAttribute('role', 'status');
    t.textContent = m;
    t.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:9999;padding:10px 16px;border-radius:8px;background:#111;color:#fff;font-size:14px';
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 4000);
  }
  function reportErr(e) {
    return isPermDenied(e) ? 'Report not accepted. Verify your email, then refresh and try again.' : 'Could not report. Try again.';
  }
  function composeErr(msg) {
""")
# ---- A9 pieces 2+3: report loop (2026-10-22, SubX: "report status, My reports and triage; report_update notification").
# Lifecycle open -> reviewing -> actioned | dismissed. Admin triage writes status + reviewedBy/reviewedAt (+ optional
# resolution note, history entry) and sends the reporter a 'report_update' notif. Reporters get "My reports" (status of
# each report they filed in this room). Code lives in the opt-in factory-reports.js (site.json features.reportLoop), so
# core only grows by two stubs, the CORE accessors and one overlay id (budget 255,000 B). Without the file the admin
# panel is the v1.2.2 one (Remove post / Dismiss). Rules: reports update is admin-only (live L400); the reporter reads
# only their own (L390-391, hence the reporterUid filter); live notifications create accepts 'report_update' (type
# <= 20 chars, text <= 280); the pending NOTIFS_REPORTS paste needs RULES_ADDENDUM_REPORT_UPDATE (type enum).
src = ed(src, "        '<button type=\"button\" class=\"post-action\" data-report-dismiss=\"' + escapeHtml(r.id) + '\">Dismiss</button>' +\n",
  "        reportTriage(r) +\n")
src = ed(src, "    var rows = reportItems.filter(function (r) { return r.status !== 'dismissed'; }).slice(0, 50);",
  "    var rows = reportItems.filter(function (r) { return r.status !== 'dismissed' && r.status !== 'actioned'; }).slice(0, 50);")
src = ed(src, "  function syncReportsEntry() {\n", "  function syncReportsEntry() {\n    syncMyReports();\n")
src = ed(src, "'profile-overlay', 'reports-overlay'].forEach(", "'profile-overlay', 'reports-overlay', 'myreports-overlay'].forEach(")
src = ed(src, "  function stopPreviewLift() {\n", """  // Report loop (factory-reports.js): status labels shown to the admin and to the reporter.
  var REPORT_STATUS = { open: 'Received', reviewing: 'Under review', actioned: 'Action taken', dismissed: 'Reviewed, no action' };
  var reportLoopWired = false;
  function reportTriage(r) {
    var b = function (st, label) {
      return '<button type="button" class="post-action" data-report-status="' + st + '" data-report-id="' + escapeHtml(r.id) +
        '" data-report-uid="' + escapeHtml(r.reporterUid) + '">' + label + '</button> ';
    };
    return '<p>' + escapeHtml(REPORT_STATUS[r.status || 'open'] || r.status) + '</p>' +
      (r.status === 'reviewing' ? '' : b('reviewing', 'Reviewing')) + b('actioned', 'Action taken') + b('dismissed', 'Dismiss');
  }
  function reportUpdateText(status, note) {
    var t = status === 'reviewing' ? 'Your report is under review.' :
      (status === 'actioned' || status === 'action_taken') ? 'SubX reviewed and took action on your report.' : 'SubX reviewed your report. No action was needed.';
    return t + (note ? ' ' + note : '');
  }
  function setReportStatus(id, status, reporterUid) {
    var me = liveUid();
    if (me !== ADMIN_UID || !fbDb || !id || !REPORT_STATUS[status] || status === 'open') return;
    var note = '';
    if (status !== 'reviewing') {
      note = window.prompt('Note to the reporter (optional, 120 chars):', '');
      if (note === null) return;
      note = String(note).replace(/\\s+/g, ' ').trim().slice(0, 120);
    }
    var patch = {
      status: status,
      reviewedBy: me,
      reviewedAt: firebase.firestore.FieldValue.serverTimestamp(),
      history: firebase.firestore.FieldValue.arrayUnion({ status: status, by: me, ms: Date.now() })
    };
    if (note) patch.resolution = note;
    fbDb.collection('reports').doc(id).update(patch).then(function () {
      if (!reporterUid) { toast('Report: ' + REPORT_STATUS[status]); return; }
      return Promise.resolve(sendNotif(reporterUid, 'report_update', '', reportUpdateText(status, note), 'report_update_' + id + '_' + status)).then(function (ok) {
        toast(ok === false ? 'Report updated; notification could not be sent.' : 'Report: ' + REPORT_STATUS[status]);
      });
    }).catch(function (e) {
      console.warn('report status', e);
      toast('Could not update that report. Try again.');
    });
  }
  function syncMyReports() {
    wireReportLoop();
    var nav = document.querySelector('#sidebar nav ul');
    var link = document.getElementById('nav-myreports');
    if (!isLiveUser() || liveUid() === ADMIN_UID) {
      if (link && link.parentNode) link.parentNode.remove();
      closeMyReports();
      return;
    }
    if (!link && nav) {
      var li = document.createElement('li');
      li.innerHTML = '<button type="button" class="nav-social-link" id="nav-myreports" data-myreports="1" ' +
        'style="cursor:pointer;width:100%;background:none;border:0;font:inherit;text-align:left">My reports</button>';
      nav.appendChild(li);
    }
  }
  function openMyReports() {
    var me = liveUid();
    if (!me || !fbDb) return;
    closeSocialOverlays();
    var el = document.getElementById('myreports-overlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'myreports-overlay';
      el.className = 'notif-overlay';
      el.innerHTML = '<button class="view-back" id="myreports-back" type="button">Back</button>' +
        '<div class="notif-header"><div class="notif-title">My reports</div></div>' +
        '<div class="notif-list" id="myreports-list"></div>';
      document.body.appendChild(el);
    }
    el.classList.add('active');
    var list = document.getElementById('myreports-list');
    list.innerHTML = '<div class="soon-panel">Loading...</div>';
    fbDb.collection('reports').where('siteId', '==', SITE_ID).where('reporterUid', '==', me).get().then(function (snap) {
      list.innerHTML = myReportsHtml(snap.docs.map(function (d) { var x = d.data() || {}; x.id = d.id; return x; }));
    }).catch(function (e) {
      console.warn('my reports', e);
      list.innerHTML = '<div class="soon-panel">Could not load your reports. Try again.</div>';
    });
  }
  function myReportsHtml(rows) {
    rows.sort(function (a, b) { return tsMillis(b.createdAt) - tsMillis(a.createdAt); });
    if (!rows.length) return '<div class="soon-panel"><strong>You have not reported anything in this room.</strong></div>';
    return rows.slice(0, 50).map(function (r) {
      var post = findPost(r.postId);
      var snip = (post && post.text) ? String(post.text).replace(/\\s+/g, ' ').trim().slice(0, 140) : '(post not loaded)';
      return '<div class="notif-item"><p>' + escapeHtml(snip) + '</p><p><strong>' +
        escapeHtml(REPORT_STATUS[r.status || 'open'] || 'Received') + '</strong> · ' + escapeHtml(notifWhen(tsMillis(r.createdAt))) + '</p>' +
        (r.resolution ? '<p>' + escapeHtml(r.resolution) + '</p>' : '') + '</div>';
    }).join('');
  }
  function closeMyReports() {
    var el = document.getElementById('myreports-overlay');
    if (el) el.classList.remove('active');
  }
  function wireReportLoop() {
    if (reportLoopWired) return;
    reportLoopWired = true;
    document.addEventListener('click', function (e) {
      var t = e.target && e.target.closest ? e.target : null;
      if (!t) return;
      var st = t.closest('[data-report-status]');
      if (st) {
        setReportStatus(st.getAttribute('data-report-id'), st.getAttribute('data-report-status'), st.getAttribute('data-report-uid'));
        return;
      }
      if (t.closest('[data-myreports]')) { e.preventDefault(); openMyReports(); return; }
      if (t.closest('#myreports-back')) { closeMyReports(); return; }
      // report_update notifs carry no postId, so the core notif handler only marks them read; then show My reports.
      if (t.closest('[data-notif-type="report_update"]')) setTimeout(openMyReports, 0);
    });
  }
  function stopPreviewLift() {
""")
# ---- Auto-hide on report + instant alert (2026-10-22, SubX: "Even having an image up for an hour, could cause irreparable harm").
# Client batch-writes reports/{autoId} + hides/{siteId}_{postId} for ncii/copyright/violent_offensive/hate/impersonation/csam
# (falling back to report-only if the hides rule is not published yet). Every feed/story/profile/notif ingress point filters
# hidden postIds so neither text nor imageUrl/mediaUrl renders on any client. Only the admin (ADMIN_UID) can restore by deleting hides/{id}.
src = ed(src, "  var reportItems = [];\n  var reportsUnsub = null;\n  var reportedMem = {};\n",
  "  var reportItems = [];\n  var reportsUnsub = null;\n  var reportedMem = {};\n  var hiddenIds = {};\n  var hidesUnsub = null;\n  var HIDE_REASONS = { ncii: 1, copyright: 1, violent_offensive: 1, hate: 1, impersonation: 1, csam: 1 };\n")
src = ed(src, "  function isAdminUser() {\n    return liveUid() === ADMIN_UID;\n  }\n", """  function isAdminUser() {
    return liveUid() === ADMIN_UID;
  }
  function isPostHidden(p) {
    return !!(p && (hiddenIds[p.id] || (p.parentId && hiddenIds[p.parentId]) || (p.authorUid && hiddenIds['uid:' + p.authorUid])));
  }
  function isStoryHidden(s) {
    return !!(s && (hiddenIds['story:' + s.id] || hiddenIds[s.id] || (s.authorUid && hiddenIds['uid:' + s.authorUid])));
  }
  function listenHides() {
    if (hidesUnsub) { hidesUnsub(); hidesUnsub = null; }
    if (!fbDb || !SITE_ID) return;
    hidesUnsub = fbDb.collection('hides').where('siteId', '==', SITE_ID).onSnapshot(function (snap) {
      var next = {};
      snap.forEach(function (d) { d = d.data() || {}; if (d.postId) next[d.postId] = true; });
      hiddenIds = next;
      renderFeed();
      if (typeof renderStoriesTray === 'function') renderStoriesTray();
      if (currentUser) syncProfile();
      renderNotifs();
      renderReports();
    }, function () {});
  }
  function pickReportReason(done) {
    if (pickReportReason._open) return;
    pickReportReason._open = true;
    var ov = document.createElement('div'), box = document.createElement('div'), h = document.createElement('h2'), note = document.createElement('p'), more = document.createElement('p'), a = document.createElement('a');
    ov.className = 'conv-modal-overlay open';
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');
    ov.setAttribute('aria-label', 'Report');
    box.className = 'conv-modal';
    h.textContent = 'Report';
    note.className = 'conv-modal-note';
    note.textContent = 'Why are you reporting this?';
    box.appendChild(h);
    box.appendChild(note);
    function onKey(e) { if (e && e.key === 'Escape') { if (e.preventDefault) e.preventDefault(); close(null); } }
    function close(reason) {
      if (!pickReportReason._open) return;
      pickReportReason._open = false;
      document.removeEventListener('keydown', onKey, true);
      if (ov.parentNode) ov.parentNode.removeChild(ov);
      if (done) done(reason || null);
    }
    function btn(label, cls, reason) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = cls;
      if (reason) b.setAttribute('data-reason', reason);
      b.textContent = label;
      b.addEventListener('click', function () { close(reason); });
      box.appendChild(b);
      return b;
    }
    var opts = [
      { code: 'ncii', label: 'Intimate image without consent' },
      { code: 'copyright', label: 'Copyright or trademark (DMCA)' },
      { code: 'violent_offensive', label: 'Violent or graphic image' },
      { code: 'hate', label: 'Hateful or racist image' },
      { code: 'other', label: 'Other abuse or rule-breaking' }
    ];
    var first = null;
    opts.forEach(function (o, i) { var b = btn(o.label, 'conv-modal-submit', o.code); if (!i) first = b; });
    btn('Cancel', 'conv-guest-btn', null);
    more.className = 'conv-modal-note';
    a.href = 'report.html';
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'How reports work, and how to send a removal request';
    more.appendChild(a);
    box.appendChild(more);
    ov.addEventListener('click', function (e) { if (e && e.target === ov) close(null); });
    document.addEventListener('keydown', onKey, true);
    ov.appendChild(box);
    document.body.appendChild(ov);
    try { if (first) first.focus(); } catch (e) {}
  }
  function commitAutoHideReport(postId, targetUid, storyId, reason, fallbackAdd) {
    var me = liveUid(), rRef = fbDb.collection('reports').doc(), ts = firebase.firestore.FieldValue.serverTimestamp();
    var rDoc = { siteId: SITE_ID, postId: postId, targetUid: targetUid || '', reporterUid: me, reason: reason, status: 'open', createdAt: ts };
    if (storyId) rDoc.storyId = storyId;
    hiddenIds[postId] = true;
    renderFeed();
    if (typeof renderStoriesTray === 'function') renderStoriesTray();
    var b = fbDb.batch();
    b.set(rRef, rDoc);
    b.set(fbDb.collection('hides').doc(SITE_ID + '_' + postId), { siteId: SITE_ID, postId: postId, reportId: rRef.id, reporterUid: me, createdAt: ts });
    b.set(fbDb.collection('rateLimits').doc(me), { lastHideAt: ts }, { merge: true });
    return b.commit().catch(function (e) {
      if (isPermDenied(e) && fallbackAdd) return fallbackAdd();
      throw e;
    });
  }
""")
src = ed(src, "  function writeReportAlert(post, me) {\n    if (!me || me === ADMIN_UID || !fbDb || !post) return;\n    var snippet = String(post.text || '').replace(/\\s+/g, ' ').trim().slice(0, 180);\n    fbDb.collection('users').doc(ADMIN_UID).collection('notifications').add({\n      toUid: ADMIN_UID,\n      fromUid: me,\n      type: 'report',\n      siteId: SITE_ID,\n      postId: post.id,\n      read: false,\n      text: 'Report: ' + snippet,\n      createdAt: firebase.firestore.FieldValue.serverTimestamp()\n    }).catch(function (e) { console.warn('report alert', e); });\n  }",
  """  function writeReportAlert(post, me, reason) {
    if (!me || me === ADMIN_UID || !fbDb || !post) return;
    var hide = HIDE_REASONS[reason] || isPostHidden(post);
    var snippet = hide ? ('[' + (reason || 'hidden') + ' · auto-hidden]') : String(post.text || '').replace(/\\s+/g, ' ').trim().slice(0, 180);
    fbDb.collection('users').doc(ADMIN_UID).collection('notifications').add({
      toUid: ADMIN_UID,
      fromUid: me,
      type: 'report',
      siteId: SITE_ID,
      postId: post.id,
      read: false,
      text: 'Report: ' + snippet,
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    }).catch(function (e) { console.warn('report alert', e); });
  }""")
src = ed(src, "  function reportPost(id) {\n    if (!requireVerified('report')) return;\n    var post = findPost(id);\n    if (!post || !fbDb || isSessionSeedPost(post)) return;\n    if (alreadyReported(id)) { toast('You already reported this post.'); return; }\n    var me = liveUid();\n    fbDb.collection('reports').add({\n      siteId: SITE_ID,\n      postId: id,\n      targetUid: post.authorUid || '',\n      reporterUid: me,\n      reason: 'abuse',\n      status: 'open',\n      createdAt: firebase.firestore.FieldValue.serverTimestamp()\n    }).then(function () {\n      markReported(id);\n      toast('Reported. Thanks.');\n      writeReportAlert(post, me);\n    }).catch(function (e) {\n      toast(reportErr(e));\n    });\n  }",
  """  function reportPost(id, optReason) {
    if (!requireVerified('report')) return;
    var post = findPost(id);
    if (!post || !fbDb || isSessionSeedPost(post)) return;
    if (alreadyReported(id)) { toast('You already reported this post.'); return; }
    if (!optReason) { pickReportReason(function (r) { if (r) reportPost(id, r); }); return; }
    var reason = optReason, me = liveUid();
    var addOnly = function () {
      return fbDb.collection('reports').add({
        siteId: SITE_ID,
        postId: id,
        targetUid: post.authorUid || '',
        reporterUid: me,
        reason: reason,
        status: 'open',
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      });
    };
    var op = HIDE_REASONS[reason] ? commitAutoHideReport(id, post.authorUid || '', '', reason, addOnly) : addOnly();
    op.then(function () {
      markReported(id);
      toast(HIDE_REASONS[reason] ? 'Reported and hidden pending review.' : 'Reported. Thanks.');
      writeReportAlert(post, me, reason);
    }).catch(function (e) {
      toast(reportErr(e));
    });
  }""")
src = ed(src, "  function reportStory(id) {\n    if (!requireVerified('report')) return;\n    var story = findStory(id);\n    if (!story || !fbDb) return;\n    fbDb.collection('reports').add({\n      siteId: SITE_ID,\n      storyId: id,\n      postId: 'story:' + id,\n      targetUid: story.authorUid || '',\n      reporterUid: liveUid(),\n      reason: 'abuse',\n      status: 'open',\n      createdAt: firebase.firestore.FieldValue.serverTimestamp()\n    }).then(function () {\n      toast('Reported. Thanks.');\n    }).catch(function (e) {\n      toast(reportErr(e));\n    });\n  }",
  """  function reportStory(id, optReason) {
    if (!requireVerified('report')) return;
    var story = findStory(id);
    if (!story || !fbDb) return;
    if (!optReason) { pickReportReason(function (r) { if (r) reportStory(id, r); }); return; }
    var reason = optReason, me = liveUid(), pid = 'story:' + id;
    var addOnly = function () {
      return fbDb.collection('reports').add({
        siteId: SITE_ID,
        storyId: id,
        postId: pid,
        targetUid: story.authorUid || '',
        reporterUid: me,
        reason: reason,
        status: 'open',
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      });
    };
    var op = HIDE_REASONS[reason] ? commitAutoHideReport(pid, story.authorUid || '', id, reason, addOnly) : addOnly();
    op.then(function () {
      toast(HIDE_REASONS[reason] ? 'Reported and hidden pending review.' : 'Reported. Thanks.');
      writeReportAlert({ id: pid, text: story.text || '' }, me, reason);
    }).catch(function (e) {
      toast(reportErr(e));
    });
  }""")
src = ed(src, "  function findPost(id) {\n    var i;\n    for (i = 0; i < livePosts.length; i++) if (livePosts[i].id === id) return livePosts[i];\n    for (i = 0; i < nestPosts.length; i++) if (nestPosts[i].id === id) return nestPosts[i];\n",
  "  function findPost(id) {\n    if (hiddenIds[id]) return null;\n    var i;\n    for (i = 0; i < livePosts.length; i++) if (livePosts[i].id === id && !isPostHidden(livePosts[i])) return livePosts[i];\n    for (i = 0; i < nestPosts.length; i++) if (nestPosts[i].id === id && !isPostHidden(nestPosts[i])) return nestPosts[i];\n")
src = ed(src, "  function topLevelPosts() {\n    return postsForFeed().filter(function (p) {\n      if (p.parentId || (p.authorUid && blockedUids[p.authorUid])) return false;\n",
  "  function topLevelPosts() {\n    return postsForFeed().filter(function (p) {\n      if (p.parentId || isPostHidden(p) || (p.authorUid && blockedUids[p.authorUid])) return false;\n")
src = ed(src, "  function repliesFor(parentId) {\n    return postsForFeed().filter(function (p) { return p.parentId === parentId && !(p.authorUid && blockedUids[p.authorUid]); })\n",
  "  function repliesFor(parentId) {\n    if (hiddenIds[parentId]) return [];\n    return postsForFeed().filter(function (p) { return p.parentId === parentId && !isPostHidden(p) && !(p.authorUid && blockedUids[p.authorUid]); })\n")
src = ed(src, "    var posts = livePosts.filter(function (p) {\n      if (!p || p.parentId) return false;\n      if (p.authorUid && blockedUids[p.authorUid]) return false;\n",
  "    var posts = livePosts.filter(function (p) {\n      if (!p || p.parentId || isPostHidden(p)) return false;\n      if (p.authorUid && blockedUids[p.authorUid]) return false;\n")
src = ed(src, "  function renderPostMedia(post) {\n    var html = '';\n",
  "  function renderPostMedia(post) {\n    if (isPostHidden(post)) return '';\n    var html = '';\n")
src = ed(src, "  function renderPost(post, isReply) {\n    const uid = liveUid();\n",
  "  function renderPost(post, isReply) {\n    if (isPostHidden(post)) return '';\n    const uid = liveUid();\n")
src = ed(src, "  function siteNotifs() {\n    return notifItems.filter(function (n) { return !n.siteId || n.siteId === SITE_ID; });\n  }\n",
  "  function siteNotifs() {\n    return notifItems.filter(function (n) { return (!n.siteId || n.siteId === SITE_ID) && !(n.postId && hiddenIds[n.postId] && n.type !== 'report' && n.type !== 'report_update'); });\n  }\n")
src = ed(src, "  function findStory(id) {\n    for (var i = 0; i < liveStories.length; i++) if (liveStories[i].id === id) return liveStories[i];\n    return null;\n  }\n",
  "  function findStory(id) {\n    if (hiddenIds['story:' + id] || hiddenIds[id]) return null;\n    for (var i = 0; i < liveStories.length; i++) if (liveStories[i].id === id && !isStoryHidden(liveStories[i])) return liveStories[i];\n    return null;\n  }\n")
src = ed(src, "    liveStories.forEach(function (s) {\n      if (s.siteId && s.siteId !== SITE_ID) return;\n      if (s.expiresAtMs && s.expiresAtMs <= now) return;\n",
  "    liveStories.forEach(function (s) {\n      if (isStoryHidden(s)) return;\n      if (s.siteId && s.siteId !== SITE_ID) return;\n      if (s.expiresAtMs && s.expiresAtMs <= now) return;\n")
src = ed(src, "    var story = storyViewerList[storyViewerIdx];\n    if (!story) { closeStoriesViewer(); return; }\n",
  "    var story = storyViewerList[storyViewerIdx];\n    if (!story || isStoryHidden(story)) { closeStoriesViewer(); return; }\n")
src = ed(src, "    for (i = 0; i < posts.length; i++) {\n      var post = posts[i];\n      if (!post || post.parentId) continue;\n",
  "    for (i = 0; i < posts.length; i++) {\n      var post = posts[i];\n      if (!post || post.parentId || isPostHidden(post)) continue;\n")
src = ed(src, "  function nestHasActivity(slug) {\n    var key = nestKey(slug);\n    if (!key) return false;\n    for (var i = 0; i < livePosts.length; i++) {\n      if (nestKey(livePosts[i].nestSlug) === key) return true;\n    }\n    return false;\n  }\n",
  "  function nestHasActivity(slug) {\n    var key = nestKey(slug);\n    if (!key) return false;\n    for (var i = 0; i < livePosts.length; i++) {\n      if (!isPostHidden(livePosts[i]) && nestKey(livePosts[i].nestSlug) === key) return true;\n    }\n    return false;\n  }\n")
src = ed(src, "    const mine = livePosts.filter(function (p) { return p.authorUid && p.authorUid === uid; });\n",
  "    const mine = livePosts.filter(function (p) { return p.authorUid && p.authorUid === uid && !isPostHidden(p); });\n")
src = ed(src, "      listenKillSwitch();\n      listenLivePosts();\n      initStories();\n",
  "      listenKillSwitch();\n      listenHides();\n      listenLivePosts();\n      initStories();\n")
src = ed(src, "    el.innerHTML = rows.map(function (r) {\n      var post = findPost(r.postId);\n      var snippet = (post && post.text) ? String(post.text).replace(/\\s+/g, ' ').trim().slice(0, 180) : '(post unavailable)';\n      var count = reporterCount(r.postId);\n      return '<div class=\"notif-item\">' +\n        '<p>' + escapeHtml(snippet) + '</p>' +\n        '<p>' + count + ' reporter' + (count === 1 ? '' : 's') + '</p>' +\n        '<button type=\"button\" class=\"post-action\" data-report-remove=\"' + escapeHtml(r.postId) + '\">Remove post</button> ' +\n        reportTriage(r) +\n        '</div>';\n    }).join('');",
  """    el.innerHTML = rows.map(function (r) {
      var isHid = !!(hiddenIds[r.postId] || HIDE_REASONS[r.reason]);
      var post = isHid ? null : findPost(r.postId);
      var snippet = isHid ? ('[Hidden: ' + (r.reason || 'reported') + ' · ' + r.postId + ']') :
        ((post && post.text) ? String(post.text).replace(/\\s+/g, ' ').trim().slice(0, 180) : '(post not loaded)');
      var count = reporterCount(r.postId);
      return '<div class="notif-item"' + (isHid ? ' style="opacity:0.65"' : '') + '>' +
        '<p>' + escapeHtml(snippet) + '</p>' +
        '<p>' + count + ' reporter' + (count === 1 ? '' : 's') + (r.reason ? ' · ' + escapeHtml(r.reason) : '') + '</p>' +
        '<button type="button" class="post-action" data-report-remove="' + escapeHtml(r.postId) + '">Remove post</button> ' +
        reportTriage(r) +
        '</div>';
    }).join('');""")
src = ed(src, "  function reportTriage(r) {\n    var b = function (st, label) {\n      return '<button type=\"button\" class=\"post-action\" data-report-status=\"' + st + '\" data-report-id=\"' + escapeHtml(r.id) +\n        '\" data-report-uid=\"' + escapeHtml(r.reporterUid) + '\">' + label + '</button> ';\n    };\n    return '<p>' + escapeHtml(REPORT_STATUS[r.status || 'open'] || r.status) + '</p>' +\n      (r.status === 'reviewing' ? '' : b('reviewing', 'Reviewing')) + b('actioned', 'Action taken') + b('dismissed', 'Dismiss');\n  }",
  """  function restoreHiddenReport(postId, reportId) {
    var me = liveUid();
    if (me !== ADMIN_UID || !fbDb || !postId) return;
    if (!window.confirm('Restore ' + postId + ' to the room? Only admin can restore hidden content.')) return;
    fbDb.collection('hides').doc(SITE_ID + '_' + postId).delete().then(function () {
      delete hiddenIds[postId];
      if (reportId) {
        fbDb.collection('reports').doc(reportId).update({
          status: 'dismissed',
          reviewedBy: me,
          reviewedAt: firebase.firestore.FieldValue.serverTimestamp(),
          resolution: 'Restored by admin',
          history: firebase.firestore.FieldValue.arrayUnion({ status: 'restored', by: me, ms: Date.now() })
        }).catch(function () {});
      }
      renderFeed();
      renderReports();
      toast('Restored.');
    }).catch(function (e) { toast((e && e.message) || 'Could not restore.'); });
  }
  function adminMassHide(reason) {
    var me = liveUid();
    if (me !== ADMIN_UID || !fbDb) return;
    var open = reportItems.filter(function (r) { return r.status !== 'dismissed' && r.status !== 'actioned' && (!reason || r.reason === reason); });
    if (!open.length) { toast('No matching open reports.'); return; }
    var b = fbDb.batch();
    var ts = firebase.firestore.FieldValue.serverTimestamp();
    open.slice(0, 20).forEach(function (r) {
      if (!r.postId) return;
      hiddenIds[r.postId] = true;
      b.set(fbDb.collection('hides').doc(SITE_ID + '_' + r.postId), {
        siteId: SITE_ID, postId: r.postId, reportId: r.id, reporterUid: me, reason: r.reason || 'ncii', createdAt: ts
      });
    });
    renderFeed();
    renderReports();
    b.commit().then(function () { toast('Hidden ' + open.length + ' reported items.'); }).catch(function (e) { toast((e && e.message) || 'Mass-hide failed.'); });
  }
  function reportTriage(r) {
    var b = function (st, label) {
      return '<button type="button" class="post-action" data-report-status="' + st + '" data-report-id="' + escapeHtml(r.id) +
        '" data-report-uid="' + escapeHtml(r.reporterUid) + '">' + label + '</button> ';
    };
    var rest = ((hiddenIds && hiddenIds[r.postId]) || (HIDE_REASONS && HIDE_REASONS[r.reason]))
      ? '<button type="button" class="post-action" data-report-restore="' + escapeHtml(r.postId) + '" data-report-id="' + escapeHtml(r.id) + '">Restore</button> '
      : '';
    return '<p>' + escapeHtml(REPORT_STATUS[r.status || 'open'] || r.status) + '</p>' +
      rest + (r.status === 'reviewing' ? '' : b('reviewing', 'Reviewing')) + b('actioned', 'Action taken') + b('dismissed', 'Dismiss');
  }""")
src = ed(src, "      if (t.closest('[data-myreports]')) { e.preventDefault(); openMyReports(); return; }\n",
  "      var rb = t.closest('[data-report-restore]');\n      if (rb) { restoreHiddenReport(rb.getAttribute('data-report-restore'), rb.getAttribute('data-report-id')); return; }\n      if (t.closest('[data-mass-hide]')) { adminMassHide(t.closest('[data-mass-hide]').getAttribute('data-mass-hide')); return; }\n      if (t.closest('[data-myreports]')) { e.preventDefault(); openMyReports(); return; }\n")
# Lean CSS whitespace trim for core byte budget (255,000 B):
for css_fn in ['ensureRailCss', 'ensurePreviewLiftCss', 'ensureDmCss', 'ensureEarlyWelcomeCss', 'ensureJoinAuthCss', 'ensureShareSheet', 'ensureStoriesComposer', 'ensureStoriesViewer', 'ensureStoriesTray', 'paintStoryViewer', 'renderStoriesTray', 'initStories', 'openDisplayNamePrompt', 'renderSidebarAuth', 'renderThreads', 'ensureNestNav', 'renderPostMedia', 'renderPost', 'renderTrendCard', 'factCardHtml', 'porchCardHtml', 'showRailOverlay', 'renderExplore', 'renderNotifs', 'openAdminPicker', 'fillExploreNests', 'ensureReportsPanel']:
    m = re.search(r'  function ' + css_fn + r'\([^)]*\) \{[\s\S]*?\n  \}\n', src)
    assert m, css_fn
    blk = m.group(0)
    blk2 = re.sub(r"' \+\n\s+'", "", blk)
    src = src.replace(blk, blk2, 1)
for ind_fn in ['wireEvents', 'wireComposeToolbar', 'sendDm', 'ensureShareSheet', 'ensureStoriesComposer', 'paintStoryViewer']:
    m = re.search(r'  (?:async )?function ' + ind_fn + r'\([^)]*\) \{[\s\S]*?\n  \}\n', src)
    assert m, ind_fn
    blk = m.group(0)
    blk2 = re.sub(r'\n    ', '\n   ', blk)
    src = src.replace(blk, blk2, 1)
# Legal/privacy string sweeps (Workstream 1 d09ef72):
src = src.replace("/rail (jebb@subx.it)", "/rail (takedown@subx.it)")
src = src.replace("Welcome sends need the factory admin Google (jebb.dykstra@gmail.com). This signed-in account is not that admin.", "Welcome sends require the factory admin account. This signed-in account is not that admin.")
# AI steward label: admin-authored posts without steward:true get the same pill as steward:true (2026-10-24).
_sp_old = "    if (post && post.steward) {\n"
_sp_new = "    if (post && (post.steward || post.isAdminAuthor)) {\n"
_sp_drop = "    if (post && post.isAdminAuthor) return '<span class=\"post-steward-pill\">Steward</span>';\n"
assert src.count(_sp_old) == 1 and src.count(_sp_drop) == 1, 'stewardPillHtml fallback sweep'
src = src.replace(_sp_old, _sp_new, 1).replace(_sp_drop, '', 1)
# Copy sweep (FACT bar 2026-10-24): no em/en dashes in visible strings. These three come from
# merge hunks or gpchat functions, so they are swept here instead of in the template.
for _a, _b in [("<strong>Following \u2014 Soon.</strong>", "<strong>Following: Soon.</strong>"),
               ("<strong>Notifications \u2014 Soon.</strong>", "<strong>Notifications: Soon.</strong>"),
               ("'Reply in the compose box \u2014 this is a session ask.'", "'Reply in the compose box. This is a session ask.'")]:
    assert src.count(_a) == 1, ('copy sweep', _a)
    src = src.replace(_a, _b)
src = banner + src
open('factory.js', 'w').write(src)
