import copy
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

import ml.se_brl.assessment as assessment_module
from ml.se_brl import load_codebook
from ml.se_brl.assessment import (
    AssessmentInput,
    AssessmentValidationError,
    assess,
)


def canonical_ids() -> tuple[tuple[str, ...], tuple[str, ...]]:
    codebook = load_codebook()
    dimensions = tuple(codebook["vector_ordering"]["dimension_order"])
    modalities = tuple(modality["id"] for modality in codebook["modalities"])
    return dimensions, modalities


def observations(value: bool = False) -> dict[str, bool]:
    dimensions, _ = canonical_ids()
    return {dimension_id: value for dimension_id in dimensions}


def assessment_input(
    modality_id: str,
    *,
    content_available: bool = True,
    conditional_available: bool = True,
    observed: dict[str, bool] | None = None,
) -> AssessmentInput:
    return AssessmentInput(
        modality_id=modality_id,
        required_content_available=content_available,
        conditional_evidence_available=conditional_available,
        observations=observations() if observed is None else observed,
    )


def states(result: object) -> tuple[str, ...]:
    return tuple(item.evidence_state for item in result.dimension_results)


def thaw(value: object) -> object:
    if isinstance(value, dict) or isinstance(value, MappingProxyType):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return copy.deepcopy(value)


def freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def patched_codebook(monkeypatch: pytest.MonkeyPatch) -> dict:
    document = thaw(load_codebook())
    assert isinstance(document, dict)
    monkeypatch.setattr(assessment_module, "load_codebook", lambda: freeze(document))
    return document


def test_successful_email_assessment() -> None:
    dimensions, modalities = canonical_ids()
    observed = observations(True)
    result = assess(assessment_input(modalities[0], observed=observed))
    assert tuple(item.dimension_id for item in result.dimension_results) == dimensions
    assert states(result) == ("supported", "supported", "supported", "supported")
    assert result.availability_mask == (1, 1, 1, 1)


def test_successful_webpage_assessment() -> None:
    dimensions, modalities = canonical_ids()
    observed = observations(False)
    observed[dimensions[1]] = True
    result = assess(assessment_input(modalities[1], observed=observed))
    assert states(result) == ("absent", "supported", "absent", "absent")
    assert result.availability_mask == (1, 1, 1, 1)


@pytest.mark.parametrize("modality_index", (0, 1))
def test_a_is_supported_when_content_is_available_and_observed(modality_index: int) -> None:
    dimensions, modalities = canonical_ids()
    result = assess(assessment_input(modalities[modality_index], observed=observations(True)))
    assert result.dimension_results[0].dimension_id == dimensions[0]
    assert result.dimension_results[0].evidence_state == "supported"


def test_a_is_absent_when_content_is_available_and_not_observed() -> None:
    _, modalities = canonical_ids()
    result = assess(assessment_input(modalities[0], observed=observations(False)))
    assert result.dimension_results[0].evidence_state == "absent"
    assert result.availability_mask[0] == 1


def test_missing_content_makes_every_content_dimension_unavailable() -> None:
    _, modalities = canonical_ids()
    result = assess(
        assessment_input(
            modalities[0], content_available=False, conditional_available=True, observed=observations(True)
        )
    )
    assert states(result) == ("unavailable",) * 4
    assert result.availability_mask == (0, 0, 0, 0)


def test_a_star_is_unavailable_without_conditional_evidence() -> None:
    dimensions, modalities = canonical_ids()
    result = assess(
        assessment_input(
            modalities[0], content_available=True, conditional_available=False, observed=observations(True)
        )
    )
    trust_index = dimensions.index("trust_identity_manipulation")
    assert result.dimension_results[trust_index].evidence_state == "unavailable"
    assert result.availability_mask == (1, 1, 0, 1)


@pytest.mark.parametrize(
    ("observed", "expected"),
    ((True, "supported"), (False, "absent")),
)
def test_a_star_resolves_observation_when_conditional_evidence_exists(
    observed: bool, expected: str
) -> None:
    dimensions, modalities = canonical_ids()
    values = observations(False)
    trust_index = dimensions.index("trust_identity_manipulation")
    values[dimensions[trust_index]] = observed
    result = assess(
        assessment_input(modalities[1], conditional_available=True, observed=values)
    )
    assert result.dimension_results[trust_index].evidence_state == expected
    assert result.availability_mask[trust_index] == 1


@pytest.mark.parametrize("modality_index", (2, 3))
@pytest.mark.parametrize(
    ("content_available", "conditional_available", "observed"),
    ((False, False, False), (True, True, True)),
)
def test_u_modalities_are_always_unavailable(
    modality_index: int,
    content_available: bool,
    conditional_available: bool,
    observed: bool,
) -> None:
    _, modalities = canonical_ids()
    result = assess(
        assessment_input(
            modalities[modality_index],
            content_available=content_available,
            conditional_available=conditional_available,
            observed=observations(observed),
        )
    )
    assert states(result) == ("unavailable",) * 4
    assert result.availability_mask == (0, 0, 0, 0)


def test_unknown_modality_is_rejected() -> None:
    with pytest.raises(AssessmentValidationError, match="Unknown modality"):
        assess(assessment_input("unknown_modality"))


def test_missing_dimension_is_rejected() -> None:
    dimensions, modalities = canonical_ids()
    values = observations()
    del values[dimensions[0]]
    with pytest.raises(AssessmentValidationError, match="missing dimensions"):
        assess(assessment_input(modalities[0], observed=values))


@pytest.mark.parametrize("dimension_id", ("unknown_dimension", "additional_dimension"))
def test_unknown_or_additional_dimension_is_rejected(dimension_id: str) -> None:
    _, modalities = canonical_ids()
    values = observations()
    values[dimension_id] = False
    with pytest.raises(AssessmentValidationError, match="additional or unknown dimensions"):
        assess(assessment_input(modalities[0], observed=values))


@pytest.mark.parametrize("field_name", ("required_content_available", "conditional_evidence_available"))
@pytest.mark.parametrize("invalid", (None, "false", (), [], 0, 1))
def test_non_boolean_availability_is_rejected(field_name: str, invalid: object) -> None:
    _, modalities = canonical_ids()
    arguments = {
        "modality_id": modalities[0],
        "required_content_available": True,
        "conditional_evidence_available": True,
        "observations": observations(),
    }
    arguments[field_name] = invalid
    with pytest.raises(AssessmentValidationError, match="must be a Boolean"):
        AssessmentInput(**arguments)


@pytest.mark.parametrize("invalid", (None, "true", (), [], 0, 1))
def test_non_boolean_observation_is_rejected(invalid: object) -> None:
    dimensions, modalities = canonical_ids()
    values = observations()
    values[dimensions[0]] = invalid
    with pytest.raises(AssessmentValidationError, match="must be a Boolean"):
        assessment_input(modalities[0], observed=values)


def test_results_follow_exact_canonical_dimension_order() -> None:
    dimensions, modalities = canonical_ids()
    reversed_values = dict(reversed(tuple(observations().items())))
    result = assess(assessment_input(modalities[0], observed=reversed_values))
    assert tuple(item.dimension_id for item in result.dimension_results) == dimensions


@pytest.mark.parametrize(
    ("conditional_available", "expected"),
    ((True, (1, 1, 1, 1)), (False, (1, 1, 0, 1))),
)
def test_mask_has_exact_immutable_integer_shape(
    conditional_available: bool, expected: tuple[int, int, int, int]
) -> None:
    _, modalities = canonical_ids()
    result = assess(
        assessment_input(modalities[0], conditional_available=conditional_available)
    )
    assert result.availability_mask == expected
    assert isinstance(result.availability_mask, tuple)
    assert len(result.availability_mask) == 4
    assert all(type(value) is int and value in (0, 1) for value in result.availability_mask)


def test_supported_and_absent_both_map_to_available() -> None:
    dimensions, modalities = canonical_ids()
    values = observations(False)
    values[dimensions[0]] = True
    result = assess(assessment_input(modalities[0], observed=values))
    assert result.dimension_results[0].evidence_state == "supported"
    assert result.dimension_results[1].evidence_state == "absent"
    assert result.availability_mask[:2] == (1, 1)


def test_unavailable_maps_to_zero() -> None:
    _, modalities = canonical_ids()
    result = assess(assessment_input(modalities[0], conditional_available=False))
    unavailable_indexes = tuple(
        index for index, item in enumerate(result.dimension_results) if item.evidence_state == "unavailable"
    )
    assert unavailable_indexes
    assert all(result.availability_mask[index] == 0 for index in unavailable_indexes)


def test_input_is_immutable_and_copies_observations() -> None:
    _, modalities = canonical_ids()
    values = observations()
    input_data = assessment_input(modalities[0], observed=values)
    values[next(iter(values))] = True
    assert not any(input_data.observations.values())
    with pytest.raises(FrozenInstanceError):
        input_data.modality_id = modalities[1]
    with pytest.raises(TypeError):
        input_data.observations[next(iter(input_data.observations))] = True


def test_output_is_immutable() -> None:
    _, modalities = canonical_ids()
    result = assess(assessment_input(modalities[0]))
    with pytest.raises(FrozenInstanceError):
        result.modality_id = modalities[1]
    with pytest.raises(TypeError):
        result.availability_mask[0] = 0
    with pytest.raises(FrozenInstanceError):
        result.dimension_results[0].evidence_state = "supported"


@pytest.mark.parametrize(
    "forbidden_field",
    ("email_body", "subject", "html", "dom", "url", "raw_evidence", "dataset_record", "confidence"),
)
def test_raw_artifact_and_confidence_fields_are_not_accepted(forbidden_field: str) -> None:
    _, modalities = canonical_ids()
    arguments = {
        "modality_id": modalities[0],
        "required_content_available": True,
        "conditional_evidence_available": True,
        "observations": observations(),
        forbidden_field: object(),
    }
    with pytest.raises(TypeError):
        AssessmentInput(**arguments)


def test_result_contains_only_approved_structural_fields() -> None:
    _, modalities = canonical_ids()
    result = assess(assessment_input(modalities[0]))
    assert result.__slots__ == (
        "codebook_version",
        "schema_version",
        "modality_id",
        "dimension_results",
        "availability_mask",
    )
    forbidden = {
        "raw_content",
        "raw_evidence",
        "evidence_locators",
        "confidence",
        "model_version",
        "classification",
        "risk_score",
        "calibrated_probability",
    }
    assert forbidden.isdisjoint(result.__slots__)


def test_unknown_support_code_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    document = patched_codebook(monkeypatch)
    document["modalities"][0]["support_by_dimension"][document["vector_ordering"]["dimension_order"][0]] = "X"
    _, modalities = canonical_ids()
    with pytest.raises(AssessmentValidationError, match="Unknown canonical support code"):
        assess(assessment_input(modalities[0]))


def test_incomplete_canonical_mapping_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    document = patched_codebook(monkeypatch)
    dimension = document["vector_ordering"]["dimension_order"][0]
    del document["modalities"][0]["support_by_dimension"][dimension]
    _, modalities = canonical_ids()
    with pytest.raises(AssessmentValidationError, match="mapping is incomplete"):
        assess(assessment_input(modalities[0]))


@pytest.mark.parametrize("version_field", ("schema_version", "codebook_version"))
def test_incompatible_version_is_rejected(
    monkeypatch: pytest.MonkeyPatch, version_field: str
) -> None:
    document = patched_codebook(monkeypatch)
    document[version_field] = "99.0.0"
    _, modalities = canonical_ids()
    with pytest.raises(AssessmentValidationError, match="Incompatible canonical"):
        assess(assessment_input(modalities[0]))
