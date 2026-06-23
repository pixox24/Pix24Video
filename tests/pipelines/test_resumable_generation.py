from datetime import datetime

import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.history_manager import HistoryManager
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
        self.tts = object()
        self.media = object()
        self.video = object()
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


@pytest.mark.asyncio
async def test_standard_pipeline_handle_exception_persists_failed_task():
    frame = StoryboardFrame(
        index=0,
        narration="narration",
        image_prompt="prompt",
    )
    storyboard = Storyboard(
        title="Failed title",
        config=StoryboardConfig(media_width=1080, media_height=1920, task_id="task"),
        frames=[frame],
    )
    core = ResumeCore(storyboard)
    pipeline = StandardPipeline(core)
    ctx = PipelineContext(input_text="topic", params={"text": "topic"})
    ctx.task_id = "task"
    ctx.final_video_path = "output/task/final.mp4"
    ctx.storyboard = storyboard
    ctx.current_stage = "frame_processing"
    ctx.current_frame_index = 0

    await pipeline.handle_exception(ctx, RuntimeError("image failed"))

    assert core.persistence.saved_storyboards[-1] == ("task", storyboard)
    task_id, metadata = core.persistence.saved_metadata[-1]
    assert task_id == "task"
    assert metadata["status"] == "failed"
    assert metadata["error"] == "image failed"
    assert metadata["failed_stage"] == "frame_processing"
    assert metadata["failed_frame_index"] == 0


class ResumeHistoryPersistence:
    async def load_task_metadata(self, task_id):
        return {
            "task_id": task_id,
            "status": "failed",
            "input": {
                "text": "topic",
                "mode": "generate",
                "title": "Title",
            },
        }


class ResumePixelleVideo:
    def __init__(self):
        self.calls = []

    async def generate_video(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "result"


@pytest.mark.asyncio
async def test_history_manager_resume_task_calls_generate_video_with_resume_id():
    history = HistoryManager(ResumeHistoryPersistence())
    pixelle_video = ResumePixelleVideo()

    result = await history.resume_task("task", pixelle_video)

    assert result == "result"
    assert pixelle_video.calls == [
        (
            "topic",
            {
                "mode": "generate",
                "title": "Title",
                "resume_task_id": "task",
            },
        )
    ]
