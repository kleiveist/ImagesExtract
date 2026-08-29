"""Read-only validation performed before a run directory is created."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from images_extract.io_utils import (
    OutputCollisionError,
    discover_images,
    plan_png_outputs,
)


class PreflightError(ValueError):
    """A user-correctable input or output problem."""


@dataclass(frozen=True, slots=True)
class PreflightResult:
    input_dir: Path
    output_dir: Path
    sources: tuple[Path, ...]
    planned_outputs: dict[Path, Path]
    input_records: tuple[dict[str, object], ...]


def inspect_run(
    *,
    input_dir: Path,
    output_dir: Path,
    collision_strategy: str,
    exclude_scale_directories: bool = False,
) -> PreflightResult:
    """Validate paths, enumerate inputs and hash sources without changing disk."""

    try:
        resolved_input = input_dir.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise PreflightError(f"input directory does not exist: {input_dir}") from exc
    if not resolved_input.is_dir():
        raise PreflightError(f"input path is not a directory: {resolved_input}")

    resolved_output = output_dir.expanduser().resolve(strict=False)
    if resolved_output.exists() and not resolved_output.is_dir():
        raise PreflightError(f"output path is not a directory: {resolved_output}")
    if _paths_overlap(resolved_input, resolved_output):
        raise PreflightError(
            "input and output directories must not contain one another; use sibling paths"
        )

    sources = tuple(
        discover_images(
            resolved_input,
            exclude_scale_directories=exclude_scale_directories,
        )
    )
    try:
        planned_outputs = plan_png_outputs(
            sources,
            input_root=resolved_input,
            strategy=collision_strategy,
        )
    except OutputCollisionError as exc:
        raise PreflightError(str(exc)) from exc

    records: list[dict[str, object]] = []
    for source in sources:
        relative = source.relative_to(resolved_input)
        try:
            snapshot = _snapshot_source(source)
        except OSError as exc:
            raise PreflightError(
                f"input could not be read consistently: {relative.as_posix()}: {exc}"
            ) from exc
        records.append(
            {
                "path": relative.as_posix(),
                "size_bytes": snapshot["size_bytes"],
                "sha256_before": snapshot["sha256"],
                "mtime_ns_before": snapshot["mtime_ns"],
                "device_before": snapshot["device"],
                "inode_before": snapshot["inode"],
                "planned_png": planned_outputs[source].as_posix(),
            }
        )

    return PreflightResult(
        input_dir=resolved_input,
        output_dir=resolved_output,
        sources=sources,
        planned_outputs=planned_outputs,
        input_records=tuple(records),
    )


def verify_sources_unchanged(
    preflight: PreflightResult,
    *,
    input_records: list[dict[str, object]] | None = None,
) -> list[str]:
    """Hash every source once after processing, record it and compare snapshots."""

    errors: list[str] = []
    expected = {str(record["path"]): record for record in preflight.input_records}
    mutable = (
        {str(record["path"]): record for record in input_records}
        if input_records is not None
        else {}
    )
    for source in preflight.sources:
        relative = source.relative_to(preflight.input_dir).as_posix()
        try:
            snapshot = _snapshot_source(source)
        except FileNotFoundError:
            errors.append(f"source disappeared during processing: {relative}")
            continue
        except OSError as exc:
            errors.append(f"source could not be verified after processing: {relative}: {exc}")
            continue

        if relative in mutable:
            mutable[relative].update(
                {
                    "sha256_after": snapshot["sha256"],
                    "size_bytes_after": snapshot["size_bytes"],
                    "mtime_ns_after": snapshot["mtime_ns"],
                    "device_after": snapshot["device"],
                    "inode_after": snapshot["inode"],
                }
            )

        before = expected[relative]
        if snapshot["sha256"] != before["sha256_before"]:
            errors.append(f"source checksum changed during processing: {relative}")
        elif any(
            snapshot[current] != before[previous]
            for current, previous in (
                ("size_bytes", "size_bytes"),
                ("mtime_ns", "mtime_ns_before"),
                ("device", "device_before"),
                ("inode", "inode_before"),
            )
        ):
            errors.append(f"source metadata changed during processing: {relative}")
    return errors


def _snapshot_source(source: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        while block := handle.read(1024 * 1024):
            digest.update(block)
        after = os.fstat(handle.fileno())

    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise OSError("file changed while it was being hashed")
    path_state = source.lstat()
    if stat.S_ISLNK(path_state.st_mode):
        raise OSError("symbolic links are not accepted")
    if (path_state.st_dev, path_state.st_ino) != (after.st_dev, after.st_ino):
        raise OSError("file was replaced while it was being hashed")
    return {
        "sha256": digest.hexdigest(),
        "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "device": after.st_dev,
        "inode": after.st_ino,
    }


def _paths_overlap(first: Path, second: Path) -> bool:
    if first == second:
        return True
    for candidate, parent in ((first, second), (second, first)):
        try:
            candidate.relative_to(parent)
        except ValueError:
            continue
        return True
    return False
