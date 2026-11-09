#!/usr/bin/env python3
"""Render one region of a diagram to PNG, to look at what changed. Never render the whole canvas to look at a part of it.

usage: render_region.py IN.svg OUT.png X Y W H [--scale S]
       render_region.py IN.svg OUT.png --box N [--margin PX] [--scale S]

X Y W H is the region in diagram coordinates; --box N takes box #N and --margin px around it (default 500). --scale S (default 1)
multiplies the pixel size. The find box script is left out (it would move the nodes into an inner <svg>). Needs rsvg-convert.
A whole 7000px canvas takes about 20s to render; a 1600x1000 region of it takes a few seconds (rsvg-convert still parses the whole
file). To compare two revisions, render the same region of each.
"""
import os, re, subprocess, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def crop(text, x, y, w, h, scale=1.0):
    """The SVG text with its root size and viewBox set to the region, and without the script."""
    text = re.sub(r'<svg ([^>]*?)width="[\d.]+" height="[\d.]+" viewBox="[^"]*"',
                  lambda m: '<svg %swidth="%d" height="%d" viewBox="%g %g %g %g"' % (m.group(1), w * scale, h * scale, x, y, w, h),
                  text, count=1)
    return re.sub(r'<script.*?</script>', '', text, flags=re.S)


def main():
    argv = sys.argv[1:]
    opt = lambda name, d: float(argv[argv.index(name) + 1]) if name in argv else d
    scale, margin = opt('--scale', 1.0), opt('--margin', 500.0)
    pos = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or not argv[i - 1].startswith('--'))]
    if len(pos) < 2:
        sys.exit(__doc__)
    src, out = pos[0], pos[1]
    text = open(src, encoding='utf-8').read()
    if '--box' in argv:
        import collapse
        n = int(argv[argv.index('--box') + 1].lstrip('#'))
        b = collapse.parse(text)[1][n]
        x, y, w, h = b['x'] - margin, b['y'] - margin, b['w'] + 2 * margin, b['h'] + 2 * margin
    elif len(pos) >= 6:
        x, y, w, h = (float(v) for v in pos[2:6])
    else:
        sys.exit(__doc__)
    fd, tmp = tempfile.mkstemp(suffix='.svg')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(crop(text, x, y, w, h, scale))
    try:
        subprocess.run(['rsvg-convert', tmp, '-o', out], check=True)
    finally:
        os.unlink(tmp)
    print('%s: region %g,%g %gx%g' % (out, x, y, w, h))


if __name__ == '__main__':
    main()
