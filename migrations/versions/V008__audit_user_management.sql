-- V008: User management fields, temporary password support, and audit log

-- User management fields
ALTER TABLE users ADD COLUMN updated_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ;
CREATE INDEX idx_users_deleted ON users (deleted_at) WHERE deleted_at IS NOT NULL;

-- Temporary password support in credentials
ALTER TABLE user_credentials ADD COLUMN password_temp BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_credentials ADD COLUMN token_temp VARCHAR(128);

-- Audit log table
CREATE TABLE audit_log (
    log_id      VARCHAR(64)  PRIMARY KEY,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    actor_id    VARCHAR(64)  NOT NULL,
    action      VARCHAR(50)  NOT NULL,
    target_type VARCHAR(30)  NOT NULL,
    target_id   VARCHAR(64)  NOT NULL,
    details     JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_audit_timestamp ON audit_log (timestamp DESC);
CREATE INDEX idx_audit_actor ON audit_log (actor_id);
CREATE INDEX idx_audit_action ON audit_log (action);
CREATE INDEX idx_audit_target ON audit_log (target_type, target_id);
