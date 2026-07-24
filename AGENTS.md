# Repository instructions

## Purpose and architecture

This undergraduate thesis prototype is a human-centered, multi-layer phishing-defense system. The Chrome extension observes permitted Gmail message-view events and user interactions, the FastAPI backend validates and stores events and exposes APIs, Supabase PostgreSQL provides persistence, the React dashboard presents email- and user-level indicators, and `ml/` will later contain the Behavior Representation Layer and trained classifier. Shared wire contracts live in `packages/shared`.

Data flows from extension -> backend -> database -> dashboard. Future ML analysis runs server-side; never put privileged database credentials or model secrets in a browser client.

## Metrics must remain separate

- **Email Risk Score** describes how suspicious one email is, based on message/sender/URL features, behavioral tactics, rules, and eventually model output.
- **Visit Count** is only the number of times that message was viewed. It must never directly determine whether an email is phishing.
- **User Susceptibility Index** is a separate user-level behavioral indicator derived from interactions with risky messages. Reopening has at most a small, explainable influence because a user may be investigating or reporting the message.

Never name a visit count `risk`, combine these concepts into one field, or present one as a proxy for another.

## Conventions

- `apps/gmail-extension`: Manifest V3 extension. Keep permissions minimal and document additions.
- `apps/web-dashboard`: React/Vite dashboard.
- `backend/app`: FastAPI routes, schemas, configuration, and services. Python modules and functions use `snake_case`.
- `database`: migrations/schema and database documentation.
- `ml`: future Python ML/behavior representation code; no browser-side ML secrets.
- `packages/shared`: browser-safe TypeScript request/response types. TypeScript symbols use `camelCase` and React components use `PascalCase`.
- `docs`: architecture, privacy, protocol, and research documentation.

Inspect existing code and local instructions before replacing files. Preserve working functionality and prefer focused changes over rewrites. Do not delete or overwrite user work without explicit approval.

All email sources implement `EmailSourceAdapter`. Gmail selectors may exist only in `adapters/gmailSelectors.ts`; popup, API, and background code must never depend on Gmail DOM details. Preserve mock mode for tests and demonstrations. Automatic Gmail tracking must remain user-disableable, selected-message-only, debounced, and duplicate-safe.

## Privacy and security

Collect only data necessary for the stated feature. Never collect or store passwords, authentication tokens, attachments, personal credentials, or Gmail session material. Do not transmit a full email body unless a specific analysis feature requires it and the user explicitly authorized it. Prefer message identifier, sender address/domain, subject, timestamps, extracted URLs, and derived behavioral features. Sanitize and validate every external input. Keep Supabase service-role keys and other secrets in backend-only environment variables. Use narrowly scoped CORS origins and extension permissions in development and production.

Link extraction is opt-in. Email-body extraction is disabled by default and requires an explicit setting, documented study purpose, and `bodyCollectionAuthorized=true`; never infer authorization from Gmail access alone.

## Research integrity

Do not fabricate ML accuracy, predictions, experimental results, evaluation metrics, or research findings. Clearly label every result as **mock**, **rule-based**, or **model-generated**. Until a validated model is integrated, UI risk values must be marked mock or rule-based and must not claim to be real phishing predictions.

## Commands

From the repository root:

- Install JS dependencies: `npm install`
- Run dashboard: `npm run dev:dashboard`
- Run extension watcher: `npm run dev:extension`
- Build/type-check JS workspaces: `npm run build` and `npm run typecheck`
- Run configured static lint check: `npm run lint` (strict TypeScript checking)
- Test dashboard and extension: `npm test`
- Install backend: `python -m venv .venv`, then `.venv\\Scripts\\pip install -r backend/requirements-dev.txt` on Windows
- Run backend: `.venv\\Scripts\\uvicorn backend.app.main:app --reload --port 8000`
- Test backend: `.venv\\Scripts\\python -m pytest backend/tests`

The first vertical slice uses local SQLite via `DATABASE_URL` and mirrors its tables in `database/migrations/001_email_open_vertical_slice.sql` for later Supabase deployment. Email-open events within five seconds for the same user/message are deduplicated; later reopens increment `visit_count`.

Run relevant tests, type checks, and builds after every change. Report commands and results honestly.
