# RevAc API Reference

Base URL (local): `http://127.0.0.1:8000`
Authentication: `Authorization: Bearer <token>` from `/api/auth/login`, except where marked **Public**.

---

## Authentication

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | Public | Exchange credentials for a bearer token |
| POST | `/api/auth/logout` | Any | Invalidate the token |
| GET | `/api/auth/me` | Any | Current user and access level |

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"revac2026"}'
```

---

## Dashboard

| Method | Path | Access |
|---|---|---|
| GET | `/api/dashboard/summary` | Any (scoped to the caller's portfolio) |
| GET | `/api/dashboard/global` | Council admin, global view |

---

## Enumeration & registry

| Method | Path | Access | Notes |
|---|---|---|---|
| GET | `/api/payers?q=` | Any | Search by name, reference or phone |
| POST | `/api/payers` | Admin, consultant, agent | Returns **409** with `duplicate_of` when the phone already exists; resend with `"force": true` to override |
| GET | `/api/payers/{id}` | Any | Payer with assets and bills |
| POST | `/api/assets` | Admin, consultant, agent | Attach premises, shop, kiosk or signage |

---

## Chart of revenue

| Method | Path | Access |
|---|---|---|
| GET | `/api/revenue-items` | Any — includes the current approved rate |
| GET | `/api/revenue-categories` | Any |
| GET | `/api/wards` | Any |

---

## Assessment & billing

| Method | Path | Access |
|---|---|---|
| GET | `/api/bills?status=` | Any (portfolio-scoped) |
| POST | `/api/bills` | Admin, consultant, agent |
| GET | `/api/bills/{bill_ref}` | **Public** — citizen bill lookup |

```json
POST /api/bills
{
  "payer_id": 42,
  "due_date": "2026-08-31",
  "lines": [
    { "revenue_item_id": 3, "quantity": 1 },
    { "revenue_item_id": 8, "quantity": 2 }
  ]
}
```

Assessment and billing happen in one transaction: each line creates an `assessment` row priced
from the current `rate_schedule`, then a `bill_line` linking it to the bill.

---

## Payments & receipting

| Method | Path | Access |
|---|---|---|
| GET | `/api/payments` | Any |
| POST | `/api/payments` | Admin, consultant, agent |
| GET | `/api/receipts` | Any |
| GET | `/api/verify/{qr_token}` | **Public** — QR / SMS receipt verification |

---

## e-Channel integration

### Channel catalogue

| Method | Path | Access |
|---|---|---|
| GET | `/api/channels` | **Public** — codes, modes and required fields |

### Webhook — all real-time channels

```
POST /api/channels/{CODE}/webhook
Header: X-RevAc-Signature: <HMAC-SHA256 hex of the raw body>
```

`{CODE}` is one of `POS`, `OTC`, `IB_MB`, `USSD`, `FIRSTMONIE`.

**Required fields per channel**

| Channel | Required fields |
|---|---|
| `POS` | `terminalId`, `rrn`, `amount`, `billRef` — set `amountInKobo: true` if the amount is in kobo |
| `OTC` | `tellerRef`, `branchCode`, `amount`, `billRef` |
| `IB_MB` | `sessionId`, `amount`, `billRef` |
| `USSD` | `ussdRef`, `msisdn`, `amount`, `billRef` |
| `FIRSTMONIE` | `agentTxnRef`, `agentId`, `amount`, `billRef` |

**Responses**

| HTTP | `status` | Meaning |
|---|---|---|
| 201 | `posted` | Payment applied, receipt issued; response carries `paymentRef`, `receiptRef`, `verifyToken` |
| 200 | `duplicate` | Reference already received — no double-post |
| 202 | `accepted_unmatched` | Credit recorded, no bill matches; held in the exception queue |
| 400 | `rejected` | Validation failed; `error` explains what |
| 401 | — | Signature verification failed (when strict mode is on) |

```bash
curl -X POST http://127.0.0.1:8000/api/channels/POS/webhook \
  -H 'Content-Type: application/json' \
  -d '{"terminalId":"20481123","rrn":"RRN12345","amount":25000,"billRef":"AMAC/2026/000001"}'
```

### Teller settlement file

```
POST /api/channels/OTC/settlement
Body: JSON array of settlement rows
```

Returns `posted`, `duplicates_skipped`, and an itemised `exceptions` array. Safe to re-send —
already-received references are skipped, not re-posted.

### USSD session callback

```
POST /api/channels/USSD/session
{ "text": "1*AMAC/2026/000001*5000", "msisdn": "08031234567" }
```

Replies `CON …` to continue the session or `END …` to close it. Menu: 1 pay a bill,
2 check balance, 3 verify a receipt.

---

## Reconciliation & settlement

| Method | Path | Access |
|---|---|---|
| GET | `/api/reconciliation` | Admin, consultant |
| POST | `/api/reconciliation/run` | Admin — body `{"date":"YYYY-MM-DD"}` |
| GET | `/api/settlements` | Admin, consultant (own only) |
| POST | `/api/settlements/compute` | Admin — body `{"period_start","period_end"}` |

---

## Debt & enforcement

| Method | Path | Access |
|---|---|---|
| GET | `/api/debt` | Admin, consultant |
| POST | `/api/debt/refresh` | Admin — re-ages overdue bills and opens cases |
| POST | `/api/debt/{id}/escalate` | Admin — advances the enforcement stage |

Enforcement ladder: `NONE → FIRST_NOTICE → FINAL_NOTICE → ENFORCEMENT → LEGAL → CLOSED`.
A case closes automatically when its bill is settled in full.

---

## Oversight

| Method | Path | Access |
|---|---|---|
| GET | `/api/consultants` | Admin, global view |
| POST | `/api/consultants/{id}/status` | Admin — onboard, suspend, reinstate, exit |
| GET | `/api/agents` | Admin, consultant (own only) |
| GET | `/api/terminals` | Admin, consultant |
| GET | `/api/audit` | Admin |

---

## Mobile field agent

| Method | Path | Access |
|---|---|---|
| GET | `/api/mobile/worklist` | Agent — assigned ward, outstanding balances, today's tally |
| POST | `/api/mobile/sync` | Agent — replay the offline queue |

```json
POST /api/mobile/sync
{
  "records": [
    { "client_id": "c1",
      "entity_type": "PAYMENT",
      "device_created_at": "2026-07-28T09:00:00",
      "payload": { "bill_id": 11, "amount": 3500, "channel_code": "POS",
                   "geo": { "lat": 9.05, "lng": 7.49 } } }
  ]
}
```

Returns `accepted` (client IDs to clear from the queue) and `conflicts` (with reasons).

---

## Error format

```json
{ "error": "Plain-language description of what went wrong" }
```

| Code | Meaning |
|---|---|
| 400 | The request was malformed or failed validation |
| 401 | No valid token, or signature verification failed |
| 403 | The caller's role does not permit this action |
| 404 | The record does not exist |
| 409 | Conflict — most commonly a suspected duplicate payer |
