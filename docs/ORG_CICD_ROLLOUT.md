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
- Protected branches: `main`, `develop`, `production`
- Required checks: `CI Pull Request / ci`
- Required reviews:
  - `main`: 2
  - `develop`: 1
  - `production`: 2
- Require CODEOWNERS review
- Dismiss stale approvals
- Block direct pushes to `production`

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
```

## Notes
- Scripts require GitHub CLI (`gh`) authenticated with admin/repo permissions.
- For repositories with non-Python stacks, define language-specific test commands when calling the reusable workflow.
