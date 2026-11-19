// node test/more.test.js
// Collapsed daily posts (factory/factory-more.js). A small DOM stands in for the browser.
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcPath = path.join(root, 'factory', 'factory-more.js');
const src = fs.readFileSync(srcPath, 'utf8');
let pass = 0;
function ok(name) { pass += 1; console.log('ok   ' + name); }

function makeRealm(opts) {
  opts = opts || {};
  const splits = { n: 0 };
  const moLog = { n: 0, targets: [] };
  let notifying = false;

  function link(parent) {
    const ch = parent.childNodes;
    for (let i = 0; i < ch.length; i++) {
      ch[i].parentNode = parent;
      ch[i].previousSibling = i ? ch[i - 1] : null;
      ch[i].nextSibling = i + 1 < ch.length ? ch[i + 1] : null;
    }
  }
  function classesOf(el) {
    return new Set(String(el._attr.class || '').split(/\s+/).filter(Boolean));
  }
  function notify(node) {
    if (notifying) return;
    let n = node;
    while (n) {
      if (n._mo && n._mo.connected) {
        notifying = true;
        try { n._mo.cb([]); } finally { notifying = false; }
        return;
      }
      n = n.parentNode;
    }
  }
  function matchSimple(el, sel) {
    if (!el || el.nodeType !== 1) return false;
    let rest = sel;
    const tm = /^[A-Za-z][\w-]*/.exec(sel);
    if (tm && sel[0] !== '.' && sel[0] !== '#' && sel[0] !== '[') {
      if (String(el.nodeName).toUpperCase() !== tm[0].toUpperCase()) return false;
      rest = sel.slice(tm[0].length);
    }
    if (!rest) return true;
    const parts = rest.match(/(\.[^.#\[]+|#[^.#\[]+|\[[^\]]+\])/g);
    if (!parts) return false;
    for (const p of parts) {
      if (p[0] === '.') {
        if (!classesOf(el).has(p.slice(1))) return false;
      } else if (p[0] === '#') {
        if (el.getAttribute('id') !== p.slice(1)) return false;
      } else {
        const m = /^\[([^\]=~|^$*]+)(?:([~|^$*]?=)"([^"]*)")?\]$/.exec(p);
        if (!m) return false;
        if (!m[2]) { if (!el.hasAttribute(m[1])) return false; }
        else if (m[2] === '=' && el.getAttribute(m[1]) !== m[3]) return false;
      }
    }
    return true;
  }
  function descendants(node) {
    const out = [];
    (node.childNodes || []).forEach((ch) => {
      if (ch.nodeType === 1) { out.push(ch); descendants(ch).forEach((d) => out.push(d)); }
    });
    return out;
  }
  function queryAll(rootNode, selector) {
    const sel = String(selector || '').trim();
    if (!sel) return [];
    if (sel.indexOf(',') !== -1) {
      const out = [];
      sel.split(',').forEach((part) => {
        queryAll(rootNode, part.trim()).forEach((el) => { if (out.indexOf(el) === -1) out.push(el); });
      });
      return out;
    }
    const steps = [];
    let comb = 'desc';
    const re = /\s*>\s*|\s+|[^\s>]+/g;
    let m;
    while ((m = re.exec(sel))) {
      const t = m[0];
      if (t.trim() === '>') { comb = 'child'; continue; }
      if (/^\s+$/.test(t)) { if (comb !== 'child') comb = 'desc'; continue; }
      steps.push({ comb: comb, sel: t });
      comb = 'desc';
    }
    let current = [rootNode];
    steps.forEach((step, i) => {
      const next = [];
      current.forEach((node) => {
        const pool = (i === 0 || step.comb !== 'child')
          ? descendants(node)
          : (node.childNodes || []).filter((ch) => ch.nodeType === 1);
        pool.forEach((el) => { if (matchSimple(el, step.sel) && next.indexOf(el) === -1) next.push(el); });
      });
      current = next;
    });
    return current;
  }

  function element(tag) {
    const el = {
      nodeType: 1,
      nodeName: String(tag).toUpperCase(),
      childNodes: [],
      parentNode: null,
      nextSibling: null,
      previousSibling: null,
      _attr: {},
      _hidden: false,
      _listeners: {},
      sheet: null,
      style: {},
      scrollHeight: 0,
      clientHeight: 0,
      ownerDocument: null,
      _mo: null
    };
    el.classList = {
      add: function () { const set = classesOf(el); for (let i = 0; i < arguments.length; i++) set.add(arguments[i]); el._attr.class = Array.from(set).join(' '); },
      remove: function () { const set = classesOf(el); for (let i = 0; i < arguments.length; i++) set.delete(arguments[i]); el._attr.class = Array.from(set).join(' '); },
      contains: function (c) { return classesOf(el).has(c); }
    };
    Object.defineProperty(el, 'className', {
      get: function () { return el._attr.class || ''; },
      set: function (v) { el._attr.class = String(v || ''); }
    });
    Object.defineProperty(el, 'id', {
      get: function () { return el._attr.id || ''; },
      set: function (v) { el._attr.id = String(v); }
    });
    Object.defineProperty(el, 'type', {
      get: function () { return el._attr.type || ''; },
      set: function (v) { el._attr.type = String(v); }
    });
    Object.defineProperty(el, 'hidden', {
      get: function () { return el._hidden; },
      set: function (v) {
        el._hidden = !!v;
        if (el._hidden) el._attr.hidden = '';
        else delete el._attr.hidden;
        if (!el._hidden && classesOf(el).has('subx-more-rest') && el.ownerDocument) el.ownerDocument.defaultView.__top = 40;
      }
    });
    Object.defineProperty(el, 'textContent', {
      get: function () { return el.childNodes.map((c) => c.textContent).join(''); },
      set: function (v) {
        el.childNodes = [];
        if (v != null && String(v) !== '') el.appendChild(textNode(String(v)));
      }
    });
    el.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(el._attr, k) ? el._attr[k] : null; };
    el.setAttribute = function (k, v) { el._attr[k] = String(v); };
    el.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(el._attr, k); };
    el.removeAttribute = function (k) { delete el._attr[k]; };
    el.appendChild = function (ch) {
      if (ch.parentNode) ch.parentNode.removeChild(ch);
      el.childNodes.push(ch);
      link(el);
      if (el.nodeName === 'STYLE' && !el.ownerDocument._blockStyle) el.sheet = { cssRules: String(ch.textContent || el.textContent).split('}') };
      notify(el);
      return ch;
    };
    el.insertBefore = function (ch, ref) {
      if (ch.parentNode) ch.parentNode.removeChild(ch);
      const i = el.childNodes.indexOf(ref);
      if (i < 0) el.childNodes.push(ch);
      else el.childNodes.splice(i, 0, ch);
      link(el);
      notify(el);
      return ch;
    };
    el.removeChild = function (ch) {
      const i = el.childNodes.indexOf(ch);
      if (i >= 0) el.childNodes.splice(i, 1);
      ch.parentNode = null;
      link(el);
      return ch;
    };
    el.addEventListener = function (type, fn) { (el._listeners[type] = el._listeners[type] || []).push(fn); };
    el.focus = function () { if (el.ownerDocument) el.ownerDocument.activeElement = el; };
    el.getBoundingClientRect = function () {
      const top = el.ownerDocument && el.ownerDocument.defaultView ? el.ownerDocument.defaultView.__top : 0;
      return { top: top || 0, left: 0, width: 44, height: 44 };
    };
    el.querySelector = function (s) { return queryAll(el, s)[0] || null; };
    el.querySelectorAll = function (s) { return queryAll(el, s); };
    el.click = function () {
      (el._listeners.click || []).forEach((fn) => fn({ target: el, preventDefault: function () {} }));
    };
    return el;
  }
  function textNode(data) {
    const n = { nodeType: 3, nodeName: '#text', _data: String(data), parentNode: null, childNodes: [], ownerDocument: null };
    Object.defineProperty(n, 'textContent', {
      get: function () { return n._data; },
      set: function (v) { n._data = String(v); }
    });
    n.splitText = function (offset) {
      splits.n += 1;
      const rest = n._data.slice(offset);
      n._data = n._data.slice(0, offset);
      const t = textNode(rest);
      t.ownerDocument = n.ownerDocument;
      const p = n.parentNode;
      if (p) {
        const i = p.childNodes.indexOf(n);
        p.childNodes.splice(i + 1, 0, t);
        link(p);
      }
      return t;
    };
    return n;
  }

  const document = {
    nodeType: 9,
    nodeName: '#document',
    childNodes: [],
    _blockStyle: !!opts.blockStyle,
    _splits: splits,
    activeElement: null,
    adoptedStyleSheets: opts.blockStyle ? [] : undefined,
    defaultView: null,
    currentScript: null
  };
  document.ownerDocument = document;
  document.createElement = function (tag) {
    const el = element(tag);
    el.ownerDocument = document;
    return el;
  };
  document.createTextNode = function (data) {
    const n = textNode(data);
    n.ownerDocument = document;
    return n;
  };
  document.querySelector = function (s) { return queryAll(document, s)[0] || null; };
  document.querySelectorAll = function (s) { return queryAll(document, s); };
  document.getElementById = function (id) { return queryAll(document, '#' + id)[0] || null; };
  const html = document.createElement('html');
  const head = document.createElement('head');
  const body = document.createElement('body');
  document.appendChild = function (ch) { document.childNodes.push(ch); ch.parentNode = document; return ch; };
  document.appendChild(html);
  html.appendChild(head);
  html.appendChild(body);
  document.documentElement = html;
  document.head = head;
  document.body = body;

  function MutationObserver(cb) {
    moLog.n += 1;
    this.cb = cb;
    this.connected = false;
    this.target = null;
    this.targets = [];
  }
  MutationObserver.prototype.observe = function (t) {
    this.target = t;
    this.connected = true;
    this.targets.push(t);
    moLog.targets.push(t);
    t._mo = this;
  };
  MutationObserver.prototype.disconnect = function () {
    this.connected = false;
    if (this.target) this.target._mo = null;
  };
  MutationObserver.prototype.takeRecords = function () { return []; };
  function CSSStyleSheet() { this.css = ''; }
  CSSStyleSheet.prototype.replaceSync = function (css) { this.css = css; };

  const sandbox = {
    console: console,
    document: document,
    MutationObserver: MutationObserver,
    CSSStyleSheet: CSSStyleSheet,
    location: { search: opts.search || '', pathname: opts.pathname || '/', href: 'https://room.test/' },
    scrollX: 0,
    scrollY: opts.scrollY != null ? opts.scrollY : 100,
    pageXOffset: 0,
    pageYOffset: opts.scrollY != null ? opts.scrollY : 100,
    __top: 10,
    _scrolled: [],
    fetches: 0,
    matchMedia: function (q) {
      return { matches: !!opts.wide && String(q).indexOf('768') !== -1, addEventListener: function () {}, removeEventListener: function () {}, addListener: function () {} };
    },
    scrollTo: function (x, y) { sandbox._scrolled.push([x, y]); sandbox.scrollX = x; sandbox.scrollY = y; },
    fetch: function () { sandbox.fetches += 1; return Promise.resolve({ ok: true }); }
  };
  sandbox.window = sandbox;
  document.defaultView = sandbox;
  const script = document.createElement('script');
  Object.keys(opts.attrs || {}).forEach((k) => script.setAttribute(k, opts.attrs[k]));
  document.currentScript = script;
  sandbox.document = document;

  return { sandbox: sandbox, document: document, body: body, script: script, splits: splits, moLog: moLog, element: document.createElement.bind(document) };
}

function h(doc, tag, attrs, text) {
  const el = doc.createElement(tag);
  Object.keys(attrs || {}).forEach((k) => {
    if (k === 'class') el.className = attrs[k];
    else el.setAttribute(k, attrs[k]);
  });
  if (text != null) el.appendChild(doc.createTextNode(text));
  return el;
}

function article(doc, id, text, extra) {
  const post = h(doc, 'article', { class: 'post', 'data-post-id': id });
  const body = h(doc, 'div', { class: 'post-body' });
  const meta = h(doc, 'div', { class: 'post-meta' });
  meta.appendChild(h(doc, 'span', { class: 'post-steward-pill' }, 'AI steward'));
  meta.appendChild(h(doc, 'span', { class: 'wm' }, 'WHOMARK'));
  body.appendChild(meta);
  body.appendChild(h(doc, 'p', { class: 'post-text' }, text));
  if (extra && extra.image) {
    const imgWrap = h(doc, 'div', { class: 'post-image' });
    imgWrap.appendChild(h(doc, 'img', { src: '/photo.jpg', alt: '' }));
    body.appendChild(imgWrap);
  }
  const actions = h(doc, 'div', { class: 'post-actions' });
  actions.appendChild(h(doc, 'button', { type: 'button' }, 'Report'));
  body.appendChild(actions);
  post.appendChild(body);
  return post;
}

function hiddenOf(el) {
  let n = el;
  while (n) {
    if (n.hidden || (n.hasAttribute && n.hasAttribute('hidden'))) return true;
    n = n.parentNode;
  }
  return false;
}

assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|new Function|eval\(/.test(src), 'no HTML or code sinks');
assert.ok(!/[\u2013\u2014]/.test(src), 'no em or en dash in the add-on');
assert.ok(src.indexOf('splitText') !== -1 && src.indexOf('createTextNode') !== -1 && src.indexOf('textContent') !== -1, 'split uses splitText, createTextNode, and textContent');
ok('source stays on text nodes');

function start(text, opts) {
  opts = opts || {};
  const r = makeRealm(opts);
  if (opts.disclaimer) r.body.appendChild(h(r.document, 'p', { 'data-room-disclaimer': '' }, opts.disclaimer));
  const post = article(r.document, opts.id || 'p1', text, { image: opts.image });
  const feed = h(r.document, 'div', { id: opts.feedId || 'thoughts-feed' });
  feed.appendChild(post);
  r.body.appendChild(feed);
  vm.createContext(r.sandbox);
  vm.runInContext(src, r.sandbox, { filename: 'factory-more.js' });
  return { r: r, feed: feed, post: post, doc: r.document };
}

{
  const { post, r } = start('First paragraph stays.\n\nSecond paragraph hides.');
  assert.ok(r.splits.n >= 1, 'splitText ran');
  assert.equal(post.querySelector('p.post-text').textContent, 'First paragraph stays.');
  const rest = post.querySelector('.subx-more-rest');
  assert.ok(rest && rest.hidden, 'rest is a hidden span');
  assert.ok(rest.textContent.indexOf('Second paragraph hides.') !== -1, 'rest holds the tail');
  ok('split at the first blank line');
}

{
  const lines = ['one', 'two', 'three', 'four', 'five', 'six'].join('\n');
  const { post, doc } = start(lines);
  const p = post.querySelector('p.post-text');
  assert.ok(p.classList.contains('subx-more-clamp') && p.classList.contains('is-over'), 'clamp class on a long lead');
  const css = doc.getElementById('subx-more-style').textContent;
  assert.ok(css.indexOf('-webkit-line-clamp:4') !== -1 && css.indexOf('line-clamp:4') !== -1, '4 lines under 768');
  assert.ok(/@media \(min-width:768px\)\{[^}]*-webkit-line-clamp:3/.test(css), '3 lines at 768 and up');
  assert.ok(css.indexOf('linear-gradient') !== -1, 'soft fade on the last line');
  assert.ok(post.querySelector('.subx-more-btn'), 'long lead gets More');
  ok('clamp');
}

{
  const { post, doc } = start('Short note.');
  assert.equal(post.querySelector('.subx-more-btn'), null, 'short post has no button');
  assert.ok(!post.querySelector('p.post-text').classList.contains('subx-more-clamp'), 'short post is not clamped');
  assert.equal(doc.querySelectorAll('.subx-more-btn').length, 0);
  ok('no button when the post already fits');
}

{
  const { post, r } = start('Lead line.\n\nThe rest of the note stays tucked away until you ask.');
  const btn = post.querySelector('.subx-more-btn');
  assert.equal(btn.type, 'button');
  assert.equal(btn.getAttribute('aria-expanded'), 'false');
  assert.equal(btn.textContent, 'More');
  assert.ok(btn.getAttribute('aria-controls'));
  assert.equal(post.querySelector('#' + btn.getAttribute('aria-controls')).hidden, true);
  const css = r.document.getElementById('subx-more-style').textContent;
  assert.ok(css.indexOf('min-height:44px') !== -1 && css.indexOf('min-width:44px') !== -1, '44px target');
  assert.ok(css.indexOf('.subx-more-bar[hidden]') !== -1, 'a hidden bar stays hidden against display:flex');
  assert.ok(css.indexOf('var(--accent,#1d9bf0)') !== -1 && css.indexOf(':focus-visible') !== -1, 'accent and focus ring');
  btn.click();
  assert.equal(btn.getAttribute('aria-expanded'), 'true');
  assert.equal(btn.textContent, 'Less');
  assert.equal(post.querySelector('.subx-more-rest').hidden, false);
  assert.equal(r.document.activeElement, btn, 'focus stays on the button');
  assert.deepEqual(r.sandbox._scrolled[0], [0, 130], 'scroll keeps the button in place');
  assert.equal(r.sandbox.fetches, 0, 'expand does not fetch');
  btn.click();
  assert.equal(btn.getAttribute('aria-expanded'), 'false');
  assert.equal(btn.textContent, 'More');
  assert.equal(post.querySelector('.subx-more-rest').hidden, true);
  ok('aria-expanded toggle');
}

{
  const skipped = start('Lead.\n\nHidden tail.', { search: '?p=abc' });
  assert.equal(skipped.r.sandbox.SubxMore.active, false);
  assert.equal(skipped.post.querySelector('.subx-more-btn'), null);
  assert.equal(skipped.doc.getElementById('subx-more-style'), null);
  assert.equal(skipped.r.moLog.n, 0, 'no observer on a single post');
  const pathSkip = start('Lead.\n\nHidden tail.', { pathname: '/p/abc' });
  assert.equal(pathSkip.r.sandbox.SubxMore.active, false);
  assert.equal(pathSkip.post.querySelector('.subx-more-btn'), null);
  const live = start('Lead.\n\nHidden tail.', { search: '?preview=1', pathname: '/room' });
  assert.equal(live.r.sandbox.SubxMore.active, true);
  assert.ok(live.post.querySelector('.subx-more-btn'));
  ok('single-post skip');
}

{
  const evil = 'Hello there.\n\n<img src=x onerror=alert(1)>\n<script>alert(1)</script>';
  const { post, doc } = start(evil);
  assert.equal(doc.querySelector('script'), null, 'script text did not become an element');
  assert.equal(post.querySelector('img'), null, 'img text did not become an element');
  assert.ok(post.textContent.indexOf('<img src=x onerror=alert(1)>') !== -1);
  assert.ok(post.textContent.indexOf('<script>alert(1)</script>') !== -1);
  const rest = post.querySelector('.subx-more-rest');
  assert.equal(rest.childNodes.length, 1);
  assert.equal(rest.childNodes[0].nodeType, 3);
  ok('XSS stays inert text');
}

{
  const text = [
    'King cobra notes for the week.',
    '',
    'Photo: Ada Lovelace, CC BY 4.0 https://creativecommons.org/licenses/by/4.0/',
    'Not a pet. Wildlife education only.',
    'WHOMARK: Human + AI',
    'Sponsored by Example',
    'Photo: Bob, CC0 https://creativecommons.org/publicdomain/zero/1.0/',
    'javascript:alert(1) and data:text/html,hi stay text',
    'The rest of the field notes stay tucked away.'
  ].join('\n');
  const { post, doc } = start(text, { image: true, disclaimer: 'Not a pet. Wildlife education only.' });
  const pill = post.querySelector('.post-steward-pill');
  const chip = post.querySelector('.wm');
  const report = post.querySelector('.post-actions button');
  assert.equal(pill.textContent, 'AI steward');
  assert.equal(chip.textContent, 'WHOMARK');
  assert.equal(report.textContent, 'Report');
  assert.equal(hiddenOf(pill), false);
  assert.equal(hiddenOf(chip), false);
  assert.equal(hiddenOf(report), false);
  assert.ok(!pill.closest || true);
  const rest = post.querySelector('.subx-more-rest');
  assert.ok(hiddenOf(rest));
  assert.ok(rest.textContent.indexOf('CC0') !== -1, 'PD/CC0 stays hidden');
  assert.ok(rest.textContent.indexOf('field notes') !== -1);
  assert.ok(rest.textContent.indexOf('CC BY') === -1, 'CC BY is not hidden');
  const credit = post.querySelector('.subx-more-credit');
  assert.ok(credit && !hiddenOf(credit), 'credit sits under the thumb');
  assert.ok(credit.textContent.indexOf('CC BY 4.0') !== -1);
  const lic = credit.querySelector('a');
  assert.equal(lic.getAttribute('href'), 'https://creativecommons.org/licenses/by/4.0/');
  assert.equal(lic.getAttribute('target'), '_blank');
  assert.equal(lic.getAttribute('rel'), 'noopener noreferrer');
  const hrefs = post.querySelectorAll('a').map((a) => a.getAttribute('href'));
  assert.ok(!hrefs.some((h) => /^javascript:/i.test(h) || /^data:/i.test(h)), 'license scheme filter');
  assert.ok(post.textContent.indexOf('javascript:alert(1)') !== -1);
  assert.ok(post.textContent.indexOf('data:text/html,hi') !== -1);
  const trustText = post.querySelectorAll('.subx-more-trust').map((n) => n.textContent).join('\n');
  assert.ok(trustText.indexOf('WHOMARK: Human + AI') !== -1);
  assert.ok(trustText.indexOf('Sponsored by Example') !== -1);
  assert.ok(trustText.indexOf('Not a pet. Wildlife education only.') !== -1);
  trustText.split('\n').forEach(() => {});
  post.querySelectorAll('.subx-more-trust').forEach((n) => assert.equal(hiddenOf(n), false));
  const disc = doc.querySelector('[data-room-disclaimer]');
  assert.equal(hiddenOf(disc), false, 'room disclaimer element stays');
  const note = post.querySelector('.subx-more-note');
  assert.ok(note && !hiddenOf(note), 'disclaimer copy sits above More');
  assert.ok(note.textContent.indexOf('Not a pet. Wildlife education only.') !== -1);
  const bar = post.querySelector('.subx-more-bar');
  const kids = note.parentNode.childNodes;
  assert.ok(kids.indexOf(note) < kids.indexOf(bar), 'disclaimer is above the More bar');
  assert.equal(credit.parentNode, post.querySelector('.post-body'));
  assert.notEqual(credit.parentNode, post.querySelector('.post-image'), 'credit sits under the thumb, outside the clip');
  const img = post.querySelector('.post-image');
  assert.ok(img.classList.contains('subx-more-thumb'));
  const css = doc.getElementById('subx-more-style').textContent;
  assert.ok(css.indexOf('aspect-ratio:16/9') !== -1 && css.indexOf('max-height:200px') !== -1 && css.indexOf('max-height:260px') !== -1);
  img.querySelector('img').click();
  assert.equal(post.querySelector('.subx-more-btn').getAttribute('aria-expanded'), 'true', 'tap on the image expands');
  assert.ok(!img.classList.contains('subx-more-thumb'));
  ok('credit, disclaimer, WHOMARK, pill, and Report stay visible');
}

{
  const { post } = start('Hello.\n\nMore body.', { id: 'a b/c' });
  const link = post.querySelector('.subx-more-openlink');
  assert.equal(link.getAttribute('href'), '?p=' + encodeURIComponent('a b/c'));
  assert.equal(link.getAttribute('href'), '?p=a%20b%2Fc');
  assert.equal(link.textContent, 'Open post');
  const path = start('Hello.\n\nMore body.', { id: 'a b/c', attrs: { 'data-permalink': 'path' } });
  assert.equal(path.post.querySelector('.subx-more-openlink').getAttribute('href'), '/p/' + encodeURIComponent('a b/c'));
  ok('Open post uses encodeURIComponent');
}

{
  const { post, feed, r, doc } = start('Hello.\n\nMore body.');
  assert.equal(r.moLog.n, 1, 'one observer');
  assert.ok(r.moLog.targets.every((t) => t === feed), 'observer watches the feed');
  assert.ok(!r.moLog.targets.some((t) => t === doc.body), 'observer does not watch body');
  assert.equal(post.querySelectorAll('.subx-more-btn').length, 1);
  feed._mo.cb([]);
  assert.equal(post.querySelectorAll('.subx-more-btn').length, 1, 'a second pass does not add a button');
  assert.equal(r.moLog.n, 1, 'still one observer');
  const again = article(doc, 'p2', 'Another lead.\n\nAnother tail.');
  feed.appendChild(again);
  assert.equal(feed.querySelectorAll('.subx-more-btn').length, 2, 'a new post is decorated once');
  assert.equal(again.querySelectorAll('.subx-more-btn').length, 1);
  feed._mo.cb([]);
  assert.equal(again.querySelectorAll('.subx-more-btn').length, 1);
  ok('observer is idempotent');
}

{
  const { doc } = start('Hello.\n\nMore body.', { blockStyle: true });
  assert.equal(doc.getElementById('subx-more-style'), null, 'blocked style element is not left in the page');
  assert.equal(doc.adoptedStyleSheets.length, 1);
  assert.ok(doc.adoptedStyleSheets[0].css.indexOf('-webkit-line-clamp:4') !== -1, 'CSSOM gets the clamp rules');
  ok('CSP fallback uses the CSSOM');
}

{
  const wide = start(['one', 'two', 'three', 'four'].join('\n'), { wide: true });
  assert.ok(wide.post.querySelector('.subx-more-btn'), '4 lines need More at 768 and up');
  const phone = start(['one', 'two', 'three', 'four'].join('\n'), { wide: false });
  assert.equal(phone.post.querySelector('.subx-more-btn'), null, '4 lines fit under 768');
  ok('line count follows the viewport');
}

const rel = JSON.parse(fs.readFileSync(path.join(root, 'FACTORY_RELEASE.json'), 'utf8'));
const raw = fs.readFileSync(srcPath);
const hash = crypto.createHash('sha256').update(raw).digest('hex');
const entry = rel.optIn && rel.optIn['factory-more.js'];
assert.ok(entry, 'FACTORY_RELEASE.json lists factory-more.js');
assert.equal(entry.sha256, hash);
assert.equal(entry.bytes, raw.length);
ok('release sha256 matches the file');

console.log('\n' + pass + ' passed');
