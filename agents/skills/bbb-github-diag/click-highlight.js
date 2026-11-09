/* Click highlight for the lineage diagram (experimental). Runs after find-box.js, which has moved the drawing into an inner <svg>.
   - Click an arrow or its label: that arrow lights up in its own colour (a halo under the line, a thicker line, a glowing label),
     and the two boxes it joins light up like matches of the find box. Nothing fades.
   - Click a box (or its open pop-up): the box, every arrow that starts or ends on it, and the box at the other end of each one light
     up; everything else fades. The box is marked like the current match of the find box, its neighbours like the other matches.
   - Escape, or a click on the background, clears it. A click on a link inside a box follows the link and changes nothing. */
(function () {
  var SVGNS = 'http://www.w3.org/2000/svg';
  var root = document.querySelector('svg svg') || document.documentElement;      /* the drawing (inner <svg> when the find box ran) */
  var arrows = [].slice.call(root.querySelectorAll('path[marker-end][data-from][data-to]'));
  if (!arrows.length) return;

  var css = document.createElementNS(SVGNS, 'style');
  css.textContent =
    '.c-halo{fill:none;stroke-opacity:0;stroke-width:12;stroke-linecap:round;stroke-linejoin:round;pointer-events:stroke;cursor:pointer}' +
    '.c-halo.c-on{stroke-opacity:.3}' +
    'path.c-arr{stroke-width:3.4px}' +
    '.c-lab{cursor:pointer}' +
    'rect.c-lab.c-on{stroke-width:2.4px}' +
    'text.c-lab.c-on{font-weight:800}' +
    'path[marker-end][data-from]{cursor:pointer}' +
    'g[id^="n"]{cursor:pointer}' +
    '.c-fade g[id^="n"]{opacity:.2;transition:opacity .15s}' +
    'g[id^="n"].c-hit{opacity:1;filter:drop-shadow(0 0 7px #ff7a00)}' +
    'g[id^="n"].c-hit>rect:first-child{stroke:#ff7a00;stroke-width:5}' +
    'g[id^="n"].c-cur>rect:first-child{stroke:#e6007a;stroke-width:6}' +
    '.c-fade path[marker-end]:not(.c-arr),.c-fade .c-lab:not(.c-on),.c-fade .xmark:not(.c-on){opacity:.15}';
  root.insertBefore(css, root.firstChild);

  function pts(d) {
    var out = [], re = /(-?[\d.]+),(-?[\d.]+)/g, m;
    while ((m = re.exec(d))) out.push([+m[1], +m[2]]);
    return out;
  }
  /* each arrow: its points, colour, a halo under it (also a wide, invisible target for the click) */
  var A = arrows.map(function (p) {
    var halo = document.createElementNS(SVGNS, 'path');
    halo.setAttribute('d', p.getAttribute('d'));
    halo.setAttribute('class', 'c-halo');
    halo.setAttribute('stroke', p.getAttribute('stroke') || '#000');
    p.parentNode.insertBefore(halo, p);
    var a = { p: p, halo: halo, pts: pts(p.getAttribute('d')), color: p.getAttribute('stroke') || '#000',
              from: p.getAttribute('data-from'), to: p.getAttribute('data-to'), kind: p.getAttribute('data-kind') || '', labs: [], xs: [] };
    halo.__arrow = a; p.__arrow = a;
    return a;
  });

  /* labels: a rect followed by one or more text.lbl. The file does not say which arrow a label belongs to, so it is the arrow whose
     straight stretch runs through the label's centre, of the label's colour (and word, when two qualify); else the nearest of its colour. */
  function onStretch(a, x, y, tol) {
    var best = 1e9;
    for (var i = 1; i < a.pts.length; i++) {
      var p = a.pts[i - 1], q = a.pts[i], d;
      if (Math.abs(p[1] - q[1]) < .5) d = Math.abs(y - p[1]) + Math.max(0, Math.min(p[0], q[0]) - x, x - Math.max(p[0], q[0]));
      else if (Math.abs(p[0] - q[0]) < .5) d = Math.abs(x - p[0]) + Math.max(0, Math.min(p[1], q[1]) - y, y - Math.max(p[1], q[1]));
      else continue;
      if (d < best) best = d;
    }
    return best <= tol ? best : 1e9;
  }
  [].slice.call(root.querySelectorAll('text.lbl')).forEach(function (t) {
    if (t.__lab) return;
    var r = t.previousElementSibling;
    while (r && r.localName === 'text') r = r.previousElementSibling;
    if (!r || r.localName !== 'rect') return;
    var texts = [], n = r.nextElementSibling;
    while (n && n.localName === 'text' && /\blbl\b/.test(n.getAttribute('class') || '')) { texts.push(n); n = n.nextElementSibling; }
    var x = +r.getAttribute('x') + +r.getAttribute('width') / 2, y = +r.getAttribute('y') + +r.getAttribute('height') / 2;
    var color = r.getAttribute('stroke'), word = texts.map(function (e) { return e.textContent; }).join(' ').replace(/\s+/g, ' ').trim();
    var pick = null, pd = 1e9;
    [2, 40].some(function (tol) {                                        /* on a stretch first; then the nearest within 40px */
      A.forEach(function (a) {
        if (a.color !== color) return;
        var d = onStretch(a, x, y, tol) + (a.kind === word ? 0 : .5);     /* the arrow of the label's word wins a tie */
        if (d < pd) { pd = d; pick = a; }
      });
      return pick;
    });
    var parts = [r].concat(texts);
    parts.forEach(function (e) { e.classList.add('c-lab'); e.__lab = pick; });
    if (pick) pick.labs = pick.labs.concat(parts);
  });

  /* red crosses (xmarks.py): one at the end of a supersedes arrow, one at the start of a duplicate-of arrow */
  [].slice.call(root.querySelectorAll('path.xmark')).forEach(function (x) {
    var c = pts(x.getAttribute('d'))[0], cx = c[0] + 5.5, cy = c[1] + 5.5;
    A.forEach(function (a) {
      [a.pts[0], a.pts[a.pts.length - 1]].forEach(function (e) { if (Math.abs(e[0] - cx) < 1.5 && Math.abs(e[1] - cy) < 1.5) a.xs.push(x); });
    });
  });

  var lit = [], litBoxes = [];
  function light(a) {
    a.halo.classList.add('c-on'); a.p.classList.add('c-arr');
    a.labs.forEach(function (e) {
      e.classList.add('c-on');
      if (e.localName === 'rect') e.style.filter = 'drop-shadow(0 0 4px ' + a.color + ')';
    });
    a.xs.forEach(function (x) { x.classList.add('c-on'); });
    lit.push(a);
  }
  function clear() {
    lit.forEach(function (a) {
      a.halo.classList.remove('c-on'); a.p.classList.remove('c-arr');
      a.labs.forEach(function (e) { e.classList.remove('c-on'); e.style.filter = ''; });
      a.xs.forEach(function (x) { x.classList.remove('c-on'); });
    });
    litBoxes.forEach(function (g) { g.classList.remove('c-hit'); g.classList.remove('c-cur'); });
    lit = []; litBoxes = [];
    root.classList.remove('c-fade');
  }
  function box(n) { return document.getElementById('n' + n); }
  function showArrow(a) {                                               /* the arrow and the two boxes it joins; nothing fades */
    clear(); light(a);
    [a.from, a.to].forEach(function (n) { var g = box(n); if (g && litBoxes.indexOf(g) < 0) { g.classList.add('c-hit'); litBoxes.push(g); } });
  }
  function showBox(n) {
    clear();
    var g = box(n);
    if (!g) return;
    root.classList.add('c-fade');
    g.classList.add('c-hit'); g.classList.add('c-cur'); litBoxes.push(g);
    A.forEach(function (a) {
      if (a.from !== n && a.to !== n) return;
      light(a);
      var o = box(a.from === n ? a.to : a.from);
      if (o && litBoxes.indexOf(o) < 0) { o.classList.add('c-hit'); litBoxes.push(o); }
    });
  }

  var input = document.querySelector('input');                         /* the find box: clicks in it are not clicks on the picture */
  var ui = input;
  while (ui && ui.parentNode && !ui.parentNode.contains(root)) ui = ui.parentNode;
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (ui && ui !== input && ui.contains(t)) return;
    if (t.closest && t.closest('a')) return;                            /* a link in a box: let it open */
    if (t.__arrow) { showArrow(t.__arrow); return; }
    if (t.__lab !== undefined) { if (t.__lab) showArrow(t.__lab); return; }
    var g = t.closest && t.closest('g[id]');
    while (g && !/^(n|pop)\d+$/.test(g.id)) g = g.parentNode && g.parentNode.closest ? g.parentNode.closest('g[id]') : null;
    if (g) { showBox(g.id.replace(/^(n|pop)/, '')); return; }
    clear();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') clear(); });
  window.lineageHighlight = { arrow: function (f, t) { var a = A.filter(function (x) { return x.from == f && x.to == t; })[0]; if (a) showArrow(a); return !!a; },
                              box: function (n) { showBox(String(n)); return litBoxes.map(function (g) { return g.id; }); },
                              clear: clear,
                              unlabeled: function () { return A.filter(function (a) { return !a.labs.length; }).map(function (a) { return a.from + '>' + a.to; }); } };
})();
