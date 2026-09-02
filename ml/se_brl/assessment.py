"""Resolve SE-BRL evidence states and the four-slot availability mask.

This module consumes caller-supplied Boolean observations. It does not inspect
content, detect behavioral indicators, produce confidence values, or estimate
phishing risk.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .codebook import load_codebook


class AssessmentValidationError(ValueError):
    """Raised when assessment input or canonical assessment metadata is invalid."""


_INITIAL_CODEBOOK = load_codebook()
_COMPATIBLE_SCHEMA_VERSION = _INITIAL_CODEBOOK["schema_version"]
_COMPATIBLE_CODEBOOK_VERSION = _INITIAL_CODEBOOK["codebook_version"]


def _strict_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise AssessmentValidationError(f"{field_name} must be a Boolean")
    return value


@dataclass(frozen=True, slots=True)
class AssessmentInput:
    """Immutable structural input for modality-based SE-BRL assessment."""

    modality_id: str
    required_content_available: bool
    conditional_evidence_available: bool
    observations: Mapping[str, bool]

    def __post_init__(self) -> None:
        if not isinstance(self.modality_id, str) or not self.modality_id:
            raise AssessmentValidationError("modality_id must be a non-empty string")
        _strict_bool(self.required_content_available, "required_content_available")
        _strict_bool(self.conditional_evidence_available, "conditional_evidence_available")
        if not isinstance(self.observations, Mapping):
            raise AssessmentValidationError("observations must be a dimension-to-Boolean mapping")

        frozen_observations: dict[str, bool] = {}
        for dimension_id, observed in self.observations.items():
            if not isinstance(dimension_id, str) or not dimension_id:
                raise AssessmentValidationError("observation dimension IDs must be non-empty strings")
            frozen_observations[dimension_id] = _strict_bool(
                observed, f"observations[{dimension_id!r}]"
            )
        object.__setattr__(self, "observations", MappingProxyType(frozen_observations))


@dataclass(frozen=True, slots=True)
class DimensionAssessment:
    """An ordered dimension ID and its resolved canonical evidence state."""

    dimension_id: str
    evidence_state: str


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    """Immutable structural result; the mask is evidence availability, not risk."""

    codebook_version: str
    schema_version: str
    modality_id: str
    dimension_results: tuple[DimensionAssessment, ...]
    availability_mask: tuple[int, int, int, int]


def _items_by_id(items: object, section: str) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, tuple):
        raise AssessmentValidationError(f"Canonical {section} must be an immutable sequence")

    indexed: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise AssessmentValidationError(f"Canonical {section} entries must be mappings")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in indexed:
            raise AssessmentValidationError(f"Canonical {section} contains an invalid or duplicate ID")
        indexed[identifier] = item
    return indexed


def _canonical_assessment_metadata() -> tuple[
    Mapping[str, object],
    tuple[str, str, str, str],
    dict[str, Mapping[str, object]],
    dict[str, str],
    dict[str, str],
]:
    codebook = load_codebook()
    vector = codebook.get("vector_ordering")
    if not isinstance(vector, Mapping):
        raise AssessmentValidationError("Canonical vector_ordering is missing")
    raw_order = vector.get("dimension_order")
    if not isinstance(raw_order, tuple) or len(raw_order) != 4:
        raise AssessmentValidationError("Canonical dimension order must contain exactly four IDs")
    if any(not isinstance(item, str) or not item for item in raw_order):
        raise AssessmentValidationError("Canonical dimension order contains an invalid ID")
    dimension_order = (raw_order[0], raw_order[1], raw_order[2], raw_order[3])
    if len(set(dimension_order)) != 4:
        raise AssessmentValidationError("Canonical dimension order must contain unique IDs")

    dimensions = _items_by_id(codebook.get("dimensions"), "dimensions")
    if set(dimensions) != set(dimension_order):
        raise AssessmentValidationError("Canonical dimension order and definitions are inconsistent")

    modalities = _items_by_id(codebook.get("modalities"), "modalities")
    evidence_states = _items_by_id(codebook.get("evidence_states"), "evidence_states")
    states_by_kind = {state_id: state_id for state_id in evidence_states}
    if set(states_by_kind) != {"supported", "absent", "unavailable"}:
        raise AssessmentValidationError("Canonical evidence states are incompatible with this resolver")

    support_codes = _items_by_id(codebook.get("support_codes"), "support_codes")
    codes_by_kind: dict[str, str] = {}
    for code_id, definition in support_codes.items():
        kind = definition.get("assessment_kind")
        if not isinstance(kind, str) or kind in codes_by_kind:
            raise AssessmentValidationError("Canonical support-code semantics are invalid")
        codes_by_kind[kind] = code_id
    required_kinds = {"assessable", "conditionally_assessable", "unavailable"}
    if set(codes_by_kind) != required_kinds:
        raise AssessmentValidationError("Canonical support codes are incompatible with this resolver")

    expected_versions = {
        "schema_version": _COMPATIBLE_SCHEMA_VERSION,
        "codebook_version": _COMPATIBLE_CODEBOOK_VERSION,
    }
    for version_field, expected_version in expected_versions.items():
        version = codebook.get(version_field)
        if not isinstance(version, str) or not version:
            raise AssessmentValidationError(f"Canonical {version_field} is invalid")
        if version != expected_version:
            raise AssessmentValidationError(
                f"Incompatible canonical {version_field} {version!r}; expected {expected_version!r}"
            )

    return codebook, dimension_order, modalities, states_by_kind, codes_by_kind


def _resolve_state(
    support_code: object,
    *,
    content_available: bool,
    conditional_evidence_available: bool,
    observed: bool,
    states: Mapping[str, str],
    codes: Mapping[str, str],
) -> str:
    if support_code not in set(codes.values()):
        raise AssessmentValidationError(f"Unknown canonical support code: {support_code!r}")
    if support_code == codes["unavailable"]:
        return states["unavailable"]
    if not content_available:
        return states["unavailable"]
    if support_code == codes["conditionally_assessable"] and not conditional_evidence_available:
        return states["unavailable"]
    if support_code == codes["assessable"] or support_code == codes["conditionally_assessable"]:
        return states["supported"] if observed else states["absent"]
    raise AssessmentValidationError(f"Unsupported canonical support code: {support_code!r}")


def assess(input_data: AssessmentInput) -> AssessmentResult:
    """Resolve ordered evidence states and their four-value availability mask."""

    if not isinstance(input_data, AssessmentInput):
        raise AssessmentValidationError("input_data must be an AssessmentInput")

    codebook, dimension_order, modalities, states, codes = _canonical_assessment_metadata()
    modality = modalities.get(input_data.modality_id)
    if modality is None:
        raise AssessmentValidationError(f"Unknown modality: {input_data.modality_id!r}")

    observation_ids = set(input_data.observations)
    expected_ids = set(dimension_order)
    missing = sorted(expected_ids - observation_ids)
    additional = sorted(observation_ids - expected_ids)
    if missing or additional:
        details: list[str] = []
        if missing:
            details.append(f"missing dimensions: {', '.join(missing)}")
        if additional:
            details.append(f"additional or unknown dimensions: {', '.join(additional)}")
        raise AssessmentValidationError("Invalid observations; " + "; ".join(details))

    support_mapping = modality.get("support_by_dimension")
    if not isinstance(support_mapping, Mapping) or set(support_mapping) != expected_ids:
        raise AssessmentValidationError("Canonical modality mapping is incomplete or contains unknown dimensions")

    results = tuple(
        DimensionAssessment(
            dimension_id=dimension_id,
            evidence_state=_resolve_state(
                support_mapping[dimension_id],
                content_available=input_data.required_content_available,
                conditional_evidence_available=input_data.conditional_evidence_available,
                observed=input_data.observations[dimension_id],
                states=states,
                codes=codes,
            ),
        )
        for dimension_id in dimension_order
    )
    mask_values = tuple(0 if result.evidence_state == states["unavailable"] else 1 for result in results)
    availability_mask = (mask_values[0], mask_values[1], mask_values[2], mask_values[3])

    return AssessmentResult(
        codebook_version=codebook["codebook_version"],
        schema_version=codebook["schema_version"],
        modality_id=input_data.modality_id,
        dimension_results=results,
        availability_mask=availability_mask,
    )
