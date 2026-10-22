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
    "        ? 'This nest could not load. The error is in the compose line above — this is not an empty room.'\n"
    "        : 'Live feed could not load. The error is in the compose line above — this is not an empty room.') + '</div>';\n"
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
R['openAdminPicker'] = ed(G['openAdminPicker'], "'<div class=\"soon-panel\">No gpchat users yet.</div>'", "'<div class=\"soon-panel\">No ' + escapeHtml((site && site.name) || SITE_ID) + ' users yet.</div>'")
R['paintProfile'] = ed(T['paintProfile'], "'<div class=\"empty-note\" id=\"profile-posts-empty\">No posts yet. Official 311 is the handoff at the top of Home. Sign in to talk with neighbors.</div>'",
  "'<div class=\"empty-note\" id=\"profile-posts-empty\">' + escapeHtml(skin('profileEmpty', 'No posts yet.')) + '</div>'")
R['syncProfile'] = ed(G['syncProfile'], 'currentUser.bio || "Talking about the city.",', "currentUser.bio || skin('bioDefault', ''),")
R['renderSidebarAuth'] = ed(T['renderSidebarAuth'], 'av.textContent = "CO";', "av.textContent = skin('avatarInitials', String(SITE_ID || 'S').replace(/chat$/i, '').slice(0, 3).toUpperCase());")
s = T['stubSignIn']
s = ed(s, "(handle || 'guest311')", "(handle || 'guest')"); s = ed(s, "|| 'guest311',", "|| 'guest',")
s = ed(s, 'bio: "Unofficial helper — not a substitute for 911.",', "bio: skin('bioDefault', ''),")
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
  "boot({ siteId: (location.hostname || 'room').replace(/^www\\./, '').replace(/\\.[a-z]+$/, ''), name: (location.hostname || 'SubX').replace(/^www\\./, ''), tagline: '' });")
src = src.replace("name: 'Grid', symbolPrefix", "name: 'Topics', symbolPrefix").replace("tax.name || 'Grid'", "tax.name || 'Topics'").replace("(taxName || 'Grid')", "(taxName || 'Topics')").replace("'Not on the Grid'", "'Not in this room'").replace("That topic is not on the Grid.", "That topic is not in this room.")
# Jebb rule (2026-10-22): no 13+ anywhere. A room without site.json minAge gets the 18+ gate.
src = ed(src, "    if (!isFinite(n) || n < 1) return 13;\n", "    if (!isFinite(n) || n < 1) return 18;\n")
# Accounts gate (2026-10-22). Ported from gpchat accountsOpen()/applyAccountsGate(). Re-scoped the same day after Jebb's
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
# ---- Notifications + reports write real docs in every room (2026-10-22, Jebb: "make sure notifications and reports
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
    if (!me || !fbDb || !to || to === me || !isEmailVerified()) return;
    var p = { toUid: to, fromUid: me, type: type, siteId: SITE_ID, read: false, createdAt: firebase.firestore.FieldValue.serverTimestamp() };
    if (postId) p.postId = postId;
    text = String(text || '').trim().slice(0, 180);
    if (text) p.text = text;
    var c = fbDb.collection('users').doc(to).collection('notifications');
    (id ? c.doc(id).set(p) : c.add(p)).catch(function (e) { console.warn(type + ' notif', e); });
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
src = banner + src
open('factory.js', 'w').write(src)
