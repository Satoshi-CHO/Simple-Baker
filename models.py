"""Small, Blender-independent value objects used by Simple Baker services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class BakeMapSpec:
    """Definition of one native Cycles bake type and its output convention."""

    key: str
    setting_name: str
    bake_type: str
    suffix: str
    label: str
    color_space: str = "sRGB"
    is_pbr: bool = False
    pbr_socket_name: str | None = None
    invert: bool = False


@dataclass(frozen=True)
class ImageSpec:
    """A generated image and its intended external output path."""

    map_spec: BakeMapSpec
    image_name: str
    output_path: str
    width: int
    height: int
    file_format: str
    color_depth: str


@dataclass(frozen=True)
class ValidationIssue:
    """A translatable validation result with data for safe message formatting."""

    code: str
    message_id: str
    values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SavedContextState:
    """Reserved state container for the bake execution phase."""

    render_engine: str
    active_object_name: str | None
    selected_object_names: tuple[str, ...]
    active_object_mode: str | None = None
