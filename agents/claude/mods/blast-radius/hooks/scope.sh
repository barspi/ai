#!/usr/bin/env bash
# Local addition to the Anthropic sample: where does a command act, relative to
# the project and its git worktrees?
#
# Usage: scope.sh <project-root> <mode> [targets...]
#
# Prints the real path of the project root and of every git worktree of that
# project, then a line "---", then:
#   mode "rm"  : the real path of each EXISTING rm target (globs expanded);
#                a missing target prints nothing (rm would do nothing to it)
#   mode "dir" : the real path of the current folder
#
# Paths are only ever read as arguments: nothing in them is run.
shopt -s nullglob dotglob

# Real path of the thing itself. A symbolic link is not followed at the last
# step, because `rm link` removes the link and not what it points to.
real() {
  local p="$1" d b
  case "$p" in "~"|"~/"*) p="$HOME${p#\~}" ;; esac
  if [[ -d "$p" && ! -L "$p" ]]; then
    (cd -- "$p" 2>/dev/null && pwd -P)
    return
  fi
  d=$(dirname -- "$p")
  b=$(basename -- "$p")
  d=$(cd -- "$d" 2>/dev/null && pwd -P) || return 1
  printf '%s/%s\n' "${d%/}" "$b"
}

root="$1"
mode="$2"
shift 2

r=$(cd -- "$root" 2>/dev/null && pwd -P) && printf '%s\n' "$r"
if wt=$(git -C "$root" worktree list --porcelain 2>/dev/null); then
  while IFS= read -r line; do
    case "$line" in
      "worktree "*)
        p=$(cd -- "${line#worktree }" 2>/dev/null && pwd -P) && printf '%s\n' "$p"
        ;;
    esac
  done <<< "$wt"
fi
echo "---"

if [[ "$mode" == "dir" ]]; then
  pwd -P
  exit 0
fi

for p in "$@"; do
  case "$p" in "~"|"~/"*) p="$HOME${p#\~}" ;; esac
  if [[ "$p" == *[*?[]* ]]; then
    while IFS= read -r m; do
      real "$m"
    done < <(compgen -G "$p")
  elif [[ -e "$p" || -L "$p" ]]; then
    real "$p"
  fi
done
