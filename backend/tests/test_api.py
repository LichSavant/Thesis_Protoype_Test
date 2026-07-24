from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.repository import TrackedEmailRepository
from backend.app.services import EmailInteractionService
from backend.app.analyzers import RuleBasedAnalyzer
from backend.app.schemas import AnalysisRiskLevel


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from backend.app import main

    repository = TrackedEmailRepository(f"sqlite:///{tmp_path / 'test.db'}")
    service = EmailInteractionService(repository, deduplication_seconds=5)
    monkeypatch.setattr(main, "repository", repository)
    monkeypatch.setattr(main, "service", service)
    with TestClient(app) as test_client:
        yield test_client


def payload(opened_at: str = "2026-01-01T00:00:00Z") -> dict[str, str]:
    return {
        "userId": "demo-user-001", "messageId": "demo-message-001",
        "senderEmail": "unknown@example.com", "senderName": "Unknown Sender",
        "subject": "Verify your account immediately", "openedAt": opened_at,
    }


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["deduplicationWindowSeconds"] == 5


def test_first_open_creates_record_with_rule_based_score(client: TestClient) -> None:
    result = client.post("/api/v1/interactions/email-open", json=payload())
    assert result.status_code == 200
    assert result.json()["visitCount"] == 1
    assert result.json()["emailRiskScore"] == 75
    assert result.json()["scoreSource"] == "mock-rule-based"


def test_later_reopen_increments_visit_count(client: TestClient) -> None:
    client.post("/api/v1/interactions/email-open", json=payload())
    result = client.post("/api/v1/interactions/email-open", json=payload("2026-01-01T00:00:06Z"))
    assert result.json()["visitCount"] == 2


def test_rapid_duplicate_is_deduplicated(client: TestClient) -> None:
    client.post("/api/v1/interactions/email-open", json=payload())
    result = client.post("/api/v1/interactions/email-open", json=payload("2026-01-01T00:00:02Z"))
    assert result.json()["visitCount"] == 1


def test_tracked_email_endpoints_return_records(client: TestClient) -> None:
    client.post("/api/v1/interactions/email-open", json=payload())
    records = client.get("/api/v1/tracked-emails")
    assert records.status_code == 200
    assert records.json()[0]["messageId"] == "demo-message-001"
    assert client.get("/api/v1/tracked-emails/demo-message-001").json()["senderEmail"] == "unknown@example.com"


def test_invalid_request_is_rejected(client: TestClient) -> None:
    invalid = payload()
    invalid["senderEmail"] = "not-an-email"
    assert client.post("/api/v1/interactions/email-open", json=invalid).status_code == 422


def analysis_payload() -> dict:
    return {
        "schemaVersion": "1.0", "messageId": "analysis-message-1", "senderEmail": "security@unrelated-example.com",
        "senderName": "Microsoft Security", "senderDomain": "unrelated-example.com",
        "subject": "Urgent: verify your Microsoft account immediately", "openedAt": "2026-01-01T00:00:00Z",
        "links": ["http://192.0.2.10/login"], "bodyCollectionAuthorized": False,
    }


def test_rule_analyzer_detects_behaviors_and_labels_source(client: TestClient) -> None:
    response = client.post("/api/v1/analyze-email", json=analysis_payload())
    assert response.status_code == 200
    result = response.json()
    assert result["scoreSource"] == "rule-based"
    assert result["modelVersion"] is None
    assert result["phishingProbability"] is None
    assert result["subject"] == analysis_payload()["subject"]
    assert result["technicalIndicators"]
    types = {item["type"] for item in result["detectedBehaviors"]}
    assert {"urgency", "credential_request", "sender_domain_mismatch", "suspicious_url"} <= types


def test_scan_can_be_listed_loaded_and_feedback_is_idempotent(client: TestClient) -> None:
    from backend.app import main
    scan = client.post("/api/v1/analyze-email", json=analysis_payload()).json()
    scan_id = scan["scanId"]
    assert client.get(f"/api/v1/email-scans/{scan_id}").json()["senderEmail"] == "security@unrelated-example.com"
    feedback = {"scanId": scan_id, "messageId": scan["messageId"], "action": "reported_suspicious", "createdAt": "2026-01-01T00:01:00Z"}
    assert client.post("/api/v1/scan-feedback", json=feedback).status_code == 200
    assert client.post("/api/v1/scan-feedback", json=feedback).status_code == 200
    assert client.get("/api/v1/email-scans").json()[0]["userReported"] is True
    with main.repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM scan_feedback WHERE scan_id = ? AND action = ?", (scan_id, "reported_suspicious")).fetchone()[0] == 1


def test_missing_scan_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/email-scans/not-found").status_code == 404
    feedback = {"scanId": "not-found", "messageId": "missing", "action": "reported_suspicious", "createdAt": "2026-01-01T00:01:00Z"}
    assert client.post("/api/v1/scan-feedback", json=feedback).status_code == 404


def test_mock_analysis_preserves_demo_score(client: TestClient) -> None:
    request = analysis_payload()
    request.update({"senderEmail": "unknown@example.com", "senderName": "Unknown Sender", "senderDomain": "example.com", "subject": "Verify your account immediately", "links": []})
    result = client.post("/api/v1/analyze-email", json=request).json()
    assert result["emailRiskScore"] == 75
    assert result["riskLevel"] == "high"


@pytest.mark.parametrize("score,expected", [
    (0, AnalysisRiskLevel.LOW), (30, AnalysisRiskLevel.MODERATE),
    (65, AnalysisRiskLevel.HIGH), (85, AnalysisRiskLevel.CRITICAL),
])
def test_analysis_risk_level_mapping(score: int, expected: AnalysisRiskLevel) -> None:
    assert RuleBasedAnalyzer.risk_level(score) == expected


def test_analysis_rejects_unauthorized_body(client: TestClient) -> None:
    request = analysis_payload()
    request["bodyText"] = "secret body"
    assert client.post("/api/v1/analyze-email", json=request).status_code == 422


@pytest.mark.parametrize("subject,expected_type", [
    ("Act now", "urgency"), ("Your account will be suspended", "fear_or_threat"),
    ("Enter your password", "credential_request"), ("Administrator notice", "authority"),
    ("Official notice from the account team", "impersonation"), ("Claim your prize", "reward"),
    ("Limited time offer", "scarcity"),
])
def test_rule_based_text_indicators(client: TestClient, subject: str, expected_type: str) -> None:
    request = analysis_payload()
    request["subject"] = subject
    request["senderDomain"] = "microsoft.com"
    request["links"] = []
    result = client.post("/api/v1/analyze-email", json=request).json()
    assert expected_type in {item["type"] for item in result["detectedBehaviors"]}
