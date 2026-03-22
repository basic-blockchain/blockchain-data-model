-- V009: User profile fields — first_name, last_name, email, username

ALTER TABLE users ADD COLUMN first_name VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN last_name VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN username VARCHAR(100) NOT NULL DEFAULT '';

CREATE INDEX idx_users_email ON users (email) WHERE email != '';
CREATE UNIQUE INDEX idx_users_username ON users (username) WHERE username != '';
