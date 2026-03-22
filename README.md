# Blockchain Data Model MVP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SemVer](https://img.shields.io/badge/semver-2.4.0-3D7EA6)](https://semver.org/)
[![Docs](https://img.shields.io/badge/docs-available-1F6FEB)](docs/MODEL_SIMULATION_GUIDE.md)

MVP for comparing two blockchain data models in Python:
- UTXO model
- Account-based model

The project includes realistic simulation scenarios, JSON persistence per model, compliance/traceability events, and basic observability metrics.

Current release line:
- Latest stable release: `v2.4.0`
- Next target: `v2.5.0`

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
py scripts/multiuser_wallet_cli.py create-wallet --user-id u-alice --wallet-id wallet_user_alpha_01 --model UTXO
py scripts/multiuser_wallet_cli.py mint --wallet-id wallet_user_alpha_01 --amount 100
py scripts/multiuser_wallet_cli.py set-risk-profile --user-id u-alice --profile-name HIGH --transfer-alert-threshold 5 --daily-alert-threshold 20
py scripts/multiuser_wallet_cli.py snapshot --json
py scripts/multiuser_wallet_cli.py list-alerts --user-id u-alice --json
```

## Estado actual de autenticacion y roles (v2.4.0)

La version actual incluye autenticacion y RBAC en la capa de dominio y persistencia:
- Password hashing con bcrypt.
- JWT con claims de usuario y roles.
- Roles: ADMIN, OPERATOR, VIEWER.

Importante para operacion diaria:
- El CLI y el terminal interactivo exponen hoy el flujo operativo de wallets/tokens de wallet (sender-token + nonce).
- Los metodos de login y asignacion de roles ya existen en dominio, pero no estan expuestos aun como comandos dedicados en `multiuser_wallet_cli.py` ni como opciones del menu interactivo.

Run tests:

```bash
py -m pytest -q
```

## Operational Runbook (v2)

Run from repository root.

### Terminal startup (Windows)

Use either Git Bash or PowerShell, but always run commands from repository root.

```bash
# 1) Move to repository root
cd /c/Users/User/Documents/sapir/blockchain_usb/scripts/python/blockchain-data-model

# 2) Sync local develop with origin/develop
git checkout develop
git pull --ff-only origin develop

# 3) Verify Python launcher is available
py --version

# 4) (Optional) reset persisted data before a fresh run
bash scripts/reset_persistence_json.sh

# 5) Quick health check for CLI availability
py scripts/multiuser_wallet_cli.py --help
```

If `py` is not available in your shell, open a terminal profile where Python Launcher is configured.

### Normal mode (CLI)

Paso a paso operativo (flujo recomendado):

```bash
# 0) Optional: validate key multiuser tests
py -m pytest -q tests/test_multiuser_wallet_ledger.py tests/test_multiuser_wallet_cli.py tests/test_multiuser_wallet_store.py

# 1) Comparative simulation (JSON)
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json

# 2) Create users
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-alice --display-name Alice --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-bob --display-name Bob --json

# 3) Create UTXO wallets
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-alice --wallet-id wallet_user_alpha_01 --model UTXO --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-bob --wallet-id wallet_user_bravo_02 --model UTXO --json

# 4) Mint funds
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json mint --wallet-id wallet_user_alpha_01 --amount 10 --json

# 5) Transfer with sender token + expected nonce
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json transfer --from-wallet wallet_user_alpha_01 --to-wallet wallet_user_bravo_02 --amount 3 --fee 1 --sender-token TOKEN_DE_ALICE --expected-nonce 1 --json

# 6) If token mismatch/expiration happens, renew token as owner
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json refresh-token --user-id u-alice --wallet-id wallet_user_alpha_01 --current-token TOKEN_ANTERIOR --json

# 7) Inspect resulting UTXOs/snapshot
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-utxos --wallet-id wallet_user_bravo_02 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json snapshot --json

# 8) Verify nonce + hash-chain integrity
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json verify-integrity --json

# 9) Verify branch content alignment (DevSecOps guard)
bash scripts/devsecops_check_content_sync.sh
```

Notes:
- Wallet IDs manuales deben tener 20-30 caracteres (`[A-Za-z0-9_-]`). Si no se envia `--wallet-id`, se genera automaticamente uno valido.
- Copy `auth_token` from wallet creation output and use it as `--sender-token`.
- Use `--expected-nonce` para evitar replay/orden incorrecto de transferencias.
- If transfer returns token expiration/mismatch, call `refresh-token` and retry with the new token.

### Interactive terminal mode

```bash
py scripts/multiuser_terminal.py
```

Recommended menu sequence (v2.4.0):
- `1) create-user` (Alice)
- `1) create-user` (Bob)
- `2) create-wallet` (Alice, model `UTXO`)
- `2) create-wallet` (Bob, model `UTXO`)
- `3) mint` (Alice)
- `4) transfer` (use Alice token + expected nonce)
- `10) transfer-wizard` (guided transfer with confirm step)
- `6) list-utxos` (Bob)
- `7) verify-integrity`
- `8) snapshot`
- `9) refresh-token` (owner recovery flow when token expired/mismatch)
- `11) dashboard` (session telemetry on demand)

Interactive UX behavior:
- Inputs numericos invalidos en `amount`/`fee` se bloquean con mensaje controlado (sin traceback Python).
- Transferencia requiere `sender_token` explicito; no hay fallback implicito de token de sesion.
- El dashboard ya no se imprime en cada accion; se consulta bajo demanda.

### Reset persistence data

Use the repository script to reset JSON stores to minimal valid state:

```bash
bash scripts/reset_persistence_json.sh
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
- frontend application.
