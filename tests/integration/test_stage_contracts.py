from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from images_extract.config import (
    AppConfig,
    EnhancementConfig,
    ExtractionConfig,
    ScalingConfig,
)
from images_extract.io_utils import sha256_file
from images_extract.models import StageStatus
from images_extract.pipeline import run_single_stage


def _write_image(
    path: Path,
    *,
    mode: str = "RGBA",
    image_format: str = "PNG",
    size: tuple[int, int] = (48, 48),
    color: tuple[int, int, int] = (24, 72, 120),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "L":
        image = Image.new("L", size, 255)
        ImageDraw.Draw(image).rectangle((8, 8, size[0] - 9, size[1] - 9), fill=32)
    elif mode == "RGB":
        image = Image.new("RGB", size, (255, 255, 255))
        ImageDraw.Draw(image).rectangle(
            (8, 8, size[0] - 9, size[1] - 9),
            fill=color,
        )
    else:
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle(
            (8, 8, size[0] - 9, size[1] - 9),
            fill=(*color, 255),
        )
    image.save(path, format=image_format)
    return path


@pytest.mark.parametrize(
    ("suffix", "image_format", "mode"),
    [
        (".webp", "WEBP", "RGB"),
        (".png", "PNG", "RGBA"),
        (".jpg", "JPEG", "RGB"),
        (".jpeg", "JPEG", "RGB"),
        (".bmp", "BMP", "L"),
        (".tif", "TIFF", "L"),
        (".tiff", "TIFF", "RGB"),
    ],
)
def test_convert_normalizes_every_supported_format_to_rgba_png(
    tmp_path: Path,
    suffix: str,
    image_format: str,
    mode: str,
) -> None:
    input_dir = tmp_path / "input"
    source = _write_image(
        input_dir / f"source{suffix}",
        mode=mode,
        image_format=image_format,
    )
    checksum = sha256_file(source)

    result = run_single_stage(
        stage_name="convert",
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=AppConfig(),
    )

    assert result.status is StageStatus.SUCCESS
    assert result.processed == 1
    assert result.failed == 0
    assert len(result.outputs) == 1
    with Image.open(result.outputs[0]) as image:
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        image.verify()
    assert sha256_file(source) == checksum


def test_convert_reports_corrupt_image_and_leaves_no_partial_file(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "corrupt.png"
    source.write_bytes(b"this is not a PNG")
    checksum = sha256_file(source)
    output_dir = tmp_path / "output"

    result = run_single_stage(
        stage_name="convert",
        input_dir=input_dir,
        output_dir=output_dir,
        config=AppConfig(),
    )

    assert result.status is StageStatus.FAILED
    assert result.processed == 0
    assert result.failed == 1
    assert "corrupt.png" in result.errors[0]
    assert not list(output_dir.rglob("*"))
    assert sha256_file(source) == checksum


def test_convert_suffix_collision_strategy_is_deterministic(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_image(input_dir / "icon.jpg", mode="RGB", image_format="JPEG")
    _write_image(input_dir / "icon.webp", mode="RGB", image_format="WEBP")

    result = run_single_stage(
        stage_name="convert",
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=AppConfig(),
        collision_strategy="suffix",
    )

    assert result.status is StageStatus.SUCCESS
    assert [path.name for path in result.outputs] == ["icon__1.png", "icon__2.png"]
    assert len({path.name for path in result.outputs}) == 2


def test_stage_uses_explicit_unicode_paths_independently_of_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "Quellen mit Leerzeichen ä"
    source = _write_image(input_dir / "Bäume 🌲.png")
    unrelated = tmp_path / "anderes-arbeitsverzeichnis"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    result = run_single_stage(
        stage_name="convert",
        input_dir=input_dir.resolve(),
        output_dir=(tmp_path / "Ausgabe ü").resolve(),
        config=AppConfig(),
    )

    assert result.status is StageStatus.SUCCESS
    assert result.outputs[0].name == "Bäume 🌲.png"
    assert source.exists()


def test_extract_orders_connected_components_spatially_and_supports_gray(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "sprite.png"
    image = Image.new("RGBA", (80, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, 15, 15), fill=(0, 200, 0, 255))
    draw.rectangle((60, 5, 70, 15), fill=(220, 0, 0, 255))
    draw.rectangle((5, 40, 15, 50), fill=(0, 0, 220, 255))
    image.save(source)
    checksum = sha256_file(source)
    config = replace(
        AppConfig(),
        extraction=ExtractionConfig(
            min_width=1,
            min_height=1,
            min_area=4,
            alpha_threshold=1,
        ),
    )

    color_result = run_single_stage(
        stage_name="extract",
        input_dir=input_dir,
        output_dir=tmp_path / "color",
        config=config,
    )
    gray_result = run_single_stage(
        stage_name="extract_gray",
        input_dir=input_dir,
        output_dir=tmp_path / "gray",
        config=config,
    )

    assert color_result.status is StageStatus.SUCCESS
    assert [path.name for path in color_result.outputs] == [
        "sprite--obj-001.png",
        "sprite--obj-002.png",
        "sprite--obj-003.png",
    ]
    expected_colors = [(0, 200, 0), (220, 0, 0), (0, 0, 220)]
    for path, expected in zip(color_result.outputs, expected_colors, strict=True):
        with Image.open(path) as extracted:
            assert extracted.mode == "RGBA"
            assert extracted.getpixel((5, 5))[:3] == expected

    assert len(gray_result.outputs) == 3
    for path in gray_result.outputs:
        with Image.open(path) as extracted:
            red, green, blue, alpha = extracted.getpixel((5, 5))
            assert red == green == blue
            assert alpha == 255
    assert sha256_file(source) == checksum


@pytest.mark.parametrize(
    "stage_name",
    ["extract", "extract_gray", "cleanup", "colors", "invert"],
)
def test_image_stages_handle_true_grayscale_without_shape_errors(
    tmp_path: Path,
    stage_name: str,
) -> None:
    input_dir = tmp_path / "input"
    _write_image(input_dir / "gray.png", mode="L", image_format="PNG")

    result = run_single_stage(
        stage_name=stage_name,
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=AppConfig(),
    )

    assert result.status is not StageStatus.FAILED
    assert result.failed == 0
    for output in result.outputs:
        with Image.open(output) as image:
            assert image.mode == "RGBA"


def test_enhancement_is_identical_with_one_or_two_workers(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_image(input_dir / "b.png", color=(40, 90, 160))
    _write_image(input_dir / "a.png", color=(180, 60, 30))
    config = replace(
        AppConfig(),
        enhancement=EnhancementConfig(
            color_levels=3,
            abstraction_passes=0,
            accuracy=1.0,
            noise_intensity=3.0,
            edge_weight=0.1,
            contrast=1.0,
            brightness=1.0,
            canny_low=25,
            canny_high=75,
        ),
    )

    sequential = run_single_stage(
        stage_name="enhance",
        input_dir=input_dir,
        output_dir=tmp_path / "sequential",
        config=config,
        workers=1,
    )
    parallel = run_single_stage(
        stage_name="enhance",
        input_dir=input_dir,
        output_dir=tmp_path / "parallel",
        config=config,
        workers=2,
    )

    assert sequential.status is StageStatus.SUCCESS
    assert parallel.status is StageStatus.SUCCESS
    assert [path.name for path in sequential.outputs] == ["a.png", "b.png"]
    assert [path.name for path in parallel.outputs] == ["a.png", "b.png"]
    assert [sha256_file(path) for path in sequential.outputs] == [
        sha256_file(path) for path in parallel.outputs
    ]


def test_scale_never_recurses_into_existing_xnn_directories(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_image(input_dir / "base.png", size=(40, 40))
    _write_image(input_dir / "x25" / "legacy.png", size=(40, 40))
    scaling = ScalingConfig(
        active_scales=(50,),
        scale_options={50: (50, 50)},
        min_percent=25,
        max_percent=200,
    )

    result = run_single_stage(
        stage_name="scale",
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=replace(AppConfig(), scaling=scaling),
    )

    assert result.status is StageStatus.SUCCESS
    assert result.processed == 1
    assert [path.relative_to(tmp_path / "output").as_posix() for path in result.outputs] == [
        "x50/base_x50.png"
    ]
    assert not list((tmp_path / "output").glob("x*/x*"))
    with Image.open(result.outputs[0]) as image:
        assert image.size == (20, 20)


def test_collation_rejects_then_deterministically_suffixes_collisions(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_image(input_dir / "a" / "icon.png", color=(200, 20, 20))
    _write_image(input_dir / "b" / "icon.png", color=(20, 20, 200))

    rejected = run_single_stage(
        stage_name="collate",
        input_dir=input_dir,
        output_dir=tmp_path / "rejected",
        config=AppConfig(),
        collision_strategy="error",
    )
    suffixed = run_single_stage(
        stage_name="collate",
        input_dir=input_dir,
        output_dir=tmp_path / "suffixed",
        config=AppConfig(),
        collision_strategy="suffix",
    )

    assert rejected.status is StageStatus.FAILED
    assert "collision" in rejected.errors[0]
    assert not list((tmp_path / "rejected").rglob("*.png"))
    assert suffixed.status is StageStatus.SUCCESS
    assert [path.name for path in suffixed.outputs] == ["icon__1.png", "icon__2.png"]
