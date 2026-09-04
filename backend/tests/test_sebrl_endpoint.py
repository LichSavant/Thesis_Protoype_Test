import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.sebrl_schemas import SebrlResultEnvelopeResponse
from backend.app.sebrl_service import SebrlServiceError
from ml.se_brl import load_result_envelope_contract


ENDPOINT = "/api/v1/se-brl/status"
EXPECTED_REASON_CODES = (
    "validated_model_not_integrated",
    "calibrator_not_integrated",
    "risk_rules_not_frozen",
)
EXPECTED_LIMITATIONS = (
    "A validated behavioral model is not integrated.",
    "A validated calibrator is not integrated.",
    "Frozen decision rules are not available.",
)


@pytest.fixture()
def client() -> TestClient:
    with TestClient(main.app) as test_client:
        yield test_client


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for child in value.values():
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def test_status_returns_valid_fail_closed_email_envelope(client: TestClient) -> None:
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    result = SebrlResultEnvelopeResponse.model_validate(response.json())
    assert result.modality_id == "content_bearing_email"
    assert result.overall_status == "not_evaluated"
    assert result.assessment_result is None


def test_status_preserves_canonical_components_without_completion(
    client: TestClient,
) -> None:
    payload = client.get(ENDPOINT).json()
    expected_components = load_result_envelope_contract()["components"]

    assert tuple(item["component_id"] for item in payload["components"]) == expected_components
    assert all(item["status"] == "not_evaluated" for item in payload["components"])


def test_status_preserves_deferred_reasons_and_safe_limitations(
    client: TestClient,
) -> None:
    payload = client.get(ENDPOINT).json()

    assert tuple(payload["reason_codes"]) == EXPECTED_REASON_CODES
    assert tuple(payload["limitations"]) == EXPECTED_LIMITATIONS


def test_status_uses_only_snake_case_fields_and_has_no_analytical_output(
    client: TestClient,
) -> None:
    payload = client.get(ENDPOINT).json()
    keys = _all_keys(payload)

    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in keys)
    assert keys.isdisjoint(
        {
            "prediction",
            "probability",
            "confidence",
            "risk_level",
            "evidence",
            "dataset",
            "dataset_value",
            "label",
            "completed_result",
        }
    )


def test_openapi_documents_status_response_schema(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"][ENDPOINT]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SebrlResultEnvelopeResponse"
    }
    assert "SebrlResultEnvelopeResponse" in openapi["components"]["schemas"]


def test_service_error_is_sanitized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*, modality_id: str) -> None:
        raise SebrlServiceError("private internal detail")

    monkeypatch.setattr(main.sebrl_analysis_service, "not_evaluated", fail)
    response = client.get(ENDPOINT)

    assert response.status_code == 503
    assert response.json() == {"detail": "SE-BRL service unavailable"}
    assert "private internal detail" not in response.text


def test_unexpected_programming_error_is_not_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*, modality_id: str) -> None:
        raise RuntimeError("unexpected programming error")

    monkeypatch.setattr(main.sebrl_analysis_service, "not_evaluated", fail)
    with TestClient(main.app) as test_client:
        with pytest.raises(RuntimeError, match="unexpected programming error"):
            test_client.get(ENDPOINT)
