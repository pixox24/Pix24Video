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
