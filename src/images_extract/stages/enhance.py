"""Deterministic color abstraction and paper-style enhancement."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance

from images_extract.config import EnhancementConfig
from images_extract.io_utils import atomic_save_image
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    load_rgba_image,
    plan_png_inputs,
    preflight_failed_result,
    run_planned_items,
    stable_seed,
    validate_finite_number,
    validate_integer,
    validate_workers,
)

STAGE_NAME = "enhance"


def _validate_config(config: EnhancementConfig) -> None:
    validate_integer(config.color_levels, name="color_levels", minimum=1, maximum=256)
    validate_integer(
        config.abstraction_passes,
        name="abstraction_passes",
        minimum=0,
        maximum=64,
    )
    validate_finite_number(config.accuracy, name="accuracy", minimum=0.000001)
    validate_finite_number(
        config.noise_intensity,
        name="noise_intensity",
        minimum=0,
        maximum=255,
    )
    validate_finite_number(config.edge_weight, name="edge_weight", minimum=0, maximum=1)
    validate_finite_number(config.contrast, name="contrast", minimum=0, maximum=16)
    validate_finite_number(config.brightness, name="brightness", minimum=0, maximum=16)
    validate_integer(config.canny_low, name="canny_low", minimum=0, maximum=255)
    validate_integer(config.canny_high, name="canny_high", minimum=0, maximum=255)
    if config.canny_low > config.canny_high:
        raise ValueError("canny_low must not exceed canny_high")


def _deterministic_quantize(
    rgb: np.ndarray,
    visible: np.ndarray,
    color_levels: int,
) -> np.ndarray:
    """Quantize visible pixels using stable initial K-Means labels."""

    pixels = rgb[visible].reshape((-1, 3)).astype(np.float32)
    if pixels.size == 0:
        result = rgb.copy()
        result[~visible] = 0
        return result

    cluster_count = min(color_levels, len(pixels))
    order = np.lexsort((pixels[:, 2], pixels[:, 1], pixels[:, 0]))
    labels = np.empty((len(pixels), 1), dtype=np.int32)
    labels[order, 0] = (
        np.arange(len(pixels), dtype=np.int64) * cluster_count // len(pixels)
    ).astype(np.int32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, final_labels, centers = cv2.kmeans(
        pixels,
        cluster_count,
        labels,
        criteria,
        1,
        cv2.KMEANS_USE_INITIAL_LABELS,
    )
    quantized = np.zeros_like(rgb)
    quantized[visible] = np.clip(centers[final_labels.reshape(-1)], 0, 255).astype(np.uint8)
    return quantized


def _enhance_image(
    source: Path,
    *,
    config: EnhancementConfig,
    noise_seed: int,
) -> Image.Image:
    rgba_image = load_rgba_image(source)
    rgba = np.asarray(rgba_image, dtype=np.uint8).copy()
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3].copy()
    visible = alpha > 0

    if not np.any(visible):
        rgba[:, :, :3] = 0
        return Image.fromarray(rgba)

    quantized = _deterministic_quantize(rgb, visible, config.color_levels)
    for _ in range(config.abstraction_passes):
        quantized = cv2.bilateralFilter(
            quantized,
            d=9,
            sigmaColor=75,
            sigmaSpace=75,
        )

    accuracy = float(config.accuracy)
    canny_low = max(0, min(255, int(round(config.canny_low / accuracy))))
    canny_high = max(canny_low, min(255, int(round(config.canny_high / accuracy))))
    gray = cv2.cvtColor(quantized, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, threshold1=canny_low, threshold2=canny_high)
    inverted_edges = cv2.cvtColor(cv2.bitwise_not(edges), cv2.COLOR_GRAY2RGB)
    combined = cv2.addWeighted(
        quantized,
        1.0 - float(config.edge_weight),
        inverted_edges,
        float(config.edge_weight),
        0,
    )

    rng = np.random.default_rng(noise_seed)
    noise = rng.normal(
        0.0,
        float(config.noise_intensity),
        size=combined.shape,
    ).astype(np.float32)
    textured = np.clip(combined.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    adjusted = Image.fromarray(textured)
    adjusted = ImageEnhance.Contrast(adjusted).enhance(float(config.contrast))
    adjusted = ImageEnhance.Brightness(adjusted).enhance(float(config.brightness))
    output = np.empty_like(rgba)
    output[:, :, :3] = np.asarray(adjusted, dtype=np.uint8)
    output[:, :, 3] = alpha
    output[alpha == 0, :3] = 0
    return Image.fromarray(output)


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: EnhancementConfig,
    seed: int = 0,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Enhance explicit images without modifying their alpha or source files."""

    started_at = time.monotonic()
    try:
        workers = validate_workers(workers)
        validate_integer(seed, name="seed", minimum=0, maximum=2**63 - 1)
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
        image = _enhance_image(
            item.source,
            config=config,
            noise_seed=stable_seed(seed, item),
        )
        output = atomic_save_image(image, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={"seed": seed, "mode": "RGBA", "format": "PNG"},
    )


enhance_images = run


__all__ = ["enhance_images", "run"]
