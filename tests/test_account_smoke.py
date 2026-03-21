from decimal import Decimal


def test_account_nonce_and_confirmations(account_module):
    chain = account_module.AccountBased_Blockchain(confirmations_required=2)
    assert "Cuenta creada" in chain.create_account("alice", 100)
    assert "Cuenta creada" in chain.create_account("bob", 0)

    msg = chain.send_transaction("alice", "bob", 10, fee=0.5, expected_nonce=0)
    assert "mempool" in msg

    tx = chain.transaction_history[-1]
    assert tx.status == "PENDING"
    assert tx.confirmations == 0
    assert chain.accounts["alice"].nonce == 1

    assert "Bloque 1" in chain.mine_block("miner_1")
    tx = chain.transaction_history[-1]
    assert tx.status == "CONFIRMED"
    assert tx.confirmations == 1

    # Forzamos una segunda transaccion para poder minar otro bloque y cerrar finality.
    chain.mint("alice", 1)
    assert "Bloque 2" in chain.mine_block("miner_2")
    tx = chain.tx_index[tx.tx_id]
    assert tx.status == "FINALIZED"
    assert tx.confirmations >= 2

    assert chain.get_balance("bob") == Decimal("10.00000000")


def test_account_compliance_pass(account_module):
    chain = account_module.AccountBased_Blockchain()
    chain.create_account("owner", 0)
    assert "registrado" in chain.register_lot("LOT-1", "owner", "Cafe", "Huila")
    assert "emitido" in chain.issue_certificate("LOT-1", "Fitosanitario", "ICA")

    chain.record_logistics_event("LOT-1", "COSECHA", "Finca", "Huila")
    chain.record_logistics_event("LOT-1", "PROCESAMIENTO", "Planta", "Neiva")
    chain.record_logistics_event("LOT-1", "EXPORTACION", "Puerto", "Buenaventura")

    report = chain.audit_compliance("LOT-1")
    assert report["status"] == "PASS"


def test_account_compliance_profile_for_cacao(account_module):
    chain = account_module.AccountBased_Blockchain()
    chain.create_account("owner", 0)
    chain.register_lot("LOT-CACAO-1", "owner", "CACAO", "Tumaco")
    chain.issue_certificate("LOT-CACAO-1", "Origen", "INVIMA")

    chain.record_logistics_event("LOT-CACAO-1", "COSECHA", "Finca", "Tumaco")
    chain.record_logistics_event("LOT-CACAO-1", "FERMENTACION", "Planta", "Tumaco")
    chain.record_logistics_event("LOT-CACAO-1", "EXPORTACION", "Puerto", "Buenaventura")

    report = chain.audit_compliance("LOT-CACAO-1")
    assert report["status"] == "PASS"
    assert "FERMENTACION" in report["required_events"]
