"""Blender-runtime smoke and self-bake test.

Run with: blender --background --python tests/run_all.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import simple_baker
from simple_baker.constants import ADDON_ID, BAKE_MAPS, PACK_PRESETS
from simple_baker.services import bake as bake_service
from simple_baker.services.bake import BakeProgress
from simple_baker.services.images import build_image_specs
from simple_baker.services.pbr import prepare_pbr_channel_extraction
from simple_baker.models import BakeMapSpec
from simple_baker.properties import render_output_directory


def _clear_all_maps(settings) -> None:
    for key, _, _ in BAKE_MAPS:
        setattr(settings, f"map_{key}", False)
    for _, prop_name, _, _ in PACK_PRESETS:
        setattr(settings, prop_name, False)
    settings.create_image_texture_nodes = False


def _snapshot_material_graph(material):
    """Snapshot nodes and surface links to detect graph mutations."""
    nodes = {n.name: n.bl_idname for n in material.node_tree.nodes}
    links = [
        (l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)
        for l in material.node_tree.links
    ]
    return nodes, set(links)


def _assert_material_graph_unchanged(material, snapshot):
    before_nodes, before_links = snapshot
    after_nodes, after_links = _snapshot_material_graph(material)
    assert after_nodes == before_nodes, f"Nodes mismatch: {after_nodes} != {before_nodes}"
    assert after_links == before_links, f"Links mismatch: {after_links} != {before_links}"


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
    _clear_all_maps(settings)
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


def _managed_image_for_output(output_path: Path):
    matches = [
        image
        for image in bpy.data.images
        if image.get("simple_baker_managed")
        and image.get("simple_baker_image_key") == str(output_path)
    ]
    assert len(matches) == 1, (output_path, [image.name for image in matches])
    return matches[0]


def _center_pixel(image) -> tuple[float, float, float, float]:
    x = image.size[0] // 2
    y = image.size[1] // 2
    offset = (y * image.size[0] + x) * 4
    return tuple(image.pixels[offset : offset + 4])


def _linear_to_srgb(value: float) -> float:
    if value <= 0.0031308:
        return value * 12.92
    return 1.055 * math.pow(value, 1.0 / 2.4) - 0.055


def _assert_pixel_close(actual, expected, tolerance=2.0 / 255.0) -> None:
    assert len(actual) == len(expected)
    for actual_channel, expected_channel in zip(actual, expected):
        assert abs(actual_channel - expected_channel) <= tolerance, (actual, expected)


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
    _clear_all_maps(settings)
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
    _clear_all_maps(settings)
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
    _clear_all_maps(settings)
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


def _run_pbr_self_bake() -> None:
    """PBR maps (base_color, metallic, alpha, smoothness) must bake and preserve original material."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.8, 0.2, 0.3, 1.0)
    principled.inputs["Metallic"].default_value = 1.0
    principled.inputs["Alpha"].default_value = 0.5
    principled.inputs["Roughness"].default_value = 0.25

    rgb_node = material.node_tree.nodes.new("ShaderNodeRGB")
    rgb_node.outputs["Color"].default_value = (0.8, 0.2, 0.3, 1.0)
    material.node_tree.links.new(rgb_node.outputs["Color"], principled.inputs["Base Color"])

    scene = bpy.context.scene
    settings = scene.simple_baker
    for k in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission", "map_base_color", "map_metallic",
        "map_alpha", "map_smoothness",
    ):
        setattr(settings, k, False)

    settings.workflow = "SELF"
    settings.common_name = "pbr_self_test"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pbr_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.create_image_texture_nodes = False
    settings.map_base_color = True
    settings.map_metallic = True
    settings.map_alpha = True
    settings.map_smoothness = True

    output_node = material.node_tree.nodes.get("Material Output")
    assert output_node is not None
    orig_surface_from = output_node.inputs["Surface"].links[0].from_node
    assert orig_surface_from == principled
    node_count_before = len(material.node_tree.nodes)

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    out_dir = Path(settings.output_directory)
    assert (out_dir / "pbr_self_test_base_color.png").is_file()
    assert (out_dir / "pbr_self_test_metallic.png").is_file()
    assert (out_dir / "pbr_self_test_alpha.png").is_file()
    assert (out_dir / "pbr_self_test_smoothness.png").is_file()

    _assert_pixel_close(
        _center_pixel(_managed_image_for_output(out_dir / "pbr_self_test_base_color.png")),
        tuple(_linear_to_srgb(value) for value in (0.8, 0.2, 0.3)) + (1.0,),
    )
    _assert_pixel_close(
        _center_pixel(_managed_image_for_output(out_dir / "pbr_self_test_metallic.png")),
        (1.0, 1.0, 1.0, 1.0),
    )
    _assert_pixel_close(
        _center_pixel(_managed_image_for_output(out_dir / "pbr_self_test_alpha.png")),
        (0.5, 0.5, 0.5, 1.0),
    )
    _assert_pixel_close(
        _center_pixel(_managed_image_for_output(out_dir / "pbr_self_test_smoothness.png")),
        (0.75, 0.75, 0.75, 1.0),
    )

    assert len(material.node_tree.nodes) == node_count_before
    assert output_node.inputs["Surface"].is_linked
    assert output_node.inputs["Surface"].links[0].from_node == principled
    print("Simple Baker PBR self-bake test passed")


def _run_pbr_retained_node_rebake() -> None:
    """A retained PBR node may feed Principled without becoming its own bake source."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.2, 0.5, 0.8, 1.0)

    settings = bpy.context.scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pbr_rebake_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.create_image_texture_nodes = True
    settings.map_base_color = True

    settings.common_name = "pbr_rebake_first"
    assert "FINISHED" in bpy.ops.simple_baker.bake_and_save()
    managed = next(
        node
        for node in material.node_tree.nodes
        if node.get("simple_baker_managed")
        and node.get("simple_baker_map_key") == "base_color"
    )
    first_pixel = _center_pixel(managed.image)
    material.node_tree.links.new(managed.outputs["Color"], principled.inputs["Base Color"])

    settings.common_name = "pbr_rebake_second"
    assert "FINISHED" in bpy.ops.simple_baker.bake_and_save()
    second_pixel = _center_pixel(managed.image)
    _assert_pixel_close(second_pixel, first_pixel)
    assert principled.inputs["Base Color"].links[0].from_node == managed
    print("Simple Baker PBR retained-node re-bake test passed")


def _run_pbr_prepare_failure_rollback() -> None:
    """Failure while preparing the current material must remove partial changes."""
    target = _create_bake_target()
    material = target.active_material
    output = material.node_tree.nodes.get("Material Output")
    principled = material.node_tree.nodes.get("Principled BSDF")
    before_nodes = tuple(material.node_tree.nodes)

    invalid_spec = BakeMapSpec(
        key="invalid",
        setting_name="map_invalid",
        bake_type="EMIT",
        suffix="invalid",
        label="Invalid",
        is_pbr=True,
        pbr_socket_name="Base Color",
        invert=True,
    )
    try:
        prepare_pbr_channel_extraction((material,), invalid_spec)
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("Expected preparation failure")

    assert tuple(material.node_tree.nodes) == before_nodes
    assert output.inputs["Surface"].is_linked
    assert output.inputs["Surface"].links[0].from_node == principled
    assert not any(node.get("simple_baker_pbr_temporary") for node in material.node_tree.nodes)
    print("Simple Baker PBR preparation rollback test passed")


def _run_pbr_selected_to_active_bake() -> None:
    """PBR maps in transfer mode must extract from source model materials."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    bpy.ops.mesh.primitive_plane_add(size=2.0)
    target = bpy.context.active_object
    target.name = "pbr_target"
    target_mat = bpy.data.materials.new("pbr_target_mat")
    target.data.materials.append(target_mat)

    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0.1))
    source = bpy.context.active_object
    source.name = "pbr_source"
    source_mat = bpy.data.materials.new("pbr_source_mat")
    src_principled = source_mat.node_tree.nodes.get("Principled BSDF")
    src_principled.inputs["Base Color"].default_value = (0.1, 0.9, 0.1, 1.0)
    src_principled.inputs["Metallic"].default_value = 0.8
    source.data.materials.append(source_mat)

    scene = bpy.context.scene
    settings = scene.simple_baker
    for k in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission", "map_base_color", "map_metallic",
        "map_alpha", "map_smoothness",
    ):
        setattr(settings, k, False)

    settings.workflow = "SELECTED_TO_ACTIVE"
    settings.bake_target = target
    settings.source_objects.clear()
    source_entry = settings.source_objects.add()
    source_entry.object = source
    settings.common_name = "pbr_transfer_test"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pbr_trans_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_base_color = True
    settings.map_metallic = True

    scene.render.bake.cage_extrusion = 0.5
    scene.render.bake.max_ray_distance = 1.0

    src_output = source_mat.node_tree.nodes.get("Material Output")
    assert src_output is not None
    src_nodes_before = len(source_mat.node_tree.nodes)

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    out_dir = Path(settings.output_directory)
    assert (out_dir / "pbr_transfer_test_base_color.png").is_file()
    assert (out_dir / "pbr_transfer_test_metallic.png").is_file()

    assert len(source_mat.node_tree.nodes) == src_nodes_before
    assert src_output.inputs["Surface"].is_linked
    assert src_output.inputs["Surface"].links[0].from_node == src_principled
    print("Simple Baker PBR selected-to-active bake test passed")


def _run_pbr_rejection_tests() -> None:
    """PBR maps must reject materials with unsupported shaders without side effects."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    material.node_tree.nodes.remove(principled)
    diffuse = material.node_tree.nodes.new("ShaderNodeBsdfDiffuse")
    output = material.node_tree.nodes.get("Material Output")
    material.node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])

    scene = bpy.context.scene
    settings = scene.simple_baker
    for k in (
        "map_combined", "map_ao", "map_shadow", "map_normal", "map_uv",
        "map_roughness", "map_emit", "map_environment", "map_diffuse",
        "map_glossy", "map_transmission", "map_base_color", "map_metallic",
        "map_alpha", "map_smoothness",
    ):
        setattr(settings, k, False)

    settings.workflow = "SELF"
    settings.common_name = "pbr_rejection_test"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pbr_rej_")
    settings.map_base_color = True

    _assert_rejected_bake_has_no_side_effects(target)
    print("Simple Baker PBR rejection tests passed")


def _run_pack_presets_bake() -> None:
    """Channel packing presets composite individual maps into RGBA textures."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.8, 0.2, 0.3, 1.0)
    principled.inputs["Metallic"].default_value = 0.9
    principled.inputs["Roughness"].default_value = 0.25
    principled.inputs["Alpha"].default_value = 0.6

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "pack_test"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pack_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"

    settings.pack_orm = True
    settings.pack_gltf = True
    settings.pack_unity_mask = True
    settings.pack_base_color_alpha = True

    node_count_before = len(material.node_tree.nodes)
    output_node = material.node_tree.nodes.get("Material Output")
    assert output_node is not None

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    out_dir = Path(settings.output_directory)
    orm_path = out_dir / "pack_test_orm.png"
    gltf_path = out_dir / "pack_test_metallic_roughness.png"
    mask_path = out_dir / "pack_test_mask.png"
    bca_path = out_dir / "pack_test_base_color_alpha.png"

    assert orm_path.is_file(), orm_path
    assert gltf_path.is_file(), gltf_path
    assert mask_path.is_file(), mask_path
    assert bca_path.is_file(), bca_path

    # ORM: R=AO (0.6 reflecting Alpha), G=Roughness (0.25), B=Metallic (0.9), A=1.0
    orm_px = _center_pixel(_managed_image_for_output(orm_path))
    _assert_pixel_close(orm_px, (0.6, 0.25, 0.9, 1.0))

    # glTF: R=1.0, G=Roughness (0.25), B=Metallic (0.9), A=1.0
    gltf_px = _center_pixel(_managed_image_for_output(gltf_path))
    _assert_pixel_close(gltf_px, (1.0, 0.25, 0.9, 1.0))

    # Unity Mask: R=Metallic (0.9), G=AO (0.6), B=Detail (0.0), A=Smoothness (1.0 - 0.25 = 0.75)
    mask_px = _center_pixel(_managed_image_for_output(mask_path))
    _assert_pixel_close(mask_px, (0.9, 0.6, 0.0, 0.75))

    # Base Color + Alpha: RGB=Base Color (sRGB encoded), A=Alpha (0.6)
    bca_px = _center_pixel(_managed_image_for_output(bca_path))
    expected_rgb = tuple(_linear_to_srgb(v) for v in (0.8, 0.2, 0.3))
    _assert_pixel_close(bca_px, expected_rgb + (0.6,))

    # Node cleanup and restoration
    assert len(material.node_tree.nodes) == node_count_before
    assert output_node.inputs["Surface"].is_linked
    assert output_node.inputs["Surface"].links[0].from_node == principled
    print("Simple Baker channel packing presets bake test passed")


def _run_pack_and_individual_combined_bake() -> None:
    """Individual maps and packed presets can be baked together without duplication."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Roughness"].default_value = 0.4
    principled.inputs["Metallic"].default_value = 0.7

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "pack_combined_test"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pack_comb_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"

    settings.map_roughness = True
    settings.pack_orm = True

    baked_keys = []
    original_bake_one_image = bake_service._bake_one_image

    def count_bake_calls(*args, **kwargs):
        baked_keys.append(args[3].map_spec.key)
        return original_bake_one_image(*args, **kwargs)

    bake_service._bake_one_image = count_bake_calls
    try:
        result = bpy.ops.simple_baker.bake_and_save()
        assert "FINISHED" in result, result
    finally:
        bake_service._bake_one_image = original_bake_one_image

    out_dir = Path(settings.output_directory)
    assert (out_dir / "pack_combined_test_roughness.png").is_file()
    assert (out_dir / "pack_combined_test_orm.png").is_file()
    assert baked_keys.count("roughness") == 1, baked_keys
    print("Simple Baker packed and individual combined bake test passed")


def _run_pack_source_failure_test() -> None:
    """A packed output must not be saved when one of its required sources fails."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "pack_source_failure"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_pack_failure_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.pack_orm = True

    original_bake_one_image = bake_service._bake_one_image

    def fail_ao_source(*args, **kwargs):
        if args[3].map_spec.key == "ao":
            raise RuntimeError("forced AO source failure")
        return original_bake_one_image(*args, **kwargs)

    bake_service._bake_one_image = fail_ao_source
    try:
        result = bake_service.run_bake_jobs(bpy.context, settings)
    finally:
        bake_service._bake_one_image = original_bake_one_image

    failure_keys = [failure.image_spec.map_spec.key for failure in result.failures]
    assert "ao" in failure_keys, failure_keys
    assert "orm" in failure_keys, failure_keys
    assert not result.saved_paths, result.saved_paths
    assert not (Path(settings.output_directory) / "pack_source_failure_orm.png").exists()
    print("Simple Baker packed source failure test passed")


def _run_advanced_pbr_self_bake() -> None:
    """Advanced Principled BSDF inputs are directly extracted with exact pixel values and zero mutation."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Transmission Weight"].default_value = 0.85
    principled.inputs["Specular IOR Level"].default_value = 0.45
    principled.inputs["Coat Weight"].default_value = 0.75
    principled.inputs["Coat Roughness"].default_value = 0.15
    principled.inputs["Sheen Weight"].default_value = 0.65
    principled.inputs["Subsurface Weight"].default_value = 0.35

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "adv_pbr_self"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_adv_self_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"

    settings.map_transmission_weight = True
    settings.map_specular_ior_level = True
    settings.map_coat_weight = True
    settings.map_coat_roughness = True
    settings.map_sheen_weight = True
    settings.map_subsurface_weight = True

    snapshot_before = _snapshot_material_graph(material)

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    out_dir = Path(settings.output_directory)
    expected_values = {
        "transmission_weight": 0.85,
        "specular_ior_level": 0.45,
        "coat_weight": 0.75,
        "coat_roughness": 0.15,
        "sheen_weight": 0.65,
        "subsurface_weight": 0.35,
    }

    for suffix, expected_scalar in expected_values.items():
        file_path = out_dir / f"adv_pbr_self_{suffix}.png"
        assert file_path.is_file(), file_path
        img = _managed_image_for_output(file_path)
        px = _center_pixel(img)
        _assert_pixel_close(px, (expected_scalar, expected_scalar, expected_scalar, 1.0))

    _assert_material_graph_unchanged(material, snapshot_before)
    print("Simple Baker advanced PBR self-bake test passed")


def _run_advanced_pbr_transfer_bake() -> None:
    """Advanced PBR inputs can be baked from source models to active target with graph restoration."""
    target = _create_bake_target()
    target_snapshot = _snapshot_material_graph(target.active_material)

    # Create source plane
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    source = bpy.context.active_object
    source.name = "adv_pbr_source"
    source_mat = bpy.data.materials.new("adv_pbr_source_material")
    source_principled = source_mat.node_tree.nodes.get("Principled BSDF")
    source_principled.inputs["Coat Weight"].default_value = 0.8
    source_principled.inputs["Transmission Weight"].default_value = 0.9
    source.data.materials.append(source_mat)
    source_snapshot = _snapshot_material_graph(source_mat)

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELECTED_TO_ACTIVE"
    settings.bake_target = target
    source_item = settings.source_objects.add()
    source_item.object = source
    settings.common_name = "adv_pbr_transfer"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_adv_xfer_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_coat_weight = True
    settings.map_transmission_weight = True

    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    out_dir = Path(settings.output_directory)
    coat_path = out_dir / "adv_pbr_transfer_coat_weight.png"
    trans_path = out_dir / "adv_pbr_transfer_transmission_weight.png"
    assert coat_path.is_file(), coat_path
    assert trans_path.is_file(), trans_path

    _assert_pixel_close(_center_pixel(_managed_image_for_output(coat_path)), (0.8, 0.8, 0.8, 1.0))
    _assert_pixel_close(_center_pixel(_managed_image_for_output(trans_path)), (0.9, 0.9, 0.9, 1.0))

    _assert_material_graph_unchanged(source_mat, source_snapshot)
    _assert_material_graph_unchanged(target.active_material, target_snapshot)
    print("Simple Baker advanced PBR transfer bake test passed")


def _run_advanced_pbr_retained_rebake() -> None:
    """Retained advanced PBR nodes wired back into Principled BSDF can be safely re-baked."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Coat Weight"].default_value = 0.7

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "adv_pbr_rebake"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_adv_rebake_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_coat_weight = True
    settings.create_image_texture_nodes = True

    # 1. Initial bake creates retained node
    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result
    managed_nodes = _managed_image_nodes(material)
    assert len(managed_nodes) == 1, managed_nodes
    retained_node = managed_nodes[0]
    initial_image = retained_node.image
    assert initial_image is not None

    # 2. Wire the retained node output into Principled's Coat Weight
    material.node_tree.links.new(retained_node.outputs["Color"], principled.inputs["Coat Weight"])

    # 3. Change common name or directory and re-bake
    settings.common_name = "adv_pbr_rebake2"
    result = bpy.ops.simple_baker.bake_and_save()
    assert "FINISHED" in result, result

    # 4. Retained node should still be present, wired, and referencing the new image
    managed_nodes = _managed_image_nodes(material)
    assert len(managed_nodes) == 1, managed_nodes
    assert managed_nodes[0] == retained_node
    assert retained_node.image != initial_image
    rebaked_path = Path(settings.output_directory) / "adv_pbr_rebake2_coat_weight.png"
    assert retained_node.image == _managed_image_for_output(rebaked_path)
    _assert_pixel_close(_center_pixel(retained_node.image), (0.7, 0.7, 0.7, 1.0))
    assert principled.inputs["Coat Weight"].is_linked
    assert principled.inputs["Coat Weight"].links[0].from_node == retained_node
    print("Simple Baker advanced PBR retained re-bake test passed")


def _run_advanced_pbr_rollback_test() -> None:
    """Save failure during advanced PBR bake must roll back all temporary nodes and images."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Sheen Weight"].default_value = 0.5
    snapshot_before = _snapshot_material_graph(material)

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "adv_pbr_rollback"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_adv_rb_")
    settings.resolution = 16
    settings.file_format = "PNG"
    settings.color_depth = "8"
    settings.map_sheen_weight = True
    settings.create_image_texture_nodes = True

    original_save_image = bake_service._save_image

    def fail_save(*args, **kwargs):
        raise RuntimeError("Simulated save failure for sheen")

    bake_service._save_image = fail_save
    try:
        result = bake_service.run_bake_jobs(bpy.context, settings)
    finally:
        bake_service._save_image = original_save_image

    assert len(result.failures) == 1, result.failures
    assert result.failures[0].image_spec.map_spec.key == "sheen_weight"
    assert not result.saved_paths

    # Material graph must be completely restored, no leftover images
    _assert_material_graph_unchanged(material, snapshot_before)
    leftover_images = [
        img for img in bpy.data.images if "adv_pbr_rollback_sheen_weight" in img.name
    ]
    assert not leftover_images, leftover_images
    print("Simple Baker advanced PBR rollback test passed")


def _run_advanced_pbr_rejection_test() -> None:
    """Advanced PBR bake must be rejected with zero side-effects if shader is unsupported."""
    target = _create_bake_target()
    material = target.active_material
    principled = material.node_tree.nodes.get("Principled BSDF")
    material.node_tree.nodes.remove(principled)
    diffuse = material.node_tree.nodes.new("ShaderNodeBsdfDiffuse")
    output = material.node_tree.nodes.get("Material Output")
    material.node_tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])

    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
    settings.workflow = "SELF"
    settings.common_name = "adv_pbr_rejection"
    settings.output_directory = tempfile.mkdtemp(prefix="simple_baker_adv_rej_")
    settings.map_coat_weight = True

    _assert_rejected_bake_has_no_side_effects(target)
    print("Simple Baker advanced PBR rejection test passed")


def _run_temporary_target_bake() -> None:
    """The default workflow must remove its temporary Image Texture target."""
    target = _create_bake_target()
    scene = bpy.context.scene
    settings = scene.simple_baker
    _clear_all_maps(settings)
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
    _clear_all_maps(settings)
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
    _clear_all_maps(settings)
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
    _clear_all_maps(settings)
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
        assert not bpy.context.scene.simple_baker.show_advanced_pbr_inputs
        assert bpy.context.scene.simple_baker.normal_format == "CUSTOM"
        direct_principled_maps = (
            "map_base_color",
            "map_metallic",
            "map_alpha",
            "map_smoothness",
            "map_transmission_weight",
            "map_specular_ior_level",
            "map_coat_weight",
            "map_coat_roughness",
            "map_sheen_weight",
            "map_subsurface_weight",
        )
        settings_rna = bpy.context.scene.simple_baker.bl_rna.properties
        for property_name in direct_principled_maps:
            assert "Requires Principled BSDF" in settings_rna[property_name].description
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
        _run_pbr_self_bake()
        _run_pbr_retained_node_rebake()
        _run_pbr_prepare_failure_rollback()
        _run_pbr_selected_to_active_bake()
        _run_pbr_rejection_tests()
        _run_pack_presets_bake()
        _run_pack_and_individual_combined_bake()
        _run_pack_source_failure_test()
        _run_advanced_pbr_self_bake()
        _run_advanced_pbr_transfer_bake()
        _run_advanced_pbr_retained_rebake()
        _run_advanced_pbr_rollback_test()
        _run_advanced_pbr_rejection_test()
        _run_temporary_target_bake()
        _run_existing_link_and_overwrite_test()
        _run_failed_save_rollback_test()
        _run_multiple_map_rebake()
    finally:
        simple_baker.unregister()


if __name__ == "__main__":
    main()
