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
- Prefer a wider picture to a crossing.

### Compactness

Make the picture as compact as clarity allows, so it fits a screen or a page better. The order of priority is: clarity first, then no unintended overlap and no crossing, then compactness.

- Use both directions. Do not let the picture grow only down a long column or only across a long row.
- Keep gaps tight. Between stacked boxes, about 25–30px. Between dotted frames, about 35px of visible space. Frame padding, about 40px above (room for the frame title) and 20px below. A horizontal gap is as wide as its longest label plus about 50px of visible shaft, and no wider.
- Look for large blank areas. Where one exists, consider moving a node, or a whole framed group, into it. Do this only if the arrows stay easy to follow: no new crossing, no arrow that doubles back across the picture, and no box that hides the flow from earlier to later.
- A column that holds a single box at the end of a chain can often fold under its neighbor, with a vertical arrow. Keep the vertical gap long enough for the label and a visible tail and head (about 100px for `closed by`).
- Good groups to move are those with few incoming arrows and none leaving the group, such as a separate umbrella linked to the source only by dashed references. In the acquirer-fee lineage, moving the jCard fees frame from below the left column to the blank area under the on-us frame cut the height by 20%.
- When a moved group's incoming arrows must cross a column of boxes, give them a corridor. Leave a horizontal gap between two frames (about 30px per arrow), run each arrow along its own line in that gap, then turn toward the target in the gutter before the target's frame. Treat the corridor height as the arrow's target height when you order the trunks, so its trunk nests with the others and nothing crosses. Put the label on the last segment, which enters the box. One corridor is fine. Each additional long corridor makes the source's fan harder to read, so weigh it against the height it saves.
- Keep an arrow at least about 30px from a frame's dotted border when it runs parallel to it. A dashed arrow next to a dotted border reads as one line.
- When a change makes the picture smaller, compare the before and after rasters. If following an arrow is harder after the change, undo it.

## Files

Small corrections edit the current SVG. Write a new `_v2`, `_v3`, … file only when the user asks for a new revision or the layout is being replaced. Do not emit a PDF unless the user asks for one. When they do, keep the issue and pull-request numbers as links.

## Check

Rasterize and look. Confirm:

- the source the user named has arrows leaving it
- every `closed` box has a visible `closed by` arrow to a pull request, or the box says why it has none
- no sibling is drawn as the parent of the other
- labels do not cover the tail or the head
- every label is in the vocabulary, and reads correctly as "A, label, B"
- every merged pull request shows its commit authors after the merge commit
- no large blank area remains that a node or framed group could fill without making the arrows harder to follow
- pill text is the box color, not black
- each issue number and each pull-request number is a link to its GitHub page
