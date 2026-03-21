#!/usr/bin/env bash
set -euo pipefail

# Usage examples:
#   bash scripts/bootstrap_org_rules.sh basic-blockchain
#   bash scripts/bootstrap_org_rules.sh basic-blockchain "repo-a,repo-b" "CI Pull Request / ci" "2" "1" "2"

ORG="${1:?Missing org}"
REPO_LIST="${2:-}"
REQUIRED_CHECK="${3:-CI Pull Request / ci}"
MAIN_APPROVALS="${4:-2}"
DEVELOP_APPROVALS="${5:-1}"
PRODUCTION_APPROVALS="${6:-2}"

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
  bash scripts/bootstrap_github_rules.sh "$ORG" "$repo" "$REQUIRED_CHECK" "$MAIN_APPROVALS" "$DEVELOP_APPROVALS" "$PRODUCTION_APPROVALS"
done

echo "Organization bootstrap completed for ${#repos[@]} repositories."
