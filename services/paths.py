"""Pure output-path helpers for Simple Baker."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import bpy

from ..models import BakeMapSpec, ImageSpec
from .pure import output_filename


def build_output_path(directory: str, common_name: str, map_spec: BakeMapSpec, file_format: str) -> str:
    """Build an absolute `<name>_<suffix>.<extension>` output path."""
    absolute_directory = bpy.path.abspath(directory)
    filename = output_filename(common_name, map_spec.suffix, file_format)
    return str(Path(absolute_directory) / filename)


def find_existing_outputs(image_specs: Iterable[ImageSpec]) -> list[str]:
    """Return existing proposed files without creating, opening, or modifying files."""
    return [spec.output_path for spec in image_specs if os.path.isfile(spec.output_path)]
