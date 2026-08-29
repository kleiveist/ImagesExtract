from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from images_extract.cli import main


def _write_rgba(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (24, 24), (20, 40, 60, 255)).save(path)
    return path


def test_help_lists_all_public_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    for command in ("run", "stage", "doctor", "validate-config"):
        assert command in output


def test_doctor_and_validate_config_succeed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    example = Path("images-extract.example.toml").resolve()

    assert main(["doctor"]) == 0
    doctor_output = capsys.readouterr().out
    assert "Konfiguration gültig" in doctor_output
    assert "Installation einsatzbereit" in doctor_output

    assert main(["validate-config", "--config", str(example)]) == 0
    validation_output = capsys.readouterr().out
    assert "Rezept transback" in validation_output


def test_validate_config_returns_usage_error_for_invalid_toml(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.toml"
    invalid.write_text('working_format = "jpeg"\n', encoding="utf-8")

    assert main(["validate-config", "--config", str(invalid)]) == 2
    assert "only png is supported" in capsys.readouterr().err


def test_cli_exit_codes_distinguish_success_processing_and_usage_errors(
    tmp_path: Path,
) -> None:
    valid_input = tmp_path / "valid"
    _write_rgba(valid_input / "image.png")
    assert (
        main(
            [
                "stage",
                "convert",
                str(valid_input),
                "--output",
                str(tmp_path / "valid-output"),
            ]
        )
        == 0
    )

    corrupt_input = tmp_path / "corrupt"
    corrupt_input.mkdir()
    (corrupt_input / "broken.png").write_bytes(b"broken")
    assert (
        main(
            [
                "stage",
                "convert",
                str(corrupt_input),
                "--output",
                str(tmp_path / "corrupt-output"),
            ]
        )
        == 1
    )

    assert (
        main(
            [
                "run",
                str(tmp_path / "missing"),
                "--output",
                str(tmp_path / "missing-output"),
            ]
        )
        == 2
    )


def test_cli_empty_contract_does_not_create_output(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    rejected_output = tmp_path / "rejected"
    allowed_output = tmp_path / "allowed"

    assert main(["run", str(empty), "--output", str(rejected_output)]) == 1
    assert (
        main(
            [
                "run",
                str(empty),
                "--output",
                str(allowed_output),
                "--allow-empty",
            ]
        )
        == 0
    )
    assert not rejected_output.exists()
    assert not allowed_output.exists()


def test_cli_rejects_collision_before_creating_a_run(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(input_dir / "same.png")
    Image.new("RGB", (8, 8), (30, 20, 10)).save(input_dir / "same.bmp")
    output_dir = tmp_path / "output"

    code = main(["run", str(input_dir), "--output", str(output_dir)])

    assert code == 2
    assert not output_dir.exists()


def test_cli_rejects_non_positive_worker_count() -> None:
    with pytest.raises(SystemExit) as raised:
        main(["run", "input", "--output", "output", "--workers", "0"])

    assert raised.value.code == 2


def test_doctor_reports_installed_but_unimportable_native_dependency(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from images_extract import cli

    real_import = cli.importlib.import_module

    def fail_cv2(name: str):
        if name == "cv2":
            raise ImportError("simulated native loader failure")
        return real_import(name)

    with patch.object(cli.importlib, "import_module", side_effect=fail_cv2):
        assert main(["doctor"]) == 1

    error_output = capsys.readouterr().err
    assert "opencv-python-headless" in error_output
    assert "simulated native loader failure" in error_output
