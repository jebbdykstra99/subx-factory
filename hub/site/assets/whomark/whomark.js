/* WHOMARK disclosure mark for the hub (family final-v4.1, palette C, light background).
 * Self-hosted, no inline styles or scripts: the CSS lives in hub.css (.whomark*). Art = the final-v4.1 SVG files in
 * /assets/whomark/ (whomark-<tier>-<s14|s16|lg>-color.svg); snapped s14/s16 files are never scaled.
 * Config mirrors hub/src/whomark/config.json (test/whomark_hub.test.py keeps them equal).
 * The glyph is never shown without its visible text label. */
(function (g) {
  'use strict';
  var CFG = {
    family: 'final-v4.1', placeholder: false, assetBase: '/assets/whomark/', defaultSizePx: 16,
    minSizePx: { human: 14, ai: 14, hybrid: 16 }, labelRequiredAtOrBelowPx: 14,
    tiers: {
      human: { textLabel: 'Human-made', title: 'WHOMARK: Human-made', plainText: 'Human-made' },
      ai: { textLabel: 'AI-made', stewardLabel: 'AI-made · AI steward', title: 'WHOMARK: AI-made', plainText: 'AI-made' },
      hybrid: { textLabel: 'Human + AI', title: 'WHOMARK: Human + AI', plainText: 'Human + AI: {names}' }
    }
  };
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); }
  function tierCfg(t) { return Object.prototype.hasOwnProperty.call(CFG.tiers, t) ? CFG.tiers[t] : null; }
  function namesText(names) {
    var a = Array.isArray(names) ? names : (names == null || names === '' ? [] : String(names).split(','));
    return a.map(function (n) { return String(n == null ? '' : n).replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim(); })
      .filter(Boolean).join(', ').slice(0, 120);
  }
  // Snap a requested size to a real file: 14 -> s14, 15..23 -> s16, 24+ -> lg (scalable). Never below the tier minimum.
  function snap(tier, px) {
    var min = CFG.minSizePx[tier] || 14;
    var s = Math.max(min, Math.round(Number(px) || CFG.defaultSizePx));
    if (s < 16) return { px: 14, file: 's14' };
    if (s < 24) return { px: 16, file: 's16' };
    return { px: s, file: 'lg' };
  }
  // whoMark(tier, names, opts) -> HTML. opts: { size: px, steward: true (AI steward posts), cls }. Label is always shown.
  function whoMark(tier, names, opts) {
    var t = tierCfg(tier);
    if (!t) return '';
    opts = opts || {};
    var z = snap(tier, opts.size);
    var label = tier === 'ai' && opts.steward ? t.stewardLabel : t.textLabel;
    var n = tier === 'hybrid' ? namesText(names) : '';
    var aria = t.title + (n ? ' (' + n + ')' : '');
    var src = CFG.assetBase + 'whomark-' + tier + '-' + z.file + '-color.svg';
    return '<span class="whomark whomark--color whomark--' + tier + (z.file === 'lg' ? ' whomark--lg' : z.file === 's14' ? ' whomark--s14' : '') +
      (opts.cls ? ' ' + esc(opts.cls) : '') + '" role="img" aria-label="' + esc(aria) + '" data-wm-family="' + CFG.family + '">' +
      '<span class="whomark-icon"><img src="' + src + '" width="' + z.px + '" height="' + z.px + '" alt="" decoding="async"></span>' +
      '<span class="whomark-label" aria-hidden="true">' + esc(label) + '</span></span>';
  }
  function whoMarkPlain(tier, names) {
    var t = tierCfg(tier);
    if (!t) return '';
    var n = namesText(names);
    return n ? t.plainText.split('{names}').join(n) : t.plainText.replace(/[\s:]*\{names\}/, '');
  }
  function whoMarkBadges(tier) {
    return tierCfg(tier) ? { og: CFG.assetBase + 'whomark-' + tier + '-lg-color-128px.png', corner: CFG.assetBase + 'whomark-' + tier + '-lg-color-48px.png' } : null;
  }
  g.whoMark = whoMark;
  g.whoMarkPlain = whoMarkPlain;
  g.whoMarkBadges = whoMarkBadges;
  g.whoMarkConfig = function () { return JSON.parse(JSON.stringify(CFG)); };
  // Upgrade the shell's AI steward text pill and any declarative [data-whomark] element in place.
  var PILL = '.post-steward-pill[title^="Operated by SubX"]';
  var DECL = '[data-whomark]';
  function collect(root, sel) {
    var out = [];
    if (typeof root.matches === 'function' && root.matches(sel)) out.push(root);
    var f = root.querySelectorAll(sel);
    for (var i = 0; i < f.length; i++) out.push(f[i]);
    return out;
  }
  function attr(el, k) { return el && typeof el.getAttribute === 'function' ? el.getAttribute(k) : null; }
  function whoMarkUpgrade(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return 0;
    var n = 0, list = collect(root, PILL), i;
    for (i = 0; i < list.length; i++) if (list[i].parentNode) { list[i].outerHTML = whoMark('ai', null, { steward: true }); n++; }
    var d = collect(root, DECL);
    for (i = 0; i < d.length; i++) {
      var el = d[i];
      if (!el.parentNode || el.classList && el.classList.contains('whomark')) continue;
      var h = whoMark(attr(el, 'data-whomark'), attr(el, 'data-whomark-names'),
        { size: attr(el, 'data-whomark-size'), steward: attr(el, 'data-whomark-steward') === 'true', cls: attr(el, 'data-whomark-class') });
      if (h) { el.outerHTML = h; n++; }
    }
    return n;
  }
  g.whoMarkUpgrade = whoMarkUpgrade;
  if (typeof document !== 'undefined' && typeof MutationObserver !== 'undefined' && document.documentElement) {
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var a = muts[i].addedNodes;
        for (var j = 0; j < a.length; j++) if (a[j].nodeType === 1) whoMarkUpgrade(a[j]);
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
    whoMarkUpgrade(document);
  }
})(typeof window !== 'undefined' ? window : globalThis);
