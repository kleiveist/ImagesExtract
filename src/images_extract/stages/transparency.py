"""Create a transparent background from dark regions and detected edges."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from images_extract.config import TransparencyConfig
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
    validate_integer,
    validate_workers,
)

STAGE_NAME = "transparency"


def _validate_config(config: TransparencyConfig) -> None:
    validate_finite_number(
        config.min_component_area,
        name="min_component_area",
        minimum=0,
    )
    validate_integer(config.kernel_size, name="kernel_size", minimum=1, maximum=255)
    validate_integer(
        config.dilation_iterations,
        name="dilation_iterations",
        minimum=0,
        maximum=64,
    )
    validate_finite_number(config.dark_weight, name="dark_weight", minimum=0, maximum=1)
    validate_integer(
        config.dark_threshold_offset,
        name="dark_threshold_offset",
        minimum=-255,
        maximum=255,
    )
    validate_integer(config.canny_low, name="canny_low", minimum=0, maximum=255)
    validate_integer(config.canny_high, name="canny_high", minimum=0, maximum=255)
    if config.canny_low > config.canny_high:
        raise ValueError("canny_low must not exceed canny_high")


def _remove_background(
    source: Path,
    *,
    config: TransparencyConfig,
) -> Image.Image | None:
    rgba = np.asarray(load_rgba_image(source), dtype=np.uint8).copy()
    alpha = rgba[:, :, 3].copy()
    rgb_for_detection = rgba[:, :, :3].copy()
    rgb_for_detection[alpha == 0] = 255
    gray = cv2.cvtColor(rgb_for_detection, cv2.COLOR_RGB2GRAY)

    minimum = int(gray.min())
    maximum = int(gray.max())
    calculated = minimum + float(config.dark_weight) * (maximum - minimum)
    dark_threshold = int(np.clip(round(calculated + config.dark_threshold_offset), 0, 255))
    _, dark_mask = cv2.threshold(gray, dark_threshold, 255, cv2.THRESH_BINARY_INV)
    edges = cv2.Canny(gray, config.canny_low, config.canny_high)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (config.kernel_size, config.kernel_size),
    )
    dilated = cv2.dilate(
        edges,
        kernel,
        iterations=config.dilation_iterations,
    )
    combined = cv2.bitwise_and(dark_mask, dilated)
    combined[alpha == 0] = 0

    contours, _ = cv2.findContours(
        combined,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    foreground = np.zeros_like(combined)
    for contour in contours:
        if cv2.contourArea(contour) >= float(config.min_component_area):
            cv2.drawContours(foreground, [contour], -1, 255, thickness=cv2.FILLED)
    if not np.any(foreground):
        return None

    rgba[:, :, 3] = np.where(foreground > 0, alpha, 0).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: TransparencyConfig,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Apply the validated transparency mask to explicit RGBA inputs."""

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
        image = _remove_background(item.source, config=config)
        if image is None:
            return ItemOutcome(skipped_reason="no foreground component matched the mask")
        output = atomic_save_image(image, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={"mode": "RGBA", "format": "PNG"},
    )


make_transparent = run


__all__ = ["make_transparent", "run"]
