from decimal import Decimal

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def test_create_users_wallets_and_transfer_flow():
    ledger = MultiUserWalletLedger()

    assert "creado" in ledger.create_user("u-alice", "Alice")
    assert "creado" in ledger.create_user("u-bob", "Bob")

    msg_wallet_a = ledger.create_wallet("u-alice", wallet_id="w-alice")
    msg_wallet_b = ledger.create_wallet("u-bob", wallet_id="w-bob")
    assert "creada" in msg_wallet_a
    assert "creada" in msg_wallet_b

    assert "Mint" in ledger.mint("w-alice", "100")
    assert ledger.get_wallet_balance("w-alice") == Decimal("100.00000000")

    tx = ledger.transfer("w-alice", "w-bob", "24.5", fee="0.5", reference="invoice-001")
    assert "Transferencia" in tx

    assert ledger.get_wallet_balance("w-alice") == Decimal("75.00000000")
    assert ledger.get_wallet_balance("w-bob") == Decimal("24.50000000")
    assert len(ledger.state_snapshot()["transfers"]) == 2


def test_transfer_rejects_insufficient_balance():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    ledger.create_wallet("u-a", wallet_id="wa")
    ledger.create_wallet("u-b", wallet_id="wb")
    ledger.mint("wa", "1")

    error = ledger.transfer("wa", "wb", "2", fee="0")
    assert "Fondos insuficientes" in error or "fondos insuficientes" in error
