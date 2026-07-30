"""
RevAc Application Suite — Backend API
=====================================
Alliance Consulting & Digital Solutions Ltd (ACDSL)
Deployment: Kuje Area Council (KAC), FCT

Serves:
  * REST API for the web portal and the field-agent mobile app
  * Multi-channel e-payment webhook + settlement endpoints
  * Reconciliation and commission settlement engines
  * Static hosting of the web portal and mobile PWA

Run:  python app.py       (http://127.0.0.1:8000)
"""

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory

from echannels import ChannelError, channel_catalogue, get_adapter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(BASE_DIR, "revac.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# In production these live in a secrets manager / HSM, never in source.
CHANNEL_SECRETS = {
    "POS": os.environ.get("REVAC_POS_SECRET", "demo-pos-secret"),
    "OTC": os.environ.get("REVAC_OTC_SECRET", "demo-otc-secret"),
    "IB_MB": os.environ.get("REVAC_IBMB_SECRET", "demo-ibmb-secret"),
    "USSD": os.environ.get("REVAC_USSD_SECRET", "demo-ussd-secret"),
    "FIRSTMONIE": os.environ.get("REVAC_AGENT_SECRET", "demo-agent-secret"),
}

app = Flask(__name__, static_folder=None)

# Live session tokens: token -> user context
SESSIONS = {}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def audit(action, entity_type, entity_id=None, detail=None):
    user = getattr(g, "current_user", None)
    execute(
        """INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail, ip_address)
           VALUES (?,?,?,?,?,?)""",
        (
            user["user_id"] if user else None,
            action, entity_type, entity_id,
            json.dumps(detail) if detail else None,
            request.remote_addr,
        ),
    )


# ---------------------------------------------------------------------------
# Auth & access control
# ---------------------------------------------------------------------------

def auth_required(*allowed_levels):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = (request.headers.get("Authorization", "")
                     .replace("Bearer ", "").strip())
            session = SESSIONS.get(token)
            if not session:
                return jsonify({"error": "Authentication required"}), 401
            if allowed_levels and session["access_level"] not in allowed_levels:
                return jsonify({"error": "Your role does not have access to this action"}), 403
            g.current_user = session
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def portfolio_filter():
    """Per-portfolio data segregation: a sub-consultant sees only its own rows."""
    user = g.current_user
    if user["access_level"] == "CONSULTANT" and user.get("consultant_id"):
        return " AND b.consultant_id = ? ", [user["consultant_id"]]
    return " ", []


@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    row = query(
        """SELECT u.*, r.access_level, r.role_name, c.consultant_name
           FROM app_user u
           JOIN app_role r ON r.role_id = u.role_id
           LEFT JOIN sub_consultant c ON c.consultant_id = u.consultant_id
           WHERE u.username = ? AND u.is_active = 1""",
        (data.get("username", "").strip(),), one=True,
    )
    if not row or row["password_hash"] != hash_password(data.get("password", "")):
        return jsonify({"error": "Username or password is incorrect"}), 401

    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {
        "user_id": row["user_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "access_level": row["access_level"],
        "role_name": row["role_name"],
        "consultant_id": row["consultant_id"],
        "consultant_name": row["consultant_name"],
    }
    execute("UPDATE app_user SET last_login_at = datetime('now') WHERE user_id = ?",
            (row["user_id"],))
    g.current_user = SESSIONS[token]
    audit("LOGIN", "app_user", row["user_id"])
    return jsonify({"token": token, "user": SESSIONS[token]})


@app.post("/api/auth/logout")
@auth_required()
def logout():
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    SESSIONS.pop(token, None)
    return jsonify({"status": "signed out"})


@app.get("/api/auth/me")
@auth_required()
def me():
    return jsonify(g.current_user)


# ---------------------------------------------------------------------------
# Dashboard & analytics
# ---------------------------------------------------------------------------

@app.get("/api/dashboard/summary")
@auth_required()
def dashboard_summary():
    clause, params = portfolio_filter()
    totals = query(
        f"""SELECT COUNT(DISTINCT b.bill_id) AS bills,
                   COALESCE(SUM(b.total_amount),0) AS billed,
                   COALESCE(SUM(b.amount_paid),0)  AS collected
            FROM bill b WHERE b.status <> 'CANCELLED' {clause}""",
        params, one=True,
    )
    payers = query("SELECT COUNT(*) AS n FROM payer WHERE is_duplicate_of IS NULL", one=True)
    assessments = query("SELECT COUNT(*) AS n FROM assessment", one=True)
    agents = query("SELECT COUNT(*) AS n FROM field_agent WHERE status='ACTIVE'", one=True)

    by_channel = query(
        """SELECT pc.channel_code, pc.channel_name,
                  COUNT(p.payment_id) AS txns, COALESCE(SUM(p.amount),0) AS amount
           FROM payment_channel pc
           LEFT JOIN payment p ON p.channel_id = pc.channel_id AND p.txn_status='CONFIRMED'
           GROUP BY pc.channel_code, pc.channel_name ORDER BY amount DESC"""
    )
    by_item = query(
        """SELECT ri.harmonised_code, ri.item_name,
                  COALESCE(SUM(bl.line_amount),0) AS billed
           FROM revenue_item ri
           LEFT JOIN assessment a ON a.revenue_item_id = ri.revenue_item_id
           LEFT JOIN bill_line bl ON bl.assessment_id = a.assessment_id
           GROUP BY ri.harmonised_code, ri.item_name
           ORDER BY billed DESC LIMIT 8"""
    )
    trend = query(
        """SELECT date(paid_at) AS d, SUM(amount) AS amount
           FROM payment WHERE txn_status='CONFIRMED'
           GROUP BY date(paid_at) ORDER BY d DESC LIMIT 14"""
    )
    return jsonify({
        "payers": payers["n"],
        "assessments": assessments["n"],
        "bills": totals["bills"],
        "billed": totals["billed"],
        "collected": totals["collected"],
        "outstanding": (totals["billed"] or 0) - (totals["collected"] or 0),
        "active_agents": agents["n"],
        "by_channel": by_channel,
        "by_item": by_item,
        "trend": list(reversed(trend)),
    })


@app.get("/api/dashboard/global")
@auth_required("COUNCIL_ADMIN", "GLOBAL_VIEW")
def global_view():
    consultants = query(
        """SELECT sc.consultant_id, sc.consultant_name, sc.commission_rate, sc.status,
                  COUNT(DISTINCT b.bill_id) AS bills,
                  COALESCE(SUM(b.total_amount),0) AS billed,
                  COALESCE(SUM(b.amount_paid),0)  AS collected
           FROM sub_consultant sc
           LEFT JOIN bill b ON b.consultant_id = sc.consultant_id AND b.status <> 'CANCELLED'
           GROUP BY sc.consultant_id ORDER BY collected DESC"""
    )
    for c in consultants:
        c["collection_rate"] = round(
            (c["collected"] / c["billed"] * 100) if c["billed"] else 0, 1)
        c["commission_accrued"] = round(c["collected"] * c["commission_rate"] / 100, 2)
    wards = query(
        """SELECT w.ward_name, COALESCE(SUM(b.amount_paid),0) AS collected,
                  COUNT(DISTINCT py.payer_id) AS payers
           FROM ward_zone w
           LEFT JOIN payer py ON py.ward_id = w.ward_id
           LEFT JOIN bill b   ON b.payer_id = py.payer_id AND b.status <> 'CANCELLED'
           GROUP BY w.ward_name ORDER BY collected DESC"""
    )
    return jsonify({"consultants": consultants, "wards": wards})


# ---------------------------------------------------------------------------
# Module: Enumeration & Payer Registry
# ---------------------------------------------------------------------------

@app.get("/api/payers")
@auth_required()
def list_payers():
    search = request.args.get("q", "").strip()
    sql = """SELECT p.*, w.ward_name FROM payer p
             LEFT JOIN ward_zone w ON w.ward_id = p.ward_id
             WHERE p.is_duplicate_of IS NULL"""
    params = []
    if search:
        sql += " AND (p.full_name LIKE ? OR p.payer_ref LIKE ? OR p.phone LIKE ?)"
        params += [f"%{search}%"] * 3
    sql += " ORDER BY p.created_at DESC LIMIT 200"
    return jsonify(query(sql, params))


@app.post("/api/payers")
@auth_required("COUNCIL_ADMIN", "CONSULTANT", "AGENT")
def create_payer():
    """Enumeration — available to admin, consultant and agent alike. Individuals
    and businesses get distinctly-formatted payer IDs (IND- vs C-), and any
    revenue items selected at enumeration are recorded as DRAFT assessments
    ready to be rolled into a harmonised bill later."""
    d = request.get_json(force=True)
    if not d.get("full_name"):
        return jsonify({"error": "Enter the payer's name"}), 400
    payer_type = d.get("payer_type", "BUSINESS")
    if payer_type not in ("INDIVIDUAL", "BUSINESS", "GOVERNMENT", "NGO"):
        return jsonify({"error": "Choose a valid payer type"}), 400

    # Deduplication check on phone or TIN before creating a new record
    dup = None
    if d.get("phone"):
        dup = query("SELECT payer_id, full_name, payer_ref FROM payer WHERE phone = ?",
                    (d["phone"],), one=True)
    if dup and not d.get("force"):
        return jsonify({
            "error": "A payer with this phone number already exists",
            "duplicate_of": dup,
        }), 409

    nin = d.get("nin_bvn")
    # Two-phase ref: insert with a throwaway-unique placeholder, then derive the
    # real payer_ref from the auto-increment payer_id so it can never collide.
    payer_id = execute(
        """INSERT INTO payer (council_id, payer_ref, payer_type, full_name, phone, email,
                              tin, nin_bvn_hash, ward_id, address, geo_lat, geo_lng,
                              kyc_status, created_by)
           VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"TMP-{uuid.uuid4().hex}", payer_type, d["full_name"], d.get("phone"),
         d.get("email"), d.get("tin"),
         hashlib.sha256(nin.encode()).hexdigest() if nin else None,
         d.get("ward_id"), d.get("address"), d.get("geo_lat"), d.get("geo_lng"),
         "VERIFIED" if nin else "PENDING", g.current_user["user_id"]),
    )
    prefix = "IND" if payer_type == "INDIVIDUAL" else "C"
    payer_ref = f"{prefix}-{9000000 + payer_id}"
    execute("UPDATE payer SET payer_ref = ? WHERE payer_id = ?", (payer_ref, payer_id))
    audit("PAYER_REGISTERED", "payer", payer_id, {"payer_ref": payer_ref})

    # Revenue items selected at enumeration become DRAFT assessments, priced
    # at the current rate, ready to be billed later (individually or as one
    # harmonised bill covering everything the payer owes).
    created_assessments = []
    for item_id in d.get("revenue_item_ids", []) or []:
        rate = query(
            """SELECT rate_id, rate_amount FROM rate_schedule WHERE revenue_item_id = ?
               AND (effective_to IS NULL OR effective_to >= date('now'))
               ORDER BY effective_from DESC LIMIT 1""", (item_id,), one=True)
        if not rate:
            continue
        assessment_id = execute(
            """INSERT INTO assessment (payer_id, revenue_item_id, rate_id, period_year,
                                       quantity, assessed_amount, status, created_by)
               VALUES (?,?,?,?,1,?, 'DRAFT', ?)""",
            (payer_id, item_id, rate["rate_id"], datetime.now().year, rate["rate_amount"],
             g.current_user["user_id"]),
        )
        created_assessments.append(assessment_id)

    payer = query("SELECT * FROM payer WHERE payer_id = ?", (payer_id,), one=True)
    payer["draft_assessments_created"] = len(created_assessments)
    return jsonify(payer), 201


@app.get("/api/payers/<int:payer_id>/draft-assessments")
@auth_required()
def payer_draft_assessments(payer_id):
    """Revenue items enumerated for a payer but not yet rolled into a bill."""
    return jsonify(query(
        """SELECT a.assessment_id, a.revenue_item_id, a.quantity, a.assessed_amount,
                  ri.item_name, ri.harmonised_code
           FROM assessment a
           JOIN revenue_item ri ON ri.revenue_item_id = a.revenue_item_id
           WHERE a.payer_id = ? AND a.status = 'DRAFT'
           ORDER BY a.created_at""", (payer_id,)))


@app.get("/api/payers/<int:payer_id>")
@auth_required()
def payer_detail(payer_id):
    payer = query("""SELECT p.*, w.ward_name FROM payer p
                     LEFT JOIN ward_zone w ON w.ward_id = p.ward_id
                     WHERE p.payer_id = ?""", (payer_id,), one=True)
    if not payer:
        return jsonify({"error": "Payer not found"}), 404
    payer["assets"] = query("SELECT * FROM enumerated_asset WHERE payer_id = ?", (payer_id,))
    payer["bills"] = query(
        """SELECT b.*, (b.total_amount - b.amount_paid) AS balance
           FROM bill b WHERE b.payer_id = ? ORDER BY b.issued_at DESC""", (payer_id,))
    return jsonify(payer)


@app.post("/api/assets")
@auth_required("COUNCIL_ADMIN", "CONSULTANT", "AGENT")
def create_asset():
    d = request.get_json(force=True)
    seq = query("SELECT COUNT(*) AS n FROM enumerated_asset", one=True)["n"] + 1
    asset_ref = f"AST-{seq:06d}"
    agent = query("SELECT agent_id FROM field_agent WHERE user_id = ?",
                  (g.current_user["user_id"],), one=True)
    asset_id = execute(
        """INSERT INTO enumerated_asset (payer_id, asset_ref, asset_type, description,
                                         ward_id, geo_lat, geo_lng, enumerated_by)
           VALUES (?,?,?,?,?,?,?,?)""",
        (d["payer_id"], asset_ref, d.get("asset_type", "PREMISES"), d.get("description"),
         d.get("ward_id"), d.get("geo_lat"), d.get("geo_lng"),
         agent["agent_id"] if agent else None),
    )
    audit("ASSET_ENUMERATED", "enumerated_asset", asset_id)
    return jsonify({"asset_id": asset_id, "asset_ref": asset_ref}), 201


# ---------------------------------------------------------------------------
# Module: Harmonised Chart of Revenue
# ---------------------------------------------------------------------------

@app.get("/api/revenue-items")
@auth_required()
def revenue_items():
    return jsonify(query(
        """SELECT ri.*, rc.category_name,
                  (SELECT rate_amount FROM rate_schedule rs
                   WHERE rs.revenue_item_id = ri.revenue_item_id
                     AND (rs.effective_to IS NULL OR rs.effective_to >= date('now'))
                   ORDER BY rs.effective_from DESC LIMIT 1) AS current_rate,
                  (SELECT rate_id FROM rate_schedule rs
                   WHERE rs.revenue_item_id = ri.revenue_item_id
                     AND (rs.effective_to IS NULL OR rs.effective_to >= date('now'))
                   ORDER BY rs.effective_from DESC LIMIT 1) AS rate_id
           FROM revenue_item ri
           JOIN revenue_category rc ON rc.category_id = ri.category_id
           ORDER BY ri.harmonised_code"""))


@app.post("/api/revenue-items/<int:item_id>/rate")
@auth_required("COUNCIL_ADMIN")
def change_revenue_item_rate(item_id):
    """Only the Council Admin may change what a revenue item costs. Keeps
    rate history intact: closes the current rate row and opens a new one."""
    d = request.get_json(force=True)
    try:
        amount = float(d["rate_amount"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Enter a valid rate amount"}), 400
    if not query("SELECT 1 FROM revenue_item WHERE revenue_item_id = ?", (item_id,), one=True):
        return jsonify({"error": "Revenue item not found"}), 404

    today = datetime.now().strftime("%Y-%m-%d")
    execute("""UPDATE rate_schedule SET effective_to = date(?, '-1 day')
               WHERE revenue_item_id = ? AND (effective_to IS NULL OR effective_to >= ?)""",
            (today, item_id, today))
    rate_id = execute(
        """INSERT INTO rate_schedule (revenue_item_id, rate_amount, rate_basis,
                                      approved_by_ref, effective_from)
           VALUES (?,?,?,?,?)""",
        (item_id, amount, d.get("rate_basis", "FLAT"),
         d.get("approved_by_ref", "Admin rate change"), today),
    )
    audit("REVENUE_ITEM_RATE_CHANGED", "revenue_item", item_id,
          {"new_rate": amount, "rate_id": rate_id})
    return jsonify(query("SELECT * FROM rate_schedule WHERE rate_id = ?", (rate_id,), one=True)), 201


@app.get("/api/revenue-categories")
@auth_required()
def revenue_categories():
    return jsonify(query("SELECT * FROM revenue_category ORDER BY category_code"))


@app.get("/api/wards")
@auth_required()
def wards():
    return jsonify(query("SELECT * FROM ward_zone ORDER BY ward_name"))


# ---------------------------------------------------------------------------
# Module: Assessment & e-Billing
# ---------------------------------------------------------------------------

@app.get("/api/bills")
@auth_required()
def list_bills():
    clause, params = portfolio_filter()
    status = request.args.get("status")
    sql = f"""SELECT b.*, p.full_name, p.payer_ref, p.phone,
                     (b.total_amount - b.amount_paid) AS balance,
                     sc.consultant_name
              FROM bill b
              JOIN payer p ON p.payer_id = b.payer_id
              LEFT JOIN sub_consultant sc ON sc.consultant_id = b.consultant_id
              WHERE 1=1 {clause}"""
    if status:
        sql += " AND b.status = ?"
        params = params + [status]
    sql += " ORDER BY b.issued_at DESC LIMIT 200"
    return jsonify(query(sql, params))


@app.post("/api/bills")
@auth_required("COUNCIL_ADMIN", "CONSULTANT", "AGENT")
def create_bill():
    """Assess and bill in one transaction — used by both portal and mobile app.

    Two ways to build the harmonised bill:
      * `lines`: explicit [{revenue_item_id, quantity}] picks, priced now.
      * `bill_all_drafts: true`: rolls up every DRAFT assessment already
        recorded for the payer (e.g. from enumeration) — a harmonised bill is
        just the payer's outstanding revenue items paid together as one.
    """
    d = request.get_json(force=True)
    lines = d.get("lines", [])
    payer = query("SELECT * FROM payer WHERE payer_id = ?", (d.get("payer_id"),), one=True)
    if not payer:
        return jsonify({"error": "Payer not found"}), 404
    if not lines and not d.get("bill_all_drafts"):
        return jsonify({"error": "Add at least one revenue item to the bill"}), 400

    consultant_id = d.get("consultant_id") or g.current_user.get("consultant_id")
    due = d.get("due_date") or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Two-phase bill_ref: insert with a throwaway-unique placeholder, then
    # derive the real reference from the auto-increment bill_id so two
    # concurrent requests can never generate the same reference.
    bill_id = execute(
        """INSERT INTO bill (bill_ref, payer_id, consultant_id, total_amount, due_date,
                             status, issued_by)
           VALUES (?,?,?,0,?, 'ISSUED', ?)""",
        (f"TMP-{uuid.uuid4().hex}", d["payer_id"], consultant_id, due, g.current_user["user_id"]),
    )
    bill_ref = f"KAC/{datetime.now():%Y}/{bill_id:06d}"
    execute("UPDATE bill SET bill_ref = ? WHERE bill_id = ?", (bill_ref, bill_id))

    total = 0.0

    if d.get("bill_all_drafts"):
        drafts = query("""SELECT * FROM assessment WHERE payer_id = ? AND status = 'DRAFT'""",
                       (d["payer_id"],))
        for a in drafts:
            execute("""UPDATE assessment SET status = 'BILLED', consultant_id = ?
                       WHERE assessment_id = ?""", (consultant_id, a["assessment_id"]))
            execute("INSERT INTO bill_line (bill_id, assessment_id, line_amount) VALUES (?,?,?)",
                    (bill_id, a["assessment_id"], a["assessed_amount"]))
            total += a["assessed_amount"]
    else:
        for ln in lines:
            item = query("""SELECT ri.*, (SELECT rate_id FROM rate_schedule rs
                              WHERE rs.revenue_item_id = ri.revenue_item_id
                              ORDER BY rs.effective_from DESC LIMIT 1) AS rate_id,
                              (SELECT rate_amount FROM rate_schedule rs
                              WHERE rs.revenue_item_id = ri.revenue_item_id
                              ORDER BY rs.effective_from DESC LIMIT 1) AS rate_amount
                            FROM revenue_item ri WHERE ri.revenue_item_id = ?""",
                         (ln["revenue_item_id"],), one=True)
            if not item or item["rate_id"] is None:
                return jsonify({"error": "That revenue item has no approved rate in the schedule"}), 400
            qty = float(ln.get("quantity", 1))
            amount = round(item["rate_amount"] * qty, 2)
            assessment_id = execute(
                """INSERT INTO assessment (payer_id, asset_id, revenue_item_id, rate_id,
                                           consultant_id, period_year, quantity,
                                           assessed_amount, status, created_by)
                   VALUES (?,?,?,?,?,?,?,?, 'BILLED', ?)""",
                (d["payer_id"], ln.get("asset_id"), item["revenue_item_id"], item["rate_id"],
                 consultant_id, datetime.now().year, qty, amount, g.current_user["user_id"]),
            )
            execute("INSERT INTO bill_line (bill_id, assessment_id, line_amount) VALUES (?,?,?)",
                    (bill_id, assessment_id, amount))
            total += amount

    if total == 0.0:
        execute("DELETE FROM bill WHERE bill_id = ?", (bill_id,))
        return jsonify({"error": "This payer has no draft assessments to bill"}), 400

    execute("UPDATE bill SET total_amount = ? WHERE bill_id = ?", (round(total, 2), bill_id))
    audit("BILL_ISSUED", "bill", bill_id, {"bill_ref": bill_ref, "total": total})
    return jsonify({"bill_id": bill_id, "bill_ref": bill_ref, "total_amount": round(total, 2)}), 201


@app.get("/api/bills/<path:bill_ref>")
def bill_lookup(bill_ref):
    """Public bill lookup — powers the citizen self-service portal, USSD and the
    printable Harmonised Demand Notice."""
    bill = query(
        """SELECT b.bill_id, b.bill_ref, b.total_amount, b.amount_paid, b.due_date, b.status,
                  b.issued_at, p.payer_id, p.full_name, p.payer_ref, p.phone, p.address,
                  w.ward_name
           FROM bill b JOIN payer p ON p.payer_id = b.payer_id
           LEFT JOIN ward_zone w ON w.ward_id = p.ward_id
           WHERE b.bill_ref = ?""", (bill_ref,), one=True)
    if not bill:
        return jsonify({"error": "No bill found with that reference"}), 404
    bill["balance"] = round(bill["total_amount"] - bill["amount_paid"], 2)
    bill["lines"] = query(
        """SELECT ri.item_name, ri.harmonised_code, bl.line_amount, a.quantity
           FROM bill_line bl
           JOIN assessment a ON a.assessment_id = bl.assessment_id
           JOIN revenue_item ri ON ri.revenue_item_id = a.revenue_item_id
           WHERE bl.bill_id = ?""", (bill["bill_id"],))
    bill["prior_arrears"] = query(
        """SELECT COALESCE(SUM(total_amount - amount_paid),0) AS a FROM bill
           WHERE payer_id = ? AND bill_id <> ? AND status IN ('ISSUED','PART_PAID','OVERDUE')""",
        (bill["payer_id"], bill["bill_id"]), one=True)["a"]
    return jsonify(bill)


# ---------------------------------------------------------------------------
# Payments — internal posting + e-receipting
# ---------------------------------------------------------------------------

def post_payment(bill_id, channel_code, amount, bank_txn_ref=None,
                 terminal_id=None, agent_id=None, geo=None):
    """Single money-in path used by every channel. Returns (payment, receipt)."""
    channel = query("SELECT * FROM payment_channel WHERE channel_code = ?",
                    (channel_code,), one=True)
    if not channel:
        raise ChannelError(f"Payment channel {channel_code} is not configured")

    bill = query("SELECT * FROM bill WHERE bill_id = ?", (bill_id,), one=True)
    if not bill:
        raise ChannelError("Bill not found")
    if bill["status"] == "CANCELLED":
        raise ChannelError("This bill has been cancelled and cannot take payment")

    payment_ref = f"PMT-{uuid.uuid4().hex[:12].upper()}"
    payment_id = execute(
        """INSERT INTO payment (payment_ref, bill_id, channel_id, terminal_id, agent_id,
                                amount, bank_txn_ref, txn_status, geo_lat, geo_lng)
           VALUES (?,?,?,?,?,?,?, 'CONFIRMED', ?, ?)""",
        (payment_ref, bill_id, channel["channel_id"], terminal_id, agent_id,
         round(float(amount), 2), bank_txn_ref,
         (geo or {}).get("lat"), (geo or {}).get("lng")),
    )

    new_paid = round(bill["amount_paid"] + float(amount), 2)
    status = "PAID" if new_paid >= bill["total_amount"] - 0.01 else "PART_PAID"
    execute("UPDATE bill SET amount_paid = ?, status = ? WHERE bill_id = ?",
            (new_paid, status, bill_id))

    receipt_ref = f"RCP-{datetime.now():%Y%m%d}-{payment_id:06d}"
    receipt_id = execute(
        """INSERT INTO receipt (receipt_ref, payment_id, qr_token, sms_sent)
           VALUES (?,?,?,1)""", (receipt_ref, payment_id, str(uuid.uuid4())))

    # Close the debt case once the bill is settled
    if status == "PAID":
        execute("""UPDATE debt_case SET enforcement_stage='CLOSED',
                   updated_at=datetime('now') WHERE bill_id = ?""", (bill_id,))

    return (query("SELECT * FROM payment WHERE payment_id = ?", (payment_id,), one=True),
            query("SELECT * FROM receipt WHERE receipt_id = ?", (receipt_id,), one=True))


@app.get("/api/payments")
@auth_required()
def list_payments():
    return jsonify(query(
        """SELECT p.*, pc.channel_name, pc.channel_code, b.bill_ref,
                  py.full_name, r.receipt_ref
           FROM payment p
           JOIN payment_channel pc ON pc.channel_id = p.channel_id
           JOIN bill b ON b.bill_id = p.bill_id
           JOIN payer py ON py.payer_id = b.payer_id
           LEFT JOIN receipt r ON r.payment_id = p.payment_id
           ORDER BY p.paid_at DESC LIMIT 200"""))


@app.post("/api/payments")
@auth_required("COUNCIL_ADMIN", "CONSULTANT", "AGENT")
def record_payment():
    d = request.get_json(force=True)
    agent = query("SELECT agent_id FROM field_agent WHERE user_id = ?",
                  (g.current_user["user_id"],), one=True)
    try:
        payment, receipt = post_payment(
            d["bill_id"], d.get("channel_code", "POS"), d["amount"],
            bank_txn_ref=d.get("bank_txn_ref"),
            terminal_id=d.get("terminal_id"),
            agent_id=agent["agent_id"] if agent else None,
            geo=d.get("geo"),
        )
    except ChannelError as e:
        return jsonify({"error": str(e)}), 400
    audit("PAYMENT_POSTED", "payment", payment["payment_id"], {"amount": d["amount"]})
    return jsonify({"payment": payment, "receipt": receipt}), 201


@app.get("/api/receipts")
@auth_required()
def list_receipts():
    return jsonify(query(
        """SELECT r.*, p.amount, p.paid_at, b.bill_ref, py.full_name, pc.channel_name
           FROM receipt r
           JOIN payment p ON p.payment_id = r.payment_id
           JOIN bill b ON b.bill_id = p.bill_id
           JOIN payer py ON py.payer_id = b.payer_id
           JOIN payment_channel pc ON pc.channel_id = p.channel_id
           ORDER BY r.issued_at DESC LIMIT 200"""))


@app.get("/api/verify/<qr_token>")
def verify_receipt(qr_token):
    """Public QR / SMS receipt verification — no authentication required."""
    rec = query(
        """SELECT r.receipt_ref, r.issued_at, p.amount, b.bill_ref, py.full_name,
                  pc.channel_name
           FROM receipt r
           JOIN payment p ON p.payment_id = r.payment_id
           JOIN bill b ON b.bill_id = p.bill_id
           JOIN payer py ON py.payer_id = b.payer_id
           JOIN payment_channel pc ON pc.channel_id = p.channel_id
           WHERE r.qr_token = ?""", (qr_token,), one=True)
    if not rec:
        return jsonify({"valid": False, "message": "No receipt matches this code"}), 404
    execute("UPDATE receipt SET verified_count = verified_count + 1 WHERE qr_token = ?",
            (qr_token,))
    return jsonify({"valid": True, "receipt": rec})


# ---------------------------------------------------------------------------
# e-CHANNEL INTEGRATION — webhooks and settlement intake
# ---------------------------------------------------------------------------

@app.get("/api/channels")
def channels():
    cat = {c["code"]: c for c in channel_catalogue()}
    rows = query("SELECT * FROM payment_channel ORDER BY channel_id")
    for r in rows:
        r.update(cat.get(r["channel_code"], {}))
    return jsonify(rows)


@app.post("/api/channels/<channel_code>/webhook")
def channel_webhook(channel_code):
    """
    Inbound notification from a collecting-bank e-channel.

    Security: HMAC-SHA256 over the raw body in the X-RevAc-Signature header.
    Idempotency: (channel_id, bank_txn_ref) is unique — a replayed
    notification returns the original result rather than double-posting.
    """
    code = channel_code.upper()
    secret = CHANNEL_SECRETS.get(code)
    if not secret:
        return jsonify({"error": f"Channel {code} is not configured"}), 404

    try:
        adapter = get_adapter(code, secret)
    except ChannelError as e:
        return jsonify({"error": str(e)}), 404

    raw = request.get_data()
    signature = request.headers.get("X-RevAc-Signature", "")
    strict = os.environ.get("REVAC_STRICT_SIGNATURES", "0") == "1"
    if strict and not adapter.verify_signature(raw, signature):
        return jsonify({"error": "Signature verification failed"}), 401

    payload = request.get_json(force=True, silent=True) or {}
    ok, err = adapter.validate(payload)
    if not ok:
        return jsonify({"status": "rejected", "error": err}), 400

    txn = adapter.normalise(payload)
    channel = query("SELECT * FROM payment_channel WHERE channel_code = ?", (code,), one=True)

    # Idempotency guard
    existing = query(
        "SELECT * FROM channel_transaction_feed WHERE channel_id = ? AND bank_txn_ref = ?",
        (channel["channel_id"], txn.bank_txn_ref), one=True)
    if existing:
        return jsonify({"status": "duplicate", "feed_id": existing["feed_id"],
                        "message": "This transaction reference has already been received"}), 200

    feed_id = execute(
        """INSERT INTO channel_transaction_feed
             (channel_id, bank_txn_ref, narration, amount, value_date, raw_payload)
           VALUES (?,?,?,?,?,?)""",
        (channel["channel_id"], txn.bank_txn_ref, txn.narration, txn.amount,
         txn.value_date, txn.raw))

    bill = query("SELECT * FROM bill WHERE bill_ref = ?", (txn.bill_ref,), one=True)
    if not bill:
        execute("UPDATE channel_transaction_feed SET match_status='EXCEPTION' WHERE feed_id = ?",
                (feed_id,))
        return jsonify({"status": "accepted_unmatched", "feed_id": feed_id,
                        "message": "Payment received but no bill matches that reference"}), 202

    terminal = None
    if txn.terminal_id:
        t = query("SELECT terminal_id FROM pos_terminal WHERE bank_terminal_id = ?",
                  (txn.terminal_id,), one=True)
        terminal = t["terminal_id"] if t else None

    try:
        payment, receipt = post_payment(bill["bill_id"], code, txn.amount,
                                        bank_txn_ref=txn.bank_txn_ref, terminal_id=terminal)
    except ChannelError as e:
        execute("UPDATE channel_transaction_feed SET match_status='EXCEPTION' WHERE feed_id = ?",
                (feed_id,))
        return jsonify({"status": "rejected", "error": str(e)}), 400

    execute("""UPDATE channel_transaction_feed
               SET match_status='MATCHED', matched_payment_id=? WHERE feed_id = ?""",
            (payment["payment_id"], feed_id))

    return jsonify({
        "status": "posted",
        "paymentRef": payment["payment_ref"],
        "receiptRef": receipt["receipt_ref"],
        "verifyToken": receipt["qr_token"],
        "billRef": txn.bill_ref,
        "amount": txn.amount,
    }), 201


@app.post("/api/channels/OTC/settlement")
def otc_settlement():
    """End-of-day teller settlement file intake (array of rows)."""
    rows = request.get_json(force=True)
    if not isinstance(rows, list):
        return jsonify({"error": "Send the settlement file as a JSON array of rows"}), 400
    adapter = get_adapter("OTC", CHANNEL_SECRETS["OTC"])
    channel = query("SELECT * FROM payment_channel WHERE channel_code='OTC'", one=True)
    posted, skipped, exceptions = 0, 0, []
    for row in rows:
        ok, err = adapter.validate(row)
        if not ok:
            exceptions.append({"row": row, "error": err})
            continue
        txn = adapter.normalise(row)
        if query("SELECT 1 FROM channel_transaction_feed WHERE channel_id=? AND bank_txn_ref=?",
                 (channel["channel_id"], txn.bank_txn_ref), one=True):
            skipped += 1
            continue
        feed_id = execute(
            """INSERT INTO channel_transaction_feed
                 (channel_id, bank_txn_ref, narration, amount, value_date, raw_payload)
               VALUES (?,?,?,?,?,?)""",
            (channel["channel_id"], txn.bank_txn_ref, txn.narration, txn.amount,
             txn.value_date, txn.raw))
        bill = query("SELECT * FROM bill WHERE bill_ref = ?", (txn.bill_ref,), one=True)
        if not bill:
            execute("UPDATE channel_transaction_feed SET match_status='EXCEPTION' WHERE feed_id=?",
                    (feed_id,))
            exceptions.append({"ref": txn.bank_txn_ref, "error": "No matching bill"})
            continue
        payment, _ = post_payment(bill["bill_id"], "OTC", txn.amount,
                                  bank_txn_ref=txn.bank_txn_ref)
        execute("""UPDATE channel_transaction_feed SET match_status='MATCHED',
                   matched_payment_id=? WHERE feed_id=?""", (payment["payment_id"], feed_id))
        posted += 1
    return jsonify({"posted": posted, "duplicates_skipped": skipped,
                    "exceptions": exceptions}), 200


@app.post("/api/channels/USSD/session")
def ussd_session():
    """
    USSD gateway callback. Stateless: the gateway sends the accumulated
    input string, RevAc returns CON (continue) or END (terminate).
    """
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    parts = [p for p in text.split("*") if p]

    if not parts:
        return jsonify({"response": "CON Welcome to KAC Revenue\n"
                                    "1. Pay a bill\n2. Check balance\n3. Verify receipt"})
    if parts[0] == "1":
        if len(parts) == 1:
            return jsonify({"response": "CON Enter your Bill Reference:"})
        bill = query("SELECT * FROM bill WHERE bill_ref = ?", (parts[1],), one=True)
        if not bill:
            return jsonify({"response": "END No bill found with that reference."})
        balance = round(bill["total_amount"] - bill["amount_paid"], 2)
        if len(parts) == 2:
            return jsonify({"response": f"CON Balance: NGN {balance:,.2f}\n"
                                        f"Enter amount to pay:"})
        try:
            amount = float(parts[2])
        except ValueError:
            return jsonify({"response": "END Enter a valid amount."})
        payment, receipt = post_payment(bill["bill_id"], "USSD", amount,
                                        bank_txn_ref=f"USSD-{uuid.uuid4().hex[:10].upper()}")
        return jsonify({"response": f"END Payment of NGN {amount:,.2f} received. "
                                    f"Receipt {receipt['receipt_ref']}."})
    if parts[0] == "2":
        if len(parts) == 1:
            return jsonify({"response": "CON Enter your Payer ID:"})
        payer = query("SELECT * FROM payer WHERE payer_ref = ?", (parts[1],), one=True)
        if not payer:
            return jsonify({"response": "END Payer ID not recognised."})
        due = query("""SELECT COALESCE(SUM(total_amount - amount_paid),0) AS bal
                       FROM bill WHERE payer_id = ? AND status IN ('ISSUED','PART_PAID','OVERDUE')""",
                    (payer["payer_id"],), one=True)
        return jsonify({"response": f"END {payer['full_name']}: outstanding "
                                    f"NGN {due['bal']:,.2f}"})
    if parts[0] == "3":
        if len(parts) == 1:
            return jsonify({"response": "CON Enter Receipt Reference:"})
        rec = query("SELECT * FROM receipt WHERE receipt_ref = ?", (parts[1],), one=True)
        return jsonify({"response": "END Receipt is valid." if rec
                                    else "END Receipt not found."})
    return jsonify({"response": "END Invalid selection."})


# ---------------------------------------------------------------------------
# Reconciliation & commission settlement
# ---------------------------------------------------------------------------

@app.get("/api/reconciliation")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def reconciliation_list():
    runs = query("""SELECT r.*, pc.channel_name,
                           (r.total_platform - r.total_bank) AS variance
                    FROM reconciliation_run r
                    LEFT JOIN payment_channel pc ON pc.channel_id = r.channel_id
                    ORDER BY r.run_date DESC LIMIT 50""")
    unmatched = query("""SELECT f.*, pc.channel_name FROM channel_transaction_feed f
                         JOIN payment_channel pc ON pc.channel_id = f.channel_id
                         WHERE f.match_status <> 'MATCHED' ORDER BY f.received_at DESC""")
    return jsonify({"runs": runs, "unmatched": unmatched})


@app.post("/api/reconciliation/run")
@auth_required("COUNCIL_ADMIN")
def reconciliation_run():
    """Match platform payments against the bank feed for a given date."""
    d = request.get_json(force=True) or {}
    run_date = d.get("date") or datetime.now().strftime("%Y-%m-%d")
    results = []
    for ch in query("SELECT * FROM payment_channel"):
        plat = query("""SELECT COALESCE(SUM(amount),0) AS t FROM payment
                        WHERE channel_id = ? AND txn_status='CONFIRMED'
                          AND date(paid_at) = ?""",
                     (ch["channel_id"], run_date), one=True)["t"]
        bank = query("""SELECT COALESCE(SUM(amount),0) AS t FROM channel_transaction_feed
                        WHERE channel_id = ? AND value_date = ?""",
                     (ch["channel_id"], run_date), one=True)["t"]
        status = "BALANCED" if abs(plat - bank) < 0.01 else "EXCEPTIONS"
        recon_id = execute(
            """INSERT INTO reconciliation_run (run_date, channel_id, total_platform,
                                               total_bank, status, run_by)
               VALUES (?,?,?,?,?,?)""",
            (run_date, ch["channel_id"], plat, bank, status, g.current_user["user_id"]))

        if status == "EXCEPTIONS":
            for f in query("""SELECT * FROM channel_transaction_feed
                              WHERE channel_id=? AND value_date=? AND match_status<>'MATCHED'""",
                           (ch["channel_id"], run_date)):
                execute("""INSERT INTO reconciliation_exception
                             (recon_id, feed_id, exception_type)
                           VALUES (?,?, 'UNMATCHED_BANK_CREDIT')""", (recon_id, f["feed_id"]))
        results.append({"channel": ch["channel_name"], "platform": plat,
                        "bank": bank, "variance": round(plat - bank, 2), "status": status})
    audit("RECONCILIATION_RUN", "reconciliation_run", None, {"date": run_date})
    return jsonify({"run_date": run_date, "results": results})


@app.get("/api/settlements")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def settlements():
    clause, params = "", []
    if g.current_user["access_level"] == "CONSULTANT":
        clause = " WHERE s.consultant_id = ? "
        params = [g.current_user["consultant_id"]]
    return jsonify(query(
        f"""SELECT s.*, sc.consultant_name FROM commission_settlement s
            JOIN sub_consultant sc ON sc.consultant_id = s.consultant_id
            {clause} ORDER BY s.period_end DESC""", params))


@app.post("/api/settlements/compute")
@auth_required("COUNCIL_ADMIN")
def compute_settlements():
    d = request.get_json(force=True) or {}
    start = d.get("period_start") or datetime.now().replace(day=1).strftime("%Y-%m-%d")
    end = d.get("period_end") or datetime.now().strftime("%Y-%m-%d")
    created = []
    for sc in query("SELECT * FROM sub_consultant WHERE status='ACTIVE'"):
        gross = query(
            """SELECT COALESCE(SUM(p.amount),0) AS t FROM payment p
               JOIN bill b ON b.bill_id = p.bill_id
               WHERE b.consultant_id = ? AND p.txn_status='CONFIRMED'
                 AND date(p.paid_at) BETWEEN ? AND ?""",
            (sc["consultant_id"], start, end), one=True)["t"]
        commission = round(gross * sc["commission_rate"] / 100, 2)
        try:
            execute("""INSERT INTO commission_settlement
                         (consultant_id, period_start, period_end, gross_collections,
                          commission_rate, commission_amount)
                       VALUES (?,?,?,?,?,?)""",
                    (sc["consultant_id"], start, end, gross, sc["commission_rate"], commission))
        except sqlite3.IntegrityError:
            execute("""UPDATE commission_settlement
                       SET gross_collections=?, commission_amount=?
                       WHERE consultant_id=? AND period_start=? AND period_end=?""",
                    (gross, commission, sc["consultant_id"], start, end))
        created.append({"consultant": sc["consultant_name"], "gross": gross,
                        "commission": commission})
    audit("SETTLEMENT_COMPUTED", "commission_settlement", None, {"period": f"{start}..{end}"})
    return jsonify({"period_start": start, "period_end": end, "settlements": created})


# ---------------------------------------------------------------------------
# Debt management & enforcement
# ---------------------------------------------------------------------------

@app.get("/api/debt")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def debt_cases():
    return jsonify(query(
        """SELECT d.*, b.bill_ref, b.total_amount, b.amount_paid, b.due_date,
                  (b.total_amount - b.amount_paid) AS balance,
                  p.full_name, p.phone
           FROM debt_case d
           JOIN bill b ON b.bill_id = d.bill_id
           JOIN payer p ON p.payer_id = b.payer_id
           WHERE d.enforcement_stage <> 'CLOSED'
           ORDER BY balance DESC LIMIT 200"""))


@app.post("/api/debt/refresh")
@auth_required("COUNCIL_ADMIN")
def refresh_debt():
    """Age unpaid bills and open/refresh enforcement cases."""
    opened = 0
    for b in query("""SELECT bill_id, due_date FROM bill
                      WHERE status IN ('ISSUED','PART_PAID','OVERDUE')
                        AND due_date < date('now')"""):
        days = (datetime.now() - datetime.strptime(b["due_date"], "%Y-%m-%d")).days
        bucket = "0_30" if days <= 30 else "31_60" if days <= 60 else \
                 "61_90" if days <= 90 else "OVER_90"
        existing = query("SELECT debt_id FROM debt_case WHERE bill_id = ?",
                         (b["bill_id"],), one=True)
        if existing:
            execute("""UPDATE debt_case SET ageing_bucket=?, updated_at=datetime('now')
                       WHERE debt_id=?""", (bucket, existing["debt_id"]))
        else:
            execute("""INSERT INTO debt_case (bill_id, ageing_bucket, enforcement_stage)
                       VALUES (?,?, 'FIRST_NOTICE')""", (b["bill_id"], bucket))
            opened += 1
        execute("UPDATE bill SET status='OVERDUE' WHERE bill_id=? AND status='ISSUED'",
                (b["bill_id"],))
    ageing = query("SELECT * FROM v_debt_ageing")
    return jsonify({"cases_opened": opened, "ageing": ageing})


@app.post("/api/debt/<int:debt_id>/escalate")
@auth_required("COUNCIL_ADMIN")
def escalate_debt(debt_id):
    ladder = ["NONE", "FIRST_NOTICE", "FINAL_NOTICE", "ENFORCEMENT", "LEGAL", "CLOSED"]
    case = query("SELECT * FROM debt_case WHERE debt_id = ?", (debt_id,), one=True)
    if not case:
        return jsonify({"error": "Case not found"}), 404
    idx = min(ladder.index(case["enforcement_stage"]) + 1, len(ladder) - 1)
    execute("""UPDATE debt_case SET enforcement_stage=?, reminder_count=reminder_count+1,
               last_reminder_at=datetime('now'), updated_at=datetime('now')
               WHERE debt_id=?""", (ladder[idx], debt_id))
    audit("DEBT_ESCALATED", "debt_case", debt_id, {"to": ladder[idx]})
    return jsonify({"debt_id": debt_id, "enforcement_stage": ladder[idx]})


# ---------------------------------------------------------------------------
# Sub-consultants, agents, terminals, audit
# ---------------------------------------------------------------------------

@app.get("/api/consultants")
@auth_required("COUNCIL_ADMIN", "GLOBAL_VIEW")
def consultants():
    return jsonify(query(
        """SELECT sc.*, COUNT(DISTINCT fa.agent_id) AS agents
           FROM sub_consultant sc
           LEFT JOIN field_agent fa ON fa.consultant_id = sc.consultant_id
           GROUP BY sc.consultant_id ORDER BY sc.consultant_name"""))


@app.post("/api/consultants")
@auth_required("COUNCIL_ADMIN")
def onboard_consultant():
    """Admin onboards a new sub-consultant onto the platform."""
    d = request.get_json(force=True)
    if not d.get("consultant_name"):
        return jsonify({"error": "Enter the consultant's name"}), 400
    rate = d.get("commission_rate", 0)
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return jsonify({"error": "Commission rate must be a number"}), 400

    consultant_id = execute(
        """INSERT INTO sub_consultant (council_id, consultant_code, consultant_name,
                                       contract_ref, commission_rate, status, onboarded_at)
           VALUES (1,?,?,?,?, 'ACTIVE', datetime('now'))""",
        (f"SC-{uuid.uuid4().hex[:6].upper()}", d["consultant_name"],
         d.get("contract_ref"), rate),
    )
    execute("UPDATE sub_consultant SET consultant_code = ? WHERE consultant_id = ?",
            (f"SC-{consultant_id:03d}", consultant_id))
    audit("CONSULTANT_ONBOARDED", "sub_consultant", consultant_id,
          {"consultant_name": d["consultant_name"]})
    return jsonify(query("SELECT * FROM sub_consultant WHERE consultant_id = ?",
                         (consultant_id,), one=True)), 201


@app.post("/api/consultants/<int:cid>/status")
@auth_required("COUNCIL_ADMIN")
def consultant_status(cid):
    d = request.get_json(force=True)
    status = d.get("status")
    if status not in ("PENDING", "ACTIVE", "SUSPENDED", "EXITED"):
        return jsonify({"error": "Choose a valid status"}), 400
    execute("UPDATE sub_consultant SET status = ? WHERE consultant_id = ?", (status, cid))
    audit("CONSULTANT_STATUS_CHANGED", "sub_consultant", cid, {"status": status})
    return jsonify({"consultant_id": cid, "status": status})


def _consultant_scope_ok(consultant_id):
    """A CONSULTANT user may only act on their own record; admin can act on any."""
    user = g.current_user
    if user["access_level"] == "CONSULTANT" and user.get("consultant_id") != consultant_id:
        return False
    return True


@app.get("/api/consultants/<int:cid>/portfolio")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def consultant_portfolio(cid):
    if not _consultant_scope_ok(cid):
        return jsonify({"error": "You may only view your own portfolio"}), 403
    return jsonify(query(
        """SELECT cp.*, ri.item_name, ri.harmonised_code, w.ward_name
           FROM consultant_portfolio cp
           JOIN revenue_item ri ON ri.revenue_item_id = cp.revenue_item_id
           LEFT JOIN ward_zone w ON w.ward_id = cp.ward_id
           WHERE cp.consultant_id = ?
             AND (cp.effective_to IS NULL OR cp.effective_to >= date('now'))
           ORDER BY ri.item_name""", (cid,)))


@app.post("/api/consultants/<int:cid>/portfolio")
@auth_required("COUNCIL_ADMIN")
def assign_consultant_portfolio(cid):
    """Admin specifies which revenue items a consultant is allowed to handle."""
    d = request.get_json(force=True)
    if not d.get("revenue_item_id"):
        return jsonify({"error": "Choose a revenue item"}), 400
    if not query("SELECT 1 FROM sub_consultant WHERE consultant_id = ?", (cid,), one=True):
        return jsonify({"error": "Consultant not found"}), 404
    portfolio_id = execute(
        """INSERT INTO consultant_portfolio (consultant_id, revenue_item_id, ward_id, effective_from)
           VALUES (?,?,?,?)""",
        (cid, d["revenue_item_id"], d.get("ward_id"),
         d.get("effective_from") or datetime.now().strftime("%Y-%m-%d")),
    )
    audit("CONSULTANT_PORTFOLIO_ASSIGNED", "consultant_portfolio", portfolio_id,
          {"consultant_id": cid, "revenue_item_id": d["revenue_item_id"]})
    return jsonify(query("SELECT * FROM consultant_portfolio WHERE portfolio_id = ?",
                         (portfolio_id,), one=True)), 201


@app.post("/api/consultants/<int:cid>/portfolio/<int:portfolio_id>/end")
@auth_required("COUNCIL_ADMIN")
def end_consultant_portfolio(cid, portfolio_id):
    """Revoke a consultant's access to a revenue item (keeps history intact)."""
    row = query("SELECT * FROM consultant_portfolio WHERE portfolio_id = ? AND consultant_id = ?",
                (portfolio_id, cid), one=True)
    if not row:
        return jsonify({"error": "Assignment not found"}), 404
    execute("UPDATE consultant_portfolio SET effective_to = date('now') WHERE portfolio_id = ?",
            (portfolio_id,))
    audit("CONSULTANT_PORTFOLIO_REVOKED", "consultant_portfolio", portfolio_id, {"consultant_id": cid})
    return jsonify({"portfolio_id": portfolio_id, "status": "revoked"})


@app.get("/api/agents")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def agents():
    clause, params = "", []
    if g.current_user["access_level"] == "CONSULTANT":
        clause = " WHERE fa.consultant_id = ? "
        params = [g.current_user["consultant_id"]]
    return jsonify(query(
        f"""SELECT fa.*, u.full_name, u.phone, w.ward_name, sc.consultant_name,
                   COALESCE((SELECT SUM(amount_collected) FROM agent_daily_return adr
                             WHERE adr.agent_id = fa.agent_id),0) AS lifetime_collected
            FROM field_agent fa
            JOIN app_user u ON u.user_id = fa.user_id
            LEFT JOIN ward_zone w ON w.ward_id = fa.assigned_ward_id
            LEFT JOIN sub_consultant sc ON sc.consultant_id = fa.consultant_id
            {clause} ORDER BY u.full_name""", params))


@app.post("/api/agents")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def onboard_agent():
    """Onboard a field agent. A consultant onboards their own team; admin can
    onboard for any consultant (or directly for the Council)."""
    d = request.get_json(force=True)
    if not d.get("full_name") or not d.get("username"):
        return jsonify({"error": "Enter the agent's name and a username"}), 400
    if query("SELECT 1 FROM app_user WHERE username = ?", (d["username"],), one=True):
        return jsonify({"error": "That username is already taken"}), 409

    consultant_id = d.get("consultant_id")
    if g.current_user["access_level"] == "CONSULTANT":
        consultant_id = g.current_user["consultant_id"]

    role = query("SELECT role_id FROM app_role WHERE role_code = 'AGENT'", one=True)
    user_id = execute(
        """INSERT INTO app_user (council_id, consultant_id, role_id, username, full_name,
                                 phone, email, password_hash)
           VALUES (1,?,?,?,?,?,?,?)""",
        (consultant_id, role["role_id"], d["username"], d["full_name"],
         d.get("phone"), d.get("email"), hash_password(d.get("password") or "revac2026")),
    )
    seq = query("SELECT COUNT(*) AS n FROM field_agent", one=True)["n"] + 1
    agent_id = execute(
        """INSERT INTO field_agent (user_id, consultant_id, agent_code, assigned_ward_id,
                                    device_imei)
           VALUES (?,?,?,?,?)""",
        (user_id, consultant_id, f"AG-{seq:03d}", d.get("assigned_ward_id"), d.get("device_imei")),
    )
    audit("AGENT_ONBOARDED", "field_agent", agent_id, {"full_name": d["full_name"]})
    return jsonify(query(
        """SELECT fa.*, u.full_name, u.username FROM field_agent fa
           JOIN app_user u ON u.user_id = fa.user_id WHERE fa.agent_id = ?""",
        (agent_id,), one=True)), 201


@app.get("/api/agents/<int:agent_id>/activity")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def agent_activity(agent_id):
    """Daily collection activity for one agent — lets a consultant track their team."""
    agent = query("SELECT * FROM field_agent WHERE agent_id = ?", (agent_id,), one=True)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
    if (g.current_user["access_level"] == "CONSULTANT"
            and agent["consultant_id"] != g.current_user["consultant_id"]):
        return jsonify({"error": "You may only view your own agents"}), 403
    returns = query(
        """SELECT * FROM agent_daily_return WHERE agent_id = ?
           ORDER BY return_date DESC LIMIT 30""", (agent_id,))
    recent_payments = query(
        """SELECT p.payment_ref, p.amount, p.paid_at, pc.channel_name, b.bill_ref
           FROM payment p
           JOIN payment_channel pc ON pc.channel_id = p.channel_id
           JOIN bill b ON b.bill_id = p.bill_id
           WHERE p.agent_id = ? ORDER BY p.paid_at DESC LIMIT 20""", (agent_id,))
    return jsonify({"agent_id": agent_id, "daily_returns": returns,
                    "recent_payments": recent_payments})


@app.get("/api/terminals")
@auth_required("COUNCIL_ADMIN", "CONSULTANT")
def terminals():
    return jsonify(query(
        """SELECT t.*, u.full_name AS agent_name, w.ward_name,
                  COALESCE((SELECT SUM(amount) FROM payment p
                            WHERE p.terminal_id = t.terminal_id
                              AND p.txn_status='CONFIRMED'),0) AS collected
           FROM pos_terminal t
           LEFT JOIN field_agent fa ON fa.agent_id = t.assigned_agent_id
           LEFT JOIN app_user u ON u.user_id = fa.user_id
           LEFT JOIN ward_zone w ON w.ward_id = t.ward_id
           ORDER BY t.terminal_serial"""))


@app.get("/api/audit")
@auth_required("COUNCIL_ADMIN")
def audit_trail():
    return jsonify(query(
        """SELECT a.*, u.full_name, u.username FROM audit_log a
           LEFT JOIN app_user u ON u.user_id = a.user_id
           ORDER BY a.occurred_at DESC LIMIT 300"""))


# ---------------------------------------------------------------------------
# Mobile field-agent endpoints (offline sync)
# ---------------------------------------------------------------------------

@app.get("/api/mobile/worklist")
@auth_required("AGENT")
def agent_worklist():
    agent = query("SELECT * FROM field_agent WHERE user_id = ?",
                  (g.current_user["user_id"],), one=True)
    if not agent:
        return jsonify({"error": "This account is not linked to a field agent record"}), 404
    payers = query(
        """SELECT p.*, w.ward_name,
                  COALESCE((SELECT SUM(total_amount - amount_paid) FROM bill b
                            WHERE b.payer_id = p.payer_id
                              AND b.status IN ('ISSUED','PART_PAID','OVERDUE')),0) AS outstanding
           FROM payer p LEFT JOIN ward_zone w ON w.ward_id = p.ward_id
           WHERE p.ward_id = ? AND p.is_duplicate_of IS NULL
           ORDER BY outstanding DESC LIMIT 100""", (agent["assigned_ward_id"],))
    today = query(
        """SELECT COALESCE(SUM(p.amount),0) AS collected, COUNT(*) AS txns
           FROM payment p WHERE p.agent_id = ? AND date(p.paid_at) = date('now')""",
        (agent["agent_id"],), one=True)
    return jsonify({"agent": dict(agent), "payers": payers, "today": today})


@app.post("/api/mobile/sync")
@auth_required("AGENT")
def mobile_sync():
    """Accepts a batch of offline-captured records and replays them server-side."""
    batch = request.get_json(force=True)
    agent = query("SELECT * FROM field_agent WHERE user_id = ?",
                  (g.current_user["user_id"],), one=True)
    accepted, conflicts = [], []
    for rec in batch.get("records", []):
        try:
            execute("""INSERT INTO sync_queue (agent_id, entity_type, payload,
                                               device_created_at, synced_at, sync_status)
                       VALUES (?,?,?,?,datetime('now'),'SYNCED')""",
                    (agent["agent_id"], rec["entity_type"], json.dumps(rec["payload"]),
                     rec.get("device_created_at", datetime.now().isoformat())))
            if rec["entity_type"] == "PAYMENT":
                p = rec["payload"]
                post_payment(p["bill_id"], p.get("channel_code", "POS"), p["amount"],
                             bank_txn_ref=p.get("bank_txn_ref"), agent_id=agent["agent_id"],
                             geo=p.get("geo"))
            accepted.append(rec.get("client_id"))
        except Exception as e:                                    # noqa: BLE001
            conflicts.append({"client_id": rec.get("client_id"), "reason": str(e)})

    # Roll up the agent's daily return
    today = datetime.now().strftime("%Y-%m-%d")
    stats = query("""SELECT COUNT(*) AS txns, COALESCE(SUM(amount),0) AS amt
                     FROM payment WHERE agent_id=? AND date(paid_at)=?""",
                  (agent["agent_id"], today), one=True)
    execute("""INSERT INTO agent_daily_return (agent_id, return_date, bills_issued,
                                               amount_collected, synced_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(agent_id, return_date) DO UPDATE SET
                 bills_issued=excluded.bills_issued,
                 amount_collected=excluded.amount_collected,
                 synced_at=datetime('now')""",
            (agent["agent_id"], today, stats["txns"], stats["amt"]))
    return jsonify({"accepted": accepted, "conflicts": conflicts,
                    "server_time": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Static hosting
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(os.path.join(ROOT_DIR, "frontend"), "index.html")


@app.get("/m")
@app.get("/m/")
def mobile_index():
    return send_from_directory(os.path.join(ROOT_DIR, "mobile"), "index.html")


@app.get("/frontend/<path:path>")
def frontend_files(path):
    return send_from_directory(os.path.join(ROOT_DIR, "frontend"), path)


@app.get("/mobile/<path:path>")
def mobile_files(path):
    return send_from_directory(os.path.join(ROOT_DIR, "mobile"), path)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "RevAc API",
                    "council": "KAC", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("No database found — run: python seed.py")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
