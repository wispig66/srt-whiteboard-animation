"""Single command-line surface for the complete whiteboard pipeline."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import sys
import webbrowser
from pathlib import Path

from PIL import Image

from .models import annotation_schema, load_annotation
from .subtitles import build_plan, plan_json

PACKAGE_ROOT = Path(__file__).resolve().parent
EDITOR_PATH = PACKAGE_ROOT / "web" / "editor.html"
DEFAULT_HAND = PACKAGE_ROOT / "assets" / "drawing-hand.png"


def _write_or_print(content: str, output: str | None) -> None:
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")
        print(f"OUTPUT={destination.resolve()}")
    else:
        print(content)


def _parse_command(args: argparse.Namespace) -> int:
    plan = build_plan(
        args.srt,
        target_sec=args.target_sec,
        min_sec=args.min_sec,
        max_sec=args.max_sec,
    )
    _write_or_print(plan_json(plan), args.output)
    for warning in plan["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    scene = load_annotation(args.annotation)
    if args.image:
        with Image.open(args.image) as image:
            scene.verify_image_size(*image.size)
    print(
        json.dumps(
            {
                "valid": True,
                "schemaVersion": scene.schema_version,
                "sceneId": scene.scene_id,
                "elements": len(scene.elements),
                "sceneDurationMs": scene.scene_duration_ms,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _schema_command(args: argparse.Namespace) -> int:
    _write_or_print(json.dumps(annotation_schema(), ensure_ascii=False, indent=2), args.output)
    return 0


def _preview_command(args: argparse.Namespace) -> int:
    from .annotation_preview import render_annotation_preview

    output = render_annotation_preview(
        args.image,
        args.annotation,
        args.output,
        font_path=args.font,
    )
    print(f"OUTPUT={output}")
    return 0


def _render_command(args: argparse.Namespace) -> int:
    from .renderer import render_file

    hand = None if args.bare_tip else (args.hand or DEFAULT_HAND)
    output = render_file(
        args.image,
        args.annotation,
        args.output,
        hand=hand,
        bare_tip=args.bare_tip,
        ink_path=args.ink_path,
        color_fill=args.color_fill,
        fps=args.fps,
        grid_edge=args.grid_edge,
        brush_radius=args.brush_radius,
        cap_long_edge=args.cap_long_edge,
    )
    print(f"OUTPUT={output}")
    return 0


def _merge_command(args: argparse.Namespace) -> int:
    from .media import merge_scenes

    output = merge_scenes(args.inputs, args.output)
    print(f"OUTPUT={output}")
    return 0


def _editor_command(_args: argparse.Namespace) -> int:
    if not EDITOR_PATH.is_file():
        raise RuntimeError(f"editor asset is missing: {EDITOR_PATH}")
    if not webbrowser.open(EDITOR_PATH.as_uri()):
        raise RuntimeError(f"could not open the editor; open this file manually: {EDITOR_PATH}")
    print(f"EDITOR={EDITOR_PATH}")
    return 0


def _doctor_command(_args: argparse.Namespace) -> int:
    from .annotation_preview import find_font

    packages = ["av", "numpy", "opencv-python-headless", "pillow", "pydantic", "srt"]
    report = {
        "python": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg"),
        "pyavFallback": importlib.metadata.version("av"),
        "font": str(find_font()) if find_font() else None,
        "editor": str(EDITOR_PATH) if EDITOR_PATH.is_file() else None,
        "hand": str(DEFAULT_HAND) if DEFAULT_HAND.is_file() else None,
        "packages": {name: importlib.metadata.version(name) for name in packages},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    required_assets = report["editor"] and report["hand"]
    return 0 if required_assets else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="srt-whiteboard",
        description="Validated SRT-driven whiteboard animation pipeline",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")
    commands = parser.add_subparsers(dest="command", required=True)

    parse = commands.add_parser("parse", help="parse SRT and optimize scene boundaries")
    parse.add_argument("srt")
    parse.add_argument("--target-sec", type=float, default=30.0)
    parse.add_argument("--min-sec", type=float, default=25.0)
    parse.add_argument("--max-sec", type=float, default=35.0)
    parse.add_argument("-o", "--output")
    parse.set_defaults(handler=_parse_command)

    validate = commands.add_parser("validate", help="validate annotation v2 invariants")
    validate.add_argument("annotation")
    validate.add_argument("--image", help="also require exact image/canvas dimensions")
    validate.set_defaults(handler=_validate_command)

    schema = commands.add_parser("schema", help="print or write the annotation v2 JSON Schema")
    schema.add_argument("-o", "--output")
    schema.set_defaults(handler=_schema_command)

    preview = commands.add_parser("preview", help="render a static numbered region audit image")
    preview.add_argument("image")
    preview.add_argument("annotation")
    preview.add_argument("output")
    preview.add_argument("--font")
    preview.set_defaults(handler=_preview_command)

    render = commands.add_parser("render", help="render a real stroke preview or final MP4")
    render.add_argument("image")
    render.add_argument("annotation")
    render.add_argument("output")
    render.add_argument("--hand")
    render.add_argument("--bare-tip", action="store_true")
    render.add_argument("--ink-path", choices=["grid", "skeleton"], default="grid")
    render.add_argument("--color-fill", choices=["contour-wipe", "brush"], default="contour-wipe")
    render.add_argument("--fps", type=int, default=60)
    render.add_argument("--grid-edge", type=int, default=10)
    render.add_argument("--brush-radius", type=int, default=40)
    render.add_argument("--cap-long-edge", type=int, default=1080)
    render.set_defaults(handler=_render_command)

    merge = commands.add_parser("merge", help="assemble matching scene MP4 files")
    merge.add_argument("--inputs", nargs="+", required=True)
    merge.add_argument("--output", required=True)
    merge.set_defaults(handler=_merge_command)

    editor = commands.add_parser("editor", help="open the local annotation editor")
    editor.set_defaults(handler=_editor_command)

    doctor = commands.add_parser("doctor", help="report codecs, fonts, assets, and dependencies")
    doctor.set_defaults(handler=_doctor_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
