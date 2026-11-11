#!/usr/bin/env python3
"""The first line of a box (kind tag, number link, assignee or author) in ONE place.

The line is ONE `<text class="kind">` that flows left to right with plain spaces. There is no x or y on its parts, so a longer
tag or name pushes the rest and nothing has to be moved by hand:

  issue        ISSUE #120 -> alice                the arrow is the character U+2192, 15px; the login is 11.5px, weight 600
  umbrella     (umbrella emoji) ISSUE #100 -> alice      the emoji U+2602 U+FE0F is 16.9px, which is 25% over the 13.5px tag
  pull request PR #122 by alice                   no arrow
  not assigned the login is `?`
  label mark   (mark) ISSUE #130 -> alice        a GitHub label the chart's metadata lists in "label_marks" (e.g. {"label": "x",
               "letter": "x", "fill": "#2e7d32"}): a 13px round pill with a white letter, drawn before the tag (and before the
               umbrella emoji). The tag sits in GAP_OPEN, a tspan with dx (honoured by browsers and rsvg alike), to make room;
               the pill is a `<rect class="mark">` and a `<text class="mark">` just before the kind text. svg_state.py adds and removes it at each refresh.

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
MARK_D = 19.5                      # the mark's diameter; its letter is MARK_D - 4.5 px
MARK_DX = MARK_D + 5
GAP_OPEN = '<tspan dx="%g">' % MARK_DX   # room for a label mark: the tag (and umbrella) shifted right inside this tspan
GAP_RE = re.compile(r'<tspan dx="([\d.]+)">')   # any size: a chart drawn with an older MARK_D is still read


def gap_of(inner):
    """The GAP_OPEN tspan a kind text starts with (any dx), or ''."""
    m = GAP_RE.match(inner)
    return m.group(0) if m else ''
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


def tag(kind, umbrella=False, gap=False):
    """`ISSUE `, `PR `, or the umbrella emoji and `ISSUE ` (an umbrella is an ISSUE); shifted right in GAP_OPEN when the box has a label mark."""
    t = (UMB_OPEN + ' ISSUE ') if umbrella else kind + ' '
    return (GAP_OPEN + t.rstrip(' ') + '</tspan> ') if gap else t      # the space outside: a renderer drops it at a tspan's end


MARK = re.compile(r'<rect class="mark"[^>]*/>\n<text class="mark"[^>]*>.*?</text>\n')


def mark(x, y, fill, letter, label=''):
    """The label mark of a kind text at (x, y): a round pill and its white letter, centred in the room GAP_OPEN leaves. The label
    name is a <title> of the letter: a tooltip, and part of the box's text, so the find box (find-box.js) matches it."""
    x, y, r = float(x), float(y), MARK_D / 2
    cy = y - 5                                                    # the middle of the 13.5px capitals
    title = '<title>label: %s</title>' % html.escape(label) if label else ''
    return ('<rect class="mark" x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s"/>'
            '\n<text class="mark" x="%g" y="%g" text-anchor="middle" style="fill:#ffffff;font:700 %gpx Georgia,serif">%s%s</text>\n'
            % (round(x, 1), round(cy - r, 2), MARK_D, MARK_D, r, fill, round(x + r, 2), round(cy + (MARK_D - 4.5) * 0.35, 1),
               MARK_D - 4.5, letter, title))


def set_mark(markup, want):
    """Put the wanted mark (a dict with letter and fill, or None) on the box's first line, or take it off. Returns (markup, changed)."""
    m = KIND_TEXT.search(markup)
    if not m:
        return markup, False
    x, y, inner = m.group(1), m.group(2), m.group(4)
    g = gap_of(inner)
    has, old = bool(g), MARK.search(markup, 0, m.start() + 1)
    new = mark(x, y, want['fill'], want['letter'], want.get('label', '')) if want else ''
    if has == bool(want) and (old.group(0) if old else '') == new and (not g or g == GAP_OPEN):
        return markup, False
    body = GAP_OPEN + inner[len(g):] if want and has else inner
    if want and not has:                                          # the tag (up to the number link) goes into the shifted tspan
        i = inner.index('<a ')
        body = GAP_OPEN + inner[:i].rstrip(' ') + '</tspan> ' + inner[i:]
    elif has and not want:
        core = inner[len(g):]
        j = core.rindex('</tspan>', 0, core.index('<a '))
        body = core[:j] + core[j + len('</tspan>'):]
    kind = markup[m.start():m.start(4)] + body + markup[m.end(4):m.end()]
    pre = markup[:m.start()]
    if old:
        pre = pre[:old.start()] + pre[old.end():]
    return pre + new + kind + markup[m.end():], True


def _tail(who, pr, with_arrow=True):
    if who is None:
        return ''
    name = '<tspan style="%s">%s</tspan>' % (NAME_STYLE, who)
    return name if pr else ('<tspan style="%s">%s</tspan> ' % (ARROW_STYLE, ARROW) if with_arrow else '') + name


def text_width(inner):
    """Estimated width in px of the inner markup of a kind text (links, tspans with their own size and spacing)."""
    inner = re.sub(r'<title>.*?</title>', '', inner, flags=re.S)
    g = GAP_RE.match(inner)
    w = float(g.group(1)) if g else 0.0
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


def header(x, y, color, kind, link, who, umbrella=False, limit=None, gap=False):
    """Markup of the first line. `link` is the finished `<a>` markup; `who` is the XML-escaped login text (issue) or `by login` (pull
    request), None for a pull request with no author. `x`, `y` are the text origin (box x + 14, box y + 28). `limit` is the x the line
    must end before. Returns (markup, two_lines)."""
    pr = kind == 'PR'
    first = '<text class="kind" x="%s" y="%s" style="fill:%s">%s%s' % (x, y, color, tag(kind, umbrella, gap), link)
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
    g = gap_of(s)
    if g:                                                         # a marked box: the tag ends its shifted tspan ("ISSUE</tspan> ")
        s = re.sub(r'(ISSUE|PR)</tspan> ', r'\1 ', s[len(g):], count=1)
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
    new, two = header(x, y, color, 'ISSUE' if umb else kind, link.group(0), who, umb, _limit(markup[end:end + 1800], float(x)),
                      bool(gap_of(inner)))
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
