"""Validated, immutable configuration for ImagesExtract.

The public loader accepts the native TOML schema and the historical
``settings.ini`` format.  Legacy spelling mistakes are intentionally handled
here so the rest of the package only has to understand one coherent model.
"""

from __future__ import annotations

import configparser
import math
import re
import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

ALLOWED_STEPS = frozenset(
    {"enhance", "transparency", "extract", "extract_gray", "cleanup", "colors", "invert"}
)
COLLISION_STRATEGIES = frozenset({"error", "suffix", "hash"})

_RECIPE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_LEGACY_COLLATION_RE = re.compile(r"output_folde(?:s|rs)_collation(\d+)$", re.IGNORECASE)
_LEGACY_COLOR_RE = re.compile(r"(src|dst)_color_(\d+)$", re.IGNORECASE)


class ConfigError(ValueError):
    """A configuration error containing every problem discovered in one pass."""

    def __init__(self, errors: str | Sequence[str]) -> None:
        if isinstance(errors, str):
            normalized = (errors,)
        else:
            normalized = tuple(str(error) for error in errors if str(error))
        if not normalized:
            normalized = ("unknown configuration error",)
        self.errors = normalized
        message = "Invalid configuration:\n" + "\n".join(f"- {error}" for error in normalized)
        super().__init__(message)


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _raise_errors(errors: list[str]) -> None:
    if errors:
        raise ConfigError(errors)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _safe_relative_directory(value: object) -> bool:
    if not isinstance(value, str) or not value or value.strip() != value or "\x00" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _safe_output_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
        and value not in {".", ".."}
        and "\x00" not in value
        and "/" not in value
        and "\\" not in value
    )


@dataclass(frozen=True, slots=True)
class RecipeConfig:
    """One explicit branch in the processing graph."""

    name: str
    steps: tuple[str, ...]
    enabled: bool = False
    output_name: str = ""

    def __post_init__(self) -> None:
        try:
            normalized_steps = tuple(self.steps)
        except TypeError:
            normalized_steps = ()
        object.__setattr__(self, "steps", normalized_steps)
        if not self.output_name:
            object.__setattr__(self, "output_name", self.name)

        errors: list[str] = []
        _require(
            isinstance(self.name, str) and bool(_RECIPE_ID_RE.fullmatch(self.name)),
            f"recipes.{self.name}: invalid recipe id",
            errors,
        )
        _require(
            _safe_output_name(self.output_name),
            f"recipes.{self.name}.output_name: invalid folder name",
            errors,
        )
        _require(
            isinstance(self.enabled, bool),
            f"recipes.{self.name}.enabled: must be a boolean",
            errors,
        )
        _require(bool(self.steps), f"recipes.{self.name}.steps: must not be empty", errors)
        unknown = [
            step for step in self.steps if not isinstance(step, str) or step not in ALLOWED_STEPS
        ]
        _require(
            not unknown,
            f"recipes.{self.name}.steps: unsupported step(s): {', '.join(map(str, unknown))}",
            errors,
        )
        _require(
            all(isinstance(step, str) for step in self.steps)
            and len(set(self.steps)) == len(self.steps),
            f"recipes.{self.name}.steps: duplicate steps are not allowed",
            errors,
        )
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class EnhancementConfig:
    color_levels: int = 7
    abstraction_passes: int = 2
    accuracy: float = 1.0
    noise_intensity: float = 10.0
    edge_weight: float = 0.1
    contrast: float = 1.2
    brightness: float = 1.05
    canny_low: int = 50
    canny_high: int = 150

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            _is_int(self.color_levels) and 1 <= self.color_levels <= 256,
            "enhancement.color_levels: must be an integer from 1 to 256",
            errors,
        )
        _require(
            _is_int(self.abstraction_passes) and 0 <= self.abstraction_passes <= 64,
            "enhancement.abstraction_passes: must be an integer from 0 to 64",
            errors,
        )
        _require(
            _is_number(self.accuracy) and self.accuracy > 0,
            "enhancement.accuracy: must be greater than zero",
            errors,
        )
        _require(
            _is_number(self.noise_intensity) and 0 <= self.noise_intensity <= 255,
            "enhancement.noise_intensity: must be between 0 and 255",
            errors,
        )
        _require(
            _is_number(self.edge_weight) and 0 <= self.edge_weight <= 1,
            "enhancement.edge_weight: must be between 0 and 1",
            errors,
        )
        _require(
            _is_number(self.contrast) and 0 <= self.contrast <= 16,
            "enhancement.contrast: must be between 0 and 16",
            errors,
        )
        _require(
            _is_number(self.brightness) and 0 <= self.brightness <= 16,
            "enhancement.brightness: must be between 0 and 16",
            errors,
        )
        _validate_thresholds("enhancement", self.canny_low, self.canny_high, errors)
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class TransparencyConfig:
    min_component_area: int = 100
    kernel_size: int = 13
    dilation_iterations: int = 1
    dark_weight: float = 0.45
    dark_threshold_offset: int = 45
    canny_low: int = 32
    canny_high: int = 155

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            _is_int(self.min_component_area) and self.min_component_area >= 0,
            "transparency.min_component_area: must be a non-negative integer",
            errors,
        )
        _require(
            _is_int(self.kernel_size) and 1 <= self.kernel_size <= 255,
            "transparency.kernel_size: must be an integer from 1 to 255",
            errors,
        )
        _require(
            _is_int(self.dilation_iterations) and 0 <= self.dilation_iterations <= 64,
            "transparency.dilation_iterations: must be an integer from 0 to 64",
            errors,
        )
        _require(
            _is_number(self.dark_weight) and 0 <= self.dark_weight <= 1,
            "transparency.dark_weight: must be between 0 and 1",
            errors,
        )
        _require(
            _is_int(self.dark_threshold_offset) and -255 <= self.dark_threshold_offset <= 255,
            "transparency.dark_threshold_offset: must be an integer from -255 to 255",
            errors,
        )
        _validate_thresholds("transparency", self.canny_low, self.canny_high, errors)
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    min_width: int = 1
    min_height: int = 1
    min_area: int = 100
    alpha_threshold: int = 1

    def __post_init__(self) -> None:
        errors: list[str] = []
        for key in ("min_width", "min_height", "min_area"):
            value = getattr(self, key)
            _require(
                _is_int(value) and value >= 1,
                f"extraction.{key}: must be a positive integer",
                errors,
            )
        _require(
            _is_int(self.alpha_threshold) and 0 <= self.alpha_threshold <= 255,
            "extraction.alpha_threshold: must be an integer from 0 to 255",
            errors,
        )
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class CleanupConfig:
    intensity_lower: int = 1
    intensity_upper: int = 185
    alpha_threshold: int = 1
    min_area: int = 100
    selection: str = "center_then_largest"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            _is_int(self.intensity_lower) and 0 <= self.intensity_lower <= 255,
            "cleanup.intensity_lower: must be an integer from 0 to 255",
            errors,
        )
        _require(
            _is_int(self.intensity_upper) and 0 <= self.intensity_upper <= 255,
            "cleanup.intensity_upper: must be an integer from 0 to 255",
            errors,
        )
        if _is_int(self.intensity_lower) and _is_int(self.intensity_upper):
            _require(
                self.intensity_lower <= self.intensity_upper,
                "cleanup: intensity_lower must not exceed intensity_upper",
                errors,
            )
        _require(
            _is_int(self.alpha_threshold) and 0 <= self.alpha_threshold <= 255,
            "cleanup.alpha_threshold: must be an integer from 0 to 255",
            errors,
        )
        _require(
            _is_int(self.min_area) and self.min_area >= 1,
            "cleanup.min_area: must be a positive integer",
            errors,
        )
        _require(
            isinstance(self.selection, str)
            and self.selection in {"center_then_largest", "largest", "center"},
            "cleanup.selection: must be center_then_largest, largest or center",
            errors,
        )
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class ScalingConfig:
    active_scales: tuple[int, ...] = (25, 50, 70, 80)
    scale_options: Mapping[int, tuple[int, int]] = field(
        default_factory=lambda: {25: (25, 25), 50: (50, 50), 70: (70, 70), 80: (80, 80)}
    )
    min_percent: int = 25
    max_percent: int = 200

    def __post_init__(self) -> None:
        try:
            active_scales = tuple(self.active_scales)
        except TypeError:
            active_scales = ()
        normalized_options: dict[int, tuple[int, int]] = {}
        errors: list[str] = []

        if not isinstance(self.scale_options, Mapping):
            errors.append("scaling.scale_options: must be a mapping")
            raw_options: Mapping[object, object] = {}
        else:
            raw_options = self.scale_options
        for key, value in raw_options.items():
            if not _is_int(key):
                errors.append(f"scaling.scale_options.{key}: scale key must be an integer")
                continue
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                errors.append(f"scaling.scale_options.{key}: must contain exactly two percentages")
                continue
            factors = tuple(value)
            if not all(_is_int(factor) and factor > 0 for factor in factors):
                errors.append(f"scaling.scale_options.{key}: factors must be positive integers")
                continue
            normalized_options[key] = (factors[0], factors[1])

        _require(
            _is_int(self.min_percent) and self.min_percent > 0,
            "scaling.min_percent: must be a positive integer",
            errors,
        )
        _require(
            _is_int(self.max_percent) and self.max_percent > 0,
            "scaling.max_percent: must be a positive integer",
            errors,
        )
        if _is_int(self.min_percent) and _is_int(self.max_percent):
            _require(
                self.min_percent <= self.max_percent,
                "scaling: min_percent must not exceed max_percent",
                errors,
            )
        _require(bool(active_scales), "scaling.active_scales: must not be empty", errors)
        _require(
            all(_is_int(scale) and scale > 0 for scale in active_scales),
            "scaling.active_scales: all scales must be positive integers",
            errors,
        )
        if all(_is_int(scale) for scale in active_scales):
            _require(
                len(set(active_scales)) == len(active_scales),
                "scaling.active_scales: duplicate scales are not allowed",
                errors,
            )
        if _is_int(self.min_percent) and _is_int(self.max_percent):
            outside = [
                scale
                for scale in active_scales
                if _is_int(scale) and not self.min_percent <= scale <= self.max_percent
            ]
            _require(
                not outside, f"scaling.active_scales: outside configured range: {outside}", errors
            )
        missing = [
            scale for scale in active_scales if _is_int(scale) and scale not in normalized_options
        ]
        _require(
            not missing,
            f"scaling.scale_options: missing mapping for active scale(s): {missing}",
            errors,
        )
        _raise_errors(errors)

        object.__setattr__(self, "active_scales", active_scales)
        object.__setattr__(self, "scale_options", MappingProxyType(normalized_options))


@dataclass(frozen=True, slots=True)
class ColorPair:
    source: str
    target: str

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            isinstance(self.source, str) and bool(_HEX_COLOR_RE.fullmatch(self.source)),
            f"colors pair source: invalid #RRGGBB color {self.source!r}",
            errors,
        )
        _require(
            isinstance(self.target, str) and bool(_HEX_COLOR_RE.fullmatch(self.target)),
            f"colors pair target: invalid #RRGGBB color {self.target!r}",
            errors,
        )
        _raise_errors(errors)
        object.__setattr__(self, "source", self.source.lower())
        object.__setattr__(self, "target", self.target.lower())


@dataclass(frozen=True, slots=True)
class ColorsConfig:
    pairs: tuple[ColorPair, ...] = ()
    max_delta_e: float = 5.0
    metric: str = "cie76"
    overlap_policy: str = "first"
    invert: bool = False

    def __post_init__(self) -> None:
        try:
            normalized_pairs = tuple(self.pairs)
        except TypeError:
            normalized_pairs = ()
        object.__setattr__(self, "pairs", normalized_pairs)
        errors: list[str] = []
        _require(
            all(isinstance(pair, ColorPair) for pair in self.pairs),
            "colors.pairs: all entries must be ColorPair objects",
            errors,
        )
        _require(
            _is_number(self.max_delta_e) and self.max_delta_e >= 0,
            "colors.max_delta_e: must be non-negative",
            errors,
        )
        _require(self.metric == "cie76", "colors.metric: only cie76 is supported", errors)
        _require(
            isinstance(self.overlap_policy, str)
            and self.overlap_policy in {"first", "last", "error"},
            "colors.overlap_policy: must be first, last or error",
            errors,
        )
        _require(isinstance(self.invert, bool), "colors.invert: must be a boolean", errors)
        _raise_errors(errors)


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    file_enabled: bool = False
    console_enabled: bool = True
    directory: str = "_log"

    def __post_init__(self) -> None:
        errors: list[str] = []
        _require(
            isinstance(self.file_enabled, bool), "logging.file_enabled: must be a boolean", errors
        )
        _require(
            isinstance(self.console_enabled, bool),
            "logging.console_enabled: must be a boolean",
            errors,
        )
        _require(
            _safe_relative_directory(self.directory),
            "logging.directory: must be a safe relative path",
            errors,
        )
        _raise_errors(errors)


def _builtin_recipes() -> dict[str, RecipeConfig]:
    specifications = (
        ("transback", "TransBack", ("transparency", "extract"), True),
        ("enhancement", "Enhancement", ("enhance", "transparency", "extract"), False),
        ("whitepaper", "Whitepaper", ("transparency", "extract_gray"), False),
        ("enhancwhite", "Enhancwhite", ("enhance", "transparency", "extract_gray"), False),
        ("enhanclean", "Enhanclean", ("enhance", "transparency", "extract", "cleanup"), False),
        ("transclean", "Transclean", ("transparency", "extract", "cleanup"), False),
        (
            "enhwhitclean",
            "Enhwhitclean",
            ("enhance", "transparency", "extract_gray", "cleanup"),
            False,
        ),
    )
    return {
        name: RecipeConfig(name=name, output_name=output_name, steps=steps, enabled=enabled)
        for name, output_name, steps, enabled in specifications
    }


@dataclass(frozen=True, slots=True)
class AppConfig:
    working_format: str = "png"
    output_folder: str = "image_ext"
    recipes: Mapping[str, RecipeConfig] = field(default_factory=_builtin_recipes)
    enhancement: EnhancementConfig = field(default_factory=EnhancementConfig)
    transparency: TransparencyConfig = field(default_factory=TransparencyConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    scaling: ScalingConfig = field(default_factory=ScalingConfig)
    colors: ColorsConfig = field(default_factory=ColorsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    random_seed: int = 0
    collision_strategy: str = "error"
    max_workers: int = 32

    def __post_init__(self) -> None:
        errors: list[str] = []
        if isinstance(self.recipes, Mapping):
            normalized_recipes = dict(self.recipes)
        else:
            normalized_recipes = {}
            errors.append("recipes: must be a mapping")
        _require(self.working_format == "png", "working_format: only png is supported", errors)
        _require(
            _safe_relative_directory(self.output_folder),
            "output_folder: must be a safe relative path",
            errors,
        )
        _require(bool(normalized_recipes), "recipes: at least one recipe is required", errors)
        for key, recipe in normalized_recipes.items():
            _require(
                isinstance(key, str) and isinstance(recipe, RecipeConfig),
                f"recipes.{key}: must be a RecipeConfig",
                errors,
            )
            if isinstance(recipe, RecipeConfig):
                _require(
                    key == recipe.name,
                    f"recipes.{key}: mapping key must match recipe name {recipe.name!r}",
                    errors,
                )
        _require(
            any(
                recipe.enabled
                for recipe in normalized_recipes.values()
                if isinstance(recipe, RecipeConfig)
            ),
            "recipes: at least one recipe must be enabled",
            errors,
        )
        output_names: dict[str, str] = {}
        for key, recipe in normalized_recipes.items():
            if not isinstance(recipe, RecipeConfig):
                continue
            folded = unicodedata.normalize("NFC", recipe.output_name).casefold()
            if folded in output_names:
                previous_name = output_names[folded]
                errors.append(
                    f"recipes.{key}.output_name: duplicates recipes.{previous_name}.output_name"
                )
            else:
                output_names[folded] = key
        _require(
            _is_int(self.random_seed) and 0 <= self.random_seed <= 2**63 - 1,
            "random_seed: must be an integer from 0 to 9223372036854775807",
            errors,
        )
        _require(
            isinstance(self.collision_strategy, str)
            and self.collision_strategy in COLLISION_STRATEGIES,
            "collision_strategy: must be error, suffix or hash",
            errors,
        )
        _require(
            _is_int(self.max_workers) and 1 <= self.max_workers <= 32,
            "max_workers: must be an integer from 1 to 32",
            errors,
        )
        for name, value, expected in (
            ("enhancement", self.enhancement, EnhancementConfig),
            ("transparency", self.transparency, TransparencyConfig),
            ("extraction", self.extraction, ExtractionConfig),
            ("cleanup", self.cleanup, CleanupConfig),
            ("scaling", self.scaling, ScalingConfig),
            ("colors", self.colors, ColorsConfig),
            ("logging", self.logging, LoggingConfig),
        ):
            _require(isinstance(value, expected), f"{name}: must be {expected.__name__}", errors)
        _raise_errors(errors)
        object.__setattr__(self, "recipes", MappingProxyType(normalized_recipes))

    @property
    def enabled_recipes(self) -> tuple[RecipeConfig, ...]:
        return tuple(recipe for recipe in self.recipes.values() if recipe.enabled)

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic payload containing JSON-compatible values only."""

        return {
            "working_format": self.working_format,
            "output_folder": self.output_folder,
            "random_seed": self.random_seed,
            "collision_strategy": self.collision_strategy,
            "max_workers": self.max_workers,
            "recipes": {
                name: {
                    "enabled": recipe.enabled,
                    "output_name": recipe.output_name,
                    "steps": list(recipe.steps),
                }
                for name, recipe in self.recipes.items()
            },
            "enhancement": _plain_dataclass(self.enhancement),
            "transparency": _plain_dataclass(self.transparency),
            "extraction": _plain_dataclass(self.extraction),
            "cleanup": _plain_dataclass(self.cleanup),
            "scaling": {
                "active_scales": list(self.scaling.active_scales),
                "scale_options": {
                    str(scale): list(factors)
                    for scale, factors in sorted(self.scaling.scale_options.items())
                },
                "min_percent": self.scaling.min_percent,
                "max_percent": self.scaling.max_percent,
            },
            "colors": {
                "pairs": [
                    {"source": pair.source, "target": pair.target} for pair in self.colors.pairs
                ],
                "max_delta_e": self.colors.max_delta_e,
                "metric": self.colors.metric,
                "overlap_policy": self.colors.overlap_policy,
                "invert": self.colors.invert,
            },
            "logging": _plain_dataclass(self.logging),
        }


def _plain_dataclass(instance: object) -> dict[str, Any]:
    return {item.name: getattr(instance, item.name) for item in fields(instance)}


def _validate_thresholds(prefix: str, low: object, high: object, errors: list[str]) -> None:
    _require(
        _is_int(low) and 0 <= low <= 255,
        f"{prefix}.canny_low: must be an integer from 0 to 255",
        errors,
    )
    _require(
        _is_int(high) and 0 <= high <= 255,
        f"{prefix}.canny_high: must be an integer from 0 to 255",
        errors,
    )
    if _is_int(low) and _is_int(high):
        _require(low <= high, f"{prefix}: canny_low must not exceed canny_high", errors)


_T = TypeVar("_T")


def _construct(factory: type[_T], errors: list[str], fallback: _T, **values: Any) -> _T:
    try:
        return factory(**values)
    except ConfigError as exc:
        errors.extend(exc.errors)
        return fallback


def load_config(path: Path | None = None) -> AppConfig:
    """Load the built-in defaults, a TOML file, or a historical INI file."""

    if path is None:
        return AppConfig()
    config_path = Path(path).expanduser().resolve(strict=False)
    if not config_path.is_file():
        raise ConfigError(f"config: file not found: {config_path}")
    suffix = config_path.suffix.casefold()
    if suffix == ".toml":
        try:
            with config_path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"config: could not read TOML file {config_path}: {exc}") from exc
        return _config_from_mapping(raw)
    if suffix == ".ini":
        return _config_from_legacy_ini(config_path)
    raise ConfigError(f"config: unsupported file type {suffix or '<none>'}; expected .toml or .ini")


def _config_from_mapping(raw: Mapping[str, Any]) -> AppConfig:
    defaults = AppConfig()
    errors: list[str] = []
    allowed_top = {
        "working_format",
        "output_folder",
        "random_seed",
        "collision_strategy",
        "max_workers",
        "recipes",
        "enhancement",
        "transparency",
        "extraction",
        "cleanup",
        "scaling",
        "colors",
        "logging",
    }
    _unknown_keys(raw, allowed_top, "", errors)

    working_format = _typed(
        raw, "working_format", defaults.working_format, str, "working_format", errors
    )
    output_folder = _typed(
        raw, "output_folder", defaults.output_folder, str, "output_folder", errors
    )
    random_seed = _typed(raw, "random_seed", defaults.random_seed, int, "random_seed", errors)
    collision_strategy = _typed(
        raw, "collision_strategy", defaults.collision_strategy, str, "collision_strategy", errors
    )
    max_workers = _typed(raw, "max_workers", defaults.max_workers, int, "max_workers", errors)

    enhancement = _section_dataclass(
        raw,
        "enhancement",
        defaults.enhancement,
        EnhancementConfig,
        {
            "color_levels": int,
            "abstraction_passes": int,
            "accuracy": float,
            "noise_intensity": float,
            "edge_weight": float,
            "contrast": float,
            "brightness": float,
            "canny_low": int,
            "canny_high": int,
        },
        errors,
    )
    transparency = _section_dataclass(
        raw,
        "transparency",
        defaults.transparency,
        TransparencyConfig,
        {
            "min_component_area": int,
            "kernel_size": int,
            "dilation_iterations": int,
            "dark_weight": float,
            "dark_threshold_offset": int,
            "canny_low": int,
            "canny_high": int,
        },
        errors,
    )
    extraction = _section_dataclass(
        raw,
        "extraction",
        defaults.extraction,
        ExtractionConfig,
        {"min_width": int, "min_height": int, "min_area": int, "alpha_threshold": int},
        errors,
    )
    cleanup = _section_dataclass(
        raw,
        "cleanup",
        defaults.cleanup,
        CleanupConfig,
        {
            "intensity_lower": int,
            "intensity_upper": int,
            "alpha_threshold": int,
            "min_area": int,
            "selection": str,
        },
        errors,
    )
    logging_config = _section_dataclass(
        raw,
        "logging",
        defaults.logging,
        LoggingConfig,
        {"file_enabled": bool, "console_enabled": bool, "directory": str},
        errors,
    )
    scaling = _scaling_from_mapping(raw, defaults.scaling, errors)
    colors = _colors_from_mapping(raw, defaults.colors, errors)
    recipes = _recipes_from_mapping(raw, defaults.recipes, errors)

    config = _construct(
        AppConfig,
        errors,
        defaults,
        working_format=working_format,
        output_folder=output_folder,
        recipes=recipes,
        enhancement=enhancement,
        transparency=transparency,
        extraction=extraction,
        cleanup=cleanup,
        scaling=scaling,
        colors=colors,
        logging=logging_config,
        random_seed=random_seed,
        collision_strategy=collision_strategy,
        max_workers=max_workers,
    )
    _raise_errors(errors)
    return config


def _section_dataclass(
    root: Mapping[str, Any],
    section_name: str,
    default: _T,
    factory: type[_T],
    schema: Mapping[str, type],
    errors: list[str],
) -> _T:
    section = _mapping_section(root, section_name, errors)
    _unknown_keys(section, set(schema), f"{section_name}.", errors)
    values = {
        key: _typed(section, key, getattr(default, key), expected, f"{section_name}.{key}", errors)
        for key, expected in schema.items()
    }
    return _construct(factory, errors, default, **values)


def _scaling_from_mapping(
    root: Mapping[str, Any], default: ScalingConfig, errors: list[str]
) -> ScalingConfig:
    section = _mapping_section(root, "scaling", errors)
    _unknown_keys(
        section,
        {"active_scales", "scale_options", "min_percent", "max_percent"},
        "scaling.",
        errors,
    )
    active_raw = section.get("active_scales", list(default.active_scales))
    if not isinstance(active_raw, list):
        errors.append("scaling.active_scales: must be an array of integers")
        active_scales = default.active_scales
    else:
        active_scales = tuple(active_raw)
    min_percent = _typed(
        section, "min_percent", default.min_percent, int, "scaling.min_percent", errors
    )
    max_percent = _typed(
        section, "max_percent", default.max_percent, int, "scaling.max_percent", errors
    )

    if "scale_options" not in section:
        options: Mapping[int, tuple[int, int]] = default.scale_options
    else:
        raw_options = section["scale_options"]
        options_dict: dict[int, tuple[int, int]] = {}
        if not isinstance(raw_options, Mapping):
            errors.append("scaling.scale_options: must be a table")
        else:
            for raw_key, raw_factors in raw_options.items():
                try:
                    key = int(raw_key)
                except (TypeError, ValueError):
                    errors.append(f"scaling.scale_options.{raw_key}: key must be an integer")
                    continue
                if isinstance(raw_key, bool) or str(key) != str(raw_key):
                    errors.append(
                        f"scaling.scale_options.{raw_key}: key must be a canonical integer"
                    )
                    continue
                if not isinstance(raw_factors, list) or len(raw_factors) != 2:
                    errors.append(
                        f"scaling.scale_options.{raw_key}: must be an array of two integers"
                    )
                    continue
                options_dict[key] = tuple(raw_factors)  # validated by ScalingConfig
        options = options_dict
    return _construct(
        ScalingConfig,
        errors,
        default,
        active_scales=active_scales,
        scale_options=options,
        min_percent=min_percent,
        max_percent=max_percent,
    )


def _colors_from_mapping(
    root: Mapping[str, Any], default: ColorsConfig, errors: list[str]
) -> ColorsConfig:
    section = _mapping_section(root, "colors", errors)
    _unknown_keys(
        section, {"pairs", "max_delta_e", "metric", "overlap_policy", "invert"}, "colors.", errors
    )
    pairs: list[ColorPair] = []
    raw_pairs = section.get("pairs", [])
    if not isinstance(raw_pairs, list):
        errors.append("colors.pairs: must be an array of tables")
    else:
        for index, raw_pair in enumerate(raw_pairs):
            path = f"colors.pairs[{index}]"
            if not isinstance(raw_pair, Mapping):
                errors.append(f"{path}: must be a table")
                continue
            _unknown_keys(raw_pair, {"source", "target"}, f"{path}.", errors)
            source = _typed(raw_pair, "source", "", str, f"{path}.source", errors)
            target = _typed(raw_pair, "target", "", str, f"{path}.target", errors)
            try:
                pairs.append(ColorPair(source=source, target=target))
            except ConfigError as exc:
                errors.extend(f"{path}: {error}" for error in exc.errors)
    values = {
        "pairs": tuple(pairs),
        "max_delta_e": _typed(
            section, "max_delta_e", default.max_delta_e, float, "colors.max_delta_e", errors
        ),
        "metric": _typed(section, "metric", default.metric, str, "colors.metric", errors),
        "overlap_policy": _typed(
            section, "overlap_policy", default.overlap_policy, str, "colors.overlap_policy", errors
        ),
        "invert": _typed(section, "invert", default.invert, bool, "colors.invert", errors),
    }
    return _construct(ColorsConfig, errors, default, **values)


def _recipes_from_mapping(
    root: Mapping[str, Any], default: Mapping[str, RecipeConfig], errors: list[str]
) -> Mapping[str, RecipeConfig]:
    if "recipes" not in root:
        return default
    raw_recipes = root["recipes"]
    if not isinstance(raw_recipes, Mapping):
        errors.append("recipes: must be a table")
        return default
    recipes = dict(default)
    for raw_name, raw_recipe in raw_recipes.items():
        name = str(raw_name)
        path = f"recipes.{name}"
        if not isinstance(raw_recipe, Mapping):
            errors.append(f"{path}: must be a table")
            continue
        _unknown_keys(raw_recipe, {"enabled", "output_name", "steps"}, f"{path}.", errors)
        previous = recipes.get(name)
        if previous is None:
            previous_steps: tuple[str, ...] = ()
            previous_enabled = False
            previous_output = name
        else:
            previous_steps = previous.steps
            previous_enabled = previous.enabled
            previous_output = previous.output_name
        enabled = _typed(raw_recipe, "enabled", previous_enabled, bool, f"{path}.enabled", errors)
        output_name = _typed(
            raw_recipe, "output_name", previous_output, str, f"{path}.output_name", errors
        )
        raw_steps = raw_recipe.get("steps", list(previous_steps))
        if not isinstance(raw_steps, list) or not all(isinstance(step, str) for step in raw_steps):
            errors.append(f"{path}.steps: must be an array of strings")
            steps = previous_steps
        else:
            steps = tuple(raw_steps)
        fallback = previous or RecipeConfig(name="fallback", steps=("extract",))
        recipe = _construct(
            RecipeConfig,
            errors,
            fallback,
            name=name,
            steps=steps,
            enabled=enabled,
            output_name=output_name,
        )
        if previous is not None or recipe.name == name:
            recipes[name] = recipe
    return recipes


def _typed(
    mapping: Mapping[str, Any],
    key: str,
    default: _T,
    expected: type,
    path: str,
    errors: list[str],
) -> _T:
    if key not in mapping:
        return default
    value = mapping[key]
    valid = False
    if expected is int:
        valid = _is_int(value)
    elif expected is float:
        valid = _is_number(value)
    elif expected is bool:
        valid = isinstance(value, bool)
    else:
        valid = isinstance(value, expected)
    if not valid:
        errors.append(f"{path}: must be {expected.__name__}")
        return default
    if expected is float:
        return float(value)  # type: ignore[return-value]
    return value


def _mapping_section(root: Mapping[str, Any], name: str, errors: list[str]) -> Mapping[str, Any]:
    value = root.get(name, {})
    if not isinstance(value, Mapping):
        errors.append(f"{name}: must be a table")
        return {}
    return value


def _unknown_keys(
    mapping: Mapping[str, Any], allowed: set[str], prefix: str, errors: list[str]
) -> None:
    for key in sorted(set(mapping) - allowed, key=str):
        errors.append(f"{prefix}{key}: unknown setting")


def _config_from_legacy_ini(path: Path) -> AppConfig:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise ConfigError(f"config: could not read legacy INI file {path}: {exc}") from exc

    errors: list[str] = []
    raw: dict[str, Any] = {}
    sections = {section.casefold(): section for section in parser.sections()}

    def section(name: str) -> configparser.SectionProxy | None:
        actual = sections.get(name.casefold())
        return parser[actual] if actual is not None else None

    settings = section("Settings")
    if settings is not None:
        if "output_format" in settings:
            raw["working_format"] = settings["output_format"].strip().lower().lstrip(".")
        if "output_folder" in settings:
            raw["output_folder"] = settings["output_folder"].strip()
        enhancement: dict[str, Any] = {}
        _legacy_number(settings, "color_levels", enhancement, "color_levels", int, errors)
        _legacy_number(
            settings, "abstraction_degree", enhancement, "abstraction_passes", int, errors
        )
        for key in ("accuracy", "noise_intensity", "edge_weight", "contrast", "brightness"):
            _legacy_number(settings, key, enhancement, key, float, errors)
        if enhancement:
            raw["enhancement"] = enhancement

        transparency: dict[str, Any] = {}
        mappings: tuple[tuple[str, str, type], ...] = (
            ("min_icon_size", "min_component_area", int),
            ("kernel_size", "kernel_size", int),
            ("iterations", "dilation_iterations", int),
            ("weight_factor", "dark_weight", float),
            ("dark_threshold_offset", "dark_threshold_offset", int),
            ("canny_threshold1", "canny_low", int),
            ("canny_threshold2", "canny_high", int),
        )
        for legacy_key, new_key, kind in mappings:
            _legacy_number(settings, legacy_key, transparency, new_key, kind, errors)
        if transparency:
            raw["transparency"] = transparency

        if "extractsize" in settings:
            extract_size = _parse_legacy_number(
                settings["extractsize"], int, "Settings.extractsize", errors
            )
            if extract_size is not None:
                raw["extraction"] = {
                    "min_width": extract_size,
                    "min_height": extract_size,
                    "min_area": extract_size,
                }

    cleanup_section = section("CleanUp")
    if cleanup_section is not None:
        cleanup: dict[str, Any] = {}
        _legacy_number(cleanup_section, "tolerance_lower", cleanup, "intensity_lower", int, errors)
        _legacy_number(cleanup_section, "tolerance_upper", cleanup, "intensity_upper", int, errors)
        if settings is not None and "extractsize" in settings:
            min_area = _parse_legacy_number(
                settings["extractsize"], int, "Settings.extractsize", errors
            )
            if min_area is not None:
                cleanup["min_area"] = min_area
        if cleanup:
            raw["cleanup"] = cleanup

    scaling_section = section("Scaling")
    if scaling_section is not None:
        scaling: dict[str, Any] = {}
        _legacy_number(scaling_section, "max_downscale", scaling, "min_percent", int, errors)
        _legacy_number(scaling_section, "max_upscale", scaling, "max_percent", int, errors)
        if "active_scales" in scaling_section:
            values: list[int] = []
            for item in scaling_section["active_scales"].split(","):
                parsed = _parse_legacy_number(item.strip(), int, "Scaling.active_scales", errors)
                if parsed is not None:
                    values.append(parsed)
            scaling["active_scales"] = values
        if "scale_options" in scaling_section and scaling_section["scale_options"].strip():
            options: dict[str, list[int]] = {}
            for item in scaling_section["scale_options"].split(";"):
                try:
                    raw_key, raw_factors = item.split(":", 1)
                    factors = [int(part.strip()) for part in raw_factors.split(",")]
                    options[str(int(raw_key.strip()))] = factors
                except (TypeError, ValueError):
                    errors.append(f"Scaling.scale_options: invalid mapping {item!r}")
            scaling["scale_options"] = options
        if scaling:
            raw["scaling"] = scaling

    logger_section = section("LOGGER")
    if logger_section is not None:
        logging_values: dict[str, Any] = {}
        if "logging_enabled" in logger_section:
            parsed = _parse_legacy_bool(
                logger_section["logging_enabled"], "LOGGER.logging_enabled", errors
            )
            if parsed is not None:
                logging_values["file_enabled"] = parsed
        if "console_output" in logger_section:
            parsed = _parse_legacy_bool(
                logger_section["console_output"], "LOGGER.console_output", errors
            )
            if parsed is not None:
                logging_values["console_enabled"] = parsed
        if "logger_folder" in logger_section:
            parsed = _parse_legacy_bool(
                logger_section["logger_folder"], "LOGGER.logger_folder", errors
            )
            if parsed is not None:
                logging_values["directory"] = "_log" if parsed else "."
        if logging_values:
            raw["logging"] = logging_values

    swap_section = section("swap")
    if swap_section is not None:
        colors: dict[str, Any] = {}
        indexes: set[int] = set()
        for option in swap_section:
            match = _LEGACY_COLOR_RE.fullmatch(option)
            if match:
                indexes.add(int(match.group(2)))
        pairs: list[dict[str, str]] = []
        for index in sorted(indexes):
            source_key = f"src_color_{index}"
            target_key = f"dst_color_{index}"
            if source_key not in swap_section or target_key not in swap_section:
                errors.append(
                    f"swap color pair {index}: both {source_key} and {target_key} are required"
                )
                continue
            pairs.append(
                {
                    "source": swap_section[source_key].strip(),
                    "target": swap_section[target_key].strip(),
                }
            )
        if pairs:
            colors["pairs"] = pairs
        if "tolerance" in swap_section:
            tolerance = _parse_legacy_number(
                swap_section["tolerance"], float, "swap.tolerance", errors
            )
            if tolerance is not None:
                colors["max_delta_e"] = tolerance
        if colors:
            raw["colors"] = colors

    _legacy_recipes(parser, sections, raw, errors)
    if errors:
        # Continue through native validation as well, returning every useful error.
        try:
            _config_from_mapping(raw)
        except ConfigError as exc:
            errors.extend(exc.errors)
        raise ConfigError(_deduplicate(errors))
    return _config_from_mapping(raw)


def _legacy_recipes(
    parser: configparser.ConfigParser,
    sections: Mapping[str, str],
    raw: dict[str, Any],
    errors: list[str],
) -> None:
    actual_settings = sections.get("settings")
    settings = parser[actual_settings] if actual_settings else None
    recipes = _recipes_to_raw(_builtin_recipes())
    explicitly_configured: set[str] = set()
    index_to_name = {
        1: "transback",
        2: "enhancement",
        3: "whitepaper",
        4: "enhancwhite",
        5: "enhanclean",
        6: "transclean",
        7: "enhwhitclean",
        8: "swapcolors",
        9: "invert",
    }
    if settings is not None:
        for option, value in settings.items():
            match = _LEGACY_COLLATION_RE.fullmatch(option)
            if not match:
                continue
            index = int(match.group(1))
            name = index_to_name.get(index)
            if name is None:
                errors.append(f"Settings.{option}: unsupported legacy collation index {index}")
                continue
            output_name = value.strip()
            if index == 8 and name not in recipes:
                recipes[name] = {"steps": ["transparency", "colors"]}
            elif index == 9 and name not in recipes:
                recipes[name] = {"steps": ["transparency", "invert"]}
            recipes[name]["enabled"] = True
            recipes[name]["output_name"] = output_name
            explicitly_configured.add(name)

    cleanup_actual = sections.get("cleanup")
    if cleanup_actual:
        cleanup = parser[cleanup_actual]
        for index, name in index_to_name.items():
            option = f"collation{index}"
            if option not in cleanup or name not in recipes:
                continue
            enabled = _parse_legacy_bool(cleanup[option], f"CleanUp.{option}", errors)
            if enabled is None:
                continue
            steps = list(recipes[name]["steps"])
            if enabled and "cleanup" not in steps:
                insertion = next(
                    (steps.index(step) for step in ("colors", "invert") if step in steps),
                    len(steps),
                )
                steps.insert(insertion, "cleanup")
            elif not enabled and "cleanup" in steps:
                steps.remove("cleanup")
            recipes[name]["steps"] = steps

    modules_actual = sections.get("moduls")
    if modules_actual:
        modules = parser[modules_actual]
        module_steps = {
            "enhancement.py": "enhance",
            "transback.py": "transparency",
            "extract.py": "extract",
            "extractgray.py": "extract_gray",
            "cleanup.py": "cleanup",
            "swapcolors.py": "colors",
            "invert.py": "invert",
        }
        for option, step in module_steps.items():
            if option not in modules:
                continue
            enabled = _parse_legacy_bool(modules[option], f"Moduls.{option}", errors)
            if enabled is False:
                for recipe in recipes.values():
                    if step in recipe["steps"]:
                        recipe["steps"].remove(step)

    # The built-in transback default remains enabled when no legacy branches exist.
    # Presence of branch entries explicitly enables every represented legacy branch.
    raw["recipes"] = recipes


def _recipes_to_raw(recipes: Mapping[str, RecipeConfig]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "enabled": recipe.enabled,
            "output_name": recipe.output_name,
            "steps": list(recipe.steps),
        }
        for name, recipe in recipes.items()
    }


def _legacy_number(
    section: configparser.SectionProxy,
    legacy_key: str,
    target: dict[str, Any],
    new_key: str,
    kind: type,
    errors: list[str],
) -> None:
    if legacy_key not in section:
        return
    value = _parse_legacy_number(section[legacy_key], kind, f"{section.name}.{legacy_key}", errors)
    if value is not None:
        target[new_key] = value


def _parse_legacy_number(
    value: str, kind: type, path: str, errors: list[str]
) -> int | float | None:
    try:
        return kind(value.strip())
    except (TypeError, ValueError):
        errors.append(f"{path}: must be {kind.__name__}")
        return None


def _parse_legacy_bool(value: str, path: str, errors: list[str]) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    errors.append(f"{path}: must be true/false, 1/0, yes/no or on/off")
    return None


def _deduplicate(errors: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(errors))


__all__ = [
    "ALLOWED_STEPS",
    "AppConfig",
    "CleanupConfig",
    "ColorPair",
    "ColorsConfig",
    "ConfigError",
    "EnhancementConfig",
    "ExtractionConfig",
    "LoggingConfig",
    "RecipeConfig",
    "ScalingConfig",
    "TransparencyConfig",
    "load_config",
]
