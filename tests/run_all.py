"""Blender-runtime smoke and self-bake test.

Run with: blender --background --python tests/run_all.py
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import simple_baker
from simple_baker.constants import ADDON_ID
from simple_baker.services.bake import BakeProgress
from simple_baker.services.images import build_image_specs
from simple_baker.properties import render_output_directory


def _create_bake_target() -> bpy.types.Object:
    """Create a UV-mapped plane with a Principled material for a fast bake."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    target = bpy.context.active_object
    target.name = "simple_baker_smoke_target"

    material = bpy.data.materials.new("simple_baker_smoke_material")
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.2, 0.6, 0.9, 1.0)
    target.data.materials.append(material)
    settings = bpy.context.scene.simple_baker
    settings.bake_target = target
    settings.source_objects.clear()
    return target


def _managed_image_nodes(material):
    return [
        node
        for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeTexImage" and node.get("simple_baker_managed")
    ]


def _managed_image_pointers():
    return {
        image.as_pointer()
        for image in bpy.data.images
        if image.get("simple_baker_managed")
    }


def _assert_rejected_bake_has_no_side_effects(target, expected_output: Path | None = None) -> None:
    """Rejected preflight requests must not create images or material nodes."""
    material = target.active_material
    before_images = _managed_image_pointers()
    before_nodes = list(material.node_tree.nodes) if material else []
    try:
        result = bpy.ops.simple_baker.bake_and_save()
    except RuntimeError:
        # In background mode Blender raises ERROR reports instead of returning
        # CANCELLED.  The assertions below verify the important contract: no
        # side effects were created before the rejection.
        pass
    else:
        assert "CANCELLED" in result, result
    assert _managed_image_pointers() == before_images
    if material:
        assert list(material.node_tree.nodes) == before_nodes
    if expected_output is not None:
        assert not expected_output.exists()


class _RecordingWindowManager:
    def __init__(self):
        self.calls = []

    def progress_begin(self, minimum, maximum):
        self.calls.append(("begin", minimum, maximum))

    def progress_update(self, value):
        self.calls.append(("update", value))

    def progress_end(self):
        self.calls.append(("end",))


class _RecordingWorkspace:
    def __init__(self):
        self.messages = []

    def status_text_set(self, text=None):
        self.messages.append(text)


class _FailingProgressUpdateWindowManager(_RecordingWindowManager):
    def progress_update(self, value):
        raise RuntimeError("Simulated progress UI failure")


def _run_progress_reporting_test() -> None:
    """Progress updates must be visible and must always be closed."""
    context = type("ProgressContext", (), {})()
    context.window_manager = _RecordingWindowManager()
    context.workspace = _RecordingWorkspace()
    progress = BakeProgress(context, 2)
    progress.start()
    progress.begin_map(0, "Ambient Occlusion")
    progress.begin_map(1, "Diffuse")
    progress.close()

    assert context.window_manager.calls == [
        ("begin", 0, 2),
        ("update", 0),
        ("update", 1),
        ("update", 2),
        ("end",),
    ]
    assert context.workspace.messages == [
        "Simple Baker: Preparing 2 map(s)",
        "Simple Baker: Baking Ambient Occlusion (1/2)",
        "Simple Baker: Baking Diffuse (2/2)",
        None,
    ]

    failure_context = type("ProgressContext", (), {})()
    failure_context.window_manager = _FailingProgressUpdateWindowManager()
    failure_context.workspace = _RecordingWorkspace()
    failing_progress = BakeProgress(failure_context, 1)
    failing_progress.start()
    failing_progress.close()
    assert failure_context.window_manager.calls == [("begin", 0, 1), ("end",)]
    assert failure_context.workspace.messages[-1] is None


def _run_preference_restore_without_feedback_test() -> None:
    """Restoring scene settings must not overwrite saved add-on preferences."""
    from simple_baker import properties as properties_module
    from simple_baker.constants import PERSISTED_FIELDS

    settings = bpy.context.scene.simple_baker
    preferences = type("SavedPreferences", (), {})()
    for field in PERSISTED_FIELDS:
        setattr(preferences, field, getattr(settings, field))

    expected = {
        "map_ao": True,
        "map_normal": True,
        "common_name": "PERSIST_TEST",
        "output_directory": "/tmp/simple_baker_preference_restore",
        "resolution": 512,
        "file_format": "OPEN_EXR",
        "color_depth": "32",
        "create_image_texture_nodes": True,
        "normal_format": "OPENGL",
    }
    for field, value in expected.items():
        setattr(preferences, field, value)

    original_preferences = properties_module._preferences
    properties_module._preferences = lambda _context: preferences
    settings.initialized = False
    try:
        properties_module.restore_preferences_to_scene(bpy.context)
        for field, value in expected.items():
            assert getattr(settings, field) == value, field
            assert getattr(preferences, field) == value, field

        settings.resolution = 1024
        assert preferences.resolution == 1024
    finally:
        properties_module._preferences = original_preferences

    print("Simple Baker preference restore feedback test passed")


def _run_render_output_directory_test() -> None:
    """The initial bake folder must follow Blender's render output folder."""
    scene = bpy.context.scene
    original_path = scene.render.filepath
    render_directory = Path(tempfile.mkdtemp(prefix="simple_baker_render_"))
    try:
        scene.render.filepath = f"{render_directory}/"
        assert Path(render_output_directory(scene)) == render_directory
        scene.render.filepath = str(render_directory / "render_")
        assert Path(render_output_directory(scene)) == render_directory
    finally:
        scene.render.filepath = original_path
    print("Simple Baker render output directory test passed")


def _run_self_bake() -> None:
    target = _create_bake_target()
    scene = bpy.context.scene
    initial_engine = "BLENDER_EEVEE"
    scene.render.engine = initial_engine

    settings = scene.simple_baker
    settings.initialized = True
    settings.bake_target = target
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_smoke"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = True

    bake = scene.render.bake
    bake.margin = 2
    bake.use_pass_color = True
    bake.use_pass_direct = False
    bake.use_pass_indirect = False

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    output_path = Path(settings.output_directory) / "simple_baker_smoke_color.png"
    assert output_path.is_file(), output_path
    assert scene.render.engine == initial_engine
    assert bpy.context.active_object == target

    material = target.active_material
    managed_nodes = _managed_image_nodes(material)
    assert len(managed_nodes) == 1
    assert managed_nodes[0].image is not None
    print("Simple Baker self-bake test passed")


def _run_preflight_rejection_tests() -> None:
    """Invalid requests must stop before creating any Blender or disk data."""
    scene = bpy.context.scene
    output_directory = Path(tempfile.mkdtemp(prefix="simple_baker_"))

    mesh = bpy.data.meshes.new("simple_baker_no_uv_mesh")
    mesh.from_pydata(((0, 0, 0), (1, 0, 0), (0, 1, 0)), (), ((0, 1, 2),))
    target = bpy.data.objects.new("simple_baker_no_uv_target", mesh)
    bpy.context.collection.objects.link(target)
    material = bpy.data.materials.new("simple_baker_no_uv_material")
    target.data.materials.append(material)
    bpy.context.view_layer.objects.active = target
    target.select_set(True)

    settings = scene.simple_baker
    settings.bake_target = target
    settings.source_objects.clear()
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_no_uv"
    settings.output_directory = str(output_directory)
    settings.map_diffuse = True
    _assert_rejected_bake_has_no_side_effects(
        target, output_directory / "simple_baker_no_uv_color.png"
    )

    target = _create_bake_target()
    settings.common_name = "simple_baker_no_output_directory"
    settings.output_directory = ""
    _assert_rejected_bake_has_no_side_effects(target)

    settings.common_name = "simple_baker_invalid_output_directory"
    invalid_directory = output_directory / "does_not_exist"
    settings.output_directory = str(invalid_directory)
    _assert_rejected_bake_has_no_side_effects(
        target, invalid_directory / "simple_baker_invalid_output_directory_color.png"
    )

    settings.workflow = "SELECTED_TO_ACTIVE"
    settings.output_directory = str(output_directory)
    settings.common_name = "simple_baker_missing_source"
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    _assert_rejected_bake_has_no_side_effects(
        target, output_directory / "simple_baker_missing_source_color.png"
    )
    print("Simple Baker preflight rejection tests passed")


def _run_selected_to_active_bake() -> None:
    """Bake a selected source mesh to the active target and restore selection."""
    target = _create_bake_target()
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0.0, 0.0, 0.1))
    source = bpy.context.active_object
    source.name = "simple_baker_smoke_source"
    source_material = bpy.data.materials.new("simple_baker_smoke_source_material")
    source_material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        0.9,
        0.3,
        0.1,
        1.0,
    )
    source.data.materials.append(source_material)

    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELECTED_TO_ACTIVE"
    settings.bake_target = target
    settings.source_objects.clear()
    source_entry = settings.source_objects.add()
    source_entry.object = source
    settings.common_name = "simple_baker_selected_to_active"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = False
    scene.render.bake.max_ray_distance = 0.2

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    assert (Path(settings.output_directory) / "simple_baker_selected_to_active_color.png").is_file()
    assert bpy.context.active_object == target
    assert set(bpy.context.selected_objects) == {source, target}
    print("Simple Baker selected-to-active bake test passed")


def _run_multiple_material_bake() -> None:
    """Every material slot on the target must receive the retained bake target."""
    target = _create_bake_target()
    scene = bpy.context.scene
    second_material = bpy.data.materials.new("simple_baker_second_material")
    target.data.materials.append(second_material)
    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_multiple_materials"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = True

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    image_nodes = []
    for material in (target.active_material, second_material):
        nodes = _managed_image_nodes(material)
        assert len(nodes) == 1
        image_nodes.append(nodes[0])
    assert image_nodes[0].image == image_nodes[1].image
    print("Simple Baker multiple-material bake test passed")


def _run_all_map_bake() -> None:
    """Every advertised Cycles bake map must save successfully in one run."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_all_maps"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.create_image_texture_nodes = False
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, True)

    image_specs = build_image_specs(settings)
    assert len(image_specs) == 11
    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    assert all(Path(image_spec.output_path).is_file() for image_spec in image_specs)
    assert bpy.context.active_object == target
    print("Simple Baker all-map bake test passed")


def _run_temporary_target_bake() -> None:
    """The default workflow must remove its temporary Image Texture target."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_temporary_target"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = False

    material = target.active_material
    user_image = bpy.data.images.new("temporary_target_user_image", 8, 8)
    user_node = material.node_tree.nodes.new("ShaderNodeTexImage")
    user_node.image = user_image
    material.node_tree.nodes.active = user_node

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    assert (Path(settings.output_directory) / "simple_baker_temporary_target_color.png").is_file()
    assert material.node_tree.nodes.active == user_node
    assert [node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeTexImage"] == [user_node]
    print("Simple Baker temporary bake target test passed")


def _run_existing_link_and_overwrite_test() -> None:
    """Existing shader links and output files require explicit user confirmation."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_existing_link"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = True

    material = target.active_material
    principled = material.node_tree.nodes["Principled BSDF"]
    user_color = material.node_tree.nodes.new("ShaderNodeRGB")
    material.node_tree.links.new(user_color.outputs["Color"], principled.inputs["Base Color"])
    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    assert principled.inputs["Base Color"].links[0].from_node == user_color
    output_path = Path(settings.output_directory) / "simple_baker_existing_link_color.png"
    original_bytes = output_path.read_bytes()
    original_image = _managed_image_nodes(material)[0].image

    try:
        bpy.ops.simple_baker.bake_and_save()
    except RuntimeError as error:
        assert "require confirmation" in str(error).lower()
    else:
        raise AssertionError("Existing output was allowed without confirmation")

    assert output_path.read_bytes() == original_bytes
    assert _managed_image_nodes(material)[0].image == original_image
    assert principled.inputs["Base Color"].links[0].from_node == user_color

    result = bpy.ops.simple_baker.bake_and_save(confirmed_overwrite=True)
    assert "FINISHED" in result, result
    assert principled.inputs["Base Color"].links[0].from_node == user_color
    assert len(_managed_image_nodes(material)) == 1
    print("Simple Baker existing link and overwrite test passed")


def _run_failed_save_rollback_test() -> None:
    """A post-bake save failure must restore the previous retained image target."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_failed_save"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.create_image_texture_nodes = True

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    material = target.active_material
    image_node = _managed_image_nodes(material)[0]
    previous_image = image_node.image
    image_spec = build_image_specs(settings)[0]

    from simple_baker.services import bake as bake_service

    @contextmanager
    def failing_image_settings(*_args, **_kwargs):
        raise RuntimeError("Simulated save failure")
        yield

    original_image_settings = bake_service.temporary_image_settings
    bake_service.temporary_image_settings = failing_image_settings
    original_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    try:
        try:
            bake_service._bake_and_save_one(
                bpy.context,
                target,
                (target,),
                image_spec,
                keep_image_nodes=True,
            )
            raise AssertionError("Expected simulated save failure")
        except RuntimeError as error:
            assert str(error) == "Simulated save failure"
    finally:
        scene.render.engine = original_engine
        bake_service.temporary_image_settings = original_image_settings

    assert image_node.image == previous_image
    assert len(_managed_image_nodes(material)) == 1
    replacement_images = [
        image
        for image in bpy.data.images
        if image.get("simple_baker_image_key") == image_spec.output_path
    ]
    assert replacement_images == [previous_image]
    print("Simple Baker failed-save rollback test passed")


def _run_normal_format_test() -> None:
    """Preset selection must set the Blender tangent-space bake axes."""
    scene = bpy.context.scene
    settings = scene.simple_baker
    settings.normal_format = "DIRECTX"
    bake = scene.render.bake
    assert bake.normal_space == "TANGENT"
    assert bake.normal_r == "POS_X"
    assert bake.normal_g == "NEG_Y"
    assert bake.normal_b == "POS_Z"

    settings.normal_format = "OPENGL"
    assert bake.normal_space == "TANGENT"
    assert bake.normal_r == "POS_X"
    assert bake.normal_g == "POS_Y"
    assert bake.normal_b == "POS_Z"

    bake.normal_space = "OBJECT"
    bake.normal_r = "NEG_X"
    bake.normal_g = "NEG_Y"
    bake.normal_b = "NEG_Z"
    settings.normal_format = "CUSTOM"
    assert bake.normal_space == "OBJECT"
    assert bake.normal_r == "NEG_X"
    assert bake.normal_g == "NEG_Y"
    assert bake.normal_b == "NEG_Z"
    print("Simple Baker normal format preset test passed")


def _run_output_format_test() -> None:
    """Changing output formats must never leave an invalid color depth selected."""
    settings = bpy.context.scene.simple_baker
    settings.file_format = "PNG"
    settings.color_depth = "16"
    settings.file_format = "TARGA"
    assert settings.color_depth == "8"
    settings.file_format = "OPEN_EXR"
    assert settings.color_depth == "16"
    settings.color_depth = "32"
    settings.file_format = "PNG"
    assert settings.color_depth == "8"
    print("Simple Baker output format compatibility test passed")


def _run_output_format_save_test() -> None:
    """Every exposed valid format/depth pair must produce an output file."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    for property_name in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission",
    ):
        setattr(settings, property_name, False)
    settings.workflow = "SELF"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.map_diffuse = True
    settings.create_image_texture_nodes = False

    formats = (
        ("PNG", "16", "png"),
        ("TARGA", "8", "tga"),
        ("OPEN_EXR", "16", "exr"),
        ("OPEN_EXR", "32", "exr"),
    )
    for index, (file_format, color_depth, extension) in enumerate(formats):
        settings.common_name = f"simple_baker_format_{index}"
        settings.file_format = file_format
        settings.color_depth = color_depth
        result = bpy.ops.simple_baker.bake_and_save()
        assert "FINISHED" in result, (file_format, color_depth, result)
        assert (
            Path(settings.output_directory)
            / f"simple_baker_format_{index}_color.{extension}"
        ).is_file()
    assert bpy.context.active_object == target
    print("Simple Baker output format save test passed")


def _run_multiple_map_rebake() -> None:
    """Verify visible per-map targets and safe coexistence with user nodes."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    settings.initialized = True
    settings.bake_target = target
    settings.workflow = "SELF"
    settings.common_name = "simple_baker_multiple"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_")
    settings.resolution = 32
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_diffuse = True
    settings.map_ao = True
    settings.create_image_texture_nodes = True

    material = target.active_material
    user_image = bpy.data.images.new("user_bake_target", 8, 8)
    user_node = material.node_tree.nodes.new("ShaderNodeTexImage")
    user_node.name = "User Image Texture"
    user_node.image = user_image
    user_node.location = (100.0, 100.0)
    material.node_tree.nodes.active = user_node

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    assert user_node.image == user_image

    managed_nodes = _managed_image_nodes(material)
    assert len(managed_nodes) == 2
    assert {node.get("simple_baker_map_key") for node in managed_nodes} == {"ao", "diffuse"}
    assert len({tuple(node.location) for node in managed_nodes}) == 2
    assert {node.image.name for node in managed_nodes} == {
        "simple_baker_multiple_ao",
        "simple_baker_multiple_color",
    }

    result = bpy.ops.simple_baker.bake_and_save(confirmed_overwrite=True)
    assert "FINISHED" in result, result
    assert user_node.image == user_image
    assert len(_managed_image_nodes(material)) == 2
    print("Simple Baker multiple-map re-bake test passed")


def main() -> None:
    initial_normal_settings = (
        bpy.context.scene.render.bake.normal_space,
        bpy.context.scene.render.bake.normal_r,
        bpy.context.scene.render.bake.normal_g,
        bpy.context.scene.render.bake.normal_b,
    )
    simple_baker.register()
    try:
        assert hasattr(bpy.types.Scene, "simple_baker")
        assert ADDON_ID == "simple_baker"
        assert bpy.context.scene.simple_baker.resolution == 2048
        assert not bpy.context.scene.simple_baker.create_image_texture_nodes
        assert bpy.context.scene.simple_baker.normal_format == "CUSTOM"
        assert Path(bpy.context.scene.simple_baker.output_directory) == Path(
            render_output_directory(bpy.context.scene)
        )
        assert initial_normal_settings == (
            bpy.context.scene.render.bake.normal_space,
            bpy.context.scene.render.bake.normal_r,
            bpy.context.scene.render.bake.normal_g,
            bpy.context.scene.render.bake.normal_b,
        )
        print("Simple Baker Blender smoke test passed")
        _run_progress_reporting_test()
        _run_preference_restore_without_feedback_test()
        _run_render_output_directory_test()
        _run_normal_format_test()
        _run_output_format_test()
        _run_output_format_save_test()
        _run_self_bake()
        _run_preflight_rejection_tests()
        _run_selected_to_active_bake()
        _run_multiple_material_bake()
        _run_all_map_bake()
        _run_temporary_target_bake()
        _run_existing_link_and_overwrite_test()
        _run_failed_save_rollback_test()
        _run_multiple_map_rebake()
    finally:
        simple_baker.unregister()


if __name__ == "__main__":
    main()
