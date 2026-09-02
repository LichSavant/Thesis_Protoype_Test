"""Strict API response schemas for the structural SE-BRL result envelope.

These models are an API boundary only. Canonical values and ordering remain
owned by the versioned contracts under :mod:`ml.se_brl`.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from ml.se_brl import load_codebook, load_result_envelope_contract


NonEmptyText = Annotated[StrictStr, Field(min_length=1)]
AvailabilityMask = tuple[StrictInt, StrictInt, StrictInt, StrictInt]


class _SebrlResponseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _canonical_metadata() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return fresh plain metadata derived only from the canonical loaders."""

    codebook = load_codebook()
    contract = load_result_envelope_contract()
    return (
        {
            "schema_version": codebook["schema_version"],
            "codebook_version": codebook["codebook_version"],
            "dimension_order": tuple(codebook["vector_ordering"]["dimension_order"]),
            "dimension_ids": {item["id"] for item in codebook["dimensions"]},
            "evidence_states": {item["id"] for item in codebook["evidence_states"]},
            "modality_ids": {item["id"] for item in codebook["modalities"]},
        },
        {
            "contract_version": contract["contract_version"],
            "schema_version": contract["compatible_se_brl"]["schema_version"],
            "codebook_version": contract["compatible_se_brl"]["codebook_version"],
            "overall_statuses": set(contract["overall_statuses"]),
            "component_statuses": set(contract["component_statuses"]),
            "component_order": tuple(contract["components"]),
            "reason_applicability": {
                item["id"]: set(item["applies_to"]) for item in contract["reason_codes"]
            },
        },
    )


class DimensionAssessmentResponse(_SebrlResponseModel):
    dimension_id: NonEmptyText
    evidence_state: NonEmptyText

    @model_validator(mode="after")
    def validate_canonical_values(self) -> "DimensionAssessmentResponse":
        codebook, _ = _canonical_metadata()
        if self.dimension_id not in codebook["dimension_ids"]:
            raise ValueError("dimension_id is not canonical")
        if self.evidence_state not in codebook["evidence_states"]:
            raise ValueError("evidence_state is not canonical")
        return self


class ModalityAssessmentResponse(_SebrlResponseModel):
    codebook_version: NonEmptyText
    schema_version: NonEmptyText
    modality_id: NonEmptyText
    dimension_results: tuple[
        DimensionAssessmentResponse,
        DimensionAssessmentResponse,
        DimensionAssessmentResponse,
        DimensionAssessmentResponse,
    ]
    availability_mask: AvailabilityMask

    @model_validator(mode="after")
    def validate_canonical_assessment(self) -> "ModalityAssessmentResponse":
        codebook, contract = _canonical_metadata()
        if self.schema_version != codebook["schema_version"]:
            raise ValueError("schema_version is incompatible")
        if self.codebook_version != codebook["codebook_version"]:
            raise ValueError("codebook_version is incompatible")
        if self.schema_version != contract["schema_version"]:
            raise ValueError("schema_version is incompatible with the envelope contract")
        if self.codebook_version != contract["codebook_version"]:
            raise ValueError("codebook_version is incompatible with the envelope contract")
        if self.modality_id not in codebook["modality_ids"]:
            raise ValueError("modality_id is not canonical")

        actual_order = tuple(item.dimension_id for item in self.dimension_results)
        if actual_order != codebook["dimension_order"]:
            raise ValueError("dimension_results are not in canonical order")

        for result, availability in zip(
            self.dimension_results, self.availability_mask, strict=True
        ):
            if availability not in (0, 1):
                raise ValueError("availability_mask values must be 0 or 1")
            expected = 0 if result.evidence_state == "unavailable" else 1
            if availability != expected:
                raise ValueError("availability_mask conflicts with evidence_state")
        return self


class SebrlComponentResponse(_SebrlResponseModel):
    component_id: NonEmptyText
    status: NonEmptyText

    @model_validator(mode="after")
    def validate_canonical_component(self) -> "SebrlComponentResponse":
        _, contract = _canonical_metadata()
        if self.component_id not in set(contract["component_order"]):
            raise ValueError("component_id is not canonical")
        if self.status not in contract["component_statuses"]:
            raise ValueError("component status is not canonical")
        return self


class SebrlResultEnvelopeResponse(_SebrlResponseModel):
    contract_version: NonEmptyText
    se_brl_schema_version: NonEmptyText
    se_brl_codebook_version: NonEmptyText
    overall_status: NonEmptyText
    modality_id: NonEmptyText
    components: tuple[
        SebrlComponentResponse,
        SebrlComponentResponse,
        SebrlComponentResponse,
        SebrlComponentResponse,
        SebrlComponentResponse,
    ]
    assessment_result: ModalityAssessmentResponse | None
    reason_codes: tuple[NonEmptyText, ...]
    limitations: tuple[NonEmptyText, ...]

    @model_validator(mode="after")
    def validate_canonical_envelope(self) -> "SebrlResultEnvelopeResponse":
        codebook, contract = _canonical_metadata()
        if self.contract_version != contract["contract_version"]:
            raise ValueError("contract_version is incompatible")
        if self.se_brl_schema_version != contract["schema_version"]:
            raise ValueError("se_brl_schema_version is incompatible")
        if self.se_brl_codebook_version != contract["codebook_version"]:
            raise ValueError("se_brl_codebook_version is incompatible")
        if self.se_brl_schema_version != codebook["schema_version"]:
            raise ValueError("se_brl_schema_version is incompatible with the codebook")
        if self.se_brl_codebook_version != codebook["codebook_version"]:
            raise ValueError("se_brl_codebook_version is incompatible with the codebook")
        if self.overall_status not in contract["overall_statuses"]:
            raise ValueError("overall_status is not canonical")
        if self.modality_id not in codebook["modality_ids"]:
            raise ValueError("modality_id is not canonical")

        component_order = tuple(item.component_id for item in self.components)
        if component_order != contract["component_order"]:
            raise ValueError("components are missing, additional, duplicated, or incorrectly ordered")
        component_statuses = {item.component_id: item.status for item in self.components}

        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must not contain duplicates")
        applicability = contract["reason_applicability"]
        if any(reason not in applicability for reason in self.reason_codes):
            raise ValueError("reason_codes contain an unknown value")
        if any(self.overall_status not in applicability[reason] for reason in self.reason_codes):
            raise ValueError("a reason_code is not applicable to overall_status")

        if self.assessment_result is not None:
            assessment = self.assessment_result
            if assessment.modality_id != self.modality_id:
                raise ValueError("assessment modality does not match envelope modality")
            if assessment.schema_version != self.se_brl_schema_version:
                raise ValueError("assessment schema version does not match the envelope")
            if assessment.codebook_version != self.se_brl_codebook_version:
                raise ValueError("assessment codebook version does not match the envelope")
            if component_statuses["modality_assessment"] != "completed":
                raise ValueError("an assessment requires completed modality_assessment")
        elif component_statuses["modality_assessment"] == "completed":
            raise ValueError("completed modality_assessment requires assessment_result")

        self._validate_component_dependencies(component_statuses)
        self._validate_overall_status(component_statuses, contract)
        return self

    def _validate_component_dependencies(self, components: dict[str, str]) -> None:
        if components["risk_decision"] == "completed" and (
            components["probability_calibration"] != "completed"
            or components["phishing_classification"] != "completed"
        ):
            raise ValueError("completed risk_decision has incomplete dependencies")
        if (
            components["probability_calibration"] == "completed"
            and components["phishing_classification"] != "completed"
        ):
            raise ValueError("completed probability_calibration has incomplete dependencies")
        if (
            components["phishing_classification"] == "completed"
            and components["behavior_identification"] != "completed"
        ):
            raise ValueError("completed phishing_classification has incomplete dependencies")

    def _validate_overall_status(
        self, components: dict[str, str], contract: dict[str, Any]
    ) -> None:
        if self.overall_status == "completed":
            if any(status != "completed" for status in components.values()):
                raise ValueError("completed envelope contains partial component data")
            if self.assessment_result is None:
                raise ValueError("completed envelope requires assessment_result")
            if self.reason_codes or self.limitations:
                raise ValueError("completed envelope cannot contain reasons or limitations")
        elif self.overall_status == "not_evaluated":
            if "not_evaluated" not in components.values():
                raise ValueError("not_evaluated envelope has no not_evaluated component")
            required_reasons = {
                reason
                for reason, statuses in contract["reason_applicability"].items()
                if statuses == {"not_evaluated"}
            }
            if not required_reasons <= set(self.reason_codes):
                raise ValueError("not_evaluated envelope is missing required reason_codes")
            if not self.limitations:
                raise ValueError("not_evaluated envelope requires limitations")
        elif self.overall_status == "review_required":
            if all(status == "completed" for status in components.values()):
                raise ValueError("review_required envelope cannot have all components completed")
            if not self.reason_codes:
                raise ValueError("review_required envelope requires a reason_code")
            if not self.limitations:
                raise ValueError("review_required envelope requires limitations")
        elif self.overall_status == "failed":
            failure_reasons = {
                reason
                for reason, statuses in contract["reason_applicability"].items()
                if "failed" in statuses
            }
            if not failure_reasons <= set(self.reason_codes):
                raise ValueError("failed envelope is missing its canonical failure reason")
            if "failed" not in components.values():
                raise ValueError("failed envelope has no failed component")
            if not self.limitations:
                raise ValueError("failed envelope requires limitations")
