import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { fileURLToPath } from 'url';
import { spawnSync } from 'child_process';

/*
 * Accounts gate, re-scoped 2026-10-22 (SubX: anyone can sign up). Closed ONLY when site.json says accountsOpen:false
 * or accounts:'closed'. A missing flag is open; preview:true is the banner only and never closes sign-ups.
 * Also checks every write path still carries its guard, every rooms.json room has an explicit boolean accountsOpen,
 * and tools/stamp.py refuses a room without one. Run: node test/accounts-gate.test.js
 */
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = fs.readFileSync(path.join(root, 'factory', 'factory.js'), 'utf8');
const signinSrc = fs.readFileSync(path.join(root, 'factory', 'factory-signin.js'), 'utf8');
const allSrc = src + '\n' + signinSrc;
const m = src.match(/  function accountsOpen\(\) \{[\s\S]*?\n  \}\n/);
assert.ok(m, 'accountsOpen() missing from factory/factory.js');
const open = site => new Function('site', m[0] + 'return accountsOpen();')(site);

const cases = [
  [{ siteId: 'gpchat', preview: true }, true, 'gpchat preview:true, no accounts flag is open'],
  [{ siteId: 'boyfriend', preview: true }, true, 'preview:true, no flag is open (banner only)'],
  [{ siteId: 'x', preview: true, accountsOpen: true }, true, 'preview:true + accountsOpen:true is open'],
  [{ siteId: 'x', accountsOpen: true, preview: false }, true, 'preview:false + accountsOpen:true is open'],
  [{ siteId: 'buffettchat' }, true, 'accountsOpen missing is open'],
  [null, true, 'no site.json is open'],
  [{ siteId: 'gpchat', accountsOpen: true }, true, 'gpchat shape is open'],
  [{ siteId: 'x', accountsOpen: false }, false, 'accountsOpen:false is closed'],
  [{ siteId: 'x', accountsOpen: false, preview: true }, false, 'accountsOpen:false + preview:true is closed'],
  [{ siteId: 'x', accounts: 'closed' }, false, "accounts:'closed' is closed"],
  [{ siteId: 'x', accounts: 'closed', accountsOpen: true }, false, "accounts:'closed' wins over accountsOpen:true"]
];
for (const [site, want, msg] of cases) assert.strictEqual(open(site), want, msg);
assert.ok(!/site\.preview/.test(src), 'preview must not be read by factory.js (banner only, static markup)');

// Juno: no room may open by omission. Every rooms.json room carries an explicit boolean; stamp.py refuses one without it.
const rooms = JSON.parse(fs.readFileSync(path.join(root, 'rooms.json'), 'utf8')).rooms;
for (const r of rooms) assert.strictEqual(typeof r.accountsOpen, 'boolean', 'rooms.json ' + r.room + ' needs an explicit accountsOpen');
const py = "import sys; sys.path.insert(0, 'tools'); import stamp as S\n" +
  "for v in (None, 'true', 1):\n" +
  "  e = {'room': 'newroom'}\n" +
  "  if v is not None: e['accountsOpen'] = v\n" +
  "  try: S.require_accounts_open(e); sys.exit('accepted %r' % (v,))\n" +
  "  except S.AccountsOpenMissing as x: assert 'accountsOpen' in str(x)\n" +
  "assert S.require_accounts_open({'room': 'r', 'accountsOpen': False}) is False\n";
const r = spawnSync('python3', ['-c', py], { cwd: root, encoding: 'utf8' });
assert.strictEqual(r.status, 0, 'stamp.py must refuse a room without an explicit boolean accountsOpen: ' + r.stderr + r.stdout);

const guards = [
  ["ensurePublicProfile", "if (!accountsOpen() && user.uid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["guardedPostWrite", "if (!accountsOpen() && doc.authorUid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["requireVerified", "if (!accountsOpen() && !isAdminUser() && action !== 'report' && action !== 'block') {"],
  ["register", "if (!host.accountsOpen()) { err.textContent = host.ACC_CLOSED;"],
  ["google click", "if (!host.accountsOpen() && !document.documentElement.classList.contains('acc-stew'))"],
  ["finishGoogle", "if (u && !host.accountsOpen() && u.uid !== host.ADMIN_UID) return fbAuth.signOut().then("],
  ["redirect", "if (!host.accountsOpen() && u.uid !== host.ADMIN_UID) return fbAuth.signOut();"],
  ["boot", "wireEvents();\n    applyAccountsGate();"],
  ["static note hidden when open", "if (n) n.style.display = o ? 'none' : '';"],
  ["once-guard on style id", "if (o || document.getElementById('acc-gate-css')) return;"],
  ["style id", "st.id = 'acc-gate-css';"],
  ["no duplicate note", "if (n || !p) return;"]
];
for (const [name, s] of guards) assert.strictEqual(allSrc.split(s).length - 1, 1, 'guard missing or duplicated: ' + name);
assert.ok(!/document\.getElementById\('cv-accounts-closed'\)\) return/.test(src), 'gate must not short-circuit on the static note');

// Share menu (gpchat PR #73): x.com Web Intent and neutral labels in every factory output.
for (const f of ['factory.js', 'factory-gp.js', 'factory-rail.js', 'factory-reports.js']) {
  const t = fs.readFileSync(path.join(root, 'factory', f), 'utf8');
  for (const bad of ['twitter.com/intent/tweet', 'Post on X', 'Post on Reddit']) assert.ok(!t.includes(bad), f + ' still has ' + bad);
}
for (const s of ["'https://x.com/intent/post?text='", '>Share to x.com</button>', '>Share to Reddit</button>']) assert.strictEqual(src.split(s).length - 1, 1, 'share menu missing: ' + s);

// Email already in use (Create Account path) lives in factory-signin.js.
assert.ok(signinSrc.includes("e.code === 'auth/email-already-in-use'"), 'register handles auth/email-already-in-use');
assert.ok(signinSrc.includes('fetchSignInMethodsForEmail'), 'looks up sign-in methods when the email is already in use');
assert.ok(signinSrc.includes('This email signs in with Google.'), 'Google-linked email shows plain copy');
assert.ok(signinSrc.includes('Continue with Google'), 'Google-linked email offers Continue with Google');
assert.ok(signinSrc.includes('signInWithEmailAndPassword(email, pw)'), 'otherwise, or if the lookup is unavailable, tries email sign-in with the entered password');
assert.ok(signinSrc.includes("Promise.reject(new Error('unavailable'))") || signinSrc.includes("Promise.reject(new Error(\"unavailable\"))") || signinSrc.includes("fetchSignInMethodsForEmail === 'function'"), 'lookup is optional (email enumeration protection may disable it)');
assert.ok(signinSrc.includes('Forgot password?') && signinSrc.includes('sendPasswordResetEmail'), 'Forgot password? calls sendPasswordResetEmail');
assert.ok(signinSrc.includes('If an account exists for that email, a reset message is on its way.'), 'password reset shows a neutral confirmation');
for (const code of ['auth/wrong-password', 'auth/invalid-credential', 'auth/user-not-found', 'auth/too-many-requests', 'auth/network-request-failed']) {
  assert.ok(signinSrc.includes(code), 'maps ' + code + ' to plain copy');
}
assert.ok(!signinSrc.includes('Firebase:'), 'never shows the Firebase: prefix');
assert.ok(signinSrc.includes("fbAuth.signInWithPopup(provider)"), 'Google popup-first flow is unchanged');
assert.ok(signinSrc.includes("code === 'auth/popup-blocked' || code === 'auth/operation-not-supported-in-this-environment'"), 'Google still redirects only when blocked or unsupported');

// Runtime: email-already-in-use, forgot password, and error mapping (mocked Firebase, no network).
{
  const vm = await import('vm');
  function makeEl(id, extra) {
    const o = Object.assign({
      id, attrs: {}, textContent: '', value: '', hidden: false, style: {}, parentNode: null, children: [],
      classList: {
        _s: new Set(),
        add(c) { this._s.add(c); },
        remove(c) { this._s.delete(c); },
        contains(c) { return this._s.has(c); }
      },
      getAttribute(k) { return o.attrs[k]; },
      setAttribute(k, v) { o.attrs[k] = v; },
      appendChild(n) { n.parentNode = o; o.children.push(n); return n; },
      insertBefore(n, ref) { n.parentNode = o; const i = o.children.indexOf(ref); o.children.splice(i < 0 ? o.children.length : i, 0, n); return n; },
      querySelector() { return null; },
      closest() { return o; },
      _listeners: {},
      addEventListener(ev, fn) { (o._listeners[ev] || (o._listeners[ev] = [])).push(fn); },
      click() { (o._listeners.click || []).forEach((fn) => fn({ preventDefault() {} })); }
    }, extra || {});
    return o;
  }
  const els = {};
  function put(id, extra) { els[id] = makeEl(id, extra); return els[id]; }
  const panel = put('cv-panel-login');
  const loginErr = put('cv-login-err');
  const regErr = put('cv-reg-err');
  const regEmail = put('cv-reg-email', { value: 'used@example.com' });
  const regPw = put('cv-reg-pw', { value: 'secret12' });
  const regName = put('cv-reg-name', { value: 'Ada' });
  const regAge = put('cv-reg-age', { checked: true });
  const loginEmail = put('cv-login-email', { value: '' });
  const loginPw = put('cv-login-pw', { value: '' });
  const document = {
    getElementById(id) { return els[id] || null; },
    documentElement: { classList: { contains() { return false; } } },
    createElement(tag) {
      const n = makeEl('tmp');
      Object.defineProperty(n, 'id', { get() { return n._id; }, set(v) { n._id = v; els[v] = n; } });
      n.tag = tag;
      return n;
    },
    head: { appendChild(n) { return n; } }
  };
  function runWith(hostExtras) {
    let installed = null;
    const calls = { methods: 0, signIn: 0, reset: 0, create: 0, popup: 0, redirect: 0 };
    const fbAuth = Object.assign({
      fetchSignInMethodsForEmail() { calls.methods++; return Promise.resolve(['password']); },
      signInWithEmailAndPassword() { calls.signIn++; return Promise.resolve({ user: { uid: 'u1' } }); },
      createUserWithEmailAndPassword() { calls.create++; return Promise.reject({ code: 'auth/email-already-in-use' }); },
      sendPasswordResetEmail() { calls.reset++; return Promise.resolve(); },
      signInWithPopup() { calls.popup++; return Promise.resolve({ user: { uid: 'u1' } }); },
      signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
    }, (hostExtras && hostExtras.fbAuth) || {});
    const host = Object.assign({
      install(api) { installed = api; },
      fbAuth,
      fbDb: null,
      ADMIN_UID: 'admin',
      ACC_CLOSED: 'Accounts are not open yet. You can read the room as a guest.',
      accountsOpen() { return true; },
      ageGateMessage() { return 'Confirm you are 18 or older.'; },
      markAuthLand() {},
      ensurePublicProfile() { return Promise.resolve(); },
      runWithAuth(err, fn) { fn(); },
      authPersistPromise: Promise.resolve(),
      nameOk() { return true; },
      composeErr() {},
      setAuthOpenWhenReady() {}
    }, hostExtras || {});
    host.fbAuth = fbAuth;
    const ctx = {
      window: { __subxSigninHost: host },
      document,
      sessionStorage: { setItem() {}, getItem() { return null; }, removeItem() {} },
      localStorage: { setItem() {}, getItem() { return null; }, removeItem() {} },
      firebase: { auth: { GoogleAuthProvider: function () {} }, firestore: { FieldValue: { serverTimestamp() { return 'ts'; } } } },
      console, Promise, Error, Array, Set
    };
    vm.runInNewContext(signinSrc, ctx, { filename: 'factory-signin.js' });
    return { api: installed, calls, fbAuth, host };
  }

  // password account already exists: switch to sign-in and retry with the same password
  {
    const { api, calls } = runWith({});
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.create, 1, 'createUser is attempted');
    assert.strictEqual(calls.methods, 1, 'fetchSignInMethodsForEmail is used when available');
    assert.strictEqual(calls.signIn, 1, 'falls back to signInWithEmailAndPassword');
    assert.strictEqual(loginEmail.value, 'used@example.com', 'switches the form to sign-in with the same email');
    assert.strictEqual(loginPw.value, 'secret12', 'reuses the entered password');
  }

  // Google-linked email: plain copy + Continue with Google, no auto email sign-in
  {
    loginErr.textContent = '';
    const { api, calls } = runWith({
      fbAuth: {
        fetchSignInMethodsForEmail() { calls.methods++; return Promise.resolve(['google.com']); },
        signInWithEmailAndPassword() { calls.signIn++; return Promise.resolve({}); },
        createUserWithEmailAndPassword() { calls.create++; return Promise.reject({ code: 'auth/email-already-in-use' }); },
        sendPasswordResetEmail() { calls.reset++; return Promise.resolve(); },
        signInWithPopup() { calls.popup++; return Promise.resolve({ user: { uid: 'u1' } }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.ok(loginErr.textContent === 'This email signs in with Google.' || (els['cv-login-err'] && els['cv-login-err'].textContent === 'This email signs in with Google.'), 'Google-linked copy');
    assert.ok(els['cv-continue-google'] && els['cv-continue-google'].textContent === 'Continue with Google', 'Continue with Google button is shown');
    assert.strictEqual(calls.signIn, 0, 'does not auto-sign-in with password when the method is Google');
  }

  // lookup unavailable: still tries email sign-in
  {
    const { api, calls } = runWith({
      fbAuth: {
        createUserWithEmailAndPassword() { calls.create++; return Promise.reject({ code: 'auth/email-already-in-use' }); },
        signInWithEmailAndPassword() { calls.signIn++; return Promise.resolve({}); },
        sendPasswordResetEmail() { calls.reset++; return Promise.resolve(); },
        signInWithPopup() { calls.popup++; return Promise.resolve({ user: {} }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
        // no fetchSignInMethodsForEmail
      }
    });
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.signIn, 1, 'when the lookup is unavailable, signs in with the entered password');
  }

  // wrong-password maps to plain copy, never Firebase:
  {
    loginErr.textContent = '';
    const { api } = runWith({
      fbAuth: {
        signInWithEmailAndPassword() { return Promise.reject({ code: 'auth/wrong-password', message: 'Firebase: Error (auth/wrong-password).' }); },
        createUserWithEmailAndPassword() { return Promise.resolve({ user: {} }); },
        sendPasswordResetEmail() { return Promise.resolve(); },
        signInWithPopup() { return Promise.resolve({ user: {} }); },
        signInWithRedirect() { return Promise.resolve(); }
      }
    });
    put('cv-login-email', Object.assign(els['cv-login-email'] || makeEl('cv-login-email'), { value: 'a@b.com' }));
    // ensure ids
    els['cv-login-email'].value = 'a@b.com';
    els['cv-login-pw'].value = 'bad';
    api.onEmailLogin();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.ok(!loginErr.textContent.includes('Firebase:'), 'wrong-password copy has no Firebase: prefix');
    assert.ok(/password is not right/i.test(loginErr.textContent), 'wrong-password uses plain copy: ' + loginErr.textContent);
  }

  // Forgot password: sendPasswordResetEmail + neutral confirmation
  {
    loginErr.textContent = '';
    els['cv-login-email'].value = 'a@b.com';
    const { api, calls } = runWith({});
    api.ensureJoinAuthLayout();
    const forgot = els['cv-forgot-pw'];
    assert.ok(forgot, 'Forgot password? control is created');
    assert.strictEqual(forgot.textContent, 'Forgot password?');
    forgot.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.reset, 1, 'Forgot password? calls sendPasswordResetEmail');
    assert.strictEqual(loginErr.textContent, 'If an account exists for that email, a reset message is on its way.', 'neutral reset confirmation');
  }
}

console.log('accounts-gate: ok (' + guards.length + ' guards, ' + cases.length + ' cases, ' + rooms.length + ' rooms explicit, stamp refuses missing, share menu, email-in-use)');
