#!/usr/bin/env python3
"""Finds the fonts the checker and the sample generator use to measure text, on macOS, Linux and Windows
(also WSL, where the Windows fonts are under /mnt/c/Windows/Fonts).

The SVG asks for `Helvetica Neue, Helvetica, Arial, sans-serif` and `Menlo, Consolas, monospace`. To measure text
the way a reader's browser will draw it, the first of these is used that exists on this machine:

  sans  Helvetica, Arial, Liberation Sans, Arimo, Nimbus Sans, DejaVu Sans, then whatever `fc-match sans` names
  mono  Menlo, Consolas, Liberation Mono, Cousine, DejaVu Sans Mono, Courier New, then `fc-match monospace`

Helvetica, Arial, Liberation Sans, Arimo and Nimbus Sans have (nearly) the same character widths, so a measurement
with any of them is the same. DejaVu is about 10% wider: lines are measured longer than they will be drawn, so a
check that passes with it also passes with the real font.

usage in a script:   from fonts import load;  f = load('bold', 54)      # 4x of 13.5px; divide getlength() by 4
usage as a check:    python3 fonts.py        (prints the file chosen for each style, exit 1 when one is missing)
Styles: regular, bold, italic, bolditalic (sans) and mono.
"""
import glob, os, shutil, subprocess, sys

from PIL import ImageFont

SANS = ['helvetica', 'arial', 'liberation sans', 'arimo', 'nimbus sans', 'dejavu sans']
MONO = ['menlo', 'consolas', 'liberation mono', 'cousine', 'dejavu sans mono', 'courier new']
METRIC_OK = {'helvetica', 'arial', 'liberation sans', 'arimo', 'nimbus sans', 'menlo', 'consolas', 'liberation mono', 'cousine'}
HINT = {'helvetica': 'helvetica', 'arial': 'arial', 'liberation sans': 'liberationsans', 'arimo': 'arimo', 'nimbus sans': 'nimbussans',
        'dejavu sans': 'dejavusans', 'menlo': 'menlo', 'consolas': 'consola', 'liberation mono': 'liberationmono', 'cousine': 'cousine',
        'dejavu sans mono': 'dejavusansmono', 'courier new': 'cour'}
DIRS = ['/System/Library/Fonts', '/System/Library/Fonts/Supplemental', '/Library/Fonts', '~/Library/Fonts',          # macOS
        '/usr/share/fonts', '/usr/local/share/fonts', '~/.local/share/fonts', '~/.fonts',                              # Linux
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'), '/mnt/c/Windows/Fonts']                         # Windows, WSL
_index = None


def _style(name):
    s = name.lower()
    bold, ital = 'bold' in s, ('italic' in s or 'oblique' in s)
    if any(w in s for w in ('light', 'thin', 'black', 'heavy', 'medium', 'semi', 'condensed', 'narrow', 'extra', 'ultra')):
        return None
    return 'bolditalic' if bold and ital else 'bold' if bold else 'italic' if ital else 'regular'


def _scan():
    """{(family, style): (path, ttc index)} for the candidate families found in the usual folders."""
    found = {}
    wanted = set(HINT.values())
    for d in DIRS:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                low = fn.lower().replace('-', '').replace('_', '').replace(' ', '')
                if not low.endswith(('.ttf', '.ttc', '.otf')) or not any(h in low for h in wanted):
                    continue
                path = os.path.join(root, fn)
                for i in range(12):
                    try:
                        fam, sty = ImageFont.truetype(path, 10, index=i).getname()
                    except (OSError, IndexError):
                        break
                    st = _style(sty)
                    if st and (fam.lower(), st) not in found:
                        found[(fam.lower(), st)] = (path, i)
                    if not path.lower().endswith('.ttc'):
                        break
    return found


def _fc(pattern, style):
    """Last resort: ask fontconfig (Linux, and macOS with Homebrew) for the file of a generic family."""
    if not shutil.which('fc-match'):
        return None
    spec = pattern + (':bold' if 'bold' in style else '') + (':italic' if 'italic' in style else '')
    out = subprocess.run(['fc-match', '-f', '%{file}|%{index}', spec], capture_output=True, text=True).stdout.split('|')
    return (out[0], int(out[1] or 0)) if out and os.path.exists(out[0]) else None


def pick(style):
    """(path, index, family) for a style; family is '' for a fontconfig answer. None when nothing is found."""
    global _index
    if _index is None:
        _index = _scan()
    for fam in (MONO if style == 'mono' else SANS):
        hit = _index.get((fam, 'regular' if style == 'mono' else style))
        if hit:
            return hit + (fam,)
    hit = _fc('monospace' if style == 'mono' else 'sans', style)
    return hit + ('',) if hit else None


def load(style, size):
    """A PIL font for `style` at `size` (pass 4x the CSS px size to keep sub-pixel widths, then divide by 4)."""
    p = pick(style)
    if not p:
        sys.exit('no %s font found. Install one of: %s (see fonts.py)' % (style, ', '.join(MONO if style == 'mono' else SANS)))
    return ImageFont.truetype(p[0], size, index=p[1])


if __name__ == '__main__':
    bad = 0
    for st in ('regular', 'bold', 'italic', 'bolditalic', 'mono'):
        p = pick(st)
        if not p:
            print('MISSING %-10s install one of: %s' % (st, ', '.join(MONO if st == 'mono' else SANS)))
            bad = 1
            continue
        note = '' if p[2] in METRIC_OK else '   (wider than Helvetica/Arial: text is measured longer than it is drawn)'
        print('%-10s %s [%d] %s%s' % (st, p[0], p[1], p[2] or 'via fc-match', note))
    sys.exit(bad)
