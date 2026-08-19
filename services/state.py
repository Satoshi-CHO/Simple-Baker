"""Context managers for restoring user-visible Blender state after a bake."""

from __future__ import annotations

from contextlib import contextmanager

import bpy

from ..models import SavedContextState


def capture_context_state(context) -> SavedContextState:
    """Capture the selection, active object, mode, and render engine."""
    active = context.view_layer.objects.active
    return SavedContextState(
        render_engine=context.scene.render.engine,
        active_object_name=active.name if active else None,
        selected_object_names=tuple(obj.name for obj in context.selected_objects),
        active_object_mode=active.mode if active else None,
    )


def _object_mode_for_restore(mode: str | None) -> str | None:
    if not mode or mode == "OBJECT":
        return None
    if mode.startswith("EDIT"):
        return "EDIT"
    return mode


def restore_context_state(context, state: SavedContextState) -> None:
    """Best-effort restoration that does not assume all original objects remain."""
    scene = context.scene
    scene.render.engine = state.render_engine

    active = context.view_layer.objects.active
    if active and active.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass

    for obj in context.view_layer.objects:
        obj.select_set(False)
    for name in state.selected_object_names:
        obj = context.view_layer.objects.get(name)
        if obj:
            obj.select_set(True)

    restored_active = (
        context.view_layer.objects.get(state.active_object_name)
        if state.active_object_name
        else None
    )
    context.view_layer.objects.active = restored_active
    mode = _object_mode_for_restore(state.active_object_mode)
    if restored_active and mode:
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            # Mode restoration should never prevent restoration of the engine
            # and selection, for example after an object was deleted mid-run.
            pass


@contextmanager
def temporary_cycles_engine(scene):
    """Temporarily switch to Cycles and always restore the original engine."""
    previous_engine = scene.render.engine
    try:
        scene.render.engine = "CYCLES"
        yield
    finally:
        scene.render.engine = previous_engine


@contextmanager
def temporary_bake_type(bake_settings, bake_type: str):
    """Temporarily set an RNA bake type when the Blender build exposes one.

    Blender 5.1 selects the bake type through ``bpy.ops.object.bake(type=...)``
    and no longer exposes ``BakeSettings.bake_type``. Older builds may still
    provide the RNA property, so keep the context manager compatible with both.
    """
    if not hasattr(bake_settings, "bake_type"):
        yield
        return

    previous_type = bake_settings.bake_type
    try:
        bake_settings.bake_type = bake_type
        yield
    finally:
        bake_settings.bake_type = previous_type


def _image_format_snapshot(image_settings) -> dict[str, str]:
    return {
        attribute: getattr(image_settings, attribute)
        for attribute in ("file_format", "color_depth", "color_mode")
        if hasattr(image_settings, attribute)
    }


def _restore_image_format(image_settings, snapshot: dict[str, str]) -> None:
    for attribute, value in snapshot.items():
        setattr(image_settings, attribute, value)


@contextmanager
def temporary_image_settings(scene, file_format: str, color_depth: str):
    """Configure external image saving without persisting scene format changes."""
    settings_to_restore = [scene.render.image_settings]
    bake_image_settings = getattr(scene.render.bake, "image_settings", None)
    if bake_image_settings is not None:
        settings_to_restore.append(bake_image_settings)
    snapshots = [(settings, _image_format_snapshot(settings)) for settings in settings_to_restore]
    try:
        for image_settings, _snapshot in snapshots:
            image_settings.file_format = file_format
            image_settings.color_depth = color_depth
        yield
    finally:
        for image_settings, snapshot in snapshots:
            _restore_image_format(image_settings, snapshot)
