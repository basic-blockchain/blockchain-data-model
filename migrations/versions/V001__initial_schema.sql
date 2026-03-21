-- V001: Initial PostgreSQL schema for blockchain-data-model
-- Domains: wallet, simulation, traceability

-- ==================== MIGRATION TRACKING ====================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER      PRIMARY KEY,
    label      VARCHAR(100) NOT NULL,
    applied_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ==================== ENUM TYPES ====================

CREATE TYPE wallet_model    AS ENUM ('ACCOUNT', 'UTXO');
CREATE TYPE transfer_type   AS ENUM ('MINT', 'TRANSFER');
CREATE TYPE transfer_status AS ENUM ('SETTLED', 'PENDING', 'FAILED');
CREATE TYPE risk_profile_t  AS ENUM ('STANDARD', 'LOW', 'MEDIUM', 'HIGH', 'RESTRICTED');
CREATE TYPE alert_type      AS ENUM ('TRANSFER_THRESHOLD', 'DAILY_THRESHOLD');
CREATE TYPE alert_severity  AS ENUM ('LOW', 'MEDIUM', 'HIGH');
CREATE TYPE compliance_status AS ENUM ('PENDING', 'PASS', 'FAIL');

-- ==================== WALLET DOMAIN ====================

CREATE TABLE users (
    user_id      VARCHAR(64)  PRIMARY KEY,
    display_name VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE wallets (
    wallet_id        VARCHAR(64)   PRIMARY KEY,
    user_id          VARCHAR(64)   NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    model            wallet_model  NOT NULL DEFAULT 'ACCOUNT',
    currency         VARCHAR(10)   NOT NULL DEFAULT 'USDX',
    balance          NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    auth_token       VARCHAR(12)   NOT NULL,
    token_issued_at  BIGINT        NOT NULL,
    token_expires_at BIGINT GENERATED ALWAYS AS (token_issued_at + 120) STORED,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_wallets_user ON wallets (user_id);

CREATE TABLE user_policies (
    user_id      VARCHAR(64) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    can_transfer BOOLEAN     NOT NULL DEFAULT TRUE,
    daily_limit  NUMERIC(28,8) CHECK (daily_limit IS NULL OR daily_limit > 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_risk_profiles (
    user_id                  VARCHAR(64)    PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    profile_name             risk_profile_t NOT NULL DEFAULT 'STANDARD',
    daily_limit              NUMERIC(28,8),
    transfer_alert_threshold NUMERIC(28,8),
    daily_alert_threshold    NUMERIC(28,8),
    updated_at               TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE TABLE wallet_nonces (
    wallet_id     VARCHAR(64) PRIMARY KEY REFERENCES wallets(wallet_id) ON DELETE CASCADE,
    current_nonce INTEGER     NOT NULL DEFAULT 0 CHECK (current_nonce >= 0)
);

CREATE TABLE wallet_utxos (
    utxo_id    VARCHAR(64)   PRIMARY KEY,
    wallet_id  VARCHAR(64)   NOT NULL REFERENCES wallets(wallet_id) ON DELETE RESTRICT,
    currency   VARCHAR(10)   NOT NULL,
    amount     NUMERIC(28,8) NOT NULL CHECK (amount > 0),
    source     VARCHAR(20)   NOT NULL,
    created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_utxos_wallet ON wallet_utxos (wallet_id);

CREATE TABLE transfers (
    transfer_id     VARCHAR(64)     PRIMARY KEY,
    type            transfer_type   NOT NULL,
    sender_wallet   VARCHAR(64),
    receiver_wallet VARCHAR(64)     NOT NULL,
    amount          NUMERIC(28,8)   NOT NULL CHECK (amount > 0),
    fee             NUMERIC(28,8)   NOT NULL DEFAULT 0 CHECK (fee >= 0),
    nonce           INTEGER,
    previous_hash   VARCHAR(64),
    tx_hash         VARCHAR(64),
    reference       VARCHAR(255)    NOT NULL DEFAULT '',
    status          transfer_status NOT NULL DEFAULT 'SETTLED',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_transfers_sender   ON transfers (sender_wallet, created_at);
CREATE INDEX idx_transfers_receiver ON transfers (receiver_wallet, created_at);
CREATE INDEX idx_transfers_daily    ON transfers (sender_wallet, created_at)
    WHERE type = 'TRANSFER';

CREATE TABLE alerts (
    alert_id     VARCHAR(64)    PRIMARY KEY,
    user_id      VARCHAR(64)    NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    profile_name risk_profile_t NOT NULL,
    type         alert_type     NOT NULL,
    severity     alert_severity NOT NULL,
    threshold    NUMERIC(28,8)  NOT NULL,
    observed     NUMERIC(28,8)  NOT NULL,
    transfer_id  VARCHAR(64)    NOT NULL,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_user     ON alerts (user_id, created_at);
CREATE INDEX idx_alerts_severity ON alerts (severity);

-- Revision tracking (replaces full JSON snapshots)
CREATE TABLE ledger_revisions (
    revision_id    VARCHAR(40) PRIMARY KEY,
    user_count     INTEGER     NOT NULL DEFAULT 0,
    wallet_count   INTEGER     NOT NULL DEFAULT 0,
    transfer_count INTEGER     NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==================== SIMULATION DOMAIN ====================

CREATE TABLE simulation_runs (
    run_id     VARCHAR(64)  PRIMARY KEY,
    model      VARCHAR(20)  NOT NULL,
    scenario   VARCHAR(100) NOT NULL,
    payload    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_sim_runs_model   ON simulation_runs (model, created_at DESC);
CREATE INDEX idx_sim_runs_payload ON simulation_runs USING GIN (payload jsonb_path_ops);

-- ==================== TRACEABILITY DOMAIN ====================

CREATE TABLE traceability_lots (
    lot_id                  VARCHAR(100) PRIMARY KEY,
    product                 VARCHAR(255) NOT NULL,
    origin                  VARCHAR(255) NOT NULL,
    owner                   VARCHAR(100) NOT NULL,
    compliance_status       compliance_status NOT NULL DEFAULT 'PENDING',
    required_events         TEXT[]       NOT NULL DEFAULT '{}',
    min_active_certificates INTEGER      NOT NULL DEFAULT 1,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_lots_owner ON traceability_lots (owner);

CREATE TABLE certificates (
    certificate_id VARCHAR(64)  PRIMARY KEY,
    lot_id         VARCHAR(100) NOT NULL REFERENCES traceability_lots(lot_id) ON DELETE CASCADE,
    cert_type      VARCHAR(100) NOT NULL,
    issuer         VARCHAR(255) NOT NULL,
    document_hash  VARCHAR(64)  NOT NULL,
    issued_at      TIMESTAMPTZ  NOT NULL,
    valid_until    TIMESTAMPTZ  NOT NULL,
    revoked        BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_certs_lot      ON certificates (lot_id);
CREATE INDEX idx_certs_validity ON certificates (valid_until) WHERE NOT revoked;

CREATE TABLE logistics_events (
    event_id   VARCHAR(64)  PRIMARY KEY,
    lot_id     VARCHAR(100) NOT NULL REFERENCES traceability_lots(lot_id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    actor      VARCHAR(255) NOT NULL,
    location   VARCHAR(255) NOT NULL,
    timestamp  TIMESTAMPTZ  NOT NULL,
    metadata   JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_events_lot  ON logistics_events (lot_id);
CREATE INDEX idx_events_type ON logistics_events (event_type);

-- Seed compliance profiles
CREATE TABLE compliance_profiles (
    profile_name            VARCHAR(50) PRIMARY KEY,
    required_events         TEXT[]      NOT NULL,
    min_active_certificates INTEGER     NOT NULL DEFAULT 1
);

INSERT INTO compliance_profiles (profile_name, required_events, min_active_certificates) VALUES
    ('DEFAULT', ARRAY['COSECHA', 'PROCESAMIENTO', 'EXPORTACION'], 1),
    ('CAFE',    ARRAY['COSECHA', 'PROCESAMIENTO', 'EXPORTACION'], 1),
    ('CACAO',   ARRAY['COSECHA', 'FERMENTACION', 'EXPORTACION'],  1);

-- Record this migration
INSERT INTO schema_migrations (version, label) VALUES (1, 'V001__initial_schema');
