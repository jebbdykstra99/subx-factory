(function () {
  'use strict';

  var SITE_URL = (document.currentScript && document.currentScript.getAttribute('data-site')) || 'site.json';
  var HONESTY = 'Unofficial helper · not a substitute for 911 · links to official city channels · preview';
  var MAX_KM = 100;
  var LS_NEST = '311chat.nest';

  var ALIASES = {
    nyc: ['nyc', 'new york', 'new york city', 'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island'],
    la: ['la', 'los angeles'],
    chicago: ['chicago', 'chi'],
    houston: ['houston'],
    phoenix: ['phoenix'],
    philadelphia: ['philadelphia', 'philly'],
    'san-antonio': ['san antonio', 'sanantonio', 'san-antonio'],
    boston: ['boston']
  };

  var ZIP3 = {
    '100': 'nyc', '101': 'nyc', '102': 'nyc', '103': 'nyc', '104': 'nyc',
    '111': 'nyc', '112': 'nyc', '113': 'nyc', '114': 'nyc',
    '900': 'la', '901': 'la', '902': 'la', '903': 'la', '904': 'la', '905': 'la',
    '906': 'la', '907': 'la', '908': 'la', '910': 'la', '911': 'la', '912': 'la',
    '913': 'la', '914': 'la', '915': 'la', '916': 'la',
    '606': 'chicago',
    '770': 'houston', '772': 'houston', '773': 'houston', '774': 'houston', '775': 'houston',
    '850': 'phoenix', '851': 'phoenix', '852': 'phoenix', '853': 'phoenix',
    '191': 'philadelphia',
    '782': 'san-antonio',
    '021': 'boston', '022': 'boston'
  };

  var CENTERS = {
    nyc: [40.7128, -74.006],
    la: [34.0522, -118.2437],
    chicago: [41.8781, -87.6298],
    houston: [29.7604, -95.3698],
    phoenix: [33.4484, -112.074],
    philadelphia: [39.9526, -75.1652],
    'san-antonio': [29.4241, -98.4936],
    boston: [42.3601, -71.0589]
  };

  var ISSUES = [
    ['pothole', 'Pothole'],
    ['streetlight', 'Streetlight'],
    ['trash', 'Trash'],
    ['graffiti', 'Graffiti'],
    ['noise', 'Noise'],
    ['animals', 'Animals'],
    ['parking', 'Parking / info'],
    ['other', 'Other']
  ];

  var site = null;
  var activeSlug = '';
  var activeIssue = '';

  function $(id) { return document.getElementById(id); }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function nests() { return (site && site.nests) || []; }
  function nestBySlug(slug) {
    var list = nests();
    for (var i = 0; i < list.length; i++) if (list[i].slug === slug) return list[i];
    return null;
  }
  function norm(s) {
    return String(s || '').toLowerCase().replace(/\./g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function cityToSlug(raw) {
    var text = norm(raw);
    if (!text) return '';
    var keys = Object.keys(ALIASES);
    for (var i = 0; i < keys.length; i++) {
      var slug = keys[i];
      var names = ALIASES[slug];
      for (var j = 0; j < names.length; j++) {
        var alias = names[j];
        if (text === alias) return slug;
        if (alias.length >= 4 && text.indexOf(alias) !== -1) return slug;
      }
    }
    var list = nests();
    for (var k = 0; k < list.length; k++) {
      var label = norm(list[k].label);
      if (label && (text === label || text.indexOf(label) !== -1)) return list[k].slug;
    }
    return '';
  }
  function zipToSlug(raw) {
    var digits = String(raw || '').replace(/\D/g, '');
    if (digits.length < 5) return '';
    return ZIP3[digits.slice(0, 3)] || '';
  }
  function haversine(lat1, lon1, lat2, lon2) {
    var R = 6371;
    var p1 = lat1 * Math.PI / 180;
    var p2 = lat2 * Math.PI / 180;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  function nearestSlug(lat, lon) {
    var best = '';
    var bestKm = Infinity;
    Object.keys(CENTERS).forEach(function (slug) {
      if (!nestBySlug(slug)) return;
      var km = haversine(lat, lon, CENTERS[slug][0], CENTERS[slug][1]);
      if (km < bestKm) { bestKm = km; best = slug; }
    });
    if (!best || bestKm > MAX_KM) return '';
    return best;
  }
  function queryNest() {
    try { return new URLSearchParams(location.search).get('nest') || ''; }
    catch (e) { return ''; }
  }
  function queryIssue() {
    try { return new URLSearchParams(location.search).get('issue') || ''; }
    catch (e) { return ''; }
  }
  function writeQuery() {
    var url;
    try { url = new URL(location.href); }
    catch (e) { return; }
    if (activeSlug) url.searchParams.set('nest', activeSlug);
    else url.searchParams.delete('nest');
    if (activeIssue) url.searchParams.set('issue', activeIssue);
    else url.searchParams.delete('issue');
    history.replaceState(null, '', url.pathname + url.search + url.hash);
  }
  function setNote(msg, isErr) {
    var el = $('city-gate-note');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('is-err', !!isErr);
  }
  function telHref(phone) {
    var raw = String(phone || '').trim();
    if (raw === '311') return 'tel:311';
    var digits = raw.replace(/[^\d+]/g, '');
    return digits ? ('tel:' + digits) : '';
  }
  function renderPicks() {
    var host = $('nest-picks');
    if (!host) return;
    host.innerHTML = nests().map(function (n) {
      var on = n.slug === activeSlug ? ' is-on' : '';
      return '<button type="button" class="nest-chip' + on + '" data-nest="' + escapeHtml(n.slug) + '">' +
        escapeHtml(n.label || n.slug) + '</button>';
    }).join('');
  }
  function renderIssues() {
    var label = $('issue-label');
    var host = $('issue-picks');
    var show = !!activeSlug;
    if (label) label.hidden = !show;
    if (!host) return;
    host.hidden = !show;
    if (!show) { host.innerHTML = ''; return; }
    host.innerHTML = ISSUES.map(function (pair) {
      var on = pair[0] === activeIssue ? ' is-on' : '';
      return '<button type="button" class="issue-chip' + on + '" data-issue="' + pair[0] + '">' +
        escapeHtml(pair[1]) + '</button>';
    }).join('');
  }
  function renderHandoff() {
    var host = $('handoff');
    if (!host) return;
    var nest = nestBySlug(activeSlug);
    if (!nest) { host.hidden = true; host.innerHTML = ''; return; }
    var cities = (site.directory && site.directory.cities) || {};
    var row = cities[activeSlug] || null;
    var label = (row && row.label) || nest.label || activeSlug;
    var blurb = nest.blurb || '';
    var phone = row && row.phone;
    var portal = row && row.portal;
    var note = (site.directory && site.directory.note) || '';
    var issueName = '';
    for (var i = 0; i < ISSUES.length; i++) if (ISSUES[i][0] === activeIssue) issueName = ISSUES[i][1];
    var actions = '';
    if (phone) {
      actions += '<a class="accent-btn" href="' + escapeHtml(telHref(phone)) + '">Call ' + escapeHtml(phone) + '</a>';
    }
    if (portal) {
      actions += '<a class="ghost-btn" href="' + escapeHtml(portal) + '" target="_blank" rel="noopener noreferrer">Official portal</a>';
    }
    var issueLine = issueName
      ? '<p class="handoff-issue">Marked as ' + escapeHtml(issueName) + '. We do not file this. Use the official channel.</p>'
      : '';
    var missing = (!phone && !portal)
      ? '<p class="handoff-blurb">No official handoff is listed for this nest yet.</p>'
      : '';
    host.hidden = false;
    host.innerHTML =
      '<article class="handoff-card">' +
        '<div class="handoff-kicker">Official channel</div>' +
        '<h3>' + escapeHtml(label) + '</h3>' +
        (blurb ? '<p class="handoff-blurb">' + escapeHtml(blurb) + '</p>' : '') +
        missing +
        '<div class="handoff-actions">' + actions + '</div>' +
        issueLine +
        (note ? '<p class="handoff-note">' + escapeHtml(note) + '</p>' : '') +
      '</article>';
  }
  function selectSlug(slug, note, isErr) {
    if (slug && !nestBySlug(slug)) slug = '';
    activeSlug = slug || '';
    try {
      if (activeSlug) sessionStorage.setItem(LS_NEST, activeSlug);
      else sessionStorage.removeItem(LS_NEST);
    } catch (e) { /* private mode */ }
    var nest = nestBySlug(activeSlug);
    var city = $('city-input');
    if (city && nest) city.value = nest.label;
    writeQuery();
    renderPicks();
    renderIssues();
    renderHandoff();
    if (note) setNote(note, isErr);
    else if (nest) setNote(nest.label + ' · nest ?nest=' + nest.slug, false);
    else setNote('Pick a city, enter a ZIP, or use location if you want to.', false);
  }
  function resolveFromForm() {
    var city = ($('city-input') && $('city-input').value) || '';
    var zip = ($('zip-input') && $('zip-input').value) || '';
    var fromCity = cityToSlug(city);
    var fromZip = zipToSlug(zip);
    if (fromCity && fromZip && fromCity !== fromZip) {
      selectSlug(fromCity, 'That ZIP is not in ' + (nestBySlug(fromCity).label) + ' for this preview. Showing the city you typed.', true);
      return;
    }
    var slug = fromCity || fromZip;
    if (!slug) {
      selectSlug('', 'No seed city matched. Pick one of the eight cities below.', true);
      return;
    }
    selectSlug(slug, '', false);
  }
  function useGeo() {
    if (!navigator.geolocation) {
      setNote('This browser has no location API. Type a city or ZIP.', true);
      return;
    }
    setNote('Asking the browser for location…', false);
    navigator.geolocation.getCurrentPosition(function (pos) {
      var slug = nearestSlug(pos.coords.latitude, pos.coords.longitude);
      if (!slug) {
        selectSlug('', 'That point is outside the eight preview cities. Type a city or pick one.', true);
        return;
      }
      selectSlug(slug, 'Matched from the location you allowed. Nothing was read from the network.', false);
    }, function () {
      setNote('Location stayed off. Type a city or ZIP instead.', true);
    }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
  }
  function syncChrome() {
    var banner = document.querySelector('.preview-banner');
    if (!banner) return;
    document.documentElement.style.setProperty('--chrome-h', banner.offsetHeight + 'px');
  }
  function paintHonesty() {
    var el = $('honesty-line');
    var line = (site && site.honesty) || HONESTY;
    if (el) el.textContent = line;
  }
  function paintPrompt() {
    var prompt = $('city-gate-prompt');
    var gate = site && site.locationGate;
    if (prompt && gate && gate.prompt) prompt.textContent = gate.prompt;
    var geo = $('geo-opt-in');
    if (geo) geo.hidden = !(gate && gate.geolocationOptIn);
  }
  function boot(data) {
    site = data || {};
    paintHonesty();
    paintPrompt();
    syncChrome();
    window.addEventListener('resize', syncChrome);
    var fromQuery = queryNest();
    var issue = queryIssue();
    if (issue) {
      for (var i = 0; i < ISSUES.length; i++) if (ISSUES[i][0] === issue) activeIssue = issue;
    }
    var stored = '';
    try { stored = sessionStorage.getItem(LS_NEST) || ''; } catch (e) { stored = ''; }
    var initial = nestBySlug(fromQuery) ? fromQuery : (nestBySlug(stored) ? stored : '');
    renderPicks();
    if (initial) selectSlug(initial, '', false);
    else setNote('Location is optional. The button asks the browser. We do not guess from your network.', false);

    var form = $('city-gate-form');
    if (form) form.addEventListener('submit', function (e) {
      e.preventDefault();
      resolveFromForm();
    });
    var geo = $('geo-opt-in');
    if (geo) geo.addEventListener('click', useGeo);
    var picks = $('nest-picks');
    if (picks) picks.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-nest]') : null;
      if (!btn) return;
      selectSlug(btn.getAttribute('data-nest'), '', false);
    });
    var issues = $('issue-picks');
    if (issues) issues.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-issue]') : null;
      if (!btn) return;
      var next = btn.getAttribute('data-issue') || '';
      activeIssue = (activeIssue === next) ? '' : next;
      writeQuery();
      renderIssues();
      renderHandoff();
    });
  }

  fetch(SITE_URL)
    .then(function (res) {
      if (!res.ok) throw new Error('site.json');
      return res.json();
    })
    .then(boot)
    .catch(function () {
      boot({ honesty: HONESTY, nests: [], directory: { cities: {} }, locationGate: { enabled: true, geolocationOptIn: true, prompt: "Where are you? We'll find your city's non-emergency 311." } });
    });
})();
