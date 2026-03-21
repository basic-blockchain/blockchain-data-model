#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/bootstrap_github_rules.sh basic-blockchain blockchain-data-model

ORG="${1:?Missing org}"
REPO="${2:?Missing repo}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install from https://cli.github.com/" >&2
  exit 1
fi

# Ensure develop exists remotely.
if ! gh api repos/${ORG}/${REPO}/branches/develop >/dev/null 2>&1; then
  echo "Creating develop branch from main..."
  MAIN_SHA="$(gh api repos/${ORG}/${REPO}/git/ref/heads/main --jq '.object.sha')"
  gh api repos/${ORG}/${REPO}/git/refs -f ref='refs/heads/develop' -f sha="${MAIN_SHA}" >/dev/null
fi

# Enable branch protection on main.
# Requires repository admin permission.

echo "Applying branch protection to main..."
gh api -X PUT repos/${ORG}/${REPO}/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]='CI Pull Request / validate' \
  -f enforce_admins=true \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f required_pull_request_reviews.require_code_owner_reviews=true \
  -f required_pull_request_reviews.required_approving_review_count=2 \
  -f restrictions= >/dev/null

echo "Applying branch protection to develop..."
gh api -X PUT repos/${ORG}/${REPO}/branches/develop/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]='CI Pull Request / validate' \
  -f enforce_admins=true \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f required_pull_request_reviews.require_code_owner_reviews=true \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f restrictions= >/dev/null

echo "Done. Branch protections are configured for main and develop."
