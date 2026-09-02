import copy
import json
from pathlib import Path

import pytest

from ml.se_brl import CodebookLoadError, CodebookValidationError, load_codebook


EXPECTED_DIMENSIONS = (
    "pressure_threat_cues",
    "lure_attention_cues",
    "trust_identity_manipulation",
    "requested_action_consequence",
)
EXPECTED_PARENTS = {
    "urgency": "pressure_threat_cues",
    "fear_threat": "pressure_threat_cues",
    "scarcity": "pressure_threat_cues",
    "curiosity": "lure_attention_cues",
    "reward_lure": "lure_attention_cues",
    "authority": "trust_identity_manipulation",
    "impersonation": "trust_identity_manipulation",
    "brand_exploitation": "trust_identity_manipulation",
    "confidentiality_isolation": "trust_identity_manipulation",
    "call_to_action": "requested_action_consequence",
    "credential_sensitive_data_request": "requested_action_consequence",
    "financial_action_request": "requested_action_consequence",
}
EXPECTED_MODALITIES = {
    "content_bearing_email": ("A", "A", "A*", "A"),
    "content_bearing_webpage": ("A", "A", "A*", "A"),
    "standalone_url": ("U", "U", "U", "U"),
    "engineered_technical_record": ("U", "U", "U", "U"),
}


@pytest.fixture()
def canonical_document() -> dict:
    path = Path(__file__).parents[1] / "se_brl" / "codebook.v0.1.0.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_candidate(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loads_approved_codebook_as_read_only_structure() -> None:
    codebook = load_codebook()
    assert codebook["schema_version"] == "1.0.0"
    assert codebook["codebook_version"] == "0.1.0"
    with pytest.raises(TypeError):
        codebook["schema_version"] = "changed"


def test_has_exact_dimension_indicator_counts_ids_and_parents() -> None:
    codebook = load_codebook()
    dimensions = codebook["dimensions"]
    assert tuple(dimension["id"] for dimension in dimensions) == EXPECTED_DIMENSIONS
    parents = {
        indicator["id"]: dimension["id"]
        for dimension in dimensions
        for indicator in dimension["indicators"]
    }
    assert len(dimensions) == 4
    assert len(parents) == 12
    assert parents == EXPECTED_PARENTS
    assert "social_proof" not in parents


def test_has_exact_evidence_states() -> None:
    states = load_codebook()["evidence_states"]
    assert tuple(state["id"] for state in states) == ("supported", "absent", "unavailable")
    assert len({state["definition"] for state in states}) == 3


def test_has_exact_modalities_and_support_matrix() -> None:
    codebook = load_codebook()
    dimension_order = codebook["vector_ordering"]["dimension_order"]
    actual = {
        modality["id"]: tuple(modality["support_by_dimension"][dimension] for dimension in dimension_order)
        for modality in codebook["modalities"]
    }
    assert actual == EXPECTED_MODALITIES
    assert {code["id"] for code in codebook["support_codes"]} == {"A", "A*", "U"}


def test_url_and_engineered_record_are_all_unavailable() -> None:
    codebook = load_codebook()
    modalities = {modality["id"]: modality for modality in codebook["modalities"]}
    for modality_id in ("standalone_url", "engineered_technical_record"):
        assert set(modalities[modality_id]["support_by_dimension"].values()) == {"U"}


def test_has_exact_future_vector_order() -> None:
    vector = load_codebook()["vector_ordering"]
    assert vector["dimension_order"] == EXPECTED_DIMENSIONS
    assert vector["future_structure"] == ("z1", "z2", "z3", "z4", "a1", "a2", "a3", "a4")
    assert vector["implementation_status"] == "metadata_only"


@pytest.mark.parametrize(
    "section",
    ("schema_version", "codebook_version", "instrument", "dimensions", "evidence_states", "support_codes", "modalities", "vector_ordering"),
)
def test_rejects_missing_required_sections(tmp_path: Path, canonical_document: dict, section: str) -> None:
    del canonical_document[section]
    with pytest.raises(CodebookValidationError, match="Missing required"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_duplicate_dimensions(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["dimensions"][1]["id"] = canonical_document["dimensions"][0]["id"]
    with pytest.raises(CodebookValidationError, match="Duplicate IDs"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_unknown_dimension(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["dimensions"][0]["id"] = "unknown_dimension"
    with pytest.raises(CodebookValidationError, match="Unknown or missing.*dimension"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_duplicate_indicators(tmp_path: Path, canonical_document: dict) -> None:
    indicators = canonical_document["dimensions"][0]["indicators"]
    indicators.append(copy.deepcopy(indicators[0]))
    with pytest.raises(CodebookValidationError, match="Duplicate IDs"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_indicator_assigned_to_multiple_parents(tmp_path: Path, canonical_document: dict) -> None:
    indicator = copy.deepcopy(canonical_document["dimensions"][0]["indicators"][0])
    canonical_document["dimensions"][1]["indicators"].append(indicator)
    with pytest.raises(CodebookValidationError, match="multiple dimensions"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_incorrect_parent_ownership(tmp_path: Path, canonical_document: dict) -> None:
    first = canonical_document["dimensions"][0]["indicators"].pop(0)
    second = canonical_document["dimensions"][1]["indicators"].pop(0)
    canonical_document["dimensions"][0]["indicators"].append(second)
    canonical_document["dimensions"][1]["indicators"].append(first)
    with pytest.raises(CodebookValidationError, match="incorrect parent"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_unknown_indicator(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["dimensions"][0]["indicators"][0]["id"] = "unknown_indicator"
    with pytest.raises(CodebookValidationError, match="Unknown or missing.*indicator"):
        load_codebook(write_candidate(tmp_path, canonical_document))


@pytest.mark.parametrize("field", ("name", "qualifying_boundary", "exclusions"))
def test_rejects_missing_dimension_definition(tmp_path: Path, canonical_document: dict, field: str) -> None:
    del canonical_document["dimensions"][0][field]
    with pytest.raises(CodebookValidationError):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_changed_dimension_boundary(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["dimensions"][0]["qualifying_boundary"][0] = "Changed boundary"
    with pytest.raises(CodebookValidationError, match="boundary mismatch"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_changed_indicator_name(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["dimensions"][0]["indicators"][0]["name"] = "Changed name"
    with pytest.raises(CodebookValidationError, match="Indicator name mismatch"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_invalid_evidence_state(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["evidence_states"][0]["id"] = "unknown"
    with pytest.raises(CodebookValidationError, match="evidence_states"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_additional_evidence_state(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["evidence_states"].append({"id": "unknown", "definition": "Unknown"})
    with pytest.raises(CodebookValidationError, match="exactly 3"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_changed_evidence_state_definition(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["evidence_states"][0]["definition"] = "Changed definition"
    with pytest.raises(CodebookValidationError, match="Definition mismatch"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_additional_modality(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["modalities"].append(copy.deepcopy(canonical_document["modalities"][0]))
    canonical_document["modalities"][-1]["id"] = "unknown_modality"
    with pytest.raises(CodebookValidationError, match="exactly 4"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_invalid_modality_support_code(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["modalities"][0]["support_by_dimension"]["pressure_threat_cues"] = "X"
    with pytest.raises(CodebookValidationError, match="Invalid modality support code"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_changed_modality_rule(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["modalities"][0]["required_evidence_rule"] = "Changed rule"
    with pytest.raises(CodebookValidationError, match="Required-evidence rule mismatch"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_changed_support_code_semantics(tmp_path: Path, canonical_document: dict) -> None:
    canonical_document["support_codes"][0]["assessment_kind"] = "changed"
    with pytest.raises(CodebookValidationError, match="Assessment-kind mismatch"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_incomplete_modality_mapping(tmp_path: Path, canonical_document: dict) -> None:
    del canonical_document["modalities"][0]["support_by_dimension"]["pressure_threat_cues"]
    with pytest.raises(CodebookValidationError, match="Incomplete"):
        load_codebook(write_candidate(tmp_path, canonical_document))


@pytest.mark.parametrize("modality_index", (2, 3))
def test_rejects_behavioral_support_for_technical_modalities(
    tmp_path: Path, canonical_document: dict, modality_index: int
) -> None:
    canonical_document["modalities"][modality_index]["support_by_dimension"]["pressure_threat_cues"] = "A"
    with pytest.raises(CodebookValidationError, match="modality-support matrix|unavailable"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_incorrect_vector_order(tmp_path: Path, canonical_document: dict) -> None:
    order = canonical_document["vector_ordering"]["dimension_order"]
    order[0], order[1] = order[1], order[0]
    with pytest.raises(CodebookValidationError, match="vector-slot ordering"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_incorrect_future_vector_structure(tmp_path: Path, canonical_document: dict) -> None:
    structure = canonical_document["vector_ordering"]["future_structure"]
    structure[0], structure[1] = structure[1], structure[0]
    with pytest.raises(CodebookValidationError, match="future SE-BRL vector structure"):
        load_codebook(write_candidate(tmp_path, canonical_document))


@pytest.mark.parametrize("field", ("schema_version", "codebook_version"))
def test_rejects_incompatible_version(tmp_path: Path, canonical_document: dict, field: str) -> None:
    canonical_document[field] = "99.0.0"
    with pytest.raises(CodebookValidationError, match="Incompatible"):
        load_codebook(write_candidate(tmp_path, canonical_document))


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CodebookLoadError, match="not found"):
        load_codebook(tmp_path / "missing.json")


def test_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text('{"schema_version":', encoding="utf-8")
    with pytest.raises(CodebookLoadError, match="Malformed"):
        load_codebook(path)
