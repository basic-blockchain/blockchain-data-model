#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data" / "multiuser" / "wallet-ledger.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.stderr.encoding and sys.stderr.encoding.lower().replace("-", "") != "utf8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.factory import create_wallet_store
from persistence.interfaces import WalletLedgerRepository


# ── ANSI helpers ─────────────────────────────────────────

def _supports_ansi() -> bool:
    return sys.stdout.isatty() and sys.stderr.isatty()


def _s(text: str, code: str) -> str:
    if not _supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


def _dim(t: str) -> str: return _s(t, "2")
def _bold(t: str) -> str: return _s(t, "1")
def _cyan(t: str) -> str: return _s(t, "1;36")
def _green(t: str) -> str: return _s(t, "1;32")
def _red(t: str) -> str: return _s(t, "1;31")
def _yellow(t: str) -> str: return _s(t, "1;33")


# ── Box drawing ──────────────────────────────────────────

W = 72


def _box_top() -> str:
    return f"\u2554{'\u2550' * (W + 2)}\u2557"


def _box_mid() -> str:
    return f"\u2560{'\u2550' * (W + 2)}\u2563"


def _box_bot() -> str:
    return f"\u255a{'\u2550' * (W + 2)}\u255d"


def _box_line(text: str = "") -> str:
    stripped = text
    for code in ("1;36", "1;32", "1;31", "1;33", "1;34", "1;35", "1;37", "0;33", "0;37", "1", "2"):
        stripped = stripped.replace(f"\033[{code}m", "").replace("\033[0m", "")
    pad = W - len(stripped)
    if pad < 0:
        pad = 0
    return f"\u2551 {text}{' ' * pad} \u2551"


def _wrap_lines(text: str, width: int) -> list[str]:
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


# ── Alert & data output ─────────────────────────────────

def _print_alert(kind: str, title: str, message: str | None = None, *, stream=None) -> None:
    color_fn = _red if kind == "ERROR" else _green
    icon = "\u2717" if kind == "ERROR" else "\u2713"
    out = stream if stream is not None else sys.stdout
    header = f"  {icon} [{kind}] {title}"

    print(color_fn(_box_top()), file=out)
    for line in _wrap_lines(header, W):
        print(color_fn(_box_line(line)), file=out)
    if message:
        print(color_fn(_box_mid()), file=out)
        for line in _wrap_lines(f"  {message}", W):
            print(color_fn(_box_line(line)), file=out)
    print(color_fn(_box_bot()), file=out)


def _print_data_box(title: str, data, revision_id: str = "", *, stream=None) -> None:
    out = stream if stream is not None else sys.stderr
    print(file=out)
    print(_box_top(), file=out)
    print(_box_line(_cyan(f"  {title}")), file=out)
    print(_box_mid(), file=out)

    if isinstance(data, dict):
        for key, val in data.items():
            val_str = str(val)
            max_val = W - 22
            if len(val_str) > max_val:
                val_str = val_str[:max_val - 3] + "..."
            print(_box_line(f"  {_dim(key + ':'):<22} {_bold(val_str)}"), file=out)
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        for i, item in enumerate(data[:10]):
            if i > 0:
                print(_box_line(_dim("  " + "\u2500" * (W - 4))), file=out)
            for key, val in item.items():
                val_str = str(val)
                max_val = W - 22
                if len(val_str) > max_val:
                    val_str = val_str[:max_val - 3] + "..."
                print(_box_line(f"  {_dim(key + ':'):<22} {val_str}"), file=out)
        if len(data) > 10:
            print(_box_line(_dim(f"  ... y {len(data) - 10} mas")), file=out)
    elif isinstance(data, str):
        for line in _wrap_lines(f"  {data}", W):
            print(_box_line(line), file=out)

    if revision_id:
        print(_box_mid(), file=out)
        print(_box_line(_dim(f"  revision: {revision_id}")), file=out)

    print(_box_bot(), file=out)


# ── Utilities ────────────────────────────────────────────

def _wants_json_from_argv() -> bool:
    return "--json" in sys.argv[1:]


def _compact_alert_message(result) -> str | None:
    if isinstance(result, dict):
        for key in ("message", "mensaje"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    if isinstance(result, str):
        cleaned = result.strip()
        if cleaned.lower().startswith("error:"):
            cleaned = cleaned[6:].strip()
        return cleaned if cleaned else None
    return None


class CliArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        if _wants_json_from_argv():
            _print_alert("ERROR", "invalid-arguments", message, stream=sys.stderr)
            _print_json(
                {
                    "success": False,
                    "error": message,
                    "error_type": "ArgumentError",
                    "revision_id": "",
                    "store_file": str(DEFAULT_STORE.resolve()),
                }
            )
        else:
            _print_alert("ERROR", "invalid-arguments", message, stream=sys.stderr)
            self.print_usage(sys.stderr)
        raise SystemExit(2)


def _print_json(payload: dict | list) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _load_ledger(store_path: Path) -> tuple[WalletLedgerRepository, MultiUserWalletLedger]:
    store = create_wallet_store(json_path=store_path)
    ledger = store.load_ledger()
    return store, ledger


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", dest="cmd_json", action="store_true", help="JSON output mode")


def _parse_optional_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Valor invalido para booleano. Use true/false.")


# ── Main ─────────────────────────────────────────────────

def main() -> None:
    parser = CliArgumentParser(description="Multi-user wallet ledger CLI")
    parser.add_argument("--store-file", default=str(DEFAULT_STORE), help="Path to the JSON ledger store")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    parser.add_argument("--token", default="", help="JWT token for authenticated operations")

    subparsers = parser.add_subparsers(dest="command", required=True)

    cmd_register = subparsers.add_parser("register", help="Register a new user with role selection")
    _add_json_flag(cmd_register)
    cmd_register.add_argument("--user-id", required=True)
    cmd_register.add_argument("--display-name", required=True)
    cmd_register.add_argument("--password", required=True)
    cmd_register.add_argument("--role", default="", choices=["ADMIN", "OPERATOR", "VIEWER", "admin", "operator", "viewer", ""])
    cmd_register.add_argument("--invitation-token", default="")

    cmd_login = subparsers.add_parser("login", help="Authenticate and obtain a JWT token")
    _add_json_flag(cmd_login)
    cmd_login.add_argument("--user-id", required=True)
    cmd_login.add_argument("--password", required=True)
    cmd_login.add_argument("--activation-code", default="")

    cmd_gen_admin = subparsers.add_parser("generate-admin-token", help="Generate an invitation token for new ADMIN (ADMIN only)")
    _add_json_flag(cmd_gen_admin)

    cmd_assign_role = subparsers.add_parser("assign-role", help="Assign a role to a user (ADMIN only)")
    _add_json_flag(cmd_assign_role)
    cmd_assign_role.add_argument("--user-id", required=True)
    cmd_assign_role.add_argument("--role", required=True, choices=["ADMIN", "OPERATOR", "VIEWER"])

    cmd_remove_role = subparsers.add_parser("remove-role", help="Remove a role from a user (ADMIN only)")
    _add_json_flag(cmd_remove_role)
    cmd_remove_role.add_argument("--user-id", required=True)
    cmd_remove_role.add_argument("--role", required=True, choices=["ADMIN", "OPERATOR", "VIEWER"])

    cmd_user = subparsers.add_parser("create-user", help="Create a user (ADMIN only)")
    _add_json_flag(cmd_user)
    cmd_user.add_argument("--user-id", required=True)
    cmd_user.add_argument("--display-name", required=True)
    cmd_user.add_argument("--password", default="")

    cmd_wallet = subparsers.add_parser("create-wallet", help="Create a wallet for an existing user")
    _add_json_flag(cmd_wallet)
    cmd_wallet.add_argument("--user-id", required=True)
    cmd_wallet.add_argument("--wallet-id", default="")
    cmd_wallet.add_argument("--currency", default="USDX")
    cmd_wallet.add_argument("--model", default="ACCOUNT", choices=["ACCOUNT", "UTXO", "account", "utxo"])

    cmd_refresh_token = subparsers.add_parser("refresh-token", help="Renew wallet token for owner user")
    _add_json_flag(cmd_refresh_token)
    cmd_refresh_token.add_argument("--user-id", required=True)
    cmd_refresh_token.add_argument("--wallet-id", required=True)
    cmd_refresh_token.add_argument("--current-token", default="")

    cmd_mint = subparsers.add_parser("mint", help="Mint funds into a wallet")
    _add_json_flag(cmd_mint)
    cmd_mint.add_argument("--wallet-id", required=True)
    cmd_mint.add_argument("--amount", required=True)
    cmd_mint.add_argument("--reference", default="MINT")

    cmd_transfer = subparsers.add_parser("transfer", help="Transfer funds between wallets")
    _add_json_flag(cmd_transfer)
    cmd_transfer.add_argument("--from-wallet", required=True)
    cmd_transfer.add_argument("--to-wallet", required=True)
    cmd_transfer.add_argument("--amount", required=True)
    cmd_transfer.add_argument("--fee", default="0")
    cmd_transfer.add_argument("--reference", default="")
    cmd_transfer.add_argument("--sender-token", default="")
    cmd_transfer.add_argument("--expected-nonce", type=int)

    cmd_balance = subparsers.add_parser("balance", help="Get wallet balance (omit --wallet-id to see all your wallets)")
    _add_json_flag(cmd_balance)
    cmd_balance.add_argument("--wallet-id", default="")

    cmd_users = subparsers.add_parser("list-users", help="List all users")
    _add_json_flag(cmd_users)

    cmd_wallets = subparsers.add_parser("list-wallets", help="List wallets")
    _add_json_flag(cmd_wallets)
    cmd_wallets.add_argument("--user-id", default="")

    cmd_utxos = subparsers.add_parser("list-utxos", help="List UTXOs (all or by wallet)")
    _add_json_flag(cmd_utxos)
    cmd_utxos.add_argument("--wallet-id", default="")

    cmd_snapshot = subparsers.add_parser("snapshot", help="Get full ledger snapshot")
    _add_json_flag(cmd_snapshot)

    cmd_revisions = subparsers.add_parser("list-revisions", help="List saved revisions")
    _add_json_flag(cmd_revisions)
    cmd_revisions.add_argument("--limit", type=int, default=20)

    cmd_set_policy = subparsers.add_parser("set-policy", help="Set transfer policy for a user")
    _add_json_flag(cmd_set_policy)
    cmd_set_policy.add_argument("--user-id", required=True)
    cmd_set_policy.add_argument("--can-transfer", type=_parse_optional_bool)
    cmd_set_policy.add_argument("--daily-limit")

    cmd_get_policy = subparsers.add_parser("get-policy", help="Get transfer policy for a user")
    _add_json_flag(cmd_get_policy)
    cmd_get_policy.add_argument("--user-id", required=True)

    cmd_list_policies = subparsers.add_parser("list-policies", help="List all user transfer policies")
    _add_json_flag(cmd_list_policies)

    cmd_set_risk_profile = subparsers.add_parser("set-risk-profile", help="Set risk profile for a user")
    _add_json_flag(cmd_set_risk_profile)
    cmd_set_risk_profile.add_argument("--user-id", required=True)
    cmd_set_risk_profile.add_argument("--profile-name")
    cmd_set_risk_profile.add_argument("--daily-limit")
    cmd_set_risk_profile.add_argument("--transfer-alert-threshold")
    cmd_set_risk_profile.add_argument("--daily-alert-threshold")

    cmd_get_risk_profile = subparsers.add_parser("get-risk-profile", help="Get risk profile for a user")
    _add_json_flag(cmd_get_risk_profile)
    cmd_get_risk_profile.add_argument("--user-id", required=True)

    cmd_list_risk_profiles = subparsers.add_parser("list-risk-profiles", help="List all user risk profiles")
    _add_json_flag(cmd_list_risk_profiles)

    cmd_list_alerts = subparsers.add_parser("list-alerts", help="List alerts generated by risk thresholds")
    _add_json_flag(cmd_list_alerts)
    cmd_list_alerts.add_argument("--user-id", default="")
    cmd_list_alerts.add_argument("--severity", default="")
    cmd_list_alerts.add_argument("--limit", type=int, default=50)

    cmd_set_exchange_rate = subparsers.add_parser("set-exchange-rate", help="Set exchange rate between two currencies (ADMIN only)")
    _add_json_flag(cmd_set_exchange_rate)
    cmd_set_exchange_rate.add_argument("--from-currency", required=True)
    cmd_set_exchange_rate.add_argument("--to-currency", required=True)
    cmd_set_exchange_rate.add_argument("--rate", required=True)
    cmd_set_exchange_rate.add_argument("--commission", default="1.0")

    cmd_list_exchange_rates = subparsers.add_parser("list-exchange-rates", help="List all configured exchange rates")
    _add_json_flag(cmd_list_exchange_rates)

    cmd_verify_integrity = subparsers.add_parser(
        "verify-integrity",
        help="Verify transfer nonce and hash-chain integrity",
    )
    _add_json_flag(cmd_verify_integrity)

    args = parser.parse_args()
    store_file = Path(args.store_file)
    output_json = bool(args.json or getattr(args, "cmd_json", False))
    jwt_token = args.token

    try:
        store, ledger = _load_ledger(store_file)

        from config.settings import get_settings
        from domain.auth import decode_jwt, has_permission, Permission

        settings = get_settings()

        def _require_auth(permission: str) -> dict:
            """Validate JWT and check permission. Returns decoded payload or exits."""
            if not jwt_token:
                raise PermissionError(f"Se requiere --token para esta operacion ({permission}).")
            if not settings.jwt_secret:
                raise PermissionError("JWT_SECRET no configurado en el entorno.")
            payload = decode_jwt(jwt_token, settings.jwt_secret)
            roles = payload.get("roles", [])
            if not has_permission(roles, permission):
                raise PermissionError(f"Permiso denegado. Se requiere: {permission}. Roles actuales: {roles}")
            return payload

        mutate = False
        result: dict | list | str

        # ── Auth commands (no token required) ──
        if args.command == "register":
            is_bootstrap = ledger.is_empty()
            role = (args.role or "").upper()
            if is_bootstrap:
                result = ledger.create_user(args.user_id, args.display_name, password=args.password)
                if not (isinstance(result, str) and result.startswith("Error")):
                    ledger.assign_role(args.user_id, "ADMIN")
                    result = {"message": result if isinstance(result, str) else result.get("message", ""), "bootstrap": True, "role": "ADMIN", "user_id": args.user_id}
            else:
                result = ledger.create_user(args.user_id, args.display_name, password=args.password, role=role, invitation_token=args.invitation_token)
            mutate = True
        elif args.command == "login":
            if not settings.jwt_secret:
                result = "Error: JWT_SECRET no configurado en el entorno."
            else:
                result = ledger.login(args.user_id, args.password, settings.jwt_secret, settings.jwt_ttl_seconds, activation_code=args.activation_code)
                if isinstance(result, dict):
                    mutate = True
        elif args.command == "generate-admin-token":
            payload = _require_auth(Permission.ASSIGN_ROLE)
            caller_id = payload.get("sub", "")
            result = ledger.generate_admin_invitation(caller_id)
            mutate = True

        # ── Admin-only commands ──
        elif args.command == "create-user":
            _require_auth(Permission.CREATE_USER)
            result = ledger.create_user(args.user_id, args.display_name, password=getattr(args, "password", ""))
            mutate = True
        elif args.command == "assign-role":
            _require_auth(Permission.ASSIGN_ROLE)
            result = ledger.assign_role(args.user_id, args.role)
            mutate = True
        elif args.command == "remove-role":
            _require_auth(Permission.ASSIGN_ROLE)
            result = ledger.remove_role(args.user_id, args.role)
            mutate = True
        # ── Operator commands (OPERATOR+) ──
        elif args.command == "create-wallet":
            _require_auth(Permission.CREATE_WALLET)
            result = ledger.create_wallet(args.user_id, wallet_id=args.wallet_id, currency=args.currency, model=args.model)
            mutate = True
        elif args.command == "refresh-token":
            _require_auth(Permission.VIEW_WALLETS)
            result = ledger.refresh_wallet_token(args.user_id, args.wallet_id, current_token=args.current_token)
            mutate = True
        elif args.command == "mint":
            _require_auth(Permission.MINT)
            result = ledger.mint(args.wallet_id, args.amount, reference=args.reference)
            mutate = True
        elif args.command == "transfer":
            _require_auth(Permission.TRANSFER)
            result = ledger.transfer(args.from_wallet, args.to_wallet, args.amount, fee=args.fee, reference=args.reference, sender_token=args.sender_token, expected_nonce=getattr(args, "expected_nonce", None))
            mutate = True

        # ── Exchange commands ──
        elif args.command == "set-exchange-rate":
            _require_auth(Permission.SET_EXCHANGE_RATE)
            result = ledger.set_exchange_rate(args.from_currency, args.to_currency, args.rate, commission_pct=args.commission)
            mutate = True
        elif args.command == "list-exchange-rates":
            _require_auth(Permission.EXCHANGE)
            result = ledger.list_exchange_rates()

        # ── Admin commands (ADMIN only) ──
        elif args.command == "set-policy":
            _require_auth(Permission.SET_POLICY)
            can_transfer = args.can_transfer if hasattr(args, "can_transfer") else None
            daily_limit = args.daily_limit if getattr(args, "daily_limit", None) is not None else None
            result = ledger.set_user_policy(args.user_id, can_transfer=can_transfer, daily_limit=daily_limit)
            mutate = True
        elif args.command == "set-risk-profile":
            _require_auth(Permission.SET_RISK_PROFILE)
            result = ledger.set_user_risk_profile(args.user_id, profile_name=getattr(args, "profile_name", None), daily_limit=getattr(args, "daily_limit", None), transfer_alert_threshold=getattr(args, "transfer_alert_threshold", None), daily_alert_threshold=getattr(args, "daily_alert_threshold", None))
            mutate = True

        # ── Viewer commands (any authenticated user) ──
        elif args.command == "balance":
            payload = _require_auth(Permission.VIEW_WALLETS)
            wallet_id = args.wallet_id
            if not wallet_id:
                caller_id = payload.get("sub", "")
                user_wallets = ledger.list_wallets(user_id=caller_id)
                result = [{"wallet_id": w["wallet_id"], "model": w["model"], "currency": w["currency"], "balance": w["balance"]} for w in user_wallets]
            else:
                result = {"wallet_id": wallet_id, "balance": str(ledger.get_wallet_balance(wallet_id))}
        elif args.command == "list-users":
            _require_auth(Permission.VIEW_USERS)
            result = ledger.list_users()
        elif args.command == "list-wallets":
            _require_auth(Permission.VIEW_WALLETS)
            result = ledger.list_wallets(user_id=args.user_id)
        elif args.command == "list-utxos":
            _require_auth(Permission.VIEW_WALLETS)
            result = ledger.list_utxos(wallet_id=args.wallet_id)
        elif args.command == "snapshot":
            _require_auth(Permission.VIEW_WALLETS)
            result = ledger.state_snapshot()
        elif args.command == "list-revisions":
            _require_auth(Permission.VIEW_REVISIONS)
            result = store.list_revisions(limit=args.limit)
        elif args.command == "get-policy":
            _require_auth(Permission.VIEW_POLICIES)
            result = ledger.get_user_policy(args.user_id)
        elif args.command == "list-policies":
            _require_auth(Permission.VIEW_POLICIES)
            result = ledger.list_user_policies()
        elif args.command == "get-risk-profile":
            _require_auth(Permission.VIEW_RISK_PROFILES)
            result = ledger.get_user_risk_profile(args.user_id)
        elif args.command == "list-risk-profiles":
            _require_auth(Permission.VIEW_RISK_PROFILES)
            result = ledger.list_user_risk_profiles()
        elif args.command == "list-alerts":
            _require_auth(Permission.VIEW_ALERTS)
            result = ledger.list_alerts(limit=args.limit, user_id=args.user_id, severity=args.severity)
        elif args.command == "verify-integrity":
            _require_auth(Permission.VIEW_WALLETS)
            result = ledger.verify_transfer_integrity()
        else:
            result = "Error: command no soportado."

        revision_id = ""
        if mutate:
            revision_id = store.save_ledger(ledger)

        success = not (
            isinstance(result, str)
            and (result.startswith("Error:") or result.startswith("Wallet invalida."))
        )
        if isinstance(result, dict) and "valid" in result and not bool(result["valid"]):
            success = False

        if output_json:
            kind = "SUCCESS" if success else "ERROR"
            _print_alert(kind, args.command, _compact_alert_message(result), stream=sys.stderr)
            payload = {
                "success": success,
                "result": result,
                "revision_id": revision_id,
                "store_file": str(store_file.resolve()),
            }
            _print_json(payload)
            sys.exit(0 if success else 1)

        # Non-JSON visual output
        if success:
            _print_alert("SUCCESS", args.command, _compact_alert_message(result))
            if isinstance(result, dict):
                _print_data_box(args.command, result, revision_id, stream=sys.stdout)
            elif isinstance(result, list) and result:
                _print_data_box(f"{args.command} ({len(result)} items)", result, stream=sys.stdout)
        else:
            _print_alert("ERROR", args.command, _compact_alert_message(result), stream=sys.stderr)
        sys.exit(0 if success else 1)
    except Exception as exc:
        if output_json:
            _print_json(
                {
                    "success": False,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "revision_id": "",
                    "store_file": str(store_file.resolve()),
                }
            )
        else:
            _print_alert("ERROR", "exception", str(exc), stream=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
