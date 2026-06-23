# MiniMax TTS API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MiniMax as a third TTS mode so users can preview and generate narration audio through MiniMax's synchronous T2A HTTP API.

**Architecture:** Extend the existing `TTSService` mode router with `minimax`, keeping local Edge TTS and ComfyUI workflows unchanged. MiniMax will build a non-streaming HTTP request, decode returned hex audio into a local mp3, and return that path to the existing frame duration and video assembly flow.

**Tech Stack:** Python async service code, `httpx`, Pydantic config schema, Streamlit UI, pytest, ruff.

---

## Files

- Modify `pixelle_video/config/schema.py`: add MiniMax TTS config defaults.
- Modify `pixelle_video/config/manager.py`: expose MiniMax config and save MiniMax API key.
- Modify `pixelle_video/services/tts_service.py`: route `inference_mode="minimax"` and implement `_call_minimax_tts`.
- Modify `pixelle_video/services/frame_processor.py`: pass MiniMax parameters to TTS service.
- Modify `pixelle_video/models/storyboard.py`: add MiniMax fields to storyboard config.
- Modify `pixelle_video/pipelines/standard.py`: map MiniMax UI params into storyboard config.
- Modify `pixelle_video/pipelines/custom.py`: keep custom pipeline compatible with MiniMax params.
- Modify `pixelle_video/services/persistence.py`: persist MiniMax storyboard fields.
- Modify `web/components/style_config.py`: add MiniMax controls and preview params.
- Modify `web/components/digital_tts_config.py`: add MiniMax controls and preview params.
- Modify `web/components/output_preview.py`: pass MiniMax params into single and batch generation.
- Modify `web/components/settings.py`: add MiniMax API key setting.
- Modify `web/pipelines/digital_human.py`: pass MiniMax params to direct TTS calls.
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: add labels.
- Modify `config.example.yaml`: document MiniMax config.
- Add or modify tests under `tests/`.

## Task 1: MiniMax Service Behavior Tests

**Files:**
- Create: `tests/services/test_minimax_tts_service.py`
- Modify later: `pixelle_video/services/tts_service.py`

- [ ] **Step 1: Write failing tests**

Create tests covering:

```python
import json
from pathlib import Path

import httpx
import pytest

from pixelle_video.services.tts_service import TTSService


class DummyCore:
    pass


@pytest.mark.asyncio
async def test_minimax_tts_decodes_hex_audio_and_writes_output(tmp_path, monkeypatch):
    captured = {}

    async def fake_post(self, url, *, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return httpx.Response(
            200,
            json={
                "data": {"audio": b"fake mp3".hex(), "status": 2},
                "extra_info": {"audio_length": 1200, "audio_format": "mp3"},
                "trace_id": "trace-123",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService(
        {
            "minimax": {
                "api_key": "sk-test",
                "model": "speech-2.8-turbo",
                "voice_id": "male-qn-qingse",
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            }
        },
        core=DummyCore(),
    )
    output_path = tmp_path / "audio.mp3"

    result = await service(
        text="大家好",
        inference_mode="minimax",
        output_path=str(output_path),
        voice="female-shaonv",
        speed=1.2,
        minimax_model="speech-2.8-hd",
        minimax_emotion="happy",
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"fake mp3"
    assert captured["url"] == "https://api.minimaxi.com/v1/t2a_v2"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "speech-2.8-hd"
    assert captured["json"]["text"] == "大家好"
    assert captured["json"]["stream"] is False
    assert captured["json"]["output_format"] == "hex"
    assert captured["json"]["voice_setting"] == {
        "voice_id": "female-shaonv",
        "speed": 1.2,
        "vol": 1.0,
        "pitch": 0,
        "emotion": "happy",
    }
    assert captured["json"]["audio_setting"]["format"] == "mp3"


@pytest.mark.asyncio
async def test_minimax_tts_uses_environment_api_key(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        assert headers["Authorization"] == "Bearer env-key"
        return httpx.Response(
            200,
            json={
                "data": {"audio": b"ok".hex(), "status": 2},
                "trace_id": "trace-env",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"minimax": {"api_key": ""}}, core=DummyCore())

    result = await service(
        text="hello",
        inference_mode="minimax",
        output_path=str(tmp_path / "audio.mp3"),
    )

    assert Path(result).exists()


@pytest.mark.asyncio
async def test_minimax_tts_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    service = TTSService({"minimax": {"api_key": ""}}, core=DummyCore())

    with pytest.raises(ValueError, match="MiniMax API key is not configured"):
        await service(
            text="hello",
            inference_mode="minimax",
            output_path=str(tmp_path / "audio.mp3"),
        )


@pytest.mark.asyncio
async def test_minimax_tts_reports_api_error(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        return httpx.Response(
            200,
            json={
                "data": None,
                "trace_id": "trace-bad",
                "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"minimax": {"api_key": "bad-key"}}, core=DummyCore())

    with pytest.raises(Exception, match="MiniMax TTS failed.*1004.*auth failed.*trace-bad"):
        await service(
            text="hello",
            inference_mode="minimax",
            output_path=str(tmp_path / "audio.mp3"),
        )


@pytest.mark.asyncio
async def test_minimax_tts_rejects_missing_audio(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        return httpx.Response(
            200,
            json={
                "data": {"status": 2},
                "trace_id": "trace-no-audio",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"minimax": {"api_key": "sk-test"}}, core=DummyCore())

    with pytest.raises(Exception, match="MiniMax TTS response did not include audio.*trace-no-audio"):
        await service(
            text="hello",
            inference_mode="minimax",
            output_path=str(tmp_path / "audio.mp3"),
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --extra dev pytest tests/services/test_minimax_tts_service.py -v
```

Expected: tests fail because `minimax` mode is not implemented.

## Task 2: MiniMax Service Implementation

**Files:**
- Modify: `pixelle_video/services/tts_service.py`

- [ ] **Step 1: Implement MiniMax routing and HTTP call**

Add mode branch and helper methods:

```python
if mode == "local":
    ...
if mode == "minimax":
    return await self._call_minimax_tts(...)
```

`_call_minimax_tts` must:

- Resolve config defaults from `self.config["minimax"]`.
- Resolve API key from explicit param, config, or `MINIMAX_API_KEY`.
- Build MiniMax request body.
- Call `https://api.minimaxi.com/v1/t2a_v2`.
- Validate `base_resp.status_code`.
- Decode `data.audio` from hex.
- Write bytes to `output_path`.

- [ ] **Step 2: Run MiniMax service tests**

Run:

```bash
uv run --extra dev pytest tests/services/test_minimax_tts_service.py -v
```

Expected: all tests pass.

## Task 3: Config Schema And Settings Persistence

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/manager.py`
- Modify: `web/components/settings.py`
- Modify: `config.example.yaml`

- [ ] **Step 1: Add config fields**

Add a `TTSMiniMaxConfig` model with:

- `api_key`
- `model`
- `voice_id`
- `speed`
- `vol`
- `pitch`
- `emotion`

Add it to `TTSSubConfig`.

- [ ] **Step 2: Expose config through manager**

`get_comfyui_config()` should return:

```python
"tts": {
    "default_workflow": ...,
    "inference_mode": ...,
    "local": ...,
    "comfyui": ...,
    "minimax": ...,
}
```

`set_comfyui_config()` should accept `minimax_api_key` and update `comfyui.tts.minimax.api_key`.

- [ ] **Step 3: Add settings UI field**

Add `MiniMax API Key` below BizyAir settings and save it through `set_comfyui_config`.

- [ ] **Step 4: Update example config**

Add MiniMax sample values under `comfyui.tts.minimax`.

## Task 4: Pipeline And Storyboard Parameter Plumbing

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/pipelines/digital_human.py`

- [ ] **Step 1: Add MiniMax fields to StoryboardConfig**

Add optional fields:

- `minimax_model`
- `minimax_voice_id`
- `minimax_emotion`

Use existing `tts_speed` for speed.

- [ ] **Step 2: Preserve MiniMax params in pipelines**

When `tts_inference_mode == "minimax"`, set `voice_id` to the selected MiniMax voice, keep workflow `None`, and copy MiniMax model and emotion into config.

- [ ] **Step 3: Pass MiniMax params from FrameProcessor**

For `config.tts_inference_mode == "minimax"`, pass:

```python
voice=config.minimax_voice_id or config.voice_id
speed=config.tts_speed
minimax_model=config.minimax_model
minimax_emotion=config.minimax_emotion
```

- [ ] **Step 4: Persist MiniMax fields**

Add MiniMax fields to storyboard config serialization/deserialization.

- [ ] **Step 5: Update direct TTS calls**

In output preview and digital-human paths, pass MiniMax params when selected.

## Task 5: TTS UI Controls And I18n

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/components/digital_tts_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: Add MiniMax labels**

Add labels for:

- mode name
- mode hint
- model
- voice
- custom voice ID
- emotion
- API key
- API key help/hint

- [ ] **Step 2: Add MiniMax controls to main style config**

Add radio option `minimax` and controls:

- model selectbox
- curated voice selectbox
- custom voice ID text input
- speed slider
- emotion selectbox

Return:

```python
"tts_inference_mode": "minimax",
"tts_voice": selected_minimax_voice,
"tts_speed": minimax_speed,
"minimax_model": minimax_model,
"minimax_emotion": minimax_emotion,
```

- [ ] **Step 3: Add MiniMax preview params**

Preview should pass same MiniMax params to `pixelle_video.tts`.

- [ ] **Step 4: Mirror controls in digital TTS config**

Keep behavior consistent in `web/components/digital_tts_config.py`.

## Task 6: Verification

**Files:**
- All touched files

- [ ] **Step 1: Run targeted tests**

Run:

```bash
uv run --extra dev pytest tests/services/test_minimax_tts_service.py -v
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run --extra dev pytest -v
```

- [ ] **Step 3: Run targeted lint**

Run:

```bash
uv run ruff check pixelle_video/services/tts_service.py pixelle_video/config/schema.py pixelle_video/config/manager.py pixelle_video/services/frame_processor.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py pixelle_video/services/persistence.py web/components/style_config.py web/components/digital_tts_config.py web/components/output_preview.py web/components/settings.py web/pipelines/digital_human.py tests/services/test_minimax_tts_service.py
```

- [ ] **Step 4: Start app**

Run:

```bash
./run_app.command
```

Expected: Streamlit app starts and the TTS mode selector includes MiniMax API.

- [ ] **Step 5: Commit implementation**

Stage only intentional files and commit:

```bash
git add pixelle_video web config.example.yaml tests docs/superpowers/plans/2026-06-21-minimax-tts-api.md
git commit -m "feat: add minimax tts api mode"
```

