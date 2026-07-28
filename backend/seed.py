"""
RevAc — Database initialisation and demonstration seed
======================================================
Creates revac.db from schema.sql and loads AMAC reference data.

Revenue items, rates, wards, sub-consultants and all transactions below are
ILLUSTRATIVE DEMONSTRATION DATA. They are placeholders pending the
Harmonisation Workstream (Component 3), the enumeration exercise, and the
Council's approved rates schedule.

Run:  python seed.py
"""

import hashlib
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "revac.db")
SCHEMA = os.path.join(BASE, "schema.sql")

random.seed(2026)


def h(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


if os.path.exists(DB):
    os.remove(DB)

con = sqlite3.connect(DB)
con.executescript(open(SCHEMA).read())
cur = con.cursor()

# --- Council & wards --------------------------------------------------------
cur.execute("INSERT INTO council (council_code, council_name) VALUES (?,?)",
            ("AMAC", "Abuja Municipal Area Council"))

WARDS = [
    ("AMAC-01", "City Centre"), ("AMAC-02", "Garki"), ("AMAC-03", "Wuse"),
    ("AMAC-04", "Gwarinpa"), ("AMAC-05", "Karu"), ("AMAC-06", "Nyanya"),
    ("AMAC-07", "Kabusa"), ("AMAC-08", "Gui"), ("AMAC-09", "Orozo"),
    ("AMAC-10", "Jiwa"), ("AMAC-11", "Gwagwa"), ("AMAC-12", "Karshi"),
]
for code, name in WARDS:
    cur.execute("INSERT INTO ward_zone (council_id, ward_code, ward_name) VALUES (1,?,?)",
                (code, name))

# --- Roles ------------------------------------------------------------------
ROLES = [
    ("COUNCIL_ADMIN", "Council Revenue Administrator", "COUNCIL_ADMIN"),
    ("HEAD_REVENUE", "Head of Revenue", "COUNCIL_ADMIN"),
    ("CONSULTANT", "Sub-Consultant Manager", "CONSULTANT"),
    ("AGENT", "Field Collection Agent", "AGENT"),
    ("STAKEHOLDER", "Council Stakeholder (Global View)", "GLOBAL_VIEW"),
]
for c, n, lvl in ROLES:
    cur.execute("INSERT INTO app_role (role_code, role_name, access_level) VALUES (?,?,?)",
                (c, n, lvl))

# --- Sub-consultants (illustrative) ----------------------------------------
CONSULTANTS = [
    ("SC-001", "Northgate Revenue Services Ltd", "AMAC/RC/2026/011", 30.0),
    ("SC-002", "Capital Assessment Partners Ltd", "AMAC/RC/2026/017", 32.5),
    ("SC-003", "Trident Fiscal Consulting Ltd", "AMAC/RC/2026/024", 28.0),
    ("SC-004", "Meridian Collections Ltd", "AMAC/RC/2026/031", 35.0),
]
for code, name, ref, rate in CONSULTANTS:
    cur.execute("""INSERT INTO sub_consultant (council_id, consultant_code, consultant_name,
                     contract_ref, commission_rate, status, onboarded_at)
                   VALUES (1,?,?,?,?, 'ACTIVE', datetime('now','-60 days'))""",
                (code, name, ref, rate))

# --- Users ------------------------------------------------------------------
USERS = [
    ("admin",      "Council Revenue Administrator", 1, None, "COUNCIL_ADMIN"),
    ("headrevenue", "Head of Revenue, AMAC",        2, None, "HEAD_REVENUE"),
    ("consultant1", "Manager, Northgate Revenue Services", 3, 1, "CONSULTANT"),
    ("consultant2", "Manager, Capital Assessment Partners", 3, 2, "CONSULTANT"),
    ("stakeholder", "Council Stakeholder",          5, None, "STAKEHOLDER"),
]
for uname, fname, role_id, cons_id, _ in USERS:
    cur.execute("""INSERT INTO app_user (council_id, consultant_id, role_id, username,
                     full_name, phone, email, password_hash)
                   VALUES (1,?,?,?,?,?,?,?)""",
                (cons_id, role_id, uname, fname, "0803000" + str(random.randint(1000, 9999)),
                 f"{uname}@amac.example.ng", h("revac2026")))

# --- Field agents -----------------------------------------------------------
AGENT_NAMES = [
    "Musa Ibrahim", "Grace Okonkwo", "Sadiq Bello", "Ngozi Eze", "Yusuf Danjuma",
    "Blessing Adeyemi", "Emeka Nwosu", "Hauwa Aliyu", "Tunde Bakare", "Amina Sule",
    "Chidi Okeke", "Fatima Garba",
]
agent_ids = []
for i, name in enumerate(AGENT_NAMES):
    cur.execute("""INSERT INTO app_user (council_id, consultant_id, role_id, username,
                     full_name, phone, email, password_hash)
                   VALUES (1,?,4,?,?,?,?,?)""",
                ((i % 4) + 1, f"agent{i+1}", name,
                 "0806000" + str(1000 + i), f"agent{i+1}@amac.example.ng", h("revac2026")))
    uid = cur.lastrowid
    cur.execute("""INSERT INTO field_agent (user_id, consultant_id, agent_code,
                     assigned_ward_id, device_imei)
                   VALUES (?,?,?,?,?)""",
                (uid, (i % 4) + 1, f"AG-{i+1:03d}", (i % 12) + 1,
                 f"35{random.randint(10**12, 10**13-1)}"))
    agent_ids.append(cur.lastrowid)

# --- Payment channels -------------------------------------------------------
CHANNELS = [
    ("POS", "POS Terminal", "Collecting Bank"),
    ("OTC", "Over-the-Counter (Branch Teller)", "Collecting Bank"),
    ("IB_MB", "Internet / Mobile Banking Transfer", "Collecting Bank"),
    ("USSD", "USSD Payment", "Collecting Bank"),
    ("FIRSTMONIE", "Agent Banking Network", "Collecting Bank"),
]
for code, name, prov in CHANNELS:
    cur.execute("INSERT INTO payment_channel (channel_code, channel_name, provider) VALUES (?,?,?)",
                (code, name, prov))

# --- POS terminal fleet -----------------------------------------------------
for i in range(1, 21):
    cur.execute("""INSERT INTO pos_terminal (terminal_serial, bank_terminal_id,
                     assigned_agent_id, ward_id, status)
                   VALUES (?,?,?,?,?)""",
                (f"POS-AMAC-{i:04d}", f"2{random.randint(10**6, 10**7-1)}",
                 agent_ids[(i-1) % len(agent_ids)], ((i-1) % 12) + 1,
                 "ACTIVE" if i <= 18 else "FAULTY"))

# --- API clients ------------------------------------------------------------
for i, (code, _, _) in enumerate(CHANNELS, start=1):
    cur.execute("""INSERT INTO api_client (client_code, client_name, api_key, secret_hash,
                     channel_id) VALUES (?,?,?,?,?)""",
                (f"BANK-{code}", f"Collecting Bank — {code} integration",
                 f"rk_live_{uuid.uuid4().hex[:24]}", h(f"demo-{code}-secret"), i))

# --- Harmonised chart of revenue (illustrative) ----------------------------
CATEGORIES = [
    ("RAT", "Rates"), ("LIC", "Licences and Permits"), ("FEE", "Fees and Charges"),
    ("LEV", "Levies"), ("EAR", "Earnings and Sales"),
]
for code, name in CATEGORIES:
    cur.execute("INSERT INTO revenue_category (council_id, category_code, category_name) VALUES (1,?,?)",
                (code, name))

ITEMS = [
    # (category_idx, code, name, unit, rate, in_scope)
    (1, "AMAC-RAT-001", "Tenement Rate — Residential", "per annum", 15000, 0),
    (1, "AMAC-RAT-002", "Tenement Rate — Commercial", "per annum", 45000, 0),
    (2, "AMAC-LIC-001", "Business Premises Registration (New)", "per annum", 25000, 1),
    (2, "AMAC-LIC-002", "Business Premises Renewal", "per annum", 15000, 1),
    (2, "AMAC-LIC-003", "Liquor Licence", "per annum", 50000, 1),
    (2, "AMAC-LIC-004", "Signage and Advertisement Permit", "per unit p.a.", 35000, 1),
    (2, "AMAC-LIC-005", "Building Plan Approval Fee", "per application", 120000, 1),
    (3, "AMAC-FEE-001", "Market Stall / Shop Fee", "per annum", 18000, 1),
    (3, "AMAC-FEE-002", "Abattoir and Slaughter Fee", "per head", 1500, 1),
    (3, "AMAC-FEE-003", "Birth and Death Registration Fee", "per certificate", 2000, 1),
    (3, "AMAC-FEE-004", "Marriage Registration Fee", "per registration", 20000, 1),
    (3, "AMAC-FEE-005", "Motor Park Levy", "per vehicle per day", 500, 0),
    (3, "AMAC-FEE-006", "Commercial Vehicle and Parking Fee", "per vehicle p.a.", 12000, 0),
    (4, "AMAC-LEV-001", "Environmental and Sanitation Levy", "per annum", 24000, 0),
    (4, "AMAC-LEV-002", "Public Convenience Levy", "per facility p.a.", 30000, 1),
    (4, "AMAC-LEV-003", "Radio and Television Licence", "per annum", 6000, 1),
    (5, "AMAC-EAR-001", "Sale of Council Bye-Laws and Forms", "per copy", 5000, 1),
    (5, "AMAC-EAR-002", "Hire of Council Facilities", "per event", 75000, 1),
]
for cat, code, name, unit, rate, scope in ITEMS:
    cur.execute("""INSERT INTO revenue_item (category_id, harmonised_code, item_name,
                     legal_basis, unit_of_charge, in_initial_scope)
                   VALUES (?,?,?,?,?,?)""",
                (cat, code, name, "Council Bye-Law (illustrative)", unit, scope))
    item_id = cur.lastrowid
    cur.execute("""INSERT INTO rate_schedule (revenue_item_id, rate_amount, rate_basis,
                     approved_by_ref, effective_from)
                   VALUES (?,?, 'FLAT', 'Illustrative — pending Council approval', ?)""",
                (item_id, rate, "2026-01-01"))
    # Portfolio allocation across sub-consultants
    cur.execute("""INSERT INTO consultant_portfolio (consultant_id, revenue_item_id,
                     effective_from) VALUES (?,?, '2026-01-01')""",
                ((item_id % 4) + 1, item_id))

# --- Payers -----------------------------------------------------------------
BIZ = ["Ventures", "Enterprises", "Nigeria Ltd", "Global Services", "Stores",
       "Trading Co", "Motors", "Pharmacy", "Supermarket", "Hotel & Suites",
       "Restaurant", "Filling Station", "Bakery", "Boutique", "Hardware"]
PRE = ["Zenith", "Alpha", "Crown", "Unity", "Royal", "Golden", "Nasara", "Emerald",
       "Peak", "Sunrise", "Silverline", "Chidera", "Al-Amin", "Greenfield", "Excel",
       "Havilah", "Blue Ridge", "Danfodio", "Obudu", "Kaduna"]

payer_ids = []
for i in range(1, 181):
    is_biz = i % 5 != 0
    name = (f"{random.choice(PRE)} {random.choice(BIZ)}" if is_biz
            else f"{random.choice(AGENT_NAMES).split()[0]} {random.choice(['Abubakar','Okafor','Adamu','Nwachukwu','Lawal'])}")
    cur.execute("""INSERT INTO payer (council_id, payer_ref, payer_type, full_name, phone,
                     email, tin, ward_id, address, geo_lat, geo_lng, kyc_status, created_by)
                   VALUES (1,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (f"AMAC-2026-{i:06d}", "BUSINESS" if is_biz else "INDIVIDUAL", name,
                 f"080{random.randint(10000000, 99999999)}",
                 f"contact{i}@example.ng", f"N-{random.randint(10**7, 10**8-1)}",
                 ((i - 1) % 12) + 1, f"{random.randint(1,250)} {random.choice(WARDS)[1]} Road, Abuja",
                 round(8.98 + random.random() * 0.35, 6),
                 round(7.30 + random.random() * 0.35, 6),
                 random.choice(["VERIFIED", "VERIFIED", "PENDING"])))
    pid = cur.lastrowid
    payer_ids.append(pid)
    if is_biz:
        cur.execute("""INSERT INTO enumerated_asset (payer_id, asset_ref, asset_type,
                         description, ward_id, geo_lat, geo_lng, enumerated_by)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (pid, f"AST-{i:06d}", random.choice(["PREMISES", "SHOP", "KIOSK", "SIGNAGE"]),
                     "Enumerated during field exercise", ((i - 1) % 12) + 1,
                     round(8.98 + random.random() * 0.35, 6),
                     round(7.30 + random.random() * 0.35, 6),
                     random.choice(agent_ids)))

# --- Bills, assessments, payments, receipts --------------------------------
in_scope = [r[0] for r in cur.execute(
    "SELECT revenue_item_id FROM revenue_item WHERE in_initial_scope = 1").fetchall()]

bill_no = 0
payment_no = 0
today = datetime.now()

for pid in payer_ids:
    for _ in range(random.randint(1, 3)):
        bill_no += 1
        issued = today - timedelta(days=random.randint(0, 120))
        due = issued + timedelta(days=30)
        consultant = random.randint(1, 4)
        bill_ref = f"AMAC/2026/{bill_no:06d}"
        cur.execute("""INSERT INTO bill (bill_ref, payer_id, consultant_id, total_amount,
                         due_date, status, issued_by, issued_at)
                       VALUES (?,?,?,0,?, 'ISSUED', 1, ?)""",
                    (bill_ref, pid, consultant, due.strftime("%Y-%m-%d"),
                     issued.strftime("%Y-%m-%d %H:%M:%S")))
        bid = cur.lastrowid
        total = 0.0
        for item_id in random.sample(in_scope, random.randint(1, 3)):
            rate = cur.execute(
                "SELECT rate_id, rate_amount FROM rate_schedule WHERE revenue_item_id=?",
                (item_id,)).fetchone()
            qty = random.choice([1, 1, 1, 2, 3])
            amt = rate[1] * qty
            cur.execute("""INSERT INTO assessment (payer_id, revenue_item_id, rate_id,
                             consultant_id, period_year, quantity, assessed_amount,
                             status, created_by, created_at)
                           VALUES (?,?,?,?,2026,?,?, 'BILLED',1,?)""",
                        (pid, item_id, rate[0], consultant, qty, amt,
                         issued.strftime("%Y-%m-%d %H:%M:%S")))
            cur.execute("INSERT INTO bill_line (bill_id, assessment_id, line_amount) VALUES (?,?,?)",
                        (bid, cur.lastrowid, amt))
            total += amt
        cur.execute("UPDATE bill SET total_amount=? WHERE bill_id=?", (total, bid))

        # ~68% of bills attract payment, weighted across the five e-channels
        if random.random() < 0.68:
            full = random.random() < 0.75
            amount = round(total if full else total * random.choice([0.25, 0.4, 0.5, 0.6]), 2)
            channel_id = random.choices([1, 2, 3, 4, 5], weights=[38, 12, 22, 16, 12])[0]
            paid_at = issued + timedelta(days=random.randint(0, 25))
            if paid_at > today:
                paid_at = today
            payment_no += 1
            agent = random.choice(agent_ids) if channel_id == 1 else None
            terminal = random.randint(1, 20) if channel_id == 1 else None
            cur.execute("""INSERT INTO payment (payment_ref, bill_id, channel_id, terminal_id,
                             agent_id, amount, bank_txn_ref, txn_status, paid_at)
                           VALUES (?,?,?,?,?,?,?, 'CONFIRMED', ?)""",
                        (f"PMT-{uuid.uuid4().hex[:12].upper()}", bid, channel_id, terminal,
                         agent, amount, f"BNK{random.randint(10**9, 10**10-1)}",
                         paid_at.strftime("%Y-%m-%d %H:%M:%S")))
            pay_id = cur.lastrowid
            cur.execute("UPDATE bill SET amount_paid=?, status=? WHERE bill_id=?",
                        (amount, "PAID" if full else "PART_PAID", bid))
            cur.execute("""INSERT INTO receipt (receipt_ref, payment_id, qr_token, sms_sent,
                             issued_at) VALUES (?,?,?,1,?)""",
                        (f"RCP-{paid_at:%Y%m%d}-{pay_id:06d}", pay_id, str(uuid.uuid4()),
                         paid_at.strftime("%Y-%m-%d %H:%M:%S")))
            # Mirror into the bank feed so reconciliation has something to match
            cur.execute("""INSERT INTO channel_transaction_feed (channel_id, bank_txn_ref,
                             narration, amount, value_date, match_status, matched_payment_id,
                             received_at)
                           VALUES (?,?,?,?,?, 'MATCHED', ?, ?)""",
                        (channel_id, f"BNK{random.randint(10**9, 10**10-1)}",
                         f"Collection {bill_ref}", amount, paid_at.strftime("%Y-%m-%d"),
                         pay_id, paid_at.strftime("%Y-%m-%d %H:%M:%S")))

# A few deliberately unmatched bank credits so the exception queue is real
for i in range(6):
    d = (today - timedelta(days=random.randint(0, 10))).strftime("%Y-%m-%d")
    cur.execute("""INSERT INTO channel_transaction_feed (channel_id, bank_txn_ref, narration,
                     amount, value_date, match_status)
                   VALUES (?,?,?,?,?, 'EXCEPTION')""",
                (random.randint(1, 5), f"UNMATCHED{random.randint(10**8, 10**9-1)}",
                 "Credit received — bill reference not quoted",
                 round(random.choice([15000, 25000, 35000, 50000]), 2), d))

# --- Debt cases on overdue bills -------------------------------------------
for row in cur.execute("""SELECT bill_id, due_date FROM bill
                          WHERE status IN ('ISSUED','PART_PAID')
                            AND due_date < date('now')""").fetchall():
    days = (today - datetime.strptime(row[1], "%Y-%m-%d")).days
    bucket = "0_30" if days <= 30 else "31_60" if days <= 60 else \
             "61_90" if days <= 90 else "OVER_90"
    stage = random.choice(["FIRST_NOTICE", "FIRST_NOTICE", "FINAL_NOTICE", "ENFORCEMENT"])
    cur.execute("""INSERT INTO debt_case (bill_id, ageing_bucket, reminder_count,
                     enforcement_stage) VALUES (?,?,?,?)""",
                (row[0], bucket, random.randint(0, 3), stage))
    cur.execute("UPDATE bill SET status='OVERDUE' WHERE bill_id=? AND status='ISSUED'", (row[0],))

# --- Agent daily returns ----------------------------------------------------
for aid in agent_ids:
    for back in range(0, 14):
        d = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        row = cur.execute("""SELECT COUNT(*) , COALESCE(SUM(amount),0) FROM payment
                             WHERE agent_id=? AND date(paid_at)=?""", (aid, d)).fetchone()
        if row[0]:
            cur.execute("""INSERT OR IGNORE INTO agent_daily_return (agent_id, return_date,
                             visits_count, bills_issued, amount_collected, synced_at)
                           VALUES (?,?,?,?,?,datetime('now'))""",
                        (aid, d, row[0] + random.randint(2, 9), row[0], row[1]))

# --- Commission settlements for the current month --------------------------
start = today.replace(day=1).strftime("%Y-%m-%d")
end = today.strftime("%Y-%m-%d")
for cid, rate in cur.execute("SELECT consultant_id, commission_rate FROM sub_consultant").fetchall():
    gross = cur.execute("""SELECT COALESCE(SUM(p.amount),0) FROM payment p
                           JOIN bill b ON b.bill_id=p.bill_id
                           WHERE b.consultant_id=? AND date(p.paid_at) BETWEEN ? AND ?""",
                        (cid, start, end)).fetchone()[0]
    cur.execute("""INSERT INTO commission_settlement (consultant_id, period_start, period_end,
                     gross_collections, commission_rate, commission_amount, status)
                   VALUES (?,?,?,?,?,?, 'COMPUTED')""",
                (cid, start, end, gross, rate, round(gross * rate / 100, 2)))

# --- Reconciliation runs for the last 7 days -------------------------------
for back in range(0, 7):
    d = (today - timedelta(days=back)).strftime("%Y-%m-%d")
    for ch in range(1, 6):
        plat = cur.execute("""SELECT COALESCE(SUM(amount),0) FROM payment
                              WHERE channel_id=? AND date(paid_at)=?""", (ch, d)).fetchone()[0]
        bank = cur.execute("""SELECT COALESCE(SUM(amount),0) FROM channel_transaction_feed
                              WHERE channel_id=? AND value_date=?""", (ch, d)).fetchone()[0]
        if plat or bank:
            cur.execute("""INSERT INTO reconciliation_run (run_date, channel_id, total_platform,
                             total_bank, status, run_by) VALUES (?,?,?,?,?,1)""",
                        (d, ch, plat, bank,
                         "BALANCED" if abs(plat - bank) < 0.01 else "EXCEPTIONS"))

# --- Audit trail ------------------------------------------------------------
for act, ent in [("LOGIN", "app_user"), ("BILL_ISSUED", "bill"), ("PAYMENT_POSTED", "payment"),
                 ("RECONCILIATION_RUN", "reconciliation_run"), ("PAYER_REGISTERED", "payer"),
                 ("SETTLEMENT_COMPUTED", "commission_settlement"),
                 ("CONSULTANT_STATUS_CHANGED", "sub_consultant")]:
    for _ in range(random.randint(3, 8)):
        cur.execute("""INSERT INTO audit_log (user_id, action, entity_type, entity_id,
                         ip_address, occurred_at) VALUES (?,?,?,?,?,?)""",
                    (random.randint(1, 5), act, ent, random.randint(1, 100), "10.0.0.14",
                     (today - timedelta(days=random.randint(0, 20),
                                        hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")))

con.commit()

stats = {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
         ["payer", "enumerated_asset", "assessment", "bill", "payment", "receipt",
          "debt_case", "channel_transaction_feed", "field_agent", "pos_terminal",
          "revenue_item", "sub_consultant", "audit_log"]}
collected = cur.execute("SELECT COALESCE(SUM(amount),0) FROM payment WHERE txn_status='CONFIRMED'").fetchone()[0]
billed = cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM bill").fetchone()[0]
con.close()

print("RevAc database created:", DB)
for k, v in stats.items():
    print(f"  {k:28} {v:>7,}")
print(f"  {'total billed':28} NGN {billed:>15,.2f}")
print(f"  {'total collected':28} NGN {collected:>15,.2f}")
print("\nSign-in accounts (password: revac2026)")
print("  admin        Council Revenue Administrator  — full admin")
print("  consultant1  Northgate Revenue Services     — own portfolio only")
print("  stakeholder  Council Stakeholder            — global performance view")
print("  agent1..12   Field Collection Agents        — mobile app")
