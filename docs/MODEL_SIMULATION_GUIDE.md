# Guia de Simulacion y Operacion — v2.8.0

## Objetivo principal

Replicar con ejemplos reales el comportamiento de los dos modelos blockchain del repositorio (UTXO y Account-based) y operar el sistema multiusuario de wallets con todos sus features activos hasta v2.8.0.

---

## Simulador de modelos blockchain

### Script principal

```bash
py scripts/blockchain_models_simulator.py
```

### Escenarios incluidos

| Escenario | Descripcion |
|-----------|-------------|
| `coffee-export` | Trazabilidad de lote de cafe: certificados, eventos logisticos, transferencias, fees, auditoria de compliance |
| `retail-payments` | Pagos minoristas: multiples transferencias, confirmaciones por bloque, costos de red (validator pool) |

### Ejecucion del simulador

```bash
# Comparar ambos modelos
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both

# Solo UTXO o Account
py scripts/blockchain_models_simulator.py --scenario retail-payments --model utxo
py scripts/blockchain_models_simulator.py --scenario retail-payments --model account

# Salida JSON
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --json

# Persistir corridas
py scripts/blockchain_models_simulator.py --scenario coffee-export --model both --persist

# Listar corridas guardadas
py scripts/blockchain_models_simulator.py --list-runs --run-model both
py scripts/blockchain_models_simulator.py --list-runs --run-model utxo --limit 10

# Ver detalle de corrida
py scripts/blockchain_models_simulator.py --show-run-id <RUN_ID> --run-model account

# Directorio personalizado
py scripts/blockchain_models_simulator.py --scenario coffee-export --model account --persist --store-dir data/my-runs
```

### Archivos de persistencia del simulador

- `data/simulation-runs/utxo-runs.json`
- `data/simulation-runs/account-runs.json`

### Metricas por corrida

| Campo | Descripcion |
|-------|-------------|
| `execution_ms` | Tiempo de ejecucion en milisegundos |
| `total_events` | Total de eventos procesados |
| `total_transactions` | Total de transacciones |
| `pending_transactions` | Transacciones pendientes |
| `confirmed_transactions` | Transacciones confirmadas |
| `finalized_transactions` | Transacciones finalizadas |
| `chain_height` | Altura de la cadena |
| `state_items` | Items en el estado final |

---

## Terminal interactivo

```bash
py scripts/multiuser_terminal.py
```

### Secciones del menu (v2.8.0)

| # | Comando | Seccion | Descripcion |
|---|---------|---------|-------------|
| 1 | create-user | Usuarios & Wallets | Registrar nuevo usuario (ID auto-generado USR-XXXXX) |
| 2 | create-wallet | Usuarios & Wallets | Crear wallet UTXO o ACCOUNT |
| 9 | refresh-token | Usuarios & Wallets | Renovar token de autenticacion |
| 12 | list-users | Usuarios & Wallets | Listar usuarios registrados |
| 13 | balance | Usuarios & Wallets | Consultar balance de wallet |
| 3 | mint | Transacciones | Emitir tokens a wallet |
| 4 | transfer | Transacciones | Transferir fondos (con preview cross-currency) |
| 10 | transfer-wizard | Transacciones | Asistente guiado con confirmacion y preview de conversion |
| 14 | set-policy | Politicas & Riesgo | Configurar politica de transferencia |
| 15 | get-policy | Politicas & Riesgo | Ver politica de un usuario |
| 16 | list-policies | Politicas & Riesgo | Listar todas las politicas |
| 17 | set-risk-profile | Politicas & Riesgo | Asignar perfil de riesgo |
| 18 | get-risk-profile | Politicas & Riesgo | Ver perfil de riesgo |
| 19 | list-risk-profiles | Politicas & Riesgo | Listar perfiles de riesgo |
| 20 | list-alerts | Politicas & Riesgo | Ver alertas generadas |
| 5 | list-wallets | Consultas | Listar wallets |
| 6 | list-utxos | Consultas | Listar UTXOs |
| 7 | verify-integrity | Consultas | Verificar nonce + hash-chain |
| 8 | snapshot | Consultas | Estado completo del ledger |
| 21 | list-revisions | Consultas | Historial de revisiones |
| 22 | set-exchange-rate | Exchange | Configurar tasa de cambio con comision |
| 23 | list-exchange-rates | Exchange | Listar tasas de cambio activas |
| 24 | convert | Exchange | Previsualizar conversion de divisa |
| 25 | create-treasury-wallet | Tesoreria | Crear wallet de tesoreria por divisa |
| 26 | list-treasury-wallets | Tesoreria | Listar wallets de tesoreria |
| 27 | top-up | Tesoreria | Fondear wallet desde tesoreria |
| 28 | grant-permission | Permisos | Otorgar permiso a un rol |
| 29 | revoke-permission | Permisos | Revocar permiso a un rol |
| 30 | list-role-permissions | Permisos | Listar permisos de un rol |
| 31 | reset-role-permissions | Permisos | Resetear permisos de un rol a defaults |
| 32 | grant-user-permission | Permisos | Otorgar permiso especifico a usuario |
| 33 | revoke-user-permission | Permisos | Revocar permiso especifico de usuario |
| 34 | list-user-permissions | Permisos | Listar permisos de usuario |
| 35 | freeze-wallet | Moderacion | Congelar wallet(s) de usuario |
| 36 | unfreeze-wallet | Moderacion | Descongelar wallet(s) de usuario |
| 37 | ban-user | Moderacion | Banear usuario (congela wallets automaticamente) |
| 38 | unban-user | Moderacion | Desbanear usuario (opcion de descongelar) |
| 39 | update-user | Gestion de usuarios | Modificar ID o nombre de usuario |
| 40 | delete-user | Gestion de usuarios | Eliminar usuario (soft delete) |
| 41 | restore-user | Gestion de usuarios | Restaurar usuario eliminado |
| 42 | generate-temp-password | Gestion de usuarios | Generar password temporal |
| 43 | list-audit-log | Gestion de usuarios | Ver log de auditoria |
| 44 | change-password | Sistema | Cambiar mi contrasena |
| 45 | update-profile | Sistema | Actualizar mi perfil |
| 11 | dashboard | Sistema | Metricas de sesion actual |
| 0 | exit | Sistema | Salir del terminal |

### Secuencia recomendada (primer uso)

1. **Crear usuario ADMIN** (opcion 1) — guarda el `auth_token`.
2. **Crear wallets** (opcion 2) — guarda el `wallet_token`.
3. **Fondear con mint** (opcion 3) — requiere token de usuario.
4. **Configurar tasa de cambio** (opcion 22) — si necesitas exchange.
5. **Crear treasury wallet** (opcion 25) si usaras top-up.
6. **Transferir** (opcion 4 o 10 wizard) — requiere wallet_token y nonce.
7. **Verificar integridad** (opcion 7) y **snapshot** (opcion 8).
8. **Consultar audit log** (opcion 43) para revisar todas las acciones.

### Comportamientos especiales del terminal

- **Banner CUENTA SUSPENDIDA**: aparece si el usuario intenta login con cuenta baneada o eliminada.
- **Forced password change**: si `must_change_password: true`, el terminal bloquea el menu y exige cambio de password antes de continuar.
- **Sudo re-validacion**: las secciones Moderacion (35-38) y Gestion (39-42) requieren introducir de nuevo las credenciales de ADMIN con JWT. Se permiten 3 intentos; palabra clave `refresh` para re-autenticar con nuevo token.
- **Transfer-wizard**: para pares cross-currency muestra desglose completo (monto bruto, comision, monto neto) antes de confirmar.

---

## CLI paso a paso (multiusuario, v2.8.0)

### 0. Preparacion

```bash
# Reset para corrida limpia (opcional)
bash scripts/reset_persistence_json.sh

# Ver todos los subcomandos disponibles
py scripts/multiuser_wallet_cli.py --help
```

### 1. Crear usuarios

```bash
# ADMIN (primer usuario del sistema)
py scripts/multiuser_wallet_cli.py create-user \
  --display-name "Admin Principal" \
  --email admin@empresa.com \
  --username adminppal \
  --role ADMIN \
  --password "SecurePass123!" --json

# OPERATOR (el user_id se auto-genera como USR-00002)
py scripts/multiuser_wallet_cli.py create-user \
  --display-name "Operador 1" \
  --email op1@empresa.com \
  --username op1 \
  --role OPERATOR \
  --password "Pass456!" --json
```

### 2. Login y obtencion de token

```bash
# Acepta user_id o username como identificador
py scripts/multiuser_wallet_cli.py login \
  --identifier adminppal \
  --password "SecurePass123!" --json
# Guarda el token retornado como ADMIN_TOKEN
```

### 3. Crear wallets

```bash
py scripts/multiuser_wallet_cli.py create-wallet \
  --wallet-id wallet_admin_usd_01 \
  --model UTXO \
  --currency USD \
  --token ADMIN_TOKEN --json
# Guarda el auth_token de la wallet como WALLET_TOKEN
```

### 4. Fondear con mint

```bash
py scripts/multiuser_wallet_cli.py mint \
  --wallet-id wallet_admin_usd_01 \
  --amount 10000 \
  --token ADMIN_TOKEN --json
```

### 5. Configurar exchange y tesoreria

```bash
# Configurar tasa USD -> EUR con 1% de comision
py scripts/multiuser_wallet_cli.py set-exchange-rate \
  --from-currency USD --to-currency EUR \
  --rate 0.92 --commission 0.01 \
  --token ADMIN_TOKEN

# Crear wallet de tesoreria
py scripts/multiuser_wallet_cli.py create-treasury-wallet \
  --currency USD --token ADMIN_TOKEN --json

# Top-up desde tesoreria
py scripts/multiuser_wallet_cli.py top-up \
  --wallet-id wallet_op_eur_01 \
  --amount 500 \
  --currency USD \
  --token ADMIN_TOKEN --json
```

### 6. Transferencia con sender-token y nonce

```bash
py scripts/multiuser_wallet_cli.py transfer \
  --from-wallet wallet_admin_usd_01 \
  --to-wallet wallet_op_eur_01 \
  --amount 100 --fee 0.5 \
  --sender-token WALLET_TOKEN \
  --expected-nonce 1 --json
# Cross-currency: aplica tasa USD->EUR automaticamente
```

### 7. Gestion de usuarios (ADMIN)

```bash
# Generar password temporal para un usuario
py scripts/multiuser_wallet_cli.py generate-temp-password \
  --user-id USR-00002 --token ADMIN_TOKEN

# Soft delete (congela wallets)
py scripts/multiuser_wallet_cli.py delete-user \
  --user-id USR-00002 --token ADMIN_TOKEN

# Restaurar
py scripts/multiuser_wallet_cli.py restore-user \
  --user-id USR-00002 --token ADMIN_TOKEN

# Actualizar perfil propio
py scripts/multiuser_wallet_cli.py update-profile \
  --first-name "Admin" --last-name "Principal" \
  --token ADMIN_TOKEN
```

### 8. Moderacion

```bash
# Congelar todas las wallets de un usuario
py scripts/multiuser_wallet_cli.py freeze-wallet \
  --user-id USR-00002 --token ADMIN_TOKEN

# Banear usuario (congela wallets automaticamente)
py scripts/multiuser_wallet_cli.py ban-user \
  --user-id USR-00002 --token ADMIN_TOKEN

# Desbanear con descongelamiento opcional
py scripts/multiuser_wallet_cli.py unban-user \
  --user-id USR-00002 --token ADMIN_TOKEN
```

### 9. Permisos dinamicos

```bash
# Otorgar MINT a OPERATOR
py scripts/multiuser_wallet_cli.py grant-permission \
  --role OPERATOR --permission MINT --token ADMIN_TOKEN

# Permiso especifico para un usuario
py scripts/multiuser_wallet_cli.py grant-user-permission \
  --user-id USR-00003 --permission SET_EXCHANGE_RATE \
  --token ADMIN_TOKEN

# Listar permisos efectivos de un rol
py scripts/multiuser_wallet_cli.py list-role-permissions \
  --role OPERATOR --token ADMIN_TOKEN
```

### 10. Consultas y auditoria

```bash
# Balance
py scripts/multiuser_wallet_cli.py balance --wallet-id wallet_admin_usd_01 --json

# UTXOs
py scripts/multiuser_wallet_cli.py list-utxos --wallet-id wallet_admin_usd_01 --json

# Integridad
py scripts/multiuser_wallet_cli.py verify-integrity --json

# Snapshot completo
py scripts/multiuser_wallet_cli.py snapshot --json

# Audit log completo
py scripts/multiuser_wallet_cli.py list-audit-log --limit 100 --token ADMIN_TOKEN

# Filtrar por accion
py scripts/multiuser_wallet_cli.py list-audit-log --action TRANSFER --token ADMIN_TOKEN

# Filtrar por usuario
py scripts/multiuser_wallet_cli.py list-audit-log --user-id USR-00002 --token ADMIN_TOKEN
```

### 11. Cambiar password

```bash
py scripts/multiuser_wallet_cli.py change-password \
  --current-password "SecurePass123!" \
  --new-password "NewSecure456!" \
  --token ADMIN_TOKEN
```

---

## Tabla de actualizacion de persistencia

| Operacion | Actualiza JSON/PG | Notas |
|-----------|-------------------|-------|
| create-user | Si | Crea UserRecord + credentials |
| update-user | Si | Modifica user_id o display_name |
| delete-user | Si | Soft delete: set deleted_at |
| restore-user | Si | Limpia deleted_at |
| update-profile | Si | Actualiza campos de perfil |
| create-wallet | Si | Crea WalletRecord |
| freeze-wallet | Si | Set frozen=True |
| unfreeze-wallet | Si | Set frozen=False |
| ban-user | Si | Set banned=True + freeze wallets |
| unban-user | Si | Set banned=False |
| mint | Si | Agrega UTXO o incrementa balance |
| transfer | Si | Registra transferencia, actualiza UTXOs/balances |
| top-up | Si | Debita tesoreria, acredita destino |
| set-exchange-rate | Si | Actualiza par en exchange_rates |
| generate-temp-password | Si | Set password_temp=True, token_temp |
| change-password | Si | Actualiza hash, limpia password_temp |
| grant/revoke permission | Si | Actualiza overrides de permisos |
| login | Solo audit_log | No modifica wallets/users |
| balance, list-*, snapshot, verify | No | Solo lectura |

---

## Setup con PostgreSQL

### 1. Configurar .env

```bash
cp .env.example .env
# Editar con credenciales reales
```

### 2. Ejecutar migraciones

```bash
PYTHONPATH=. py migrations/migrate.py
```

Aplica V001-V009. El migrador maneja `ALTER TYPE ADD VALUE` con autocommit para compatibilidad PostgreSQL.

### 3. Verificar backend activo

El banner del terminal muestra:
- **Verde**: `PostgreSQL (blockchain_data_model)`
- **Amarillo**: `JSON (local files)`

### 4. Cambiar entre backends

```bash
PERSISTENCE_BACKEND=postgres py scripts/multiuser_terminal.py
PERSISTENCE_BACKEND=json py scripts/multiuser_terminal.py
```

Los datos de cada backend son independientes.

---

## Flujo de sincronizacion de ramas

```bash
# Verificar estado de todas las ramas
git fetch origin
for branch in main develop production staging qa; do
  echo "$branch: $(git log --oneline origin/$branch -1)"
done

# Promotion chain completo
GH_BIN="/c/Program Files/GitHub CLI/gh.exe" bash scripts/devsecops_promotion_chain.sh basic-blockchain blockchain-data-model

# Release completo desde develop
GH_BIN="/c/Program Files/GitHub CLI/gh.exe" bash scripts/devsecops_release_and_promote.sh basic-blockchain blockchain-data-model develop
```
