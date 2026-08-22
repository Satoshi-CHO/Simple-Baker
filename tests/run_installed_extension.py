"""Smoke-test an installed Blender Extension across two Blender processes.

Usage:
    blender --background --python tests/run_installed_extension.py -- save
    blender --background --python tests/run_installed_extension.py -- check
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

import bpy


EXPECTED = {
    "common_name": "simple_baker_extension_smoke",
    "output_directory": tempfile.gettempdir(),
    "resolution": 32,
    "file_format": "PNG",
    "color_depth": "8",
    "create_image_texture_nodes": True,
    "normal_format": "OPENGL",
}


def _extension_id() -> str:
    matches = [
        module_name
        for module_name in bpy.context.preferences.addons.keys()
        if module_name.startswith("bl_ext.") and module_name.endswith(".simple_baker")
    ]
    assert len(matches) == 1, matches
    return matches[0]


def _assert_extension_identity() -> str:
    extension_id = _extension_id()
    package = importlib.import_module(extension_id)
    constants = importlib.import_module(f"{extension_id}.constants")
    assert package.__package__ == extension_id
    assert constants.ADDON_ID == extension_id
    preferences = bpy.context.preferences.addons[extension_id].preferences
    assert type(preferences).bl_idname == extension_id
    return extension_id


def _create_target():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    target = bpy.context.active_object
    material = bpy.data.materials.new("simple_baker_extension_material")
    target.data.materials.append(material)
    return target


def _save_preferences_and_bake() -> None:
    extension_id = _assert_extension_identity()
    settings = bpy.context.scene.simple_baker
    target = _create_target()
    settings.bake_target = target
    settings.workflow = "SELF"
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.map_diffuse = True
    for field, value in EXPECTED.items():
        setattr(settings, field, value)

    result = bpy.ops.simple_baker.bake_and_save(confirmed_overwrite=True)
    assert "FINISHED" in result, result
    output = Path(EXPECTED["output_directory"]) / "simple_baker_extension_smoke_color.png"
    assert output.is_file(), output

    preferences = bpy.context.preferences.addons[extension_id].preferences
    for field, value in EXPECTED.items():
        assert getattr(preferences, field) == value, field
    bpy.ops.wm.save_userpref()
    print("Simple Baker installed Extension save test passed")


def _check_preferences_after_restart() -> None:
    extension_id = _assert_extension_identity()
    preferences = bpy.context.preferences.addons[extension_id].preferences
    settings = bpy.context.scene.simple_baker
    for field, value in EXPECTED.items():
        assert getattr(preferences, field) == value, field
        assert getattr(settings, field) == value, field
    print("Simple Baker installed Extension restart test passed")


def main() -> None:
    separator = sys.argv.index("--") if "--" in sys.argv else -1
    mode = sys.argv[separator + 1] if separator >= 0 and separator + 1 < len(sys.argv) else ""
    if mode == "save":
        _save_preferences_and_bake()
    elif mode == "check":
        _check_preferences_after_restart()
    else:
        raise ValueError("Expected test mode 'save' or 'check' after --")


if __name__ == "__main__":
    main()
