import json

from pixelle_video.services.media import MediaService


def test_bizyair_modelzoo_workflow_metadata_is_parsed(tmp_path):
    workflow_path = tmp_path / "image_o2.json"
    workflow_path.write_text(
        json.dumps(
            {
                "source": "bizyair",
                "api_type": "modelzoo",
                "endpoint": "bza-image-o2-official/text-to-image",
                "display_name": "BizyAir 通用图片O.2 文生图",
                "defaults": {"quality": "medium"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = MediaService({"comfyui": {"image": {"default_workflow": "bizyair/image_o2.json"}}})

    workflow_info = service._parse_workflow_file(workflow_path, "bizyair")

    assert workflow_info["key"] == "bizyair/image_o2.json"
    assert workflow_info["source"] == "bizyair"
    assert workflow_info["api_type"] == "modelzoo"
    assert workflow_info["endpoint"] == "bza-image-o2-official/text-to-image"
    assert workflow_info["display_name"] == "BizyAir 通用图片O.2 文生图"
    assert workflow_info["defaults"] == {"quality": "medium"}
