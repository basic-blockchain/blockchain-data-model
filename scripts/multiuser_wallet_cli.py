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

from domain.multiuser_wallet_ledger import MultiUserWalletLedger, TransferListQuery
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
    cmd_user.add_argument("--first-name", default="")
    cmd_user.add_argument("--last-name", default="")
    cmd_user.add_argument("--email", default="")
    cmd_user.add_argument("--username", default="")

    cmd_update_profile = subparsers.add_parser("update-profile", help="Update user profile (own or ADMIN for others)")
    _add_json_flag(cmd_update_profile)
    cmd_update_profile.add_argument("--user-id", required=True)
    cmd_update_profile.add_argument("--first-name", default="")
    cmd_update_profile.add_argument("--last-name", default="")
    cmd_update_profile.add_argument("--email", default="")
    cmd_update_profile.add_argument("--username", default="")

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

    cmd_list_transfers = subparsers.add_parser("list-transfers", help="List transfers (filterable by wallet, user, type, or ID)")
    _add_json_flag(cmd_list_transfers)
    cmd_list_transfers.add_argument("--wallet-id", default="")
    cmd_list_transfers.add_argument("--user-id", default="")
    cmd_list_transfers.add_argument("--type", default="", dest="transfer_type")
    cmd_list_transfers.add_argument("--transfer-id", default="")
    cmd_list_transfers.add_argument("--limit", type=int, default=50)

    cmd_set_exchange_rate = subparsers.add_parser("set-exchange-rate", help="Set exchange rate between two currencies (ADMIN only)")
    _add_json_flag(cmd_set_exchange_rate)
    cmd_set_exchange_rate.add_argument("--from-currency", required=True)
    cmd_set_exchange_rate.add_argument("--to-currency", required=True)
    cmd_set_exchange_rate.add_argument("--rate", required=True)
    cmd_set_exchange_rate.add_argument("--commission", default="1.0")

    cmd_list_exchange_rates = subparsers.add_parser("list-exchange-rates", help="List all configured exchange rates")
    _add_json_flag(cmd_list_exchange_rates)

    # ── Treasury commands ──
    cmd_create_treasury_wallet = subparsers.add_parser("create-treasury-wallet", help="Create a treasury wallet (ADMIN only)")
    _add_json_flag(cmd_create_treasury_wallet)
    cmd_create_treasury_wallet.add_argument("--currency", default="USDX")
    cmd_create_treasury_wallet.add_argument("--model", default="ACCOUNT", choices=["ACCOUNT", "UTXO", "account", "utxo"])

    cmd_list_treasury_wallets = subparsers.add_parser("list-treasury-wallets", help="List treasury wallets")
    _add_json_flag(cmd_list_treasury_wallets)

    cmd_top_up = subparsers.add_parser("top-up", help="Top up a wallet from treasury (ADMIN only)")
    _add_json_flag(cmd_top_up)
    cmd_top_up.add_argument("--treasury-wallet-id", required=True)
    cmd_top_up.add_argument("--target-wallet-id", required=True)
    cmd_top_up.add_argument("--amount", required=True)
    cmd_top_up.add_argument("--reference", default="TOP_UP")

    # ── Permission management commands ──
    cmd_grant_perm = subparsers.add_parser("grant-permission", help="Grant permission to a role (ADMIN only)")
    _add_json_flag(cmd_grant_perm)
    cmd_grant_perm.add_argument("--role", required=True)
    cmd_grant_perm.add_argument("--permission", required=True)

    cmd_revoke_perm = subparsers.add_parser("revoke-permission", help="Revoke permission from a role (ADMIN only)")
    _add_json_flag(cmd_revoke_perm)
    cmd_revoke_perm.add_argument("--role", required=True)
    cmd_revoke_perm.add_argument("--permission", required=True)

    cmd_grant_user_perm = subparsers.add_parser("grant-user-permission", help="Grant permission to a user (ADMIN only)")
    _add_json_flag(cmd_grant_user_perm)
    cmd_grant_user_perm.add_argument("--user-id", required=True)
    cmd_grant_user_perm.add_argument("--permission", required=True)

    cmd_revoke_user_perm = subparsers.add_parser("revoke-user-permission", help="Revoke permission from a user (ADMIN only)")
    _add_json_flag(cmd_revoke_user_perm)
    cmd_revoke_user_perm.add_argument("--user-id", required=True)
    cmd_revoke_user_perm.add_argument("--permission", required=True)

    cmd_list_role_perms = subparsers.add_parser("list-role-permissions", help="List effective permissions for a role")
    _add_json_flag(cmd_list_role_perms)
    cmd_list_role_perms.add_argument("--role", required=True)

    cmd_list_user_perms = subparsers.add_parser("list-user-permissions", help="List direct permissions for a user")
    _add_json_flag(cmd_list_user_perms)
    cmd_list_user_perms.add_argument("--user-id", required=True)

    cmd_reset_role_perms = subparsers.add_parser("reset-role-permissions", help="Reset role permissions to defaults (ADMIN only)")
    _add_json_flag(cmd_reset_role_perms)
    cmd_reset_role_perms.add_argument("--role", required=True)

    cmd_verify_integrity = subparsers.add_parser(
        "verify-integrity",
        help="Verify transfer nonce and hash-chain integrity",
    )
    _add_json_flag(cmd_verify_integrity)

    # ── Moderation commands ──
    cmd_freeze_wallet = subparsers.add_parser("freeze-wallet", help="Freeze a wallet (ADMIN only)")
    _add_json_flag(cmd_freeze_wallet)
    cmd_freeze_wallet.add_argument("--wallet-id", required=True)

    cmd_unfreeze_wallet = subparsers.add_parser("unfreeze-wallet", help="Unfreeze a wallet (ADMIN only)")
    _add_json_flag(cmd_unfreeze_wallet)
    cmd_unfreeze_wallet.add_argument("--wallet-id", required=True)

    cmd_ban_user = subparsers.add_parser("ban-user", help="Ban a user and freeze their wallets (ADMIN only)")
    _add_json_flag(cmd_ban_user)
    cmd_ban_user.add_argument("--user-id", required=True)

    cmd_unban_user = subparsers.add_parser("unban-user", help="Unban a user (ADMIN only)")
    _add_json_flag(cmd_unban_user)
    cmd_unban_user.add_argument("--user-id", required=True)
    cmd_unban_user.add_argument("--unfreeze-wallets", type=_parse_optional_bool, default=True)

    # ── User management commands ──
    cmd_update_user = subparsers.add_parser("update-user", help="Update user ID or display name (ADMIN only)")
    _add_json_flag(cmd_update_user)
    cmd_update_user.add_argument("--user-id", required=True)
    cmd_update_user.add_argument("--new-user-id", default="")
    cmd_update_user.add_argument("--new-display-name", default="")

    cmd_delete_user = subparsers.add_parser("delete-user", help="Soft-delete a user (ADMIN only)")
    _add_json_flag(cmd_delete_user)
    cmd_delete_user.add_argument("--user-id", required=True)

    cmd_restore_user = subparsers.add_parser("restore-user", help="Restore a soft-deleted user (ADMIN only)")
    _add_json_flag(cmd_restore_user)
    cmd_restore_user.add_argument("--user-id", required=True)
    cmd_restore_user.add_argument("--unfreeze-wallets", type=_parse_optional_bool, default=True)

    cmd_gen_temp_pw = subparsers.add_parser("generate-temp-password", help="Generate temporary password for a user (ADMIN only)")
    _add_json_flag(cmd_gen_temp_pw)
    cmd_gen_temp_pw.add_argument("--user-id", required=True)

    cmd_change_pw = subparsers.add_parser("change-password", help="Change your own password")
    _add_json_flag(cmd_change_pw)
    cmd_change_pw.add_argument("--current-password", required=True)
    cmd_change_pw.add_argument("--new-password", required=True)

    cmd_audit = subparsers.add_parser("list-audit-log", help="List audit log entries (ADMIN only)")
    _add_json_flag(cmd_audit)
    cmd_audit.add_argument("--user-id", default="")
    cmd_audit.add_argument("--action", default="")
    cmd_audit.add_argument("--limit", type=int, default=50)

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
            result = ledger.create_user(args.user_id, args.display_name, password=getattr(args, "password", ""), first_name=getattr(args, "first_name", ""), last_name=getattr(args, "last_name", ""), email=getattr(args, "email", ""), username=getattr(args, "username", ""))
            mutate = True
        elif args.command == "update-profile":
            _require_auth(Permission.UPDATE_PROFILE)
            result = ledger.update_profile(args.user_id, first_name=args.first_name or None, last_name=args.last_name or None, email=args.email or None, username=args.username or None)
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

        # ── Treasury commands ──
        elif args.command == "create-treasury-wallet":
            _require_auth(Permission.TOP_UP)
            result = ledger.create_treasury_wallet(currency=args.currency, model=args.model.upper())
            mutate = True
        elif args.command == "list-treasury-wallets":
            _require_auth(Permission.TOP_UP)
            result = ledger.list_treasury_wallets()
        elif args.command == "top-up":
            _require_auth(Permission.TOP_UP)
            result = ledger.top_up(args.treasury_wallet_id, args.target_wallet_id, args.amount, reference=args.reference)
            mutate = True

        # ── Permission management ──
        elif args.command == "grant-permission":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.grant_role_permission(args.role, args.permission)
            mutate = True
        elif args.command == "revoke-permission":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.revoke_role_permission(args.role, args.permission)
            mutate = True
        elif args.command == "grant-user-permission":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.grant_user_permission(args.user_id, args.permission)
            mutate = True
        elif args.command == "revoke-user-permission":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.revoke_user_permission(args.user_id, args.permission)
            mutate = True
        elif args.command == "list-role-permissions":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.list_role_permissions(args.role)
        elif args.command == "list-user-permissions":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.list_user_permissions(args.user_id)
        elif args.command == "reset-role-permissions":
            _require_auth(Permission.MANAGE_PERMISSIONS)
            result = ledger.reset_role_permissions(args.role)
            mutate = True

        # ── Moderation commands ──
        elif args.command == "freeze-wallet":
            _require_auth(Permission.FREEZE_WALLET)
            result = ledger.freeze_wallet(args.wallet_id)
            mutate = True
        elif args.command == "unfreeze-wallet":
            _require_auth(Permission.UNFREEZE_WALLET)
            result = ledger.unfreeze_wallet(args.wallet_id)
            mutate = True
        elif args.command == "ban-user":
            _require_auth(Permission.BAN_USER)
            result = ledger.ban_user(args.user_id)
            mutate = True
        elif args.command == "unban-user":
            _require_auth(Permission.UNBAN_USER)
            result = ledger.unban_user(args.user_id, unfreeze_wallets=args.unfreeze_wallets)
            mutate = True

        # ── User management commands ──
        elif args.command == "update-user":
            _require_auth(Permission.UPDATE_USER)
            result = ledger.update_user(args.user_id, new_user_id=args.new_user_id or None, new_display_name=args.new_display_name or None)
            mutate = True
        elif args.command == "delete-user":
            _require_auth(Permission.DELETE_USER)
            result = ledger.delete_user(args.user_id)
            mutate = True
        elif args.command == "restore-user":
            _require_auth(Permission.RESTORE_USER)
            result = ledger.restore_user(args.user_id, unfreeze_wallets=args.unfreeze_wallets)
            mutate = True
        elif args.command == "generate-temp-password":
            _require_auth(Permission.GENERATE_TEMP_PASSWORD)
            result = ledger.generate_temp_password_for_user(args.user_id)
            mutate = True
        elif args.command == "change-password":
            payload = _require_auth(Permission.TRANSFER)
            caller_id = payload.get("sub", "")
            result = ledger.change_password(caller_id, args.current_password, args.new_password)
            mutate = True
        elif args.command == "list-audit-log":
            _require_auth(Permission.VIEW_AUDIT_LOG)
            result = ledger.list_audit_log(limit=args.limit, user_id=args.user_id, action=args.action)

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
        elif args.command == "list-transfers":
            payload = _require_auth(Permission.VIEW_TRANSFERS)
            scope = ledger.build_transfer_access_scope(
                actor_user_id=payload.get("sub", ""),
                actor_roles=payload.get("roles", []),
            )
            query = TransferListQuery(
                limit=args.limit,
                wallet_id=args.wallet_id,
                user_id=args.user_id,
                transfer_type=args.transfer_type,
                transfer_id=args.transfer_id,
            )
            result = ledger.list_transfers_scoped(query, scope)
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
