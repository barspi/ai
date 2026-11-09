#!/usr/bin/env python3
"""Layout of a lineage graph: which column and row each box gets, where the frames go, and the easy arrows.

Pure geometry; no SVG text. build.py calls plan() and then draws. The method (all of it generic, nothing about one diagram):

1. Columns. The graph is read left to right: a box's column is the longest chain of forward arrows (child, follow-up, led to,
   closed by, ...) that reaches it. Arrows that may point back (blocked by, supersedes, related, ...) never set a column. A pure
   source moves next to its first child; a box with only weak arrows sits in the column of the box it is tied to.
2. Bands. Boxes of one dotted frame sit together; every frame is a horizontal band, stacked from top to bottom after the boxes that
   belong to no frame.
3. Rows. Inside a column the order starts as given, then follows the average height of the neighbours in the other columns
   (barycenter sweeps), which removes most crossings. Heights come from the neighbours too: a parent sits level with the middle of
   its children, a single child level with its parent (so the arrow is straight). Boxes keep their order and a minimum gap
   (isotonic regression), 28px, or 100px where a vertical arrow with a label joins two boxes. Then gaps close: a group no arrow
   joins moves up to its neighbours (compact_components), and an empty strip across a whole frame shrinks to 100px (close_strips).
4. Gaps between columns grow with the number of arrow lanes they hold (14px per lane, the widest label, margins).
5. Easy arrows (column to the next column, and vertical ones inside a column) get their exit and entry points, 16px (exits) and 22px
   (entries) apart on a box side, and their lanes in the gap, ordered by trial so that as few arrows as possible cross. The other
   arrows (they skip a column, point back, or have a box in the way) are left to route.py, which reads the arrows already placed.
"""
import os, sys

import draw, route

LEFT, TOP, STACK_GAP, VGAP = 80, 190, 28, 100
FRAME_TOP, FRAME_BOT, FRAME_L, FRAME_R, BAND_GAP = 46, 24, 60, 30, 34
LANE0, LANE = 66, 14
COLL_MIN = 62.0


def forward(kind):
    return draw.EDGE[kind][3]


def auto_columns(nums, edges):
    """Column of every box: the longest chain of forward arrows that reaches it (cycles are cut at the arrow that closes them)."""
    succ = {n: [] for n in nums}
    for a, b, k in edges:
        if forward(k) and a != b and a in succ and b in succ:
            succ[a].append(b)
    state, keep = {}, []
    sys.setrecursionlimit(max(1000, 10 * len(nums)))

    def dfs(u):
        state[u] = 1
        for v in succ[u]:
            if state.get(v) == 1:
                continue                      # closes a cycle: ignore this arrow for the columns
            keep.append((u, v))
            if v not in state:
                dfs(v)
        state[u] = 2

    for n in nums:
        if n not in state:
            dfs(n)
    preds = {n: [] for n in nums}
    for u, v in keep:
        preds[v].append(u)
    col = {}

    def depth(n):
        if n not in col:
            col[n] = 0
            col[n] = max([depth(p) + 1 for p in preds[n]] or [0])
        return col[n]

    for n in nums:
        depth(n)
    kids = {n: [] for n in nums}
    for u, v in keep:
        kids[u].append(v)
    for n in nums:                            # a pure source moves next to its nearest child
        if not preds[n] and kids[n]:
            col[n] = max(col[n], min(col[c] for c in kids[n]) - 1)
    linked = {n for u, v in keep for n in (u, v)}
    # Boxes with only weak arrows (blocked by, related, ...): their own columns from the longest chain of those arrows, read tail to head
    # (nine items blocked by one decision become a fan into it, not a stack in its column). A group of them tied to a box of the main
    # graph sits next to it: its tail one column to the left of that box, its head one column to the right.
    weak = [n for n in nums if n not in linked]
    ws = set(weak)
    c2 = _longest(weak, [(a, b) for a, b, k in edges if a in ws and b in ws and a != b])
    comp = {n: n for n in weak}

    def root_of(n):
        while comp[n] != n:
            comp[n] = comp[comp[n]]
            n = comp[n]
        return n

    for a, b, k in edges:
        if a in ws and b in ws:
            comp[root_of(a)] = root_of(b)
    groups = {}
    for n in weak:
        groups.setdefault(root_of(n), []).append(n)
    for mem in groups.values():
        ms = set(mem)
        tie = next(((x, col[y] - 1 if x == a else col[y] + 1) for a, b, k in edges for x, y in ((a, b), (b, a)) if x in ms and y in linked), None)
        off = (tie[1] - c2[tie[0]]) if tie else 0
        if tie and min(c2[n] for n in mem) + off < 0:  # never a new column in front of column 0 (it would push every box, the
            y_tie = next(y for a, b, k in edges for x, y in ((a, b), (b, a)) if x == tie[0] and y in linked)   # root's children too,
            off = col[y_tie] + 1 - min(c2[n] for n in mem)                     # out of the first column): go right of the tie box
        for n in mem:
            col[n] = c2[n] + off
    # A hub: three or more weak-only boxes point at one box (nine issues blocked by one decision). They form a fan in the column right
    # before the hub, like a root's children, so every one of those arrows is a short easy arrow. Left on their chains, they spread
    # over several columns and their arrows must climb over the boxes between, the knot this rule removes. The biggest hub goes first.
    into = {}
    for a, b, k in edges:
        if a in ws and a != b and b in col and not forward(k):
            into.setdefault(b, set()).add(a)
    moved = set()
    for h in sorted(into, key=lambda h: -len(into[h])):
        ps = into[h] - moved - {h}
        if len(into[h]) >= 3 and h not in moved:
            for p in ps:
                col[p] = col[h] - 1
            moved |= ps
    low = min(col.values()) if col else 0
    return {n: c - low for n, c in col.items()}


def _longest(nums, pairs):
    """Longest-chain column of each node over the arrows `pairs` (a, b); an arrow that closes a cycle is ignored."""
    succ = {n: [] for n in nums}
    for a, b in pairs:
        succ[a].append(b)
    state, keep = {}, []

    def dfs(u):
        state[u] = 1
        for v in succ[u]:
            if state.get(v) == 1:
                continue
            keep.append((u, v))
            if v not in state:
                dfs(v)
        state[u] = 2

    for n in nums:
        if n not in state:
            dfs(n)
    preds = {n: [] for n in nums}
    for u, v in keep:
        preds[v].append(u)
    col = {}

    def depth(n):
        if n not in col:
            col[n] = 0
            col[n] = max([depth(p) + 1 for p in preds[n]] or [0])
        return col[n]

    for n in nums:
        depth(n)
    return col


def isotonic(z):
    blocks = []
    for v in z:
        blocks.append([v, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    out = []
    for s, c in blocks:
        out += [s / c] * c
    return out


def slots(y, h, m, step):
    """y of m attach points on one side of a box: one at 60px from the top, several centred and `step` apart (less if the box is short)."""
    if m <= 1:
        return [y + min(60.0, h / 2)]
    st = min(step, max(14.0, (h - 32) / (m - 1)))
    c = y + h / 2
    return [c + (i - (m - 1) / 2) * st for i in range(m)]


def min_height(natural, m_out, m_in, collapsed):
    """Least box height that holds its attach points (exits 14px apart, entries 20px apart, 16px of margin at each end)."""
    need = max(32 + 14 * max(m_out - 1, 0), 32 + 20 * max(m_in - 1, 0))
    return max(natural, need) if not collapsed else max(collapsed if isinstance(collapsed, float) else COLL_MIN, 24 + 20 * max(m_out - 1, m_in - 1, 0))


PAIR_KINDS = ('closed by', 'work done by', 'evidence, does not close', 'revised by')   # an issue and its pull request: side by side


def fold_leaves(nums, edges, col, outside=()):
    """A column that holds only leaves (boxes with one arrow, to a box in another column) costs a whole column of width for a few boxes.
    Each such leaf moves into the column of the box it is tied to and sits right under it, with a short vertical arrow. Not folded: a
    box with arrows to other blocks (`outside`), and an issue with its pull request (they stay side by side). Returns {leaf: partner}
    and changes `col` in place (empty columns are removed)."""
    deg = {n: [] for n in nums}
    for a, b, k in edges:
        if a != b and a in deg and b in deg:
            deg[a].append((a, b, k))
            deg[b].append((a, b, k))
    sat = {}
    for c in sorted(set(col.values())):
        mem = [n for n in nums if col[n] == c]
        if mem and all(len(deg[n]) == 1 and n not in outside and deg[n][0][2] not in PAIR_KINDS for n in mem):
            for n in mem:
                a, b, k = deg[n][0]
                p = b if a == n else a
                if col[p] != c and p not in sat:
                    sat[n] = p
    for n, p in sat.items():
        col[n] = col[p]
    idx = {c: i for i, c in enumerate(sorted(set(col.values())))}
    for n in col:
        col[n] = idx[col[n]]
    return sat


def compact_components(nums, edges, col, y, H, members, top_b):
    """Boxes of one frame that no arrow joins form separate groups. Each group is placed by its own neighbours, so a small group (an
    issue and its pull request) can float away from the rest with an empty gap between. Close those gaps: every group, from the top
    down, moves up until it meets a box of its column (28px apart) or the top of its frame."""
    ms = set(members)
    comp = {n: n for n in members}

    def root(n):
        while comp[n] != n:
            comp[n] = comp[comp[n]]
            n = comp[n]
        return n

    for a, b, k in edges:
        if a in ms and b in ms:
            comp[root(a)] = root(b)
    groups = {}
    for n in members:
        groups.setdefault(root(n), []).append(n)
    if len(groups) < 2:
        return
    for g in sorted(groups.values(), key=lambda g: min(y[n] for n in g)):
        gs = set(g)
        up = min(y[n] - max([y[m] + H[m] + STACK_GAP for m in members if m not in gs and col[m] == col[n] and y[m] < y[n]] + [top_b])
                 for n in g)
        # a group that cannot rise (it is at the top already) moves down to the group under it instead, so the two read as one list
        floor = max(y[m] + H[m] for m in members)       # never below the frame's current bottom: the frame must not grow
        down = min([y[m] - (y[n] + H[n] + STACK_GAP) for n in g for m in members if m not in gs and col[m] == col[n] and y[m] > y[n]]
                   or [0.0])
        down = min([down] + [floor - (y[n] + H[n]) for n in g])
        move = -up if up > 0.5 else (down if down > 0.5 else 0.0)
        for n in g:
            y[n] += move


def close_strips(members, y, H, keep=VGAP):
    """An empty horizontal strip across a whole frame: no box of any column covers those rows. It appears when one long arrow joins
    two groups (so compact_components sees one group) and each group is centred on its own neighbours: a hub level with the middle of
    its many tails, a small chain level with its root. No straight arrow can cross such a strip (its two boxes would share rows), so
    moving every box under it up keeps every alignment; only the joining arrows get shorter. Each strip shrinks to `keep` px, room
    for one routed arrow and its label."""
    spans = sorted((y[n], y[n] + H[n]) for n in members)
    cuts, reach = [], spans[0][1]
    for top, bot in spans[1:]:
        if top - reach > keep:
            cuts.append((reach, top - reach - keep))   # rows below `reach` move up by the excess
        reach = max(reach, bot)
    for at, excess in reversed(cuts):
        for n in members:
            if y[n] >= at:
                y[n] -= excess


Y_METHOD = os.environ.get('LAYOUT_Y', 'sweep')     # 'sweep' (barycenter averages + gap passes) or 'simplex' (on trial)


def simplex_rows(members, edges, col, y, H, vlink, offs):
    """Rows by network simplex (netsimplex.py; Gansner et al. 1993, section 4.2). The order inside each column is kept (it comes from
    the barycenter sweeps); the rows minimise  sum of weight(kind) * |attach(a) - attach(b)|  over the arrows of the frame, where
    attach is the point the arrow leaves or enters (offs), and weight is draw.pull (the importance tiers). Boxes next to each other in
    a column keep their gap: 28px, or 100px for a vertical arrow. Gaps that no arrow needs are not kept: closing them shortens arrows."""
    import netsimplex
    ms = sorted(members, key=lambda n: y[n])
    idx = {n: i for i, n in enumerate(ms)}
    cons = []
    cols = {}
    for n in ms:
        cols.setdefault(col[n], []).append(n)
    for lst in cols.values():
        for a, b in zip(lst, lst[1:]):
            gap = VGAP if frozenset((a, b)) in vlink else STACK_GAP
            cons.append((idx[a], idx[b], int(round(H[a] + gap)), 0))
    k = len(ms)
    for a, b, kind in edges:
        if a in idx and b in idx and a != b:
            w = max(1, int(round(10 * draw.pull(kind))))
            oa, ob = int(round(offs(a))), int(round(offs(b)))
            cons += [(k, idx[a], -oa, w), (k, idx[b], -ob, w)]    # aux node z <= attach(a), z <= attach(b): cost w*|attach(a)-attach(b)|
            k += 1
    r = netsimplex.solve(k, cons)
    top = min(y[n] for n in ms)
    base = min(r[idx[n]] for n in ms)
    for n in ms:
        y[n] = top + r[idx[n]] - base


def plan(nodes, edges, left=None, top=None, col_override=None, outside=(), degree=None):
    """nodes: [{num, h (natural height), frame (name or None), collapsed (bool), title_w (frame title width, optional)}], edges: [(a, b, kind)].
    Returns a dict: rect {num: (x, y, w, h)}, frames [(name, x, y, w, h)], easy [(a, b, kind, points)], hard [(a, b, kind)],
    size (W, H without the legend), right (right edge of the boxes), col {num: column}. left/top move the origin; col_override fixes the
    column of some boxes (plan_blocks uses it to spread boxes that have no arrow inside their frame); `outside` names the boxes that
    have arrows to other blocks (they are never folded under a neighbour)."""
    LEFT_, TOP_ = (LEFT if left is None else left), (TOP if top is None else top)
    nums = [n['num'] for n in nodes]
    info = {n['num']: n for n in nodes}
    col = auto_columns(nums, edges)
    if col_override:
        col.update(col_override)
    sat = fold_leaves(nums, edges, col, set(outside))
    ncol = max(col.values()) + 1 if col else 1
    # bands: unframed first, then frames in order of first appearance
    names = []
    for n in nodes:
        if n.get('frame') and n['frame'] not in names:
            names.append(n['frame'])
    band = {n['num']: (names.index(n['frame']) + 1 if n.get('frame') else 0) for n in nodes}
    nb = len(names) + 1

    easy_pairs = [(a, b, k) for a, b, k in edges if col[b] == col[a] + 1]
    vert_pairs = [(a, b, k) for a, b, k in edges if col[b] == col[a] and a != b]
    m_out = {n: sum(1 for a, b, k in easy_pairs if a == n) for n in nums}
    m_in = {n: sum(1 for a, b, k in easy_pairs if b == n) for n in nums}
    H = {n: min_height(info[n]['h'], m_out[n], m_in[n], info[n].get('collapsed')) for n in nums}
    # Room for the arrows the router adds later (to other frames, skipping a column, pointing back). They leave and enter by the left
    # and right sides (the top and bottom face neighbours 28px away) and keep 22px from each other (route.HARD_H). Without this a short
    # (collapsed) box with many arrows has full sides, and its most important arrows end as NO PATH. `degree`: all arrows of a box.
    for n in nums:
        routed = (degree or {}).get(n, 0) - m_out[n] - m_in[n]
        if routed >= 1:                           # per side: its drawn exits (16px apart) or entries (22px), route.HARD_H clear of them,
            r_out, r_in = (routed + 1) // 2, routed // 2                  # then its share of the routed arrows, route.HARD_H apart, 20px margins
            need = lambda m, step, r: 40 + step * max(m - 1, 0) + (route.HARD_H * r + (route.HARD_H if m else 0) if r else 0)
            H[n] = max(H[n], need(m_out[n], 16, r_out), need(m_in[n], 22, r_in))

    nbr_left = {n: [] for n in nums}
    nbr_right = {n: [] for n in nums}
    vlink = set()
    for a, b, k in edges:
        if a == b:
            continue
        if col[a] < col[b]:
            nbr_right[a].append(b)
            nbr_left[b].append(a)
        elif col[a] > col[b]:
            nbr_left[a].append(b)
            nbr_right[b].append(a)
        else:
            vlink.add(frozenset((a, b)))

    def fan(n):
        return len(nbr_left[n]) > 1 or len(nbr_right[n]) > 1

    def att(n, y):
        return y[n] + (H[n] / 2 if fan(n) else min(60.0, H[n] / 2))

    def offs(n):
        return H[n] / 2 if fan(n) else min(60.0, H[n] / 2)

    def after_partner(rank):                      # a folded leaf comes right after the box it is tied to
        for n, p in sat.items():
            rank[n] = rank[p] + 1e-3
        return rank

    rank = after_partner({n: i for i, n in enumerate(nums)})
    best = None
    for rounds in range(6):
        y, band_top, top = {}, [], TOP_
        for b in range(nb):
            members = [n for n in nums if band[n] == b]
            if not members:
                band_top.append(top)
                continue
            top_b = top + (FRAME_TOP if b else 0)
            band_top.append(top_b)
            cols = {}
            for n in sorted(members, key=lambda n: rank[n]):
                cols.setdefault(col[n], []).append(n)
            for c, lst in cols.items():
                t = top_b
                for n in lst:
                    y[n] = t
                    t += H[n] + STACK_GAP

            def settle(c, target):
                lst = cols[c]
                gaps = [VGAP if frozenset((lst[i], lst[i + 1])) in vlink else STACK_GAP for i in range(len(lst) - 1)]
                off, o = [], 0.0
                for i, n in enumerate(lst):
                    off.append(o)
                    o += H[n] + (gaps[i] if i < len(gaps) else 0)
                z = isotonic([target[n] - off[i] for i, n in enumerate(lst)])
                for i, n in enumerate(lst):
                    y[n] = z[i] + off[i]

            def wants(n):
                if n in sat and sat[n] in y:                               # a folded leaf: right under its box
                    return y[sat[n]] + H[sat[n]] + VGAP
                if len(nbr_left[n]) == 1 and nbr_left[n][0] in y:          # a single parent: level with it, so the arrow is straight
                    return att(nbr_left[n][0], y) - offs(n)
                got = []
                for side in (nbr_left[n], nbr_right[n]):
                    pts = [att(m, y) for m in side if m in y]
                    if pts:
                        got.append(sum(pts) / len(pts) - offs(n))
                return sum(got) / len(got) if got else y[n]

            for _ in range(8):
                for c in sorted(cols):
                    settle(c, {n: wants(n) for n in cols[c]})
                for c in sorted(cols, reverse=True):
                    settle(c, {n: wants(n) for n in cols[c]})
            shift = top_b - min(y[n] for n in members)
            for n in members:
                y[n] += shift
            bottom = max(y[n] + H[n] for n in members)
            top = bottom + (FRAME_BOT if b else 0) + BAND_GAP
        ncross = sum(1 for a, b, k in easy_pairs for a2, b2, k2 in easy_pairs
                     if (a, b) < (a2, b2) and (y[a] - y[a2]) * (y[b] - y[b2]) < 0)
        if best is None or ncross < best[0]:
            best = (ncross, dict(y))
        # next round: one sweep, a column at a time (left to right, then right to left on the next round). A column is ordered by the
        # NEW positions of its neighbours on the side already swept, so a pull request lands next to the issue it closed. Ordering every
        # column at once, each by the other's old order, makes two columns chase each other and never line up.
        pos = {n: y[n] + H[n] / 2 for n in nums}
        cols_seq = sorted(set(col.values()), reverse=bool(rounds % 2))
        side = nbr_right if rounds % 2 else nbr_left
        new = dict(pos)
        for c in cols_seq:
            for n in nums:
                if col[n] == c and side[n]:
                    new[n] = sum(new[m] for m in side[n]) / len(side[n]) + pos[n] * 1e-6
        rank = after_partner({n: new[n] + band[n] * 1e6 for n in nums})
    _, y = best
    for b in range(nb):                           # close the gaps that separate groups leave (compact_components)
        members = [n for n in nums if band[n] == b]
        if not members:
            continue
        if Y_METHOD == 'simplex':
            simplex_rows(members, edges, col, y, H, vlink, offs)
        else:
            compact_components(nums, edges, col, y, H, members, min(y[n] for n in members))
            close_strips(members, y, H)

    # attach points
    outs = {n: sorted([(a, b, k) for a, b, k in easy_pairs if a == n], key=lambda e: y[e[1]] + H[e[1]] / 2) for n in nums}
    ins = {n: sorted([(a, b, k) for a, b, k in easy_pairs if b == n], key=lambda e: y[e[0]] + H[e[0]] / 2) for n in nums}
    ey, ty = {}, {}
    for n in nums:
        step_o, step_i = (14.0, 20.0) if info[n].get('collapsed') else (16.0, 22.0)
        for e, v in zip(outs[n], slots(y[n], H[n], len(outs[n]), step_o)):
            ey[e] = v
        for e, v in zip(ins[n], slots(y[n], H[n], len(ins[n]), step_i)):
            ty[e] = v
    for e in easy_pairs:                          # make an arrow straight whenever a level line fits both boxes (20px from their corners)
        a, b, k = e
        if 0.5 < abs(ey[e] - ty[e]):
            lo_b, hi_b = y[b] + 20, y[b] + H[b] - 20
            lo_a, hi_a = y[a] + 20, y[a] + H[a] - 20
            if lo_b <= ey[e] <= hi_b and all(abs(ey[e] - ty[o]) >= 20 for o in ins[b] if o != e):
                ty[e] = ey[e]
            elif lo_a <= ty[e] <= hi_a and all(abs(ty[e] - ey[o]) >= 14 for o in outs[a] if o != e):
                ey[e] = ty[e]

    # columns: x of each, from the lanes each gap holds
    lanes = [0] * max(ncol, 1)
    lbl = [0.0] * max(ncol, 1)
    for e in easy_pairs:
        c = col[e[0]]
        lbl[c] = max(lbl[c], draw.label_width(e[2]))
        if abs(ey[e] - ty[e]) > 0.5:
            lanes[c] += 1
    X = [LEFT_]
    for c in range(ncol - 1):
        gap = max(205.0, LANE0 + LANE * lanes[c] + max(lbl[c] + 30, 80))
        X.append(X[-1] + draw.BOX_W + gap)
    gapx = lambda c: (X[c] + draw.BOX_W, X[c + 1])
    rect = {n: (X[col[n]], y[n], float(draw.BOX_W), H[n]) for n in nums}

    # lanes: order the jogging arrows of each gap by trial, fewest crossings first
    easy = []
    for c in range(ncol - 1):
        gl, gr = gapx(c)
        es = [e for e in easy_pairs if col[e[0]] == c]
        paths = {}
        jog = []
        for e in es:
            if abs(ey[e] - ty[e]) <= 0.5:
                paths[e] = [(gl, ey[e]), (gr, ey[e])]
            else:
                jog.append(e)

        def poly(e, k):
            lx = gl + LANE0 + LANE * k
            return [(gl, ey[e]), (lx, ey[e]), (lx, ty[e]), (gr, ty[e])]

        order = []
        for e in sorted(jog, key=lambda e: -abs(ty[e] - ey[e])):
            bestpos = None
            for pos in range(len(order) + 1):
                trial = order[:pos] + [e] + order[pos:]
                cost = sum(crossings(poly(trial[i], i), poly(trial[j], j)) for i in range(len(trial)) for j in range(i + 1, len(trial)))
                cost += sum(crossings(poly(trial[i], i), paths[s]) for i in range(len(trial)) for s in paths)
                if bestpos is None or cost < bestpos[0]:
                    bestpos = (cost, trial)
            order = bestpos[1]
        for k, e in enumerate(order):
            paths[e] = poly(e, k)
        for e in es:
            easy.append((e[0], e[1], e[2], paths[e]))

    # vertical arrows inside a column: between neighbours in the column, 40px apart on a shared side
    used = {}
    hard = []
    for a, b, k in vert_pairs:
        lst = sorted([n for n in nums if col[n] == col[a]], key=lambda n: y[n])
        ia, ib = lst.index(a), lst.index(b)
        if abs(ia - ib) != 1 or abs(rect[a][1] - rect[b][1]) < 1:
            hard.append((a, b, k))
            continue
        up, down = (a, b) if ia < ib else (b, a)
        gapv = y[down] - (y[up] + H[up])
        if gapv < 80:
            hard.append((a, b, k))
            continue
        x0 = X[col[a]]
        for s in (0, -40, 40, -80, 80):
            if (up, 'B', s) not in used and (down, 'T', s) not in used:
                break
        used[(up, 'B', s)] = used[(down, 'T', s)] = True
        px = x0 + 130 + s
        pts = [(px, y[up] + H[up]), (px, y[down])] if a == up else [(px, y[down]), (px, y[up] + H[up])]
        easy.append((a, b, k, pts))
    done = {(a, b, k) for a, b, k, _ in easy}
    hard += [e for e in edges if e not in done and e not in hard and e[0] != e[1]]

    # frames
    frames = []
    for i, name in enumerate(names, 1):
        mem = [n for n in nums if band[n] == i]
        x0 = min(rect[n][0] for n in mem) - FRAME_L
        x1 = max(rect[n][0] + rect[n][2] for n in mem) + FRAME_R
        y0 = min(rect[n][1] for n in mem) - FRAME_TOP
        y1 = max(rect[n][1] + rect[n][3] for n in mem) + FRAME_BOT
        tw = info[next(n for n in mem)].get('title_w', 0)
        x1 = max(x1, x0 + tw + 40)
        frames.append((name, x0, y0, x1 - x0, y1 - y0))
    right = max([r[0] + r[2] for r in rect.values()] + [f[1] + f[3] for f in frames] + [0])
    bottom = max([r[1] + r[3] for r in rect.values()] + [f[2] + f[4] for f in frames] + [0])
    return dict(rect=rect, frames=frames, easy=easy, hard=hard, right=right, bottom=bottom, col=col)


SHELF_GAP = 240          # between two columns of frames: room for the arrows the router runs between them
FORK_PAD = 60            # from the root's right edge to its first lane, and from the last lane to the frame border
GROW_PULL = 2.0          # cost per pixel a frame's place adds to the canvas width or height (compactness)
BACK_PULL = 0.5          # extra cost per pixel of a lineage arrow that points right to left between frames


def wrap_isolated(nodes, edges):
    """Columns for the boxes of one frame that no arrow inside the frame touches. Without this they all land in column 0, one under the
    other, and a frame of 30 such boxes is 6000px tall. They are spread over a few columns, so the frame is about as tall as wide."""
    tied = {x for a, b, k in edges for x in (a, b)}
    iso = [n for n in nodes if n['num'] not in tied]
    if len(iso) < 4:
        return {}
    col = auto_columns([n['num'] for n in nodes if n['num'] in tied], edges) if tied else {}
    ncol = (max(col.values()) + 1) if col else 1
    total = sum(n['h'] + STACK_GAP for n in nodes)
    k = max(ncol, min(4, int(round((total / (draw.BOX_W + 205)) ** 0.5))))
    height = [0.0] * k
    info = {n['num']: n for n in nodes}
    for n, c in col.items():
        height[c] += info[n]['h'] + STACK_GAP
    out = {}
    for n in sorted(iso, key=lambda n: n['num']):
        c = min(range(k), key=lambda c: height[c])
        out[n['num']] = c
        height[c] += n['h'] + STACK_GAP
    return out


def plan_blocks(nodes, edges, roots=()):
    """Layout for a graph with dotted frames (same result format as plan()).

    1. Each frame is a block: its boxes are laid out inside it with plan() (its own columns, rows and easy arrows). Boxes that no arrow
       inside the frame touches are spread over a few columns (wrap_isolated). Boxes outside every frame, except the roots, form one block
       without a border.
    2. The roots (graph.json "roots", or else the unframed source with the most forward arrows) sit in the first column. The blocks that
       hold a root's children are stacked in the next column, in the order of those children; the other blocks follow, those tied by
       arrows to blocks already placed first, packed into further columns up to a target height (the first column's height, or more
       when the picture would get much taller than wide).
    3. A root sits level with the middle of its children and forks: one exit per child on its right edge (16px apart, the root grows),
       one lane per arrow in the gap, nested so none crosses (going up, the topmost exit takes the lane nearest the root; going down, the
       lowest exit does). Every other arrow between blocks is left to route.py."""
    nums = [n['num'] for n in nodes]
    info = {n['num']: n for n in nodes}
    names = []
    for n in nodes:
        if n.get('frame') and n['frame'] not in names:
            names.append(n['frame'])
    roots = [r for r in roots if r in info and not info[r].get('frame')]
    if not roots:
        outs = {n: sum(1 for a, b, k in edges if a == n and forward(k)) for n in nums}
        ins = {n: sum(1 for a, b, k in edges if b == n and forward(k)) for n in nums}
        cand = [n for n in nums if not info[n].get('frame') and ins[n] == 0 and outs[n] >= 2]
        roots = sorted(cand, key=lambda n: -outs[n])[:1]
    degree = {}
    for a, b, k in edges:
        if a != b:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
    blocks = [dict(name=name, mem=[n for n in nums if info[n].get('frame') == name]) for name in names]
    loose = [n for n in nums if not info[n].get('frame') and n not in roots]
    if loose:
        blocks.append(dict(name=None, mem=loose))
    for B in blocks:
        mem = set(B['mem'])
        ie = [e for e in edges if e[0] in mem and e[1] in mem]
        sub = [dict(info[n], frame=None) for n in B['mem']]
        outside = {x for a, b, k in edges for x, y in ((a, b), (b, a)) if x in mem and y not in mem}
        P = plan(sub, ie, left=0, top=0, col_override=wrap_isolated(sub, ie), outside=outside, degree=degree)
        r = P['rect'].values()
        x0, y0 = min(v[0] for v in r), min(v[1] for v in r)
        x1, y1 = max(v[0] + v[2] for v in r), max(v[1] + v[3] for v in r)
        pad = (FRAME_L, FRAME_TOP, FRAME_R, FRAME_BOT) if B['name'] else (FRAME_L, 0, 0, 0)   # unframed: room on the left for a label
        tw = info[B['mem'][0]].get('title_w', 0) if B['name'] else 0
        B.update(P=P, x0=x0, y0=y0, pad=pad, w=max(x1 - x0 + pad[0] + pad[2], tw + 40), h=y1 - y0 + pad[1] + pad[3])

    kids = {r: [b for a, b, k in edges if a == r and forward(k) and b in info and b not in roots] for r in roots}
    root_kids = {b for r in roots for b in kids[r]}
    first = sorted([B for B in blocks if root_kids & set(B['mem'])], key=lambda B: min(root_kids & set(B['mem'])))
    rest, placed = [B for B in blocks if B not in first], {n for B in first for n in B['mem']} | set(roots)
    order = []
    while rest:                                   # blocks tied by arrows to what is placed come first, so their arrows stay short
        tie = lambda B: sum(draw.pull(k) for a, b, k in edges                        # an important arrow counts more (draw.IMPORTANCE)
                            if (a in placed) != (b in placed) and (a in B['mem'] or b in B['mem']))
        # per box: a small frame hanging off one spot (an issue that came out of a placed frame) goes before a big flexible one,
        # which then fills the space around it; by the total, the big frames always came first and took the small one's spot
        B = max(rest, key=lambda B: (tie(B) / len(B['mem']), -min(B['mem'])))
        order.append(B)
        rest.remove(B)
        placed |= set(B['mem'])

    x = LEFT + (draw.BOX_W if roots else 0)      # moved right below, once the fork knows how many lanes it needs
    y = TOP
    for B in first:
        B['x'], B['y'] = x, y
        y += B['h'] + BAND_GAP
    h1 = y - BAND_GAP - TOP if first else 0
    area = sum(B['w'] * B['h'] for B in blocks)
    low = max([h1, (area * 1.4 / 1.3) ** 0.5] + [B['h'] for B in order])
    # The other blocks: each goes where its arrows to the boxes already placed are shortest. Candidate places are the corners the placed
    # blocks leave (below one, or right of one), inside the target height and overlapping nothing; a block with no arrow to what is placed
    # takes the place nearest the top left. This keeps a frame next to the frames it talks to, and leaves no column of empty space.
    def centre(B, n, bx, by):
        r = B['P']['rect'][n]
        return bx + B['pad'][0] - B['x0'] + r[0] + r[2] / 2, by + B['pad'][1] - B['y0'] + r[1] + r[3] / 2

    def tie_cost(k, mine_is_head, m, o):
        """Cost of one arrow between a block being placed (its box at m) and a placed box (at o): its length times its pull
        (draw.pull: 1 for a very important arrow such as child, closed by, blocked by; 0.6 for follow-up, led to, references; 0.2 for
        related), so a frame sits next to the frames its important arrows join, not halfway to one it only mentions. A forward arrow
        whose head would sit left of its tail costs BACK_PULL more per pixel: the chart reads left to right, earlier to later."""
        d = abs(m[0] - o[0]) + abs(m[1] - o[1])
        w = draw.pull(k)
        if not forward(k):
            return w * d
        head_x, tail_x = (m[0], o[0]) if mine_is_head else (o[0], m[0])
        return w * (d + BACK_PULL * max(0.0, tail_x - head_x))

    def pack(target):
      where = {}                                  # box -> centre, for the boxes placed so far
      for B in first:
        for n in B['mem']:
            where[n] = centre(B, n, B['x'], B['y'])
      for r in roots:                             # the root will sit level with the middle of its children (the fork, below)
        ks = [where[c][1] for c in kids[r] if c in where]
        where[r] = (LEFT + draw.BOX_W / 2, (min(ks) + max(ks)) / 2 if ks else TOP + 300)
      placed_rects = [(B['x'], B['y'], B['w'], B['h']) for B in first]
      x2 = x + max([B['w'] for B in first] + [0]) + (SHELF_GAP if first else 0)
      total = 0.0
      for B in order:
        xs = {x2} | {px + pw + SHELF_GAP for px, py, pw, ph in placed_rects} | {px for px, py, pw, ph in placed_rects} \
            | {px - SHELF_GAP - B['w'] for px, py, pw, ph in placed_rects}            # also left of a block, and above one
        ys = {TOP} | {py + ph + BAND_GAP for px, py, pw, ph in placed_rects} | {py - BAND_GAP - B['h'] for px, py, pw, ph in placed_rects}
        ties = [(a, b, k) for a, b, k in edges if (a in B['mem']) != (b in B['mem']) and (a in where or b in where)]
        for a, b, k in ties:                         # also the places that put a box level with, or right above or below, its partner
            mine, other = (a, b) if a in B['mem'] else (b, a)
            if other in where:
                r = B['P']['rect'][mine]
                xs.add(where[other][0] - (B['pad'][0] - B['x0'] + r[0] + r[2] / 2))
                ys.add(where[other][1] - (B['pad'][1] - B['y0'] + r[1] + r[3] / 2))
        best = None
        for cx in sorted(xs):
            for cy in sorted(ys):
                if cy < TOP or cx < x or cy + B['h'] > TOP + max(target, B['h']):
                    continue
                if any(cx < px + pw + SHELF_GAP and px < cx + B['w'] + SHELF_GAP and cy < py + ph + BAND_GAP and py < cy + B['h'] + BAND_GAP
                       for px, py, pw, ph in placed_rects):
                    continue
                cost = 0.0
                for a, b, k in ties:
                    mine, other = (a, b) if a in B['mem'] else (b, a)
                    if other in where:
                        mx, my = centre(B, mine, cx, cy)
                        cost += tie_cost(k, mine == b, (mx, my), where[other])
                # compactness: every pixel the spot adds to the width or height of what is placed costs like a pixel of arrow
                bx1 = max([px + pw for px, py, pw, ph in placed_rects] + [x2])
                by1 = max([py + ph for px, py, pw, ph in placed_rects] + [TOP])
                cost += GROW_PULL * (max(0.0, cx + B['w'] - bx1) + max(0.0, cy + B['h'] - by1))
                cost += 0.05 * (cx + cy)                 # ties broken towards the top left
                if best is None or cost < best[0]:
                    best = (cost, cx, cy)
        if best is None:                             # nothing fits: a new column right of everything
            best = (0, max(px + pw for px, py, pw, ph in placed_rects) + SHELF_GAP if placed_rects else x2, TOP)
        B['x'], B['y'] = best[1], best[2]
        if os.environ.get('LAYOUT_DEBUG'):                # which frame went where, at what cost (set LAYOUT_DEBUG=1)
            print('target %d: %s at (%d,%d) cost %.0f' % (target, B['name'], best[1], best[2], best[0]), file=sys.stderr)
        total += best[0]
        placed_rects.append((B['x'], B['y'], B['w'], B['h']))
        for n in B['mem']:
            where[n] = centre(B, n, B['x'], B['y'])
      # Gravity: every placed block, top to bottom, rises until it meets a block above it (or the top). Placement keeps a block near
      # the frames it talks to, but the first free corner it finds can leave an empty band above it; this closes such bands.
      # A block rises only when that does not make its arrows to other blocks longer (a box placed right under its partner stays).
      def arrow_len(B, bx, by):
        s = 0.0
        for a, b, k in edges:
          if (a in B['mem']) != (b in B['mem']):
            mine, other = (a, b) if a in B['mem'] else (b, a)
            if other in where:
              s += tie_cost(k, mine == b, centre(B, mine, bx, by), where[other])
        return s

      fixed = [(B['x'], B['y'], B['w'], B['h']) for B in first]
      for B in sorted(order, key=lambda B: B['y']):
        above = [r for r in fixed + [(C['x'], C['y'], C['w'], C['h']) for C in order if C is not B]
                 if B['x'] < r[0] + r[2] + SHELF_GAP and r[0] < B['x'] + B['w'] + SHELF_GAP and r[1] + r[3] <= B['y']]
        ny = max([TOP] + [r[1] + r[3] + BAND_GAP for r in above])
        if ny < B['y'] and arrow_len(B, B['x'], ny) <= arrow_len(B, B['x'], B['y']) + 1:
          B['y'] = ny
          for n in B['mem']:
            where[n] = centre(B, n, B['x'], B['y'])
      placed_rects = fixed + [(B['x'], B['y'], B['w'], B['h']) for B in order]
      W = max([px + pw for px, py, pw, ph in placed_rects] + [x2]) + 60 + draw.LEGEND_W + 60
      H = max([py + ph for px, py, pw, ph in placed_rects] + [TOP]) + 80
      return W / H, total, {id(B): (B['x'], B['y']) for B in order}, W * H

    # Try many heights for the columns of blocks. Keep the smallest canvas (least empty space) whose shape is between 0.9 and 2 wide
    # to 1 tall (SKILL.md: near square; ask the user past 2:1); shorter arrows break a tie. With no such canvas, the shape nearest 1.3.
    trials = []
    for i in range(17):
        asp, cost, pos, area_ = pack(low * (1.0 + 0.1 * i))
        trials.append((area_ * (1 + cost * 1e-7), asp, pos))
        if os.environ.get('LAYOUT_DEBUG'):
            print('trial target %d: aspect %.2f, canvas area %.1fM, arrow cost %.0f' % (low * (1.0 + 0.1 * i), asp, area_ / 1e6, cost), file=sys.stderr)
    ok = [t for t in trials if 0.9 <= t[1] <= 2.0]
    _, asp, pos = min(ok, key=lambda t: t[0]) if ok else min(trials, key=lambda t: abs(t[1] - 1.3))
    for B in order:
        B['x'], B['y'] = pos[id(B)]

    rect, easy, frames, first_col = {}, [], [], {}
    for B in blocks:
        ox, oy = B['x'] + B['pad'][0] - B['x0'], B['y'] + B['pad'][1] - B['y0']
        for n, (bx, by, bw, bh) in B['P']['rect'].items():
            rect[n] = (bx + ox, by + oy, bw, bh)
            first_col[n] = abs(bx - B['x0']) < 1
        for a, b, k, pts in B['P']['easy']:
            easy.append((a, b, k, [(px + ox, py + oy) for px, py in pts]))
        if B['name']:
            frames.append((B['name'], B['x'], B['y'], B['w'], B['h']))

    forks, lanes_needed = [], 0
    for r in roots:                               # the fork: heights first (they do not depend on x)
        fk = sorted([c for c in kids[r] if first_col.get(c)], key=lambda c: rect[c][1])
        ty = {c: rect[c][1] + min(60.0, rect[c][3] / 2) for c in fk}
        hr = min_height(info[r]['h'], len(fk), 0, info[r].get('collapsed'))
        mid = (min(ty.values()) + max(ty.values())) / 2 if fk else TOP + hr / 2
        yr = max(TOP, mid - hr / 2)
        rect[r] = (LEFT, yr, float(draw.BOX_W), hr)
        ex = dict(zip(fk, slots(yr, hr, len(fk), 16.0)))
        for c in fk:                              # a jog under 30px is a glitch: enter level with the exit when the child allows it
            if 0.5 < abs(ty[c] - ex[c]) < 30 and rect[c][1] + 20 <= ex[c] <= rect[c][1] + rect[c][3] - 20:
                ty[c] = ex[c]
        up = sorted([c for c in fk if ty[c] < ex[c] - .5], key=lambda c: ex[c])
        down = sorted([c for c in fk if ty[c] > ex[c] + .5], key=lambda c: -ex[c])
        lanes_needed = max(lanes_needed, len(up), len(down))
        forks.append((r, fk, ty, ex, {c: k for grp in (up, down) for k, c in enumerate(grp)}))
    if roots:                                     # the gap: FORK_PAD + 14px per lane + 40px clear of the frame border
        dx = LEFT + draw.BOX_W + FORK_PAD + LANE * max(lanes_needed - 1, 0) + 40 - x
        shift = lambda pts: [(px + dx, py) for px, py in pts]
        rect = {n: ((v[0] + dx,) + v[1:] if n not in roots else v) for n, v in rect.items()}
        easy = [(a, b, k, shift(p)) for a, b, k, p in easy]
        frames = [(f[0], f[1] + dx) + f[2:] for f in frames]
    rx = LEFT + draw.BOX_W
    for r, fk, ty, ex, lane in forks:
        kind_of = {b: k for a, b, k in edges if a == r}
        for c in fk:
            cl = rect[c][0]
            if c in lane:
                lx = rx + FORK_PAD + LANE * lane[c]
                pts = [(rx, ex[c]), (lx, ex[c]), (lx, ty[c]), (cl, ty[c])]
            else:
                pts = [(rx, ex[c]), (cl, ex[c])]
            easy.append((r, c, kind_of[c], pts))
    done = {(a, b, k) for a, b, k, _ in easy}
    hard = [e for e in edges if e not in done and e[0] != e[1]]
    right = max([v[0] + v[2] for v in rect.values()] + [f[1] + f[3] for f in frames] + [0])
    bottom = max([v[1] + v[3] for v in rect.values()] + [f[2] + f[4] for f in frames] + [0])
    return dict(rect=rect, frames=frames, easy=easy, hard=hard, right=right, bottom=bottom, col={})


def crossings(p, q):
    """Number of proper crossings between two orthogonal polylines (touching ends are not crossings)."""
    n = 0
    for a, b in zip(p, p[1:]):
        for c, d in zip(q, q[1:]):
            ah, ch = abs(a[1] - b[1]) < .01, abs(c[1] - d[1]) < .01
            if ah == ch:
                continue
            (h1, h2), (v1, v2) = ((a, b), (c, d)) if ah else ((c, d), (a, b))
            if min(h1[0], h2[0]) + .01 < v1[0] < max(h1[0], h2[0]) - .01 and min(v1[1], v2[1]) + .01 < h1[1] < max(v1[1], v2[1]) - .01:
                n += 1
    return n
