# Gitflow and Delivery Policy

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
