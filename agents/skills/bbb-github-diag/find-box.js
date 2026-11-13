/* Find box for the lineage diagram: type a number (120, #120) to jump to that issue or pull request,
   or any text (a username, a title word, merged) to light up every matching box.
   Query: words separated by spaces must all be in the box (AND); `&&` is the same AND; `||` is OR and binds looser
   (a b || c && !d  =  (a AND b) OR (c AND NOT d)); `!word` (or `! word`) is NOT. No parentheses. `#123` in an expression is
   box number 123 exactly; a query of digits alone is a number (exact, else the numbers that start with it).
   The `regex` box: the query is one JavaScript regular expression (case-insensitive), at the reader's risk.
   A box's text is, in document order: the first line (tag, number, assignee or author), pill word, title, date line, notes (no hover
   tooltips, no label mark); then
   its pop-up's text (a collapsed box); then `label:NAME` for each GitHub label in its data-github attribute (never drawn). */
(function () {
  var SVGNS = 'http://www.w3.org/2000/svg', HTMLNS = 'http://www.w3.org/1999/xhtml';
  var svg = document.documentElement;
  function labelsOf(g) {   /* the GitHub labels refresh_meta.py stores on the box: searchable, not drawn */
    try { return (JSON.parse(g.getAttribute('data-github') || '{}').labels || []).map(function (l) { return ' label:' + l; }).join(''); }
    catch (e) { return ''; }
  }
  function textOf(g) {      /* the text drawn in the box, its parts apart: no <title> (a link's tooltip holds the linked item's title)
                               and no label mark (its label is in labelsOf) */
    if (!g) return '';
    var c = g.cloneNode(true);
    [].slice.call(c.querySelectorAll('title, .mark')).forEach(function (n) { n.parentNode.removeChild(n); });
    return [].slice.call(c.childNodes).map(function (n) { return n.textContent || ''; }).join(' ');
  }
  var info = [].slice.call(document.querySelectorAll('g[id]')).filter(function (g) { return /^n\d+$/.test(g.id); })
    .map(function (g) {
      var raw = (textOf(g) + ' ' + textOf(document.getElementById('pop' + g.id.slice(1))) + labelsOf(g)).replace(/\s+/g, ' ').trim();
      return { g: g, num: g.id.slice(1), raw: raw, text: raw.toLowerCase() };   /* a collapsed box is also searched by the text of its pop-up */
    });
  if (!info.length) return;

  var css = document.createElementNS(SVGNS, 'style');
  css.textContent =
    '.q-on g[id^="n"]{opacity:.2;transition:opacity .15s}' +
    '.q-on g[id^="n"].hit{opacity:1;filter:drop-shadow(0 0 7px #ff7a00)}' +
    '.q-on g[id^="n"].hit>rect:first-child{stroke:#ff7a00;stroke-width:5}' +
    '.q-on g[id^="n"].cur>rect:first-child{stroke:#e6007a;stroke-width:6}' +
    '.q-on path[marker-end]{opacity:.35}' +
    '.q-on path[marker-end].q-arr{opacity:1;stroke-width:3px}' +        /* an arrow that starts or ends on a match */
    '.q-on g[id^="n"].nb{opacity:.75}';                                 /* the box at its other end: seen, but not a match */
  svg.insertBefore(css, svg.firstChild);

  /* Host: move the drawing into a scrollable HTML container that fills the window, and put the find box
     OUTSIDE the scrolling area, so it stays at the bottom-left whatever is scrolled, focused or zoomed. */
  var W = 330;
  var inner = document.createElementNS(SVGNS, 'svg');
  ['width', 'height', 'viewBox', 'font-family'].forEach(function (a) { if (svg.hasAttribute(a)) inner.setAttribute(a, svg.getAttribute(a)); });
  /* The drawing opens at 65% of its drawn size (data-scale on the root <svg> overrides it): at 100% a box fills too much of the
     window and its text reads large. That start size is the reader's 100% (shift-zoom.js counts from it). The browser zoom still
     works on top of it. */
  var SCALE = parseFloat(svg.getAttribute('data-scale')) || 0.65, W0 = svg.getAttribute('width'), H0 = svg.getAttribute('height');
  if (W0 && H0 && svg.hasAttribute('viewBox')) { inner.setAttribute('width', +W0 * SCALE); inner.setAttribute('height', +H0 * SCALE); }
  inner.setAttribute('style', 'display:block');
  [].slice.call(svg.childNodes).forEach(function (n) {
    if (n.nodeType === 1 && (n.localName === 'script' || n === css)) return;
    inner.appendChild(n);
  });
  svg.removeAttribute('viewBox'); svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
  var fo = document.createElementNS(SVGNS, 'foreignObject');
  fo.setAttribute('x', 0); fo.setAttribute('y', 0); fo.setAttribute('width', '100%'); fo.setAttribute('height', '100%');
  var host = document.createElementNS(HTMLNS, 'div');
  var page = inner.querySelector('rect[x="0"][y="0"]');          /* the page colour, read from the drawing: never out of step */
  var bg = (page && /^#[0-9a-fA-F]{6}$/.test(page.getAttribute('fill') || '')) ? page.getAttribute('fill') : '#f3f0e8';
  host.setAttribute('style', 'position:relative;width:100%;height:100%;overflow:hidden;background:' + bg);
  var scroller = document.createElementNS(HTMLNS, 'div');
  scroller.setAttribute('style', 'position:absolute;left:0;top:0;right:0;bottom:0;overflow:auto');
  scroller.appendChild(inner); host.appendChild(scroller);

  var box = document.createElementNS(HTMLNS, 'div');
  box.setAttribute('style', 'position:absolute;left:12px;bottom:30px;z-index:10;box-sizing:border-box;width:' + W + 'px;padding:8px 10px;background:rgba(22,62,115,.55);border:2px solid rgba(14,43,82,.55);border-radius:10px;box-shadow:0 3px 12px rgba(14,43,82,.25);font:12px Helvetica,Arial,sans-serif;color:#fff;opacity:.75;transition:opacity .2s');
  /* Half transparent like the Shift + scroll hint (shift-zoom.js): background at 55%, the whole box at 75%; full while the pointer is
     on it or the field has the focus, so typing is never faint. */
  var row = document.createElementNS(HTMLNS, 'div');
  row.setAttribute('style', 'display:flex;gap:6px;align-items:center');
  var input = document.createElementNS(HTMLNS, 'input');
  input.setAttribute('type', 'text');
  input.setAttribute('placeholder', 'number or name');
  input.setAttribute('style', 'flex:1;min-width:0;font:13px Helvetica,Arial,sans-serif;padding:4px 8px;border:1px solid #0e2b52;border-radius:6px;background:#fff;color:#1c2430');
  function btn(label, title) {
    var b = document.createElementNS(HTMLNS, 'button');
    b.textContent = label; b.setAttribute('title', title);
    b.setAttribute('style', 'font:12px Helvetica,Arial,sans-serif;padding:3px 7px;border:1px solid #6f93c4;border-radius:6px;background:#1d4e89;color:#fff;cursor:pointer');
    return b;
  }
  var prev = btn('◀', 'previous match (Shift+Enter)'), next = btn('▶', 'next match (Enter)'), clear = btn('✕', 'clear (Esc)');
  var row2 = document.createElementNS(HTMLNS, 'div');
  row2.setAttribute('style', 'display:flex;justify-content:space-between;align-items:center;margin-top:11px;font-size:11px;color:#cfe0f5');   /* 4px + half a 13px row */
  var note = document.createElementNS(HTMLNS, 'div');
  note.setAttribute('style', 'min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap');
  note.textContent = 'press / to search';
  var reLabel = document.createElementNS(HTMLNS, 'label');
  reLabel.setAttribute('style', 'display:flex;align-items:center;gap:3px;cursor:pointer;flex:none;margin-left:8px');
  reLabel.setAttribute('title', 'the query is one regular expression (case-insensitive); Esc twice turns it off');
  var reBox = document.createElementNS(HTMLNS, 'input');
  reBox.setAttribute('type', 'checkbox');
  reBox.setAttribute('style', 'margin:0;cursor:pointer');
  reLabel.appendChild(reBox); reLabel.appendChild(document.createTextNode('regex'));
  row2.appendChild(note); row2.appendChild(reLabel);
  row.appendChild(input); row.appendChild(prev); row.appendChild(next); row.appendChild(clear);
  box.appendChild(row); box.appendChild(row2); host.appendChild(box);
  var hover = false;
  function shade() { box.style.opacity = (hover || document.activeElement === input) ? '1' : '.75'; }
  box.addEventListener('mouseenter', function () { hover = true; shade(); });
  box.addEventListener('mouseleave', function () { hover = false; shade(); });
  input.addEventListener('focus', shade); input.addEventListener('blur', shade);
  fo.appendChild(host); svg.appendChild(fo);
  svg.style.overflow = 'hidden';
  /* Size everything in explicit pixels from the window size. Percentages are not re-resolved by every browser
     after the window or the zoom changes, which left part of the screen undrawn. */
  function fit() {
    if (typeof settle === 'function') settle();
    var w = Math.max(1, window.innerWidth), h = Math.max(1, window.innerHeight);
    svg.setAttribute('width', w); svg.setAttribute('height', h);
    fo.setAttribute('width', w); fo.setAttribute('height', h);
    host.style.width = w + 'px'; host.style.height = h + 'px';
    comp();
  }
  /* Keep the find box about the same size on screen when the browser zoom changes. The zoom is read as the
     absolute zoom (devicePixelRatio over the native ratio, found below). The box is
     scaled by the inverse, from its bottom-left corner, and its offsets are scaled with it. */
  /* A reload keeps the zoom the page had, so the zoom at load is not 1 and cannot be read from the change since
     load. The absolute zoom is devicePixelRatio / nativeDpr, where nativeDpr is the ratio at 100% (1 on a plain
     screen, 2 on a retina one, 1.25, 1.5 ... with a Windows scale). nativeDpr is chosen among those values: the one
     whose implied zoom is closest to outerWidth/innerWidth (outerWidth does not scale with the page zoom in Chrome
     and Safari, innerWidth does). A docked devtools panel or a sidebar spoils the ratio, so the match must be
     within 20%, else the page is taken to be at 100% at load. */
  /* The outerWidth/innerWidth ratio is only trustworthy when no side panel (docked devtools, a browser sidebar)
     eats part of the window. So the result is used in three steps:
     1. a CONFIDENT match (ratio within 4% of a candidate and the zoom a standard browser zoom step) is saved in
        localStorage for this screen (key: screen size, which does not change with the page zoom) and used;
     2. otherwise the value saved earlier for this screen is used (this is what keeps the box right on a reload at
        20% or 300% with a panel open);
     3. otherwise the old guess (best match within 20%, else the page is taken to be at 100% at load).
     Safari does not change devicePixelRatio with the page zoom, so there the zoom is read from the ratio itself. */
  var STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5];
  function nearStep(z) { return STEPS.some(function (s) { return Math.abs(z / s - 1) < 0.03; }); }
  var calKey = 'lineageFindBox:' + (/Firefox\//.test(navigator.userAgent || '') ? 'ff2:' : '') + window.screen.width + 'x' + window.screen.height;
  function loadCal() { try { var v = parseFloat(window.localStorage.getItem(calKey)); return v > 0 ? v : 0; } catch (e) { return 0; } }
  function saveCal(n) { try { window.localStorage.setItem(calKey, String(n)); } catch (e) { } }
  var ua = navigator.userAgent || '';
  var safari = /Safari\//.test(ua) && !/Chrome\/|Chromium\/|Edg\/|OPR\/|Firefox\//.test(ua);
  var calSource = 'none';
  var firefox = /Firefox\//.test(ua);
  /* Firefox: outerWidth is scaled by the page zoom like innerWidth, so outerWidth/innerWidth is always about 1 and says
     nothing about the zoom (using it made the box jump at some zoom levels). What Firefox does give is
     devicePixelRatio = native ratio x zoom, and the zoom is always one of its fixed steps. So the native ratio is a value
     (1, 1.25, 1.5, 2, 2.5, 3) for which the implied zoom is such a step. Several values often fit (at ratio 2: 100% on a
     retina screen, 200% on a plain one), so: keep the value already chosen while it still fits (the ratio never changes
     within a page); else take the only one that fits (saved for this screen); else the one saved for this screen; else a
     Mac is taken as retina (2). A value saved by the first Firefox version of this code used another key and is ignored. */
  /* No step list: the zoom is devicePixelRatio / native for any value (43%, 79%, 134%). Firefox rounds the ratio to 60/N, so
     at very high zoom (3x and up) the box can be off by a few percent; below that the error is under 2%. */
  function ffOk(d, n) { var z = d / n; return z >= 0.25 && z <= 5.5; }
  function ffNative() {
    var d = window.devicePixelRatio || 1;
    var prev = (typeof ndpr === 'number') ? ndpr : 0;
    if (prev) return prev;   /* the ratio never changes within a page: keep it at any zoom, no range check */
    /* Firefox reads no saved value: screen.width (the key) changes with the zoom, so old entries were wrong ones. */
    var mac = /Mac/.test(navigator.platform || ua);
    var pick = [mac ? 2 : 1, 1, 2, 1.5, 1.25, 2.5, 3].filter(function (n) { return ffOk(d, n); })[0];
    if (pick) { calSource = 'prior'; return pick; }
    calSource = 'guess';
    return d;
  }
  function nativeDpr() {
    if (firefox) return ffNative();
    var d = window.devicePixelRatio || 1, r = window.outerWidth / window.innerWidth, best = d, bd = 0.2;
    var ok = isFinite(r) && r > 0 && window.innerWidth >= 200;
    if (ok) [1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 3, 4].forEach(function (n) {
      var e = Math.abs(Math.log((d / n) / r));
      if (e < bd) { bd = e; best = n; }
    });
    if (ok && bd < 0.04 && nearStep(d / best)) { saveCal(best); calSource = 'measured'; return best; }
    var cal = loadCal();
    if (cal) { calSource = 'saved'; return cal; }   /* saved from a strict measurement on this screen: trusted at any zoom */
    calSource = 'guess';
    return ok && bd < 0.2 ? best : d;
  }
  var ndpr = nativeDpr(), zoomNow = 1;
  /* While the page loads, innerWidth and outerWidth may not be settled yet, so the first reading can be a guess. Read it
     again when the page has loaded and a little later; a strict match then replaces the guess and is saved. */
  function settle() {
    var prev = calSource, keep = ndpr, n = nativeDpr();
    if (calSource === 'guess' && prev !== 'guess') { ndpr = keep; calSource = prev; } else ndpr = n;   /* a later guess never replaces a measured or saved value */
  }
  window.addEventListener('load', settle);
  setTimeout(settle, 700); setTimeout(settle, 2500);
  function zoomRead() {
    if (safari) {
      var r = window.outerWidth / window.innerWidth;
      if (isFinite(r) && r > 0 && window.innerWidth >= 200) {
        var s = STEPS.filter(function (x) { return Math.abs(r / x - 1) < 0.05; })[0];
        return s || r;
      }
      return 1;
    }
    var raw = (window.devicePixelRatio || 1) / ndpr;
    return raw;
  }
  function comp() {
    var z = zoomRead();
    z = Math.min(5, Math.max(0.1, z));
    if (Math.abs(z - zoomNow) < 0.005) return;
    zoomNow = z;
    box.style.transformOrigin = 'left bottom';
    box.style.transform = 'scale(' + (1 / z) + ')';
    box.style.left = (12 / z) + 'px'; box.style.bottom = (30 / z) + 'px';
  }
  window.lineageZoom = function () { return { dpr: window.devicePixelRatio, outer: window.outerWidth, inner: window.innerWidth, native: ndpr, source: calSource, safari: safari, firefox: firefox, screen: window.screen.width + 'x' + window.screen.height, zoom: zoomNow, scale: box.style.transform, left: box.style.left, bottom: box.style.bottom, boxPx: Math.round(box.getBoundingClientRect().width), boxScreenPx: Math.round(box.getBoundingClientRect().width * (window.devicePixelRatio || 1) / (ndpr || 1)) }; };
  fit();
  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', fit);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', fit);
  setInterval(function () {   /* safety net for a zoom that fires no resize event */
    comp();
    if (+fo.getAttribute('width') !== Math.max(1, window.innerWidth) || +fo.getAttribute('height') !== Math.max(1, window.innerHeight)) fit();
  }, 300);
  if (window.innerWidth < 50 || window.innerHeight < 50 || !scroller.clientWidth || !scroller.clientHeight) {      /* no real window (for example a thumbnail): keep the plain picture */
    while (inner.firstChild) svg.insertBefore(inner.firstChild, fo);
    svg.removeChild(fo);
    ['width', 'height', 'viewBox'].forEach(function (a) { if (inner.hasAttribute(a)) svg.setAttribute(a, inner.getAttribute(a)); });
    if (W0 && H0) { svg.setAttribute('width', W0); svg.setAttribute('height', H0); }     /* the plain picture keeps its drawn size */
    return;
  }

  var hits = [], cur = 0;
  var arrowEls = [].slice.call(svg.querySelectorAll('path[marker-end][data-from][data-to]'));
  /* Every arrow that starts or ends on a match is marked, and the box at its other end loses most of its fade. click-highlight.js,
     when the file has it, also lights those arrows its own way (halo, glowing label); it loads after this script, so it is looked up
     at search time. */
  function lightArrows(list) {
    var set = {};
    list.forEach(function (i) { set[i.num] = 1; });
    arrowEls.forEach(function (p) {
      var f = p.getAttribute('data-from'), t = p.getAttribute('data-to');
      if (!set[f] && !set[t]) return;
      p.classList.add('q-arr');
      [f, t].forEach(function (n) { var g = set[n] ? null : document.getElementById('n' + n); if (g) g.classList.add('nb'); });
    });
    if (window.lineageHighlight && window.lineageHighlight.boxes) window.lineageHighlight.boxes(Object.keys(set));
  }
  function reset() {
    svg.classList.remove('q-on');
    info.forEach(function (i) { i.g.classList.remove('hit'); i.g.classList.remove('cur'); i.g.classList.remove('nb'); });
    arrowEls.forEach(function (p) { p.classList.remove('q-arr'); });
    if (hits.length && window.lineageHighlight) window.lineageHighlight.clear();   /* only the arrows a search lit; a click's stay */
    hits = []; cur = 0;
  }
  /* The query as OR terms, each a list of AND factors {t, neg, num}. Empty pieces (a half-typed `a ||`, a lone `!`) are dropped. */
  function parse(q) {
    return q.toLowerCase().split('||').map(function (term) {
      var out = [], neg = false;
      term.split('&&').join(' ').split(/\s+/).forEach(function (w) {
        while (w.charAt(0) === '!') { neg = !neg; w = w.slice(1); }
        if (!w) return;                                           /* `! word`: the NOT waits for the next word */
        var num = /^#\d+$/.test(w);
        out.push({ t: num ? w.slice(1) : w, neg: neg, num: num });
        neg = false;
      });
      return out;
    }).filter(function (f) { return f.length; });
  }
  /* null: nothing to search (empty, or only operators); {bad: message}: a regex that does not compile; else the matching boxes. */
  function find(q) {
    if (reBox.checked) {
      if (!q.trim()) return null;
      var rx;
      try { rx = new RegExp(q, 'i'); } catch (e) { return { bad: e.message }; }
      return info.filter(function (i) { return rx.test(i.raw); });
    }
    var d = q.trim().toLowerCase().replace(/^#/, '');
    if (/^\d+$/.test(d)) {
      var exact = info.filter(function (i) { return i.num === d; });
      return exact.length ? exact : info.filter(function (i) { return i.num.indexOf(d) === 0; });
    }
    var terms = parse(q);
    if (!terms.length) return null;
    return info.filter(function (i) {
      return terms.some(function (fs) {
        return fs.every(function (f) { return (f.num ? i.num === f.t : i.text.indexOf(f.t) >= 0) !== f.neg; });
      });
    });
  }
  function show(jump) {
    info.forEach(function (i) { i.g.classList.remove('cur'); });
    if (!hits.length) return;
    hits[cur].g.classList.add('cur');
    note.textContent = hits.length + (hits.length === 1 ? ' match: #' : ' matches, showing #') + hits[cur].num + (hits.length > 1 ? ' (' + (cur + 1) + '/' + hits.length + ')' : '');
    if (jump) {
      var r = hits[cur].g.getBoundingClientRect(), sr = scroller.getBoundingClientRect();
      scroller.scrollTo({ left: Math.max(0, scroller.scrollLeft + (r.left - sr.left) + r.width / 2 - scroller.clientWidth / 2),
                          top: Math.max(0, scroller.scrollTop + (r.top - sr.top) + r.height / 2 - scroller.clientHeight / 2), behavior: jump === 'instant' ? 'auto' : 'smooth' });
    }
  }
  /* The field's colour tells the result: white when empty (spaces trimmed), pale green on a match, pale pink with a red border on
     none. Red border: the buttons' hsl(213,65%,33%) at hue 0. Green hsl(120,45%,86%) and pink hsl(350,45%,86%): equally strong. */
  function paint(state) {
    var c = { empty: ['#0e2b52', '#fff'], hit: ['#0e2b52', '#cdeccd'], miss: ['#8b1d1d', '#ebcbd0'] }[state];
    input.style.borderColor = c[0]; input.style.backgroundColor = c[1];
  }
  function run(q, jump) {
    reset();
    var r = find(q);
    hits = (r && !r.bad) ? r : [];
    paint(!r ? 'empty' : hits.length ? 'hit' : 'miss');
    if (!r) { note.textContent = reBox.checked ? 'regex: type a pattern' : 'press / to search'; return; }
    if (r.bad) { note.textContent = 'bad regex: ' + r.bad; note.title = r.bad; return; }
    if (!hits.length) { note.textContent = 'no match'; return; }
    svg.classList.add('q-on');
    hits.forEach(function (i) { i.g.classList.add('hit'); });
    lightArrows(hits);
    show(jump);
  }
  function step(d) { if (hits.length) { cur = (cur + d + hits.length) % hits.length; show(true); } }

  input.addEventListener('input', function () { run(input.value, true); });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
    else if (e.key === 'Escape') { escape(); }
    e.stopPropagation();
  });
  reBox.addEventListener('change', function () { run(input.value, true); });
  prev.addEventListener('click', function () { step(-1); });
  next.addEventListener('click', function () { step(1); });
  clear.addEventListener('click', function () { input.value = ''; run('', false); });
  function clearAll() { input.value = ''; run('', false); input.blur(); }   /* the regex box stays as it is */
  function escape() {                     /* Esc clears; a second Esc, on an empty field, also turns the regex box off */
    if (!input.value.trim() && reBox.checked) reBox.checked = false;
    clearAll();
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== input) { e.preventDefault(); input.focus(); }
    else if (e.key === 'Escape') { escape(); }
  });
  document.addEventListener('dblclick', function (e) {
    if (box.contains(e.target)) return;
    clearAll();
    if (window.getSelection) window.getSelection().removeAllRanges();
  });

  var h = decodeURIComponent((location.hash || '').replace(/^#(find=)?/, ''));
  if (h) { input.value = h; setTimeout(function () { run(h, 'instant'); }, 50); }
  window.lineageFind = function (q) { input.value = q; run(q, true); return hits.map(function (i) { return i.num; }); };
})();
