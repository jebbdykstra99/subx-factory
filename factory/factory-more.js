/* SubX factory-more.js. Feed posts collapse to a few lines with Show more / Show less.
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
    '.subx-more-clamp.is-over{-webkit-mask-image:linear-gradient(to bottom,#000 calc(100% - 1.5em),transparent);mask-image:linear-gradient(to bottom,#000 calc(100% - 1.5em),transparent)}',
    '@supports not (mask-image: linear-gradient(#000,#000)){.subx-more-clamp.is-over::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1.5em;background:linear-gradient(to bottom,rgba(0,0,0,0),var(--bg,#fff));pointer-events:none}}',
    '@media (min-width:768px){.subx-more-clamp{-webkit-line-clamp:3;line-clamp:3}}',
    '.subx-more-collapsed.is-over .post-image img,.subx-more-collapsed.is-over .post-image video,.subx-more-collapsed.is-over video{width:100%;max-height:200px;object-fit:cover;object-position:var(--subx-focal,center)}',
    '@media (min-width:768px){.subx-more-collapsed.is-over .post-image img,.subx-more-collapsed.is-over .post-image video,.subx-more-collapsed.is-over video{max-height:260px}}',
    '.subx-more-trust,.subx-more-note,.subx-more-credit{display:block;font-size:12px;line-height:1.35;color:var(--text-muted,var(--text-light,#5c6c73));white-space:normal;overflow-wrap:anywhere;margin:2px 0 0}',
    '.subx-more-credit a,.subx-more-trust a{color:var(--link,var(--text-muted,var(--text-light,#5c6c73)))}',
    '.subx-more-lic{white-space:nowrap}',
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
    var ccBy = s.indexOf('CC BY') !== -1;
    var bySa = s.indexOf('BY-SA') !== -1;
    // Photo:, Image:, and Photo by are credits when the line also carries CC BY.
    var named = /^(Photo:|Image:|Photo by)(\s|$)/.test(s);
    if (knownCcIn(s) || ccBy || bySa || (named && ccBy)) return 'credit';
    if (s.indexOf('CC0') !== -1 || /public domain/i.test(s) || /(^|[^A-Za-z])PD([^A-Za-z]|$)/.test(s)) return 'pd';
    if (disclaimer && s === disclaimer) return 'disclaimer';
    if (/^Disclaimer:/i.test(s)) return 'disclaimer';
    if (/WHOMARK|authorship|AI disclosure|AI steward|Human \+ AI|Human-made|Operated by SubX|Not a real person/i.test(s)) return 'whomark';
    if (/^Sponsored\b/i.test(s) || /Sponsored by/i.test(s)) return 'sponsored';
    return 'body';
  }

  function normLine(s) {
    return String(s || '').replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '').toLowerCase();
  }

  function visibleText(el) {
    if (!el) return '';
    if (el.nodeType === 3) return el.textContent || '';
    if (el.nodeType !== 1) return '';
    if (el.hidden) return '';
    if (el.classList && (el.classList.contains('subx-more-rest') || el.classList.contains('post-meta') || el.classList.contains('post-steward-pill') || el.classList.contains('wm') || el.classList.contains('post-actions') || el.classList.contains('post-avatar'))) return '';
    var out = '', i, ch = el.childNodes || [];
    for (i = 0; i < ch.length; i++) out += visibleText(ch[i]);
    return out;
  }

  function alreadyInCard(post, line) {
    var want = normLine(line);
    if (!want) return true;
    return normLine(visibleText(post)).indexOf(want) !== -1;
  }

  var CC_LABELS = { 'by': 'CC BY', 'by-sa': 'CC BY-SA', 'by-nd': 'CC BY-ND', 'by-nc': 'CC BY-NC', 'by-nc-sa': 'CC BY-NC-SA', 'by-nc-nd': 'CC BY-NC-ND', 'cc0': 'CC0', 'zero': 'CC0' };

  function knownCcIn(s) {
    var re = /https:\/\/[^\s<>"']+/gi;
    var m;
    while ((m = re.exec(s))) {
      if (ccParts(m[0].replace(/[)\].,;:]+$/, ''))) return true;
    }
    return false;
  }

  function ccParts(raw) {
    var parsed;
    try { parsed = new URL(raw); } catch (e) { return null; }
    if (!parsed || parsed.protocol !== 'https:') return null;
    var host = String(parsed.hostname || '').toLowerCase();
    if (host !== 'creativecommons.org' && host !== 'www.creativecommons.org') return null;
    var bits = String(parsed.pathname || '').split('/');
    var i, parts = [];
    for (i = 0; i < bits.length; i++) if (bits[i]) parts.push(bits[i].toLowerCase());
    var code = '', version = '';
    if (parts[0] === 'licenses' && parts.length >= 3) { code = parts[1]; version = parts[2]; }
    else if (parts[0] === 'publicdomain' && parts[1] === 'zero' && parts[2]) { code = 'zero'; version = parts[2]; }
    var name = CC_LABELS[code];
    if (!name || !/^[0-9]+\.[0-9]+$/.test(version)) return null;
    return { href: parsed.href, label: name + ' ' + version };
  }

  function fillCredit(el, line) {
    var re = /https:\/\/[^\s<>"']+/gi;
    var m, found = null;
    while ((m = re.exec(line))) {
      var raw = m[0];
      var url = raw.replace(/[)\].,;:]+$/, '');
      var parts = ccParts(url);
      if (parts) { found = { href: parts.href, label: parts.label, index: m.index, raw: raw }; break; }
    }
    if (!found) {
      el.appendChild(document.createTextNode(line));
      return;
    }
    var body = (line.slice(0, found.index) + ' ' + line.slice(found.index + found.raw.length));
    body = body.replace(new RegExp(found.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig'), ' ');
    body = body.replace(/\s+/g, ' ').replace(/^[\s,;:.·-]+|[\s,;:.·-]+$/g, '');
    if (body) {
      el.appendChild(document.createTextNode(body));
      el.appendChild(document.createTextNode(' \u00b7 '));
    }
    var a = document.createElement('a');
    a.setAttribute('href', found.href);
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
    var span = document.createElement('span');
    span.className = 'subx-more-lic';
    span.textContent = found.label;
    a.appendChild(span);
    el.appendChild(a);
  }

  function appendRich(el, line) {
    el.appendChild(document.createTextNode(line));
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
    if (classify(line) === 'credit') fillCredit(el, line);
    else appendRich(el, line);
    return el;
  }

  function safeFocal(v) {
    v = String(v || '').replace(/^\s+|\s+$/g, '');
    if (/^(?:center|top|bottom|left|right|[0-9]{1,3}%)(?:\s+(?:center|top|bottom|left|right|[0-9]{1,3}%))?$/.test(v)) return v;
    return '';
  }

  function primeFocal(post) {
    var nodes = post.querySelectorAll ? post.querySelectorAll('img, video') : [];
    var media = null, i, parent;
    for (i = 0; i < nodes.length; i++) {
      parent = nodes[i].parentNode;
      if (parent && parent.classList && (parent.classList.contains('post-avatar') || parent.classList.contains('post-meta'))) continue;
      media = nodes[i];
      break;
    }
    var focal = 'center';
    if (media && media.getAttribute) {
      var raw = media.getAttribute('data-focal') || media.getAttribute('data-focal-point') || media.getAttribute('data-object-position') || '';
      var ok = safeFocal(raw);
      if (ok) focal = ok;
    }
    if (!post.style) return;
    if (post.style.setProperty) post.style.setProperty('--subx-focal', focal);
    else post.style['--subx-focal'] = focal;
  }

  function syncCollapsed(st) {
    if (!st.post || !st.post.classList) return;
    if (st.open) {
      st.post.classList.remove('subx-more-collapsed');
      st.post.classList.remove('is-over');
      return;
    }
    st.post.classList.add('subx-more-collapsed');
    if (st.over) st.post.classList.add('is-over');
    else st.post.classList.remove('is-over');
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
      if (st.lead) {
        if (open) {
          st.lead.classList.remove('subx-more-clamp');
          st.lead.classList.remove('is-over');
        } else {
          applyClamp(st);
        }
      }
      st.btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      st.btn.textContent = open ? 'Show less' : 'Show more';
      syncCollapsed(st);
    });
  }

  function ensureBar(st, host, before) {
    if (st.bar) return;
    var bar = document.createElement('div');
    bar.className = 'subx-more-bar';
    if (disclaimer && !alreadyInCard(st.post, disclaimer)) st.note = makeTrust(disclaimer, 'subx-more-note');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'subx-more-btn';
    btn.textContent = 'Show more';
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
    var keep = {};
    parts.trust.forEach(function (t) { keep[normLine(t)] = true; });
    if (disclaimer) keep[normLine(disclaimer)] = true;
    if (parts.hidden) {
      parts.hidden = parts.hidden.split(/\r?\n/).filter(function (line) {
        var key = normLine(line);
        if (!key || keep[key]) return false;
        keep[key] = true;
        return true;
      }).join('\n');
    }
    var host = (lead && lead.parentNode) || post;
    var cursor = lead;
    var ti, trustEl;
    var credits = [];
    var otherTrust = [];
    var seen = {};
    function take(line) {
      var key = normLine(line);
      if (!key || seen[key] || alreadyInCard(post, line)) return false;
      seen[key] = true;
      return true;
    }
    for (ti = 0; ti < parts.trust.length; ti++) {
      if (!take(parts.trust[ti])) continue;
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
      var hit = image.querySelector ? (image.querySelector('img') || image) : image;
      hit.addEventListener('click', function () {
        if (!st.open && st.btn) setOpen(st, true);
      });
    }
    primeFocal(post);
    applyClamp(st);
    syncCollapsed(st);
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
      syncCollapsed(st);
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
