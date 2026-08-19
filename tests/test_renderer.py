from __future__ import annotations

import shutil
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw

from srt_whiteboard import media
from srt_whiteboard.models import SceneAnnotation
from srt_whiteboard.renderer import RegionStreamRenderer, render_file
from srt_whiteboard.strokes import Config


def test_allowed_mask_subtracts_later_and_protected_regions(annotation_payload: dict) -> None:
    scene = SceneAnnotation.model_validate(annotation_payload)
    image = np.full((90, 160, 3), 245, dtype=np.uint8)
    renderer = RegionStreamRenderer(image, scene, Config(cap_long_edge=160), None, True)
    mask = renderer._allowed_mask(scene.elements[0], scene.elements[1:])
    assert mask[10, 10]
    assert not mask[10, 85]
    assert not mask[35, 75]


def test_render_has_exact_frames_and_clean_opening(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "scene.png"
    annotation_path = tmp_path / "scene.annotation.json"
    output_path = tmp_path / "scene.mp4"

    image = Image.new("RGB", (160, 90), "#F5EBD7")
    draw = ImageDraw.Draw(image)
    draw.line((20, 20, 130, 70), fill="#222222", width=4)
    image.save(image_path)
    payload = {
        "schemaVersion": 2,
        "sceneId": "smoke",
        "canvas": {"width": 160, "height": 90},
        "storyBasis": "Render smoke test.",
        "sceneDurationMs": 1000,
        "holdMs": 500,
        "elements": [
            {
                "id": "line",
                "label": "Line",
                "narrativeRole": "Draws the test line",
                "subtitle": "Draw a line.",
                "region": {"x": 0, "y": 0, "width": 160, "height": 90},
                "timing": {"startMs": 100, "durationMs": 400},
                "protectedRegions": [],
            }
        ],
    }
    scene = SceneAnnotation.model_validate(payload)
    annotation_path.write_text(scene.to_json(), encoding="utf-8")

    monkeypatch.setattr(media.shutil, "which", lambda _command: None)
    render_file(
        image_path,
        annotation_path,
        output_path,
        bare_tip=True,
        fps=10,
        cap_long_edge=160,
    )

    container = av.open(str(output_path))
    frames = list(container.decode(video=0))
    codec = container.streams.video[0].codec_context.name
    container.close()
    assert codec == "h264"
    assert len(frames) == 10
    first = frames[0].to_ndarray(format="bgr24")
    expected = np.array([0xD7, 0xEB, 0xF5], dtype=np.int16)
    assert np.abs(first.astype(np.int16) - expected).mean() < 8

    second_path = tmp_path / "scene-02.mp4"
    merged_path = tmp_path / "merged.mp4"
    shutil.copyfile(output_path, second_path)
    media.merge_scenes([output_path, second_path], merged_path)
    merged_container = av.open(str(merged_path))
    merged_frames = list(merged_container.decode(video=0))
    merged_container.close()
    assert len(merged_frames) == 20
