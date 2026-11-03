// SubX takedown and report contact (single constant per room).
var SUBX_TAKEDOWN_EMAIL = 'takedown@subx.it';
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('a[data-takedown]').forEach(function (a) {
    var h = a.getAttribute('href') || '';
    var q = h.indexOf('?');
    a.setAttribute('href', 'mailto:' + SUBX_TAKEDOWN_EMAIL + (q >= 0 ? h.slice(q) : ''));
    if (a.textContent.indexOf('@') >= 0) a.textContent = SUBX_TAKEDOWN_EMAIL;
  });
});
