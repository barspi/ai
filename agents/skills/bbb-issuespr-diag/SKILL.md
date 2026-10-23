---
name: bbb-issuespr-diag
disable-model-invocation: true
description: >-
  Draws a directed acyclic graph of GitHub issues and pull requests as a
  hand-authored SVG: parent to child, what closed what, what is still open.
  Use ONLY when the user explicitly asks (for example /bbb-issuespr-diag,
  names this skill, or asks for an issue/PR lineage diagram or DAG). Do not
  run it because a conversation mentions issue numbers.
---

# Github issue and pull-request lineage diagram

Apply only on an explicit request. This is not a composition diagram. Do not use it to show how a result is assembled. That is `bbb-code-flow`.

Borrow from `bbb-code-flow` only the drawing hygiene: cream page `#f3f0e8`, ink `#1c2430`, SVG with a title and a description, numeric entities for dashes and arrows, orthogonal paths, and a look at a raster before you call it done. The graph rules below win when they differ.

## What a node is

One box is one issue or one pull request. Read the facts from `gh`, not from memory.

Each box shows:

- `ISSUE`, `UMBRELLA`, or `PR`, and the number, as a link (see Links)
- the title
- opened date, and closed or merged date when it has one
- the merge commit, short, on a pull request
- on a merged pull request, right after the merge commit and in parentheses, the GitHub usernames of the pull request's commit authors, in first-commit order: `merge 3229bfa45 (barspi, ar)`. With more than two authors, write the first username and `et al.`: `(barspi et al.)`. Read them with `gh api repos/OWNER/REPO/pulls/N/commits` (`.author.login`). The account that opened the pull request is a different fact; do not substitute it. A pull request that is not merged shows its branch commits and no authors.
- a design document or memo when one is the source of that item

A status pill sits in the upper right. The word is `open`, `closed`, `merged`, or `waiting`.

| State | Box | Pill fill | Pill text |
|---|---|---|---|
| Open issue or open umbrella | `#f8e8e4` / stroke `#8a3030` | `#9f2d2d` | the box fill `#f8e8e4` |
| Closed issue or closed umbrella | gray `#eceae6` / stroke `#6e6a64` | `#4e4b48` | the box fill `#eceae6` |
| Merged pull request | `#e7f0fb` / stroke `#1d4e89` | `#163e73` | the box fill `#e7f0fb` |
| Pull request waiting for review | saturated yellow `#ffe566` / stroke `#c48a00` | `#e6a100` | the box fill `#ffe566` |

Open issues and open umbrellas are the same color. Say `UMBRELLA` in the label when it is one. Closed is gray, not green.

Set the pill text with a `style="fill:…"` attribute. A shared SVG text class will otherwise paint it black.

### The `new` pill

When you update a diagram, mark every box that was not in the previous revision with a `new` pill. It tells the reader what to look at first. Mark only boxes added in this update, not boxes whose state changed. Remove the old `new` pills when you make the next revision.

- Position: on the top-left corner of the box, centered on the corner (nudge it about 2px inside), rotated −45° so it reads up and to the right across the corner. It is a corner ribbon, not a label inside the box.
- Color: bright red `#ff2a2a`, white text, a thin stroke in the page color `#f3f0e8` so it separates from the box edge.
- Size: the text is 85% of the status-pill text (8.9px when the status pill is 10.5px), bold, letter-spacing about 0.3px. Keep the margin tight: about 25px wide and 12.5px tall for the word `new`, fully rounded ends.
- Keep arrows and labels clear of it. Treat it as an obstacle when you route.

## Links

Every issue number and every pull-request number is a link to the GitHub page. Issue `#1752` goes to `https://github.com/ar/mgl/issues/1752`. Pull request `#1757` goes to `https://github.com/ar/mgl/pull/1757`. Use the repository that owns the item. In SVG, wrap the number text in `<a href="…">`.

If the user asks for a PDF, those same numbers are links there too. A PNG cannot hold a link. Do not promise links on a raster.

## What an arrow is

The picture is a directed acyclic graph. Arrows point forward, from the earlier item to the later one.

- A source has no arrow pointing into it. `#1752` is that kind of node for the acquirer-fee lineage.
- Read every arrow as a sentence from tail to head: A, label, B. `#1891 closed by #1965`. When the later item acts on the earlier one, the label is passive (`closed by`, `revised by`, `work done by`). A noun label (`child`, `follow-up`) names what B is to A.
- Use only the labels in the vocabulary below. If no label fits, add one to this table first, with its definition. Do not invent a label in the picture. Do not use two labels for one meaning.
- When a pull request closed an issue, say the pull request number on the issue box as well.
- If two items both come from the same item, draw two arrows out of that item. Do not draw an arrow between the two siblings. Parallel is not a chain.
- A node may have no outgoing arrow. An open issue with no pull request is that kind of node. It still has its incoming arrow.

### Arrow vocabulary

| Label | Line | `A → B` means |
|---|---|---|
| `child` | solid, ink | B is a formal child of umbrella A: A lists B, or B names A as its parent. |
| `follow-up` | solid, brown | B was filed to finish something that A left out. |
| `led to` | solid, brown | Work on A produced B. |
| `found` | solid, brown | Work on A exposed the defect that B reports. |
| `spawned` | solid, brown | A caused B to be filed as a new umbrella or work stream. |
| `revised by` | solid, brown | B is a later pull request that changes what pull request A delivered. |
| `closed by` | solid, blue | B is the pull request that closed issue A. |
| `work done by` | dashed, blue | B did work for A but did not close it. A was closed by hand, or stays open. |
| `evidence, does not close` | dashed, amber | B gives evidence for A. A stays open. |
| `uses` | dashed, gray | A depends on the result of B. |
| `references` | dashed, gray | A's text points to B as relevant prior work. |
| `mentioned` | dashed, gray | A names B in passing. B is not part of this lineage. |
| `related` | dashed, gray | A and B are related work. Neither is the parent of the other. |

A dotted frame may name an area (`ss-visa`, `ss-mastercard`, `jCard`). The frame does not replace an arrow. Do not put the parentage only in a section title.

## Layout

Use the plane. Rows and columns are for alignment, not a substitute for edges.

- Leave a gap long enough that the label, which has an opaque background, does not cover the whole shaft. The tail and the arrowhead stay visible. A gap under about 150px is too small for a `closed by` label.
- Draw every path first, then every label, so a later path cannot hide an earlier label. Labels sit on top of the stroke.
- Put the label on a long segment of that arrow, not on a stub, and not on a bus shared by many arrows. A shared bus stacks the words.
- When one item has several children, fan the arrows. A vertical column of children with the parent on one side and the closing pull request on the other is the pattern: arrows leave the parent and enter each child; `closed by` arrows leave those children and converge on the pull request. Give each arrow its own vertical position so the labels do not sit on each other, and so each arrowhead can be seen.
- Do not route an arrow through a box. If a box sits between two ends, go around it in a gutter.
- Prefer a wider picture to a crossing. When a crossing cannot be avoided, see "Hard arrows" below.

### Compactness

Make the picture as compact as clarity allows, so it fits a screen or a page better. The order of priority is: clarity first, then no unintended overlap and no crossing, then compactness.

- Use both directions. Do not let the picture grow only down a long column or only across a long row.
- Keep gaps tight. Between stacked boxes, about 25–30px. Between dotted frames, about 35px of visible space. Frame padding, about 40px above (room for the frame title) and 20px below. A horizontal gap is as wide as its longest label plus about 50px of visible shaft, and no wider.
- Look for large blank areas. Where one exists, consider moving a node, or a whole framed group, into it. Do this only if the arrows stay easy to follow: no new crossing, no arrow that doubles back across the picture, and no box that hides the flow from earlier to later.
- A column that holds a single box at the end of a chain can often fold under its neighbor, with a vertical arrow. Keep the vertical gap long enough for the label and a visible tail and head (about 80px for `closed by`: an 18px label, about 25px of straight shaft above and below it, and the arrowhead). Measure the shaft as the straight line only, from the tail to the base of the arrowhead (the tip minus about 11px). Center the label on that straight shaft, so both visible shafts are equal, even when neither is as long as on a horizontal arrow. An error of up to about 6px is fine; centering on the tail-to-tip span, which is off by half the arrowhead, is acceptable.
- Good groups to move are those with few incoming arrows and none leaving the group, such as a separate umbrella linked to the source only by dashed references. In the acquirer-fee lineage, moving the jCard fees frame from below the left column to the blank area under the on-us frame cut the height by 20%.
- When a moved group's incoming arrows must cross a column of boxes, give them a corridor. Leave a horizontal gap between two frames (about 30px per arrow), run each arrow along its own line in that gap, then turn toward the target in the gutter before the target's frame. Treat the corridor height as the arrow's target height when you order the trunks, so its trunk nests with the others and nothing crosses. Put the label on the last segment, which enters the box. One corridor is fine. Each additional long corridor makes the source's fan harder to read, so weigh it against the height it saves.
- Keep an arrow at least about 30px from a frame's dotted border when it runs parallel to it. A dashed arrow next to a dotted border reads as one line.
- When a change makes the picture smaller, compare the before and after rasters. If following an arrow is harder after the change, undo it.

### Hard arrows

Some arrows have no clean path: the tail's side is full of other arrows, or a column of boxes sits between the ends. Do not let them shape the layout. Finish the main layout first, with every easy arrow in place. Then route the hard ones last, in this order: the ones with the fewest options first, then the rest. Route them with a script on a grid (5px is enough), not by eye.

Rules for a hard arrow:

- Never draw it under a box or under a label. Keep it about 26px from boxes and 10px from labels, and clear of any `new` pill.
- Never run it parallel to another line closer than about 36px. Two lines closer than that read as one.
- It may cross another line only at a right angle, and only on a long straight stretch: at least about 30px from either line's bends and from its arrowhead. Never turn on top of a line.
- Draw each crossing as a small jump: a semicircle of about 7px radius, over the line already there. A horizontal arrow hops up. A vertical arrow hops to the right. The older line stays straight.
- Minimize crossings first, then bends. Do not leave a jog shorter than about 30px; a flat lane at a slightly different height is better.
- Put the label on a long straight stretch, away from every jump and from other lines.
- Each hard arrow keeps its own entry point on the target's edge, about 40px from the others, and enters it straight for at least 25px before the arrowhead.
- If no path meets the rules, leave that arrow out of the picture, name it in the box note and in your report, and say what would have to move to make room. Do not draw it with a worse path.

## Files

Small corrections edit the current SVG. Write a new `_v2`, `_v3`, … file only when the user asks for a new revision or the layout is being replaced. Do not emit a PDF unless the user asks for one. When they do, keep the issue and pull-request numbers as links.

## Check

Check from the SVG text and geometry, with a script, not by looking. A script costs seconds and no image tokens. Look at a rendered image only at the end (see "Looking at the picture").

### Measure text once

- Measure the width of each text style one time, with the real font, and keep the table: title, meta, mono, note, status pill, `new` pill, edge label. Use the table for every occurrence. Do not measure again for each box.
- The pill words and the edge labels are a small, fixed set (`open`, `closed`, `merged`, `waiting`, `new`, and each label in the vocabulary). Measure each word once, then set the pill or label width from it: text width plus the padding. Do not guess a width per pill.
- Wrap titles and notes with the table, not by a character count. Fail the check when any line is wider than the inner width of its box.

### Checks on every run (script)

- The SVG is well-formed XML. Every node has a box, a kind, a number link, a status pill and a pill word that matches the state read from `gh`.
- Content, by text search: every item in the revision appears once, as a link to the right page (`issues` or `pull`); every merged pull request shows its merge commit and its authors; every `closed` box has a `closed by` arrow or says why not; the source has arrows leaving it; no arrow joins two siblings; every label is in the vocabulary; pill text uses the box color; the legend and the date line name the current items and the current date.
- Geometry, from the path points and the box and label rectangles: no segment passes through a box, a label or a pill; no unintended crossing; no two parallel lines closer than the spacing rules; no label covers the tail or the head; every arrowhead enters its box straight; no jog shorter than about 30px; every endpoint touches the edge of its box.
- Revision marks: on an update, exactly the boxes added since the previous revision have a `new` pill on the top-left corner, and no other box has one.
- Report the largest empty rectangle. If a node or a framed group could fill it without making an arrow harder to follow, move it.
- Any arrow left out as too hard is named in the report.

When a check fails, fix the cause and run the script again. Do not look at an image to find out what is wrong.

### Looking at the picture

Look at most twice. Look only at crops of the regions that changed, at reduced size, not at the whole picture.

1. After the main layout, when boxes moved or arrows were added: one look at the changed regions.
2. At the end, after the hard arrows are routed: one look at the regions with jumps and `new` pills. Check that each hop bumps the right way and still reads as one line, and that nothing looks like clutter. Do not look at the jumps before this step.

Skip both looks when only states, dates or text changed. A PNG is only for this look. Do not keep it unless the user asks for one.
