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
const CRED_MSG = 'That email or password is not right. Try again, reset your password, or use Continue with Google.';
assert.ok(signinSrc.includes(CRED_MSG), 'user-not-found, wrong-password, and invalid-credential share one neutral message');
assert.ok(!signinSrc.includes('That password is not right. Try again or reset it.'), 'old distinct wrong-password copy is gone');
assert.ok(!signinSrc.includes('No account matches that email'), 'old distinct user-not-found copy is gone');
assert.ok(signinSrc.includes('Google sign-in is not available right now. Use email.'), 'Google disabled copy has no project id');
assert.ok(!signinSrc.includes('subx-skins') && !signinSrc.includes('Google is not enabled'), 'factory-signin.js never names the Firebase project');
assert.ok(signinSrc.includes("typeof host.isLiveUser === 'function' && host.isLiveUser()"), 'onRegister has its own isLiveUser guard');
assert.ok(signinSrc.includes("typeof host.closeAuth === 'function') host.closeAuth()"), 'onRegister closes the sheet when the user is live');
assert.ok(src.includes('isLiveUser: isLiveUser') && src.includes('closeAuth: closeAuth'), 'sign-in host exposes isLiveUser and closeAuth');
assert.ok(signinSrc.includes("fbAuth.signInWithPopup(provider)"), 'Google popup-first flow is unchanged');
assert.ok(signinSrc.includes("fbAuth.signInWithRedirect(provider)"), 'blocked popup falls back to signInWithRedirect');
assert.ok(signinSrc.includes('Google popup sign-in could not open. Trying another sign-in method.'), 'redirect fallback explains itself');
assert.ok(signinSrc.includes("Your browser blocked the Google popup."), 'failed redirect still has the blocked message');
assert.ok(signinSrc.includes("Try Google again") && signinSrc.includes("Use email instead"), 'failed redirect offers Try Google again and Use email instead');
assert.ok(signinSrc.includes('setJoinActionsHidden') && signinSrc.includes('is-google-blocked'), 'blocked notice hides the normal button block');
assert.ok(signinSrc.includes('auth/popup-closed-by-user') && signinSrc.includes('POPUP_BLOCK_MS'), 'detects a quick close and a silent blocked popup');
assert.ok(!signinSrc.includes('—') && !signinSrc.includes('–'), 'no em or en dashes in factory-signin.js');

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
  const googleAge = put('cv-google-age', { checked: true });
  put('cv-google-login');
  const docListeners = {};
  const document = {
    getElementById(id) { return els[id] || null; },
    documentElement: { classList: { contains() { return false; } } },
    hidden: false,
    visibilityState: 'visible',
    createElement(tag) {
      const n = makeEl('tmp');
      Object.defineProperty(n, 'id', { get() { return n._id; }, set(v) { n._id = v; els[v] = n; } });
      n.tag = tag;
      return n;
    },
    head: { appendChild(n) { return n; } },
    addEventListener(ev, fn) { (docListeners[ev] || (docListeners[ev] = [])).push(fn); },
    removeEventListener(ev, fn) { docListeners[ev] = (docListeners[ev] || []).filter((f) => f !== fn); }
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
    const mem = function () {
      const d = Object.create(null);
      return {
        setItem(k, v) { d[k] = String(v); },
        getItem(k) { return Object.prototype.hasOwnProperty.call(d, k) ? d[k] : null; },
        removeItem(k) { delete d[k]; }
      };
    };
    const sessionStorage = mem();
    const localStorage = mem();
    const winListeners = {};
    const windowObj = {
      __subxSigninHost: host,
      addEventListener(ev, fn) { (winListeners[ev] || (winListeners[ev] = [])).push(fn); },
      removeEventListener(ev, fn) { winListeners[ev] = (winListeners[ev] || []).filter((f) => f !== fn); }
    };
    let authOpen = 0;
    const origReady = host.setAuthOpenWhenReady;
    host.setAuthOpenWhenReady = function (v) { authOpen++; if (typeof origReady === 'function') origReady(v); };
    const ctx = {
      window: windowObj,
      document,
      sessionStorage,
      localStorage,
      firebase: { auth: { GoogleAuthProvider: function () {} }, firestore: { FieldValue: { serverTimestamp() { return 'ts'; } } } },
      console, Promise, Error, Array, Set, Date, setTimeout, clearTimeout
    };
    vm.runInNewContext(signinSrc, ctx, { filename: 'factory-signin.js' });
    return { api: installed, calls, fbAuth, host, sessionStorage, localStorage, authOpen: () => authOpen, windowObj };
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

  // password-already-in-use also offers Continue with Google (fix 2)
  {
    loginErr.textContent = '';
    delete els['cv-continue-google'];
    const { api, calls } = runWith({});
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.signIn, 1, 'password account still retries sign-in');
    assert.ok(els['cv-continue-google'] && els['cv-continue-google'].textContent === 'Continue with Google' && els['cv-continue-google'].hidden === false, 'Continue with Google is shown for email-already-in-use even when methods is password');
  }

  // enumeration protection: methods is [], Google-only account would have taken the password path
  {
    loginErr.textContent = '';
    delete els['cv-continue-google'];
    const { api, calls } = runWith({
      fbAuth: {
        fetchSignInMethodsForEmail() { calls.methods++; return Promise.resolve([]); },
        signInWithEmailAndPassword() { calls.signIn++; return Promise.reject({ code: 'auth/invalid-credential', message: 'Firebase: Error (auth/invalid-credential).' }); },
        createUserWithEmailAndPassword() { calls.create++; return Promise.reject({ code: 'auth/email-already-in-use' }); },
        sendPasswordResetEmail() { calls.reset++; return Promise.resolve(); },
        signInWithPopup() { calls.popup++; return Promise.resolve({ user: { uid: 'u1' } }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.methods, 1, 'lookup ran');
    assert.strictEqual(calls.signIn, 1, 'empty methods still tries the password (enumeration protection returns [])');
    assert.strictEqual(loginErr.textContent, CRED_MSG, 'empty methods + invalid-credential uses the unified message: ' + loginErr.textContent);
    assert.ok(!loginErr.textContent.includes('Firebase:'), 'no Firebase: prefix on enumeration-protection path');
    assert.ok(els['cv-continue-google'] && els['cv-continue-google'].textContent === 'Continue with Google' && els['cv-continue-google'].hidden === false, 'Continue with Google is shown when methods is empty');
  }

  // user-not-found, wrong-password, invalid-credential, and invalid-login-credentials share one message and offer Google
  for (const code of ['auth/wrong-password', 'auth/invalid-credential', 'auth/invalid-login-credentials', 'auth/user-not-found']) {
    loginErr.textContent = '';
    delete els['cv-continue-google'];
    const { api } = runWith({
      fbAuth: {
        signInWithEmailAndPassword() { return Promise.reject({ code, message: 'Firebase: Error (' + code + ').' }); },
        createUserWithEmailAndPassword() { return Promise.resolve({ user: {} }); },
        sendPasswordResetEmail() { return Promise.resolve(); },
        signInWithPopup() { return Promise.resolve({ user: {} }); },
        signInWithRedirect() { return Promise.resolve(); }
      }
    });
    els['cv-login-email'].value = 'a@b.com';
    els['cv-login-pw'].value = 'bad';
    api.onEmailLogin();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(loginErr.textContent, CRED_MSG, code + ' uses the unified message: ' + loginErr.textContent);
    assert.ok(!loginErr.textContent.includes('Firebase:'), code + ' has no Firebase: prefix');
    assert.ok(els['cv-continue-google'] && els['cv-continue-google'].textContent === 'Continue with Google' && els['cv-continue-google'].hidden === false, code + ' shows Continue with Google');
  }

  // onRegister: signed-in user closes the sheet and does not call createUser
  {
    let closed = 0;
    const { api, calls } = runWith({
      isLiveUser() { return true; },
      closeAuth() { closed++; }
    });
    await api.onRegister();
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.create, 0, 'onRegister does not call createUser when the user is live');
    assert.strictEqual(closed, 1, 'onRegister closes the sheet when the user is live');
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

  function redirectingUi() {
    const msg = loginErr.textContent || (els['cv-login-err'] && els['cv-login-err'].textContent) || '';
    assert.ok(msg === 'Google popup sign-in could not open. Trying another sign-in method.', 'redirect message: ' + msg);
    assert.ok(els['cv-google-login'] && els['cv-google-login'].hidden === true, 'normal Google button is hidden while redirecting');
    assert.ok(!els['cv-google-blocked'] || els['cv-google-blocked'].hidden, 'no second button sheet while redirect starts');
    assert.ok(els['cv-google-age'] && els['cv-google-age'].hidden !== true, '18+ checkbox stays visible');
    assert.ok(panel.classList.contains('is-google-blocked'), 'panel is marked is-google-blocked');
  }

  function blockedUi() {
    const box = els['cv-google-blocked'];
    const retry = els['cv-google-retry'];
    const useEmail = els['cv-google-use-email'];
    assert.ok(loginErr.textContent === 'Your browser blocked the Google popup.' || (els['cv-login-err'] && els['cv-login-err'].textContent === 'Your browser blocked the Google popup.'), 'blocked message: ' + loginErr.textContent);
    assert.ok(box && box.hidden === false, 'blocked sheet is visible');
    assert.ok(retry && retry.textContent === 'Try Google again', 'Try Google again button');
    assert.ok(useEmail && useEmail.textContent === 'Use email instead', 'Use email instead button');
    assert.ok(els['cv-google-login'] && els['cv-google-login'].hidden === true, 'normal Google button is hidden when the notice shows');
    assert.ok(els['cv-google-age'] && els['cv-google-age'].hidden !== true, '18+ checkbox stays visible next to the notice');
  }

  // 18+ gate still blocks Google (popup and redirect) when unchecked.
  {
    const prev = googleAge.checked;
    googleAge.checked = false;
    loginErr.textContent = '';
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() { calls.popup++; return Promise.resolve({ user: { uid: 'u1' } }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    api.onGoogleClick();
    assert.strictEqual(calls.popup, 0, 'unchecked 18+ does not open a popup');
    assert.strictEqual(calls.redirect, 0, 'unchecked 18+ does not redirect');
    assert.ok((loginErr.textContent || '').length > 0, 'unchecked 18+ shows the age-gate message');
    googleAge.checked = prev;
  }

  // auth/popup-blocked falls back to signInWithRedirect and hides the normal buttons.
  {
    loginErr.textContent = '';
    delete els['cv-google-blocked'];
    delete els['cv-google-retry'];
    delete els['cv-google-use-email'];
    els['cv-google-login'].hidden = false;
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() { calls.popup++; return Promise.reject({ code: 'auth/popup-blocked' }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    api.onGoogleClick();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.popup, 1, 'popup is tried first');
    assert.strictEqual(calls.redirect, 1, 'blocked popup falls back to redirect');
    redirectingUi();
  }

  // A popup that never resolves and has no focus loss falls back to redirect after the timeout (iOS Chrome).
  {
    loginErr.textContent = '';
    delete els['cv-google-blocked'];
    delete els['cv-google-retry'];
    delete els['cv-google-use-email'];
    els['cv-google-login'].hidden = false;
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() { calls.popup++; return new Promise(function () {}); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); },
        getRedirectResult() { return Promise.resolve(null); }
      }
    });
    api.onGoogleClick();
    assert.strictEqual(calls.popup, 1, 'never-resolving popup is opened once');
    assert.strictEqual(calls.redirect, 0, 'does not redirect while waiting');
    await new Promise((r) => setTimeout(r, 500));
    assert.strictEqual(calls.redirect, 0, 'does not treat a 0.5s wait as blocked');
    await new Promise((r) => setTimeout(r, 1700));
    assert.strictEqual(calls.redirect, 1, 'silent blocked popup falls back to redirect after the timeout');
    redirectingUi();
  }

  // popup-closed-by-user arriving quickly is treated as blocked and redirects, not as a cancel.
  {
    loginErr.textContent = '';
    delete els['cv-google-blocked'];
    delete els['cv-google-retry'];
    delete els['cv-google-use-email'];
    els['cv-google-login'].hidden = false;
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() { calls.popup++; return Promise.reject({ code: 'auth/popup-closed-by-user' }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    api.onGoogleClick();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.redirect, 1, 'quick close falls back to redirect');
    assert.ok(loginErr.textContent !== 'Google sign-in cancelled.', 'quick close is not a cancel message');
    redirectingUi();
  }

  // An empty redirect result where a redirect was pending shows the blocked sheet (replacing the buttons) and settles. It does not redirect again.
  {
    loginErr.textContent = '';
    delete els['cv-google-blocked'];
    delete els['cv-google-retry'];
    delete els['cv-google-use-email'];
    els['cv-google-login'].hidden = false;
    let settled = false;
    const { api, calls, sessionStorage, authOpen } = runWith({
      fbAuth: {
        getRedirectResult() { return Promise.resolve({ user: null }); },
        signInWithPopup() { calls.popup++; return Promise.resolve({ user: {} }); },
        signInWithRedirect() { calls.redirect++; return Promise.resolve(); }
      }
    });
    sessionStorage.setItem('subx.googleRedirect', '1');
    const p = api.handleRedirectResult();
    assert.ok(p && typeof p.then === 'function', 'handleRedirectResult returns a promise');
    await p.then(function () { settled = true; });
    assert.ok(settled, 'empty redirect result settles (Join is not deadlocked)');
    blockedUi();
    assert.ok(authOpen() >= 1, 'empty redirect asks the sheet to open');
    assert.strictEqual(calls.redirect, 0, 'empty redirect never auto-redirects again');
    assert.strictEqual(sessionStorage.getItem('subx.googleRedirect'), null, 'pending redirect flag is cleared');
  }

  // When redirect itself fails, the blocked sheet replaces the normal buttons. "Try Google again" calls signInWithPopup synchronously, then falls back to redirect.
  {
    loginErr.textContent = '';
    delete els['cv-google-blocked'];
    delete els['cv-google-retry'];
    delete els['cv-google-use-email'];
    els['cv-google-login'].hidden = false;
    let syncPopup = false;
    let syncRedirect = false;
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() {
          calls.popup++;
          syncPopup = true;
          return Promise.reject({ code: 'auth/popup-blocked' });
        },
        signInWithRedirect() {
          calls.redirect++;
          syncRedirect = true;
          return Promise.reject({ code: 'auth/operation-not-supported-in-this-environment' });
        }
      }
    });
    api.onGoogleClick();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    blockedUi();
    assert.strictEqual(calls.redirect, 1, 'first blocked popup tried redirect');
    const firstPopup = calls.popup;
    const firstRedirect = calls.redirect;
    syncPopup = false;
    syncRedirect = false;
    els['cv-google-retry'].click();
    assert.ok(syncPopup, 'Try Google again calls signInWithPopup synchronously');
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.strictEqual(calls.popup, firstPopup + 1, 'Try Google again opens a new popup');
    assert.ok(calls.redirect === firstRedirect + 1, 'Try Google again falls back to redirect after the popup is blocked');
  }

  // "Use email instead" opens the existing email sign-in and restores a single button set.
  {
    els['cv-google-login'].hidden = false;
    const { api, calls } = runWith({
      fbAuth: {
        signInWithPopup() { calls.popup++; return Promise.reject({ code: 'auth/popup-blocked' }); },
        signInWithRedirect() { calls.redirect++; return Promise.reject({ code: 'auth/operation-not-supported-in-this-environment' }); }
      }
    });
    api.ensureJoinAuthLayout();
    api.onGoogleClick();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    blockedUi();
    els['cv-google-use-email'].click();
    const emailBox = els['cv-email-signin'];
    assert.ok(emailBox && emailBox.hidden === false, 'Use email instead opens the email form');
    assert.ok(!els['cv-google-blocked'] || els['cv-google-blocked'].hidden, 'Use email instead hides the blocked sheet');
    assert.ok(els['cv-google-login'] && els['cv-google-login'].hidden === false, 'Use email instead restores the normal Google button (one set)');
  }
}

console.log('accounts-gate: ok (' + guards.length + ' guards, ' + cases.length + ' cases, ' + rooms.length + ' rooms explicit, stamp refuses missing, share menu, email-in-use, unified credential copy, live-user register guard, popup-blocked redirect fallback)');
