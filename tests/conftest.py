from __future__ import annotations

import copy

import pytest


@pytest.fixture
def annotation_payload() -> dict:
    return {
        "schemaVersion": 2,
        "sceneId": "scene-01",
        "canvas": {"width": 160, "height": 90},
        "storyBasis": "A simple two-part scene.",
        "sceneDurationMs": 1500,
        "holdMs": 500,
        "elements": [
            {
                "id": "left",
                "label": "Left subject",
                "narrativeRole": "Establishes the scene",
                "subtitle": "The first subtitle.",
                "region": {"x": 0, "y": 0, "width": 90, "height": 90},
                "timing": {"startMs": 100, "durationMs": 400},
                "protectedRegions": [
                    {"x": 70, "y": 30, "width": 10, "height": 10}
                ],
            },
            {
                "id": "right",
                "label": "Right subject",
                "narrativeRole": "Completes the action",
                "subtitle": "The second subtitle.",
                "region": {"x": 80, "y": 0, "width": 80, "height": 90},
                "timing": {"startMs": 600, "durationMs": 400},
                "protectedRegions": [],
            },
        ],
    }


@pytest.fixture
def payload_copy(annotation_payload: dict):
    return lambda: copy.deepcopy(annotation_payload)
