# BizyAir Image Generation Workflow Design

Date: 2026-06-20

## Context

Pixelle-Video currently routes generated illustrations through `pixelle_video.media(...)`.
The Web UI discovers image generation options by scanning `workflows/<source>/image_*.json`
and showing them in the existing workflow selector. Existing sources include local
ComfyUI workflows under `selfhost/` and RunningHub workflows under `runninghub/`.

The target BizyAir model is the standard model API documented at:

- `https://bizyair.cn/modelzoo/bza-image-o2-official/text-to-image?tab=docs`
- `https://bizyair.cn/llms/modelzoo/bza-image-o2-official/text-to-image?lang=python`

This API is a standard Model Zoo task API, not a BizyAir WebApp API. It uses:

- Submit task: `POST https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/bza-image-o2-official/text-to-image`
- Query task: `GET https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/{request_id}`

The local working tree already contains partial BizyAir-related code, but that code is shaped around
the WebApp API (`/w/v1/webapp/...`, `web_app_id`, and `field_mapping`). This design intentionally
targets the standard Model Zoo API from the supplied documentation.

## Goal

Add BizyAir as a selectable image generation workflow source.

Users should be able to select a BizyAir image workflow from the existing "Image Generation"
workflow dropdown. When selected, Pixelle-Video should generate storyboard illustrations with
BizyAir while preserving the rest of the video pipeline:

1. Generate or split narration.
2. Generate image prompts.
3. Apply the prompt prefix.
4. Generate each illustration with BizyAir.
5. Download the returned image URL.
6. Compose HTML frames.
7. Build video segments and concatenate the final video.

## Non-Goals

The first implementation will not include:

- BizyAir WebApp API support.
- Webhook mode.
- File upload APIs.
- Image-to-image support.
- Video generation through BizyAir.
- Multi-image selection when an endpoint returns more than one image.
- A UI control for `quality`.
- BizyAir-specific parallel execution.
- A broad provider abstraction for all media backends.

## User Experience

BizyAir appears in the existing workflow selector as a normal workflow option, for example:

```text
image_o2.json - Bizyair
```

The user flow is:

1. Open the Web UI.
2. Configure LLM settings as usual.
3. Enter a BizyAir API key in system configuration.
4. Select an image template.
5. Select the BizyAir image workflow from the existing image workflow dropdown.
6. Generate a style preview or a full video.

No separate BizyAir-specific panel is required in the first version.

## Workflow Definition

Add a standard Model Zoo wrapper workflow under:

```text
workflows/bizyair/image_o2.json
```

Recommended shape:

```json
{
  "source": "bizyair",
  "api_type": "modelzoo",
  "endpoint": "bza-image-o2-official/text-to-image",
  "display_name": "BizyAir 通用图片O.2 文生图",
  "defaults": {
    "quality": "medium"
  }
}
```

The filename must start with `image_` so the current media workflow scanner includes it for
image templates. The `source` value tells `MediaService` to bypass ComfyKit and call BizyAir.

`api_type` is included to keep the format explicit. The first implementation only needs to support
`modelzoo`; unsupported values should produce a clear error.

## Configuration

Store the BizyAir API key in the existing media-backend configuration object:

```yaml
comfyui:
  bizyair_api_key: ""
```

Although the parent key is named `comfyui`, it already owns cloud media backend settings such as
RunningHub. Keeping BizyAir here minimizes churn and matches current configuration access patterns.

Runtime lookup order:

1. `config.yaml` value: `comfyui.bizyair_api_key`
2. Environment fallback: `BIZYAIR_API_KEY`

The Web UI system settings should expose a password input for "BizyAir API Key" below the existing
RunningHub cloud settings and persist it through `ConfigManager`.

## BizyAir API Contract

Submit request:

```http
POST https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/bza-image-o2-official/text-to-image
Authorization: Bearer <BIZYAIR_API_KEY>
Content-Type: application/json
X-BizyAir-Log-Mask-Fields: prompt
```

Request body:

```json
{
  "prompt": "final prompt",
  "width": 1080,
  "height": 1920,
  "quality": "medium"
}
```

Submit response:

```json
{
  "request_id": "4569bb94-1d30-417a-a987-9715de1e2633"
}
```

Poll request:

```http
GET https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/{request_id}
Authorization: Bearer <BIZYAIR_API_KEY>
```

Successful poll response:

```json
{
  "request_id": "4569bb94-1d30-417a-a987-9715de1e2633",
  "status": "Success",
  "message": null,
  "outputs": {
    "images": [
      "https://storage.bizyair.cn/outputs_examples/WpD9CsEByO82auMg.png"
    ]
  }
}
```

Supported task statuses:

- `Pending`: keep polling.
- `Running`: keep polling.
- `Saving`: keep polling.
- `Success`: return the first URL in `outputs.images`.
- `Failed`: raise an error using `message`.

Unknown non-terminal statuses should be logged and polled until timeout. Missing `request_id` or
missing `outputs.images` after `Success` should be treated as errors.

## Dimension Validation

Validate dimensions before submitting to BizyAir:

- `480 <= width <= 3840`
- `480 <= height <= 3840`
- `width % 16 == 0`
- `height % 16 == 0`
- `max(width, height) / min(width, height) <= 3`
- `655360 <= width * height <= 8294400`

If validation fails, raise a clear error. Do not silently resize, because the downstream HTML frame
composition expects media dimensions to match template metadata.

Existing standard templates such as `1080x1920`, `1920x1080`, and `1080x1080` satisfy these rules.

## Service Design

Extend workflow parsing so BizyAir wrapper metadata is included in workflow info:

- `source`
- `api_type`
- `endpoint`
- `display_name`, if present
- `defaults`, if present

Update `MediaService.__call__`:

1. Resolve the workflow as it does today.
2. Build `workflow_params` from `prompt`, `width`, `height`, and extra params.
3. If `workflow_info["source"] == "bizyair"`, call a BizyAir-specific method.
4. Otherwise, keep the current ComfyKit path for selfhost and RunningHub.

BizyAir-specific method:

1. Read API key from config or `BIZYAIR_API_KEY`.
2. Validate `api_type == "modelzoo"`.
3. Merge workflow defaults with runtime params.
4. Validate dimensions.
5. Submit the task with `httpx.AsyncClient`.
6. Poll every 5 seconds until success, failure, or timeout.
7. Return `MediaResult(media_type="image", url=image_url)`.

Suggested first-version polling limits:

- Poll interval: 5 seconds.
- Timeout: 10 minutes.

`quality` defaults to `medium`. It can be overridden by workflow JSON defaults or advanced params
later, but the first UI does not need a dedicated quality control.

## Error Handling

Errors should be actionable and visible in the Web UI through existing exception handling.

Required error cases:

- BizyAir API key is not configured.
- Workflow has `source=bizyair` but no `endpoint`.
- Unsupported BizyAir `api_type`.
- Width or height violates BizyAir constraints.
- Submit API returns an HTTP error.
- Submit response has no `request_id`.
- Poll API returns an HTTP error.
- Task status is `Failed`.
- Task times out.
- Task succeeds but does not include `outputs.images`.
- Downloading the returned image URL fails.

Logs should include `request_id` once available so the user can correlate a failed run with BizyAir
calling records.

## Concurrency

The first version should not add BizyAir parallel execution. Current parallel frame processing is
RunningHub-specific and controlled by `runninghub_concurrent_limit`.

BizyAir is also a cloud task API, but its practical rate limits and billing behavior need validation.
Start with serial execution. A later version can add `bizyair_concurrent_limit` and extend the
pipeline's parallel path to include `bizyair/` workflows.

## Testing

Automated tests should not call the real BizyAir API because it requires a live API key and consumes
coins.

Add mocked tests for:

- Workflow parsing of a `source=bizyair` Model Zoo wrapper.
- API key lookup from config and environment fallback.
- Dimension validation pass/fail cases.
- Successful task lifecycle: submit returns `request_id`, poll returns `Running`, then `Success`.
- Failed task lifecycle: poll returns `Failed` with `message`.
- Malformed success response with missing `outputs.images`.
- Timeout behavior.

Manual verification:

1. Put a valid BizyAir API key in system settings.
2. Select `bizyair/image_o2.json`.
3. Generate a style preview.
4. Confirm the preview image appears and the returned URL is downloaded during full video generation.

## Implementation Notes

Preserve user changes already present in the working tree. The current BizyAir-related code appears
to be a partial WebApp API implementation; the implementation should either replace that branch with
Model Zoo support or separate it behind `api_type == "webapp"` without making WebApp support part of
the first version.

Keep the integration scoped to image workflows. A selected BizyAir workflow should be treated as
`media_type="image"` even if future BizyAir endpoints support other outputs.

## Open Questions Resolved

- BizyAir should appear as a normal image workflow option in the current dropdown.
- The target API is the standard Model Zoo text-to-image API.
- First version quality should default to `medium`.
- First version should use polling, not webhook callbacks.
- First version should run serially.
