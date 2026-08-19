"""Versioned annotation model and cross-field invariants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
StartMs = Annotated[int, Field(strict=True, ge=100)]
DurationMs = Annotated[int, Field(strict=True, ge=100)]


class AnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class Canvas(AnnotationModel):
    width: PositiveInt
    height: PositiveInt


class Rectangle(AnnotationModel):
    x: NonNegativeInt
    y: NonNegativeInt
    width: PositiveInt
    height: PositiveInt

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def is_within(self, canvas: Canvas) -> bool:
        return self.right <= canvas.width and self.bottom <= canvas.height


class Timing(AnnotationModel):
    start_ms: StartMs = Field(alias="startMs")
    duration_ms: DurationMs = Field(alias="durationMs")

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


class Element(AnnotationModel):
    id: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    narrative_role: Annotated[str, Field(min_length=1, max_length=240)] = Field(
        alias="narrativeRole"
    )
    subtitle: Annotated[str, Field(min_length=1)]
    region: Rectangle
    timing: Timing
    protected_regions: list[Rectangle] = Field(default_factory=list, alias="protectedRegions")


class SceneAnnotation(AnnotationModel):
    """Schema v2. Array order is the only narrative/drawing order."""

    schema_version: Literal[2] = Field(alias="schemaVersion")
    scene_id: Annotated[str, Field(min_length=1, max_length=120)] = Field(alias="sceneId")
    canvas: Canvas
    story_basis: Annotated[str, Field(min_length=1)] = Field(alias="storyBasis")
    scene_duration_ms: PositiveInt = Field(alias="sceneDurationMs")
    hold_ms: Annotated[int, Field(strict=True, ge=500, le=10_000)] = Field(
        default=500, alias="holdMs"
    )
    elements: Annotated[list[Element], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_scene_invariants(self) -> SceneAnnotation:
        ids: set[str] = set()
        previous_end = 0
        for index, element in enumerate(self.elements, start=1):
            if element.id in ids:
                raise ValueError(f"elements[{index - 1}].id duplicates {element.id!r}")
            ids.add(element.id)
            if not element.region.is_within(self.canvas):
                raise ValueError(f"element {element.id!r} region exceeds canvas bounds")
            for protected in element.protected_regions:
                if not protected.is_within(self.canvas):
                    raise ValueError(
                        f"element {element.id!r} protected region exceeds canvas bounds"
                    )
            if index > 1 and element.timing.start_ms < previous_end:
                raise ValueError(
                    f"element {element.id!r} starts at {element.timing.start_ms}ms before "
                    f"the previous element ends at {previous_end}ms"
                )
            previous_end = element.timing.end_ms

        required_duration = previous_end + self.hold_ms
        if self.scene_duration_ms < required_duration:
            raise ValueError(
                f"sceneDurationMs must be at least {required_duration}ms "
                f"(last element end + holdMs)"
            )
        return self

    def verify_image_size(self, width: int, height: int) -> None:
        if (width, height) != (self.canvas.width, self.canvas.height):
            raise ValueError(
                "annotation canvas does not match image pixels: "
                f"annotation={self.canvas.width}x{self.canvas.height}, image={width}x{height}"
            )

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)


def load_annotation(path: str | Path) -> SceneAnnotation:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read annotation {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}: {exc}") from exc
    try:
        return SceneAnnotation.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid annotation {source}:\n{exc}") from exc


def annotation_schema() -> dict:
    schema = SceneAnnotation.model_json_schema(by_alias=True)
    schema["$id"] = "https://github.com/wispig66/srt-whiteboard-animation/annotation-v2.schema.json"
    schema["title"] = "SRT Whiteboard Annotation v2"
    return schema
