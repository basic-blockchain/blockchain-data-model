# Blockchain Data Model MVP

MVP for comparing two blockchain data models in Python:
- UTXO model
- Account-based model

The project includes realistic simulation scenarios, JSON persistence per model, compliance/traceability events, and basic observability metrics.

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
