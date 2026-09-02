import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest

from ml.se_brl import load_codebook
from ml.se_brl.assessment import AssessmentInput, AssessmentResult, assess
from ml.se_brl.result_envelope import (
    ComponentResult,
    ResultEnvelope,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    create_result_envelope,
    failed_result,
    load_result_envelope_contract,
    not_evaluated_result,
    review_required_result,
    serialize_result_envelope,
)


MISSING_COMPONENT_REASONS = (
    "validated_model_not_integrated",
    "calibrator_not_integrated",
    "risk_rules_not_frozen",
)
REVIEW_REASONS = (
    "unsupported_modality",
    "missing_required_evidence",
    "invalid_schema",
    "incompatible_version",
    "parser_failure",
)


def canonical_modality(index: int = 0) -> str:
    return load_codebook()["modalities"][index]["id"]


def valid_assessment(modality_id: str | None = None) -> AssessmentResult:
    codebook = load_codebook()
    modality = canonical_modality() if modality_id is None else modality_id
    dimensions = tuple(codebook["vector_ordering"]["dimension_order"])
    return assess(
        AssessmentInput(
            modality_id=modality,
            required_content_available=True,
            conditional_evidence_available=True,
            observations={dimension_id: False for dimension_id in dimensions},
        )
    )


def component_results(**overrides: str) -> tuple[ComponentResult, ...]:
    contract = load_result_envelope_contract()
    return tuple(
        ComponentResult(component_id, overrides.get(component_id, "not_evaluated"))
        for component_id in contract["components"]
    )


def current_components(assessment: AssessmentResult | None = None) -> tuple[ComponentResult, ...]:
    status = "completed" if assessment is not None else "not_evaluated"
    return component_results(modality_assessment=status)


def write_contract(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "candidate-envelope.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def mutable_contract() -> dict:
    path = Path(__file__).parents[1] / "se_brl" / "result-envelope.v0.1.0.json"
    return json.loads(path.read_text(encoding="utf-8"))


def assert_primitive(value: object) -> None:
    if value is None or type(value) in (str, int, bool):
        return
    if isinstance(value, list):
        for item in value:
            assert_primitive(item)
        return
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            assert_primitive(item)
        return
    pytest.fail(f"Non-JSON-compatible value: {type(value).__name__}")


def test_loads_canonical_contract_as_immutable() -> None:
    contract = load_result_envelope_contract()
    assert isinstance(contract, MappingProxyType)
    with pytest.raises(TypeError):
        contract["contract_version"] = "changed"


def test_contract_version_and_compatible_versions() -> None:
    contract = load_result_envelope_contract()
    codebook = load_codebook()
    assert contract["contract_version"] == "0.1.0"
    assert contract["compatible_se_brl"] == {
        "schema_version": codebook["schema_version"],
        "codebook_version": codebook["codebook_version"],
    }


def test_contract_has_exact_overall_statuses() -> None:
    assert load_result_envelope_contract()["overall_statuses"] == (
        "completed",
        "not_evaluated",
        "review_required",
        "failed",
    )


def test_contract_has_exact_component_statuses() -> None:
    assert load_result_envelope_contract()["component_statuses"] == (
        "completed",
        "not_evaluated",
        "failed",
    )


def test_contract_has_exact_components_and_order() -> None:
    assert load_result_envelope_contract()["components"] == (
        "modality_assessment",
        "behavior_identification",
        "phishing_classification",
        "probability_calibration",
        "risk_decision",
    )


def test_contract_has_only_approved_reason_codes() -> None:
    actual = tuple(reason["id"] for reason in load_result_envelope_contract()["reason_codes"])
    assert actual == MISSING_COMPONENT_REASONS + REVIEW_REASONS + ("component_failure",)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("contract_version", "99.0.0"),
        ("schema_version", "99.0.0"),
        ("codebook_version", "99.0.0"),
    ),
)
def test_rejects_incompatible_contract_versions(
    tmp_path: Path, field: str, value: str
) -> None:
    document = mutable_contract()
    if field == "contract_version":
        document[field] = value
    else:
        document["compatible_se_brl"][field] = value
    with pytest.raises(ResultEnvelopeValidationError, match="Incompatible"):
        load_result_envelope_contract(write_contract(tmp_path, document))


def test_rejects_missing_or_malformed_contract(tmp_path: Path) -> None:
    with pytest.raises(ResultEnvelopeLoadError, match="not found"):
        load_result_envelope_contract(tmp_path / "missing.json")
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"contract_version":', encoding="utf-8")
    with pytest.raises(ResultEnvelopeLoadError, match="Malformed"):
        load_result_envelope_contract(malformed)


def test_current_not_evaluated_factory_without_assessment() -> None:
    result = not_evaluated_result(canonical_modality())
    assert result.overall_status == "not_evaluated"
    assert result.assessment_result is None
    assert tuple(component.status for component in result.components) == (
        "not_evaluated",
    ) * 5


def test_not_evaluated_has_required_missing_component_reasons() -> None:
    result = not_evaluated_result(canonical_modality())
    assert result.reason_codes == MISSING_COMPONENT_REASONS


def test_not_evaluated_attaches_valid_assessment_without_reinterpreting_it() -> None:
    assessment = valid_assessment()
    result = not_evaluated_result(assessment.modality_id, assessment)
    assert result.assessment_result is assessment
    assert result.components[0] == ComponentResult("modality_assessment", "completed")
    assert tuple(component.status for component in result.components[1:]) == (
        "not_evaluated",
    ) * 4


def test_assessment_modality_mismatch_is_rejected() -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError, match="modality does not match"):
        not_evaluated_result(canonical_modality(1), assessment)


@pytest.mark.parametrize(
    ("field", "message"),
    (("schema_version", "schema version"), ("codebook_version", "codebook version")),
)
def test_assessment_version_mismatch_is_rejected(field: str, message: str) -> None:
    assessment = replace(valid_assessment(), **{field: "99.0.0"})
    with pytest.raises(ResultEnvelopeValidationError, match=message):
        not_evaluated_result(assessment.modality_id, assessment)


def test_invalid_assessment_type_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="must be an AssessmentResult"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components=component_results(modality_assessment="completed"),
            assessment_result=object(),
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_invalid_assessment_shape_and_mask_are_rejected() -> None:
    assessment = valid_assessment()
    missing_dimension = replace(assessment, dimension_results=assessment.dimension_results[:-1])
    with pytest.raises(ResultEnvelopeValidationError, match="exactly four"):
        not_evaluated_result(assessment.modality_id, missing_dimension)
    invalid_mask = replace(assessment, availability_mask=(1, 1, 1, 2))
    with pytest.raises(ResultEnvelopeValidationError, match="four integers"):
        not_evaluated_result(assessment.modality_id, invalid_mask)


def test_completed_without_assessment_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="requires an AssessmentResult"):
        create_result_envelope(
            overall_status="completed",
            modality_id=canonical_modality(),
            components=component_results(
                modality_assessment="completed",
                behavior_identification="completed",
                phishing_classification="completed",
                probability_calibration="completed",
                risk_decision="completed",
            ),
        )


def test_completed_with_incomplete_components_is_rejected() -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError, match="all components completed"):
        create_result_envelope(
            overall_status="completed",
            modality_id=assessment.modality_id,
            components=current_components(assessment),
            assessment_result=assessment,
        )


@pytest.mark.parametrize("reason", MISSING_COMPONENT_REASONS + ("component_failure",))
def test_completed_with_failure_or_missing_component_reason_is_rejected(reason: str) -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError):
        create_result_envelope(
            overall_status="completed",
            modality_id=assessment.modality_id,
            components=component_results(
                modality_assessment="completed",
                behavior_identification="completed",
                phishing_classification="completed",
                probability_calibration="completed",
                risk_decision="completed",
            ),
            assessment_result=assessment,
            reason_codes=(reason,),
        )


def test_reserved_completed_state_is_structurally_representable() -> None:
    assessment = valid_assessment()
    result = create_result_envelope(
        overall_status="completed",
        modality_id=assessment.modality_id,
        components=component_results(
            modality_assessment="completed",
            behavior_identification="completed",
            phishing_classification="completed",
            probability_calibration="completed",
            risk_decision="completed",
        ),
        assessment_result=assessment,
    )
    assert result.overall_status == "completed"
    assert result.reason_codes == ()


def test_not_evaluated_with_every_component_completed_is_rejected() -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError, match="at least one not-evaluated"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=assessment.modality_id,
            components=component_results(
                modality_assessment="completed",
                behavior_identification="completed",
                phishing_classification="completed",
                probability_calibration="completed",
                risk_decision="completed",
            ),
            assessment_result=assessment,
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_review_required_without_relevant_reason_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="approved review reason"):
        create_result_envelope(
            overall_status="review_required",
            modality_id=canonical_modality(),
            components=component_results(),
        )


@pytest.mark.parametrize("reason", REVIEW_REASONS)
def test_review_required_for_each_approved_condition(reason: str) -> None:
    modality = "unsupported_input" if reason == "unsupported_modality" else canonical_modality()
    result = review_required_result(modality, (reason,))
    assert result.overall_status == "review_required"
    assert result.reason_codes == (reason,)
    assert result.assessment_result is None
    assert all(component.status != "completed" for component in result.components)


def test_review_required_preserves_valid_assessment() -> None:
    assessment = valid_assessment()
    result = review_required_result(
        assessment.modality_id, ("missing_required_evidence",), assessment
    )
    assert result.assessment_result is assessment
    assert result.components[0].status == "completed"


def test_failed_without_component_failure_reason_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError):
        create_result_envelope(
            overall_status="failed",
            modality_id=canonical_modality(),
            components=component_results(behavior_identification="failed"),
            reason_codes=(),
        )


def test_failed_without_failed_component_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="failed component"):
        create_result_envelope(
            overall_status="failed",
            modality_id=canonical_modality(),
            components=component_results(),
            reason_codes=("component_failure",),
        )


def test_failed_factory_marks_exact_component_and_exposes_no_exception() -> None:
    result = failed_result(canonical_modality(), "behavior_identification")
    failed = tuple(component.component_id for component in result.components if component.status == "failed")
    assert failed == ("behavior_identification",)
    assert result.reason_codes == ("component_failure",)
    assert "exception" not in serialize_result_envelope(result)


def test_failed_modality_assessment_rejects_supplied_assessment() -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError, match="cannot retain"):
        failed_result(assessment.modality_id, "modality_assessment", assessment)


def test_failed_component_cannot_have_completed_overall() -> None:
    assessment = valid_assessment()
    with pytest.raises(ResultEnvelopeValidationError):
        create_result_envelope(
            overall_status="completed",
            modality_id=assessment.modality_id,
            components=component_results(
                modality_assessment="completed",
                behavior_identification="failed",
                phishing_classification="completed",
                probability_calibration="completed",
                risk_decision="completed",
            ),
            assessment_result=assessment,
        )


def test_missing_component_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="missing components"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components=component_results()[:-1],
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_additional_or_unknown_component_is_rejected() -> None:
    components = component_results() + (ComponentResult("unknown_component", "not_evaluated"),)
    with pytest.raises(ResultEnvelopeValidationError, match="additional or unknown components"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components=components,
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_unknown_component_status_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="Unknown component status"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components=component_results(behavior_identification="unknown"),
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_mutable_component_mapping_is_rejected() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="immutable tuple"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components={"modality_assessment": "not_evaluated"},
            reason_codes=MISSING_COMPONENT_REASONS,
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"risk_decision": "completed"},
        {"probability_calibration": "completed"},
        {"phishing_classification": "completed"},
    ),
)
def test_dependency_order_is_enforced(overrides: dict[str, str]) -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="requires completed"):
        create_result_envelope(
            overall_status="not_evaluated",
            modality_id=canonical_modality(),
            components=component_results(**overrides),
            reason_codes=MISSING_COMPONENT_REASONS,
        )


def test_components_are_returned_in_canonical_order() -> None:
    result = create_result_envelope(
        overall_status="not_evaluated",
        modality_id=canonical_modality(),
        components=tuple(reversed(component_results())),
        reason_codes=MISSING_COMPONENT_REASONS,
    )
    assert tuple(component.component_id for component in result.components) == tuple(
        load_result_envelope_contract()["components"]
    )


def test_component_input_and_envelope_output_are_immutable() -> None:
    component = ComponentResult("behavior_identification", "not_evaluated")
    with pytest.raises(FrozenInstanceError):
        component.status = "completed"
    result = not_evaluated_result(canonical_modality())
    with pytest.raises(FrozenInstanceError):
        result.overall_status = "completed"
    with pytest.raises(TypeError):
        result.components[0] = component
    with pytest.raises(TypeError, match="validated result-envelope factory"):
        ResultEnvelope()


def test_only_canonical_safe_reason_codes_are_accepted() -> None:
    with pytest.raises(ResultEnvelopeValidationError, match="Unknown or unsafe reason"):
        review_required_result(canonical_modality(), ("ValueError: parser exploded",))


def test_result_structure_has_no_forbidden_analytical_fields() -> None:
    forbidden = {
        "artifact_content",
        "subject",
        "email_body",
        "sender",
        "html",
        "dom",
        "url",
        "raw_evidence",
        "evidence_locator",
        "dataset_source",
        "annotator_information",
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
    assert forbidden.isdisjoint(ResultEnvelope.__slots__)


def test_serialization_is_json_compatible_and_ordered() -> None:
    assessment = valid_assessment()
    result = not_evaluated_result(assessment.modality_id, assessment)
    serialized = serialize_result_envelope(result)
    assert_primitive(serialized)
    json.dumps(serialized)
    assert tuple(item["component_id"] for item in serialized["components"]) == tuple(
        load_result_envelope_contract()["components"]
    )
    assert tuple(
        item["dimension_id"] for item in serialized["assessment_result"]["dimension_results"]
    ) == tuple(load_codebook()["vector_ordering"]["dimension_order"])
    assert isinstance(serialized["assessment_result"]["availability_mask"], list)


def test_serialized_copy_mutation_does_not_change_envelope() -> None:
    assessment = valid_assessment()
    result = not_evaluated_result(assessment.modality_id, assessment)
    serialized = serialize_result_envelope(result)
    serialized["components"][0]["status"] = "failed"
    serialized["reason_codes"].clear()
    serialized["assessment_result"]["availability_mask"][0] = 0
    assert result.components[0].status == "completed"
    assert result.reason_codes == MISSING_COMPONENT_REASONS
    assert result.assessment_result.availability_mask == (1, 1, 1, 1)
