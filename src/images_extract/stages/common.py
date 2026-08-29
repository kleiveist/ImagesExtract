"""Shared, side-effect-conscious helpers for image processing stages.

Stages consume explicit file lists.  Directory discovery and recipe routing belong
to the pipeline layer; keeping them out of this module prevents accidental reuse
of output files as inputs on a later run.
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from images_extract.io_utils import atomic_copy, atomic_save_image, normalize_output_target
from images_extract.models import StageResult, StageStatus

MAX_WORKERS = 32


@dataclass(frozen=True, slots=True)
class PlannedImage:
    """One validated input and its deterministic output location."""

    source: Path
    relative: Path
    target: Path


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """Internal per-input outcome used to aggregate a :class:`StageResult`."""

    outputs: tuple[Path, ...] = ()
    skipped_reason: str | None = None


def validate_workers(workers: int) -> int:
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise TypeError("workers must be an integer")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    return workers


def normalized_path_key(path: Path) -> tuple[str, str]:
    """Return a stable and case-insensitive primary ordering key."""

    normalized = unicodedata.normalize("NFC", path.as_posix())
    return normalized.casefold(), normalized


def collision_path_key(path: Path) -> str:
    """Normalize a destination for portable collision detection."""

    return normalized_path_key(path)[0]


def plan_png_inputs(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    overwrite: bool,
    planned_outputs: Mapping[Path, Path] | None = None,
    reject_in_place_anchor: bool = True,
) -> list[PlannedImage]:
    """Validate explicit inputs and mirror their relative paths as PNG outputs.

    Case-folded and Unicode-normalized destination collisions are rejected up
    front.  This is deliberately stricter than the current Linux filesystem so a
    run remains portable to case-insensitive filesystems.
    """

    root = input_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"input_root is not a directory: {root}")
    destination_root = output_dir.expanduser().resolve(strict=False)

    normalized_mapping: dict[Path, Path] | None = None
    if planned_outputs is not None:
        normalized_mapping = {}
        for raw_source, raw_target in planned_outputs.items():
            mapping_source = Path(raw_source).expanduser()
            if not mapping_source.is_absolute():
                mapping_source = root / mapping_source
            mapping_source = mapping_source.resolve(strict=True)
            relative_target = Path(raw_target)
            if relative_target.is_absolute() or ".." in relative_target.parts:
                raise ValueError(
                    f"planned output must be relative and remain inside output_dir: {raw_target}"
                )
            if relative_target.suffix.lower() != ".png":
                raise ValueError(f"planned output must use the .png suffix: {raw_target}")
            if mapping_source in normalized_mapping:
                raise ValueError(f"duplicate planned output source: {mapping_source}")
            normalized_mapping[mapping_source] = relative_target

    resolved: list[tuple[Path, Path]] = []
    seen_sources: set[Path] = set()
    for raw_source in inputs:
        source = Path(raw_source).expanduser()
        if not source.is_absolute():
            source = root / source
        if source.is_symlink():
            raise ValueError(f"symbolic-link inputs are not accepted: {source}")
        source = source.resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"input is not a regular file: {source}")
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"input is outside input_root: {source}") from exc
        if source in seen_sources:
            raise ValueError(f"input was supplied more than once: {source}")
        seen_sources.add(source)
        resolved.append((source, relative))

    if normalized_mapping is not None and set(normalized_mapping) != seen_sources:
        missing = seen_sources - set(normalized_mapping)
        extra = set(normalized_mapping) - seen_sources
        fragments: list[str] = []
        if missing:
            fragments.append("missing: " + ", ".join(str(path) for path in sorted(missing)))
        if extra:
            fragments.append("extra: " + ", ".join(str(path) for path in sorted(extra)))
        raise ValueError("planned_outputs does not match inputs (" + "; ".join(fragments) + ")")

    resolved.sort(key=lambda item: normalized_path_key(item[1]))
    planned: list[PlannedImage] = []
    targets_by_key: dict[str, tuple[Path, Path]] = {}
    for source, relative in resolved:
        relative_target = (
            normalized_mapping[source]
            if normalized_mapping is not None
            else relative.with_suffix(".png")
        )
        target = destination_root / relative_target
        try:
            target.resolve(strict=False).relative_to(destination_root)
        except ValueError as exc:
            raise ValueError(f"planned output escapes output_dir: {relative_target}") from exc
        key = collision_path_key(relative_target)
        prior = targets_by_key.get(key)
        if prior is not None:
            raise ValueError(
                f"output filename collision: {prior[0]} and {source} both map to {prior[1]}"
            )
        targets_by_key[key] = (source, target)
        if reject_in_place_anchor and source == target.resolve(strict=False):
            raise ValueError(f"in-place processing is forbidden: {source}")
        planned.append(PlannedImage(source, relative, target))

    preflight_targets((item.target for item in planned), overwrite=overwrite)
    return planned


def preflight_targets(targets: Iterable[Path], *, overwrite: bool) -> None:
    """Reject internal and existing destination collisions before any writes."""

    seen: dict[str, Path] = {}
    existing: list[Path] = []
    for target in targets:
        target = normalize_output_target(target)
        key = collision_path_key(target)
        if key in seen:
            raise ValueError(f"output filename collision: {seen[key]} and {target}")
        seen[key] = target
        if (target.exists() or target.is_symlink()) and not overwrite:
            existing.append(target)
    if existing:
        rendered = ", ".join(str(path) for path in sorted(existing, key=normalized_path_key))
        raise FileExistsError(f"output already exists: {rendered}")


def ensure_targets_do_not_replace_inputs(
    targets: Iterable[Path],
    *,
    inputs: Iterable[Path],
) -> None:
    """Protect every explicit source even when output overwrite is enabled."""

    protected = {Path(path).resolve(strict=True) for path in inputs}
    for target in targets:
        resolved_target = Path(target).expanduser().resolve(strict=False)
        if resolved_target in protected:
            raise ValueError(f"output would replace an explicit input: {resolved_target}")


def validate_finite_number(
    value: int | float,
    *,
    name: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and numeric > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return numeric


def validate_integer(
    value: int,
    *,
    name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def stable_seed(seed: int, item: PlannedImage) -> int:
    """Derive a scheduling-independent 32-bit seed for one input."""

    digest = hashlib.sha256()
    digest.update(str(seed).encode("ascii"))
    digest.update(b"\0")
    digest.update(unicodedata.normalize("NFC", item.relative.as_posix()).encode("utf-8"))
    digest.update(b"\0")
    with item.source.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return int.from_bytes(digest.digest()[:4], byteorder="big", signed=False)


def load_rgba_image(path: Path) -> Image.Image:
    """Fully decode one unambiguous image and normalize it to RGBA."""

    with Image.open(path) as opened:
        frame_count = int(getattr(opened, "n_frames", 1))
        if bool(getattr(opened, "is_animated", False)) or frame_count != 1:
            raise ValueError(
                f"stage input must contain exactly one static frame/page ({frame_count} found)"
            )
        opened.seek(0)
        opened.load()
        converted = ImageOps.exif_transpose(opened).convert("RGBA")
        converted.load()
        return converted.copy()


def run_planned_items(
    *,
    name: str,
    planned: Sequence[PlannedImage],
    workers: int,
    processor: Callable[[PlannedImage], ItemOutcome],
    started_at: float,
    details: dict[str, object] | None = None,
) -> StageResult:
    """Run independent inputs concurrently while aggregating in input order."""

    if not planned:
        return StageResult(
            name=name,
            status=StageStatus.SKIPPED,
            details={"reason": "no_inputs", **(details or {})},
            duration_seconds=time.monotonic() - started_at,
        )

    def guarded(item: PlannedImage) -> tuple[ItemOutcome | None, str | None]:
        try:
            return processor(item), None
        except Exception as exc:  # item errors must become a failed StageResult
            return None, f"{item.relative.as_posix()}: {type(exc).__name__}: {exc}"

    if workers == 1:
        completed = [guarded(item) for item in planned]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"stage-{name}") as pool:
            completed = list(pool.map(guarded, planned))

    outputs: list[Path] = []
    errors: list[str] = []
    skipped_reasons: list[str] = []
    processed = skipped = failed = 0
    for item, (outcome, error) in zip(planned, completed, strict=True):
        if error is not None:
            failed += 1
            errors.append(error)
            continue
        assert outcome is not None
        if outcome.skipped_reason is not None:
            skipped += 1
            skipped_reasons.append(f"{item.relative.as_posix()}: {outcome.skipped_reason}")
            continue
        processed += 1
        outputs.extend(outcome.outputs)

    result_details = dict(details or {})
    if skipped_reasons:
        result_details["skipped_reasons"] = skipped_reasons
    status = (
        StageStatus.FAILED if failed else StageStatus.SUCCESS if processed else StageStatus.SKIPPED
    )
    return StageResult(
        name=name,
        status=status,
        processed=processed,
        skipped=skipped,
        failed=failed,
        outputs=outputs,
        errors=errors,
        details=result_details,
        duration_seconds=time.monotonic() - started_at,
    )


def preflight_failed_result(
    *,
    name: str,
    error: Exception,
    input_count: int,
    started_at: float,
) -> StageResult:
    return StageResult(
        name=name,
        status=StageStatus.FAILED,
        failed=max(1, input_count),
        errors=[f"preflight: {type(error).__name__}: {error}"],
        duration_seconds=time.monotonic() - started_at,
    )


def save_images_transactionally(
    images_and_targets: Sequence[tuple[Image.Image, Path]],
    *,
    overwrite: bool,
) -> tuple[Path, ...]:
    """Publish all outputs for one input, rolling back if a commit fails.

    There is no portable multi-file atomic rename.  The helper therefore stages
    and validates every PNG first, backs up explicitly overwritten targets, and
    restores/removes committed files if a later publication fails.
    """

    if not images_and_targets:
        return ()
    targets = [normalize_output_target(target) for _, target in images_and_targets]
    preflight_targets(targets, overwrite=overwrite)
    staging_parent = targets[0].parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage-transaction-", dir=staging_parent) as temporary:
        temporary_dir = Path(temporary)
        staged: list[Path] = []
        for index, (image, _) in enumerate(images_and_targets):
            staged_target = temporary_dir / f"output-{index:04d}.png"
            atomic_save_image(image, staged_target, overwrite=False)
            staged.append(staged_target)

        backups: dict[Path, Path] = {}
        for index, target in enumerate(targets):
            if target.exists():
                backup = temporary_dir / f"backup-{index:04d}.png"
                atomic_copy(target, backup, overwrite=False)
                backups[target] = backup

        committed: list[Path] = []
        try:
            for staged_source, target in zip(staged, targets, strict=True):
                atomic_copy(staged_source, target, overwrite=overwrite)
                committed.append(target)
        except Exception as publication_error:
            rollback_errors: list[str] = []
            for target in reversed(committed):
                try:
                    backup = backups.get(target)
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_copy(backup, target, overwrite=True)
                except Exception as rollback_error:  # pragma: no cover - exceptional I/O
                    rollback_errors.append(f"{target}: {rollback_error}")
            if rollback_errors:
                raise RuntimeError(
                    f"publication failed ({publication_error}); rollback failed: "
                    + "; ".join(rollback_errors)
                ) from publication_error
            raise
    return tuple(targets)
