"""Command-line interface for the safe ImagesExtract pipeline."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from images_extract import __version__
from images_extract.config import COLLISION_STRATEGIES, AppConfig, ConfigError, load_config
from images_extract.models import PipelineResult, StageResult, StageStatus
from images_extract.stage_registry import PIPELINE_STAGES

EXIT_SUCCESS = 0
EXIT_PROCESSING_ERROR = 1
EXIT_USAGE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="images-extract",
        description="Nicht-destruktive, reproduzierbare Bildextraktions-Pipeline.",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="eine vollständige Rezept-Pipeline ausführen")
    run_parser.add_argument("input", type=Path, metavar="INPUT")
    run_parser.add_argument("--output", type=Path, required=True, metavar="OUTPUT")
    _add_config_argument(run_parser)
    run_parser.add_argument(
        "--recipe",
        action="append",
        dest="recipes",
        metavar="NAME",
        help="nur dieses Rezept ausführen; für mehrere Rezepte wiederholen",
    )
    run_parser.add_argument("--workers", type=_positive_int, default=1, metavar="N")
    run_parser.add_argument(
        "--collision",
        choices=sorted(COLLISION_STRATEGIES),
        help="Strategie für kollidierende PNG-Zielnamen",
    )
    run_parser.add_argument("--allow-empty", action="store_true")
    run_parser.add_argument("--move-sources", action="store_true")
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.add_argument("--delete-intermediates", action="store_true")
    run_parser.add_argument("--run-id", metavar="ID")
    run_parser.add_argument("--verbose", action="store_true")

    stage_parser = subparsers.add_parser("stage", help="eine einzelne Stufe ausführen")
    stage_parser.add_argument("stage", choices=PIPELINE_STAGES, metavar="STAGE")
    stage_parser.add_argument("input", type=Path, metavar="INPUT")
    stage_parser.add_argument("--output", type=Path, required=True, metavar="OUTPUT")
    _add_config_argument(stage_parser)
    stage_parser.add_argument("--workers", type=_positive_int, default=1, metavar="N")
    stage_parser.add_argument("--overwrite", action="store_true")
    stage_parser.add_argument(
        "--collision",
        choices=sorted(COLLISION_STRATEGIES),
        help="nur für convert: Strategie für gleiche Basisnamen",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Installation und Konfiguration prüfen")
    _add_config_argument(doctor_parser)

    validate_parser = subparsers.add_parser(
        "validate-config", help="TOML- oder Legacy-INI-Konfiguration prüfen"
    )
    _add_config_argument(validate_parser)
    return parser


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, metavar="FILE")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("muss eine Ganzzahl sein") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("muss mindestens 1 sein")
    return parsed


def _load_requested_config(path: Path | None) -> AppConfig:
    config = load_config(path)
    print("✔ Konfiguration gültig")
    return config


def _run_command(arguments: argparse.Namespace) -> int:
    from images_extract.pipeline import run_pipeline

    config = _load_requested_config(arguments.config)
    collision = arguments.collision or config.collision_strategy
    result = run_pipeline(
        input_dir=arguments.input,
        output_dir=arguments.output,
        config=config,
        recipe_names=arguments.recipes,
        workers=arguments.workers,
        collision_strategy=collision,
        allow_empty=arguments.allow_empty,
        move_sources=arguments.move_sources,
        overwrite=arguments.overwrite,
        delete_intermediates=arguments.delete_intermediates,
        run_id=arguments.run_id,
        verbose=arguments.verbose,
    )
    _print_pipeline_result(result)
    return result.exit_code


def _stage_command(arguments: argparse.Namespace) -> int:
    from images_extract.pipeline import run_single_stage

    config = _load_requested_config(arguments.config)
    result = run_single_stage(
        stage_name=arguments.stage,
        input_dir=arguments.input,
        output_dir=arguments.output,
        config=config,
        workers=arguments.workers,
        overwrite=arguments.overwrite,
        collision_strategy=arguments.collision or config.collision_strategy,
    )
    _print_stage_result(result)
    return EXIT_SUCCESS if result.ok else EXIT_PROCESSING_ERROR


def _doctor_command(arguments: argparse.Namespace) -> int:
    config = _load_requested_config(arguments.config)
    failures: list[str] = []
    python_version = tuple(sys.version_info[:3])
    if python_version >= (3, 11):
        print(f"✔ Python {platform.python_version()}")
    else:
        failures.append(f"Python >= 3.11 erforderlich, gefunden: {platform.python_version()}")

    for distribution, label, module in (
        ("Pillow", "Pillow", "PIL"),
        ("numpy", "NumPy", "numpy"),
        ("opencv-python-headless", "OpenCV headless", "cv2"),
    ):
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"Abhängigkeit fehlt: {distribution}")
        else:
            try:
                importlib.import_module(module)
            except Exception as exc:
                failures.append(
                    f"Abhängigkeit nicht importierbar: {distribution}: {type(exc).__name__}: {exc}"
                )
            else:
                print(f"✔ {label} {version}")

    print(f"✔ Arbeitsformat {config.working_format.upper()}/RGBA")
    print(f"✔ {len(config.enabled_recipes)} aktive(s) Rezept(e)")
    if failures:
        for failure in failures:
            print(f"✘ {failure}", file=sys.stderr)
        return EXIT_PROCESSING_ERROR
    print("✔ Installation einsatzbereit")
    return EXIT_SUCCESS


def _validate_command(arguments: argparse.Namespace) -> int:
    config = _load_requested_config(arguments.config)
    for recipe in config.enabled_recipes:
        print(f"✔ Rezept {recipe.name}: {' → '.join(recipe.steps)}")
    return EXIT_SUCCESS


def _print_pipeline_result(result: PipelineResult) -> None:
    if result.run_id is not None:
        print(f"✔ Run: {result.run_id}")
    for stage in result.stages:
        _print_stage_result(stage)
    if result.status is StageStatus.SKIPPED and result.run_id is None:
        print("✔ Keine Eingabedateien; Leer-Lauf erlaubt, kein Run erzeugt")
    if result.ok and result.run_id is not None:
        print(
            "✔ Originale unverändert"
            if not any(stage.name == "move_sources" for stage in result.stages)
            else "✔ Quellen auf ausdrücklichen Wunsch verschoben"
        )
        if result.manifest_path is not None:
            print(f"✔ Manifest: {result.manifest_path}")
    for error in result.errors:
        print(f"✘ {error}", file=sys.stderr)


def _print_stage_result(result: StageResult) -> None:
    icon = "✔" if result.ok else "✘"
    generated = (
        f", {len(result.outputs)} Ausgaben"
        if result.outputs and len(result.outputs) != result.processed
        else ""
    )
    print(
        f"{icon} {result.name}: {result.processed} verarbeitet{generated}, "
        f"{result.skipped} übersprungen, {result.failed} fehlgeschlagen"
    )
    for error in result.errors:
        print(f"  ✘ {error}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "run":
            return _run_command(arguments)
        if arguments.command == "stage":
            return _stage_command(arguments)
        if arguments.command == "doctor":
            return _doctor_command(arguments)
        if arguments.command == "validate-config":
            return _validate_command(arguments)
    except ConfigError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        print("✘ Abgebrochen", file=sys.stderr)
        return 130
    except Exception as exc:  # keep the normal CLI free of tracebacks
        print(f"✘ Unerwarteter Fehler: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_PROCESSING_ERROR
    parser.error(f"unknown command: {arguments.command}")
    return EXIT_USAGE_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
