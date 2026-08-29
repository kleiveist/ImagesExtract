"""Deterministic, alpha-correct Lanczos scaling for explicit RGBA inputs."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from images_extract.config import ScalingConfig
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    ensure_targets_do_not_replace_inputs,
    load_rgba_image,
    plan_png_inputs,
    preflight_failed_result,
    preflight_targets,
    run_planned_items,
    save_images_transactionally,
    validate_integer,
    validate_workers,
)

STAGE_NAME = "scale"


def _validated_specs(config: ScalingConfig) -> tuple[tuple[int, int, int], ...]:
    validate_integer(config.min_percent, name="min_percent", minimum=1)
    validate_integer(config.max_percent, name="max_percent", minimum=1)
    if config.min_percent > config.max_percent:
        raise ValueError("min_percent must not exceed max_percent")
    if len(set(config.active_scales)) != len(config.active_scales):
        raise ValueError("active_scales contains duplicates")

    specs: list[tuple[int, int, int]] = []
    for scale in sorted(config.active_scales):
        validate_integer(
            scale,
            name=f"active scale {scale!r}",
            minimum=config.min_percent,
            maximum=config.max_percent,
        )
        if scale not in config.scale_options:
            raise ValueError(f"active scale {scale} has no scale_options mapping")
        factors = config.scale_options[scale]
        if not isinstance(factors, (tuple, list)) or len(factors) != 2:
            raise ValueError(f"scale_options[{scale}] must contain two percentages")
        width_percent, height_percent = factors
        validate_integer(
            width_percent,
            name=f"scale_options[{scale}].width",
            minimum=config.min_percent,
            maximum=config.max_percent,
        )
        validate_integer(
            height_percent,
            name=f"scale_options[{scale}].height",
            minimum=config.min_percent,
            maximum=config.max_percent,
        )
        specs.append((scale, width_percent, height_percent))
    return tuple(specs)


def _round_dimension(value: int, percentage: int) -> int:
    # Explicit round-half-up avoids Python's banker's rounding and platform drift.
    result = int(math.floor(value * percentage / 100.0 + 0.5))
    if result < 1:
        raise ValueError(f"scale factor {percentage}% reduces dimension {value} below one pixel")
    return result


def _resize_premultiplied_rgba(
    source: Path,
    *,
    width_percent: int,
    height_percent: int,
) -> Image.Image:
    rgba = np.asarray(load_rgba_image(source), dtype=np.uint8)
    height, width = rgba.shape[:2]
    target_width = _round_dimension(width, width_percent)
    target_height = _round_dimension(height, height_percent)

    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    premultiplied = rgba[:, :, :3].astype(np.float32) * alpha[:, :, None]
    working = np.dstack((premultiplied, alpha)).astype(np.float32)
    resized = cv2.resize(
        working,
        (target_width, target_height),
        interpolation=cv2.INTER_LANCZOS4,
    )

    resized_alpha = np.clip(resized[:, :, 3], 0.0, 1.0)
    resized_rgb = np.zeros(resized.shape[:2] + (3,), dtype=np.float32)
    np.divide(
        resized[:, :, :3],
        resized_alpha[:, :, None],
        out=resized_rgb,
        where=resized_alpha[:, :, None] > 1e-7,
    )
    output = np.empty(resized.shape[:2] + (4,), dtype=np.uint8)
    output[:, :, :3] = np.clip(np.rint(resized_rgb), 0, 255).astype(np.uint8)
    output[:, :, 3] = np.clip(np.rint(resized_alpha * 255.0), 0, 255).astype(np.uint8)
    output[output[:, :, 3] == 0, :3] = 0
    return Image.fromarray(output)


def _target_for(item: PlannedImage, scale: int) -> Path:
    return item.target.parent / f"x{scale}" / f"{item.target.stem}_x{scale}.png"


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: ScalingConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Produce every configured scale without scanning or modifying source trees."""

    started_at = time.monotonic()
    try:
        workers = validate_workers(workers)
        specs = _validated_specs(config)
        planned = plan_png_inputs(
            inputs,
            input_root=input_root,
            output_dir=output_dir,
            overwrite=True,
            reject_in_place_anchor=False,
        )
        all_targets = [_target_for(item, scale) for item in planned for scale, _, _ in specs]
        ensure_targets_do_not_replace_inputs(
            all_targets,
            inputs=(item.source for item in planned),
        )
        preflight_targets(all_targets, overwrite=overwrite)
    except Exception as exc:
        return preflight_failed_result(
            name=STAGE_NAME,
            error=exc,
            input_count=len(inputs),
            started_at=started_at,
        )

    def process(item: PlannedImage) -> ItemOutcome:
        images_and_targets = [
            (
                _resize_premultiplied_rgba(
                    item.source,
                    width_percent=width_percent,
                    height_percent=height_percent,
                ),
                _target_for(item, scale),
            )
            for scale, width_percent, height_percent in specs
        ]
        if not images_and_targets:
            return ItemOutcome(skipped_reason="no active scales")
        published = save_images_transactionally(
            images_and_targets,
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
            "resampling": "lanczos4-premultiplied-alpha",
            "active_scales": [scale for scale, _, _ in specs],
        },
    )


scale_images = run


__all__ = ["run", "scale_images"]
