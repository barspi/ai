#!/usr/bin/env python3
"""Put this skill's current page scripts into a diagram: the find box (find-box.js), the click highlight (click-highlight.js) and the
Shift + scroll zoom (shift-zoom.js).

usage: refresh_scripts.py IN.svg OUT.svg        (OUT may be IN)
As a module: refresh_scripts.refresh(svg_text) -> svg_text. build.py and new_revision.py call it, so a new picture and every new
revision carry the scripts as the skill has them now; run the command only on a file made some other way.

- The find box script is the first <script> of the file; its body is replaced (it is added before </svg> when there is none). It must
  stay after the pop-ups (collapse.py puts them before the first <script>).
- The click highlight script <script id="click-highlight"> comes right after the find box script, and the Shift + scroll zoom script
  <script id="shift-zoom"> right after it; they are replaced or added. They run after the find box script has moved the drawing into an
  inner <svg>.
Nothing else in the file changes. Running it twice gives the same file.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIND = re.compile(r'<script type="text/javascript"><!\[CDATA\[.*?\]\]></script>', re.S)
CLICK = re.compile(r'<script type="text/javascript" id="click-highlight"><!\[CDATA\[.*?\]\]></script>\n?', re.S)
ZOOM = re.compile(r'<script type="text/javascript" id="shift-zoom"><!\[CDATA\[.*?\]\]></script>\n?', re.S)


def tag(name, attrs=''):
    body = open(os.path.join(HERE, name), encoding='utf-8').read().rstrip('\n')
    return '<script type="text/javascript"%s><![CDATA[\n%s\n]]></script>' % (attrs, body)


def refresh(text):
    find, click, zoom = tag('find-box.js'), tag('click-highlight.js', ' id="click-highlight"'), tag('shift-zoom.js', ' id="shift-zoom"')
    text = ZOOM.sub('', CLICK.sub('', text))
    if FIND.search(text):
        text = FIND.sub(lambda m: find, text, count=1)
    else:
        i = text.rindex('</svg>')
        text = text[:i] + find + '\n' + text[i:]
    i = FIND.search(text).end()
    return text[:i] + '\n' + click + '\n' + zoom + text[i:]


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = open(sys.argv[1], encoding='utf-8').read()
    out = refresh(src)
    open(sys.argv[2], 'w', encoding='utf-8').write(out)
    print('scripts: find box, click highlight and Shift + scroll zoom (%s)' % ('unchanged' if out == src else 'updated'))
