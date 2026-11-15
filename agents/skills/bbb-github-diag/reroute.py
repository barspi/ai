#!/usr/bin/env python3
"""Route again some arrows of a diagram, in the diagram as it is. Boxes and the other arrows do not move.

usage: reroute.py IN.svg OUT.svg (A>B ...|--frame-leavers|--in-frame WORDS|--improve [N]) [--force]

--in-frame WORDS takes every arrow whose two boxes lie inside the one dotted frame whose title contains WORDS (case is ignored; more
than one such frame is an error). Use it after a frame was compacted, to route its inner arrows again. With --improve, only the
arrows named (A>B, --in-frame, --frame-leavers) are tried, so the rest of the picture keeps its routes.
--improve [N] takes every drawn arrow (or only the named ones), the most costly first (route.path_cost: steps, bends, crossings, frame borders, in the picture
with the other arrows), and keeps a new path only when it costs less than the old one; N passes (default 2: an arrow that improved can
free a channel for one tried before it). Use it after the routing rules change, or after boxes moved, to let every arrow take the
routes that opened up. It never makes an arrow worse by that measure, and it never touches a pinned arrow.
--pin A>B ... / --unpin A>B ...: mark (or unmark) arrows whose route the user chose (`data-pinned="1"` on the path, svgmeta.pin);
nothing is routed. move.py pins every arrow named in its --sides or --reroute.
A>B names one drawn arrow by its two boxes (its data-from and data-to, svgmeta.py). --frame-leavers takes every arrow whose two boxes are
in the same frame but whose path leaves that frame (check_diag.py fails them). They are taken out with their labels and
model.route_arrows routes them again in the picture as it is now: an arrow inside one frame never leaves it (the frame grows down when
it has no room, frames.grow), and each path leaves room for its label where one of the cheapest paths can. Then the jump arcs and every
label that sits badly are redone (model.finish). An arrow that finds no path keeps its old one and is printed. Nothing is written when the result has more invalid arrows than the input (exit 1), unless --force.
"""
import os, re, sys, tempfile
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draw, hops, model, route, svgmeta


def leaves_frame(text):
    """(a, b) of every drawn arrow whose two boxes share a frame while some point of its path is outside that frame."""
    sc, info = model.read(text)
    out = []
    for ln in info['lines']:
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if not at or at[0] not in sc.boxes or at[1] not in sc.boxes:
            continue
        fr = route.common_frame(sc, at[0], at[1])
        if fr and any(not (fr[0] - 1 <= x <= fr[0] + fr[2] + 1 and fr[1] - 1 <= y <= fr[1] + fr[3] + 1) for x, y in model.arrow_points(ln)):
            out.append(at[:2])
    return out


def in_frame(text, words):
    """(a, b) of every drawn arrow whose two boxes lie inside the dotted frame whose title contains `words`."""
    import collapse
    _, box, _, frames = collapse.parse(text)
    hit = [f for f in frames if words.lower() in f['name'].lower()]
    if len(hit) != 1:
        sys.exit('--in-frame %r: %d frames have it in their title: %s' % (words, len(hit), '; '.join(f['name'][:60] for f in hit)))
    f = hit[0]

    def inside(n):
        b = box.get(n)
        return b and f['x'] <= b['x'] and b['x'] + b['w'] <= f['x'] + f['w'] and f['y'] <= b['y'] and b['y'] + b['h'] <= f['y'] + f['h']
    out = []
    for ln in text.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at and inside(at[0]) and inside(at[1]) and at[:2] not in out:
            out.append(at[:2])
    return out


def costs(text):
    """{(a, b): path_cost} of every drawn arrow whose two boxes are drawn, each measured against the other arrows."""
    sc, info = model.read(text)
    out = {}
    for ln in info['lines']:
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at and at[0] in sc.boxes and at[1] in sc.boxes:
            out[at[:2]] = route.path_cost(sc, model.arrow_points(ln), at[0], at[1])
    return out


def bends_of(text):
    """{(a, b): (bends, corner points)} of every drawn arrow."""
    out = {}
    for ln in text.split('\n'):
        at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
        if at:
            p = route.straight(model.arrow_points(ln))
            out[at[:2]] = (len(p) - 2, tuple(p))
    return out


def _lines_of(text, pairs):
    """{(a, b): [line indexes]} of the drawn arrows with these ends."""
    out = {tuple(p): [] for p in pairs}
    for i, ln in enumerate(text.split('\n')):
        at = svgmeta.is_arrow(ln) and model.arrow_at(ln)
        if at and at[:2] in out:
            out[at[:2]].append(i)
    return out


def reroute(text, pairs, improve=False):
    """Returns (text, done [(a, b, bends, short label, old bends)], failed [(a, b, why)]).
    Without improve: the arrows are taken out with their labels and model.route_arrows routes them again (an arrow inside one frame
    never leaves it; the frame grows when it has no room); an arrow with no path keeps its old markup.
    improve: one arrow at a time, a new path is kept only when route.path_cost says it costs less than the old one; frames never grow."""
    found = _lines_of(text, pairs)
    failed = [(a, b, '%d drawn arrows with these ends' % len(v)) for (a, b), v in found.items() if len(v) != 1]
    one = [(p, v[0]) for p, v in found.items() if len(v) == 1]
    if not improve:
        bends0 = {p: len(route.straight(model.arrow_points(text.split('\n')[i]))) - 2 for p, i in one}
        t, pend = model.take_out(text, [i for _, i in one])
        res = model.route_arrows(t, pend, keep_old=True)
        failed += [(a, b, why + ': the old one stays') for a, b, _, why in res.failed]
        for g in res.grown:
            print('frame "%s" inflated (%s) to make room for an arrow' % g)
        return res.text, [(a, b, bends, not room, bends0.get((a, b), 0)) for a, b, bends, room in res.routed], failed
    done = []
    for (a, b), _ in one:
        lines = text.split('\n')
        i = _lines_of(text, [(a, b)])[(a, b)][0]
        if svgmeta.is_pinned(lines[i]):                    # the user chose this route
            continue
        old_pts = model.arrow_points(lines[i])
        t, (p,) = model.take_out(text, [i])
        sc = model.scene(t)
        res = route.route_labelled(sc, a, b, p.kind, *p.sides)
        if not res or route.path_cost(sc, res[0], a, b) >= route.path_cost(sc, old_pts, a, b) - 1:
            continue
        pts, lab, room = res
        line = re.sub(r'd="[^"]*"', 'd="M%s"' % ' L'.join('%s,%s' % (draw.fmt(x), draw.fmt(y)) for x, y in pts), p.line, count=1)
        text = t.replace(p.slot, '\n'.join([line] + (draw.label(p.kind, lab[0], lab[1], lab[2]) if lab else [])), 1)
        done.append((a, b, len(pts) - 2, not room, len(route.straight(old_pts)) - 2))
    return text, done, failed


def main():
    argv, passes, words = sys.argv[1:], 0, None
    if '--in-frame' in argv:
        k = argv.index('--in-frame')
        if k + 1 >= len(argv):
            sys.exit(__doc__)
        words = argv.pop(k + 1)
    if '--improve' in argv:
        k = argv.index('--improve')
        passes = 2
        if k + 1 < len(argv) and argv[k + 1].isdigit():
            passes = int(argv.pop(k + 1))
    args = [a for a in argv if not a.startswith('--')]
    if len(args) < 2:
        sys.exit(__doc__)
    src, out = args[0], args[1]
    text = open(src, encoding='utf-8').read()
    pairs = [tuple(int(x.lstrip('#')) for x in p.split('>')) for p in args[2:]]
    if '--pin' in argv or '--unpin' in argv:                 # mark routes the user chose; nothing is routed
        lines = text.split('\n')
        for k, ln in enumerate(lines):
            at = svgmeta.is_arrow(ln) and svgmeta.arrow_of(ln)
            if at and at[:2] in pairs:
                lines[k] = svgmeta.pin(ln, '--pin' in argv)
                print('#%d -> #%d %s' % (at[0], at[1], 'pinned' if '--pin' in argv else 'unpinned'))
        open(out, 'w', encoding='utf-8').write('\n'.join(lines))
        return
    if '--frame-leavers' in sys.argv:
        pairs += [p for p in leaves_frame(text) if p not in pairs]
    if words:
        pairs += [p for p in in_frame(text, words) if p not in pairs]
        print('%d arrows inside the frame "%s"' % (len(pairs), words))
    if not pairs and not passes:
        print('nothing to route again')
        open(out, 'w', encoding='utf-8').write(text)
        return
    before = model.repair(text, count_only=True)[1]
    if passes:
        res, done, failed = text, [], []
        total0 = sum(costs(text).values())
        for _ in range(passes):
            cost = costs(res)
            order = sorted((p for p in cost if not pairs or p in pairs), key=lambda p: -cost[p])
            res, d, _ = reroute(res, order, improve=True)
            res, _, _ = hops.add_hops(res, marks=False)      # fresh arcs before the next pass reads the picture
            done += d
            if not d:
                break
        print('total path cost %.0f -> %.0f' % (total0, sum(costs(res).values())))
    else:
        res, done, failed = reroute(text, pairs)
    res, nolab = model.finish(res, [(d[0], d[1]) for d in done])    # jump arcs, labels: nothing left for a later step
    after = model.repair(res, count_only=True)[1]
    if after > before and '--force' not in sys.argv:
        print('REFUSED: %d arrows invalid after, %d before. Nothing written.' % (after, before))
        sys.exit(1)
    want, got = model.count_arrows(text), model.count_arrows(res)       # a failed arrow keeps its old path: none may go or come
    if got != want:
        print('REFUSED: %d arrows after, %d before. Nothing written.' % (got, want))
        sys.exit(1)
    open(out, 'w', encoding='utf-8').write(res)
    for x in nolab:
        print('PROBLEM', model.no_label(x))
    for a, b, bends, short, old_bends in done:
        print('#%d -> #%d: %d bends (was %d)%s' % (a, b, bends, old_bends, ' (WARN: no path of the cheapest had room for the full label)' if short else ''))
    if passes:                                             # what the user should look at: the arrows that took more bends
        b0, b1 = bends_of(text), bends_of(res)
        changed = [p for p in b1 if p in b0 and b0[p][1] != b1[p][1]]
        more = sorted((p for p in changed if b1[p][0] > b0[p][0]), key=lambda p: b0[p][0] - b1[p][0])
        print('%d arrows changed: %d with fewer bends, %d with as many, %d with more (each traded bends for crossings, frame borders or '
              'length: show these to the user, and pin a route the user prefers before the next --improve):'
              % (len(changed), sum(1 for p in changed if b1[p][0] < b0[p][0]), sum(1 for p in changed if b1[p][0] == b0[p][0]), len(more)))
        for p in more:
            print('  MORE BENDS #%d -> #%d: %d (was %d)' % (p[0], p[1], b1[p][0], b0[p][0]))
    for a, b, why in failed:
        print('PROBLEM #%d -> #%d: %s' % (a, b, why))
    print('next: check_diag.py %s' % out)


if __name__ == '__main__':
    main()
