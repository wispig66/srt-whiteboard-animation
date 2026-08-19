"""Isolated PyAV fallback process.

OpenCV and PyAV wheels may bundle different FFmpeg builds on macOS. Running PyAV
in this worker prevents both dynamic-library sets from entering one process.
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import av


def probe(path: Path) -> dict:
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        rate = stream.average_rate or Fraction(30, 1)
        return {
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "rate": f"{rate.numerator}/{rate.denominator}",
        }
    finally:
        container.close()


def transcode(source: Path, destination: Path) -> None:
    input_container = av.open(str(source), mode="r")
    input_stream = input_container.streams.video[0]
    rate = input_stream.average_rate or Fraction(30, 1)
    output_container = av.open(str(destination), mode="w")
    output_stream = output_container.add_stream("libx264", rate=rate)
    output_stream.width = input_stream.codec_context.width
    output_stream.height = input_stream.codec_context.height
    output_stream.pix_fmt = "yuv420p"
    output_stream.options = {"crf": "24", "preset": "medium"}
    try:
        for frame in input_container.decode(video=0):
            for packet in output_stream.encode(frame):
                output_container.mux(packet)
        for packet in output_stream.encode(None):
            output_container.mux(packet)
    finally:
        input_container.close()
        output_container.close()


def merge(sources: list[Path], destination: Path) -> None:
    contract = probe(sources[0])
    rate_parts = contract["rate"].split("/", maxsplit=1)
    rate = Fraction(int(rate_parts[0]), int(rate_parts[1]))
    output_container = av.open(str(destination), mode="w")
    output_stream = output_container.add_stream("libx264", rate=rate)
    output_stream.width = contract["width"]
    output_stream.height = contract["height"]
    output_stream.pix_fmt = "yuv420p"
    output_stream.options = {"crf": "20", "preset": "medium"}
    try:
        for source in sources:
            input_container = av.open(str(source))
            try:
                for frame in input_container.decode(video=0):
                    # Each source starts its timestamps at zero. Let the encoder assign a
                    # continuous timeline across scene boundaries.
                    frame.pts = None
                    for packet in output_stream.encode(frame):
                        output_container.mux(packet)
            finally:
                input_container.close()
        for packet in output_stream.encode(None):
            output_container.mux(packet)
    finally:
        output_container.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("source")
    transcode_parser = commands.add_parser("transcode")
    transcode_parser.add_argument("source")
    transcode_parser.add_argument("destination")
    merge_parser = commands.add_parser("merge")
    merge_parser.add_argument("destination")
    merge_parser.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)

    if args.command == "probe":
        print(json.dumps(probe(Path(args.source))))
    elif args.command == "transcode":
        transcode(Path(args.source), Path(args.destination))
    else:
        merge([Path(source) for source in args.sources], Path(args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
