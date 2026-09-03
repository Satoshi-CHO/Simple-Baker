"""Render Properties UI for Simple Baker."""

from __future__ import annotations

import bpy
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
from .services.images import build_image_specs
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
        maps.prop(settings, "output_map_tab", expand=True)
        if settings.output_map_tab == "PBR":
            maps.prop(settings, "pbr_output_section", expand=True)
            if settings.pbr_output_section == "INDIVIDUAL":
                maps.label(text="Standard PBR Maps")
                grid = maps.grid_flow(columns=2, even_columns=True, even_rows=False)
                map_properties = (
                    ("map_base_color", None),
                    ("map_metallic", None),
                    ("map_roughness", None),
                    ("map_smoothness", None),
                    ("map_normal", None),
                    ("map_ao", None),
                    ("map_alpha", None),
                    ("map_emit", "Emission"),
                )
                for property_name, label in map_properties:
                    if label is None:
                        grid.prop(settings, property_name)
                    else:
                        grid.prop(settings, property_name, text=label)

                maps.prop(settings, "show_advanced_pbr_inputs")
                if settings.show_advanced_pbr_inputs:
                    adv_grid = maps.grid_flow(columns=2, even_columns=True, even_rows=False)
                    adv_properties = (
                        "map_transmission_weight",
                        "map_specular_ior_level",
                        "map_coat_weight",
                        "map_coat_roughness",
                        "map_sheen_weight",
                        "map_subsurface_weight",
                    )
                    for property_name in adv_properties:
                        adv_grid.prop(settings, property_name)
            else:
                pack_col = maps.column(align=True)
                for prop_name, channels_text in (
                    ("pack_orm", "R: AO | G: Roughness | B: Metallic | A: 1.0"),
                    ("pack_gltf", "R: 1.0 | G: Roughness | B: Metallic | A: 1.0"),
                    ("pack_unity_mask", "R: Metallic | G: AO | B: 0.0 | A: Smoothness"),
                    ("pack_base_color_alpha", "RGB: Base Color | A: Alpha"),
                ):
                    item_box = pack_col.box()
                    item_box.prop(settings, prop_name)
                    sub_row = item_box.row()
                    sub_row.alignment = "LEFT"
                    sub_row.label(
                        text=f"  ↳ {bpy.app.translations.pgettext_iface(channels_text)}",
                        icon="TEXTURE",
                    )
        else:
            grid = maps.grid_flow(columns=2, even_columns=True, even_rows=False)
            map_properties = (
                ("map_combined", None),
                ("map_ao", None),
                ("map_shadow", None),
                ("map_normal", None),
                ("map_uv", None),
                ("map_roughness", None),
                ("map_emit", None),
                ("map_environment", None),
                ("map_diffuse", None),
                ("map_glossy", None),
                ("map_transmission", None),
            )
            for property_name, label in map_properties:
                if label is None:
                    grid.prop(settings, property_name)
                else:
                    grid.prop(settings, property_name, text=label)
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
        if not settings.create_image_texture_nodes:
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
        selected_specs = build_image_specs(settings)
        action.label(
            text=bpy.app.translations.pgettext_iface("Selected Maps: {count}").format(
                count=len(selected_specs)
            )
        )
        if selected_specs:
            selected_labels = [
                bpy.app.translations.pgettext_iface(
                    "Emission" if spec.map_spec.key == "emit" else spec.map_spec.label
                )
                for spec in selected_specs
            ]
            for index in range(0, len(selected_labels), 4):
                action.label(
                    text=", ".join(selected_labels[index : index + 4]),
                    icon="CHECKMARK" if index == 0 else "BLANK1",
                )
        else:
            action.label(text="No maps selected.", icon="INFO")
        action.label(text="Undo does not restore overwritten output files.", icon="INFO")
        action.label(text="Choose the models above, then run Bake & Save.", icon="INFO")
        action.operator(SIMPLEBAKER_OT_bake_and_save.bl_idname, icon="RENDER_STILL")
