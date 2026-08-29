from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

import images_extract.pipeline as pipeline_module
from images_extract.config import AppConfig, RecipeConfig, ScalingConfig
from images_extract.io_utils import sha256_file
from images_extract.models import StageStatus
from images_extract.pipeline import run_pipeline


def _safety_config(*, max_workers: int = 32) -> AppConfig:
    return replace(
        AppConfig(),
        recipes={
            "safety": RecipeConfig(
                name="safety",
                steps=("colors",),
                enabled=True,
                output_name="Safety",
            )
        },
        scaling=ScalingConfig(
            active_scales=(50,),
            scale_options={50: (50, 50)},
            min_percent=25,
            max_percent=200,
        ),
        max_workers=max_workers,
    )


def _write_source(path: Path, *, color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16), (*color, 255)).save(path)
    return path


def _read_manifest(path: Path | None) -> dict[str, object]:
    assert path is not None
    return json.loads(path.read_text(encoding="utf-8"))


def test_logging_setup_failure_is_returned_and_written_to_failed_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    _write_source(input_dir / "source.png")

    def fail_logging_setup(**_kwargs: object) -> None:
        raise OSError("simulated logging setup failure")

    monkeypatch.setattr(pipeline_module, "configure_logging", fail_logging_setup)

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_safety_config(),
        run_id="logging-failure",
    )

    assert result.status is StageStatus.FAILED
    assert result.exit_code == 1
    assert result.run_id == "logging-failure"
    assert result.errors == ["OSError: simulated logging setup failure"]
    manifest = _read_manifest(result.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["errors"] == result.errors
    assert manifest["stages"] == []


def test_source_verification_failure_is_visible_in_result_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    _write_source(input_dir / "source.png")
    error = "source checksum changed during processing: source.png"

    def reject_source_verification(*_args: object, **_kwargs: object) -> list[str]:
        return [error]

    monkeypatch.setattr(
        pipeline_module,
        "verify_sources_unchanged",
        reject_source_verification,
    )

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_safety_config(),
        run_id="source-verification-failure",
    )

    assert result.status is StageStatus.FAILED
    assert result.exit_code == 1
    assert result.errors == [error]
    manifest = _read_manifest(result.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["errors"] == [error]


def test_effective_hash_collision_strategy_is_recorded_in_manifest(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    first = _write_source(input_dir / "icon.png")
    second = input_dir / "icon.jpg"
    second.write_bytes(first.read_bytes())

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=replace(_safety_config(), collision_strategy="hash"),
        run_id="effective-hash-strategy",
    )

    assert result.status is StageStatus.SUCCESS
    assert result.exit_code == 0
    manifest = _read_manifest(result.manifest_path)
    assert manifest["options"]["collision_strategy"] == "hash"
    planned = [record["planned_png"] for record in manifest["inputs"]]
    assert len(planned) == 2
    assert len(set(planned)) == 2
    assert all("__" in Path(path).stem for path in planned)


def test_existing_run_id_is_rejected_without_modifying_existing_run(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    _write_source(input_dir / "source.png")
    output_dir = tmp_path / "output"
    existing_run = output_dir / "runs" / "already-there"
    existing_run.mkdir(parents=True)
    sentinel = existing_run / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=_safety_config(),
        run_id="already-there",
    )

    assert result.status is StageStatus.FAILED
    assert result.exit_code == 2
    assert result.run_id is None
    assert "Run-Verzeichnis konnte nicht angelegt werden" in result.errors[0]
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert sorted(existing_run.iterdir()) == [sentinel]


def test_worker_limit_is_rejected_before_output_is_created(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_source(input_dir / "source.png")
    output_dir = tmp_path / "output"

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        config=_safety_config(max_workers=2),
        workers=3,
    )

    assert result.status is StageStatus.FAILED
    assert result.exit_code == 2
    assert result.run_id is None
    assert result.errors == ["workers darf höchstens 2 sein"]
    assert not output_dir.exists()


def test_move_sources_success_preserves_verified_copy_and_updates_manifest(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    source = _write_source(input_dir / "nested" / "source.png")
    checksum = sha256_file(source)

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_safety_config(),
        move_sources=True,
        run_id="move-success",
    )

    assert result.status is StageStatus.SUCCESS
    assert result.exit_code == 0
    assert result.run_dir is not None
    moved = result.run_dir / "sources" / "nested" / "source.png"
    assert not source.exists()
    assert moved.is_file()
    assert sha256_file(moved) == checksum
    move_stage = next(stage for stage in result.stages if stage.name == "move_sources")
    assert move_stage.status is StageStatus.SUCCESS
    assert move_stage.outputs == [moved]
    manifest = _read_manifest(result.manifest_path)
    assert manifest["options"]["move_sources"] is True
    assert manifest["inputs"][0]["moved_to"] == "sources/nested/source.png"


def test_move_sources_failure_rolls_back_already_removed_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    first = _write_source(input_dir / "a.png", color=(10, 20, 30))
    second = _write_source(input_dir / "b.png", color=(30, 20, 10))
    checksums = {first: sha256_file(first), second: sha256_file(second)}
    blocked = second.resolve()
    real_unlink = Path.unlink
    injected = False

    def fail_second_source_once(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal injected
        if not injected and path.resolve(strict=False) == blocked:
            injected = True
            raise OSError("simulated source unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_second_source_once)

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_safety_config(),
        move_sources=True,
        run_id="move-rollback",
    )

    assert injected is True
    assert result.status is StageStatus.FAILED
    assert result.exit_code == 1
    move_stage = next(stage for stage in result.stages if stage.name == "move_sources")
    assert move_stage.status is StageStatus.FAILED
    assert "simulated source unlink failure" in move_stage.errors[0]
    for source, checksum in checksums.items():
        assert source.is_file()
        assert sha256_file(source) == checksum
    assert not list(input_dir.glob(".*.move-backup"))


def test_delete_intermediates_preserves_final_outputs_and_manifest(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_source(input_dir / "source.png")

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=_safety_config(),
        delete_intermediates=True,
        run_id="delete-intermediates",
    )

    assert result.status is StageStatus.SUCCESS
    assert result.exit_code == 0
    assert result.run_dir is not None
    assert not (result.run_dir / "working").exists()
    assert not (result.run_dir / "recipes").exists()
    assert not (result.run_dir / "scales").exists()
    assert list((result.run_dir / "collation").rglob("*.png"))
    assert result.manifest_path is not None and result.manifest_path.is_file()
    delete_stage = next(stage for stage in result.stages if stage.name == "delete_intermediates")
    assert delete_stage.status is StageStatus.SUCCESS
    assert delete_stage.processed == 3
    manifest = _read_manifest(result.manifest_path)
    assert manifest["status"] == "success"
    assert manifest["options"]["delete_intermediates"] is True
