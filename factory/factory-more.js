/* SubX factory-more.js. Feed posts collapse to a few lines with More / Less.
 * Same file in every room. Text is split with splitText, createTextNode, and textContent only.
 * A single post URL (?p= or /p/) is left alone. Clamp classes are added only from this script,
 * so with no JS the full post stays visible. Expanding does not fetch again.
 * Selectors come from data attributes on this script tag (Agent Room uses different markup).
 * One style element. If CSP blocks it, rules go through the CSSOM. CSP is never loosened. */
(function () {
  'use strict';
  if (window.SubxMore) return;

  var CSS = [
    '.subx-more-clamp{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;line-clamp:4;overflow:hidden;position:relative;white-space:pre-wrap}',
    '.subx-more-clamp.is-over::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1.5em;background:linear-gradient(to bottom,rgba(0,0,0,0),var(--bg,#fff));pointer-events:none}',
    '@media (min-width:768px){.subx-more-clamp{-webkit-line-clamp:3;line-clamp:3}}',
    '.subx-more-thumb{aspect-ratio:16/9;max-height:200px;overflow:hidden;cursor:pointer}',
    '.subx-more-thumb img{width:100%;height:100%;max-height:200px;object-fit:cover;display:block}',
    '@media (min-width:768px){.subx-more-thumb,.subx-more-thumb img{max-height:260px}}',
    '.subx-more-trust,.subx-more-note,.subx-more-credit{display:block;font-size:12px;line-height:1.35;color:var(--text-muted,var(--text-light,#5c6c73));white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:2px 0 0}',
    '.subx-more-bar{display:flex;align-items:center;gap:8px;margin-top:2px}',
    '.subx-more-bar[hidden],.subx-more-note[hidden],.subx-more-trust[hidden],.subx-more-credit[hidden]{display:none}',
    '.subx-more-btn{appearance:none;-webkit-appearance:none;background:transparent;border:0;padding:0 8px;margin:0;color:var(--accent,#1d9bf0);font:inherit;font-weight:700;min-height:44px;min-width:44px;cursor:pointer;border-radius:8px}',
    '.subx-more-btn:focus,.subx-more-btn:focus-visible{outline:2px solid var(--accent,#1d9bf0);outline-offset:2px}',
    '.subx-more-openlink{color:inherit;font:inherit;min-height:44px;display:inline-flex;align-items:center;text-decoration:underline}',
    '.subx-more-rest{display:block;white-space:pre-wrap}',
    '.subx-more-rest[hidden]{display:none}'
  ].join('\n');

  function attr(script, name, fallback) {
    if (!script || !script.getAttribute) return fallback;
    var v = script.getAttribute(name);
    return v ? v : fallback;
  }

  var script = document.currentScript;
  var cfg = {
    feed: attr(script, 'data-feed', '#thoughts-feed'),
    post: attr(script, 'data-post', 'article.post'),
    text: attr(script, 'data-text', '.post-body > p.post-text'),
    image: attr(script, 'data-image', '.post-body > .post-image'),
    disclaimer: attr(script, 'data-disclaimer', '[data-room-disclaimer]'),
    permalink: attr(script, 'data-permalink', 'query'),
    actions: attr(script, 'data-actions', '.post-actions'),
    idAttr: attr(script, 'data-id-attr', 'data-post-id')
  };

  function isSinglePost() {
    var loc = window.location || {};
    var search = String(loc.search || '');
    if (/[?&]p=/.test(search)) return true;
    var path = String(loc.pathname || '');
    return path === '/p' || path.indexOf('/p/') === 0;
  }

  if (isSinglePost()) {
    window.SubxMore = { active: false };
    return;
  }

  var feed = null;
  var mo = null;
  var painting = false;
  var seq = 0;
  var items = [];
  var disclaimer = disclaimerText();

  function disclaimerText() {
    var el = null;
    try { el = document.querySelector(cfg.disclaimer); } catch (e) { return ''; }
    if (!el) return '';
    var t = String(el.textContent || '').replace(/^\s+|\s+$/g, '');
    if (!t || /[\r\n]/.test(t)) return '';
    return t;
  }

  function metaBlocksInlineStyle() {
    var metas = document.querySelectorAll ? document.querySelectorAll('meta[http-equiv]') : [];
    var i, eq, c, m, src;
    for (i = 0; i < metas.length; i++) {
      eq = String(metas[i].getAttribute('http-equiv') || '').toLowerCase();
      if (eq !== 'content-security-policy') continue;
      c = metas[i].getAttribute('content') || '';
      m = c.match(/(?:^|;)\s*style-src\s+([^;]*)/i);
      if (!m) continue;
      src = m[1];
      if (src.indexOf('unsafe-inline') === -1) return true;
    }
    return false;
  }

  function injectCss() {
    if (document.getElementById && document.getElementById('subx-more-style')) return;
    var st = document.createElement('style');
    st.id = 'subx-more-style';
    st.textContent = CSS;
    var parent = document.head || document.documentElement;
    if (!parent) return;
    parent.appendChild(st);
    var blocked = metaBlocksInlineStyle();
    if (!blocked) {
      try {
        if (st.sheet && st.sheet.cssRules) blocked = false;
        else if (!st.sheet && typeof CSSStyleSheet === 'function' && document.adoptedStyleSheets) blocked = true;
      } catch (e) { blocked = true; }
    }
    if (!blocked) return;
    if (st.parentNode) st.parentNode.removeChild(st);
    if (typeof CSSStyleSheet === 'function' && document.adoptedStyleSheets) {
      try {
        var sheet = new CSSStyleSheet();
        sheet.replaceSync(CSS);
        var prev = Array.prototype.slice.call(document.adoptedStyleSheets);
        prev.push(sheet);
        document.adoptedStyleSheets = prev;
        return;
      } catch (e2) {}
    }
    if (!st.parentNode) parent.appendChild(st);
  }

  function nextId(prefix) {
    seq += 1;
    return prefix + seq;
  }

  function postId(post) {
    var v = post.getAttribute && post.getAttribute(cfg.idAttr);
    if (v) return v;
    if (post.id) return post.id;
    return '';
  }

  function openHref(id) {
    var enc = encodeURIComponent(id);
    if (cfg.permalink === 'path') return '/p/' + enc;
    return '?p=' + enc;
  }

  function limit() {
    try {
      if (window.matchMedia && window.matchMedia('(min-width: 768px)').matches) return 3;
    } catch (e) {}
    return 4;
  }

  function lineCount(s) {
    if (!s || !String(s).replace(/\s/g, '')) return 0;
    return String(s).split(/\r?\n/).length;
  }

  function overflows(el) {
    if (!el) return false;
    var sh = el.scrollHeight, ch = el.clientHeight;
    if (!sh || !ch) return false;
    return sh > ch + 1;
  }

  function classify(line) {
    var s = String(line || '').replace(/^\s+|\s+$/g, '');
    if (!s) return 'empty';
    if (s.indexOf('CC BY') !== -1 || s.indexOf('BY-SA') !== -1) return 'credit';
    if (s.indexOf('Photo:') === 0 && s.indexOf('CC BY') !== -1) return 'credit';
    if (s.indexOf('CC0') !== -1 || /public domain/i.test(s) || /(^|[^A-Za-z])PD([^A-Za-z]|$)/.test(s)) return 'pd';
    if (disclaimer && s === disclaimer) return 'disclaimer';
    if (/^Disclaimer:/i.test(s)) return 'disclaimer';
    if (/WHOMARK|authorship|AI disclosure|AI steward|Human \+ AI|Human-made|Operated by SubX|Not a real person/i.test(s)) return 'whomark';
    if (/^Sponsored\b/i.test(s) || /Sponsored by/i.test(s)) return 'sponsored';
    return 'body';
  }

  function safeHttp(u) {
    if (!u || /[\s"'<>]/.test(u)) return '';
    if (/^javascript:/i.test(u) || /^data:/i.test(u)) return '';
    if (!/^https?:\/\//i.test(u)) return '';
    return u;
  }

  function appendRich(el, line) {
    var re = /https?:\/\/[^\s<>"']+/gi;
    var last = 0, m, raw, url, a;
    while ((m = re.exec(line))) {
      raw = m[0];
      url = raw.replace(/[)\].,;:]+$/, '');
      el.appendChild(document.createTextNode(line.slice(last, m.index)));
      if (safeHttp(url)) {
        a = document.createElement('a');
        a.setAttribute('href', url);
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
        a.appendChild(document.createTextNode(url));
        el.appendChild(a);
        if (url.length < raw.length) el.appendChild(document.createTextNode(raw.slice(url.length)));
      } else {
        el.appendChild(document.createTextNode(raw));
      }
      last = m.index + raw.length;
    }
    el.appendChild(document.createTextNode(line.slice(last)));
  }

  function textNode(p) {
    var i, n;
    if (p.childNodes.length !== 1 || !p.childNodes[0] || p.childNodes[0].nodeType !== 3) {
      p.textContent = p.textContent;
    }
    n = p.childNodes;
    for (i = 0; i < n.length; i++) {
      if (n[i].nodeType === 3) return n[i];
    }
    return null;
  }

  function splitParts(p) {
    var node = textNode(p);
    var raw = node ? node.textContent : '';
    var re = /\r?\n[ \t]*\r?\n/;
    var m = node ? re.exec(raw) : null;
    var head, tail;
    if (m) {
      var after = node.splitText(m.index);
      after.textContent = String(after.textContent || '').replace(/^\r?\n[ \t]*\r?\n/, '');
      if (after.parentNode) after.parentNode.removeChild(after);
      head = node.textContent;
      tail = after.textContent;
    } else {
      head = raw;
      tail = '';
    }
    var trust = [];
    var hidden = [];
    var lead = [];
    // The first chunk is the opening paragraph. Trust lines are lifted out of it.
    // Lines after the blank line are hidden, except trust lines.
    var headLines = head ? String(head).split(/\r?\n/) : [];
    var tailLines = tail ? String(tail).split(/\r?\n/) : [];
    var hi;
    for (hi = 0; hi < headLines.length; hi++) {
      var hk = classify(headLines[hi]);
      var hs = String(headLines[hi] || '').replace(/^\s+|\s+$/g, '');
      if (hk === 'credit' || hk === 'disclaimer' || hk === 'whomark' || hk === 'sponsored') trust.push(hs);
      else if (hk === 'pd') hidden.push(headLines[hi]);
      else lead.push(headLines[hi]);
    }
    for (hi = 0; hi < tailLines.length; hi++) {
      var tk = classify(tailLines[hi]);
      var ts = String(tailLines[hi] || '').replace(/^\s+|\s+$/g, '');
      if (!ts) continue;
      if (tk === 'credit' || tk === 'disclaimer' || tk === 'whomark' || tk === 'sponsored') trust.push(ts);
      else hidden.push(tailLines[hi]);
    }
    if (node) node.textContent = lead.join('\n');
    return { lead: lead.join('\n'), trust: trust, hidden: hidden.join('\n') };
  }

  function alreadyCollapsed(post) {
    if (post.querySelector('.post-more, .subx-more-btn')) return true;
    var buttons = post.querySelectorAll('button');
    var i, t;
    for (i = 0; i < buttons.length; i++) {
      t = String(buttons[i].textContent || '').replace(/^\s+|\s+$/g, '').toLowerCase();
      if (t === 'show more' || t === 'show less' || t === 'read more') return true;
    }
    return false;
  }

  function insertAfter(ref, node) {
    if (!ref || !ref.parentNode) return;
    if (ref.nextSibling) ref.parentNode.insertBefore(node, ref.nextSibling);
    else ref.parentNode.appendChild(node);
  }

  function makeTrust(line, cls) {
    var el = document.createElement('span');
    el.className = cls || 'subx-more-trust';
    appendRich(el, line);
    return el;
  }

  function scrollKeep(btn, fn) {
    var y = window.scrollY || window.pageYOffset || 0;
    var x = window.scrollX || window.pageXOffset || 0;
    var before = btn.getBoundingClientRect ? btn.getBoundingClientRect().top : 0;
    fn();
    var after = btn.getBoundingClientRect ? btn.getBoundingClientRect().top : before;
    if (window.scrollTo) window.scrollTo(x, y + (after - before));
    if (btn.focus) btn.focus();
  }

  function applyClamp(st) {
    var byLines = lineCount(st.leadText) > limit();
    var byBox = false;
    if (st.lead && !st.open) {
      st.lead.classList.add('subx-more-clamp');
      byBox = overflows(st.lead);
    }
    st.over = byLines || byBox;
    if (!st.lead || st.open) return;
    if (st.over) {
      st.lead.classList.add('subx-more-clamp');
      st.lead.classList.add('is-over');
    } else {
      st.lead.classList.remove('subx-more-clamp');
      st.lead.classList.remove('is-over');
    }
  }

  function needsControl(st) {
    return !!(st.hiddenText || st.image || st.over);
  }

  function setOpen(st, open) {
    scrollKeep(st.btn, function () {
      st.open = open;
      if (st.rest) st.rest.hidden = !open;
      if (st.note) st.note.hidden = !!open;
      if (st.image) {
        if (open) st.image.classList.remove('subx-more-thumb');
        else st.image.classList.add('subx-more-thumb');
      }
      if (st.lead) {
        if (open) {
          st.lead.classList.remove('subx-more-clamp');
          st.lead.classList.remove('is-over');
        } else {
          applyClamp(st);
        }
      }
      st.btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      st.btn.textContent = open ? 'Less' : 'More';
    });
  }

  function ensureBar(st, host, before) {
    if (st.bar) return;
    var bar = document.createElement('div');
    bar.className = 'subx-more-bar';
    if (disclaimer) st.note = makeTrust(disclaimer, 'subx-more-note');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'subx-more-btn';
    btn.textContent = 'More';
    btn.setAttribute('aria-expanded', 'false');
    var controls = st.rest || st.image || st.lead;
    if (controls) {
      if (!controls.id) controls.id = nextId('subx-more-');
      btn.setAttribute('aria-controls', controls.id);
    }
    btn.addEventListener('click', function (e) {
      if (e && e.preventDefault) e.preventDefault();
      setOpen(st, !st.open);
    });
    bar.appendChild(btn);
    var id = postId(st.post);
    if (id) {
      var link = document.createElement('a');
      link.className = 'subx-more-openlink';
      link.setAttribute('href', openHref(id));
      link.textContent = 'Open post';
      bar.appendChild(link);
    }
    function place(node) {
      if (before && before.parentNode) before.parentNode.insertBefore(node, before);
      else if (st.anchor) insertAfter(st.anchor, node);
      else host.appendChild(node);
    }
    if (st.note) {
      place(st.note);
      st.anchor = st.note;
      before = null;
    }
    place(bar);
    st.bar = bar;
    st.btn = btn;
  }

  function decorate(post) {
    if (!post || post.nodeType !== 1) return;
    if (post.getAttribute('data-subx-more') === '1') return;
    if (alreadyCollapsed(post)) {
      post.setAttribute('data-subx-more', '1');
      return;
    }
    var lead = null;
    var image = null;
    try { lead = post.querySelector(cfg.text); } catch (e1) { lead = null; }
    try { image = post.querySelector(cfg.image); } catch (e2) { image = null; }
    if (!lead && !image) {
      post.setAttribute('data-subx-more', '1');
      return;
    }
    var parts = lead ? splitParts(lead) : { lead: '', trust: [], hidden: '' };
    var host = (lead && lead.parentNode) || post;
    var cursor = lead;
    var ti, trustEl;
    var credits = [];
    var otherTrust = [];
    for (ti = 0; ti < parts.trust.length; ti++) {
      if (classify(parts.trust[ti]) === 'credit') credits.push(parts.trust[ti]);
      else otherTrust.push(parts.trust[ti]);
    }
    for (ti = 0; ti < otherTrust.length; ti++) {
      trustEl = makeTrust(otherTrust[ti], 'subx-more-trust');
      if (cursor) insertAfter(cursor, trustEl);
      else host.appendChild(trustEl);
      cursor = trustEl;
    }
    var rest = null;
    if (parts.hidden) {
      rest = document.createElement('span');
      rest.className = 'subx-more-rest';
      rest.id = nextId('subx-more-rest-');
      rest.hidden = true;
      rest.appendChild(document.createTextNode(parts.hidden));
      if (cursor) insertAfter(cursor, rest);
      else host.appendChild(rest);
      cursor = rest;
    }
    if (image) {
      if (credits.length) insertAfter(image, makeTrust(credits[0], 'subx-more-credit'));
      for (ti = 1; ti < credits.length; ti++) {
        trustEl = makeTrust(credits[ti], 'subx-more-trust');
        if (cursor) insertAfter(cursor, trustEl);
        else host.appendChild(trustEl);
        cursor = trustEl;
      }
    } else {
      for (ti = 0; ti < credits.length; ti++) {
        trustEl = makeTrust(credits[ti], 'subx-more-trust');
        if (cursor) insertAfter(cursor, trustEl);
        else host.appendChild(trustEl);
        cursor = trustEl;
      }
    }
    var st = {
      post: post,
      lead: lead,
      leadText: parts.lead,
      trust: parts.trust,
      hiddenText: parts.hidden,
      rest: rest,
      image: image,
      note: null,
      bar: null,
      btn: null,
      anchor: image || cursor || lead,
      open: false,
      over: false
    };
    if (image) {
      image.classList.add('subx-more-thumb');
      var hit = image.querySelector('img') || image;
      hit.addEventListener('click', function () {
        if (!st.open && st.btn) setOpen(st, true);
      });
    }
    applyClamp(st);
    if (needsControl(st)) {
      var actions = null;
      try { actions = post.querySelector(cfg.actions); } catch (e3) { actions = null; }
      ensureBar(st, host, actions);
    }
    items.push(st);
    post.setAttribute('data-subx-more', '1');
  }

  function scan() {
    if (!feed || painting) return;
    painting = true;
    var watch = mo;
    try {
      if (watch) watch.disconnect();
      var nodes = feed.querySelectorAll(cfg.post);
      var i;
      for (i = 0; i < nodes.length; i++) decorate(nodes[i]);
    } finally {
      if (watch && feed) {
        watch.observe(feed, { childList: true, subtree: true });
        if (watch.takeRecords) watch.takeRecords();
      }
      painting = false;
    }
  }

  function refreshAll() {
    var i, st, want;
    for (i = 0; i < items.length; i++) {
      st = items[i];
      if (st.open) continue;
      applyClamp(st);
      want = needsControl(st);
      if (want && !st.bar) {
        var actions = null;
        try { actions = st.post.querySelector(cfg.actions); } catch (e4) { actions = null; }
        var host = (st.lead && st.lead.parentNode) || st.post;
        ensureBar(st, host, actions);
      } else if (!want && st.bar) {
        st.bar.hidden = true;
      } else if (want && st.bar) {
        st.bar.hidden = false;
      }
    }
  }

  injectCss();
  try { feed = document.querySelector(cfg.feed); } catch (e5) { feed = null; }
  if (feed) {
    scan();
    if (typeof MutationObserver === 'function') {
      mo = new MutationObserver(function () {
        if (painting) return;
        scan();
      });
      mo.observe(feed, { childList: true, subtree: true });
    }
  }
  if (window.matchMedia) {
    try {
      var mq = window.matchMedia('(min-width: 768px)');
      if (mq.addEventListener) mq.addEventListener('change', refreshAll);
      else if (mq.addListener) mq.addListener(refreshAll);
    } catch (e6) {}
  }
  window.SubxMore = { active: true };
})();
