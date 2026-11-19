#!/usr/bin/env python3
"""Turn the folded v1.2.10 core into the room v1.2.11 factory.js (sha256 f18d07e4).

Featured articles ride a lazy addon(). This is the base the stories split reads.
"""
import hashlib, pathlib, re, sys
RAIL = "  function ensureRailCss() {\n    addCss('rail-porch-css', '.news-item{display:block;padding:1rem 1.4rem;border-bottom:1px solid rgba(255,255,255,0.06);}a.news-item{text-decoration:none;cursor:pointer;}.porch-btns{display:flex;gap:0.45rem;margin:0.45rem 0 0.2rem;flex-wrap:wrap;}.porch-btn{font:inherit;font-size:0.78rem;font-weight:600;padding:0.35rem 0.8rem;border-radius:999px;border:1px solid rgba(255,255,255,0.22);background:rgba(255,255,255,0.08);color:#f0f4f7;cursor:pointer;}.porch-btn:hover{background:rgba(255,255,255,0.16);}.porch-btn-picked{border-color:var(--accent,#e07a3d);background:rgba(224,122,61,0.28);box-shadow:inset 0 0 0 1px var(--accent,#e07a3d);}.porch-tally{font-size:0.75rem;line-height:1.4;color:#8aa0b0;margin:0.28rem 0 0.1rem;}.news-page-list .news-item{background:var(--surface,#f4f7fa);border:1px solid var(--border,#c9d5de);border-radius:10px;padding:1.05rem 1.15rem;}.news-page-list .porch-btn{border-color:var(--border,#c9d5de);background:#fff;color:var(--text,#12202c);}.news-page-list .porch-btn:hover{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);}.news-page-list .porch-btn-picked{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);background:rgba(192,54,44,0.08);}.news-page-list .porch-tally{color:var(--text-muted,#4a5f66);}[data-porch-dwell] .news-item-porch{padding-top:1.25rem;padding-bottom:1.25rem;}' + (featureOn('topicFollow') ? '.news-item{padding:1rem 2.8rem 1rem 1.4rem;position:relative;}a.news-item,.news-item-main{text-decoration:none;cursor:pointer;color:inherit;display:block;padding-right:2.15rem;}.news-follow-btn{position:absolute;top:0.75rem;right:0.85rem;z-index:2;width:28px;height:28px;padding:0;border-radius:999px;border:1px solid var(--accent,#e10600);background:transparent;color:var(--accent,#e10600);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;}.news-follow-btn:hover{background:rgba(225,6,0,0.14);}.news-follow-btn:focus-visible{outline:2px solid var(--accent,#e10600);outline-offset:2px;}.news-follow-btn.is-following{background:var(--accent,#e10600);color:#fff;border-color:var(--accent,#e10600);}.news-page-list .news-follow-btn{border-color:var(--accent,#c0362c);color:var(--accent,#c0362c);}.news-page-list .news-follow-btn.is-following{background:var(--accent,#c0362c);color:#fff;border-color:var(--accent,#c0362c);}' : ''));\n  }\n"
p = pathlib.Path('factory.js')
t = p.read_text()
ROOM = 'f18d07e4db5aaa2722f284aba542eb6b41a48699ae2bad0c54bbec5e558a29d0'
if hashlib.sha256(t.encode()).hexdigest() == ROOM:
    sys.exit(0)
addon = "  function addon(n){var s=document.createElement('script');s.src=FACTORY_SRC?FACTORY_SRC.replace(/factory\\.js(\\?[^#]*)?(#.*)?$/i,n+'.js$1$2'):n+'.js';document.head.append(s);return s}\n"
hook = "  'use strict';\n"
if t.count(hook) != 1:
    sys.exit('v1211: use strict hook not unique')
t = t.replace(hook, hook + addon, 1)
old_s = """      var s = document.createElement('script');
      s.src = FACTORY_SRC ? FACTORY_SRC.replace(/factory\\.js(\\?[^#]*)?(#.*)?$/i, 'factory-signin.js$1$2') : 'factory-signin.js';
      s.async = true;
      s.onerror = function() { signinP = null; reject(new Error('Could not load factory-signin.js')); };
      s.onload = function() { if (!signinApi) { signinP = null; reject(new Error('factory-signin.js did not install')); } };
      (document.head || document.documentElement).appendChild(s);"""
new_s = """      var s = addon('factory-signin');
      s.onerror = function() { signinP = null; reject(new Error('Could not load factory-signin.js')); };
      s.onload = function() { if (!signinApi) { signinP = null; reject(new Error('factory-signin.js did not install')); } };"""
if old_s not in t:
    sys.exit('v1211: sign-in script block did not match')
t = t.replace(old_s, new_s, 1)
old_img = """  function renderPostMedia(post) {
    if (isPostHidden(post)) return '';
    var html = '';
    if (post.imageUrl) {"""
new_img = """  function renderPostMedia(post) {
    if (isPostHidden(post)) return '';
    var html = '';
    if (/^https:/i.test(post.imageUrl)) {"""
if old_img not in t:
    sys.exit('v1211: renderPostMedia image check did not match')
t = t.replace(old_img, new_img, 1)
old_feed = "   }).join('') + nestMoreHtml();\n   highlightDeepPost();"
new_feed = "   }).join('') + nestMoreHtml();\n   PLUGIN.feat&&PLUGIN.feat(el);\n   highlightDeepPost();"
if old_feed not in t:
    sys.exit('v1211: renderFeed anchor did not match')
t = t.replace(old_feed, new_feed, 1)
m = re.search(r"  function ensureRailCss\(\) \{\n(?:.*\n)*?  \}\n", t)
if not m:
    sys.exit('v1211: ensureRailCss not found')
t = t[:m.start()] + RAIL + t[m.end():]
old_paint = "    if (page) page.innerHTML = html;\n    maybeShowRailOverlay();"
new_paint = "    if (page) page.innerHTML = html;\n    PLUGIN.feat&&PLUGIN.feat();\n    maybeShowRailOverlay();"
if t.count(old_paint) != 1:
    sys.exit('v1211: paintRail anchor did not match')
t = t.replace(old_paint, new_paint, 1)
old_boot = "    renderFeed();\n    railOverlayUiReady = true;"
new_boot = "    renderFeed();\n    if(site.featured)addon('factory-featured').onload=function(){var f=window.__subxFeat;f&&Object.assign(PLUGIN,f(CORE));renderFeed()};\n    railOverlayUiReady = true;"
if old_boot not in t:
    sys.exit('v1211: boot anchor did not match')
t = t.replace(old_boot, new_boot, 1)
h = hashlib.sha256(t.encode()).hexdigest()
if h != ROOM:
    sys.exit('v1211: patched factory.js sha256 %s != room %s' % (h, ROOM))
p.write_text(t)
