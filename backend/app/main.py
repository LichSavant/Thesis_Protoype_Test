from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .analyzers import RuleBasedAnalyzer
from .repository import TrackedEmailRepository
from .schemas import AnalyzeEmailRequest, AnalyzeEmailResponse, EmailOpenRequest, EmailScanResponse, HealthResponse, ScanFeedbackRequest, TrackedEmailResponse
from .services import EmailInteractionService

settings = get_settings()
repository = TrackedEmailRepository(settings.database_url)
service = EmailInteractionService(repository, settings.email_open_deduplication_seconds)
analyzer = RuleBasedAnalyzer()

app = FastAPI(title="Phishing Defense API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"chrome-extension://[a-p]{32}" if settings.app_env == "development" else None,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse, include_in_schema=False)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", persistence="sqlite-local-development", deduplication_window_seconds=settings.email_open_deduplication_seconds
    )


@app.post("/api/v1/interactions/email-open", response_model=TrackedEmailResponse)
def record_email_open(request: EmailOpenRequest) -> TrackedEmailResponse:
    return service.record_open(request)


@app.post("/api/v1/analyze-email", response_model=EmailScanResponse)
def analyze_email(request: AnalyzeEmailRequest) -> EmailScanResponse:
    result = analyzer.analyze(request)
    return repository.record_scan(result, request)


@app.post("/api/v1/scan-feedback")
def record_scan_feedback(request: ScanFeedbackRequest) -> dict[str, bool]:
    if not repository.record_feedback(request):
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"ok": True}


@app.get("/api/v1/email-scans/{scan_id}", response_model=EmailScanResponse)
def get_email_scan(scan_id: str) -> EmailScanResponse:
    result = repository.get_scan(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return result


@app.get("/api/v1/email-scans", response_model=list[EmailScanResponse])
def list_email_scans() -> list[EmailScanResponse]:
    return repository.list_scans()


@app.get("/api/v1/tracked-emails", response_model=list[TrackedEmailResponse])
def list_tracked_emails() -> list[TrackedEmailResponse]:
    return repository.list_tracked_emails()


@app.get("/api/v1/tracked-emails/{message_id}", response_model=TrackedEmailResponse)
def get_tracked_email(message_id: str) -> TrackedEmailResponse:
    tracked = repository.get_tracked_email(message_id)
    if tracked is None:
        raise HTTPException(status_code=404, detail="Tracked email not found")
    return tracked
