"""Recipe orchestration for isolated, manifest-driven pipeline runs."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import shutil
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

import cv2

from images_extract.config import COLLISION_STRATEGIES, AppConfig, RecipeConfig
from images_extract.context import RunContext, validate_run_id
from images_extract.io_utils import atomic_copy, sha256_file
from images_extract.logging_utils import configure_logging
from images_extract.manifest import RunManifest
from images_extract.models import PipelineResult, StageResult, StageStatus
from images_extract.preflight import PreflightResult, inspect_run, verify_sources_unchanged
from images_extract.stage_registry import PIPELINE_STAGES
from images_extract.stages import (
    CollateConfig,
    CollationInput,
    cleanup,
    collate,
    colors,
    convert,
    enhance,
    extract,
    scale,
    transparency,
)

_SCALE_RE = re.compile(r"^x(\d+)$", re.IGNORECASE)


def run_pipeline(
    *,
    input_dir: Path,
    output_dir: Path,
    config: AppConfig,
    recipe_names: Sequence[str] | None = None,
    workers: int = 1,
    collision_strategy: str | None = None,
    allow_empty: bool = False,
    move_sources: bool = False,
    overwrite: bool = False,
    delete_intermediates: bool = False,
    run_id: str | None = None,
    verbose: bool = False,
) -> PipelineResult:
    """Execute enabled recipes without mutating sources by default."""

    effective_collision_strategy = (
        config.collision_strategy
        if isinstance(config, AppConfig) and collision_strategy is None
        else collision_strategy
    )
    validation_errors = _validate_run_options(
        config=config,
        recipe_names=recipe_names,
        workers=workers,
        collision_strategy=effective_collision_strategy,
        run_id=run_id,
        boolean_options={
            "allow_empty": allow_empty,
            "move_sources": move_sources,
            "overwrite": overwrite,
            "delete_intermediates": delete_intermediates,
            "verbose": verbose,
        },
    )
    if validation_errors:
        return PipelineResult(
            status=StageStatus.FAILED,
            exit_code=2,
            errors=validation_errors,
        )
    assert effective_collision_strategy is not None

    try:
        preflight = inspect_run(
            input_dir=input_dir,
            output_dir=output_dir,
            collision_strategy=effective_collision_strategy,
        )
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as exc:
        return PipelineResult(
            status=StageStatus.FAILED,
            exit_code=2,
            errors=[str(exc)],
        )

    if not preflight.sources:
        if allow_empty:
            return PipelineResult(status=StageStatus.SKIPPED, exit_code=0)
        return PipelineResult(
            status=StageStatus.FAILED,
            exit_code=1,
            errors=["Keine unterstützten Eingabedateien gefunden; es wurde kein Run erzeugt."],
        )

    recipes = _select_recipes(config, recipe_names)
    try:
        context = RunContext.create(
            input_dir=preflight.input_dir,
            output_dir=preflight.output_dir,
            config=config,
            workers=workers,
            collision_strategy=effective_collision_strategy,
            allow_empty=allow_empty,
            overwrite=overwrite,
            move_sources=move_sources,
            delete_intermediates=delete_intermediates,
            verbose=verbose,
            run_id=run_id,
        )
    except (FileExistsError, PermissionError, OSError, ValueError) as exc:
        return PipelineResult(
            status=StageStatus.FAILED,
            exit_code=2,
            errors=[f"Run-Verzeichnis konnte nicht angelegt werden: {exc}"],
        )

    input_records = [dict(record) for record in preflight.input_records]
    manifest = RunManifest(
        context=context,
        inputs=input_records,
        configuration={
            "app": config.to_dict(),
            "runtime": _runtime_versions(),
            "selected_recipes": [recipe.name for recipe in recipes],
        },
    )
    stages: list[StageResult] = []
    try:
        cv2.setNumThreads(1)
        logger = configure_logging(
            console_enabled=config.logging.console_enabled and verbose,
            file_enabled=config.logging.file_enabled,
            log_directory=context.run_dir / config.logging.directory,
            verbose=verbose,
        )
        manifest.write()
        logger.info("Run %s started with %d inputs", context.run_id, len(preflight.sources))

        converted_root = context.working_dir / "converted"
        converted = convert(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=converted_root,
            config=None,
            planned_outputs=preflight.planned_outputs,
            overwrite=overwrite,
            workers=workers,
        )
        _record_stage(manifest, stages, converted)
        if not converted.ok:
            return _failed_pipeline(context, manifest, stages, converted.errors)

        collation_inputs: list[CollationInput] = []
        for recipe in recipes:
            current_inputs = list(converted.outputs)
            current_root = converted_root
            for index, step in enumerate(recipe.steps, start=1):
                stage_root = context.recipes_dir / recipe.name / f"{index:02d}-{step}"
                result = _run_recipe_stage(
                    step=step,
                    inputs=current_inputs,
                    input_root=current_root,
                    output_dir=stage_root,
                    config=config,
                    workers=workers,
                    overwrite=overwrite,
                )
                result.name = f"{recipe.name}.{step}"
                _record_stage(manifest, stages, result)
                if not result.ok:
                    return _failed_pipeline(context, manifest, stages, result.errors)
                current_inputs = list(result.outputs)
                current_root = stage_root

            for image_path in current_inputs:
                collation_inputs.append(
                    CollationInput(
                        path=image_path,
                        recipe=recipe.output_name,
                        logical_name=image_path.name,
                    )
                )

            scale_root = context.scales_dir / recipe.name
            scaled = scale(
                current_inputs,
                input_root=current_root,
                output_dir=scale_root,
                config=config.scaling,
                overwrite=overwrite,
                workers=workers,
            )
            scaled.name = f"{recipe.name}.scale"
            _record_stage(manifest, stages, scaled)
            if not scaled.ok:
                return _failed_pipeline(context, manifest, stages, scaled.errors)
            for image_path in scaled.outputs:
                scale_value = _scale_from_path(image_path, scale_root)
                collation_inputs.append(
                    CollationInput(
                        path=image_path,
                        recipe=recipe.output_name,
                        scale=scale_value,
                        logical_name=image_path.name,
                    )
                )

        collated = collate(
            collation_inputs,
            input_root=context.run_dir,
            output_dir=context.collation_dir,
            config=CollateConfig(
                layout="recipe_scale",
                include_unscaled=True,
                collision_policy=effective_collision_strategy,
            ),
            overwrite=overwrite,
            workers=workers,
        )
        _record_stage(manifest, stages, collated)
        if not collated.ok:
            return _failed_pipeline(context, manifest, stages, collated.errors)

        source_errors = verify_sources_unchanged(
            preflight,
            input_records=input_records,
        )
        if source_errors:
            return _failed_pipeline(context, manifest, stages, source_errors)

        if move_sources:
            moved = _move_sources_transactionally(preflight, context)
            _record_stage(manifest, stages, moved)
            if not moved.ok:
                return _failed_pipeline(context, manifest, stages, moved.errors)
            destinations = {
                output.relative_to(context.sources_dir).as_posix(): output
                for output in moved.outputs
            }
            for record in input_records:
                relative = str(record["path"])
                if relative in destinations:
                    record["moved_to"] = (
                        destinations[relative].relative_to(context.run_dir).as_posix()
                    )

        if delete_intermediates:
            deleted = _delete_intermediates(context)
            _record_stage(manifest, stages, deleted)
            if not deleted.ok:
                return _failed_pipeline(context, manifest, stages, deleted.errors)

        final_status = StageStatus.SUCCESS if collated.outputs else StageStatus.SKIPPED
        manifest.finish(final_status.value)
        logger.info("Run %s completed with status %s", context.run_id, final_status.value)
        return PipelineResult(
            status=final_status,
            exit_code=0,
            run_id=context.run_id,
            run_dir=context.run_dir,
            manifest_path=context.manifest_path,
            stages=stages,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        with suppress(Exception):
            manifest.finish("failed", errors=[error])
        # Logging can itself be the reason execution failed. Keep error handling
        # independent from a successfully configured logger.
        with suppress(Exception):
            logger.exception("Run %s failed", context.run_id)
        return PipelineResult(
            status=StageStatus.FAILED,
            exit_code=1,
            run_id=context.run_id,
            run_dir=context.run_dir,
            manifest_path=context.manifest_path if context.manifest_path.exists() else None,
            stages=stages,
            errors=[error],
        )


def run_single_stage(
    *,
    stage_name: str,
    input_dir: Path,
    output_dir: Path,
    config: AppConfig,
    workers: int = 1,
    overwrite: bool = False,
    collision_strategy: str | None = None,
) -> StageResult:
    """Run one stage with explicit input/output paths and no hidden run lookup."""

    effective_collision_strategy = (
        config.collision_strategy
        if isinstance(config, AppConfig) and collision_strategy is None
        else collision_strategy
    )
    option_errors = _validate_run_options(
        config=config,
        recipe_names=None,
        workers=workers,
        collision_strategy=effective_collision_strategy,
        run_id=None,
        boolean_options={"overwrite": overwrite},
    )
    if option_errors:
        raise ValueError("; ".join(option_errors))
    assert effective_collision_strategy is not None
    if stage_name not in PIPELINE_STAGES:
        raise ValueError(f"Unbekannte Stufe: {stage_name}")

    preflight = inspect_run(
        input_dir=input_dir,
        output_dir=output_dir,
        collision_strategy=effective_collision_strategy,
        exclude_scale_directories=stage_name == "scale",
    )
    if not preflight.sources:
        return StageResult(
            name=stage_name,
            status=StageStatus.FAILED,
            failed=1,
            errors=["Keine unterstützten Eingabedateien gefunden."],
        )
    cv2.setNumThreads(1)
    destination = preflight.output_dir
    if stage_name == "convert":
        return convert(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=None,
            planned_outputs=preflight.planned_outputs,
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name == "enhance":
        return enhance(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=config.enhancement,
            seed=config.random_seed,
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name == "transparency":
        return transparency(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=config.transparency,
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name in {"extract", "extract_gray"}:
        return extract(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=config.extraction,
            grayscale=stage_name == "extract_gray",
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name == "cleanup":
        return cleanup(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=config.cleanup,
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name in {"colors", "invert"}:
        colors_config = config.colors
        if stage_name == "invert":
            colors_config = replace(colors_config, pairs=(), invert=True)
        return colors(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=colors_config,
            overwrite=overwrite,
            workers=workers,
        )
    if stage_name == "scale":
        return scale(
            preflight.sources,
            input_root=preflight.input_dir,
            output_dir=destination,
            config=config.scaling,
            overwrite=overwrite,
            workers=workers,
        )

    entries = [
        CollationInput(path=path, recipe="standalone", logical_name=path.name)
        for path in preflight.sources
    ]
    return collate(
        entries,
        input_root=preflight.input_dir,
        output_dir=destination,
        config=CollateConfig(collision_policy=effective_collision_strategy),
        overwrite=overwrite,
        workers=workers,
    )


def _run_recipe_stage(
    *,
    step: str,
    inputs: Sequence[Path],
    input_root: Path,
    output_dir: Path,
    config: AppConfig,
    workers: int,
    overwrite: bool,
) -> StageResult:
    common = {
        "input_root": input_root,
        "output_dir": output_dir,
        "overwrite": overwrite,
        "workers": workers,
    }
    if step == "enhance":
        return enhance(inputs, config=config.enhancement, seed=config.random_seed, **common)
    if step == "transparency":
        return transparency(inputs, config=config.transparency, **common)
    if step in {"extract", "extract_gray"}:
        return extract(
            inputs,
            config=config.extraction,
            grayscale=step == "extract_gray",
            **common,
        )
    if step == "cleanup":
        return cleanup(inputs, config=config.cleanup, **common)
    if step in {"colors", "invert"}:
        colors_config = config.colors
        if step == "invert":
            colors_config = replace(colors_config, pairs=(), invert=True)
        return colors(inputs, config=colors_config, **common)
    raise ValueError(f"unsupported recipe step: {step}")


def _select_recipes(
    config: AppConfig, recipe_names: Sequence[str] | None
) -> tuple[RecipeConfig, ...]:
    if not recipe_names:
        return config.enabled_recipes
    return tuple(config.recipes[name] for name in recipe_names)


def _validate_run_options(
    *,
    config: AppConfig,
    recipe_names: Sequence[str] | None,
    workers: int,
    collision_strategy: str | None,
    run_id: str | None,
    boolean_options: dict[str, object] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(config, AppConfig):
        return ["config muss eine AppConfig-Instanz sein"]
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        errors.append("workers muss eine positive Ganzzahl sein")
    elif workers > min(config.max_workers, 32):
        errors.append(f"workers darf höchstens {min(config.max_workers, 32)} sein")
    if collision_strategy not in COLLISION_STRATEGIES:
        errors.append("collision_strategy muss error, suffix oder hash sein")
    if recipe_names:
        if isinstance(recipe_names, (str, bytes)) or any(
            not isinstance(name, str) for name in recipe_names
        ):
            errors.append("Rezeptnamen müssen als Sequenz von Zeichenketten angegeben werden")
            return errors
        if len(set(recipe_names)) != len(recipe_names):
            errors.append("Rezeptnamen dürfen nicht doppelt angegeben werden")
        unknown = [name for name in recipe_names if name not in config.recipes]
        if unknown:
            errors.append("Unbekannte Rezepte: " + ", ".join(unknown))
    if run_id is not None:
        try:
            validate_run_id(run_id)
        except ValueError as exc:
            errors.append(str(exc))
    for name, value in (boolean_options or {}).items():
        if not isinstance(value, bool):
            errors.append(f"{name} muss ein boolescher Wert sein")
    return errors


def _record_stage(manifest: RunManifest, stages: list[StageResult], result: StageResult) -> None:
    stages.append(result)
    manifest.record_stage(result)


def _failed_pipeline(
    context: RunContext,
    manifest: RunManifest,
    stages: list[StageResult],
    errors: Sequence[str],
) -> PipelineResult:
    rendered = list(errors) or ["Eine Pipeline-Stufe ist fehlgeschlagen."]
    manifest.finish("failed", errors=rendered)
    return PipelineResult(
        status=StageStatus.FAILED,
        exit_code=1,
        run_id=context.run_id,
        run_dir=context.run_dir,
        manifest_path=context.manifest_path,
        stages=stages,
        errors=([] if stages and rendered == stages[-1].errors else rendered),
    )


def _scale_from_path(path: Path, scale_root: Path) -> int:
    relative = path.relative_to(scale_root)
    for component in relative.parts:
        match = _SCALE_RE.fullmatch(component)
        if match:
            return int(match.group(1))
    raise ValueError(f"Skalierungsordner fehlt im Ausgabepfad: {relative}")


def _move_sources_transactionally(preflight: PreflightResult, context: RunContext) -> StageResult:
    started = time.monotonic()
    destinations: list[Path] = []
    backups: dict[Path, Path] = {}
    expected = {
        preflight.input_dir / str(record["path"]): str(record["sha256_before"])
        for record in preflight.input_records
    }
    try:
        for source in preflight.sources:
            relative = source.relative_to(preflight.input_dir)
            destination = context.sources_dir / relative
            atomic_copy(source, destination, overwrite=False)
            if sha256_file(destination) != expected[source]:
                raise OSError(f"checksum mismatch after copying {relative.as_posix()}")
            destinations.append(destination)

        for source in preflight.sources:
            backup = source.with_name(f".{source.name}.images-extract-{context.run_id}.move-backup")
            if backup.exists() or backup.is_symlink():
                raise FileExistsError(f"move backup already exists: {backup}")
            os.link(source, backup, follow_symlinks=False)
            try:
                source.unlink()
            except Exception:
                backup.unlink(missing_ok=True)
                raise
            backups[source] = backup
            if sha256_file(backup) != expected[source]:
                raise OSError(
                    "checksum mismatch while staging source move: "
                    f"{source.relative_to(preflight.input_dir).as_posix()}"
                )

        for backup in backups.values():
            backup.unlink()
    except Exception as exc:
        rollback_errors = _restore_sources_after_move_failure(
            preflight=preflight,
            destinations=destinations,
            backups=backups,
            expected=expected,
        )
        error = f"{type(exc).__name__}: {exc}"
        if rollback_errors:
            error += "; rollback errors: " + "; ".join(rollback_errors)
        return StageResult(
            name="move_sources",
            status=StageStatus.FAILED,
            failed=1,
            outputs=destinations,
            errors=[error],
            duration_seconds=time.monotonic() - started,
        )
    return StageResult(
        name="move_sources",
        status=StageStatus.SUCCESS,
        processed=len(destinations),
        outputs=destinations,
        duration_seconds=time.monotonic() - started,
    )


def _restore_sources_after_move_failure(
    *,
    preflight: PreflightResult,
    destinations: list[Path],
    backups: dict[Path, Path],
    expected: dict[Path, str],
) -> list[str]:
    errors: list[str] = []
    destinations_by_source = dict(zip(preflight.sources, destinations, strict=False))
    for source in preflight.sources:
        backup = backups.get(source)
        try:
            if not source.exists() and not source.is_symlink():
                if backup is not None and backup.exists():
                    os.link(backup, source, follow_symlinks=False)
                elif source in destinations_by_source:
                    atomic_copy(destinations_by_source[source], source, overwrite=False)
                else:
                    raise FileNotFoundError("no verified recovery copy is available")
            if sha256_file(source) != expected[source]:
                raise OSError("restored source checksum mismatch")
        except Exception as exc:
            relative = source.relative_to(preflight.input_dir).as_posix()
            errors.append(f"{relative}: {type(exc).__name__}: {exc}")

    for backup in backups.values():
        try:
            backup.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{backup.name}: {type(exc).__name__}: {exc}")
    return errors


def _delete_intermediates(context: RunContext) -> StageResult:
    started = time.monotonic()
    owned_directories = (context.working_dir, context.recipes_dir, context.scales_dir)
    try:
        processed = 0
        for directory in owned_directories:
            if directory.exists():
                shutil.rmtree(directory)
                processed += 1
    except OSError as exc:
        return StageResult(
            name="delete_intermediates",
            status=StageStatus.FAILED,
            processed=processed,
            failed=1,
            errors=[f"{type(exc).__name__}: {exc}"],
            duration_seconds=time.monotonic() - started,
        )
    return StageResult(
        name="delete_intermediates",
        status=StageStatus.SUCCESS,
        processed=processed,
        details={"directories": [path.name for path in owned_directories]},
        duration_seconds=time.monotonic() - started,
    )


def _runtime_versions() -> dict[str, str]:
    versions = {"python": platform.python_version(), "opencv_threads": "1"}
    for distribution, key in (
        ("ImagesExtract", "images_extract"),
        ("Pillow", "pillow"),
        ("numpy", "numpy"),
        ("opencv-python-headless", "opencv"),
    ):
        try:
            versions[key] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[key] = "unknown"
    return versions


__all__ = ["PIPELINE_STAGES", "run_pipeline", "run_single_stage"]
