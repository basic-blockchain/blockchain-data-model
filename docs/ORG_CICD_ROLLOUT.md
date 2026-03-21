# Organization CI/CD Rollout Plan (`basic-blockchain`)

## Goal
Roll out a consistent CI/CD and repository governance baseline across all current and future repositories, regardless of language.

## Recommended baseline repository
Create an organization repository named `.github` and place there:
- Reusable workflows (polyglot CI, security checks, release checks)
- Organization-wide PR template
- Default issue templates

Then reference workflows from every repository:

```yaml
jobs:
  ci:
    uses: basic-blockchain/.github/.github/workflows/reusable-ci-polyglot.yml@main
    with:
      language: auto
      run-tests-command: "pytest -q"
```

## Branch governance baseline
- Protected branches: `production`, `main`, `staging`, `qa`, `develop`
- Required checks: `CI Pull Request / ci`
- Required reviews:
  - `production`: 2
  - `main`: 2
  - `staging`: 1
  - `qa`: 1
  - `develop`: 1
- Require CODEOWNERS review
- Dismiss stale approvals
- Block direct pushes to `production`

## Promotion chain policy
- Promotion is PR-based and automated through workflow:
  - `production -> main`
  - `production -> staging`
  - `staging -> qa`
  - `qa -> develop`
- This keeps `main` synchronized with production while preserving staged validation layers.
- Direct local pushes to `production` are blocked by `.githooks/pre-push`.

## Rollout sequence
1. Apply workflows and templates in this repository as reference implementation.
2. Create/update the organization `.github` repository with reusable assets.
3. Migrate each repository to consume the centralized reusable workflows.
4. Apply branch protections in bulk using automation.

## Automation scripts in this repository
- Per repository setup:
  - `scripts/bootstrap_github_rules.sh`
- Organization-wide setup:
  - `scripts/bootstrap_org_rules.sh`
- Unified org CLI (bootstrap + audit + promotion PR):
  - `scripts/devsecops_org_cli.sh`
- Batch onboarding report (pre/post snapshot):
  - `scripts/devsecops_org_onboarding.sh`
- Promotion chain PR automation:
  - `scripts/devsecops_promotion_chain.sh`
- GitHub CLI auth helper for Git Bash/Windows:
  - `scripts/gh_auth_setup.sh`

## GitHub CLI operational model
Use `gh` as the standard control plane for organization-wide DevSecOps operations.

Pre-requisites:
- `gh` installed and authenticated (`gh auth login`)
- Admin permissions for repository branch protection updates

Recommended lifecycle:
1. Run `audit` to detect missing branches/protections.
2. Run `bootstrap` in `DRY_RUN=true` mode to validate intended actions.
3. Run `bootstrap` without dry-run to apply protections in bulk.
4. Use `promote-pr` for manual promotions when needed.
5. Run `onboard` to generate pre/post evidence reports.
6. Use `promote-chain` to create all promotion PRs in one command.

Core commands:

```bash
bash scripts/devsecops_org_cli.sh audit basic-blockchain
DRY_RUN=true bash scripts/devsecops_org_cli.sh bootstrap basic-blockchain
bash scripts/devsecops_org_cli.sh bootstrap basic-blockchain
bash scripts/devsecops_org_cli.sh promote-pr basic-blockchain blockchain-data-model qa develop
bash scripts/devsecops_org_cli.sh promote-chain basic-blockchain blockchain-data-model
APPLY_CHANGES=true bash scripts/devsecops_org_cli.sh onboard basic-blockchain
bash scripts/devsecops_org_cli.sh auth-login
```

## GitHub CLI authentication from scripts
If `gh` is not found in Git Bash, use script helpers:

```bash
bash scripts/gh_auth_setup.sh enable-path
source ~/.bashrc
bash scripts/gh_auth_setup.sh login
bash scripts/gh_auth_setup.sh status
```

## Onboarding evidence reports
- The onboarding script exports CSV and summary files under `reports/devsecops/`.
- Report includes both phases:
  - `pre`: status before applying controls
  - `post`: status after applying controls
- Useful for compliance evidence and change management records.

Direct onboarding command:

```bash
APPLY_CHANGES=false bash scripts/devsecops_org_onboarding.sh basic-blockchain
APPLY_CHANGES=true bash scripts/devsecops_org_onboarding.sh basic-blockchain "repo-a,repo-b"
```

Optional bootstrap tuning:

```bash
REQUIRED_CHECK="CI Pull Request / ci" \
MAIN_APPROVALS=2 DEVELOP_APPROVALS=1 PRODUCTION_APPROVALS=2 STAGING_APPROVALS=1 QA_APPROVALS=1 \
bash scripts/devsecops_org_cli.sh bootstrap basic-blockchain
```

## Local collaboration guardrails
- This repository includes `.githooks/pre-push` to block direct local pushes to `production`.
- Ensure hooks are active in each clone:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push .githooks/commit-msg
```

## Example commands
```bash
bash scripts/bootstrap_github_rules.sh basic-blockchain blockchain-data-model
bash scripts/bootstrap_org_rules.sh basic-blockchain
bash scripts/bootstrap_org_rules.sh basic-blockchain "repo-a,repo-b" "CI Pull Request / ci"
bash scripts/devsecops_org_cli.sh audit basic-blockchain
bash scripts/devsecops_org_cli.sh promote-pr basic-blockchain blockchain-data-model production main
```

## Notes
- Scripts require GitHub CLI (`gh`) authenticated with admin/repo permissions.
- For repositories with non-Python stacks, define language-specific test commands when calling the reusable workflow.
