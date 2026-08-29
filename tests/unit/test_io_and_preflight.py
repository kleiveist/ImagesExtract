from __future__ import annotations

import pytest
from PIL import Image

from images_extract.io_utils import (
    OutputCollisionError,
    atomic_save_image,
    discover_images,
    plan_png_outputs,
    sha256_file,
)
from images_extract.preflight import PreflightError, inspect_run, verify_sources_unchanged


def test_discover_images_is_sorted_and_excludes_scale_directories(tmp_path, make_image):
    make_image(tmp_path / "z.png")
    make_image(tmp_path / "ä" / "a.jpg", mode="RGB", image_format="JPEG")
    make_image(tmp_path / "x25" / "ignored.png")

    found = discover_images(tmp_path, exclude_scale_directories=True)

    assert [path.relative_to(tmp_path).as_posix() for path in found] == ["z.png", "ä/a.jpg"]


def test_plan_png_outputs_rejects_same_stem_collision(tmp_path, make_image):
    jpg = make_image(tmp_path / "icon.jpg", mode="RGB", image_format="JPEG")
    webp = make_image(tmp_path / "icon.webp", mode="RGB", image_format="WEBP")

    with pytest.raises(OutputCollisionError, match="icon.png"):
        plan_png_outputs([jpg, webp], input_root=tmp_path)


def test_hash_collision_strategy_is_deterministic(tmp_path, make_image):
    jpg = make_image(tmp_path / "icon.jpg", mode="RGB", image_format="JPEG")
    webp = make_image(tmp_path / "icon.webp", mode="RGB", image_format="WEBP")

    first = plan_png_outputs([webp, jpg], input_root=tmp_path, strategy="hash")
    second = plan_png_outputs([jpg, webp], input_root=tmp_path, strategy="hash")

    assert first == second
    assert len(set(first.values())) == 2
    assert all("__" in path.stem for path in first.values())


def test_atomic_save_does_not_overwrite_by_default(tmp_path):
    target = tmp_path / "image.png"
    original = Image.new("RGBA", (4, 4), (10, 20, 30, 255))
    replacement = Image.new("RGBA", (4, 4), (200, 100, 50, 255))
    atomic_save_image(original, target)
    checksum = sha256_file(target)

    with pytest.raises(FileExistsError):
        atomic_save_image(replacement, target)

    assert sha256_file(target) == checksum
    assert list(tmp_path.glob("*.tmp.png")) == []


def test_preflight_is_read_only_and_detects_source_changes(tmp_path, make_image):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source = make_image(input_dir / "Bild ü.png")

    result = inspect_run(
        input_dir=input_dir,
        output_dir=output_dir,
        collision_strategy="error",
    )

    assert not output_dir.exists()
    assert len(result.sources) == 1
    assert verify_sources_unchanged(result) == []
    source.write_bytes(source.read_bytes() + b"changed")
    assert verify_sources_unchanged(result) == [
        "source checksum changed during processing: Bild ü.png"
    ]


def test_preflight_rejects_overlapping_paths(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(PreflightError, match="must not contain"):
        inspect_run(
            input_dir=input_dir,
            output_dir=input_dir / "output",
            collision_strategy="error",
        )
