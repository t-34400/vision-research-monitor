#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <commit-message> <path> [<path> ...]" >&2
  exit 2
fi

: "${CANONICAL_BRANCH:?CANONICAL_BRANCH must be set}"

commit_message=$1
shift

stage_if_match_exists() {
  local path=$1

  if git ls-files -- "$path" | grep -q .; then
    git add -- "$path"
    return
  fi

  if [[ -f "$path" || -L "$path" ]]; then
    git add -- "$path"
    return
  fi

  if [[ -d "$path" ]] && find "$path" -type f -print -quit | grep -q .; then
    git add -- "$path"
  fi
}

for path in "$@"; do
  stage_if_match_exists "$path"
done

if git diff --cached --quiet; then
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "$commit_message"
git pull --rebase origin "$CANONICAL_BRANCH"
git push origin "HEAD:$CANONICAL_BRANCH"
