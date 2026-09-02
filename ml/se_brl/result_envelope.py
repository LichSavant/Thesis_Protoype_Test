"""Fail-closed lifecycle envelope for SE-BRL analytical processing.

The envelope reports structural processing status only. It does not contain or
produce model output, confidence, probability, classification, or risk.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .assessment import AssessmentResult, DimensionAssessment
from .codebook import load_codebook


class ResultEnvelopeLoadError(RuntimeError):
    """Raised when the canonical result-envelope contract cannot be loaded."""


class ResultEnvelopeValidationError(ValueError):
    """Raised when contract metadata or an envelope violates safe invariants."""


def _contract_path() -> Path:
    return Path(__file__).with_name("result-envelope.v0.1.0.json")


def _read_contract(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError as error:
        raise ResultEnvelopeLoadError(f"Result-envelope contract not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ResultEnvelopeLoadError(
            f"Malformed result-envelope JSON at line {error.lineno}, column {error.colno}: {path}"
        ) from error
    except OSError as error:
        raise ResultEnvelopeLoadError(f"Unable to read result-envelope contract: {path}") from error
    if not isinstance(document, dict):
        raise ResultEnvelopeValidationError("Result-envelope contract root must be an object")
    return document


def _text(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ResultEnvelopeValidationError(f"{location} must be a non-empty string")
    return value


def _unique_text_list(value: object, location: str, expected_count: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != expected_count:
        raise ResultEnvelopeValidationError(
            f"{location} must contain exactly {expected_count} entries"
        )
    items = tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(value))
    if len(set(items)) != len(items):
        raise ResultEnvelopeValidationError(f"{location} must contain unique entries")
    return items


def _reason_metadata(value: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, list) or len(value) < 9:
        raise ResultEnvelopeValidationError("reason_codes must contain at least nine entries")
    reasons: list[tuple[str, tuple[str, ...]]] = []
    for index, raw_reason in enumerate(value):
        if not isinstance(raw_reason, dict) or set(raw_reason) != {"id", "applies_to"}:
            raise ResultEnvelopeValidationError(f"reason_codes[{index}] has an invalid structure")
        reason_id = _text(raw_reason.get("id"), f"reason_codes[{index}].id")
        applies_to = raw_reason.get("applies_to")
        if not isinstance(applies_to, list) or not applies_to:
            raise ResultEnvelopeValidationError(
                f"reason_codes[{index}].applies_to must be a non-empty array"
            )
        statuses = tuple(
            _text(status, f"reason_codes[{index}].applies_to") for status in applies_to
        )
        if len(set(statuses)) != len(statuses):
            raise ResultEnvelopeValidationError(
                f"reason_codes[{index}].applies_to must contain unique statuses"
            )
        reasons.append((reason_id, statuses))
    if len({reason_id for reason_id, _ in reasons}) != len(reasons):
        raise ResultEnvelopeValidationError("reason_codes must contain unique IDs")
    return tuple(reasons)


def _validate_contract(document: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    required_sections = {
        "contract_version",
        "compatible_se_brl",
        "overall_statuses",
        "component_statuses",
        "components",
        "reason_codes",
    }
    if set(document) != required_sections:
        raise ResultEnvelopeValidationError("Result-envelope contract sections are incomplete or unknown")

    contract_version = _text(document.get("contract_version"), "contract_version")
    reference_version = _text(reference.get("contract_version"), "canonical.contract_version")
    if contract_version != reference_version:
        raise ResultEnvelopeValidationError(
            f"Incompatible result-envelope contract version {contract_version!r}"
        )

    compatibility = document.get("compatible_se_brl")
    reference_compatibility = reference.get("compatible_se_brl")
    if not isinstance(compatibility, dict) or set(compatibility) != {
        "schema_version",
        "codebook_version",
    }:
        raise ResultEnvelopeValidationError("compatible_se_brl has an invalid structure")
    if not isinstance(reference_compatibility, dict):
        raise ResultEnvelopeValidationError("Canonical compatible_se_brl is invalid")
    for version_field in ("schema_version", "codebook_version"):
        actual = _text(compatibility.get(version_field), f"compatible_se_brl.{version_field}")
        expected = _text(
            reference_compatibility.get(version_field),
            f"canonical.compatible_se_brl.{version_field}",
        )
        if actual != expected:
            raise ResultEnvelopeValidationError(
                f"Incompatible SE-BRL {version_field} {actual!r}; expected {expected!r}"
            )

    sections = (
        ("overall_statuses", 4),
        ("component_statuses", 3),
        ("components", 5),
    )
    for section, count in sections:
        actual = _unique_text_list(document.get(section), section, count)
        expected = _unique_text_list(reference.get(section), f"canonical.{section}", count)
        if actual != expected:
            raise ResultEnvelopeValidationError(f"Unknown or incorrectly ordered entry in {section}")

    reasons = _reason_metadata(document.get("reason_codes"))
    reference_reasons = _reason_metadata(reference.get("reason_codes"))
    if reasons != reference_reasons:
        raise ResultEnvelopeValidationError("Unknown or incompatible reason-code metadata")
    overall_statuses = set(_unique_text_list(document.get("overall_statuses"), "overall_statuses", 4))
    if any(not set(applies_to) <= overall_statuses for _, applies_to in reasons):
        raise ResultEnvelopeValidationError("A reason code references an unknown overall status")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load_result_envelope_contract(path: str | Path | None = None) -> Mapping[str, Any]:
    """Load, validate, and recursively freeze the canonical or a candidate contract."""

    canonical_path = _contract_path()
    reference = _read_contract(canonical_path)
    target_path = canonical_path if path is None else Path(path)
    document = reference if target_path.resolve() == canonical_path.resolve() else _read_contract(target_path)
    _validate_contract(document, reference)

    codebook = load_codebook()
    compatibility = document["compatible_se_brl"]
    if compatibility["schema_version"] != codebook["schema_version"]:
        raise ResultEnvelopeValidationError("Envelope contract has an incompatible SE-BRL schema version")
    if compatibility["codebook_version"] != codebook["codebook_version"]:
        raise ResultEnvelopeValidationError("Envelope contract has an incompatible SE-BRL codebook version")
    return _freeze(document)


@dataclass(frozen=True, slots=True)
class ComponentResult:
    """One analytical component and its lifecycle status."""

    component_id: str
    status: str

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        _text(self.status, "component status")


@dataclass(frozen=True, slots=True, init=False)
class ResultEnvelope:
    """Immutable ML-neutral analytical lifecycle result."""

    contract_version: str
    se_brl_schema_version: str
    se_brl_codebook_version: str
    overall_status: str
    modality_id: str
    components: tuple[ComponentResult, ...]
    assessment_result: AssessmentResult | None
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    def __init__(self) -> None:
        raise TypeError("Use a validated result-envelope factory")


def _contract_metadata() -> tuple[
    Mapping[str, Any],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    dict[str, tuple[str, ...]],
]:
    contract = load_result_envelope_contract()
    overall_statuses = tuple(contract["overall_statuses"])
    component_statuses = tuple(contract["component_statuses"])
    component_order = tuple(contract["components"])
    reason_applicability = {
        reason["id"]: tuple(reason["applies_to"]) for reason in contract["reason_codes"]
    }
    return contract, overall_statuses, component_statuses, component_order, reason_applicability


def _validate_assessment(assessment: object, modality_id: str) -> AssessmentResult:
    if not isinstance(assessment, AssessmentResult):
        raise ResultEnvelopeValidationError("assessment_result must be an AssessmentResult")
    codebook = load_codebook()
    if assessment.schema_version != codebook["schema_version"]:
        raise ResultEnvelopeValidationError("Assessment schema version is incompatible")
    if assessment.codebook_version != codebook["codebook_version"]:
        raise ResultEnvelopeValidationError("Assessment codebook version is incompatible")
    if assessment.modality_id != modality_id:
        raise ResultEnvelopeValidationError("Assessment modality does not match envelope modality")

    dimension_order = tuple(codebook["vector_ordering"]["dimension_order"])
    if not isinstance(assessment.dimension_results, tuple) or len(assessment.dimension_results) != 4:
        raise ResultEnvelopeValidationError("Assessment must contain exactly four dimension results")
    if any(not isinstance(item, DimensionAssessment) for item in assessment.dimension_results):
        raise ResultEnvelopeValidationError("Assessment contains an invalid dimension result")
    actual_order = tuple(item.dimension_id for item in assessment.dimension_results)
    if actual_order != dimension_order:
        raise ResultEnvelopeValidationError("Assessment dimensions are not in canonical order")

    valid_states = {item["id"] for item in codebook["evidence_states"]}
    if any(item.evidence_state not in valid_states for item in assessment.dimension_results):
        raise ResultEnvelopeValidationError("Assessment contains an unknown evidence state")
    mask = assessment.availability_mask
    if (
        not isinstance(mask, tuple)
        or len(mask) != 4
        or any(type(value) is not int or value not in (0, 1) for value in mask)
    ):
        raise ResultEnvelopeValidationError("Assessment availability mask must contain four integers in {0,1}")
    expected_mask = tuple(
        0 if item.evidence_state == "unavailable" else 1
        for item in assessment.dimension_results
    )
    if mask != expected_mask:
        raise ResultEnvelopeValidationError("Assessment availability mask conflicts with evidence states")
    return assessment


def _ordered_components(
    components: object,
    component_order: tuple[str, ...],
    valid_statuses: tuple[str, ...],
) -> tuple[ComponentResult, ...]:
    if type(components) is not tuple:
        raise ResultEnvelopeValidationError("components must be an immutable tuple")
    if any(not isinstance(component, ComponentResult) for component in components):
        raise ResultEnvelopeValidationError("components must contain only ComponentResult values")

    indexed: dict[str, ComponentResult] = {}
    for component in components:
        if component.component_id in indexed:
            raise ResultEnvelopeValidationError("components contain a duplicate component")
        indexed[component.component_id] = component
        if component.status not in valid_statuses:
            raise ResultEnvelopeValidationError(
                f"Unknown component status: {component.status!r}"
            )
    missing = sorted(set(component_order) - set(indexed))
    additional = sorted(set(indexed) - set(component_order))
    if missing or additional:
        details: list[str] = []
        if missing:
            details.append(f"missing components: {', '.join(missing)}")
        if additional:
            details.append(f"additional or unknown components: {', '.join(additional)}")
        raise ResultEnvelopeValidationError("Invalid components; " + "; ".join(details))
    return tuple(indexed[component_id] for component_id in component_order)


def _validated_reasons(
    reason_codes: object,
    overall_status: str,
    reason_applicability: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    if type(reason_codes) is not tuple:
        raise ResultEnvelopeValidationError("reason_codes must be an immutable tuple")
    if any(not isinstance(reason, str) or not reason for reason in reason_codes):
        raise ResultEnvelopeValidationError("reason_codes must contain only non-empty strings")
    if len(set(reason_codes)) != len(reason_codes):
        raise ResultEnvelopeValidationError("reason_codes must not contain duplicates")
    unknown = sorted(set(reason_codes) - set(reason_applicability))
    if unknown:
        raise ResultEnvelopeValidationError(
            f"Unknown or unsafe reason code: {', '.join(unknown)}"
        )
    if any(overall_status not in reason_applicability[reason] for reason in reason_codes):
        raise ResultEnvelopeValidationError("A reason code is not valid for the overall status")
    return reason_codes


def _validate_dependencies(components: Mapping[str, str]) -> None:
    if components["risk_decision"] == "completed" and (
        components["probability_calibration"] != "completed"
        or components["phishing_classification"] != "completed"
    ):
        raise ResultEnvelopeValidationError(
            "Completed risk decision requires completed calibration and classification"
        )
    if (
        components["probability_calibration"] == "completed"
        and components["phishing_classification"] != "completed"
    ):
        raise ResultEnvelopeValidationError(
            "Completed calibration requires completed phishing classification"
        )
    if (
        components["phishing_classification"] == "completed"
        and components["behavior_identification"] != "completed"
    ):
        raise ResultEnvelopeValidationError(
            "Completed phishing classification requires completed behavior identification"
        )


def _limitations_for(overall_status: str) -> tuple[str, ...]:
    if overall_status == "not_evaluated":
        return (
            "Behavior identification and downstream model-based processing are not integrated.",
            "Calibration and risk-decision rules remain deferred.",
        )
    if overall_status == "review_required":
        return ("Processing stopped without a definitive analytical result.",)
    if overall_status == "failed":
        return ("Analytical processing failed closed; no definitive result is available.",)
    return ()


def create_result_envelope(
    *,
    overall_status: str,
    modality_id: str,
    components: tuple[ComponentResult, ...],
    assessment_result: AssessmentResult | None = None,
    reason_codes: tuple[str, ...] = (),
) -> ResultEnvelope:
    """Create a strictly validated envelope, including reserved future states."""

    contract, overall_statuses, component_statuses, component_order, reason_applicability = (
        _contract_metadata()
    )
    if overall_status not in overall_statuses:
        raise ResultEnvelopeValidationError(f"Unknown overall status: {overall_status!r}")
    modality_id = _text(modality_id, "modality_id")
    ordered_components = _ordered_components(components, component_order, component_statuses)
    component_map = {
        component.component_id: component.status for component in ordered_components
    }
    reasons = _validated_reasons(reason_codes, overall_status, reason_applicability)

    codebook = load_codebook()
    known_modalities = {modality["id"] for modality in codebook["modalities"]}
    unsupported_review = (
        overall_status == "review_required" and "unsupported_modality" in reasons
    )
    if modality_id not in known_modalities and not unsupported_review:
        raise ResultEnvelopeValidationError(f"Unknown modality: {modality_id!r}")

    validated_assessment = None
    if assessment_result is not None:
        validated_assessment = _validate_assessment(assessment_result, modality_id)
        if component_map["modality_assessment"] != "completed":
            raise ResultEnvelopeValidationError(
                "A supplied assessment requires completed modality_assessment"
            )
    elif component_map["modality_assessment"] == "completed":
        raise ResultEnvelopeValidationError(
            "Completed modality_assessment requires an AssessmentResult"
        )

    _validate_dependencies(component_map)

    if overall_status == "completed":
        if any(status != "completed" for status in component_map.values()):
            raise ResultEnvelopeValidationError("Completed envelope requires all components completed")
        if reasons:
            raise ResultEnvelopeValidationError("Completed envelope cannot contain reason codes")
        if validated_assessment is None:
            raise ResultEnvelopeValidationError("Completed envelope requires a valid assessment")
    elif overall_status == "not_evaluated":
        if "not_evaluated" not in component_map.values():
            raise ResultEnvelopeValidationError(
                "Not-evaluated envelope requires at least one not-evaluated component"
            )
        required_reasons = {
            "validated_model_not_integrated",
            "calibrator_not_integrated",
            "risk_rules_not_frozen",
        }
        if not required_reasons <= set(reasons):
            raise ResultEnvelopeValidationError(
                "Not-evaluated envelope is missing required deferred-component reasons"
            )
    elif overall_status == "review_required":
        relevant_reasons = {
            reason
            for reason, applicable_statuses in reason_applicability.items()
            if "review_required" in applicable_statuses
        }
        if not set(reasons) & relevant_reasons:
            raise ResultEnvelopeValidationError(
                "Review-required envelope requires an approved review reason"
            )
        if all(status == "completed" for status in component_map.values()):
            raise ResultEnvelopeValidationError(
                "Review-required envelope cannot have every component completed"
            )
    elif overall_status == "failed":
        if "component_failure" not in reasons:
            raise ResultEnvelopeValidationError(
                "Failed envelope requires component_failure"
            )
        if "failed" not in component_map.values():
            raise ResultEnvelopeValidationError(
                "Failed envelope requires at least one failed component"
            )

    compatibility = contract["compatible_se_brl"]
    envelope = object.__new__(ResultEnvelope)
    object.__setattr__(envelope, "contract_version", contract["contract_version"])
    object.__setattr__(envelope, "se_brl_schema_version", compatibility["schema_version"])
    object.__setattr__(envelope, "se_brl_codebook_version", compatibility["codebook_version"])
    object.__setattr__(envelope, "overall_status", overall_status)
    object.__setattr__(envelope, "modality_id", modality_id)
    object.__setattr__(envelope, "components", ordered_components)
    object.__setattr__(envelope, "assessment_result", validated_assessment)
    object.__setattr__(envelope, "reason_codes", reasons)
    object.__setattr__(envelope, "limitations", _limitations_for(overall_status))
    return envelope


def _base_components(assessment_result: AssessmentResult | None) -> tuple[ComponentResult, ...]:
    contract = load_result_envelope_contract()
    return tuple(
        ComponentResult(
            component_id=component_id,
            status=(
                "completed"
                if component_id == "modality_assessment" and assessment_result is not None
                else "not_evaluated"
            ),
        )
        for component_id in contract["components"]
    )


def not_evaluated_result(
    modality_id: str,
    assessment_result: AssessmentResult | None = None,
) -> ResultEnvelope:
    """Create the current prototype's safe, explicitly incomplete result."""

    return create_result_envelope(
        overall_status="not_evaluated",
        modality_id=modality_id,
        components=_base_components(assessment_result),
        assessment_result=assessment_result,
        reason_codes=(
            "validated_model_not_integrated",
            "calibrator_not_integrated",
            "risk_rules_not_frozen",
        ),
    )


def review_required_result(
    modality_id: str,
    reason_codes: tuple[str, ...],
    assessment_result: AssessmentResult | None = None,
) -> ResultEnvelope:
    """Create a fail-closed result for an approved review condition."""

    return create_result_envelope(
        overall_status="review_required",
        modality_id=modality_id,
        components=_base_components(assessment_result),
        assessment_result=assessment_result,
        reason_codes=reason_codes,
    )


def failed_result(
    modality_id: str,
    failed_component: str,
    assessment_result: AssessmentResult | None = None,
) -> ResultEnvelope:
    """Create a fail-closed component-failure result without exception details."""

    if failed_component == "modality_assessment" and assessment_result is not None:
        raise ResultEnvelopeValidationError(
            "A failed modality_assessment cannot retain an AssessmentResult"
        )
    components = list(_base_components(assessment_result))
    matching_indexes = [
        index for index, component in enumerate(components)
        if component.component_id == failed_component
    ]
    if len(matching_indexes) != 1:
        raise ResultEnvelopeValidationError(f"Unknown failed component: {failed_component!r}")
    index = matching_indexes[0]
    components[index] = ComponentResult(failed_component, "failed")
    return create_result_envelope(
        overall_status="failed",
        modality_id=modality_id,
        components=tuple(components),
        assessment_result=assessment_result,
        reason_codes=("component_failure",),
    )


def serialize_result_envelope(envelope: ResultEnvelope) -> dict[str, Any]:
    """Return a fresh primitive dictionary; this is not a FastAPI wire contract."""

    if not isinstance(envelope, ResultEnvelope):
        raise ResultEnvelopeValidationError("envelope must be a ResultEnvelope")
    assessment = envelope.assessment_result
    serialized_assessment: dict[str, Any] | None = None
    if assessment is not None:
        serialized_assessment = {
            "codebook_version": assessment.codebook_version,
            "schema_version": assessment.schema_version,
            "modality_id": assessment.modality_id,
            "dimension_results": [
                {
                    "dimension_id": dimension.dimension_id,
                    "evidence_state": dimension.evidence_state,
                }
                for dimension in assessment.dimension_results
            ],
            "availability_mask": list(assessment.availability_mask),
        }
    return {
        "contract_version": envelope.contract_version,
        "se_brl_schema_version": envelope.se_brl_schema_version,
        "se_brl_codebook_version": envelope.se_brl_codebook_version,
        "overall_status": envelope.overall_status,
        "modality_id": envelope.modality_id,
        "components": [
            {"component_id": component.component_id, "status": component.status}
            for component in envelope.components
        ],
        "assessment_result": serialized_assessment,
        "reason_codes": list(envelope.reason_codes),
        "limitations": list(envelope.limitations),
    }
