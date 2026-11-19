/* SubX factory-featured.js (subx-factory master). DO NOT EDIT IN A ROOM REPO.
 * Lazy add-on. factory.js loads it only when site.json has a "featured" block.
 * 1. Pins new articles by the room's own stewards to the top of For You for a short window, with a Featured label.
 * 2. Adds an "Our articles" card next to the Porch, newest first.
 * 3. X-style Show more: feed posts show the first paragraph, the rest opens in place. A permalink (?p=) shows it all.
 * 4. Post images: alt text from the post, fixed aspect, lazy, https only.
 * All user text goes in with textContent or setAttribute, never as markup. */
(function(root) {
  'use strict';
  var DAY_MS = 86400000;
  var PARA_RE = /\n[ \t]*\n+/;

  function cfgOf(site) {
    var f = (site && site.featured) || {};
    var days = Number(f.featuredDays);
    var minChars = Number(f.articleMinChars);
    var max = Number(f.maxPinned);
    return {
      days: isFinite(days) && days >= 0 ? days : 3,
      handles: (Array.isArray(f.handles) ? f.handles : []).map(function(h) { return String(h).replace(/^@/, '').toLowerCase(); }),
      minChars: isFinite(minChars) && minChars > 0 ? minChars : 600,
      maxPinned: isFinite(max) && max >= 0 ? max : 3,
      listMax: 5,
      label: f.label || 'Our articles'
    };
  }
  function paragraphs(text) {
    return String(text || '').replace(/\r\n?/g, '\n').trim().split(PARA_RE).filter(function(p) { return p.trim(); });
  }
  function firstParagraph(text) {
    var ps = paragraphs(text);
    return ps.length ? ps[0].trim() : '';
  }
  function isLong(text) {
    return paragraphs(text).length > 1;
  }
  function isOurs(post, cfg) {
    if (!post || post.parentId || !(post.steward || post.isAdminAuthor)) return false;
    if (!cfg.handles.length) return true;
    return cfg.handles.indexOf(String(post.handle || '').toLowerCase()) !== -1;
  }
  function isArticle(post, cfg) {
    var t = String((post && post.text) || '');
    return isOurs(post, cfg) && (t.length >= cfg.minChars || isLong(t));
  }
  function ourArticles(posts, cfg) {
    return (posts || []).filter(function(p) { return isArticle(p, cfg); })
      .sort(function(a, b) { return (b.ms || 0) - (a.ms || 0); });
  }
  function featuredIds(posts, cfg, now) {
    var cutoff = (now || Date.now()) - cfg.days * DAY_MS;
    return ourArticles(posts, cfg).filter(function(p) { return (p.ms || 0) >= cutoff; })
      .slice(0, cfg.maxPinned).map(function(p) { return String(p.id); });
  }
  function safeImageUrl(u) {
    return typeof u === 'string' && /^https:\/\/[^\s"'<>]+$/i.test(u) ? u : '';
  }
  function titleOf(text, max) {
    var t = firstParagraph(text).split('\n')[0].replace(/\s+/g, ' ').trim();
    max = max || 90;
    return t.length > max ? t.slice(0, max - 3).replace(/\s+\S*$/, '') + '...' : t;
  }
  function permalink(id) {
    return '/?p=' + encodeURIComponent(String(id));
  }

  function install(CORE) {
    var expanded = {};
    function deepId() {
      try { return new URLSearchParams(location.search).get('p') || ''; } catch (e) { return ''; }
    }
    function cfg() { return cfgOf(CORE.site); }
    function homeForYou() {
      if (CORE.currentNest || CORE.focusedTopicId) return false;
      var tab = document.querySelector('[data-thoughts-tab].active');
      return !tab || tab.dataset.thoughtsTab === 'foryou';
    }
    function postNode(el, id) {
      var nodes = el.querySelectorAll('article.post[data-post-id]');
      for (var i = 0; i < nodes.length; i++) if (nodes[i].getAttribute('data-post-id') === id) return nodes[i];
      return null;
    }
    function pin(el, c, posts) {
      var ids = featuredIds(posts, c, Date.now());
      for (var i = ids.length - 1; i >= 0; i--) {
        var node = postNode(el, ids[i]);
        if (!node) continue;
        var group = [node];
        var sib = node.nextElementSibling;
        while (sib && sib.getAttribute('data-parent-id') === ids[i]) { group.push(sib); sib = sib.nextElementSibling; }
        var top = el.firstChild;
        group.forEach(function(n) { el.insertBefore(n, top); });
        node.classList.add('post-featured');
        var meta = node.querySelector('.post-meta');
        if (meta && !meta.querySelector('.post-featured-pill')) {
          var pill = document.createElement('span');
          pill.className = 'post-featured-pill';
          pill.textContent = 'Featured';
          meta.appendChild(pill);
        }
      }
    }
    function collapse(el) {
      var deep = deepId();
      var nodes = el.querySelectorAll('article.post[data-post-id]');
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        var id = node.getAttribute('data-post-id');
        var p = node.querySelector('.post-text');
        if (!p || p.getAttribute('data-full') === '1' || node.querySelector('.post-more')) continue;
        var full = p.textContent;
        if (!isLong(full) || id === deep) continue;
        var first = firstParagraph(full);
        p.id = 'post-text-' + id.replace(/[^A-Za-z0-9_-]/g, '');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'post-more';
        btn.setAttribute('aria-controls', p.id);
        (function(p, btn, id, full, first) {
          function set(open) {
            p.textContent = open ? full : first;
            btn.textContent = open ? 'Show less' : 'Show more';
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (open) expanded[id] = true; else delete expanded[id];
          }
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            set(btn.getAttribute('aria-expanded') !== 'true');
          });
          set(!!expanded[id]);
        })(p, btn, id, full, first);
        p.parentNode.insertBefore(btn, p.nextSibling);
      }
    }
    function images(el, posts) {
      var byId = {};
      (posts || []).forEach(function(p) { byId[String(p.id)] = p; });
      var imgs = el.querySelectorAll('.post-image img');
      for (var i = 0; i < imgs.length; i++) {
        var img = imgs[i];
        var wrap = img.parentNode;
        if (!safeImageUrl(img.getAttribute('src'))) { if (wrap && wrap.parentNode) wrap.parentNode.removeChild(wrap); continue; }
        var art = img.closest('article.post');
        var post = art && byId[art.getAttribute('data-post-id')];
        img.setAttribute('loading', 'lazy');
        img.setAttribute('decoding', 'async');
        if (!img.getAttribute('alt')) img.setAttribute('alt', post ? (post.imageAlt || titleOf(post.text, 120) || 'Post image') : 'Post image');
        if (wrap) wrap.classList.add('post-image-fixed');
      }
    }
    function ourCard(c, list) {
      var card = document.createElement('div');
      card.className = 'news-item news-item-ours';
      var tag = document.createElement('div');
      tag.className = 'news-item-tag';
      tag.textContent = 'Porch';
      var h = document.createElement('h3');
      h.className = 'news-item-headline';
      h.id = 'our-articles-h';
      h.textContent = c.label;
      var ul = document.createElement('ul');
      ul.className = 'our-articles';
      ul.setAttribute('aria-labelledby', 'our-articles-h');
      list.slice(0, c.listMax).forEach(function(p) {
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = permalink(p.id);
        a.textContent = titleOf(p.text, 80) || 'Article';
        var meta = document.createElement('span');
        meta.className = 'our-articles-meta';
        var d = new Date(p.ms || Date.now());
        meta.textContent = '@' + (p.handle || '') + ' · ' + d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        li.appendChild(a);
        li.appendChild(meta);
        ul.appendChild(li);
      });
      card.appendChild(tag);
      card.appendChild(h);
      card.appendChild(ul);
      return card;
    }
    function porch(c, posts) {
      var list = ourArticles(posts, c);
      ['news-feed', 'news-page-list'].forEach(function(cid, k) {
        var box = document.getElementById(cid);
        if (!box) return;
        var old = box.querySelector('.news-item-ours');
        if (old) old.parentNode.removeChild(old);
        if (!list.length) return;
        var card = ourCard(c, list);
        if (k) { card.querySelector('h3').id = 'our-articles-h2'; card.querySelector('ul').setAttribute('aria-labelledby', 'our-articles-h2'); }
        var anchor = box.querySelector('.news-item-porch');
        if (anchor) box.insertBefore(card, anchor.nextSibling);
        else box.insertBefore(card, box.firstChild);
      });
    }
    function feat(el) {
      var c = cfg();
      var posts = CORE.topLevelPosts ? CORE.topLevelPosts() : [];
      if (el) {
        if (homeForYou()) pin(el, c, posts);
        images(el, posts);
        collapse(el);
      }
      porch(c, posts);
    }
    return { feat: feat };
  }

  var api = {
    cfgOf: cfgOf, paragraphs: paragraphs, firstParagraph: firstParagraph, isLong: isLong,
    isOurs: isOurs, isArticle: isArticle, ourArticles: ourArticles, featuredIds: featuredIds,
    safeImageUrl: safeImageUrl, titleOf: titleOf, permalink: permalink, install: install
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.__subxFeat = install;
})(typeof window !== 'undefined' ? window : null);
