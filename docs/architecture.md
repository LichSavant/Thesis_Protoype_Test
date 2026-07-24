# Architecture

```mermaid
flowchart LR
  Popup[Extension popup] --> Source{EmailSourceAdapter}
  Source --> Mock[MockEmailSourceAdapter]
  Source --> Gmail[GmailEmailSourceAdapter]
  Gmail --> Content[Selected-message content script]
  Popup --> Worker[MV3 service worker]
  Content --> Worker
  Worker --> Open[POST email-open]
  Worker --> Analyze[POST analyze-email v1.0]
  Open --> Interaction[EmailInteractionService]
  Interaction --> DB[(SQLite / future Supabase)]
  Analyze --> Interface[Analyzer interface]
  Interface --> Rules[RuleBasedAnalyzer]
  Dashboard[React dashboard] --> DBAPI[Tracked-email API]
  DBAPI --> DB
```

Gmail DOM assumptions are confined to `gmailSelectors.ts` and `GmailEmailSourceAdapter`. The popup, service worker, API client, and backend receive typed metadata and do not know Gmail selectors. Mock mode follows the same contracts and remains the automated-test default.

## Duplicate prevention

The content script debounces mutations by 600 ms and tracks each visible message ID once until another message is selected. FastAPI separately ignores the same user/message `email_open` within five seconds. Reopening later remains countable.

## Analysis pipeline

`Analyzer` currently resolves to `RuleBasedAnalyzer`. `/api/v1/analyze-email` accepts schema version `1.0` and returns behaviors, recommendation, risk, classification, and `modelVersion: null`. Future BRL, text/URL feature extractors, ML classifier, and explanation generator should be introduced behind this boundary. Rule-based results must never be called ML predictions.

See [gmail-integration.md](gmail-integration.md) for operational limitations.
