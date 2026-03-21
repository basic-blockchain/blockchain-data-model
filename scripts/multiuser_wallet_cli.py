#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data" / "multiuser" / "wallet-ledger.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from persistence.factory import create_wallet_store
from persistence.interfaces import WalletLedgerRepository


def _supports_ansi() -> bool:
    return sys.stdout.isatty() and sys.stderr.isatty()


def _style(text: str, code: str) -> str:
    if not _supports_ansi():
        return text
    return f"\033[{code}m{text}\033[0m"


def _wrap_lines(text: str, width: int) -> list[str]:
    """Break text into lines that fit within the given width."""
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


def _print_alert(kind: str, title: str, message: str | None = None, *, stream=None) -> None:
    color = "1;31" if kind == "ERROR" else "1;32"
    out = stream if stream is not None else sys.stdout
    header = f"[{kind}] {title}"
    inner_width = 74
    border = _style("+" + "-" * (inner_width + 2) + "+", color)
    print(border, file=out)
    for line in _wrap_lines(header, inner_width):
        print(_style(f"| {line:<{inner_width}} |", color), file=out)
    if message:
        body = f"Mensaje: {message}"
        for line in _wrap_lines(body, inner_width):
            print(_style(f"| {line:<{inner_width}} |", color), file=out)
    print(border, file=out)


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
    raise argparse.ArgumentTypeError("Valor inválido para booleano. Use true/false.")


def main() -> None:
    parser = CliArgumentParser(description="Multi-user wallet ledger CLI")
    parser.add_argument("--store-file", default=str(DEFAULT_STORE), help="Path to the JSON ledger store")
    parser.add_argument("--json", action="store_true", help="JSON output mode")

    subparsers = parser.add_subparsers(dest="command", required=True)

    cmd_user = subparsers.add_parser("create-user", help="Create a user")
    _add_json_flag(cmd_user)
    cmd_user.add_argument("--user-id", required=True)
    cmd_user.add_argument("--display-name", required=True)

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

    cmd_balance = subparsers.add_parser("balance", help="Get wallet balance")
    _add_json_flag(cmd_balance)
    cmd_balance.add_argument("--wallet-id", required=True)

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

    cmd_verify_integrity = subparsers.add_parser(
        "verify-integrity",
        help="Verify transfer nonce and hash-chain integrity",
    )
    _add_json_flag(cmd_verify_integrity)

    args = parser.parse_args()
    store_file = Path(args.store_file)
    output_json = bool(args.json or getattr(args, "cmd_json", False))

    try:
        store, ledger = _load_ledger(store_file)

        mutate = False
        result: dict | list | str

        if args.command == "create-user":
            result = ledger.create_user(args.user_id, args.display_name)
            mutate = True
        elif args.command == "create-wallet":
            result = ledger.create_wallet(
                args.user_id,
                wallet_id=args.wallet_id,
                currency=args.currency,
                model=args.model,
            )
            mutate = True
        elif args.command == "refresh-token":
            result = ledger.refresh_wallet_token(
                args.user_id,
                args.wallet_id,
                current_token=args.current_token,
            )
            mutate = True
        elif args.command == "mint":
            result = ledger.mint(args.wallet_id, args.amount, reference=args.reference)
            mutate = True
        elif args.command == "transfer":
            result = ledger.transfer(
                args.from_wallet,
                args.to_wallet,
                args.amount,
                fee=args.fee,
                reference=args.reference,
                sender_token=args.sender_token,
                expected_nonce=getattr(args, "expected_nonce", None),
            )
            mutate = True
        elif args.command == "balance":
            result = {
                "wallet_id": args.wallet_id,
                "balance": str(ledger.get_wallet_balance(args.wallet_id)),
            }
        elif args.command == "list-users":
            result = ledger.list_users()
        elif args.command == "list-wallets":
            result = ledger.list_wallets(user_id=args.user_id)
        elif args.command == "list-utxos":
            result = ledger.list_utxos(wallet_id=args.wallet_id)
        elif args.command == "snapshot":
            result = ledger.state_snapshot()
        elif args.command == "list-revisions":
            result = store.list_revisions(limit=args.limit)
        elif args.command == "set-policy":
            can_transfer = args.can_transfer if hasattr(args, "can_transfer") else None
            daily_limit = args.daily_limit if getattr(args, "daily_limit", None) is not None else None
            result = ledger.set_user_policy(
                args.user_id,
                can_transfer=can_transfer,
                daily_limit=daily_limit,
            )
            mutate = True
        elif args.command == "get-policy":
            result = ledger.get_user_policy(args.user_id)
        elif args.command == "list-policies":
            result = ledger.list_user_policies()
        elif args.command == "set-risk-profile":
            result = ledger.set_user_risk_profile(
                args.user_id,
                profile_name=getattr(args, "profile_name", None),
                daily_limit=getattr(args, "daily_limit", None),
                transfer_alert_threshold=getattr(args, "transfer_alert_threshold", None),
                daily_alert_threshold=getattr(args, "daily_alert_threshold", None),
            )
            mutate = True
        elif args.command == "get-risk-profile":
            result = ledger.get_user_risk_profile(args.user_id)
        elif args.command == "list-risk-profiles":
            result = ledger.list_user_risk_profiles()
        elif args.command == "list-alerts":
            result = ledger.list_alerts(
                limit=args.limit,
                user_id=args.user_id,
                severity=args.severity,
            )
        elif args.command == "verify-integrity":
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
            if not success:
                _print_alert("ERROR", args.command, _compact_alert_message(result), stream=sys.stderr)
            else:
                _print_alert("SUCCESS", args.command, _compact_alert_message(result), stream=sys.stderr)
            payload = {
                "success": success,
                "result": result,
                "revision_id": revision_id,
                "store_file": str(store_file.resolve()),
            }
            _print_json(payload)
            sys.exit(0 if success else 1)

        if success:
            _print_alert("SUCCESS", args.command, _compact_alert_message(result))
            if revision_id:
                print(f"revision_id={revision_id}")
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
