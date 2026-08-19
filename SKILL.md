---
name: srt-whiteboard-animation
description: Turn an SRT transcript into a validated, reviewable whiteboard animation. Use when a user asks to make an SRT-driven whiteboard, hand-drawn explainer, or streaming-stroke video. The workflow plans scenes, generates consistent line art, creates annotation v2, validates timing and masks, renders a real low-resolution proof, then renders and assembles final MP4 scenes.
---

# SRT whiteboard animation

Build the video as a sequence of independently reviewable scene contracts. Match the user's language in all explanations and labels.

## Non-negotiable invariants

- Use annotation schema v2 from `src/srt_whiteboard/schemas/annotation-v2.schema.json`.
- `elements` array order is the only narrative and drawing order. Do not add `sequence`.
- Element timings must be monotonic and non-overlapping.
- The annotation canvas must exactly match the source image's pixel dimensions.
- Every region and protected region must remain inside the canvas.
- `sceneDurationMs` must include at least `holdMs` after the final element.
- Do not use removed v1 fields: `reveal`, `handPath`, `direction`, `maskPaddingPx`, or `type`.
- The browser editor is a layout and timing editor. Only an actual `render` output proves the stroke result.

## Environment

From the skill root, run:

```bash
uv sync --locked
uv run --locked srt-whiteboard doctor
```

Stop if `doctor` reports a missing editor or hand asset. System FFmpeg is preferred; PyAV is the supported fallback.

## Workflow and confirmation gates

Each numbered stage is a separate user confirmation gate. Finish the stage, show its artifacts, and wait for explicit approval before continuing.

### 1. Parse the SRT and propose scenes

```bash
uv run --locked srt-whiteboard parse input.srt -o scene-plan.json
```

Read `warnings`; do not claim every scene is within 25–35 seconds when cue boundaries make that impossible. For each proposed scene, explain its one core idea, source cue range, visual subject, and duration. Do not generate images yet.

### 2. Generate consistent source illustrations

After plan approval, generate one 16:9 illustration per scene with the available image-generation capability.

Use this visual system unless the user asks for another:

- warm paper background near `#F5EBD7`;
- restrained dark-gray sketch lines;
- small red, orange, or blue accents only;
- clean composition, generous whitespace, stable character design;
- no embedded words, labels, watermarks, photographic texture, or 3D rendering.

Show all images and wait for approval.

### 3. Author and validate annotation v2

Inspect both the approved image and its corresponding subtitles. Create `<image-stem>.annotation.json`. Map visible subjects to subtitle events in narrative order, not screen-coordinate order.

```bash
uv run --locked srt-whiteboard validate scene.annotation.json --image scene.png
uv run --locked srt-whiteboard editor
```

The editor can adjust regions, array order, timing, labels, and subtitles. Saving must pass its local v2 validation. Wait for approval after the edited JSON is saved.

### 4. Produce a static region audit

```bash
uv run --locked srt-whiteboard preview scene.png scene.png.annotation.json scene-regions.jpg
```

Check ordering, bounds, timing labels, subject coverage, and dashed protected regions. Wait for approval.

### 5. Render a real low-resolution proof

The layout editor is not a stroke renderer. Produce the actual renderer proof:

```bash
uv run --locked srt-whiteboard render scene.png scene.png.annotation.json scene-proof.mp4 \
  --cap-long-edge 640 --fps 24
```

Inspect the opening frame, each element transition, an overlap midpoint, and the final hold. Wait for approval. If the proof needs changes, edit the v2 annotation and repeat stages 3–5; do not regenerate approved art unless the art itself is wrong.

### 6. Render and assemble final scenes

```bash
uv run --locked srt-whiteboard render scene.png scene.png.annotation.json scene-final.mp4
uv run --locked srt-whiteboard merge --inputs scene-01-final.mp4 scene-02-final.mp4 --output final.mp4
```

All scenes must share dimensions and frame rate; merge fails closed when their video contracts differ. Show the final MP4 and report its dimensions, duration, frame rate, and codec.

## Annotation v2 shape

```json
{
  "schemaVersion": 2,
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "One scene, one narrative idea.",
  "sceneDurationMs": 8600,
  "holdMs": 500,
  "elements": [
    {
      "id": "setting",
      "label": "Setting",
      "narrativeRole": "Establishes the scene",
      "subtitle": "The matching subtitle text.",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "timing": { "startMs": 300, "durationMs": 2600 },
      "protectedRegions": []
    }
  ]
}
```

## Final acceptance

- `validate --image` succeeds for every scene.
- Frame zero contains only the paper canvas.
- No future element leaks through an earlier region.
- Actual drawing order matches the JSON array and subtitle narrative.
- The output frame count matches `sceneDurationMs` at the selected FPS.
- The final complete image remains visible for at least `holdMs`.
- Final scene contracts match before merge.
