"""Safe, deterministic filesystem helpers used by all stages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

SUPPORTED_EXTENSIONS = frozenset({".webp", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
_SCALE_DIRECTORY_RE = re.compile(r"^x\d+$", re.IGNORECASE)


class OutputCollisionError(ValueError):
    """Raised when two source images would produce the same output path."""


def normalize_output_target(path: Path) -> Path:
    """Resolve a target's parent without following the target leaf itself."""

    expanded = path.expanduser()
    return expanded.parent.resolve(strict=False) / expanded.name


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def discover_images(
    root: Path,
    *,
    excluded_roots: Iterable[Path] = (),
    exclude_scale_directories: bool = False,
) -> list[Path]:
    """Return regular, non-symlink image files in deterministic path order."""

    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"input path is not a directory: {root}")

    excluded = [path.expanduser().resolve(strict=False) for path in excluded_roots]
    discovered: list[Path] = []
    for current, directories, filenames in os.walk(
        root,
        followlinks=False,
        onerror=_raise_walk_error,
    ):
        current_path = Path(current)
        directories[:] = sorted(
            directory
            for directory in directories
            if not (current_path / directory).is_symlink()
            and not (exclude_scale_directories and _SCALE_DIRECTORY_RE.fullmatch(directory))
            and not _is_within_any((current_path / directory).resolve(), excluded)
        )
        for filename in sorted(filenames):
            candidate = current_path / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                discovered.append(candidate.resolve())
    return discovered


def _raise_walk_error(error: OSError) -> None:
    raise error


def _is_within_any(path: Path, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def plan_png_outputs(
    sources: Sequence[Path],
    *,
    input_root: Path,
    strategy: str = "error",
) -> dict[Path, Path]:
    """Map inputs to relative PNG outputs and handle same-stem collisions."""

    if strategy not in {"error", "suffix", "hash"}:
        raise ValueError(f"unsupported collision strategy: {strategy}")

    input_root = input_root.resolve()
    grouped: dict[str, list[tuple[Path, Path]]] = {}
    seen_sources: set[Path] = set()

    def source_key(item: Path) -> tuple[str, str]:
        normalized = unicodedata.normalize("NFC", item.as_posix())
        return normalized.casefold(), normalized

    for source in sorted(sources, key=source_key):
        resolved_source = source.resolve(strict=True)
        if resolved_source in seen_sources:
            raise ValueError(f"input was supplied more than once: {resolved_source}")
        seen_sources.add(resolved_source)
        relative = resolved_source.relative_to(input_root)
        target = relative.with_suffix(".png")
        key = unicodedata.normalize("NFC", target.as_posix()).casefold()
        grouped.setdefault(key, []).append((target, resolved_source))

    collisions = {key: items for key, items in grouped.items() if len(items) > 1}
    if collisions and strategy == "error":
        descriptions = [
            f"{items[0][0].as_posix()}: "
            + ", ".join(source.relative_to(input_root).as_posix() for _, source in items)
            for _, items in sorted(collisions.items())
        ]
        raise OutputCollisionError("output filename collision(s): " + "; ".join(descriptions))

    planned: dict[Path, Path] = {}
    for items in grouped.values():
        if len(items) == 1:
            target, source = items[0]
            planned[source] = target
            continue
        for index, (target, source) in enumerate(items, start=1):
            marker = _portable_source_hash(source, input_root) if strategy == "hash" else str(index)
            planned[source] = target.with_name(f"{target.stem}__{marker}.png")

    targets_by_key: dict[str, Path] = {}
    for target in planned.values():
        key = unicodedata.normalize("NFC", target.as_posix()).casefold()
        if key in targets_by_key:
            raise OutputCollisionError(
                f"collision strategy produced duplicate targets: {targets_by_key[key]} and {target}"
            )
        targets_by_key[key] = target
    return planned


def _portable_source_hash(source: Path, input_root: Path) -> str:
    """Hash content and relative path so identical files remain distinguishable."""

    relative = unicodedata.normalize(
        "NFC",
        source.relative_to(input_root).as_posix(),
    )
    digest = hashlib.sha256()
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(sha256_file(source).encode("ascii"))
    return digest.hexdigest()[:12]


def atomic_save_image(
    image: Image.Image,
    target: Path,
    *,
    overwrite: bool = False,
    optimize: bool = False,
) -> Path:
    """Write a validated PNG beside its target and atomically publish it."""

    target = normalize_output_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}.", suffix=".tmp.png", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        image.save(temporary, format="PNG", optimize=optimize)
        with Image.open(temporary) as verification:
            verification.verify()
        _publish_temporary(temporary, target, overwrite=overwrite)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def atomic_copy(source: Path, target: Path, *, overwrite: bool = False) -> Path:
    target = normalize_output_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        _publish_temporary(temporary, target, overwrite=overwrite)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def atomic_write_json(payload: dict[str, Any], target: Path) -> Path:
    target = normalize_output_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _publish_temporary(temporary: Path, target: Path, *, overwrite: bool) -> None:
    """Publish a same-directory temporary file without a no-clobber race."""

    if overwrite:
        os.replace(temporary, target)
        return
    try:
        os.link(temporary, target)
    except FileExistsError as exc:
        raise FileExistsError(f"output already exists: {target}") from exc
    try:
        temporary.unlink()
    except OSError:
        target.unlink(missing_ok=True)
        raise
