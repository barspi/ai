#!/usr/bin/env python3
"""Network simplex: the standard solver for ranking problems in layered graph drawing.

Source: E. R. Gansner, E. Koutsofios, S. C. North, K.-P. Vo, "A Technique for Drawing Directed Graphs", IEEE Trans. Software Eng.
19(3), 1993, section 2.3 (the solver) and section 4.2 (its use for coordinates). Graphviz `dot` uses it for both.

Problem: integer values lam[v] that minimise  sum over edges e=(t, h) of weight(e) * (lam[h] - lam[t])
subject to                                    lam[h] - lam[t] >= delta(e)   for every edge.
The edges must form a directed acyclic graph. The graph need not be connected: a hidden source ties every part to one root with
weight 0, so each part keeps the place the first feasible ranking gave it (the top) unless an edge pulls it.

Steps, as in the paper: init_rank (longest path), feasible_tree (grow a tree of tight edges, shifting the tree to tighten the
cheapest edge that leaves it), then repeat: a tree edge with a negative cut value leaves, the non-tree edge of least slack that
crosses the cut the other way enters, ranks shift so it is tight. Stops when no cut value is negative (optimal), or after max_iter.
Cut values are recomputed in full after each exchange: the graphs here have a few hundred edges, so clarity wins over speed.
"""


def solve(n, edges, max_iter=5000):
    """n nodes 0..n-1; edges [(tail, head, delta, weight)] with integer delta and weight >= 0. Returns ranks, min rank 0."""
    src = n                                        # hidden source: makes the graph connected, costs nothing
    E = [tuple(e) for e in edges] + [(src, v, 0, 0) for v in range(n)]
    N = n + 1
    out, adj = [[] for _ in range(N)], [[] for _ in range(N)]
    indeg = [0] * N
    for i, (t, h, d, w) in enumerate(E):
        out[t].append(i)
        adj[t].append(i)
        adj[h].append(i)
        indeg[h] += 1

    # init_rank: longest path from the sources, so every edge is feasible
    rank = [0] * N
    queue = [v for v in range(N) if indeg[v] == 0]
    seen = 0
    while queue:
        u = queue.pop()
        seen += 1
        for i in out[u]:
            t, h, d, w = E[i]
            rank[h] = max(rank[h], rank[u] + d)
            indeg[h] -= 1
            if indeg[h] == 0:
                queue.append(h)
    if seen != N:
        raise ValueError('netsimplex: the constraint graph has a cycle')

    slack = lambda i: rank[E[i][1]] - rank[E[i][0]] - E[i][2]

    # feasible_tree
    in_tree = [False] * N
    tree = set()
    in_tree[src] = True
    members = [src]

    def grow():
        stack = list(members)
        while stack:
            u = stack.pop()
            for i in adj[u]:
                t, h = E[i][0], E[i][1]
                o = h if t == u else t
                if not in_tree[o] and slack(i) == 0:
                    in_tree[o] = True
                    members.append(o)
                    tree.add(i)
                    stack.append(o)

    grow()
    while len(members) < N:
        best = None
        for i in range(len(E)):
            t, h = E[i][0], E[i][1]
            if in_tree[t] != in_tree[h] and (best is None or slack(i) < slack(best)):
                best = i
        d = slack(best)
        if in_tree[E[best][1]]:                     # the tree holds the head: lower the tree
            d = -d
        for v in members:
            rank[v] += d
        grow()

    # cut values on a rooted tree (low/lim postorder numbers tell subtree membership)
    def number():
        tadj = [[] for _ in range(N)]
        for i in tree:
            tadj[E[i][0]].append(i)
            tadj[E[i][1]].append(i)
        low, lim, parent_edge = [0] * N, [0] * N, [None] * N
        counter = [1]
        stack = [(src, None, iter(tadj[src]))]
        low[src] = 1
        while stack:
            v, pe, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                lim[v] = counter[0]
                counter[0] += 1
                stack.pop()
                continue
            if nxt == pe:
                continue
            o = E[nxt][1] if E[nxt][0] == v else E[nxt][0]
            parent_edge[o] = nxt
            low[o] = counter[0]
            stack.append((o, nxt, iter(tadj[o])))
        return low, lim, parent_edge

    def cut_value(i, low, lim):
        t, h = E[i][0], E[i][1]
        c = t if lim[t] < lim[h] else h            # the endpoint below the other in the rooted tree
        inside = lambda v: low[c] <= lim[v] <= lim[c]
        tail_side_is_sub = (c == t)
        cv = 0
        for (u, v, d, w) in E:
            a, b = inside(u), inside(v)
            if a == b:
                continue
            u_tail = a if tail_side_is_sub else not a          # u is on the tail side of the cut
            cv += w if u_tail else -w
        return cv

    for _ in range(max_iter):
        low, lim, _pe = number()
        leave = None
        for i in sorted(tree):
            if cut_value(i, low, lim) < 0:
                leave = i
                break
        if leave is None:
            break
        t, h = E[leave][0], E[leave][1]
        c = t if lim[t] < lim[h] else h
        inside = lambda v: low[c] <= lim[v] <= lim[c]
        tail_side = (lambda v: inside(v)) if c == t else (lambda v: not inside(v))
        enter = None
        for i, (u, v, d, w) in enumerate(E):       # non-tree edges from the head side to the tail side
            if i in tree or tail_side(u) or not tail_side(v):
                continue
            if enter is None or slack(i) < slack(enter):
                enter = i
        if enter is None:
            break
        d = slack(enter)
        for v in range(N):                          # the tail side moves down by the slack: enter becomes tight
            if tail_side(v):
                rank[v] -= d
        tree.discard(leave)
        tree.add(enter)
    base = min(rank[:n]) if n else 0
    return [r - base for r in rank[:n]]


if __name__ == '__main__':
    # self-test: a hub with three tails in one column, offsets in delta; the hub must land on the median tail
    #   column A: t0, t1, t2 stacked (100 tall, gap 28); column B: hub (h). Aux nodes 4..6 carry |y_ti - y_h|.
    sep = [(0, 1, 128, 0), (1, 2, 128, 0)]
    aux = []
    for k, t in enumerate((0, 1, 2)):
        z = 4 + k
        aux += [(z, t, 0, 1), (z, 3, 0, 1)]
    r = solve(7, sep + aux)
    assert r[1] - r[0] == 128 and r[2] - r[1] == 128 and r[3] == r[1], r
    print('netsimplex self-test OK', r[:4])
