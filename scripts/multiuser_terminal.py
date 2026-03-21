#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data" / "multiuser" / "wallet-ledger.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence.multiuser_wallet_store import JsonMultiUserWalletStore


@dataclass
class SessionState:
    last_action: str = "-"
    last_status: str = "-"
    last_message: str = "-"
    last_revision_id: str = "-"
    last_token: str = "-"
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    total_exec_ms: float = 0.0
    last_exec_ms: float = 0.0
    total_input_units: int = 0
    total_output_units: int = 0
    total_saved_units: int = 0
    pending_feedback_kind: str = ""
    pending_feedback_action: str = ""
    pending_feedback_message: str = ""
    command_metrics: dict[str, dict[str, float | int]] = field(default_factory=dict)


def _load(store_file: Path):
    store = JsonMultiUserWalletStore(store_file)
    ledger = store.load_ledger()
    return store, ledger


def _persist(store, ledger):
    return store.save_ledger(ledger)


def _ask(label: str) -> str:
    return input(label).strip()


def _short_json(value, max_len: int = 120) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_token_from_result(result) -> str | None:
    if isinstance(result, dict):
        token = result.get("auth_token")
        if isinstance(token, str) and token:
            return token
    return None


def _supports_ansi() -> bool:
    return sys.stdout.isatty()


def _style(text: str, code: str) -> str:
    if not _supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


def _meter(percentage: float, width: int = 24) -> str:
    safe = max(0.0, min(100.0, percentage))
    filled = int(round((safe / 100.0) * width))
    return "#" * filled + "-" * (width - filled)


def _measure_units(*values) -> int:
    total = 0
    for value in values:
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            total += len(json.dumps(value, ensure_ascii=False, sort_keys=True))
        else:
            total += len(str(value))
    return total


def _register_command_metric(
    session: SessionState,
    action: str,
    is_error: bool,
    elapsed_ms: float,
    input_units: int,
    output_units: int,
) -> None:
    session.total_commands += 1
    session.total_exec_ms += max(0.0, elapsed_ms)
    session.last_exec_ms = max(0.0, elapsed_ms)
    session.total_input_units += max(0, input_units)
    session.total_output_units += max(0, output_units)
    saved_units = max(0, input_units - output_units)
    session.total_saved_units += saved_units
    if is_error:
        session.failed_commands += 1
    else:
        session.successful_commands += 1

    metric = session.command_metrics.setdefault(
        action,
        {
            "count": 0,
            "ok": 0,
            "input_units": 0,
            "output_units": 0,
            "saved_units": 0,
            "save_percent_sum": 0.0,
            "total_ms": 0.0,
        },
    )
    metric["count"] = int(metric["count"]) + 1
    if not is_error:
        metric["ok"] = int(metric["ok"]) + 1
    metric["input_units"] = int(metric["input_units"]) + max(0, input_units)
    metric["output_units"] = int(metric["output_units"]) + max(0, output_units)
    metric["saved_units"] = int(metric["saved_units"]) + saved_units
    save_percent = (saved_units / input_units) * 100.0 if input_units > 0 else 0.0
    metric["save_percent_sum"] = float(metric["save_percent_sum"]) + save_percent
    metric["total_ms"] = float(metric["total_ms"]) + max(0.0, elapsed_ms)


def _parse_optional_int(raw_value: str, field_name: str) -> tuple[int | None, str | None]:
    raw = raw_value.strip()
    if not raw:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, f"Error: {field_name} debe ser entero"


def _validate_numeric(raw_value: str, field_name: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return f"Error: {field_name} es requerido y solo acepta numeros"
    try:
        Decimal(value)
    except (InvalidOperation, ValueError):
        return f"Error: {field_name} solo acepta numeros"
    return None


def _resolve_sender_token(session: SessionState, provided_token: str) -> str:
    _ = session
    return provided_token.strip()


def _sender_token_prompt(session: SessionState) -> str:
    _ = session
    return "sender_token (requerido): "


def _is_domain_error_result(result) -> bool:
    if not isinstance(result, str):
        return False
    return result.startswith("Error:") or result.startswith("Wallet invalida")


def _compact_feedback_message(result) -> str:
    text = _short_json(result, max_len=180)
    if text.lower().startswith("error:"):
        return text[6:].strip()
    return text


def _run_transfer_wizard(ledger, session: SessionState):
    print("\nTransfer wizard")
    from_wallet = _ask("from_wallet: ")
    to_wallet = _ask("to_wallet: ")
    amount = _ask("amount: ")
    fee = _ask("fee (default 0): ") or "0"
    sender_token_input = _ask(_sender_token_prompt(session))
    sender_token = _resolve_sender_token(session, sender_token_input)
    expected_nonce_raw = _ask("expected_nonce (optional): ")
    expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
    amount_error = _validate_numeric(amount, "amount")
    fee_error = _validate_numeric(fee, "fee")
    if nonce_error:
        return nonce_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce_raw)
    if amount_error:
        return amount_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
    if fee_error:
        return fee_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)

    print("\nConfirm transfer")
    print(f"- from_wallet: {from_wallet}")
    print(f"- to_wallet: {to_wallet}")
    print(f"- amount: {amount}")
    print(f"- fee: {fee}")
    print(f"- sender_token_source: {'provided' if sender_token_input.strip() else 'empty'}")
    print(f"- expected_nonce: {expected_nonce if expected_nonce is not None else '-'}")
    confirm = (_ask("confirm (y/N): ") or "n").lower()
    input_units = _measure_units(
        from_wallet,
        to_wallet,
        amount,
        fee,
        sender_token,
        expected_nonce,
        confirm,
    )
    if confirm != "y":
        return "Cancelled by user", True, input_units

    if not sender_token:
        return "Error: sender_token es requerido.", True, input_units

    result = ledger.transfer(
        from_wallet,
        to_wallet,
        amount,
        fee=fee,
        sender_token=sender_token,
        expected_nonce=expected_nonce,
    )
    is_error = _is_domain_error_result(result)
    return result, is_error, input_units


def _apply_result_to_session(
    session: SessionState,
    *,
    action: str,
    result,
    revision_id: str | None,
    is_error: bool,
    elapsed_ms: float = 0.0,
    input_units: int = 0,
) -> None:
    session.last_action = action
    session.last_status = "ERROR" if is_error else "OK"
    session.last_message = _short_json(result)
    session.last_revision_id = revision_id or "-"
    token = _extract_token_from_result(result)
    if token:
        session.last_token = token
    session.pending_feedback_kind = "ERROR" if is_error else "SUCCESS"
    session.pending_feedback_action = action
    session.pending_feedback_message = _compact_feedback_message(result)
    output_units = _measure_units(result)
    _register_command_metric(session, action, is_error, elapsed_ms, input_units, output_units)


def _print_alert(kind: str, action: str, message: str) -> None:
    if kind == "ERROR":
        color = "1;31"
    else:
        color = "1;32"
    label = f"[{kind}]"
    title = f"{label} {action}"
    body = f"Mensaje: {message}"

    border = "+" + "-" * 76 + "+"
    print(_style(border, color))
    print(_style(f"| {title:<74} |", color))
    print(_style(f"| {body:<74} |", color))
    print(_style(border, color))


def _print_pending_feedback(session: SessionState) -> None:
    if not session.pending_feedback_action:
        return
    print("\nResultado inmediato:")
    _print_alert(session.pending_feedback_kind, session.pending_feedback_action, session.pending_feedback_message)
    session.pending_feedback_kind = ""
    session.pending_feedback_action = ""
    session.pending_feedback_message = ""


def _print_session(session: SessionState) -> None:
    print("\n" + "=" * 78)
    print(_style("Console UX Dashboard", "1;36"))
    print("-" * 78)

    efficiency = (session.total_saved_units / session.total_input_units) * 100.0 if session.total_input_units > 0 else 0.0

    avg_exec_ms = 0.0
    if session.total_commands > 0:
        avg_exec_ms = session.total_exec_ms / session.total_commands

    saved_percent = (session.total_saved_units / session.total_input_units) * 100.0 if session.total_input_units > 0 else 0.0

    eff_text = _style(f"{efficiency:5.1f}%", "1;32") if efficiency >= 70.0 else _style(f"{efficiency:5.1f}%", "1;33")
    avg_text = _style(f"{saved_percent:5.1f}%", "1;32") if saved_percent >= 70.0 else _style(f"{saved_percent:5.1f}%", "1;33")

    print(f"Total commands:      {session.total_commands}")
    print(f"Input tokens:        {session.total_input_units}")
    print(f"Output tokens:       {session.total_output_units}")
    print(f"Tokens saved:        {session.total_saved_units} ({avg_text})")
    print(f"Total exec time:     {session.total_exec_ms:.0f}ms (avg {avg_exec_ms:.0f}ms)")
    print(f"Efficiency meter:    [{_style(_meter(efficiency), '1;32')}] {eff_text}")

    print("\nBy Command")
    print("-" * 78)
    print(f"{'#':<3} {'Command':<22} {'Count':>5} {'Saved':>7} {'Avg%':>7} {'Time':>10} {'Impact':>20}")
    print("-" * 78)

    if not session.command_metrics:
        print("1. no-commands-yet           0       0    0.0%      0.0ms  [--------------------]")
        return

    rows = sorted(session.command_metrics.items(), key=lambda item: int(item[1]["count"]), reverse=True)
    for idx, (name, metric) in enumerate(rows, start=1):
        count = int(metric["count"])
        saved = int(metric["saved_units"])
        avg_percent = (float(metric["save_percent_sum"]) / count) if count else 0.0
        avg_ms = (float(metric["total_ms"]) / count) if count else 0.0
        impact_percent = ((saved / session.total_saved_units) * 100.0) if session.total_saved_units else ((count / session.total_commands) * 100.0 if session.total_commands else 0.0)
        impact_bar = _meter(impact_percent, width=20)
        avg_text = _style(f"{avg_percent:5.1f}%", "1;32") if avg_percent >= 70 else _style(f"{avg_percent:5.1f}%", "1;33")
        print(
            f"{idx}. {name:<22} {count:>5} {saved:>7} {avg_text:>7} {avg_ms:>9.1f}ms  [{_style(impact_bar, '1;36')}]"
        )


def main() -> None:
    store_file = DEFAULT_STORE
    session = SessionState()
    print("Multiuser Terminal (ACCOUNT/UTXO)")
    print(f"Store: {store_file}")
    print("Tip: usa 11 para ver el dashboard completo cuando lo necesites.")

    while True:
        _print_pending_feedback(session)
        print("\nMenu:")
        print("1) create-user")
        print("2) create-wallet")
        print("3) mint")
        print("4) transfer")
        print("5) list-wallets")
        print("6) list-utxos")
        print("7) verify-integrity")
        print("8) snapshot")
        print("9) refresh-token")
        print("10) transfer-wizard")
        print("11) view-dashboard")
        print("0) exit")

        option = _ask("Option: ")
        store, ledger = _load(store_file)

        if option == "1":
            user_id = _ask("user_id: ")
            display_name = _ask("display_name: ")
            input_units = _measure_units(user_id, display_name)
            started_at = time.perf_counter()
            result = ledger.create_user(user_id, display_name)
            rev = _persist(store, ledger)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            print(result)
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="create-user",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "2":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id (20-30, enter=auto): ")
            currency = _ask("currency (default USDX): ") or "USDX"
            model = (_ask("model ACCOUNT|UTXO (default ACCOUNT): ") or "ACCOUNT").upper()
            input_units = _measure_units(user_id, wallet_id, currency, model)
            started_at = time.perf_counter()
            result = ledger.create_wallet(user_id, wallet_id=wallet_id, currency=currency, model=model)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if _is_domain_error_result(result):
                print(result)
                _apply_result_to_session(
                    session,
                    action="create-wallet",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                    input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print("Wallet creada correctamente.")
            if isinstance(result, dict) and result.get("auth_token"):
                print(f"TOKEN para transfer/refresh-token: {result['auth_token']}")
                print("Tip: en transfer, ingresa este token en sender_token (es obligatorio).")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="create-wallet",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "3":
            wallet_id = _ask("wallet_id: ")
            amount = _ask("amount: ")
            reference = _ask("reference (default MINT): ") or "MINT"
            input_units = _measure_units(wallet_id, amount, reference)
            amount_error = _validate_numeric(amount, "amount")
            if amount_error:
                _apply_result_to_session(
                    session,
                    action="mint",
                    result=amount_error,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=0.0,
                    input_units=input_units,
                )
                continue
            started_at = time.perf_counter()
            result = ledger.mint(wallet_id, amount, reference=reference)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(result)
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="mint",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "4":
            from_wallet = _ask("from_wallet: ")
            to_wallet = _ask("to_wallet: ")
            amount = _ask("amount: ")
            fee = _ask("fee (default 0): ") or "0"
            sender_token = _resolve_sender_token(session, _ask(_sender_token_prompt(session)))
            expected_nonce_raw = _ask("expected_nonce (optional): ")
            expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
            input_units = _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
            amount_error = _validate_numeric(amount, "amount")
            fee_error = _validate_numeric(fee, "fee")
            if nonce_error:
                print(nonce_error)
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=nonce_error,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=0.0,
                    input_units=input_units,
                )
                continue
            if amount_error:
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=amount_error,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=0.0,
                    input_units=input_units,
                )
                continue
            if fee_error:
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=fee_error,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=0.0,
                    input_units=input_units,
                )
                continue
            started_at = time.perf_counter()
            result = ledger.transfer(
                from_wallet,
                to_wallet,
                amount,
                fee=fee,
                sender_token=sender_token,
                expected_nonce=expected_nonce,
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if _is_domain_error_result(result):
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                    input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="transfer",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "5":
            user_id = _ask("user_id (optional): ")
            input_units = _measure_units(user_id)
            started_at = time.perf_counter()
            result = ledger.list_wallets(user_id=user_id)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            _apply_result_to_session(
                session,
                action="list-wallets",
                result=result,
                revision_id=None,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "6":
            wallet_id = _ask("wallet_id (optional): ")
            input_units = _measure_units(wallet_id)
            started_at = time.perf_counter()
            result = ledger.list_utxos(wallet_id=wallet_id)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            _apply_result_to_session(
                session,
                action="list-utxos",
                result=result,
                revision_id=None,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "7":
            input_units = _measure_units("verify-integrity")
            started_at = time.perf_counter()
            result = ledger.verify_transfer_integrity()
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            _apply_result_to_session(
                session,
                action="verify-integrity",
                result=result,
                revision_id=None,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "8":
            input_units = _measure_units("snapshot")
            started_at = time.perf_counter()
            result = ledger.state_snapshot()
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            _apply_result_to_session(
                session,
                action="snapshot",
                result=result,
                revision_id=None,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "9":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id: ")
            current_token = _ask("current_token (optional): ")
            input_units = _measure_units(user_id, wallet_id, current_token)
            started_at = time.perf_counter()
            result = ledger.refresh_wallet_token(user_id, wallet_id, current_token=current_token)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if _is_domain_error_result(result):
                print(result)
                _apply_result_to_session(
                    session,
                    action="refresh-token",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                    input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="refresh-token",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "10":
            started_at = time.perf_counter()
            result, is_error, input_units = _run_transfer_wizard(ledger, session)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if is_error:
                _apply_result_to_session(
                    session,
                    action="transfer-wizard",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                    input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="transfer-wizard",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
                input_units=input_units,
            )
        elif option == "11":
            _print_session(session)
        elif option == "0":
            print("Bye")
            break
        else:
            print("Invalid option")
            _apply_result_to_session(
                session,
                action="invalid-option",
                result=f"Invalid option: {option}",
                revision_id=None,
                is_error=True,
                elapsed_ms=0.0,
                input_units=_measure_units(option),
            )


if __name__ == "__main__":
    main()
