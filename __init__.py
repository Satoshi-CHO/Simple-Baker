"""Simple Baker Blender add-on entry point."""

from __future__ import annotations

import bpy
from bpy.app.handlers import persistent
from bpy.props import PointerProperty

from .i18n import register_translations, unregister_translations
from .operators import (
    SIMPLEBAKER_OT_add_source_object,
    SIMPLEBAKER_OT_bake_and_save,
    SIMPLEBAKER_OT_remove_source_object,
)
from .preferences import SIMPLEBAKER_Preferences
from .properties import SIMPLEBAKER_Settings, SIMPLEBAKER_SourceObject, restore_preferences_to_scene
from .ui import SIMPLEBAKER_PT_bake

CLASSES = (
    SIMPLEBAKER_Preferences,
    SIMPLEBAKER_SourceObject,
    SIMPLEBAKER_Settings,
    SIMPLEBAKER_OT_add_source_object,
    SIMPLEBAKER_OT_remove_source_object,
    SIMPLEBAKER_OT_bake_and_save,
    SIMPLEBAKER_PT_bake,
)


def _initialize_current_scene() -> bool:
    """Initialize a scene when Blender has made a full context available."""
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return False
    restore_preferences_to_scene(bpy.context)
    return True


def _initialize_when_context_ready() -> float | None:
    """Defer initialization during add-on enable, when context can be restricted."""
    if not hasattr(bpy.types.Scene, "simple_baker"):
        return None
    return None if _initialize_current_scene() else 0.1


@persistent
def _on_load_post(_unused) -> None:
    """Restore the persisted add-on values for a newly loaded .blend file."""
    _initialize_current_scene()


def register() -> None:
    """Register the add-on and its scene-level settings."""
    registered_classes = []
    translations_registered = False
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered_classes.append(cls)
        bpy.types.Scene.simple_baker = PointerProperty(type=SIMPLEBAKER_Settings)
        register_translations()
        translations_registered = True
        if _on_load_post not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(_on_load_post)
        if not _initialize_current_scene():
            bpy.app.timers.register(_initialize_when_context_ready, first_interval=0.0)
    except Exception:
        if _on_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_on_load_post)
        if hasattr(bpy.types.Scene, "simple_baker"):
            del bpy.types.Scene.simple_baker
        if translations_registered:
            unregister_translations()
        for cls in reversed(registered_classes):
            bpy.utils.unregister_class(cls)
        raise


def unregister() -> None:
    """Unregister Simple Baker classes in reverse registration order."""
    if bpy.app.timers.is_registered(_initialize_when_context_ready):
        bpy.app.timers.unregister(_initialize_when_context_ready)
    unregister_translations()
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if hasattr(bpy.types.Scene, "simple_baker"):
        del bpy.types.Scene.simple_baker
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
