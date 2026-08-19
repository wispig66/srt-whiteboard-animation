from __future__ import annotations

from pathlib import Path

from PIL import Image

from srt_whiteboard import annotation_preview
from srt_whiteboard.models import SceneAnnotation


def test_preview_renders_without_an_os_font(
    tmp_path: Path, annotation_payload: dict, monkeypatch
) -> None:
    image_path = tmp_path / "scene.png"
    output_path = tmp_path / "preview.jpg"
    Image.new("RGB", (160, 90), "#F5EBD7").save(image_path)
    scene = SceneAnnotation.model_validate(annotation_payload)
    monkeypatch.setattr(annotation_preview, "find_font", lambda _explicit=None: None)

    result = annotation_preview.render_annotation_preview(image_path, scene, output_path)

    assert result == output_path.resolve()
    assert output_path.is_file()
