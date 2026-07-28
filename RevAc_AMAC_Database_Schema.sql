# RevAc Application Suite — AMAC

Revenue Administration & Collection platform for **Abuja Municipal Area Council**, Federal
Capital Territory. Web portal + offline-capable mobile field app + API backend, with
multi-channel e-payment integration.

Built by **Alliance Consulting & Digital Solutions Ltd (ACDSL)** as Lead Revenue Technology
Consultant, as the technical companion to the AMAC Revenue Computerisation Proposal (July 2026).

---

## Run it

```bash
cd backend
python3 seed.py      # creates revac.db with AMAC reference and demonstration data
python3 app.py       # serves on http://127.0.0.1:8000
```

Requires Python 3.10+ and Flask. Nothing else — no build step, no npm, no external services.

| Surface | URL |
|---|---|
| Web portal | http://127.0.0.1:8000/ |
| Mobile field app | http://127.0.0.1:8000/m |
| API health check | http://127.0.0.1:8000/api/health |

### Sign-in accounts (password `revac2026`)

| Username | Role | Sees |
|---|---|---|
| `admin` | Council Revenue Administrator | Everything |
| `headrevenue` | Head of Revenue | Everything |
| `consultant1` | Northgate Revenue Services | Its own portfolio only |
| `consultant2` | Capital Assessment Partners | Its own portfolio only |
| `stakeholder` | Council stakeholder | Global performance view |
| `agent1` … `agent12` | Field collection agents | Mobile app, assigned ward |

---

## What's here

```
backend/
  app.py          Flask API — all nine RevAc modules, 40+ endpoints
  echannels.py    Five e-channel adapters (POS, teller, IB/MB, USSD, agent banking)
  schema.sql      SQLite schema — 24 tables, 3 reporting views
  seed.py         Database initialisation + AMAC demonstration data
frontend/
  index.html      Web portal shell
  app.js          15 module views
  styles.css      Design system
mobile/
  index.html      Field agent PWA
  app.js          Offline queue, sync, GPS enumeration, QR receipts
  sw.js           Service worker — offline app shell
  manifest.json   Installable app manifest
docs/
  ARCHITECTURE.md   Solution architecture
  API_REFERENCE.md  Endpoint reference
RevAc_AMAC_Database_Schema.sql   PostgreSQL reference DDL (production target)
```

---

## Modules

**Revenue operations** — Dashboard · Enumeration · Payer Records · Revenue Items ·
Bill Management · Payments · Receipting

**Control & assurance** — Reconciliation · Debt & Enforcement · Commission Settlements ·
Audit Trail

**Oversight** — Sub-Consultants · Global Performance View · Agents & Terminals

**Integration** — e-Channel Console · Receipt Verification

---

## e-Channel integration

| Channel | Mode | Endpoint |
|---|---|---|
| POS terminals | Real-time webhook | `POST /api/channels/POS/webhook` |
| Over-the-counter (teller) | Settlement file | `POST /api/channels/OTC/settlement` |
| Internet / mobile banking | Real-time webhook | `POST /api/channels/IB_MB/webhook` |
| USSD | Session callback | `POST /api/channels/USSD/session` |
| Agent banking network | Real-time webhook | `POST /api/channels/FIRSTMONIE/webhook` |

Controls: HMAC-SHA256 signatures · idempotency on (channel, bank reference) · field validation ·
unmatched credits held in an exception queue rather than rejected · full raw payload retained ·
daily automated reconciliation per channel.

Try them from the portal: **e-Channel Console** → pick a channel → send a test notification.

---

## Important caveats

- **All data is illustrative.** Revenue items, codes, rates, wards, sub-consultants, payers and
  transactions are demonstration placeholders pending the Harmonisation Workstream, the
  enumeration exercise, and the Council's approved rates schedule. Rate-setting remains the
  Council's statutory prerogative.
- **Endpoint paths and payload field names for the bank integration are indicative.** They are
  aligned during the integration workstream against the collecting bank's published API
  specification.
- **Security is demonstration-grade in three specific places** — password hashing, session
  tokens, and transport. Section 7 of `docs/ARCHITECTURE.md` sets out the production
  requirement for each.
- **No cost figures appear anywhere in this build.** Costs are established through technical
  needs assessment and the Council's procurement processes.

---

*Alliance Consulting & Digital Solutions Ltd — 4th Floor, Yobe Investment House,
Plot 1352, Ralph Shodeinde Street, CBD, Abuja.*
