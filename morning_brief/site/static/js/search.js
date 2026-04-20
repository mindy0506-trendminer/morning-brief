/* Client-side search over search_index.json (or per-year shards).
 *
 * Load strategy: lazy. The JSON is fetched only after the user types the
 * first character. This keeps the index page's initial render cheap.
 *
 * Ranking:
 *   score = (match_count * 10) + recency_bonus
 * where recency_bonus decays linearly from 30 (today) to 0 (~1 year old).
 *
 * Graceful degradation: if fetch fails or JS is disabled, the search form
 * becomes a no-op (onsubmit=return false) so it does not break navigation.
 */
(function () {
  var input = document.querySelector('[data-search-input]');
  var results = document.querySelector('[data-search-results]');
  if (!input || !results) return;

  var index = null;
  var fetchPromise = null;

  function searchIndexUrl() {
    // Relative to the current page. archive pages are 3 levels deep so the
    // script needs to walk back to the site root. We rely on the <base> or
    // on /search_index.json (served from root) — use absolute root path.
    return (window.MB_SITE_ROOT || '/') + 'search_index.json';
  }

  function ensureIndex() {
    if (index) return Promise.resolve(index);
    if (fetchPromise) return fetchPromise;
    fetchPromise = fetch(searchIndexUrl())
      .then(function (r) {
        if (!r.ok) throw new Error('search index HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        index = Array.isArray(data) ? data : (data.records || []);
        return index;
      })
      .catch(function () {
        fetchPromise = null;
        index = [];
        return index;
      });
    return fetchPromise;
  }

  function scoreRecord(rec, terms) {
    var haystack = (
      (rec.headline || '') + ' ' +
      (rec.summary || '') + ' ' +
      (rec.original_headline || '') + ' ' +
      (rec.source_name || '')
    ).toLowerCase();
    var matches = 0;
    for (var i = 0; i < terms.length; i++) {
      var t = terms[i];
      if (!t) continue;
      var idx = haystack.indexOf(t);
      while (idx !== -1) {
        matches++;
        idx = haystack.indexOf(t, idx + t.length);
      }
    }
    if (!matches) return 0;
    var recency = 0;
    if (rec.date) {
      var d = new Date(rec.date);
      var days = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24);
      recency = Math.max(0, 30 - days / 12);  // ~0 after 1 year.
    }
    return matches * 10 + recency;
  }

  function highlight(text, terms) {
    if (!text) return '';
    var out = text;
    terms.forEach(function (t) {
      if (!t) return;
      var re = new RegExp('(' + t.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&') + ')', 'ig');
      out = out.replace(re, '<mark>$1</mark>');
    });
    return out;
  }

  function render(hits, terms) {
    if (!hits.length) {
      results.innerHTML = '<li><em>결과 없음</em></li>';
      results.hidden = false;
      return;
    }
    results.innerHTML = hits.slice(0, 20).map(function (h) {
      var href = h.url || '#';
      return '<li><a href="' + href + '">' +
        '<strong>' + highlight(h.headline || '', terms) + '</strong>' +
        ' <small>' + (h.date || '') + ' · ' + (h.tab || '') + '</small>' +
        '</a></li>';
    }).join('');
    results.hidden = false;
  }

  var debounceTimer = null;
  input.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    var query = input.value.trim().toLowerCase();
    if (!query) {
      results.hidden = true;
      results.innerHTML = '';
      return;
    }
    debounceTimer = setTimeout(function () {
      ensureIndex().then(function (records) {
        var terms = query.split(/\s+/).filter(Boolean);
        var scored = [];
        for (var i = 0; i < records.length; i++) {
          var s = scoreRecord(records[i], terms);
          if (s > 0) scored.push({ rec: records[i], score: s });
        }
        scored.sort(function (a, b) { return b.score - a.score; });
        render(scored.map(function (x) { return x.rec; }), terms);
      });
    }, 120);
  });

  input.addEventListener('blur', function () {
    // Small delay so click-on-result still fires before we hide the list.
    setTimeout(function () { results.hidden = true; }, 150);
  });
})();
