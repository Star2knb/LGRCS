# RevAc Application Suite — Solution Architecture

**Deployment:** Abuja Municipal Area Council (AMAC), Federal Capital Territory
**Lead Revenue Technology Consultant:** Alliance Consulting & Digital Solutions Ltd (ACDSL)
**Document status:** Technical companion to the AMAC Revenue Computerisation Proposal (July 2026)
**Date:** July 2026

---

## 1. Purpose and scope

This document describes the technical architecture of the RevAc (Revenue Administration &
Collection) Application Suite as deployed for one FCT Area Council — AMAC — covering the web
portal, the field-agent mobile application, the API backend, the database schema, and the
multi-channel e-payment integration layer.

The architecture implements the five programme components set out in the proposal:

| Component | Realised in this build as |
|---|---|
| 1 — RevAc Application Suite | Nine functional modules across web and mobile |
| 2 — HR training facilitation | Role-differentiated interfaces requiring minimal training |
| 3 — Harmonised chart of revenue | `revenue_category` / `revenue_item` / `rate_schedule` as enforced master data |
| 4 — Unified sub-consultants platform | Three access levels with per-portfolio row segregation |
| 5 — Global performance view | Consolidated dashboard across consultants, wards and channels |

> **Data caveat.** All revenue items, codes, rates, wards, sub-consultants, payers and
> transactions in the running build are illustrative demonstration data. They are placeholders
> pending the Harmonisation Workstream, the enumeration exercise, and the Council's approved
> rates schedule. Rate-setting remains the Council's statutory prerogative.

---

## 2. System context

```
                          ┌──────────────────────────────┐
   Ratepayers ───────────▶│  Public surfaces             │
   (no sign-in)           │  · Bill lookup               │
                          │  · Receipt verification (QR) │
                          │  · USSD menu                 │
                          └───────────────┬──────────────┘
                                          │
  Council staff ─────┐                    │
  Sub-consultants ───┼──▶ Web portal ─────┤
  Stakeholders ──────┘                    │
                                          ▼
  Field agents ─────────▶ Mobile PWA ─▶ ┌──────────────────┐      ┌──────────────────┐
  (offline capable)                      │  RevAc API      │◀────▶│ Collecting bank  │
                                         │  (application   │      │ e-channels       │
                                         │   services)     │      │ POS · OTC · IB/MB│
                                         └────────┬────────┘      │ USSD · agent net │
                                                  │               └──────────────────┘
                                                  ▼
                                         ┌──────────────────┐
                                         │  RevAc database  │
                                         │  24 tables       │
                                         │  3 reporting     │
                                         │  views           │
                                         └──────────────────┘
```

---

## 3. Layered architecture

### 3.1 Presentation layer

| Surface | Technology | Users | Key characteristic |
|---|---|---|---|
| Web portal | HTML5 / CSS / vanilla JS SPA | Council admin, sub-consultants, stakeholders | No build step; runs on modest Council hardware |
| Mobile field app | Progressive Web App (installable) | Field collection agents | Offline-capable with local queue and replay |
| Public surfaces | Same web stack, unauthenticated routes | Ratepayers | Bill lookup, QR receipt verification |
| USSD | Server-rendered menu over gateway callback | Ratepayers without smartphones | Stateless CON/END session protocol |

The mobile app is deliberately a PWA rather than a native binary: it installs from a URL with
no app-store dependency, updates centrally, and runs on the low-cost Android devices typical of
field deployments. Where a native wrapper is later required (for example to drive an integrated
card reader), the same API and offline queue are reused.

### 3.2 Application layer

The API is organised around the nine RevAc modules:

| # | Module | Principal endpoints |
|---|---|---|
| 1 | Taxpayer Enumeration & Registry | `/api/payers`, `/api/assets` |
| 2 | Assessment & e-Billing | `/api/bills` |
| 3 | Multi-Channel e-Payments | `/api/payments`, `/api/channels/{code}/webhook` |
| 4 | e-Receipting & Verification | `/api/receipts`, `/api/verify/{token}` |
| 5 | Field Agent Mobile | `/api/mobile/worklist`, `/api/mobile/sync` |
| 6 | Revenue Accounting & Reconciliation | `/api/reconciliation`, `/api/settlements` |
| 7 | Council Dashboard & Reports | `/api/dashboard/summary`, `/api/dashboard/global` |
| 8 | Debt Management & Enforcement | `/api/debt` |
| 9 | Security, Audit & Compliance | `/api/auth/*`, `/api/audit` |

**Single money-in path.** Every payment — whatever its origin — converges on one internal
function that posts the payment, updates the bill, issues the receipt, and closes any debt case.
POS, teller, transfer, USSD, agent banking, portal and mobile all use it. There is no second
route by which money can enter the system, which is what makes the reconciliation figures
trustworthy.

### 3.3 Data layer

24 tables in eleven functional groups (organisation, access control, chart of revenue, registry,
billing, payments, receipting, reconciliation, debt, field operations, API clients) plus three
reporting views. The reference DDL targets PostgreSQL 15+; the runnable build uses an
equivalent SQLite schema.

---

## 4. Multi-channel e-payment integration

### 4.1 Channels in scope

| Code | Channel | Mode | Identifying reference |
|---|---|---|---|
| `POS` | POS terminals deployed to the Council | Real-time webhook | Terminal ID + RRN |
| `OTC` | Over-the-counter teller payments at branches | End-of-day settlement file | Teller reference + branch code |
| `IB_MB` | Internet banking and mobile banking transfers | Real-time webhook | Session ID |
| `USSD` | USSD payment channel | Session callback + webhook | USSD reference + MSISDN |
| `FIRSTMONIE` | Agent banking network | Real-time webhook | Agent transaction reference + agent ID |

### 4.2 Adapter pattern

Each channel has an adapter implementing one contract — `validate`, `normalise`,
`verify_signature` — so the core platform stays channel-agnostic. Adding a sixth channel means
adding one adapter class, not changing the payment engine.

Every adapter converts its channel-specific payload into a canonical transaction record:
channel, bank reference, bill reference, amount, narration, value date, and where applicable
terminal, agent and payer MSISDN.

### 4.3 Integration controls

| Control | Mechanism |
|---|---|
| Authenticity | HMAC-SHA256 over the raw request body, `X-RevAc-Signature` header |
| Idempotency | Unique constraint on (channel, bank reference); a replay returns the original result and never double-posts |
| Validation | Required fields and a positive amount enforced before anything is written |
| Unknown bill reference | Credit recorded and routed to the exception queue rather than rejected — the money is never lost |
| Auditability | Full raw payload retained against every feed record |
| Reconciliation | Platform total vs bank feed total, per channel, per day, with exceptions itemised |

### 4.4 Payment flow

```
Bank e-channel
     │  POST /api/channels/{CODE}/webhook   (HMAC-signed)
     ▼
Signature check ──▶ Field validation ──▶ Idempotency check
     │                                          │
     │                              (duplicate) └──▶ return original result
     ▼
Record in channel_transaction_feed
     │
     ├── bill reference matches ──▶ post payment ──▶ update bill ──▶ issue receipt
     │                                                                     │
     │                                                        SMS + QR to ratepayer
     │
     └── no match ──▶ EXCEPTION ──▶ reconciliation exception queue
```

---

## 5. Access control and data segregation

Four access levels, enforced server-side on every request:

| Level | Sees | Cannot |
|---|---|---|
| `COUNCIL_ADMIN` | Everything across all portfolios | — |
| `CONSULTANT` | Only its own portfolio's payers, bills, payments, agents, settlements | See any other sub-consultant's data |
| `AGENT` | Only its assigned ward worklist and own collections | Access portal administration |
| `GLOBAL_VIEW` | Consolidated and comparative performance | Transact or administer |

Segregation is applied as a server-side predicate on the query, not as a filter in the browser.
A sub-consultant signing in and requesting the full bill list receives only its own rows.
This is verified in the test suite.

In the PostgreSQL deployment this is additionally enforced by row-level security policies keyed
on a session-scoped consultant identifier, so segregation holds even for direct database access.

---

## 6. Offline capability

Connectivity in outer wards is unreliable, so the field app assumes it will lose signal:

1. The app shell is cached by a service worker; the app opens without a network.
2. The agent's ward worklist is persisted locally at each sync.
3. A collection captured offline is written to a local queue and the ratepayer is given a
   queued reference immediately.
4. On reconnection the queue replays to `/api/mobile/sync`; the server applies each record
   through the same money-in path and returns accepted and conflicted client IDs.
5. Accepted records clear from the queue; conflicts are surfaced to the agent for resolution.

Records carry a device-side timestamp, so the audit trail preserves when a collection actually
happened, not merely when it reached the server.

---

## 7. Security and compliance posture

| Area | Position in this build | Production requirement |
|---|---|---|
| Password storage | SHA-256 (demonstration only) | Argon2id or bcrypt with per-user salt |
| Session tokens | In-memory bearer tokens | Signed JWT with short expiry and refresh rotation |
| Transport | Plain HTTP locally | TLS 1.3 only, HSTS enforced |
| KYC identifiers | NIN/BVN stored as one-way hash, never plaintext | Unchanged — this is the correct pattern |
| Audit trail | Append-only log of user, action, entity, IP, timestamp | Unchanged, with write-once storage |
| Maker-checker | Approval fields on assessments and settlements | Enforced workflow with segregation of duties |
| Data protection | Per-portfolio segregation, hashed identifiers, minimal collection | Full NDPA/NDPR programme: DPIA, retention schedule, breach procedure, DPO registration |
| Secrets | Environment variables | Managed secrets store or HSM |

The demonstration-grade items above are marked deliberately: they are the specific hardening
tasks for the production deployment, not oversights.

---

## 8. Deployment topology

**Recommended production topology**

- Cloud-hosted, Nigeria-resident data centre, per the Council's data-residency position
- Application tier: two or more API instances behind a load balancer
- Database: managed PostgreSQL with synchronous replica and point-in-time recovery
- Static surfaces: CDN-delivered web portal and PWA
- Integration tier: dedicated webhook receivers, rate-limited, IP-allowlisted to the bank
- Observability: centralised logs, uptime and reconciliation-variance alerting
- Backup: continuous WAL archiving plus daily snapshots, restore tested quarterly

**Data ownership.** The Council owns and controls its data. Each sub-consultant is confined to
its own portfolio. Exit of a sub-consultant does not remove Council data or continuity.

---

## 9. Non-functional targets

| Attribute | Target |
|---|---|
| Availability | 99.5%+ monthly, aligned to the proposal's 99%+ KPI |
| Webhook response | Under 500 ms at the 95th percentile |
| Portal page load | Under 2 s on a 3G connection |
| Offline endurance | 7 days of field capture without sync |
| Concurrent agents | 500+ per Area Council deployment |
| Reconciliation | Daily automated run per channel |

---

## 10. Extension to the remaining Area Councils

The build is single-Council by configuration, not by design. `council_id` is present on every
tenant-scoped table, and the harmonised chart of revenue is per-Council. Extending to Bwari,
Gwagwalada, Kuje, Kwali and Abaji requires configuration and onboarding — a new council record,
its wards, its harmonised chart of revenue, its sub-consultants and agents — rather than a
second codebase. The global performance view then generalises from Council-wide to
Territory-wide.

---

*Prepared by Alliance Consulting & Digital Solutions Ltd (ACDSL) — Lead Revenue Technology
Consultant. 4th Floor, Yobe Investment House, Plot 1352, Ralph Shodeinde Street, CBD, Abuja.*
