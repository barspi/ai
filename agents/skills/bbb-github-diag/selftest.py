#!/usr/bin/env python3
"""Self-test of the skill's scripts. Run it after every change to a .py file here; it must print `selftest: OK` (exit 0).

usage: selftest.py [--no-static]

1. Static checks (skipped with a note when `uvx` is not installed; --no-static skips them):
   - ruff, the pyflakes rules (F) less three dead-code ones (F401 unused import, F841 unused variable, F402 import shadowed by a loop
     variable): an undefined name, a `%` format with the wrong number of arguments.
   - mypy --check-untyped-defs with the codes that need annotations this code does not carry turned off. What stays on catches a
     record formatted in the wrong order (`'%d %s %d' % arrow` when the fields are a, b, kind), a call with too many arguments, an
     attribute a value does not have.
2. rules.selftest(): the phrase, close and blocked-note rules.
3. The failure paths, run on a copy of example/sample-lineage.svg: every line that only prints when something goes wrong runs at least
   once, and no script may lose an arrow it did not report:
   - move.py with every label refused (route.place_label_any patched to find nothing): each moved arrow prints its "has no label" PROBLEM;
   - move.py again on that output, moving the box back: the arrows that had no label get one, and none may disappear;
   - move.py onto another box (a place PROBLEM), and inside a keep-out area (each arrow of the box finds no path, goes to nopath);
   - reroute.py with every label refused;
   - check_diag.py on the picture with the overlapping box: it must print FAIL lines, not a traceback.
The in-process runs call each script's main() with sys.argv set, so a crash shows its traceback here.
"""
import contextlib, io, os, re, shutil, subprocess, sys, tempfile, traceback
sys.pycache_prefix = os.path.join(tempfile.gettempdir(), 'bbb-github-diag-pycache')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model, move, reroute, route, rules, svgmeta

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
    """(exit code, stdout) of mod.main() with sys.argv = argv. no_labels: route.place_label_any finds no place for any label."""
    old_argv, old_place = sys.argv, route.place_label_any
    sys.argv = [mod.__file__] + argv
    if no_labels:
        route.place_label_any = lambda *a, **k: None
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
        sys.argv, route.place_label_any = old_argv, old_place
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

    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), c], capture_output=True, text=True)
    m = re.search(r'^FAILS (\d+)', r.stdout, re.M)
    check('Traceback' not in r.stderr and m is not None and int(m.group(1)) > 0,
          'check_diag.py on an overlapping box prints FAIL lines' + ('' if 'Traceback' not in r.stderr else ':\n' + r.stderr))
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_diag.py'), EXAMPLE], capture_output=True, text=True)
    check(r.returncode == 0 and re.search(r'^FAILS 0$', r.stdout, re.M) is not None, 'check_diag.py on the example: FAILS 0')


def main():
    if '--no-static' not in sys.argv:
        static()
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        passed = rules.selftest()                # True when every rule case passes
    check(passed, 'rules.selftest()' + ('' if passed else ':\n' + buf.getvalue()))
    check(model.no_label(model.Arrow(10, 11, 'closed by')) == '#10 closed by #11 has no label: no place on it or beside it',
          'model.no_label wording')
    with tempfile.TemporaryDirectory() as tmp:
        failure_paths(tmp)
    print('selftest: %s' % ('OK' if not fails else '%d FAILED: %s' % (len(fails), '; '.join(f.split(':')[0] for f in fails))))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
