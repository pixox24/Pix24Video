# Resumable Generation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve partially generated video tasks when generation fails and allow users to continue from saved assets instead of starting over.

**Architecture:** Keep the existing filesystem persistence model. Add a resume path to `StandardPipeline` that loads a saved storyboard, validates lightweight asset existence, skips valid completed steps, and updates metadata/storyboard during generation. Expose resume through `HistoryManager` and the History Streamlit page for failed or running tasks.

**Tech Stack:** Python dataclasses, filesystem JSON persistence, Streamlit UI, pytest, existing Pixelle-Video pipeline services.

---

## File Structure

- Modify `pixelle_video/models/storyboard.py`
  - Add per-frame status/error/completed step fields while preserving backward compatibility.
- Modify `pixelle_video/services/persistence.py`
  - Persist new frame fields and support saving running/failed metadata.
- Modify `pixelle_video/services/frame_processor.py`
  - Validate existing assets before skipping generation.
  - Save storyboard after each successful frame step.
  - Mark failed step on frame errors.
- Modify `pixelle_video/pipelines/standard.py`
  - Save running metadata early.
  - Persist storyboard after content planning and each frame.
  - Add `resume_task_id` path to reuse a saved storyboard and continue from missing/failed assets.
  - Save failed metadata in exception handling.
- Modify `pixelle_video/services/history_manager.py`
  - Add `resume_task` wrapper that loads metadata input and calls `generate_video` with `resume_task_id`.
- Modify `web/pages/2_📚_History.py`
  - Show failure status and add a continue button for failed/running tasks.
- Test `tests/pipelines/test_resumable_generation.py`
  - Cover resume loading, asset validation skip behavior, and failed metadata persistence.

## Task 1: Storyboard Resume State

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/pipelines/test_resumable_generation.py`

- [ ] **Step 1: Write failing tests for frame resume fields persistence**

Create `tests/pipelines/test_resumable_generation.py` with:

```python
from datetime import datetime

import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.persistence import PersistenceService


@pytest.mark.asyncio
async def test_persistence_round_trips_frame_resume_state(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path / "output"))
    frame = StoryboardFrame(
        index=0,
        narration="hello",
        image_prompt="image prompt",
        audio_path="output/task/frames/01_audio.mp3",
        image_path="output/task/frames/01_image.png",
        video_segment_path=None,
        created_at=datetime.now(),
    )
    frame.status = "failed"
    frame.completed_steps = {"audio": True, "media": True, "compose": False, "segment": False}
    frame.errors = {"segment": "ffmpeg failed"}

    storyboard = Storyboard(
        title="Title",
        config=StoryboardConfig(
            media_width=1080,
            media_height=1920,
            task_id="task",
        ),
        frames=[frame],
    )

    await persistence.save_storyboard("task", storyboard)
    loaded = await persistence.load_storyboard("task")

    assert loaded.frames[0].status == "failed"
    assert loaded.frames[0].completed_steps == {
        "audio": True,
        "media": True,
        "compose": False,
        "segment": False,
    }
    assert loaded.frames[0].errors == {"segment": "ffmpeg failed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_persistence_round_trips_frame_resume_state -v
```

Expected: FAIL because `StoryboardFrame` has no `status`, `completed_steps`, or `errors` fields.

- [ ] **Step 3: Implement frame resume fields**

In `pixelle_video/models/storyboard.py`, extend `StoryboardFrame`:

```python
    status: str = "pending"
    completed_steps: Dict[str, bool] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
```

In `__post_init__`, initialize missing step keys:

```python
        defaults = {"audio": False, "media": False, "compose": False, "segment": False}
        defaults.update(self.completed_steps)
        self.completed_steps = defaults
```

In `pixelle_video/services/persistence.py`, include these keys in `_frame_to_dict` and `_dict_to_frame`, defaulting old tasks to pending/empty.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_persistence_round_trips_frame_resume_state -v
```

Expected: PASS.

## Task 2: Asset Validation in Frame Processing

**Files:**
- Modify: `pixelle_video/services/frame_processor.py`
- Test: `tests/pipelines/test_resumable_generation.py`

- [ ] **Step 1: Write failing tests for asset validation**

Append:

```python
from pathlib import Path

from pixelle_video.services.frame_processor import FrameProcessor


def test_frame_processor_reuses_existing_nonempty_asset(tmp_path):
    processor = FrameProcessor(pixelle_video_core=object())
    asset = tmp_path / "asset.mp3"
    asset.write_bytes(b"audio")

    assert processor._is_existing_asset_valid(str(asset)) is True


def test_frame_processor_rejects_missing_or_empty_asset(tmp_path):
    processor = FrameProcessor(pixelle_video_core=object())
    empty_asset = tmp_path / "empty.mp3"
    empty_asset.write_bytes(b"")

    assert processor._is_existing_asset_valid(str(tmp_path / "missing.mp3")) is False
    assert processor._is_existing_asset_valid(str(empty_asset)) is False
    assert processor._is_existing_asset_valid(None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_frame_processor_reuses_existing_nonempty_asset tests/pipelines/test_resumable_generation.py::test_frame_processor_rejects_missing_or_empty_asset -v
```

Expected: FAIL because `_is_existing_asset_valid` does not exist.

- [ ] **Step 3: Implement validation helper and use it**

Add `FrameProcessor._is_existing_asset_valid(path)`:

```python
    def _is_existing_asset_valid(self, path: Optional[str]) -> bool:
        if not path:
            return False
        try:
            from pathlib import Path
            asset = Path(path)
            return asset.exists() and asset.is_file() and asset.stat().st_size > 0
        except OSError:
            return False
```

Use it before skipping audio/media/segment work:

- Keep `frame.audio_path` only if valid; otherwise clear it.
- Keep `frame.image_path` or `frame.video_path` only if valid; otherwise clear invalid paths.
- Mark `completed_steps["audio"]`, `completed_steps["media"]`, `completed_steps["compose"]`, and `completed_steps["segment"]` after successful steps.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_frame_processor_reuses_existing_nonempty_asset tests/pipelines/test_resumable_generation.py::test_frame_processor_rejects_missing_or_empty_asset -v
```

Expected: PASS.

## Task 3: Persist Running, Failed, and Resumed Standard Tasks

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/pipelines/test_resumable_generation.py`

- [ ] **Step 1: Write failing tests for resume context loading**

Append:

```python
from types import SimpleNamespace

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class ResumePersistence:
    def __init__(self, storyboard):
        self.storyboard = storyboard
        self.saved_metadata = []
        self.saved_storyboards = []
        self.status_updates = []

    async def load_storyboard(self, task_id):
        return self.storyboard

    async def save_task_metadata(self, task_id, metadata):
        self.saved_metadata.append((task_id, metadata))

    async def save_storyboard(self, task_id, storyboard):
        self.saved_storyboards.append((task_id, storyboard))

    async def update_task_status(self, task_id, status, error=None):
        self.status_updates.append((task_id, status, error))


class ResumeCore:
    def __init__(self, storyboard):
        self.config = {"comfyui": {"image": {"prompt_prefix": ""}}}
        self.llm = object()
        self.persistence = ResumePersistence(storyboard)


@pytest.mark.asyncio
async def test_standard_pipeline_setup_loads_resume_storyboard(tmp_path):
    audio = tmp_path / "01_audio.mp3"
    audio.write_bytes(b"audio")
    frame = StoryboardFrame(
        index=0,
        narration="kept narration",
        image_prompt="kept prompt",
        audio_path=str(audio),
    )
    storyboard = Storyboard(
        title="Kept title",
        config=StoryboardConfig(media_width=1080, media_height=1920, task_id="task"),
        frames=[frame],
    )
    pipeline = StandardPipeline(ResumeCore(storyboard))
    ctx = PipelineContext(
        input_text="new input ignored for resume content",
        params={"resume_task_id": "task", "text": "new input ignored for resume content"},
    )

    await pipeline.setup_environment(ctx)

    assert ctx.task_id == "task"
    assert ctx.storyboard is storyboard
    assert ctx.title == "Kept title"
    assert ctx.narrations == ["kept narration"]
    assert ctx.image_prompts == ["kept prompt"]
    assert ctx.params["resume"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_standard_pipeline_setup_loads_resume_storyboard -v
```

Expected: FAIL because `resume_task_id` is ignored.

- [ ] **Step 3: Implement resume setup**

In `StandardPipeline.setup_environment`, when `ctx.params.get("resume_task_id")` exists:

- Load storyboard from persistence.
- Set `ctx.task_id`, `ctx.task_dir`, `ctx.final_video_path`.
- Set `ctx.storyboard`, `ctx.config`, `ctx.title`, `ctx.narrations`, `ctx.image_prompts`.
- Set `ctx.params["resume"] = True`.
- Save task metadata as `running`.

In `generate_content`, `determine_title`, `plan_visuals`, and `initialize_storyboard`, return early when `ctx.params.get("resume")` is true and `ctx.storyboard` is loaded.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py::test_standard_pipeline_setup_loads_resume_storyboard -v
```

Expected: PASS.

- [ ] **Step 5: Implement failed metadata handling**

Override `StandardPipeline.handle_exception(ctx, error)` to:

- Save available storyboard if present.
- Save/update task metadata with `status="failed"`, `error=str(error)`, `failed_stage`, and `failed_frame_index` if available.
- Avoid raising inside persistence failure handling.

Update `produce_assets` to set `ctx.current_stage = "frame_processing"` and `ctx.current_frame_index = i` before processing each frame.

- [ ] **Step 6: Run targeted pipeline tests**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py tests/pipelines/test_standard_composition_config.py -v
```

Expected: PASS.

## Task 4: Continue From History UI

**Files:**
- Modify: `pixelle_video/services/history_manager.py`
- Modify: `web/pages/2_📚_History.py`

- [ ] **Step 1: Add HistoryManager resume API**

Add:

```python
    async def resume_task(self, task_id: str, pixelle_video, progress_callback=None):
        metadata = await self.persistence.load_task_metadata(task_id)
        if not metadata:
            raise ValueError(f"Task {task_id} not found")
        input_params = dict(metadata.get("input", {}))
        text = input_params.pop("text", "")
        input_params["resume_task_id"] = task_id
        if progress_callback:
            input_params["progress_callback"] = progress_callback
        return await pixelle_video.generate_video(text=text, **input_params)
```

- [ ] **Step 2: Add Streamlit continue action**

In `render_task_detail_modal`, when `metadata["status"]` is `failed` or `running`, show:

- error text if present
- a `继续生成` button
- progress bar/status text
- call `run_async(pixelle_video.history.resume_task(task_id, pixelle_video, progress_callback=...))`
- on success show video path and rerun
- on failure show error and keep the task failed

In `render_grid_task_card`, show a small continue button for failed/running tasks that opens detail view.

- [ ] **Step 3: Run import/lint check**

Run:

```bash
uv run ruff check pixelle_video/services/history_manager.py 'web/pages/2_📚_History.py'
```

Expected: PASS.

## Task 5: Full Verification and Commit

**Files:**
- All files touched above.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run --extra dev pytest tests/pipelines/test_resumable_generation.py tests/pipelines/test_standard_composition_config.py tests/services/test_persistence_config.py tests/services/test_frame_processor_composition.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run --extra dev pytest -v
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
uv run ruff check pixelle_video/models/storyboard.py pixelle_video/services/persistence.py pixelle_video/services/frame_processor.py pixelle_video/pipelines/standard.py pixelle_video/services/history_manager.py 'web/pages/2_📚_History.py' tests/pipelines/test_resumable_generation.py
```

Expected: PASS.

- [ ] **Step 4: Stage only resumable generation files**

Run:

```bash
git add docs/superpowers/plans/2026-06-21-resumable-generation-mvp.md \
  pixelle_video/models/storyboard.py \
  pixelle_video/services/persistence.py \
  pixelle_video/services/frame_processor.py \
  pixelle_video/pipelines/standard.py \
  pixelle_video/services/history_manager.py \
  'web/pages/2_📚_History.py'
git add -f tests/pipelines/test_resumable_generation.py
```

Do not stage existing unrelated changes in:

- `pixelle_video/services/tts_service.py`
- `tests/services/test_minimax_tts_service.py`
- `workflows/bizyair/image_o2.json`
- `.playwright-cli/`
- `workflows/bizyair/image_o2_副本.json`

- [ ] **Step 5: Commit**

Run:

```bash
git commit -m "feat: add resumable generation drafts"
```

Expected: commit succeeds.

