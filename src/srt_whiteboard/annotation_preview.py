"""Cross-platform static annotation preview rendering."""

from __future__ import annotations

import platform
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import SceneAnnotation, load_annotation

_FONT_CANDIDATES = {
    "Darwin": [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ],
    "Windows": [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "Linux": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def find_font(explicit: str | Path | None = None) -> Path | None:
    candidates = [Path(explicit)] if explicit else []
    candidates.extend(Path(path) for path in _FONT_CANDIDATES.get(platform.system(), []))
    return next((path for path in candidates if path.is_file()), None)


def _font(path: Path | None, size: int):
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)


def _draw_dashed_rectangle(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int],
    width: int = 3,
    dash: int = 12,
) -> None:
    left, top, right, bottom = bounds
    for start in range(left, right, dash * 2):
        draw.line((start, top, min(start + dash, right), top), fill=fill, width=width)
        draw.line((start, bottom, min(start + dash, right), bottom), fill=fill, width=width)
    for start in range(top, bottom, dash * 2):
        draw.line((left, start, left, min(start + dash, bottom)), fill=fill, width=width)
        draw.line((right, start, right, min(start + dash, bottom)), fill=fill, width=width)


def render_annotation_preview(
    image_path: str | Path,
    annotation: SceneAnnotation | str | Path,
    output_path: str | Path,
    *,
    font_path: str | Path | None = None,
) -> Path:
    scene = load_annotation(annotation) if not isinstance(annotation, SceneAnnotation) else annotation
    image = Image.open(image_path).convert("RGBA")
    scene.verify_image_size(*image.size)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    resolved_font = find_font(font_path)
    label_font = _font(resolved_font, max(14, round(image.width / 90)))
    number_font = _font(resolved_font, max(14, round(image.width / 100)))
    colors = [
        (38, 103, 255, 225),
        (255, 105, 92, 225),
        (41, 167, 102, 225),
        (181, 100, 255, 225),
    ]

    for index, element in enumerate(scene.elements, start=1):
        region = element.region
        right, bottom = region.right, region.bottom
        color = colors[(index - 1) % len(colors)]
        draw.rounded_rectangle(
            (region.x, region.y, right, bottom),
            radius=12,
            outline=color,
            width=4,
            fill=(*color[:3], 24),
        )
        badge = max(28, round(image.width / 50))
        draw.ellipse(
            (region.x + 8, region.y + 8, region.x + 8 + badge, region.y + 8 + badge),
            fill=color,
        )
        draw.text(
            (region.x + 8 + badge / 2, region.y + 8 + badge / 2),
            str(index),
            anchor="mm",
            font=number_font,
            fill="white",
        )
        label = (
            f"{index}. {element.label}  "
            f"{element.timing.start_ms / 1000:.1f}s–{element.timing.end_ms / 1000:.1f}s"
        )
        text_x, text_y = region.x + 16 + badge, region.y + 10
        draw.rounded_rectangle(
            (text_x - 6, text_y - 4, min(right - 6, text_x + len(label) * 20), text_y + badge),
            radius=6,
            fill=(255, 255, 255, 225),
        )
        draw.text((text_x, text_y), label, font=label_font, fill=color)
        for protected in element.protected_regions:
            _draw_dashed_rectangle(
                draw,
                (protected.x, protected.y, protected.right, protected.bottom),
                fill=(220, 38, 38, 230),
            )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(destination, quality=95)
    return destination.resolve()
