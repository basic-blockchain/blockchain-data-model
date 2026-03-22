-- V004: Cross-currency exchange rates and transfer exchange metadata

-- Add EXCHANGE to transfer_type enum
ALTER TYPE transfer_type ADD VALUE 'EXCHANGE';

CREATE TABLE exchange_rates (
    pair_id         VARCHAR(20)    PRIMARY KEY,
    from_currency   VARCHAR(10)    NOT NULL,
    to_currency     VARCHAR(10)    NOT NULL,
    rate            NUMERIC(28,8)  NOT NULL CHECK (rate > 0),
    commission_pct  NUMERIC(5,2)   NOT NULL DEFAULT 1.00 CHECK (commission_pct >= 0),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    UNIQUE(from_currency, to_currency)
);

-- Extend transfers with exchange metadata columns
ALTER TABLE transfers ADD COLUMN sender_currency     VARCHAR(10);
ALTER TABLE transfers ADD COLUMN receiver_currency   VARCHAR(10);
ALTER TABLE transfers ADD COLUMN exchange_rate        NUMERIC(28,8);
ALTER TABLE transfers ADD COLUMN exchange_commission  NUMERIC(28,8);
ALTER TABLE transfers ADD COLUMN converted_amount     NUMERIC(28,8);
