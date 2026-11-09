#!/usr/bin/env python3
"""The red crosses of closed work, drawn on top of the boxes, and the arrowheads every arrow needs.

usage: xmarks.py IN.svg OUT.svg        (OUT may be IN)
As a module: xmarks.redo(svg_text) -> svg_text. hops.add_hops() calls it, so every script that writes arrows gets it.

An SVG marker is painted with its path, and the arrows come before the boxes in the file, so a box hides the half of the cross that
lies on it. The cross belongs ON the closed box: it is the mark of what was closed by hand. So each cross is drawn again in its own
layer, `<g id="xmarks">`, right before the legend: after every box, before the pop-ups (a pop-up still covers it).
- an arrow whose head is the cross (`supersedes`: the head is on the closed pull request) gets a cross at its end;
- a `duplicate of` arrow runs from the closed issue to the one that stays: its head is an arrowhead on the one that stays, and the
  cross is at its start, on the closed issue.
The layer is rebuilt from the arrows each time, so a moved or removed arrow leaves no cross behind.
A file drawn before an arrow kind existed may lack its marker in <defs> (an arrow with no head at all): the missing ones are added
from draw.defs().
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

START = '<g id="xmarks">'
HALF = 5.5                     # the marker's cross: 11px diagonals, 3px red stroke (draw.defs, h-cross)
CROSS_AT_START = ('duplicate of',)


def _points(d):
    return [(float(x), float(y)) for x, y in re.findall(r'(-?[\d.]+),(-?[\d.]+)', d)]


def cross(x, y):
    return ('<path class="xmark" d="M%.1f,%.1f L%.1f,%.1f M%.1f,%.1f L%.1f,%.1f" stroke="#ff2a2a" stroke-width="3" stroke-linecap="round" '
            'fill="none"/>' % (x - HALF, y - HALF, x + HALF, y + HALF, x + HALF, y - HALF, x - HALF, y + HALF))


def ensure_markers(text):
    """Add to the first <defs> every arrow marker draw.defs() knows and the file does not define."""
    import draw
    have = set(re.findall(r'<marker id="([\w-]+)"', text))
    want = re.findall(r'(<marker id="([\w-]+)".*?</marker>)', draw.defs(), flags=re.S)
    add = [m for m, mid in want if mid not in have]
    if add and '<defs>' in text:
        i = text.index('<defs>') + len('<defs>')
        text = text[:i] + '\n' + '\n'.join(add) + text[i:]
    return text


def redo(text):
    text = ensure_markers(text)
    lines = [l for l in text.split('\n')]
    if START in lines:                               # the old layer goes
        a = lines.index(START)
        b = lines.index('</g>', a)
        del lines[a:b + 1]
    marks = []
    for ln in lines:
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = _points(ln.split('"')[1])
        if len(pts) < 2:
            continue
        kind = re.search(r'data-kind="([^"]*)"', ln)
        if 'url(#h-cross)' in ln:
            marks.append(cross(*pts[-1]))
        elif kind and kind.group(1) in CROSS_AT_START:
            marks.append(cross(*pts[0]))
    if marks:
        k = lines.index('<!--legend-->') if '<!--legend-->' in lines else len(lines) - 1
        lines[k:k] = [START] + marks + ['</g>']
    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    out = redo(open(sys.argv[1], encoding='utf-8').read())
    open(sys.argv[2], 'w', encoding='utf-8').write(out)
    print('crosses on top:', out.count('class="xmark"'))
