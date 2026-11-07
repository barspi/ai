#!/usr/bin/env python3
"""Measure one or more built diagrams the same way, to compare two layouts of the same graph.

usage: metrics.py A.svg [B.svg ...]

Per file it prints: canvas size and area; boxes; arrows; straight arrows (no bend); bends; total arrow length, and the length of the
important arrows (draw.IMPORTANCE tier 3); jump arcs (crossings); frame area (sum of frame rectangles); box fill (box area / frame
area, higher is denser). All deterministic, read from the SVG only. Run check_diag.py for faults and NO PATH comes from build.py.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draw, model

def measure(path):
    text = open(path, encoding='utf-8').read()
    W, H = (int(float(v)) for v in re.search(r'<svg[^>]* width="([\d.]+)" height="([\d.]+)"', text).groups())
    sc, _ = model.read(text)
    m = dict(canvas='%dx%d' % (W, H), area_M=round(W * H / 1e6, 1), boxes=len(sc.boxes))
    arrows = straight = bends = 0
    length = imp_len = 0.0
    for ln in text.split('\n'):
        if not (ln.startswith('<path d="M') and 'marker-end' in ln):
            continue
        pts = []
        for p in model.arrow_points(ln):             # a jump arc leaves points on a straight run: they are not bends
            if len(pts) >= 2 and (pts[-2][0] == pts[-1][0] == p[0] or pts[-2][1] == pts[-1][1] == p[1]):
                pts[-1] = p
            elif not pts or p != pts[-1]:
                pts.append(p)
        arrows += 1
        b = max(len(pts) - 2, 0)
        bends += b
        straight += (b == 0)
        L = sum(abs(x2 - x1) + abs(y2 - y1) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
        length += L
        kind = model.MARKER_KIND.get(re.search(r'marker-end="url\(#([^)]+)\)"', ln).group(1))
        if draw.IMPORTANCE.get(kind, 2) == 3:
            imp_len += L
    m.update(arrows=arrows, straight=straight, bends=bends, length_k=round(length / 1000, 1), tier3_length_k=round(imp_len / 1000, 1),
             jump_arcs=len(re.findall(r' A7 7 0 0 [01] ', text)))
    frames = re.findall(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*stroke-dasharray', text)
    fa = sum(float(w) * float(h) for _, _, w, h in frames)
    ba = sum(r[2] * r[3] for r in sc.boxes.values())
    m.update(frame_area_M=round(fa / 1e6, 1), box_fill=round(ba / fa, 3) if fa else None)
    return m


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rows = [(os.path.basename(p), measure(p)) for p in sys.argv[1:]]
    keys = list(rows[0][1])
    w0 = max(len(k) for k in keys)
    print(' ' * w0 + ''.join('  %18s' % n[-18:] for n, _ in rows))
    for k in keys:
        print(k.ljust(w0) + ''.join('  %18s' % m.get(k) for _, m in rows))


if __name__ == '__main__':
    main()
