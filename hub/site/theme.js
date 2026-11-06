/* Optional Lights Out. No stored value means light. Does not read prefers-color-scheme.
   The choice stays in this browser under subx-hub-theme. Nothing is sent. */
(function () {
  var KEY = 'subx-hub-theme';
  function read() {
    try {
      var v = window.localStorage.getItem(KEY);
      if (v === 'dark' || v === 'light') return v;
    } catch (e) {}
    return 'light';
  }
  function paint(theme) {
    document.documentElement.setAttribute('data-hub-theme', theme);
    var btn = document.getElementById('hub-theme-toggle');
    if (!btn) return;
    btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
  }
  function setTheme(theme) {
    if (theme !== 'dark' && theme !== 'light') theme = 'light';
    try { window.localStorage.setItem(KEY, theme); } catch (e) {}
    paint(theme);
  }
  paint(read());
  function bind() {
    var btn = document.getElementById('hub-theme-toggle');
    if (!btn || btn.getAttribute('data-bound') === '1') return;
    btn.setAttribute('data-bound', '1');
    paint(read());
    btn.addEventListener('click', function () {
      setTheme(document.documentElement.getAttribute('data-hub-theme') === 'dark' ? 'light' : 'dark');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
  window.subxSetHubTheme = setTheme;
})();
