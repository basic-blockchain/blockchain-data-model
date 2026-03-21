class AccountBased_Blockchain:
    def __init__(self):
        # El estado es un diccionario: { "Dirección": Saldo }
        self.accounts = {}

    def create_account(self, address, initial_balance):
        self.accounts[address] = initial_balance

    def send_transaction(self, sender, receiver, amount):
        # 1. Verificar existencia y saldo
        if sender not in self.accounts or self.accounts[sender] < amount:
            return "Error: Transacción rechazada."

        # 2. Inicializar receptor si no existe
        if receiver not in self.accounts:
            self.accounts[receiver] = 0

        # 3. Actualizar estados (Lógica de Smart Contract simple)
        self.accounts[sender] -= amount
        self.accounts[receiver] += amount
        
        return f"Transacción exitosa: {amount} transferidos."

# --- DEMO CUENTAS ---
print("\n--- SISTEMA DE CUENTAS ---")
agro_eth = AccountBased_Blockchain()
agro_eth.create_account("Exportador_Colombia", 100)
print(f"Estado inicial: {agro_eth.accounts}")

# Transferencia directa
status = agro_eth.send_transaction("Exportador_Colombia", "Logistica_Latam", 30)
print(status)
print(f"Estado final: {agro_eth.accounts}")