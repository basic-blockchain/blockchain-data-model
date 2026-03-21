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

from persistence.factory import create_wallet_store


# ── ANSI helpers ─────────────────────────────────────────

def _supports_ansi() -> bool:
    return sys.stdout.isatty()


def _s(text: str, code: str) -> str:
    if not _supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


# Color shortcuts
def _dim(t: str) -> str: return _s(t, "2")
def _bold(t: str) -> str: return _s(t, "1")
def _cyan(t: str) -> str: return _s(t, "1;36")
def _green(t: str) -> str: return _s(t, "1;32")
def _red(t: str) -> str: return _s(t, "1;31")
def _yellow(t: str) -> str: return _s(t, "1;33")
def _blue(t: str) -> str: return _s(t, "1;34")
def _magenta(t: str) -> str: return _s(t, "1;35")
def _white(t: str) -> str: return _s(t, "1;37")


# ── Box drawing ──────────────────────────────────────────

W = 72  # Inner width for boxes


def _box_top() -> str:
    return _dim(f"╔{'═' * (W + 2)}╗")


def _box_mid() -> str:
    return _dim(f"╠{'═' * (W + 2)}╣")


def _box_bot() -> str:
    return _dim(f"╚{'═' * (W + 2)}╝")


def _box_line(text: str = "", align: str = "left") -> str:
    plain = text.replace("\033[0m", "").replace("\033[1m", "").replace("\033[2m", "")
    for code in ("1;36", "1;32", "1;31", "1;33", "1;34", "1;35", "1;37", "0;33", "0;37"):
        plain = plain.replace(f"\033[{code}m", "")
    pad = W - len(plain)
    if pad < 0:
        pad = 0
    if align == "center":
        left_pad = pad // 2
        right_pad = pad - left_pad
        content = " " * left_pad + text + " " * right_pad
    else:
        content = text + " " * pad
    return f"{_dim('║')} {content} {_dim('║')}"


def _wrap_box(text: str, width: int = W) -> list[str]:
    if len(text) <= width:
        return [text]
    lines: list[str] = []
    while text:
        if len(text) <= width:
            lines.append(text)
            break
        cut = text.rfind(" ", 0, width)
        if cut <= 0:
            cut = width
        lines.append(text[:cut])
        text = text[cut:].lstrip()
    return lines


# ── Banner ───────────────────────────────────────────────

BANNER = r"""
       ___       ___       ___       ___       ___       ___
      /\  \     /\__\     /\  \     /\  \     /\__\     /\  \
     /::\  \   /::L_L_   /::\  \   _\:\  \   /:| _|_   /::\  \
    /::\:\__\ /:/L:\__\ /::\:\__\ /\/::\__\ /::|/\__\ /\:\:\__\
    \:\:\/  / \/_/:/  / \:\::/  / \::/\/__/ \/|::/  / \:\:\/__/
     \:\/  /    /:/  /   \::/  /   \:\__\     |:/  /   \:\/  /
      \/__/     \/__/     \/__/     \/__/     \/__/     \/__/
"""

LOGO_LINES = [
    "   ╭─────────────────────────────────────────────╮",
    "   │         ₿  BLOCKCHAIN WALLET SYSTEM         │",
    "   │         ── Multiuser Terminal v2.2 ──        │",
    "   ╰─────────────────────────────────────────────╯",
]


def _print_banner() -> None:
    print(_cyan(BANNER))
    for line in LOGO_LINES:
        print(_yellow(line))
    print()
    print(_dim("  UTXO & Account-based models • JSON / PostgreSQL persistence"))
    print(_dim("  Type the option number and press Enter. Type 0 to exit."))
    print()


# ── Menu ─────────────────────────────────────────────────

MENU_SECTIONS = [
    ("USUARIOS & WALLETS", [
        ("1", "create-user", "Registrar nuevo usuario en el ledger"),
        ("2", "create-wallet", "Crear wallet UTXO o ACCOUNT para un usuario"),
        ("9", "refresh-token", "Renovar token de autenticacion de wallet"),
    ]),
    ("TRANSACCIONES", [
        ("3", "mint", "Emitir tokens a una wallet"),
        ("4", "transfer", "Transferir fondos entre wallets"),
        ("10", "transfer-wizard", "Asistente interactivo de transferencia"),
    ]),
    ("CONSULTAS", [
        ("5", "list-wallets", "Listar wallets registradas"),
        ("6", "list-utxos", "Listar UTXOs de una wallet"),
        ("7", "verify-integrity", "Verificar integridad nonce + hash-chain"),
        ("8", "snapshot", "Exportar estado completo del ledger"),
    ]),
    ("SISTEMA", [
        ("11", "dashboard", "Metricas de sesion y rendimiento"),
        ("0", "exit", "Salir del terminal"),
    ]),
]


def _print_menu() -> None:
    print()
    print(_box_top())
    print(_box_line(_bold(_cyan("  MENU PRINCIPAL")), "center"))
    print(_box_mid())
    for section_idx, (section_name, items) in enumerate(MENU_SECTIONS):
        print(_box_line(f"  {_dim('──')} {_bold(section_name)} {_dim('─' * (W - len(section_name) - 8))}"))
        for num, name, desc in items:
            num_styled = _yellow(f"[{num:>2}]")
            name_styled = _bold(name)
            print(_box_line(f"   {num_styled} {name_styled:<24} {_dim(desc)}"))
        if section_idx < len(MENU_SECTIONS) - 1:
            print(_box_line())
    print(_box_bot())


# ── Result display ───────────────────────────────────────

def _print_result_box(kind: str, action: str, message: str) -> None:
    if kind == "ERROR":
        color_fn = _red
        icon = "✗"
    else:
        color_fn = _green
        icon = "✓"

    print()
    print(_box_top())
    print(_box_line(color_fn(f"  {icon} [{kind}] {action}")))
    print(_box_mid())
    for line in _wrap_box(f"  {message}", W):
        print(_box_line(line))
    print(_box_bot())


def _print_data_box(title: str, data: dict | list | str, revision_id: str | None = None) -> None:
    print()
    print(_box_top())
    print(_box_line(_cyan(f"  {title}")))
    print(_box_mid())

    if isinstance(data, dict):
        for key, val in data.items():
            val_str = str(val)
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            print(_box_line(f"  {_dim(key + ':'):<30} {_bold(val_str)}"))
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            for i, item in enumerate(data[:20]):
                if i > 0:
                    print(_box_line(_dim("  " + "─" * (W - 4))))
                for key, val in item.items():
                    val_str = str(val)
                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    print(_box_line(f"  {_dim(key + ':'):<30} {val_str}"))
            if len(data) > 20:
                print(_box_line(_dim(f"  ... y {len(data) - 20} mas")))
        else:
            for item in data[:20]:
                print(_box_line(f"  {item}"))
    else:
        for line in _wrap_box(f"  {data}", W):
            print(_box_line(line))

    if revision_id:
        print(_box_mid())
        print(_box_line(_dim(f"  revision: {revision_id}")))

    print(_box_bot())


def _print_token_notice(token: str) -> None:
    print()
    print(_box_top())
    print(_box_line(_yellow("  ⚡ TOKEN DE AUTENTICACION")))
    print(_box_mid())
    print(_box_line(f"  Token: {_bold(token)}"))
    print(_box_line(_dim("  Usa este token en transfer como sender_token.")))
    print(_box_line(_dim("  Expira en 120 segundos.")))
    print(_box_bot())


# ── Prompt helpers ───────────────────────────────────────

def _ask(label: str) -> str:
    return input(label).strip()


def _prompt(label: str, hint: str = "", default: str = "") -> str:
    parts = [f"  {_cyan('›')} {_bold(label)}"]
    if hint:
        parts.append(f" {_dim(hint)}")
    if default:
        parts.append(f" {_dim(f'[{default}]')}")
    parts.append(": ")
    value = input("".join(parts)).strip()
    return value if value else default


def _prompt_confirm(message: str) -> bool:
    resp = input(f"  {_yellow('?')} {message} {_dim('[y/N]')}: ").strip().lower()
    return resp == "y"


def _section_header(title: str) -> None:
    print()
    print(f"  {_cyan('━' * 3)} {_bold(title)} {_cyan('━' * (60 - len(title)))}")
    print()


# ── Session & metrics ────────────────────────────────────

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


def _meter(percentage: float, width: int = 24) -> str:
    safe = max(0.0, min(100.0, percentage))
    filled = int(round((safe / 100.0) * width))
    return "█" * filled + "░" * (width - filled)


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
            "count": 0, "ok": 0, "input_units": 0, "output_units": 0,
            "saved_units": 0, "save_percent_sum": 0.0, "total_ms": 0.0,
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


# ── Validation helpers ───────────────────────────────────

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


def _is_domain_error_result(result) -> bool:
    if not isinstance(result, str):
        return False
    return result.startswith("Error:") or result.startswith("Wallet invalida")


def _compact_feedback_message(result) -> str:
    text = _short_json(result, max_len=180)
    if text.lower().startswith("error:"):
        return text[6:].strip()
    return text


# ── Domain helpers ───────────────────────────────────────

def _resolve_sender_token(session: SessionState, provided_token: str) -> str:
    _ = session
    return provided_token.strip()


def _sender_token_prompt() -> str:
    return "sender_token"


# ── Transfer wizard ──────────────────────────────────────

def _run_transfer_wizard(ledger, session: SessionState):
    _section_header("TRANSFER WIZARD")

    from_wallet = _prompt("from_wallet")
    to_wallet = _prompt("to_wallet")
    amount = _prompt("amount")
    fee = _prompt("fee", default="0")
    sender_token_input = _prompt(_sender_token_prompt(), hint="(requerido)")
    sender_token = _resolve_sender_token(session, sender_token_input)
    expected_nonce_raw = _prompt("expected_nonce", hint="(opcional)")
    expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
    amount_error = _validate_numeric(amount, "amount")
    fee_error = _validate_numeric(fee, "fee")
    if nonce_error:
        return nonce_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce_raw)
    if amount_error:
        return amount_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
    if fee_error:
        return fee_error, True, _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)

    print()
    print(_box_top())
    print(_box_line(_yellow("  CONFIRMAR TRANSFERENCIA")))
    print(_box_mid())
    print(_box_line(f"  {_dim('Origen:')}       {from_wallet}"))
    print(_box_line(f"  {_dim('Destino:')}      {to_wallet}"))
    print(_box_line(f"  {_dim('Monto:')}        {amount}"))
    print(_box_line(f"  {_dim('Fee:')}          {fee}"))
    print(_box_line(f"  {_dim('Token:')}        {'••••' + sender_token[-4:] if len(sender_token) > 4 else '(provided)'}"))
    print(_box_line(f"  {_dim('Nonce:')}        {expected_nonce if expected_nonce is not None else 'auto'}"))
    print(_box_bot())

    input_units = _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
    if not _prompt_confirm("Ejecutar transferencia?"):
        return "Cancelado por el usuario", True, input_units

    if not sender_token:
        return "Error: sender_token es requerido.", True, input_units

    result = ledger.transfer(
        from_wallet, to_wallet, amount,
        fee=fee, sender_token=sender_token, expected_nonce=expected_nonce,
    )
    is_error = _is_domain_error_result(result)
    return result, is_error, input_units


# ── Session result tracking ──────────────────────────────

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


def _print_pending_feedback(session: SessionState) -> None:
    if not session.pending_feedback_action:
        return
    _print_result_box(
        session.pending_feedback_kind,
        session.pending_feedback_action,
        session.pending_feedback_message,
    )
    session.pending_feedback_kind = ""
    session.pending_feedback_action = ""
    session.pending_feedback_message = ""


# ── Dashboard ────────────────────────────────────────────

def _print_dashboard(session: SessionState) -> None:
    efficiency = (session.total_saved_units / session.total_input_units) * 100.0 if session.total_input_units > 0 else 0.0
    avg_exec_ms = session.total_exec_ms / session.total_commands if session.total_commands > 0 else 0.0

    print()
    print(_box_top())
    print(_box_line(_cyan("  ⚡ DASHBOARD DE SESION"), "center"))
    print(_box_mid())

    eff_color = _green if efficiency >= 70 else _yellow
    print(_box_line(f"  {_dim('Comandos totales:')}     {_bold(str(session.total_commands))} ({_green(str(session.successful_commands))} ok, {_red(str(session.failed_commands))} err)"))
    print(_box_line(f"  {_dim('Input tokens:')}         {session.total_input_units}"))
    print(_box_line(f"  {_dim('Output tokens:')}        {session.total_output_units}"))
    print(_box_line(f"  {_dim('Tokens ahorrados:')}     {session.total_saved_units} ({eff_color(f'{efficiency:.1f}%')})"))
    print(_box_line(f"  {_dim('Tiempo total:')}         {session.total_exec_ms:.0f}ms (avg {avg_exec_ms:.0f}ms)"))
    print(_box_line(f"  {_dim('Eficiencia:')}           [{eff_color(_meter(efficiency))}] {eff_color(f'{efficiency:.1f}%')}"))

    if session.command_metrics:
        print(_box_mid())
        print(_box_line(_bold("  Comando              Count  Saved   Avg%     Time    Impact")))
        print(_box_line(_dim("  " + "─" * (W - 4))))
        rows = sorted(session.command_metrics.items(), key=lambda item: int(item[1]["count"]), reverse=True)
        for name, metric in rows:
            count = int(metric["count"])
            saved = int(metric["saved_units"])
            avg_p = (float(metric["save_percent_sum"]) / count) if count else 0.0
            avg_ms = (float(metric["total_ms"]) / count) if count else 0.0
            impact = ((saved / session.total_saved_units) * 100.0) if session.total_saved_units else 0.0
            avg_fn = _green if avg_p >= 70 else _yellow
            bar = _meter(impact, width=12)
            print(_box_line(f"  {name:<20} {count:>5} {saved:>6} {avg_fn(f'{avg_p:>5.1f}%')} {avg_ms:>8.1f}ms  [{_cyan(bar)}]"))

    print(_box_bot())


# ── Persistence helpers ──────────────────────────────────

def _load(store_file: Path):
    store = create_wallet_store(json_path=store_file)
    ledger = store.load_ledger()
    return store, ledger


def _persist(store, ledger):
    return store.save_ledger(ledger)


# ── Main loop ────────────────────────────────────────────

def main() -> None:
    store_file = DEFAULT_STORE
    session = SessionState()

    _print_banner()
    print(_dim(f"  Store: {store_file}"))
    print()

    while True:
        _print_pending_feedback(session)
        _print_menu()

        option = input(f"\n  {_cyan('›')} {_bold('Opcion')}: ").strip()
        store, ledger = _load(store_file)

        if option == "1":
            _section_header("CREAR USUARIO")
            user_id = _prompt("user_id")
            display_name = _prompt("display_name")
            input_units = _measure_units(user_id, display_name)
            started_at = time.perf_counter()
            result = ledger.create_user(user_id, display_name)
            rev = _persist(store, ledger)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            _print_data_box("Usuario creado", result if isinstance(result, dict) else {"resultado": result}, rev)
            _apply_result_to_session(
                session, action="create-user", result=result,
                revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "2":
            _section_header("CREAR WALLET")
            user_id = _prompt("user_id")
            wallet_id = _prompt("wallet_id", hint="(20-30 chars, enter=auto)")
            currency = _prompt("currency", default="USDX")
            model = _prompt("model", hint="ACCOUNT | UTXO", default="ACCOUNT").upper()
            input_units = _measure_units(user_id, wallet_id, currency, model)
            started_at = time.perf_counter()
            result = ledger.create_wallet(user_id, wallet_id=wallet_id, currency=currency, model=model)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if _is_domain_error_result(result):
                _print_result_box("ERROR", "create-wallet", str(result))
                _apply_result_to_session(
                    session, action="create-wallet", result=result,
                    revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            _print_data_box("Wallet creada", result if isinstance(result, dict) else {"resultado": result}, rev)
            if isinstance(result, dict) and result.get("auth_token"):
                _print_token_notice(result["auth_token"])
            _apply_result_to_session(
                session, action="create-wallet", result=result,
                revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "3":
            _section_header("MINT TOKENS")
            wallet_id = _prompt("wallet_id")
            amount = _prompt("amount")
            reference = _prompt("reference", default="MINT")
            input_units = _measure_units(wallet_id, amount, reference)
            amount_error = _validate_numeric(amount, "amount")
            if amount_error:
                _apply_result_to_session(
                    session, action="mint", result=amount_error,
                    revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units,
                )
                continue
            started_at = time.perf_counter()
            result = ledger.mint(wallet_id, amount, reference=reference)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            _print_data_box("Mint ejecutado", result if isinstance(result, dict) else {"resultado": result}, rev)
            _apply_result_to_session(
                session, action="mint", result=result,
                revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "4":
            _section_header("TRANSFERENCIA")
            from_wallet = _prompt("from_wallet")
            to_wallet = _prompt("to_wallet")
            amount = _prompt("amount")
            fee = _prompt("fee", default="0")
            sender_token = _resolve_sender_token(session, _prompt(_sender_token_prompt(), hint="(requerido)"))
            expected_nonce_raw = _prompt("expected_nonce", hint="(opcional)")
            expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
            input_units = _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
            amount_error = _validate_numeric(amount, "amount")
            fee_error = _validate_numeric(fee, "fee")
            for err in (nonce_error, amount_error, fee_error):
                if err:
                    _apply_result_to_session(
                        session, action="transfer", result=err,
                        revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units,
                    )
                    break
            else:
                started_at = time.perf_counter()
                result = ledger.transfer(
                    from_wallet, to_wallet, amount,
                    fee=fee, sender_token=sender_token, expected_nonce=expected_nonce,
                )
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                if _is_domain_error_result(result):
                    _apply_result_to_session(
                        session, action="transfer", result=result,
                        revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
                    )
                    continue
                persist_started = time.perf_counter()
                rev = _persist(store, ledger)
                elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
                _print_data_box("Transferencia ejecutada", result if isinstance(result, dict) else {"resultado": result}, rev)
                _apply_result_to_session(
                    session, action="transfer", result=result,
                    revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
                )
                continue
            continue

        elif option == "5":
            _section_header("LISTAR WALLETS")
            user_id = _prompt("user_id", hint="(opcional, filtrar por usuario)")
            input_units = _measure_units(user_id)
            started_at = time.perf_counter()
            result = ledger.list_wallets(user_id=user_id)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            _print_data_box(f"Wallets ({len(result)} encontradas)", result)
            _apply_result_to_session(
                session, action="list-wallets", result=result,
                revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "6":
            _section_header("LISTAR UTXOS")
            wallet_id = _prompt("wallet_id", hint="(opcional)")
            input_units = _measure_units(wallet_id)
            started_at = time.perf_counter()
            result = ledger.list_utxos(wallet_id=wallet_id)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            _print_data_box(f"UTXOs ({len(result)} encontrados)", result)
            _apply_result_to_session(
                session, action="list-utxos", result=result,
                revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "7":
            _section_header("VERIFICAR INTEGRIDAD")
            input_units = _measure_units("verify-integrity")
            started_at = time.perf_counter()
            result = ledger.verify_transfer_integrity()
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            _print_data_box("Resultado de integridad", result)
            _apply_result_to_session(
                session, action="verify-integrity", result=result,
                revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "8":
            _section_header("SNAPSHOT DEL LEDGER")
            input_units = _measure_units("snapshot")
            started_at = time.perf_counter()
            result = ledger.state_snapshot()
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            summary = {
                "users": len(result.get("users", [])),
                "wallets": len(result.get("wallets", [])),
                "policies": len(result.get("policies", [])),
                "risk_profiles": len(result.get("risk_profiles", [])),
                "transfers": len(result.get("transfers", [])),
                "alerts": len(result.get("alerts", [])),
                "utxos": len(result.get("utxos", [])),
            }
            _print_data_box("Estado del Ledger", summary)
            _apply_result_to_session(
                session, action="snapshot", result=result,
                revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "9":
            _section_header("REFRESH TOKEN")
            user_id = _prompt("user_id")
            wallet_id = _prompt("wallet_id")
            current_token = _prompt("current_token", hint="(opcional)")
            input_units = _measure_units(user_id, wallet_id, current_token)
            started_at = time.perf_counter()
            result = ledger.refresh_wallet_token(user_id, wallet_id, current_token=current_token)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if _is_domain_error_result(result):
                _print_result_box("ERROR", "refresh-token", str(result))
                _apply_result_to_session(
                    session, action="refresh-token", result=result,
                    revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            _print_data_box("Token renovado", result if isinstance(result, dict) else {"resultado": result}, rev)
            if isinstance(result, dict) and result.get("new_token"):
                _print_token_notice(result["new_token"])
            _apply_result_to_session(
                session, action="refresh-token", result=result,
                revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "10":
            started_at = time.perf_counter()
            result, is_error, input_units = _run_transfer_wizard(ledger, session)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            if is_error:
                _apply_result_to_session(
                    session, action="transfer-wizard", result=result,
                    revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
                )
                continue
            persist_started = time.perf_counter()
            rev = _persist(store, ledger)
            elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
            _print_data_box("Transferencia ejecutada", result if isinstance(result, dict) else {"resultado": result}, rev)
            _apply_result_to_session(
                session, action="transfer-wizard", result=result,
                revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
            )

        elif option == "11":
            _print_dashboard(session)

        elif option == "0":
            print()
            print(_box_top())
            print(_box_line(_cyan("  Sesion finalizada. Hasta pronto."), "center"))
            print(_box_bot())
            print()
            break

        else:
            _print_result_box("ERROR", "invalid-option", f"Opcion '{option}' no reconocida.")
            _apply_result_to_session(
                session, action="invalid-option", result=f"Invalid option: {option}",
                revision_id=None, is_error=True, elapsed_ms=0.0, input_units=_measure_units(option),
            )


if __name__ == "__main__":
    main()
