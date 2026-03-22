# Simulacion Realista de Modelos Blockchain

## Objetivo principal
Replicar con ejemplos reales el comportamiento de los dos modelos iniciales del repositorio:
- UTXO
- Account-based

Esta guia tambien cubre el flujo operativo multiusuario vigente en v2.4.0.

## Script principal

```bash
py scripts/blockchain_models_simulator.py
```

## Estado verificado en develop

Antes de ejecutar, sincroniza la rama de trabajo:

```bash
cd /c/Users/User/Documents/sapir/blockchain_usb/scripts/python/blockchain-data-model
git checkout develop
git pull --ff-only origin develop
```

Estado funcional actual (v2.4.0):
- Auth y RBAC existen en dominio/persistencia (bcrypt + JWT + roles).
- CLI y terminal interactivo exponen el flujo operativo de wallets, transferencias, politicas y riesgo.
- La seguridad operativa activa en CLI/terminal usa sender-token de wallet + expected-nonce.

## Escenarios incluidos
1. coffee-export
- Trazabilidad de lote de cafe
- Certificados
- Eventos logisticos
- Transferencias y fees
- Auditoria de compliance

2. retail-payments
- Pagos de comercio minorista
- Multiples transferencias
- Confirmaciones por bloques
- Costos de red (validator pool)

## Ejemplos de ejecucion del simulador

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo
py scripts/blockchain_models_simulator.py --scenario retail-payments --model account
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json
```

## Persistencia JSON del simulador
Archivos:
- data/simulation-runs/utxo-runs.json
- data/simulation-runs/account-runs.json

Guardar corridas:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --persist
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo --persist
```

Consultar corridas:

```bash
py scripts/blockchain_models_simulator.py --list-runs --run-model both
py scripts/blockchain_models_simulator.py --list-runs --run-model utxo --limit 10
py scripts/blockchain_models_simulator.py --show-run-id <RUN_ID> --run-model account
```

Directorio personalizado:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model account --persist --store-dir data/my-runs
```

## Metricas por corrida
Cada resultado incorpora metricas para observabilidad:
- execution_ms
- total_events
- total_transactions
- pending_transactions
- confirmed_transactions
- finalized_transactions
- chain_height
- state_items

En modo --json, estas metricas viajan dentro de cada elemento de results.

## Flujo CLI paso a paso (multiusuario, v2.4.0)

```bash
# 0) Opcional: reset para corrida limpia
bash scripts/reset_persistence_json.sh

# 1) Ver comandos disponibles
py scripts/multiuser_wallet_cli.py --help

# 2) Crear usuarios
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-alice --display-name "Alice" --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-bob --display-name "Bob" --json

# 3) Crear wallets (wallet_id manual: 20-30 chars [A-Za-z0-9_-])
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-alice --wallet-id wallet_user_alpha_01 --model UTXO --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-bob --wallet-id wallet_user_bravo_02 --model UTXO --json

# 4) Fondear wallet
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json mint --wallet-id wallet_user_alpha_01 --amount 100 --json

# 5) Transferencia con sender-token + expected-nonce
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json transfer --from-wallet wallet_user_alpha_01 --to-wallet wallet_user_bravo_02 --amount 15 --fee 0.5 --sender-token TOKEN_DE_ALICE --expected-nonce 1 --json

# 6) Consultas
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json balance --wallet-id wallet_user_bravo_02 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-utxos --wallet-id wallet_user_bravo_02 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json verify-integrity --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json snapshot --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-revisions --limit 10 --json

# 7) Politicas y riesgo
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json set-policy --user-id u-alice --can-transfer true --daily-limit 25 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json set-risk-profile --user-id u-alice --profile-name HIGH --transfer-alert-threshold 5 --daily-alert-threshold 12 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-alerts --user-id u-alice --limit 20 --json

# 8) Renovar token cuando venza o no coincida
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json refresh-token --user-id u-alice --wallet-id wallet_user_alpha_01 --current-token TOKEN_ANTERIOR --json
```

## Flujo de terminal interactiva (menu)

Ejecucion:

```bash
py scripts/multiuser_terminal.py
```

Secuencia recomendada:
1. 1) create-user para Alice y Bob.
2. 2) create-wallet para cada usuario.
3. Guardar auth_token mostrado al crear wallet.
4. 3) mint sobre wallet emisora.
5. 4) transfer o 10) transfer-wizard con sender_token y nonce.
6. 6) list-utxos + 7) verify-integrity.
7. 8) snapshot para revisar estado global.
8. 11) dashboard para metricas de sesion.
9. 9) refresh-token cuando el token vence o no coincide.

Comportamiento UX actual:
- Alertas visuales [SUCCESS] / [ERROR].
- Validacion preventiva de numericos (amount, fee) para evitar traceback.
- Token de sender requerido explicitamente en transferencia interactiva.

## Cuadro de actualizacion JSON

| Componente | Comando / Accion | Actualiza JSON | Archivo |
|---|---|---|---|
| Simulador UTXO/Account | run con --persist | Si | data/simulation-runs/utxo-runs.json, data/simulation-runs/account-runs.json |
| Simulador UTXO/Account | run sin --persist | No | No aplica |
| Simulador UTXO/Account | --list-runs / --show-run-id | No | Solo lectura |
| Multiusuario CLI | create-user | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | create-wallet | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | mint | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | transfer | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | refresh-token | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | set-policy | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | set-risk-profile | Si | data/multiuser/wallet-ledger.json |
| Multiusuario CLI | balance/list-users/list-wallets/list-utxos/snapshot/list-revisions/get-policy/list-policies/get-risk-profile/list-risk-profiles/list-alerts/verify-integrity | No | Solo lectura |

## Setup con PostgreSQL

### 1. Configurar .env

```bash
cp .env.example .env
# Editar .env con credenciales reales de PostgreSQL
```

El archivo `.env` se carga automaticamente por `config/settings.py`. Las variables de entorno del sistema toman precedencia sobre `.env`.

### 2. Ejecutar migraciones

```bash
PYTHONPATH=. py migrations/migrate.py
```

Esto crea la base de datos si no existe y aplica:
- V001: Tablas core (users, wallets, transfers, policies, risk_profiles, alerts, simulation_runs, traceability)
- V002: Tablas de autenticacion (user_credentials, user_roles)

### 3. Verificar backend activo

Al iniciar `py scripts/multiuser_terminal.py`, el banner muestra:
- **Verde**: `PostgreSQL (blockchain_data_model)` — leyendo/escribiendo en PG
- **Amarillo**: `JSON (local files)` — leyendo/escribiendo en archivos JSON locales

Si ves JSON pero esperabas PostgreSQL, verifica que `.env` tenga `PERSISTENCE_BACKEND=postgres` y `DATABASE_URL` correcto.

### 4. Cambiar entre backends

```bash
# Modo PostgreSQL
PERSISTENCE_BACKEND=postgres py scripts/multiuser_terminal.py

# Modo JSON (default si no hay .env)
PERSISTENCE_BACKEND=json py scripts/multiuser_terminal.py
```

Los datos de cada backend son independientes. Crear datos en JSON no los replica en PostgreSQL y viceversa.

## Menu completo del terminal interactivo (v2.4.0)

| # | Comando | Seccion | Descripcion |
|---|---------|---------|-------------|
| 1 | create-user | Usuarios & Wallets | Registrar nuevo usuario |
| 2 | create-wallet | Usuarios & Wallets | Crear wallet UTXO o ACCOUNT |
| 9 | refresh-token | Usuarios & Wallets | Renovar token de autenticacion |
| 12 | list-users | Usuarios & Wallets | Listar usuarios registrados |
| 13 | balance | Usuarios & Wallets | Consultar balance de wallet |
| 3 | mint | Transacciones | Emitir tokens a wallet |
| 4 | transfer | Transacciones | Transferir fondos |
| 10 | transfer-wizard | Transacciones | Asistente guiado con confirmacion |
| 14 | set-policy | Politicas & Riesgo | Configurar politica de transferencia |
| 15 | get-policy | Politicas & Riesgo | Ver politica de un usuario |
| 16 | list-policies | Politicas & Riesgo | Listar todas las politicas |
| 17 | set-risk-profile | Politicas & Riesgo | Asignar perfil de riesgo |
| 18 | get-risk-profile | Politicas & Riesgo | Ver perfil de riesgo |
| 19 | list-risk-profiles | Politicas & Riesgo | Listar perfiles de riesgo |
| 20 | list-alerts | Politicas & Riesgo | Ver alertas generadas |
| 5 | list-wallets | Consultas | Listar wallets |
| 6 | list-utxos | Consultas | Listar UTXOs |
| 7 | verify-integrity | Consultas | Verificar nonce + hash-chain |
| 8 | snapshot | Consultas | Estado completo del ledger |
| 21 | list-revisions | Consultas | Historial de revisiones |
| 11 | dashboard | Sistema | Metricas de sesion |
| 0 | exit | Sistema | Salir del terminal |
