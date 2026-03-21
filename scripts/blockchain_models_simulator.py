#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE_DIR = ROOT / "data" / "simulation-runs"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence.factory import create_simulation_store
from persistence.interfaces import SimulationRunRepository


def load_module(module_name: str, file_name: str):
    module_path = ROOT / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {module_name} desde {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


account_model = load_module("account_model", "account-model.py")
utxo_model = load_module("utxo_model", "utxo-model.py")


def _to_jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _store_for_model(model: str, store_dir: Path) -> SimulationRunRepository:
    model_file = f"{model}-runs.json"
    return create_simulation_store(json_path=store_dir / model_file)


def persist_results(results: list[dict], requested_model: str, scenario: str, store_dir: Path) -> list[dict]:
    persisted = []
    for result in results:
        model = result["model"]
        store = _store_for_model(model, store_dir)
        payload = {
            "model": model,
            "scenario": scenario,
            "requested_model": requested_model,
            "results": [_to_jsonable(result)],
        }
        run_id = store.save_run(payload)
        persisted.append(
            {
                "model": model,
                "run_id": run_id,
                "store_file": str((store_dir / f"{model}-runs.json").resolve()),
            }
        )
    return persisted


def list_persisted_runs(store_dir: Path, model: str, limit: int) -> list[dict]:
    models = ["utxo", "account"] if model == "both" else [model]
    collected = []
    for selected_model in models:
        store = _store_for_model(selected_model, store_dir)
        for item in store.list_runs(limit=limit):
            item["source_model"] = selected_model
            collected.append(item)

    collected.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    if limit > 0:
        return collected[:limit]
    return collected


def get_persisted_run(store_dir: Path, run_id: str, model: str) -> dict | None:
    models = ["utxo", "account"] if model == "both" else [model]
    for selected_model in models:
        store = _store_for_model(selected_model, store_dir)
        record = store.get_run(run_id)
        if record is not None:
            record["source_model"] = selected_model
            record["store_file"] = str((store_dir / f"{selected_model}-runs.json").resolve())
            return record
    return None


def print_runs_summary(runs: list[dict]) -> None:
    if not runs:
        print("No hay corridas persistidas.")
        return
    _print_header("CORRIDAS PERSISTIDAS")
    for row in runs:
        print(
            f"- run_id={row.get('run_id')} | model={row.get('model')} | "
            f"scenario={row.get('scenario')} | source={row.get('source_model')} | "
            f"created_at={row.get('created_at')}"
        )


def _count_by_status(transactions: list[dict], status: str) -> int:
    return sum(1 for tx in transactions if str(tx.get("status", "")).upper() == status.upper())


def _attach_metrics(result: dict, started_at: float) -> dict:
    transactions = result.get("transactions", [])
    metrics = {
        "execution_ms": round((perf_counter() - started_at) * 1000, 3),
        "total_events": len(result.get("events", [])),
        "total_transactions": len(transactions),
        "pending_transactions": _count_by_status(transactions, "PENDING"),
        "confirmed_transactions": _count_by_status(transactions, "CONFIRMED"),
        "finalized_transactions": _count_by_status(transactions, "FINALIZED"),
        "chain_height": int(result.get("chain_height", 0)),
    }

    if result.get("model") == "utxo":
        metrics["state_items"] = len(result.get("utxos", []))
    else:
        metrics["state_items"] = len(result.get("state", {}))

    result["metrics"] = metrics
    return result


def run_utxo_coffee_export() -> dict:
    started_at = perf_counter()
    chain = utxo_model.UTXO_Blockchain(confirmations_required=2, max_txs_per_block=5)

    outputs = []
    outputs.append(chain.create_wallet("Exportador_Colombia")[0])
    outputs.append(chain.create_wallet("Logistica_Latam")[0])
    outputs.append(chain.create_wallet("Aduana_Pacifico")[0])

    outputs.append(
        chain.register_lot(
            lot_id="Lote_Cafe_001",
            owner="Exportador_Colombia",
            product="Cafe Arabe",
            origin="Huila_Colombia",
            initial_amount=Decimal("100"),
        )
    )
    outputs.append(chain.issue_certificate("Lote_Cafe_001", "Fitosanitario", "ICA"))
    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "COSECHA", "Cooperativa_Huila", "Finca_El_Roble"))
    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "PROCESAMIENTO", "Planta_Trillado", "Neiva"))

    outputs.append(chain.send_transaction("Exportador_Colombia", "Logistica_Latam", 30, fee=0.25, lot_id="Lote_Cafe_001"))
    outputs.append(chain.mine_block("Nodo_Validador_1"))

    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "EXPORTACION", "Puerto_Buenaventura", "Buenaventura"))
    outputs.append(chain.mine_block("Nodo_Validador_2"))

    compliance = chain.audit_compliance("Lote_Cafe_001")

    result = {
        "model": "utxo",
        "scenario": "coffee-export",
        "events": outputs,
        "compliance": compliance,
        "balances": {
            "Exportador_Colombia": chain.get_balance("Exportador_Colombia"),
            "Logistica_Latam": chain.get_balance("Logistica_Latam"),
            "Aduana_Pacifico": chain.get_balance("Aduana_Pacifico"),
        },
        "validator_pool": chain.validator_pool,
        "chain_height": len(chain.blocks) - 1,
        "transactions": chain.ledger_snapshot(),
        "utxos": chain.utxo_snapshot(),
    }
    return _attach_metrics(result, started_at)


def run_account_coffee_export() -> dict:
    started_at = perf_counter()
    chain = account_model.AccountBased_Blockchain(confirmations_required=2, max_txs_per_block=5)

    outputs = []
    outputs.append(chain.create_wallet("Exportador_Colombia")[0])
    outputs.append(chain.create_wallet("Logistica_Latam")[0])
    outputs.append(chain.create_wallet("Aduana_Pacifico")[0])

    outputs.append(chain.create_account("Exportador_Colombia", 100))
    outputs.append(chain.create_account("Logistica_Latam", 0))
    outputs.append(chain.create_account("Aduana_Pacifico", 0))

    outputs.append(chain.register_lot("Lote_Cafe_001", "Exportador_Colombia", "Cafe Arabe", "Huila_Colombia"))
    outputs.append(chain.issue_certificate("Lote_Cafe_001", "Fitosanitario", "ICA"))
    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "COSECHA", "Cooperativa_Huila", "Finca_El_Roble"))
    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "PROCESAMIENTO", "Planta_Trillado", "Neiva"))

    outputs.append(chain.send_transaction("Exportador_Colombia", "Logistica_Latam", 30, fee=0.15, expected_nonce=0))
    outputs.append(chain.send_transaction("Exportador_Colombia", "Aduana_Pacifico", 20, fee=0.10, expected_nonce=1))
    outputs.append(chain.mine_block("Nodo_Validador_1"))

    outputs.append(chain.record_logistics_event("Lote_Cafe_001", "EXPORTACION", "Puerto_Buenaventura", "Buenaventura"))
    outputs.append(chain.mine_block("Nodo_Validador_2"))
    outputs.append(chain.transfer_lot("Lote_Cafe_001", "Exportador_Colombia", "Aduana_Pacifico"))

    compliance = chain.audit_compliance("Lote_Cafe_001")

    result = {
        "model": "account",
        "scenario": "coffee-export",
        "events": outputs,
        "compliance": compliance,
        "balances": {
            "Exportador_Colombia": chain.get_balance("Exportador_Colombia"),
            "Logistica_Latam": chain.get_balance("Logistica_Latam"),
            "Aduana_Pacifico": chain.get_balance("Aduana_Pacifico"),
        },
        "validator_pool": chain.validator_pool,
        "chain_height": len(chain.blocks) - 1,
        "transactions": chain.ledger_snapshot(),
        "state": chain.state_snapshot(),
    }
    return _attach_metrics(result, started_at)


def run_utxo_retail() -> dict:
    started_at = perf_counter()
    chain = utxo_model.UTXO_Blockchain(confirmations_required=2, max_txs_per_block=10)
    chain.create_wallet("Fintech_Emisor")
    chain.create_wallet("Comercio_A")
    chain.create_wallet("Comercio_B")

    events = [chain.mint_initial_coins(200, "Fintech_Emisor")]
    events.append(chain.send_transaction("Fintech_Emisor", "Comercio_A", 12.5, fee=0.05))
    events.append(chain.send_transaction("Fintech_Emisor", "Comercio_B", 7.3, fee=0.04))
    events.append(chain.mine_block("Nodo_Retail_1"))
    events.append(chain.send_transaction("Comercio_A", "Comercio_B", 2.1, fee=0.02))
    events.append(chain.mine_block("Nodo_Retail_2"))

    result = {
        "model": "utxo",
        "scenario": "retail-payments",
        "events": events,
        "balances": {
            "Fintech_Emisor": chain.get_balance("Fintech_Emisor"),
            "Comercio_A": chain.get_balance("Comercio_A"),
            "Comercio_B": chain.get_balance("Comercio_B"),
        },
        "validator_pool": chain.validator_pool,
        "chain_height": len(chain.blocks) - 1,
        "transactions": chain.ledger_snapshot(),
        "utxos": chain.utxo_snapshot(),
    }
    return _attach_metrics(result, started_at)


def run_account_retail() -> dict:
    started_at = perf_counter()
    chain = account_model.AccountBased_Blockchain(confirmations_required=2, max_txs_per_block=10)
    chain.create_wallet("Fintech_Emisor")
    chain.create_wallet("Comercio_A")
    chain.create_wallet("Comercio_B")

    events = [chain.create_account("Fintech_Emisor", 200)]
    events.append(chain.create_account("Comercio_A", 0))
    events.append(chain.create_account("Comercio_B", 0))
    events.append(chain.send_transaction("Fintech_Emisor", "Comercio_A", 12.5, fee=0.05, expected_nonce=0))
    events.append(chain.send_transaction("Fintech_Emisor", "Comercio_B", 7.3, fee=0.04, expected_nonce=1))
    events.append(chain.mine_block("Nodo_Retail_1"))
    events.append(chain.send_transaction("Comercio_A", "Comercio_B", 2.1, fee=0.02, expected_nonce=0))
    events.append(chain.mine_block("Nodo_Retail_2"))

    result = {
        "model": "account",
        "scenario": "retail-payments",
        "events": events,
        "balances": {
            "Fintech_Emisor": chain.get_balance("Fintech_Emisor"),
            "Comercio_A": chain.get_balance("Comercio_A"),
            "Comercio_B": chain.get_balance("Comercio_B"),
        },
        "validator_pool": chain.validator_pool,
        "chain_height": len(chain.blocks) - 1,
        "transactions": chain.ledger_snapshot(),
        "state": chain.state_snapshot(),
    }
    return _attach_metrics(result, started_at)


def run_scenario(model: str, scenario: str) -> list[dict]:
    runners = {
        ("utxo", "coffee-export"): run_utxo_coffee_export,
        ("account", "coffee-export"): run_account_coffee_export,
        ("utxo", "retail-payments"): run_utxo_retail,
        ("account", "retail-payments"): run_account_retail,
    }

    if model == "both":
        return [runners[("utxo", scenario)](), runners[("account", scenario)]()]
    return [runners[(model, scenario)]()]


def print_human_report(results: list[dict]) -> None:
    for result in results:
        _print_header(f"MODEL={result['model'].upper()} | SCENARIO={result['scenario']}")
        print("Eventos ejecutados:")
        for event in result["events"]:
            print(f"  - {event}")

        print("\nResumen:")
        print(f"  chain_height: {result['chain_height']}")
        print(f"  validator_pool: {result['validator_pool']}")
        print("  balances:")
        for actor, balance in result["balances"].items():
            print(f"    - {actor}: {balance}")

        if "compliance" in result:
            print("  compliance:")
            print(f"    - status: {result['compliance'].get('status')}")
            missing_events = result["compliance"].get("missing_events", [])
            missing_certs = result["compliance"].get("missing_certificates", [])
            print(f"    - missing_events: {missing_events}")
            print(f"    - missing_certificates: {missing_certs}")

        print(f"\nTransacciones registradas: {len(result['transactions'])}")
        print("Métricas:")
        for key, value in result.get("metrics", {}).items():
            print(f"  - {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulador comparativo para UTXO y modelo de cuentas con escenarios reales."
    )
    parser.add_argument(
        "--model",
        choices=["utxo", "account", "both"],
        default="both",
        help="Modelo a ejecutar.",
    )
    parser.add_argument(
        "--scenario",
        choices=["coffee-export", "retail-payments"],
        default="coffee-export",
        help="Escenario realista a simular.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Salida en JSON estructurado.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persistir movimientos/resultados en JSON por modelo.",
    )
    parser.add_argument(
        "--store-dir",
        default=str(DEFAULT_STORE_DIR),
        help="Directorio de persistencia JSON (separado por modelo).",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="Listar corridas persistidas.",
    )
    parser.add_argument(
        "--show-run-id",
        default="",
        help="Mostrar detalle de una corrida persistida por run_id.",
    )
    parser.add_argument(
        "--run-model",
        choices=["utxo", "account", "both"],
        default="both",
        help="Filtro de modelo para listado/consulta de corridas persistidas.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Cantidad de corridas a listar.",
    )

    args = parser.parse_args()
    store_dir = Path(args.store_dir)

    if args.list_runs:
        runs = list_persisted_runs(store_dir, args.run_model, args.limit)
        if args.json:
            print(json.dumps(_to_jsonable(runs), indent=2, ensure_ascii=False))
            return
        print_runs_summary(runs)
        return

    if args.show_run_id:
        run = get_persisted_run(store_dir, args.show_run_id, args.run_model)
        if run is None:
            print(f"No se encontró run_id={args.show_run_id}.")
            return
        print(json.dumps(_to_jsonable(run), indent=2, ensure_ascii=False))
        return

    results = run_scenario(args.model, args.scenario)
    persisted = []
    if args.persist:
        persisted = persist_results(results, args.model, args.scenario, store_dir)

    if args.json:
        payload = {
            "results": results,
            "persisted_runs": persisted,
        }
        print(json.dumps(_to_jsonable(payload), indent=2, ensure_ascii=False))
        return

    print_human_report(results)
    if persisted:
        _print_header("PERSISTENCIA JSON")
        for item in persisted:
            print(
                f"- model={item['model']} | run_id={item['run_id']} | "
                f"store_file={item['store_file']}"
            )


if __name__ == "__main__":
    main()
