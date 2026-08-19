"""Render Properties UI for Simple Baker."""

from __future__ import annotations

from bpy.types import Panel

from .constants import (
    NORMAL_FORMAT_CUSTOM,
    NORMAL_FORMAT_DIRECTX,
    NORMAL_FORMAT_OPENGL,
)
from .operators import (
    SIMPLEBAKER_OT_add_source_object,
    SIMPLEBAKER_OT_bake_and_save,
    SIMPLEBAKER_OT_remove_source_object,
)
from .services.pure import supported_color_depths


class SIMPLEBAKER_PT_bake(Panel):
    """A sequential UI for configuring Blender's native Cycles bake system."""

    bl_idname = "SIMPLEBAKER_PT_bake"
    bl_label = "Simple Baker"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context) -> None:
        layout = self.layout
        # Blender forbids writes to ID data-blocks while a panel is drawing.
        # Scene settings are initialized during add-on registration/load and
        # immediately before execution; drawing must remain read-only.
        settings = context.scene.simple_baker
        bake = context.scene.render.bake

        source = layout.box()
        source.label(text="Bake Objects")
        source.prop(settings, "workflow", expand=True)
        if settings.workflow == "SELF":
            source.prop(settings, "bake_target", text="Model to Bake")
        else:
            source.label(text="Source Models")
            for index, source_object in enumerate(settings.source_objects):
                row = source.row(align=True)
                row.prop(source_object, "object", text="")
                remove = row.operator(
                    SIMPLEBAKER_OT_remove_source_object.bl_idname,
                    text="",
                    icon="X",
                )
                remove.index = index
            source.operator(SIMPLEBAKER_OT_add_source_object.bl_idname, icon="ADD")
            source.prop(settings, "bake_target", text="Bake Target")

        maps = layout.box()
        maps.label(text="Output Maps")
        grid = maps.grid_flow(columns=2, even_columns=True, even_rows=False)
        for property_name in (
            "map_combined",
            "map_ao",
            "map_shadow",
            "map_normal",
            "map_uv",
            "map_roughness",
            "map_emit",
            "map_environment",
            "map_diffuse",
            "map_glossy",
            "map_transmission",
        ):
            grid.prop(settings, property_name)

        output = layout.box()
        output.label(text="Output Images & Targets")
        output.prop(settings, "common_name")
        output.prop(settings, "output_directory")
        output.prop(settings, "resolution")
        row = output.row(align=True)
        row.prop(settings, "file_format")
        for color_depth in supported_color_depths(settings.file_format):
            row.prop_enum(settings, "color_depth", color_depth)
        output.prop(settings, "create_image_texture_nodes")
        if settings.create_image_texture_nodes:
            output.prop(settings, "connection_mode")
        else:
            output.label(text="Baked images are saved, but no Image Texture nodes are kept.", icon="INFO")

        standard = layout.box()
        standard.label(text="Bake Settings")
        standard.prop(bake, "margin")
        if hasattr(bake, "margin_type"):
            standard.prop(bake, "margin_type")
        standard.prop(bake, "use_clear")
        if settings.workflow == "SELECTED_TO_ACTIVE":
            standard.prop(bake, "use_cage")
            if bake.use_cage:
                standard.prop(bake, "cage_object")
            standard.prop(bake, "cage_extrusion")
            standard.prop(bake, "max_ray_distance")

        if settings.map_normal:
            normal = standard.column(align=True)
            normal.label(text="Normal")
            format_row = normal.row(align=True)
            format_row.prop_enum(settings, "normal_format", NORMAL_FORMAT_OPENGL)
            format_row.prop_enum(settings, "normal_format", NORMAL_FORMAT_DIRECTX)
            format_row.prop_enum(settings, "normal_format", NORMAL_FORMAT_CUSTOM)
            if settings.normal_format == NORMAL_FORMAT_CUSTOM:
                normal.prop(bake, "normal_space")
                normal.prop(bake, "normal_r")
                normal.prop(bake, "normal_g")
                normal.prop(bake, "normal_b")

        if settings.map_combined:
            combined = standard.column(align=True)
            combined.label(text="Combined Contributions")
            combined.prop(bake, "use_pass_direct")
            combined.prop(bake, "use_pass_indirect")
            combined.prop(bake, "use_pass_diffuse")
            combined.prop(bake, "use_pass_glossy")
            combined.prop(bake, "use_pass_transmission")
            combined.prop(bake, "use_pass_emit")
            combined.prop(bake, "use_pass_ambient_occlusion")

        if settings.map_diffuse or settings.map_glossy or settings.map_transmission:
            contributions = standard.column(align=True)
            contributions.label(text="Surface Contributions")
            contributions.prop(settings, "direct_lighting")
            contributions.prop(settings, "indirect_lighting")
            contributions.prop(settings, "pass_color")

        action = layout.box()
        action.label(text="Bake & Save")
        action.label(text="Undo does not restore overwritten output files.", icon="INFO")
        action.label(text="Choose the models above, then run Bake & Save.", icon="INFO")
        action.operator(SIMPLEBAKER_OT_bake_and_save.bl_idname, icon="RENDER_STILL")
