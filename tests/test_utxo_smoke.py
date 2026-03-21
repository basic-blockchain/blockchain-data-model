from decimal import Decimal


def test_utxo_flow_and_confirmations(utxo_module):
    chain = utxo_module.UTXO_Blockchain(confirmations_required=2)

    assert "Wallet creada" in chain.create_wallet("alice")[0]
    assert "Wallet creada" in chain.create_wallet("bob")[0]
    assert "Emision" in chain.mint_initial_coins(100, "alice").replace("ó", "o")

    msg = chain.send_transaction("alice", "bob", 25, fee=0.25)
    assert "mempool" in msg
    tx = chain.transaction_history[-1]
    assert tx.status == "PENDING"

    assert "Bloque 1" in chain.mine_block("miner_1")
    tx = chain.tx_index[tx.tx_id]
    assert tx.status == "CONFIRMED"

    # Transaccion de relleno para habilitar nuevo bloque y alcanzar finality.
    chain.mint_initial_coins(1, "alice")
    assert "Bloque 2" in chain.mine_block("miner_2")
    tx = chain.tx_index[tx.tx_id]
    assert tx.status == "FINALIZED"

    assert chain.get_balance("bob") == Decimal("25.00000000")


def test_utxo_compliance_pass(utxo_module):
    chain = utxo_module.UTXO_Blockchain()
    chain.register_lot("LOT-UTXO-1", "owner", "Cafe", "Huila", 100)
    chain.issue_certificate("LOT-UTXO-1", "Fitosanitario", "ICA")
    chain.record_logistics_event("LOT-UTXO-1", "COSECHA", "Finca", "Huila")
    chain.record_logistics_event("LOT-UTXO-1", "PROCESAMIENTO", "Planta", "Neiva")
    chain.record_logistics_event("LOT-UTXO-1", "EXPORTACION", "Puerto", "Buenaventura")

    report = chain.audit_compliance("LOT-UTXO-1")
    assert report["status"] == "PASS"
