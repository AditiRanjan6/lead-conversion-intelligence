# Lead Conversion Intelligence

Lead Conversion Intelligence pairs a dataset-isolated FastAPI and SQLite
backend with a responsive React/Vite dashboard for growth and funnel analytics.

## Prerequisites

- Windows with PowerShell
- Python 3.13
- Node.js 20.19+ or 22.13+ (with npm)
- Git

The project uses Python's built-in `sqlite3` module. Dependencies are listed in
`requirements.txt`.

## Set up the Python environment

From the project root, create a virtual environment and install the backend
dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use the environment's interpreter
directly instead:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

To install or refresh project dependencies when needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## Start the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Start the frontend

In a second PowerShell terminal, install the locked frontend dependencies and
start the Vite development server:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Keep the API running at
`http://127.0.0.1:8000`; Vite proxies `/api` requests to it during development.
For a different local API port, set `VITE_API_PROXY_TARGET` before starting
Vite (for example, `$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8123"`).
The frontend uses the dataset registry and analytics API responses directly.
The dataset selector scopes each request explicitly and does not change the
backend's active-dataset selection. Set `VITE_API_BASE_URL` at build time when
the built frontend must call an API at a different origin. Configure the API's
`LEAD_CONVERSION_CORS_ORIGINS` environment variable as a comma-separated list
of allowed frontend origins. Without that setting, the API allows the
`localhost` and `127.0.0.1` Vite origins on port 5173.

Create and preview the production build with:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm run build
npm audit
npm run preview
```

The API health endpoint is available at `http://127.0.0.1:8000/api/health`.
The SQLite database defaults to `data/lead_conversion.sqlite3`. Set
`LEAD_CONVERSION_DB_PATH` to use a different location:

```powershell
$env:LEAD_CONVERSION_DB_PATH = "C:\path\to\lead_conversion.sqlite3"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Dataset registry API

Application startup idempotently registers the `synthetic-demo` dataset
(`Synthetic Demo Dataset`) and seeds its deterministic demo leads without
selecting it. Dataset selection is always explicit.

- `GET /api/datasets` lists registered datasets and their ID, name, type,
  active/inactive status, and creation time.
- `GET /api/datasets/active` returns the current selection, or
  `{"active_dataset": null}` when none has been selected.
- `PUT /api/datasets/active` selects a registered dataset using a JSON body
  such as `{"dataset_id": "synthetic-demo"}`. Unknown IDs return `404`;
  malformed IDs return `422`. Neither error changes the current selection.

## Lead data model and synthetic dataset

The `leads` table references the dataset registry with a foreign key. Its
dataset-scoped indexes cover creation time, stage, acquisition source, last
activity, next follow-up, and conversion time. UTC timestamps use
`YYYY-MM-DDTHH:MM:SSZ`. Database checks restrict acquisition source to
`paid_search`, `organic_search`, `referral`, `webinar`, `partner`, or `outbound`;
pipeline stage to `new`, `contacted`, `qualified`, `proposal`, `negotiation`,
`closed_won`, or `closed_lost`; and status to `open`, `converted`, or `lost`.
Qualification is stored as a boolean (`is_qualified`); assigned owners are
`Demo Owner A` through `Demo Owner D`. Campaigns are selected from these
source-specific demo values:

- Paid search: `Demo Search - Brand`, `Demo Search - Industry`,
  `Demo Search - General`
- Organic search: `Demo SEO - Product Guide`, `Demo SEO - Comparison Pages`
- Referral: `Demo Referral - Customer Network`,
  `Demo Referral - Advisor Network`
- Webinar: `Demo Webinar - Operations`, `Demo Webinar - Growth`
- Partner: `Demo Partner - Integration`, `Demo Partner - Reseller`
- Outbound: `Demo Outbound - Mid-Market`, `Demo Outbound - Enterprise`

Converted leads must be `closed_won` and have a conversion timestamp and
positive deal value. Lost leads must be `closed_lost`; open and lost leads have
no conversion timestamp or deal value.

Startup seeds 120 records only into the registered `synthetic-demo` dataset.
Generation uses Python `random.Random` seed `20261011`, a fixed UTC reference
time of `2026-10-11T12:00:00Z`, and stable IDs `synthetic-demo-0001` through
`synthetic-demo-0120`. Names are clearly fictional (`Demo Lead NNNN`), and
owners are labeled `Demo Owner`. Creation times vary over the preceding 365
days; sources are chosen uniformly at random, with campaigns drawn from
source-specific demo campaign names. Outcome-stage weights are new 18%,
contacted 18%, qualified 19%, proposal 15%, negotiation 10%, converted 13%,
and lost 7%.
Open leads have a follow-up date with 72% probability, 1-45 days after the
reference time. Converted leads receive a timestamp between creation and the
reference time and a positive deal value. A fixed seed and reference time keep
generated records reproducible; insert-on-conflict behavior preserves any
existing records.

Lead retrieval and counts are available through the service layer and require
an explicitly supplied, registered dataset ID. They always constrain the SQL
query to that dataset; there is no fallback to the active dataset.

## Phase 3: Growth Overview

The Growth Overview endpoint calculates SQL-aggregated metrics for exactly
one explicitly requested, registered dataset. It does not use or change the
active dataset and does not modify or seed leads.

```http
GET /api/analytics/growth?dataset_id=synthetic-demo
```

Metric definitions:

- `total_leads`: all leads in the requested dataset.
- `qualified_leads`: leads where `is_qualified = 1`.
- `converted_leads`: leads where `status = 'converted'`.
- `lost_leads`: leads where `status = 'lost'`.
- `conversion_rate`: converted leads / total leads × 100.
- `qualification_rate`: qualified leads / total leads × 100.
- `converted_deal_value`: sum of `deal_value` for converted leads only.

Rates and deal value are rounded to two decimal places. For a registered
dataset with no leads, counts, rates, and deal value are all zero. The
`dataset_id` query parameter is required; missing, blank, or malformed IDs
return `422`, while unregistered IDs return `404`.

Example request against a locally running server:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/analytics/growth?dataset_id=synthetic-demo"
```

Illustrative response only (the actual values are calculated from the
requested dataset):

```json
{
  "total_leads": 120,
  "qualified_leads": 75,
  "converted_leads": 24,
  "lost_leads": 18,
  "conversion_rate": 20.0,
  "qualification_rate": 62.5,
  "converted_deal_value": 184500.0
}
```

## Phase 4: Funnel & Drop-off Intelligence

The funnel endpoint returns a current-stage snapshot for exactly one
explicitly requested, registered dataset:

```http
GET /api/analytics/funnel?dataset_id=synthetic-demo
```

Example request against a locally running server:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/analytics/funnel?dataset_id=synthetic-demo"
```

The typed response includes the dataset ID and total lead count, plus:

- `stage_distribution`: counts and percentages for every stage in pipeline
  order, including stages with no leads.
- `funnel`: the same stage counts in the same order; each percentage is the
  stage count divided by all leads in the requested dataset, not a
  stage-to-stage conversion rate.
- `loss_analysis.total_lost_leads`: leads whose recorded status is `lost`.
- `loss_analysis.loss_rate`: lost leads divided by all leads in the dataset.
- `loss_analysis.leads_by_stage`: lost-lead counts grouped by recorded current
  stage, including zero-count stages; each percentage is of all lost leads.
- `data_limitations`: explicit caveats returned with every response.

All percentages are rounded to two decimal places. A registered dataset with
no leads returns zero counts and percentages. As with Growth Overview,
`dataset_id` is mandatory: missing, blank, or malformed IDs return `422`, and
unregistered IDs return `404`. Analytics never uses or changes the active
dataset and does not write to leads.

The lead schema stores only each lead's current stage. Consequently, this
endpoint cannot reliably reconstruct historical stage transitions or exact
drop-off counts; the current-stage percentages must not be interpreted as
historical step conversion rates. The schema also does not record loss reasons,
so none are inferred or reported.

Run the analytics tests or full suite with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -v tests\test_analytics.py
.\.venv\Scripts\python.exe -m pytest -v
```

## Implemented scope through Phase 4

Implemented:

- FastAPI app entry point, database initialization at startup, and health check
- Idempotent SQLite schema for dataset registry and application settings
- Synthetic demo dataset registration, registry listing, and explicit
  active-dataset API for `synthetic` and `real` datasets; no dataset is selected
  automatically
- Lead model and constrained SQLite table, including dataset-scoped indexes
- Deterministic, idempotent synthetic lead seeding and explicitly scoped
  retrieval/count services
- SQL-aggregated Growth Overview metrics and a dataset-explicit API endpoint
- Dataset-scoped current-stage funnel and loss metrics, with typed response
  schemas and documented historical-data limitations
- Responsive React/Vite dashboard with live, dataset-scoped Growth Overview
  and Funnel Intelligence pages, loading/error/empty states, and creator links
- Vite development proxy and configurable FastAPI CORS allowlist for
  frontend/API communication
- Temporary-path tests for database initialization, transactions, cleanup,
  dataset management, lead isolation, synthetic seeding, analytics metrics,
  and API behavior

Not yet implemented:

- CSV import, upload, or export
- Conversion scoring or predictive machine learning
- Destructive dataset reset or deletion
- External services or integrations