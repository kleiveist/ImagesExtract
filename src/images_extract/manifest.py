"""Per-run manifest with inputs, configuration and stage outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from images_extract.context import RunContext
from images_extract.io_utils import atomic_write_json, sha256_file
from images_extract.models import StageResult


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class RunManifest:
    context: RunContext
    inputs: list[dict[str, Any]]
    configuration: dict[str, Any]
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    status: str = "running"
    stages: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record_stage(self, result: StageResult) -> None:
        payload = result.to_dict(relative_to=self.context.run_dir)
        output_records: list[dict[str, object]] = []
        for output in result.outputs:
            relative = _display_path(output, self.context.run_dir)
            output_records.append(
                {
                    "path": relative,
                    "size_bytes": output.stat().st_size,
                    "sha256": sha256_file(output),
                }
            )
        payload["output_records"] = output_records
        self.stages.append(payload)
        self.write()

    def finish(self, status: str, *, errors: list[str] | None = None) -> None:
        self.status = status
        self.finished_at = _utc_now()
        if errors:
            self.errors.extend(errors)
        self.write()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.context.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "input_dir": str(self.context.input_dir),
            "output_dir": str(self.context.output_dir),
            "options": {
                "workers": self.context.workers,
                "collision_strategy": self.context.collision_strategy,
                "allow_empty": self.context.allow_empty,
                "overwrite": self.context.overwrite,
                "move_sources": self.context.move_sources,
                "delete_intermediates": self.context.delete_intermediates,
                "verbose": self.context.verbose,
            },
            "configuration": self.configuration,
            "inputs": self.inputs,
            "stages": self.stages,
            "errors": list(self.errors),
        }

    def write(self) -> Path:
        return atomic_write_json(self.to_dict(), self.context.manifest_path)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
