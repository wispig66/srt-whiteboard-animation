---
name: srt-whiteboard-animation
description: Turn an SRT transcript into a validated, reviewable whiteboard explainer with visible captions and approved narration. Use when a user asks to make an SRT-driven whiteboard, hand-drawn explainer, or streaming-stroke video. The workflow plans scenes, approves TTS, generates consistent line art, validates annotation v2, renders a real low-resolution audiovisual proof, then delivers a captioned MP4 with audio.
---

# SRT whiteboard animation

Build the video as a sequence of independently reviewable scene contracts. Match the user's
language in all explanations and labels.

## Non-negotiable invariants

- Use annotation schema v2 from `src/srt_whiteboard/schemas/annotation-v2.schema.json`.
- `elements` array order is the only narrative and drawing order. Do not add `sequence`.
- Element timings must be monotonic and non-overlapping.
- The annotation canvas must exactly match the source image's pixel dimensions.
- Every region and protected region must remain inside the canvas.
- `sceneDurationMs` must include at least `holdMs` after the final element.
- Treat `sceneDurationMs` as an upstream SRT/scene contract. The current editor rewrites it
  when saving, so restore the approved plan value after every editor save and revalidate.
- Do not use removed v1 fields: `reveal`, `handPath`, `direction`, `maskPaddingPx`, or `type`.
- The browser editor is a layout and timing editor. Only an actual `render` output proves
  the stroke result.
- Every render must explicitly pass `--bare-tip`; never rely on the renderer's bundled hand
  default. The only exception is an exact transparent PNG that the user has reviewed and
  approved, passed explicitly with `--hand` instead of `--bare-tip`.
- Every CLI render must explicitly state its FPS and `--cap-long-edge`. Use a small value for
  proofs and the source image's measured long edge for the final scene.
- The approved SRT is the only global timeline and spoken-text authority. Annotation
  subtitles are scene audit metadata; never use them to independently retime delivery.
- An SRT-driven explainer includes visible burned-in captions and audible narration by
  default. Omit either only when the user explicitly approves a silent or caption-free
  exception before production.
- Narration is a media responsibility. Use the available `media-use` Skill for TTS; do not
  add a TTS provider, credential flow, or voice catalog to this renderer.
- Generate TTS per SRT cue and place each clip at the cue's global start time. Never silently
  truncate speech, overlap voices, stretch the video, rewrite text, or choose a fallback voice.
- Do not add background music or sound effects unless the user separately approves them.

## Runtime and workspace boundary

Treat the directory containing this `SKILL.md` as `SKILL_ROOT`. Treat the directory the
user opened in Codex as `WORKSPACE_ROOT`.

- Keep SRT files under `WORKSPACE_ROOT/input/`.
- Keep plans, illustrations, annotations, audio assets, audits, and proofs under
  `WORKSPACE_ROOT/work/`.
- Keep only approved deliverables under `WORKSPACE_ROOT/output/`.
- Never write generated artifacts into `SKILL_ROOT`.
- Run commands from `WORKSPACE_ROOT` and point uv at the Skill package explicitly.
- Resolve `SKILL_ROOT` from the absolute Skill path supplied by Codex; do not assume the
  Skill was installed globally or that the current directory is the Skill repository.

Bootstrap the isolated renderer runtime once:

```bash
SKILL_ROOT="/absolute/path/to/.agents/skills/srt-whiteboard-animation"
[ -f "${SKILL_ROOT:?}/pyproject.toml" ]
uv sync --project "$SKILL_ROOT" --locked
uv run --project "$SKILL_ROOT" --locked srt-whiteboard doctor
command -v ffmpeg
command -v ffprobe
ffmpeg -hide_banner -filters 2>/dev/null | rg ' (ass|subtitles) '
```

Stop if the editor, FFmpeg, FFprobe, or libass subtitle filter is missing. PyAV may fall back
for silent rendering and merging, but a captioned audiovisual deliverable requires FFmpeg.

For narration, resolve the available `media-use` Skill as `MEDIA_SKILL_ROOT`, read its audio
and provider instructions, then run its doctor before offering voice choices:

```bash
MEDIA_SKILL_ROOT="/absolute/path/to/media-use"
node "$MEDIA_SKILL_ROOT/scripts/resolve.mjs" --doctor
npx hyperframes auth status
```

Recommend HeyGen sign-in when it is available, then stop for the user's choice between that
cloud route and an installed offline route such as Kokoro. If `media-use` or an approved TTS
route is unavailable, stop at the narration gate and ask the user. Never continue to a
nominally final silent video.

All commands below assume the same validated roots and execute from `WORKSPACE_ROOT`.

## Workflow and confirmation gates

Each numbered stage is a separate user confirmation gate. Finish the stage, show its
artifacts, and wait for explicit approval before continuing.

### 1. Parse and approve the authoritative SRT

```bash
uv run --project "$SKILL_ROOT" --locked srt-whiteboard parse \
  input/narration.srt -o work/scene-plan.json
```

Read `warnings`; do not claim every scene is within 25–35 seconds when cue boundaries make
that impossible. For each scene, explain its one core idea, cue range, visual subject, and
duration. Explicitly confirm that the SRT wording and cue times will drive both captions and
narration. Ask once whether the user wants optional BGM/SFX; absence of a request means none.
Do not generate images or speech yet.

### 2. Select and approve a TTS voice sample

Follow `media-use` authentication and provider rules. Present the available provider and
voice choices with privacy/cost implications. The user must choose the provider, candidate
voice, language, and speed before synthesis; never use `auto` or an implicit fallback.
List voices with the provider-specific command documented by `media-use`; for example,
`heygen-tts.mjs --list` for HeyGen or `npx hyperframes tts --list` for Kokoro. Only offer a
speed control that the selected provider route actually supports.

Create `work/audio/sample-request.json` with one representative cue containing the product
name and the video's primary language:

```json
{
  "provider": "APPROVED_PROVIDER",
  "voice": "APPROVED_VOICE",
  "lang": "zh",
  "speed": 1.0,
  "lines": [
    { "id": "cue-0003", "text": "Exact approved SRT cue text." }
  ],
  "bgm": { "mode": "none" }
}
```

```bash
node "$MEDIA_SKILL_ROOT/audio/scripts/audio.mjs" \
  --request "$WORKSPACE_ROOT/work/audio/sample-request.json" \
  --hyperframes "$WORKSPACE_ROOT/work/audio/sample" \
  --out "$WORKSPACE_ROOT/work/audio/sample/audio-meta.json" \
  --only tts --provider APPROVED_PROVIDER --voice APPROVED_VOICE --speed 1.0
```

Play the exact sample and report provider, voice ID, language, effective speed, file duration,
and the approved cost route (`offline`, OAuth allowance, or paid API). Do not infer actual
billing from `audio-meta.json`; it contains no billing receipt. Wait for approval. A provider
choice is not voice-sample approval.

### 3. Generate and approve the full narration timeline

Create `work/audio/audio-request.json` from the approved SRT with exactly one `lines` entry
per cue. IDs must be stable global IDs `cue-0001`, `cue-0002`, and so on; text must match the
SRT exactly. Pin the same approved provider, voice, language, and speed from stage 2.

```bash
node "$MEDIA_SKILL_ROOT/audio/scripts/audio.mjs" \
  --request "$WORKSPACE_ROOT/work/audio/audio-request.json" \
  --hyperframes "$WORKSPACE_ROOT/work/audio" \
  --out "$WORKSPACE_ROOT/work/audio/audio-meta.json" \
  --only tts --provider APPROVED_PROVIDER --voice APPROVED_VOICE --speed 1.0
```

Read `audio-meta.json` and verify every cue has exactly one real voice file. Measure the real
files with FFprobe; metadata duration alone is not proof. Each clip must fit entirely inside
its SRT cue. If a clip is too long, try a still-natural speed up to about 1.2 only with user
approval; otherwise revise the SRT and return to stage 1. Never clip speech.

Build `work/audio/narration-filter.txt` from the validated cue starts. For every cue, resample
its clip to 48 kHz mono and apply `adelay=<cue.startMs>:all=1`; mix all delayed inputs with
`amix`, pad with silence, and trim exactly at the final SRT end. Then render a lossless master:

```bash
ffmpeg -y -loglevel error \
  -i work/audio/assets/voice/cue-0001.wav \
  -i work/audio/assets/voice/cue-0002.wav \
  -filter_complex_script work/audio/narration-filter.txt \
  -map '[narration]' -c:a pcm_s16le -ar 48000 -ac 1 \
  work/audio/narration.wav
```

The input list and filter script are generated per project; do not copy a fixed cue count or
timing example. Confirm the WAV duration equals the final SRT end, listen through the entire
narration, and check pronunciation, clipping, missing cues, overlaps, unnatural pacing, and
silence placement. Show or play the WAV and wait for approval.

### 4. Generate consistent source illustrations

After plan and narration approval, generate one 16:9 illustration per scene with the
available image-generation capability.

Use this visual system unless the user asks for another:

- warm paper background near `#F5EBD7`;
- restrained dark-gray sketch lines;
- small red, orange, or blue accents only;
- clean composition, generous whitespace, stable character design;
- no embedded words, labels, watermarks, photographic texture, or 3D rendering.

Show all images and wait for approval.

### 5. Author and validate annotation v2

Inspect both the approved image and its corresponding SRT cues. Create
`<image-stem>.annotation.json`. Map visible subjects to subtitle events in narrative order,
not screen-coordinate order. Copy subtitle text exactly from the approved SRT; it remains
audit metadata.

```bash
uv run --project "$SKILL_ROOT" --locked srt-whiteboard validate \
  work/scene.annotation.json --image work/scene.png
uv run --project "$SKILL_ROOT" --locked srt-whiteboard editor
```

The editor can adjust regions, array order, timing, labels, and subtitles. After saving,
restore `sceneDurationMs` from the approved scene plan, run `validate --image` again, and
confirm the final element still leaves at least `holdMs`. Wait for approval only after that
post-editor validation succeeds.

### 6. Produce a static region audit

```bash
uv run --project "$SKILL_ROOT" --locked srt-whiteboard preview \
  work/scene.png work/scene.annotation.json work/scene-regions.jpg
```

Check ordering, bounds, timing labels, subject coverage, and dashed protected regions. Wait
for approval.

### 7. Render a real low-resolution audiovisual proof

The layout editor is not a stroke renderer. Render every scene at the proof contract:

```bash
uv run --project "$SKILL_ROOT" --locked srt-whiteboard render \
  work/scene.png work/scene.annotation.json work/scene-proof.mp4 \
  --bare-tip --cap-long-edge 640 --fps 24
```

Do not add a hand overlay unless the user asks for one. If requested, keep the candidate PNG
under `WORKSPACE_ROOT/work/`, inspect and show that exact asset, and obtain explicit approval
before adding `--hand work/approved-hand.png`. Reject any asset containing text, a logo, a
watermark, or unrelated marks. `--hand` replaces `--bare-tip`; never pass both.

Merge the proof scenes into `work/proof-silent.mp4`. Then use FFmpeg to burn the original SRT
into the frames with the libass `subtitles` filter and mux the approved narration. Use
`wrap_unicode=1`, an explicitly resolved CJK-capable font, a high-contrast background,
48 kHz mono AAC, loudness normalization, and the exact SRT end time. Do not use `-shortest`
as a substitute for proving duration equality.

The canonical filter shape is:

```text
subtitles=filename='input/narration.srt':fontsdir='APPROVED_FONT_DIR':wrap_unicode=1:force_style='FontName=APPROVED_FONT,FontSize=PROPORTIONAL_SIZE,PrimaryColour=&H00FFFFFF,BackColour=&H78000000,BorderStyle=3,Outline=8,Shadow=0,Alignment=2,MarginL=SAFE_MARGIN,MarginR=SAFE_MARGIN,MarginV=SAFE_MARGIN'
```

First verify that `work/proof-silent.mp4`, `work/audio/narration.wav`, and the final SRT end
already match within one video frame. Set the validated filter string and end time explicitly,
then run the finishing pass:

```bash
ffmpeg -y -loglevel error \
  -i work/proof-silent.mp4 -i work/audio/narration.wav \
  -map 0:v:0 -map 1:a:0 \
  -vf "$CAPTION_FILTER" \
  -af 'loudnorm=I=-16:LRA=7:TP=-1.5' \
  -c:v libx264 -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -ac 1 \
  -t "$SRT_END_SECONDS" -movflags +faststart \
  work/proof-av.mp4
```

Pass paths and filter values safely; keep generated paths simple and escape FFmpeg filter
characters. Inspect the opening frame, every scene boundary, longest subtitle, multi-line CJK
wrapping, safe margins, final frame, and the full audio track.
Report video/audio codecs, frame rate, duration, font, provider/voice, and overlay asset. Wait
for approval. If visuals change, repeat stages 5–7; if wording, timing, or voice changes,
return to stages 1–3.

### 8. Render and deliver the final audiovisual MP4

Measure each approved source image's long edge. Render all scenes with the proof-approved
FPS, ink path, color fill, and hand setting; only `--cap-long-edge` changes. If the source
images do not share dimensions, normalize them before rendering.

```bash
uv run --project "$SKILL_ROOT" --locked srt-whiteboard render \
  work/scene.png work/scene.annotation.json work/scene-final.mp4 \
  --bare-tip --cap-long-edge SOURCE_LONG_EDGE --fps 24
uv run --project "$SKILL_ROOT" --locked srt-whiteboard merge \
  --inputs work/scene-01-final.mp4 work/scene-02-final.mp4 \
  --output work/final-silent.mp4
```

If the proof used an approved hand, replace `--bare-tip` with the same explicit `--hand`
path for every final scene.

Repeat the approved FFmpeg caption/audio finishing pass with the same SRT, narration WAV,
font, colors, margins, loudness target, and proportional subtitle sizing. Write only the
finished audiovisual file to `output/final.mp4`; keep the silent merge under `work/`.

Show the final MP4 and report dimensions, duration, frame rate, video/audio codecs, audio
sample rate/channel count, caption mode (`burned-in`), font, TTS provider/voice, and overlay
asset (or `none`).

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
      "subtitle": "The matching approved SRT cue text.",
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
- The approved SRT text is visibly burned into the final frames at its original cue times.
- Long Latin and CJK captions wrap without clipping and remain inside the safe area.
- The final MP4 contains exactly one audible narration track and one video track.
- The final MP4 contains no subtitle stream; the approved captions are visibly burned in.
- Every spoken cue matches its SRT text, fits inside its cue window, and has been checked for
  pronunciation and natural pacing.
- Silent video duration, narration duration, SRT end time, and final duration match within
  one video frame.
