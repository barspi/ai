// Local addition to the Anthropic sample (see SOURCE.txt).
//
// The decision "does this command stay inside the project and its git
// worktrees?" Pure functions, so they are tested without a session. The paths
// come from scope.sh, which prints real paths.

/** Risks that change files on disk. The rest (force push, migrations) are not about the filesystem and always hold. */
export const FILESYSTEM_KINDS = new Set(["rm", "git-reset", "git-clean", "git-checkout"]);

/**
 * True when a word names something this code cannot resolve by looking at it:
 * a variable, a command substitution, a brace list or another user's `~name`.
 * Such a command is held, since what it touches is unknown.
 */
export function hasShellSyntax(word) {
  return /[$`{}]/.test(word) || /^~[^/]/.test(word);
}

/** `path` is `root` itself or something under it. */
export function isWithin(path, root) {
  return path === root || path.startsWith(root.endsWith("/") ? root : `${root}/`);
}

/** `path` is under `root`, not `root` itself: deleting a root is not "inside". */
export function isBelow(path, root) {
  return path !== root && isWithin(path, root);
}

/** The output of scope.sh as { roots, paths }; empty roots when the script gave no usable answer. */
export function parseScope(stdout) {
  const lines = String(stdout).split("\n").filter((l) => l !== "");
  const cut = lines.indexOf("---");
  if (cut < 0) {
    return { roots: [], paths: [] };
  }
  return {
    roots: lines.slice(0, cut).filter((r) => r !== "/"),
    paths: lines.slice(cut + 1),
  };
}

/**
 * True when the command acts only inside the project or one of its worktrees,
 * or acts on nothing at all (an `rm` whose paths do not exist).
 *
 * rm: every existing target is under a root. A root itself does not count.
 * git: the folder it runs in is a root or inside one.
 * With no root to compare against, the answer is false: hold.
 */
export function staysInside(risk, roots, paths) {
  if (roots.length === 0) {
    return false;
  }
  if (risk.kind === "rm") {
    return paths.every((p) => roots.some((r) => isBelow(p, r)));
  }
  return paths.length > 0 && paths.every((p) => roots.some((r) => isWithin(p, r)));
}
