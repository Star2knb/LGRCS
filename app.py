-- ============================================================================
-- RevAc (Revenue Administration & Collection) Application Suite
-- Database Schema — Abuja Municipal Area Council (AMAC) Deployment
-- Alliance Consulting & Digital Solutions Ltd (ACDSL) — Lead Revenue
-- Technology Consultant
-- Target platform: PostgreSQL 15+  |  July 2026
--
-- NOTE: This schema is the technical companion to the "Technology
-- Computerisation of the AMAC Revenue Department" proposal (July 2026).
-- It implements the nine RevAc modules, the three access levels
-- (Consultant Dashboard / Council Admin / Field Agent), the harmonised
-- chart of revenue, and multi-channel e-payment integration covering:
--   1. POS terminals (FirstBank-issued);
--   2. Over-the-counter (teller) payments at FirstBank branches;
--   3. Internet banking and mobile banking transfers;
--   4. USSD payment channels;
--   5. FirstMonie agent banking network.
-- Revenue items, rates and codes are ILLUSTRATIVE placeholders pending the
-- Harmonisation Workstream (Component 3) and Council rate approval.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS revac;
SET search_path TO revac;

-- ---------------------------------------------------------------------------
-- 1. ORGANISATION & TERRITORY
-- ---------------------------------------------------------------------------

CREATE TABLE council (
    council_id        SERIAL PRIMARY KEY,
    council_code      VARCHAR(10)  NOT NULL UNIQUE,          -- e.g. 'AMAC'
    council_name      VARCHAR(120) NOT NULL,                 -- Abuja Municipal Area Council
    state_territory   VARCHAR(60)  NOT NULL DEFAULT 'Federal Capital Territory',
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE ward_zone (
    ward_id           SERIAL PRIMARY KEY,
    council_id        INT NOT NULL REFERENCES council(council_id),
    ward_code         VARCHAR(20)  NOT NULL,
    ward_name         VARCHAR(120) NOT NULL,
    zone_type         VARCHAR(20)  NOT NULL DEFAULT 'WARD'
                      CHECK (zone_type IN ('WARD','ZONE','DISTRICT')),
    UNIQUE (council_id, ward_code)
);

-- Sub-consultants unified onto the platform (Component 4)
CREATE TABLE sub_consultant (
    consultant_id     SERIAL PRIMARY KEY,
    council_id        INT NOT NULL REFERENCES council(council_id),
    consultant_code   VARCHAR(20)  NOT NULL UNIQUE,
    consultant_name   VARCHAR(160) NOT NULL,
    contract_ref      VARCHAR(60),
    commission_rate   NUMERIC(5,2) NOT NULL DEFAULT 0.00,    -- % per contract terms
    status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','EXITED')),
    onboarded_at      TIMESTAMPTZ,
    exited_at         TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Portfolio assignment: which revenue heads / territories each
-- sub-consultant administers (per-portfolio data segregation boundary)
CREATE TABLE consultant_portfolio (
    portfolio_id      SERIAL PRIMARY KEY,
    consultant_id     INT NOT NULL REFERENCES sub_consultant(consultant_id),
    revenue_item_id   INT NOT NULL,                          -- FK added after revenue_item
    ward_id           INT REFERENCES ward_zone(ward_id),     -- NULL = council-wide
    effective_from    DATE NOT NULL,
    effective_to      DATE,
    UNIQUE (consultant_id, revenue_item_id, ward_id, effective_from)
);

-- ---------------------------------------------------------------------------
-- 2. USERS, ROLES & ACCESS LEVELS (Security, Audit & Compliance module)
-- ---------------------------------------------------------------------------

CREATE TABLE app_role (
    role_id           SERIAL PRIMARY KEY,
    role_code         VARCHAR(30) NOT NULL UNIQUE,
    role_name         VARCHAR(80) NOT NULL,
    access_level      VARCHAR(20) NOT NULL
                      CHECK (access_level IN ('COUNCIL_ADMIN','CONSULTANT','AGENT','GLOBAL_VIEW'))
);

CREATE TABLE app_user (
    user_id           SERIAL PRIMARY KEY,
    council_id        INT NOT NULL REFERENCES council(council_id),
    consultant_id     INT REFERENCES sub_consultant(consultant_id), -- NULL for Council staff
    role_id           INT NOT NULL REFERENCES app_role(role_id),
    username          VARCHAR(60)  NOT NULL UNIQUE,
    full_name         VARCHAR(160) NOT NULL,
    phone             VARCHAR(20),
    email             VARCHAR(160),
    password_hash     TEXT NOT NULL,                         -- bcrypt/argon2
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    requires_2fa      BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Field agents (Council staff or sub-consultant-deployed) — Agent view
CREATE TABLE field_agent (
    agent_id          SERIAL PRIMARY KEY,
    user_id           INT NOT NULL UNIQUE REFERENCES app_user(user_id),
    consultant_id     INT REFERENCES sub_consultant(consultant_id),
    agent_code        VARCHAR(20) NOT NULL UNIQUE,
    assigned_ward_id  INT REFERENCES ward_zone(ward_id),
    device_imei       VARCHAR(30),
    status            VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','SUSPENDED','EXITED'))
);

-- Immutable audit trail (maker-checker & NDPA/NDPR accountability)
CREATE TABLE audit_log (
    audit_id          BIGSERIAL PRIMARY KEY,
    user_id           INT REFERENCES app_user(user_id),
    action            VARCHAR(60)  NOT NULL,                 -- e.g. BILL_APPROVED
    entity_type       VARCHAR(60)  NOT NULL,
    entity_id         BIGINT,
    detail            JSONB,
    ip_address        INET,
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- 3. HARMONISED CHART OF REVENUE (Component 3 — revenue master data)
-- ---------------------------------------------------------------------------

CREATE TABLE revenue_category (
    category_id       SERIAL PRIMARY KEY,
    council_id        INT NOT NULL REFERENCES council(council_id),
    category_code     VARCHAR(20)  NOT NULL,
    category_name     VARCHAR(160) NOT NULL,                 -- Rates, Licences, Fees, Levies...
    UNIQUE (council_id, category_code)
);

CREATE TABLE revenue_item (
    revenue_item_id   SERIAL PRIMARY KEY,
    category_id       INT NOT NULL REFERENCES revenue_category(category_id),
    harmonised_code   VARCHAR(30)  NOT NULL UNIQUE,          -- e.g. AMAC-LIC-014
    item_name         VARCHAR(200) NOT NULL,
    legal_basis       VARCHAR(240),                          -- enabling law / bye-law
    unit_of_charge    VARCHAR(60),                           -- per annum, per unit, per sqm...
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    in_initial_scope  BOOLEAN NOT NULL DEFAULT TRUE,         -- FALSE = accommodated for future
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE consultant_portfolio
    ADD CONSTRAINT fk_portfolio_item
    FOREIGN KEY (revenue_item_id) REFERENCES revenue_item(revenue_item_id);

-- Rate schedule — rate-setting remains the Council's statutory prerogative
CREATE TABLE rate_schedule (
    rate_id           SERIAL PRIMARY KEY,
    revenue_item_id   INT NOT NULL REFERENCES revenue_item(revenue_item_id),
    rate_amount       NUMERIC(18,2) NOT NULL,
    rate_basis        VARCHAR(20) NOT NULL DEFAULT 'FLAT'
                      CHECK (rate_basis IN ('FLAT','PER_UNIT','PERCENTAGE','BANDED')),
    approved_by_ref   VARCHAR(120),                          -- Council resolution reference
    effective_from    DATE NOT NULL,
    effective_to      DATE
);

-- ---------------------------------------------------------------------------
-- 4. TAXPAYER ENUMERATION & REGISTRY
-- ---------------------------------------------------------------------------

CREATE TABLE payer (
    payer_id          BIGSERIAL PRIMARY KEY,
    council_id        INT NOT NULL REFERENCES council(council_id),
    payer_ref         VARCHAR(24) NOT NULL UNIQUE,           -- unique ratepayer ID
    payer_type        VARCHAR(20) NOT NULL
                      CHECK (payer_type IN ('INDIVIDUAL','BUSINESS','GOVERNMENT','NGO')),
    full_name         VARCHAR(200) NOT NULL,
    phone             VARCHAR(20),
    email             VARCHAR(160),
    tin               VARCHAR(30),                           -- Tax Identification Number
    nin_bvn_hash      TEXT,                                  -- hashed KYC identifier (NDPA)
    ward_id           INT REFERENCES ward_zone(ward_id),
    address           TEXT,
    geo_lat           NUMERIC(10,7),
    geo_lng           NUMERIC(10,7),
    kyc_status        VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                      CHECK (kyc_status IN ('PENDING','VERIFIED','FLAGGED')),
    is_duplicate_of   BIGINT REFERENCES payer(payer_id),     -- deduplication linkage
    created_by        INT REFERENCES app_user(user_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payer_name  ON payer(full_name);
CREATE INDEX idx_payer_ward  ON payer(ward_id);

-- Enumerated revenue-generating assets (premises, shops, signage, etc.)
CREATE TABLE enumerated_asset (
    asset_id          BIGSERIAL PRIMARY KEY,
    payer_id          BIGINT NOT NULL REFERENCES payer(payer_id),
    asset_ref         VARCHAR(24) NOT NULL UNIQUE,
    asset_type        VARCHAR(60) NOT NULL,                  -- premises, shop, kiosk, signage...
    description       TEXT,
    ward_id           INT REFERENCES ward_zone(ward_id),
    geo_lat           NUMERIC(10,7),
    geo_lng           NUMERIC(10,7),
    enumerated_by     INT REFERENCES field_agent(agent_id),
    enumerated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    photo_url         TEXT
);

-- ---------------------------------------------------------------------------
-- 5. ASSESSMENT & e-BILLING
-- ---------------------------------------------------------------------------

CREATE TABLE assessment (
    assessment_id     BIGSERIAL PRIMARY KEY,
    payer_id          BIGINT NOT NULL REFERENCES payer(payer_id),
    asset_id          BIGINT REFERENCES enumerated_asset(asset_id),
    revenue_item_id   INT NOT NULL REFERENCES revenue_item(revenue_item_id),
    rate_id           INT NOT NULL REFERENCES rate_schedule(rate_id),
    consultant_id     INT REFERENCES sub_consultant(consultant_id),
    period_year       SMALLINT NOT NULL,
    quantity          NUMERIC(12,2) NOT NULL DEFAULT 1,
    assessed_amount   NUMERIC(18,2) NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                      CHECK (status IN ('DRAFT','APPROVED','BILLED','CANCELLED')),
    approved_by       INT REFERENCES app_user(user_id),      -- maker-checker
    created_by        INT REFERENCES app_user(user_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE bill (
    bill_id           BIGSERIAL PRIMARY KEY,
    bill_ref          VARCHAR(30) NOT NULL UNIQUE,           -- unique bill reference
    payer_id          BIGINT NOT NULL REFERENCES payer(payer_id),
    consultant_id     INT REFERENCES sub_consultant(consultant_id),
    total_amount      NUMERIC(18,2) NOT NULL,
    amount_paid       NUMERIC(18,2) NOT NULL DEFAULT 0,
    due_date          DATE NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'ISSUED'
                      CHECK (status IN ('ISSUED','PART_PAID','PAID','OVERDUE','CANCELLED')),
    issued_by         INT REFERENCES app_user(user_id),
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bill_payer  ON bill(payer_id);
CREATE INDEX idx_bill_status ON bill(status);

CREATE TABLE bill_line (
    bill_line_id      BIGSERIAL PRIMARY KEY,
    bill_id           BIGINT NOT NULL REFERENCES bill(bill_id) ON DELETE CASCADE,
    assessment_id     BIGINT NOT NULL REFERENCES assessment(assessment_id),
    line_amount       NUMERIC(18,2) NOT NULL
);

-- ---------------------------------------------------------------------------
-- 6. MULTI-CHANNEL e-PAYMENTS (POS / OTC teller / Internet & Mobile banking /
--    USSD / FirstMonie agent banking) + API integration layer
-- ---------------------------------------------------------------------------

CREATE TABLE payment_channel (
    channel_id        SERIAL PRIMARY KEY,
    channel_code      VARCHAR(20) NOT NULL UNIQUE,
    channel_name      VARCHAR(120) NOT NULL,
    provider          VARCHAR(120) NOT NULL,                 -- e.g. FirstBank, gateway
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

-- Seed: the five e-channels in the FirstBank integration scope
INSERT INTO payment_channel (channel_code, channel_name, provider) VALUES
 ('POS',       'POS Terminal',                          'FirstBank of Nigeria'),
 ('OTC',       'Over-the-Counter (Branch Teller)',      'FirstBank of Nigeria'),
 ('IB_MB',     'Internet / Mobile Banking Transfer',    'FirstBank of Nigeria'),
 ('USSD',      'USSD Payment',                          'FirstBank of Nigeria'),
 ('FIRSTMONIE','FirstMonie Agent Banking Network',      'FirstBank of Nigeria');

-- Physical POS terminal fleet (e.g. terminals already deployed at the Council)
CREATE TABLE pos_terminal (
    terminal_id       SERIAL PRIMARY KEY,
    terminal_serial   VARCHAR(40) NOT NULL UNIQUE,
    bank_terminal_id  VARCHAR(40),                           -- acquirer TID
    assigned_agent_id INT REFERENCES field_agent(agent_id),
    ward_id           INT REFERENCES ward_zone(ward_id),
    status            VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','FAULTY','RETIRED'))
);

CREATE TABLE payment (
    payment_id        BIGSERIAL PRIMARY KEY,
    payment_ref       VARCHAR(40) NOT NULL UNIQUE,
    bill_id           BIGINT NOT NULL REFERENCES bill(bill_id),
    channel_id        INT NOT NULL REFERENCES payment_channel(channel_id),
    terminal_id       INT REFERENCES pos_terminal(terminal_id),
    agent_id          INT REFERENCES field_agent(agent_id),
    amount            NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    bank_txn_ref      VARCHAR(60),                           -- bank/gateway reference
    txn_status        VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED'
                      CHECK (txn_status IN ('PENDING','CONFIRMED','FAILED','REVERSED')),
    paid_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    geo_lat           NUMERIC(10,7),
    geo_lng           NUMERIC(10,7)
);
CREATE INDEX idx_payment_bill    ON payment(bill_id);
CREATE INDEX idx_payment_channel ON payment(channel_id, paid_at);

-- Inbound channel notifications (webhooks / statement feeds) prior to matching
CREATE TABLE channel_transaction_feed (
    feed_id           BIGSERIAL PRIMARY KEY,
    channel_id        INT NOT NULL REFERENCES payment_channel(channel_id),
    bank_txn_ref      VARCHAR(60) NOT NULL,
    narration         TEXT,
    amount            NUMERIC(18,2) NOT NULL,
    value_date        DATE NOT NULL,
    raw_payload       JSONB,                                 -- full API/webhook payload
    match_status      VARCHAR(20) NOT NULL DEFAULT 'UNMATCHED'
                      CHECK (match_status IN ('UNMATCHED','MATCHED','EXCEPTION')),
    matched_payment_id BIGINT REFERENCES payment(payment_id),
    received_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, bank_txn_ref)
);

-- ---------------------------------------------------------------------------
-- 7. e-RECEIPTING & VERIFICATION
-- ---------------------------------------------------------------------------

CREATE TABLE receipt (
    receipt_id        BIGSERIAL PRIMARY KEY,
    receipt_ref       VARCHAR(40) NOT NULL UNIQUE,
    payment_id        BIGINT NOT NULL UNIQUE REFERENCES payment(payment_id),
    qr_token          UUID NOT NULL DEFAULT gen_random_uuid(),  -- QR/SMS verification
    sms_sent          BOOLEAN NOT NULL DEFAULT FALSE,
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_count    INT NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 8. REVENUE ACCOUNTING, RECONCILIATION & COMMISSION SETTLEMENT
-- ---------------------------------------------------------------------------

CREATE TABLE reconciliation_run (
    recon_id          BIGSERIAL PRIMARY KEY,
    run_date          DATE NOT NULL,
    channel_id        INT REFERENCES payment_channel(channel_id),
    total_platform    NUMERIC(18,2) NOT NULL DEFAULT 0,
    total_bank        NUMERIC(18,2) NOT NULL DEFAULT 0,
    variance          NUMERIC(18,2) GENERATED ALWAYS AS (total_platform - total_bank) STORED,
    status            VARCHAR(20) NOT NULL DEFAULT 'OPEN'
                      CHECK (status IN ('OPEN','BALANCED','EXCEPTIONS','CLOSED')),
    run_by            INT REFERENCES app_user(user_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reconciliation_exception (
    exception_id      BIGSERIAL PRIMARY KEY,
    recon_id          BIGINT NOT NULL REFERENCES reconciliation_run(recon_id),
    feed_id           BIGINT REFERENCES channel_transaction_feed(feed_id),
    payment_id        BIGINT REFERENCES payment(payment_id),
    exception_type    VARCHAR(40) NOT NULL,                  -- MISSING_IN_BANK, DUP, AMT_DIFF...
    resolution_note   TEXT,
    resolved_by       INT REFERENCES app_user(user_id),
    resolved_at       TIMESTAMPTZ
);

CREATE TABLE commission_settlement (
    settlement_id     BIGSERIAL PRIMARY KEY,
    consultant_id     INT NOT NULL REFERENCES sub_consultant(consultant_id),
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    gross_collections NUMERIC(18,2) NOT NULL,
    commission_rate   NUMERIC(5,2)  NOT NULL,                -- snapshot of contract rate
    commission_amount NUMERIC(18,2) NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'COMPUTED'
                      CHECK (status IN ('COMPUTED','APPROVED','SETTLED','DISPUTED')),
    approved_by       INT REFERENCES app_user(user_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (consultant_id, period_start, period_end)
);

-- ---------------------------------------------------------------------------
-- 9. DEBT MANAGEMENT & ENFORCEMENT
-- ---------------------------------------------------------------------------

CREATE TABLE debt_case (
    debt_id           BIGSERIAL PRIMARY KEY,
    bill_id           BIGINT NOT NULL REFERENCES bill(bill_id),
    ageing_bucket     VARCHAR(20) NOT NULL
                      CHECK (ageing_bucket IN ('0_30','31_60','61_90','OVER_90')),
    reminder_count    INT NOT NULL DEFAULT 0,
    last_reminder_at  TIMESTAMPTZ,
    enforcement_stage VARCHAR(30) NOT NULL DEFAULT 'NONE'
                      CHECK (enforcement_stage IN
                        ('NONE','FIRST_NOTICE','FINAL_NOTICE','ENFORCEMENT','LEGAL','CLOSED')),
    assigned_to       INT REFERENCES app_user(user_id),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 10. FIELD OPERATIONS (Agent mobile app — offline-capable)
-- ---------------------------------------------------------------------------

CREATE TABLE agent_daily_return (
    return_id         BIGSERIAL PRIMARY KEY,
    agent_id          INT NOT NULL REFERENCES field_agent(agent_id),
    return_date       DATE NOT NULL,
    visits_count      INT NOT NULL DEFAULT 0,
    bills_issued      INT NOT NULL DEFAULT 0,
    amount_collected  NUMERIC(18,2) NOT NULL DEFAULT 0,
    synced_at         TIMESTAMPTZ,                           -- offline sync timestamp
    UNIQUE (agent_id, return_date)
);

CREATE TABLE sync_queue (                                    -- offline store-and-forward
    sync_id           BIGSERIAL PRIMARY KEY,
    agent_id          INT NOT NULL REFERENCES field_agent(agent_id),
    entity_type       VARCHAR(60) NOT NULL,
    payload           JSONB NOT NULL,
    device_created_at TIMESTAMPTZ NOT NULL,
    synced_at         TIMESTAMPTZ,
    sync_status       VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                      CHECK (sync_status IN ('PENDING','SYNCED','CONFLICT'))
);

-- ---------------------------------------------------------------------------
-- 11. REPORTING VIEWS (Council Dashboard & Global Performance View)
-- ---------------------------------------------------------------------------

CREATE VIEW v_collections_by_channel AS
SELECT pc.channel_name,
       date_trunc('day', p.paid_at)::date AS collection_date,
       COUNT(*)        AS txn_count,
       SUM(p.amount)   AS total_collected
FROM payment p
JOIN payment_channel pc ON pc.channel_id = p.channel_id
WHERE p.txn_status = 'CONFIRMED'
GROUP BY pc.channel_name, date_trunc('day', p.paid_at);

CREATE VIEW v_global_performance AS
SELECT sc.consultant_name,
       ri.harmonised_code,
       ri.item_name,
       w.ward_name,
       SUM(b.total_amount)                    AS total_billed,
       SUM(b.amount_paid)                     AS total_collected,
       SUM(b.total_amount - b.amount_paid)    AS outstanding
FROM bill b
LEFT JOIN sub_consultant sc ON sc.consultant_id = b.consultant_id
JOIN bill_line bl  ON bl.bill_id = b.bill_id
JOIN assessment a  ON a.assessment_id = bl.assessment_id
JOIN revenue_item ri ON ri.revenue_item_id = a.revenue_item_id
JOIN payer py      ON py.payer_id = b.payer_id
LEFT JOIN ward_zone w ON w.ward_id = py.ward_id
GROUP BY sc.consultant_name, ri.harmonised_code, ri.item_name, w.ward_name;

CREATE VIEW v_debt_ageing AS
SELECT d.ageing_bucket,
       COUNT(*)                                AS cases,
       SUM(b.total_amount - b.amount_paid)     AS outstanding_amount
FROM debt_case d
JOIN bill b ON b.bill_id = d.bill_id
WHERE b.status IN ('ISSUED','PART_PAID','OVERDUE')
GROUP BY d.ageing_bucket;

-- ============================================================================
-- END OF SCHEMA — 24 tables, 3 reporting views
-- Row-level security policies (per-portfolio segregation) to be applied per
-- deployment: each CONSULTANT role is constrained to rows where
-- consultant_id = current_setting('revac.consultant_id')::int.
-- ============================================================================
