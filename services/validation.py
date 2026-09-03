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
    from .packing import selected_pack_specs

    has_maps = bool(selected_map_specs(settings)) or bool(selected_pack_specs(settings))
    if not has_maps:
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


def validate_pbr_compatibility(settings, target) -> list[ValidationIssue]:
    """Validate material node structure when PBR extraction maps are selected."""
    from .images import MAP_SPECS
    from .packing import required_source_map_keys

    needed_keys = {spec.key for spec in selected_map_specs(settings)}
    for key in required_source_map_keys(settings):
        needed_keys.add(key)

    pbr_map_lookup = {spec.key: spec for spec in MAP_SPECS if spec.is_pbr}
    needed_pbr_specs = [pbr_map_lookup[k] for k in needed_keys if k in pbr_map_lookup]
    if not needed_pbr_specs:
        return []

    if settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE:
        sources = [item.object for item in settings.source_objects if item.object and item.object.type == "MESH"]
        source_objects = sources
    else:
        source_objects = [target] if target and target.type == "MESH" else []

    if not source_objects:
        return []

    from .pbr import collect_source_materials, inspect_pbr_compatibility

    materials = collect_source_materials(source_objects)
    if not materials:
        return [
            ValidationIssue(
                "pbr_no_materials",
                "PBR map baking requires at least one material assigned to the source model(s).",
            )
        ]

    issues: list[ValidationIssue] = []
    for material in materials:
        for map_spec in needed_pbr_specs:
            issue = inspect_pbr_compatibility(material, map_spec)
            if issue is not None:
                issues.append(issue)
                break
    return issues


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
    issues.extend(validate_pbr_compatibility(settings, target))
    return tuple(issues)
