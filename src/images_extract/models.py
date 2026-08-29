"""Shared result models for the ImagesExtract pipeline."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class StageStatus(StrEnum):
    """Machine-readable outcome of a pipeline stage."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class StageResult:
    """A uniform result returned by every processing stage."""

    name: str
    status: StageStatus
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    outputs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("stage name must be a non-empty string")
        if not isinstance(self.status, StageStatus):
            raise TypeError("status must be a StageStatus")
        for field_name in ("processed", "skipped", "failed"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.failed and self.status is not StageStatus.FAILED:
            raise ValueError("a stage with failed items must have failed status")
        if self.status is StageStatus.FAILED and self.failed == 0:
            raise ValueError("a failed stage must count at least one failed item")
        if self.status is StageStatus.SKIPPED and self.processed:
            raise ValueError("a skipped stage cannot count processed items")
        if any(not isinstance(path, Path) for path in self.outputs):
            raise TypeError("outputs must contain Path objects")
        if any(not isinstance(error, str) for error in self.errors):
            raise TypeError("errors must contain strings")
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, (int, float))
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds < 0
        ):
            raise ValueError("duration_seconds must be a finite non-negative number")
        try:
            json.dumps(self.details, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("details must be valid JSON data") from exc

    @property
    def ok(self) -> bool:
        return self.status is not StageStatus.FAILED and self.failed == 0

    def to_dict(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        def display_path(path: Path) -> str:
            if relative_to is not None:
                try:
                    return path.resolve().relative_to(relative_to.resolve()).as_posix()
                except ValueError:
                    pass
            return str(path)

        return {
            "name": self.name,
            "status": self.status.value,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "outputs": [display_path(path) for path in self.outputs],
            "errors": list(self.errors),
            "details": dict(self.details),
            "duration_seconds": round(self.duration_seconds, 6),
        }


@dataclass(slots=True)
class PipelineResult:
    """Top-level pipeline outcome used by the CLI."""

    status: StageStatus
    exit_code: int
    run_id: str | None = None
    run_dir: Path | None = None
    manifest_path: Path | None = None
    stages: list[StageResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.status is not StageStatus.FAILED
