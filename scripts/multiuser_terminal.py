#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data" / "multiuser" / "wallet-ledger.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from persistence.multiuser_wallet_store import JsonMultiUserWalletStore


def _load(store_file: Path):
    store = JsonMultiUserWalletStore(store_file)
    ledger = store.load_ledger()
    return store, ledger


def _persist(store, ledger):
    return store.save_ledger(ledger)


def _ask(label: str) -> str:
    return input(label).strip()


def main() -> None:
    store_file = DEFAULT_STORE
    print("Multiuser Terminal (ACCOUNT/UTXO)")
    print(f"Store: {store_file}")

    while True:
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
        print("0) exit")

        option = _ask("Option: ")
        store, ledger = _load(store_file)

        if option == "1":
            user_id = _ask("user_id: ")
            display_name = _ask("display_name: ")
            result = ledger.create_user(user_id, display_name)
            rev = _persist(store, ledger)
            print(result)
            print(f"revision_id={rev}")
        elif option == "2":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id (20-30, enter=auto): ")
            currency = _ask("currency (default USDX): ") or "USDX"
            model = (_ask("model ACCOUNT|UTXO (default ACCOUNT): ") or "ACCOUNT").upper()
            result = ledger.create_wallet(user_id, wallet_id=wallet_id, currency=currency, model=model)
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                continue
            rev = _persist(store, ledger)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"revision_id={rev}")
        elif option == "3":
            wallet_id = _ask("wallet_id: ")
            amount = _ask("amount: ")
            reference = _ask("reference (default MINT): ") or "MINT"
            result = ledger.mint(wallet_id, amount, reference=reference)
            rev = _persist(store, ledger)
            print(result)
            print(f"revision_id={rev}")
        elif option == "4":
            from_wallet = _ask("from_wallet: ")
            to_wallet = _ask("to_wallet: ")
            amount = _ask("amount: ")
            fee = _ask("fee (default 0): ") or "0"
            sender_token = _ask("sender_token: ")
            expected_nonce_raw = _ask("expected_nonce (optional): ")
            expected_nonce = int(expected_nonce_raw) if expected_nonce_raw else None
            result = ledger.transfer(
                from_wallet,
                to_wallet,
                amount,
                fee=fee,
                sender_token=sender_token,
                expected_nonce=expected_nonce,
            )
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                continue
            rev = _persist(store, ledger)
            print(result)
            print(f"revision_id={rev}")
        elif option == "5":
            user_id = _ask("user_id (optional): ")
            print(json.dumps(ledger.list_wallets(user_id=user_id), indent=2, ensure_ascii=False))
        elif option == "6":
            wallet_id = _ask("wallet_id (optional): ")
            print(json.dumps(ledger.list_utxos(wallet_id=wallet_id), indent=2, ensure_ascii=False))
        elif option == "7":
            print(json.dumps(ledger.verify_transfer_integrity(), indent=2, ensure_ascii=False))
        elif option == "8":
            print(json.dumps(ledger.state_snapshot(), indent=2, ensure_ascii=False))
        elif option == "9":
            user_id = _ask("user_id: ")
            wallet_id = _ask("wallet_id: ")
            current_token = _ask("current_token (optional): ")
            result = ledger.refresh_wallet_token(user_id, wallet_id, current_token=current_token)
            if isinstance(result, str) and result.startswith("Error:"):
                print(result)
                continue
            rev = _persist(store, ledger)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"revision_id={rev}")
        elif option == "0":
            print("Bye")
            break
        else:
            print("Invalid option")


if __name__ == "__main__":
    main()
