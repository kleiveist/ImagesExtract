"""Dependency-free registry of public pipeline stage names."""

from __future__ import annotations

PIPELINE_STAGES = (
    "convert",
    "enhance",
    "transparency",
    "extract",
    "extract_gray",
    "cleanup",
    "colors",
    "invert",
    "scale",
    "collate",
)


__all__ = ["PIPELINE_STAGES"]
