from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from srt_whiteboard.models import SceneAnnotation, annotation_schema


def test_valid_scene_and_alias_serialization(annotation_payload: dict) -> None:
    scene = SceneAnnotation.model_validate(annotation_payload)
    dumped = scene.model_dump(by_alias=True)
    assert dumped["schemaVersion"] == 2
    assert [element["id"] for element in dumped["elements"]] == ["left", "right"]
    assert "sequence" not in dumped["elements"][0]


@pytest.mark.parametrize("legacy_field", ["sequence", "reveal", "handPath", "type"])
def test_legacy_fields_fail_closed(payload_copy, legacy_field: str) -> None:
    payload = payload_copy()
    payload["elements"][0][legacy_field] = 1
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneAnnotation.model_validate(payload)


def test_overlap_is_rejected(payload_copy) -> None:
    payload = payload_copy()
    payload["elements"][1]["timing"]["startMs"] = 400
    with pytest.raises(ValidationError, match="before the previous element ends"):
        SceneAnnotation.model_validate(payload)


def test_out_of_bounds_region_is_rejected(payload_copy) -> None:
    payload = payload_copy()
    payload["elements"][0]["region"]["width"] = 200
    with pytest.raises(ValidationError, match="exceeds canvas bounds"):
        SceneAnnotation.model_validate(payload)


def test_scene_must_include_final_hold(payload_copy) -> None:
    payload = payload_copy()
    payload["sceneDurationMs"] = 1400
    with pytest.raises(ValidationError, match=r"last element end \+ holdMs"):
        SceneAnnotation.model_validate(payload)


def test_first_element_leaves_a_clean_opening_frame(payload_copy) -> None:
    payload = payload_copy()
    payload["elements"][0]["timing"]["startMs"] = 0
    with pytest.raises(ValidationError):
        SceneAnnotation.model_validate(payload)


def test_json_schema_is_v2() -> None:
    schema = annotation_schema()
    assert schema["title"] == "SRT Whiteboard Annotation v2"
    assert schema["properties"]["schemaVersion"]["const"] == 2


def test_checked_in_json_schema_matches_model() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "srt_whiteboard"
        / "schemas"
        / "annotation-v2.schema.json"
    )
    assert json.loads(path.read_text(encoding="utf-8")) == annotation_schema()
