#!/usr/bin/env python3
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

def _print_banner() -> None:
    btc = [
        "       ▄▄████▄▄       ",
        "     ▄██▀▀▀▀▀▀██▄     ",
        "    ██▀  ▄██▄  ▀██    ",
        "   ██   ██  ██▌  ██   ",
        "   ██   ▀██▄▄▄  ▄██   ",
        "   ██    ▄▄▄██▌ ▀██   ",
        "   ██   ██▌ ██   ██   ",
        "    ██▄  ▀██▀  ▄██    ",
        "     ▀██▄▄▄▄▄▄██▀     ",
        "       ▀▀████▀▀       ",
    ]
    title = [
        "",
        " ██████╗██╗  ██╗ █████╗ ██╗███╗  ██╗███████╗",
        "██╔════╝██║  ██║██╔══██╗██║████╗ ██║██╔════╝",
        "██║     ███████║███████║██║██╔██╗██║███████╗ ",
        "██║     ██╔══██║██╔══██║██║██║╚████║╚════██║ ",
        "╚██████╗██║  ██║██║  ██║██║██║ ╚███║███████║ ",
        " ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚══╝╚══════╝ ",
        "",
        " ₿  B L O C K C H A I N   W A L L E T   S Y S T E M",
        " ── Multiuser Terminal v2.5 ──",
    ]

    max_lines = max(len(btc), len(title))
    for i in range(max_lines):
        left = btc[i] if i < len(btc) else " " * 22
        right = title[i] if i < len(title) else ""
        print(f"  {_yellow(left)}  {_cyan(right)}")

    print()
    from config.settings import get_settings
    _settings = get_settings()
    _backend = _settings.persistence_backend.upper()
    if _backend == "POSTGRES":
        _db_name = _settings.pg_dsn.rsplit("/", 1)[-1] if "/" in _settings.pg_dsn else "?"
        backend_label = _green(f"PostgreSQL ({_db_name})")
    else:
        backend_label = _yellow("JSON (local files)")
    print(f"  {_dim('Backend:')} {backend_label}    {_dim('Models:')} UTXO & Account-based")
    print(_dim("  Ingresa el numero de opcion y presiona Enter. Escribe 0 para salir."))
    print()


# ── Menu ─────────────────────────────────────────────────

ADMIN_MENU = [
    ("USUARIOS & WALLETS", [
        ("1", "create-user", "Registrar nuevo usuario en el ledger"),
        ("2", "create-wallet", "Crear wallet UTXO o ACCOUNT"),
        ("9", "refresh-token", "Renovar token de autenticacion de wallet"),
        ("12", "list-users", "Listar usuarios registrados"),
        ("13", "balance", "Consultar balance de una wallet"),
    ]),
    ("TRANSACCIONES", [
        ("3", "mint", "Emitir tokens a una wallet"),
        ("4", "transfer", "Transferir fondos entre wallets"),
        ("10", "transfer-wizard", "Asistente interactivo de transferencia"),
    ]),
    ("POLITICAS & RIESGO", [
        ("14", "set-policy", "Configurar politica de transferencia"),
        ("15", "get-policy", "Ver politica de un usuario"),
        ("16", "list-policies", "Listar todas las politicas"),
        ("17", "set-risk-profile", "Asignar perfil de riesgo"),
        ("18", "get-risk-profile", "Ver perfil de riesgo"),
        ("19", "list-risk-profiles", "Listar perfiles de riesgo"),
        ("20", "list-alerts", "Ver alertas generadas"),
    ]),
    ("CONSULTAS", [
        ("5", "list-wallets", "Listar wallets registradas"),
        ("6", "list-utxos", "Listar UTXOs de una wallet"),
        ("7", "verify-integrity", "Verificar integridad nonce + hash-chain"),
        ("8", "snapshot", "Exportar estado completo del ledger"),
        ("21", "list-revisions", "Historial de revisiones del ledger"),
    ]),
    ("EXCHANGE", [
        ("23", "set-exchange-rate", "Configurar tasa de conversion"),
        ("24", "list-exchange-rates", "Ver tasas de conversion"),
    ]),
    ("SISTEMA", [
        ("22", "generate-admin-token", "Generar token de invitacion ADMIN"),
        ("11", "dashboard", "Metricas de sesion y rendimiento"),
        ("0", "exit", "Salir del terminal"),
    ]),
]

OPERATOR_MENU = [
    ("WALLETS", [
        ("2", "create-wallet", "Crear wallet UTXO o ACCOUNT"),
        ("9", "refresh-token", "Renovar token de wallet"),
        ("13", "balance", "Consultar balance"),
    ]),
    ("TRANSACCIONES", [
        ("3", "mint", "Emitir tokens"),
        ("4", "transfer", "Transferir fondos"),
        ("10", "transfer-wizard", "Asistente de transferencia"),
    ]),
    ("EXCHANGE", [
        ("24", "list-exchange-rates", "Ver tasas de conversion"),
    ]),
    ("CONSULTAS", [
        ("5", "list-wallets", "Listar mis wallets"),
        ("6", "list-utxos", "Listar mis UTXOs"),
        ("7", "verify-integrity", "Verificar integridad"),
    ]),
    ("SISTEMA", [
        ("11", "dashboard", "Metricas de sesion"),
        ("0", "exit", "Salir"),
    ]),
]

VIEWER_MENU = [
    ("WALLETS", [
        ("2", "create-wallet", "Crear wallet UTXO o ACCOUNT"),
        ("9", "refresh-token", "Renovar token de wallet"),
        ("13", "balance", "Consultar balance"),
    ]),
    ("TRANSACCIONES", [
        ("4", "transfer", "Transferir fondos"),
        ("10", "transfer-wizard", "Asistente de transferencia"),
    ]),
    ("EXCHANGE", [
        ("24", "list-exchange-rates", "Ver tasas de conversion"),
    ]),
    ("CONSULTAS", [
        ("5", "list-wallets", "Listar mis wallets"),
        ("6", "list-utxos", "Listar mis UTXOs"),
        ("7", "verify-integrity", "Verificar integridad"),
    ]),
    ("SISTEMA", [
        ("11", "dashboard", "Metricas de sesion"),
        ("0", "exit", "Salir"),
    ]),
]

MENU_SECTIONS = ADMIN_MENU  # default fallback


def _get_menu_for_roles(roles: list[str]) -> list:
    if "ADMIN" in roles:
        return ADMIN_MENU
    if "OPERATOR" in roles:
        return OPERATOR_MENU
    if "VIEWER" in roles:
        return VIEWER_MENU
    return VIEWER_MENU


def _print_menu(menu: list | None = None) -> None:
    sections = menu or MENU_SECTIONS
    print()
    print(_box_top())
    print(_box_line(_bold(_cyan("  MENU PRINCIPAL")), "center"))
    print(_box_mid())
    for section_idx, (section_name, items) in enumerate(sections):
        print(_box_line(f"  {_dim('──')} {_bold(section_name)} {_dim('─' * (W - len(section_name) - 8))}"))
        for num, name, desc in items:
            num_styled = _yellow(f"[{num:>2}]")
            name_styled = _bold(name)
            print(_box_line(f"   {num_styled} {name_styled:<24} {_dim(desc)}"))
        if section_idx < len(sections) - 1:
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
            max_val = W - 22
            if len(val_str) > max_val:
                val_str = val_str[:max_val - 3] + "..."
            print(_box_line(f"  {_dim(key + ':'):<22} {_bold(val_str)}"))
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            for i, item in enumerate(data[:20]):
                if i > 0:
                    print(_box_line(_dim("  " + "─" * (W - 4))))
                for key, val in item.items():
                    val_str = str(val)
                    max_val = W - 22
                    if len(val_str) > max_val:
                        val_str = val_str[:max_val - 3] + "..."
                    print(_box_line(f"  {_dim(key + ':'):<22} {val_str}"))
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
    print(_box_line(_dim("  Expira en 5 minutos.")))
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
    auth_user_id: str = ""
    auth_roles: list[str] = field(default_factory=list)
    jwt_token: str = ""
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

    # ── Exchange preview if cross-currency ──
    sender_w = ledger.wallets.get(from_wallet)
    receiver_w = ledger.wallets.get(to_wallet)
    if sender_w and receiver_w and sender_w.currency != receiver_w.currency:
        rate_info = ledger.get_exchange_rate(sender_w.currency, receiver_w.currency)
        if rate_info:
            from domain.exchange import convert_amount as _convert
            from domain.multiuser_wallet_ledger import normalize_amount
            conv = _convert(normalize_amount(amount), normalize_amount(rate_info["rate"]), Decimal(str(rate_info["commission_pct"])))
            print()
            print(_box_top())
            print(_box_line(_yellow("  CONVERSION DE MONEDA")))
            print(_box_mid())
            print(_box_line(f"  {_dim('Origen:')}       {amount} {sender_w.currency}"))
            print(_box_line(f"  {_dim('Tasa:')}         1 {sender_w.currency} = {rate_info['rate']} {receiver_w.currency}"))
            print(_box_line(f"  {_dim('Bruto:')}        {conv['gross_amount']} {receiver_w.currency}"))
            print(_box_line(f"  {_dim('Comision:')}     {conv['commission']} {receiver_w.currency} ({rate_info['commission_pct']}%)"))
            print(_box_line(f"  {_dim('Destino:')}      {conv['net_amount']} {receiver_w.currency}"))
            print(_box_bot())

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

def _auth_flow(store_file) -> SessionState:
    """Login or register flow at terminal startup. Returns authenticated SessionState."""
    from config.settings import get_settings

    session = SessionState()
    store, ledger = _load(store_file)
    settings = get_settings()
    jwt_secret = settings.jwt_secret
    jwt_ttl = settings.jwt_ttl_seconds

    if not jwt_secret:
        print(_red("  Error critico: JWT_SECRET no disponible."))
        raise SystemExit(1)

    # ── 1. Bootstrap: ledger vacio → crear primer ADMIN ──────────
    if ledger.is_empty():
        print()
        print(_box_top())
        print(_box_line(_yellow("  No hay usuarios registrados. Creando cuenta ADMIN inicial.")))
        print(_box_bot())
        print()
        user_id = _prompt("user_id", hint="(sera el administrador)")
        display_name = _prompt("display_name")
        password = _prompt("password", hint="(min 4 caracteres)")
        if not user_id or not display_name or len(password) < 4:
            print(_red("  Datos invalidos. Reinicia el terminal."))
            raise SystemExit(1)
        ledger.create_user(user_id, display_name, password=password)
        ledger.assign_role(user_id, "ADMIN")
        store.save_ledger(ledger)
        _print_result_box("SUCCESS", "bootstrap", f"Usuario ADMIN '{user_id}' creado. Ahora inicia sesion.")

    # ── 2. Ledger con usuarios → elegir Login o Registro ─────────
    else:
        print()
        print(_box_top())
        print(_box_line(_cyan("  BIENVENIDO AL SISTEMA")))
        print(_box_mid())
        print(_box_line(f"  {_yellow('[L]')} Iniciar sesion"))
        print(_box_line(f"  {_yellow('[R]')} Crear cuenta"))
        print(_box_bot())
        print()
        choice = _prompt("Opcion", hint="L / R").upper()

        # ── 3. Registro de nueva cuenta ──────────────────────────
        if choice == "R":
            print()
            print(_box_top())
            print(_box_line(_cyan("  SELECCIONAR ROL")))
            print(_box_mid())
            print(_box_line(f"  {_yellow('[1]')} ADMIN      {_dim('(requiere token de invitacion)')}"))
            print(_box_line(f"  {_yellow('[2]')} OPERATOR   {_dim('(registro libre)')}"))
            print(_box_line(f"  {_yellow('[3]')} VIEWER     {_dim('(registro libre)')}"))
            print(_box_bot())
            print()
            role_choice = _prompt("Rol", hint="1 / 2 / 3")

            if role_choice == "1":
                # ── ADMIN con invitation token ───────────────────
                invitation_token = _prompt("invitation_token", hint="(proporcionado por un ADMIN)")
                user_id = _prompt("user_id")
                display_name = _prompt("display_name")
                password = _prompt("password", hint="(min 4 caracteres)")
                if not user_id or not display_name or len(password) < 4 or not invitation_token:
                    print(_red("  Datos invalidos. Reinicia el terminal."))
                    raise SystemExit(1)
                store, ledger = _load(store_file)
                result = ledger.create_user(
                    user_id, display_name,
                    password=password, role="ADMIN",
                    invitation_token=invitation_token,
                )
                if isinstance(result, str) and result.startswith("Error"):
                    _print_result_box("ERROR", "register", result)
                    raise SystemExit(1)
                store.save_ledger(ledger)
                _print_result_box("SUCCESS", "register", f"Usuario ADMIN '{user_id}' creado. Ahora inicia sesion.")

            elif role_choice in ("2", "3"):
                selected_role = "OPERATOR" if role_choice == "2" else "VIEWER"
                user_id = _prompt("user_id")
                display_name = _prompt("display_name")
                password = _prompt("password", hint="(min 4 caracteres)")
                if not user_id or not display_name or len(password) < 4:
                    print(_red("  Datos invalidos. Reinicia el terminal."))
                    raise SystemExit(1)
                store, ledger = _load(store_file)
                result = ledger.create_user(
                    user_id, display_name,
                    password=password, role=selected_role,
                )
                if isinstance(result, str) and result.startswith("Error"):
                    _print_result_box("ERROR", "register", result)
                    raise SystemExit(1)
                store.save_ledger(ledger)
                # Mostrar activation_code en caja prominente
                activation_code = result.get("activation_code", "") if isinstance(result, dict) else ""
                print()
                print(_box_top())
                print(_box_line(_yellow("  CUENTA CREADA — CODIGO DE ACTIVACION")))
                print(_box_mid())
                print(_box_line(f"  Usuario:    {_bold(user_id)}"))
                print(_box_line(f"  Rol:        {_bold(selected_role)}"))
                print(_box_line(f"  Codigo:     {_green(_bold(str(activation_code)))}"))
                print(_box_mid())
                print(_box_line(_dim("  Guarda este codigo. Lo necesitaras para activar tu cuenta.")))
                print(_box_bot())

            else:
                print(_red("  Opcion de rol invalida. Reinicia el terminal."))
                raise SystemExit(1)

        elif choice != "L":
            print(_red("  Opcion invalida. Reinicia el terminal."))
            raise SystemExit(1)

    # ── 4. Login (siempre, despues de bootstrap o registro) ──────
    print()
    print(_box_top())
    print(_box_line(_cyan("  INICIAR SESION")))
    print(_box_bot())
    print()

    for attempt in range(3):
        user_id = _prompt("user_id")
        password = _prompt("password")

        # Verificar si la cuenta necesita activacion
        activation_code = None
        if not ledger.is_account_activated(user_id):
            activation_code = _prompt("activation_code", hint="(cuenta pendiente de activacion)")

        store, ledger = _load(store_file)
        result = ledger.login(
            user_id, password, jwt_secret, jwt_ttl,
            activation_code=activation_code,
        )
        if isinstance(result, dict):
            if activation_code:
                store.save_ledger(ledger)
            session.auth_user_id = result["user_id"]
            session.auth_roles = result["roles"]
            session.jwt_token = result["access_token"]
            print()
            print(_box_top())
            print(_box_line(_green(f"  Bienvenido, {_bold(user_id)}")))
            print(_box_mid())
            print(_box_line(f"  {_dim('Roles:')}  {_bold(', '.join(result['roles']) or 'sin roles')}"))
            print(_box_bot())
            return session

        _print_result_box("ERROR", "login", str(result))
        if attempt < 2:
            print(_dim(f"  Intentos restantes: {2 - attempt}"))

    print(_red("  Maximo de intentos alcanzado. Saliendo."))
    raise SystemExit(1)


# ── Command Context & helpers ────────────────────────────

@dataclass
class CommandContext:
    session: SessionState
    store: object  # WalletLedgerRepository
    ledger: object  # MultiUserWalletLedger
    store_file: Path


class _SkipCommand(Exception):
    """Raised inside a handler to signal ``continue`` in the main loop."""


def _execute_and_track(
    ctx: CommandContext,
    *,
    action: str,
    result,
    revision_id: str | None,
    is_error: bool,
    elapsed_ms: float = 0.0,
    input_units: int = 0,
) -> None:
    _apply_result_to_session(
        ctx.session,
        action=action,
        result=result,
        revision_id=revision_id,
        is_error=is_error,
        elapsed_ms=elapsed_ms,
        input_units=input_units,
    )


# ── Command handlers ────────────────────────────────────

def _cmd_create_user(ctx: CommandContext) -> None:
    _section_header("CREAR USUARIO")
    user_id = _prompt("user_id")
    display_name = _prompt("display_name")
    password = _prompt("password", hint="(min 4 caracteres, vacio=sin password)")
    role = _prompt("role", hint="ADMIN / OPERATOR / VIEWER", default="VIEWER").upper()
    if role not in ("ADMIN", "OPERATOR", "VIEWER"):
        _print_result_box("ERROR", "create-user", f"Rol invalido: {role}")
        raise _SkipCommand
    invitation_token = ""
    if role == "ADMIN":
        invitation_token = _prompt("invitation_token", hint="(requerido para ADMIN)")
    input_units = _measure_units(user_id, display_name, role)
    started_at = time.perf_counter()
    result = ctx.ledger.create_user(user_id, display_name, password=password, role=role, invitation_token=invitation_token)
    if isinstance(result, str) and result.startswith("Error"):
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        _print_result_box("ERROR", "create-user", result)
        _execute_and_track(
            ctx, action="create-user", result=result,
            revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
        )
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Usuario creado", result if isinstance(result, dict) else {"resultado": result}, rev)
    if isinstance(result, dict) and result.get("activation_code"):
        print()
        print(_box_top())
        print(_box_line(_yellow("  CODIGO DE ACTIVACION")))
        print(_box_mid())
        print(_box_line(f"  Codigo: {_bold(result['activation_code'])}"))
        print(_box_line(_dim("  El usuario necesita este codigo en su primer login.")))
        print(_box_bot())
    _execute_and_track(
        ctx, action="create-user", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_create_wallet(ctx: CommandContext) -> None:
    _section_header("CREAR WALLET")
    if "ADMIN" in ctx.session.auth_roles:
        user_id = _prompt("user_id")
    else:
        user_id = ctx.session.auth_user_id
        print(_dim(f"  Usuario: {user_id}"))
    wallet_id = _prompt("wallet_id", hint="(20-30 chars, enter=auto)")
    currency = _prompt("currency", default="USDX")
    model = _prompt("model", hint="ACCOUNT | UTXO", default="ACCOUNT").upper()
    input_units = _measure_units(user_id, wallet_id, currency, model)
    started_at = time.perf_counter()
    result = ctx.ledger.create_wallet(user_id, wallet_id=wallet_id, currency=currency, model=model)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if _is_domain_error_result(result):
        _print_result_box("ERROR", "create-wallet", str(result))
        _execute_and_track(
            ctx, action="create-wallet", result=result,
            revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
        )
        raise _SkipCommand
    persist_started = time.perf_counter()
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
    _print_data_box("Wallet creada", result if isinstance(result, dict) else {"resultado": result}, rev)
    if isinstance(result, dict) and result.get("auth_token"):
        _print_token_notice(result["auth_token"])
    _execute_and_track(
        ctx, action="create-wallet", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_mint(ctx: CommandContext) -> None:
    _section_header("MINT TOKENS")
    wallet_id = _prompt("wallet_id")
    amount = _prompt("amount")
    reference = _prompt("reference", default="MINT")
    input_units = _measure_units(wallet_id, amount, reference)
    amount_error = _validate_numeric(amount, "amount")
    if amount_error:
        _execute_and_track(
            ctx, action="mint", result=amount_error,
            revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units,
        )
        raise _SkipCommand
    started_at = time.perf_counter()
    result = ctx.ledger.mint(wallet_id, amount, reference=reference)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    persist_started = time.perf_counter()
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
    _print_data_box("Mint ejecutado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(
        ctx, action="mint", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_transfer(ctx: CommandContext) -> None:
    _section_header("TRANSFERENCIA")
    from_wallet = _prompt("from_wallet")
    to_wallet = _prompt("to_wallet")
    amount = _prompt("amount")
    fee = _prompt("fee", default="0")
    sender_token = _resolve_sender_token(ctx.session, _prompt(_sender_token_prompt(), hint="(requerido)"))
    expected_nonce_raw = _prompt("expected_nonce", hint="(opcional)")
    expected_nonce, nonce_error = _parse_optional_int(expected_nonce_raw, "expected_nonce")
    input_units = _measure_units(from_wallet, to_wallet, amount, fee, sender_token, expected_nonce)
    amount_error = _validate_numeric(amount, "amount")
    fee_error = _validate_numeric(fee, "fee")
    for err in (nonce_error, amount_error, fee_error):
        if err:
            _execute_and_track(
                ctx, action="transfer", result=err,
                revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units,
            )
            break
    else:
        started_at = time.perf_counter()
        result = ctx.ledger.transfer(
            from_wallet, to_wallet, amount,
            fee=fee, sender_token=sender_token, expected_nonce=expected_nonce,
        )
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if _is_domain_error_result(result):
            _execute_and_track(
                ctx, action="transfer", result=result,
                revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
            )
            return
        persist_started = time.perf_counter()
        rev = _persist(ctx.store, ctx.ledger)
        elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
        _print_data_box("Transferencia ejecutada", result if isinstance(result, dict) else {"resultado": result}, rev)
        _execute_and_track(
            ctx, action="transfer", result=result,
            revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
        )


def _cmd_list_wallets(ctx: CommandContext) -> None:
    _section_header("LISTAR WALLETS")
    is_admin = "ADMIN" in ctx.session.auth_roles
    if is_admin:
        user_id = _prompt("user_id", hint="(opcional, filtrar por usuario)")
    else:
        user_id = ctx.session.auth_user_id
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.list_wallets(user_id=user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if not result and not is_admin:
        _print_result_box("ERROR", "list-wallets", "No tienes wallets creadas. Usa la opcion [2] para crear una.")
    else:
        _print_data_box(f"Wallets ({len(result)} encontradas)", result)
    _execute_and_track(
        ctx, action="list-wallets", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_utxos(ctx: CommandContext) -> None:
    _section_header("LISTAR UTXOS")
    is_admin = "ADMIN" in ctx.session.auth_roles
    if is_admin:
        wallet_id = _prompt("wallet_id", hint="(opcional)")
    else:
        my_wallets = ctx.ledger.list_wallets(user_id=ctx.session.auth_user_id)
        if not my_wallets:
            _print_result_box("ERROR", "list-utxos", "No tienes wallets creadas.")
            raise _SkipCommand
        if len(my_wallets) == 1:
            wallet_id = my_wallets[0]["wallet_id"]
        else:
            print()
            print(_box_top())
            print(_box_line(_cyan("  Tus wallets:")))
            print(_box_mid())
            for i, w in enumerate(my_wallets, 1):
                print(_box_line(f"  {_yellow(f'[{i}]')} {w['wallet_id']}  {_dim(w['model'])}"))
            print(_box_bot())
            sel = _prompt("Selecciona", hint=f"1-{len(my_wallets)}")
            try:
                wallet_id = my_wallets[int(sel) - 1]["wallet_id"]
            except (ValueError, IndexError):
                _print_result_box("ERROR", "list-utxos", "Seleccion invalida.")
                raise _SkipCommand
    input_units = _measure_units(wallet_id)
    started_at = time.perf_counter()
    result = ctx.ledger.list_utxos(wallet_id=wallet_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"UTXOs ({len(result)} encontrados)", result)
    _execute_and_track(
        ctx, action="list-utxos", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_verify_integrity(ctx: CommandContext) -> None:
    _section_header("VERIFICAR INTEGRIDAD")
    input_units = _measure_units("verify-integrity")
    started_at = time.perf_counter()
    result = ctx.ledger.verify_transfer_integrity()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Resultado de integridad", result)
    _execute_and_track(
        ctx, action="verify-integrity", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_snapshot(ctx: CommandContext) -> None:
    _section_header("SNAPSHOT DEL LEDGER")
    input_units = _measure_units("snapshot")
    started_at = time.perf_counter()
    result = ctx.ledger.state_snapshot()
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
    _execute_and_track(
        ctx, action="snapshot", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_refresh_token(ctx: CommandContext) -> None:
    _section_header("REFRESH TOKEN")
    is_admin = "ADMIN" in ctx.session.auth_roles
    if is_admin:
        user_id = _prompt("user_id")
        wallet_id = _prompt("wallet_id")
    else:
        user_id = ctx.session.auth_user_id
        my_wallets = ctx.ledger.list_wallets(user_id=user_id)
        if not my_wallets:
            _print_result_box("ERROR", "refresh-token", "No tienes wallets creadas.")
            raise _SkipCommand
        if len(my_wallets) == 1:
            wallet_id = my_wallets[0]["wallet_id"]
            print(_dim(f"  Wallet: {wallet_id}"))
        else:
            print()
            print(_box_top())
            print(_box_line(_cyan("  Tus wallets:")))
            print(_box_mid())
            for i, w in enumerate(my_wallets, 1):
                print(_box_line(f"  {_yellow(f'[{i}]')} {w['wallet_id']}  {_dim(w['model'])}"))
            print(_box_bot())
            sel = _prompt("Selecciona", hint=f"1-{len(my_wallets)}")
            try:
                wallet_id = my_wallets[int(sel) - 1]["wallet_id"]
            except (ValueError, IndexError):
                _print_result_box("ERROR", "refresh-token", "Seleccion invalida.")
                raise _SkipCommand
    current_token = _prompt("current_token", hint="(opcional)")
    input_units = _measure_units(user_id, wallet_id, current_token)
    started_at = time.perf_counter()
    result = ctx.ledger.refresh_wallet_token(user_id, wallet_id, current_token=current_token)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if _is_domain_error_result(result):
        _print_result_box("ERROR", "refresh-token", str(result))
        _execute_and_track(
            ctx, action="refresh-token", result=result,
            revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
        )
        raise _SkipCommand
    persist_started = time.perf_counter()
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
    _print_data_box("Token renovado", result if isinstance(result, dict) else {"resultado": result}, rev)
    if isinstance(result, dict) and result.get("new_token"):
        _print_token_notice(result["new_token"])
    _execute_and_track(
        ctx, action="refresh-token", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_transfer_wizard(ctx: CommandContext) -> None:
    started_at = time.perf_counter()
    result, is_error, input_units = _run_transfer_wizard(ctx.ledger, ctx.session)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if is_error:
        _execute_and_track(
            ctx, action="transfer-wizard", result=result,
            revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
        )
        raise _SkipCommand
    persist_started = time.perf_counter()
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms += (time.perf_counter() - persist_started) * 1000.0
    _print_data_box("Transferencia ejecutada", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(
        ctx, action="transfer-wizard", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_dashboard(ctx: CommandContext) -> None:
    _print_dashboard(ctx.session)


def _cmd_list_users(ctx: CommandContext) -> None:
    _section_header("LISTAR USUARIOS")
    input_units = _measure_units("list-users")
    started_at = time.perf_counter()
    result = ctx.ledger.list_users()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Usuarios ({len(result)} registrados)", result)
    _execute_and_track(
        ctx, action="list-users", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_balance(ctx: CommandContext) -> None:
    _section_header("CONSULTAR BALANCE")
    wallet_id = _prompt("wallet_id", hint="(vacio = mostrar todas tus wallets)")
    if not wallet_id:
        user_wallets = ctx.ledger.list_wallets(user_id=ctx.session.auth_user_id)
        if not user_wallets:
            _print_result_box("ERROR", "balance", "No tienes wallets creadas.")
            raise _SkipCommand
        if len(user_wallets) == 1:
            wallet_id = user_wallets[0]["wallet_id"]
        else:
            print()
            print(_box_top())
            print(_box_line(_cyan("  Tus wallets:")))
            print(_box_mid())
            for i, w in enumerate(user_wallets, 1):
                print(_box_line(f"  {_yellow(f'[{i}]')} {w['wallet_id']}  {_dim(w['model'])}  {_bold(w['balance'])} {w['currency']}"))
            print(_box_bot())
            sel = _prompt("Selecciona", hint=f"1-{len(user_wallets)}")
            try:
                idx = int(sel) - 1
                wallet_id = user_wallets[idx]["wallet_id"]
            except (ValueError, IndexError):
                _print_result_box("ERROR", "balance", "Seleccion invalida.")
                raise _SkipCommand
    if wallet_id and "ADMIN" not in ctx.session.auth_roles:
        my_wallet_ids = [w["wallet_id"] for w in ctx.ledger.list_wallets(user_id=ctx.session.auth_user_id)]
        if wallet_id not in my_wallet_ids:
            _print_result_box("ERROR", "balance", "No tienes acceso a esa wallet.")
            raise _SkipCommand
    input_units = _measure_units(wallet_id)
    started_at = time.perf_counter()
    balance = ctx.ledger.get_wallet_balance(wallet_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    result = {"wallet_id": wallet_id, "balance": str(balance)}
    _print_data_box("Balance", result)
    _execute_and_track(
        ctx, action="balance", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_set_policy(ctx: CommandContext) -> None:
    _section_header("CONFIGURAR POLITICA")
    user_id = _prompt("user_id")
    can_transfer = _prompt("can_transfer", hint="true/false", default="true").lower() in ("true", "1", "yes")
    daily_limit = _prompt("daily_limit", hint="(opcional, vacio=sin limite)")
    input_units = _measure_units(user_id, can_transfer, daily_limit)
    started_at = time.perf_counter()
    dl = Decimal(daily_limit) if daily_limit else None
    result = ctx.ledger.set_user_policy(user_id, can_transfer=can_transfer, daily_limit=dl)
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Politica configurada", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(
        ctx, action="set-policy", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_get_policy(ctx: CommandContext) -> None:
    _section_header("VER POLITICA")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.get_user_policy(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Politica de usuario", result)
    _execute_and_track(
        ctx, action="get-policy", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_policies(ctx: CommandContext) -> None:
    _section_header("LISTAR POLITICAS")
    input_units = _measure_units("list-policies")
    started_at = time.perf_counter()
    result = ctx.ledger.list_user_policies()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Politicas ({len(result)} registradas)", result)
    _execute_and_track(
        ctx, action="list-policies", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_set_risk_profile(ctx: CommandContext) -> None:
    _section_header("ASIGNAR PERFIL DE RIESGO")
    user_id = _prompt("user_id")
    profile_name = _prompt("profile_name", hint="STANDARD/LOW/MEDIUM/HIGH/RESTRICTED", default="STANDARD").upper()
    daily_limit = _prompt("daily_limit", hint="(opcional)")
    transfer_threshold = _prompt("transfer_alert_threshold", hint="(opcional)")
    daily_threshold = _prompt("daily_alert_threshold", hint="(opcional)")
    input_units = _measure_units(user_id, profile_name, daily_limit, transfer_threshold, daily_threshold)
    started_at = time.perf_counter()
    dl = Decimal(daily_limit) if daily_limit else None
    tt = Decimal(transfer_threshold) if transfer_threshold else None
    dt = Decimal(daily_threshold) if daily_threshold else None
    result = ctx.ledger.set_user_risk_profile(user_id, profile_name=profile_name, daily_limit=dl, transfer_alert_threshold=tt, daily_alert_threshold=dt)
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Perfil de riesgo asignado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(
        ctx, action="set-risk-profile", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_get_risk_profile(ctx: CommandContext) -> None:
    _section_header("VER PERFIL DE RIESGO")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.get_user_risk_profile(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Perfil de riesgo", result)
    _execute_and_track(
        ctx, action="get-risk-profile", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_risk_profiles(ctx: CommandContext) -> None:
    _section_header("LISTAR PERFILES DE RIESGO")
    input_units = _measure_units("list-risk-profiles")
    started_at = time.perf_counter()
    result = ctx.ledger.list_user_risk_profiles()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Perfiles de riesgo ({len(result)})", result)
    _execute_and_track(
        ctx, action="list-risk-profiles", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_alerts(ctx: CommandContext) -> None:
    _section_header("LISTAR ALERTAS")
    user_id = _prompt("user_id", hint="(opcional)")
    severity = _prompt("severity", hint="LOW/MEDIUM/HIGH (opcional)")
    input_units = _measure_units(user_id, severity)
    started_at = time.perf_counter()
    result = ctx.ledger.list_alerts(user_id=user_id, severity=severity)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Alertas ({len(result)} encontradas)", result)
    _execute_and_track(
        ctx, action="list-alerts", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_revisions(ctx: CommandContext) -> None:
    _section_header("HISTORIAL DE REVISIONES")
    limit_raw = _prompt("limit", default="10")
    limit = int(limit_raw) if limit_raw.isdigit() else 10
    input_units = _measure_units(limit)
    started_at = time.perf_counter()
    result = ctx.store.list_revisions(limit=limit)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Revisiones ({len(result)} recientes)", result)
    _execute_and_track(
        ctx, action="list-revisions", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_generate_admin_token(ctx: CommandContext) -> None:
    _section_header("GENERAR TOKEN DE INVITACION ADMIN")
    input_units = _measure_units("generate-admin-token")
    started_at = time.perf_counter()
    result = ctx.ledger.generate_admin_invitation(ctx.session.auth_user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "generate-admin-token", result)
        _execute_and_track(ctx, action="generate-admin-token", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Token de invitacion generado", result, rev)
    print()
    print(_box_top())
    print(_box_line(_yellow("  ⚡ IMPORTANTE: Comparte este token con el nuevo ADMIN")))
    print(_box_mid())
    print(_box_line(f"  Token: {_bold(result['token'])}"))
    print(_box_line(_dim("  Este token es de un solo uso.")))
    print(_box_bot())
    _execute_and_track(ctx, action="generate-admin-token", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


# ── Exchange handlers ────────────────────────────────────

def _cmd_set_exchange_rate(ctx: CommandContext) -> None:
    _section_header("CONFIGURAR TASA DE CONVERSION")
    from_currency = _prompt("from_currency", hint="ej: BTC").upper()
    to_currency = _prompt("to_currency", hint="ej: SOL").upper()
    rate = _prompt("rate", hint="ej: 150.0")
    commission_pct = _prompt("commission_pct", hint="porcentaje", default="1.0")
    input_units = _measure_units(from_currency, to_currency, rate, commission_pct)
    rate_error = _validate_numeric(rate, "rate")
    comm_error = _validate_numeric(commission_pct, "commission_pct")
    for err in (rate_error, comm_error):
        if err:
            _print_result_box("ERROR", "set-exchange-rate", err)
            _execute_and_track(
                ctx, action="set-exchange-rate", result=err,
                revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units,
            )
            raise _SkipCommand
    started_at = time.perf_counter()
    result = ctx.ledger.set_exchange_rate(from_currency, to_currency, rate, commission_pct=commission_pct)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "set-exchange-rate", result)
        _execute_and_track(
            ctx, action="set-exchange-rate", result=result,
            revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units,
        )
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    elapsed_ms += (time.perf_counter() - started_at) * 1000.0
    _print_data_box("Tasa configurada", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(
        ctx, action="set-exchange-rate", result=result,
        revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


def _cmd_list_exchange_rates(ctx: CommandContext) -> None:
    _section_header("TASAS DE CONVERSION")
    input_units = _measure_units("list-exchange-rates")
    started_at = time.perf_counter()
    result = ctx.ledger.list_exchange_rates()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if not result:
        _print_result_box("SUCCESS", "list-exchange-rates", "No hay tasas configuradas.")
    else:
        _print_data_box(f"Tasas de conversion ({len(result)})", result)
    _execute_and_track(
        ctx, action="list-exchange-rates", result=result,
        revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units,
    )


# ── Command handler registry ────────────────────────────

from typing import Callable
from domain.auth import Permission

COMMAND_HANDLERS: dict[str, tuple[Callable, str | None]] = {
    "1":  (_cmd_create_user,          Permission.CREATE_USER),
    "2":  (_cmd_create_wallet,        Permission.CREATE_WALLET),
    "3":  (_cmd_mint,                 Permission.MINT),
    "4":  (_cmd_transfer,             Permission.TRANSFER),
    "5":  (_cmd_list_wallets,         Permission.VIEW_WALLETS),
    "6":  (_cmd_list_utxos,           Permission.VIEW_WALLETS),
    "7":  (_cmd_verify_integrity,     Permission.VIEW_WALLETS),
    "8":  (_cmd_snapshot,             Permission.VIEW_WALLETS),
    "9":  (_cmd_refresh_token,        Permission.VIEW_WALLETS),
    "10": (_cmd_transfer_wizard,      Permission.TRANSFER),
    "11": (_cmd_dashboard,            None),
    "12": (_cmd_list_users,           Permission.VIEW_USERS),
    "13": (_cmd_balance,              Permission.VIEW_WALLETS),
    "14": (_cmd_set_policy,           Permission.SET_POLICY),
    "15": (_cmd_get_policy,           Permission.VIEW_POLICIES),
    "16": (_cmd_list_policies,        Permission.VIEW_POLICIES),
    "17": (_cmd_set_risk_profile,     Permission.SET_RISK_PROFILE),
    "18": (_cmd_get_risk_profile,     Permission.VIEW_RISK_PROFILES),
    "19": (_cmd_list_risk_profiles,   Permission.VIEW_RISK_PROFILES),
    "20": (_cmd_list_alerts,          Permission.VIEW_ALERTS),
    "21": (_cmd_list_revisions,       Permission.VIEW_REVISIONS),
    "22": (_cmd_generate_admin_token, None),
    "23": (_cmd_set_exchange_rate,    Permission.SET_EXCHANGE_RATE),
    "24": (_cmd_list_exchange_rates,  None),
}


# ── Main loop ────────────────────────────────────────────

def main() -> None:
    store_file = DEFAULT_STORE

    _print_banner()
    print(_dim(f"  Store: {store_file}"))

    session = _auth_flow(store_file)

    from domain.auth import has_permission

    user_menu = _get_menu_for_roles(session.auth_roles)

    while True:
        _print_pending_feedback(session)
        _print_menu(user_menu)
        print(_dim(f"  Usuario: {_bold(session.auth_user_id)} [{', '.join(session.auth_roles)}]"))

        option = input(f"\n  {_cyan('›')} {_bold('Opcion')}: ").strip()

        if option == "0":
            print()
            print(_box_top())
            print(_box_line(_cyan("  Sesion finalizada. Hasta pronto."), "center"))
            print(_box_bot())
            print()
            break

        handler_entry = COMMAND_HANDLERS.get(option)
        if not handler_entry:
            _print_result_box("ERROR", "invalid-option", f"Opcion '{option}' no reconocida.")
            _apply_result_to_session(
                session, action="invalid-option", result=f"Invalid option: {option}",
                revision_id=None, is_error=True, elapsed_ms=0.0, input_units=_measure_units(option),
            )
            continue

        handler, required_perm = handler_entry
        if required_perm and not has_permission(session.auth_roles, required_perm):
            _print_result_box("ERROR", "permiso-denegado", f"Se requiere: {required_perm}. Tus roles: {', '.join(session.auth_roles) or 'ninguno'}")
            continue

        try:
            store, ledger = _load(store_file)
        except Exception as exc:
            _print_result_box("ERROR", "startup", str(exc))
            _print_result_box(
                "ERROR",
                "migration-hint",
                "Ejecuta: PYTHONPATH=. py migrations/migrate.py",
            )
            break

        ctx = CommandContext(session=session, store=store, ledger=ledger, store_file=store_file)
        try:
            handler(ctx)
        except _SkipCommand:
            continue


if __name__ == "__main__":
    main()
