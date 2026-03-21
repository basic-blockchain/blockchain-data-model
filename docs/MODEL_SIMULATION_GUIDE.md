# Simulación Realista de Modelos Blockchain

## Objetivo principal
Replicar con ejemplos reales el comportamiento de los dos modelos iniciales del repositorio:
- UTXO
- Account-based

## Script principal

```bash
py scripts/blockchain_models_simulator.py
```

## Escenarios incluidos
1. `coffee-export`
- Trazabilidad de lote de café
- Certificados
- Eventos logísticos
- Transferencias y fees
- Auditoría de compliance

2. `retail-payments`
- Pagos de comercio minorista
- Múltiples transferencias
- Confirmaciones por bloques
- Costos de red (validator pool)

## Ejemplos de ejecución

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo
py scripts/blockchain_models_simulator.py --scenario retail-payments --model account
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json
```

## Persistencia JSON (separada por modelo)
La capa de persistencia se implementa por archivo independiente para no mezclar movimientos:
- `data/simulation-runs/utxo-runs.json`
- `data/simulation-runs/account-runs.json`

Guardar resultados y movimientos de una corrida:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --persist
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo --persist
```

Consultar corridas persistidas:

```bash
py scripts/blockchain_models_simulator.py --list-runs --run-model both
py scripts/blockchain_models_simulator.py --list-runs --run-model utxo --limit 10
py scripts/blockchain_models_simulator.py --show-run-id <RUN_ID> --run-model account
```

Directorio personalizado de persistencia:

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model account --persist --store-dir data/my-runs
```

## Métricas por corrida
Cada resultado incorpora métricas para observabilidad técnica y futura exposición por API:
- `execution_ms`
- `total_events`
- `total_transactions`
- `pending_transactions`
- `confirmed_transactions`
- `finalized_transactions`
- `chain_height`
- `state_items`

En modo `--json`, estas métricas viajan dentro de cada elemento de `results`.

## Nota sobre el módulo de observabilidad
El módulo de observabilidad de agentes (`scripts/dev_team_console.py`) se mantiene como plus/MVP opcional.
No es el núcleo del sistema de simulación de modelos blockchain.

## Cuándo se actualiza cada JSON

| Componente | Comando / Acción | ¿Actualiza JSON? | Archivo |
|---|---|---|---|
| Simulador UTXO/Account | run con `--persist` | Sí | `data/simulation-runs/utxo-runs.json`, `data/simulation-runs/account-runs.json` |
| Simulador UTXO/Account | run sin `--persist` | No | No aplica |
| Simulador UTXO/Account | `--list-runs` | No | Solo lectura |
| Simulador UTXO/Account | `--show-run-id` | No | Solo lectura |
| Multiusuario CLI | `create-user` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `create-wallet` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `mint` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `transfer` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `balance` | No | Solo lectura |
| Multiusuario CLI | `list-users` | No | Solo lectura |
| Multiusuario CLI | `list-wallets` | No | Solo lectura |
| Multiusuario CLI | `snapshot` | No | Solo lectura |
| Multiusuario CLI | `list-revisions` | No | Solo lectura |
| Multiusuario CLI | `set-policy` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `set-risk-profile` | Sí | `data/multiuser/wallet-ledger.json` |
| Multiusuario CLI | `get-policy` | No | Solo lectura |
| Multiusuario CLI | `list-policies` | No | Solo lectura |
| Multiusuario CLI | `get-risk-profile` | No | Solo lectura |
| Multiusuario CLI | `list-risk-profiles` | No | Solo lectura |
| Multiusuario CLI | `list-alerts` | No | Solo lectura |

## Ejemplos de uso (multiusuario)

```bash
# 1) Crear usuarios
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-alice --display-name "Alice" --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-user --user-id u-bob --display-name "Bob" --json

# 2) Crear wallets
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-alice --wallet-id w-alice --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json create-wallet --user-id u-bob --wallet-id w-bob --json

# 3) Fondear wallet
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json mint --wallet-id w-alice --amount 100 --json

# 4) Transferir entre wallets
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json transfer --from-wallet w-alice --to-wallet w-bob --amount 15 --fee 0.5 --reference invoice-1001 --json

# 5) Consultar estado
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json balance --wallet-id w-bob --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json snapshot --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-revisions --limit 10 --json

# 6) Configurar policy + perfil de riesgo para alertas
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json set-policy --user-id u-alice --can-transfer true --daily-limit 25 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json set-risk-profile --user-id u-alice --profile-name HIGH --transfer-alert-threshold 5 --daily-alert-threshold 12 --json

# 7) Ejecutar transferencias y consultar alertas
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json transfer --from-wallet w-alice --to-wallet w-bob --amount 6 --fee 0 --reference risk-check-1 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json list-alerts --user-id u-alice --limit 20 --json
py scripts/multiuser_wallet_cli.py --store-file data/multiuser/wallet-ledger.json get-risk-profile --user-id u-alice --json
```
