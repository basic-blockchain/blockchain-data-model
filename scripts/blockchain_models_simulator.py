#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def run_utxo_coffee_export() -> dict:
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

    return {
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


def run_account_coffee_export() -> dict:
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

    return {
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


def run_utxo_retail() -> dict:
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

    return {
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


def run_account_retail() -> dict:
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

    return {
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

    args = parser.parse_args()
    results = run_scenario(args.model, args.scenario)

    if args.json:
        print(json.dumps(_to_jsonable(results), indent=2, ensure_ascii=False))
        return

    print_human_report(results)


if __name__ == "__main__":
    main()
