"""Assemble explicit manifest-like artifacts into a deterministic final layout."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from images_extract.io_utils import atomic_copy, sha256_file
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    collision_path_key,
    ensure_targets_do_not_replace_inputs,
    normalized_path_key,
    preflight_failed_result,
    preflight_targets,
    run_planned_items,
    validate_integer,
    validate_workers,
)

STAGE_NAME = "collate"
_LAYOUTS = frozenset({"recipe_scale", "recipe_flat"})
_COLLISION_POLICIES = frozenset({"error", "suffix", "hash"})


@dataclass(frozen=True, slots=True)
class CollationInput:
    """The manifest fields needed to place one final PNG."""

    path: Path
    recipe: str
    scale: int | None = None
    logical_name: str | None = None


@dataclass(frozen=True, slots=True)
class CollateConfig:
    layout: str = "recipe_scale"
    include_unscaled: bool = True
    collision_policy: str = "error"


def _safe_component(value: str, *, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or value in {".", ".."}
        or "\x00" in value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{name} must be one safe path component")
    return value


def _normalize_entry(raw: CollationInput | Mapping[str, Any]) -> CollationInput:
    if isinstance(raw, CollationInput):
        return raw
    if not isinstance(raw, Mapping):
        raise TypeError("collate inputs must be CollationInput objects or mappings")
    raw_path = raw.get("path", raw.get("source"))
    if raw_path is None or "recipe" not in raw:
        raise ValueError("collate mapping input requires path/source and recipe")
    return CollationInput(
        path=Path(raw_path),
        recipe=str(raw["recipe"]),
        scale=raw.get("scale"),
        logical_name=raw.get("logical_name", raw.get("name")),
    )


def _validate_config(config: CollateConfig) -> None:
    if config.layout not in _LAYOUTS:
        raise ValueError(f"layout must be one of {sorted(_LAYOUTS)}")
    if not isinstance(config.include_unscaled, bool):
        raise TypeError("include_unscaled must be a boolean")
    if config.collision_policy not in _COLLISION_POLICIES:
        raise ValueError(f"collision_policy must be one of {sorted(_COLLISION_POLICIES)}")


def _validate_rgba_png(source: Path) -> None:
    with Image.open(source) as image:
        if image.format != "PNG":
            raise ValueError(f"collation input is not a PNG: {source}")
        if image.mode != "RGBA":
            raise ValueError(f"collation input must be RGBA, got {image.mode}: {source}")
        if int(getattr(image, "n_frames", 1)) != 1:
            raise ValueError(f"collation input must contain one frame: {source}")
        image.verify()


def _collision_marker(item: PlannedImage, *, policy: str, index: int) -> str:
    if policy == "suffix":
        return str(index)
    content = sha256_file(item.source)[:8]
    path_hash = hashlib.sha256(item.relative.as_posix().encode("utf-8")).hexdigest()[:4]
    return f"{content}-{path_hash}"


def _resolve_collisions(
    planned: Sequence[PlannedImage],
    *,
    policy: str,
) -> list[PlannedImage]:
    groups: dict[str, list[PlannedImage]] = {}
    for item in planned:
        groups.setdefault(collision_path_key(item.target), []).append(item)
    collisions = [items for items in groups.values() if len(items) > 1]
    if collisions and policy == "error":
        descriptions = []
        for items in collisions:
            target = items[0].target
            sources = ", ".join(
                item.relative.as_posix()
                for item in sorted(items, key=lambda value: normalized_path_key(value.relative))
            )
            descriptions.append(f"{target}: {sources}")
        raise ValueError("collation output collision(s): " + "; ".join(descriptions))

    resolved: list[PlannedImage] = []
    for items in groups.values():
        ordered = sorted(items, key=lambda item: normalized_path_key(item.relative))
        if len(ordered) == 1:
            resolved.append(ordered[0])
            continue
        for index, item in enumerate(ordered, start=1):
            marker = _collision_marker(item, policy=policy, index=index)
            target = item.target.with_name(f"{item.target.stem}__{marker}.png")
            resolved.append(PlannedImage(item.source, item.relative, target))
    resolved.sort(key=lambda item: normalized_path_key(item.target))
    return resolved


def run(
    inputs: Sequence[CollationInput | Mapping[str, Any]],
    *,
    input_root: Path,
    output_dir: Path,
    config: CollateConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Atomically copy only explicitly supplied final artifacts.

    No directory is searched.  All internal and existing-name collisions are
    resolved or rejected before the first copy is published.
    """

    started_at = time.monotonic()
    excluded_unscaled = 0
    try:
        workers = validate_workers(workers)
        _validate_config(config)
        root = input_root.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(f"input_root is not a directory: {root}")
        destination_root = output_dir.expanduser().resolve(strict=False)
        initial: list[PlannedImage] = []
        seen_records: set[tuple[Path, str, int | None, str]] = set()

        for raw in inputs:
            entry = _normalize_entry(raw)
            recipe = _safe_component(entry.recipe, name="recipe")
            source = entry.path.expanduser()
            if not source.is_absolute():
                source = root / source
            if source.is_symlink():
                raise ValueError(f"symbolic-link inputs are not accepted: {source}")
            source = source.resolve(strict=True)
            if not source.is_file():
                raise ValueError(f"collation input is not a regular file: {source}")
            try:
                relative = source.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"collation input is outside input_root: {source}") from exc

            if entry.scale is not None:
                validate_integer(entry.scale, name="scale", minimum=1)
            elif not config.include_unscaled:
                excluded_unscaled += 1
                continue

            logical_name = entry.logical_name or source.name
            logical_name = _safe_component(logical_name, name="logical_name")
            logical_path = Path(logical_name)
            if logical_path.suffix.lower() != ".png":
                raise ValueError(f"collation logical_name must end in .png: {logical_name}")
            record = (source, recipe, entry.scale, logical_name)
            if record in seen_records:
                raise ValueError(f"duplicate collation record: {record}")
            seen_records.add(record)

            if config.layout == "recipe_scale":
                scale_directory = "original" if entry.scale is None else f"x{entry.scale}"
                target = destination_root / recipe / scale_directory / logical_name
            else:
                target = destination_root / recipe / logical_name
            if source == target.resolve(strict=False):
                raise ValueError(f"in-place collation is forbidden: {source}")
            _validate_rgba_png(source)
            initial.append(PlannedImage(source, relative, target))

        initial.sort(key=lambda item: normalized_path_key(item.relative))
        planned = _resolve_collisions(initial, policy=config.collision_policy)
        ensure_targets_do_not_replace_inputs(
            (item.target for item in planned),
            inputs=(item.source for item in planned),
        )
        preflight_targets((item.target for item in planned), overwrite=overwrite)
    except Exception as exc:
        return preflight_failed_result(
            name=STAGE_NAME,
            error=exc,
            input_count=len(inputs),
            started_at=started_at,
        )

    def process(item: PlannedImage) -> ItemOutcome:
        output = atomic_copy(item.source, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    result = run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={
            "layout": config.layout,
            "collision_policy": config.collision_policy,
            "explicit_inputs_only": True,
        },
    )
    result.skipped += excluded_unscaled
    if excluded_unscaled:
        result.details["excluded_unscaled"] = excluded_unscaled
    return result


collate_images = run


__all__ = ["CollateConfig", "CollationInput", "collate_images", "run"]
