"""Safe, explicit image-processing stages used by the pipeline."""

from images_extract.stages.cleanup import run as cleanup
from images_extract.stages.collate import CollateConfig, CollationInput
from images_extract.stages.collate import run as collate
from images_extract.stages.colors import run as colors
from images_extract.stages.convert import run as convert
from images_extract.stages.enhance import run as enhance
from images_extract.stages.extract import run as extract
from images_extract.stages.extract import run_grayscale as extract_grayscale
from images_extract.stages.scale import run as scale
from images_extract.stages.transparency import run as transparency

__all__ = [
    "CollateConfig",
    "CollationInput",
    "cleanup",
    "collate",
    "colors",
    "convert",
    "enhance",
    "extract",
    "extract_grayscale",
    "scale",
    "transparency",
]
