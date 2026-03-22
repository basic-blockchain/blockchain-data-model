-- V002: Authentication and role-based access control

CREATE TYPE user_role AS ENUM ('ADMIN', 'OPERATOR', 'VIEWER');

CREATE TABLE user_credentials (
    user_id       VARCHAR(64)  PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash VARCHAR(128) NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (
    user_id    VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role       user_role   NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role)
);

CREATE INDEX idx_user_roles_user ON user_roles (user_id);

INSERT INTO schema_migrations (version, label) VALUES (2, 'V002__auth_roles');
