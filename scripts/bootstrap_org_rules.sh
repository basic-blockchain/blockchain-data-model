#!/usr/bin/env bash
set -euo pipefail

# Usage examples:
#   bash scripts/bootstrap_org_rules.sh basic-blockchain
#   bash scripts/bootstrap_org_rules.sh basic-blockchain "repo-a,repo-b" "CI Pull Request / ci"

ORG="${1:?Missing org}"
REPO_LIST="${2:-}"
REQUIRED_CHECK="${3:-CI Pull Request / ci}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install from https://cli.github.com/" >&2
  exit 1
fi

if [[ -z "$REPO_LIST" ]]; then
  mapfile -t repos < <(gh repo list "$ORG" --limit 200 --json name --jq '.[].name')
else
  IFS=',' read -r -a repos <<< "$REPO_LIST"
fi

for repo in "${repos[@]}"; do
  repo="$(echo "$repo" | xargs)"
  [[ -z "$repo" ]] && continue
  echo "Configuring protections for ${ORG}/${repo}..."
  bash scripts/bootstrap_github_rules.sh "$ORG" "$repo" "$REQUIRED_CHECK" "2" "1"
done

echo "Organization bootstrap completed for ${#repos[@]} repositories."
