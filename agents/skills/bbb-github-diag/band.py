#!/usr/bin/env python3
"""Insert a horizontal band of free space: everything at or below a line y moves down by d px, the way a row is inserted in a grid.

usage: band.py IN.svg OUT.svg --at Y --by D        (OUT may be IN)
       band.py IN.svg --free LO HI                 print the first y in [LO, HI) where a band can go, or nothing

What moves, for every y >= Y (the rest stays):
  - a box group and its pop-up, as one piece, when the box's top is at or below Y;
  - a frame whose top is at or below Y; a frame that crosses Y grows by d (its bottom moves);
  - every point of an arrow at or below Y (a vertical stretch that crosses Y gets longer; arrows stay valid);
  - labels, jump arcs, crosses, legend and header lines at or below Y; the canvas grows by d.
A band may not cross a box, a label or a jump arc (they would be cut): insert() refuses such a Y, and free_y() finds a Y that crosses
none. Used by svg_state.py when a box must grow and has no room below it: the band goes just under the box, so nothing else changes
shape. Script blocks are never touched.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GROUP = re.compile(r'<g id="(n|pop)(\d+)"')
RECT = re.compile(r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)"')
PAGE = re.compile(r'<rect x="0" y="0" width="[\d.]+" height="[\d.]+" fill="#[0-9a-f]{6}"/>')   # the page background: the canvas itself


def _is_page(ln, svg_h):
    """The background rect that fills the canvas: it is never cut, it grows with the canvas."""
    r = RECT.search(ln)
    return bool(PAGE.match(ln.strip())) and r is not None and abs(float(r.group(4)) - svg_h) < 1


def _svg_h(lines):
    m = next((re.search(r'\bheight="([\d.]+)"', l) for l in lines if l.startswith('<svg ')), None)
    return float(m.group(1)) if m else -1.0


def fmt(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def _shift(line, y0, d):
    """Every y coordinate of one line at or below y0, moved by d: y, y1, y2 attributes, x,y points of a path, a rotate centre."""
    f = lambda v: fmt(float(v) + d) if float(v) >= y0 else v
    line = re.sub(r'\b(y|y1|y2)="(-?[\d.]+)"', lambda m: '%s="%s"' % (m.group(1), f(m.group(2))), line)
    line = re.sub(r'\b(d|points)="([^"]*)"', lambda m: '%s="%s"' % (m.group(1), re.sub(
        r'(-?[\d.]+),(-?[\d.]+)', lambda k: '%s,%s' % (k.group(1), f(k.group(2))), m.group(2))), line)
    line = re.sub(r'rotate\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)', lambda m: 'rotate(%s %s %s)' % (m.group(1), m.group(2), f(m.group(3))), line)
    return line


def _parse(lines):
    """(groups, script): groups {('n'|'pop', num): (first line, last line, top, bottom)}; script: the line indexes inside <script>."""
    groups, script, i, inside = {}, set(), 0, False
    while i < len(lines):
        ln = lines[i]
        if '<script' in ln:
            inside = True
        if inside:
            script.add(i)
            if '</script>' in ln:
                inside = False
            i += 1
            continue
        m = GROUP.match(ln)
        if m:
            depth, j = 0, i
            while True:
                depth += len(re.findall(r'<g[ >]', lines[j])) - lines[j].count('</g>')
                if depth <= 0:
                    break
                j += 1
            r = next((RECT.search(lines[k]) for k in range(i, j + 1) if RECT.search(lines[k])), None)
            top, h = (float(r.group(2)), float(r.group(4))) if r else (0.0, 0.0)
            groups[(m.group(1), int(m.group(2)))] = (i, j, top, top + h)
            i = j + 1
            continue
        i += 1
    return groups, script


def blockers(svg, y):
    """What a band at y would cut: boxes and labels that cross it, and jump arcs that straddle it. [] when y is free."""
    lines = svg.split('\n')
    groups, script = _parse(lines)
    inside = {k for (kind, n), (a, b, _, _) in groups.items() for k in range(a, b + 1)}
    cut = ['box #%d' % n for (kind, n), (_, _, t, bt) in groups.items() if kind == 'n' and t < y < bt]
    svg_h = _svg_h(lines)
    for i, ln in enumerate(lines):
        if i in inside or i in script or _is_page(ln, svg_h):
            continue
        r = RECT.search(ln)
        if r and 'rx="18"' not in ln and float(r.group(2)) < y < float(r.group(2)) + float(r.group(4)):
            cut.append(('label at y %s' if 'fill="#fffdf7"' in ln else 'legend or other block at y %s') % r.group(2))   # only a frame stretches
        for p, q in re.findall(r'(-?[\d.]+) A[\d. ]+ (?:-?[\d.]+),(-?[\d.]+)', ln):
            if min(float(p), float(q)) < y < max(float(p), float(q)):
                cut.append('jump arc near y %s' % p)
    return cut


def free_y(svg, lo, hi):
    """The first y in [lo, hi) where a band cuts nothing (whole pixels and halves), or None."""
    y = float(int(lo))
    while y < hi:
        if y >= lo and not blockers(svg, y):
            return y
        y += 0.5
    return None


def insert(svg, y, d):
    """The diagram with a band of d px at y (see the module text). Raises ValueError when the band would cut something."""
    cut = blockers(svg, y)
    if cut:
        raise ValueError('a band at y %s would cut: %s' % (fmt(y), ', '.join(cut[:6])))
    lines = svg.split('\n')
    groups, script = _parse(lines)
    moving = {n for (kind, n), (_, _, t, _) in groups.items() if kind == 'n' and t >= y}
    owner = {}
    for (kind, n), (a, b, t, _) in groups.items():
        for k in range(a, b + 1):
            owner[k] = (kind, n)
    svg_h = _svg_h(lines)
    for i, ln in enumerate(lines):
        if i in script:
            continue
        if _is_page(ln, svg_h):                                  # the page background grows with the canvas
            lines[i] = re.sub(r'height="([\d.]+)"', lambda m: 'height="%s"' % fmt(float(m.group(1)) + d), ln, count=1)
            continue
        if i in owner:                                           # a box and its pop-up move as one piece, or not at all
            if owner[i][1] in moving:
                lines[i] = _shift(ln, -1e18, d)
            continue
        r = RECT.search(ln)
        if r and 'rx="18"' in ln and float(r.group(2)) < y < float(r.group(2)) + float(r.group(4)):
            lines[i] = ln.replace('height="%s"' % r.group(4), 'height="%s"' % fmt(float(r.group(4)) + d), 1)   # a frame across Y grows
            continue
        if ln.startswith('<svg '):
            ln = re.sub(r'\bheight="([\d.]+)"', lambda m: 'height="%s"' % fmt(float(m.group(1)) + d), ln, count=1)
            lines[i] = re.sub(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"',
                              lambda m: 'viewBox="%s %s %s %s"' % (m.group(1), m.group(2), m.group(3), fmt(float(m.group(4)) + d)), ln)
            continue
        lines[i] = _shift(ln, y, d)
    import model                                                 # a stretched straight arrow: its label goes back to the middle
    return model.relabel('\n'.join(lines))[0]


def main():
    a = sys.argv[1:]
    if len(a) == 4 and a[1] == '--free':
        y = free_y(open(a[0], encoding='utf-8').read(), float(a[2]), float(a[3]))
        if y is not None:
            print(fmt(y))
        return
    if len(a) != 6 or a[2] != '--at' or a[4] != '--by':
        sys.exit(__doc__)
    svg = open(a[0], encoding='utf-8').read()
    try:
        out = insert(svg, float(a[3]), float(a[5]))
    except ValueError as e:
        sys.exit(str(e))
    open(a[1], 'w', encoding='utf-8').write(out)
    print('band of %spx at y %s' % (a[5], a[3]))


if __name__ == '__main__':
    main()
