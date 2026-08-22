"""Read-only preflight validation for the Simple Baker workflow."""

from __future__ import annotations

import os

import bpy

from ..constants import WORKFLOW_SELECTED_TO_ACTIVE
from ..models import ValidationIssue
from .images import selected_map_specs
from .pure import is_supported_color_depth


def validate_target_mesh(target) -> list[ValidationIssue]:
    if target is None:
        return [ValidationIssue("no_target", "Select a mesh object to use as the bake target.")]
    if target.type != "MESH":
        return [
            ValidationIssue(
                "target_not_mesh",
                "Bake target '{name}' must be a mesh object.",
                {"name": target.name},
            )
        ]
    return []


def validate_target_uv(target) -> list[ValidationIssue]:
    if target is None or target.type != "MESH":
        return []
    if not target.data.uv_layers:
        return [
            ValidationIssue(
                "missing_uv",
                "Bake target '{name}' has no UV map. Create one in UV Editing before baking.",
                {"name": target.name},
            )
        ]
    return []


def validate_target_materials(target) -> list[ValidationIssue]:
    """Require at least one actual material for Image Texture bake targets."""
    if target is None or target.type != "MESH":
        return []
    if not any(slot.material is not None for slot in target.material_slots):
        return [
            ValidationIssue(
                "missing_material",
                "Bake target '{name}' has no material. Assign a material before baking.",
                {"name": target.name},
            )
        ]
    return []


def validate_output_directory(directory: str) -> list[ValidationIssue]:
    if not directory:
        return [
            ValidationIssue(
                "missing_output_directory",
                "Choose an output directory before baking.",
            )
        ]
    path = bpy.path.abspath(directory)
    if not os.path.isdir(path):
        return [
            ValidationIssue(
                "invalid_output_directory",
                "Output directory does not exist: {path}",
                {"path": path},
            )
        ]
    if not os.access(path, os.W_OK):
        return [
            ValidationIssue(
                "unwritable_output_directory",
                "Output directory is not writable: {path}",
                {"path": path},
            )
        ]
    return []


def validate_selected_maps(settings) -> list[ValidationIssue]:
    if not selected_map_specs(settings):
        return [ValidationIssue("no_maps", "Select at least one output map before baking.")]
    return []


def validate_output_format(settings) -> list[ValidationIssue]:
    """Reject invalid values from scripts or older saved preference data."""
    if not is_supported_color_depth(settings.file_format, settings.color_depth):
        return [
            ValidationIssue(
                "unsupported_color_depth",
                "{depth}-bit output is not supported for {format}. Choose a supported color depth.",
                {"depth": settings.color_depth, "format": settings.file_format},
            )
        ]
    return []


def validate_selected_to_active(settings, target) -> list[ValidationIssue]:
    sources = [item.object for item in settings.source_objects]
    if any(source is None for source in sources):
        return [
            ValidationIssue(
                "missing_source",
                "Choose a mesh object for every source-model entry.",
            )
        ]
    if not sources:
        return [
            ValidationIssue(
                "missing_sources",
                "Add at least one source model before baking.",
            )
        ]
    if target in sources:
        return [
            ValidationIssue(
                "target_is_source",
                "The bake target cannot also be a source model.",
            )
        ]
    non_meshes = [obj.name for obj in sources if obj.type != "MESH"]
    if non_meshes:
        return [
            ValidationIssue(
                "source_not_mesh",
                "Selected bake sources must be mesh objects: {names}",
                {"names": ", ".join(non_meshes)},
            )
        ]
    return []


def validate_bake_request(context, settings) -> tuple[ValidationIssue, ...]:
    """Run every preflight check without creating images, nodes, or files."""
    target = settings.bake_target
    issues = validate_target_mesh(target)
    issues.extend(validate_target_uv(target))
    issues.extend(validate_target_materials(target))
    issues.extend(validate_output_directory(settings.output_directory))
    issues.extend(validate_selected_maps(settings))
    issues.extend(validate_output_format(settings))
    if settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE:
        issues.extend(validate_selected_to_active(settings, target))
    return tuple(issues)
