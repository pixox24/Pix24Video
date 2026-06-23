from pathlib import Path

import httpx
import pytest

from pixelle_video.config.manager import ConfigManager
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
async def test_minimax_tts_prefers_environment_api_key_over_saved_config(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        assert headers["Authorization"] == "Bearer env-key"
        return httpx.Response(
            200,
            json={
                "data": {"audio": b"ok".hex(), "status": 2},
                "trace_id": "trace-env-priority",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"minimax": {"api_key": "saved-config-key"}}, core=DummyCore())

    result = await service(
        text="hello",
        inference_mode="minimax",
        output_path=str(tmp_path / "audio.mp3"),
    )

    assert Path(result).exists()


@pytest.mark.asyncio
async def test_minimax_tts_loads_api_key_from_dotenv(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        assert headers["Authorization"] == "Bearer dotenv-key"
        return httpx.Response(
            200,
            json={
                "data": {"audio": b"ok".hex(), "status": 2},
                "trace_id": "trace-dotenv",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
            request=httpx.Request("POST", url),
        )

    env_file = tmp_path / ".env"
    env_file.write_text('MINIMAX_API_KEY="dotenv-key"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"minimax": {"api_key": "saved-config-key"}}, core=DummyCore())

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


def test_config_manager_accepts_minimax_api_key(tmp_path):
    config_path = tmp_path / "config.yaml"
    original_instance = ConfigManager._instance
    ConfigManager._instance = None
    try:
        manager = ConfigManager(str(config_path))
        manager.set_comfyui_config(minimax_api_key="minimax-key")
        assert manager.get_comfyui_config()["tts"]["minimax"]["api_key"] == "minimax-key"
    finally:
        ConfigManager._instance = original_instance
