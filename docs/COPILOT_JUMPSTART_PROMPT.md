# Copilot Jumpstart Prompt (Organization Optimized)

Use this prompt in the "Jumpstart your project with Copilot" box when creating new repositories in `basic-blockchain`.

## Suggested prompt

Build a production-oriented Python blockchain data-model repository for enterprise traceability with two ledger simulations (UTXO and account-based), shared domain modules, pytest test suite, and GitHub Actions CI.

Requirements:
1. Create branch structure and documentation for Gitflow (`main`, `develop`, `feature/*`, `release/*`, `hotfix/*`, `refactor/*`).
2. Add CI workflows for pull requests and main merges.
3. Add PR template, CODEOWNERS, and labeler automation.
4. Keep commit message policy with title + What + Why.
5. Include scripts to bootstrap GitHub branch protection via `gh` CLI.
6. Include docs for architecture, governance, and contribution.

Output expected:
- Working repository structure.
- Passing test pipeline on PR.
- Governance files under `.github/`.
- Practical docs for onboarding.

## Why this helps
- Accelerates standardization across the organization.
- Ensures every repo starts with CI/CD and governance defaults.
- Reduces setup friction for new contributors and teams.
