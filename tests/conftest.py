from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def make_image():
    def factory(
        path: Path,
        *,
        mode: str = "RGBA",
        size: tuple[int, int] = (128, 128),
        image_format: str | None = None,
    ) -> Path:
        if mode == "L":
            image = Image.new("L", size, 255)
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 16, size[0] - 17, size[1] - 17), fill=32)
        else:
            background = (255, 255, 255, 0 if mode == "RGBA" else 255)
            image = Image.new(mode, size, background)
            draw = ImageDraw.Draw(image)
            fill = (24, 72, 120, 255) if mode == "RGBA" else (24, 72, 120)
            draw.rectangle((16, 16, size[0] - 17, size[1] - 17), fill=fill)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format=image_format)
        return path

    return factory
