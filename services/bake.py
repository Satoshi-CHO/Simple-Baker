"""Native Cycles bake orchestration for Simple Baker."""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from ..constants import WORKFLOW_SELECTED_TO_ACTIVE
from ..models import ImageSpec
from ..properties import apply_normal_map_format
from .images import MAP_SPECS, build_image_specs, create_bake_image, remove_unused_managed_images
from .materials import (
    prepare_bake_image_nodes,
    remove_temporary_bake_image_nodes,
    rollback_prepared_bake_image_nodes,
    restore_bake_target_links,
    suspend_bake_target_links,
)
from .packing import (
    PackPresetSpec,
    build_pack_image_specs,
    composite_packed_image,
    required_source_map_keys,
    selected_pack_specs,
)
from .pbr import (
    collect_source_materials,
    prepare_pbr_channel_extraction,
    restore_pbr_channel_extraction,
)
from .state import (
    capture_context_state,
    restore_context_state,
    temporary_image_settings,
)


def _translated(message_id: str) -> str:
    return bpy.app.translations.pgettext(message_id)


@dataclass(frozen=True)
class BakeFailure:
    """A map that could not be baked or saved, without discarding other maps."""

    image_spec: ImageSpec
    reason: str


@dataclass(frozen=True)
class BakeRunResult:
    """Summary returned to the operator for user-facing reporting."""

    saved_paths: tuple[str, ...]
    failures: tuple[BakeFailure, ...]


class BakeProgress:
    """Best-effort status-bar progress for a sequence of native bake calls."""

    def __init__(self, context, total: int) -> None:
        self._context = context
        self._total = total
        self._started = False

    def _set_status(self, text: str | None) -> None:
        workspace = getattr(self._context, "workspace", None)
        status_text_set = getattr(workspace, "status_text_set", None)
        if status_text_set is None:
            return
        try:
            status_text_set(text)
        except (RuntimeError, TypeError):
            # UI feedback must not interfere with a valid bake in background
            # mode or in workspaces that reject a custom status message.
            pass

    def start(self) -> None:
        try:
            self._context.window_manager.progress_begin(0, self._total)
            self._started = True
        except RuntimeError:
            return
        self._set_status(
            _translated("Simple Baker: Preparing {count} map(s)").format(count=self._total)
        )

    def begin_map(self, index: int, label: str) -> None:
        if self._started:
            try:
                self._context.window_manager.progress_update(index)
            except RuntimeError:
                pass
        self._set_status(
            _translated("Simple Baker: Baking {label} ({current}/{total})").format(
                label=label, current=index + 1, total=self._total
            )
        )

    def close(self) -> None:
        if self._started:
            try:
                self._context.window_manager.progress_update(self._total)
            except RuntimeError:
                pass
            finally:
                try:
                    self._context.window_manager.progress_end()
                except RuntimeError:
                    pass
            self._started = False
        self._set_status(None)


def _set_bake_target_settings(bake_settings, selected_to_active: bool) -> dict[str, object]:
    """Use Image Texture targets while retaining prior Blender settings for restore."""
    snapshot: dict[str, object] = {}
    for attribute, value in (
        ("target", "IMAGE_TEXTURES"),
        ("use_selected_to_active", selected_to_active),
        ("use_split_materials", False),
    ):
        if hasattr(bake_settings, attribute):
            snapshot[attribute] = getattr(bake_settings, attribute)
            setattr(bake_settings, attribute, value)
    return snapshot


def _restore_bake_target_settings(bake_settings, snapshot: dict[str, object]) -> None:
    for attribute, value in snapshot.items():
        setattr(bake_settings, attribute, value)


def _set_bake_selection(context, target, sources, selected_to_active: bool) -> None:
    """Make Cycles' required active/selected selection deterministically."""
    active = context.view_layer.objects.active
    if active and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in context.view_layer.objects:
        obj.select_set(False)

    if selected_to_active:
        for source in sources:
            if source and source != target:
                source.select_set(True)
    target.select_set(True)
    context.view_layer.objects.active = target


def _bake_context_objects(target, sources, selected_to_active: bool) -> tuple:
    """Return the exact objects Cycles must see for this bake operation."""
    return (target, *sources) if selected_to_active else (target,)


def _bake_one_image(
    context,
    target,
    bake_objects,
    image_spec: ImageSpec,
    keep_image_nodes: bool,
    pbr_source_objects: tuple = (),
):
    """Bake a prepared internal image without saving it to disk."""
    image = create_bake_image(image_spec)
    bake_target_nodes = ()
    retained_nodes = ()
    suspended_links = ()
    prepared_pbr = ()
    stage_retained_pbr_target = image_spec.map_spec.is_pbr and keep_image_nodes
    try:
        if image_spec.map_spec.is_pbr:
            pbr_materials = collect_source_materials(pbr_source_objects)
            prepared_pbr = prepare_pbr_channel_extraction(pbr_materials, image_spec.map_spec)

        bake_target_nodes = prepare_bake_image_nodes(
            target,
            image,
            image_spec.map_spec,
            keep_nodes=keep_image_nodes and not stage_retained_pbr_target,
        )
        suspended_links = suspend_bake_target_links(bake_target_nodes)

        with context.temp_override(
            active_object=target,
            object=target,
            selected_objects=bake_objects,
            selected_editable_objects=bake_objects,
        ):
            result = bpy.ops.object.bake(type=image_spec.map_spec.bake_type)
        if "FINISHED" not in result:
            raise RuntimeError("Blender cancelled the bake operation.")
        restore_bake_target_links(suspended_links)
        suspended_links = ()
        remove_temporary_bake_image_nodes(bake_target_nodes)
        if prepared_pbr:
            restore_pbr_channel_extraction(prepared_pbr)
            prepared_pbr = ()

        if stage_retained_pbr_target:
            retained_nodes = prepare_bake_image_nodes(
                target, image, image_spec.map_spec, keep_nodes=True
            )
        active_nodes = retained_nodes if stage_retained_pbr_target else bake_target_nodes
        return image, active_nodes
    except Exception:
        try:
            if prepared_pbr:
                restore_pbr_channel_extraction(prepared_pbr)
        finally:
            try:
                restore_bake_target_links(suspended_links)
            finally:
                try:
                    rollback_prepared_bake_image_nodes(retained_nodes)
                finally:
                    rollback_prepared_bake_image_nodes(bake_target_nodes)
                    bpy.data.images.remove(image)
        raise


def _save_image(context, image, image_spec: ImageSpec) -> str:
    """Save an internal image data-block to disk."""
    scene = context.scene
    with temporary_image_settings(scene, image_spec.file_format, image_spec.color_depth):
        image.save_render(image_spec.output_path, scene=scene)
    remove_unused_managed_images(image_spec.output_path, image)
    return image_spec.output_path


def _bake_and_save_one(
    context,
    target,
    bake_objects,
    image_spec: ImageSpec,
    keep_image_nodes: bool,
    pbr_source_objects: tuple = (),
) -> str:
    """Bake a prepared internal image, then save that same data-block to disk."""
    image, active_nodes = _bake_one_image(
        context,
        target,
        bake_objects,
        image_spec,
        keep_image_nodes,
        pbr_source_objects,
    )
    try:
        return _save_image(context, image, image_spec)
    except Exception:
        rollback_prepared_bake_image_nodes(active_nodes)
        if image in bpy.data.images.values():
            bpy.data.images.remove(image)
        raise


def _composite_and_save_packed(
    context,
    target,
    source_images: Mapping[str, bpy.types.Image],
    preset: PackPresetSpec,
    image_spec: ImageSpec,
    keep_image_nodes: bool,
) -> str:
    """Create destination image, composite channels from source_images, and save."""
    dest_image = create_bake_image(image_spec)
    prepared_nodes = ()
    try:
        composite_packed_image(source_images, preset, dest_image)
        if keep_image_nodes:
            prepared_nodes = prepare_bake_image_nodes(
                target, dest_image, image_spec.map_spec, keep_nodes=True
            )
        return _save_image(context, dest_image, image_spec)
    except Exception:
        rollback_prepared_bake_image_nodes(prepared_nodes)
        if dest_image in bpy.data.images.values():
            bpy.data.images.remove(dest_image)
        raise


def _bake_failure_reason(error: Exception, keep_image_nodes: bool) -> str:
    """Add an actionable explanation for Blender's active-image-target errors."""
    reason = str(error)
    normalized = reason.lower()
    active_image_error = (
        "active image" in normalized
        or "no image found" in normalized
        or "image texture" in normalized and "bake" in normalized
    )
    if keep_image_nodes and active_image_error:
        resolution = _translated(
            "Image Texture node bake target failed. Select the generated Image Texture node, "
            "or disable Keep Image Texture Nodes After Baking to use a temporary bake target."
        )
        return f"{reason} {resolution}"
    return reason


def run_bake_jobs(context, settings) -> BakeRunResult:
    """Run selected maps and pack presets independently and preserve successes."""
    target = settings.bake_target
    sources = tuple(item.object for item in settings.source_objects)
    selected_to_active = settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE
    bake_objects = _bake_context_objects(target, sources, selected_to_active)
    pbr_source_objects = sources if selected_to_active else (target,)

    # 1. Determine requested individual maps and requested pack presets
    requested_individual_specs = build_image_specs(settings, include_packed=False)
    requested_individual_keys = {spec.map_spec.key for spec in requested_individual_specs}
    pack_presets = selected_pack_specs(settings)
    pack_image_specs = build_pack_image_specs(settings)

    # 2. Determine any intermediate maps required by packing that weren't explicitly requested
    needed_source_keys = set(required_source_map_keys(settings))
    missing_source_keys = needed_source_keys - requested_individual_keys

    map_spec_lookup = {spec.key: spec for spec in MAP_SPECS}
    intermediate_specs: list[ImageSpec] = []
    for key in missing_source_keys:
        if key in map_spec_lookup:
            ms = map_spec_lookup[key]
            intermediate_specs.append(
                ImageSpec(
                    map_spec=ms,
                    image_name=f"temp_pack_{ms.suffix}",
                    output_path="",
                    width=settings.resolution,
                    height=settings.resolution,
                    file_format=settings.file_format,
                    color_depth=settings.color_depth,
                )
            )

    all_source_specs = (*requested_individual_specs, *intermediate_specs)
    total_steps = len(all_source_specs) + len(pack_image_specs)

    if any(spec.map_spec.key == "normal" for spec in all_source_specs):
        apply_normal_map_format(context.scene, settings.normal_format)

    state = capture_context_state(context)
    saved_paths: list[str] = []
    failures: list[BakeFailure] = []
    bake_settings = context.scene.render.bake
    target_settings = None
    progress = BakeProgress(context, total_steps)

    baked_images: dict[str, bpy.types.Image] = {}
    created_intermediate_images: list[bpy.types.Image] = []

    try:
        progress.start()
        context.scene.render.engine = "CYCLES"
        _set_bake_selection(
            context,
            target,
            sources,
            selected_to_active,
        )
        target_settings = _set_bake_target_settings(
            bake_settings,
            selected_to_active,
        )

        step_index = 0
        # 3. Bake all source maps
        for image_spec in all_source_specs:
            progress.begin_map(step_index, image_spec.map_spec.label)
            step_index += 1
            is_intermediate = image_spec.map_spec.key in missing_source_keys
            try:
                # Do not retain image nodes for purely intermediate maps
                keep_nodes = settings.create_image_texture_nodes and not is_intermediate
                img, active_nodes = _bake_one_image(
                    context,
                    target,
                    bake_objects,
                    image_spec,
                    keep_nodes,
                    pbr_source_objects=pbr_source_objects,
                )
                baked_images[image_spec.map_spec.key] = img
                if is_intermediate:
                    created_intermediate_images.append(img)
                else:
                    try:
                        saved_path = _save_image(context, img, image_spec)
                        saved_paths.append(saved_path)
                    except Exception:
                        rollback_prepared_bake_image_nodes(active_nodes)
                        if img in bpy.data.images.values():
                            bpy.data.images.remove(img)
                        raise
            except Exception as error:
                failures.append(
                    BakeFailure(
                        image_spec=image_spec,
                        reason=_bake_failure_reason(error, settings.create_image_texture_nodes),
                    )
                )

        # 4. Composite and save packed presets
        preset_by_key = {p.key: p for p in pack_presets}
        for pack_spec in pack_image_specs:
            progress.begin_map(step_index, pack_spec.map_spec.label)
            step_index += 1
            preset = preset_by_key.get(pack_spec.map_spec.key)
            if preset is None:
                continue

            try:
                saved_path = _composite_and_save_packed(
                    context,
                    target,
                    baked_images,
                    preset,
                    pack_spec,
                    settings.create_image_texture_nodes,
                )
                saved_paths.append(saved_path)
            except Exception as error:
                failures.append(BakeFailure(image_spec=pack_spec, reason=str(error)))

    except Exception as error:
        failures.extend(
            BakeFailure(image_spec=spec, reason=str(error))
            for spec in (*requested_individual_specs, *pack_image_specs)
        )
    finally:
        # Clean up purely intermediate images
        for intermediate_img in created_intermediate_images:
            if intermediate_img in bpy.data.images.values():
                bpy.data.images.remove(intermediate_img)

        if target_settings is not None:
            _restore_bake_target_settings(bake_settings, target_settings)
        restore_context_state(context, state)
        progress.close()

    return BakeRunResult(tuple(saved_paths), tuple(failures))
