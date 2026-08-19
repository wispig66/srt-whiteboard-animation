"""Standards-tolerant SRT parsing and globally optimized scene grouping."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import srt

_SENTENCE_END = re.compile(r"[。！？.!?…][\"'”’）)]*$")


@dataclass(frozen=True, slots=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "durationMs": self.duration_ms,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class SceneSuggestion:
    scene_index: int
    start_ms: int
    end_ms: int
    cue_start: int
    cue_end: int
    text: str
    within_target_range: bool

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict:
        return {
            "sceneIndex": self.scene_index,
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "sceneDurationMs": self.duration_ms,
            "cueRange": [self.cue_start, self.cue_end],
            "text": self.text,
            "withinTargetRange": self.within_target_range,
        }


def _milliseconds(value) -> int:
    return round(value.total_seconds() * 1000)


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT with the maintained ``srt`` package and normalize cue content."""
    try:
        subtitles = list(srt.parse(text.lstrip("\ufeff")))
    except srt.SRTParseError as exc:
        raise ValueError(f"invalid SRT: {exc}") from exc

    cues: list[Cue] = []
    for position, subtitle in enumerate(subtitles, start=1):
        start_ms = _milliseconds(subtitle.start)
        end_ms = _milliseconds(subtitle.end)
        content = " ".join(line.strip() for line in subtitle.content.splitlines()).strip()
        if end_ms <= start_ms:
            raise ValueError(f"cue {position} has a non-positive duration")
        if not content:
            raise ValueError(f"cue {position} has no text")
        cues.append(Cue(position, start_ms, end_ms, content))

    if not cues:
        raise ValueError("SRT contains no subtitle cues")
    for previous, current in zip(cues, cues[1:], strict=False):
        if current.start_ms < previous.start_ms:
            raise ValueError("subtitle cues are not ordered by start time")
    return cues


def _segment_cost(
    cues: list[Cue], start: int, end: int, target_ms: int, min_ms: int, max_ms: int
) -> float:
    duration = cues[end - 1].end_ms - cues[start].start_ms
    normalized = (duration - target_ms) / target_ms
    cost = normalized * normalized * 100.0
    if duration < min_ms:
        shortfall = (min_ms - duration) / min_ms
        cost += 350.0 * shortfall * shortfall
    elif duration > max_ms:
        overflow = (duration - max_ms) / max_ms
        cost += 500.0 * overflow * overflow
    if _SENTENCE_END.search(cues[end - 1].text):
        cost -= 8.0
    return cost


def group_scenes(
    cues: list[Cue], *, target_sec: float = 30, min_sec: float = 25, max_sec: float = 35
) -> list[SceneSuggestion]:
    """Find the lowest-cost global partition instead of greedily cutting at 30 seconds."""
    if not 0 < min_sec <= target_sec <= max_sec:
        raise ValueError("expected 0 < min_sec <= target_sec <= max_sec")
    if not cues:
        return []

    target_ms = round(target_sec * 1000)
    min_ms = round(min_sec * 1000)
    max_ms = round(max_sec * 1000)
    count = len(cues)
    best = [math.inf] * (count + 1)
    previous = [-1] * (count + 1)
    best[0] = 0.0

    for end in range(1, count + 1):
        for start in range(end):
            candidate = best[start] + _segment_cost(
                cues, start, end, target_ms, min_ms, max_ms
            )
            if candidate < best[end]:
                best[end] = candidate
                previous[end] = start

    partitions: list[tuple[int, int]] = []
    cursor = count
    while cursor > 0:
        start = previous[cursor]
        if start < 0:
            raise RuntimeError("failed to partition subtitle cues")
        partitions.append((start, cursor))
        cursor = start
    partitions.reverse()

    suggestions: list[SceneSuggestion] = []
    for scene_index, (start, end) in enumerate(partitions, start=1):
        segment = cues[start:end]
        duration = segment[-1].end_ms - segment[0].start_ms
        suggestions.append(
            SceneSuggestion(
                scene_index=scene_index,
                start_ms=segment[0].start_ms,
                end_ms=segment[-1].end_ms,
                cue_start=segment[0].index,
                cue_end=segment[-1].index,
                text=" ".join(cue.text for cue in segment),
                within_target_range=min_ms <= duration <= max_ms,
            )
        )
    return suggestions


def build_plan(
    source: str | Path, *, target_sec: float = 30, min_sec: float = 25, max_sec: float = 35
) -> dict:
    path = Path(source)
    cues = parse_srt(path.read_text(encoding="utf-8-sig"))
    scenes = group_scenes(cues, target_sec=target_sec, min_sec=min_sec, max_sec=max_sec)
    warnings = [
        f"scene {scene.scene_index} is {scene.duration_ms / 1000:.1f}s, outside "
        f"the requested {min_sec:g}-{max_sec:g}s range"
        for scene in scenes
        if not scene.within_target_range
    ]
    return {
        "source": str(path),
        "cues": [cue.to_dict() for cue in cues],
        "scenes": [scene.to_dict() for scene in scenes],
        "warnings": warnings,
    }


def plan_json(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)
