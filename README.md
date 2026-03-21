# Blockchain Data Model MVP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SemVer](https://img.shields.io/badge/semver-2.0.0-3D7EA6)](https://semver.org/)
[![Docs](https://img.shields.io/badge/docs-available-1F6FEB)](docs/MODEL_SIMULATION_GUIDE.md)

MVP for comparing two blockchain data models in Python:
- UTXO model
- Account-based model

The project includes realistic simulation scenarios, JSON persistence per model, compliance/traceability events, and basic observability metrics.

Current release line:
- Latest stable release: `v2.0.0`
- Next target: `v2.1.0`

## Quick Start

Requirements:
- Python 3.11+

Run simulations:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo
py scripts/blockchain_models_simulator.py --scenario retail-payments --model account
```

JSON output:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json
```

Persist simulation runs by model:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --persist
py scripts/blockchain_models_simulator.py --list-runs --run-model both
py scripts/blockchain_models_simulator.py --show-run-id <RUN_ID> --run-model account
```

Multi-user wallet flow (new iteration):

```bash
py scripts/multiuser_wallet_cli.py create-user --user-id u-alice --display-name "Alice"
py scripts/multiuser_wallet_cli.py create-wallet --user-id u-alice --wallet-id w-alice
py scripts/multiuser_wallet_cli.py mint --wallet-id w-alice --amount 100
py scripts/multiuser_wallet_cli.py set-risk-profile --user-id u-alice --profile-name HIGH --transfer-alert-threshold 5 --daily-alert-threshold 20
py scripts/multiuser_wallet_cli.py snapshot --json
py scripts/multiuser_wallet_cli.py list-alerts --user-id u-alice --json
```

Run tests:

```bash
py -m pytest -q
```

## Core Structure

- account-model.py: account-based blockchain model.
- utxo-model.py: UTXO blockchain model.
- scripts/blockchain_models_simulator.py: comparative simulator CLI.
- persistence/simulation_store.py: JSON run persistence store.
- data/simulation-runs/: persisted outputs (`utxo-runs.json`, `account-runs.json`).

## Documentation

Spanish docs:
- docs/es/README.md
- docs/es/SYSTEM_DOCUMENTATION.md

English docs:
- docs/en/README.md
- docs/en/SYSTEM_DOCUMENTATION.md

Operational guide with JSON update matrix and multiuser CLI examples:
- docs/MODEL_SIMULATION_GUIDE.md

## Versioning, Tags, and Releases

This repository uses semantic versioning for public delivery tags:
- `MAJOR`: incompatible architecture or API-level shifts.
- `MINOR`: backward-compatible feature increments.
- `PATCH`: backward-compatible fixes, documentation hardening, and delivery automation fixes.

Release hygiene:
- create annotated tags (never lightweight tags for official releases).
- publish release notes in markdown from a file to avoid escaped `\\n` artifacts.
- include: summary, included changes, validation status, and next-step roadmap.

Release command example:

```bash
git checkout main
git pull --ff-only origin main
RELEASE_TAG=v2.0.0
git tag -a "$RELEASE_TAG" -m "Release $RELEASE_TAG"
git push origin "$RELEASE_TAG"
gh release create "$RELEASE_TAG" --repo basic-blockchain/blockchain-data-model --title "$RELEASE_TAG" --notes-file "docs/releases/$RELEASE_TAG.md"
```

## MVP Scope

Included:
- two working blockchain state models.
- realistic scenarios (coffee export, retail payments).
- per-model persistence with run history.
- compliance and traceability events.
- run metrics for observability.

Not included yet:
- HTTP API layer.
- database backend (JSON is currently the persistence layer).
- frontend application.
