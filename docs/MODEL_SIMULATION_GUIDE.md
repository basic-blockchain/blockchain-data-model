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
