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
