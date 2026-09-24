---
name: bbb-conflicts
disable-model-invocation: true
description: >-
  Detects merge/rebase conflicts between two git commits or refs from their
  common ancestor (merge-base): files both sides modified, independently
  created at the same path, both removed, or one modified while the other
  renamed/moved; then textual diff conflicts, logical conflicts inside a
  file, and logical conflicts across files that need the project's
  architecture. Use ONLY when the user explicitly requests it (for example
  /bbb-conflicts, names this skill, or asks to check merge conflicts /
  overlap / rebase safety between two SHAs or refs such as HEAD and
  origin/main). Do not run it automatically because remotes advanced.
---

# BBB conflicts

Apply **only on explicit request**: `/bbb-conflicts`, this skill's name, or a
clear ask to check merge conflicts / overlap / rebase safety between two
commits or refs. Advancing `origin/main` is not a trigger.

**Do not merge, rebase, checkout, or edit the worktree.** Read-only git
(`diff`, `merge-tree`, `show`, `log`). If the user then asks to rebase, that
is a different task.

## Inputs

The user passes **two commits or ref names** (SHAs, `HEAD`, `origin/main`,
branch names). Call them **ours** (first / the branch they are on) and
**theirs** (second / the other line, often `origin/main`).

If they also name a merge-base, verify it equals `git merge-base OURS THEIRS`.
If they omit it, compute that merge-base. If the two refs are not in the
current repo, stop and say so.

Resolve each input to a SHA and a one-line subject before continuing.

## What to report

From the common ancestor (or merge-base):

- First, what files have **BOTH sides modified**, or **both created the same
  file path independently**, but maybe with different content, or **both
  removed the same file** (no problem there), or maybe **one side modified a
  file and the other one renamed or moved the same file to another path**.
  Then, those are the possibly conflicting files.
- From those **POTENTIAL** conflicts, I want to know:
  - **TEXTUAL** diff conflicts (such as both sides have modified more or less
    the same hunk and a normal diff merge is impossible or difficult without
    further direction from user)
  - **LOGICAL** conflicts **within the same file**: e.g. both files have
    modified separate hunks of the same file but the code logic contradicts
    itself or produces some type of logical BUG. These conflicts sometimes
    require only looking at the internal code logic, but often requires
    UNDERSTANDING of the project's goals and architecture.
  - **LOGICAL** conflicts **in between many files** in the project as a whole.
    This conflict ABSOLUTELY REQUIRES UNDERSTANDING OF THE PROJECT'S GLOBAL
    GOALS AND ARCHITECTURE. So it must be done carefully. Typical industry
    cases: design docs or ADRs on one branch already describe a new protocol
    while the other still codes to the old assumptions; OpenAPI/schema and
    implementation have forked (broken contract, lost backward compatibility);
    a shared library's ABI or a public API changed on one side while callers
    on the other still compile against the previous types; feature-flag or
    configuration defaults disagree; migration versions collided; test
    fixtures freeze the old payload; high-level architecture has split into
    two approaches (monolith vs service boundary, sync vs async, shared DB vs
    explicit API). Use that vocabulary (API contract, ABI, schema
    compatibility, semantic versioning, bounded context, source of truth)
    when you name the break.

Write for **humans and for another AI** that may resolve or rebase next.
Cite paths and, when it matters, a short code or diff excerpt. Use the host
repo's citation conventions if it has them.

## Architecture first

Cross-file logic is worthless without the project's goals. Before judging
logical conflicts:

1. Load that repo's agent instructions (`AGENTS.md`, `CLAUDE.md`, and any
   project skill the task hits). Read only what the overlapping modules
   need: in-repo documentation, ADRs, the GitHub issue or ticket for the
   branches, and external specifications (protocol PDFs such as ISO 8583,
   OpenAPI/AsyncAPI, vendor API docs, RFCs, requirement docs). Do not
   ingest an entire documentation tree "to be sure."
2. Treat **source, tests, CI, infrastructure-as-code, and deployment
   manifests** as the source of truth for what the software does. Treat
   design docs, ADRs, comments, and the GitHub issue (or ticket) as the
   high-level or task goals; they can lag. When they disagree, name the
   drift.
3. Name the **contract** the two sides share (message shape, schema, SPI,
   NEED/hold formula, API field). A file-disjoint change can still break it.

## Git (read-only)

`A...B` means merge-base of A and B, then B. With merge-base `M`:

```text
M = git merge-base OURS THEIRS
```

### Histories

```bash
git log --oneline M..OURS
git log --oneline M..THEIRS
```

### File inventory (potential conflicts)

```bash
git diff --name-status M...OURS
git diff --name-status M...THEIRS
comm -12 <(git diff --name-only M...OURS | sort) <(git diff --name-only M...THEIRS | sort)
```

Also:

| Situation | How |
|---|---|
| Both added the same path | `comm -12` of `git diff --diff-filter=A --name-only M...OURS` and `...THEIRS` |
| Both deleted the same path | `comm -12` of `--diff-filter=D` on each side (usually harmless) |
| Rename vs modify | `--diff-filter=R` on each side vs `M`/`D` on the other; follow the similarity to the new path |
| One added, one ignored | Still list independent same-path adds; do not assume "only modifies" |

Empty intersection of names is **not** "no logical conflict." Continue to
cross-file.

### Textual merge (no worktree)

```bash
git merge-tree --write-tree --name-only --messages --merge-base=M OURS THEIRS
```

Exit **0**: Git believes it can auto-merge (may still be logically wrong).
Exit **1**: content conflict; the tool names the files. Extract hunks with
`git merge-file -p --diff3` on `git show M:path`, `OURS:path`, `THEIRS:path`
when you need the markers. Inspect the auto-merged blob of a clean overlap
with `git show <tree>:path`.

Do **not** use `git merge` / `git rebase` for this skill.

## Classify each potential file

For every overlapping path, read **both** `git diff M...OURS -- path` and
`git diff M...THEIRS -- path`.

**TEXTUAL.** Same region, conflict markers, or a rewrite vs a small insert
(Git reports one huge hunk). Say whether a resolver should take theirs and
re-insert ours (typical when they rewrote a doc and we added a sentence).

**LOGICAL, same file.** Hunks do not overlap, Git auto-merges, but the
combined file is inconsistent: mixed models in one suite, a comment that
contradicts a nearby table, a test that still pins the pre-change shape, an
API field both sides redefined differently. Confirm the auto-merged result
**keeps both edits** and then ask whether those edits agree.

**Both deleted.** Note it; usually no work.

**Rename vs modify.** Treat as a potential conflict on the **new** path plus
any leftover old path. Textual merge may miss it.

## Cross-file / whole-project logic

Large teams on separate branches usually do not collide on the same hunk.
They collide on **shared contracts**: public APIs, event and wire schemas,
database migrations, SPI/plugin surfaces, feature flags, configuration
defaults, and the fixtures that freeze those shapes. Integration tests,
end-to-end suites, and generated clients are often the first place the
break shows, even when neither side touched the other's implementation
files. Git's name intersection is necessary but not sufficient.

Even when implementation-file lists do not intersect:

1. What **incoming contract** did ours change (wire fields, DTO, schema,
   template variables, seed data)?
2. What **consumer** did theirs add or change (pricing, posting, tests,
   another station)?
3. After compose: does the money/API/schema invariant still hold in one
   unit (one currency, one id space, one on-the-wire shape)? Did ours
   rewrite a field theirs now reads? Did a test or suite still send the
   pre-change payload?

Look at tests and suites that **exercise the boundary**, not only files in
the name intersection. A new case on theirs that never carries the field
we changed is a no-op; a case neither side edited in this window can still
be wrong if ours changed the meaning of that payload.

Stale design docs versus live code are **doc drift**, not a merge blocker,
unless the auto-merge would resurrect a stale sentence on top of a rewrite.
Prefer **their** rewritten doc and re-home **our** fact in the current
section.

## Report shape

Lead with refs: ours SHA, theirs SHA, merge-base SHA, commit lists (short).

### 1. Potential files

A table: path | ours change | theirs change. Include same-path adds, both
deletes, rename-vs-modify. If none, say so, then still do §4.

### 2. TEXTUAL

Named files with conflict, or **none**. For each: why Git lost (same hunk vs
rewrite vs insert), and a recommended resolution (often: take theirs, re-insert
our sentence in the equivalent new heading). Link to the files and the
conflicting hunks; include a brief diff when it is only a few lines.

### 3. LOGICAL within a file

Per overlapping path that auto-merges: both edits present? Do they agree?
Call out mixed models in one file. Link to the files and the hunks; include
a brief diff when it is only a few lines.

### 4. LOGICAL across files / modules

The contract, what each side assumes, whether they compose, residual watches
(future consumers). Cite the functions that implement the compose. Explain
these thoroughly; include a short walk-through of the logic when it fits.
If the conflicts are many or long, offer to write them to a file for later
inspection rather than dumping them all in chat.

### 5. Plan (only if asked, or one short paragraph)

Detection is the default. If they want a rebase plan: stash unrelated dirty
tracked files; rebase onto theirs; expect stops only on TEXTUAL files; take
theirs then re-insert; leave Java alone unless a cross-file bug requires it;
name the tests on the boundary.

Do not start that rebase in this skill unless they asked.

## Pattern from a prior run

Branch vs `origin/main`: two or four overlapping docs/YAML; `git merge-tree`
clean, or one design-note rewrite vs a small insert (TEXTUAL: take theirs,
re-home the sentence). No Java overlap. Cross-file: station peeled a fee
out of the principal; issuer `need = amount + issuerFee + acquirerFee` still
composed; a later FX reader of the billing amount is a watch. Auto-merged
YAML kept a CIS-inclusive case next to exclusive cases neither side edited
in that window—that is **LOGICAL within a file**, not textual.
