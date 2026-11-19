// Split opt-in feature code out of the folded factory.js (core byte budget, lean audit 2026-10-22).
//   in : factory.js (output of fold.py, the single-file build)
//   out: factory.js (core, every room), factory-gp.js (gpchat only), factory-rail.js (NWS/CWF/BART live rails),
//        factory-reports.js (report loop, features.reportLoop)
// Moved functions keep their exact source. Inside an opt-in file, core functions are bound once by name
// (function declarations never get reassigned) and core variables are read/written through live accessors
// (core.site, core.SITE_ID, ...), so behavior is identical to the single-file build when the file is loaded.
// Core keeps a stub for every moved function it calls; with the file absent the stub returns what the
// feature-off path returns. Opt-in files push an installer onto window.__subxPlugins and must load BEFORE
// factory.js. The script fails the build if a moved function is called from core without a stub.
import fs from 'fs';
import crypto from 'crypto';
import * as espree from 'espree';
import * as eslintScope from 'eslint-scope';

// Lazy stories split. Input is the room v1.2.11 core (sha256 f18d07e4…), after the
// featured addon() patch and before this pass. Moves the stories cluster into
// factory-stories.js and leaves stubs that load it from a fixed same-origin path
// (addon('factory-stories'), the same script URL pattern as loadSigninModule)
// only when storiesOn(). Does not rewrite factory-signin.js, factory-reports.js,
// factory-gp.js, or factory-rail.js.
if (process.argv.includes('--stories')) {
  splitStories();
  process.exit(0);
}

const GROUPS = [
  {
    file: 'factory-gp.js',
    title: 'gpchat only: Watchlist (features.watchlist), topic follow (features.topicFollow), session seeds (features.sessionSeeds), F1 rail (rail.kind f1-calendar)',
    fns: [
      // topic follow
      'topicFollowsStoreKey', 'loadTopicFollows', 'topicFollowSlug', 'cardTopicKey', 'isTopicFollowed', 'setTopicFollowed',
      'topicFollowLabel', 'followIconSvg', 'renderFollowBtn', 'paintFollowBtn', 'syncTopicFollowButtons', 'toggleTopicFollow',
      // session seeds
      'sessionSeedList', 'sessionSeedPosts',
      // watchlist + topic feed
      'taxonomyCatalog', 'activeTopics', 'topicById', 'postHasTopic', 'topicFocusHtml', 'renderTopicFeed',
      'defaultWatchlistIds', 'sanitizeTopicIds', 'watchlistStoreKey', 'savePersonalWatchlist', 'personalWatchlistIds',
      'addToWatchlist', 'removeFromWatchlist', 'watchRowHtml', 'renderWatchlistCatalog', 'renderWatchlist',
      // F1 rail (OpenF1)
      'f1ParseWhen', 'f1FormatLocal', 'f1Sessions', 'f1RaceFromPayload', 'f1CardsFromRace', 'fetchF1Json', 'openf1Url',
      'fetchOpenF1Json', 'f1ParseIso', 'f1OpenF1Tag', 'f1FormatDuration', 'f1FormatGap', 'f1DriverLabel', 'f1Top3Line',
      'f1SessionRank', 'f1SessionUsable', 'f1PickResultSession', 'overlayOpenF1Cards', 'fetchF1Cards', 'stalePreRaceCard',
      'mergeF1Rail'
    ],
    vars: ['LS_TOPIC_FOLLOWS', 'watchlistQuery', 'F1_SESSION_KEYS', 'F1_SESSION_MS'],
    stubs: {
      renderFollowBtn: "return '';",
      syncTopicFollowButtons: '',
      toggleTopicFollow: '',
      sessionSeedPosts: 'return [];',
      renderTopicFeed: '',
      renderWatchlist: "var box = document.getElementById('watchlist');\n    if (box) box.hidden = true;",
      addToWatchlist: '',
      removeFromWatchlist: '',
      fetchF1Cards: "return Promise.reject(new Error('factory-gp.js not loaded'));",
      mergeF1Rail: 'return (cards || []).concat(extra || []);'
    },
    stubParams: { mergeF1Rail: 'cards, extra' }
  },
  {
    file: 'factory-rail.js',
    title: 'live rails: NWS forecast + alerts (rail.kind nws-forecast, or rail lat/lon/forecastUrl), NWS CWF (nws-cwf), BART BSA (bart-bsa)',
    fns: [
      'nwsHeaders', 'nwsTagFor', 'nwsCardFromPeriod', 'nwsCardFromAlert', 'resolveForecastUrl', 'fetchNwsCards',
      'cwfHeadline', 'cwfSnippet', 'cwfTag', 'parseCwfPeriods', 'parseCwfCards', 'latestCwfProductId', 'fetchCwfCards',
      'bartCdata', 'fetchBartCards'
    ],
    vars: [],
    stubs: {
      fetchNwsCards: "return Promise.reject(new Error('factory-rail.js not loaded'));",
      fetchCwfCards: "return Promise.reject(new Error('factory-rail.js not loaded'));",
      fetchBartCards: "return Promise.reject(new Error('factory-rail.js not loaded'));"
    },
    stubParams: {}
  },
  {
    file: 'factory-reports.js',
    title: 'report loop (A9): report status + admin triage with audit fields, "My reports", report_update notif (site.json features.reportLoop)',
    fns: [
      'reportTriage', 'reportUpdateText', 'setReportStatus', 'syncMyReports', 'openMyReports', 'myReportsHtml', 'closeMyReports',
      'wireReportLoop', 'restoreHiddenReport', 'adminMassHide'
    ],
    vars: ['REPORT_STATUS', 'reportLoopWired'],
    stubs: {
      reportTriage: "return '<button type=\"button\" class=\"post-action\" data-report-dismiss=\"' + escapeHtml(r.id) + '\">Dismiss</button>';",
      syncMyReports: ''
    },
    stubParams: { reportTriage: 'r' }
  }
];
const INSTALL_AFTER = '  const DM_TEXT_MAX = 1000;\n';

const src = fs.readFileSync('factory.js', 'utf8');
const ast = espree.parse(src, { ecmaVersion: 2020, range: true });
const sm = eslintScope.analyze(ast, { ecmaVersion: 2020 });
const iife = sm.scopes.find((s) => s.type === 'function' && s.upper && s.upper.type === 'global');
const V = new Map(iife.variables.map((v) => [v.name, v]));
const fail = (m) => { console.error('split: ' + m); process.exit(1); };

const lineStart = (i) => src.lastIndexOf('\n', i - 1) + 1;
const lineEnd = (i) => { const j = src.indexOf('\n', i); return j < 0 ? src.length : j + 1; };
function declRange(name) {
  const v = V.get(name);
  if (!v || v.defs.length !== 1) fail('not a single top-level declaration: ' + name);
  const d = v.defs[0];
  let node;
  if (d.type === 'FunctionName') node = d.node;
  else if (d.type === 'Variable') { node = d.parent; if (node.declarations.length !== 1) fail('multi-declaration: ' + name); }
  else fail('unsupported declaration: ' + name);
  let s = lineStart(node.range[0]);
  const e = lineEnd(node.range[1]);
  if (src.slice(s, node.range[0]).trim() || src.slice(node.range[1], e).trim()) fail('declaration does not own its lines: ' + name);
  // carry the comment lines directly above (no blank line between)
  for (;;) {
    const ps = lineStart(s - 1);
    if (s === 0 || !/^\s*\/\//.test(src.slice(ps, s))) break;
    s = ps;
  }
  return { name, kind: d.type, s, e, node };
}

const moved = new Map(); // name -> { group, range }
for (const g of GROUPS) {
  g.ranges = [...g.fns, ...g.vars].map(declRange);
  for (const r of g.ranges) { if (moved.has(r.name)) fail('in two groups: ' + r.name); moved.set(r.name, { g, r }); }
}
const groupOf = (pos) => { for (const g of GROUPS) for (const r of g.ranges) if (pos >= r.s && pos < r.e) return g; return null; };

// Classify every reference to a top-level binding.
const edits = []; // [start, end, text] inside moved code
for (const g of GROUPS) { g.coreFns = new Set(); g.coreVars = new Map(); }
const calledFromCore = new Map();
for (const v of iife.variables) {
  if (!v.defs.length) continue;
  const isFn = v.defs[0].type === 'FunctionName';
  for (const ref of v.references) {
    const id = ref.identifier;
    const at = groupOf(id.range[0]);
    const m = moved.get(v.name);
    if (!at) {
      if (!m) continue;
      if (id.range[0] >= m.r.node.range[0] && id.range[1] <= m.r.node.range[1]) continue;
      if (m.r.kind !== 'FunctionName') fail('core uses moved variable ' + v.name);
      calledFromCore.set(v.name, m.g);
      continue;
    }
    if (m && m.g === at) continue; // same file
    if (m && m.g !== at) fail(v.name + ' crosses opt-in files');
    if (isFn) { at.coreFns.add(v.name); continue; }
    const w = at.coreVars.get(v.name) || { write: false };
    if (ref.isWrite()) w.write = true;
    at.coreVars.set(v.name, w);
    edits.push([id.range[0], id.range[1], 'core.' + v.name]);
  }
}
for (const [name, g] of calledFromCore) if (!(name in g.stubs)) fail('core calls ' + name + ' (' + g.file + ') with no stub');
for (const g of GROUPS) for (const name of Object.keys(g.stubs)) if (!calledFromCore.has(name)) fail('unused stub ' + name);

function rewritten(s, e) {
  let out = '', pos = s;
  for (const [a, b, t] of edits.filter((x) => x[0] >= s && x[1] <= e).sort((x, y) => x[0] - y[0])) { out += src.slice(pos, a) + t; pos = b; }
  return out + src.slice(pos, e);
}

const version = (JSON.parse(fs.readFileSync('../FACTORY_RELEASE.json', 'utf8')).version);
// A stories-only release must not rewrite the committed opt-in banners. factory-reports.js
// (and gp / rail) stay byte-identical; their banner keeps the version already on disk.
function bannerVersion(file) {
  try {
    const prev = fs.readFileSync('../factory/' + file, 'utf8');
    const m = prev.match(/subx-factory (v\d+\.\d+\.\d+), opt-in/);
    if (m) return m[1];
  } catch (e) { /* first generation */ }
  return version;
}
for (const g of GROUPS) {
  const fns = [...g.coreFns].sort();
  const exportsList = [...g.ranges].filter((r) => r.name in g.stubs).map((r) => r.name);
  const gVersion = bannerVersion(g.file);
  let out = '/* SubX ' + g.file + ' (subx-factory ' + gVersion + ', opt-in). DO NOT EDIT IN A ROOM REPO; generated by build/split.mjs.\n' +
    ' * ' + g.title + '.\n' +
    ' * Load before factory.js: <script src="' + g.file + '?v=N"></script>. Rooms that do not load it run the core stubs. */\n' +
    '(window.__subxPlugins = window.__subxPlugins || []).push(function (core) {\n  \'use strict\';\n';
  for (let i = 0; i < fns.length; i += 4) out += '  var ' + fns.slice(i, i + 4).map((n) => n + ' = core.' + n).join(', ') + ';\n';
  out += '\n';
  for (const r of [...g.ranges].sort((a, b) => a.s - b.s)) out += rewritten(r.s, r.e);
  out += '\n  return {\n' + exportsList.map((n) => '    ' + n + ': ' + n).join(',\n') + '\n  };\n});\n';
  fs.writeFileSync(g.file, out);
}

// Core: drop moved declarations, put stubs where the originals were, add the installer.
const cuts = [];
for (const g of GROUPS) for (const r of g.ranges) {
  let text = '';
  if (r.name in g.stubs) {
    const body = g.stubs[r.name];
    const call = 'PLUGIN.' + r.name + '.apply(null, arguments)';
    text = '  function ' + r.name + '(' + (g.stubParams[r.name] || '') + ') { // ' + g.file + '\n' +
      '    if (PLUGIN.' + r.name + ') return ' + call + ';\n' + (body ? '    ' + body + '\n' : '') + '  }\n';
  }
  let e = r.e;
  // no stub left behind: drop one of the two blank lines that surrounded the declaration
  if (!text && src.slice(r.s - 2, r.s) === '\n\n' && src[e] === '\n') e += 1;
  cuts.push([r.s, e, text]);
}
const coreFns = new Set(), coreVars = new Map();
for (const g of GROUPS) { g.coreFns.forEach((n) => coreFns.add(n)); g.coreVars.forEach((w, n) => coreVars.set(n, (coreVars.get(n) || false) || w.write)); }
const ia = src.indexOf(INSTALL_AFTER);
if (ia < 0 || src.indexOf(INSTALL_AFTER, ia + 1) >= 0) fail('installer anchor');
const members = [...coreFns].sort().map((n) => '    ' + n + ': ' + n)
  .concat([...coreVars.keys()].sort().map((n) => '    get ' + n + '() { return ' + n + '; }' + (coreVars.get(n) ? ',\n    set ' + n + '(v) { ' + n + ' = v; }' : '')));
// Opt-in files push installers onto window.__subxPlugins before factory.js runs. A room that does not load one keeps
// the neutral stubs (feature-off behavior). (No comment in the emitted core; lean trim 2026-10-22.)
const installer = '\n  var PLUGIN = {};\n  var CORE = {\n' + members.join(',\n') + '\n  };\n' +
  '  (window.__subxPlugins || []).forEach(function (install) {\n' +
  '    var api = install(CORE) || {};\n    Object.keys(api).forEach(function (k) { PLUGIN[k] = api[k]; });\n  });\n';
cuts.push([ia + INSTALL_AFTER.length, ia + INSTALL_AFTER.length, installer]);
cuts.sort((a, b) => b[0] - a[0]);
let core = src;
for (const [s, e, t] of cuts) core = core.slice(0, s) + t + core.slice(e);
fs.writeFileSync('factory.js', core);
console.log('split: core ' + Buffer.byteLength(core) + ' B; ' + GROUPS.map((g) => g.file + ' ' + fs.statSync(g.file).size + ' B').join('; '));

function splitStories() {
  const ROOM_SHA = 'f18d07e4db5aaa2722f284aba542eb6b41a48699ae2bad0c54bbec5e558a29d0';
  const KEEP = new Set(['storiesCfg', 'storiesOn']);
  const EXPORTS = ['openStoriesComposer', 'closeStoriesComposer', 'closeStoriesViewer', 'renderStoriesTray', 'syncStoriesTray', 'initStories'];
  const src = fs.readFileSync('factory.js', 'utf8');
  const sha = crypto.createHash('sha256').update(src).digest('hex');
  if (sha !== ROOM_SHA) fail('stories input is not room v1.2.11 factory.js sha256 ' + ROOM_SHA.slice(0, 16) + ' (got ' + sha.slice(0, 16) + ')');
  if (src.includes('function loadStoriesModule')) fail('stories already split');
  const ast = espree.parse(src, { ecmaVersion: 2020, range: true });
  const scope = eslintScope.analyze(ast, { ecmaVersion: 2020 });
  const iife = scope.scopes.find((s) => s.type === 'function' && s.upper && s.upper.type === 'global');
  const clusterStart = src.indexOf('  var STORIES_TTL_MS');
  const clusterEnd = src.indexOf('  function boot(data)');
  if (clusterStart < 0 || clusterEnd < clusterStart) fail('stories cluster anchors');
  const lineStart = (i) => src.lastIndexOf('\n', i - 1) + 1;
  const lineEnd = (i) => { const j = src.indexOf('\n', i); return j < 0 ? src.length : j + 1; };
  function declRange(v) {
    if (!v || v.defs.length !== 1) fail('not a single top-level declaration: ' + (v && v.name));
    const d = v.defs[0];
    let node;
    if (d.type === 'FunctionName') node = d.node;
    else if (d.type === 'Variable') { node = d.parent; if (node.declarations.length !== 1) fail('multi-declaration: ' + v.name); }
    else fail('unsupported declaration: ' + v.name);
    let s = lineStart(node.range[0]);
    const e = lineEnd(node.range[1]);
    if (src.slice(s, node.range[0]).trim() || src.slice(node.range[1], e).trim()) fail('declaration does not own its lines: ' + v.name);
    for (;;) {
      const ps = lineStart(s - 1);
      if (s === 0 || !/^\s*\/\//.test(src.slice(ps, s))) break;
      s = ps;
    }
    return { name: v.name, kind: d.type, s, e, node };
  }
  const moved = [];
  for (const v of iife.variables) {
    if (!v.defs.length || KEEP.has(v.name)) continue;
    const d = v.defs[0];
    const node = d.type === 'FunctionName' ? d.node : (d.type === 'Variable' ? d.parent : null);
    if (!node || node.range[0] < clusterStart || node.range[0] >= clusterEnd) continue;
    moved.push(declRange(v));
  }
  moved.sort((a, b) => a.s - b.s);
  const movedNames = new Set(moved.map((r) => r.name));
  if (moved.filter((r) => r.kind === 'FunctionName').length < 48) fail('expected about 50 stories functions, found ' + moved.filter((r) => r.kind === 'FunctionName').length);
  for (const name of EXPORTS) if (!movedNames.has(name)) fail('stories export missing: ' + name);
  const inMoved = (pos) => moved.some((r) => pos >= r.s && pos < r.e);
  const edits = [];
  const coreFns = new Set();
  const coreVars = new Map();
  for (const v of iife.variables) {
    if (!v.defs.length || movedNames.has(v.name)) continue;
    const isFn = v.defs[0].type === 'FunctionName';
    for (const ref of v.references) {
      if (!inMoved(ref.identifier.range[0])) continue;
      if (isFn) coreFns.add(v.name);
      else {
        const w = coreVars.get(v.name) || { write: false };
        if (ref.isWrite()) w.write = true;
        coreVars.set(v.name, w);
      }
      edits.push([ref.identifier.range[0], ref.identifier.range[1], 'core.' + v.name]);
    }
  }
  if ([...coreVars.values()].some((w) => w.write)) fail('stories assigns a core variable; needs a setter: ' + [...coreVars.entries()].filter((e) => e[1].write).map((e) => e[0]).join(','));
  function rewritten(s, e) {
    let out = '', pos = s;
    for (const [a, b, tx] of edits.filter((x) => x[0] >= s && x[1] <= e).sort((x, y) => x[0] - y[0])) {
      if (a < pos) fail('overlapping stories rewrite');
      out += src.slice(pos, a) + tx;
      pos = b;
    }
    return out + src.slice(pos, e);
  }
  const rel = JSON.parse(fs.readFileSync('../FACTORY_RELEASE.json', 'utf8'));
  const fns = [...coreFns].sort();
  let body = '';
  for (let i = 0; i < fns.length; i += 4) body += '  var ' + fns.slice(i, i + 4).map((n) => n + ' = core.' + n).join(', ') + ';\n';
  body += '\n';
  for (const r of moved) body += rewritten(r.s, r.e);
  let stories = '/* SubX factory-stories.js (subx-factory ' + rel.version + ', lazy). DO NOT EDIT IN A ROOM REPO; generated by build/split.mjs.\n' +
    ' * Stories cluster. factory.js loads this fixed same-origin file (factory-stories.js next to factory.js)\n' +
    ' * only when stories are on, using addon() the same way loadSigninModule loads factory-signin.js. */\n' +
    '(function() {\n  \'use strict\';\n' +
    '  var host = window.__subxStoriesHost;\n' +
    '  if (!host || typeof host.install !== \'function\') {\n' +
    '    console.warn(\'factory-stories: host not ready\');\n' +
    '    return;\n  }\n' +
    '  var core = host.core;\n' +
    body +
    '\n  host.install({\n' + EXPORTS.map((n) => '    ' + n + ': ' + n).join(',\n') + '\n  });\n})();\n';
  if (stories.slice(0, stories.indexOf(body)).includes('innerHTML')) fail('stories loader added innerHTML');
  const stubs = {
    openStoriesComposer: '  function openStoriesComposer(force) { // factory-stories.js\n' +
      '    if (!storiesOn()) return;\n' +
      '    if (storiesApi) return storiesApi.openStoriesComposer(force);\n' +
      '    return loadStoriesModule().then(function(api) { return api.openStoriesComposer(force); });\n  }\n',
    closeStoriesComposer: '  function closeStoriesComposer() { // factory-stories.js\n' +
      '    if (storiesApi) return storiesApi.closeStoriesComposer();\n' +
      '    return false;\n  }\n',
    closeStoriesViewer: '  function closeStoriesViewer() { // factory-stories.js\n' +
      '    if (storiesApi) return storiesApi.closeStoriesViewer();\n' +
      '    return false;\n  }\n',
    renderStoriesTray: '  function renderStoriesTray() { // factory-stories.js\n' +
      '    if (!storiesOn()) {\n' +
      '      var stale = document.getElementById(\'stories-tray\');\n' +
      '      if (stale) stale.hidden = true;\n' +
      '      return;\n    }\n' +
      '    if (storiesApi) return storiesApi.renderStoriesTray();\n' +
      '    return loadStoriesModule().then(function(api) { return api.renderStoriesTray(); });\n  }\n',
    syncStoriesTray: '  function syncStoriesTray() { // factory-stories.js\n' +
      '    if (!storiesOn()) {\n' +
      '      var el = document.getElementById(\'stories-tray\');\n' +
      '      if (el) el.hidden = true;\n' +
      '      return;\n    }\n' +
      '    if (storiesApi) return storiesApi.syncStoriesTray();\n' +
      '    return loadStoriesModule().then(function(api) { return api.syncStoriesTray(); });\n  }\n',
    initStories: '  function initStories() { // factory-stories.js\n' +
      '    if (!storiesOn()) return;\n' +
      '    return loadStoriesModule().then(function(api) { return api.initStories(); });\n  }\n'
  };
  const cuts = [];
  for (const r of moved) {
    let text = stubs[r.name] || '';
    let e = r.e;
    if (!text && src.slice(r.s - 2, r.s) === '\n\n' && src[e] === '\n') e += 1;
    cuts.push([r.s, e, text]);
  }
  const loader = '\n  var storiesApi = null;\n  var storiesP = null;\n' +
    '  function loadStoriesModule() {\n' +
    '    if (!storiesOn()) return Promise.resolve(null);\n' +
    '    if (storiesApi) return Promise.resolve(storiesApi);\n' +
    '    if (storiesP) return storiesP;\n' +
    '    storiesP = new Promise(function(resolve, reject) {\n' +
    '      window.__subxStoriesHost = {\n' +
    '        install: function(api) { storiesApi = api; resolve(api); },\n' +
    '        get core() { return CORE; }\n' +
    '      };\n' +
    '      var s = addon(\'factory-stories\');\n' +
    '      s.onerror = function() { storiesP = null; reject(new Error(\'Could not load factory-stories.js\')); };\n' +
    '      s.onload = function() { if (!storiesApi) { storiesP = null; reject(new Error(\'factory-stories.js did not install\')); } };\n' +
    '    });\n' +
    '    return storiesP;\n  }\n';
  if (loader.includes('innerHTML')) fail('stories loader added innerHTML');
  const signinAnchor = '    p.catch(function(e) { console.warn(\'factory-signin\', e); });\n    return p;\n  }\n';
  const sa = src.indexOf(signinAnchor);
  if (sa < 0 || src.indexOf(signinAnchor, sa + 1) >= 0) fail('stories loader anchor');
  cuts.push([sa + signinAnchor.length, sa + signinAnchor.length, loader]);
  const coreBlockStart = src.indexOf('  var CORE = {');
  const coreBlockEnd = src.indexOf('  };\n  (window.__subxPlugins', coreBlockStart);
  if (coreBlockStart < 0 || coreBlockEnd < 0) fail('CORE block not found');
  const coreBlock = src.slice(coreBlockStart, coreBlockEnd);
  const extraFns = [...coreFns].filter((n) => !coreBlock.includes(n + ': ' + n));
  const extraGets = [...coreVars.keys()].filter((n) => !coreBlock.includes('get ' + n + '()'));
  const extra = extraFns.sort().map((n) => '    ' + n + ': ' + n).concat(extraGets.sort().map((n) => '    get ' + n + '() { return ' + n + '; }'));
  const coreClose = '    set watchlistPickerOpen(v) { watchlistPickerOpen = v; }\n  };';
  const cc = src.indexOf(coreClose);
  if (cc < 0 || src.indexOf(coreClose, cc + 1) >= 0) fail('CORE close anchor');
  if (extra.length) {
    cuts.push([cc, cc + coreClose.length, '    set watchlistPickerOpen(v) { watchlistPickerOpen = v; },\n' + extra.join(',\n') + '\n  };']);
  }
  cuts.sort((a, b) => b[0] - a[0]);
  let core = src;
  for (const [s, e, tx] of cuts) core = core.slice(0, s) + tx + core.slice(e);
  if (core.includes('innerHTML') && (core.split('innerHTML').length > src.split('innerHTML').length)) fail('core gained an innerHTML');
  const bytes = Buffer.byteLength(core);
  if (bytes > 226000) fail('factory.js ' + bytes + ' B is over the 226000 B stories target');
  fs.writeFileSync('factory-stories.js', stories);
  fs.writeFileSync('factory.js', core);
  console.log('split stories: core ' + bytes + ' B; factory-stories.js ' + Buffer.byteLength(stories) + ' B; fns ' + moved.filter((r) => r.kind === 'FunctionName').length);
}
