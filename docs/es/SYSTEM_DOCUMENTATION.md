# Documentacion Tecnica del Sistema — v2.8.0

## 1. Objetivo

Modelar y comparar dos enfoques blockchain (UTXO y Account-based) con escenarios funcionales realistas, trazabilidad de cadena de suministro, compliance, persistencia dual (JSON / PostgreSQL), gestion multiusuario completa de wallets, intercambio de divisas, tesoreria corporativa, RBAC dinamico y log de auditoria append-only.

---

## 2. Diagrama de arquitectura

```mermaid
flowchart TB
    subgraph CLI["Capa CLI / Interaccion"]
        T[multiuser_terminal.py\n45 opciones, 10 secciones]
        C[multiuser_wallet_cli.py\n45+ subcomandos]
        S[blockchain_models_simulator.py]
    end

    subgraph Domain["Capa de Dominio (Python puro)"]
        L[multiuser_wallet_ledger.py\nUsuarios · Wallets · Transferencias\nExchange · Tesoreria · Auditoria]
        A[auth.py\nJWT · bcrypt · RBAC\nPermisos dinamicos]
        E[exchange.py\nExchangeRate · convert_amount]
        CM[compliance.py]
        TR[traceability_models.py]
    end

    subgraph Persistence["Capa de Persistencia"]
        F[factory.py\nStrategy Pattern]
        J[multiuser_wallet_store.py\nBackend JSON]
        P[pg_multiuser_wallet_store.py\nBackend PostgreSQL]
        PC[pg_connection.py\nPool de conexiones]
    end

    subgraph DB["Almacenamiento"]
        JF[data/multiuser/wallet-ledger.json]
        PG[(PostgreSQL 16\nMigraciones V001–V009)]
    end

    CLI --> Domain
    Domain --> Persistence
    F -->|PERSISTENCE_BACKEND=json| J
    F -->|PERSISTENCE_BACKEND=postgres| P
    P --> PC --> PG
    J --> JF
```

---

## 3. Diagrama de clases del dominio

```mermaid
classDiagram
    class UserRecord {
        +str user_id
        +str display_name
        +str created_at
        +bool banned
        +str updated_at
        +str deleted_at
        +str first_name
        +str last_name
        +str email
        +str username
    }

    class WalletRecord {
        +str wallet_id
        +str user_id
        +str model
        +str currency
        +str created_at
        +bool frozen
    }

    class ExchangeRate {
        +str from_currency
        +str to_currency
        +Decimal rate
        +Decimal commission_pct
        +pair_key() str
        +convert_amount(amount) dict
    }

    class MultiUserWalletLedger {
        +dict users
        +dict wallets
        +dict credentials
        +list transfers
        +list audit_log
        +dict exchange_rates
        +dict role_permission_overrides
        +dict user_permission_overrides
        +int _user_seq
        +create_user() dict
        +login() dict
        +resolve_user_id() str
        +update_user() dict
        +delete_user() dict
        +restore_user() dict
        +update_profile() dict
        +generate_temp_password_for_user() dict
        +change_password() dict
        +reset_password_with_token() dict
        +create_wallet() dict
        +freeze_wallet() dict
        +unfreeze_wallet() dict
        +ban_user() dict
        +unban_user() dict
        +transfer() dict
        +mint() dict
        +top_up() dict
        +set_exchange_rate() dict
        +grant_role_permission() dict
        +grant_user_permission() dict
        +ensure_treasury_user() dict
        +_audit() void
        +list_audit_log() list
        +state_snapshot() dict
        +from_snapshot() MultiUserWalletLedger
    }

    class Permission {
        <<enumeration>>
        CREATE_USER
        CREATE_WALLET
        TRANSFER
        MINT
        SET_POLICY
        ASSIGN_ROLE
        VIEW_USERS
        VIEW_WALLETS
        VIEW_TRANSFERS
        EXCHANGE
        SET_EXCHANGE_RATE
        TOP_UP
        MANAGE_PERMISSIONS
        FREEZE_WALLET
        UNFREEZE_WALLET
        BAN_USER
        UNBAN_USER
        UPDATE_USER
        DELETE_USER
        RESTORE_USER
        GENERATE_TEMP_PASSWORD
        VIEW_AUDIT_LOG
        UPDATE_PROFILE
    }

    class Role {
        <<enumeration>>
        ADMIN
        OPERATOR
        VIEWER
    }

    MultiUserWalletLedger "1" --> "0..*" UserRecord
    MultiUserWalletLedger "1" --> "0..*" WalletRecord
    MultiUserWalletLedger "1" --> "0..*" ExchangeRate
    MultiUserWalletLedger ..> Permission
    MultiUserWalletLedger ..> Role
```

---

## 4. Casos de uso

### Gestion de usuarios
1. ADMIN crea un usuario — ID auto-generado `USR-XXXXX`, password hasheado con bcrypt.
2. Usuario hace login con `user_id` o `username`; recibe JWT.
3. ADMIN genera password temporal; usuario debe cambiarlo en el primer login.
4. ADMIN elimina (soft delete) un usuario: congela wallets, bloquea login; puede restaurar.
5. ADMIN modifica ID o display_name de un usuario.
6. Cualquier usuario actualiza su propio perfil (first_name, last_name, email, username).

### Operaciones de wallets
7. Usuario crea wallet UTXO o Account-based.
8. ADMIN/OPERATOR hace mint de tokens a una wallet.
9. Usuario transfiere fondos entre wallets (misma o distinta divisa con conversion automatica).
10. ADMIN realiza top-up desde tesoreria corporativa.
11. ADMIN congela/descongela una wallet (bloquea transferencias).
12. ADMIN banea un usuario (congela todas sus wallets automaticamente).

### Exchange y tesoreria
13. ADMIN configura tasa de cambio con comision para un par de divisas.
14. Transferencia entre wallets de distinta divisa aplica la tasa automaticamente.
15. ADMIN crea wallets de tesoreria por divisa; top-up debita de tesoreria.

### RBAC y permisos
16. ADMIN otorga/revoca permisos a nivel de rol (override de defaults hardcoded).
17. ADMIN otorga/revoca permisos a nivel de usuario (maxima prioridad).
18. Operaciones de moderacion requieren re-validacion JWT (sudo, 3 intentos).

### Auditoria
19. Cada accion significativa escribe una entrada en `audit_log` con actor, objetivo, timestamp y detalles.
20. ADMIN consulta el audit log filtrado por tipo de accion y/o usuario.

---

## 5. Diagramas de secuencia principales

### Login con password temporal

```mermaid
sequenceDiagram
    participant U as Usuario
    participant CLI as CLI/Terminal
    participant L as MultiUserWalletLedger
    participant A as auth.py

    U->>CLI: login(identifier, password)
    CLI->>L: resolve_user_id(identifier)
    L-->>CLI: user_id
    CLI->>L: login(user_id, password)
    L->>A: verify_password(password, hash)
    A-->>L: ok
    L->>L: verifica deleted_at, banned
    L->>L: verifica password_temp
    L-->>CLI: {token, must_change_password: true}
    CLI->>U: Solicitar cambio de password
    U->>CLI: change_password(actual, nuevo)
    CLI->>L: change_password(user_id, actual, nuevo)
    L->>L: limpia password_temp, token_temp
    L->>L: _audit(PASSWORD_CHANGED)
    L-->>CLI: {ok}
    CLI->>U: Mostrar menu
```

### Transferencia cross-currency

```mermaid
sequenceDiagram
    participant U as Usuario
    participant L as MultiUserWalletLedger
    participant E as ExchangeRate

    U->>L: transfer(from_wallet, to_wallet, amount, fee, token)
    L->>L: verifica token de sender
    L->>L: verifica estado frozen de wallets
    L->>L: detecta diferencia de divisas
    L->>E: convert_amount(amount)
    E-->>L: {gross, commission, net}
    L->>L: debita from_wallet (amount + fee)
    L->>L: acredita to_wallet (net)
    L->>L: registra transferencia tipo EXCHANGE
    L->>L: _audit(EXCHANGE)
    L-->>U: {transfer_id, detalles_conversion}
```

### Eliminacion suave de usuario

```mermaid
sequenceDiagram
    participant A as ADMIN
    participant L as MultiUserWalletLedger

    A->>L: delete_user(user_id, admin_token)
    L->>L: verifica token + permiso DELETE_USER
    L->>L: user.deleted_at = ahora()
    loop cada wallet
        L->>L: freeze_wallet(wallet_id)
        L->>L: _audit(WALLET_FROZEN)
    end
    L->>L: _audit(USER_DELETED)
    L-->>A: {deleted_at, wallets_congeladas}
```

---

## 6. Estructuras de datos

### UserRecord (dominio)

```python
@dataclass
class UserRecord:
    user_id: str          # Auto-generado USR-XXXXX
    display_name: str
    created_at: str       # ISO 8601
    banned: bool = False
    updated_at: str = ""
    deleted_at: str = ""  # No vacio = eliminacion suave
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    username: str = ""    # Unico, se usa para login
```

### Credenciales (dict interno)

```python
{
    "hash": str,           # Hash bcrypt
    "role": str,           # ADMIN | OPERATOR | VIEWER
    "password_temp": bool, # True = debe cambiar en proximo login
    "token_temp": str      # Token de un solo uso para reset de password
}
```

### Entrada de audit log

```python
{
    "log_id": str,        # UUID
    "timestamp": str,     # ISO 8601
    "actor_id": str,      # user_id de quien ejecuto la accion
    "action": str,        # USER_CREATED | LOGIN_SUCCESS | TRANSFER | ...
    "target_type": str,   # user | wallet | role | system
    "target_id": str,
    "details": dict       # Payload especifico de la accion
}
```

### Acciones auditadas

| Accion | Disparador |
|--------|-----------|
| USER_CREATED | create_user() |
| USER_UPDATED | update_user(), update_profile() |
| USER_DELETED | delete_user() |
| USER_RESTORED | restore_user() |
| USER_BANNED | ban_user() |
| USER_UNBANNED | unban_user() |
| WALLET_CREATED | create_wallet() |
| WALLET_FROZEN | freeze_wallet() |
| WALLET_UNFROZEN | unfreeze_wallet() |
| LOGIN_SUCCESS | login() exitoso |
| LOGIN_FAILED | login() password incorrecto |
| LOGIN_BANNED | login() cuenta baneada/eliminada |
| PASSWORD_CHANGED | change_password() |
| PASSWORD_TEMP_GENERATED | generate_temp_password_for_user() |
| ROLE_ASSIGNED | assign_role() |
| PERMISSION_GRANTED | grant_role/user_permission() |
| PERMISSION_REVOKED | revoke_role/user_permission() |
| TRANSFER | transfer() misma divisa |
| EXCHANGE | transfer() divisas distintas |
| MINT | mint() |
| TOP_UP | top_up() |

### ExchangeRate

```python
@dataclass
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    commission_pct: Decimal  # ej. Decimal("0.01") = 1%
```

### Estructura del snapshot JSON

```json
{
  "schema_version": 3,
  "updated_at": "2026-03-22T00:00:00+00:00",
  "users": {
    "USR-00001": {
      "display_name": "Alice", "deleted_at": "", "first_name": "Alice",
      "last_name": "Smith", "email": "alice@example.com", "username": "alicesmith"
    }
  },
  "credentials": {
    "USR-00001": { "hash": "...", "role": "ADMIN", "password_temp": false, "token_temp": "" }
  },
  "wallets": {
    "wallet_alice_01": { "user_id": "USR-00001", "model": "UTXO", "frozen": false }
  },
  "transfers": [],
  "exchange_rates": { "USD->EUR": { "rate": "0.92", "commission_pct": "0.01" } },
  "role_permission_overrides": { "OPERATOR": ["MINT"] },
  "user_permission_overrides": { "USR-00003": ["EXCHANGE"] },
  "audit_log": [],
  "user_seq": 3
}
```

---

## 7. Esquema PostgreSQL (V001–V009)

```mermaid
erDiagram
    users {
        varchar user_id PK
        varchar display_name
        timestamptz created_at
        boolean banned
        timestamptz updated_at
        timestamptz deleted_at
        varchar first_name
        varchar last_name
        varchar email
        varchar username UK
    }
    user_credentials {
        varchar user_id PK FK
        text password_hash
        varchar role
        boolean password_temp
        varchar token_temp
    }
    wallets {
        varchar wallet_id PK
        varchar user_id FK
        varchar model
        varchar currency
        timestamptz created_at
        boolean frozen
    }
    transfers {
        varchar transfer_id PK
        varchar from_wallet FK
        varchar to_wallet FK
        numeric amount
        numeric fee
        varchar transfer_type
        timestamptz created_at
        jsonb exchange_meta
    }
    exchange_rates {
        varchar pair_key PK
        varchar from_currency
        varchar to_currency
        numeric rate
        numeric commission_pct
    }
    role_permissions {
        varchar role PK
        varchar permission PK
    }
    user_permissions {
        varchar user_id PK FK
        varchar permission PK
    }
    audit_log {
        varchar log_id PK
        timestamptz timestamp
        varchar actor_id FK
        varchar action
        varchar target_type
        varchar target_id
        jsonb details
    }
    users ||--o{ user_credentials : "tiene"
    users ||--o{ wallets : "posee"
    wallets ||--o{ transfers : "origen"
    wallets ||--o{ transfers : "destino"
    users ||--o{ user_permissions : "tiene"
    users ||--o{ audit_log : "actua"
```

---

## 8. Resolucion de permisos

```
user_permission_overrides  (maxima prioridad)
        |
role_permission_overrides
        |
ROLE_PERMISSIONS hardcoded defaults
```

---

## 9. Convenciones de ejecucion

- `--json`: salida JSON para integracion programatica.
- `--token JWT`: JWT de usuario para autenticacion.
- `--sender-token WALLET_TOKEN`: token de wallet para transferencias (anti-replay).
- `--expected-nonce N`: previene replay attacks en transferencias.
- `user_id`: se auto-genera como `USR-XXXXX` si se omite al crear.
- Identificador de login: acepta `user_id` o `username`.

---

## 10. Limitaciones actuales

- Sin API REST ni GraphQL (planificado para v2.9.0+).
- Sin multi-tenancy ni aislamiento por organizacion.
- El audit log no tiene politica de retencion ni archivado.
- `token_temp` se almacena en texto plano en el snapshot JSON; usar backend PostgreSQL en produccion.
