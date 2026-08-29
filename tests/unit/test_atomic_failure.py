from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from images_extract.io_utils import atomic_save_image, sha256_file


def test_atomic_save_failure_keeps_existing_target_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target.png"
    atomic_save_image(Image.new("RGBA", (8, 8), (10, 20, 30, 255)), target)
    checksum = sha256_file(target)

    def fail_save(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("simulated write failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)

    with pytest.raises(OSError, match="simulated write failure"):
        atomic_save_image(
            Image.new("RGBA", (8, 8), (200, 100, 50, 255)),
            target,
            overwrite=True,
        )

    assert sha256_file(target) == checksum
    assert not list(tmp_path.glob(".*.tmp.png"))
