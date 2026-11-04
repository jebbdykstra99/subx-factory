// SubX takedown and report contact (single constant, from brand/brand.json takedownEmail).
var HUB_TAKEDOWN_EMAIL = 'takedown@subx.it';
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('a[data-takedown]').forEach(function (a) {
    var h = a.getAttribute('href') || '';
    var q = h.indexOf('?');
    a.setAttribute('href', 'mailto:' + HUB_TAKEDOWN_EMAIL + (q >= 0 ? h.slice(q) : ''));
    if (a.textContent.indexOf('@') >= 0) a.textContent = HUB_TAKEDOWN_EMAIL;
  });
});
