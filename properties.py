"""Scene-level UI settings and preference synchronization."""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from .constants import (
    ADDON_ID,
    NORMAL_FORMAT_CUSTOM,
    NORMAL_FORMAT_DIRECTX,
    NORMAL_FORMAT_OPENGL,
    PERSISTED_FIELDS,
    WORKFLOW_SELF,
    WORKFLOW_SELECTED_TO_ACTIVE,
)
from .services.pure import default_color_depth, supported_color_depths

_preference_sync_suspended = False


def _preferences(context):
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def _sync_to_preferences(settings, context) -> None:
    # Assigning RNA properties while restoring them also invokes their update
    # callbacks. Do not copy the scene's still-partial state back over the saved
    # preferences while the restoration batch is in progress.
    if _preference_sync_suspended:
        return
    preferences = _preferences(context)
    if preferences is None:
        return
    for field in PERSISTED_FIELDS:
        setattr(preferences, field, getattr(settings, field))


def _workflow_updated(settings, context) -> None:
    _sync_to_preferences(settings, context)
    scene = getattr(context, "scene", None)
    if scene is not None:
        scene.render.bake.use_selected_to_active = (
            settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE
        )


def _setting_updated(settings, context) -> None:
    _sync_to_preferences(settings, context)


def _file_format_updated(settings, context) -> None:
    if settings.color_depth not in supported_color_depths(settings.file_format):
        settings.color_depth = default_color_depth(settings.file_format)
    _sync_to_preferences(settings, context)


def apply_normal_map_format(scene, normal_format: str) -> None:
    """Apply a target format to Blender's tangent-space normal bake settings."""
    if normal_format == NORMAL_FORMAT_CUSTOM:
        return
    bake = scene.render.bake
    bake.normal_space = "TANGENT"
    bake.normal_r = "POS_X"
    bake.normal_g = "POS_Y" if normal_format == NORMAL_FORMAT_OPENGL else "NEG_Y"
    bake.normal_b = "POS_Z"


def _normal_format_updated(settings, context) -> None:
    _sync_to_preferences(settings, context)
    scene = getattr(context, "scene", None)
    if scene is not None:
        apply_normal_map_format(scene, settings.normal_format)


def _bake_pass_get(attribute: str):
    def get_value(settings) -> bool:
        return bool(getattr(settings.id_data.render.bake, attribute))

    return get_value


def _bake_pass_set(attribute: str):
    def set_value(settings, value: bool) -> None:
        setattr(settings.id_data.render.bake, attribute, value)

    return set_value


def _map_property(name: str, description: str) -> BoolProperty:
    return BoolProperty(name=name, description=description, default=False, update=_setting_updated)


def _is_mesh_object(_self, obj) -> bool:
    return obj.type == "MESH"


def render_output_directory(scene) -> str:
    """Return the folder represented by Blender's render output path."""
    render_path = scene.render.filepath
    absolute_render_path = bpy.path.abspath(render_path)
    if render_path.endswith(("/", "\\")) or os.path.isdir(absolute_render_path):
        return absolute_render_path
    return os.path.dirname(absolute_render_path) if absolute_render_path else ""


class SIMPLEBAKER_SourceObject(PropertyGroup):
    """One explicitly chosen source object for selected-to-active baking."""

    object: PointerProperty(type=bpy.types.Object, poll=_is_mesh_object)


class SIMPLEBAKER_Settings(PropertyGroup):
    """Current-scene settings not supplied by Blender's BakeSettings RNA."""

    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})
    output_map_tab: EnumProperty(
        name="Output Map Category",
        items=(
            ("PBR", "PBR Maps", "PBR texture maps for Principled BSDF and external tools"),
            ("CYCLES", "Cycles Standard", "Blender's standard Cycles bake passes"),
        ),
        default="PBR",
        options={"SKIP_SAVE"},
    )
    pbr_output_section: EnumProperty(
        name="PBR Output Type",
        items=(
            ("INDIVIDUAL", "Individual Maps", "Bake individual PBR texture maps"),
            ("PACK", "Packed Output", "Pack PBR data into RGBA presets"),
        ),
        default="INDIVIDUAL",
        options={"SKIP_SAVE"},
    )
    show_advanced_pbr_inputs: BoolProperty(
        name="Advanced PBR Inputs (Raw)",
        description="Show advanced raw Principled BSDF input maps",
        default=False,
        options={"SKIP_SAVE"},
    )
    workflow: EnumProperty(
        name="Bake Method",
        items=(
            (WORKFLOW_SELF, "Bake This Model", "Bake a mesh object to itself"),
            (
                WORKFLOW_SELECTED_TO_ACTIVE,
                "Transfer From Other Models",
                "Bake source meshes onto a separate target mesh",
            ),
        ),
        default=WORKFLOW_SELF,
        update=_workflow_updated,
    )
    bake_target: PointerProperty(
        name="Bake Target",
        description="Mesh object that receives the baked images",
        type=bpy.types.Object,
        poll=_is_mesh_object,
    )
    source_objects: CollectionProperty(type=SIMPLEBAKER_SourceObject)
    map_combined: _map_property(
        "Combined",
        "Bakes materials, textures, and lighting except specularity. Use for a final-look texture; contribution settings control its contents.",
    )
    map_ao: _map_property(
        "Ambient Occlusion",
        "Bakes grayscale ambient occlusion and ignores scene lights. Usually multiply with a color texture in a shader or compositor.",
    )
    map_shadow: _map_property(
        "Shadow",
        "Bakes shadows and lighting. Use for compositing or a custom lighting workflow.",
    )
    map_normal: _map_property(
        "Normal",
        "Bakes surface normal directions as RGB. Use through a Normal Map node when connecting it to a shader.",
    )
    map_uv: _map_property(
        "UV",
        "Bakes mapped UV coordinates into red and green; blue is always 1. Use for diagnostics or custom coordinate-based shaders.",
    )
    map_roughness: _map_property(
        "Roughness",
        "Bakes the material roughness pass for use with a shader's Roughness input.",
    )
    map_emit: _map_property(
        "Emit",
        "Bakes the material emission or glow color for use with a shader's Emission Color input.",
    )
    map_environment: _map_property(
        "Environment",
        "Bakes the scene World shader as seen by rays from the world origin. Use for compositing or a custom environment-lighting workflow.",
    )
    map_diffuse: _map_property(
        "Diffuse",
        "Bakes the diffuse pass. With only Color enabled it is the surface base color; connect it to Principled Base Color. Direct and Indirect add lighting.",
    )
    map_glossy: _map_property(
        "Glossy",
        "Bakes the glossy reflection pass. Use for compositing or a custom shader workflow.",
    )
    map_transmission: _map_property(
        "Transmission",
        "Bakes the transmission or refraction pass. Use for compositing or a custom shader workflow.",
    )
    map_base_color: _map_property(
        "Base Color",
        "Bakes the direct Principled Base Color input. Requires Principled BSDF connected directly to Material Output.",
    )
    map_metallic: _map_property(
        "Metallic",
        "Bakes the Principled Metallic input. Requires Principled BSDF connected directly to Material Output.",
    )
    map_alpha: _map_property(
        "Alpha",
        "Bakes the Principled Alpha input. Requires Principled BSDF connected directly to Material Output.",
    )
    map_smoothness: _map_property(
        "Smoothness",
        "Bakes inverted Principled Roughness (1 - Roughness). Requires Principled BSDF connected directly to Material Output.",
    )
    map_transmission_weight: _map_property(
        "Transmission Weight",
        "Bakes raw Principled Transmission Weight. Requires Principled BSDF connected directly to Material Output.",
    )
    map_specular_ior_level: _map_property(
        "Specular IOR Level",
        "Bakes raw Principled Specular IOR Level; it is not F0 itself. Requires Principled BSDF connected directly to Material Output.",
    )
    map_coat_weight: _map_property(
        "Coat Weight",
        "Bakes raw Principled Coat Weight. Requires Principled BSDF connected directly to Material Output.",
    )
    map_coat_roughness: _map_property(
        "Coat Roughness",
        "Bakes raw Principled Coat Roughness. Requires Principled BSDF connected directly to Material Output.",
    )
    map_sheen_weight: _map_property(
        "Sheen Weight",
        "Bakes raw Principled Sheen Weight. Requires Principled BSDF connected directly to Material Output.",
    )
    map_subsurface_weight: _map_property(
        "Subsurface Weight",
        "Bakes raw Principled Subsurface Weight. Requires Principled BSDF connected directly to Material Output.",
    )
    pack_orm: _map_property(
        "ORM (AO, Roughness, Metallic)",
        "Pack Occlusion (R), Roughness (G), Metallic (B) for Godot and Unreal Engine.",
    )
    pack_gltf: _map_property(
        "glTF Metallic-Roughness",
        "Pack Roughness (G) and Metallic (B) according to the glTF 2.0 standard.",
    )
    pack_unity_mask: _map_property(
        "Unity Mask Map",
        "Pack Metallic (R), AO (G), Detail (B), Smoothness (A) for Unity Lit shaders.",
    )
    pack_base_color_alpha: _map_property(
        "Base Color + Alpha",
        "Pack Base Color (RGB) and Alpha (A) into a single 4-channel image.",
    )
    common_name: StringProperty(name="Common Name", default="", update=_setting_updated)
    output_directory: StringProperty(
        name="Output Directory", subtype="DIR_PATH", default="", update=_setting_updated
    )
    resolution: IntProperty(
        name="Resolution", default=2048, min=4, max=16384, update=_setting_updated
    )
    file_format: EnumProperty(
        name="File Format",
        items=(("PNG", "PNG", ""), ("TARGA", "Targa", ""), ("OPEN_EXR", "OpenEXR", "")),
        default="PNG",
        update=_file_format_updated,
    )
    color_depth: EnumProperty(
        name="Color Depth",
        items=(("8", "8", "8-bit"), ("16", "16", "16-bit"), ("32", "32", "32-bit")),
        default="8",
        update=_setting_updated,
    )
    create_image_texture_nodes: BoolProperty(
        name="Keep Image Texture Nodes After Baking",
        description="Keep baked images available in the material's node editor for later use",
        default=False,
        update=_setting_updated,
    )
    normal_format: EnumProperty(
        name="Normal Map Format",
        items=(
            (
                NORMAL_FORMAT_OPENGL,
                "OpenGL (Y+)",
                "Blender, Unity, and Godot. Tangent space: +X, +Y, +Z.",
            ),
            (
                NORMAL_FORMAT_DIRECTX,
                "DirectX (Y-)",
                "Unreal Engine. Tangent space: +X, -Y, +Z; flips the green channel.",
            ),
            (
                NORMAL_FORMAT_CUSTOM,
                "Custom",
                "Configure Blender's normal space and RGB axes manually.",
            ),
        ),
        default=NORMAL_FORMAT_CUSTOM,
        update=_normal_format_updated,
    )
    direct_lighting: BoolProperty(
        name="Direct Lighting",
        description="Light that reaches the surface without bouncing. When enabled it is included in the bake; when disabled it is excluded. Use Color alone for an unlit base-color map.",
        get=_bake_pass_get("use_pass_direct"),
        set=_bake_pass_set("use_pass_direct"),
    )
    indirect_lighting: BoolProperty(
        name="Indirect Lighting",
        description="Light that reaches the surface after one or more bounces. When enabled it is included in the bake; when disabled it is excluded.",
        get=_bake_pass_get("use_pass_indirect"),
        set=_bake_pass_set("use_pass_indirect"),
    )
    pass_color: BoolProperty(
        name="Color",
        description="The surface shader color without lighting. Color alone bakes the base color. Without Color, direct and indirect lighting are grayscale; with Color, they are baked in color.",
        get=_bake_pass_get("use_pass_color"),
        set=_bake_pass_set("use_pass_color"),
    )


def restore_preferences_to_scene(context) -> SIMPLEBAKER_Settings:
    """Populate a fresh scene's settings from persistent add-on preferences."""
    global _preference_sync_suspended

    settings = context.scene.simple_baker
    if settings.initialized:
        return settings

    preferences = _preferences(context)
    if preferences is not None:
        previous_sync_state = _preference_sync_suspended
        _preference_sync_suspended = True
        try:
            for field in PERSISTED_FIELDS:
                setattr(settings, field, getattr(preferences, field))
        finally:
            _preference_sync_suspended = previous_sync_state

    if not settings.output_directory:
        settings.output_directory = render_output_directory(context.scene)
    if settings.bake_target is None and context.active_object and context.active_object.type == "MESH":
        settings.bake_target = context.active_object
    if not settings.common_name and settings.bake_target:
        settings.common_name = settings.bake_target.name

    context.scene.render.bake.use_selected_to_active = (
        settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE
    )
    apply_normal_map_format(context.scene, settings.normal_format)
    settings.initialized = True
    return settings
