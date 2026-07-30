# RevAc — Revenue Administration & Collection

A unified revenue platform for Kuje Area Council (KAC), FCT, built by Alliance
Consulting & Digital Solutions Ltd (ACDSL). Covers enumeration through to
enforcement: payer registry, harmonised chart of revenue, assessment &
e-billing, multi-channel e-payments (POS, over-the-counter teller, internet &
mobile banking, USSD, FirstMonie agent banking), printable Harmonised Demand
Notices, e-receipting with QR verification, bank reconciliation, sub-consultant
commission settlement, and debt/enforcement tracking — with per-portfolio data
segregation across sub-consultants.

The harmonised chart of revenue (items and codes), the Gazette-derived rates,
and the Harmonised Demand Notice print format are drawn from Kuje Area
Council's actual revenue code list, Gazette, and January 2026 sample demand
notices — see [Note on data](#note-on-data) below.

## Structure

- **[backend/](backend/)** — Flask + SQLite API (`app.py`), e-channel payment
  adapters (`echannels.py`), schema (`schema.sql`) and demo data seed (`seed.py`).
- **[frontend/](frontend/)** — web portal for Council Admins, Sub-Consultants
  and Stakeholders (dashboards, payer registry, billing, reconciliation,
  settlements, debt management, audit log).
- **[mobile/](mobile/)** — offline-capable PWA for field collection agents
  (worklist, cash collection, payer enumeration, background sync).
- **[docs/](docs/)** — [architecture](docs/ARCHITECTURE.md),
  [API reference](docs/API_REFERENCE.md), and the source
  [reference documents](docs/reference/) (Gazette, revenue code list, demand
  notice template and a real sample) the harmonised chart and print format
  were built from.

## Running it locally

```bash
cd backend
python seed.py   # creates backend/revac.db with demo data
python app.py    # serves the API + web portal at http://127.0.0.1:8000
```

The web portal is served at `/`, the mobile field-agent app at `/m`.

Demo accounts (password `revac2026`):

| Username | Role |
|---|---|
| `admin` | Council Revenue Administrator — full access |
| `consultant1` | Northgate Revenue Services — own portfolio only |
| `stakeholder` | Council stakeholder — global performance view |
| `agent1`…`agent12` | Field collection agents — mobile app only |

## Deploying

The app needs a host that runs Python — it can't be served as static files
(GitHub Pages, etc.), since the frontend and mobile app call a live Flask API.

**[Render](https://render.com)** (recommended, has a free tier):
1. Push this repo to GitHub (already done if you're reading this there).
2. On Render: **New → Blueprint**, connect the repo. It reads
   [`render.yaml`](render.yaml) automatically — no manual config needed.
3. Deploy. Render builds with `backend/requirements.txt`, seeds the demo
   database, and starts the app bound to the `$PORT` it assigns.

**Railway** works the same way via the included [`Procfile`](Procfile) —
create a new project from the repo and it will detect and run it.

Either way, the demo database reseeds fresh on every restart, so it's not a
place to store real production data as-is.

## Note on data

The harmonised chart of revenue (item names and codes) is taken from the Kuje
Area Council Revenue Item/Revenue Code list; rates come from the KAC Gazette
where it gives a clean, single figure (e.g. tenement rate by property type,
contractor registration by category) and are otherwise a single illustrative
flat rate per item, since the Gazette's more granular tiers (e.g. liquor
licensing by premises size) aren't broken out on the demand notices Council
actually issues. Payers, wards' demo assignments, sub-consultants and all
transactions are **illustrative demonstration data** — not real ratepayer
records — pending the Harmonisation Workstream, the enumeration exercise, and
the Council's confirmed current rates schedule.
