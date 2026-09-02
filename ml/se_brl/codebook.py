"""Load and validate the canonical, versioned SE-BRL codebook.

The JSON document is the sole runtime source for taxonomy, evidence-state,
modality, and vector-ordering definitions. This module contains structural and
compatibility checks only; it performs no behavioral detection or inference.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any


class CodebookLoadError(RuntimeError):
    """Raised when a codebook file cannot be read or decoded."""


class CodebookValidationError(ValueError):
    """Raised when a codebook violates the approved schema or taxonomy."""


def _canonical_path() -> Path:
    return Path(__file__).with_name("codebook.v0.1.0.json")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError as error:
        raise CodebookLoadError(f"SE-BRL codebook file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CodebookLoadError(
            f"Malformed SE-BRL codebook JSON at line {error.lineno}, column {error.colno}: {path}"
        ) from error
    except OSError as error:
        raise CodebookLoadError(f"Unable to read SE-BRL codebook: {path}") from error
    if not isinstance(document, dict):
        raise CodebookValidationError("The SE-BRL codebook root must be a JSON object")
    return document


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CodebookValidationError(f"{location} must be an object")
    return value


def _sequence(value: Any, location: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise CodebookValidationError(f"{location} must be an array")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodebookValidationError(f"{location} must be a non-empty string")
    return value


def _text_list(value: Any, location: str) -> tuple[str, ...]:
    values = _sequence(value, location)
    if not values:
        raise CodebookValidationError(f"{location} must not be empty")
    return tuple(_text(item, f"{location}[{index}]") for index, item in enumerate(values))


def _unique_ids(items: Sequence[Any], location: str) -> tuple[str, ...]:
    identifiers: list[str] = []
    for index, item in enumerate(items):
        entry = _mapping(item, f"{location}[{index}]")
        identifiers.append(_text(entry.get("id"), f"{location}[{index}].id"))
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise CodebookValidationError(f"Duplicate IDs in {location}: {', '.join(duplicates)}")
    return tuple(identifiers)


def _reference_ids(reference: Mapping[str, Any], section: str) -> tuple[str, ...]:
    return _unique_ids(_sequence(reference.get(section), section), section)


def _validate_versions(document: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    for field in ("schema_version", "codebook_version"):
        actual = _text(document.get(field), field)
        expected = _text(reference.get(field), f"canonical.{field}")
        if actual != expected:
            raise CodebookValidationError(
                f"Incompatible {field.replace('_', ' ')} {actual!r}; expected {expected!r}"
            )


def _validate_instrument(document: Mapping[str, Any]) -> None:
    instrument = _mapping(document.get("instrument"), "instrument")
    for field in ("id", "name", "status", "description"):
        _text(instrument.get(field), f"instrument.{field}")
    _text_list(instrument.get("deferred_protocol_details"), "instrument.deferred_protocol_details")


def _validate_dimensions(
    document: Mapping[str, Any], reference: Mapping[str, Any]
) -> tuple[tuple[str, ...], dict[str, str]]:
    dimensions = _sequence(document.get("dimensions"), "dimensions")
    if len(dimensions) != 4:
        raise CodebookValidationError(f"SE-BRL requires exactly 4 dimensions; found {len(dimensions)}")
    dimension_ids = _unique_ids(dimensions, "dimensions")
    if set(dimension_ids) != set(_reference_ids(reference, "dimensions")):
        raise CodebookValidationError("Unknown or missing SE-BRL dimension ID")

    reference_dimensions = {
        _text(item.get("id"), "canonical.dimension.id"): item
        for item in (
            _mapping(raw, "canonical.dimension")
            for raw in _sequence(reference.get("dimensions"), "canonical.dimensions")
        )
    }

    indicator_parents: dict[str, str] = {}
    for dimension_index, raw_dimension in enumerate(dimensions):
        dimension = _mapping(raw_dimension, f"dimensions[{dimension_index}]")
        dimension_id = dimension_ids[dimension_index]
        reference_dimension = reference_dimensions[dimension_id]
        name = _text(dimension.get("name"), f"dimensions[{dimension_index}].name")
        boundaries = _text_list(dimension.get("qualifying_boundary"), f"dimensions[{dimension_index}].qualifying_boundary")
        exclusions = _text_list(dimension.get("exclusions"), f"dimensions[{dimension_index}].exclusions")
        if name != reference_dimension.get("name"):
            raise CodebookValidationError(f"Dimension name mismatch for {dimension_id!r}")
        if boundaries != tuple(reference_dimension.get("qualifying_boundary", ())):
            raise CodebookValidationError(f"Qualifying boundary mismatch for {dimension_id!r}")
        if exclusions != tuple(reference_dimension.get("exclusions", ())):
            raise CodebookValidationError(f"Exclusion mismatch for {dimension_id!r}")
        reference_indicators = {
            _text(item.get("id"), "canonical.indicator.id"): item
            for item in (
                _mapping(raw, "canonical.indicator")
                for raw in _sequence(reference_dimension.get("indicators"), "canonical.dimension.indicators")
            )
        }
        indicators = _sequence(dimension.get("indicators"), f"dimensions[{dimension_index}].indicators")
        indicator_ids = _unique_ids(indicators, f"dimensions[{dimension_index}].indicators")
        for indicator_index, raw_indicator in enumerate(indicators):
            indicator = _mapping(raw_indicator, f"dimensions[{dimension_index}].indicators[{indicator_index}]")
            indicator_id = indicator_ids[indicator_index]
            indicator_name = _text(indicator.get("name"), f"dimensions[{dimension_index}].indicators[{indicator_index}].name")
            if indicator_id in reference_indicators and indicator_name != reference_indicators[indicator_id].get("name"):
                raise CodebookValidationError(f"Indicator name mismatch for {indicator_id!r}")
            if indicator_id in indicator_parents:
                raise CodebookValidationError(
                    f"Indicator {indicator_id!r} is assigned to multiple dimensions"
                )
            indicator_parents[indicator_id] = dimension_id

    if len(indicator_parents) != 12:
        raise CodebookValidationError(
            f"SE-BRL requires exactly 12 unique indicators; found {len(indicator_parents)}"
        )

    reference_parents: dict[str, str] = {}
    for parent_id, dimension in reference_dimensions.items():
        for raw_indicator in _sequence(dimension.get("indicators"), "canonical.dimension.indicators"):
            indicator = _mapping(raw_indicator, "canonical.indicator")
            reference_parents[_text(indicator.get("id"), "canonical.indicator.id")] = parent_id
    if set(indicator_parents) != set(reference_parents):
        raise CodebookValidationError("Unknown or missing SE-BRL indicator ID")
    if indicator_parents != reference_parents:
        raise CodebookValidationError("An indicator has an incorrect parent dimension")
    return dimension_ids, indicator_parents


def _validate_named_definitions(
    document: Mapping[str, Any], reference: Mapping[str, Any], section: str, expected_count: int
) -> tuple[str, ...]:
    entries = _sequence(document.get(section), section)
    if len(entries) != expected_count:
        raise CodebookValidationError(
            f"{section} must contain exactly {expected_count} entries; found {len(entries)}"
        )
    identifiers = _unique_ids(entries, section)
    reference_entries = {
        _text(entry.get("id"), f"canonical.{section}.id"): _text(
            entry.get("definition"), f"canonical.{section}.definition"
        )
        for entry in (_mapping(item, f"canonical.{section}") for item in _sequence(reference.get(section), f"canonical.{section}"))
    }
    if set(identifiers) != set(reference_entries):
        raise CodebookValidationError(f"Unknown, missing, or additional entry in {section}")
    for index, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, f"{section}[{index}]")
        identifier = identifiers[index]
        definition = _text(entry.get("definition"), f"{section}[{index}].definition")
        if definition != reference_entries[identifier]:
            raise CodebookValidationError(f"Definition mismatch for {section} entry {identifier!r}")
    return identifiers


def _validate_modalities(
    document: Mapping[str, Any],
    reference: Mapping[str, Any],
    dimension_ids: tuple[str, ...],
    support_codes: tuple[str, ...],
) -> None:
    modalities = _sequence(document.get("modalities"), "modalities")
    if len(modalities) != 4:
        raise CodebookValidationError(f"modalities must contain exactly 4 entries; found {len(modalities)}")
    modality_ids = _unique_ids(modalities, "modalities")
    if set(modality_ids) != set(_reference_ids(reference, "modalities")):
        raise CodebookValidationError("Unknown, missing, or additional modality")

    reference_modalities = {
        _text(item.get("id"), "canonical.modality.id"): item
        for item in (_mapping(raw, "canonical.modality") for raw in _sequence(reference.get("modalities"), "canonical.modalities"))
    }
    unavailable_codes = [
        _text(item.get("id"), "support_codes.id")
        for item in (_mapping(raw, "support_codes") for raw in _sequence(document.get("support_codes"), "support_codes"))
        if item.get("assessment_kind") == "unavailable"
    ]
    if len(unavailable_codes) != 1:
        raise CodebookValidationError("Exactly one support code must represent unavailable assessment")
    unavailable_code = unavailable_codes[0]

    for index, raw_modality in enumerate(modalities):
        modality = _mapping(raw_modality, f"modalities[{index}]")
        modality_id = modality_ids[index]
        modality_name = _text(modality.get("name"), f"modalities[{index}].name")
        evidence_rule = _text(modality.get("required_evidence_rule"), f"modalities[{index}].required_evidence_rule")
        reference_modality = reference_modalities[modality_id]
        if modality_name != reference_modality.get("name"):
            raise CodebookValidationError(f"Modality name mismatch for {modality_id!r}")
        if evidence_rule != reference_modality.get("required_evidence_rule"):
            raise CodebookValidationError(f"Required-evidence rule mismatch for {modality_id!r}")
        support = _mapping(modality.get("support_by_dimension"), f"modalities[{index}].support_by_dimension")
        if set(support) != set(dimension_ids):
            raise CodebookValidationError(
                f"Incomplete or unknown dimension mapping for modality {modality_id!r}"
            )
        invalid_codes = sorted({value for value in support.values() if value not in support_codes})
        if invalid_codes:
            raise CodebookValidationError(
                f"Invalid modality support code(s) for {modality_id!r}: {', '.join(map(str, invalid_codes))}"
            )
        reference_support = _mapping(
            reference_modality.get("support_by_dimension"), "canonical.modality.support_by_dimension"
        )
        if dict(support) != dict(reference_support):
            raise CodebookValidationError(f"Incorrect modality-support matrix for {modality_id!r}")
        if modality_id in {"standalone_url", "engineered_technical_record"} and any(
            value != unavailable_code for value in support.values()
        ):
            raise CodebookValidationError(f"{modality_id!r} must mark every behavioral dimension unavailable")


def _validate_vector_ordering(
    document: Mapping[str, Any], reference: Mapping[str, Any], dimension_ids: tuple[str, ...]
) -> None:
    vector = _mapping(document.get("vector_ordering"), "vector_ordering")
    reference_vector = _mapping(reference.get("vector_ordering"), "canonical.vector_ordering")
    dimension_order = tuple(
        _text(item, f"vector_ordering.dimension_order[{index}]")
        for index, item in enumerate(_sequence(vector.get("dimension_order"), "vector_ordering.dimension_order"))
    )
    if dimension_order != dimension_ids or dimension_order != tuple(reference_vector.get("dimension_order", ())):
        raise CodebookValidationError("Incorrect SE-BRL dimension/vector-slot ordering")

    structure = tuple(
        _text(item, f"vector_ordering.future_structure[{index}]")
        for index, item in enumerate(_sequence(vector.get("future_structure"), "vector_ordering.future_structure"))
    )
    confidence = tuple(
        _text(item, f"vector_ordering.confidence_slots[{index}]")
        for index, item in enumerate(_sequence(vector.get("confidence_slots"), "vector_ordering.confidence_slots"))
    )
    availability = tuple(
        _text(item, f"vector_ordering.availability_slots[{index}]")
        for index, item in enumerate(_sequence(vector.get("availability_slots"), "vector_ordering.availability_slots"))
    )
    if structure != tuple(reference_vector.get("future_structure", ())):
        raise CodebookValidationError("Incorrect future SE-BRL vector structure")
    if confidence + availability != structure or len(confidence) != 4 or len(availability) != 4:
        raise CodebookValidationError("SE-BRL vector slots must contain four confidence slots followed by four availability slots")
    if vector.get("implementation_status") != "metadata_only":
        raise CodebookValidationError("SE-BRL vector metadata must remain metadata-only")
    _text(vector.get("note"), "vector_ordering.note")


def _validate_document(document: Mapping[str, Any], reference: Mapping[str, Any]) -> None:
    required_sections = {
        "schema_version",
        "codebook_version",
        "instrument",
        "dimensions",
        "evidence_states",
        "support_codes",
        "modalities",
        "vector_ordering",
    }
    missing = sorted(required_sections - set(document))
    if missing:
        raise CodebookValidationError(f"Missing required top-level section(s): {', '.join(missing)}")
    _validate_versions(document, reference)
    _validate_instrument(document)
    dimension_ids, _ = _validate_dimensions(document, reference)
    _validate_named_definitions(document, reference, "evidence_states", 3)
    support_codes = _validate_named_definitions(document, reference, "support_codes", 3)
    reference_support_codes = {
        _text(item.get("id"), "canonical.support_codes.id"): item
        for item in (
            _mapping(raw, "canonical.support_codes")
            for raw in _sequence(reference.get("support_codes"), "canonical.support_codes")
        )
    }
    for index, raw_code in enumerate(_sequence(document.get("support_codes"), "support_codes")):
        code = _mapping(raw_code, f"support_codes[{index}]")
        code_id = _text(code.get("id"), f"support_codes[{index}].id")
        assessment_kind = _text(code.get("assessment_kind"), f"support_codes[{index}].assessment_kind")
        if assessment_kind != reference_support_codes[code_id].get("assessment_kind"):
            raise CodebookValidationError(f"Assessment-kind mismatch for support code {code_id!r}")
    _validate_modalities(document, reference, dimension_ids, support_codes)
    _validate_vector_ordering(document, reference, dimension_ids)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load_codebook(path: str | Path | None = None) -> Mapping[str, Any]:
    """Load, validate, and recursively freeze the canonical or a candidate codebook.

    Candidate files are checked for compatibility against the canonical JSON so
    altered test documents cannot introduce unknown taxonomy or versions.
    """

    canonical_path = _canonical_path()
    reference = _read_json(canonical_path)
    target_path = canonical_path if path is None else Path(path)
    document = reference if target_path.resolve() == canonical_path.resolve() else _read_json(target_path)
    _validate_document(document, reference)
    return _freeze(document)
