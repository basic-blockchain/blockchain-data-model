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
from scripts.terminal_ui import (
    W,
    _bold,
    _box_bot,
    _box_line,
    _box_mid,
    _box_top,
    _cyan,
    _dim,
    _green,
    _meter,
    _print_data_box,
    _print_result_box,
    _print_token_notice,
    _prompt,
    _prompt_confirm,
    _red,
    _section_header,
    _short_json,
    _yellow,
)


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
        " ── Multiuser Terminal v2.8.1 ──",
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
        ("46", "list-transfers", "Listar transferencias"),
        ("7", "verify-integrity", "Verificar integridad nonce + hash-chain"),
        ("8", "snapshot", "Exportar estado completo del ledger"),
        ("21", "list-revisions", "Historial de revisiones del ledger"),
    ]),
    ("EXCHANGE", [
        ("23", "set-exchange-rate", "Configurar tasa de conversion"),
        ("24", "list-exchange-rates", "Ver tasas de conversion"),
    ]),
    ("TESORERIA", [
        ("25", "create-treasury-wallet", "Crear wallet de tesoreria"),
        ("26", "list-treasury-wallets", "Ver wallets de tesoreria"),
        ("27", "top-up", "Recargar wallet desde tesoreria"),
    ]),
    ("PERMISOS", [
        ("28", "grant-permission", "Otorgar permiso a rol"),
        ("29", "revoke-permission", "Revocar permiso de rol"),
        ("30", "grant-user-permission", "Otorgar permiso a usuario"),
        ("31", "revoke-user-permission", "Revocar permiso de usuario"),
        ("32", "list-role-permissions", "Ver permisos de un rol"),
        ("33", "list-user-permissions", "Ver permisos de un usuario"),
        ("34", "reset-role-permissions", "Resetear permisos de un rol"),
    ]),
    ("MODERACION", [
        ("35", "freeze-wallet", "Congelar wallet"),
        ("36", "unfreeze-wallet", "Descongelar wallet"),
        ("37", "ban-user", "Banear usuario"),
        ("38", "unban-user", "Desbanear usuario"),
    ]),
    ("GESTION DE USUARIOS", [
        ("39", "update-user", "Modificar usuario (ID o nombre)"),
        ("40", "delete-user", "Eliminar usuario (soft delete)"),
        ("41", "restore-user", "Restaurar usuario eliminado"),
        ("42", "generate-temp-password", "Generar password temporal"),
        ("43", "list-audit-log", "Ver log de auditoria"),
    ]),
    ("SISTEMA", [
        ("22", "generate-admin-token", "Generar token de invitacion ADMIN"),
        ("44", "change-password", "Cambiar mi contrasena"),
        ("45", "update-profile", "Actualizar mi perfil"),
        ("11", "dashboard", "Metricas de sesion y rendimiento"),
        ("0", "exit", "Salir del terminal"),
    ]),
]

_SHARED_WALLETS = ("WALLETS", [
    ("2", "create-wallet", "Crear wallet UTXO o ACCOUNT"),
    ("9", "refresh-token", "Renovar token de wallet"),
    ("13", "balance", "Consultar balance"),
])

_VIEWER_TRANSACCIONES = ("TRANSACCIONES", [
    ("4", "transfer", "Transferir fondos"),
    ("10", "transfer-wizard", "Asistente de transferencia"),
])

_OPERATOR_TRANSACCIONES = ("TRANSACCIONES", [
    ("3", "mint", "Emitir tokens"),
    ("4", "transfer", "Transferir fondos"),
    ("10", "transfer-wizard", "Asistente de transferencia"),
])

_SHARED_EXCHANGE = ("EXCHANGE", [
    ("24", "list-exchange-rates", "Ver tasas de conversion"),
])

_SHARED_CONSULTAS = ("CONSULTAS", [
    ("5", "list-wallets", "Listar mis wallets"),
    ("6", "list-utxos", "Listar mis UTXOs"),
    ("46", "list-transfers", "Listar mis transferencias"),
    ("7", "verify-integrity", "Verificar integridad"),
])

_SHARED_SISTEMA = ("SISTEMA", [
    ("44", "change-password", "Cambiar mi contrasena"),
    ("45", "update-profile", "Actualizar mi perfil"),
    ("11", "dashboard", "Metricas de sesion"),
    ("0", "exit", "Salir"),
])


def _build_user_menu(transacciones_section: tuple) -> list:
    return [
        _SHARED_WALLETS,
        transacciones_section,
        _SHARED_EXCHANGE,
        _SHARED_CONSULTAS,
        _SHARED_SISTEMA,
    ]


OPERATOR_MENU = _build_user_menu(_OPERATOR_TRANSACCIONES)
VIEWER_MENU = _build_user_menu(_VIEWER_TRANSACCIONES)

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


def _extract_token_from_result(result) -> str | None:
    if isinstance(result, dict):
        token = result.get("auth_token")
        if isinstance(token, str) and token:
            return token
    return None


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
        ledger.ensure_treasury_user()
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

            if result.get("must_change_password"):
                print()
                print(_box_top())
                print(_box_line(_yellow("  CAMBIO DE CONTRASENA OBLIGATORIO")))
                print(_box_mid())
                print(_box_line(_dim("  Tu contrasena es temporal. Debes cambiarla ahora.")))
                print(_box_bot())
                print()
                new_pw = _prompt("nueva contrasena", hint="(min 4 caracteres)")
                if len(new_pw) < 4:
                    print(_red("  Contrasena muy corta. Reinicia el terminal."))
                    raise SystemExit(1)
                store, ledger = _load(store_file)
                change_result = ledger.change_password(user_id, password, new_pw)
                if isinstance(change_result, str) and change_result.startswith("Error"):
                    print(_red(f"  {change_result}"))
                    raise SystemExit(1)
                store.save_ledger(ledger)
                _print_result_box("SUCCESS", "change-password", "Contrasena actualizada. Continua con tu sesion.")

            return session

        if "suspendida" in str(result).lower():
            print()
            print(_box_top())
            print(_box_line(_red("  CUENTA SUSPENDIDA")))
            print(_box_mid())
            print(_box_line(f"  {_dim('Tu cuenta ha sido suspendida por un administrador.')}"))
            print(_box_line(f"  {_dim('Contacta a soporte tecnico o servicio al cliente.')}"))
            print(_box_bot())
            raise SystemExit(1)
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
    email = _prompt("email", hint="(obligatorio)")
    username = _prompt("username", hint=f"(enter={display_name})")
    first_name = _prompt("first_name", hint="(opcional)")
    last_name = _prompt("last_name", hint="(opcional)")
    invitation_token = ""
    if role == "ADMIN":
        invitation_token = _prompt("invitation_token", hint="(requerido para ADMIN)")
    input_units = _measure_units(user_id, display_name, role, email, username)
    started_at = time.perf_counter()
    result = ctx.ledger.create_user(user_id, display_name, password=password, role=role, invitation_token=invitation_token, first_name=first_name, last_name=last_name, email=email, username=username)
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


def _cmd_list_transfers(ctx: CommandContext) -> None:
    from domain.multiuser_wallet_ledger import TransferListQuery

    _section_header("LISTAR TRANSFERENCIAS")
    is_admin = "ADMIN" in ctx.session.auth_roles

    print()
    print(_box_top())
    print(_box_line(_cyan("  Filtros de busqueda")))
    print(_box_mid())
    print(_box_line(f"  {_yellow('[1]')} Por ID de transferencia"))
    print(_box_line(f"  {_yellow('[2]')} Mas recientes (limit)"))
    if is_admin:
        print(_box_line(f"  {_yellow('[3]')} Por wallet"))
        print(_box_line(f"  {_yellow('[4]')} Por usuario"))
    else:
        print(_box_line(f"  {_yellow('[3]')} Por mi wallet"))
    print(_box_bot())

    filter_choice = _prompt("Filtro", hint="1/2/3/4")

    transfer_id = ""
    wallet_id = ""
    user_id = ""
    limit = 50

    if filter_choice == "1":
        transfer_id = _prompt("transfer_id")
        if not transfer_id:
            _print_result_box("ERROR", "list-transfers", "transfer_id es requerido.")
            raise _SkipCommand
    elif filter_choice == "2":
        limit_raw = _prompt("limit", default="20")
        parsed_limit, limit_err = _parse_optional_int(limit_raw, "limit")
        if limit_err:
            _print_result_box("ERROR", "list-transfers", limit_err)
            raise _SkipCommand
        limit = parsed_limit or 20
    elif filter_choice == "3":
        if is_admin:
            wallet_id = _prompt("wallet_id")
        else:
            my_wallets = ctx.ledger.list_wallets(user_id=ctx.session.auth_user_id)
            if not my_wallets:
                _print_result_box("ERROR", "list-transfers", "No tienes wallets creadas.")
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
                    _print_result_box("ERROR", "list-transfers", "Seleccion invalida.")
                    raise _SkipCommand
    elif filter_choice == "4" and is_admin:
        user_id = _prompt("user_id")
    else:
        _print_result_box("ERROR", "list-transfers", f"Filtro '{filter_choice}' no reconocido.")
        raise _SkipCommand

    scope = ctx.ledger.build_transfer_access_scope(
        actor_user_id=ctx.session.auth_user_id,
        actor_roles=ctx.session.auth_roles,
    )
    query = TransferListQuery(
        limit=limit,
        wallet_id=wallet_id,
        user_id=user_id,
        transfer_id=transfer_id,
    )

    input_units = _measure_units(transfer_id, wallet_id, user_id, limit)
    started_at = time.perf_counter()
    result = ctx.ledger.list_transfers_scoped(query, scope)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if not result:
        _print_result_box("ERROR", "list-transfers", "No se encontraron transferencias con esos filtros.")
    else:
        _print_data_box(f"Transferencias ({len(result)} encontradas)", result)
    _execute_and_track(
        ctx, action="list-transfers", result=result,
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


# ── Treasury handlers ────────────────────────────────────

def _cmd_create_treasury_wallet(ctx: CommandContext) -> None:
    _section_header("CREAR WALLET DE TESORERIA")
    currency = _prompt("currency", default="USDX")
    model = _prompt("model", hint="ACCOUNT | UTXO", default="ACCOUNT").upper()
    input_units = _measure_units(currency, model)
    started_at = time.perf_counter()
    result = ctx.ledger.create_treasury_wallet(currency=currency, model=model)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if _is_domain_error_result(result):
        _print_result_box("ERROR", "create-treasury-wallet", str(result))
        _execute_and_track(ctx, action="create-treasury-wallet", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Wallet de tesoreria creada", result if isinstance(result, dict) else {"resultado": result}, rev)
    if isinstance(result, dict) and result.get("auth_token"):
        _print_token_notice(result["auth_token"])
    _execute_and_track(ctx, action="create-treasury-wallet", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_list_treasury_wallets(ctx: CommandContext) -> None:
    _section_header("WALLETS DE TESORERIA")
    input_units = _measure_units("list-treasury-wallets")
    started_at = time.perf_counter()
    result = ctx.ledger.list_treasury_wallets()
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if not result:
        _print_result_box("SUCCESS", "list-treasury-wallets", "No hay wallets de tesoreria creadas.")
    else:
        _print_data_box(f"Wallets de tesoreria ({len(result)})", result)
    _execute_and_track(ctx, action="list-treasury-wallets", result=result, revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_top_up(ctx: CommandContext) -> None:
    _section_header("RECARGAR WALLET DESDE TESORERIA")
    treasury_wallets = ctx.ledger.list_treasury_wallets()
    if not treasury_wallets:
        _print_result_box("ERROR", "top-up", "No hay wallets de tesoreria. Crea una primero con opcion [25].")
        raise _SkipCommand
    if len(treasury_wallets) == 1:
        treasury_wallet_id = treasury_wallets[0]["wallet_id"]
        print(_dim(f"  Treasury wallet: {treasury_wallet_id} ({treasury_wallets[0]['currency']})"))
    else:
        print()
        print(_box_top())
        print(_box_line(_cyan("  Wallets de tesoreria:")))
        print(_box_mid())
        for i, w in enumerate(treasury_wallets, 1):
            print(_box_line(f"  {_yellow(f'[{i}]')} {w['wallet_id']}  {_dim(w['model'])}  {_bold(w['balance'])} {w['currency']}"))
        print(_box_bot())
        sel = _prompt("Selecciona treasury", hint=f"1-{len(treasury_wallets)}")
        try:
            treasury_wallet_id = treasury_wallets[int(sel) - 1]["wallet_id"]
        except (ValueError, IndexError):
            _print_result_box("ERROR", "top-up", "Seleccion invalida.")
            raise _SkipCommand
    target_wallet_id = _prompt("target_wallet_id")
    amount = _prompt("amount")
    reference = _prompt("reference", default="TOP_UP")
    input_units = _measure_units(treasury_wallet_id, target_wallet_id, amount, reference)
    amount_error = _validate_numeric(amount, "amount")
    if amount_error:
        _execute_and_track(ctx, action="top-up", result=amount_error, revision_id=None, is_error=True, elapsed_ms=0.0, input_units=input_units)
        raise _SkipCommand
    started_at = time.perf_counter()
    result = ctx.ledger.top_up(treasury_wallet_id, target_wallet_id, amount, reference=reference)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if _is_domain_error_result(result):
        _print_result_box("ERROR", "top-up", str(result))
        _execute_and_track(ctx, action="top-up", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Recarga ejecutada", {"resultado": result}, rev)
    _execute_and_track(ctx, action="top-up", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


# ── Permission handlers ──────────────────────────────────

def _cmd_grant_permission(ctx: CommandContext) -> None:
    _section_header("OTORGAR PERMISO A ROL")
    role = _prompt("role", hint="ADMIN / OPERATOR / VIEWER").upper()
    permission = _prompt("permission").upper()
    input_units = _measure_units(role, permission)
    started_at = time.perf_counter()
    result = ctx.ledger.grant_role_permission(role, permission)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "grant-permission", result)
        _execute_and_track(ctx, action="grant-permission", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Permiso otorgado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="grant-permission", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_revoke_permission(ctx: CommandContext) -> None:
    _section_header("REVOCAR PERMISO DE ROL")
    role = _prompt("role", hint="ADMIN / OPERATOR / VIEWER").upper()
    permission = _prompt("permission").upper()
    input_units = _measure_units(role, permission)
    started_at = time.perf_counter()
    result = ctx.ledger.revoke_role_permission(role, permission)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "revoke-permission", result)
        _execute_and_track(ctx, action="revoke-permission", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Permiso revocado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="revoke-permission", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_grant_user_permission(ctx: CommandContext) -> None:
    _section_header("OTORGAR PERMISO A USUARIO")
    user_id = _prompt("user_id")
    permission = _prompt("permission").upper()
    input_units = _measure_units(user_id, permission)
    started_at = time.perf_counter()
    result = ctx.ledger.grant_user_permission(user_id, permission)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "grant-user-permission", result)
        _execute_and_track(ctx, action="grant-user-permission", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Permiso otorgado a usuario", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="grant-user-permission", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_revoke_user_permission(ctx: CommandContext) -> None:
    _section_header("REVOCAR PERMISO DE USUARIO")
    user_id = _prompt("user_id")
    permission = _prompt("permission").upper()
    input_units = _measure_units(user_id, permission)
    started_at = time.perf_counter()
    result = ctx.ledger.revoke_user_permission(user_id, permission)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "revoke-user-permission", result)
        _execute_and_track(ctx, action="revoke-user-permission", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Permiso revocado de usuario", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="revoke-user-permission", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_list_role_permissions(ctx: CommandContext) -> None:
    _section_header("VER PERMISOS DE ROL")
    role = _prompt("role", hint="ADMIN / OPERATOR / VIEWER").upper()
    input_units = _measure_units(role)
    started_at = time.perf_counter()
    result = ctx.ledger.list_role_permissions(role)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Permisos de {role}", result)
    _execute_and_track(ctx, action="list-role-permissions", result=result, revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_list_user_permissions(ctx: CommandContext) -> None:
    _section_header("VER PERMISOS DE USUARIO")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.list_user_permissions(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _print_data_box(f"Permisos de {user_id}", result)
    _execute_and_track(ctx, action="list-user-permissions", result=result, revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_reset_role_permissions(ctx: CommandContext) -> None:
    _section_header("RESETEAR PERMISOS DE ROL")
    role = _prompt("role", hint="ADMIN / OPERATOR / VIEWER").upper()
    if not _prompt_confirm(f"Resetear permisos de {role} a defaults?"):
        _print_result_box("SUCCESS", "reset-role-permissions", "Cancelado por el usuario.")
        raise _SkipCommand
    input_units = _measure_units(role)
    started_at = time.perf_counter()
    result = ctx.ledger.reset_role_permissions(role)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Permisos reseteados", {"resultado": result}, rev)
    _execute_and_track(ctx, action="reset-role-permissions", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


# ── Admin token re-validation (sudo) ─────────────────────

def _require_admin_token(ctx: CommandContext, action_label: str) -> bool:
    """Prompt ADMIN to re-enter JWT token for sensitive operations.

    Returns True if validated. Raises _SkipCommand on failure after retries.
    """
    from domain.auth import decode_jwt
    from config.settings import get_settings

    settings = get_settings()
    if not settings.jwt_secret:
        _print_result_box("ERROR", action_label, "JWT_SECRET no configurado.")
        raise _SkipCommand

    print()
    print(_box_top())
    print(_box_line(_yellow("  VALIDACION DE SEGURIDAD")))
    print(_box_mid())
    print(_box_line(f"  {_dim('Operacion sensible. Ingresa tu token de sesion para confirmar.')}"))
    print(_box_line(f"  {_dim('Si tu token ha expirado, escribe')} {_bold('refresh')} {_dim('para renovarlo.')}"))
    print(_box_bot())

    for attempt in range(3):
        token_input = _prompt("token", hint="(JWT o 'refresh')")

        if token_input.lower() == "refresh":
            # Re-authenticate with password to get new token
            password = _prompt("password", hint="(tu password actual)")
            result = ctx.ledger.login(
                ctx.session.auth_user_id, password,
                settings.jwt_secret, settings.jwt_ttl_seconds,
            )
            if isinstance(result, dict):
                ctx.session.jwt_token = result["access_token"]
                _print_result_box("SUCCESS", "token-refresh", "Token renovado exitosamente.")
                return True
            _print_result_box("ERROR", "token-refresh", "Credenciales invalidas.")
            if attempt < 2:
                print(_dim(f"  Intentos restantes: {2 - attempt}"))
            continue

        # Validate the provided token
        try:
            payload = decode_jwt(token_input, settings.jwt_secret)
            if payload.get("sub") != ctx.session.auth_user_id:
                _print_result_box("ERROR", action_label, "Token no corresponde al usuario actual.")
                if attempt < 2:
                    print(_dim(f"  Intentos restantes: {2 - attempt}"))
                continue
            return True
        except Exception:
            _print_result_box("ERROR", action_label, "Token invalido o expirado. Escribe 'refresh' para renovar.")
            if attempt < 2:
                print(_dim(f"  Intentos restantes: {2 - attempt}"))

    _print_result_box("ERROR", action_label, "Maximo de intentos alcanzado. Operacion cancelada.")
    raise _SkipCommand


# ── Moderation handlers ──────────────────────────────────

def _cmd_freeze_wallet(ctx: CommandContext) -> None:
    _section_header("CONGELAR WALLET")
    _require_admin_token(ctx, "freeze-wallet")
    print()
    print(_box_top())
    print(_box_line(_cyan("  Modo de congelamiento:")))
    print(_box_mid())
    print(_box_line(f"  {_yellow('[1]')} Por usuario   {_dim('(congela TODAS las wallets del usuario)')}"))
    print(_box_line(f"  {_yellow('[2]')} Por wallet    {_dim('(congela una wallet especifica)')}"))
    print(_box_bot())
    mode = _prompt("Modo", hint="1 / 2")
    if mode == "1":
        user_id = _prompt("user_id")
        input_units = _measure_units(user_id)
        wallet_ids = ctx.ledger.user_wallets.get(user_id, [])
        if not wallet_ids:
            _print_result_box("ERROR", "freeze-wallet", f"Usuario {user_id} no tiene wallets.")
            raise _SkipCommand
        started_at = time.perf_counter()
        frozen = []
        for wid in wallet_ids:
            ctx.ledger.freeze_wallet(wid)
            frozen.append(wid)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        rev = _persist(ctx.store, ctx.ledger)
        result = {"user_id": user_id, "frozen_wallets": frozen, "message": f"{len(frozen)} wallet(s) congelada(s)."}
        _print_data_box("Wallets congeladas", result, rev)
        _execute_and_track(ctx, action="freeze-wallet", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)
    else:
        wallet_id = _prompt("wallet_id")
        input_units = _measure_units(wallet_id)
        started_at = time.perf_counter()
        result = ctx.ledger.freeze_wallet(wallet_id)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if isinstance(result, str) and result.startswith("Error"):
            _print_result_box("ERROR", "freeze-wallet", result)
            _execute_and_track(ctx, action="freeze-wallet", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
            raise _SkipCommand
        rev = _persist(ctx.store, ctx.ledger)
        _print_data_box("Wallet congelada", result if isinstance(result, dict) else {"resultado": result}, rev)
        _execute_and_track(ctx, action="freeze-wallet", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_unfreeze_wallet(ctx: CommandContext) -> None:
    _section_header("DESCONGELAR WALLET")
    _require_admin_token(ctx, "unfreeze-wallet")
    print()
    print(_box_top())
    print(_box_line(_cyan("  Modo de descongelamiento:")))
    print(_box_mid())
    print(_box_line(f"  {_yellow('[1]')} Por usuario   {_dim('(descongela TODAS las wallets del usuario)')}"))
    print(_box_line(f"  {_yellow('[2]')} Por wallet    {_dim('(descongela una wallet especifica)')}"))
    print(_box_bot())
    mode = _prompt("Modo", hint="1 / 2")
    if mode == "1":
        user_id = _prompt("user_id")
        input_units = _measure_units(user_id)
        wallet_ids = ctx.ledger.user_wallets.get(user_id, [])
        if not wallet_ids:
            _print_result_box("ERROR", "unfreeze-wallet", f"Usuario {user_id} no tiene wallets.")
            raise _SkipCommand
        started_at = time.perf_counter()
        unfrozen = []
        for wid in wallet_ids:
            ctx.ledger.unfreeze_wallet(wid)
            unfrozen.append(wid)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        rev = _persist(ctx.store, ctx.ledger)
        result = {"user_id": user_id, "unfrozen_wallets": unfrozen, "message": f"{len(unfrozen)} wallet(s) descongelada(s)."}
        _print_data_box("Wallets descongeladas", result, rev)
        _execute_and_track(ctx, action="unfreeze-wallet", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)
    else:
        wallet_id = _prompt("wallet_id")
        input_units = _measure_units(wallet_id)
        started_at = time.perf_counter()
        result = ctx.ledger.unfreeze_wallet(wallet_id)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if isinstance(result, str) and result.startswith("Error"):
            _print_result_box("ERROR", "unfreeze-wallet", result)
            _execute_and_track(ctx, action="unfreeze-wallet", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
            raise _SkipCommand
        rev = _persist(ctx.store, ctx.ledger)
        _print_data_box("Wallet descongelada", result if isinstance(result, dict) else {"resultado": result}, rev)
        _execute_and_track(ctx, action="unfreeze-wallet", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_ban_user(ctx: CommandContext) -> None:
    _section_header("BANEAR USUARIO")
    _require_admin_token(ctx, "ban-user")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.ban_user(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "ban-user", result)
        _execute_and_track(ctx, action="ban-user", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Usuario baneado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="ban-user", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_unban_user(ctx: CommandContext) -> None:
    _section_header("DESBANEAR USUARIO")
    _require_admin_token(ctx, "unban-user")
    user_id = _prompt("user_id")
    unfreeze = _prompt_confirm("Desbanear Y descongelar todas las wallets del usuario?")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.unban_user(user_id, unfreeze_wallets=unfreeze)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "unban-user", result)
        _execute_and_track(ctx, action="unban-user", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Usuario desbaneado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="unban-user", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


# ── User management handlers ─────────────────────────────

def _cmd_update_user(ctx: CommandContext) -> None:
    _section_header("MODIFICAR USUARIO")
    _require_admin_token(ctx, "update-user")
    user_id = _prompt("user_id")
    new_user_id = _prompt("new_user_id", hint="(vacio=no cambiar)")
    new_display_name = _prompt("new_display_name", hint="(vacio=no cambiar)")
    input_units = _measure_units(user_id, new_user_id, new_display_name)
    started_at = time.perf_counter()
    result = ctx.ledger.update_user(user_id, new_user_id=new_user_id or None, new_display_name=new_display_name or None)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "update-user", result)
        _execute_and_track(ctx, action="update-user", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Usuario actualizado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="update-user", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_delete_user(ctx: CommandContext) -> None:
    _section_header("ELIMINAR USUARIO (SOFT DELETE)")
    _require_admin_token(ctx, "delete-user")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.delete_user(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "delete-user", result)
        _execute_and_track(ctx, action="delete-user", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Usuario eliminado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="delete-user", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_restore_user(ctx: CommandContext) -> None:
    _section_header("RESTAURAR USUARIO")
    _require_admin_token(ctx, "restore-user")
    user_id = _prompt("user_id")
    unfreeze = _prompt_confirm("Restaurar Y descongelar wallets del usuario?")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.restore_user(user_id, unfreeze_wallets=unfreeze)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "restore-user", result)
        _execute_and_track(ctx, action="restore-user", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Usuario restaurado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="restore-user", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_generate_temp_password(ctx: CommandContext) -> None:
    _section_header("GENERAR PASSWORD TEMPORAL")
    _require_admin_token(ctx, "generate-temp-password")
    user_id = _prompt("user_id")
    input_units = _measure_units(user_id)
    started_at = time.perf_counter()
    result = ctx.ledger.generate_temp_password_for_user(user_id)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "generate-temp-password", result)
        _execute_and_track(ctx, action="generate-temp-password", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    print()
    print(_box_top())
    print(_box_line(_yellow("  PASSWORD TEMPORAL GENERADO")))
    print(_box_mid())
    print(_box_line(f"  {_dim('Usuario:')}     {_bold(user_id)}"))
    print(_box_line(f"  {_dim('Password:')}    {_green(_bold(result.get('temp_password', '')))}"))
    print(_box_line(f"  {_dim('Token:')}       {result.get('token_temp', '')[:20]}..."))
    print(_box_mid())
    print(_box_line(_dim("  Entrega estos datos al usuario. El password es de un solo uso.")))
    print(_box_line(_dim("  Al ingresar, el usuario debera cambiar su contrasena.")))
    print(_box_bot())
    _execute_and_track(ctx, action="generate-temp-password", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_list_audit_log(ctx: CommandContext) -> None:
    _section_header("LOG DE AUDITORIA")
    user_id = _prompt("user_id", hint="(filtrar por usuario, vacio=todos)")
    action = _prompt("action", hint="(filtrar por accion, vacio=todas)")
    limit_raw = _prompt("limit", default="20")
    limit = int(limit_raw) if limit_raw.isdigit() else 20
    input_units = _measure_units(user_id, action, limit)
    started_at = time.perf_counter()
    result = ctx.ledger.list_audit_log(limit=limit, user_id=user_id, action=action)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if not result:
        _print_result_box("SUCCESS", "list-audit-log", "No hay entradas de auditoria.")
    else:
        _print_data_box(f"Audit Log ({len(result)} entradas)", result)
    _execute_and_track(ctx, action="list-audit-log", result=result, revision_id=None, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_change_password(ctx: CommandContext) -> None:
    _section_header("CAMBIAR CONTRASENA")
    current_password = _prompt("current_password")
    new_password = _prompt("new_password", hint="(min 4 caracteres)")
    input_units = _measure_units(current_password, new_password)
    started_at = time.perf_counter()
    result = ctx.ledger.change_password(ctx.session.auth_user_id, current_password, new_password)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "change-password", result)
        _execute_and_track(ctx, action="change-password", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Contrasena actualizada", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="change-password", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


def _cmd_update_profile(ctx: CommandContext) -> None:
    _section_header("ACTUALIZAR PERFIL")
    is_admin = "ADMIN" in ctx.session.auth_roles
    if is_admin:
        user_id = _prompt("user_id", hint=f"(enter={ctx.session.auth_user_id})", default=ctx.session.auth_user_id)
    else:
        user_id = ctx.session.auth_user_id
        print(_dim(f"  Usuario: {user_id}"))
    first_name = _prompt("first_name", hint="(vacio=no cambiar)")
    last_name = _prompt("last_name", hint="(vacio=no cambiar)")
    email = _prompt("email", hint="(vacio=no cambiar)")
    username = _prompt("username", hint="(vacio=no cambiar)")
    input_units = _measure_units(user_id, first_name, last_name, email, username)
    started_at = time.perf_counter()
    result = ctx.ledger.update_profile(user_id, first_name=first_name or None, last_name=last_name or None, email=email or None, username=username or None)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if isinstance(result, str) and result.startswith("Error"):
        _print_result_box("ERROR", "update-profile", result)
        _execute_and_track(ctx, action="update-profile", result=result, revision_id=None, is_error=True, elapsed_ms=elapsed_ms, input_units=input_units)
        raise _SkipCommand
    rev = _persist(ctx.store, ctx.ledger)
    _print_data_box("Perfil actualizado", result if isinstance(result, dict) else {"resultado": result}, rev)
    _execute_and_track(ctx, action="update-profile", result=result, revision_id=rev, is_error=False, elapsed_ms=elapsed_ms, input_units=input_units)


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
    "23": (_cmd_set_exchange_rate,       Permission.SET_EXCHANGE_RATE),
    "24": (_cmd_list_exchange_rates,     None),
    "25": (_cmd_create_treasury_wallet,  Permission.TOP_UP),
    "26": (_cmd_list_treasury_wallets,   Permission.TOP_UP),
    "27": (_cmd_top_up,                  Permission.TOP_UP),
    "28": (_cmd_grant_permission,        Permission.MANAGE_PERMISSIONS),
    "29": (_cmd_revoke_permission,       Permission.MANAGE_PERMISSIONS),
    "30": (_cmd_grant_user_permission,   Permission.MANAGE_PERMISSIONS),
    "31": (_cmd_revoke_user_permission,  Permission.MANAGE_PERMISSIONS),
    "32": (_cmd_list_role_permissions,   Permission.MANAGE_PERMISSIONS),
    "33": (_cmd_list_user_permissions,   Permission.MANAGE_PERMISSIONS),
    "34": (_cmd_reset_role_permissions,  Permission.MANAGE_PERMISSIONS),
    "35": (_cmd_freeze_wallet,           Permission.FREEZE_WALLET),
    "36": (_cmd_unfreeze_wallet,         Permission.UNFREEZE_WALLET),
    "37": (_cmd_ban_user,                Permission.BAN_USER),
    "38": (_cmd_unban_user,              Permission.UNBAN_USER),
    "39": (_cmd_update_user,             Permission.UPDATE_USER),
    "40": (_cmd_delete_user,             Permission.DELETE_USER),
    "41": (_cmd_restore_user,            Permission.RESTORE_USER),
    "42": (_cmd_generate_temp_password,  Permission.GENERATE_TEMP_PASSWORD),
    "43": (_cmd_list_audit_log,          Permission.VIEW_AUDIT_LOG),
    "44": (_cmd_change_password,         None),
    "45": (_cmd_update_profile,          Permission.UPDATE_PROFILE),
    "46": (_cmd_list_transfers,          Permission.VIEW_TRANSFERS),
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

        if required_perm and not has_permission(
            session.auth_roles, required_perm,
            role_overrides=ledger.role_permission_overrides,
            user_permissions=ledger.user_permission_overrides,
            user_id=session.auth_user_id,
        ):
            _print_result_box("ERROR", "permiso-denegado", f"Se requiere: {required_perm}. Tus roles: {', '.join(session.auth_roles) or 'ninguno'}")
            continue

        ctx = CommandContext(session=session, store=store, ledger=ledger, store_file=store_file)
        try:
            handler(ctx)
        except _SkipCommand:
            continue


if __name__ == "__main__":
    main()
