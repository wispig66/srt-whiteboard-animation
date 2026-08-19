from __future__ import annotations

import pytest

from srt_whiteboard.subtitles import Cue, group_scenes, parse_srt


def test_parse_multiline_and_dot_milliseconds() -> None:
    cues = parse_srt(
        "1\n00:00:00.100 --> 00:00:02.000\nFirst line\nsecond line\n\n"
        "2\n00:00:02,100 --> 00:00:04,000\n结束。\n"
    )
    assert [cue.text for cue in cues] == ["First line second line", "结束。"]
    assert cues[0].start_ms == 100


def test_invalid_scene_range_configuration_fails() -> None:
    with pytest.raises(ValueError, match="min_sec"):
        group_scenes([], target_sec=20, min_sec=25, max_sec=35)


def test_global_partition_avoids_two_bad_short_scenes() -> None:
    cues = [
        Cue(1, 0, 20_000, "A"),
        Cue(2, 21_000, 40_000, "B."),
    ]
    scenes = group_scenes(cues, target_sec=30, min_sec=25, max_sec=35)
    assert len(scenes) == 1
    assert scenes[0].duration_ms == 40_000
    assert not scenes[0].within_target_range


def test_sentence_boundary_is_preferred() -> None:
    cues = [Cue(i, (i - 1) * 10_000, i * 10_000, f"Cue {i}{'.' if i == 3 else ''}") for i in range(1, 7)]
    scenes = group_scenes(cues, target_sec=30, min_sec=20, max_sec=40)
    assert [scene.cue_end for scene in scenes] == [3, 6]
