import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

import backend.app.sebrl_adapter as adapter_module
from backend.app.sebrl_adapter import SebrlApiContractError, to_sebrl_api_response
from backend.app.sebrl_schemas import SebrlResultEnvelopeResponse
from ml.se_brl import (
    AssessmentInput,
    CodebookLoadError,
    CodebookValidationError,
    ResultEnvelope,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    assess,
    failed_result,
    load_codebook,
    load_result_envelope_contract,
    not_evaluated_result,
    review_required_result,
    serialize_result_envelope,
)


FORBIDDEN_FIELDS = {
    "raw_email_content",
    "subject",
    "sender",
    "html",
    "dom",
    "url",
    "dataset_name",
    "artifact_identifier",
    "evidence_text",
    "evidence_locator",
    "confidence",
    "probability",
    "classification",
    "risk_score",
    "risk_tier",
    "intervention",
    "attribution",
    "user_susceptibility",
    "visit_count",
}


def canonical_modality() -> str:
    return load_codebook()["modalities"][0]["id"]


def valid_assessment():
    codebook = load_codebook()
    dimensions = tuple(codebook["vector_ordering"]["dimension_order"])
    return assess(
        AssessmentInput(
            modality_id=canonical_modality(),
            required_content_available=True,
            conditional_evidence_available=True,
            observations={dimension_id: index % 2 == 0 for index, dimension_id in enumerate(dimensions)},
        )
    )


def candidate(*, with_assessment: bool = True) -> dict[str, Any]:
    assessment = valid_assessment() if with_assessment else None
    return serialize_result_envelope(not_evaluated_result(canonical_modality(), assessment))


def assert_primitive(value: Any) -> None:
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            assert_primitive(item)
    elif isinstance(value, list):
        for item in value:
            assert_primitive(item)
    else:
        assert value is None or type(value) in {str, int, float, bool}


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


def test_valid_not_evaluated_domain_envelope_conversion() -> None:
    response = to_sebrl_api_response(not_evaluated_result(canonical_modality()))
    assert response.overall_status == "not_evaluated"


def test_valid_review_required_domain_envelope_conversion() -> None:
    envelope = review_required_result(canonical_modality(), ("missing_required_evidence",))
    response = to_sebrl_api_response(envelope)
    assert response.overall_status == "review_required"
    assert response.reason_codes == ("missing_required_evidence",)


def test_valid_failed_domain_envelope_conversion() -> None:
    envelope = failed_result(canonical_modality(), "behavior_identification")
    response = to_sebrl_api_response(envelope)
    assert response.overall_status == "failed"
    assert response.components[1].status == "failed"


def test_valid_envelope_with_assessment_conversion() -> None:
    assessment = valid_assessment()
    response = to_sebrl_api_response(not_evaluated_result(assessment.modality_id, assessment))
    assert response.assessment_result is not None
    assert response.assessment_result.modality_id == assessment.modality_id


def test_envelope_without_assessment_serializes_json_null() -> None:
    response = to_sebrl_api_response(not_evaluated_result(canonical_modality()))
    assert response.model_dump(mode="json")["assessment_result"] is None
    assert json.loads(response.model_dump_json())["assessment_result"] is None


def test_canonical_contract_version() -> None:
    response = SebrlResultEnvelopeResponse.model_validate(candidate())
    assert response.contract_version == load_result_envelope_contract()["contract_version"]


def test_canonical_schema_version() -> None:
    response = SebrlResultEnvelopeResponse.model_validate(candidate())
    assert response.se_brl_schema_version == load_codebook()["schema_version"]


def test_canonical_codebook_version() -> None:
    response = SebrlResultEnvelopeResponse.model_validate(candidate())
    assert response.se_brl_codebook_version == load_codebook()["codebook_version"]


@pytest.mark.parametrize(
    "field",
    ("contract_version", "se_brl_schema_version", "se_brl_codebook_version"),
)
def test_incompatible_envelope_version_rejection(field: str) -> None:
    data = candidate()
    data[field] = "99.0.0"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_canonical_component_ordering() -> None:
    response = SebrlResultEnvelopeResponse.model_validate(candidate())
    assert tuple(item.component_id for item in response.components) == tuple(
        load_result_envelope_contract()["components"]
    )


def test_canonical_dimension_ordering() -> None:
    response = SebrlResultEnvelopeResponse.model_validate(candidate())
    assert response.assessment_result is not None
    assert tuple(item.dimension_id for item in response.assessment_result.dimension_results) == tuple(
        load_codebook()["vector_ordering"]["dimension_order"]
    )


def test_exact_availability_mask_serialization() -> None:
    assessment = valid_assessment()
    response = to_sebrl_api_response(not_evaluated_result(assessment.modality_id, assessment))
    dumped = response.model_dump(mode="json")
    assert dumped["assessment_result"]["availability_mask"] == list(
        assessment.availability_mask
    )


@pytest.mark.parametrize("index", range(4))
def test_boolean_availability_mask_values_are_strictly_rejected(index: int) -> None:
    data = candidate()
    data["assessment_result"]["availability_mask"][index] = True
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_modality_rejection() -> None:
    data = candidate(with_assessment=False)
    data["modality_id"] = "unknown_modality"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_overall_status_rejection() -> None:
    data = candidate()
    data["overall_status"] = "unknown_status"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_component_rejection() -> None:
    data = candidate()
    data["components"][1]["component_id"] = "unknown_component"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_missing_component_rejection() -> None:
    data = candidate()
    data["components"].pop()
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_additional_component_rejection() -> None:
    data = candidate()
    data["components"].append(copy.deepcopy(data["components"][-1]))
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_duplicate_component_rejection() -> None:
    data = candidate()
    data["components"][1]["component_id"] = data["components"][0]["component_id"]
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_incorrect_component_order_rejection() -> None:
    data = candidate()
    data["components"][1], data["components"][2] = (
        data["components"][2],
        data["components"][1],
    )
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_component_status_rejection() -> None:
    data = candidate()
    data["components"][1]["status"] = "unknown_status"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_reason_code_rejection() -> None:
    data = candidate()
    data["reason_codes"].append("unknown_reason")
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_inapplicable_reason_code_rejection() -> None:
    data = candidate()
    data["reason_codes"].append("missing_required_evidence")
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_duplicate_reason_code_rejection() -> None:
    data = candidate()
    data["reason_codes"].append(data["reason_codes"][0])
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_assessment_modality_mismatch_rejection() -> None:
    data = candidate()
    data["assessment_result"]["modality_id"] = load_codebook()["modalities"][1]["id"]
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_assessment_schema_mismatch_rejection() -> None:
    data = candidate()
    data["assessment_result"]["schema_version"] = "99.0.0"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_assessment_codebook_mismatch_rejection() -> None:
    data = candidate()
    data["assessment_result"]["codebook_version"] = "99.0.0"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_incorrect_dimension_order_rejection() -> None:
    data = candidate()
    results = data["assessment_result"]["dimension_results"]
    results[0], results[1] = results[1], results[0]
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_dimension_rejection() -> None:
    data = candidate()
    data["assessment_result"]["dimension_results"][0]["dimension_id"] = "unknown_dimension"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_unknown_evidence_state_rejection() -> None:
    data = candidate()
    data["assessment_result"]["dimension_results"][0]["evidence_state"] = "unknown_state"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_incorrect_mask_state_relationship_rejection() -> None:
    data = candidate()
    data["assessment_result"]["dimension_results"][0]["evidence_state"] = "unavailable"
    data["assessment_result"]["availability_mask"][0] = 1
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


@pytest.mark.parametrize("value", (-1, 2, "1", None, 1.0))
def test_invalid_availability_mask_value_rejection(value: Any) -> None:
    data = candidate()
    data["assessment_result"]["availability_mask"][0] = value
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


@pytest.mark.parametrize("level", ("envelope", "component", "assessment", "dimension"))
def test_extra_field_rejection_at_every_nested_level(level: str) -> None:
    data = candidate()
    targets = {
        "envelope": data,
        "component": data["components"][0],
        "assessment": data["assessment_result"],
        "dimension": data["assessment_result"]["dimension_results"][0],
    }
    targets[level]["unexpected"] = "value"
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_dictionary_input_rejected_by_adapter() -> None:
    with pytest.raises(SebrlApiContractError, match="ResultEnvelope"):
        to_sebrl_api_response(candidate())


def test_input_envelope_remains_unchanged() -> None:
    envelope = not_evaluated_result(canonical_modality(), valid_assessment())
    before = serialize_result_envelope(envelope)
    to_sebrl_api_response(envelope)
    assert serialize_result_envelope(envelope) == before


def test_returned_pydantic_response_is_fresh_and_independent() -> None:
    envelope = not_evaluated_result(canonical_modality(), valid_assessment())
    first = to_sebrl_api_response(envelope)
    second = to_sebrl_api_response(envelope)
    assert first == second
    assert first is not second
    assert first.components is not second.components
    with pytest.raises(ValidationError):
        first.overall_status = "completed"


def test_json_mode_serialization_uses_only_primitive_values() -> None:
    response = to_sebrl_api_response(
        not_evaluated_result(canonical_modality(), valid_assessment())
    )
    dumped = response.model_dump(mode="json")
    assert_primitive(dumped)
    assert json.loads(response.model_dump_json()) == dumped


def test_no_forbidden_analytical_fields_appear_in_output() -> None:
    response = to_sebrl_api_response(
        not_evaluated_result(canonical_modality(), valid_assessment())
    )
    assert FORBIDDEN_FIELDS.isdisjoint(all_keys(response.model_dump(mode="json")))


def test_partial_data_cannot_be_represented_as_completed() -> None:
    data = candidate()
    data["overall_status"] = "completed"
    data["reason_codes"] = []
    data["limitations"] = []
    with pytest.raises(ValidationError, match="partial component data"):
        SebrlResultEnvelopeResponse.model_validate(data)


@pytest.mark.parametrize("status", ("not_evaluated", "review_required", "failed"))
def test_noncompleted_status_rejects_empty_limitations(status: str) -> None:
    if status == "not_evaluated":
        data = candidate(with_assessment=False)
    elif status == "review_required":
        data = serialize_result_envelope(
            review_required_result(canonical_modality(), ("missing_required_evidence",))
        )
    else:
        data = serialize_result_envelope(
            failed_result(canonical_modality(), "behavior_identification")
        )
    data["limitations"] = []
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_whitespace_is_normalized_and_blank_text_is_rejected() -> None:
    data = candidate(with_assessment=False)
    data["modality_id"] = f"  {data['modality_id']}  "
    response = SebrlResultEnvelopeResponse.model_validate(data)
    assert response.modality_id == canonical_modality()
    data = candidate(with_assessment=False)
    data["limitations"][0] = "   "
    with pytest.raises(ValidationError):
        SebrlResultEnvelopeResponse.model_validate(data)


def test_adapter_rejects_tampered_domain_envelope_without_partial_response() -> None:
    envelope = not_evaluated_result(canonical_modality())
    object.__setattr__(envelope, "contract_version", "99.0.0")
    with pytest.raises(SebrlApiContractError, match="incompatible"):
        to_sebrl_api_response(envelope)


@pytest.mark.parametrize(
    "exception_type",
    (
        CodebookLoadError,
        CodebookValidationError,
        ResultEnvelopeLoadError,
        ResultEnvelopeValidationError,
    ),
)
def test_adapter_sanitizes_domain_serialization_failures(
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[Exception],
) -> None:
    internal_message = "internal contract artifact details must remain private"
    validation_called = False
    no_response = object()
    result: object = no_response

    def fail_serialization(envelope: ResultEnvelope) -> dict[str, Any]:
        raise exception_type(internal_message)

    def track_validation(value: object) -> object:
        nonlocal validation_called
        validation_called = True
        return value

    monkeypatch.setattr(adapter_module, "serialize_result_envelope", fail_serialization)
    monkeypatch.setattr(
        adapter_module.SebrlResultEnvelopeResponse,
        "model_validate",
        track_validation,
    )

    with pytest.raises(SebrlApiContractError) as captured:
        result = to_sebrl_api_response(not_evaluated_result(canonical_modality()))

    assert str(captured.value) == (
        "SE-BRL result is incompatible with the backend API contract"
    )
    assert internal_message not in str(captured.value)
    assert captured.value.__cause__ is None
    assert result is no_response
    assert validation_called is False


def test_adapter_accepts_only_actual_domain_type() -> None:
    class PretendEnvelope:
        pass

    assert not isinstance(PretendEnvelope(), ResultEnvelope)
    with pytest.raises(SebrlApiContractError):
        to_sebrl_api_response(PretendEnvelope())
