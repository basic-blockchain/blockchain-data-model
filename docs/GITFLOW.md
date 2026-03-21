# Gitflow and Delivery Policy

## Organization scope
- This policy is intended for all repositories under `basic-blockchain`.
- Keep repository governance (`CODEOWNERS`, PR templates, labels, workflows) aligned across projects.
- Prefer a central organization repository named `.github` to host reusable workflows and templates.

## Branch model
- `main`: production-ready history.
- `develop`: integration branch for the next release.
- `feature/*`: regular feature work from `develop`.
- `refactor/*`: architecture and codebase improvements from `develop`.
- `release/*`: release hardening branch from `develop`.
- `hotfix/*`: urgent fixes from `main`.

## Pull request rules
- `feature/*` and `refactor/*` must target `develop`.
- `release/*` and `hotfix/*` can target `main`.
- PR must pass CI and require at least 2 approvals.
- Dismiss stale approvals when new commits are pushed.
- Require conversation resolution before merge.
- Enforce CODEOWNERS review where applicable.

## Merge strategy
- Use squash merge for feature/refactor branches.
- Use merge commit for release and hotfix branches to preserve context.

## CI/CD strategy for multi-language repositories
- Use a reusable workflow as baseline for all repositories.
- Keep language-specific test commands configurable per repo.
- Suggested required status check context: `CI Pull Request / ci`.
- Minimum controls for `main` and `develop`:
	- Required status checks enabled.
	- Required pull request reviews enabled.
	- Dismiss stale reviews enabled.
	- CODEOWNERS review enabled.

## Organization bootstrap automation
- Repository-level protections:
	- `scripts/bootstrap_github_rules.sh`
- Organization-wide protections (all repos or selected repos):
	- `scripts/bootstrap_org_rules.sh`

## Delivery automation (no repetitive manual chain)
To avoid repeating the full release and promotion sequence manually on every cycle,
use the one-command automation script:

```bash
bash scripts/devsecops_release_and_promote.sh basic-blockchain blockchain-data-model develop
```

What this command does:
- creates `release/*` from `develop`
- opens and merges `release/* -> production`
- creates and merges promotion PRs for:
	- `production -> main`
	- `production -> staging`
	- `staging -> qa`
	- `qa -> develop`
- retries merges while required checks are still running

Optional env vars:
- `RELEASE_PREFIX` (default: `release/auto`)
- `MAX_WAIT_SECONDS` (default: `1800`)
- `POLL_SECONDS` (default: `15`)
- `GH_BIN` (explicit path for GitHub CLI)

## Tags and releases standard

Tag policy:
- all production releases must use annotated tags.
- use semantic versioning: `vMAJOR.MINOR.PATCH`.
- patch tags are for fixes, docs hardening, and CI/CD automation reliability.

Release notes policy:
- always write notes in a markdown file and publish with `--notes-file`.
- do not pass multi-line notes inline with escaped newlines.
- required sections:
	- `Summary`
	- `Included`
	- `Validation`
	- `Next`

Patch release command set:

```bash
git checkout main
git pull --ff-only origin main
git tag -a v1.0.1 -m "Patch release v1.0.1"
git push origin v1.0.1
gh release create v1.0.1 --repo basic-blockchain/blockchain-data-model --title "v1.0.1" --notes-file docs/releases/v1.0.1.md
```

Release note template:

```markdown
## Summary
Short statement of the release objective.

## Included
- item 1
- item 2
- item 3

## Validation
- CI Pull Request: pass
- branch promotion chain: pass

## Next
- next planned phase
```

Examples:

```bash
bash scripts/bootstrap_github_rules.sh basic-blockchain blockchain-data-model
bash scripts/bootstrap_org_rules.sh basic-blockchain
bash scripts/bootstrap_org_rules.sh basic-blockchain "repo-a,repo-b" "CI Pull Request / ci"
```

## Commit message standard
First line: professional title with 20+ characters.

Body must include:
- `What:`
- `Why:`

Example:

```
Introduce reusable wallet management module

What:
Extracted wallet key generation and signature verification into shared infrastructure components.

Why:
This reduces duplication and enables a safer path for future cryptography upgrades.
```
