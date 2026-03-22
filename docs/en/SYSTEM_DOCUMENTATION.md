# System Technical Documentation — v2.8.0

## 1. Goal

Model and compare two blockchain approaches (UTXO and Account-based) with realistic functional scenarios, supply chain traceability, compliance, dual persistence (JSON / PostgreSQL), full multi-user wallet management, cross-currency exchange, corporate treasury, dynamic RBAC, and an append-only audit log.

---

## 2. Architecture diagram

```mermaid
flowchart TB
    subgraph CLI["CLI / Interaction Layer"]
        T[multiuser_terminal.py\n45 options, 10 sections]
        C[multiuser_wallet_cli.py\n45+ subcommands]
        S[blockchain_models_simulator.py]
    end

    subgraph Domain["Domain Layer (pure Python)"]
        L[multiuser_wallet_ledger.py\nUsers · Wallets · Transfers\nExchange · Treasury · Audit]
        A[auth.py\nJWT · bcrypt · RBAC\nDynamic permissions]
        E[exchange.py\nExchangeRate · convert_amount]
        CM[compliance.py]
        TR[traceability_models.py]
    end

    subgraph Persistence["Persistence Layer"]
        F[factory.py\nStrategy Pattern]
        J[multiuser_wallet_store.py\nJSON backend]
        P[pg_multiuser_wallet_store.py\nPostgreSQL backend]
        PC[pg_connection.py\nConnection pool]
    end

    subgraph DB["Storage"]
        JF[data/multiuser/wallet-ledger.json]
        PG[(PostgreSQL 16\nV001–V009 migrations)]
    end

    CLI --> Domain
    Domain --> Persistence
    F -->|PERSISTENCE_BACKEND=json| J
    F -->|PERSISTENCE_BACKEND=postgres| P
    P --> PC --> PG
    J --> JF
```

---

## 3. Domain class diagram

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

## 4. Use cases

### User management
1. ADMIN creates a user — auto-generated `USR-XXXXX` ID, bcrypt-hashed password.
2. User logs in by `user_id` or `username`; receives JWT.
3. ADMIN generates a temporary password; user is forced to change on first login.
4. ADMIN soft-deletes a user (freezes all wallets, blocks login); can restore later.
5. ADMIN updates user ID or display name.
6. Any user updates their own profile (first_name, last_name, email, username).

### Wallet operations
7. User creates a UTXO or Account-based wallet.
8. ADMIN/OPERATOR mints tokens to a wallet.
9. User transfers funds between wallets (same or cross-currency with exchange conversion).
10. ADMIN tops up a wallet from the corporate treasury.
11. ADMIN freezes/unfreezes a wallet (blocks transfers).
12. ADMIN bans a user (auto-freezes all wallets).

### Exchange and treasury
13. ADMIN sets exchange rate with commission for a currency pair.
14. Transfer between wallets of different currencies applies the rate automatically.
15. ADMIN creates treasury wallets per currency; top-up debits treasury.

### RBAC and permissions
16. ADMIN grants/revokes permissions at role level (override hardcoded defaults).
17. ADMIN grants/revokes permissions at user level (highest priority).
18. Moderation operations require sudo JWT re-validation.

### Audit
19. Every significant action writes an entry to `audit_log` with actor, target, timestamp, details.
20. ADMIN lists audit log filtered by action type and/or user.

---

## 5. Main sequence diagrams

### Login with temporary password

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI/Terminal
    participant L as MultiUserWalletLedger
    participant A as auth.py

    U->>CLI: login(identifier, password)
    CLI->>L: resolve_user_id(identifier)
    L-->>CLI: user_id
    CLI->>L: login(user_id, password)
    L->>A: verify_password(password, hash)
    A-->>L: ok
    L->>L: check deleted_at, banned
    L->>L: check password_temp
    L-->>CLI: {token, must_change_password: true}
    CLI->>U: Prompt: change password now
    U->>CLI: change_password(current, new)
    CLI->>L: change_password(user_id, current, new)
    L->>L: clear password_temp, token_temp
    L->>L: _audit(PASSWORD_CHANGED)
    L-->>CLI: {ok}
    CLI->>U: Show menu
```

### Cross-currency transfer

```mermaid
sequenceDiagram
    participant U as User
    participant L as MultiUserWalletLedger
    participant E as ExchangeRate

    U->>L: transfer(from_wallet, to_wallet, amount, fee, token)
    L->>L: verify sender token
    L->>L: check wallet frozen status
    L->>L: detect currency mismatch
    L->>E: convert_amount(amount)
    E-->>L: {gross, commission, net}
    L->>L: debit from_wallet (amount + fee)
    L->>L: credit to_wallet (net)
    L->>L: record EXCHANGE transfer
    L->>L: _audit(EXCHANGE)
    L-->>U: {transfer_id, conversion_details}
```

### Soft delete user

```mermaid
sequenceDiagram
    participant A as ADMIN
    participant L as MultiUserWalletLedger

    A->>L: delete_user(user_id, admin_token)
    L->>L: verify admin token + DELETE_USER permission
    L->>L: set user.deleted_at = now()
    loop each wallet
        L->>L: freeze_wallet(wallet_id)
        L->>L: _audit(WALLET_FROZEN)
    end
    L->>L: _audit(USER_DELETED)
    L-->>A: {deleted_at, frozen_wallets}
```

---

## 6. Data structures

### UserRecord (domain)

```python
@dataclass
class UserRecord:
    user_id: str          # Auto-generated USR-XXXXX
    display_name: str
    created_at: str       # ISO 8601
    banned: bool = False
    updated_at: str = ""
    deleted_at: str = ""  # Non-empty = soft deleted
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    username: str = ""    # Unique, used for login
```

### Credentials (dict)

```python
{
    "hash": str,           # bcrypt hash
    "role": str,           # ADMIN | OPERATOR | VIEWER
    "password_temp": bool, # True = must change on next login
    "token_temp": str      # One-use token for password reset
}
```

### Audit log entry

```python
{
    "log_id": str,        # UUID
    "timestamp": str,     # ISO 8601
    "actor_id": str,      # user_id of who performed the action
    "action": str,        # USER_CREATED | LOGIN_SUCCESS | TRANSFER | ...
    "target_type": str,   # user | wallet | role | system
    "target_id": str,
    "details": dict       # Action-specific payload
}
```

### Audit actions reference

| Action | Trigger |
|--------|---------|
| USER_CREATED | create_user() |
| USER_UPDATED | update_user(), update_profile() |
| USER_DELETED | delete_user() |
| USER_RESTORED | restore_user() |
| USER_BANNED | ban_user() |
| USER_UNBANNED | unban_user() |
| WALLET_CREATED | create_wallet() |
| WALLET_FROZEN | freeze_wallet() |
| WALLET_UNFROZEN | unfreeze_wallet() |
| LOGIN_SUCCESS | login() success |
| LOGIN_FAILED | login() wrong password |
| LOGIN_BANNED | login() banned/deleted account |
| PASSWORD_CHANGED | change_password() |
| PASSWORD_TEMP_GENERATED | generate_temp_password_for_user() |
| ROLE_ASSIGNED | assign_role() |
| PERMISSION_GRANTED | grant_role/user_permission() |
| PERMISSION_REVOKED | revoke_role/user_permission() |
| TRANSFER | transfer() same currency |
| EXCHANGE | transfer() cross-currency |
| MINT | mint() |
| TOP_UP | top_up() |

### ExchangeRate

```python
@dataclass
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    commission_pct: Decimal  # e.g. Decimal("0.01") = 1%
```

### JSON snapshot structure

```json
{
  "schema_version": 3,
  "updated_at": "2026-03-22T00:00:00+00:00",
  "users": { "USR-00001": { "display_name": "Alice", "deleted_at": "", ... } },
  "credentials": { "USR-00001": { "hash": "...", "role": "ADMIN", "password_temp": false, "token_temp": "" } },
  "wallets": { "wallet_alice_01": { "user_id": "USR-00001", "model": "UTXO", "frozen": false, ... } },
  "transfers": [],
  "policies": {},
  "risk_profiles": {},
  "alerts": [],
  "exchange_rates": { "USD->EUR": { "rate": "0.92", "commission_pct": "0.01" } },
  "role_permission_overrides": { "OPERATOR": ["MINT"] },
  "user_permission_overrides": { "USR-00003": ["EXCHANGE"] },
  "audit_log": [],
  "user_seq": 3
}
```

---

## 7. PostgreSQL schema (V001–V009)

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
    users ||--o{ user_credentials : "has"
    users ||--o{ wallets : "owns"
    wallets ||--o{ transfers : "from"
    wallets ||--o{ transfers : "to"
    users ||--o{ user_permissions : "has"
    users ||--o{ audit_log : "acts"
```

---

## 8. Permission resolution order

```
user_permission_overrides  (highest priority)
        ↓
role_permission_overrides
        ↓
ROLE_PERMISSIONS hardcoded defaults
```

---

## 9. CLI execution conventions

- `--json`: machine-readable JSON output.
- `--token JWT`: user-level JWT for authentication.
- `--sender-token WALLET_TOKEN`: wallet-level token for transfers (anti-replay).
- `--expected-nonce N`: prevents replay attacks on transfers.
- `user_id`: auto-generated as `USR-XXXXX` if omitted at creation.
- Login identifier: accepts `user_id` or `username`.

---

## 10. Current limitations

- No REST or GraphQL API (planned for v2.9.0+).
- No multi-tenancy or organization-level isolation.
- Audit log has no retention policy or archival mechanism.
- `token_temp` stored as plaintext in JSON snapshot; use PostgreSQL backend in production.
