#!/usr/bin/env python3
"""Start a new revision of a lineage diagram: copy the file and drop every `new` pill. Nothing else changes.

usage: new_revision.py old.svg new.svg [--add N[,N...]]

- The old file is never touched (a frozen revision stays frozen). The new file must not exist yet.
- `--add` is only a reminder printed at the end: the `new` pill of a box added in this revision is drawn by the
  build or by hand; this script does not draw pills.
- Afterwards: `refresh_meta.py ... --apply` for the state changes, then `check_diag.py new.svg old.svg`.
"""
import os, re, sys


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        sys.exit(__doc__)
    old, new = args
    if os.path.exists(new):
        sys.exit('%s exists: a revision is never overwritten here' % new)
    s = open(old, encoding='utf-8').read()
    # a `new` pill: <g transform="rotate(-45 cx cy)"> rect + text "new" </g>, inside a box group
    pat = re.compile(r'\n?<g transform="rotate\(-45 [\d.]+ [\d.]+\)">\s*<rect [^>]*fill="#ff2a2a"[^>]*/>\s*<text class="pill"[^>]*>new</text>\s*</g>')
    out, n = pat.subn('', s)
    open(new, 'w', encoding='utf-8').write(out)
    print('%s -> %s: %d new pills dropped' % (old, new, n))
    if '--add' in sys.argv:
        print('add the pill by hand or in the build for: %s' % sys.argv[sys.argv.index('--add') + 1])
    print('next: refresh_meta.py ... --apply, then check_diag.py %s %s' % (new, old))


if __name__ == '__main__':
    main()
