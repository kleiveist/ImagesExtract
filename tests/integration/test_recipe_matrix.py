from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from images_extract.config import (
    AppConfig,
    ColorPair,
    ColorsConfig,
    RecipeConfig,
    ScalingConfig,
)
from images_extract.models import StageStatus
from images_extract.pipeline import run_pipeline


def _write_example(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (96, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 36, 54), fill="#143349")
    draw.ellipse((56, 12, 88, 44), fill="#143349")
    image.save(path)


def test_every_builtin_recipe_completes_in_one_explicit_graph(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    _write_example(input_dir / "shapes.png")
    config = replace(
        AppConfig(),
        scaling=ScalingConfig(
            active_scales=(50,),
            scale_options={50: (50, 50)},
            min_percent=25,
            max_percent=200,
        ),
    )

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=config,
        recipe_names=list(config.recipes),
        workers=2,
        run_id="all-recipes",
    )

    assert result.status is StageStatus.SUCCESS
    assert result.run_dir is not None
    stage_names = {stage.name for stage in result.stages}
    for recipe in config.recipes.values():
        assert f"{recipe.name}.scale" in stage_names
        assert (result.run_dir / "collation" / recipe.output_name).is_dir()


def test_colors_and_invert_are_reachable_as_recipe_steps(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    Image.new("RGB", (12, 12), "white").save(input_dir / "white.png")
    recipe = RecipeConfig(
        name="colorinvert",
        output_name="ColorInvert",
        steps=("colors", "invert"),
        enabled=True,
    )
    config = AppConfig(
        recipes={recipe.name: recipe},
        colors=ColorsConfig(
            pairs=(ColorPair(source="#ffffff", target="#ff0000"),),
            max_delta_e=0,
            metric="cie76",
            overlap_policy="first",
            invert=False,
        ),
        scaling=ScalingConfig(
            active_scales=(100,),
            scale_options={100: (100, 100)},
            min_percent=25,
            max_percent=200,
        ),
    )

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=tmp_path / "output",
        config=config,
        run_id="colors-and-invert",
    )

    assert result.status is StageStatus.SUCCESS
    assert result.run_dir is not None
    final = result.run_dir / "collation" / "ColorInvert" / "original" / "white.png"
    with Image.open(final) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (0, 255, 255, 255)
