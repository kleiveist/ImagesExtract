from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from PIL import Image

import images_extract.io_utils as io_utils
from images_extract.config import AppConfig
from images_extract.context import RunContext
from images_extract.io_utils import atomic_copy, atomic_write_json, plan_png_outputs
from images_extract.logging_utils import configure_logging
from images_extract.models import StageStatus
from images_extract.preflight import PreflightError, inspect_run
from images_extract.stages import CollateConfig, CollationInput, collate


def test_hash_strategy_distinguishes_same_stem_sources_with_identical_bytes(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    png = input_dir / "icon.png"
    disguised_jpeg = input_dir / "icon.jpg"
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(png)
    disguised_jpeg.write_bytes(png.read_bytes())

    planned = plan_png_outputs(
        [disguised_jpeg, png],
        input_root=input_dir,
        strategy="hash",
    )

    assert len(planned) == 2
    assert len(set(planned.values())) == 2
    assert all("__" in target.stem for target in planned.values())
    assert planned == plan_png_outputs(
        [png, disguised_jpeg],
        input_root=input_dir,
        strategy="hash",
    )


def test_collate_hash_strategy_keeps_identical_content_as_distinct_outputs(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    first = input_dir / "first" / "icon.png"
    second = input_dir / "second" / "icon.png"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(first)
    second.write_bytes(first.read_bytes())

    result = collate(
        [
            CollationInput(first, recipe="result", logical_name="icon.png"),
            CollationInput(second, recipe="result", logical_name="icon.png"),
        ],
        input_root=input_dir,
        output_dir=tmp_path / "collated",
        config=CollateConfig(collision_policy="hash"),
        workers=2,
    )

    assert result.status is StageStatus.SUCCESS
    assert result.processed == 2
    assert len(result.outputs) == 2
    assert len({path.name for path in result.outputs}) == 2
    assert {path.read_bytes() for path in result.outputs} == {first.read_bytes()}


@pytest.mark.parametrize(
    ("first_stem", "second_stem"),
    [
        ("Icon", "icon"),
        ("Café", "Cafe\u0301"),
    ],
    ids=["casefold", "unicode-nfc"],
)
def test_preflight_rejects_portable_name_collision_without_creating_output(
    tmp_path: Path,
    first_stem: str,
    second_stem: str,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(input_dir / f"{first_stem}.jpg")
    Image.new("RGB", (4, 4), (3, 2, 1)).save(input_dir / f"{second_stem}.webp")
    output_dir = tmp_path / "output"

    with pytest.raises(PreflightError, match="collision"):
        inspect_run(
            input_dir=input_dir,
            output_dir=output_dir,
            collision_strategy="error",
        )

    assert not output_dir.exists()


def test_atomic_no_clobber_survives_competing_target_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"stage output")
    target = tmp_path / "target.bin"
    real_link = os.link
    competitor = b"created by another writer"

    def create_competitor_then_link(
        temporary: str | os.PathLike[str],
        destination: str | os.PathLike[str],
        *args: object,
        **kwargs: object,
    ) -> None:
        Path(destination).write_bytes(competitor)
        real_link(temporary, destination, *args, **kwargs)

    monkeypatch.setattr(io_utils.os, "link", create_competitor_then_link)

    with pytest.raises(FileExistsError, match="output already exists"):
        atomic_copy(source, target, overwrite=False)

    assert target.read_bytes() == competitor
    assert not list(tmp_path.glob(".target.bin.*.tmp"))


def test_atomic_no_clobber_does_not_follow_or_replace_symlink_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"replacement")
    victim = tmp_path / "victim.bin"
    victim.write_bytes(b"keep me")
    target = tmp_path / "target.bin"
    target.symlink_to(victim)

    with pytest.raises(FileExistsError, match="output already exists"):
        atomic_copy(source, target, overwrite=False)

    assert target.is_symlink()
    assert target.resolve() == victim.resolve()
    assert victim.read_bytes() == b"keep me"
    assert not list(tmp_path.glob(".target.bin.*.tmp"))


def test_reconfiguring_logging_closes_and_detaches_old_file_handler(
    tmp_path: Path,
) -> None:
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    logger = configure_logging(
        console_enabled=False,
        file_enabled=True,
        log_directory=first_directory,
    )
    old_handler = next(
        handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)
    )
    logger.info("first destination")

    try:
        reconfigured = configure_logging(
            console_enabled=False,
            file_enabled=True,
            log_directory=second_directory,
        )
        reconfigured.info("second destination")

        assert old_handler not in reconfigured.handlers
        assert old_handler.stream is None
        assert "second destination" not in (first_directory / "images-extract.log").read_text(
            encoding="utf-8"
        )
        assert "second destination" in (second_directory / "images-extract.log").read_text(
            encoding="utf-8"
        )
    finally:
        configure_logging(console_enabled=False, file_enabled=False)


def test_context_initialization_failure_removes_partial_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    real_mkdir = Path.mkdir

    def fail_recipes_directory(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "recipes":
            raise OSError("simulated run initialization failure")
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_recipes_directory)

    with pytest.raises(OSError, match="simulated run initialization failure"):
        RunContext.create(
            input_dir=input_dir,
            output_dir=output_dir,
            config=AppConfig(),
            run_id="partial-run",
        )

    assert not (output_dir / "runs" / "partial-run").exists()
    assert not list((output_dir / "runs").iterdir())


def test_context_rejects_symlinked_runs_directory(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (output_dir / "runs").symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symbolic link"):
        RunContext.create(
            input_dir=input_dir,
            output_dir=output_dir,
            config=AppConfig(),
            run_id="symlink-run",
        )

    assert not list(external.iterdir())


def test_atomic_json_rejects_nan_and_removes_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"

    with pytest.raises(ValueError, match="Out of range float values"):
        atomic_write_json({"invalid": float("nan")}, target)

    assert not target.exists()
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))
