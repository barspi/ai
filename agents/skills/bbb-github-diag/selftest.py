#!/usr/bin/env python3
"""Self-test of the skill's scripts. Run it after every change to a .py file here; it must print `selftest: OK` (exit 0).

usage: selftest.py [--no-static]

1. Static checks (skipped with a note when `uvx` is not installed; --no-static skips them):
   - ruff, the pyflakes rules (F) less three dead-code ones (F401 unused import, F841 unused variable, F402 import shadowed by a loop
     variable): an undefined name, a `%` format with the wrong number of arguments.
   - mypy --check-untyped-defs with the codes that need annotations this code does not carry turned off. What stays on catches a
     record formatted in the wrong order (`'%d %s %d' % arrow` when the fields are a, b, kind), a call with too many arguments, an
     attribute a value does not have.
2. rules.selftest(): the phrase, close and blocked-note rules. route.selftest(): one small scene per routing rule, with the router
   BBB_ROUTER names. ovg.selftest(): both routers on random scenes, the same cost for every arrow.
3. The failure paths, run on a copy of example/sample-lineage.svg: every line that only prints when something goes wrong runs at least
   once, and no script may lose an arrow it did not report:
   - move.py with every label refused (route.place_label and place_label_beside patched to find nothing): each moved arrow prints its "has no label" PROBLEM;
   - move.py again on that output, moving the box back: the arrows that had no label get one, and none may disappear;
   - move.py onto another box (a place PROBLEM), and inside a keep-out area (each arrow of the box finds no path, goes to nopath);
   - reroute.py with every label refused;
   - ports.py: #103's two arrows of one side drawn in the wrong order cross; check_diag.py warns; ports.py (B, then A) routes every
     arrow again and leaves no two arrows of one side crossing, every arrow kept, FAILS 0;
   - check_diag.py on the picture with the overlapping box: it must print FAIL lines, not a traceback.
4. by_construction(): one case per rule of the by-construction work (SKILL.md, "Check"): only revise.py --render renders; an arrow
   between two boxes of one frame never leaves it, the frame grows and the frame below moves as much (frames.grow); add_nodes.py in
   a full frame puts the box inside it, beside `near`; route_labelled takes the next cheapest path when the cheapest has no room for
   the label, and no label goes where a jump arc will be; the spatial index answers like a full scan; collapse.py and move.py leave
   no invalid arrow; a short label shaft is a WARN, two boxes on top of each other a FAIL.
The in-process runs call each script's main() with sys.argv set, so a crash shows its traceback here.
"""
import contextlib, io, os, re, shutil, subprocess, sys, tempfile, traceback
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import add_nodes, collapse, model, move, ovg, ports, reroute, route, rules, svgmeta

EXAMPLE = os.path.join(HERE, 'example', 'sample-lineage.svg')
RUFF_IGNORE = 'F401,F841,F402'                   # dead code only; every other pyflakes rule is an error
MYPY_OFF = ['var-annotated', 'assignment', 'operator', 'index', 'union-attr', 'misc', 'dict-item', 'call-overload', 'arg-type']
# MYPY_OFF: codes that fire on untyped code by design (a variable reused with another type, a Match that may be None after a regex
# the caller already checked). Turn one on and fix what it finds, never the reverse.

fails = []


def check(ok, what):
    print('%s %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        fails.append(what)


def static():
    if not shutil.which('uvx'):
        print('SKIP static checks: uvx is not installed (https://docs.astral.sh/uv/)')
        return
    env = dict(os.environ, NO_COLOR='1', MYPYPATH=HERE)
    py = sorted(f for f in os.listdir(HERE) if f.endswith('.py'))
    r = subprocess.run(['uvx', 'ruff', 'check', '--no-cache', '--output-format', 'concise', '--select', 'F', '--ignore', RUFF_IGNORE]
                       + py, cwd=HERE, capture_output=True, text=True, env=env)
    check(r.returncode == 0, 'ruff (pyflakes rules)' + ('' if r.returncode == 0 else ':\n' + r.stdout + r.stderr))
    cache = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-mypy')
    r = subprocess.run(['uvx', 'mypy', '--ignore-missing-imports', '--check-untyped-defs', '--no-color-output', '--cache-dir', cache]
                       + ['--disable-error-code=' + c for c in MYPY_OFF] + py, cwd=HERE, capture_output=True, text=True, env=env)
    out = '\n'.join(l for l in r.stdout.splitlines() if ': note:' not in l)
    check(r.returncode == 0, 'mypy' + ('' if r.returncode == 0 else ':\n' + out + r.stderr))


def call(mod, argv, no_labels=False):
    """(exit code, stdout) of mod.main() with sys.argv = argv. no_labels: route.place_label and route.place_label_beside find no
    place for any label (so neither does anything built on them)."""
    old_argv, old_place = sys.argv, (route.place_label, route.place_label_beside)
    sys.argv = [mod.__file__] + argv
    if no_labels:
        route.place_label = route.place_label_beside = lambda *a, **k: None
    buf, code = io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception:
        code = 'crash'
        buf.write(traceback.format_exc())
    finally:
        sys.argv, (route.place_label, route.place_label_beside) = old_argv, old_place
    return code, buf.getvalue()


def arrows(path):
    return model.count_arrows(open(path, encoding='utf-8').read())


def failure_paths(tmp):
    src = os.path.join(tmp, 'in.svg')
    shutil.copy(EXAMPLE, src)
    n0 = arrows(src)
    box = 100                                    # four `child` arrows leave it, so a move of it reroutes four arrows
    x, y = 80, 251.5                             # its place in the example

    a = os.path.join(tmp, 'nolabel.svg')
    code, out = call(move, [src, a, '%d@%s,+40' % (box, x)], no_labels=True)
    check(code == 0, 'move.py with no label anywhere ends normally' + ('' if code == 0 else ' (%s):\n%s' % (code, out)))
    check('has no label' in out, 'move.py prints the "has no label" PROBLEM')
    check(os.path.exists(a) and arrows(a) == n0, 'move.py keeps every arrow (%s of %d)' % (os.path.exists(a) and arrows(a), n0))

    b = os.path.join(tmp, 'back.svg')
    code, out = call(move, [a, b, '%d@%s,%s' % (box, x, y)])
    check(code == 0, 'move.py back, labels found again, ends normally' + ('' if code == 0 else ' (%s):\n%s' % (code, out)))
    check(os.path.exists(b) and arrows(b) == n0, 'an arrow that had no label and gets one is kept (%s of %d)' % (os.path.exists(b) and arrows(b), n0))

    c = os.path.join(tmp, 'overlap.svg')
    code, out = call(move, [src, c, '%d@514,365.5' % box])           # on top of another box of the example
    check(code == 0 and 'PROBLEM' in out, 'move.py onto another box prints a PROBLEM' + ('' if code == 0 else ' (%s):\n%s' % (code, out)))

    d = os.path.join(tmp, 'keepout.svg')
    code, out = call(move, [src, d, '%d@%s,%s' % (box, x, y + 40), '--keep-out', '0,0,4000,4000'])   # nothing can be routed
    lost = len(re.findall(r'^PROBLEM #\d+ -> #\d+: no path', out, re.M))
    check(code == 0 and lost > 0, 'move.py in a keep-out area reports arrows with no path (%d)' % lost
          + ('' if code == 0 else ' (%s):\n%s' % (code, out)))
    if os.path.exists(d):
        check(arrows(d) == n0 - lost, 'only the arrows reported with no path are left out (%d of %d)' % (arrows(d), n0 - lost))
        check(len(svgmeta.read(open(d, encoding='utf-8').read()).get('nopath', [])) >= lost, 'they are listed in nopath')

    e = os.path.join(tmp, 'reroute.svg')
    code, out = call(reroute, [src, e, '101>110', '102>111'], no_labels=True)
    check(code == 0, 'reroute.py with no label anywhere ends normally' + ('' if code == 0 else ' (%s):\n%s' % (code, out)))
    check('has no label' in out, 'reroute.py prints the "has no label" PROBLEM')
    check(os.path.exists(e) and arrows(e) == n0, 'reroute.py keeps every arrow')

    crossed = os.path.join(tmp, 'crossed.svg')                         # #103's two arrows on its right side, in the wrong order
    t = open(src, encoding='utf-8').read()
    side = ports.groups(t)[(103, 'R')]
    open(crossed, 'w', encoding='utf-8').write(ports.reorder(t, side, key=lambda e: [-v for v in ports.far_key(e)]) or t)
    check(len(ports.crossing_pairs(open(crossed, encoding='utf-8').read())) == 1, 'ports.reorder in the wrong order makes them cross')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), crossed], capture_output=True, text=True)
    check(re.search(r'^WARN #103 -> #11\d and #103 -> #11\d: both on the R side of #103', r.stdout, re.M) is not None,
          'check_diag.py warns about two arrows of one side that cross')
    fixed = os.path.join(tmp, 'fixed.svg')
    code, out = call(ports, [crossed, fixed])
    check(code == 0 and os.path.exists(fixed) and not ports.crossing_pairs(open(fixed, encoding='utf-8').read()),
          'ports.py (B, then A) leaves no two arrows of one side crossing' + ('' if code == 0 else ' (%s):\n%s' % (code, out)))
    check(os.path.exists(fixed) and arrows(fixed) == n0, 'ports.py keeps every arrow')
    if os.path.exists(fixed):
        r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), fixed], capture_output=True, text=True)
        check(re.search(r'^FAILS 0$', r.stdout, re.M) is not None, 'check_diag.py after ports.py: FAILS 0'
              + ('' if 'FAILS 0' in r.stdout else ':\n' + '\n'.join(l for l in r.stdout.splitlines() if l.startswith('FAIL'))))

    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), c], capture_output=True, text=True)
    m = re.search(r'^FAILS (\d+)', r.stdout, re.M)
    check('Traceback' not in r.stderr and m is not None and int(m.group(1)) > 0,
          'check_diag.py on an overlapping box prints FAIL lines' + ('' if 'Traceback' not in r.stderr else ':\n' + r.stderr))
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), EXAMPLE], capture_output=True, text=True)
    check(r.returncode == 0 and re.search(r'^FAILS 0$', r.stdout, re.M) is not None, 'check_diag.py on the example: FAILS 0')


def checked(text, tmp, name):
    """(FAILS, WARNS, stdout) of check_diag.py on text."""
    path = os.path.join(tmp, name)
    open(path, 'w', encoding='utf-8').write(text)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), path], capture_output=True, text=True)
    num = lambda w: int(m.group(1)) if (m := re.search(r'^%s (\d+)$' % w, r.stdout, re.M)) else -1
    return num('FAILS'), num('WARNS'), r.stdout + r.stderr


def two_frames():
    """The example with its frame made tight (6px under #104) and a second frame, "returns", 72px under it: the scene of the grow and
    push tests. Returns (text, rect of the tight frame)."""
    lines = open(EXAMPLE, encoding='utf-8').read().split('\n')
    _, _, _, frs = collapse.parse('\n'.join(lines))
    f = frs[0]
    lines[f['rl']] = lines[f['rl']].replace('height="451.5"', 'height="433.5"')
    below = lines[f['rl']].replace('y="595"', 'y="1100"').replace('height="433.5"', 'height="120"')
    title = re.sub(r'y="([\d.]+)"', lambda m: 'y="%s"' % (float(m.group(1)) + 505), lines[f['tl']]).replace('guest checkout', 'returns')
    lines[f['tl'] + 1:f['tl'] + 1] = [below, title]
    return '\n'.join(lines), (f['x'], f['y'], f['w'], 433.5)


def by_construction(tmp):
    """One case per rule of the by-construction work: no render unless asked, same-frame arrows never leave their frame (the frame
    grows and pushes), add_nodes in a full frame, label room when a route is accepted, the spatial index, no stale state, the
    checker's FAIL and WARN."""
    import frames, spatial
    # 1. no script renders unless asked: render_region.py and rsvg-convert are called by render_region.py and revise.py --render only
    callers = [f for f in os.listdir(HERE) if f.endswith('.py') and f not in ('render_region.py', 'selftest.py')
               and re.search(r"'render_region\.py'|'rsvg-convert'", open(os.path.join(HERE, f), encoding='utf-8').read())]
    rv = open(os.path.join(HERE, 'revise.py'), encoding='utf-8').read()
    check(callers == ['revise.py'] and re.search(r"if o\.render and added:\n(?:.*\n){0,8}.*'render_region\.py'", rv) is not None,
          '1. only revise.py --render renders (%s)' % callers)
    # 2. an arrow between two boxes of one frame never leaves it; with no room the frame grows and the frame below moves as much
    text, tight = two_frames()
    sc = model.scene(text)
    check(route.route(sc, 104, 112, 'B', 'B') is None, '2. route() gives no path rather than leave the frame')
    text2, p = model.new_arrow(text, 104, 112, 'related', ('B', 'B'))
    res = model.route_arrows(text2, [p])
    sc2 = model.scene(res.text)
    grown = res.grown[0][1] if res.grown else 0
    check(res.routed and grown > 0 and not reroute.leaves_frame(res.text), '2. the frame grew %dpx and the arrow stays inside it' % grown)
    check(sc2.frames[1][1] == 1100 + grown and sc2.frames[0][3] == tight[3] + grown,
          '2. the frame below moved down by as much (%s)' % (sc2.frames,))
    f, w, out = checked(res.text, tmp, 'grown.svg')
    check(f == 0, '2. check_diag.py after the push: FAILS 0' + ('' if f == 0 else ':\n' + out))
    # 2. the cascade never leaves two frames overlapping, frames that touch both move
    check(frames.selftest.__call__ is not None and _quiet(frames.selftest), '2. frames.selftest(): the cascade')
    # 3. add_nodes.py in a full frame, near a box: inside the frame (grown), in near's column, no overlap
    spec = os.path.join(tmp, 'spec.json')
    open(spec, 'w').write('{"repo": "acme/shop", "boxes": [{"num": 150, "state": "open", "title": "a new issue in a full frame", '
                          '"meta": "opened 2026-01-05 · still open", "new": true, "near": 103, "frame": "guest checkout"}], '
                          '"arrows": [{"from": 103, "to": 150, "kind": "follow-up"}]}')
    src, dst = os.path.join(tmp, 'full.svg'), os.path.join(tmp, 'added.svg')
    open(src, 'w', encoding='utf-8').write(text)
    code, out = call(add_nodes, [src, dst, spec])
    if code == 0 and os.path.exists(dst):
        sc3 = model.scene(open(dst, encoding='utf-8').read())
        b = sc3.boxes.get(150)
        check(b is not None and route.holds(sc3.frames[0], b) and b[0] in (514.0, 514.0 + 260 + add_nodes.GAP_X),
              '3. the new box is inside its grown frame, in or beside the column of `near` (%s)' % (b,))
        check(sc3.frames[1][1] > 1100 and not any(route.holds(sc3.frames[1], r) or _overlap(r, sc3.frames[1]) for r in [b]),
              '3. the frame below moved; the new box is not on it')
        f, w, out = checked(open(dst, encoding='utf-8').read(), tmp, 'added2.svg')
        check(f == 0, '3. check_diag.py after add_nodes.py: FAILS 0' + ('' if f == 0 else ':\n' + out))
    else:
        check(False, '3. add_nodes.py in a full frame ran (%s):\n%s' % (code, out))
    # 4. label room is a test on the path: the cheapest straight path has no room (a label just above it), the next one has
    sc4 = route.Scene({1: (0, 200, 100, 60), 2: (360, 200, 100, 60)}, labels=[(100, 190, 260, 30)], bounds=(-600, -600, 3000, 3000))
    cheap = route.route(sc4, 1, 2, '*', '*')
    got = route.route_labelled(sc4, 1, 2, 'follow-up')
    check(route.place_label(sc4, cheap, 'follow-up', shaft=route.LABEL_SHAFT) is None and got is not None and got[2]
          and got[0] != cheap, '4. the cheapest path has no room for the label; route_labelled takes the next that has (%s)' % (got,))
    # 4. a label is never put where hops.py will draw an arc: a vertical arrow crosses the straight path in the middle
    sc5 = route.Scene({1: (0, 200, 100, 60), 2: (300, 200, 100, 60)}, arrows=[[(200, -200), (200, 600)]], bounds=(-600, -600, 3000, 3000))
    lab = route.place_label(sc5, [(100, 230), (300, 230)], 'follow-up', shaft=route.LABEL_SHAFT)
    check(lab is None, '4. no label within 20px of the jump arc hops.py will draw (%s)' % (lab,))
    # 5. the spatial index answers like a full scan; _hit by the index equals a scan of every item
    check(_quiet(spatial.selftest), '5. spatial.selftest()')
    sc6 = model.scene(open(EXAMPLE, encoding='utf-8').read())
    rnd = __import__('random').Random(3)
    differ = 0
    for _ in range(400):
        r = (rnd.uniform(0, 2000), rnd.uniform(150, 1100), rnd.uniform(30, 120), 18.0)
        full = route.Scene(dict(sc6.boxes), sc6.frames, list(sc6.labels), list(sc6.pills), list(sc6.arrows), sc6.bounds)
        if route._hit(r, sc6) != _hit_scan(r, full):
            differ += 1
    check(differ == 0, '5. route._hit by the index equals a scan of everything (%d of 400 differ)' % differ)
    # 6. no stale state: collapse.py (a box collapsed again keeps its arrows on it) and move.py (a box moved onto an arrow)
    src = os.path.join(tmp, 'c_in.svg')
    shutil.copy(EXAMPLE, src)
    dst = os.path.join(tmp, 'c_out.svg')
    code, out = call(collapse, [src, dst, '--set', '113=old checkout totals', '--set', '101=a new keyword line'])
    t6 = open(dst, encoding='utf-8').read() if os.path.exists(dst) else ''
    check(code == 0 and t6 and not model.invalid(t6), '6. collapse.py leaves no invalid arrow (%s)' % (model.invalid(t6) if t6 else out))
    dst = os.path.join(tmp, 'm_out.svg')
    code, out = call(move, [src, dst, '104@700,880'])        # #104 onto the path of #103 -> #113 (not its own arrow)
    t6 = open(dst, encoding='utf-8').read() if os.path.exists(dst) else ''
    check(code == 0 and t6 and not model.invalid(t6), '6. move.py routes again an arrow a moved box landed on (%s)' % (model.invalid(t6) if t6 else out))
    # 7. a short label shaft is a WARN with its measure, not a FAIL; two boxes on top of each other are a FAIL
    t7 = open(EXAMPLE, encoding='utf-8').read()
    t7 = t7.replace('<rect x="835.3" y="286.5"', '<rect x="890.3" y="286.5"').replace('x="871.0" y="299.5"', 'x="926.0" y="299.5"')
    f, w, out = checked(t7, tmp, 'short.svg')
    check(f == 0 and re.search(r'^WARN label \d+ at .* leaves \d+/\d+px of straight shaft', out, re.M) is not None,
          '7. a label with a short shaft: WARN with its measure, FAILS 0' + ('' if f == 0 else ':\n' + out))
    t8 = re.sub(r'(<g id="n122"[^>]*>\n<rect x=")1909(" y=")411', r'\g<1>1444\g<2>420', open(EXAMPLE, encoding='utf-8').read())
    f, w, out = checked(t8, tmp, 'boxes.svg')
    check(re.search(r'^FAIL boxes #121 and #122 overlap', out, re.M) is not None, '7. two boxes on top of each other: FAIL')


def _quiet(fn):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()


def _overlap(r, s):
    return r[0] < s[0] + s[2] and s[0] < r[0] + r[2] and r[1] < s[1] + s[3] and s[1] < r[1] + r[3]


def _hit_scan(rect, sc, pad=2, hop_pad=20, g=route.LABM):
    """route._hit as it was before the index: every item of the scene tested."""
    x, y, w, h = rect
    for (bx, by, bw, bh) in list(sc.boxes.values()) + list(sc.labels) + list(sc.pills):
        if bx - pad < x + w and bx + bw + pad > x and by - pad < y + h and by + bh + pad > y:
            return True
    for pts in sc.arrows:
        for o, c, lo, hi in route.segments(pts):
            if (o == 'h' and y - g < c < y + h + g and lo < x + w + g and hi > x - g) or (o == 'v' and x - g < c < x + w + g and lo < y + h + g and hi > y - g):
                return True
    return False


def main():
    if '--no-static' not in sys.argv:
        static()
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        passed = rules.selftest()                # True when every rule case passes
    check(passed, 'rules.selftest()' + ('' if passed else ':\n' + buf.getvalue()))
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        try:
            route.selftest()                     # exits 1 on a failure
            passed = True
        except SystemExit:
            passed = False
    check(passed, 'route.selftest() (%s router)' % os.environ.get('BBB_ROUTER', 'vis') + ('' if passed else ':\n' + buf.getvalue()))
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        passed = ovg.selftest()
    check(passed, 'ovg.selftest(): ' + buf.getvalue().strip())
    check(model.no_label(model.Arrow(10, 11, 'closed by')) == '#10 closed by #11 has no label: no place on it or beside it',
          'model.no_label wording')
    with tempfile.TemporaryDirectory() as tmp:
        failure_paths(tmp)
        by_construction(tmp)
    print('selftest: %s' % ('OK' if not fails else '%d FAILED: %s' % (len(fails), '; '.join(f.split(':')[0] for f in fails))))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
