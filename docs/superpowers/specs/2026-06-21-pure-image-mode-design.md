# Pure Image Mode, Motion, and Subtitles Design

Date: 2026-06-21

## Context

Pixelle-Video currently generates each storyboard frame through a template-first composition path:

1. Generate narration audio.
2. Generate image or video media.
3. Render an HTML frame template with the media and narration text.
4. Convert the rendered frame plus narration audio into a video segment.
5. Concatenate all segments into the final video.

This works for template-driven videos, but it makes generated illustrations feel constrained by the
selected template. The user wants a simpler mode where generated images become the video itself:
each image fills the canvas, receives subtle zoom or pan motion, optionally shows bottom subtitles,
and then gets stitched into the final video.

The template library should not be removed yet. The new mode should sit beside the existing template
mode so existing users can keep using templates while the new pure-image path can be tested and
expanded.

## Goal

Add a selectable pure image composition mode that creates video segments directly from generated
images, with optional Ken Burns style motion and optional bottom subtitles.

The implemented result should let users choose:

- `模板模式`: existing HTML template rendering path, unchanged by default.
- `纯图片模式`: generated image fills the video canvas, without HTML template rendering.

Pure image mode should support:

- Full-canvas image display using a predictable `cover` fit.
- Optional dynamic motion: subtle zoom in, zoom out, and pan variants selected automatically by frame
  index.
- Optional bottom subtitles based on each storyboard frame's narration text.
- The same image generation backends and prompt flow already used by the standard pipeline,
  including BizyAir.

## Non-Goals

This implementation will not:

- Delete the template library.
- Migrate existing templates to the pure-image path.
- Add a full motion editor with keyframes.
- Add per-frame manual motion controls in the first version.
- Add per-frame subtitle editing in the first version.
- Change image prompt generation behavior.
- Change RunningHub, ComfyUI, or BizyAir provider semantics.
- Change video-media workflows. Pure image mode is for image media segments; video media keeps the
  current template overlay behavior unless a separate design expands it.

## User Experience

The Web UI should expose a new visual mode control in the style configuration area:

```text
画面模式: [模板模式] [纯图片模式]
```

When `模板模式` is selected:

- The current template selector remains visible.
- Template preview remains available.
- Template custom parameters remain available.
- Existing video generation behavior remains unchanged.

When `纯图片模式` is selected:

- Template-specific controls are hidden or visually de-emphasized.
- The image workflow selector and prompt prefix remain available.
- Canvas defaults to vertical `1080x1920`.
- Two switches are shown:
  - `动态图片效果`: default on.
  - `显示字幕`: default on.

Pure image mode should produce a finished video without requiring the user to pick a template.

## Configuration Model

Extend `StoryboardConfig` with composition settings:

```python
composition_mode: str = "template"
image_motion_enabled: bool = False
subtitle_enabled: bool = True
image_motion_mode: str = "auto"
image_motion_strength: str = "subtle"
image_fit_mode: str = "cover"
```

Allowed values:

- `composition_mode`: `template`, `plain_image`
- `image_motion_mode`: `auto`
- `image_motion_strength`: `subtle`
- `image_fit_mode`: `cover`

Only `template` and `plain_image` need to be exposed in the first UI. The additional fields exist so
the video service has an explicit contract and future UI controls can be added without changing the
pipeline boundary again.

Default behavior must preserve existing results:

- `composition_mode="template"` keeps the existing HTML template path.
- `image_motion_enabled=False` avoids changing template mode output.
- `subtitle_enabled=True` keeps template mode subtitle rendering available through existing
  templates, but the new FFmpeg subtitle overlay is only used in pure image mode.

## Data Flow

Template mode keeps the current path:

```text
StoryboardFrame.image_path
  -> HTMLFrameGenerator
  -> StoryboardFrame.composed_image_path
  -> VideoService.create_video_from_image(composed_image_path, audio_path)
```

Pure image mode uses a direct path:

```text
StoryboardFrame.image_path
  -> VideoService.create_video_from_image_with_motion(
       image=image_path,
       audio=audio_path,
       width=config.media_width,
       height=config.media_height,
       subtitle_text=frame.narration,
       motion_enabled=config.image_motion_enabled,
       subtitle_enabled=config.subtitle_enabled,
     )
  -> StoryboardFrame.video_segment_path
```

`FrameProcessor` should branch by `config.composition_mode`.

For `plain_image` image frames:

- Skip `_step_compose_frame`.
- Leave `frame.composed_image_path` as `None`.
- Require `frame.image_path`.
- Create the video segment from `frame.image_path`.

For `template` image frames:

- Keep `_step_compose_frame`.
- Continue using `frame.composed_image_path`.

For generated video frames:

- Keep the current video overlay path in the first implementation.
- If `composition_mode="plain_image"` is selected with a video media workflow, raise a clear error
  before segment creation because pure image mode promises image-only composition.

## Video Composition

Add a new `VideoService` method rather than changing the existing static-image method:

```python
def create_video_from_image_with_motion(
    self,
    image: str,
    audio: str,
    output: str,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    subtitle_text: str | None = None,
    subtitle_enabled: bool = True,
    motion_enabled: bool = True,
    motion_mode: str = "auto",
    motion_strength: str = "subtle",
    image_fit_mode: str = "cover",
    frame_index: int = 0,
) -> str:
    ...
```

The method should:

1. Probe audio duration.
2. Loop the input image for the audio duration.
3. Scale and crop to the requested canvas with `cover` semantics.
4. Apply subtle motion when enabled.
5. Overlay subtitles when enabled and text is non-empty.
6. Encode H.264 video with AAC audio and `yuv420p` pixel format.

The existing `create_video_from_image` method remains available for template mode and tests.

## Motion Design

Use a restrained Ken Burns effect. The motion should make still images feel alive without calling
attention to itself.

First-version automatic motion variants:

- Frame index `% 4 == 0`: slow zoom in from center.
- Frame index `% 4 == 1`: slow zoom out from center.
- Frame index `% 4 == 2`: slow pan left-to-right with slight zoom.
- Frame index `% 4 == 3`: slow pan right-to-left with slight zoom.

Subtle strength target:

- Zoom range should stay around `1.00` to `1.08`.
- Pan should stay within the extra crop area created by the slight zoom.
- Motion must last exactly for the audio duration and should not create visible black borders.

FFmpeg `zoompan` can implement this, but the implementation may use an equivalent FFmpeg filter chain
if it is more reliable. The important contract is the visual behavior and output duration, not the
specific filter name.

When motion is disabled, the method should still apply the same `cover` scaling and subtitle overlay
so the output shape stays consistent.

## Subtitle Design

Pure image subtitles should be rendered with FFmpeg `drawtext`.

Subtitle behavior:

- Source text: `StoryboardFrame.narration`.
- Position: bottom safe area, centered.
- Text color: white.
- Stroke: black outline for contrast.
- Font size: responsive to canvas width, with a practical default near 48 px for `1080x1920`.
- Line wrapping: handled in Python before passing text to FFmpeg.
- Maximum subtitle block: 2 to 3 lines depending on text length.
- Long text should be wrapped and clipped conservatively rather than overflowing the frame.

Font handling:

- Prefer a local Chinese-capable macOS font such as `/System/Library/Fonts/PingFang.ttc`.
- Fall back to other system fonts if PingFang is unavailable.
- If no usable font is found, raise a clear error that names the missing subtitle font problem and
  advises disabling subtitles as a workaround.

Escaping:

- Escape characters that are meaningful to FFmpeg filter expressions.
- Preserve Chinese text and common punctuation.
- Avoid shell interpolation by using `ffmpeg-python` or argument-safe command construction.

## Persistence

The storyboard persistence layer should include the new config fields so history entries can be
reloaded accurately:

- `composition_mode`
- `image_motion_enabled`
- `subtitle_enabled`
- `image_motion_mode`
- `image_motion_strength`
- `image_fit_mode`

Backward compatibility:

- Missing `composition_mode` loads as `template`.
- Missing motion fields load as the defaults above.
- Existing saved storyboards continue to open.

History preview behavior:

- If `frame.composed_image_path` exists, keep showing it as today.
- If it does not exist and `frame.image_path` exists, show the original image for pure image mode
  history entries.

## Pipeline and Web UI Propagation

The standard pipeline should accept the new params from `generate_video(...)` and pass them into
`StoryboardConfig`.

Affected path:

```text
web/components/style_config.py
  -> web/components/output_preview.py
  -> pixelle_video.service generate_video wrapper
  -> pixelle_video/pipelines/standard.py
  -> StoryboardConfig
  -> FrameProcessor
  -> VideoService
```

Batch generation must pass the same shared settings as single generation. If a batch task is created
in pure image mode, every generated video in that batch uses the same pure-image, motion, and subtitle
settings.

The `PixelleVideoService` wrapper should forward unknown keyword arguments only if the underlying
pipeline accepts them. If the wrapper has an explicit parameter list, add the new mode fields there.

## Validation and Errors

Required validation:

- Unknown `composition_mode` raises `ValueError("Unsupported composition mode: ...")`.
- `plain_image` requires image media, not video media.
- `plain_image` requires `frame.image_path` before segment creation.
- `media_width` and `media_height` must be positive integers.
- Subtitle font discovery failure raises a clear, actionable error.
- FFmpeg failures include stderr in the raised exception, as existing video methods do.

Preview and full generation should surface these errors through the existing Web UI exception display.

## Testing Strategy

Add focused tests for:

- `StoryboardConfig` defaults preserve template mode.
- Persistence round-trips the new config fields and loads old config dictionaries with defaults.
- Standard pipeline passes composition settings into `StoryboardConfig`.
- `FrameProcessor` skips HTML composition in `plain_image` mode.
- `FrameProcessor` uses `frame.image_path` for pure image video segments.
- Template mode still calls the existing composed-image path.
- `VideoService.create_video_from_image_with_motion` can create a short segment from a test image
  and test audio.
- Subtitle escaping and wrapping produce drawtext-safe text.

Verification commands:

```bash
uv run --extra dev pytest -v
uv run --extra dev ruff check pixelle_video/services/video.py pixelle_video/services/frame_processor.py pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py pixelle_video/services/persistence.py web/components/style_config.py web/components/output_preview.py web/pages/2_📚_History.py tests
uv run python -m json.tool web/i18n/locales/zh_CN.json >/tmp/zh_CN.json
uv run python -m json.tool web/i18n/locales/en_US.json >/tmp/en_US.json
```

After implementation, restart the local Streamlit app and verify:

- The Web UI loads.
- Template mode still shows template controls and can generate preview.
- Pure image mode shows motion and subtitle switches.
- Pure image mode can generate a short preview segment.
- The resulting video has full-canvas imagery, visible motion when enabled, and bottom subtitles when
  enabled.

## Rollout

Ship this as an additive feature on `main`.

Risk controls:

- Keep `template` as the default composition mode.
- Keep the existing `create_video_from_image` method unchanged.
- Route pure image behavior through new config fields and a new video service method.
- Keep pure image mode image-only in the first version.
- Make all new UI strings localized in Chinese and English.

This lets the user try the simpler image-first workflow immediately while retaining the existing
template library as a stable fallback.
