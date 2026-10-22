// node test/autohide.test.js — auto-hide on report + DOM reason chooser + atomic 3-write batch + greyed-out report rows + admin-only restore.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert';

const rd = (f) => fs.readFileSync(new URL('../factory/' + f, import.meta.url), 'utf8');
const core = rd('factory.js');
const gp = rd('factory-gp.js');
const reportsPlug = rd('factory-reports.js');

function fnSrc(src, name) {
  const i = src.indexOf('  function ' + name + '(');
  assert.ok(i >= 0, name + ' missing');
  return src.slice(i, src.indexOf('\n  }\n', i) + 4);
}

const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';

// 1. Verify HIDE_REASONS includes all 6 categories (including the 4 requested: ncii, copyright, violent_offensive, hate)
assert.ok(
  core.includes("var HIDE_REASONS = { ncii: 1, copyright: 1, violent_offensive: 1, hate: 1, impersonation: 1, csam: 1 };"),
  'HIDE_REASONS must include ncii, copyright, violent_offensive, hate, impersonation, csam'
);

// 2. Verify pickReportReason(done) renders accessible DOM modal (no window.prompt) with 5 reason buttons + Cancel + report.html link
{
  let modalEl = null;
  const fakeDoc = {
    createElement: (tag) => {
      const el = {
        tag,
        id: '',
        className: '',
        type: '',
        href: '',
        target: '',
        rel: '',
        textContent: '',
        innerHTML: '',
        style: {},
        attrs: {},
        children: [],
        parentNode: null,
        _click: null,
        setAttribute(k, v) { this.attrs[k] = v; },
        getAttribute(k) { return this.attrs[k]; },
        appendChild(ch) { ch.parentNode = this; this.children.push(ch); return ch; },
        removeChild(ch) { this.children = this.children.filter((x) => x !== ch); if (ch === modalEl) modalEl = null; },
        addEventListener(ev, fn) { if (ev === 'click') this._click = fn; },
        focus() {},
        findBtn(pred) {
          for (const ch of this.children) {
            if (pred(ch)) return ch;
            const f = ch.findBtn && ch.findBtn(pred);
            if (f) return f;
          }
          return null;
        }
      };
      return el;
    },
    addEventListener() {},
    removeEventListener() {},
    body: {
      appendChild(el) { el.parentNode = this; modalEl = el; return el; },
      removeChild(el) { if (el === modalEl) modalEl = null; }
    }
  };
  const ctx = { document: fakeDoc };
  vm.createContext(ctx);
  vm.runInContext(fnSrc(core, 'pickReportReason'), ctx);

  for (const reason of ['ncii', 'copyright', 'violent_offensive', 'hate', 'other']) {
    let chosen = 'unset';
    ctx.pickReportReason((r) => { chosen = r; });
    assert.ok(modalEl, 'modal mounted for ' + reason);
    assert.strictEqual(modalEl.attrs.role, 'dialog');
    const btn = modalEl.findBtn((el) => el.attrs && el.attrs['data-reason'] === reason);
    assert.ok(btn, 'button present for ' + reason);
    const link = modalEl.findBtn((el) => el.href === 'report.html');
    assert.ok(link, 'formal report.html link present');
    btn._click();
    assert.strictEqual(chosen, reason, 'callback received ' + reason);
    assert.strictEqual(modalEl, null, 'modal removed after selection');
  }

  // Cancel button returns null and closes modal without reporting
  let cancelledVal = 'unset';
  ctx.pickReportReason((r) => { cancelledVal = r; });
  assert.ok(modalEl, 'modal mounted before cancel');
  const cancelBtn = modalEl.findBtn((el) => el.textContent === 'Cancel');
  assert.ok(cancelBtn, 'Cancel button present');
  cancelBtn._click();
  assert.strictEqual(cancelledVal, null, 'Cancel passes null');
  assert.strictEqual(modalEl, null, 'modal removed on cancel');
}

// 3. Verify reportPost + commitAutoHideReport writes reports + hides + rateLimits in a 3-write batch for hide-eligible reasons
{
  const batches = [];
  const standaloneReports = [];
  const toasts = [];
  const alerts = [];
  let batchShouldRejectWith = null;
  let currentUid = 'uReporter';
  let modalPick = 'ncii';

  const makeFakeDb = () => ({
    collection: (c) => ({
      doc: (id) => ({
        id: id || 'genReportId',
        _path: c + '/' + (id || 'genReportId')
      }),
      add: (payload) => {
        standaloneReports.push([c, payload]);
        return Promise.resolve({ id: 'fallbackId' });
      }
    }),
    batch: () => {
      const ops = [];
      return {
        set: (ref, payload, opts) => { ops.push([ref._path, payload, opts || null]); },
        commit: () => {
          batches.push(ops);
          if (batchShouldRejectWith) return Promise.reject(batchShouldRejectWith);
          return Promise.resolve();
        }
      };
    }
  });

  const ctx = {
    ADMIN_UID: ADMIN,
    HIDE_REASONS: { ncii: 1, copyright: 1, violent_offensive: 1, hate: 1, impersonation: 1, csam: 1 },
    SITE_ID: 'gpchat',
    fbDb: makeFakeDb(),
    hiddenIds: {},
    firebase: { firestore: { FieldValue: { serverTimestamp: () => 'TS' } } },
    requireVerified: () => true,
    liveUid: () => currentUid,
    pickReportReason: (done) => done(modalPick),
    findPost: (id) => (id === 'p100' ? { id: 'p100', authorUid: 'uAuthor', text: 'secret text' } : null),
    isSessionSeedPost: () => false,
    alreadyReported: () => false,
    markReported: () => {},
    writeReportAlert: (post, me, reason) => alerts.push({ postId: post.id, me, reason }),
    reportErr: (e) => String(e),
    isPermDenied: (e) => Boolean(e && e.code === 'permission-denied'),
    toast: (m) => toasts.push(m),
    renderFeed: () => { ctx._rendered = (ctx._rendered || 0) + 1; },
    renderStoriesTray: () => {}
  };
  vm.createContext(ctx);
  vm.runInContext(
    fnSrc(core, 'isAdminUser') +
    fnSrc(core, 'isPostHidden') +
    fnSrc(core, 'isStoryHidden') +
    fnSrc(core, 'commitAutoHideReport') +
    fnSrc(core, 'reportPost'),
    ctx
  );

  // 3a. Hide-eligible reasons ('ncii', 'copyright', 'violent_offensive', 'hate', 'impersonation', 'csam') write reports/{id}, hides/gpchat_p100 (createdAt: ts, no reason, no hiddenAt), and rateLimits/{me}
  for (const hr of ['ncii', 'copyright', 'violent_offensive', 'hate', 'impersonation', 'csam']) {
    ctx.hiddenIds = {};
    batches.length = 0;
    standaloneReports.length = 0;
    toasts.length = 0;
    ctx.reportPost('p100', hr);
    await new Promise((r) => setImmediate(r));
    assert.strictEqual(ctx.hiddenIds.p100, true, 'immediately hidden locally for ' + hr);
    assert.strictEqual(batches.length, 1, 'batch committed for ' + hr);
    assert.strictEqual(batches[0].length, 3, 'batch has 3 writes (report + hide + rateLimits) for ' + hr);
    assert.strictEqual(batches[0][0][0], 'reports/genReportId');
    assert.strictEqual(batches[0][0][1].reason, hr);
    assert.strictEqual(batches[0][1][0], 'hides/gpchat_p100');
    assert.deepStrictEqual(
      JSON.parse(JSON.stringify(batches[0][1][1])),
      { siteId: 'gpchat', postId: 'p100', reportId: 'genReportId', reporterUid: 'uReporter', createdAt: 'TS' },
      'exact /hides payload with createdAt: ts and no reason/hiddenAt for ' + hr
    );
    assert.strictEqual(batches[0][2][0], 'rateLimits/uReporter');
    assert.deepStrictEqual(JSON.parse(JSON.stringify(batches[0][2][1])), { lastHideAt: 'TS' });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(batches[0][2][2])), { merge: true });
    assert.ok(toasts[0].includes('hidden pending review'), 'toast confirms hidden for ' + hr);
  }

  // 3b. Non-hide reasons ('other', 'abuse') write only reports collection and do NOT auto-hide for non-admin
  for (const nr of ['other', 'abuse']) {
    ctx.hiddenIds = {};
    batches.length = 0;
    standaloneReports.length = 0;
    toasts.length = 0;
    ctx.reportPost('p100', nr);
    await new Promise((r) => setImmediate(r));
    assert.strictEqual(Boolean(ctx.hiddenIds.p100), false, nr + ' does not auto-hide');
    assert.strictEqual(batches.length, 0, 'no batch hide write for ' + nr);
    assert.strictEqual(standaloneReports.length, 1, 'standalone report added for ' + nr);
    assert.strictEqual(standaloneReports[0][1].reason, nr);
    assert.strictEqual(toasts[0], 'Reported. Thanks.');
  }

  // 3c. Fallback when hides rules are not yet live (batch rejects with permission-denied -> falls back to standalone report add)
  ctx.hiddenIds = {};
  batches.length = 0;
  standaloneReports.length = 0;
  batchShouldRejectWith = { code: 'permission-denied' };
  ctx.reportPost('p100', 'hate');
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  assert.strictEqual(standaloneReports.length, 1, 'fallback wrote standalone report');
  assert.strictEqual(standaloneReports[0][0], 'reports');
  assert.strictEqual(standaloneReports[0][1].reason, 'hate');
}

// 4. Verify feed, replies, following, stories, profile, and notifications filter out hidden posts/stories/authors
{
  const ctx = {
    SITE_ID: 'gpchat',
    hiddenIds: { pHidden: true, sHidden: true, 'uid:uBanned': true },
    blockedUids: {},
    livePosts: [
      { id: 'pVisible', text: 'hello world', authorUid: 'u1', ms: 10 },
      { id: 'pHidden', text: 'bad image', authorUid: 'uBad', ms: 20 },
      { id: 'pByBanned', text: 'from hidden uid', authorUid: 'uBanned', ms: 30 },
      { id: 'rVis', parentId: 'pVisible', text: 'visible reply', authorUid: 'u2', ms: 15 },
      { id: 'rOnHidden', parentId: 'pHidden', text: 'reply on hidden parent', authorUid: 'u2', ms: 25 }
    ],
    currentNest: null,
    nestPosts: [],
    sessionSeedPosts: () => [],
    postsForFeed: () => ctx.livePosts,
    notifItems: [
      { id: 'n1', siteId: 'gpchat', type: 'like', postId: 'pHidden', text: 'liked bad post' },
      { id: 'n2', siteId: 'gpchat', type: 'report', postId: 'pHidden', text: 'Report: [ncii · auto-hidden]' },
      { id: 'n3', siteId: 'gpchat', type: 'like', postId: 'pVisible', text: 'liked good post' }
    ]
  };
  vm.createContext(ctx);
  vm.runInContext(
    fnSrc(core, 'isPostHidden') +
    fnSrc(core, 'isStoryHidden') +
    fnSrc(core, 'topLevelPosts') +
    fnSrc(core, 'repliesFor') +
    fnSrc(core, 'findPost') +
    fnSrc(core, 'siteNotifs'),
    ctx
  );

  assert.deepStrictEqual(ctx.topLevelPosts().map((p) => p.id), ['pVisible'], 'topLevelPosts filters hidden post and hidden uid');
  assert.deepStrictEqual(ctx.repliesFor('pVisible').map((r) => r.id), ['rVis'], 'repliesFor keeps visible reply');
  assert.strictEqual(ctx.repliesFor('pHidden').length, 0, 'repliesFor returns empty on hidden parent');
  assert.strictEqual(ctx.findPost('pHidden'), null, 'findPost returns null for hidden post');
  assert.strictEqual(ctx.findPost('pByBanned'), null, 'findPost returns null for hidden author uid');
  assert.strictEqual(ctx.findPost('pVisible').id, 'pVisible', 'findPost returns visible post');
  assert.deepStrictEqual(ctx.siteNotifs().map((n) => n.id), ['n2', 'n3'], 'siteNotifs hides social notifs on hidden post but keeps admin report alerts');
  assert.strictEqual(ctx.isStoryHidden({ id: 'sHidden', authorUid: 'u1' }), true, 'isStoryHidden detects hidden story');
  assert.strictEqual(ctx.isStoryHidden({ id: 'sOk', authorUid: 'uBanned' }), true, 'isStoryHidden detects hidden story author');
  assert.strictEqual(ctx.isStoryHidden({ id: 'sOk', authorUid: 'u1' }), false, 'isStoryHidden allows visible story');
}

// 5. Verify greyed-out report rows (no text snippet shown) and admin-only Restore + adminMassHide in factory-reports.js
{
  let listHtml = '';
  const ctx = {
    ADMIN_UID: ADMIN,
    SITE_ID: 'gpchat',
    HIDE_REASONS: { ncii: 1, copyright: 1, violent_offensive: 1, hate: 1, impersonation: 1, csam: 1 },
    hiddenIds: { p1: true },
    reportItems: [
      { id: 'rep1', postId: 'p1', reason: 'ncii', status: 'open' },
      { id: 'rep2', postId: 'p2', reason: 'abuse', status: 'open' }
    ],
    PLUGIN: {},
    findPost: (id) => ({ id, text: 'SENSITIVE TEXT THAT MUST NEVER RENDER FOR HIDDEN POSTS (' + id + ')' }),
    document: {
      getElementById: (id) => (id === 'reports-list' ? { set innerHTML(v) { listHtml = v; }, get innerHTML() { return listHtml; } } : null)
    }
  };
  vm.createContext(ctx);
  vm.runInContext(
    fnSrc(core, 'escapeHtml') +
    fnSrc(core, 'reporterCount') +
    fnSrc(core, 'reportTriage') +
    fnSrc(core, 'renderReports'),
    ctx
  );

  ctx.renderReports();
  assert.ok(listHtml.includes('[Hidden — ncii · p1]'), 'hidden report renders placeholder instead of post text');
  assert.ok(!listHtml.includes('SENSITIVE TEXT THAT MUST NEVER RENDER FOR HIDDEN POSTS (p1)'), 'hidden post text is never rendered in report row');
  assert.ok(listHtml.includes('style="opacity:0.65"'), 'hidden report row is greyed out');
  assert.ok(listHtml.includes('SENSITIVE TEXT THAT MUST NEVER RENDER FOR HIDDEN POSTS (p2)'), 'non-hidden abuse report still shows snippet');

  // Verify factory-reports.js plugin includes Restore button, enforces admin-only restore, and uses createdAt in adminMassHide
  assert.ok(reportsPlug.includes('createdAt: ts'), 'factory-reports.js adminMassHide uses createdAt: ts');
  assert.ok(!reportsPlug.includes('hiddenAt'), 'factory-reports.js does not use hiddenAt');

  let clickHandler = null;
  const deletedDocs = [];
  const updatedReports = [];
  let me = ADMIN;
  const plugCtx = {
    window: { confirm: () => true },
    document: { addEventListener: (t, fn) => { if (t === 'click') clickHandler = fn; }, querySelector: () => null, getElementById: () => null },
    Date,
    firebase: { firestore: { FieldValue: { serverTimestamp: () => 'TS', arrayUnion: (x) => x } } }
  };
  vm.createContext(plugCtx);
  vm.runInContext(reportsPlug, plugCtx);
  const plugApi = plugCtx.window.__subxPlugins[0]({
    escapeHtml: ctx.escapeHtml,
    liveUid: () => me,
    isLiveUser: () => true,
    ADMIN_UID: ADMIN,
    SITE_ID: 'gpchat',
    hiddenIds: ctx.hiddenIds,
    HIDE_REASONS: ctx.HIDE_REASONS,
    renderFeed: () => {},
    renderReports: () => {},
    toast: () => {},
    fbDb: {
      collection: (c) => ({
        doc: (id) => ({
          delete: () => { deletedDocs.push(c + '/' + id); return Promise.resolve(); },
          update: (p) => { updatedReports.push([c + '/' + id, p]); return Promise.resolve(); }
        })
      })
    }
  });

  // Wire listener via syncMyReports
  plugApi.syncMyReports();
  assert.ok(clickHandler, 'factory-reports click handler wired');

  // Check Restore button rendered for hidden or hide-eligible report
  const triageHtml = plugApi.reportTriage({ id: 'rep1', postId: 'p1', reason: 'ncii', reporterUid: 'u1', status: 'open' });
  assert.ok(triageHtml.includes('data-report-restore="p1"'), 'Restore button rendered for hidden report');

  // Non-admin cannot restore
  me = 'uNotAdmin';
  clickHandler({
    target: { closest: (sel) => (sel === '[data-report-restore]' ? { getAttribute: (k) => (k === 'data-report-restore' ? 'p1' : 'rep1') } : null) },
    preventDefault() {}
  });
  await new Promise((r) => setImmediate(r));
  assert.strictEqual(deletedDocs.length, 0, 'non-admin cannot delete /hides doc');

  // Admin can restore
  me = ADMIN;
  clickHandler({
    target: { closest: (sel) => (sel === '[data-report-restore]' ? { getAttribute: (k) => (k === 'data-report-restore' ? 'p1' : 'rep1') } : null) },
    preventDefault() {}
  });
  await new Promise((r) => setImmediate(r));
  assert.deepStrictEqual(deletedDocs, ['hides/gpchat_p1'], 'admin deletes /hides/gpchat_p1');
  assert.strictEqual(updatedReports[0][0], 'reports/rep1');
  assert.strictEqual(updatedReports[0][1].resolution, 'Restored by admin');
}

console.log('autohide: DOM reason chooser (4 auto-hide + other + cancel), 3-write atomic batch (reports + hides + rateLimits) + fallback, multi-surface filtering, greyed-out report rows, admin-only restore ok');
