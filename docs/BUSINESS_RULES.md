# Reglas de Negocio — blockchain-data-model

> Documento de referencia técnica. Cubre todas las reglas de negocio, validaciones,
> restricciones, flujos y contratos del sistema a partir de la versión v2.8.2.

---

## Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Modelo UTXO vs Modelo Account](#2-modelo-utxo-vs-modelo-account)
3. [Gestión Multi-Usuario de Wallets](#3-gestión-multi-usuario-de-wallets)
4. [Exchange (Conversión de Divisas)](#4-exchange-conversión-de-divisas)
5. [Políticas y Perfiles de Riesgo](#5-políticas-y-perfiles-de-riesgo)
6. [RBAC — Roles y Permisos](#6-rbac--roles-y-permisos)
7. [Gestión de Contraseñas y JWT](#7-gestión-de-contraseñas-y-jwt)
8. [Ciclo de Vida de Usuario](#8-ciclo-de-vida-de-usuario)
9. [Audit Log](#9-audit-log)
10. [Compliance y Trazabilidad de Cadena de Suministro](#10-compliance-y-trazabilidad-de-cadena-de-suministro)
11. [Precisión Monetaria](#11-precisión-monetaria-regla-universal)
12. [Persistencia](#12-persistencia)
13. [Escenarios del Simulador](#13-escenarios-del-simulador)
14. [Resumen de Reglas Críticas](#14-resumen-de-reglas-de-negocio-críticas)

---

## 1. Arquitectura General

El proyecto simula dos modelos blockchain complementarios con una capa de gestión multi-usuario encima.

| Capa | Componente | Propósito |
|------|-----------|----------|
| Blockchain base | `utxo-model.py`, `account-model.py` | Dos modelos de libro mayor con firmas digitales, bloques y confirmaciones |
| Ledger multi-usuario | `domain/multiuser_wallet_ledger.py` | Wallets, usuarios, transferencias, políticas, RBAC, auditoría |
| Auth & RBAC | `domain/auth.py` | Roles, permisos, bcrypt, JWT, tokens temporales |
| Exchange | `domain/exchange.py` | Conversión entre divisas con comisión |
| Compliance | `domain/compliance.py` | Evaluación de cumplimiento por lote de producto |
| Traceability | `domain/traceability_models.py` | Cadena de suministro (lotes, certificados, eventos logísticos) |
| Precisión | `domain/precision.py` | `UNIT = Decimal("0.00000001")` — fuente única de precisión monetaria |
| UTXO ops | `domain/utxo_operations.py` | Funciones puras de selección y manipulación de UTXOs |
| Blockchain base | `domain/blockchain_base.py` | BaseBlockchain con 18 métodos compartidos entre modelos |
| Persistencia | `persistence/` | Backends intercambiables: JSON y PostgreSQL |

---

## 2. Modelo UTXO vs Modelo Account

### 2.1 Modelo UTXO

Cada unidad de dinero existe como un **UTXO** (Unspent Transaction Output). Las transacciones consumen UTXOs completos y producen nuevos.

#### Estructura de datos

**UTXO**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `utxo_id` | str | `{tx_id}:{output_index}` — índice 0 = receptor, 1 = cambio |
| `tx_id` | str | ID de la transacción que creó este UTXO |
| `output_index` | int | Posición en los outputs de la transacción |
| `amount` | Decimal | Cantidad normalizada a 8 decimales |
| `owner` | str | Dirección que controla este UTXO |
| `created_at` | str | ISO8601 timestamp |
| `lot_id` | str | (opcional) Vincula el UTXO a un lote de trazabilidad |
| `metadata` | dict | (opcional) Metadatos del evento: `{"event": "transfer"/"change", ...}` |

**TransactionRecord**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `tx_id` | str | SHA256 del payload canónico |
| `sender` | str | Emisor o `"COINBASE"` para issuance |
| `receiver` | str | Receptor |
| `amount` | Decimal | Monto transferido (sin fee) |
| `fee` | Decimal | Fee al validador |
| `inputs` | list[str] | IDs de UTXOs consumidos (vacío en coinbase) |
| `outputs` | list[str] | IDs de UTXOs creados |
| `status` | str | `"PENDING"` → `"CONFIRMED"` → `"FINALIZED"` |
| `signer_public_key` | str | Clave pública firmante o `"COINBASE"` |
| `signature` | str | Firma digital o `"SYSTEM"` |
| `block_height` | int | Altura del bloque que incluye esta tx (None si pendiente) |
| `confirmations` | int | Número de confirmaciones (0 hasta ser minada) |
| `lot_id` | str | (opcional) Lote de trazabilidad asociado |

#### Reglas operacionales

| Regla | Detalle |
|-------|---------|
| ID de UTXO | `{tx_id}:{output_index}` — índice 0 = receptor, índice 1 = cambio |
| Selección de UTXOs | Greedy ascendente (primero los más pequeños) hasta cubrir `amount + fee` |
| Cambio | Si `selected_total > amount + fee`, se crea un UTXO de cambio devuelto al emisor |
| Fee | Se acumula en `validator_pool` — no genera UTXO de fee |
| Coinbase / Mint | `sender = "COINBASE"`, `inputs = []`, `fee = 0` |
| Lot ID | Los UTXOs heredan el `lot_id` de los inputs; el cambio también hereda el lot |
| Doble gasto | UTXOs usados van a `spent_outputs` (set); jamás se reutilizan |
| Balance | Suma de `unspent_outputs` donde `owner == address` |
| Lot con `lot_id` | Si se especifica `lot_id` en selección, solo se eligen UTXOs de ese lot |

#### Algoritmo de selección de UTXOs (`select_utxos`)

```
1. Filtrar UTXOs por currency
2. Ordenar ascendente por amount (más pequeños primero)
3. Acumular en order hasta que selected_total >= target_amount
4. Retornar (lista seleccionada, total acumulado)
5. Responsabilidad del caller: verificar que selected_total >= target_amount
```

### 2.2 Modelo Account

Cada cuenta mantiene un **balance** directo y un **nonce** (contador de transacciones).

#### Estructura de datos

**AccountState**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `balance` | Decimal | Balance actual |
| `nonce` | int | Contador de transacciones (inicia en 0) |
| `created_at` | str | ISO8601 timestamp |
| `public_key` | str | Clave pública asociada a la cuenta |

**AccountTransaction**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `tx_id` | str | SHA256 del payload canónico |
| `sender` | str | Cuenta emisora o `"TREASURY"` para mint |
| `receiver` | str | Cuenta receptora |
| `amount` | Decimal | Monto transferido |
| `fee` | Decimal | Fee al validador |
| `nonce` | int | Nonce del emisor al momento de crear la tx |
| `status` | str | `"PENDING"` → `"CONFIRMED"` → `"FINALIZED"` |
| `signer_public_key` | str | Clave pública firmante o `"TREASURY"` |
| `block_height` | int | Altura del bloque (None si pendiente) |
| `confirmations` | int | Número de confirmaciones |

#### Reglas operacionales

| Regla | Detalle |
|-------|---------|
| Nonce | Inicia en 0; se incrementa por cada tx del emisor |
| `expected_nonce` | Si se provee, debe coincidir exactamente — previene replay attacks y garantiza orden |
| Balance update | **Inmediato en aceptación** (no espera minado): `sender.balance -= total_cost`, `receiver.balance += amount` |
| Mint | `sender = "TREASURY"`, nonce = -1 (especial), sin fee |
| `transfer_lot()` | Solo cambia metadata del lot — **no** transfiere fondos |
| Auto-creación | Si el receptor no existe, se crea con balance 0 automáticamente |

### 2.3 Infraestructura compartida (BaseBlockchain)

#### Claves y firmas

| Elemento | Generación | Formato |
|----------|-----------|---------|
| `private_key` | `secrets.token_hex(32)` | 64 caracteres hexadecimales (32 bytes) |
| `public_key` | `SHA256(private_key)` | 64 caracteres hexadecimales |
| `signature` | `SHA256("{private_key}:{canonical_json_payload}")` | 64 caracteres hexadecimales |
| `tx_id` / `block_hash` | `SHA256(json.dumps(payload, sort_keys=True))` | 64 caracteres hexadecimales |

#### Mining y confirmaciones

```
max_txs_per_block = 10     (configurable)
confirmations_required = 2  (configurable)

confirmations = chain_height - tx.block_height + 1

status = "PENDING"   si block_height == None
status = "CONFIRMED" si 0 < confirmations < confirmations_required
status = "FINALIZED" si confirmations >= confirmations_required
```

- Sin Proof-of-Work — el minado es instantáneo.
- Solo las primeras `max_txs_per_block` transacciones pendientes se incluyen en cada bloque.
- Las fees se acumulan en `validator_pool`.
- El bloque génesis siempre existe: `height=0`, `previous_hash="0"*64`, `tx_ids=[]`.

### 2.4 Comparativa de modelos

| Aspecto | UTXO | Account |
|---------|------|---------|
| Balance | Suma de UTXOs activos | Campo directo en AccountState |
| Cambio | UTXO explícito devuelto al emisor | Implícito (resta del balance) |
| Orden de txs | Implícito por el set UTXO | Explícito por nonce |
| Lot linkage | UTXOs llevan `lot_id` | Lot trackeado por separado |
| Minting | `register_lot()` crea UTXO inicial | `register_lot()` no crea fondos |
| Gestión de fondos | Outputs inmutables, UTXO consumidos | Balance mutable, estado actualizado inmediatamente |

---

## 3. Gestión Multi-Usuario de Wallets

### 3.1 Constantes del ledger

| Constante | Valor | Uso |
|-----------|-------|-----|
| `TREASURY_USER_ID` | `"__TREASURY__"` | Usuario reservado del sistema (tesorería corporativa) |
| `TOKEN_TTL_SECONDS` | `300` | Tiempo de vida del `auth_token` de wallet en segundos |
| `TOKEN_ALPHABET` | ascii_letters + digits | 62 caracteres para generar tokens de wallet |

### 3.2 Estructura de datos del ledger

**UserRecord**

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `user_id` | str | — | `USR-00001` ... `USR-99999` (auto-secuencial) |
| `display_name` | str | — | Nombre visible (obligatorio) |
| `created_at` | str | — | ISO8601 |
| `banned` | bool | `False` | Usuario baneado |
| `updated_at` | str | `""` | Última modificación |
| `deleted_at` | str | `""` | Soft delete (vacío = activo) |
| `first_name` | str | `""` | Nombre (opcional) |
| `last_name` | str | `""` | Apellido (opcional) |
| `email` | str | `""` | Email (opcional) |
| `username` | str | `""` | Username único (opcional) |

**WalletRecord**

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `wallet_id` | str | — | Regex `[A-Za-z0-9_-]{20,30}` |
| `user_id` | str | — | Propietario |
| `model` | str | — | `"ACCOUNT"` o `"UTXO"` — inmutable |
| `currency` | str | `"USDX"` | Divisa de la wallet |
| `balance` | Decimal | `0` | Saldo actual |
| `auth_token` | str | — | 12 chars aleatorios para autorizar transfers |
| `token_issued_at` | int | — | Epoch timestamp de emisión del token |
| `created_at` | str | — | ISO8601 |
| `frozen` | bool | `False` | Wallet congelada |

### 3.3 Usuarios

| Campo / Regla | Detalle |
|---------------|---------|
| `user_id` auto-generado | `USR-00001` incrementando con `_user_seq` (zero-padded 5 dígitos) |
| `display_name` | Obligatorio; se valida que no esté vacío |
| `username` | Si no se provee, toma el valor de `display_name`. Único si se provee |
| `TREASURY_USER_ID` | No puede usarse como `user_id`, no puede ser baneado, no puede ser eliminado |
| Resolución de identidad | `resolve_user_id(identifier)` busca por `user_id` exacto, luego por `username` |

### 3.4 Bootstrap del primer ADMIN

| Condición | Comportamiento |
|-----------|---------------|
| Ledger vacío | Primer `create_user(role="ADMIN")` no necesita `invitation_token` |
| Ledger no vacío | `role="ADMIN"` requiere `invitation_token` válido (de un solo uso, generado por otro ADMIN) |
| OPERATOR / VIEWER | Al crearse, reciben `activation_code` de 16 caracteres alfanuméricos |
| Login OPERATOR/VIEWER | Primer login requiere proveer el `activation_code` |

**Token de invitación ADMIN**: 32 hex chars (`secrets.token_hex(16)`). Marcado como `used=True` al consumirse.

**Código de activación OPERATOR/VIEWER**: 16 chars `ascii_uppercase + digits`. Marcado como `activated=True` al consumirse.

### 3.5 Wallets

| Regla | Detalle |
|-------|---------|
| `wallet_id` formato | Regex `[A-Za-z0-9_-]{20,30}` — 20 a 30 caracteres |
| `wallet_id` auto | Si no se provee, se genera como `wlt-{secrets.token_hex(10)}` |
| `model` | `"ACCOUNT"` o `"UTXO"` — inmutable tras creación |
| `currency` | Default `"USDX"`; normalizado a uppercase |
| `auth_token` | 12 chars; expira a los **300 segundos** (`TOKEN_TTL_SECONDS`) |
| `frozen` | Wallet congelada bloquea toda operación: mint, transfer, top-up |
| Balance PG | `CHECK balance >= 0` — nunca negativo |

### 3.6 Operación Mint

**Validaciones (en orden):**
1. `amount > 0`
2. `wallet_id` existe
3. Wallet no congelada

**Efectos:**
- ACCOUNT: `wallet.balance += amount`
- UTXO: crea UTXO + sincroniza balance
- Registro de tipo `MINT` en `transfers` con `sender_wallet = "TREASURY"`

### 3.7 Operación Transfer

**Validaciones (en orden estricto):**

```
1.  sender ≠ receiver
2.  ambas wallets existen
3.  amount > 0
4.  fee >= 0
5.  sender wallet no congelada
6.  receiver wallet no congelada
7.  usuario emisor no baneado
8.  mismo modelo (ACCOUNT↔ACCOUNT o UTXO↔UTXO)
9.  si cross-currency → existe tasa de cambio configurada
10. sender_token no vacío
11. sender_token no expirado (< 300s desde token_issued_at)
12. sender_token coincide con wallet.auth_token
13. expected_nonce (si se provee) == wallet_nonce + 1
14. policy.can_transfer == True
15. daily_limit efectivo no excedido
16. balance / UTXOs suficientes para amount + fee
```

**Límite diario efectivo:**

```
effective_daily_limit = min(policy.daily_limit, risk_profile.daily_limit)
  — ignorando los que sean None
  — verifica: (daily_total_hoy + amount) > effective_daily_limit
```

**Chain of integrity (hash encadenado):**

```
previous_hash = tx_hash del último TRANSFER (o "GENESIS" si es el primero)
tx_hash = SHA256(transfer_id | model | wallets | amount | fee | reference | nonce | created_at | previous_hash)
```

Verificable con `verify_transfer_integrity()`.

**Flujo de fondos (ACCOUNT):**
```
sender.balance   -= (amount + fee)
receiver.balance += credit_amount
validator_pool   += fee
```

**Flujo de fondos (UTXO):**
```
1. Seleccionar UTXOs del sender que cubran (amount + fee)
2. Crear UTXO para receiver con credit_amount
3. Si hay cambio: crear UTXO de cambio para sender
4. Marcar UTXOs consumidos como gastados
5. Sincronizar balances
```

**Si cross-currency:** `credit_amount = net_amount` (resultado de `convert_amount()`).

### 3.8 Operación Top-Up (Tesorería → Usuario)

**Validaciones adicionales sobre transfer:**
- `treasury_wallet` debe pertenecer a `TREASURY_USER_ID`
- `treasury_wallet ≠ target_wallet`
- Modelos deben coincidir
- Si cross-currency: debe existir tasa configurada

**Diferencias respecto a transfer:**
- Se registra como tipo `TOP_UP`
- El `auth_token` de la wallet del tesoro no se valida (operación interna)
- El monto descontado del tesoro es `amount`; el acreditado es `net_amount` (tras comisión)

---

## 4. Exchange (Conversión de Divisas)

### 4.1 Configuración de tasa

**Validaciones:**

```
from_currency ≠ to_currency
from_currency no vacío (strip)
to_currency no vacío (strip)
rate > 0
commission_pct >= 0  (quantizado a 0.01)
```

**Clave canónica:** `pair_key = "{FROM_UPPER}-{TO_UPPER}"` (ej. `"USD-EUR"`).

**Cada par es unidireccional:** `USD→EUR` y `EUR→USD` son registros independientes.

### 4.2 Cálculo de conversión

```python
gross      = (amount × rate).quantize(UNIT, ROUND_DOWN)
commission = (gross × commission_pct / 100).quantize(UNIT, ROUND_DOWN)
net        = gross - commission
```

| Regla | Descripción |
|-------|-------------|
| Rounding | Siempre `ROUND_DOWN` — nunca hacia arriba |
| Comisión | Se **deduce** del gross; nunca se suma al monto enviado |
| Retorno | `{gross_amount, commission, net_amount, rate, commission_pct}` — todos en string |

### 4.3 Estructura almacenada

```python
{
    "pair_id":        "USD-EUR",
    "from_currency":  "USD",
    "to_currency":    "EUR",
    "rate":           "0.92000000",
    "commission_pct": "1.00",
    "updated_at":     "2026-01-01T00:00:00+00:00"
}
```

---

## 5. Políticas y Perfiles de Riesgo

### 5.1 Política de usuario (`UserPolicyRecord`)

| Campo | Tipo | Default | Regla |
|-------|------|---------|-------|
| `can_transfer` | bool | `True` | `False` bloquea transferencias (hard block, validación paso 14) |
| `daily_limit` | Decimal \| None | `None` | Si se configura: debe ser `> 0`. `None` = sin límite |

### 5.2 Perfiles de riesgo predefinidos

| Perfil | `daily_limit` | `transfer_alert_threshold` | `daily_alert_threshold` |
|--------|--------------|---------------------------|------------------------|
| `STANDARD` | — | — | — |
| `LOW` | 25,000 | 10,000 | 20,000 |
| `MEDIUM` | 10,000 | 5,000 | 8,000 |
| `HIGH` | 5,000 | 2,000 | 4,000 |
| `RESTRICTED` | 1,000 | 300 | 800 |

Al asignar un perfil, los thresholds se resetean a los valores predefinidos; luego pueden sobreescribirse individualmente.

### 5.3 Límite efectivo

```
effective_daily_limit = min(policy.daily_limit, risk_profile.daily_limit)
```

- Si ambos son `None`: sin límite diario.
- Si uno es `None`: se aplica el otro.
- Si ambos tienen valor: se aplica el más restrictivo.

### 5.4 Sistema de alertas

**Trigger de alerta:**
- `TRANSFER_THRESHOLD`: `transfer_amount >= transfer_alert_threshold`
- `DAILY_THRESHOLD`: `daily_total_proyectado >= daily_alert_threshold`

**Cálculo de severidad:**

```
ratio = observed / threshold

severity = "HIGH"   si ratio >= 1.5
severity = "MEDIUM" si ratio <  1.5
```

**Las alertas son informativas — no bloquean operaciones.**

**Estructura de alerta:**
```python
{
    "alert_id":     "alt-{16hex}",
    "user_id":      str,
    "profile_name": str,
    "type":         "TRANSFER_THRESHOLD" | "DAILY_THRESHOLD",
    "severity":     "MEDIUM" | "HIGH",
    "threshold":    str,
    "observed":     str,
    "transfer_id":  str,
    "created_at":   str
}
```

---

## 6. RBAC — Roles y Permisos

### 6.1 Roles disponibles

| Rol | Descripción |
|-----|-------------|
| `ADMIN` | Acceso total a todas las operaciones |
| `OPERATOR` | Operaciones transaccionales y de configuración |
| `VIEWER` | Solo lectura + operaciones básicas propias |

### 6.2 Permisos por rol (defaults)

| Permiso | ADMIN | OPERATOR | VIEWER |
|---------|:-----:|:--------:|:------:|
| `CREATE_USER` | ✓ | — | — |
| `CREATE_WALLET` | ✓ | ✓ | ✓ |
| `TRANSFER` | ✓ | ✓ | ✓ |
| `MINT` | ✓ | ✓ | — |
| `EXCHANGE` | ✓ | ✓ | ✓ |
| `SET_EXCHANGE_RATE` | ✓ | — | — |
| `TOP_UP` | ✓ | ✓ | — |
| `SET_POLICY` | ✓ | ✓ | — |
| `SET_RISK_PROFILE` | ✓ | ✓ | — |
| `ASSIGN_ROLE` | ✓ | — | — |
| `MANAGE_PERMISSIONS` | ✓ | — | — |
| `FREEZE_WALLET` | ✓ | — | — |
| `UNFREEZE_WALLET` | ✓ | — | — |
| `BAN_USER` | ✓ | — | — |
| `UNBAN_USER` | ✓ | — | — |
| `UPDATE_USER` | ✓ | — | — |
| `DELETE_USER` | ✓ | — | — |
| `RESTORE_USER` | ✓ | — | — |
| `GENERATE_TEMP_PASSWORD` | ✓ | — | — |
| `VIEW_AUDIT_LOG` | ✓ | — | — |
| `UPDATE_PROFILE` | ✓ | ✓ | ✓ |
| `VIEW_USERS` | ✓ | ✓ | ✓ |
| `VIEW_WALLETS` | ✓ | ✓ | ✓ |
| `VIEW_TRANSFERS` | ✓ | ✓ | ✓ |
| `VIEW_ALERTS` | ✓ | ✓ | ✓ |
| `VIEW_POLICIES` | ✓ | ✓ | ✓ |
| `VIEW_RISK_PROFILES` | ✓ | ✓ | ✓ |
| `VIEW_REVISIONS` | ✓ | ✓ | ✓ |

### 6.3 Jerarquía de resolución de permisos

```
1. user_permission_overrides[user_id]  →  ¿tiene el permiso?  →  SÍ → permitido
       ↓ no
2. role_permission_overrides[role]     →  ¿tiene el permiso?  →  SÍ → permitido
       ↓ no
3. ROLE_PERMISSIONS[role] (defaults)   →  ¿tiene el permiso?  →  SÍ → permitido
       ↓ no
4. Denegado
```

El override a nivel de **usuario** tiene precedencia sobre el de **rol**, y ambos sobre los defaults.

### 6.4 Restricciones de gestión de permisos

| Restricción | Descripción |
|-------------|-------------|
| `MANAGE_PERMISSIONS` de ADMIN | **No se puede revocar.** `revoke_role_permission(ADMIN, MANAGE_PERMISSIONS)` es rechazado |
| Permisos dinámicos por rol | Al sobreescribir un rol, se inicializa con los defaults y se aplica el cambio |
| Permisos por usuario | Pueden coexistir con los de rol; tienen prioridad |
| `reset_role_permissions(role)` | Elimina todos los overrides del rol, volviendo a los defaults |

### 6.5 Operaciones con sudo (re-validación JWT)

Las siguientes operaciones requieren re-validación de credenciales (hasta 3 intentos):
- `freeze_wallet`, `unfreeze_wallet`
- `ban_user`, `unban_user`
- `delete_user`, `restore_user`
- `update_user`
- `generate_temp_password`

---

## 7. Gestión de Contraseñas y JWT

### 7.1 Hashing de contraseña

```python
hash = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
# rounds configurable vía BCRYPT_ROUNDS (default 12)
```

### 7.2 JWT de usuario

| Campo del payload | Valor |
|-------------------|-------|
| `sub` | `user_id` |
| `roles` | lista de roles del usuario |
| `iat` | epoch timestamp de emisión |
| `exp` | `iat + jwt_ttl` |

- Algoritmo: `HS256`
- TTL default: `3600` segundos (configurable vía `JWT_TTL_SECONDS`)
- Secreto mínimo recomendado: 32 bytes

### 7.3 Auth token de wallet

- 12 caracteres aleatorios de `ascii_letters + digits`
- Expira a los **300 segundos** desde `token_issued_at`
- Se rota automáticamente al expirar (llamadas a `list_wallets`, `get_wallet_balance`, `refresh_wallet_token`)
- **Requerido en toda transferencia** — debe coincidir con `wallet.auth_token` y no estar expirado

### 7.4 Password temporal

| Paso | Descripción |
|------|-------------|
| Generación | 12 chars (`ascii_letters + digits + "!@#$%"`) |
| Almacenamiento | Se hashea con bcrypt; se activa `password_temp = True` |
| Token temporal | 64 hex chars (`secrets.token_hex(32)`); permite reset sin conocer la contraseña actual |
| Login con temp | Retorna `{..., "must_change_password": true}` |
| Terminal | Fuerza `change_password()` inmediatamente después del login antes de mostrar menú |
| `change_password` | Requiere contraseña actual + nueva (mínimo 4 chars); limpia `password_temp` y `token_temp` |
| `reset_password_with_token` | Requiere `token_temp` + nueva contraseña (mínimo 4 chars) |

### 7.5 Flujo de login

```
1. resolve_user_id(identifier)    → busca por user_id o username
2. authenticate(user_id, password) → bcrypt verify
3. is_user_deleted(user_id)       → error si deleted_at != ""
4. is_user_banned(user_id)        → error si banned == True
5. is_account_activated(user_id)  → si no, requiere activation_code
6. Crear JWT                       → retornar access_token
7. Si password_temp == True       → agregar must_change_password: true
```

---

## 8. Ciclo de Vida de Usuario

### 8.1 Diagrama de estados

```
[create_user()]
      │
      ├─ role=ADMIN ──────────────────────────── login() inmediato
      │
      └─ role=OPERATOR/VIEWER ─── activation_code ─── login() con código
                                                              │
                                          ┌─────────────────┘
                                          │
                                    Usuario activo
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
      [ban_user()]                  [delete_user()]              [update_user()]
            │                             │                             │
      banned=True                  deleted_at=now()              cambio de user_id
      wallets frozen               wallets frozen                o display_name
            │                             │
      [unban_user()]               [restore_user()]
            │                             │
      banned=False                 deleted_at=""
      wallets unfrozen             wallets unfrozen (opcional)
```

### 8.2 Reglas de modificación de usuario

**`update_user(user_id, new_user_id, new_display_name)`:**
- No aplica a `TREASURY_USER_ID`
- `new_user_id` no puede ya existir ni ser `TREASURY_USER_ID`
- Al cambiar `user_id`: se actualiza en cascada en `users`, `wallets`, `user_wallets`, `user_policies`, `user_risk_profiles`, `user_roles`, `user_credentials`, `activation_codes`, `user_permission_overrides`

**`delete_user(user_id)`** (soft delete):
- No aplica a `TREASURY_USER_ID`
- No aplica si ya está eliminado
- Congela **todas** las wallets del usuario
- Login bloqueado inmediatamente

**`restore_user(user_id, unfreeze_wallets=True)`:**
- Solo aplica si `deleted_at != ""`
- Opcionalmente descongela wallets

### 8.3 Ban vs Soft Delete

| Característica | Ban | Soft Delete |
|----------------|-----|-------------|
| Login | Bloqueado | Bloqueado |
| Wallets | Congeladas | Congeladas |
| Datos preservados | Sí | Sí |
| Reversible | Sí (`unban_user`) | Sí (`restore_user`) |
| Prioridad en login | 2° check | 1° check |
| Mensaje de error | "cuenta baneada" | "cuenta eliminada" |

---

## 9. Audit Log

### 9.1 Estructura de entrada

```python
{
    "log_id":      "aud-{16hex}",
    "timestamp":   "ISO8601 UTC",
    "actor_id":    str,   # quien realizó la acción
    "action":      str,   # tipo de acción (ver tabla abajo)
    "target_type": str,   # entidad afectada: USER, WALLET, TRANSFER, etc.
    "target_id":   str,   # ID de la entidad
    "details":     dict   # contexto adicional variable
}
```

### 9.2 Acciones auditadas (~22 tipos)

| Acción | Trigger |
|--------|---------|
| `USER_CREATED` | `create_user()` |
| `USER_UPDATED` | `update_user()`, `update_profile()` |
| `USER_DELETED` | `delete_user()` |
| `USER_RESTORED` | `restore_user()` |
| `USER_BANNED` | `ban_user()` |
| `USER_UNBANNED` | `unban_user()` |
| `WALLET_CREATED` | `create_wallet()` |
| `WALLET_FROZEN` | `freeze_wallet()` |
| `WALLET_UNFROZEN` | `unfreeze_wallet()` |
| `LOGIN_SUCCESS` | `login()` exitoso |
| `LOGIN_FAILED` | `login()` con credenciales incorrectas |
| `LOGIN_BANNED` | `login()` de usuario baneado |
| `PASSWORD_CHANGED` | `change_password()`, `reset_password_with_token()` |
| `PASSWORD_TEMP_GENERATED` | `generate_temp_password_for_user()` |
| `ROLE_ASSIGNED` | `assign_role()` |
| `ROLE_REMOVED` | `remove_role()` |
| `PERMISSION_GRANTED` | `grant_role_permission()` |
| `PERMISSION_REVOKED` | `revoke_role_permission()` |
| `TRANSFER` | `transfer()` (mismo modelo/divisa) |
| `EXCHANGE` | `transfer()` (cross-currency) |
| `MINT` | `mint()` |
| `TOP_UP` | `top_up()` |

### 9.3 Reglas

- **Append-only**: nunca se modifica ni elimina una entrada.
- En PostgreSQL: `INSERT ON CONFLICT (log_id) DO NOTHING`.
- `list_audit_log(limit, user_id, action)` filtra por `actor_id OR target_id` y por `action` (case-insensitive).
- Default limit: 50 entradas (retorna las más recientes).

---

## 10. Compliance y Trazabilidad de Cadena de Suministro

### 10.1 Estructuras de datos

**TraceabilityLot**

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `lot_id` | str | — | Identificador único |
| `product` | str | — | Tipo de producto (ej. "Cafe Arabe") |
| `origin` | str | — | Origen/fuente |
| `owner` | str | — | Propietario actual |
| `created_at` | str | — | ISO8601 |
| `certificate_ids` | list[str] | `[]` | Referencias a certificados |
| `event_ids` | list[str] | `[]` | Referencias a eventos logísticos |
| `compliance_status` | str | `"PENDING"` | `PENDING` → `PASS` o `FAIL` |
| `required_events` | list[str]\|None | `None` | `None` usa perfil DEFAULT |
| `min_active_certificates` | int | `1` | Mínimo de certificados activos requeridos |

**CertificateRecord**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `certificate_id` | str | `"CERT-{12hex}"` |
| `lot_id` | str | Lote asociado |
| `cert_type` | str | Tipo (ej. `"ORGANIC"`, `"FAIRTRADE"`) |
| `issuer` | str | Entidad emisora |
| `document_hash` | str | SHA256 del documento |
| `issued_at` | str | ISO8601 |
| `valid_until` | str | ISO8601 — fecha de expiración |
| `revoked` | bool | `False` — si se revoca, no puede reactivarse |

**LogisticsEvent**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `event_id` | str | `"EVT-{12hex}"` |
| `lot_id` | str | Lote asociado |
| `event_type` | str | Ej. `"COSECHA"`, `"PROCESAMIENTO"`, `"EXPORTACION"` |
| `actor` | str | Quien ejecutó el evento |
| `location` | str | Lugar del evento |
| `timestamp` | str | ISO8601 |
| `metadata` | dict | Datos adicionales arbitrarios |

### 10.2 Perfiles de compliance por producto

| Perfil | Eventos requeridos | Mín. certificados activos |
|--------|--------------------|--------------------------|
| `DEFAULT` | COSECHA, PROCESAMIENTO, EXPORTACION | 1 |
| `CAFE` | COSECHA, PROCESAMIENTO, EXPORTACION | 1 |
| `CACAO` | COSECHA, FERMENTACION, EXPORTACION | 1 |

El perfil se resuelve por nombre de producto (`str(product).strip().upper()`); si no coincide, usa `DEFAULT`. Los perfiles son configurables en runtime con `configure_compliance_profile()`.

### 10.3 Evaluación de compliance

**Algoritmo de `evaluate_compliance(lot, certificates, logistics_events)`:**

```
1. Recopilar event_types de todos los LogisticsEvents referenciados por el lote
2. Determinar required_events del lote (o DEFAULT si None)
3. has_required_events = required_events ⊆ event_types_recopilados

4. Para cada certificate_id en lot.certificate_ids:
     a. Obtener CertificateRecord (skip si no existe)
     b. Skip si revoked == True
     c. Skip si valid_until < now(UTC)
     d. active_certificates += 1

5. compliant = has_required_events AND active_certificates >= lot.min_active_certificates

6. Retornar:
     status:                  "PASS" si compliant, "FAIL" si no
     has_required_events:     bool
     active_certificates:     int
     required_events:         sorted list
     min_active_certificates: int
```

### 10.4 Flujo típico de un lote

```
register_lot(lot_id, owner, product, origin)
    → compliance_status = "PENDING"
    → UTXOs iniciales (solo modelo UTXO)

issue_certificate(lot_id, cert_type, issuer, valid_days=365)
    → certificate_id = "CERT-{12hex}"
    → lot.certificate_ids.append(certificate_id)

record_logistics_event(lot_id, "COSECHA",        actor, location)
record_logistics_event(lot_id, "PROCESAMIENTO",  actor, location)
record_logistics_event(lot_id, "EXPORTACION",    actor, location)
    → event_id = "EVT-{12hex}"
    → lot.event_ids.append(event_id)

audit_compliance(lot_id)
    → actualiza lot.compliance_status = "PASS" o "FAIL"
```

---

## 11. Precisión Monetaria (Regla Universal)

```python
UNIT   = Decimal("0.00000001")   # 8 decimales — precisión satoshi
SATOSHI = UNIT                    # alias para el modelo UTXO

def normalize_amount(value) -> Decimal:
    return Decimal(str(value)).quantize(UNIT, rounding=ROUND_DOWN)
```

| Regla | Descripción |
|-------|-------------|
| Precisión | Exactamente 8 decimales en todas las operaciones monetarias |
| Rounding | Siempre `ROUND_DOWN` — nunca se redondea hacia arriba |
| Fuente única | `domain/precision.py` — importado por todos los módulos (no hay definiciones locales duplicadas) |
| En PostgreSQL | `NUMERIC(28,8)` en todas las columnas monetarias |
| Máximo valor PG | 99,999,999,999,999,999,999 (28 dígitos enteros + 8 decimales) |

Aplica en: mint, transfer, top-up, selección de UTXOs, exchange, alertas, límites diarios, risk thresholds.

---

## 12. Persistencia

### 12.1 Selección de backend

```
PERSISTENCE_BACKEND=json     (default) → multiuser_wallet_store.py
PERSISTENCE_BACKEND=postgres           → pg_multiuser_wallet_store.py
```

> **Importante:** Cuando `PERSISTENCE_BACKEND=postgres`, el parámetro `--store-file`
> es completamente ignorado por la factory. Para usar JSON explícitamente en scripts,
> usar `export PERSISTENCE_BACKEND=json` antes de ejecutar.

### 12.2 Backend JSON

| Característica | Detalle |
|----------------|---------|
| Estructura | `{schema_version, updated_at, current_revision_id, snapshot, revisions}` |
| Revisiones | Append-only, máximo 20 retornadas, ordenadas descendente (más reciente primero) |
| `revision_id` | `rev-YYYYMMDDTHHMMSSZ-{4hex}` |
| Escritura atómica | tempfile → replace (previene corrupción) |
| Snapshot keys | `users, wallets, policies, risk_profiles, transfers, alerts, credentials, roles, admin_invitation_tokens, activation_codes, exchange_rates, role_permission_overrides, user_permission_overrides, audit_log` |

### 12.3 Backend PostgreSQL — Evolución del esquema

| Migración | Contenido |
|-----------|-----------|
| `V001` | Tablas core: `users`, `wallets`, `user_policies`, `user_risk_profiles`, `wallet_nonces`, `wallet_utxos`, `transfers` (MINT/TRANSFER), `alerts`, `ledger_revisions`, `simulation_runs`, `traceability_lots`, `certificates`, `logistics_events`, `compliance_profiles` (con seed data) |
| `V002` | Auth: `user_credentials`, `user_roles`, enum `user_role` (ADMIN/OPERATOR/VIEWER) |
| `V003` | `admin_invitation_tokens`, `activation_codes` |
| `V004` | `exchange_rates`; tipo `EXCHANGE` en `transfer_type`; columnas de conversión en `transfers` |
| `V005` | Tipo `TOP_UP` en `transfer_type` |
| `V006` | `permissions` (catálogo con 18 permisos seed), `role_permissions`, `user_permissions` |
| `V007` | `banned` en `users`, `frozen` en `wallets`; índices parciales condicionales |
| `V008` | `updated_at`/`deleted_at` en `users`; `password_temp`/`token_temp` en `user_credentials`; tabla `audit_log` |
| `V009` | `first_name`, `last_name`, `email`, `username` en `users`; índice único condicional en `username` |

### 12.4 Invariantes de base de datos

| Tabla | Constraint | Regla de negocio |
|-------|-----------|------------------|
| `wallets.balance` | `CHECK balance >= 0` | El saldo nunca es negativo |
| `wallet_utxos.amount` | `CHECK amount > 0` | Un UTXO siempre tiene valor positivo |
| `transfers.amount` | `CHECK amount > 0` | Toda transferencia tiene monto positivo |
| `transfers.fee` | `CHECK fee >= 0` | El fee no puede ser negativo |
| `exchange_rates.rate` | `CHECK rate > 0` | La tasa de cambio siempre es positiva |
| `exchange_rates.commission_pct` | `CHECK commission_pct >= 0` | La comisión no puede ser negativa |
| `user_policies.daily_limit` | `CHECK daily_limit IS NULL OR daily_limit > 0` | Si hay límite, debe ser positivo |
| `wallet_nonces.current_nonce` | `CHECK current_nonce >= 0` | El nonce no puede ser negativo |
| `wallets.token_expires_at` | `GENERATED AS token_issued_at + 120` | Columna computada (120s de ventana) |
| `wallets.user_id → users` | `ON DELETE RESTRICT` | No se puede eliminar un usuario con wallets |
| `wallet_utxos.wallet_id → wallets` | `ON DELETE RESTRICT` | No se puede eliminar wallet con UTXOs |
| `exchange_rates` | `UNIQUE(from_currency, to_currency)` | Un par de divisas tiene exactamente una tasa |
| `user_roles` | `PK(user_id, role)` | Un rol no puede asignarse dos veces al mismo usuario |
| `users.username` | Índice UNIQUE condicional `WHERE username != ''` | Usernames únicos (múltiples vacíos permitidos) |

### 12.5 Tipos ENUM de PostgreSQL

| Enum | Valores |
|------|---------|
| `wallet_model` | `ACCOUNT`, `UTXO` |
| `transfer_type` | `MINT`, `TRANSFER`, `EXCHANGE`, `TOP_UP` |
| `transfer_status` | `SETTLED`, `PENDING`, `FAILED` |
| `risk_profile_t` | `STANDARD`, `LOW`, `MEDIUM`, `HIGH`, `RESTRICTED` |
| `alert_type` | `TRANSFER_THRESHOLD`, `DAILY_THRESHOLD` |
| `alert_severity` | `LOW`, `MEDIUM`, `HIGH` |
| `compliance_status` | `PENDING`, `PASS`, `FAIL` |
| `user_role` | `ADMIN`, `OPERATOR`, `VIEWER` |

---

## 13. Escenarios del Simulador

### 13.1 Coffee Export (`--scenario coffee-export`)

**Modelos:** UTXO y Account (producen los mismos balances finales)

| Participante | Balance inicial | Rol |
|-------------|-----------------|-----|
| Exportador_Colombia | 100 | Dueño del lote |
| Logistica_Latam | 0 | Receptor de pago |
| Aduana_Pacifico | 0 | Receptor de pago / dueño final del lote |

**Perfil de compliance:** `CAFE` → COSECHA + PROCESAMIENTO + EXPORTACION + 1 certificado activo

**Flujo:**
1. Wallet + cuenta + lot `"Lote_Cafe_001"` (producto `"Cafe Arabe"`, origen `"Huila_Colombia"`)
2. `issue_certificate` (ICA, tipo Fitosanitario)
3. `record_logistics_event` → COSECHA (Cooperativa_Huila / Finca_El_Roble)
4. `record_logistics_event` → PROCESAMIENTO (Planta_Trillado / Neiva)
5. Transferencia: 30 a Logistica, fee=0.25 (UTXO: cambio=69.75) / fee=0.15 (Account: nonce=0)
6. `mine_block` (Nodo_Validador_1)
7. `record_logistics_event` → EXPORTACION (Puerto_Buenaventura)
8. `mine_block` (Nodo_Validador_2)
9. (Account) Segunda transferencia: 20 a Aduana, fee=0.10, nonce=1
10. (Account) `transfer_lot` → Exportador → Aduana
11. `audit_compliance` → PASS

**Resultado:** compliance_status = `"PASS"`, validator_pool acumulado.

### 13.2 Retail Payments (`--scenario retail-payments`)

**Modelos:** UTXO y Account

| Participante | Balance inicial |
|-------------|-----------------|
| Fintech_Emisor | 200 |
| Comercio_A | 0 |
| Comercio_B | 0 |

**Sin trazabilidad** — pagos simples sin lots, certificados ni eventos.

**Flujo:**
1. Mint 200 → Fintech_Emisor
2. 12.5 → Comercio_A, fee=0.05
3. 7.3 → Comercio_B, fee=0.04
4. `mine_block`
5. 2.1 Comercio_A → Comercio_B, fee=0.02
6. `mine_block`

**Balances finales:** Fintech=180.11, Comercio_A=10.38, Comercio_B=9.4, validator_pool=0.11

### 13.3 Diferencias clave entre modelos en los escenarios

| Aspecto | UTXO | Account |
|---------|------|---------|
| Minting inicial | Crea UTXO con `lot_id` | Asigna balance directo |
| Cambio | UTXO explícito (output_index=1) | Implícito en balance |
| Transferencia de lot | No necesario (UTXO hereda lot_id) | Requiere `transfer_lot()` explícito |
| Orden de tx | Implícito | `nonce` explícito (0, 1, 2...) |

---

## 14. Resumen de Reglas de Negocio Críticas

| # | Regla | Módulo / Método |
|---|-------|----------------|
| 1 | `UNIT = 0.00000001`, siempre `ROUND_DOWN` — precisión satoshi en toda operación monetaria | `domain/precision.py` |
| 2 | Wallet ID: regex `[A-Za-z0-9_-]{20,30}` | `create_wallet()` |
| 3 | `auth_token` de wallet expira en **300 segundos** y es requerido en toda transferencia | `transfer()` |
| 4 | `expected_nonce` previene replay attacks y garantiza orden de transferencias | `transfer()`, `send_transaction()` |
| 5 | Primer `create_user(role=ADMIN)` con ledger vacío no necesita `invitation_token` | `create_user()` |
| 6 | Login checks en orden: credenciales → `deleted_at` → `banned` → activación → JWT | `login()` |
| 7 | Soft delete = `deleted_at != ""` → login bloqueado + wallets congeladas | `delete_user()` |
| 8 | `must_change_password=True` en login con password temporal → terminal fuerza cambio inmediato | `login()` |
| 9 | Jerarquía de permisos: `user_overrides > role_overrides > defaults` | `has_permission()` |
| 10 | No se puede revocar `MANAGE_PERMISSIONS` al rol ADMIN | `revoke_role_permission()` |
| 11 | Cross-currency requiere tasa configurada **de antemano**; no hay fallback | `transfer()`, `top_up()` |
| 12 | Comisión: `net = (amount × rate) - (amount × rate × commission_pct / 100)` | `convert_amount()` |
| 13 | Compliance PASS = todos los eventos requeridos presentes **Y** ≥ min certificados activos no expirados | `audit_compliance()` |
| 14 | UTXOs gastados van a `spent_outputs` — nunca se reutilizan | `send_transaction()` UTXO |
| 15 | `TREASURY_USER_ID = "__TREASURY__"` no puede banearse, eliminarse ni usarse como `user_id` | Múltiples métodos |
| 16 | `PERSISTENCE_BACKEND=postgres` ignora `--store-file` completamente — no hay fallback silencioso | `persistence/factory.py` |
| 17 | Audit log es append-only en ambos backends | `_audit()`, `_sync_audit_log()` |
| 18 | Las alertas de riesgo son **informativas** — no bloquean operaciones | `_register_alert()` |
| 19 | Límite diario efectivo = `min(policy.daily_limit, risk_profile.daily_limit)` | `transfer()` |
| 20 | Severidad de alerta: `HIGH` si `observed/threshold >= 1.5`, `MEDIUM` si `< 1.5` | `_register_alert()` |
| 21 | Certificado activo = `NOT revoked AND valid_until >= now(UTC)` | `evaluate_compliance()` |
| 22 | Firma: `SHA256("{private_key}:{canonical_json_sorted_keys}")` | `_sign_payload()` |
| 23 | `balance >= 0` y `utxo.amount > 0` — invariantes estructurales en DB y dominio | SQL CHECK + Python |
| 24 | `token_expires_at = token_issued_at + 120` — columna generada en PostgreSQL (solo referencia; la lógica de negocio usa 300s) | V001 SQL |

---

*Generado a partir del análisis estático del código fuente en v2.8.2.*
*Archivo: `docs/BUSINESS_RULES.md`*
