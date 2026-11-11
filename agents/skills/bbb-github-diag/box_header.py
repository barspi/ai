#!/usr/bin/env python3
"""The first line of a box (kind tag, number link, assignee or author) in ONE place.

The line is ONE `<text class="kind">` that flows left to right with plain spaces. There is no x or y on its parts, so a longer
tag or name pushes the rest and nothing has to be moved by hand:

  issue        ISSUE #120 -> alice                the arrow is the character U+2192, 15px; the login is 11.5px, weight 600
  umbrella     (umbrella emoji) ISSUE #100 -> alice      the emoji U+2602 U+FE0F is 16.9px, which is 25% over the 13.5px tag
  pull request PR #122 by alice                   no arrow
  not assigned the login is `?`

  <text class="kind" x=".." y=".." style="fill:#..">ISSUE <a>#120</a> <tspan ARROW>&#8594;</tspan> <tspan NAME>alice</tspan></text>

A tspan sets letter-spacing:0 so the 0.3px spacing of the `.kind` class is not inherited by the arrow and the name.
The line must end before the pill (6px) and before the red cross (12px). When it does not, the arrow and the name go on a
second `<text class="kind">` 13px lower (never truncated, never smaller than 11.5px).

usage as a module:  header(...), kind_of(box_markup), who_of(box_markup), set_who(box_markup, label), refit(box_markup),
                    text_width(inner), restyle(svg)
usage as a command: box_header.py restyle IN.svg OUT.svg     converts boxes and pop-ups drawn the old way (kind + 5-point arrow
                                                             polyline + separate name text, tag UMBRELLA) to this form. OUT may be IN.
                    Run it once on a revision that was drawn the old way. On a file already in this form it changes nothing.
"""
import html, re, sys

from fonts import load

EMOJI = '☂️'
ARROW = '→'
KIND_PX, KIND_SPACING = 13.5, 0.3
UMBRELLA_PX = 16.9                 # 25% over the tag
ARROW_PX = 15
NAME_PX = 11.5
ARROW_STYLE = 'font-size:%gpx;letter-spacing:0' % ARROW_PX
NAME_STYLE = 'font-size:%gpx;font-weight:600;letter-spacing:0' % NAME_PX
UMB_OPEN = '<tspan style="font-size:%gpx">%s</tspan>' % (UMBRELLA_PX, EMOJI)
EMOJI_EM, ARROW_EM = 1.02, 1.0     # advance in ems of the emoji and the arrow glyph (font dependent; measured in a browser)

KIND_TEXT = re.compile(r'<text class="kind" x="([\d.]+)" y="([\d.]+)" style="fill:(#[0-9a-f]{6})">(.*?)</text>', re.S)
NAME_TSPAN = re.compile(r'<tspan style="%s">(.*?)</tspan>' % re.escape(NAME_STYLE), re.S)
OLD = re.compile(
    r'<text class="kind" x="([\d.]+)" y="([\d.]+)" style="fill:(#[0-9a-f]{6})">(ISSUE|UMBRELLA|PR) (<a [^>]*>.*?</a>)</text>'
    r'(?:\n<polyline points="[^"]*" fill="none" stroke="#[0-9a-f]{6}" stroke-width="1.3"[^>]*/>)?'
    r'(?:\n<text class="meta" x="([\d.]+)" y="([\d.]+)" style="fill:#[0-9a-f]{6};font-size:([\d.]+)px;font-weight:600">([^<]*)</text>)?', re.S)


def tag(kind, umbrella=False):
    """`ISSUE `, `PR `, or the umbrella emoji and `ISSUE ` (an umbrella is an ISSUE)."""
    return (UMB_OPEN + ' ISSUE ') if umbrella else kind + ' '


def _tail(who, pr, with_arrow=True):
    if who is None:
        return ''
    name = '<tspan style="%s">%s</tspan>' % (NAME_STYLE, who)
    return name if pr else ('<tspan style="%s">%s</tspan> ' % (ARROW_STYLE, ARROW) if with_arrow else '') + name


def text_width(inner):
    """Estimated width in px of the inner markup of a kind text (links, tspans with their own size and spacing)."""
    inner = re.sub(r'<title>.*?</title>', '', inner, flags=re.S)
    w = 0.0
    for m in re.finditer(r'<tspan style="([^"]*)">(.*?)</tspan>|([^<]+)|<[^>]+>', inner, re.S):
        style, txt = (m.group(1), m.group(2)) if m.group(1) is not None else ('', m.group(3) or '')
        txt = html.unescape(re.sub(r'<[^>]+>', '', txt))
        size = float((re.search(r'font-size:([\d.]+)px', style) or [0, KIND_PX])[1])
        sp = float((re.search(r'letter-spacing:([\d.]+)', style) or [0, KIND_SPACING])[1])
        bold = int((re.search(r'font-weight:(\d+)', style) or [0, 700])[1]) >= 600
        f = load('bold' if bold else 'regular', int(size * 4))
        for ch in txt:
            if ch == '️':
                continue
            w += (EMOJI_EM * size if ch == '☂' else ARROW_EM * size if ch == ARROW else f.getlength(ch) / 4) + sp
    return w


def header(x, y, color, kind, link, who, umbrella=False, limit=None):
    """Markup of the first line. `link` is the finished `<a>` markup; `who` is the XML-escaped login text (issue) or `by login` (pull
    request), None for a pull request with no author. `x`, `y` are the text origin (box x + 14, box y + 28). `limit` is the x the line
    must end before. Returns (markup, two_lines)."""
    pr = kind == 'PR'
    first = '<text class="kind" x="%s" y="%s" style="fill:%s">%s%s' % (x, y, color, tag(kind, umbrella), link)
    one = first + (' ' + _tail(who, pr) if who is not None else '') + '</text>'
    if who is None or limit is None or float(x) + text_width(one[one.index('>', one.index('style=')) + 1:-7]) <= limit:
        return one, False
    two = '<text class="kind" x="%s" y="%s" style="fill:%s">%s</text>' % (x, '%g' % round(float(y) + 13, 1), color, _tail(who, pr))
    return first + '</text>\n' + two, True


def kind_of(markup):
    """'ISSUE', 'UMBRELLA', 'PR' (or None) of a box group, from its first kind text. Reads the old tag UMBRELLA too."""
    m = KIND_TEXT.search(markup)
    if not m:
        return None
    s = m.group(4)
    if s.startswith(UMB_OPEN) or s.startswith('UMBRELLA '):
        return 'UMBRELLA'
    return 'PR' if s.startswith('PR ') else 'ISSUE' if s.startswith('ISSUE ') else None


def who_of(markup):
    """The login text (or `by login`) of a box drawn in this form, or None."""
    found = NAME_TSPAN.findall(markup)
    return found[-1] if found else None


def set_who(markup, label):
    """Replace the login text. Returns (markup, old) or (markup, None) when the box is not drawn in this form."""
    ms = list(NAME_TSPAN.finditer(markup))
    if not ms:
        return markup, None
    m = ms[-1]
    return markup[:m.start(1)] + label + markup[m.end(1):], m.group(1)


TAIL_LINE = re.compile(r'\n<text class="kind" x="[\d.]+" y="[\d.]+" style="fill:#[0-9a-f]{6}">((?:(?!<a |</text>).)*)</text>', re.S)


def refit(markup):
    """Lay out the first line of a box again after its login changed (set_who swaps only the text): one line when it ends before the
    pill (and cross), else the arrow and the name on a second line 13px lower, as header() draws it. Returns (markup, lines before,
    lines after); (markup, None, None) when the box is not drawn in this form."""
    m = KIND_TEXT.search(markup)
    who = who_of(markup)
    if not m or who is None:
        return markup, None, None
    x, y, color, inner = m.group(1), m.group(2), m.group(3), m.group(4)
    link = re.search(r'<a .*?</a>', inner, re.S)
    if not link:
        return markup, None, None
    end = m.end()
    t = TAIL_LINE.match(markup, end)
    before = 2 if t and NAME_TSPAN.search(t.group(1)) else 1
    if before == 2:
        end = t.end()
    kind = kind_of(markup)
    umb = kind == 'UMBRELLA'
    new, two = header(x, y, color, 'ISSUE' if umb else kind, link.group(0), who, umb, _limit(markup[end:end + 1800], float(x)))
    return markup[:m.start()] + new + markup[end:], before, 2 if two else 1


def _limit(tail, x):
    """The x a header must end before, from the pill (and red cross) that follow it in the box markup."""
    cut = tail.find('class="ttl"')
    seg = tail[:cut if cut > 0 else 1500]
    p = re.search(r'<rect x="([\d.]+)" y="[\d.]+" width="[\d.]+" height="20" rx="10"', seg)
    if not p:
        return x + 232
    c = re.search(r'<line x1="([\d.]+)"[^>]*stroke="#ff2a2a"', seg)
    return float(c.group(1)) - 12 if c else float(p.group(1)) - 6


def restyle(svg):
    """Old form to the single-line form, for every box and pop-up. Returns (svg, counts)."""
    n = {'headers': 0, 'umbrella': 0, 'second line': 0}

    def fix(m):
        x, y, color, k, link = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        name = m.group(9)
        pr = k == 'PR'
        umb = k == 'UMBRELLA'
        kind = 'ISSUE' if umb else k
        limit = _limit(svg[m.end():m.end() + 1800], float(x))
        out, two = header(x, y, color, kind, link, name if name is not None else None, umb, limit)
        n['headers'] += 1
        n['umbrella'] += umb
        n['second line'] += two
        return out

    return OLD.sub(fix, svg), n


def main():
    if len(sys.argv) != 4 or sys.argv[1] != 'restyle':
        sys.exit(__doc__)
    s = open(sys.argv[2], encoding='utf-8').read()
    out, n = restyle(s)
    open(sys.argv[3], 'w', encoding='utf-8').write(out)
    print('%s -> %s: %d headers converted (%d umbrella, %d on two lines)' % (sys.argv[2], sys.argv[3], n['headers'], n['umbrella'], n['second line']))


if __name__ == '__main__':
    main()
