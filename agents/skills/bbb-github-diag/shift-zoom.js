/* Shift + scroll zoom for the lineage diagram. Runs after find-box.js, which has put the drawing (an inner <svg>) in a scrollable
   container. Hold Shift and turn the mouse wheel, or scroll up or down on a trackpad: the drawing grows or shrinks around the pointer.
   It changes only the size of the inner <svg>; the browser zoom and find-box.js's handling of it are left alone.
   A small hint, at the top-left right under the page header (where the header ends when the page opens), says so and shows the scale,
   counted from the size the page opens at (that is 100%); a click on it goes back to it. It keeps the same size on screen when the
   browser zoom changes, like the find box (it reads window.lineageZoom()). */
(function () {
  var HTMLNS = 'http://www.w3.org/1999/xhtml';
  var inner = document.querySelector('svg svg');
  if (!inner || !inner.parentNode || inner.parentNode.namespaceURI !== HTMLNS) return;    /* no find box host: nothing to zoom in */
  var scroller = inner.parentNode, host = scroller.parentNode;
  var vb = (inner.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  if (vb.length !== 4 || !vb[2]) return;
  var VW = vb[2], VH = vb[3];
  var start = (+inner.getAttribute('width') || VW) / VW, s = start;
  var MIN = 0.1, MAX = 3;

  var hint = document.createElementNS(HTMLNS, 'div');
  hint.setAttribute('style', 'position:absolute;left:16px;top:16px;z-index:10;padding:5px 10px;border-radius:8px;' +
    'background:rgba(22,62,115,.55);color:#fff;font:12px Helvetica,Arial,sans-serif;cursor:pointer;user-select:none;' +
    'opacity:.75;transition:opacity .2s;white-space:nowrap');
  hint.title = 'Click: back to the start scale';
  host.appendChild(hint);
  hint.addEventListener('mouseenter', function () { hint.style.opacity = '1'; });
  hint.addEventListener('mouseleave', function () { hint.style.opacity = '.75'; });
  function label() { hint.textContent = 'Shift + scroll to zoom · ' + Math.round(s / start * 100) + '%'; }   /* the start size is 100% */
  label();

  function zoomTo(ns, px, py) {            /* px, py: the point of the window that stays put (pointer), in the scroller's pixels */
    ns = Math.min(MAX, Math.max(MIN, ns));
    if (Math.abs(ns - s) < 1e-4) return;
    var cx = (scroller.scrollLeft + px) / s, cy = (scroller.scrollTop + py) / s;     /* the drawing point under it */
    s = ns;
    inner.setAttribute('width', VW * s); inner.setAttribute('height', VH * s);
    scroller.scrollLeft = cx * s - px; scroller.scrollTop = cy * s - py;
    label();
  }
  scroller.addEventListener('wheel', function (e) {
    if (!e.shiftKey) return;
    e.preventDefault();
    /* With Shift held, most browsers turn a vertical scroll into a horizontal one (deltaX): take whichever moved. */
    var d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (e.deltaMode === 1) d *= 16; else if (e.deltaMode === 2) d *= 400;
    var r = scroller.getBoundingClientRect();
    zoomTo(s * Math.exp(-d * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  hint.addEventListener('click', function () {
    var r = scroller.getBoundingClientRect();
    zoomTo(start, r.width / 2, r.height / 2);
  });

  /* Where it sits: under the last line of the page header (the h1 and h2 lines), at the header's left edge, as the page opens. It stays
     there while the drawing scrolls or zooms, like the find box. */
  var at = [16, 16];
  (function () {
    var hs = [].slice.call(inner.querySelectorAll('text.h1, text.h2'));
    if (!hs.length) return;
    var hr = host.getBoundingClientRect(), left = 1e9, bottom = 0;
    hs.forEach(function (t) { var r = t.getBoundingClientRect(); left = Math.min(left, r.left - hr.left); bottom = Math.max(bottom, r.bottom - hr.top); });
    at = [Math.max(8, left), bottom + 10];
  })();
  var z0 = 0;                              /* keep the hint the same size on screen under the browser zoom, like the find box */
  function keep() {
    var z = window.lineageZoom ? (window.lineageZoom().zoom || 1) : 1;
    if (Math.abs(z - z0) < 0.005) return;
    z0 = z;
    hint.style.transformOrigin = 'left top';
    hint.style.transform = 'scale(' + (1 / z) + ')';
    hint.style.left = at[0] + 'px'; hint.style.top = at[1] + 'px';
  }
  keep();
  setInterval(keep, 300);
  window.lineageShiftZoom = { scale: function () { return s; }, zoomTo: zoomTo };
})();
