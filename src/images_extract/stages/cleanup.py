"""Keep one deterministic foreground component and make the remainder transparent."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from images_extract.config import CleanupConfig
from images_extract.io_utils import atomic_save_image
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    load_rgba_image,
    plan_png_inputs,
    preflight_failed_result,
    run_planned_items,
    validate_integer,
    validate_workers,
)

STAGE_NAME = "cleanup"
_SELECTIONS = frozenset({"center_then_largest", "largest", "center"})


def _validate_config(config: CleanupConfig) -> None:
    validate_integer(
        config.intensity_lower,
        name="intensity_lower",
        minimum=0,
        maximum=255,
    )
    validate_integer(
        config.intensity_upper,
        name="intensity_upper",
        minimum=0,
        maximum=255,
    )
    if config.intensity_lower > config.intensity_upper:
        raise ValueError("intensity_lower must not exceed intensity_upper")
    validate_integer(
        config.alpha_threshold,
        name="alpha_threshold",
        minimum=0,
        maximum=255,
    )
    validate_integer(config.min_area, name="min_area", minimum=1)
    if config.selection not in _SELECTIONS:
        raise ValueError(
            f"selection must be one of {sorted(_SELECTIONS)}, got {config.selection!r}"
        )


def _cleanup_image(source: Path, *, config: CleanupConfig) -> Image.Image | None:
    rgba = np.asarray(load_rgba_image(source), dtype=np.uint8).copy()
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
    visible = rgba[:, :, 3] > config.alpha_threshold
    in_range = (gray >= config.intensity_lower) & (gray <= config.intensity_upper)
    candidate_mask = (visible & in_range).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate_mask,
        connectivity=8,
    )

    candidates: list[tuple[int, int, int, int]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < config.min_area:
            continue
        top = int(stats[label, cv2.CC_STAT_TOP])
        left = int(stats[label, cv2.CC_STAT_LEFT])
        candidates.append((label, area, top, left))
    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[1], item[2], item[3], item[0]))
    valid_labels = {item[0] for item in candidates}
    height, width = candidate_mask.shape
    center_label = int(labels[height // 2, width // 2])

    chosen: int | None = None
    if config.selection in {"center_then_largest", "center"}:
        if center_label in valid_labels:
            chosen = center_label
        elif config.selection == "center":
            return None
    if chosen is None:
        chosen = candidates[0][0]

    selected = labels == chosen
    original_alpha = rgba[:, :, 3].copy()
    rgba[:, :, 3] = np.where(selected, original_alpha, 0).astype(np.uint8)
    rgba[~selected, :3] = 0
    return Image.fromarray(rgba)


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: CleanupConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Isolate the configured main component without touching the source image."""

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
        image = _cleanup_image(item.source, config=config)
        if image is None:
            return ItemOutcome(skipped_reason="no component matched cleanup selection")
        output = atomic_save_image(image, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={"mode": "RGBA", "format": "PNG", "selection": config.selection},
    )


cleanup_images = run


__all__ = ["cleanup_images", "run"]
