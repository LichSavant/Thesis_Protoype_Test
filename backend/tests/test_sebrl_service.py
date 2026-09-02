import inspect
import json
from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

import backend.app.sebrl_service as service_module
from backend.app.sebrl_adapter import SebrlApiContractError
from backend.app.sebrl_schemas import SebrlResultEnvelopeResponse
from backend.app.sebrl_service import SebrlAnalysisService, SebrlServiceError
from ml.se_brl import (
    AssessmentInput,
    AssessmentResult,
    CodebookLoadError,
    CodebookValidationError,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    assess,
    load_codebook,
    load_result_envelope_contract,
)


def canonical_modalities() -> tuple[str, ...]:
    return tuple(item["id"] for item in load_codebook()["modalities"])


def canonical_components() -> tuple[str, ...]:
    return tuple(load_result_envelope_contract()["components"])


def canonical_review_reasons() -> tuple[str, ...]:
    return tuple(
        item["id"]
        for item in load_result_envelope_contract()["reason_codes"]
        if "review_required" in item["applies_to"]
    )


def valid_assessment(modality_id: str | None = None) -> AssessmentResult:
    codebook = load_codebook()
    modality = canonical_modalities()[0] if modality_id is None else modality_id
    dimensions = tuple(codebook["vector_ordering"]["dimension_order"])
    return assess(
        AssessmentInput(
            modality_id=modality,
            required_content_available=True,
            conditional_evidence_available=True,
            observations={dimension_id: False for dimension_id in dimensions},
        )
    )


def component_statuses(response: SebrlResultEnvelopeResponse) -> dict[str, str]:
    return {item.component_id: item.status for item in response.components}


def all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for item in value.values():
            keys.update(all_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(all_keys(item))
    return keys


def test_valid_not_evaluated_without_assessment() -> None:
    response = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])
    assert response.overall_status == "not_evaluated"
    assert response.assessment_result is None


def test_valid_not_evaluated_with_assessment() -> None:
    assessment = valid_assessment()
    response = SebrlAnalysisService().not_evaluated(
        assessment.modality_id, assessment
    )
    assert response.overall_status == "not_evaluated"
    assert response.assessment_result is not None
    assert response.assessment_result.modality_id == assessment.modality_id


def test_not_evaluated_component_statuses_without_assessment() -> None:
    response = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])
    assert component_statuses(response) == {
        component_id: "not_evaluated" for component_id in canonical_components()
    }


def test_not_evaluated_component_statuses_with_assessment() -> None:
    assessment = valid_assessment()
    response = SebrlAnalysisService().not_evaluated(
        assessment.modality_id, assessment
    )
    statuses = component_statuses(response)
    assert statuses[canonical_components()[0]] == "completed"
    assert all(
        statuses[component_id] == "not_evaluated"
        for component_id in canonical_components()[1:]
    )


def test_not_evaluated_preserves_required_reason_codes() -> None:
    response = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])
    assert response.reason_codes == (
        "validated_model_not_integrated",
        "calibrator_not_integrated",
        "risk_rules_not_frozen",
    )


def test_not_evaluated_uses_fixed_safe_limitations() -> None:
    response = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])
    assert response.limitations == (
        "A validated behavioral model is not integrated.",
        "A validated calibrator is not integrated.",
        "Frozen decision rules are not available.",
    )


@pytest.mark.parametrize("reason", canonical_review_reasons())
def test_valid_review_required_for_each_canonical_reason(reason: str) -> None:
    response = SebrlAnalysisService().review_required(
        canonical_modalities()[0], (reason,)
    )
    assert response.overall_status == "review_required"
    assert response.reason_codes == (reason,)


def test_review_required_accepts_multiple_canonical_reasons() -> None:
    reasons = canonical_review_reasons()[:3]
    response = SebrlAnalysisService().review_required(
        canonical_modalities()[0], reasons
    )
    assert response.reason_codes == reasons
    assert len(response.limitations) == len(reasons)


def test_review_required_preserves_canonical_reason_order() -> None:
    canonical = canonical_review_reasons()
    response = SebrlAnalysisService().review_required(
        canonical_modalities()[0], tuple(reversed(canonical))
    )
    assert response.reason_codes == canonical


def test_review_required_can_attach_compatible_assessment() -> None:
    assessment = valid_assessment()
    response = SebrlAnalysisService().review_required(
        assessment.modality_id,
        (canonical_review_reasons()[1],),
        assessment,
    )
    assert response.assessment_result is not None
    assert component_statuses(response)[canonical_components()[0]] == "completed"


def test_empty_review_reasons_are_rejected() -> None:
    with pytest.raises(SebrlServiceError, match="non-empty tuple"):
        SebrlAnalysisService().review_required(canonical_modalities()[0], ())


def test_unknown_review_reason_is_rejected() -> None:
    with pytest.raises(SebrlServiceError, match="unknown"):
        SebrlAnalysisService().review_required(
            canonical_modalities()[0], ("unknown_reason",)
        )


def test_inapplicable_review_reason_is_rejected() -> None:
    contract = load_result_envelope_contract()
    inapplicable = next(
        item["id"]
        for item in contract["reason_codes"]
        if "review_required" not in item["applies_to"]
    )
    with pytest.raises(SebrlServiceError, match="not valid"):
        SebrlAnalysisService().review_required(
            canonical_modalities()[0], (inapplicable,)
        )


def test_duplicate_review_reasons_are_rejected() -> None:
    reason = canonical_review_reasons()[0]
    with pytest.raises(SebrlServiceError, match="duplicates"):
        SebrlAnalysisService().review_required(
            canonical_modalities()[0], (reason, reason)
        )


@pytest.mark.parametrize("invalid", ([], {}, "parser_failure", ("",), (1,)))
def test_invalid_review_reason_collection_is_rejected(invalid: object) -> None:
    with pytest.raises(SebrlServiceError):
        SebrlAnalysisService().review_required(
            canonical_modalities()[0], invalid
        )


@pytest.mark.parametrize("component_id", canonical_components())
def test_valid_failed_response_for_each_canonical_component(
    component_id: str,
) -> None:
    response = SebrlAnalysisService().failed(
        canonical_modalities()[0], component_id
    )
    assert response.overall_status == "failed"
    assert component_statuses(response)[component_id] == "failed"


def test_unknown_failed_component_is_rejected() -> None:
    with pytest.raises(SebrlServiceError, match="not canonical"):
        SebrlAnalysisService().failed(
            canonical_modalities()[0], "unknown_component"
        )


@pytest.mark.parametrize("invalid", (None, 1, (), "", "   "))
def test_invalid_failed_component_type_or_value_is_rejected(invalid: object) -> None:
    with pytest.raises(SebrlServiceError, match="non-empty string"):
        SebrlAnalysisService().failed(canonical_modalities()[0], invalid)


def test_failed_response_contains_component_failure_reason() -> None:
    response = SebrlAnalysisService().failed(
        canonical_modalities()[0], canonical_components()[1]
    )
    assert response.reason_codes == ("component_failure",)


def test_failed_response_uses_only_generic_safe_limitation() -> None:
    response = SebrlAnalysisService().failed(
        canonical_modalities()[0], canonical_components()[1]
    )
    assert response.limitations == (
        "Analytical processing could not safely complete.",
    )


@pytest.mark.parametrize(
    ("reason", "limitation"),
    (
        ("unsupported_modality", "The modality is unsupported for this operation."),
        ("missing_required_evidence", "Required evidence is unavailable."),
        ("invalid_schema", "The input schema is invalid."),
        ("incompatible_version", "Component versions are incompatible."),
        ("parser_failure", "Parsing could not safely complete."),
    ),
)
def test_review_required_uses_fixed_safe_limitation(
    reason: str,
    limitation: str,
) -> None:
    response = SebrlAnalysisService().review_required(
        canonical_modalities()[0], (reason,)
    )
    assert response.limitations == (limitation,)


@pytest.mark.parametrize("modality_id", canonical_modalities())
def test_not_evaluated_accepts_all_canonical_modalities(modality_id: str) -> None:
    response = SebrlAnalysisService().not_evaluated(modality_id)
    assert response.modality_id == modality_id


def test_unknown_modality_is_rejected() -> None:
    with pytest.raises(SebrlServiceError, match="not canonical"):
        SebrlAnalysisService().not_evaluated("unknown_modality")


@pytest.mark.parametrize("invalid", ("", "   ", None, 0, (), {}))
def test_empty_or_non_string_modality_is_rejected(invalid: object) -> None:
    with pytest.raises(SebrlServiceError, match="non-empty string"):
        SebrlAnalysisService().not_evaluated(invalid)


def test_assessment_modality_mismatch_is_rejected() -> None:
    assessment = valid_assessment(canonical_modalities()[1])
    with pytest.raises(SebrlServiceError, match="modality"):
        SebrlAnalysisService().not_evaluated(
            canonical_modalities()[0], assessment
        )


def test_assessment_schema_mismatch_is_rejected() -> None:
    assessment = replace(valid_assessment(), schema_version="99.0.0")
    with pytest.raises(SebrlServiceError, match="schema version"):
        SebrlAnalysisService().not_evaluated(
            canonical_modalities()[0], assessment
        )


def test_assessment_codebook_mismatch_is_rejected() -> None:
    assessment = replace(valid_assessment(), codebook_version="99.0.0")
    with pytest.raises(SebrlServiceError, match="codebook version"):
        SebrlAnalysisService().not_evaluated(
            canonical_modalities()[0], assessment
        )


@pytest.mark.parametrize("invalid", ({}, [], object(), "assessment"))
def test_invalid_assessment_type_is_rejected(invalid: object) -> None:
    with pytest.raises(SebrlServiceError, match="AssessmentResult"):
        SebrlAnalysisService().not_evaluated(
            canonical_modalities()[0], invalid
        )


@pytest.mark.parametrize(
    "exception_type",
    (
        CodebookLoadError,
        CodebookValidationError,
        ResultEnvelopeLoadError,
        ResultEnvelopeValidationError,
    ),
)
def test_domain_factory_error_becomes_sanitized_service_error(
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[Exception],
) -> None:
    internal_message = "C:\\private\\artifact.json contained a secret"
    adapter_called = False
    no_response = object()
    result: object = no_response

    def fail_factory(*args: object) -> object:
        raise exception_type(internal_message)

    def track_adapter(envelope: object) -> object:
        nonlocal adapter_called
        adapter_called = True
        return envelope

    monkeypatch.setattr(service_module, "not_evaluated_result", fail_factory)
    monkeypatch.setattr(service_module, "to_sebrl_api_response", track_adapter)

    with pytest.raises(SebrlServiceError) as captured:
        result = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])

    assert str(captured.value) == "SE-BRL service could not safely complete"
    assert internal_message not in str(captured.value)
    assert captured.value.__cause__ is None
    assert adapter_called is False
    assert result is no_response


def test_adapter_error_becomes_sanitized_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    internal_message = "raw validation details and secret values"
    no_response = object()
    result: object = no_response

    def fail_adapter(envelope: object) -> object:
        raise SebrlApiContractError(internal_message)

    monkeypatch.setattr(service_module, "to_sebrl_api_response", fail_adapter)
    with pytest.raises(SebrlServiceError) as captured:
        result = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])

    assert str(captured.value) == "SE-BRL service could not safely complete"
    assert internal_message not in str(captured.value)
    assert captured.value.__cause__ is None
    assert result is no_response


def test_unapproved_programming_error_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_factory(*args: object) -> object:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(service_module, "not_evaluated_result", fail_factory)
    with pytest.raises(RuntimeError, match="programming defect"):
        SebrlAnalysisService().not_evaluated(canonical_modalities()[0])


def test_no_completed_public_service_method_exists() -> None:
    public_methods = {
        name
        for name, member in inspect.getmembers(
            SebrlAnalysisService, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert public_methods == {"not_evaluated", "review_required", "failed"}


@pytest.mark.parametrize("method", ("not_evaluated", "review_required", "failed"))
def test_service_returns_pydantic_response(method: str) -> None:
    service = SebrlAnalysisService()
    if method == "not_evaluated":
        response = service.not_evaluated(canonical_modalities()[0])
    elif method == "review_required":
        response = service.review_required(
            canonical_modalities()[0], (canonical_review_reasons()[0],)
        )
    else:
        response = service.failed(
            canonical_modalities()[0], canonical_components()[0]
        )
    assert isinstance(response, SebrlResultEnvelopeResponse)


def test_returned_response_is_immutable() -> None:
    response = SebrlAnalysisService().not_evaluated(canonical_modalities()[0])
    with pytest.raises(ValidationError):
        response.overall_status = "completed"
    with pytest.raises(TypeError):
        response.limitations[0] = "changed"


def test_json_serialization_remains_valid() -> None:
    response = SebrlAnalysisService().not_evaluated(
        canonical_modalities()[0], valid_assessment()
    )
    dumped = response.model_dump(mode="json")
    assert json.loads(response.model_dump_json()) == dumped
    assert isinstance(dumped["components"], list)
    assert isinstance(dumped["limitations"], list)


def test_forbidden_analytical_fields_are_absent() -> None:
    forbidden = {
        "artifact_content",
        "subject",
        "sender",
        "html",
        "dom",
        "url",
        "evidence",
        "confidence",
        "probability",
        "classification",
        "risk_score",
        "risk_tier",
        "intervention",
        "model_attribution",
        "visit_count",
        "user_susceptibility",
    }
    response = SebrlAnalysisService().not_evaluated(
        canonical_modalities()[0], valid_assessment()
    )
    assert forbidden.isdisjoint(all_keys(response.model_dump(mode="json")))


def test_arbitrary_limitations_are_not_accepted() -> None:
    with pytest.raises(TypeError):
        SebrlAnalysisService().not_evaluated(
            canonical_modalities()[0], limitations=("raw exception text",)
        )
