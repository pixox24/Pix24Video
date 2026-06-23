# MiniMax TTS API Integration Design

Date: 2026-06-21

## Goal

Add MiniMax as a first-class audio synthesis backend in the existing audio synthesis module. The user should be able to choose MiniMax API from the UI, preview generated speech, and use it during normal video generation without changing the downstream storyboard, frame composition, or final video stitching flow.

MiniMax should appear as an independent TTS mode:

```text
Local / ComfyUI / MiniMax API
```

It should not be represented as a ComfyUI workflow because MiniMax T2A HTTP is a direct cloud API and returns generated audio data directly.

## Source References

- MiniMax synchronous T2A HTTP API: https://platform.minimaxi.com/docs/api-reference/speech-t2a-http
- MiniMax API overview: https://platform.minimaxi.com/docs/api-reference/api-overview
- MiniMax system voice list: https://platform.minimaxi.com/docs/faq/system-voice-id
- MiniMax voice query API: https://platform.minimaxi.com/docs/api-reference/voice-management-get

## Current System Context

The existing TTS system has two modes:

- `local`: Edge TTS, implemented in `pixelle_video/services/tts_service.py`.
- `comfyui`: ComfyUI or RunningHub workflow execution, also routed through `TTSService`.

Key integration points:

- `pixelle_video/services/tts_service.py`
  - Main TTS service entry point.
  - Currently branches between local Edge TTS and ComfyUI workflow execution.
- `pixelle_video/services/frame_processor.py`
  - Generates one audio file per storyboard frame.
  - Passes `inference_mode`, narration text, output path, voice, speed, workflow, and reference audio into `core.tts`.
- `pixelle_video/models/storyboard.py`
  - Stores `tts_inference_mode`, `voice_id`, `tts_workflow`, `tts_speed`, and `ref_audio`.
- `pixelle_video/config/schema.py` and `pixelle_video/config/manager.py`
  - Define and expose persisted app configuration.
- `web/components/style_config.py`
  - Main video TTS UI, including preview.
- `web/components/digital_tts_config.py`
  - Digital-human TTS UI, including preview.
- `web/components/output_preview.py`
  - Passes selected TTS parameters into video generation.

The existing generation pipeline processes narration in segments. Each segment gets one audio file, and downstream logic derives frame duration from that audio file. MiniMax integration should preserve this behavior.

## Recommended Approach

Implement `minimax` as a third TTS inference mode.

```python
tts_inference_mode = "minimax"
```

`TTSService.__call__` should route as follows:

```text
local   -> _call_local_tts
comfyui -> _call_comfyui_workflow
minimax -> _call_minimax_tts
```

The MiniMax backend will call the synchronous HTTP endpoint:

```text
POST https://api.minimaxi.com/v1/t2a_v2
Authorization: Bearer <MINIMAX_API_KEY>
Content-Type: application/json
```

The first implementation will use non-streaming output and write an audio file locally. This keeps the generated audio compatible with current duration probing and video assembly.

## User-Facing Behavior

### Settings

Add a MiniMax cloud configuration section in advanced settings, near the existing RunningHub and BizyAir cloud keys.

Fields:

- `MiniMax API Key`

Optional future fields can be added later if needed:

- Base URL override.
- Account-specific voice loading.
- Default model.
- Default voice.

For the first version, keep settings simple and only persist the API key.

### TTS Mode UI

Update the TTS mode selector from:

```text
local / comfyui
```

to:

```text
local / comfyui / minimax
```

Chinese labels:

- 本地合成
- ComfyUI 合成
- MiniMax API

English labels:

- Local
- ComfyUI
- MiniMax API

When MiniMax mode is selected, show MiniMax-specific controls:

- Model selector.
- Voice ID selector or input.
- Speed slider.
- Optional emotion selector.

Default values:

- Model: `speech-2.8-turbo`
- Voice ID: `male-qn-qingse`
- Speed: `1.0`
- Volume: `1`
- Pitch: `0`
- Output format: `mp3`
- Sample rate: `32000`
- Bitrate: `128000`
- Channel: `1`
- Stream: `false`
- Output format response: `hex`
- Subtitle generation from MiniMax: disabled
- AIGC watermark: disabled unless MiniMax requires otherwise

The voice control should allow direct manual entry of a voice ID. A small curated dropdown can be provided for common system voices, but manual entry is important because MiniMax also supports account-specific cloned or generated voices.

Initial curated voice list:

- `male-qn-qingse`
- `male-qn-jingying`
- `male-qn-daxuesheng`
- `female-shaonv`
- `female-yujie`
- `female-chengshu`
- `female-tianmei`
- `Chinese (Mandarin)_News_Anchor`
- `Chinese (Mandarin)_Warm_Girl`
- `Chinese (Mandarin)_Gentleman`

### Preview

The existing TTS preview should support MiniMax mode.

Preview flow:

1. User selects MiniMax mode.
2. User enters preview text.
3. App calls `pixelle_video.tts(text=..., inference_mode="minimax", ...)`.
4. MiniMax response audio is saved as a local `mp3`.
5. Streamlit plays the generated local file.

If the MiniMax API key is missing, preview should fail with a direct message explaining that MiniMax API Key must be configured first.

### Video Generation

During normal video generation, MiniMax should be used per storyboard frame, matching the existing TTS model:

```text
frame narration -> MiniMax T2A -> local mp3 -> duration probe -> video segment
```

No downstream video composition changes are required.

## Configuration Design

Add a MiniMax config object under the existing TTS configuration tree:

```yaml
comfyui:
  tts:
    inference_mode: minimax
    minimax:
      api_key: ""
      model: speech-2.8-turbo
      voice_id: male-qn-qingse
      speed: 1.0
      vol: 1.0
      pitch: 0
      emotion: null
```

This placement is slightly imperfect because MiniMax is not ComfyUI. However, the current app already groups cloud generation settings under `comfyui`, and moving the broader config structure would be unrelated churn. A future provider-oriented config tree can be introduced if more TTS providers are added.

Also support environment fallback:

```text
MINIMAX_API_KEY
```

Resolution order:

1. Explicit call parameter, if provided.
2. Saved app config.
3. `MINIMAX_API_KEY` environment variable.
4. Error.

## API Request Design

Request body for first version:

```json
{
  "model": "speech-2.8-turbo",
  "text": "旁白文本",
  "stream": false,
  "voice_setting": {
    "voice_id": "male-qn-qingse",
    "speed": 1.0,
    "vol": 1.0,
    "pitch": 0
  },
  "audio_setting": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1
  },
  "subtitle_enable": false,
  "output_format": "hex"
}
```

If emotion is selected, include it in `voice_setting`. If emotion is not selected, omit the field so MiniMax can infer expression from text.

## Response Handling

Expected successful response:

```text
data.audio: hex-encoded audio
data.status: 2
base_resp.status_code: 0
base_resp.status_msg: success
trace_id: MiniMax trace id
extra_info.audio_length: duration in milliseconds
```

Handling rules:

- Check HTTP status first.
- Parse JSON.
- Check `base_resp.status_code == 0`.
- Check `data` is present.
- Check `data.audio` is present.
- Decode `data.audio` from hex to bytes.
- Ensure the output directory exists.
- Write bytes to `output_path`.
- Return `output_path`.

The service should not rely on MiniMax `extra_info.audio_length` for frame duration. It can log that metadata, but the current code should continue probing the written audio file so all backends behave consistently.

If `output_format=url` is added later, response handling can be expanded to download the returned URL. First version should stay with `hex` to avoid URL expiry and extra download handling.

## Error Handling

MiniMax failures should surface actionable messages.

Examples:

- Missing API key:
  - `MiniMax API key is not configured. Please set it in Advanced Settings or MINIMAX_API_KEY.`
- Authentication failure:
  - Include MiniMax status code and status message.
- Rate limit:
  - Include MiniMax status code and trace ID.
- Missing audio data:
  - Include a sanitized summary of response keys and trace ID.
- Invalid hex:
  - Include trace ID and a short decode failure message.

Do not log API keys.

MiniMax documented API-level errors include authentication failure, timeout, rate limits, TPM limits, invalid character ratio, and invalid parameters. These should not be collapsed into a generic "No audio generated" message.

## Concurrency And Ordering

The current storyboard flow generates TTS per frame as part of frame processing. The first MiniMax version should follow the same behavior and not introduce independent concurrency controls.

Reasoning:

- It preserves current audio/video synchronization behavior.
- It avoids accidental API rate limit spikes.
- It keeps debugging simple.

If the current pipeline processes multiple frames concurrently in some modes, MiniMax calls will naturally follow that pipeline behavior. A provider-level semaphore can be added later if rate limits become a practical issue.

## Scope

In scope:

- Add `minimax` TTS inference mode.
- Add MiniMax API key configuration.
- Add MiniMax-specific model, voice, speed, optional emotion UI.
- Support TTS preview with MiniMax.
- Support normal video generation with MiniMax audio.
- Decode MiniMax hex audio and write local mp3 files.
- Add focused tests for request construction, response decoding, config defaults, and error messages.
- Update Chinese and English UI text.
- Update `config.example.yaml` if present and aligned with existing config examples.

Out of scope for first version:

- Streaming TTS playback.
- Async long-text TTS API.
- Voice cloning upload or management UI.
- Full account voice browser using `/v1/get_voice`.
- MiniMax subtitles.
- MiniMax base URL customization in UI.
- Provider-wide TTS architecture refactor.
- Parallel batch tuning for MiniMax rate limits.

## Testing Plan

Unit tests:

- MiniMax request body includes required fields.
- API key resolution works from config and environment.
- Successful hex response writes an mp3 file and returns the output path.
- MiniMax `base_resp.status_code != 0` raises a clear exception.
- Missing `data.audio` raises a clear exception.
- Invalid hex raises a clear exception.
- Existing local and ComfyUI TTS paths remain unchanged.

UI/parameter tests where practical:

- MiniMax mode appears in the mode selector.
- MiniMax preview passes `inference_mode="minimax"`.
- Video generation passes MiniMax voice/model/speed parameters through to the pipeline.

Manual verification:

- Configure MiniMax API key.
- Generate TTS preview.
- Generate a short one-scene video in MiniMax mode.
- Confirm the generated audio file exists and the final video has audio.
- Confirm local and ComfyUI modes still preview and generate as before.

## Implementation Notes

The smallest safe implementation path is:

1. Add MiniMax config schema.
2. Expose MiniMax config through `ConfigManager`.
3. Add `_call_minimax_tts` to `TTSService`.
4. Update `FrameProcessor` and pipeline parameter mapping so `minimax` passes voice/model/speed instead of workflow/ref audio.
5. Update Streamlit TTS UI and preview logic.
6. Update output generation parameter passing.
7. Add i18n labels.
8. Add tests.
9. Run targeted lint and test suite.

## Open Decisions

The following defaults are selected for first implementation unless the user changes them:

- MiniMax appears as a third independent mode.
- Default model is `speech-2.8-turbo`.
- Default voice is `male-qn-qingse`.
- Output is non-streaming `mp3` via hex response.
- API key is stored in app config and can fall back to `MINIMAX_API_KEY`.

