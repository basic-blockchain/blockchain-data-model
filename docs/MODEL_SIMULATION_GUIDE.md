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

## Nota sobre el módulo de observabilidad
El módulo de observabilidad de agentes (`scripts/dev_team_console.py`) se mantiene como plus/MVP opcional.
No es el núcleo del sistema de simulación de modelos blockchain.
