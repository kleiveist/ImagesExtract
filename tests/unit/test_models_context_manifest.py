from __future__ import annotations

import json

import pytest

from images_extract.config import AppConfig
from images_extract.context import RunContext
from images_extract.manifest import RunManifest
from images_extract.models import StageResult, StageStatus


def test_stage_result_serializes_relative_outputs(tmp_path):
    output = tmp_path / "run" / "out.png"
    result = StageResult(
        name="convert",
        status=StageStatus.SUCCESS,
        processed=1,
        outputs=[output],
    )

    payload = result.to_dict(relative_to=tmp_path / "run")

    assert payload["status"] == "success"
    assert payload["outputs"] == ["out.png"]
    assert result.ok


def test_context_creates_isolated_unique_runs(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    config = AppConfig()

    first = RunContext.create(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=config,
    )
    second = RunContext.create(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=config,
    )

    assert first.run_id != second.run_id
    assert first.run_dir.is_dir()
    assert second.run_dir.is_dir()
    assert first.working_dir.is_dir()
    assert first.manifest_path.parent == first.run_dir


def test_manifest_records_stage_and_finishes_atomically(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    context = RunContext.create(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=AppConfig(),
        run_id="test-run",
    )
    manifest = RunManifest(context=context, inputs=[], configuration={"working_format": "png"})
    manifest.write()
    manifest.record_stage(StageResult(name="convert", status=StageStatus.SKIPPED, skipped=1))
    manifest.finish("success")

    payload = json.loads(context.manifest_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "test-run"
    assert payload["status"] == "success"
    assert payload["stages"][0]["status"] == "skipped"
    assert not list(context.run_dir.glob(".manifest.json.*.tmp"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": StageStatus.SUCCESS, "failed": 1},
        {"status": StageStatus.FAILED, "failed": 0},
        {"status": StageStatus.SUCCESS, "processed": -1},
        {"status": StageStatus.SUCCESS, "details": {"invalid": float("nan")}},
    ],
)
def test_stage_result_rejects_inconsistent_or_non_json_state(kwargs):
    with pytest.raises((TypeError, ValueError)):
        StageResult(name="invalid", **kwargs)
