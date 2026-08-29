from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from images_extract.config import (
    AppConfig,
    EnhancementConfig,
    ExtractionConfig,
    ScalingConfig,
    TransparencyConfig,
)
from images_extract.io_utils import sha256_file
from images_extract.models import StageStatus
from images_extract.pipeline import run_pipeline


def _write_pipeline_source(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 51, 51), fill=(15, 30, 45, 255))
    image.save(path)
    return path


def _fast_config() -> AppConfig:
    return replace(
        AppConfig(),
        transparency=TransparencyConfig(
            min_component_area=0,
            kernel_size=3,
            dilation_iterations=2,
            dark_weight=0.45,
            dark_threshold_offset=0,
            canny_low=10,
            canny_high=100,
        ),
        extraction=ExtractionConfig(
            min_width=1,
            min_height=1,
            min_area=16,
            alpha_threshold=1,
        ),
        scaling=ScalingConfig(
            active_scales=(50,),
            scale_options={50: (50, 50)},
            min_percent=25,
            max_percent=200,
        ),
        enhancement=EnhancementConfig(
            color_levels=3,
            abstraction_passes=0,
            accuracy=1.0,
            noise_intensity=0.0,
            edge_weight=0.0,
            contrast=1.0,
            brightness=1.0,
            canny_low=25,
            canny_high=75,
        ),
    )


def _file_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _png_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*.png"))
    }


def test_empty_input_never_creates_or_changes_a_run(tmp_path: Path) -> None:
    input_dir = tmp_path / "empty"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    old_run = output_dir / "runs" / "old-run"
    old_run.mkdir(parents=True)
    sentinel = old_run / "sentinel.txt"
    sentinel.write_text("do not change\n", encoding="utf-8")
    before = _file_snapshot(output_dir)

    rejected = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=_fast_config(),
    )
    allowed = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=_fast_config(),
        allow_empty=True,
    )

    assert rejected.exit_code == 1
    assert rejected.status is StageStatus.FAILED
    assert rejected.run_id is None
    assert allowed.exit_code == 0
    assert allowed.status is StageStatus.SKIPPED
    assert allowed.run_id is None
    assert _file_snapshot(output_dir) == before
    assert sorted(path.name for path in (output_dir / "runs").iterdir()) == ["old-run"]


def test_pipeline_collision_fails_before_creating_output(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(input_dir / "same.png")
    Image.new("RGB", (16, 16), (30, 20, 10)).save(input_dir / "same.bmp")
    output_dir = tmp_path / "output"

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=_fast_config(),
        collision_strategy="error",
    )

    assert result.exit_code == 2
    assert result.status is StageStatus.FAILED
    assert result.run_id is None
    assert "collision" in result.errors[0]
    assert not output_dir.exists()


def test_corrupt_input_fails_pipeline_and_manifest_records_failure(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "broken.png"
    source.write_bytes(b"not an image")
    checksum = sha256_file(source)

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_fast_config(),
        run_id="corrupt-run",
    )

    assert result.exit_code == 1
    assert result.status is StageStatus.FAILED
    assert result.run_id == "corrupt-run"
    assert result.manifest_path is not None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["stages"][0]["name"] == "convert"
    assert manifest["stages"][0]["failed"] == 1
    assert manifest["errors"]
    assert sha256_file(source) == checksum
    assert not list(result.run_dir.rglob("*.tmp"))
    assert not list(result.run_dir.rglob("*.tmp.*"))


def test_two_runs_are_idempotent_and_keep_sources_and_old_runs_unchanged(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    source = _write_pipeline_source(input_dir / "Baum ü.png")
    source_checksum = sha256_file(source)
    output_dir = tmp_path / "output"
    legacy_run = output_dir / "runs" / "legacy-run"
    legacy_run.mkdir(parents=True)
    (legacy_run / "manifest.json").write_text(
        '{"status":"legacy"}\n',
        encoding="utf-8",
    )
    legacy_before = _file_snapshot(legacy_run)
    config = _fast_config()

    first = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        run_id="first-run",
    )
    assert first.exit_code == 0
    assert first.status is StageStatus.SUCCESS
    assert first.run_dir is not None
    assert first.manifest_path is not None
    first_pngs = _png_snapshot(first.run_dir)
    first_before_second = _file_snapshot(first.run_dir)

    second = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        run_id="second-run",
    )

    assert second.exit_code == 0
    assert second.status is StageStatus.SUCCESS
    assert second.run_dir is not None
    assert first_pngs
    assert _png_snapshot(second.run_dir) == first_pngs
    assert _file_snapshot(first.run_dir) == first_before_second
    assert _file_snapshot(legacy_run) == legacy_before
    assert sha256_file(source) == source_checksum
    assert not any("filtered_" in path.name for path in output_dir.rglob("*.png"))
    assert not list(output_dir.glob("**/x[0-9]*/x[0-9]*"))

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "first-run"
    assert manifest["status"] == "success"
    assert manifest["options"] == {
        "workers": 1,
        "collision_strategy": "error",
        "allow_empty": False,
        "overwrite": False,
        "move_sources": False,
        "delete_intermediates": False,
        "verbose": False,
    }
    assert manifest["configuration"]["selected_recipes"] == ["transback"]
    assert manifest["inputs"][0]["sha256_before"] == source_checksum
    assert manifest["inputs"][0]["sha256_after"] == source_checksum
    assert [stage["name"] for stage in manifest["stages"]] == [
        "convert",
        "transback.transparency",
        "transback.extract",
        "transback.scale",
        "collate",
    ]
    assert all(stage["status"] == "success" for stage in manifest["stages"])
    assert all(
        not Path(path).is_absolute() for stage in manifest["stages"] for path in stage["outputs"]
    )
    for path in first.run_dir.rglob("*.png"):
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            image.verify()


def test_recipe_selection_rejects_missing_and_can_select_disabled_recipe(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_pipeline_source(input_dir / "source.png")
    config = _fast_config()

    missing = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "missing-output",
        config=config,
        recipe_names=["does-not-exist"],
    )
    selected = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "selected-output",
        config=config,
        recipe_names=["enhancement"],
        run_id="selected-disabled-recipe",
    )

    assert missing.exit_code == 2
    assert missing.run_id is None
    assert "does-not-exist" in missing.errors[0]
    assert not (tmp_path / "missing-output").exists()
    assert selected.exit_code == 0
    stage_names = [stage.name for stage in selected.stages]
    assert "enhancement.enhance" in stage_names
    assert not any(name.startswith("transback.") for name in stage_names)
