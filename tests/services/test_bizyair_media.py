
import httpx
import pytest

from pixelle_video.config.manager import ConfigManager
from pixelle_video.services.media import MediaService


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.bizyair.cn")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("HTTP error", request=request, response=response)


class FakeAsyncClient:
    posts = []
    gets = []
    post_responses = []
    get_responses = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.__class__.posts.append({"url": url, "headers": headers, "json": json})
        return self.__class__.post_responses.pop(0)

    async def get(self, url, headers=None):
        self.__class__.gets.append({"url": url, "headers": headers})
        return self.__class__.get_responses.pop(0)


async def no_sleep(_seconds):
    return None


@pytest.fixture(autouse=True)
def reset_fake_client(monkeypatch):
    FakeAsyncClient.posts = []
    FakeAsyncClient.gets = []
    FakeAsyncClient.post_responses = []
    FakeAsyncClient.get_responses = []
    monkeypatch.setattr("pixelle_video.services.media.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("pixelle_video.services.media.asyncio.sleep", no_sleep)


def make_service(api_key="test-key"):
    return MediaService(
        {
            "comfyui": {
                "bizyair_api_key": api_key,
                "image": {"default_workflow": "bizyair/image_o2.json"},
            }
        }
    )


def make_workflow_info():
    return {
        "source": "bizyair",
        "api_type": "modelzoo",
        "endpoint": "bza-image-o2-official/text-to-image",
        "defaults": {"quality": "medium"},
        "key": "bizyair/image_o2.json",
    }


@pytest.mark.asyncio
async def test_bizyair_modelzoo_successful_lifecycle():
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse({"request_id": "req-123", "status": "Running", "outputs": None}),
        FakeResponse(
            {
                "request_id": "req-123",
                "status": "Success",
                "outputs": {"images": ["https://storage.bizyair.cn/out.png"]},
            }
        ),
    ]

    result = await make_service()._call_bizyair_api(
        make_workflow_info(),
        {"prompt": "a dog", "width": 1080, "height": 1920},
    )

    assert result.media_type == "image"
    assert result.url == "https://storage.bizyair.cn/out.png"
    assert FakeAsyncClient.posts[0]["url"] == (
        "https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/"
        "bza-image-o2-official/text-to-image"
    )
    assert FakeAsyncClient.posts[0]["headers"]["Authorization"] == "Bearer test-key"
    assert FakeAsyncClient.posts[0]["headers"]["X-BizyAir-Log-Mask-Fields"] == "prompt"
    assert FakeAsyncClient.posts[0]["json"] == {
        "prompt": "a dog",
        "width": 1080,
        "height": 1920,
        "quality": "medium",
    }
    assert FakeAsyncClient.gets[-1]["url"] == (
        "https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi/req-123"
    )


@pytest.mark.asyncio
async def test_bizyair_modelzoo_accepts_wrapped_submit_response():
    FakeAsyncClient.post_responses = [
        FakeResponse(
            {
                "code": 20000,
                "message": "Ok",
                "status": True,
                "data": {"request_id": "req-123"},
            }
        )
    ]
    FakeAsyncClient.get_responses = [
        FakeResponse(
            {
                "request_id": "req-123",
                "status": "Success",
                "outputs": {"images": ["https://storage.bizyair.cn/out.png"]},
            }
        )
    ]

    result = await make_service()._call_bizyair_api(
        make_workflow_info(),
        {"prompt": "a dog", "width": 1080, "height": 1920},
    )

    assert result.media_type == "image"
    assert result.url == "https://storage.bizyair.cn/out.png"


@pytest.mark.asyncio
async def test_bizyair_modelzoo_accepts_wrapped_poll_response():
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse(
            {
                "code": 20000,
                "message": "Ok",
                "status": True,
                "data": {
                    "request_id": "req-123",
                    "status": "Success",
                    "outputs": {"images": ["https://storage.bizyair.cn/out.png"]},
                },
            }
        )
    ]

    result = await make_service()._call_bizyair_api(
        make_workflow_info(),
        {"prompt": "a dog", "width": 1080, "height": 1920},
    )

    assert result.media_type == "image"
    assert result.url == "https://storage.bizyair.cn/out.png"


@pytest.mark.asyncio
async def test_bizyair_api_key_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("BIZYAIR_API_KEY", "env-key")
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse(
            {
                "request_id": "req-123",
                "status": "Success",
                "outputs": {"images": ["https://storage.bizyair.cn/out.png"]},
            }
        )
    ]

    result = await make_service(api_key=None)._call_bizyair_api(
        make_workflow_info(),
        {"prompt": "a dog", "width": 1080, "height": 1920},
    )

    assert result.url == "https://storage.bizyair.cn/out.png"
    assert FakeAsyncClient.posts[0]["headers"]["Authorization"] == "Bearer env-key"


@pytest.mark.asyncio
async def test_bizyair_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("BIZYAIR_API_KEY", raising=False)

    with pytest.raises(ValueError, match="BizyAir API key not configured"):
        await make_service(api_key=None)._call_bizyair_api(
            make_workflow_info(),
            {"prompt": "a dog", "width": 1080, "height": 1920},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("width", "height", "message"),
    [
        (479, 1024, "between 480 and 3840"),
        (1025, 1024, "multiples of 16"),
        (3840, 1024, "aspect ratio"),
        (512, 512, "total pixels"),
    ],
)
async def test_bizyair_dimension_validation(width, height, message):
    with pytest.raises(ValueError, match=message):
        await make_service()._call_bizyair_api(
            make_workflow_info(),
            {"prompt": "a dog", "width": width, "height": height},
        )


@pytest.mark.asyncio
async def test_bizyair_failed_status_raises_message():
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse(
            {"request_id": "req-123", "status": "Failed", "message": "No image generated."}
        )
    ]

    with pytest.raises(RuntimeError, match="No image generated"):
        await make_service()._call_bizyair_api(
            make_workflow_info(),
            {"prompt": "a dog", "width": 1080, "height": 1920},
        )


@pytest.mark.asyncio
async def test_bizyair_success_without_image_raises():
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse({"request_id": "req-123", "status": "Success", "outputs": {"images": []}})
    ]

    with pytest.raises(RuntimeError, match="returned no image URL"):
        await make_service()._call_bizyair_api(
            make_workflow_info(),
            {"prompt": "a dog", "width": 1080, "height": 1920},
        )


@pytest.mark.asyncio
async def test_bizyair_timeout_raises():
    FakeAsyncClient.post_responses = [FakeResponse({"request_id": "req-123"})]
    FakeAsyncClient.get_responses = [
        FakeResponse({"request_id": "req-123", "status": "Running", "outputs": None})
        for _ in range(2)
    ]

    service = make_service()
    service.BIZYAIR_MAX_POLL_ATTEMPTS = 2

    with pytest.raises(TimeoutError, match="timed out"):
        await service._call_bizyair_api(
            make_workflow_info(),
            {"prompt": "a dog", "width": 1080, "height": 1920},
        )


def test_config_manager_round_trips_bizyair_api_key(tmp_path):
    config_path = tmp_path / "config.yaml"
    original_instance = ConfigManager._instance
    ConfigManager._instance = None

    try:
        manager = ConfigManager(str(config_path))

        manager.set_comfyui_config(bizyair_api_key="bizy-key")

        comfyui_config = manager.get_comfyui_config()
        assert comfyui_config["bizyair_api_key"] == "bizy-key"
    finally:
        ConfigManager._instance = original_instance
