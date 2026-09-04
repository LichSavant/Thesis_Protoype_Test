# Phishing Defense System

Working thesis prototype for the **SE-BRL: Modality-Aware Social Engineering Behavior Representation Architecture**.

The current system provides a tested vertical slice with preserved mock mode, a selected-message Gmail adapter, FastAPI backend, SQLite persistence, and a dashboard for tracked records.

The existing `/api/v1/analyze-email` endpoint uses transparent prototype rules. These outputs are kept separate from SE-BRL and are **not presented as trained machine-learning predictions**.

## Current progress

### Step 1 — Prototype Foundation: Complete

The following SE-BRL foundation components have been implemented:

- Canonical four-dimension hierarchy:
  - Pressure and Threat Cues
  - Lure and Attention Cues
  - Trust and Identity Manipulation
  - Requested Action and Consequence
- Twelve subordinate behavioral indicators
- Versioned canonical SE-BRL codebook
- Strict codebook and compatibility validation
- `supported`, `absent`, and `unavailable` evidence states
- Modality-aware support rules for:
  - Content-bearing email
  - Content-bearing webpage
  - Stand-alone URL
  - Engineered technical record
- Prevention of behavioral inference from bare URLs and technical-only records
- Deterministic dimension and component ordering
- Four-value assessment-availability mask
- Immutable modality-assessment results
- Fail-closed SE-BRL result envelope
- Strict Pydantic API response contract
- Domain-to-API response adapter
- Internal SE-BRL orchestration service
- Safe `not_evaluated`, `review_required`, and `failed` outcomes
- Sanitized domain, adapter, service, and response-validation failures
- Read-only SE-BRL status endpoint
- Automated tests covering the SE-BRL foundation and existing prototype

The SE-BRL foundation is intentionally isolated from the current rule-based analyzer.

## SE-BRL status endpoint

```http
GET /api/v1/se-brl/status
```

This endpoint exposes the current fail-closed status of the SE-BRL foundation for the `content_bearing_email` modality.

It currently returns:

- `overall_status: "not_evaluated"`
- `assessment_result: null`
- Canonically ordered components and reason codes
- Fixed, non-sensitive limitations

This is a readiness/status endpoint, not a phishing-analysis endpoint. It does not return behavioral predictions, probabilities, confidence values, calibrated risks, or model-generated evidence.

## Deferred research work

The following components require the manuscript-defined dataset and experimental phases and remain unimplemented:

- Dataset provenance and suitability audits
- Dataset preprocessing and attrition reporting
- Duplicate, leakage, and source-confounding checks
- Grouped development, calibration, and sealed-test partitions
- Frozen behavioral evidence-detection rules
- Email and webpage feature-extraction pipelines
- Model training and comparison
- Five-fold grouped cross-validation
- Probability calibration
- Low, Medium, and High risk thresholds
- Explainable evidence generation
- Completed SE-BRL analytical outputs
- Extension and dashboard SE-BRL integration
- Final sealed-test evaluation and performance reporting

Datasets will be used offline for auditing, training, calibration, and evaluation. They will not simply be stored inside the running prototype.

## Existing prototype components

- Gmail selected-message adapter
- Preserved mock mode
- Gmail extension popup and background worker
- FastAPI backend
- SQLite interaction and scan persistence
- Transparent rule-based prototype analyzer
- Tracked-email dashboard
- Scan-feedback recording
- Duplicate open-interaction prevention

## Run locally

Requires Node.js 20+ and Python 3.11+.

```powershell
npm install
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements-dev.txt
Copy-Item backend/.env.example backend/.env
```

Start the backend from the repository root:

```powershell
.venv\Scripts\uvicorn backend.app.main:app --reload --port 8000
```

Start the dashboard in another terminal:

```powershell
npm run dev:dashboard
```

Build the extension:

```powershell
npm run build:extension
```

In Chrome:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `apps/gmail-extension/dist`.

Mock mode remains the default.

To demonstrate the Gmail integration:

1. Reload Gmail after installing the extension.
2. Open one email message.
3. Choose **Current Gmail message** in the extension popup.
4. Click **Analyze Current Email**.
5. Refresh `http://localhost:5173` to view the tracked record.

Automatic tracking is explicitly opt-in.

## Verify

```powershell
npm run typecheck
npm test
.venv\Scripts\python -m pytest ml/tests
.venv\Scripts\python -m pytest backend/tests
npm run build
```

## Important limitations

- The existing email analyzer is rule-based.
- Rule-based results must not be described as ML predictions.
- No validated behavioral model is currently integrated.
- No probability calibrator or frozen risk thresholds are currently integrated.
- The SE-BRL codebook remains pre-freeze until the manuscript-required evidence protocol and dataset validation phases are completed.
- A missing assessment opportunity is represented as `unavailable`, never as `absent`.
- Stand-alone URLs and engineered technical records cannot produce SE-BRL behavioral findings.

## Project documentation

The local SQLite database is `database/phishing_defense.db` and is ignored by Git.

The equivalent Supabase schema is available at:

[database/migrations/001_email_open_vertical_slice.sql](database/migrations/001_email_open_vertical_slice.sql)

Additional documentation:

- [Architecture](docs/architecture.md)
- [Privacy and permissions](docs/privacy-and-permissions.md)
- [Gmail integration](docs/gmail-integration.md)
- [SE-BRL foundation](ml/README.md)
