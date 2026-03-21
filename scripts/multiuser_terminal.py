#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, field
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


def _register_command_metric(session: SessionState, action: str, is_error: bool, elapsed_ms: float, result) -> None:
    session.total_commands += 1
    session.total_exec_ms += max(0.0, elapsed_ms)
    session.last_exec_ms = max(0.0, elapsed_ms)
    if is_error:
        session.failed_commands += 1
    else:
        session.successful_commands += 1

    metric = session.command_metrics.setdefault(
        action,
        {
            "count": 0,
            "ok": 0,
            "total_ms": 0.0,
        },
    )
    metric["count"] = int(metric["count"]) + 1
    if not is_error:
        metric["ok"] = int(metric["ok"]) + 1
    metric["total_ms"] = float(metric["total_ms"]) + max(0.0, elapsed_ms)


def _parse_optional_int(raw_value: str, field_name: str) -> tuple[int | None, str | None]:
    raw = raw_value.strip()
    if not raw:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, f"Error: {field_name} debe ser entero"


def _resolve_sender_token(session: SessionState, provided_token: str) -> str:
    token = provided_token.strip()
    if token:
        return token
    if session.last_token != "-":
        return session.last_token
    return ""


def _run_transfer_wizard(ledger, session: SessionState):
    print("\nTransfer wizard")
    from_wallet = _ask("from_wallet: ")
    to_wallet = _ask("to_wallet: ")
    amount = _ask("amount: ")
    fee = _ask("fee (default 0): ") or "0"
    sender_token_input = _ask("sender_token (enter=use last token): ")
    sender_token = _resolve_sender_token(session, sender_token_input)
    expected_nonce_raw = _ask("expected_nonce (optional): ")
    expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
    if nonce_error:
        return nonce_error, True

    print("\nConfirm transfer")
    print(f"- from_wallet: {from_wallet}")
    print(f"- to_wallet: {to_wallet}")
    print(f"- amount: {amount}")
    print(f"- fee: {fee}")
    print(f"- sender_token_source: {'provided' if sender_token_input.strip() else 'session-last-token'}")
    print(f"- expected_nonce: {expected_nonce if expected_nonce is not None else '-'}")
    confirm = (_ask("confirm (y/N): ") or "n").lower()
    if confirm != "y":
        return "Cancelled by user", True

    if not sender_token:
        return "Error: sender_token es requerido y no hay token de sesion", True

    result = ledger.transfer(
        from_wallet,
        to_wallet,
        amount,
        fee=fee,
        sender_token=sender_token,
        expected_nonce=expected_nonce,
    )
    is_error = isinstance(result, str) and result.startswith("Error:")
    return result, is_error


def _apply_result_to_session(
    session: SessionState,
    *,
    action: str,
    result,
    revision_id: str | None,
    is_error: bool,
    elapsed_ms: float = 0.0,
) -> None:
    session.last_action = action
    session.last_status = "ERROR" if is_error else "OK"
    session.last_message = _short_json(result)
    session.last_revision_id = revision_id or "-"
    token = _extract_token_from_result(result)
    if token:
        session.last_token = token
    _register_command_metric(session, action, is_error, elapsed_ms, result)


def _print_session(session: SessionState) -> None:
    print("\n" + "=" * 78)
    print(_style("Console UX Dashboard", "1;36"))
    print("-" * 78)

    efficiency = 0.0
    if session.total_commands > 0:
        efficiency = (session.successful_commands / session.total_commands) * 100.0

    avg_exec_ms = 0.0
    if session.total_commands > 0:
        avg_exec_ms = session.total_exec_ms / session.total_commands

    eff_text = _style(f"{efficiency:5.1f}%", "1;32") if efficiency >= 70.0 else _style(f"{efficiency:5.1f}%", "1;33")
    status_text = _style(session.last_status, "1;31") if session.last_status == "ERROR" else _style(session.last_status, "1;32")

    print(f"Total commands:      {session.total_commands}")
    print(f"Success / Errors:    {session.successful_commands} / {session.failed_commands}")
    print(f"Last exec time:      {session.last_exec_ms:.1f}ms")
    print(f"Average exec time:   {avg_exec_ms:.1f}ms")
    print(f"Last action/status:  {session.last_action} / {status_text}")
    print(f"Last revision id:    {session.last_revision_id}")
    print(f"Last token:          {session.last_token}")
    print(f"Last message:        {session.last_message}")
    print(f"Efficiency meter:    [{_style(_meter(efficiency), '1;32')}] {eff_text}")

    print("\nBy Command")
    print("-" * 78)
    print(f"{'#':<3} {'Command':<22} {'Count':>5} {'OK':>5} {'Avg%':>7} {'Time':>10} {'Impact':>20}")
    print("-" * 78)

    if not session.command_metrics:
        print("1. no-commands-yet           0     0    0.0%      0.0ms  [--------------------]")
        return

    rows = sorted(session.command_metrics.items(), key=lambda item: int(item[1]["count"]), reverse=True)
    for idx, (name, metric) in enumerate(rows, start=1):
        count = int(metric["count"])
        ok = int(metric["ok"])
        avg_percent = ((ok / count) * 100.0) if count else 0.0
        avg_ms = (float(metric["total_ms"]) / count) if count else 0.0
        impact_percent = ((count / session.total_commands) * 100.0) if session.total_commands else 0.0
        impact_bar = _meter(impact_percent, width=20)
        avg_text = _style(f"{avg_percent:5.1f}%", "1;32") if avg_percent >= 70 else _style(f"{avg_percent:5.1f}%", "1;33")
        print(
            f"{idx}. {name:<22} {count:>5} {ok:>5} {avg_text:>7} {avg_ms:>9.1f}ms  [{_style(impact_bar, '1;36')}]"
        )


def main() -> None:
    store_file = DEFAULT_STORE
    session = SessionState()
    print("Multiuser Terminal (ACCOUNT/UTXO)")
    print(f"Store: {store_file}")

    while True:
        _print_session(session)
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
        print("0) exit")

        option = _ask("Option: ")
        store, ledger = _load(store_file)

        if option == "1":
            user_id = _ask("user_id: ")
            display_name = _ask("display_name: ")
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
            )
        elif option == "2":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id (20-30, enter=auto): ")
            currency = _ask("currency (default USDX): ") or "USDX"
            model = (_ask("model ACCOUNT|UTXO (default ACCOUNT): ") or "ACCOUNT").upper()
            started_at = time.perf_counter()
            result = ledger.create_wallet(user_id, wallet_id=wallet_id, currency=currency, model=model)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                _apply_result_to_session(
                    session,
                    action="create-wallet",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="create-wallet",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
            )
        elif option == "3":
            wallet_id = _ask("wallet_id: ")
            amount = _ask("amount: ")
            reference = _ask("reference (default MINT): ") or "MINT"
            started_at = time.perf_counter()
            result = ledger.mint(wallet_id, amount, reference=reference)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(result)
            print(f"revision_id={rev}")
            _apply_result_to_session(session, action="mint", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms)
        elif option == "4":
            from_wallet = _ask("from_wallet: ")
            to_wallet = _ask("to_wallet: ")
            amount = _ask("amount: ")
            fee = _ask("fee (default 0): ") or "0"
            sender_token = _resolve_sender_token(session, _ask("sender_token (enter=use last token): "))
            expected_nonce_raw = _ask("expected_nonce (optional): ")
            expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
            if nonce_error:
                print(nonce_error)
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=nonce_error,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=0.0,
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
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                _apply_result_to_session(
                    session,
                    action="transfer",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(result)
            print(f"revision_id={rev}")
            _apply_result_to_session(session, action="transfer", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms)
        elif option == "5":
            user_id = _ask("user_id (optional): ")
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
            )
        elif option == "6":
            wallet_id = _ask("wallet_id (optional): ")
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
            )
        elif option == "7":
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
            )
        elif option == "8":
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
            )
        elif option == "9":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id: ")
            current_token = _ask("current_token (optional): ")
            started_at = time.perf_counter()
            result = ledger.refresh_wallet_token(user_id, wallet_id, current_token=current_token)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                _apply_result_to_session(
                    session,
                    action="refresh-token",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
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
            )
        elif option == "10":
            started_at = time.perf_counter()
            result, is_error = _run_transfer_wizard(ledger, session)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if is_error:
                print(result)
                _apply_result_to_session(
                    session,
                    action="transfer-wizard",
                    result=result,
                    revision_id=None,
                    is_error=True,
                    elapsed_ms=elapsed_ms,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            print(result)
            print(f"revision_id={rev}")
            _apply_result_to_session(
                session,
                action="transfer-wizard",
                result=result,
                revision_id=rev,
                is_error=False,
                elapsed_ms=elapsed_ms,
            )
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
            )


if __name__ == "__main__":
    main()
