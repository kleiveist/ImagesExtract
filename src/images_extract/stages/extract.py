"""Deterministically extract alpha-connected objects as independent RGBA PNGs."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from images_extract.config import ExtractionConfig
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    ensure_targets_do_not_replace_inputs,
    load_rgba_image,
    plan_png_inputs,
    preflight_failed_result,
    run_planned_items,
    save_images_transactionally,
    validate_integer,
    validate_workers,
)

STAGE_NAME = "extract"


def _validate_config(config: ExtractionConfig) -> None:
    validate_integer(config.min_width, name="min_width", minimum=1)
    validate_integer(config.min_height, name="min_height", minimum=1)
    validate_integer(config.min_area, name="min_area", minimum=1)
    validate_integer(
        config.alpha_threshold,
        name="alpha_threshold",
        minimum=0,
        maximum=255,
    )


def _extract_components(
    source: Path,
    *,
    config: ExtractionConfig,
    grayscale: bool,
) -> list[Image.Image]:
    rgba = np.asarray(load_rgba_image(source), dtype=np.uint8).copy()
    alpha = rgba[:, :, 3]
    binary = (alpha > config.alpha_threshold).astype(np.uint8)
    label_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8,
    )

    components: list[tuple[int, int, int, int, int, int]] = []
    for label in range(1, label_count):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if width >= config.min_width and height >= config.min_height and area >= config.min_area:
            components.append((top, left, height, width, area, label))

    # Spatial reading order is stable across OpenCV contour/component order changes.
    components.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4], item[5]))
    extracted: list[Image.Image] = []
    for top, left, height, width, _, label in components:
        component = labels[top : top + height, left : left + width] == label
        crop = rgba[top : top + height, left : left + width].copy()
        crop_alpha = np.where(component, crop[:, :, 3], 0).astype(np.uint8)
        if grayscale:
            luminance = cv2.cvtColor(crop[:, :, :3], cv2.COLOR_RGB2GRAY)
            crop[:, :, :3] = np.repeat(luminance[:, :, None], 3, axis=2)
        crop[:, :, 3] = crop_alpha
        crop[~component, :3] = 0
        extracted.append(Image.fromarray(crop))
    return extracted


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: ExtractionConfig,
    grayscale: bool = False,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Extract components; all outputs belonging to one input commit together."""

    started_at = time.monotonic()
    try:
        if not isinstance(grayscale, bool):
            raise TypeError("grayscale must be a boolean")
        workers = validate_workers(workers)
        _validate_config(config)
        # The base PNG target is a naming anchor only; real component targets are
        # preflighted transactionally after the component count is known.
        planned = plan_png_inputs(
            inputs,
            input_root=input_root,
            output_dir=output_dir,
            overwrite=True,
            reject_in_place_anchor=False,
        )
        protected_sources = tuple(item.source for item in planned)
    except Exception as exc:
        return preflight_failed_result(
            name=STAGE_NAME,
            error=exc,
            input_count=len(inputs),
            started_at=started_at,
        )

    def process(item: PlannedImage) -> ItemOutcome:
        images = _extract_components(
            item.source,
            config=config,
            grayscale=grayscale,
        )
        if not images:
            return ItemOutcome(skipped_reason="no component met the extraction limits")
        marker = "--gray-obj-" if grayscale else "--obj-"
        outputs = [
            item.target.with_name(f"{item.target.stem}{marker}{index:03d}.png")
            for index in range(1, len(images) + 1)
        ]
        ensure_targets_do_not_replace_inputs(
            outputs,
            inputs=protected_sources,
        )
        published = save_images_transactionally(
            list(zip(images, outputs, strict=True)),
            overwrite=overwrite,
        )
        return ItemOutcome(outputs=published)

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={
            "mode": "RGBA",
            "format": "PNG",
            "grayscale": grayscale,
            "ordering": "top-left-height-width-area",
        },
    )


def run_grayscale(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: ExtractionConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    return run(
        inputs,
        input_root=input_root,
        output_dir=output_dir,
        config=config,
        grayscale=True,
        overwrite=overwrite,
        workers=workers,
    )


extract_objects = run


__all__ = ["extract_objects", "run", "run_grayscale"]
