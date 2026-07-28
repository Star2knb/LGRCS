# RevAc — Revenue Administration & Collection

A unified revenue platform for the Abuja Municipal Area Council (AMAC), built by
Alliance Consulting & Digital Solutions Ltd (ACDSL). Covers enumeration through
to enforcement: payer registry, harmonised chart of revenue, assessment &
e-billing, multi-channel e-payments (POS, over-the-counter teller, internet &
mobile banking, USSD, FirstMonie agent banking), e-receipting with QR
verification, bank reconciliation, sub-consultant commission settlement, and
debt/enforcement tracking — with per-portfolio data segregation across
sub-consultants.

## Structure

- **[backend/](backend/)** — Flask + SQLite API (`app.py`), e-channel payment
  adapters (`echannels.py`), schema (`schema.sql`) and demo data seed (`seed.py`).
- **[frontend/](frontend/)** — web portal for Council Admins, Sub-Consultants
  and Stakeholders (dashboards, payer registry, billing, reconciliation,
  settlements, debt management, audit log).
- **[mobile/](mobile/)** — offline-capable PWA for field collection agents
  (worklist, cash collection, payer enumeration, background sync).
- **[docs/](docs/)** — [architecture](docs/ARCHITECTURE.md) and
  [API reference](docs/API_REFERENCE.md).

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

Revenue items, rates, wards, sub-consultants and all transactions in the seed
data are **illustrative demonstration data**, pending the Harmonisation
Workstream (Component 3), the enumeration exercise, and the Council's approved
rates schedule.
