-- V006: Dynamic permissions — catalog, role-level, and user-level permission tables

-- Permission catalog
CREATE TABLE permissions (
    permission_id  VARCHAR(50)  PRIMARY KEY,
    description    VARCHAR(255) NOT NULL DEFAULT ''
);

-- Seed from Permission enum
INSERT INTO permissions (permission_id) VALUES
    ('CREATE_USER'), ('CREATE_WALLET'), ('TRANSFER'), ('MINT'),
    ('SET_POLICY'), ('SET_RISK_PROFILE'), ('ASSIGN_ROLE'),
    ('VIEW_USERS'), ('VIEW_WALLETS'), ('VIEW_TRANSFERS'),
    ('VIEW_ALERTS'), ('VIEW_POLICIES'), ('VIEW_RISK_PROFILES'),
    ('VIEW_REVISIONS'), ('EXCHANGE'), ('SET_EXCHANGE_RATE'),
    ('TOP_UP'), ('MANAGE_PERMISSIONS');

-- Role-level permission overrides (when present, replaces hardcoded defaults)
CREATE TABLE role_permissions (
    role           user_role    NOT NULL,
    permission_id  VARCHAR(50)  NOT NULL REFERENCES permissions(permission_id),
    granted_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (role, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions (role);

-- User-level permission overrides (direct grants to individual users)
CREATE TABLE user_permissions (
    user_id        VARCHAR(64)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    permission_id  VARCHAR(50)  NOT NULL REFERENCES permissions(permission_id),
    granted_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, permission_id)
);

CREATE INDEX idx_user_permissions_user ON user_permissions (user_id);
CREATE INDEX idx_user_permissions_perm ON user_permissions (permission_id);
