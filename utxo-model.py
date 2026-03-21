import hashlib
import json

class UTXO:
    def __init__(self, tx_id, amount, owner):
        self.tx_id = tx_id
        self.amount = amount
        self.owner = owner

    def __repr__(self):
        return f"[TX:{self.tx_id[:6]} | {self.amount} BTC -> {self.owner}]"

class UTXO_Blockchain:
    def __init__(self):
        # El "Libro Mayor" son solo salidas que no se han gastado
        self.unspent_outputs = []

    def mint_initial_coins(self, amount, owner):
        """Simula la creación inicial de monedas (Coinbase)"""
        new_utxo = UTXO("genesis_tx", amount, owner)
        self.unspent_outputs.append(new_utxo)

    def send_transaction(self, sender, receiver, amount_to_send):
        # 1. Buscar UTXOs que pertenezcan al sender y sumen lo necesario
        sender_utxos = [u for u in self.unspent_outputs if u.owner == sender]
        total_available = sum(u.amount for u in sender_utxos)

        if total_available < amount_to_send:
            return "Error: Fondos insuficientes."

        # 2. "Gastar" los UTXOs antiguos (eliminarlos de la lista)
        for u in sender_utxos:
            self.unspent_outputs.remove(u)

        # 3. Crear el nuevo UTXO para el receptor
        tx_id = hashlib.sha256(str(amount_to_send).encode()).hexdigest()
        self.unspent_outputs.append(UTXO(tx_id, amount_to_send, receiver))

        # 4. Crear el UTXO de "Cambio" (Refund) para el sender
        change = total_available - amount_to_send
        if change > 0:
            self.unspent_outputs.append(UTXO(tx_id + "_change", change, sender))
        
        return f"Transacción exitosa: {amount_to_send} enviados a {receiver}"

# --- DEMO UTXO ---
print("--- SISTEMA UTXO ---")
agro_bolsa = UTXO_Blockchain()
agro_bolsa.mint_initial_coins(100, "Exportador_Colombia")
print(f"Estado inicial: {agro_bolsa.unspent_outputs}")

# El exportador envía 30 a un transportista
status = agro_bolsa.send_transaction("Exportador_Colombia", "Logistica_Latam", 30)
print(status)
print(f"Estado final (Nótese el cambio de 70): {agro_bolsa.unspent_outputs}")