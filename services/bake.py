"""Native Cycles bake orchestration for Simple Baker."""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from ..constants import CONNECTION_MATERIAL, WORKFLOW_SELECTED_TO_ACTIVE
from ..models import ImageSpec, SavedContextState
from ..properties import apply_normal_map_format
from .images import build_image_specs, create_bake_image, remove_unused_managed_images
from .materials import (
    MaterialConnectionResult,
    apply_material_connections,
    prepare_bake_image_nodes,
    remove_temporary_bake_image_nodes,
    rollback_prepared_bake_image_nodes,
    restore_bake_target_links,
    suspend_bake_target_links,
)
from .state import (
    capture_context_state,
    restore_context_state,
    temporary_bake_type,
    temporary_cycles_engine,
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
    connection_results: tuple[MaterialConnectionResult, ...]


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


def _bake_and_save_one(
    context,
    target,
    bake_objects,
    image_spec: ImageSpec,
    connect_material: bool,
    keep_image_nodes: bool,
) -> tuple[str, tuple[MaterialConnectionResult, ...]]:
    """Bake a prepared internal image, then save that same data-block to disk."""
    scene = context.scene
    bake_settings = scene.render.bake
    image = create_bake_image(image_spec)
    prepared_nodes = ()
    suspended_links = ()
    try:
        prepared_nodes = prepare_bake_image_nodes(
            target, image, image_spec.map_spec, keep_nodes=keep_image_nodes
        )
        suspended_links = suspend_bake_target_links(prepared_nodes)
        with temporary_bake_type(bake_settings, image_spec.map_spec.bake_type):
            # The Properties-editor button can run with a context whose visible
            # selection differs from the objects selected above.  Pass the UI
            # choices explicitly so Cycles never falls back to stale selection
            # state on a re-bake with retained Image Texture nodes.
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
        remove_temporary_bake_image_nodes(prepared_nodes)

        # save_render writes the existing image data-block; it does not reload
        # an external image, so the generated image remains usable inside Blender.
        with temporary_image_settings(scene, image_spec.file_format, image_spec.color_depth):
            image.save_render(image_spec.output_path, scene=scene)
        connections = (
            apply_material_connections(target, image, image_spec.map_spec) if connect_material else ()
        )
    except Exception:
        # Do not leave a partly prepared retained node or a partially baked
        # replacement image behind.  Existing nodes still reference their
        # previous image because every attempt uses a fresh staging image.
        try:
            restore_bake_target_links(suspended_links)
        finally:
            rollback_prepared_bake_image_nodes(prepared_nodes)
            bpy.data.images.remove(image)
        raise

    remove_unused_managed_images(image_spec.output_path, image)
    return image_spec.output_path, connections


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
    """Run selected maps independently and preserve successes after later errors."""
    target = settings.bake_target
    sources = tuple(item.object for item in settings.source_objects)
    bake_objects = _bake_context_objects(
        target,
        sources,
        settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE,
    )
    image_specs = build_image_specs(settings)
    if any(image_spec.map_spec.key == "normal" for image_spec in image_specs):
        # Reapply the selected target format immediately before baking. This
        # keeps output deterministic if Blender's native bake settings were
        # changed outside this add-on after choosing a preset.
        apply_normal_map_format(context.scene, settings.normal_format)
    state = capture_context_state(context)
    saved_paths: list[str] = []
    failures: list[BakeFailure] = []
    connection_results: list[MaterialConnectionResult] = []
    bake_settings = context.scene.render.bake
    target_settings = None
    progress = BakeProgress(context, len(image_specs))

    try:
        progress.start()
        with temporary_cycles_engine(context.scene):
            _set_bake_selection(
                context,
                target,
                sources,
                settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE,
            )
            target_settings = _set_bake_target_settings(
                bake_settings,
                settings.workflow == WORKFLOW_SELECTED_TO_ACTIVE,
            )
            for index, image_spec in enumerate(image_specs):
                try:
                    progress.begin_map(index, image_spec.map_spec.label)
                    saved_path, map_connections = _bake_and_save_one(
                        context,
                        target,
                        bake_objects,
                        image_spec,
                        settings.connection_mode == CONNECTION_MATERIAL,
                        settings.create_image_texture_nodes,
                    )
                    saved_paths.append(saved_path)
                    connection_results.extend(map_connections)
                except Exception as error:  # Blender operators expose RuntimeError and may vary by build.
                    failures.append(
                        BakeFailure(
                            image_spec=image_spec,
                            reason=_bake_failure_reason(error, settings.create_image_texture_nodes),
                        )
                    )
    except Exception as error:
        # If Cycles cannot be activated or selection setup fails, return a
        # useful result instead of leaking an exception through the operator.
        failures.extend(
            BakeFailure(image_spec=image_spec, reason=str(error))
            for image_spec in image_specs
        )
    finally:
        if target_settings is not None:
            _restore_bake_target_settings(bake_settings, target_settings)
        restore_context_state(context, state)
        progress.close()

    return BakeRunResult(tuple(saved_paths), tuple(failures), tuple(connection_results))
