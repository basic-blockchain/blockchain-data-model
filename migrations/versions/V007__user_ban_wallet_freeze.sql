-- V007: User ban and wallet freeze support

ALTER TABLE users ADD COLUMN banned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE wallets ADD COLUMN frozen BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_users_banned ON users (banned) WHERE banned = TRUE;
CREATE INDEX idx_wallets_frozen ON wallets (frozen) WHERE frozen = TRUE;
