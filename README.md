# Blockchain Data Model

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SemVer](https://img.shields.io/badge/semver-2.5.0-3D7EA6)](https://semver.org/)
[![Docs](https://img.shields.io/badge/docs-available-1F6FEB)](docs/MODEL_SIMULATION_GUIDE.md)

Simulacion realista de dos modelos blockchain (UTXO y Account-based) con gestion multiusuario de wallets, trazabilidad de cadena de suministro, compliance, autenticacion (bcrypt + JWT) y control de acceso basado en roles (RBAC).

Current release line:
- Latest stable release: `v2.5.0`
- Next target: `v2.6.0`

---

## Quick Start

### Requisitos

- Python 3.11+
- PostgreSQL 16 (opcional, JSON es el backend por defecto)

### 1. Clonar e instalar dependencias

```bash
cd /c/Users/User/Documents/sapir/blockchain_usb/scripts/python/blockchain-data-model
py -m pip install -r requirements.txt
```

### 2. Configurar entorno

```bash
# Copia el archivo de ejemplo y edita con tus credenciales
cp .env.example .env

# O usa el script asistido (crea .env si no existe)
source scripts/env_setup.sh
```

Variables en `.env`:

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `PERSISTENCE_BACKEND` | `postgres` | Backend: `json` o `postgres` |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/blockchain_data_model` | Conexion PostgreSQL |
| `JWT_SECRET` | (placeholder) | Clave para firmar JWT (min 32 chars en produccion) |
| `JWT_TTL_SECONDS` | `3600` | Duracion del token JWT |
| `BCRYPT_ROUNDS` | `12` | Rondas de hashing bcrypt |

### 3. Preparar base de datos (si usas PostgreSQL)

```bash
# Crea la base de datos y aplica todas las migraciones
PYTHONPATH=. py migrations/migrate.py
```

El migrator crea la base de datos automaticamente si no existe.

### 4. Verificar instalacion

```bash
# Ejecutar tests (94 tests)
PYTHONPATH=. py -m pytest -q -m "not integration"

# Verificar CLI
py scripts/multiuser_wallet_cli.py --help
```

---

## Modos de operacion

### Modo CLI (comandos manuales)

Cada operacion es un comando independiente. Ideal para scripting y automatizacion.

```bash
# Crear usuarios
py scripts/multiuser_wallet_cli.py create-user --user-id u-alice --display-name Alice --json
py scripts/multiuser_wallet_cli.py create-user --user-id u-bob --display-name Bob --json

# Crear wallets UTXO
py scripts/multiuser_wallet_cli.py create-wallet --user-id u-alice --wallet-id wallet_user_alpha_01 --model UTXO --json
py scripts/multiuser_wallet_cli.py create-wallet --user-id u-bob --wallet-id wallet_user_bravo_02 --model UTXO --json

# Fondear wallet
py scripts/multiuser_wallet_cli.py mint --wallet-id wallet_user_alpha_01 --amount 100 --json

# Transferir (usar auth_token del create-wallet como sender-token)
py scripts/multiuser_wallet_cli.py transfer \
  --from-wallet wallet_user_alpha_01 \
  --to-wallet wallet_user_bravo_02 \
  --amount 15 --fee 0.5 \
  --sender-token TOKEN_DE_ALICE \
  --expected-nonce 1 --json

# Consultar
py scripts/multiuser_wallet_cli.py balance --wallet-id wallet_user_alpha_01 --json
py scripts/multiuser_wallet_cli.py list-wallets --json
py scripts/multiuser_wallet_cli.py list-utxos --wallet-id wallet_user_bravo_02 --json
py scripts/multiuser_wallet_cli.py verify-integrity --json
py scripts/multiuser_wallet_cli.py snapshot --json

# Politicas y riesgo
py scripts/multiuser_wallet_cli.py set-policy --user-id u-alice --can-transfer true --daily-limit 25 --json
py scripts/multiuser_wallet_cli.py set-risk-profile --user-id u-alice --profile-name HIGH --transfer-alert-threshold 5 --json
py scripts/multiuser_wallet_cli.py list-alerts --user-id u-alice --json

# Renovar token expirado
py scripts/multiuser_wallet_cli.py refresh-token --user-id u-alice --wallet-id wallet_user_alpha_01 --json
```

Notas:
- `--json` habilita salida JSON para integracion programatica.
- `auth_token` se muestra al crear una wallet. Guardalo para usarlo como `--sender-token`.
- Los tokens de wallet expiran en 120 segundos. Usa `refresh-token` para renovar.
- `--expected-nonce` previene replay attacks y garantiza orden de transferencias.

### Modo Terminal Interactivo

Interfaz visual con menu categorizado, prompts asistidos y respuestas en recuadros.

```bash
py scripts/multiuser_terminal.py
```

El terminal muestra un banner con el logo Bitcoin + CHAINS, el backend activo (JSON o PostgreSQL), y un menu con 21 opciones organizadas en 5 secciones:

| Seccion | Opciones |
|---------|----------|
| **Usuarios & Wallets** | create-user, create-wallet, refresh-token, list-users, balance |
| **Transacciones** | mint, transfer, transfer-wizard |
| **Politicas & Riesgo** | set/get/list-policy, set/get/list-risk-profile, list-alerts |
| **Consultas** | list-wallets, list-utxos, verify-integrity, snapshot, list-revisions |
| **Sistema** | dashboard, exit |

Secuencia recomendada:
1. Crear usuarios (opcion 1)
2. Crear wallets (opcion 2) — guardar el `auth_token` mostrado
3. Fondear con mint (opcion 3)
4. Transferir (opcion 4 o 10 para wizard guiado)
5. Verificar UTXOs y integridad (opciones 6, 7)
6. Consultar snapshot (opcion 8)
7. Dashboard de sesion (opcion 11)

### Modo Simulador

Compara los modelos UTXO y Account-based con escenarios realistas.

```bash
# Ejecutar simulacion comparativa
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json

# Persistir resultado
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --persist

# Consultar corridas guardadas
py scripts/blockchain_models_simulator.py --list-runs --run-model both
```

---

## Autenticacion y Roles (v2.4.0)

La capa de dominio incluye autenticacion y RBAC:

- **Password hashing** con bcrypt (configurable via BCRYPT_ROUNDS).
- **JWT** con claims de usuario y roles (configurable via JWT_SECRET y JWT_TTL_SECONDS).
- **Tres roles**: ADMIN (todo), OPERATOR (transferencias + lectura), VIEWER (solo lectura).

Estos metodos existen en el domain layer y se persisten en PostgreSQL (`user_credentials`, `user_roles`). Seran expuestos como endpoints en la API REST (v2.5.0).

---

## Persistencia

El sistema soporta dos backends seleccionables via `PERSISTENCE_BACKEND`:

| Backend | Cuando usarlo | Configuracion |
|---------|---------------|---------------|
| **JSON** | Desarrollo rapido, demos, sin dependencias | `PERSISTENCE_BACKEND=json` |
| **PostgreSQL** | Produccion, multi-sesion, integridad | `PERSISTENCE_BACKEND=postgres` + `DATABASE_URL` |

El terminal interactivo muestra el backend activo en el banner de inicio.

### Migraciones PostgreSQL

```bash
# Aplica todas las migraciones pendientes (crea DB si no existe)
PYTHONPATH=. py migrations/migrate.py
```

Migraciones disponibles:
- `V001__initial_schema.sql` — Tablas core: users, wallets, transfers, policies, risk_profiles, alerts, simulation_runs, traceability
- `V002__auth_roles.sql` — Tablas de autenticacion: user_credentials, user_roles

---

## Estructura del proyecto

```
blockchain-data-model/
├── domain/                    # Logica de negocio (sin dependencias externas)
│   ├── auth.py               # Autenticacion, JWT, RBAC
│   ├── multiuser_wallet_ledger.py  # Core: usuarios, wallets, transferencias
│   ├── compliance.py         # Evaluacion de compliance
│   └── traceability_models.py # Lotes, certificados, eventos
├── persistence/              # Capa de persistencia (Repository Pattern)
│   ├── interfaces.py         # ABCs: WalletLedgerRepository, SimulationRunRepository
│   ├── factory.py            # Strategy Pattern: seleccion de backend
│   ├── multiuser_wallet_store.py  # Backend JSON
│   ├── pg_multiuser_wallet_store.py  # Backend PostgreSQL
│   └── pg_connection.py      # Pool de conexiones
├── config/
│   └── settings.py           # Settings desde .env y env vars
├── migrations/
│   ├── migrate.py            # Runner de migraciones SQL
│   └── versions/             # Archivos SQL versionados
├── scripts/
│   ├── multiuser_wallet_cli.py     # CLI por comandos
│   ├── multiuser_terminal.py       # Terminal interactivo
│   ├── blockchain_models_simulator.py  # Simulador comparativo
│   └── *.sh                        # DevSecOps automation
├── tests/                    # 94 tests (unit + integration)
├── account-model.py          # Modelo Account-based
├── utxo-model.py             # Modelo UTXO
├── .env.example              # Template de configuracion
└── requirements.txt          # Dependencias: psycopg2, bcrypt, PyJWT
```

---

## Tests

```bash
# Unit tests (sin PostgreSQL, rapido)
PYTHONPATH=. py -m pytest -q -m "not integration"

# Incluir integracion (requiere DATABASE_URL)
PYTHONPATH=. py -m pytest -q

# Test especifico
PYTHONPATH=. py -m pytest tests/test_domain_auth.py -v
```

---

## DevSecOps y GitFlow

Ramas: `main` ← `production` ← `staging` ← `qa` ← `develop` ← `feature/*`

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
| v2.5.0 | Self-registration, wallet ownership, Command Registry refactor |
| v2.4.0 | Auth (bcrypt + JWT) + RBAC (ADMIN/OPERATOR/VIEWER) |
| v2.3.0 | Terminal UX profesional + 21 opciones interactivas |
| v2.2.0 | Persistencia PostgreSQL + Repository Pattern |
| v2.1.0 | UX hardening + alertas visuales |
| v2.0.0 | Multi-user wallet system |

## Roadmap

- `v2.6.0` — Cross-currency exchange con tasas de conversion
- `v2.7.0` — API REST (FastAPI + Pydantic)
- `v2.8.0` — GraphQL (Strawberry)
- `v2.9.0` — Docker + DockerHub
