import re
s = open('merged_raw.js').read()
pat = re.compile(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', re.S)
blocks = list(pat.finditer(s))
assert len(blocks) == 8, len(blocks)
def res(i, o, t):
    if i == 0:
        # keep template hosted config + runWithAuth; add PR31 guard block, drop gpchat inline AIza init
        cut = t.index('  try {\n    firebase.initializeApp({')
        return o + t[:cut].rstrip('\n') + '\n'
    if i == 6:
        # registration: template runWithAuth wrapper + PR31 body (ageGateMessage, nameOk, ensurePublicProfile)
        return """      runWithAuth(err, function () {
        const name = (document.getElementById('cv-reg-name').value || '').trim();
        const email = (document.getElementById('cv-reg-email').value || '').trim();
        const pw = document.getElementById('cv-reg-pw').value || '';
        const age = document.getElementById('cv-reg-age');
        if (!age || !age.checked) {
          err.textContent = ageGateMessage();
          err.classList.add('show');
          return;
        }
        if (name && !nameOk(name)) {
          err.textContent = 'That display name is reserved.';
          err.classList.add('show');
          return;
        }
        if (!email || pw.length < 6) { err.textContent = 'Email and a password of at least 6 characters.'; err.classList.add('show'); return; }
        err.textContent = '';
        markAuthLand();
        fbAuth.createUserWithEmailAndPassword(email, pw).then(function (cred) {
          cred.user.sendEmailVerification().catch(function () {});
          return ensurePublicProfile(cred.user, name, {
            createdAt: firebase.firestore.FieldValue.serverTimestamp()
          }).then(function () {
            composeErr('Account created. Verify your email before posting.');
          });
        }).catch(function (e) {
          err.textContent = (e && e.message) ? e.message : 'Could not create account.';
          err.classList.add('show');
"""
    if i == 7:
        # template boots auth inside fbReadyPromise (patched below); gpchat's sync auth boot is dropped
        return o
    return t  # 1-5: take PR31 (report dedupe, watchlist/reports chrome, post fields, taxonomy/watchlist block, DM guard)
out = []; last = 0
for i, m in enumerate(blocks):
    out.append(s[last:m.start()]); out.append(res(i, m.group(1), m.group(2))); last = m.end()
out.append(s[last:])
s = ''.join(out)
# template auth boot -> PR31 behavior
old_rr = """            var disp = u.displayName || (u.email || 'member').split('@')[0];
            return fbDb.collection('users').doc(u.uid).set({
              displayName: disp,
              siteId: SITE_ID,
              provider: 'google',
              createdAt: firebase.firestore.FieldValue.serverTimestamp()
            }, { merge: true });"""
new_rr = """            return ensurePublicProfile(u, '', {
              provider: 'google',
              createdAt: firebase.firestore.FieldValue.serverTimestamp()
            });"""
assert s.count(old_rr) == 1; s = s.replace(old_rr, new_rr)
old_os = """          else {
            listenBlocks(null);
            if (currentUser && currentUser.live) {
              currentUser = null;
              saveJSON(LS_USER, null);
              renderSidebarAuth();
              hideDummyChrome();
              teardownDms();
              listenConversations();
              syncProfile();
              renderFeed();
            }
          }"""
new_os = """          else {
            stopPreviewLift();
            listenMemberNests(null);
            listenBlocks(null);
            teardownPeopleSocial();
            if (currentUser && currentUser.live) {
              currentUser = null;
              saveJSON(LS_USER, null);
              renderSidebarAuth();
              hideDummyChrome();
              teardownDms();
              listenConversations();
              syncProfile();
              renderNotifs();
              renderFeed();
            } else {
              renderWatchlist();
            }
          }"""
assert s.count(old_os) == 1; s = s.replace(old_os, new_os)
open('merged.js', 'w').write(s)
print('ok')
