-- =============================================================================
-- Sterling Vance Bank — Card Dispute & Chargeback Processing
-- Database: SQLite
-- File:     db/schema.sql
-- Purpose:  Full DDL for the dispute-processing system. Enforces referential
--           integrity, locks down enum columns with CHECK constraints, and
--           documents every table/column so the MCP server layer can reason
--           about the schema without touching raw SQL.
-- =============================================================================

-- SQLite does not enforce foreign keys by default.
-- Every connection that uses this database MUST run this pragma first.
PRAGMA foreign_keys = ON;


-- =============================================================================
-- TABLE: customers
-- One row per cardholder. risk_flag surfaces a pattern of past abuse and is
-- used by the notification trigger: when it flips to 'high', the server pushes
-- tools/list_changed to unlock fraud-related tools for the active analyst.
-- =============================================================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    phone        TEXT,
    -- 'normal' = no pattern detected
    -- 'elevated' = 3+ resolved disputes in the last 12 months
    -- 'high'     = flagged for likely abuse; unlocks fraud tools via notification
    risk_flag    TEXT NOT NULL DEFAULT 'normal'
                     CHECK (risk_flag IN ('normal', 'elevated', 'high')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =============================================================================
-- TABLE: analysts
-- Bank staff who are assigned disputes. Role controls which tools the MCP
-- server exposes via capability negotiation and live notifications:
--   junior  → read-only tools only on connect
--   senior  → read-only tools on connect; write tools unlocked after auth
-- =============================================================================
CREATE TABLE IF NOT EXISTS analysts (
    analyst_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    -- 'junior' or 'senior' — checked in every write-tool handler
    role        TEXT NOT NULL
                    CHECK (role IN ('junior', 'senior')),
    -- 1 = currently active / authenticated; 0 = inactive
    -- toggling this to 1 is what fires the tools/list_changed notification
    active      INTEGER NOT NULL DEFAULT 0
                    CHECK (active IN (0, 1))
);


-- =============================================================================
-- TABLE: merchants
-- Businesses that appear on transactions. risk_score (0–100) feeds the
-- evidence-summary sampling call so the model can reason about merchant
-- credibility without the server embedding that logic itself.
-- =============================================================================
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    -- 0 = no known issues; 100 = extremely high-risk / repeated chargebacks
    risk_score   INTEGER NOT NULL DEFAULT 0
                     CHECK (risk_score BETWEEN 0 AND 100)
);


-- =============================================================================
-- TABLE: accounts
-- Each customer may hold one or more credit-card accounts.
-- Disputes are ultimately anchored to a transaction on a specific account.
-- =============================================================================
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers (customer_id)
                         ON DELETE RESTRICT ON UPDATE CASCADE,
    -- 'active', 'closed', 'frozen'
    status       TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'closed', 'frozen')),
    credit_limit REAL NOT NULL CHECK (credit_limit > 0),
    opened_at    TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =============================================================================
-- TABLE: transactions
-- Individual charges posted to an account. A transaction may have at most one
-- dispute (enforced by the UNIQUE constraint on dispute.transaction_id).
-- =============================================================================
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id  TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts (account_id)
                            ON DELETE RESTRICT ON UPDATE CASCADE,
    merchant_id     TEXT NOT NULL REFERENCES merchants (merchant_id)
                            ON DELETE RESTRICT ON UPDATE CASCADE,
    amount          REAL NOT NULL CHECK (amount > 0),
    txn_date        TEXT NOT NULL,
    -- 'settled'  = posted and cleared
    -- 'pending'  = authorized but not yet settled
    -- 'reversed' = already reversed by the bank (guards against double-refund)
    status          TEXT NOT NULL DEFAULT 'settled'
                        CHECK (status IN ('settled', 'pending', 'reversed'))
);


-- =============================================================================
-- TABLE: disputes
-- Core of the system. One row per contested transaction.
--
-- Status lifecycle:
--   open  →  investigating  →  refunded
--                           →  denied
--                           →  escalated   (senior analyst required)
--
-- The 'amount' column is the disputed portion (may be less than the full
-- transaction amount). When amount > 500.00, the MCP tool handler fires
-- elicitation/create to pause and require explicit human approval before
-- updating status to 'refunded'.
-- =============================================================================
CREATE TABLE IF NOT EXISTS disputes (
    dispute_id           TEXT PRIMARY KEY,
    transaction_id       TEXT NOT NULL UNIQUE        -- one dispute per transaction
                                 REFERENCES transactions (transaction_id)
                                 ON DELETE RESTRICT ON UPDATE CASCADE,
    reason_code          TEXT NOT NULL
                             CHECK (reason_code IN (
                                 'duplicate_charge',
                                 'item_not_received',
                                 'unauthorized_transaction',
                                 'incorrect_amount',
                                 'service_not_rendered',
                                 'fraud'
                             )),
    -- See lifecycle above
    status               TEXT NOT NULL DEFAULT 'open'
                             CHECK (status IN (
                                 'open',
                                 'investigating',
                                 'refunded',
                                 'denied',
                                 'escalated'
                             )),
    -- The portion of the transaction the customer is disputing
    amount               REAL NOT NULL CHECK (amount > 0),
    evidence_notes       TEXT,                       -- free-text field fed to sampling
    opened_at            TEXT NOT NULL DEFAULT (datetime('now')),
    assigned_analyst_id  TEXT REFERENCES analysts (analyst_id)
                                 ON DELETE SET NULL ON UPDATE CASCADE,
    resolved_at          TEXT                        -- NULL until status leaves 'open'/'investigating'
);


-- =============================================================================
-- TABLE: dispute_history
-- Append-only audit log. One row is inserted whenever a dispute reaches a
-- terminal state (refunded / denied / escalated). Used by the server to
-- count a customer's recent outcomes and decide whether to flip risk_flag,
-- which in turn fires the tools/list_changed notification.
-- =============================================================================
CREATE TABLE IF NOT EXISTS dispute_history (
    history_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers (customer_id)
                         ON DELETE RESTRICT ON UPDATE CASCADE,
    dispute_id   TEXT NOT NULL REFERENCES disputes (dispute_id)
                         ON DELETE RESTRICT ON UPDATE CASCADE,
    -- mirrors the terminal status of the linked dispute
    outcome      TEXT NOT NULL
                     CHECK (outcome IN ('refunded', 'denied', 'escalated')),
    resolved_at  TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =============================================================================
-- INDEXES
-- Created separately so schema readers can see them clearly.
-- =============================================================================

-- Speed up dispute lookups by analyst (common in dashboard queries)
CREATE INDEX IF NOT EXISTS idx_disputes_analyst
    ON disputes (assigned_analyst_id);

-- Speed up history lookups per customer (used by risk-flag recalculation)
CREATE INDEX IF NOT EXISTS idx_dispute_history_customer
    ON dispute_history (customer_id, resolved_at);

-- Speed up transaction lookups per account
CREATE INDEX IF NOT EXISTS idx_transactions_account
    ON transactions (account_id, txn_date);
