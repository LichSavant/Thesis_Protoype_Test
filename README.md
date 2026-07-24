# Phishing Defense System

Working thesis vertical slice with preserved mock mode and a carefully isolated selected-message Gmail adapter. FastAPI stores open interactions in SQLite, `/api/v1/analyze-email` returns transparent prototype rules, and the dashboard displays tracked records. No result is presented as a trained ML prediction.

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

In Chrome, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `apps/gmail-extension/dist`. Mock mode remains the default. To demonstrate Gmail, reload Gmail after installation, open one message, choose **Current Gmail message** in the popup, and click **Analyze Current Email**. Automatic tracking is explicitly opt-in. Refresh the dashboard at `http://localhost:5173` to see the tracked record.

## Verify

```powershell
npm run typecheck
npm test
.venv\Scripts\python -m pytest backend/tests
npm run build
```

The local SQLite database is `database/phishing_defense.db` and is ignored by Git. The equivalent Supabase schema is [database/migrations/001_email_open_vertical_slice.sql](database/migrations/001_email_open_vertical_slice.sql). See [docs/architecture.md](docs/architecture.md), [privacy-and-permissions.md](docs/privacy-and-permissions.md), and [gmail-integration.md](docs/gmail-integration.md).
