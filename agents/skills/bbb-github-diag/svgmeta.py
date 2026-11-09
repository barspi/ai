#!/usr/bin/env python3
"""The facts a lineage SVG keeps about itself, beside what it draws. The SVG is the only file of a diagram: no snapshot, no notes file.

Every script reads and writes these facts through this module; nobody edits them by hand. Browsers ignore them, so the picture, the find
box and the pop-ups are unchanged.

On each box group, `<g id="nN" data-frame="..." data-github="{...}">`:
  data-frame   the visible title of the dotted frame the box belongs to (absent: outside every frame). The checker fails when the box
               does not sit inside that frame, or sits inside another one.
  data-github  what GitHub said at the last refresh (refresh_meta.py): updatedAt, kind, state, title, assignees, opener, comment and
               review counts, merge commit and its authors, dates and the native relations, as compact JSON. The next refresh compares
               the live data with it, so a box whose updatedAt is unchanged needs no reading. A box and its record cannot come apart.
On each arrow path, `data-from="A" data-to="B" data-kind="led to"` (read: A, kind, B). The kind is never guessed from an arrowhead, which
several kinds share.
One `<metadata id="diagram">` block after `<desc>`, one line of JSON, for the facts that have no box or arrow of their own:
  {"format": 1, "repo": "owner/name", "roots": [N], "lastRun": "ISO time of the last refresh",
   "ignored":   [{"num": N, "reason": "..."}],               items looked at and left out (refresh_meta.py --discover counts, not lists, them)
   "nopath":    [{"from": A, "to": B, "kind": "...", "reason": "..."}],   arrows that are true but not drawn (no clean path, or dropped)
   "decisions": ["YYYY-MM-DD who: what was decided and why"],             choices the drawing alone does not explain
   "notes":     "markdown: scope, revision naming, rules for this diagram (example/NOTES_template.md is the outline)",
   "accepted":  [{"from": A, "to": B, "check": "stale-far", "reason": "...", "date": "..."}],   review findings answered "keep" (rules.py)
   "closed":    [{"num": N, "verdict": "hand|done", "reason": "...", "date": "..."}]}   why an issue was closed, as the user said (rules.py)
Every key is written, empty when unused, so a reader sees the whole shape. A box record may also hold closeVerdict, replacedBy and
duplicateOf (refresh_meta.py).
Everything here travels with the file: facts and neutral reasons only, never remarks about people.

usage:
  svgmeta.py show IN.svg                                  the block, and counts of boxes and arrows with and without their attributes
  svgmeta.py check IN.svg                                 the checks check_diag.py runs (exit 1 on an error)
  svgmeta.py decide IN.svg "text" [--by NAME] [--date D]  add a dated decision
  svgmeta.py ignore IN.svg N "reason" | --remove N        an item looked at and left out
  svgmeta.py nopath IN.svg A B KIND "reason" | --remove A B   an arrow that is true but not drawn
  svgmeta.py notes IN.svg [--from FILE]                   print the notes, or replace them with the text of FILE
  svgmeta.py drop IN.svg A B "reason"                     remove the drawn arrow A -> B and its label, and record it in "nopath"
  svgmeta.py kind IN.svg A B KIND                         set the kind of the drawn arrow A -> B (same arrowhead only: a kind with
                                                          another arrowhead or a label must be drawn again)
  svgmeta.py migrate IN.svg OUT.svg [--repo R] [--roots N,N] [--snapshot snap.json] [--notes NOTES.md]
                                                          bring a file drawn before this module up to date (see migrate())
The commands that change a file edit IN.svg in place, like refresh_meta.py --apply.
"""
import datetime, html, json, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FORMAT = 1
BOX_OPEN = r'<g id="n(\d+)"((?: data-[\w-]+="[^"]*")*)>'      # a box group's opening tag, with or without its attributes
BOX_RE = re.compile(BOX_OPEN)
META_RE = re.compile(r'<metadata id="diagram">(.*?)</metadata>', re.S)
ATTR_RE = re.compile(r' (data-[\w-]+)="([^"]*)"')
KEYS = ('format', 'repo', 'roots', 'lastRun', 'ignored', 'nopath', 'decisions', 'notes', 'accepted', 'closed')


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def dumps(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def box_tag(num):
    """A regex for the opening tag of box `num`, with or without attributes."""
    return r'<g id="n%s"(?: data-[\w-]+="[^"]*")*>' % num


# ---------------------------------------------------------------- boxes

def box_open(num, frame=None, github=None):
    """The opening tag of a box group (draw.box writes it)."""
    a = ''
    if frame:
        a += ' data-frame="%s"' % esc(frame)
    if github:
        a += ' data-github="%s"' % esc(dumps(github))
    return '<g id="n%s"%s>' % (num, a)


def attrs(fragment):
    return {k: html.unescape(v) for k, v in ATTR_RE.findall(fragment)}


def boxes(text):
    """num -> {'frame': name or None, 'github': record or None}."""
    out = {}
    for m in BOX_RE.finditer(text):
        a = attrs(m.group(2))
        gh = a.get('data-github')
        out[int(m.group(1))] = {'frame': a.get('data-frame'), 'github': json.loads(gh) if gh else None}
    return out


_KEEP = object()


def set_box(text, num, frame=_KEEP, github=_KEEP):
    """Set or remove (None) the attributes of box `num`; others stay. Returns the text."""
    m = re.search(r'<g id="n%d"((?: data-[\w-]+="[^"]*")*)>' % num, text)
    if not m:
        raise KeyError('no box #%d' % num)
    a = attrs(m.group(1))
    old_f, old_g = a.pop('data-frame', None), a.pop('data-github', None)
    f = old_f if frame is _KEEP else frame
    g = old_g if github is _KEEP else (dumps(github) if github else None)
    tag = '<g id="n%d"' % num
    if f:
        tag += ' data-frame="%s"' % esc(f)
    if g:
        tag += ' data-github="%s"' % esc(g)
    tag += ''.join(' %s="%s"' % (k, esc(v)) for k, v in a.items()) + '>'
    return text[:m.start()] + tag + text[m.end():]


# ---------------------------------------------------------------- arrows

def arrow_attrs(a, b, kind):
    return ' data-from="%s" data-to="%s" data-kind="%s"' % (a, b, esc(kind))


def arrow_of(line):
    """(from, to, kind) of an arrow path line, or None when it has no attributes."""
    a = attrs(line)
    if 'data-from' in a and 'data-to' in a and 'data-kind' in a:
        return int(a['data-from']), int(a['data-to']), a['data-kind']
    return None


def set_arrow(line, a, b, kind):
    line = re.sub(r' data-(?:from|to|kind)="[^"]*"', '', line)
    return line.replace('/>', arrow_attrs(a, b, kind) + '/>', 1) if line.endswith('/>') else line


def is_arrow(line):
    return line.startswith('<path d="M') and 'marker-end' in line


def is_pinned(line):
    """An arrow whose route the user chose (`data-pinned="1"`): reroute.py --improve leaves it alone."""
    return ' data-pinned="1"' in line


def pin(line, on=True):
    """The arrow line with data-pinned set (on) or removed."""
    line = line.replace(' data-pinned="1"', '')                # at the end of the tag: every script finds arrows by '<path d="M'
    return line[:-2] + ' data-pinned="1"/>' if on and line.endswith('/>') else line


# ---------------------------------------------------------------- the diagram block

def new_meta(repo='', roots=()):
    return {'format': FORMAT, 'repo': repo, 'roots': [int(r) for r in roots], 'lastRun': None, 'ignored': [], 'nopath': [],
            'decisions': [], 'notes': '', 'accepted': [], 'closed': []}


def read(text):
    """The block as a dict (every key present), or None when the file has none (drawn before this module)."""
    m = META_RE.search(text)
    if not m:
        return None
    raw = json.loads(html.unescape(m.group(1)))
    meta = new_meta()
    meta.update(raw)
    meta['ignored'] = [x if isinstance(x, dict) else {'num': int(x), 'reason': ''} for x in meta['ignored']]
    return meta


def write(text, meta):
    """Put the block in the file: in place of the old one, else after <desc>, else after <title>, else after the <svg> tag."""
    data = {k: meta[k] for k in KEYS if k in meta}
    data.update({k: v for k, v in meta.items() if k not in KEYS})
    block = '<metadata id="diagram">%s</metadata>' % json.dumps(data, sort_keys=True, ensure_ascii=False).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if META_RE.search(text):
        return META_RE.sub(lambda _: block, text, count=1)
    for pat in (r'</desc>', r'</title>', r'<svg [^>]*>'):
        m = re.search(pat, text)
        if m:
            return text[:m.end()] + '\n' + block + text[m.end():]
    raise ValueError('no <svg> tag')


def ignored_nums(meta):
    return {x['num'] for x in (meta or {}).get('ignored', [])}


def add_nopath(meta, a, b, kind, reason):
    meta['nopath'] = [x for x in meta['nopath'] if (x['from'], x['to']) != (a, b)] + [{'from': a, 'to': b, 'kind': kind, 'reason': reason}]


# ---------------------------------------------------------------- what the drawing shows (used by migrate and the checks)

def frame_name(line):
    """The visible title of a frame's `<text class="ftl">` line (a tooltip inside it is not part of the name)."""
    line = re.sub(r'<title>.*?</title>', '', line, flags=re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', line)).strip()


def drawn_frames(text):
    """num -> the name of the smallest frame that contains the box, for every box inside one."""
    import collapse
    lines, box, _, frames = collapse.parse(text)
    out = {}
    for n, b in box.items():
        inside = [f for f in frames if f['x'] <= b['x'] and b['x'] + b['w'] <= f['x'] + f['w'] and f['y'] <= b['y'] and b['y'] + b['h'] <= f['y'] + f['h']]
        if inside:
            out[n] = frame_name(lines[min(inside, key=lambda f: f['w'] * f['h'])['tl']])
    return out


def drawn_arrows(text):
    """One entry per arrow path: (line index, tail box, tip box, label word or None, marker id). A box end is None when the end touches
    no box. Geometry only; the attributes are not read."""
    import draw, model, route
    sc, info = model.read(text)
    lines = info['lines']
    labels = []
    for i in range(len(lines)):
        lab = draw.label_at(lines, i)
        if lab:
            labels.append((lab[0] + lab[2] / 2, lab[1] + lab[3] / 2, lab[5]))
    out = []
    for i, ln in enumerate(lines):
        if not is_arrow(ln):
            continue
        pts = model.arrow_points(ln)
        ends = [next((n for n, r in sc.boxes.items() if model._side(p, r)), None) for p in (pts[0], pts[-1])]
        word = None
        for cx, cy, wd in labels:
            if wd in draw.EDGE and any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1)
                                       for o, c, lo, hi in route.segments(pts)):
                word = wd
        mk = re.search(r'marker-end="url\(#([\w-]+)\)"', ln)
        out.append((i, ends[0], ends[1], word, mk.group(1) if mk else None))
    return out


def kinds_of_marker(marker):
    import draw
    return [k for k, v in draw.EDGE.items() if v[2] == marker]


# ---------------------------------------------------------------- checks

def problems(text):
    """[(level, message)], level 'error' or 'warn'. A file with no block is an old file: one warning, nothing else is checked."""
    meta = read(text)
    if meta is None:
        return [('warn', 'no <metadata id="diagram">: a file drawn before svgmeta.py; run svgmeta.py migrate on the next revision')]
    out = []
    if meta.get('format') != FORMAT:
        out.append(('error', 'metadata format %r, this skill reads %d' % (meta.get('format'), FORMAT)))
    if not meta.get('repo'):
        out.append(('error', 'metadata has no "repo"'))
    bx = boxes(text)
    geo = drawn_frames(text)
    for n in sorted(bx):
        want, got = bx[n]['frame'], geo.get(n)
        if want != got:
            out.append(('error', '#%d: data-frame %r, but the box sits %s' % (n, want, ('inside %r' % got) if got else 'outside every frame')))
    no_gh = sorted(n for n in bx if not bx[n]['github'])
    if no_gh:
        out.append(('warn', '%d boxes have no data-github yet (run refresh_meta.py): %s' % (len(no_gh), ' '.join('#%d' % n for n in no_gh[:12]) + (' ...' if len(no_gh) > 12 else ''))))
    import draw
    lines = text.split('\n')
    pairs = set()
    for i, a, b, word, marker in drawn_arrows(text):
        at = arrow_of(lines[i])
        if at is None:
            out.append(('error', 'arrow #%s -> #%s (line %d) has no data-from/data-to/data-kind' % (a, b, i + 1)))
            continue
        fa, fb, kind = at
        pairs.add((fa, fb))
        if kind not in draw.EDGE:
            out.append(('error', 'arrow #%d -> #%d: unknown kind %r' % (fa, fb, kind)))
            continue
        if (a, b) != (fa, fb):
            out.append(('error', 'arrow data says #%d -> #%d, but it is drawn from %s to %s' % (fa, fb, '#%s' % a if a else 'no box', '#%s' % b if b else 'no box')))
        if draw.EDGE[kind][2] != marker:
            out.append(('error', 'arrow #%d %s #%d: data-kind %r, but its arrowhead is %s' % (fa, kind, fb, kind, marker)))
        if word and word != kind:
            out.append(('error', 'arrow #%d -> #%d: data-kind %r, but its label says %r' % (fa, fb, kind, word)))
    for x in meta['nopath']:
        if x['from'] not in bx or x['to'] not in bx:
            out.append(('warn', 'nopath #%s -> #%s names a box that is not in the diagram' % (x['from'], x['to'])))
        if (x['from'], x['to']) in pairs:
            out.append(('error', 'nopath #%s -> #%s, but that arrow is drawn: remove it from nopath' % (x['from'], x['to'])))
    for n in sorted(ignored_nums(meta) & set(bx)):
        out.append(('error', '#%d is in "ignored" but it is a box' % n))
    return out


# ---------------------------------------------------------------- drop a drawn arrow

def drop(text, a, b, reason):
    """Remove the drawn arrow a -> b (its path and the label on it), record it in "nopath" with the reason, and redo the jump arcs
    (an arc that hopped over it now hops over nothing). Returns the text. The boxes and the other arrows do not move."""
    import draw, hops, model, route
    lines = text.split('\n')
    hit = [i for i, l in enumerate(lines) if is_arrow(l) and (arrow_of(l) or (None, None))[:2] == (a, b)]
    if len(hit) != 1:
        raise KeyError('%d drawn arrows #%d -> #%d with data-from/data-to' % (len(hit), a, b))
    i = hit[0]
    kind = arrow_of(lines[i])[2]
    segs = route.segments(model.arrow_points(lines[i]))
    gone = [i]
    for j in range(len(lines)):
        lab = draw.label_at(lines, j)
        if lab and lab[5] == kind:
            cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
            if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1) for o, c, lo, hi in segs):
                gone += list(range(j, j + 1 + lab[4]))
                break
    text = '\n'.join(l for k, l in enumerate(lines) if k not in set(gone))
    text, _, _ = hops.add_hops(text)
    meta = read(text)
    if meta is not None:
        add_nopath(meta, a, b, kind, reason)
        text = write(text, meta)
    return text


# ---------------------------------------------------------------- migrate

def migrate(text, repo=None, roots=(), snapshot=None, notes=None):
    """Bring a file drawn before this module up to date. Returns (text, report lines).
    - each arrow gets data-from/data-to from its geometry and data-kind from its label; with no label, from its arrowhead, and when that
      arrowhead is shared by several kinds it gets that arrowhead's general word (led to, related) and is listed as AMBIGUOUS: read
      GitHub and fix it with `svgmeta.py kind`;
    - each box inside a frame gets data-frame (the smallest frame around it);
    - with --snapshot, each box gets data-github from the old snapshot file, and its `_meta` (lastRun, ignored) goes into the block;
    - with --notes, the text of the old NOTES file becomes "notes".
    An arrow that touches no box at one end is reported and left without attributes."""
    import model
    rep = []
    lines = text.split('\n')
    for i, a, b, word, marker in drawn_arrows(text):
        if a is None or b is None or a == b:
            rep.append('line %d: an arrow with no box at %s: left as it is' % (i + 1, 'its tail' if a is None else 'its tip'))
            continue
        if word:
            kind = word
        else:
            ks = kinds_of_marker(marker)
            kind = model.MARKER_KIND.get(marker, 'related')       # the general word of that arrowhead
            if len(ks) > 1:
                rep.append('AMBIGUOUS #%d -> #%d: no label, arrowhead %s is one of %s; set to %r' % (a, b, marker, ', '.join(ks), kind))
        lines[i] = set_arrow(lines[i], a, b, kind)
    text = '\n'.join(lines)
    for n, f in drawn_frames(text).items():
        text = set_box(text, n, frame=f)
    meta = read(text) or new_meta()
    if not meta['repo']:
        m = re.search(r'Repository: ([^<]+)', text) or re.search(r'github\.com/([^/"]+/[^/"]+)/(?:issues|pull)/', text)
        meta['repo'] = repo or (m.group(1).strip() if m else '')
    if repo:
        meta['repo'] = repo
    if roots:
        meta['roots'] = [int(r) for r in roots]
    if snapshot:
        snap = json.load(open(snapshot, encoding='utf-8'))
        sm = snap.get('_meta', {})
        if sm.get('lastRun'):
            meta['lastRun'] = sm['lastRun']
        known = ignored_nums(meta)
        meta['ignored'] += [{'num': int(x), 'reason': ''} for x in sm.get('ignored', []) if int(x) not in known]
        have = boxes(text)
        put = 0
        for k, v in snap.items():
            if k != '_meta' and isinstance(v, dict) and int(k) in have:
                text = set_box(text, int(k), github=v)
                put += 1
        rep.append('data-github from the snapshot on %d of %d boxes' % (put, len(have)))
    if notes:
        meta['notes'] = open(notes, encoding='utf-8').read()
    return write(text, meta), rep


# ---------------------------------------------------------------- command line

def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    cmd, path = a[0], a[1]
    rest = a[2:]
    text = open(path, encoding='utf-8').read()

    def opt(name, default=None):
        if name in rest:
            i = rest.index(name)
            v = rest[i + 1]
            del rest[i:i + 2]
            return v
        return default

    def save(t):
        open(path, 'w', encoding='utf-8').write(t)

    if cmd == 'show':
        meta = read(text)
        print(json.dumps(meta, indent=1, ensure_ascii=False) if meta else 'no <metadata id="diagram"> (an old file: svgmeta.py migrate)')
        bx = boxes(text)
        arrows = [l for l in text.split('\n') if is_arrow(l)]
        print('%d boxes: %d with data-frame, %d with data-github; %d arrows, %d with data-kind' % (
            len(bx), sum(1 for v in bx.values() if v['frame']), sum(1 for v in bx.values() if v['github']), len(arrows),
            sum(1 for l in arrows if arrow_of(l))))
    elif cmd == 'check':
        ps = problems(text)
        for lvl, msg in ps:
            print(lvl.upper(), msg)
        print('metadata: %d errors, %d warnings' % (sum(1 for p in ps if p[0] == 'error'), sum(1 for p in ps if p[0] == 'warn')))
        sys.exit(1 if any(p[0] == 'error' for p in ps) else 0)
    elif cmd == 'drop':
        if len(rest) != 3:
            sys.exit(__doc__)
        fa, fb = int(rest[0].lstrip('#')), int(rest[1].lstrip('#'))
        try:
            save(drop(text, fa, fb, rest[2]))
        except KeyError as e:
            sys.exit(str(e))
        print('updated %s: #%d -> #%d dropped and kept in "nopath"' % (path, fa, fb))
    elif cmd == 'kind':
        if len(rest) != 3:
            sys.exit(__doc__)
        import draw
        fa, fb, kind = int(rest[0].lstrip('#')), int(rest[1].lstrip('#')), rest[2]
        if kind not in draw.EDGE:
            sys.exit('unknown kind %r: use one of %s' % (kind, ', '.join(draw.EDGE)))
        lines = text.split('\n')
        hit = [i for i, l in enumerate(lines) if is_arrow(l) and (arrow_of(l) or (None, None))[:2] == (fa, fb)]
        if len(hit) != 1:
            sys.exit('%d drawn arrows #%d -> #%d with data-from/data-to' % (len(hit), fa, fb))
        mk = re.search(r'marker-end="url\(#([\w-]+)\)"', lines[hit[0]]).group(1)
        if draw.EDGE[kind][2] != mk:
            sys.exit('#%d -> #%d has the arrowhead %s; %r needs %s: draw the arrow again' % (fa, fb, mk, kind, draw.EDGE[kind][2]))
        lab = [w for i, a, b, w, m in drawn_arrows(text) if i == hit[0]]
        if lab and lab[0] and lab[0] != kind:
            sys.exit('#%d -> #%d carries the label %r: draw the arrow again to change it' % (fa, fb, lab[0]))
        lines[hit[0]] = set_arrow(lines[hit[0]], fa, fb, kind)
        save('\n'.join(lines))
        print('updated %s: #%d %s #%d' % (path, fa, kind, fb))
    elif cmd in ('decide', 'ignore', 'nopath', 'notes'):
        meta = read(text)
        if meta is None:
            sys.exit('%s has no metadata block: run svgmeta.py migrate first' % path)
        if cmd == 'decide':
            by, day = opt('--by', ''), opt('--date', datetime.date.today().isoformat())
            if len(rest) != 1:
                sys.exit(__doc__)
            meta['decisions'].append('%s%s: %s' % (day, ' ' + by if by else '', rest[0]))
        elif cmd == 'ignore':
            rm = opt('--remove')
            if rm:
                meta['ignored'] = [x for x in meta['ignored'] if x['num'] != int(rm.lstrip('#'))]
            elif len(rest) == 2:
                n = int(rest[0].lstrip('#'))
                meta['ignored'] = [x for x in meta['ignored'] if x['num'] != n] + [{'num': n, 'reason': rest[1]}]
            else:
                sys.exit(__doc__)
        elif cmd == 'nopath':
            if '--remove' in rest:
                rest.remove('--remove')
                fa, fb = (int(x.lstrip('#')) for x in rest[:2])
                meta['nopath'] = [x for x in meta['nopath'] if (x['from'], x['to']) != (fa, fb)]
            elif len(rest) == 4:
                add_nopath(meta, int(rest[0].lstrip('#')), int(rest[1].lstrip('#')), rest[2], rest[3])
            else:
                sys.exit(__doc__)
        else:
            src = opt('--from')
            if not src:
                print(meta['notes'])
                return
            meta['notes'] = open(src, encoding='utf-8').read()
        save(write(text, meta))
        print('updated %s' % path)
    elif cmd == 'migrate':
        if not rest:
            sys.exit(__doc__)
        out = rest.pop(0)
        roots = opt('--roots', '')
        text, rep = migrate(text, opt('--repo'), [r for r in roots.replace('#', '').split(',') if r.strip()], opt('--snapshot'), opt('--notes'))
        if os.path.exists(out) and os.path.abspath(out) != os.path.abspath(path):
            sys.exit('%s exists: give a new name (a migrated file is a new revision)' % out)
        open(out, 'w', encoding='utf-8').write(text)
        for r in rep:
            print(r)
        ps = problems(text)
        print('wrote %s; metadata: %d errors, %d warnings (svgmeta.py check %s)' % (out, sum(1 for p in ps if p[0] == 'error'), sum(1 for p in ps if p[0] == 'warn'), out))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
