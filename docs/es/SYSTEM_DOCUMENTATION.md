# Documentacion Tecnica del MVP

## 1. Objetivo

Modelar y comparar dos enfoques de blockchain:
- UTXO
- Account-based

con escenarios funcionales, trazabilidad, compliance y persistencia JSON separada por modelo.

## 2. Diagrama lineal del sistema

```mermaid
flowchart LR
    A[CLI: blockchain_models_simulator.py] --> B{Modelo}
    B --> C[UTXO model]
    B --> D[Account model]
    C --> E[Resultados]
    D --> E
    E --> F[Metricas]
    E --> G[Persistencia JSON]
    G --> H[data/simulation-runs/utxo-runs.json]
    G --> I[data/simulation-runs/account-runs.json]
```

## 3. Casos de uso

1. Ejecutar simulacion coffee-export en ambos modelos.
2. Ejecutar simulacion retail-payments en un modelo especifico.
3. Persistir corrida de simulacion por modelo.
4. Listar corridas persistidas con limite y filtro.
5. Consultar detalle de una corrida por run_id.
6. Auditar cumplimiento (eventos/certificados) para lotes trazables.

## 4. Diagrama de secuencia principal

```mermaid
sequenceDiagram
    participant U as Usuario
    participant CLI as Simulator CLI
    participant M as Modelo (UTXO/Account)
    participant S as JsonSimulationStore

    U->>CLI: Ejecuta comando con --scenario y --model
    CLI->>M: run_scenario(model, scenario)
    M-->>CLI: resultados + transacciones + estado
    CLI->>CLI: attach metrics
    alt --persist activo
        CLI->>S: save_run(payload)
        S-->>CLI: run_id
    end
    CLI-->>U: salida humana o JSON
```

## 5. Estructura de datos

### 5.1 UTXO (estado no gastado)

Campos principales:
- utxo_id
- tx_id
- output_index
- amount
- owner
- created_at
- lot_id
- metadata

### 5.2 AccountState

Campos principales:
- balance
- nonce
- created_at
- public_key

### 5.3 Documento de persistencia

```json
{
  "schema_version": 1,
  "updated_at": "2026-03-21T00:00:00+00:00",
  "runs": [
    {
      "run_id": "run-20260321T000000Z-deadbeef",
      "created_at": "2026-03-21T00:00:00+00:00",
      "payload": {
        "model": "utxo",
        "scenario": "coffee-export",
        "requested_model": "both",
        "results": [
          {
            "model": "utxo",
            "scenario": "coffee-export",
            "metrics": {
              "execution_ms": 12.4,
              "total_events": 10,
              "total_transactions": 3,
              "pending_transactions": 0,
              "confirmed_transactions": 0,
              "finalized_transactions": 3,
              "chain_height": 2,
              "state_items": 4
            }
          }
        ]
      }
    }
  ]
}
```

## 6. Payloads y respuestas

Nota: el MVP actual no expone API HTTP; los payloads son de CLI y respuesta JSON.

### 6.1 Request (CLI)

```bash
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json --persist
```

### 6.2 Response (JSON)

```json
{
  "results": [
    {
      "model": "utxo",
      "scenario": "coffee-export",
      "events": ["..."],
      "balances": {"Exportador_Colombia": "69.75000000"},
      "validator_pool": "0.25000000",
      "chain_height": 2,
      "transactions": [],
      "utxos": [],
      "metrics": {
        "execution_ms": 10.1,
        "total_events": 11,
        "total_transactions": 3,
        "pending_transactions": 0,
        "confirmed_transactions": 0,
        "finalized_transactions": 3,
        "chain_height": 2,
        "state_items": 4
      }
    }
  ],
  "persisted_runs": [
    {
      "model": "utxo",
      "run_id": "run-20260321T000000Z-deadbeef",
      "store_file": ".../data/simulation-runs/utxo-runs.json"
    }
  ]
}
```

## 7. Convenciones de ejecucion

- Modelo: `utxo`, `account`, `both`
- Escenario: `coffee-export`, `retail-payments`
- Persistencia separada por archivo para evitar mezclar dominios.
- Tests de regresion: `py -m pytest -q`

## 8. Limites actuales del MVP

- Sin endpoints REST/GraphQL.
- Sin base de datos SQL/NoSQL (persistencia JSON file-based).
- Sin autenticacion/autorizacion de usuarios finales.
