"""Non-destructive CIE76 color replacement and RGB inversion."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from images_extract.config import ColorsConfig
from images_extract.io_utils import atomic_save_image
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    load_rgba_image,
    plan_png_inputs,
    preflight_failed_result,
    run_planned_items,
    validate_finite_number,
    validate_workers,
)

STAGE_NAME = "colors"
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_OVERLAP_POLICIES = frozenset({"first", "last", "error"})


def _hex_to_rgb(value: str) -> np.ndarray:
    if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
        raise ValueError(f"invalid #RRGGBB color: {value!r}")
    return np.asarray(
        [int(value[index : index + 2], 16) for index in (1, 3, 5)],
        dtype=np.uint8,
    )


def _rgb_to_cielab(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 sRGB to OpenCV's physical float CIELAB representation."""

    normalized = rgb.astype(np.float32) / 255.0
    return cv2.cvtColor(normalized, cv2.COLOR_RGB2LAB)


def _color_to_cielab(rgb: np.ndarray) -> np.ndarray:
    sample = rgb.reshape((1, 1, 3))
    return _rgb_to_cielab(sample)[0, 0]


def _validate_config(config: ColorsConfig) -> None:
    if config.metric != "cie76":
        raise ValueError("colors.metric must be 'cie76'")
    if config.overlap_policy not in _OVERLAP_POLICIES:
        raise ValueError(f"overlap_policy must be one of {sorted(_OVERLAP_POLICIES)}")
    validate_finite_number(config.max_delta_e, name="max_delta_e", minimum=0)
    if not isinstance(config.invert, bool):
        raise TypeError("invert must be a boolean")
    for index, pair in enumerate(config.pairs, start=1):
        try:
            _hex_to_rgb(pair.source)
            _hex_to_rgb(pair.target)
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"invalid color pair {index}: {exc}") from exc


def _apply_colors(source: Path, *, config: ColorsConfig) -> Image.Image:
    rgba = np.asarray(load_rgba_image(source), dtype=np.uint8).copy()
    rgb = rgba[:, :, :3].copy()
    visible = rgba[:, :, 3] > 0
    lab = _rgb_to_cielab(rgb)

    masks_and_targets: list[tuple[np.ndarray, np.ndarray]] = []
    for pair in config.pairs:
        source_lab = _color_to_cielab(_hex_to_rgb(pair.source))
        delta = lab - source_lab
        # This is CIE76: Euclidean distance in physical L*, a*, b* units.
        delta_e = np.sqrt(np.sum(delta * delta, axis=2))
        mask = (delta_e <= float(config.max_delta_e)) & visible
        masks_and_targets.append((mask, _hex_to_rgb(pair.target)))

    if config.overlap_policy == "error" and masks_and_targets:
        overlap_count = np.zeros(visible.shape, dtype=np.uint16)
        for mask, _ in masks_and_targets:
            overlap_count += mask.astype(np.uint16)
        overlapping_pixels = int(np.count_nonzero(overlap_count > 1))
        if overlapping_pixels:
            raise ValueError(f"{overlapping_pixels} pixels match more than one color pair")

    claimed = np.zeros(visible.shape, dtype=bool)
    for mask, target in masks_and_targets:
        if config.overlap_policy in {"first", "error"}:
            applied = mask & ~claimed
            claimed |= mask
        else:
            applied = mask
        rgb[applied] = target

    if config.invert:
        rgb = 255 - rgb
    rgb[~visible] = 0
    rgba[:, :, :3] = rgb
    return Image.fromarray(rgba)


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: ColorsConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Apply non-cascading CIE76 replacements, then optional inversion."""

    started_at = time.monotonic()
    try:
        workers = validate_workers(workers)
        _validate_config(config)
        planned = plan_png_inputs(
            inputs,
            input_root=input_root,
            output_dir=output_dir,
            overwrite=overwrite,
        )
    except Exception as exc:
        return preflight_failed_result(
            name=STAGE_NAME,
            error=exc,
            input_count=len(inputs),
            started_at=started_at,
        )

    def process(item: PlannedImage) -> ItemOutcome:
        image = _apply_colors(item.source, config=config)
        output = atomic_save_image(image, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={
            "mode": "RGBA",
            "format": "PNG",
            "metric": "cie76",
            "invert": config.invert,
            "overlap_policy": config.overlap_policy,
        },
    )


transform_colors = run


__all__ = ["run", "transform_colors"]
