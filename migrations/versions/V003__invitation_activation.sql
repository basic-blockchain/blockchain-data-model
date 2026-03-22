-- V003: Invitation tokens for ADMIN creation and activation codes for OPERATOR/VIEWER

CREATE TABLE admin_invitation_tokens (
    token      VARCHAR(64)  PRIMARY KEY,
    created_by VARCHAR(64)  NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    used       BOOLEAN      NOT NULL DEFAULT FALSE,
    used_by    VARCHAR(64)
);

CREATE INDEX idx_invitation_tokens_creator ON admin_invitation_tokens (created_by);

CREATE TABLE activation_codes (
    user_id    VARCHAR(64)  PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    code       VARCHAR(32)  NOT NULL,
    activated  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version, label) VALUES (3, 'V003__invitation_activation');
