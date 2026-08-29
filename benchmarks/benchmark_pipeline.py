#!/usr/bin/env python3
"""Run reproducible, informational ImagesExtract pipeline benchmarks.

The program intentionally has no performance pass/fail threshold. A non-zero
pipeline exit status still makes the benchmark invalid and is propagated after
the JSON report has been written.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from PIL import Image

SUPPORTED_EXTENSIONS = {
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
}
PACKAGE_NAMES = (
    "ImagesExtract",
    "Pillow",
    "numpy",
    "opencv-python",
    "opencv-python-headless",
)
TAIL_LIMIT = 4_000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the complete ImagesExtract CLI with several worker counts. "
            "Results are informational and written as JSON."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="input image directory")
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        default=Path("benchmark-results.json"),
        help="result JSON path",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="keep benchmark runs below this directory instead of using temp space",
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[1, 2, 4],
        help="worker counts to measure",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="recorded runs per worker count",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=1,
        help="unrecorded warm-up runs per worker count",
    )
    parser.add_argument("--config", type=Path, help="optional TOML or legacy INI")
    parser.add_argument(
        "--recipe",
        action="append",
        default=[],
        help="recipe to pass to the CLI; repeat for several recipes",
    )
    parser.add_argument(
        "--executable",
        default="images-extract",
        help="ImagesExtract console-script path",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3_600.0,
        help="maximum seconds for one pipeline run",
    )
    args = parser.parse_args(argv)

    args.input = args.input.expanduser().resolve(strict=False)
    args.json_path = args.json_path.expanduser().resolve(strict=False)
    if args.output_root is not None:
        args.output_root = args.output_root.expanduser().resolve(strict=False)
    if args.config is not None:
        args.config = args.config.expanduser().resolve(strict=False)

    if not args.input.is_dir():
        parser.error(f"input is not a directory: {args.input}")
    if args.config is not None and not args.config.is_file():
        parser.error(f"config is not a file: {args.config}")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.warmups < 0:
        parser.error("--warmups must not be negative")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not args.workers or any(count < 1 for count in args.workers):
        parser.error("--workers values must be positive integers")
    if len(set(args.workers)) != len(args.workers):
        parser.error("--workers values must be unique")
    return args


def input_inventory(root: Path) -> dict[str, Any]:
    candidates = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.casefold() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )
    total_bytes = 0
    total_pixels = 0
    invalid: list[str] = []
    readable = 0
    for path in candidates:
        total_bytes += path.stat().st_size
        try:
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
            total_pixels += width * height
            readable += 1
        except (OSError, ValueError) as exc:
            invalid.append(f"{path.relative_to(root).as_posix()}: {exc}")
    return {
        "candidate_files": len(candidates),
        "readable_files": readable,
        "total_bytes": total_bytes,
        "total_megapixels": round(total_pixels / 1_000_000, 6),
        "invalid_files": invalid,
    }


def package_versions() -> dict[str, str | None]:
    discovered: dict[str, str | None] = {}
    for package in PACKAGE_NAMES:
        try:
            discovered[package] = version(package)
        except PackageNotFoundError:
            discovered[package] = None
    return discovered


def git_commit() -> str | None:
    repository = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def output_inventory(root: Path) -> dict[str, Any]:
    files = [path for path in root.rglob("*.png") if path.is_file() and not path.is_symlink()]
    manifests = sorted(path for path in root.rglob("manifest.json") if path.is_file())
    stage_durations: dict[str, float] = {}
    manifest_statuses: list[str] = []
    manifest_errors: list[str] = []
    for manifest_path in manifests:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            manifest_errors.append(f"{manifest_path}: {exc}")
            continue
        manifest_statuses.append(str(payload.get("status", "unknown")))
        for stage in payload.get("stages", []):
            if not isinstance(stage, dict):
                continue
            name = stage.get("name")
            duration = stage.get("duration_seconds")
            if isinstance(name, str) and isinstance(duration, (int, float)):
                stage_durations[name] = stage_durations.get(name, 0.0) + float(duration)
    return {
        "png_files": len(files),
        "png_bytes": sum(path.stat().st_size for path in files),
        "manifests": len(manifests),
        "manifest_statuses": manifest_statuses,
        "manifest_errors": manifest_errors,
        "stage_durations_seconds": {
            name: round(duration, 6) for name, duration in sorted(stage_durations.items())
        },
    }


def tail(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-TAIL_LIMIT:]


def command_for(
    args: argparse.Namespace,
    *,
    workers: int,
    output: Path,
) -> list[str]:
    command = [
        args.executable,
        "run",
        str(args.input),
        "--output",
        str(output),
        "--workers",
        str(workers),
        "--run-id",
        "benchmark",
    ]
    if args.config is not None:
        command.extend(("--config", str(args.config)))
    for recipe in args.recipe:
        command.extend(("--recipe", recipe))
    return command


def run_once(
    args: argparse.Namespace,
    *,
    workers: int,
    output: Path,
    repetition: int,
    warmup: bool,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    command = command_for(args, workers=workers, output=output)
    started = time.perf_counter()
    stdout = ""
    stderr = ""
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        return_code = 127
        stderr = str(exc)
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout = tail(exc.stdout)
        stderr = tail(exc.stderr)
        timed_out = True
    duration = time.perf_counter() - started
    return {
        "workers": workers,
        "repetition": repetition,
        "warmup": warmup,
        "duration_seconds": round(duration, 6),
        "return_code": return_code,
        "timed_out": timed_out,
        "output": output_inventory(output),
        "stdout_tail": tail(stdout) if return_code else "",
        "stderr_tail": tail(stderr) if return_code else "",
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(
    measurements: list[dict[str, Any]],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    successful = [item for item in measurements if item["return_code"] == 0]
    durations = [float(item["duration_seconds"]) for item in successful]
    if not durations:
        return {
            "successful_runs": 0,
            "failed_runs": len(measurements),
            "median_seconds": None,
            "p95_seconds": None,
            "images_per_second": None,
            "megapixels_per_second": None,
            "stages": {},
        }
    median = statistics.median(durations)
    readable = int(inventory["readable_files"])
    megapixels = float(inventory["total_megapixels"])
    stage_names = sorted(
        {name for item in successful for name in item["output"]["stage_durations_seconds"]}
    )
    stage_summary: dict[str, dict[str, float | int]] = {}
    for name in stage_names:
        values = [
            float(item["output"]["stage_durations_seconds"][name])
            for item in successful
            if name in item["output"]["stage_durations_seconds"]
        ]
        stage_summary[name] = {
            "samples": len(values),
            "median_seconds": round(statistics.median(values), 6),
            "p95_seconds": round(percentile(values, 0.95), 6),
        }
    return {
        "successful_runs": len(successful),
        "failed_runs": len(measurements) - len(successful),
        "median_seconds": round(median, 6),
        "p95_seconds": round(percentile(durations, 0.95), 6),
        "images_per_second": round(readable / median, 6),
        "megapixels_per_second": round(megapixels / median, 6),
        "stages": stage_summary,
    }


def write_json(payload: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def benchmark(args: argparse.Namespace, session_root: Path) -> dict[str, Any]:
    inventory = input_inventory(args.input)
    if inventory["readable_files"] == 0:
        raise ValueError(f"no readable input images found in {args.input}")

    worker_results: list[dict[str, Any]] = []
    for workers in args.workers:
        warmups = [
            run_once(
                args,
                workers=workers,
                output=session_root / f"workers-{workers}" / f"warmup-{index}",
                repetition=index,
                warmup=True,
            )
            for index in range(1, args.warmups + 1)
        ]
        measurements = [
            run_once(
                args,
                workers=workers,
                output=session_root / f"workers-{workers}" / f"run-{index}",
                repetition=index,
                warmup=False,
            )
            for index in range(1, args.repeats + 1)
        ]
        worker_results.append(
            {
                "workers": workers,
                "warmups": warmups,
                "measurements": measurements,
                "summary": summarize(measurements, inventory),
            }
        )

    command_shape = [
        args.executable,
        "run",
        "INPUT",
        "--output",
        "OUTPUT",
        "--workers",
        "N",
        "--run-id",
        "benchmark",
    ]
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "informational_only": True,
        "performance_thresholds": None,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version,
            "cpu_count": os.cpu_count(),
            "packages": package_versions(),
            "git_commit": git_commit(),
        },
        "input": {"path": str(args.input), **inventory},
        "settings": {
            "command_shape": command_shape,
            "config": str(args.config) if args.config is not None else None,
            "recipes": list(args.recipe),
            "workers": list(args.workers),
            "repeats": args.repeats,
            "warmups": args.warmups,
            "timeout_seconds": args.timeout,
            "outputs_retained": args.output_root is not None,
        },
        "results": worker_results,
    }


def print_summary(payload: dict[str, Any], json_path: Path) -> None:
    print(f"Benchmark result: {json_path}")
    for result in payload["results"]:
        summary = result["summary"]
        print(
            f"workers={result['workers']}: "
            f"median={summary['median_seconds']}s, "
            f"p95={summary['p95_seconds']}s, "
            f"images/s={summary['images_per_second']}, "
            f"failed={summary['failed_runs']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_name = datetime.now(UTC).strftime("benchmark-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    try:
        if args.output_root is not None:
            session_root = args.output_root / session_name
            session_root.mkdir(parents=True, exist_ok=False)
            payload = benchmark(args, session_root)
        else:
            with tempfile.TemporaryDirectory(prefix="images-extract-benchmark-") as temporary:
                payload = benchmark(args, Path(temporary) / session_name)
    except ValueError as exc:
        print(f"Benchmark could not start: {exc}", file=sys.stderr)
        return 2

    write_json(payload, args.json_path)
    print_summary(payload, args.json_path)
    failed = any(
        item["return_code"] != 0
        for result in payload["results"]
        for group in (result["warmups"], result["measurements"])
        for item in group
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
