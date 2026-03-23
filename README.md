# Blockchain Data Model

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SemVer](https://img.shields.io/badge/semver-2.8.0-3D7EA6)](https://semver.org/)
[![Docs](https://img.shields.io/badge/docs-available-1F6FEB)](docs/MODEL_SIMULATION_GUIDE.md)

Simulacion realista de dos modelos blockchain (UTXO y Account-based) con gestion multiusuario de wallets, trazabilidad de cadena de suministro, compliance, autenticacion (bcrypt + JWT), control de acceso basado en roles (RBAC), intercambio de divisas, tesoreria corporativa, auditoria completa y gestion avanzada de usuarios.

Current release line:
- Latest stable release: `v2.8.0`
- Next target: `v2.9.0`

---

## Quick Start

### Requisitos

- Python 3.11+
- PostgreSQL 16 (opcional, JSON es el backend por defecto)

### 1. Clonar e instalar dependencias

```bash
cd ruta_del_proyecto/blockchain-data-model
py -m pip install -r requirements.txt
```

### 2. Configurar entorno

```bash
cp .env.example .env
# Editar .env con credenciales reales
source scripts/env_setup.sh
```

Variables en `.env`:

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `PERSISTENCE_BACKEND` | `json` | Backend: `json` o `postgres` |
| `DATABASE_URL` | (vacio) | DSN de PostgreSQL |
| `JWT_SECRET` | (placeholder) | Clave para firmar JWT (min 32 chars) |
| `JWT_TTL_SECONDS` | `3600` | Duracion del token JWT |
| `BCRYPT_ROUNDS` | `12` | Rondas de hashing bcrypt |

### 3. Preparar base de datos (PostgreSQL)

```bash
PYTHONPATH=. py migrations/migrate.py
```

El migrador crea la base de datos automaticamente si no existe y aplica las 9 migraciones disponibles (V001-V009).

### 4. Verificar instalacion

```bash
# Ejecutar tests unitarios (213 tests)
PYTHONPATH=. py -m pytest -q -m "not integration"

# Verificar CLI
py scripts/multiuser_wallet_cli.py --help
```

---

## Modos de operacion

### Modo CLI (comandos manuales)

```bash
# --- Usuarios ---
py scripts/multiuser_wallet_cli.py create-user --display-name "Alice" --email alice@example.com --username alicesmith --role ADMIN --password pass1234 --json
py scripts/multiuser_wallet_cli.py list-users --json
py scripts/multiuser_wallet_cli.py update-user --user-id USR-00001 --new-display-name "Alicia" --token JWT
py scripts/multiuser_wallet_cli.py delete-user --user-id USR-00002 --token JWT
py scripts/multiuser_wallet_cli.py restore-user --user-id USR-00002 --token JWT
py scripts/multiuser_wallet_cli.py update-profile --first-name "Alice" --last-name "Smith" --email alice@example.com --token JWT

# --- Autenticacion ---
py scripts/multiuser_wallet_cli.py login --identifier alicesmith --password pass1234 --json
py scripts/multiuser_wallet_cli.py change-password --current-password pass1234 --new-password newpass --token JWT
py scripts/multiuser_wallet_cli.py generate-temp-password --user-id USR-00002 --token JWT

# --- Wallets ---
py scripts/multiuser_wallet_cli.py create-wallet --wallet-id wallet_alice_01 --model UTXO --token JWT --json
py scripts/multiuser_wallet_cli.py balance --wallet-id wallet_alice_01 --json
py scripts/multiuser_wallet_cli.py list-wallets --json
py scripts/multiuser_wallet_cli.py freeze-wallet --user-id USR-00002 --token JWT
py scripts/multiuser_wallet_cli.py unfreeze-wallet --user-id USR-00002 --token JWT

# --- Transacciones ---
py scripts/multiuser_wallet_cli.py mint --wallet-id wallet_alice_01 --amount 100 --token JWT --json
py scripts/multiuser_wallet_cli.py transfer --from-wallet wallet_alice_01 --to-wallet wallet_bob_02 --amount 15 --fee 0.5 --sender-token WALLET_TOKEN --expected-nonce 1 --json
py scripts/multiuser_wallet_cli.py top-up --wallet-id wallet_bob_02 --amount 50 --currency USD --token JWT --json

# --- Exchange ---
py scripts/multiuser_wallet_cli.py set-exchange-rate --from-currency USD --to-currency EUR --rate 0.92 --commission 0.01 --token JWT
py scripts/multiuser_wallet_cli.py list-exchange-rates --json

# --- Tesoreria ---
py scripts/multiuser_wallet_cli.py create-treasury-wallet --currency USD --token JWT --json
py scripts/multiuser_wallet_cli.py list-treasury-wallets --json

# --- Permisos ---
py scripts/multiuser_wallet_cli.py grant-permission --role OPERATOR --permission MINT --token JWT
py scripts/multiuser_wallet_cli.py revoke-permission --role OPERATOR --permission MINT --token JWT
py scripts/multiuser_wallet_cli.py grant-user-permission --user-id USR-00003 --permission EXCHANGE --token JWT
py scripts/multiuser_wallet_cli.py list-role-permissions --role OPERATOR --token JWT
py scripts/multiuser_wallet_cli.py reset-role-permissions --role OPERATOR --token JWT

# --- Moderacion ---
py scripts/multiuser_wallet_cli.py ban-user --user-id USR-00003 --token JWT
py scripts/multiuser_wallet_cli.py unban-user --user-id USR-00003 --token JWT

# --- Auditoria ---
py scripts/multiuser_wallet_cli.py list-audit-log --limit 50 --token JWT
py scripts/multiuser_wallet_cli.py list-audit-log --action LOGIN_FAILED --token JWT
py scripts/multiuser_wallet_cli.py list-audit-log --user-id USR-00001 --token JWT

# --- Consultas ---
py scripts/multiuser_wallet_cli.py list-utxos --wallet-id wallet_alice_01 --json
py scripts/multiuser_wallet_cli.py verify-integrity --json
py scripts/multiuser_wallet_cli.py snapshot --json
py scripts/multiuser_wallet_cli.py list-revisions --limit 10 --json
```

Notas:
- `--json` habilita salida JSON para integracion programatica.
- `user_id` se auto-genera en formato `USR-XXXXX` si no se especifica.
- Los tokens de wallet expiran segun `JWT_TTL_SECONDS`. Usa `refresh-token` para renovar.
- `--expected-nonce` previene replay attacks y garantiza orden de transferencias.

### Modo Terminal Interactivo

```bash
py scripts/multiuser_terminal.py
```

Menu con 45 opciones en 10 secciones:

| Seccion | Opciones | Descripcion |
|---------|----------|-------------|
| **Usuarios & Wallets** | 1-2, 9, 12-13 | Crear usuarios/wallets, balance, list-users, refresh-token |
| **Transacciones** | 3-4, 10 | Mint, transfer, transfer-wizard con preview cross-currency |
| **Politicas & Riesgo** | 14-20 | Set/get/list politicas y perfiles de riesgo, alertas |
| **Consultas** | 5-8, 21 | List-wallets, list-utxos, verify-integrity, snapshot, list-revisions |
| **Exchange** | 22-24 | Gestionar tasas de cambio y conversion entre divisas |
| **Tesoreria** | 25-27 | Treasury wallets y top-up |
| **Permisos** | 28-34 | Grant/revoke por rol y por usuario, reset, listar |
| **Moderacion** | 35-38 | Freeze/unfreeze wallet, ban/unban usuario (requiere sudo) |
| **Gestion de usuarios** | 39-43 | Update/delete/restore usuario, temp password, audit log |
| **Sistema** | 44-45, 11, 0 | Change-password, update-profile, dashboard, exit |

Comportamientos especiales:
- Login detecta cuenta suspendida: muestra banner `CUENTA SUSPENDIDA`.
- Password temporal: fuerza cambio inmediato antes de mostrar menu.
- Operaciones de moderacion y gestion: requieren re-validacion JWT (sudo, 3 intentos).
- Transfer-wizard: preview de conversion para pares cross-currency.

### Modo Simulador

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo --persist
py scripts/blockchain_models_simulator.py --list-runs --run-model both
```

---

## Autenticacion y RBAC

| Rol | Permisos principales |
|-----|---------------------|
| **ADMIN** | Todo: gestionar usuarios, wallets, permisos, moderacion, auditoria, tesoreria, exchange |
| **OPERATOR** | Transferencias, mint, top-up, exchange, politicas, riesgo, update-profile |
| **VIEWER** | Consultas de lectura, create-wallet, transfer, update-profile |

Caracteristicas:
- Password hashing con **bcrypt** (configurable via `BCRYPT_ROUNDS`).
- **JWT** por usuario y por wallet con TTL configurable.
- Permisos **dinamicos** por rol y por usuario con override en DB y JSON snapshot.
- Sudo re-validacion JWT para operaciones sensibles (3 intentos, keyword `refresh`).
- **Password temporal**: ADMIN genera password de un uso; usuario debe cambiar en primer login.
- Login acepta `user_id` o `username` como identificador.
- **Soft delete**: usuarios eliminados conservan datos, wallets congeladas, login bloqueado.
- **Audit log** append-only con ~20 tipos de accion (USER_CREATED, LOGIN_FAILED, TRANSFER, etc.).

---

## Persistencia

| Backend | Cuando usarlo | Configuracion |
|---------|---------------|---------------|
| **JSON** | Desarrollo rapido, demos, sin dependencias | `PERSISTENCE_BACKEND=json` |
| **PostgreSQL** | Produccion, multi-sesion, integridad referencial | `PERSISTENCE_BACKEND=postgres` + `DATABASE_URL` |

### Migraciones PostgreSQL

```bash
PYTHONPATH=. py migrations/migrate.py
```

| Migracion | Contenido |
|-----------|-----------|
| `V001` | Tablas core: users, wallets, transfers, policies, risk_profiles, alerts, simulation_runs, traceability |
| `V002` | Autenticacion: user_credentials, user_roles |
| `V003` | Revision history |
| `V004` | exchange_rates, tipo EXCHANGE en transfers, metadatos de conversion |
| `V005` | Tipo TOP_UP en transfers |
| `V006` | permissions, role_permissions, user_permissions |
| `V007` | Campo banned en users, campo frozen en wallets, indices parciales |
| `V008` | updated_at/deleted_at en users, password_temp/token_temp en credentials, tabla audit_log |
| `V009` | first_name, last_name, email, username en users, indice unico en username |

---

## Estructura del proyecto

```
blockchain-data-model/
├── domain/
│   ├── auth.py                      # Auth, JWT, RBAC, permisos dinamicos, temp password
│   ├── exchange.py                  # ExchangeRate, convert_amount()
│   ├── multiuser_wallet_ledger.py   # Core: usuarios, wallets, transferencias, auditoria
│   ├── compliance.py                # Evaluacion de compliance
│   └── traceability_models.py       # Lotes, certificados, eventos
├── persistence/
│   ├── interfaces.py                # ABCs: WalletLedgerRepository, SimulationRunRepository
│   ├── factory.py                   # Strategy Pattern: seleccion de backend
│   ├── multiuser_wallet_store.py    # Backend JSON
│   ├── pg_multiuser_wallet_store.py # Backend PostgreSQL (con _column_exists guard)
│   └── pg_connection.py             # Pool de conexiones
├── config/
│   └── settings.py                  # Settings desde .env y env vars
├── migrations/
│   ├── migrate.py                   # Runner de migraciones SQL (autocommit para ALTER TYPE)
│   └── versions/                    # V001–V009 SQL files
├── scripts/
│   ├── multiuser_wallet_cli.py      # CLI por comandos (45+ subcommands)
│   ├── multiuser_terminal.py        # Terminal interactivo (45 opciones, 10 secciones)
│   ├── blockchain_models_simulator.py
│   └── *.sh                         # DevSecOps automation
├── tests/                           # 213 tests
│   ├── test_domain_auth.py
│   ├── test_exchange.py
│   ├── test_corporate_wallet.py
│   ├── test_dynamic_permissions.py
│   ├── test_freeze_ban.py
│   ├── test_user_management.py
│   ├── test_audit_log.py
│   ├── test_user_profile.py
│   └── integration/
├── docs/
│   ├── releases/                    # Release notes v1.0.0–v2.8.0
│   ├── en/SYSTEM_DOCUMENTATION.md
│   ├── es/SYSTEM_DOCUMENTATION.md
│   ├── MODEL_SIMULATION_GUIDE.md
│   └── GITFLOW.md
├── account-model.py
├── utxo-model.py
├── .env.example
└── requirements.txt
```

---

## Tests

```bash
# Unit tests (sin PostgreSQL)
PYTHONPATH=. py -m pytest -q -m "not integration"

# Incluir integracion (requiere DATABASE_URL)
PYTHONPATH=. py -m pytest -q

# Test especifico
PYTHONPATH=. py -m pytest tests/test_audit_log.py -v
```

---

## DevSecOps y GitFlow

Ramas: `main` <- `production` <- `staging` <- `qa` <- `develop` <- `feature/*`

```bash
# Release completo automatizado
GH_BIN="/c/Program Files/GitHub CLI/gh.exe" bash scripts/devsecops_release_and_promote.sh basic-blockchain blockchain-data-model develop

# Solo promotion chain
GH_BIN="/c/Program Files/GitHub CLI/gh.exe" bash scripts/devsecops_promotion_chain.sh basic-blockchain blockchain-data-model

# Reset datos JSON
bash scripts/reset_persistence_json.sh
```

---

## Documentacion

- [Guia de simulacion y operacion](docs/MODEL_SIMULATION_GUIDE.md)
- [GitFlow y branching](docs/GITFLOW.md)
- [Consola de agentes](docs/AGENT_CONSOLE.md)
- [Release notes](docs/releases/)
- [Documentacion en espanol](docs/es/)
- [English documentation](docs/en/)

---

## Versionamiento

SemVer estricto con tags anotados. Release notes en `docs/releases/vX.Y.Z.md`.

| Version | Highlight |
|---------|-----------|
| v2.8.0 | User management, audit log, profile fields, auto-generated user IDs (USR-XXXXX) |
| v2.7.0 | Wallet freeze/unfreeze, user ban, admin sudo re-validation |
| v2.6.0 | Cross-currency exchange, corporate treasury, dynamic RBAC permissions |
| v2.5.0 | Self-registration, wallet ownership enforcement, Command Registry refactor |
| v2.4.0 | Auth (bcrypt + JWT) + RBAC (ADMIN/OPERATOR/VIEWER) |
| v2.3.0 | Terminal UX profesional + opciones interactivas |
| v2.2.0 | Persistencia PostgreSQL + Repository Pattern |
| v2.1.0 | UX hardening + alertas visuales |
| v2.0.0 | Multi-user wallet system |
