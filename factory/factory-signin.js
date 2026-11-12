/* SubX factory-signin.js (subx-factory master). DO NOT EDIT IN A ROOM REPO.
 * Source: github.com/jebbdykstra99/subx-factory  (version + sha256 in the room's FACTORY.lock)
 * Room differences belong in site.json (features, skin, rail, nests, minAge) or in EXCEPTIONS.md. */
(function () {
  'use strict';
  var host = window.__subxSigninHost;
  if (!host || typeof host.install !== 'function') {
    console.warn('factory-signin: host not ready');
    return;
  }
  if (host._installed) return;

  var GOOGLE_REDIRECT_KEY = 'subx.googleRedirect';
  function storageSet(store, key, val) {
    try { store.setItem(key, val); } catch (e) {}
  }
  function storageGet(store, key) {
    try { return store.getItem(key); } catch (e) { return null; }
  }
  function storageDel(store, key) {
    try { store.removeItem(key); } catch (e) {}
  }
  function rememberGoogleRedirect() {
    storageSet(sessionStorage, GOOGLE_REDIRECT_KEY, '1');
    storageSet(localStorage, GOOGLE_REDIRECT_KEY, '1');
  }
  function peekGoogleRedirect() {
    return storageGet(sessionStorage, GOOGLE_REDIRECT_KEY) === '1' || storageGet(localStorage, GOOGLE_REDIRECT_KEY) === '1';
  }
  function clearGoogleRedirect() {
    storageDel(sessionStorage, GOOGLE_REDIRECT_KEY);
    storageDel(localStorage, GOOGLE_REDIRECT_KEY);
  }
  function showGooglePopupBlocked(msg) {
    var err = document.getElementById('cv-login-err');
    if (!err) return;
    err.textContent = msg || 'Google sign-in did not complete. Try again or use email.';
    err.classList.add('show');
  }

  function ensureJoinAuthCss() {
    if (document.getElementById('join-auth-css')) return;
    var st = document.createElement('style');
    st.id = 'join-auth-css';
    st.textContent =
      '.conv-modal-tabs.is-join-hidden{display:none;}.conv-email-toggle{width:100%;padding:0.55rem;margin:0.15rem 0 0.35rem;background:transparent;border:1px solid var(--border,rgba(0,0,0,0.14));border-radius:50px;cursor:pointer;font-size:0.82rem;font-weight:600;color:var(--text-muted,#666);}.conv-email-toggle:hover{color:var(--text,#111);}.cv-email-signin{margin-top:0.2rem;}.conv-google-btn{margin-bottom:0.2rem;}';
    document.head.appendChild(st);
  }
  function ageCheckLabel() {
    var box = document.getElementById('cv-google-age');
    if (!box) return null;
    return box.closest('label') || box;
  }
  function fieldWrap(input) {
    if (!input) return null;
    return input.closest('.conv-modal-field') || input;
  }
  function toggleEmailAuth(forceOpen) {
    var box = document.getElementById('cv-email-signin');
    var btn = document.getElementById('cv-use-email-btn');
    if (!box) return;
    var open = forceOpen === true ? true : forceOpen === false ? false : box.hidden;
    box.hidden = !open;
    if (btn) btn.textContent = open ? 'Hide email' : 'Use email';
  }
  function ensureJoinAuthLayout() {
    var panel = document.getElementById('cv-panel-login');
    if (!panel) return;
    ensureJoinAuthCss();
    if (panel.getAttribute('data-join-layout') === '1') { ensureInAppNote(); return; }
    panel.setAttribute('data-join-layout', '1');

    var err = document.getElementById('cv-login-err');
    var ageLab = ageCheckLabel();
    var google = document.getElementById('cv-google-login');
    var divider = panel.querySelector('.conv-modal-divider');
    var guest = document.getElementById('cv-guest-login');
    var emailIn = document.getElementById('cv-login-email');
    var pwIn = document.getElementById('cv-login-pw');
    var loginBtn = document.getElementById('cv-login-btn');

    var emailBox = document.getElementById('cv-email-signin');
    if (!emailBox) {
      emailBox = document.createElement('div');
      emailBox.id = 'cv-email-signin';
      emailBox.className = 'cv-email-signin';
    }
    emailBox.hidden = true;

    var emailField = fieldWrap(emailIn);
    var pwField = fieldWrap(pwIn);
    if (emailField && emailField.parentNode !== emailBox) emailBox.appendChild(emailField);
    if (pwField && pwField.parentNode !== emailBox) emailBox.appendChild(pwField);
    if (loginBtn && loginBtn.parentNode !== emailBox) emailBox.appendChild(loginBtn);

    var gotoReg = document.getElementById('cv-goto-register');
    if (!gotoReg) {
      gotoReg = document.createElement('button');
      gotoReg.id = 'cv-goto-register';
      gotoReg.type = 'button';
      gotoReg.className = 'conv-guest-btn';
      gotoReg.textContent = 'Create an account';
    }
    if (gotoReg.parentNode !== emailBox) emailBox.appendChild(gotoReg);
    ensureForgotPasswordLink(emailBox);

    var useEmail = document.getElementById('cv-use-email-btn');
    if (!useEmail) {
      useEmail = document.createElement('button');
      useEmail.id = 'cv-use-email-btn';
      useEmail.type = 'button';
      useEmail.className = 'conv-email-toggle';
      useEmail.textContent = 'Use email';
    }

    if (divider) divider.textContent = 'or use email';

    [err, ageLab, google, divider, useEmail, emailBox, guest].forEach(function (n) {
      if (n) panel.appendChild(n);
    });
    ensureInAppNote();

    var reg = document.getElementById('cv-panel-register');
    if (reg && !document.getElementById('cv-goto-join')) {
      var back = document.createElement('button');
      back.id = 'cv-goto-join';
      back.type = 'button';
      back.className = 'conv-guest-btn';
      back.textContent = 'Continue with Google instead';
      var regErr = document.getElementById('cv-reg-err');
      if (regErr && regErr.nextSibling) reg.insertBefore(back, regErr.nextSibling);
      else if (reg.firstChild) reg.insertBefore(back, reg.firstChild);
      else reg.appendChild(back);
    }
  }

  function onGoogleClick() {
    var fbAuth = host.fbAuth;
    var err = document.getElementById('cv-login-err');
    if (!fbAuth) {
      err.textContent = 'Auth is not ready.';
      err.classList.add('show');
      return;
    }
    if (!host.accountsOpen() && !document.documentElement.classList.contains('acc-stew')) { err.textContent = host.ACC_CLOSED; err.classList.add('show'); return; }
    var age = document.getElementById('cv-google-age');
    if (!age || !age.checked) {
      err.textContent = host.ageGateMessage();
      err.classList.add('show');
      return;
    }
    err.textContent = '';
    err.classList.remove('show');
    host.markAuthLand();
    clearGoogleRedirect();
    var provider = new firebase.auth.GoogleAuthProvider();
    function finishGoogle(cred) {
      clearGoogleRedirect();
      var u = cred && cred.user;
      if (u && !host.accountsOpen() && u.uid !== host.ADMIN_UID) return fbAuth.signOut().then(function () { throw new Error(host.ACC_CLOSED); });
      if (host.fbDb && u) {
        return host.ensurePublicProfile(u, '', {
          provider: 'google',
          createdAt: firebase.firestore.FieldValue.serverTimestamp()
        });
      }
    }
    function failGoogle(e) {
      var msg;
      if (e && e.code === 'auth/operation-not-allowed') {
        msg = 'Google sign-in is not available right now. Use email.';
      } else if (e && e.code === 'auth/popup-closed-by-user') {
        msg = 'Google sign-in cancelled.';
      } else {
        msg = authErrorMessage(e, 'Google sign-in failed.');
      }
      err.textContent = msg;
      err.classList.add('show');
    }
    function redirectGoogle() {
      rememberGoogleRedirect();
      showGooglePopupBlocked('Google popup sign-in could not open. Trying another sign-in method.');
      return fbAuth.signInWithRedirect(provider).catch(function (e2) {
        clearGoogleRedirect();
        failGoogle(e2);
      });
    }
    // Call popup in this tap. iOS Safari blocks it if this handler waits first.
    fbAuth.signInWithPopup(provider).then(finishGoogle).catch(function (e) {
      var code = e && e.code;
      if (code === 'auth/popup-blocked' || code === 'auth/operation-not-supported-in-this-environment') {
        return redirectGoogle();
      }
      failGoogle(e);
    });
  }

  function handleRedirectResult() {
    var fbAuth = host.fbAuth;
    if (!fbAuth) return Promise.resolve();
    return fbAuth.getRedirectResult().then(function (cred) {
      var u = cred && cred.user;
      if (u) {
        clearGoogleRedirect();
        if (!host.accountsOpen() && u.uid !== host.ADMIN_UID) return fbAuth.signOut();
        if (host.fbDb) {
          return host.ensurePublicProfile(u, '', {
            provider: 'google',
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
          });
        }
        return;
      }
      if (peekGoogleRedirect() && !(fbAuth && fbAuth.currentUser)) {
        clearGoogleRedirect();
        showGooglePopupBlocked();
        host.setAuthOpenWhenReady(true);
      }
    }).catch(function (e) {
      console.warn('redirect result', e);
      clearGoogleRedirect();
      if (fbAuth && fbAuth.currentUser) return;
      var el = document.getElementById('cv-login-err');
      var msg = authErrorMessage(e, 'Google sign-in failed.');
      if (el) { el.textContent = msg; el.classList.add('show'); }
      host.setAuthOpenWhenReady(true);
    });
  }


  function authErrorMessage(e, fallback) {
    var code = (e && e.code) || '';
    if (code === 'auth/wrong-password' || code === 'auth/invalid-credential' || code === 'auth/invalid-login-credentials' || code === 'auth/user-not-found') {
      return 'That email or password is not right. Try again, reset your password, or use Continue with Google.';
    }
    if (code === 'auth/too-many-requests') return 'Too many tries. Wait a few minutes and try again.';
    if (code === 'auth/network-request-failed' || /network/i.test(code)) return 'Could not reach the sign-in service. Check your connection and try again.';
    return fallback || 'Sign-in failed. Try again.';
  }
  function offersGoogleOn(code) {
    return code === 'auth/email-already-in-use' || code === 'auth/invalid-credential' || code === 'auth/invalid-login-credentials' || code === 'auth/wrong-password' || code === 'auth/user-not-found';
  }
  function inAppBrowserName() {
    var ua = (typeof navigator !== 'undefined' && navigator.userAgent) || '';
    if (/Instagram/i.test(ua)) return 'Instagram';
    if (/\bTwitter\b|\bTweetie\b|X\/\d/i.test(ua)) return 'X';
    if (/FBAN|FBAV|FB_IAB|FBIOS/i.test(ua)) return 'Facebook';
    return '';
  }
  function ensureInAppNote() {
    var panel = document.getElementById('cv-panel-login');
    var name = inAppBrowserName();
    var note = document.getElementById('cv-inapp-note');
    if (!name) {
      if (note) note.hidden = true;
      return;
    }
    if (!note) {
      note = document.createElement('p');
      note.id = 'cv-inapp-note';
      note.className = 'conv-modal-note';
      note.setAttribute('role', 'status');
    }
    note.textContent = 'Google sign-in may not work inside ' + name + '. Open in your browser, or use email.';
    note.hidden = false;
    if (panel && note.parentNode !== panel) panel.insertBefore(note, panel.firstChild);
    toggleEmailAuth(true);
  }
  function ensureForgotPasswordLink(emailBox) {
    if (!emailBox) return;
    var forgot = document.getElementById('cv-forgot-pw');
    if (!forgot) {
      forgot = document.createElement('button');
      forgot.id = 'cv-forgot-pw';
      forgot.type = 'button';
      forgot.className = 'conv-email-toggle';
      forgot.textContent = 'Forgot password?';
      forgot.addEventListener('click', onForgotPassword);
    }
    if (forgot.parentNode !== emailBox) emailBox.appendChild(forgot);
  }
  function onForgotPassword(e) {
    if (e && e.preventDefault) e.preventDefault();
    var email = ((document.getElementById('cv-login-email') && document.getElementById('cv-login-email').value) ||
      (document.getElementById('cv-reg-email') && document.getElementById('cv-reg-email').value) || '').trim();
    var err = document.getElementById('cv-login-err') || document.getElementById('cv-reg-err');
    function show(msg) {
      if (!err) return;
      err.textContent = msg;
      err.classList.add('show');
    }
    if (!email) { show('Enter your email first.'); return; }
    var fbAuth = host.fbAuth;
    if (!fbAuth || typeof fbAuth.sendPasswordResetEmail !== 'function') { show('Auth is not ready.'); return; }
    fbAuth.sendPasswordResetEmail(email).then(function () {
      show('If an account exists for that email, a reset message is on its way.');
    }).catch(function (e2) {
      var code = (e2 && e2.code) || '';
      if (code === 'auth/user-not-found' || code === 'auth/invalid-email') {
        show('If an account exists for that email, a reset message is on its way.');
        return;
      }
      show(authErrorMessage(e2, 'If an account exists for that email, a reset message is on its way.'));
    });
  }
  function switchToSignInForm(email, pw) {
    var login = document.getElementById('cv-panel-login');
    var reg = document.getElementById('cv-panel-register');
    if (login) login.style.display = '';
    if (reg) reg.style.display = 'none';
    toggleEmailAuth(true);
    var emailIn = document.getElementById('cv-login-email');
    var pwIn = document.getElementById('cv-login-pw');
    if (emailIn) emailIn.value = email || '';
    if (pwIn) pwIn.value = pw || '';
    var emailBox = document.getElementById('cv-email-signin');
    ensureForgotPasswordLink(emailBox);
  }
  function showContinueGoogle(errEl, msg) {
    if (errEl && msg) {
      errEl.textContent = msg;
      errEl.classList.add('show');
    }
    var hostEl = errEl && errEl.parentNode;
    var btn = document.getElementById('cv-continue-google');
    if (!btn) {
      btn = document.createElement('button');
      btn.id = 'cv-continue-google';
      btn.type = 'button';
      btn.className = 'conv-google-btn';
      btn.textContent = 'Continue with Google';
      btn.addEventListener('click', function () {
        var regAge = document.getElementById('cv-reg-age');
        var gAge = document.getElementById('cv-google-age');
        if (regAge && regAge.checked && gAge && !gAge.checked) gAge.checked = true;
        onGoogleClick();
      });
    }
    btn.hidden = false;
    if (hostEl && btn.parentNode !== hostEl) {
      if (errEl && errEl.nextSibling) hostEl.insertBefore(btn, errEl.nextSibling);
      else if (hostEl) hostEl.appendChild(btn);
    }
  }
  function switchToSignInAndTry(email, pw, errEl) {
    switchToSignInForm(email, pw);
    var fbAuth = host.fbAuth;
    var loginErr = document.getElementById('cv-login-err') || errEl;
    showContinueGoogle(loginErr);
    if (!fbAuth) {
      if (loginErr) { loginErr.textContent = 'Auth is not ready.'; loginErr.classList.add('show'); }
      return Promise.resolve();
    }
    host.markAuthLand();
    return fbAuth.signInWithEmailAndPassword(email, pw).catch(function (e) {
      var code = (e && e.code) || '';
      if (loginErr) {
        loginErr.textContent = authErrorMessage(e, 'Sign-in failed. Try again.');
        loginErr.classList.add('show');
      }
      if (offersGoogleOn(code)) showContinueGoogle(loginErr);
    });
  }
  function handleEmailAlreadyInUse(email, pw, errEl) {
    var fbAuth = host.fbAuth;
    var lookup = (fbAuth && typeof fbAuth.fetchSignInMethodsForEmail === 'function')
      ? Promise.resolve().then(function () { return fbAuth.fetchSignInMethodsForEmail(email); })
      : Promise.reject(new Error('unavailable'));
    return lookup.then(function (methods) {
      var list = Array.isArray(methods) ? methods : [];
      var hasGoogle = list.indexOf('google.com') !== -1;
      if (hasGoogle) {
        switchToSignInForm(email, pw);
        showContinueGoogle(document.getElementById('cv-login-err') || errEl, 'This email signs in with Google.');
        return;
      }
      return switchToSignInAndTry(email, pw, errEl);
    }).catch(function () {
      return switchToSignInAndTry(email, pw, errEl);
    });
  }

  function onEmailLogin() {
    var err = document.getElementById('cv-login-err');
    var fbAuth = host.fbAuth;
    host.runWithAuth(err, function () {
      host.authPersistPromise.then(function () {
      var email = (document.getElementById('cv-login-email').value || '').trim();
      var pw = document.getElementById('cv-login-pw').value || '';
      err.textContent = '';
      host.markAuthLand();
      fbAuth.signInWithEmailAndPassword(email, pw).catch(function (e) {
        var code = (e && e.code) || '';
        err.textContent = authErrorMessage(e, 'Sign-in failed. Try again.');
        err.classList.add('show');
        if (offersGoogleOn(code)) showContinueGoogle(err);
      });
      });
    });
  }
  function onRegister() {
    if (typeof host.isLiveUser === 'function' && host.isLiveUser()) {
      if (typeof host.closeAuth === 'function') host.closeAuth();
      return;
    }
    var err = document.getElementById('cv-reg-err');
    var fbAuth = host.fbAuth;
    host.runWithAuth(err, function () {
      host.authPersistPromise.then(function () {
      var name = (document.getElementById('cv-reg-name').value || '').trim();
      var email = (document.getElementById('cv-reg-email').value || '').trim();
      var pw = document.getElementById('cv-reg-pw').value || '';
      var age = document.getElementById('cv-reg-age');
      if (!host.accountsOpen()) { err.textContent = host.ACC_CLOSED; err.classList.add('show'); return; }
      if (!age || !age.checked) {
        err.textContent = host.ageGateMessage();
        err.classList.add('show');
        return;
      }
      if (name && !host.nameOk(name)) {
        err.textContent = 'That display name is reserved.';
        err.classList.add('show');
        return;
      }
      if (!email || pw.length < 6) { err.textContent = 'Email and a password of at least 6 characters.'; err.classList.add('show'); return; }
      err.textContent = '';
      host.markAuthLand();
      fbAuth.createUserWithEmailAndPassword(email, pw).then(function (cred) {
        cred.user.sendEmailVerification().catch(function () {});
        return host.ensurePublicProfile(cred.user, name, {
          createdAt: firebase.firestore.FieldValue.serverTimestamp()
        }).then(function () {
          host.composeErr('Account created. Verify your email before posting.');
        });
      }).catch(function (e) {
        if (e && e.code === 'auth/email-already-in-use') {
          return handleEmailAlreadyInUse(email, pw, err);
        }
        err.textContent = authErrorMessage(e, 'Could not create account.');
        err.classList.add('show');
      });
      });
    });
  }

  host._installed = true;
  host.install({
    ensureJoinAuthLayout: ensureJoinAuthLayout,
    ensureInAppNote: ensureInAppNote,
    toggleEmailAuth: toggleEmailAuth,
    onEmailLogin: onEmailLogin,
    onRegister: onRegister,
    onGoogleClick: onGoogleClick,
    handleRedirectResult: handleRedirectResult
  });
})();
