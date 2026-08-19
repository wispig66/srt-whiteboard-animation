"""Video encoding and deterministic scene assembly."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


class MediaError(RuntimeError):
    pass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _run_pyav_worker(operation: str, *paths: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        [sys.executable, "-m", "srt_whiteboard.pyav_worker", operation, *(str(path) for path in paths)]
    )


def transcode_h264(source: str | Path, destination: str | Path) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        result = _run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(destination_path),
            ]
        )
        if result.returncode == 0:
            source_path.unlink(missing_ok=True)
            return destination_path.resolve()
        destination_path.unlink(missing_ok=True)

    fallback = _run_pyav_worker("transcode", source_path, destination_path)
    if fallback.returncode != 0:
        destination_path.unlink(missing_ok=True)
        raise MediaError(f"H.264 transcoding failed: {fallback.stderr.strip()}")
    source_path.unlink(missing_ok=True)
    return destination_path.resolve()


def _probe_video(path: Path) -> tuple[int, int, Fraction]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = _run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ]
        )
    else:
        result = _run_pyav_worker("probe", path)
    if result.returncode != 0:
        raise MediaError(f"cannot probe {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    stream = payload["streams"][0] if "streams" in payload else payload
    numerator, denominator = stream.get("r_frame_rate", stream.get("rate", "30/1")).split("/")
    return int(stream["width"]), int(stream["height"]), Fraction(int(numerator), int(denominator))


def merge_scenes(inputs: list[str | Path], output: str | Path) -> Path:
    """Concatenate scenes after proving that their video contracts match."""
    if not inputs:
        raise MediaError("at least one input scene is required")
    sources = [Path(value).resolve() for value in inputs]
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise MediaError(f"missing input scenes: {', '.join(missing)}")
    destination = Path(output).resolve()
    if destination in sources:
        raise MediaError("output must not overwrite an input scene")
    destination.parent.mkdir(parents=True, exist_ok=True)

    contracts = [_probe_video(path) for path in sources]
    if len(set(contracts)) != 1:
        rendered = ", ".join(
            f"{path.name}={width}x{height}@{rate}"
            for path, (width, height, rate) in zip(sources, contracts, strict=True)
        )
        raise MediaError(f"scene video contracts differ: {rendered}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        with tempfile.TemporaryDirectory(prefix="srt-whiteboard-") as temp_dir:
            list_path = Path(temp_dir) / "scenes.ffconcat"
            lines = ["ffconcat version 1.0"]
            for path in sources:
                escaped = str(path).replace("\\", "\\\\").replace("'", "\\'")
                lines.append(f"file '{escaped}'")
            list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = _run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_path),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(destination),
                ]
            )
        if result.returncode == 0:
            return destination
        destination.unlink(missing_ok=True)

    fallback = _run_pyav_worker("merge", destination, *sources)
    if fallback.returncode != 0:
        destination.unlink(missing_ok=True)
        raise MediaError(f"scene merge failed: {fallback.stderr.strip()}")
    return destination
