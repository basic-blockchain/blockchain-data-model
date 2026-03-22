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

## Nota de compatibilidad PostgreSQL

Si trabajas con backend PostgreSQL y vienes de un esquema antiguo, aplica migraciones para habilitar tablas de auth/roles:

```bash
PYTHONPATH=. py migrations/migrate.py
```

La aplicacion ahora tolera ausencia temporal de tablas auth/roles para no bloquear operaciones de wallets, pero la migracion sigue siendo recomendada.
