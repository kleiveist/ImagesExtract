#!/usr/bin/env python3
"""Regenerate the small, deterministic Quick-Start input image."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    target = Path(__file__).parent / "input" / "basic-shapes.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (384, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 40, 152, 216), radius=24, fill="#143349")
    draw.ellipse((224, 48, 352, 176), fill="#143349")
    draw.polygon(((288, 178), (232, 224), (344, 224)), fill="#143349")
    image.save(target, format="PNG", optimize=True)


if __name__ == "__main__":
    main()
