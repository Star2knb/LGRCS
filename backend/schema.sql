-- ===========================================================================
-- RevAc Application Suite — SQLite schema (runtime edition)
-- Derived from RevAc_AMAC_Database_Schema.sql (PostgreSQL reference DDL)
-- Alliance Consulting & Digital Solutions Ltd (ACDSL)
-- Deployment: Abuja Municipal Area Council (AMAC), FCT
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- --- 1. ORGANISATION & TERRITORY -------------------------------------------
CREATE TABLE council (
    council_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    council_code    TEXT NOT NULL UNIQUE,
    council_name    TEXT NOT NULL,
    state_territory TEXT NOT NULL DEFAULT 'Federal Capital Territory',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ward_zone (
    ward_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id INTEGER NOT NULL REFERENCES council(council_id),
    ward_code  TEXT NOT NULL,
    ward_name  TEXT NOT NULL,
    zone_type  TEXT NOT NULL DEFAULT 'WARD' CHECK (zone_type IN ('WARD','ZONE','DISTRICT')),
    UNIQUE (council_id, ward_code)
);

CREATE TABLE sub_consultant (
    consultant_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id      INTEGER NOT NULL REFERENCES council(council_id),
    consultant_code TEXT NOT NULL UNIQUE,
    consultant_name TEXT NOT NULL,
    contract_ref    TEXT,
    commission_rate REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','EXITED')),
    onboarded_at    TEXT,
    exited_at       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- --- 2. USERS, ROLES & ACCESS LEVELS ---------------------------------------
CREATE TABLE app_role (
    role_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role_code    TEXT NOT NULL UNIQUE,
    role_name    TEXT NOT NULL,
    access_level TEXT NOT NULL
                 CHECK (access_level IN ('COUNCIL_ADMIN','CONSULTANT','AGENT','GLOBAL_VIEW'))
);

CREATE TABLE app_user (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id    INTEGER NOT NULL REFERENCES council(council_id),
    consultant_id INTEGER REFERENCES sub_consultant(consultant_id),
    role_id       INTEGER NOT NULL REFERENCES app_role(role_id),
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    phone         TEXT,
    email         TEXT,
    password_hash TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    requires_2fa  INTEGER NOT NULL DEFAULT 1,
    last_login_at TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE field_agent (
    agent_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL UNIQUE REFERENCES app_user(user_id),
    consultant_id    INTEGER REFERENCES sub_consultant(consultant_id),
    agent_code       TEXT NOT NULL UNIQUE,
    assigned_ward_id INTEGER REFERENCES ward_zone(ward_id),
    device_imei      TEXT,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','SUSPENDED','EXITED'))
);

CREATE TABLE audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES app_user(user_id),
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   INTEGER,
    detail      TEXT,
    ip_address  TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);

-- --- 3. HARMONISED CHART OF REVENUE ----------------------------------------
CREATE TABLE revenue_category (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id    INTEGER NOT NULL REFERENCES council(council_id),
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    UNIQUE (council_id, category_code)
);

CREATE TABLE revenue_item (
    revenue_item_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id      INTEGER NOT NULL REFERENCES revenue_category(category_id),
    harmonised_code  TEXT NOT NULL UNIQUE,
    item_name        TEXT NOT NULL,
    legal_basis      TEXT,
    unit_of_charge   TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    in_initial_scope INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE consultant_portfolio (
    portfolio_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    consultant_id   INTEGER NOT NULL REFERENCES sub_consultant(consultant_id),
    revenue_item_id INTEGER NOT NULL REFERENCES revenue_item(revenue_item_id),
    ward_id         INTEGER REFERENCES ward_zone(ward_id),
    effective_from  TEXT NOT NULL,
    effective_to    TEXT
);

CREATE TABLE rate_schedule (
    rate_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    revenue_item_id INTEGER NOT NULL REFERENCES revenue_item(revenue_item_id),
    rate_amount     REAL NOT NULL,
    rate_basis      TEXT NOT NULL DEFAULT 'FLAT'
                    CHECK (rate_basis IN ('FLAT','PER_UNIT','PERCENTAGE','BANDED')),
    approved_by_ref TEXT,
    effective_from  TEXT NOT NULL,
    effective_to    TEXT
);

-- --- 4. TAXPAYER ENUMERATION & REGISTRY ------------------------------------
CREATE TABLE payer (
    payer_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id      INTEGER NOT NULL REFERENCES council(council_id),
    payer_ref       TEXT NOT NULL UNIQUE,
    payer_type      TEXT NOT NULL CHECK (payer_type IN ('INDIVIDUAL','BUSINESS','GOVERNMENT','NGO')),
    full_name       TEXT NOT NULL,
    phone           TEXT,
    email           TEXT,
    tin             TEXT,
    nin_bvn_hash    TEXT,
    ward_id         INTEGER REFERENCES ward_zone(ward_id),
    address         TEXT,
    geo_lat         REAL,
    geo_lng         REAL,
    kyc_status      TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (kyc_status IN ('PENDING','VERIFIED','FLAGGED')),
    is_duplicate_of INTEGER REFERENCES payer(payer_id),
    created_by      INTEGER REFERENCES app_user(user_id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_payer_name ON payer(full_name);
CREATE INDEX idx_payer_ward ON payer(ward_id);

CREATE TABLE enumerated_asset (
    asset_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    payer_id      INTEGER NOT NULL REFERENCES payer(payer_id),
    asset_ref     TEXT NOT NULL UNIQUE,
    asset_type    TEXT NOT NULL,
    description   TEXT,
    ward_id       INTEGER REFERENCES ward_zone(ward_id),
    geo_lat       REAL,
    geo_lng       REAL,
    enumerated_by INTEGER REFERENCES field_agent(agent_id),
    enumerated_at TEXT NOT NULL DEFAULT (datetime('now')),
    photo_url     TEXT
);

-- --- 5. ASSESSMENT & e-BILLING ---------------------------------------------
CREATE TABLE assessment (
    assessment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    payer_id        INTEGER NOT NULL REFERENCES payer(payer_id),
    asset_id        INTEGER REFERENCES enumerated_asset(asset_id),
    revenue_item_id INTEGER NOT NULL REFERENCES revenue_item(revenue_item_id),
    rate_id         INTEGER NOT NULL REFERENCES rate_schedule(rate_id),
    consultant_id   INTEGER REFERENCES sub_consultant(consultant_id),
    period_year     INTEGER NOT NULL,
    quantity        REAL NOT NULL DEFAULT 1,
    assessed_amount REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT','APPROVED','BILLED','CANCELLED')),
    approved_by     INTEGER REFERENCES app_user(user_id),
    created_by      INTEGER REFERENCES app_user(user_id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE bill (
    bill_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_ref      TEXT NOT NULL UNIQUE,
    payer_id      INTEGER NOT NULL REFERENCES payer(payer_id),
    consultant_id INTEGER REFERENCES sub_consultant(consultant_id),
    total_amount  REAL NOT NULL,
    amount_paid   REAL NOT NULL DEFAULT 0,
    due_date      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'ISSUED'
                  CHECK (status IN ('ISSUED','PART_PAID','PAID','OVERDUE','CANCELLED')),
    issued_by     INTEGER REFERENCES app_user(user_id),
    issued_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_bill_payer  ON bill(payer_id);
CREATE INDEX idx_bill_status ON bill(status);

CREATE TABLE bill_line (
    bill_line_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id       INTEGER NOT NULL REFERENCES bill(bill_id) ON DELETE CASCADE,
    assessment_id INTEGER NOT NULL REFERENCES assessment(assessment_id),
    line_amount   REAL NOT NULL
);

-- --- 6. MULTI-CHANNEL e-PAYMENTS -------------------------------------------
CREATE TABLE payment_channel (
    channel_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_code TEXT NOT NULL UNIQUE,
    channel_name TEXT NOT NULL,
    provider     TEXT NOT NULL,
    is_active    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE pos_terminal (
    terminal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_serial   TEXT NOT NULL UNIQUE,
    bank_terminal_id  TEXT,
    assigned_agent_id INTEGER REFERENCES field_agent(agent_id),
    ward_id           INTEGER REFERENCES ward_zone(ward_id),
    status            TEXT NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','FAULTY','RETIRED'))
);

CREATE TABLE payment (
    payment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_ref  TEXT NOT NULL UNIQUE,
    bill_id      INTEGER NOT NULL REFERENCES bill(bill_id),
    channel_id   INTEGER NOT NULL REFERENCES payment_channel(channel_id),
    terminal_id  INTEGER REFERENCES pos_terminal(terminal_id),
    agent_id     INTEGER REFERENCES field_agent(agent_id),
    amount       REAL NOT NULL CHECK (amount > 0),
    bank_txn_ref TEXT,
    txn_status   TEXT NOT NULL DEFAULT 'CONFIRMED'
                 CHECK (txn_status IN ('PENDING','CONFIRMED','FAILED','REVERSED')),
    paid_at      TEXT NOT NULL DEFAULT (datetime('now')),
    geo_lat      REAL,
    geo_lng      REAL
);
CREATE INDEX idx_payment_bill    ON payment(bill_id);
CREATE INDEX idx_payment_channel ON payment(channel_id, paid_at);

CREATE TABLE channel_transaction_feed (
    feed_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id         INTEGER NOT NULL REFERENCES payment_channel(channel_id),
    bank_txn_ref       TEXT NOT NULL,
    narration          TEXT,
    amount             REAL NOT NULL,
    value_date         TEXT NOT NULL,
    raw_payload        TEXT,
    match_status       TEXT NOT NULL DEFAULT 'UNMATCHED'
                       CHECK (match_status IN ('UNMATCHED','MATCHED','EXCEPTION')),
    matched_payment_id INTEGER REFERENCES payment(payment_id),
    received_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (channel_id, bank_txn_ref)
);

-- --- 7. e-RECEIPTING --------------------------------------------------------
CREATE TABLE receipt (
    receipt_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_ref    TEXT NOT NULL UNIQUE,
    payment_id     INTEGER NOT NULL UNIQUE REFERENCES payment(payment_id),
    qr_token       TEXT NOT NULL UNIQUE,
    sms_sent       INTEGER NOT NULL DEFAULT 0,
    issued_at      TEXT NOT NULL DEFAULT (datetime('now')),
    verified_count INTEGER NOT NULL DEFAULT 0
);

-- --- 8. RECONCILIATION & COMMISSION ----------------------------------------
CREATE TABLE reconciliation_run (
    recon_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date       TEXT NOT NULL,
    channel_id     INTEGER REFERENCES payment_channel(channel_id),
    total_platform REAL NOT NULL DEFAULT 0,
    total_bank     REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'OPEN'
                   CHECK (status IN ('OPEN','BALANCED','EXCEPTIONS','CLOSED')),
    run_by         INTEGER REFERENCES app_user(user_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE reconciliation_exception (
    exception_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    recon_id        INTEGER NOT NULL REFERENCES reconciliation_run(recon_id),
    feed_id         INTEGER REFERENCES channel_transaction_feed(feed_id),
    payment_id      INTEGER REFERENCES payment(payment_id),
    exception_type  TEXT NOT NULL,
    resolution_note TEXT,
    resolved_by     INTEGER REFERENCES app_user(user_id),
    resolved_at     TEXT
);

CREATE TABLE commission_settlement (
    settlement_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    consultant_id     INTEGER NOT NULL REFERENCES sub_consultant(consultant_id),
    period_start      TEXT NOT NULL,
    period_end        TEXT NOT NULL,
    gross_collections REAL NOT NULL,
    commission_rate   REAL NOT NULL,
    commission_amount REAL NOT NULL,
    status            TEXT NOT NULL DEFAULT 'COMPUTED'
                      CHECK (status IN ('COMPUTED','APPROVED','SETTLED','DISPUTED')),
    approved_by       INTEGER REFERENCES app_user(user_id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (consultant_id, period_start, period_end)
);

-- --- 9. DEBT MANAGEMENT & ENFORCEMENT --------------------------------------
CREATE TABLE debt_case (
    debt_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id           INTEGER NOT NULL REFERENCES bill(bill_id),
    ageing_bucket     TEXT NOT NULL CHECK (ageing_bucket IN ('0_30','31_60','61_90','OVER_90')),
    reminder_count    INTEGER NOT NULL DEFAULT 0,
    last_reminder_at  TEXT,
    enforcement_stage TEXT NOT NULL DEFAULT 'NONE'
                      CHECK (enforcement_stage IN
                        ('NONE','FIRST_NOTICE','FINAL_NOTICE','ENFORCEMENT','LEGAL','CLOSED')),
    assigned_to       INTEGER REFERENCES app_user(user_id),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- --- 10. FIELD OPERATIONS ---------------------------------------------------
CREATE TABLE agent_daily_return (
    return_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id         INTEGER NOT NULL REFERENCES field_agent(agent_id),
    return_date      TEXT NOT NULL,
    visits_count     INTEGER NOT NULL DEFAULT 0,
    bills_issued     INTEGER NOT NULL DEFAULT 0,
    amount_collected REAL NOT NULL DEFAULT 0,
    synced_at        TEXT,
    UNIQUE (agent_id, return_date)
);

CREATE TABLE sync_queue (
    sync_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id          INTEGER NOT NULL REFERENCES field_agent(agent_id),
    entity_type       TEXT NOT NULL,
    payload           TEXT NOT NULL,
    device_created_at TEXT NOT NULL,
    synced_at         TEXT,
    sync_status       TEXT NOT NULL DEFAULT 'PENDING'
                      CHECK (sync_status IN ('PENDING','SYNCED','CONFLICT'))
);

-- --- 11. API CLIENT REGISTRY (e-channel integration) ------------------------
CREATE TABLE api_client (
    client_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code   TEXT NOT NULL UNIQUE,
    client_name   TEXT NOT NULL,
    api_key       TEXT NOT NULL UNIQUE,
    secret_hash   TEXT NOT NULL,
    channel_id    INTEGER REFERENCES payment_channel(channel_id),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- --- REPORTING VIEWS --------------------------------------------------------
CREATE VIEW v_collections_by_channel AS
SELECT pc.channel_code, pc.channel_name, date(p.paid_at) AS collection_date,
       COUNT(*) AS txn_count, SUM(p.amount) AS total_collected
FROM payment p JOIN payment_channel pc ON pc.channel_id = p.channel_id
WHERE p.txn_status = 'CONFIRMED'
GROUP BY pc.channel_code, pc.channel_name, date(p.paid_at);

CREATE VIEW v_global_performance AS
SELECT COALESCE(sc.consultant_name,'Council Direct') AS consultant_name,
       ri.harmonised_code, ri.item_name, w.ward_name,
       SUM(bl.line_amount) AS total_billed,
       SUM(bl.line_amount * (b.amount_paid / CASE WHEN b.total_amount = 0 THEN 1 ELSE b.total_amount END)) AS total_collected
FROM bill b
JOIN bill_line bl   ON bl.bill_id = b.bill_id
JOIN assessment a   ON a.assessment_id = bl.assessment_id
JOIN revenue_item ri ON ri.revenue_item_id = a.revenue_item_id
JOIN payer py       ON py.payer_id = b.payer_id
LEFT JOIN sub_consultant sc ON sc.consultant_id = b.consultant_id
LEFT JOIN ward_zone w ON w.ward_id = py.ward_id
WHERE b.status <> 'CANCELLED'
GROUP BY consultant_name, ri.harmonised_code, ri.item_name, w.ward_name;

CREATE VIEW v_debt_ageing AS
SELECT d.ageing_bucket, COUNT(*) AS cases,
       SUM(b.total_amount - b.amount_paid) AS outstanding_amount
FROM debt_case d JOIN bill b ON b.bill_id = d.bill_id
WHERE b.status IN ('ISSUED','PART_PAID','OVERDUE')
GROUP BY d.ageing_bucket;
