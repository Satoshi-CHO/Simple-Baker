"""Pure filename helpers that can be tested without Blender's Python API."""

from __future__ import annotations

import re

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FORMAT_EXTENSIONS = {
    "PNG": "png",
    "TARGA": "tga",
    "OPEN_EXR": "exr",
}
COLOR_DEPTHS_BY_FORMAT = {
    "PNG": ("8", "16"),
    "TARGA": ("8",),
    "OPEN_EXR": ("16", "32"),
}


def sanitize_common_name(value: str) -> str:
    """Make a portable file stem without altering the displayed UI value."""
    sanitized = _INVALID_FILENAME_CHARS.sub("_", value.strip())
    sanitized = sanitized.rstrip(". ")
    return sanitized or "bake"


def output_extension(file_format: str) -> str:
    """Return the extension used by a supported Blender image format."""
    return FORMAT_EXTENSIONS[file_format]


def supported_color_depths(file_format: str) -> tuple[str, ...]:
    """Return the bit depths supported by one exposed output format."""
    return COLOR_DEPTHS_BY_FORMAT[file_format]


def default_color_depth(file_format: str) -> str:
    """Return the safest default bit depth for an output format."""
    return supported_color_depths(file_format)[0]


def is_supported_color_depth(file_format: str, color_depth: str) -> bool:
    """Check an output format/depth pair without importing Blender's API."""
    return color_depth in supported_color_depths(file_format)


def output_filename(common_name: str, suffix: str, file_format: str) -> str:
    """Build the language-independent output filename for one selected map."""
    return f"{sanitize_common_name(common_name)}_{suffix}.{output_extension(file_format)}"
