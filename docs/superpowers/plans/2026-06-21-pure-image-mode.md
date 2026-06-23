# Pure Image Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure image video composition mode that skips HTML templates, applies optional subtle image motion, and overlays optional bottom subtitles.

**Architecture:** Preserve the existing template path as the default. Add composition fields to `StoryboardConfig`, propagate them from the Web UI through the standard pipeline, branch `FrameProcessor` so `plain_image` frames use the original generated image, and add a new `VideoService.create_video_from_image_with_motion(...)` method for cover fit, motion, subtitles, and audio muxing.

**Tech Stack:** Python dataclasses, Streamlit, ffmpeg-python, FFmpeg `zoompan`/`drawtext`, pytest, pytest-asyncio, Pillow for test fixtures.

---

## File Structure

- Modify `pixelle_video/models/storyboard.py`
  - Add composition mode, motion, subtitle, fit fields with template-safe defaults.
- Modify `pixelle_video/pipelines/standard.py`
  - Make pure image mode require image prompts/media regardless of selected template.
  - Pass new composition fields into `StoryboardConfig`.
- Modify `pixelle_video/services/frame_processor.py`
  - Skip HTML frame composition in `plain_image` mode.
  - Use `frame.image_path` plus the new video service method for pure image segments.
  - Raise clear errors for unsupported modes and video media in pure image mode.
- Modify `pixelle_video/services/video.py`
  - Add subtitle font discovery, text wrapping/escaping helpers, cover/motion filter construction, and `create_video_from_image_with_motion(...)`.
- Modify `pixelle_video/services/persistence.py`
  - Round-trip new config fields while preserving old saved storyboards.
- Modify `web/components/style_config.py`
  - Add visual mode selector, pure image motion/subtitle switches, pure image dimensions, and template-control gating.
- Modify `web/components/output_preview.py`
  - Pass new composition fields and dimensions to single and batch generation.
  - Display result dimensions from storyboard config instead of template parsing in pure image mode.
- Modify `web/i18n/locales/zh_CN.json`
  - Add Chinese labels for visual mode, pure image mode, motion, subtitles, and pure image size text.
- Modify `web/i18n/locales/en_US.json`
  - Add English labels for the same UI controls.
- Test `tests/models/test_storyboard_config.py`
  - Verify config defaults and explicit pure image settings.
- Test `tests/services/test_persistence_config.py`
  - Verify persistence round-trip and backward-compatible loads.
- Test `tests/pipelines/test_standard_composition_config.py`
  - Verify standard pipeline config propagation and pure image visual planning.
- Test `tests/services/test_frame_processor_composition.py`
  - Verify frame processor branch behavior for template and pure image modes.
- Test `tests/services/test_video_motion.py`
  - Verify subtitle helpers and a short FFmpeg-generated pure image segment.

## Task 1: Config and Persistence

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Create: `tests/models/test_storyboard_config.py`
- Create: `tests/services/test_persistence_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/models/test_storyboard_config.py`:

```python
import pytest

from pixelle_video.models.storyboard import StoryboardConfig


def test_storyboard_config_defaults_preserve_template_mode():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert config.composition_mode == "template"
    assert config.image_motion_enabled is False
    assert config.subtitle_enabled is True
    assert config.image_motion_mode == "auto"
    assert config.image_motion_strength == "subtle"
    assert config.image_fit_mode == "cover"


def test_storyboard_config_accepts_plain_image_settings():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        composition_mode="plain_image",
        image_motion_enabled=True,
        subtitle_enabled=False,
    )

    assert config.composition_mode == "plain_image"
    assert config.image_motion_enabled is True
    assert config.subtitle_enabled is False


@pytest.mark.parametrize("mode", ["template", "plain_image"])
def test_storyboard_config_allows_supported_modes(mode):
    config = StoryboardConfig(media_width=1080, media_height=1920, composition_mode=mode)

    assert config.composition_mode == mode
```

- [ ] **Step 2: Write failing persistence tests**

Create `tests/services/test_persistence_config.py`:

```python
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.services.persistence import PersistenceService


def test_persistence_round_trips_composition_config(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        composition_mode="plain_image",
        image_motion_enabled=True,
        subtitle_enabled=False,
        image_motion_mode="auto",
        image_motion_strength="subtle",
        image_fit_mode="cover",
    )

    data = service._config_to_dict(config)
    loaded = service._dict_to_config(data)

    assert loaded.composition_mode == "plain_image"
    assert loaded.image_motion_enabled is True
    assert loaded.subtitle_enabled is False
    assert loaded.image_motion_mode == "auto"
    assert loaded.image_motion_strength == "subtle"
    assert loaded.image_fit_mode == "cover"


def test_persistence_loads_old_config_with_template_defaults(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))

    loaded = service._dict_to_config({"media_width": 1080, "media_height": 1920})

    assert loaded.composition_mode == "template"
    assert loaded.image_motion_enabled is False
    assert loaded.subtitle_enabled is True
    assert loaded.image_motion_mode == "auto"
    assert loaded.image_motion_strength == "subtle"
    assert loaded.image_fit_mode == "cover"
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
uv run pytest tests/models/test_storyboard_config.py tests/services/test_persistence_config.py -v
```

Expected: FAIL because the new config fields are not defined.

- [ ] **Step 4: Implement config fields and persistence**

In `pixelle_video/models/storyboard.py`, add the fields after `template_params`:

```python
    composition_mode: str = "template"
    image_motion_enabled: bool = False
    subtitle_enabled: bool = True
    image_motion_mode: str = "auto"
    image_motion_strength: str = "subtle"
    image_fit_mode: str = "cover"
```

In `pixelle_video/services/persistence.py`, add these keys to `_config_to_dict()`:

```python
            "composition_mode": config.composition_mode,
            "image_motion_enabled": config.image_motion_enabled,
            "subtitle_enabled": config.subtitle_enabled,
            "image_motion_mode": config.image_motion_mode,
            "image_motion_strength": config.image_motion_strength,
            "image_fit_mode": config.image_fit_mode,
```

And pass them in `_dict_to_config()` with defaults:

```python
            composition_mode=data.get("composition_mode", "template"),
            image_motion_enabled=data.get("image_motion_enabled", False),
            subtitle_enabled=data.get("subtitle_enabled", True),
            image_motion_mode=data.get("image_motion_mode", "auto"),
            image_motion_strength=data.get("image_motion_strength", "subtle"),
            image_fit_mode=data.get("image_fit_mode", "cover"),
```

- [ ] **Step 5: Run tests to verify green**

Run:

```bash
uv run pytest tests/models/test_storyboard_config.py tests/services/test_persistence_config.py -v
```

Expected: PASS.

## Task 2: Pipeline Propagation

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Create: `tests/pipelines/test_standard_composition_config.py`

- [ ] **Step 1: Write failing pipeline tests**

Create `tests/pipelines/test_standard_composition_config.py`:

```python
import pytest

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class DummyCore:
    config = {"comfyui": {"image": {"prompt_prefix": ""}}}


@pytest.mark.asyncio
async def test_standard_pipeline_passes_composition_settings_to_storyboard_config():
    pipeline = StandardPipeline(DummyCore())
    ctx = PipelineContext(
        input_text="topic",
        params={
            "composition_mode": "plain_image",
            "image_motion_enabled": True,
            "subtitle_enabled": False,
            "image_motion_mode": "auto",
            "image_motion_strength": "subtle",
            "image_fit_mode": "cover",
            "media_width": 1080,
            "media_height": 1920,
            "media_workflow": "bizyair/image_o2.json",
        },
    )
    ctx.task_id = "task-1"
    ctx.title = "Title"
    ctx.narrations = ["第一段", "第二段"]
    ctx.image_prompts = ["prompt 1", "prompt 2"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.composition_mode == "plain_image"
    assert ctx.config.image_motion_enabled is True
    assert ctx.config.subtitle_enabled is False
    assert ctx.config.image_motion_mode == "auto"
    assert ctx.config.image_motion_strength == "subtle"
    assert ctx.config.image_fit_mode == "cover"


@pytest.mark.asyncio
async def test_plain_image_mode_requires_visual_prompts_even_with_static_template(monkeypatch):
    pipeline = StandardPipeline(DummyCore())
    ctx = PipelineContext(
        input_text="topic",
        params={
            "composition_mode": "plain_image",
            "frame_template": "1080x1920/static_default.html",
            "prompt_prefix": "",
        },
    )
    ctx.narrations = ["第一段"]

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base prompt"]

    monkeypatch.setattr("pixelle_video.pipelines.standard.generate_image_prompts", fake_generate_image_prompts)

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["base prompt"]
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv run pytest tests/pipelines/test_standard_composition_config.py -v
```

Expected: FAIL because the pipeline does not pass new config fields and static templates still skip visual prompts.

- [ ] **Step 3: Implement standard pipeline propagation**

In `plan_visuals()`, compute:

```python
        composition_mode = ctx.params.get("composition_mode", "template")
        pure_image_mode = composition_mode == "plain_image"
        template_requires_media = pure_image_mode or (template_type in ["image", "video"])
```

Log pure image mode as image generation. In `initialize_storyboard()`, pass the six new config values into `StoryboardConfig`.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
uv run pytest tests/pipelines/test_standard_composition_config.py -v
```

Expected: PASS.

## Task 3: Frame Processor Branching

**Files:**
- Modify: `pixelle_video/services/frame_processor.py`
- Create: `tests/services/test_frame_processor_composition.py`

- [ ] **Step 1: Write failing frame processor tests**

Create `tests/services/test_frame_processor_composition.py`:

```python
import pytest

from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor


class DummyCore:
    pass


def make_config(**overrides):
    values = {
        "task_id": "task-1",
        "media_width": 1080,
        "media_height": 1920,
        "composition_mode": "plain_image",
        "image_motion_enabled": True,
        "subtitle_enabled": True,
    }
    values.update(overrides)
    return StoryboardConfig(**values)


@pytest.mark.asyncio
async def test_plain_image_mode_skips_html_composition(monkeypatch):
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(index=0, narration="旁白", image_prompt="prompt", image_path="/tmp/image.png")
    frame.media_type = "image"

    async def fail_compose(*args, **kwargs):
        raise AssertionError("HTML composition should be skipped in plain image mode")

    monkeypatch.setattr(processor, "_compose_frame_html", fail_compose)

    await processor._step_compose_frame(frame, None, make_config())

    assert frame.composed_image_path is None


@pytest.mark.asyncio
async def test_plain_image_segment_uses_original_image(monkeypatch, tmp_path):
    calls = {}
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(index=0, narration="旁白", image_prompt="prompt")
    frame.media_type = "image"
    frame.image_path = str(tmp_path / "source.png")
    frame.audio_path = str(tmp_path / "audio.mp3")

    class FakeVideoService:
        def create_video_from_image_with_motion(self, **kwargs):
            calls.update(kwargs)
            return kwargs["output"]

    monkeypatch.setattr("pixelle_video.services.video.VideoService", FakeVideoService)

    await processor._step_create_video_segment(frame, make_config(task_id="task-plain"))

    assert calls["image"] == frame.image_path
    assert calls["audio"] == frame.audio_path
    assert calls["width"] == 1080
    assert calls["height"] == 1920
    assert calls["subtitle_text"] == "旁白"
    assert calls["motion_enabled"] is True
    assert calls["subtitle_enabled"] is True
    assert frame.video_segment_path == calls["output"]


@pytest.mark.asyncio
async def test_plain_image_mode_rejects_video_media():
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(index=0, narration="旁白", image_prompt="prompt")
    frame.media_type = "video"
    frame.video_path = "/tmp/video.mp4"
    frame.audio_path = "/tmp/audio.mp3"

    with pytest.raises(ValueError, match="Pure image mode only supports image media"):
        await processor._step_create_video_segment(frame, make_config())
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv run pytest tests/services/test_frame_processor_composition.py -v
```

Expected: FAIL because `plain_image` mode is not implemented.

- [ ] **Step 3: Implement frame processor mode branching**

Add helper checks in `FrameProcessor`:

```python
    def _is_plain_image_mode(self, config: StoryboardConfig) -> bool:
        if config.composition_mode not in {"template", "plain_image"}:
            raise ValueError(f"Unsupported composition mode: {config.composition_mode}")
        return config.composition_mode == "plain_image"
```

Use it in `_step_compose_frame()` to skip HTML composition in pure image mode. Use it in `_step_create_video_segment()` to call `create_video_from_image_with_motion(...)` for image frames and raise for video frames.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
uv run pytest tests/services/test_frame_processor_composition.py -v
```

Expected: PASS.

## Task 4: Video Service Motion and Subtitles

**Files:**
- Modify: `pixelle_video/services/video.py`
- Create: `tests/services/test_video_motion.py`

- [ ] **Step 1: Write failing video service tests**

Create `tests/services/test_video_motion.py`:

```python
import subprocess

import pytest
from PIL import Image

from pixelle_video.services.video import VideoService


def test_subtitle_text_is_wrapped_and_escaped():
    service = VideoService()

    wrapped = service._wrap_subtitle_text("这是一段很长的中文字幕需要自动换行", max_chars=8, max_lines=2)
    escaped = service._escape_drawtext_text(wrapped)

    assert "\\n" in escaped
    assert ":" not in escaped
    assert "'" not in escaped


def test_create_video_from_image_with_motion_outputs_segment(tmp_path):
    image_path = tmp_path / "image.png"
    audio_path = tmp_path / "audio.wav"
    output_path = tmp_path / "segment.mp4"

    Image.new("RGB", (640, 960), color=(80, 120, 160)).save(image_path)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.6",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
    )

    service = VideoService()
    result = service.create_video_from_image_with_motion(
        image=str(image_path),
        audio=str(audio_path),
        output=str(output_path),
        fps=12,
        width=360,
        height=640,
        subtitle_text="测试字幕",
        subtitle_enabled=True,
        motion_enabled=True,
        frame_index=1,
    )

    assert result == str(output_path)
    assert output_path.exists()

    probe = service._probe_video_geometry(str(output_path))
    assert probe == (360, 640)


def test_create_video_from_image_with_motion_validates_mode(tmp_path):
    service = VideoService()

    with pytest.raises(ValueError, match="Unsupported image fit mode"):
        service.create_video_from_image_with_motion(
            image=str(tmp_path / "missing.png"),
            audio=str(tmp_path / "missing.wav"),
            output=str(tmp_path / "out.mp4"),
            image_fit_mode="contain",
        )
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
uv run pytest tests/services/test_video_motion.py -v
```

Expected: FAIL because the new method and helpers do not exist.

- [ ] **Step 3: Implement video service helpers and method**

Add:

- `_probe_video_geometry(path) -> tuple[int, int]`
- `_find_subtitle_font() -> str`
- `_wrap_subtitle_text(text, max_chars=18, max_lines=2) -> str`
- `_escape_drawtext_text(text) -> str`
- `_build_plain_image_video_stream(...)`
- `create_video_from_image_with_motion(...)`

The method validates `image_fit_mode == "cover"`, `motion_mode == "auto"`, and `image_motion_strength == "subtle"`, probes audio duration, builds a cover-fitted video stream, applies motion with `zoompan` when enabled, overlays subtitles through `drawtext` when enabled, muxes AAC audio, and writes H.264/yuv420p MP4.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
uv run pytest tests/services/test_video_motion.py -v
```

Expected: PASS.

## Task 5: Web UI Propagation and Localization

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: Add localized strings**

Add keys:

```json
"style.composition_mode": "画面模式",
"style.composition_mode.template": "模板模式",
"style.composition_mode.plain_image": "纯图片模式",
"style.composition_mode_help": "选择使用模板合成画面，或直接用生成图片制作视频。",
"style.plain_image_hint": "纯图片模式会跳过模板，让生成插图铺满画面。",
"style.plain_image_size_info": "纯图片模式尺寸：{width}x{height}",
"style.image_motion_enabled": "动态图片效果",
"style.image_motion_help": "为静态图片添加轻微放大、缩小和平移动效。",
"style.subtitle_enabled": "显示字幕",
"style.subtitle_help": "在画面底部显示每段旁白字幕。"
```

Use equivalent English values in `en_US.json`.

- [ ] **Step 2: Add UI controls and return params**

In `render_style_config()`:

- Add a radio for composition mode before template controls.
- When mode is `template`, keep current template section behavior.
- When mode is `plain_image`, set:

```python
frame_template = st.session_state.get("selected_template", "1080x1920/default.html")
template_media_type = "image"
template_requires_media = True
media_width = 1080
media_height = 1920
custom_values_for_video = {}
```

- Show motion/subtitle checkboxes.
- Return the six new composition keys.

- [ ] **Step 3: Pass params through output preview**

In `render_single_output()` and `render_batch_output()`, include:

```python
"composition_mode": video_params.get("composition_mode", "template"),
"image_motion_enabled": video_params.get("image_motion_enabled", False),
"subtitle_enabled": video_params.get("subtitle_enabled", True),
"image_motion_mode": video_params.get("image_motion_mode", "auto"),
"image_motion_strength": video_params.get("image_motion_strength", "subtle"),
"image_fit_mode": video_params.get("image_fit_mode", "cover"),
```

Use `result.storyboard.config.media_width` and `media_height` for the generated video info caption when `composition_mode == "plain_image"`.

- [ ] **Step 4: Validate JSON**

Run:

```bash
uv run python -m json.tool web/i18n/locales/zh_CN.json >/tmp/zh_CN.json
uv run python -m json.tool web/i18n/locales/en_US.json >/tmp/en_US.json
```

Expected: both commands exit 0.

## Task 6: Full Verification and Runtime Check

**Files:**
- All touched implementation and test files.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
uv run pytest tests/models/test_storyboard_config.py tests/services/test_persistence_config.py tests/pipelines/test_standard_composition_config.py tests/services/test_frame_processor_composition.py tests/services/test_video_motion.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run --extra dev pytest -v
```

Expected: PASS.

- [ ] **Step 3: Run targeted lint**

Run:

```bash
uv run --extra dev ruff check pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py pixelle_video/services/video.py pixelle_video/services/persistence.py web/components/style_config.py web/components/output_preview.py tests
```

Expected: PASS or only pre-existing unrelated lint outside touched code. Fix touched-code issues.

- [ ] **Step 4: Restart Streamlit**

Run:

```bash
ps -Ao pid=,command= | awk '/streamlit run web\/app.py/ && !/awk/ {print $1}' | xargs -r kill
screen -ls | awk '/pixelle-video/ {print $1}' | xargs -r -I{} screen -S {} -X quit || true
screen -dmS pixelle-video bash -lc 'cd /Users/huazi/Pixelle-Video && export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" && uv run streamlit run web/app.py --server.headless true'
sleep 8
curl -I --max-time 10 http://localhost:8501
```

Expected: HTTP response headers from Streamlit.

- [ ] **Step 5: Commit implementation**

Run:

```bash
git status --short
git add docs/superpowers/plans/2026-06-21-pure-image-mode.md pixelle_video/models/storyboard.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py pixelle_video/services/video.py pixelle_video/services/persistence.py web/components/style_config.py web/components/output_preview.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/models/test_storyboard_config.py tests/services/test_persistence_config.py tests/pipelines/test_standard_composition_config.py tests/services/test_frame_processor_composition.py tests/services/test_video_motion.py
git commit -m "feat: add pure image composition mode"
```
