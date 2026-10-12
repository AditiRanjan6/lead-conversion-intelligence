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
`localhost` and `127.0.0.1` Vite origins on port 5173 and the deployed Render
frontend origin.

## Render deployment

The production frontend uses
`https://lead-conversion-intelligence.onrender.com` as its API origin unless
`VITE_API_BASE_URL` overrides it. In the Render frontend service, set
`VITE_API_BASE_URL` to that exact URL in the service's environment settings,
then redeploy so Vite includes it in the generated frontend assets.

The backend must allow the frontend origin
`https://lead-conversion-intelligence-1.onrender.com`. This origin is included
in the backend's default CORS allowlist. If the backend service already defines
`LEAD_CONVERSION_CORS_ORIGINS`, add the frontend origin to its comma-separated
value (alongside any other required origins), then redeploy/restart the backend.
After both services finish deploying, verify `/api/datasets` on the backend and
reload the frontend.

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

- `total_leads`: leads in the requested dataset that match the optional filters.
- `qualified_leads`: matching leads where `is_qualified = 1`.
- `converted_leads`: matching leads where `status = 'converted'`.
- `lost_leads`: matching leads where `status = 'lost'`.
- `conversion_rate`: converted matching leads / all matching leads × 100.
- `qualification_rate`: qualified matching leads / all matching leads × 100.
- `converted_deal_value`: sum of matching converted-lead `deal_value` values.

Both growth and funnel endpoints accept optional `stage`, `status`, `source`,
`qualified`, `date_from`, and `date_to` query parameters. Dates filter by the
lead's `created_at` date and are inclusive. Every rate uses the filtered result
set as its denominator; the funnel still returns each stage in a consistent
order, with non-matching/empty stages at zero.

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

The dashboard's shared filters apply to Growth Overview, Funnel Intelligence,
and Lead Explorer. When both date bounds are set, Growth Overview compares the
selected interval with an immediately preceding interval of equal length and
the same non-date filters. Comparison values are absolute changes; rate changes
are percentage-point differences. KPI definitions are available through the
info marker, and KPI links open matching lead records. The executive summary
uses only the filtered API response. Export report downloads those metrics,
current-stage counts, and returned data caveats as CSV.

Run the analytics tests or full suite with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -v tests\test_analytics.py
.\.venv\Scripts\python.exe -m pytest -v
```

## CSV import and dataset management

The Data Management page accepts UTF-8 CSV files up to 5 MB and 10,000
non-empty rows. Excel workbooks are not supported. Required fields are
`name`, `acquisition_source`, `campaign`, `created_at`, `stage`, `status`,
`is_qualified`, `assigned_owner`, and `last_activity_at`. Optional fields are
`lead_id`, `next_follow_up_at`, `converted_at`, and `deal_value`.

Example CSV (the example row is fictional):

```csv
lead_id,name,acquisition_source,campaign,created_at,stage,status,is_qualified,assigned_owner,last_activity_at,next_follow_up_at,converted_at,deal_value
,Example lead only,referral,Example campaign,2026-09-01T09:00:00Z,new,open,false,Example owner,2026-09-01T09:00:00Z,,,
```

Allowed sources are `paid_search`, `organic_search`, `referral`, `webinar`,
`partner`, and `outbound`. Stages and statuses use the values listed in the
lead schema above. Timestamps must be ISO 8601 with an explicit timezone.
`is_qualified` accepts `true`/`false`, `yes`/`no`, or `1`/`0`. Converted leads
must be at `closed_won` with a conversion timestamp and positive deal value;
lost leads must be `closed_lost`. The preview detects duplicates by an existing
`lead_id` or by a case-insensitive match on name, source, campaign, and
creation timestamp within the destination dataset. Rows with invalid fields
and duplicate rows are skipped; the user confirms the number imported before
the transaction writes valid rows and import history atomically. Imports append
to an existing imported dataset; there is no in-place replace operation.

Column names are matched automatically where possible and can be mapped in the
preview. Download the CSV template from Data Management. The template includes
one clearly fictional example row. Dataset names and lead counts are shown in
the dataset manager. Imported datasets can be renamed or deleted after
confirmation. The built-in `synthetic-demo` dataset cannot be deleted. Deleting
an imported dataset removes its leads and import history in one SQLite
transaction; this cannot be undone.

The database initializes the `import_history` table with
`CREATE TABLE IF NOT EXISTS`; existing lead and dataset tables are not rebuilt,
so no manual data migration is required.

## Lead explorer and exports

The Lead Explorer provides dataset-scoped search across lead ID, name,
campaign, and owner; filters for stage, status, source, owner, campaign, and
created-date range; supported-column sorting; and pagination. It supports
record details, create, edit, and confirmed delete. Export downloads all
records matching the current filters as UTF-8 CSV, confirms before exporting
more than 1,000 records, and refuses exports above 50,000 records. CSV cells
that could be interpreted as spreadsheet formulas are prefixed before export.

Supported lead API operations:

- `GET /api/leads?dataset_id=...` with `search`, `stage`, `status`, `source`,
  `owner`, `campaign`, `date_from`, `date_to`, `sort`, `direction`, `page`,
  and `page_size` query parameters.
- `GET /api/leads/{lead_id}?dataset_id=...` reads one lead in that dataset.
- `POST /api/leads?dataset_id=...`, `PUT /api/leads/{lead_id}?dataset_id=...`,
  and `DELETE /api/leads/{lead_id}?dataset_id=...` create, update, or delete
  individual records.

## Administrative access and security

Read-only dataset and analytics endpoints remain public. Dataset rename/delete,
CSV commit, and lead create/update/delete operations require the
`X-Admin-Token` request header. They fail closed with `503` when the backend
does not have `LEAD_CONVERSION_ADMIN_TOKEN`; a missing or incorrect request
token receives `401`. Set a long, randomly generated secret in the backend
environment. Never put this value in a `VITE_*` variable or frontend build.
The administrator enters it into the Data Management or Lead Explorer page;
the app holds it in page memory only and does not persist it. Configure CORS to
allow only origins you trust, including the frontend origin.

This is a shared-token gate, not user accounts, per-user authorization, or
tenant isolation. Anyone who obtains the token can mutate all datasets. Use
TLS, restrict access to the secret, rotate it if exposed, and add proper
authentication, authorization, audit controls, and rate limiting before
offering public multi-user or customer use. A trusted frontend origin does not
replace authentication.

## Analytics definitions and remaining scope

Growth Overview reports metrics for the selected dataset and shared filters:

- Qualified leads are records with `is_qualified = true`.
- Converted leads are records with `status = converted`.
- Conversion rate is converted leads divided by all matching leads.
- Qualification rate is qualified leads divided by all matching leads.
- Converted deal value is the sum of recorded deal values for converted leads.
- Funnel shares are current-stage counts divided by all leads; they are not
  historical stage transition rates.

The lead schema has no email address, currency code, loss reason, or
stage-transition events. Duplicate matching therefore uses the documented
composite fields rather than email. Deal-value currency is unspecified.
Current stage cannot reconstruct historical funnel movements or exact
drop-off counts.

The dashboard also provides shared filters, equal-length previous-period
comparisons, KPI definitions and drilldowns, a deterministic executive summary,
and CSV report export. Excel import/export, AI-generated analysis, PDF reports,
predictive scoring, and individual user accounts are not implemented. The
dashboard remains an analytics demonstration, not an authenticated,
multi-tenant CRM.

## Render storage and environment

On Render, configure:

- Frontend build-time `VITE_API_BASE_URL=https://lead-conversion-intelligence.onrender.com`
- Backend `LEAD_CONVERSION_ADMIN_TOKEN` to a secure random secret before
  enabling import or record changes
- Backend `LEAD_CONVERSION_CORS_ORIGINS` to a comma-separated allowlist of
  exact frontend origins; do not use `*`
- Backend `LEAD_CONVERSION_DB_PATH` to a location on a mounted persistent disk
  if imported business data must survive service restarts/redeploys

SQLite on a Render ephemeral filesystem can be lost when the service is
restarted or redeployed. A local SQLite file is suitable for a single-instance
demonstration, not horizontal scaling or concurrent multi-user production use.
Set up and verify a persistent disk (or migrate to a managed database) before
importing valuable records. Redeploy the frontend after changing
`VITE_API_BASE_URL`; it is embedded into the Vite build.

## Current implementation and verification

Implemented features include dataset-isolated Growth Overview and current-stage
funnel analytics with shared filters, previous-period comparison, KPI
definitions/drilldowns, an executive summary and CSV report export; a
deterministic fictional 120-lead demo dataset; responsive React/Vite pages; CSV
preview/mapping/import with row validation, duplicate detection, size limits,
and import history; dataset counts, rename and protected deletion; and a
searchable, filterable, sortable, paginated lead explorer with token-gated CRUD
and filtered CSV export.

Run backend and frontend tests/checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

## Manual end-to-end checklist

1. Start the API and Vite servers using the setup instructions above.
2. Confirm the demo dataset is labelled synthetic and its lead count is derived
   from the API.
3. Open Funnel Intelligence, select a stage, and verify the lead explorer is
   filtered to that current stage.
4. Download the CSV template; import a copy with one valid and one invalid row
   and verify the preview counts and row-specific validation message.
5. Set the backend admin token in the UI, confirm import, then verify the new
   dataset count, import history, and lead rows.
6. Search and filter those leads, change pages, export the filtered CSV, and
   confirm spreadsheet-formula-like values are escaped.
7. Create, edit, and delete a lead; verify the record is scoped to the selected
   dataset and that protected demo deletion is rejected.
8. Restart the backend and verify persistence only when using the same durable
   SQLite path; on Render, confirm the mounted persistent disk is active.