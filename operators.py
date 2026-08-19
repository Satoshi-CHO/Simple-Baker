"""Operators for Simple Baker."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, IntProperty
from bpy.types import Operator

from .services.bake import run_bake_jobs
from .services.images import build_image_specs
from .services.paths import find_existing_outputs
from .services.validation import validate_bake_request
from .properties import restore_preferences_to_scene


def _translated(message_id: str) -> str:
    return bpy.app.translations.pgettext(message_id)


class SIMPLEBAKER_OT_add_source_object(Operator):
    """Add an empty source-object slot for explicit object selection."""

    bl_idname = "simple_baker.add_source_object"
    bl_label = "Add Source Model"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        restore_preferences_to_scene(context).source_objects.add()
        return {"FINISHED"}


class SIMPLEBAKER_OT_remove_source_object(Operator):
    """Remove one source-object slot."""

    bl_idname = "simple_baker.remove_source_object"
    bl_label = "Remove Source Model"
    bl_options = {"INTERNAL"}

    index: IntProperty(min=0, options={"HIDDEN"})

    def execute(self, context):
        sources = restore_preferences_to_scene(context).source_objects
        if self.index < len(sources):
            sources.remove(self.index)
        return {"FINISHED"}


class SIMPLEBAKER_OT_bake_and_save(Operator):
    """Validate, confirm replacement, then run native Cycles bake jobs."""

    bl_idname = "simple_baker.bake_and_save"
    bl_label = "Bake & Save"
    bl_description = "Bake selected maps and save them to disk"
    # Node, material, and image data-block changes should participate in
    # Blender's undo history.  Files already written to disk remain outside
    # Blender's undo system and are protected by the overwrite confirmation.
    bl_options = {"REGISTER", "UNDO"}

    confirmed_overwrite: BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    def _report_issues(self, context) -> bool:
        settings = restore_preferences_to_scene(context)
        issues = validate_bake_request(context, settings)
        for issue in issues:
            self.report({"ERROR"}, _translated(issue.message_id).format(**issue.values))
        return bool(issues)

    def invoke(self, context, event):
        if self._report_issues(context):
            return {"CANCELLED"}

        settings = restore_preferences_to_scene(context)
        existing_paths = find_existing_outputs(build_image_specs(settings))
        if not existing_paths:
            self.confirmed_overwrite = True
            return self.execute(context)

        self._existing_paths = existing_paths
        # Reaching this dialog is the overwrite confirmation. Cancelling the
        # dialog does not call execute, so no output is changed.
        self.confirmed_overwrite = True
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context) -> None:
        layout = self.layout
        layout.label(text="The following files already exist and will be overwritten:", icon="ERROR")
        for path in getattr(self, "_existing_paths", []):
            layout.label(text=path, icon="FILE_IMAGE")

    def execute(self, context):
        if self._report_issues(context):
            return {"CANCELLED"}

        settings = restore_preferences_to_scene(context)
        existing_paths = find_existing_outputs(build_image_specs(settings))
        if existing_paths and not self.confirmed_overwrite:
            self.report(
                {"ERROR"},
                _translated("Existing output files require confirmation. Use Bake & Save from the panel."),
            )
            return {"CANCELLED"}

        result = run_bake_jobs(context, settings)
        for failure in result.failures:
            self.report(
                {"ERROR"},
                f"{failure.image_spec.map_spec.label}: {failure.reason}",
            )
        if result.saved_paths:
            self.report(
                {"INFO"},
                _translated("Saved {count} map(s).").format(count=len(result.saved_paths)),
            )
        if not result.saved_paths:
            self.report({"ERROR"}, _translated("No maps were baked successfully."))
            return {"CANCELLED"}
        if result.failures:
            self.report(
                {"WARNING"},
                _translated("{count} map(s) failed; successful maps were saved.").format(
                    count=len(result.failures)
                ),
            )
        skipped_connections = [item for item in result.connection_results if not item.connected]
        if skipped_connections:
            self.report(
                {"WARNING"},
                _translated("Kept {count} existing material input connection(s) unchanged.").format(
                    count=len(skipped_connections)
                ),
            )
        return {"FINISHED"}
