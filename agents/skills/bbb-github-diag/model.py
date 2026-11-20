#!/usr/bin/env python3
"""Read the geometry of a lineage SVG (boxes, frames, labels, `new` pills, arrows) into a route.Scene, so the router sees the diagram as it is.

    sc, info = model.read(svg_text)
    info: {'lines': [...], 'titles': {num: title}, 'prs': {num}, 'right': x, 'bottom': y, 'legend': (x, y, w, h) or None}
"""
import itertools, math, os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from typing import NamedTuple
import collapse, route


class Arrow(NamedTuple):
    """One arrow, as svgmeta.arrow_of gives it. Callers use the names (x.kind), never the position (x[2]): a bare (a, b, kind) tuple,
    documented as (a, kind, b), was formatted in the wrong order by three scripts, each crashing only when an arrow got no label."""
    a: int
    b: int
    kind: str


def no_label(x: Arrow) -> str:
    """The PROBLEM text for an arrow that found no place for its label: one wording, written once, for every script."""
    return '#%d %s #%d has no label: no place on it or beside it' % (x.a, x.kind, x.b)


def count_arrows(text: str) -> int:
    """Arrows drawn in the picture (path lines with an arrowhead). move.py and reroute.py compare it before and after their work."""
    return sum(1 for ln in text.split('\n') if ln.startswith('<path d="M') and 'marker-end' in ln)


def arrow_points(line):
    d = line.split('"')[1]
    return [(float(a), float(b)) for a, b in re.findall(r'(-?[\d.]+),(-?[\d.]+)', re.sub(r'A[^L]*', '', d))]


MARKER_KIND = {'h-child': 'child', 'h-closed': 'closed by', 'h-work': 'work done by', 'h-led': 'led to', 'h-blocked': 'blocked by',
               'h-resolved': 'blocked by', 'h-ref': 'related', 'h-cross': 'supersedes', 'h-evid': 'evidence, does not close', 'h-dup': 'duplicate of'}


def _side(p, r, tol=1.5):
    x, y, w, h = r
    if y - 1 <= p[1] <= y + h + 1:
        if abs(p[0] - (x + w)) < tol:
            return 'R'
        if abs(p[0] - x) < tol:
            return 'L'
    if x - 1 <= p[0] <= x + w + 1:
        if abs(p[1] - y) < tol:
            return 'T'
        if abs(p[1] - (y + h)) < tol:
            return 'B'
    return None


SLOT = '<!--slot:%d-->'        # where a taken-out arrow's new path and label go; never left in a written file
_slots = itertools.count(1)
GROW_STEP = 40                  # px a frame grows by when an arrow between two of its boxes has no path inside it (frames.grow)
GROW_STEPS = 8                  # at most this many steps for one arrow; then it has no path, and the frame keeps its size


class Pending(NamedTuple):
    """An arrow to route: taken out of the picture (take_out) or new (new_arrow). Its path and label go where `slot` is."""
    a: int
    b: int
    kind: str
    line: str                   # the path line to write: its d is replaced, its other attributes stay
    slot: str                   # the marker in the text
    old: str                    # the markup taken out (path and label lines); put back when route_arrows(keep_old=True) finds no path
    sides: tuple = ('*', '*')   # the sides it must leave a and enter b by (route.route)
    pin: bool = False           # mark the new path as chosen by the user (svgmeta.pin)
    keep: bool = False          # an arrow the caller did not ask to route (a push cut it): with no path it keeps its old markup


class Routed(NamedTuple):
    text: str
    routed: list                # (a, b, bends, room): room is False when no path of the cheapest had room for the full label
    failed: list                # (a, b, kind, why)
    grown: list                 # (frame title, px) of every frame grown to make room
    unlabelled: list            # [Arrow] still with no label after finish()
    noted: list = []            # (a, b, kind, why): low-importance arrows routed now whose path was crazy: a note on box a instead


NOTED = 'low importance and a crazy path (route.is_crazy): not drawn'   # the start of the `why` of a Routed.noted arrow


def arrow_at(line, boxes=None):
    """The Arrow of a path line: its data-from, data-to and data-kind (svgmeta.py); for an old file without them, the boxes its two
    ends touch and the word of its arrowhead. None when that cannot be told."""
    import svgmeta
    at = svgmeta.arrow_of(line)
    if at:
        return Arrow(*at)
    if boxes is None:
        return None
    pts = arrow_points(line)
    ends = [next((n for n, r in boxes.items() if _side(p, r)), None) for p in (pts[0], pts[-1])]
    mk = re.search(r'marker-end="url\(#([\w-]+)\)"', line)
    return Arrow(ends[0], ends[1], MARKER_KIND.get(mk.group(1) if mk else '', 'related')) if None not in ends else None


def label_lines(lines, i):
    """Line indexes of the label of the arrow on line i: a label of its word centred on one of its stretches (none: empty)."""
    return frames_mod().labels_of(lines, [i]).get(i, range(0))


def take_out(text, idxs, sides=None, pin=(), keep=()):
    """Take the arrows on the lines `idxs` out of the picture, each with its label: a slot marker stays where the path was. Returns
    (text, [Pending]). sides {(a, b): (sa, sb)} and pin {(a, b)}: what route_arrows should keep to for those arrows. keep: line
    indexes of arrows a push cut, which nobody asked to route: one that finds no path keeps its old markup (check_diag.py then fails it, so the
    loss is never silent), rather than disappear."""
    lines = text.split('\n')
    boxes = None
    out, gone = [], set()
    labels = frames_mod().labels_of(lines, sorted(set(idxs)))
    for i in sorted(set(idxs)):
        at = arrow_at(lines[i])
        if at is None:
            boxes = boxes if boxes is not None else read(text)[0].boxes
            at = arrow_at(lines[i], boxes)
        if at is None:
            continue                                      # ends on no box: the checker reports it; nothing to route
        lab = list(labels.get(i, ()))
        slot = SLOT % next(_slots)
        out.append(Pending(at.a, at.b, at.kind, lines[i], slot, '\n'.join([lines[i]] + [lines[j] for j in lab]),
                           tuple((sides or {}).get(at[:2], ('*', '*'))), at[:2] in pin, i in keep))
        gone.update(lab)
        lines[i] = slot
    return '\n'.join(l for k, l in enumerate(lines) if k not in gone), out


def new_arrow(text, a, b, kind, sides=('*', '*')):
    """A slot for a new arrow, before the first box (arrows are drawn under the boxes). Returns (text, Pending)."""
    import draw
    slot = SLOT % next(_slots)
    k = text.find('<g id="n')
    k = text.rfind('\n', 0, k) + 1 if k >= 0 else text.rfind('</svg>')
    return text[:k] + slot + '\n' + text[k:], Pending(a, b, kind, draw.arrow([(0, 0), (0, 0)], kind, a, b), slot, '', tuple(sides))


def _old_path(p):
    """The path a Pending arrow had before it was taken out (one routed again), or None for a new arrow."""
    return arrow_points(p.line) if p.old else None


def _route_one(sc, p):
    """route.route_labelled for one Pending, or None (no path, or a box that is not drawn). An arrow routed again is never made
    crazier than its old path while a calmer candidate exists (route_labelled's old)."""
    if p.a not in sc.boxes or p.b not in sc.boxes:
        return None
    return route.route_labelled(sc, p.a, p.b, p.kind, *p.sides, old=_old_path(p))


def _by_importance(items, sc):
    """Pending arrows, the most important first (draw.IMPORTANCE), then the shortest (box centres)."""
    import draw
    centre = lambda n: (sc.boxes[n][0] + sc.boxes[n][2] / 2, sc.boxes[n][1] + sc.boxes[n][3] / 2) if n in sc.boxes else (0, 0)
    return sorted(items, key=lambda p: (-draw.IMPORTANCE.get(p.kind, 2), sum(abs(u - v) for u, v in zip(centre(p.a), centre(p.b)))))


STRETCH = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3)            # what a frame grows by, as a share of its size, in the stretches _plans tries
GROW_MAX = GROW_STEP * GROW_STEPS                        # px a frame may grow on one side for one arrow


def _plans(sc, p, frame):
    """The inflations to try for an arrow p with no path inside `frame`, in order: [(grow_by {side: px}, profile)] for
    frames.inflate. Where the arrow fits best is its path with the frame as a soft limit (route.route_soft): the sides that path
    goes past get the overshoot plus the border clearance (route.FPROX and two lattice steps), stretched graded toward them, then
    linear, then with no stretch (profile edge: the room opens at the border) once, 1.5 and 2 times the overshoot, at most GROW_MAX.
    Then, and first when no such path exists (the arrow is walled in by other arrows, not by the border), the stretches that open
    lanes everywhere in the frame, the smallest growth first (left and top count 1.5 times): graded toward one side, linear along
    one axis, a balloon on both, each by STRETCH of the frame's size; no side grows more than GROW_MAX."""
    soft = route.route_soft(sc, p.a, p.b, frame, *p.sides)
    x, y, w, h = frame
    need = {}
    if soft:
        over = {'left': x - min(q[0] for q in soft), 'right': max(q[0] for q in soft) - x - w,
                'top': y - min(q[1] for q in soft), 'bottom': max(q[1] for q in soft) - y - h}
        need = {sd: min(GROW_MAX, 10 * math.ceil((v + route.FPROX + 2 * route.G) / 10)) for sd, v in over.items() if v > 0}
    plans = [(need, pr) for pr in ('graded', 'linear')] if need else []
    plans += [({sd: min(GROW_MAX, 10 * math.ceil(v * f / 10)) for sd, v in need.items()}, 'edge') for f in (1, 1.5, 2)] if need else []
    size = {'left': w, 'right': w, 'top': h, 'bottom': h}
    shapes = [({sd: 1.0}, 'graded') for sd in ('top', 'bottom', 'left', 'right')] + \
             [({'top': .5, 'bottom': .5}, 'linear'), ({'left': .5, 'right': .5}, 'linear'),
              ({'left': .5, 'right': .5, 'top': .5, 'bottom': .5}, 'linear')]
    stretch = [({sd: v * f * size[sd] for sd, v in sh.items()}, pr) for f in STRETCH for sh, pr in shapes]
    stretch = [pl for pl in stretch if max(pl[0].values()) <= GROW_MAX]
    # the least growth first; growing left or up costs half as much again, since it moves the frame out of its column (or the
    # whole picture, past the top or the left edge)
    return plans + sorted(stretch, key=lambda pl: sum(v * (1.5 if sd in ('left', 'top') else 1) for sd, v in pl[0].items()))


def _grow_for(text, p, frame, keep_out):
    """Grow `frame` for the arrow p, which has no path inside it, by the first of _plans after which p has a path inside it
    (frames.inflate: the frame's area grows, its content is stretched, its neighbours move rigidly; nothing is routed but p, and an
    arrow whose corridor step found no room, which must find a path too: a growth is taken whole or not at all). A cut arrow that
    was already invalid before (an input fault) does not veto it: with no path it keeps its old markup.
    Returns (text with all of them drawn, scene, [(Pending, route_labelled result)], description), or None."""
    lines0 = text.split('\n')
    was_bad = {(arrow_at(lines0[i]) or (0, 0))[:2] for i in invalid(text)}
    fm = frames_mod()
    for grow_by, profile in _plans(scene(text, keep_out), p, frame):
        push = fm.inflate(text, frame, grow_by, profile)
        lines1 = push.text.split('\n')                   # what the inflation left invalid (a step too near something) is routed too
        broken = [i for i in invalid(push.text) if (arrow_at(lines1[i]) or (0, 0))[:2] not in was_bad]
        t, cut = take_out(push.text, sorted(set(push.cut) | set(broken)))
        sc = scene(t, keep_out)
        if _route_one(sc, p) is None:                     # p first, alone: most plans fail here, at the cost of one search
            continue
        drawn = []
        for q in [p] + _by_importance(cut, sc):
            res = _route_one(sc, q)
            if res is None and q is not p and (q.a, q.b) in was_bad:
                t = t.replace(q.slot, q.old, 1)
                sc = scene(t, keep_out)
                continue
            if res is None:
                break
            t = _fill(t, sc, q, res)
            drawn.append((q, res))
        else:
            moved = '; '.join('%s %s' % (_frame_title(t, nw)[:24], _shift_text(old, nw)) for old, nw in push.frames)
            desc = '%s %s; frames: %s; corridor steps: %d; routed again besides it: %d' % (
                profile, ', '.join('%s %dpx' % (sd, round(v)) for sd, v in grow_by.items() if v > 0), moved,
                fm.STATS.get('jogs', 0), len(drawn) - 1)
            return t, sc, drawn, desc
    return None


def _shift_text(old, new):
    """How a frame changed: grown (w, h) and moved (x, y), in px."""
    parts = ['%s %+d' % (k, round(b - a)) for k, a, b in (('x', old[0], new[0]), ('y', old[1], new[1]), ('w', old[2], new[2]),
                                                           ('h', old[3], new[3])) if abs(b - a) > .5]
    return '(%s)' % ' '.join(parts)


def frames_mod():
    import frames                                         # here: frames.py is imported only by the scripts that grow frames
    return frames


def scene(text, keep_out=()):
    """read(text)[0], with the keep-out rectangles as boxes under keys no box has (-1, -2, ...)."""
    sc, _ = read(text)
    for k, r in enumerate(keep_out):
        sc.boxes[-1 - k] = tuple(r)
    return sc


def route_arrows(text, pending, keep_out=(), keep_old=False):
    """Route every Pending arrow in the picture as it is, the most important first (draw.IMPORTANCE), then the shortest, each in the
    picture with the ones before it. Each path must leave room for its label (route.route_labelled: the cheapest of a few cheapest
    that has room, else the cheapest). An arrow between two boxes of one frame stays in that frame: when the frame has no room for
    it, the frame grows down (frames.grow, the one operation that makes room, which pushes down what lies below and cuts the arrows
    that ran through it; _grow_for routes them in the same step, and takes the growth only when all of them find a path).
    An arrow with no path is left out. keep_old: the arrows are routed one at a time with the others still drawn as they were, and
    one with no path keeps the markup it had (so an old path is never put back into channels that others took while it was out).
    A new path is made only where it is worth it: a low-importance arrow (draw.IMPORTANCE 1: related, mentioned) that the caller asked
    to route (new, or routed again now; not one a push cut, Pending.keep) and whose best path is crazy (route.is_crazy) is not drawn.
    It becomes a note on its tail box ("Related: #N.", draw.LOW_NOTE; svg_state.add_note, where there is room) and goes into the
    metadata's "nopath" with the reason (Routed.noted). An arrow that is drawn and not routed now is never touched by this.
    Then the arrows that had no room for their label are tried once more in the finished picture (retry_short), and finish():
    jump arcs, labels. Returns a Routed. The text holds no slot afterwards."""
    import draw
    sc = scene(text, keep_out)
    queue = _by_importance(pending, sc)
    if keep_old:                                          # everything back as it was; each arrow is taken out on its turn
        for p in queue:
            text = text.replace(p.slot, p.old, 1)
        sc = scene(text, keep_out)
    results, failed, grown, noted = {}, [], [], []
    while queue:
        p = queue.pop(0)
        key = (p.a, p.b, p.kind)
        if key in results:
            continue                                      # already routed again by a growth that cut it
        if keep_old:
            lines = text.split('\n')
            i = next((i for i, ln in enumerate(lines) if svgmeta_arrow(ln) == key), None)
            if i is None:
                continue
            text, got = take_out(text, [i])
            p = got[0]._replace(sides=p.sides, pin=p.pin, keep=p.keep)
            sc = scene(text, keep_out)
        res = _route_one(sc, p)
        if res and not p.keep and draw.IMPORTANCE.get(p.kind, 2) == 1 and route.is_crazy(res[0]):
            noted.append((p.a, p.b, p.kind))              # not worth a crazy path: a note instead (docstring)
            text = text.replace(p.slot, '', 1)
            continue
        drawn = [(p, res)] if res else []
        fr = route.common_frame(sc, p.a, p.b) if res is None and p.a in sc.boxes and p.b in sc.boxes else None
        if fr:
            title = _frame_title(text, fr)
            more = _grow_for(text, p, fr, keep_out)
            if more:
                text, sc, drawn, how = more
                grown.append((title, '#%d -> #%d: %s' % (p.a, p.b, how)))
        if not drawn:
            why = 'a box is not in the diagram' if p.a not in sc.boxes or p.b not in sc.boxes else \
                'no path inside its frame, even inflated (soft-limit sides to %dpx, stretches to %d%% of its size)' % (GROW_MAX, 100 * STRETCH[-1]) \
                if fr else 'no path'
            failed.append((p.a, p.b, p.kind, why))
            text = text.replace(p.slot, p.old if keep_old or p.keep else '', 1)
            if (keep_old or p.keep) and p.old:
                sc = scene(text, keep_out)
            continue
        if not fr:
            text = _fill(text, sc, p, res)
        for q, r in drawn:
            results[(q.a, q.b, q.kind)] = (len(r[0]) - 2, r[2])
    text, noted = _note_instead(text, noted)
    own = {p.slot for p in pending}                       # only this call's slots: a caller may still hold others (add_nodes, settle)
    text = '\n'.join(l for l in text.split('\n') if l not in own)
    routed = [(a, b, bends, room) for (a, b, _), (bends, room) in results.items()]
    kinds = {(a, b): k for a, b, k in results}
    text, unlabelled = finish(text, list(kinds), room=False)
    routed, again = retry_short(text, routed, keep_out, kinds)
    text, unlabelled = finish(again, list(kinds))         # with room: no arrow is left without a label
    return Routed(text, routed, failed, grown, unlabelled, noted)


def _note_instead(text, noted):
    """route_arrows' low-importance arrows with a crazy path: a note on the tail box and a "nopath" record each. Returns (text,
    [(a, b, kind, why)])."""
    import draw, svg_state, svgmeta
    out = []
    for a, b, kind in noted:
        text, why = svg_state.add_note(text, a, '%s #%d.' % (draw.LOW_NOTE.get(kind, 'See'), b))
        reason = NOTED + ('; a note on #%d instead' % a if why is None else '; no note on #%d (%s): name it there by hand' % (a, why))
        meta = svgmeta.read(text)
        if meta is not None:
            svgmeta.add_nopath(meta, a, b, kind, reason)
            text = svgmeta.write(text, meta)
        out.append((a, b, kind, reason))
    return text, out


def svgmeta_arrow(line):
    """(a, b, kind) of an arrow line that carries them, else None."""
    at = arrow_at(line)
    return tuple(at) if at else None


def retry_short(text, routed, keep_out=(), kinds=None):
    """Rip-up and retry of the arrows that had no room for their label (routed: [(a, b, bends, room)]; kinds {(a, b): kind}): each
    was routed before the arrows after it were drawn; in the finished picture one of its cheapest paths may have room. A new path is
    kept only when it has. Returns (routed, text)."""
    routed = list(routed)
    for k, (a, b, bends, room) in enumerate(routed):
        if room:
            continue
        lines = text.split('\n')
        want = (a, b, (kinds or {}).get((a, b)))
        i = next((i for i, ln in enumerate(lines) if (svgmeta_arrow(ln) or ())[:2] == (a, b) and want[2] in (None, svgmeta_arrow(ln)[2])), None)
        if i is None:
            continue
        t, got = take_out(text, [i])
        sc = scene(t, keep_out)
        res = _route_one(sc, got[0]) if got else None
        if res and res[2]:
            text = _fill(t, sc, got[0], res)
            routed[k] = (a, b, len(res[0]) - 2, True)
    return routed, text


def _fill(text, sc, p, res):
    """Write the path and label of a route_labelled result in p's slot, and add both to the scene. An arrow routed again whose new
    path is crazier than its old one (no calmer candidate existed) is reported on stderr as a PROBLEM."""
    import draw, svgmeta
    pts, lab, _ = res
    old = _old_path(p)
    if old and route.crazier(pts, old):
        print('PROBLEM: #%d -> #%d (%s) routed again is crazier than before: overshoot %dpx, %d turns back (before: %dpx, %d)'
              % ((p.a, p.b, p.kind) + tuple(round(v) for v in route.crazy(pts) + route.crazy(old))), file=sys.stderr)
    line = re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts), p.line, count=1)
    line = svgmeta.pin(line, True) if p.pin else line
    markup = [line] + (draw.label(p.kind, lab[0], lab[1], lab[2]) if lab else [])
    sc.arrows.append(pts)
    if lab:
        w = draw.label_width(p.kind)
        dx, dy = lab[2] or (0, 0)
        sc.labels.append((lab[0] + dx - w / 2, lab[1] + dy - 9, w, 18.0))
    return text.replace(p.slot, '\n'.join(markup), 1)


def _frame_title(text, rect):
    import collapse, svgmeta
    lines, _, _, frames = collapse.parse(text)
    f = next((f for f in frames if abs(f['x'] - rect[0]) < .5 and abs(f['y'] - rect[1]) < .5), None)
    return svgmeta.frame_name(lines[f['tl']]) if f else '?'



def finish(text, pairs, room=True):
    """What every script does after it routed arrows, so that nothing is left for a later step: the jump arcs of the whole diagram
    (hops.py) and the red crosses, every label that now sits badly placed again (relabel, with the checker's 20px of shaft from a
    jump), and a label for every arrow that still has none (label_missing: no arrow is left without a label). Then, with room (the
    default; never inside a push's own routing), for the arrows the caller routed in this call (`pairs`, (a, b) each: new arrows,
    arrows routed on request, arrows a push or a repair routed again; None: every arrow, only for an explicit whole-chart run,
    tidy()): push.make_room for each that still has no label, or whose label still covers something (its end boxes move apart,
    push.py), and push.straighten for each that is crazy where a small push can save it. An old arrow the call did not route is
    never straightened or pushed for. Then labels_on_top: every
    label after every path. Last, svg_state.grey_resolved: a `blocked by` arrow whose blocker is closed or merged is grey again after
    it was drawn anew (and normal again once the blocker reopens). Returns (text, [Arrow] with no label)."""
    import hops
    text, _, _ = hops.add_hops(text)
    text, _, _ = relabel(text, hop_pad=route.LABEL_SHAFT)
    text, _, none = label_missing(text, None)
    import push                                           # push.DEPTH, not a global here: model.py may run as __main__ too
    if room and not push.DEPTH['n'] and os.environ.get('BBB_NO_PUSH') != '1':
        push.DEPTH['n'] += 1                              # finish() inside a push's own routing makes no room again
        try:
            only = None if pairs is None else {tuple(p[:2]) for p in pairs}
            text = push.make_room(text, only)
            text = push.straighten(text, only)
        finally:
            push.DEPTH['n'] -= 1
        text, _, _ = hops.add_hops(text)
        text, _, _ = relabel(text, hop_pad=route.LABEL_SHAFT)
        text, _, none = label_missing(text, None)
    import svg_state
    return svg_state.grey_resolved(labels_on_top(text))[0], none


def labels_on_top(text):
    """SVG has no z-index: what comes later in the file is painted on top, so a label written before a path is drawn under it (a
    routed path is written in its slot, its label beside it, and a later path crosses it). Every label (its rectangle and text lines)
    that comes before the last arrow path moves, in its order, to the label block: before the first label that follows the last path,
    else right after that path. Nothing else moves. Run by relabel() and finish(), so every script ends with it."""
    lines = text.split('\n')
    last = max((i for i, ln in enumerate(lines) if ln.startswith('<path d="M') and 'marker-end' in ln), default=-1)
    early, i = [], 0
    while i < last:
        lab = route.draw.label_at(lines, i)
        if lab:
            early += range(i, i + 1 + lab[4])
            i += 1 + lab[4]
        else:
            i += 1
    if not early:
        return text
    at = next((j for j in range(last + 1, len(lines)) if route.draw.label_at(lines, j)), last + 1)
    gone = set(early)
    return '\n'.join([ln for k, ln in enumerate(lines[:at]) if k not in gone] + [lines[k] for k in early] + lines[at:])


def invalid(text):
    """{line index: why} of every arrow that is not valid as drawn: an end that touches no box, a run that leaves the frame its two
    boxes are in, a run through a box, or a run closer than 14px beside another arrow or on top of it (the later one of the two; on
    top of an arrow that shares its tail box or its tip box is a fork's trunk, and valid)."""
    sc, info = read(text)
    lines = info['lines']
    arrows = [(i, arrow_points(ln)) for i, ln in enumerate(lines) if ln.startswith('<path d="M') and 'marker-end' in ln]
    out, box_ends = {}, {}
    for i, pts in arrows:
        ends = [next((n for n, r in sc.boxes.items() if _side(p, r)), None) for p in (pts[0], pts[-1])]
        box_ends[i] = ends
        if None in ends:
            out[i] = 'an end touches no box'
            continue
        fr = route.common_frame(sc, *ends)
        if fr and any(not (fr[0] - 1 <= x <= fr[0] + fr[2] + 1 and fr[1] - 1 <= y <= fr[1] + fr[3] + 1) for x, y in pts):
            out[i] = 'leaves the frame its two boxes are in'
            continue
        q = (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
        for (x, y, w, h) in sc.near('boxes', q):
            if any((o == 'h' and y + 1 < c < y + h - 1 and lo < x + w - 1 and hi > x + 1) or
                   (o == 'v' and x + 1 < c < x + w - 1 and lo < y + h - 1 and hi > y + 1) for o, c, lo, hi in route.segments(pts)):
                out[i] = 'runs through a box'
                break
    seen = []
    for i, pts in arrows:
        for o, c, lo, hi in route.segments(pts):
            for k, (o2, c2, lo2, hi2) in seen:
                fork = None not in box_ends[i] and (box_ends[i][0] == box_ends[k][0] or box_ends[i][1] == box_ends[k][1])
                if o == o2 and min(hi, hi2) - max(lo, lo2) > 20 and abs(c - c2) < 13.5 and (abs(c - c2) > 0.5 or not fork):
                    out.setdefault(i, 'runs closer than 14px beside another arrow, or on top of it')
        seen += [(i, sg) for sg in route.segments(pts)]
    return out


def repair(text, count_only=False, only=None):
    """Route again every arrow that is invalid (invalid()): a move or a collapse left an end off its box, a run through a box, or a
    run too close beside another arrow. only: a set of (a, b); then only those arrows are looked at. The others stay as they are.
    An arrow with no path keeps its old markup. Returns (text, rerouted, problems)."""
    bad = invalid(text)
    if only is not None:
        lines = text.split('\n')
        bad = {i: why for i, why in bad.items() if (arrow_at(lines[i]) or (None, None))[:2] in only}
    if count_only:
        return text, len(bad), []
    if not bad:
        return text, 0, []
    lines = text.split('\n')
    known = {i for i in bad if arrow_at(lines[i])}        # an arrow off its box is still known by its data-from and data-to
    problems = ['an arrow near (%d,%d) ends on no box and carries no data-from/data-to: draw it again with add_nodes.py'
                % arrow_points(lines[i])[0] for i in set(bad) - known]
    text, pend = take_out(text, sorted(known), keep=known)    # an operation broke them; nobody asked to route them (no note)
    res = route_arrows(text, pend, keep_old=True)
    problems += ['NO PATH for the arrow #%s -> #%s (%s): it stays as it was' % (a, b, why) for a, b, _, why in res.failed]
    problems += ['frame "%s" inflated (%s) to make room' % g for g in res.grown]
    problems += [no_label(x) for x in res.unlabelled]
    return res.text, len(res.routed), problems


def settle(before, text, touched=()):
    """After an operation changed box geometry (collapse.py, move.py): route again every arrow it left invalid (invalid() now, and
    valid in `before`, or in touched {(a, b)}), with its label, then finish(). So nothing is left for a later step to repair.
    Returns (text, rerouted, problems)."""
    old_lines, lines, touched = before.split('\n'), text.split('\n'), set(touched)
    was = {arrow_at(old_lines[i]) for i in invalid(before)}
    now = [i for i in invalid(text) if arrow_at(lines[i]) not in was or (arrow_at(lines[i]) or (0, 0))[:2] in touched]
    if not now:
        text, none = finish(text, list(touched))
        return text, 0, [no_label(x) for x in none]
    return repair(text, only={(arrow_at(lines[i]) or (0, 0))[:2] for i in now})


def replace_labels(old, new, idxs):
    """After arrows changed shape (same line indexes in `old` and `new`), take the label of each arrow in `idxs` off (found on its OLD
    path: a label of its word centred on one of its stretches) and place it again on its NEW path with route.place_label (20px of shaft;
    else the best place with less, reported). Returns (text, problems)."""
    import svgmeta
    lo_, ln_ = old.split('\n'), new.split('\n')
    found = {}                                             # arrow line -> (label line, number of lines)
    for i in idxs:
        at = svgmeta.arrow_of(lo_[i])
        if not at:
            continue
        segs = route.segments(arrow_points(lo_[i]))
        for j in range(len(lo_)):
            lab = route.draw.label_at(lo_, j)
            if lab and lab[5] == at[2] and j not in [v[0] for v in found.values()]:
                cx, cy = lab[0] + lab[2] / 2, lab[1] + lab[3] / 2
                if any((o == 'h' and abs(c - cy) < 1 and lo - 1 <= cx <= hi + 1) or (o == 'v' and abs(c - cx) < 1 and lo - 1 <= cy <= hi + 1) for o, c, lo, hi in segs):
                    found[i] = (j, 1 + lab[4])
                    break
    drop = {k for j, m in found.values() for k in range(j, j + m)}
    keep = [l if k not in drop else None for k, l in enumerate(ln_)]
    sc, _ = read('\n'.join(l for l in keep if l is not None))
    problems = []
    for i in idxs:
        at = svgmeta.arrow_of(ln_[i])
        if i not in found or not at:
            continue
        pts = arrow_points(ln_[i])
        lab = route.place_label_any(sc, pts, at[2])
        if not lab or lab[3]:
            problems.append('label of #%d %s #%d: %s' % (at[0], at[2], at[1], 'WARN: less than 20px of shaft' if lab else 'no straight stretch: it is left off'))
        if lab:
            w = route.draw.label_width(at[2])
            dx, dy = lab[2] or (0, 0)
            sc.labels.append((lab[0] + dx - w / 2, lab[1] + dy - 9, w, 18))
            keep[found[i][0]] = '\n'.join(route.draw.label(at[2], lab[0], lab[1], lab[2]))
    return '\n'.join(l for l in keep if l is not None), problems


def off_middle(pts, cx, cy, tol=6):
    """Is the label at (cx, cy) more than tol px from the middle of a straight arrow's shaft (tail to the base of the head)? check_diag.py
    fails 12.5px. An arrow with a bend is never off its middle here."""
    p = route.straight([tuple(x) for x in pts])
    if len(p) != 2:
        return False
    (x0, y0), (x1, y1) = p
    if abs(y0 - y1) < .01:
        return abs(cx - (x0 + x1 - 11 * (1 if x1 > x0 else -1)) / 2) > tol
    return abs(cy - (y0 + y1 - 11 * (1 if y1 > y0 else -1)) / 2) > tol


def relabel(text, hop_pad=0, redo=()):
    """Put every label that does not sit well on its arrow (it covers another arrow, a box or a label, or is off its arrow) on a better
    straight stretch. Returns (text, fixed, failed): the number of labels moved, and (x, y, reason) for each label that found no good place.
    A label with no arrow under it goes back to the nearest arrow of its word that has no label. hop_pad: a label nearer than this to a
    jump arc counts as badly placed (0: only one that covers an arc; build.py passes 20, the shaft the checker asks for). redo: line
    indexes of arrows whose labels are placed again even when they sit well (fit_heights.py passes the arrows it changed). An arrow's
    word is its data-kind (svgmeta.py), else the word of its arrowhead."""
    import svgmeta
    sc, info = read(text)
    lines = info['lines']
    fixed, failed = 0, []
    kinds, redo_k = [], set()                               # the word of each arrow (same order as sc.arrows); the arrows to redo
    for i, ln in enumerate(lines):
        if ln.startswith('<path d="M') and 'marker-end' in ln:
            at = svgmeta.arrow_of(ln)
            mk = re.search(r'marker-end="url\(#([\w-]+)\)"', ln)
            if i in redo:
                redo_k.add(len(kinds))
            kinds.append(at[2] if at else (MARKER_KIND.get(mk.group(1)) if mk else None))

    def on_arrow(k, cx, cy):
        return any((o == 'h' and abs(c - cy) < 1 and lo <= cx <= hi) or (o == 'v' and abs(c - cx) < 1 and lo <= cy <= hi) for o, c, lo, hi in route.segments(sc.arrows[k]))

    def distance(k, cx, cy):
        if not route.segments(sc.arrows[k]):              # an arrow of no length has no stretch to carry a label
            return 1e18
        return min((abs(c - cy) + max(0, lo - cx, cx - hi)) if o == 'h' else (abs(c - cx) + max(0, lo - cy, cy - hi)) for o, c, lo, hi in route.segments(sc.arrows[k]))

    labelled = set()                                        # arrows that carry a label now
    for i in range(len(lines)):
        lab = route.draw.label_at(lines, i)
        if lab:
            labelled |= {k for k in range(len(sc.arrows)) if on_arrow(k, lab[0] + lab[2] / 2, lab[1] + lab[3] / 2)}
    for i, ln in enumerate(lines):
        lab = route.draw.label_at(lines, i)
        if not lab:
            continue
        x, y, w, h, _, word = lab
        rect = route.draw.label_box(lines, i)                  # as drawn: a label beside its shaft is shifted
        shift = route.draw.label_shift(ln)
        cx, cy = x + w / 2, y + h / 2                          # on the shaft, for every label
        own, orphan, own_k = None, False, None
        for k in range(len(sc.arrows)):
            if on_arrow(k, cx, cy) and (kinds[k] == word or own is None):
                own, own_k = sc.arrows[k], k
        if own is None:                                    # a label with no arrow under it (an arrow moved and left it behind):
            free = [k for k in range(len(sc.arrows)) if kinds[k] == word and k not in labelled]   # give it back to the nearest arrow of its word that has no label
            if free:
                k = min(free, key=lambda k: distance(k, cx, cy))
                own, orphan = sc.arrows[k], True
                labelled.add(k)
        with sc.hide('labels', rect) as others:            # the label is tested against everything but itself
            if own is not None and not orphan and own_k not in redo_k and not route._hit(rect, others, own=own, hop_pad=hop_pad) \
                    and (not off_middle(own, cx, cy) if not shift else route.place_label(others, own, word, w, h, strict=False) is None):
                continue                                    # sits well (a label beside its shaft: while the shaft is still too short)
            if own is None or word not in route.draw.EDGE:
                failed.append((round(cx), round(cy), 'no arrow of this word to attach the label to'))
                continue
            new, nshift = route.place_label(others, own, word, w, h, shaft=route.LABEL_SHAFT) or route.place_label(others, own, word, w, h), None
            if not new:                                     # no place with the full 20px of shaft: take the best place with 8px and say so
                new = route.place_label(others, own, word, w, h, strict=False)
                if new:
                    failed.append((round(new[0]), round(new[1]), 'WARN: the label has less than 20px of shaft (a short arrow)'))
                else:                                       # a shaft too short for any label: beside it
                    bs = route.place_label_beside(others, own, word, w, h)
                    rx = None if bs else route.place_label(others, own, word, w, h, relaxed=True)
                    if bs:
                        new, nshift = bs[:2], bs[2:]
                    elif rx:                                # the soft rules give way; the label still covers nothing
                        new = rx
                        failed.append((round(new[0]), round(new[1]), 'WARN: the label has less than 20px of shaft (relaxed)'))
                    else:
                        failed.append((round(cx), round(cy), 'no straight stretch long enough for this label'))
                        continue
        route.draw.move_label(lines, i, new[0], new[1], nshift)
        dx, dy = nshift or (0, 0)
        sc.labels.remove(tuple(rect))                      # the one change to the labels: only a label that moved costs a new index
        sc.labels.append((new[0] + dx - w / 2, new[1] + dy - h / 2, w, h))
        fixed += 1
    return labels_on_top('\n'.join(lines)), fixed, failed


def label_missing(text: str, pairs) -> tuple[str, int, list[Arrow]]:
    """Give a label to each arrow between the pairs [(a, b)] (None: every arrow) that has none, in the picture as it is now
    (route.place_label_any, down to its relaxed try). A script that routes an arrow places its label before hops.py draws the jump
    arcs, and a straight arrow's label may only sit at its middle: when a crossing line is there, the label found no place and was
    left off; with the arcs drawn, the arrow is cut in two pieces and one of them may carry it. Run it after hops.py and relabel().
    Returns (text, labels added, [Arrow] still with none)."""
    import svgmeta
    sc, info = read(text)
    lines = info['lines']
    want = None if pairs is None else {tuple(p) for p in pairs}
    centres = [(l[0] + l[2] / 2, l[1] + l[3] / 2) for l in
               (route.draw.label_at(lines, i) for i in range(len(lines))) if l]
    added, ins = 0, []
    none: list[Arrow] = []
    for ln in lines:
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if not at or (want is not None and (at[0], at[1]) not in want) or at[2] not in route.draw.EDGE:
            continue
        pts = arrow_points(ln)
        segs = route.segments(route.straight([tuple(p) for p in pts]))
        if any((o == 'h' and abs(c - cy) < 1 and lo <= cx <= hi) or (o == 'v' and abs(c - cx) < 1 and lo <= cy <= hi)
               for o, c, lo, hi in segs for cx, cy in centres):
            continue
        lab = route.place_label_any(sc, pts, at[2])
        if not lab:
            none.append(Arrow(*at))
            continue
        w = route.draw.label_width(at[2])
        dx, dy = lab[2] or (0, 0)
        sc.labels.append((lab[0] + dx - w / 2, lab[1] + dy - 9, w, 18))
        ins += route.draw.label(at[2], lab[0], lab[1], lab[2])
        added += 1
    if ins:
        k = next((i for i in range(len(lines)) if route.draw.label_at(lines, i)), None)
        k = k if k is not None else next((i for i, l in enumerate(lines) if l == '<!--legend-->'), len(lines) - 2)
        lines[k:k] = ins
    return labels_on_top('\n'.join(lines)), added, none


def read(text, bounds=None):
    lines, box, pop, frame = collapse.parse(text)
    boxes = {n: (b['x'], b['y'], b['w'], b['h']) for n, b in box.items()}
    frames = [(f['x'], f['y'], f['w'], f['h']) for f in frame]
    labels = []
    for i, ln in enumerate(lines):
        lab = route.draw.label_box(lines, i)
        if lab:
            labels.append(lab)                                      # as drawn (beside its shaft too); the real height: a two-line label is 30px
        m = re.match(r'<text class="ftl" x="([\d.-]+)" y="([\d.-]+)">([^<]*)', ln)
        if m:
            labels.append((float(m.group(1)) - 4, float(m.group(2)) - 20, 8.5 * len(m.group(3)) + 40, 30.0))
    pills = [(float(m.group(1)) - 26, float(m.group(2)) - 26, 52.0, 52.0) for m in re.finditer(r'<g transform="rotate\(-45 ([\d.]+) ([\d.]+)\)">', text)]
    arrows = [arrow_points(ln) for ln in lines if ln.startswith('<path d="M') and 'marker-end' in ln]
    titles = {}
    for n, b in box.items():
        grp = '\n'.join(lines[b['a']:b['b'] + 1])
        t = re.sub(r'<[^>]+>', '', ' '.join(re.findall(r'class="ttl"[^>]*>(.*?)</text>', grp)))
        titles[n] = t
    prs = {int(m.group(1)) for m in re.finditer(r'href="https://github.com/[^"/]+/[^"/]+/pull/(\d+)"', text)}
    legend = None
    m = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14" fill="#fbfaf6"', text)
    if m:
        legend = tuple(float(v) for v in m.groups())
    right = max([b[0] + b[2] for b in boxes.values()] + [f[0] + f[2] for f in frames] + [0])
    bottom = max([b[1] + b[3] for b in boxes.values()] + [f[1] + f[3] for f in frames] + [0])
    if bounds is None:
        bounds = (30, 165, (legend[0] - 25) if legend and legend[0] > right else right + 400, bottom + 400)
    sc = route.Scene(boxes, frames, labels, pills, arrows, bounds)
    for ln in lines:                                        # jump arcs: "L x,y A r r 0 0 1 x2,y2" (the arc spans x..x2 on one run)
        if ln.startswith('<path d="M') and ' A' in ln:
            for m in re.finditer(r'L(-?[\d.]+),(-?[\d.]+) A[\d. ]+? (-?[\d.]+),(-?[\d.]+)(?= L| ")', ln.split('"')[1]):
                sc.hops.append(tuple(float(v) for v in m.groups()))
    return sc, dict(lines=lines, titles=titles, prs=prs, right=right, bottom=bottom, legend=legend)


USAGE = """usage: model.py relabel IN.svg OUT.svg     put every badly placed label back on a good straight stretch of its own arrow
                                         (a label left behind by an old move goes back to the nearest unlabelled arrow of its word)
       model.py repair IN.svg OUT.svg      route again every arrow that is invalid (an end on no box, a run through a box)
       model.py tidy IN.svg OUT.svg        repair, then finish() over the whole chart: jump arcs, labels, room for every label
                                         (push.make_room), short paths for long detours (push.straighten), labels on top
Run check_diag.py afterwards."""


def tidy(text):
    """repair(), then finish() on every arrow (the room pass included). Returns (text, rerouted, problems)."""
    text, n, notes = repair(text)
    text, none = finish(text, None)
    return text, n, notes + [no_label(x) for x in none]


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in ('relabel', 'repair', 'tidy'):
        sys.exit(USAGE)
    src = open(sys.argv[2], encoding='utf-8').read()
    if sys.argv[1] == 'relabel':
        out, n, notes = relabel(src)
        print('%d labels moved' % n)
    elif sys.argv[1] == 'tidy':
        out, n, notes = tidy(src)
        print('%d arrows routed again' % n)
    else:
        out, n, notes = repair(src)
        print('%d arrows routed again' % n)
    for p in notes:
        print('PROBLEM', '%s near (%d,%d)' % (p[2], p[0], p[1]) if isinstance(p, tuple) else p)
    print(__import__('push').report(), end='')
    open(sys.argv[3], 'w', encoding='utf-8').write(out)
