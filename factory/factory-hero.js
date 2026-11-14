/* SubX shared shell add-on: rotating hero photo (factory-hero.js, opt-in).
   A room loads it after factory.js and lists its photos in site.json heroImages ({ interval, items: [...] }).
   Without heroImages, or with no valid item, it adds nothing: no element, no class, no CSS, no layout change.
   It reads only the room's own site.json (the data-site URL on factory.js, the same request as the preload),
   writes nothing, and every photo is self-hosted; credit links leave the page only when clicked.
   The slot sits at the top of the center column (#page-thoughts), above the For You tabs and the composer, under
   the room's own brief strip when it has one: a 3:1 strip capped at 232px on desktop, a 16:9 photo edge to edge on phone. */
(function () {
  'use strict';
  if (window.SubxHero) return;
  /* hx-core:start (shared by factory/factory-hero.js and the hub's hub.js; test/hub_hero.test.py keeps the copies identical) */
  var HX_REQ = ['src', 'alt', 'credit', 'license', 'licenseUrl', 'sourceUrl'];
  function hxLicenseOk(l) {
    l = String(l == null ? '' : l).trim();
    if (/(^|[^A-Za-z])(NC|ND)([^A-Za-z]|$)/i.test(l)) return false;
    return /^(CC0( 1\.0)?|Public Domain( Mark)?( 1\.0)?|PDM( 1\.0)?|CC BY(-SA)?( [0-9]\.[0-9])?( [a-z]{2})?)$/i.test(l);
  }
  function hxHttps(u) { return /^https:\/\/[a-z0-9.-]+\.[a-z]{2,}\/[^\s"'<>\\]*$/i.test(String(u == null ? '' : u)); }
  function hxLocal(u) {
    u = String(u == null ? '' : u);
    return /^\/?[A-Za-z0-9_][A-Za-z0-9_\/.-]*\.(webp|jpe?g|png|avif)$/.test(u) && u.indexOf('..') < 0 && u.indexOf('//') < 0;
  }
  // Every item needs src, alt, credit, license, licenseUrl and sourceUrl. An item that fails is refused (never shown
  // without its credit) and listed in refused. Allowed licenses: CC0, Public Domain Mark, CC BY, CC BY-SA. NC or ND is refused.
  function hxValidate(cfg) {
    var out = { interval: 7000, items: [], refused: [] };
    if (!cfg || typeof cfg !== 'object' || !Array.isArray(cfg.items)) return out;
    var iv = Number(cfg.interval);
    if (iv >= 4000 && iv <= 15000) out.interval = Math.round(iv);
    cfg.items.forEach(function (it, n) {
      var why = '';
      if (!it || typeof it !== 'object') why = 'not an object';
      else {
        for (var k = 0; k < HX_REQ.length && !why; k++) {
          if (typeof it[HX_REQ[k]] !== 'string' || !it[HX_REQ[k]].trim()) why = 'missing ' + HX_REQ[k];
        }
        if (!why && !hxLicenseOk(it.license)) why = 'license not allowed';
        if (!why && !(hxHttps(it.licenseUrl) && hxHttps(it.sourceUrl))) why = 'credit links must be https';
        if (!why && !hxLocal(it.src)) why = 'src must be a self-hosted image path';
        if (!why && it.srcSm != null && !hxLocal(it.srcSm)) why = 'srcSm must be a self-hosted image path';
        if (!why && it.fallback != null && !hxLocal(it.fallback)) why = 'fallback must be a self-hosted image path';
      }
      if (why) { out.refused.push({ index: n, why: why }); return; }
      var w = Number(it.w), h = Number(it.h);
      out.items.push({
        src: it.src, srcSm: it.srcSm || '', fallback: it.fallback || '',
        w: w > 0 && w <= 4000 ? Math.round(w) : 1200, h: h > 0 && h <= 4000 ? Math.round(h) : 800,
        focal: /^[0-9]{1,3}% [0-9]{1,3}%$/.test(String(it.focal || '')) ? it.focal : '50% 50%',
        alt: it.alt.trim(), credit: it.credit.trim(), license: it.license.trim(),
        licenseUrl: it.licenseUrl, sourceUrl: it.sourceUrl
      });
    });
    return out;
  }
  var HX_SVG_PAUSE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  var HX_SVG_NEXT = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  function hxEl(e, cls, attrs) {
    if (cls) e.className = cls;
    for (var k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) e.setAttribute(k, attrs[k]);
    return e;
  }
  function hxLoad(slide) {
    if (!slide || slide.hxLoaded) return;
    slide.hxLoaded = true;
    var it = slide.hxItem, img = slide.querySelector('img'), source = slide.querySelector('source');
    if (source) source.setAttribute('srcset', it.src + ' ' + it.w + 'w' + (it.srcSm ? ', ' + it.srcSm + ' ' + Math.round(it.w / 2) + 'w' : ''));
    img.setAttribute('src', it.fallback || it.src);
  }
  // Builds the carousel figure and inserts it into opts.host (before opts.before). Returns the figure, or null when
  // there is nothing valid to show (then nothing is added). Photo 1 loads eagerly at low priority; photo N+1 gets its
  // src only when photo N becomes active, so a visitor who never sees a photo never downloads it.
  function hxMount(opts) {
    var v = hxValidate(opts.cfg);
    if (v.refused.length && window.console) console.warn('heroImages: refused', v.refused);
    var items = v.items;
    if (!items.length || !opts.host) return null;
    var multi = items.length > 1;
    var fig = hxEl(document.createElement('figure'), 'hx ' + (opts.cls || ''), { role: 'group', 'aria-roledescription': 'carousel', 'aria-label': opts.label || 'Photos' });
    var frame = hxEl(document.createElement('div'), 'hx-frame', {});
    var slides = items.map(function (it, n) {
      var s = hxEl(document.createElement('div'), 'hx-slide' + (n === 0 ? ' is-active' : ''), { role: 'group', 'aria-roledescription': 'slide', 'aria-label': (n + 1) + ' of ' + items.length });
      if (n) s.setAttribute('aria-hidden', 'true');
      var pic = hxEl(document.createElement('picture'), '', {});
      if (/\.webp$/i.test(it.src) && it.fallback) pic.appendChild(hxEl(document.createElement('source'), '', { type: 'image/webp', sizes: opts.sizes || '100vw' }));
      var img = hxEl(document.createElement('img'), '', { alt: it.alt, width: String(it.w), height: String(it.h), decoding: 'async', loading: n === 0 ? 'eager' : 'lazy' });
      if (n === 0) img.setAttribute('fetchpriority', 'low');
      img.style.objectPosition = it.focal;
      pic.appendChild(img);
      s.appendChild(pic);
      s.hxItem = it;
      frame.appendChild(s);
      return s;
    });
    fig.appendChild(frame);
    var bar = hxEl(document.createElement('div'), 'hx-bar', {});
    var credit = hxEl(document.createElement('p'), 'hx-credit', {});
    var author = hxEl(document.createElement('a'), 'hx-author', { rel: 'noopener noreferrer', target: '_blank' });
    var lic = hxEl(document.createElement('a'), 'hx-lic', { rel: 'noopener noreferrer', target: '_blank' });
    credit.appendChild(document.createTextNode('Photo: '));
    credit.appendChild(author);
    credit.appendChild(document.createTextNode(' \u00b7 '));
    credit.appendChild(lic);
    bar.appendChild(credit);
    var ctrl = hxEl(document.createElement('div'), 'hx-ctrl', {});
    var dots = hxEl(document.createElement('span'), 'hx-dots', { 'aria-hidden': 'true' });
    var dotEls = items.map(function (it, n) { var d = hxEl(document.createElement('span'), 'hx-dot' + (n === 0 ? ' is-active' : ''), {}); dots.appendChild(d); return d; });
    var pauseBtn = hxEl(document.createElement('button'), 'hx-pause', { type: 'button', 'aria-pressed': 'false', 'aria-label': 'Pause photos' });
    pauseBtn.innerHTML = HX_SVG_PAUSE;
    var nextBtn = hxEl(document.createElement('button'), 'hx-next', { type: 'button', 'aria-label': 'Next photo' });
    nextBtn.innerHTML = HX_SVG_NEXT;
    ctrl.appendChild(dots);
    ctrl.appendChild(pauseBtn);
    ctrl.appendChild(nextBtn);
    if (multi) bar.appendChild(ctrl);
    fig.appendChild(bar);
    var live = hxEl(document.createElement('div'), 'hx-sr', { 'aria-live': 'polite', 'aria-atomic': 'true' });
    fig.appendChild(live);
    var i = 0, timer = null, userPaused = false, hover = false;
    var reduce = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
    function show(n, user) {
      i = (n + slides.length) % slides.length;
      hxLoad(slides[i]);
      slides.forEach(function (s, k) {
        s.classList.toggle('is-active', k === i);
        if (k === i) s.removeAttribute('aria-hidden'); else s.setAttribute('aria-hidden', 'true');
      });
      dotEls.forEach(function (d, k) { d.classList.toggle('is-active', k === i); });
      var it = slides[i].hxItem;
      author.textContent = it.credit; author.setAttribute('href', it.sourceUrl);
      lic.textContent = it.license; lic.setAttribute('href', it.licenseUrl);
      if (user) live.textContent = 'Photo ' + (i + 1) + ' of ' + slides.length;
      if (multi) hxLoad(slides[(i + 1) % slides.length]);
    }
    function running() { return multi && !userPaused && !hover && !reduce.matches && !document.hidden; }
    function tick() {
      clearTimeout(timer);
      if (running()) timer = setTimeout(function () { show(i + 1); tick(); }, v.interval);
    }
    function syncReduce() { pauseBtn.hidden = !!reduce.matches; tick(); }
    nextBtn.addEventListener('click', function () { show(i + 1, true); tick(); });
    pauseBtn.addEventListener('click', function () {
      userPaused = !userPaused;
      pauseBtn.setAttribute('aria-pressed', String(userPaused));
      pauseBtn.setAttribute('aria-label', userPaused ? 'Play photos' : 'Pause photos');
      tick();
    });
    fig.addEventListener('mouseenter', function () { hover = true; tick(); });
    fig.addEventListener('mouseleave', function () { hover = false; tick(); });
    fig.addEventListener('focusin', function () { hover = true; tick(); });
    fig.addEventListener('focusout', function (e) { if (!fig.contains(e.relatedTarget)) { hover = false; tick(); } });
    document.addEventListener('visibilitychange', tick);
    if (reduce.addEventListener) reduce.addEventListener('change', syncReduce);
    opts.host.insertBefore(fig, opts.before || null);
    show(0);
    syncReduce();
    fig.hxShow = function (n) { show(n, true); };
    fig.hxPause = function () { userPaused = true; pauseBtn.setAttribute('aria-pressed', 'true'); pauseBtn.setAttribute('aria-label', 'Play photos'); clearTimeout(timer); };
    return fig;
  }
  var HX_CSS_BASE =
    '.hx{margin:0;position:relative;min-width:0;overflow:hidden;z-index:0;background:var(--surface,#1c1c20)}' +
    '.hx-frame{position:absolute;inset:0;overflow:hidden}' +
    '.hx-slide{position:absolute;inset:0;opacity:0;transition:opacity 700ms ease}' +
    '.hx-slide.is-active{opacity:1;z-index:1}' +
    '.hx-slide picture{display:block;width:100%;height:100%}' +
    '.hx-slide img{width:100%;height:100%;object-fit:cover;display:block}' +
    '.hx-bar{position:absolute;left:0;right:0;bottom:0;z-index:1;display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:4px 8px;padding:22px 10px 8px 12px;background:linear-gradient(to bottom,rgba(0,0,0,0),rgba(0,0,0,.45));pointer-events:none}' +
    '.hx-credit{flex:0 1 auto;font:500 11px/1.3 var(--ui,system-ui,sans-serif);color:#fff;margin:0;min-width:0;max-width:100%;pointer-events:auto;background:rgba(0,0,0,.62);padding:3px 7px;border-radius:6px;overflow-wrap:anywhere;white-space:normal}' +
    '.hx-credit a{color:#fff;text-decoration:underline;text-decoration-color:rgba(255,255,255,.55);text-underline-offset:2px}' +
    '.hx-credit a:hover{text-decoration-color:#fff}' +
    '.hx-ctrl{display:flex;align-items:center;gap:3px;flex:none;margin-left:auto;pointer-events:auto}' +
    '.hx-dots{display:flex;align-items:center;padding:0 6px;height:24px;border-radius:12px;background:rgba(0,0,0,.45)}' +
    '.hx-dot{width:6px;height:6px;margin:0 2px;display:inline-block;border-radius:3px;background:rgba(255,255,255,.6);box-shadow:0 0 0 1px rgba(0,0,0,.3);transition:width .25s}' +
    '.hx-dot.is-active{width:16px;background:#fff}' +
    '.hx-next,.hx-pause{width:32px;height:32px;margin-left:4px;padding:0;border-radius:50%;border:0;background:rgba(0,0,0,.55);color:#fff;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}' +
    '.hx-pause[hidden]{display:none}' +
    '.hx-pause[aria-pressed="true"] svg{display:none}' +
    '.hx-pause[aria-pressed="true"]::before{content:"";border-left:9px solid #fff;border-top:6px solid transparent;border-bottom:6px solid transparent;margin-left:2px}' +
    '.hx :focus-visible{outline:2px solid #fff;outline-offset:2px;box-shadow:0 0 0 4px rgba(0,0,0,.6)}' +
    '.hx-sr{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}' +
    '@media (prefers-reduced-motion: reduce){.hx-slide,.hx-dot{transition:none} }';
  function hxCss(extra) {
    if (document.getElementById('hx-style')) return;
    var st = document.createElement('style');
    st.id = 'hx-style';
    st.textContent = HX_CSS_BASE + (extra || '');
    (document.head || document.documentElement).appendChild(st);
  }
  /* hx-core:end */
  var HX_CSS_ROOM =
    '.hx-room{display:block;aspect-ratio:3 / 1;max-height:232px;width:auto;margin:12px 16px 14px;border-radius:16px;border:1px solid var(--border,#2c2c32);isolation:isolate}' +
    '@media (max-width:999px){.hx-room{aspect-ratio:16 / 9;max-height:none;margin:0 0 12px;border-radius:0;border-width:0 0 1px}}';
  function siteUrl() {
    var s = document.querySelector('script[data-site]');
    return (s && s.getAttribute('data-site')) || 'site.json';
  }
  function boot() {
    var page = document.getElementById('page-thoughts');
    if (!page || page.querySelector('.hx')) return;
    fetch(siteUrl(), { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (site) {
      if (!site || !site.heroImages) return;
      if (!hxValidate(site.heroImages).items.length) { hxMount({ cfg: site.heroImages }); return; }
      hxCss(HX_CSS_ROOM);
      hxMount({
        cfg: site.heroImages, host: page, before: page.querySelector(':scope > .thoughts-tabs') || page.firstChild, cls: 'hx-room',
        label: String(site.name || site.siteId || 'Room') + ' photos', sizes: '(min-width:1000px) 760px, 100vw'
      });
    }).catch(function () {});
  }
  window.SubxHero = { validate: hxValidate, mount: hxMount, css: hxCss, licenseOk: hxLicenseOk };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
