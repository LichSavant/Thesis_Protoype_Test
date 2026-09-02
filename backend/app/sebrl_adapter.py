"""Safe conversion from the immutable SE-BRL domain envelope to API data."""

from pydantic import ValidationError

from ml.se_brl import (
    CodebookLoadError,
    CodebookValidationError,
    ResultEnvelope,
    ResultEnvelopeLoadError,
    ResultEnvelopeValidationError,
    serialize_result_envelope,
)

from .sebrl_schemas import SebrlResultEnvelopeResponse


class SebrlApiContractError(ValueError):
    """Raised when a domain result cannot safely cross the backend boundary."""


def to_sebrl_api_response(envelope: ResultEnvelope) -> SebrlResultEnvelopeResponse:
    """Return a fresh, validated API response without mutating the domain value."""

    if not isinstance(envelope, ResultEnvelope):
        raise SebrlApiContractError("Expected an SE-BRL ResultEnvelope")

    serialized = serialize_result_envelope(envelope)
    try:
        return SebrlResultEnvelopeResponse.model_validate(serialized)
    except (
        ValidationError,
        CodebookLoadError,
        CodebookValidationError,
        ResultEnvelopeLoadError,
        ResultEnvelopeValidationError,
    ):
        raise SebrlApiContractError(
            "SE-BRL result is incompatible with the backend API contract"
        ) from None
