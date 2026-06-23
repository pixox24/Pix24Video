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


def test_motion_output_uses_supersampled_zoompan_canvas(monkeypatch, tmp_path):
    captured = {}
    image_path = tmp_path / "image.png"
    audio_path = tmp_path / "audio.wav"
    output_path = tmp_path / "segment.mp4"

    Image.new("RGB", (640, 960), color=(80, 120, 160)).save(image_path)
    audio_path.write_bytes(b"placeholder")

    service = VideoService()
    monkeypatch.setattr(service, "_ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(service, "_get_audio_duration", lambda _audio: 1.0)

    def fake_run(self, *args, **kwargs):
        compiled = " ".join(str(arg) for arg in self.get_args())
        captured["command"] = compiled
        output_path.write_bytes(b"video")
        return b"", b""

    monkeypatch.setattr("ffmpeg.nodes.OutputStream.run", fake_run)

    service.create_video_from_image_with_motion(
        image=str(image_path),
        audio=str(audio_path),
        output=str(output_path),
        fps=24,
        width=360,
        height=640,
        subtitle_enabled=False,
        motion_enabled=True,
        frame_index=2,
    )

    assert "s=720x1280" in captured["command"]
    assert "scale=360:640:flags=lanczos" in captured["command"]


def test_create_video_from_image_with_motion_validates_mode(tmp_path):
    service = VideoService()

    with pytest.raises(ValueError, match="Unsupported image fit mode"):
        service.create_video_from_image_with_motion(
            image=str(tmp_path / "missing.png"),
            audio=str(tmp_path / "missing.wav"),
            output=str(tmp_path / "out.mp4"),
            image_fit_mode="contain",
        )
