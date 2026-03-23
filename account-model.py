import time
from dataclasses import asdict, dataclass
from decimal import Decimal, getcontext

from domain.blockchain_base import BaseBlockchain, Block, WalletKeys  # noqa: F401
from domain.compliance import resolve_profile
from domain.precision import UNIT, normalize_amount  # noqa: F401 — UNIT re-exported
from domain.traceability_models import TraceabilityLot

getcontext().prec = 28


@dataclass
class AccountState:
    balance: Decimal
    nonce: int
    created_at: str
    public_key: str


@dataclass
class AccountTransaction:
    tx_id: str
    sender: str
    receiver: str
    amount: Decimal
    fee: Decimal
    nonce: int
    status: str
    timestamp: str
    signer_public_key: str
    signature: str
    block_height: int | None = None
    confirmations: int = 0


class AccountBased_Blockchain(BaseBlockchain):
    def __init__(self, confirmations_required=2, max_txs_per_block=10):
        # Estado global de cuentas con control de nonce por dirección.
        self.accounts = {}
        super().__init__(confirmations_required=confirmations_required, max_txs_per_block=max_txs_per_block)

    def create_account(self, address, initial_balance=0):
        if not self._is_valid_address(address):
            return "Error: Dirección inválida."
        if address in self.accounts:
            return f"Aviso: La cuenta {address} ya existe."

        balance = normalize_amount(initial_balance)
        if balance < 0:
            return "Error: Saldo inicial inválido."

        wallet = self._ensure_wallet(address)
        self.accounts[address] = AccountState(
            balance=balance,
            nonce=0,
            created_at=self._timestamp(),
            public_key=wallet.public_key,
        )
        return f"Cuenta creada: {address} con saldo {balance}."

    def mint(self, receiver, amount):
        minted = normalize_amount(amount)
        if minted <= 0 or not self._is_valid_address(receiver):
            return "Error: Datos inválidos para mint."

        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        self.accounts[receiver].balance += minted
        tx_payload = {
            "type": "mint",
            "receiver": receiver,
            "amount": str(minted),
            "ts": time.time_ns(),
        }
        public_key, signature = self._sign_payload(receiver, tx_payload)
        if not self._verify_signature(public_key, tx_payload, signature):
            return "Error: Firma digital inválida en mint."

        tx_id = self._build_tx_id(tx_payload)
        tx_record = AccountTransaction(
            tx_id=tx_id,
            sender="TREASURY",
            receiver=receiver,
            amount=minted,
            fee=Decimal("0"),
            nonce=-1,
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key=public_key,
            signature=signature,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)
        return f"Mint confirmado: {minted} para {receiver}."

    def send_transaction(self, sender, receiver, amount, fee=0, expected_nonce=None):
        transfer_amount = normalize_amount(amount)
        tx_fee = normalize_amount(fee)

        if not self._is_valid_address(sender) or not self._is_valid_address(receiver):
            return "Error: Dirección inválida."
        if sender == receiver:
            return "Error: Sender y receiver deben ser distintos."
        if transfer_amount <= 0:
            return "Error: El monto debe ser mayor a cero."
        if tx_fee < 0:
            return "Error: La comisión no puede ser negativa."
        if sender not in self.accounts:
            return "Error: La cuenta emisora no existe."
        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        sender_state = self.accounts[sender]
        receiver_state = self.accounts[receiver]

        if expected_nonce is not None and expected_nonce != sender_state.nonce:
            return (
                f"Error: Nonce inválido. Esperado={sender_state.nonce}, "
                f"Recibido={expected_nonce}."
            )

        total_cost = transfer_amount + tx_fee
        if sender_state.balance < total_cost:
            return (
                f"Error: Fondos insuficientes. Disponible={sender_state.balance}, "
                f"Requerido={total_cost}."
            )

        next_nonce = sender_state.nonce + 1

        tx_payload = {
            "type": "transfer",
            "sender": sender,
            "receiver": receiver,
            "amount": str(transfer_amount),
            "fee": str(tx_fee),
            "nonce": next_nonce,
            "ts": time.time_ns(),
        }
        public_key, signature = self._sign_payload(sender, tx_payload)
        if sender_state.public_key != public_key:
            return "Error: La llave pública no coincide con la cuenta emisora."
        if not self._verify_signature(public_key, tx_payload, signature):
            return "Error: Firma digital inválida en transferencia."

        sender_state.balance -= total_cost
        sender_state.nonce = next_nonce
        receiver_state.balance += transfer_amount
        self.validator_pool += tx_fee

        tx_id = self._build_tx_id(tx_payload)

        tx_record = AccountTransaction(
            tx_id=tx_id,
            sender=sender,
            receiver=receiver,
            amount=transfer_amount,
            fee=tx_fee,
            nonce=sender_state.nonce,
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key=public_key,
            signature=signature,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)

        return (
            f"Transacción aceptada en mempool: {transfer_amount} de {sender} a {receiver}. "
            f"Fee={tx_fee}. Nonce={sender_state.nonce}."
        )

    def register_lot(self, lot_id, owner, product, origin):
        if lot_id in self.lots:
            return "Error: El lote ya existe."
        if not all(
            [
                self._is_valid_address(lot_id),
                self._is_valid_address(owner),
                self._is_valid_address(product),
                self._is_valid_address(origin),
            ]
        ):
            return "Error: Datos inválidos para lote."

        if owner not in self.accounts:
            self.create_account(owner, 0)

        profile = resolve_profile(product, custom_profiles=self.compliance_profiles)

        self.lots[lot_id] = TraceabilityLot(
            lot_id=lot_id,
            product=product,
            origin=origin,
            owner=owner,
            created_at=self._timestamp(),
            certificate_ids=[],
            event_ids=[],
            required_events=profile["required_events"],
            min_active_certificates=profile["min_active_certificates"],
        )
        return f"Lote {lot_id} registrado para {owner}."

    def transfer_lot(self, lot_id, sender, receiver):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."
        if lot.owner != sender:
            return "Error: El sender no es propietario del lote."
        if not self._is_valid_address(receiver):
            return "Error: Receiver inválido."

        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        lot.owner = receiver
        return f"Lote {lot_id} transferido de {sender} a {receiver}."

    def get_balance(self, address):
        if address not in self.accounts:
            return Decimal("0")
        return self.accounts[address].balance

    def state_snapshot(self):
        return {address: asdict(state) for address, state in self.accounts.items()}


if __name__ == "__main__":
    print("\n--- SISTEMA DE MODELO DE CUENTAS - ITERACION 2 ---")
    agro_eth = AccountBased_Blockchain(confirmations_required=2, max_txs_per_block=5)
    print(agro_eth.create_wallet("Exportador_Colombia")[0])
    print(agro_eth.create_wallet("Logistica_Latam")[0])
    print(agro_eth.create_wallet("Aduana_Pacifico")[0])
    print(agro_eth.create_account("Exportador_Colombia", 100))
    print(agro_eth.create_account("Logistica_Latam", 0))
    print(agro_eth.register_lot("Lote_Cafe_001", "Exportador_Colombia", "Cafe Arabe", "Huila_Colombia"))
    print(agro_eth.issue_certificate("Lote_Cafe_001", "Fitosanitario", "ICA"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "COSECHA", "Cooperativa_Huila", "Finca_El_Roble"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "PROCESAMIENTO", "Planta_Trillado", "Neiva"))

    status_1 = agro_eth.send_transaction(
        "Exportador_Colombia", "Logistica_Latam", 30, fee=0.15, expected_nonce=0
    )
    print(status_1)

    status_2 = agro_eth.send_transaction(
        "Exportador_Colombia", "Aduana_Pacifico", 20, fee=0.10, expected_nonce=1
    )
    print(status_2)
    print(agro_eth.mine_block("Nodo_Validador_1"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "EXPORTACION", "Puerto_Buenaventura", "Buenaventura"))
    print(agro_eth.mine_block("Nodo_Validador_2"))
    print(agro_eth.transfer_lot("Lote_Cafe_001", "Exportador_Colombia", "Aduana_Pacifico"))
    print("Auditoria compliance:", agro_eth.audit_compliance("Lote_Cafe_001"))

    print("Balance Exportador:", agro_eth.get_balance("Exportador_Colombia"))
    print("Balance Logistica:", agro_eth.get_balance("Logistica_Latam"))
    print("Balance Aduana:", agro_eth.get_balance("Aduana_Pacifico"))
    print("Altura cadena:", len(agro_eth.blocks) - 1)
    print("Pool de validadores:", agro_eth.validator_pool)
    print("Estado final:", agro_eth.state_snapshot())
