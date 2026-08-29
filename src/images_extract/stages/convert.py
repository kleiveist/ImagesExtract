"""Decode supported source images into the canonical RGBA/PNG format."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from PIL import Image, ImageOps

from images_extract.io_utils import SUPPORTED_EXTENSIONS, atomic_save_image
from images_extract.models import StageResult
from images_extract.stages.common import (
    ItemOutcome,
    PlannedImage,
    plan_png_inputs,
    preflight_failed_result,
    run_planned_items,
    validate_workers,
)

STAGE_NAME = "convert"


def _decode_unambiguous_static_image(source: Path) -> Image.Image:
    with Image.open(source) as opened:
        frame_count = int(getattr(opened, "n_frames", 1))
        is_animated = bool(getattr(opened, "is_animated", False))
        if is_animated or frame_count != 1:
            raise ValueError(
                "animated or multi-page input is ambiguous and is not supported "
                f"({frame_count} frames/pages)"
            )
        opened.seek(0)
        opened.load()
        transposed = ImageOps.exif_transpose(opened)
        rgba = transposed.convert("RGBA")
        rgba.load()
        return rgba.copy()


def run(
    inputs: Sequence[Path],
    *,
    input_root: Path,
    output_dir: Path,
    config: object | None,
    planned_outputs: Mapping[Path, Path] | None = None,
    overwrite: bool = False,
    workers: int = 1,
) -> StageResult:
    """Convert explicit source paths to mirrored, non-destructive RGBA PNGs.

    ``config`` is explicit for the uniform stage interface.  Conversion policy is
    intentionally fixed for the first safe release: EXIF orientation is applied,
    and ambiguous animation/multi-page inputs are rejected.
    """

    started_at = time.monotonic()
    del config
    try:
        workers = validate_workers(workers)
        planned = plan_png_inputs(
            inputs,
            input_root=input_root,
            output_dir=output_dir,
            overwrite=overwrite,
            planned_outputs=planned_outputs,
        )
        unsupported = [
            item.relative.as_posix()
            for item in planned
            if item.source.suffix.lower() not in SUPPORTED_EXTENSIONS
        ]
        if unsupported:
            raise ValueError("unsupported input extension(s): " + ", ".join(unsupported))
    except Exception as exc:
        return preflight_failed_result(
            name=STAGE_NAME,
            error=exc,
            input_count=len(inputs),
            started_at=started_at,
        )

    def process(item: PlannedImage) -> ItemOutcome:
        rgba = _decode_unambiguous_static_image(item.source)
        output = atomic_save_image(rgba, item.target, overwrite=overwrite)
        return ItemOutcome(outputs=(output,))

    return run_planned_items(
        name=STAGE_NAME,
        planned=planned,
        workers=workers,
        processor=process,
        started_at=started_at,
        details={"format": "PNG", "mode": "RGBA", "exif_transposed": True},
    )


convert_images = run


__all__ = ["convert_images", "run"]
