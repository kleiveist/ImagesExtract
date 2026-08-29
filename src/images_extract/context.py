"""Explicit filesystem context for one isolated pipeline run."""

from __future__ import annotations

import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from images_extract.config import AppConfig


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            "run_id must start with an alphanumeric character and contain only "
            "letters, digits, '.', '_' or '-' (maximum 64 characters)"
        )
    return run_id


@dataclass(frozen=True, slots=True)
class RunContext:
    """All paths and explicit runtime choices for a single run."""

    input_dir: Path
    output_dir: Path
    run_id: str
    run_dir: Path
    config: AppConfig
    workers: int = 1
    collision_strategy: str = "error"
    allow_empty: bool = False
    overwrite: bool = False
    move_sources: bool = False
    delete_intermediates: bool = False
    verbose: bool = False

    @property
    def working_dir(self) -> Path:
        return self.run_dir / "working"

    @property
    def recipes_dir(self) -> Path:
        return self.run_dir / "recipes"

    @property
    def scales_dir(self) -> Path:
        return self.run_dir / "scales"

    @property
    def collation_dir(self) -> Path:
        return self.run_dir / "collation"

    @property
    def sources_dir(self) -> Path:
        return self.run_dir / "sources"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @classmethod
    def create(
        cls,
        *,
        input_dir: Path,
        output_dir: Path,
        config: AppConfig,
        workers: int = 1,
        collision_strategy: str = "error",
        allow_empty: bool = False,
        overwrite: bool = False,
        move_sources: bool = False,
        delete_intermediates: bool = False,
        verbose: bool = False,
        run_id: str | None = None,
    ) -> RunContext:
        from images_extract.config import COLLISION_STRATEGIES, AppConfig

        if not isinstance(config, AppConfig):
            raise TypeError("config must be an AppConfig instance")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise ValueError("workers must be a positive integer")
        if workers > min(config.max_workers, 32):
            raise ValueError(f"workers must not exceed {min(config.max_workers, 32)}")
        if collision_strategy not in COLLISION_STRATEGIES:
            raise ValueError("collision_strategy must be error, suffix or hash")
        for name, value in (
            ("allow_empty", allow_empty),
            ("overwrite", overwrite),
            ("move_sources", move_sources),
            ("delete_intermediates", delete_intermediates),
            ("verbose", verbose),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a boolean")

        input_dir = input_dir.expanduser().resolve(strict=True)
        output_dir = output_dir.expanduser().resolve(strict=False)
        if not input_dir.is_dir():
            raise NotADirectoryError(f"input path is not a directory: {input_dir}")
        if output_dir.exists() and not output_dir.is_dir():
            raise NotADirectoryError(f"output path is not a directory: {output_dir}")
        if _paths_overlap(input_dir, output_dir):
            raise ValueError("input and output directories must not contain one another")

        if run_id is not None:
            validate_run_id(run_id)

        runs_dir = output_dir / "runs"
        if runs_dir.is_symlink():
            raise ValueError(f"runs directory must not be a symbolic link: {runs_dir}")
        runs_dir.mkdir(parents=True, exist_ok=True)
        if runs_dir.resolve() != runs_dir:
            raise ValueError(f"runs directory escapes the output directory: {runs_dir}")

        if run_id is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            for _ in range(100):
                candidate = f"{timestamp}-{secrets.token_hex(2)}"
                candidate_dir = runs_dir / candidate
                try:
                    candidate_dir.mkdir()
                except FileExistsError:
                    continue
                run_id = candidate
                run_dir = candidate_dir
                break
            else:
                raise RuntimeError("could not allocate a unique run directory")
        else:
            run_dir = runs_dir / run_id
            run_dir.mkdir(parents=False, exist_ok=False)

        try:
            context = cls(
                input_dir=input_dir,
                output_dir=output_dir,
                run_id=run_id,
                run_dir=run_dir,
                config=config,
                workers=workers,
                collision_strategy=collision_strategy,
                allow_empty=allow_empty,
                overwrite=overwrite,
                move_sources=move_sources,
                delete_intermediates=delete_intermediates,
                verbose=verbose,
            )
            for directory in (
                context.working_dir,
                context.recipes_dir,
                context.scales_dir,
                context.collation_dir,
            ):
                directory.mkdir()
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        return context


def _paths_overlap(first: Path, second: Path) -> bool:
    if first == second:
        return True
    for candidate, parent in ((first, second), (second, first)):
        try:
            candidate.relative_to(parent)
        except ValueError:
            continue
        return True
    return False
