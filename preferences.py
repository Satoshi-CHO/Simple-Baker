"""Persistent Blender preferences for Simple Baker."""

from __future__ import annotations

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences

from .constants import (
    ADDON_ID,
    CONNECTION_MATERIAL,
    CONNECTION_NODES_ONLY,
    NORMAL_FORMAT_CUSTOM,
    NORMAL_FORMAT_DIRECTX,
    NORMAL_FORMAT_OPENGL,
    WORKFLOW_SELF,
    WORKFLOW_SELECTED_TO_ACTIVE,
)


def _map_property(name: str) -> BoolProperty:
    return BoolProperty(name=name, default=False)


class SIMPLEBAKER_Preferences(AddonPreferences):
    """Values restored into a scene when Simple Baker is first opened."""

    bl_idname = ADDON_ID

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
    )
    map_combined: _map_property("Combined")
    map_ao: _map_property("Ambient Occlusion")
    map_shadow: _map_property("Shadow")
    map_normal: _map_property("Normal")
    map_uv: _map_property("UV")
    map_roughness: _map_property("Roughness")
    map_emit: _map_property("Emit")
    map_environment: _map_property("Environment")
    map_diffuse: _map_property("Diffuse")
    map_glossy: _map_property("Glossy")
    map_transmission: _map_property("Transmission")
    common_name: StringProperty(name="Common Name", default="")
    output_directory: StringProperty(name="Output Directory", subtype="DIR_PATH", default="")
    resolution: IntProperty(name="Resolution", default=2048, min=4, max=16384)
    file_format: EnumProperty(
        name="File Format",
        items=(("PNG", "PNG", ""), ("TARGA", "Targa", ""), ("OPEN_EXR", "OpenEXR", "")),
        default="PNG",
    )
    color_depth: EnumProperty(
        name="Color Depth",
        items=(("8", "8", "8-bit"), ("16", "16", "16-bit"), ("32", "32", "32-bit")),
        default="8",
    )
    connection_mode: EnumProperty(
        name="Node Usage",
        description="Choose whether baked results are automatically applied to the material",
        items=(
            (
                CONNECTION_NODES_ONLY,
                "Place Nodes Only",
                "Add baked images to the material's node editor without changing its appearance.",
            ),
            (
                CONNECTION_MATERIAL,
                "Place Nodes and Connect to Material",
                "Automatically apply supported baked results to the material. Existing settings are kept.",
            ),
        ),
        default=CONNECTION_NODES_ONLY,
    )
    create_image_texture_nodes: BoolProperty(
        name="Keep Image Texture Nodes After Baking",
        description="Keep baked images available in the material's node editor for later use",
        default=False,
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
    )

    def draw(self, context) -> None:
        layout = self.layout
        layout.label(text="Simple Baker restores its most recently used bake settings.")
        layout.label(text="Configure the current scene from Render Properties > Simple Baker.")
