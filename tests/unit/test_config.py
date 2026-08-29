from __future__ import annotations

import json
from pathlib import Path

import pytest

from images_extract.config import AppConfig, ConfigError, load_config


def test_builtin_config_is_valid_and_json_serializable():
    config = load_config()

    assert isinstance(config, AppConfig)
    assert config.working_format == "png"
    assert [recipe.name for recipe in config.enabled_recipes] == ["transback"]
    assert json.loads(json.dumps(config.to_dict()))["working_format"] == "png"


def test_example_toml_loads():
    config = load_config(Path("images-extract.example.toml"))

    assert config.scaling.active_scales == (25, 50, 70, 80)
    assert config.scaling.scale_options[70] == (70, 70)
    assert config.recipes["enhanclean"].steps[-1] == "cleanup"


def test_toml_reports_unknown_and_invalid_values_together(tmp_path):
    config_file = tmp_path / "invalid.toml"
    config_file.write_text(
        """
working_format = "jpeg"
unknown_option = true

[scaling]
active_scales = [25, 75]
min_percent = 25
max_percent = 200

[scaling.scale_options]
25 = [25, 25]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as raised:
        load_config(config_file)

    message = str(raised.value)
    assert "unknown_option" in message
    assert "only png is supported" in message
    assert "missing mapping" in message


def test_legacy_ini_migrates_historical_keys():
    config = load_config(Path("examples/legacy-settings.ini"))

    assert config.working_format == "png"
    assert config.output_folder == "image_ext"
    assert config.extraction.min_width == 100
    assert config.transparency.dark_weight == pytest.approx(0.45)
    assert config.logging.file_enabled is False
    assert config.recipes["transback"].output_name == "TransBack"
    assert config.recipes["enhwhitclean"].output_name == "Enhwhitclean"


def test_legacy_invalid_boolean_is_a_config_error(tmp_path):
    config_file = tmp_path / "legacy.ini"
    config_file.write_text(
        """
[Settings]
output_format = .png
output_foldes_collation1 = TransBack

[Moduls]
TransBack.py = perhaps
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="must be true/false"):
        load_config(config_file)
