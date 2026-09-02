"""Internal orchestration for safe, incomplete SE-BRL structural results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ml.se_brl import (
    AssessmentResult,
    CodebookLoadError,
    CodebookValidationError,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    failed_result,
    load_codebook,
    load_result_envelope_contract,
    not_evaluated_result,
    review_required_result,
)

from .sebrl_adapter import SebrlApiContractError, to_sebrl_api_response
from .sebrl_schemas import SebrlResultEnvelopeResponse


class SebrlServiceError(ValueError):
    """Raised when the service cannot safely construct an SE-BRL response."""


_BOUNDARY_EXCEPTIONS = (
    CodebookLoadError,
    CodebookValidationError,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    SebrlApiContractError,
    ValidationError,
)

_SAFE_LIMITATION_BY_REASON = {
    "validated_model_not_integrated": "A validated behavioral model is not integrated.",
    "calibrator_not_integrated": "A validated calibrator is not integrated.",
    "risk_rules_not_frozen": "Frozen decision rules are not available.",
    "unsupported_modality": "The modality is unsupported for this operation.",
    "missing_required_evidence": "Required evidence is unavailable.",
    "invalid_schema": "The input schema is invalid.",
    "incompatible_version": "Component versions are incompatible.",
    "parser_failure": "Parsing could not safely complete.",
    "component_failure": "Analytical processing could not safely complete.",
}


def _canonical_sources() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    return load_codebook(), load_result_envelope_contract()


def _validate_modality(modality_id: object, codebook: Mapping[str, Any]) -> str:
    if type(modality_id) is not str or not modality_id.strip():
        raise SebrlServiceError("modality_id must be a non-empty string")
    canonical_modalities = {item["id"] for item in codebook["modalities"]}
    if modality_id not in canonical_modalities:
        raise SebrlServiceError("modality_id is not canonical")
    return modality_id


def _validate_assessment(
    assessment_result: object,
    modality_id: str,
    codebook: Mapping[str, Any],
) -> AssessmentResult | None:
    if assessment_result is None:
        return None
    if not isinstance(assessment_result, AssessmentResult):
        raise SebrlServiceError("assessment_result must be an AssessmentResult")
    if assessment_result.modality_id != modality_id:
        raise SebrlServiceError("assessment_result modality is incompatible")
    if assessment_result.schema_version != codebook["schema_version"]:
        raise SebrlServiceError("assessment_result schema version is incompatible")
    if assessment_result.codebook_version != codebook["codebook_version"]:
        raise SebrlServiceError("assessment_result codebook version is incompatible")
    return assessment_result


def _ordered_review_reasons(
    reason_codes: object,
    contract: Mapping[str, Any],
) -> tuple[str, ...]:
    if type(reason_codes) is not tuple or not reason_codes:
        raise SebrlServiceError("review reason_codes must be a non-empty tuple")
    if any(type(reason) is not str or not reason.strip() for reason in reason_codes):
        raise SebrlServiceError("review reason_codes must contain non-empty strings")
    if len(set(reason_codes)) != len(reason_codes):
        raise SebrlServiceError("review reason_codes must not contain duplicates")

    reason_metadata = {
        item["id"]: tuple(item["applies_to"]) for item in contract["reason_codes"]
    }
    unknown = set(reason_codes) - set(reason_metadata)
    if unknown:
        raise SebrlServiceError("review reason_codes contain an unknown value")
    if any("review_required" not in reason_metadata[reason] for reason in reason_codes):
        raise SebrlServiceError("a reason_code is not valid for review_required")
    return tuple(
        item["id"] for item in contract["reason_codes"] if item["id"] in set(reason_codes)
    )


def _validate_failed_component(
    failed_component_id: object,
    contract: Mapping[str, Any],
) -> str:
    if type(failed_component_id) is not str or not failed_component_id.strip():
        raise SebrlServiceError("failed_component_id must be a non-empty string")
    if failed_component_id not in set(contract["components"]):
        raise SebrlServiceError("failed_component_id is not canonical")
    return failed_component_id


def _with_safe_limitations(
    response: SebrlResultEnvelopeResponse,
) -> SebrlResultEnvelopeResponse:
    payload = response.model_dump(mode="python")
    payload["limitations"] = tuple(
        _SAFE_LIMITATION_BY_REASON[reason] for reason in response.reason_codes
    )
    return SebrlResultEnvelopeResponse.model_validate(payload)


class SebrlAnalysisService:
    """Construct API-ready fail-closed SE-BRL responses for future routing."""

    def not_evaluated(
        self,
        modality_id: str,
        assessment_result: AssessmentResult | None = None,
    ) -> SebrlResultEnvelopeResponse:
        try:
            codebook, _ = _canonical_sources()
            modality = _validate_modality(modality_id, codebook)
            assessment = _validate_assessment(assessment_result, modality, codebook)
            envelope = not_evaluated_result(modality, assessment)
            return _with_safe_limitations(to_sebrl_api_response(envelope))
        except _BOUNDARY_EXCEPTIONS:
            raise SebrlServiceError("SE-BRL service could not safely complete") from None

    def review_required(
        self,
        modality_id: str,
        reason_codes: tuple[str, ...],
        assessment_result: AssessmentResult | None = None,
    ) -> SebrlResultEnvelopeResponse:
        try:
            codebook, contract = _canonical_sources()
            modality = _validate_modality(modality_id, codebook)
            reasons = _ordered_review_reasons(reason_codes, contract)
            assessment = _validate_assessment(assessment_result, modality, codebook)
            envelope = review_required_result(modality, reasons, assessment)
            return _with_safe_limitations(to_sebrl_api_response(envelope))
        except _BOUNDARY_EXCEPTIONS:
            raise SebrlServiceError("SE-BRL service could not safely complete") from None

    def failed(
        self,
        modality_id: str,
        failed_component_id: str,
    ) -> SebrlResultEnvelopeResponse:
        try:
            codebook, contract = _canonical_sources()
            modality = _validate_modality(modality_id, codebook)
            component = _validate_failed_component(failed_component_id, contract)
            envelope = failed_result(modality, component)
            return _with_safe_limitations(to_sebrl_api_response(envelope))
        except _BOUNDARY_EXCEPTIONS:
            raise SebrlServiceError("SE-BRL service could not safely complete") from None
