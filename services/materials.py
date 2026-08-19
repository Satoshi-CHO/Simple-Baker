"""Non-destructive Image Texture node preparation for bake targets."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import BakeMapSpec

MANAGED_NODE_FLAG = "simple_baker_managed"
MANAGED_NODE_MAP_KEY = "simple_baker_map_key"


@dataclass(frozen=True)
class PreparedImageNode:
    """A material/node pair prepared as a Blender bake target."""

    material_name: str
    node_name: str
    material: object
    node: object
    temporary: bool = False
    previous_active_node: object | None = None
    previous_image: object | None = None
    previous_selected: bool = False
    created: bool = False


@dataclass(frozen=True)
class MaterialConnectionResult:
    """One material auto-connection or a safe reason it was left untouched."""

    material_name: str
    map_key: str
    connected: bool
    reason: str = ""


@dataclass(frozen=True)
class SuspendedNodeLink:
    """A managed output link removed only while its image is being baked."""

    node_tree: object
    from_socket: object
    to_socket: object


def _managed_node(material, map_key: str):
    for node in material.node_tree.nodes:
        if (
            node.bl_idname == "ShaderNodeTexImage"
            and node.get(MANAGED_NODE_FLAG)
            and node.get(MANAGED_NODE_MAP_KEY) == map_key
        ):
            return node
    return None


def _layout_managed_image_nodes(material) -> None:
    """Keep this add-on's image targets visible without moving user nodes."""
    node_tree = material.node_tree
    managed_nodes = sorted(
        (
            node
            for node in node_tree.nodes
            if node.bl_idname == "ShaderNodeTexImage" and node.get(MANAGED_NODE_FLAG)
        ),
        key=lambda node: str(node.get(MANAGED_NODE_MAP_KEY, "")),
    )
    if not managed_nodes:
        return

    user_nodes = [node for node in node_tree.nodes if node not in managed_nodes]
    # Reserve a dedicated row to the right of user nodes. Repositioning is
    # restricted to nodes marked as managed, so existing shader layouts remain
    # untouched while every baked map remains individually visible.
    start_x = max((node.location.x + node.width for node in user_nodes), default=0.0) + 80.0
    start_y = min((node.location.y for node in user_nodes), default=0.0) - 280.0
    for index, node in enumerate(managed_nodes):
        node.location = (start_x + index * (node.width + 80.0), start_y)


def _prepare_material_node(material, image, map_spec: BakeMapSpec):
    """Create or update only this add-on's dedicated Image Texture node."""
    node_tree = material.node_tree
    node = _managed_node(material, map_spec.key)
    created = node is None
    if node is None:
        node = node_tree.nodes.new("ShaderNodeTexImage")
        node.name = f"Simple Baker - {map_spec.label}"
        node.label = f"Simple Baker: {map_spec.label}"
        node[MANAGED_NODE_FLAG] = True
        node[MANAGED_NODE_MAP_KEY] = map_spec.key

    previous_image = node.image if not created else None
    previous_selected = node.select if not created else False

    # This is the only node updated. Links and all user-created nodes remain
    # untouched. Blender expects its image target to be both selected and
    # active; assigning only ``nodes.active`` is not reliable for old nodes.
    node.image = image
    _layout_managed_image_nodes(material)
    node.select = True
    node_tree.nodes.active = node
    return node, created, previous_image, previous_selected


def _prepare_temporary_material_node(material, image):
    """Create a disposable, active Image Texture node for one bake call."""
    node_tree = material.node_tree
    node = node_tree.nodes.new("ShaderNodeTexImage")
    node.name = "Simple Baker - Temporary Bake Target"
    node.label = "Simple Baker: Temporary Bake Target"
    node.image = image
    # A fresh node is selected by Blender today, but set it explicitly so the
    # bake target state does not depend on the editor's current selection.
    node.select = True
    node_tree.nodes.active = node
    return node, True, None, False


def prepare_bake_image_nodes(
    target, image, map_spec: BakeMapSpec, *, keep_nodes: bool
) -> tuple[PreparedImageNode, ...]:
    """Prepare the same image as active target in every assigned material.

    When ``keep_nodes`` is false, temporary nodes are removed after the bake.
    Empty material slots are skipped; no material slots are added and no existing
    material links are changed or removed.
    """
    prepared: list[PreparedImageNode] = []
    seen_materials: set[int] = set()
    try:
        for slot in target.material_slots:
            material = slot.material
            if material is None or material.as_pointer() in seen_materials:
                continue
            seen_materials.add(material.as_pointer())
            # Blender 5.0+ materials always expose a shader node tree.
            # ``Material.use_nodes`` is deprecated in Blender 5.2 and removed
            # in Blender 6.0, so do not read or mutate that legacy flag.
            previous_active_node = material.node_tree.nodes.active
            node, created, previous_image, previous_selected = (
                _prepare_material_node(material, image, map_spec)
                if keep_nodes
                else _prepare_temporary_material_node(material, image)
            )
            prepared.append(
                PreparedImageNode(
                    material.name,
                    node.name,
                    material,
                    node,
                    not keep_nodes,
                    previous_active_node,
                    previous_image,
                    previous_selected,
                    created,
                )
            )
    except Exception:
        rollback_prepared_bake_image_nodes(tuple(prepared))
        raise
    return tuple(prepared)


def remove_temporary_bake_image_nodes(prepared_nodes: tuple[PreparedImageNode, ...]) -> None:
    """Remove only nodes created as disposable bake targets for this run."""
    for prepared in prepared_nodes:
        if not prepared.temporary:
            continue
        node_tree = prepared.material.node_tree
        if node_tree and prepared.node.name in node_tree.nodes:
            node_tree.nodes.remove(prepared.node)
        if (
            node_tree
            and prepared.previous_active_node is not None
            and prepared.previous_active_node.name in node_tree.nodes
        ):
            node_tree.nodes.active = prepared.previous_active_node


def rollback_prepared_bake_image_nodes(
    prepared_nodes: tuple[PreparedImageNode, ...],
) -> None:
    """Restore every node touched by a bake that did not complete.

    Retained targets are only made permanent after the image has baked and
    saved.  A failed map must therefore leave pre-existing nodes and legacy
    materials exactly as they were, and remove nodes created for the failed
    attempt.
    """
    for prepared in reversed(prepared_nodes):
        material = prepared.material
        node_tree = material.node_tree
        node_exists = node_tree and prepared.node.name in node_tree.nodes
        if prepared.created and node_exists:
            node_tree.nodes.remove(prepared.node)
        elif node_exists:
            prepared.node.image = prepared.previous_image
            prepared.node.select = prepared.previous_selected

        if (
            node_tree
            and prepared.previous_active_node is not None
            and prepared.previous_active_node.name in node_tree.nodes
        ):
            node_tree.nodes.active = prepared.previous_active_node
        elif node_tree and prepared.created and node_tree.nodes.active == prepared.node:
            node_tree.nodes.active = None



def suspend_bake_target_links(
    prepared_nodes: tuple[PreparedImageNode, ...],
) -> tuple[SuspendedNodeLink, ...]:
    """Temporarily unlink retained targets so Cycles never reads its output image.

    A retained node can already feed the target's shader after a previous bake.
    Leaving that link in place makes Cycles report a circular image dependency.
    Only links *from this add-on's current bake target* are suspended and every
    link is restored immediately after the operator returns.
    """
    suspended: list[SuspendedNodeLink] = []
    for prepared in prepared_nodes:
        if prepared.temporary:
            continue
        node_tree = prepared.material.node_tree
        for output in prepared.node.outputs:
            for link in tuple(output.links):
                suspended.append(SuspendedNodeLink(node_tree, link.from_socket, link.to_socket))
                node_tree.links.remove(link)
    return tuple(suspended)


def restore_bake_target_links(suspended_links: tuple[SuspendedNodeLink, ...]) -> None:
    """Restore managed output links suspended solely to prevent feedback."""
    for link in suspended_links:
        link.node_tree.links.new(link.from_socket, link.to_socket)


def _principled_node(material):
    """Prefer the Principled shader connected to the material output."""
    nodes = material.node_tree.nodes
    for output in (node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"):
        surface = output.inputs.get("Surface")
        if surface and surface.is_linked:
            shader = surface.links[0].from_node
            if shader.bl_idname == "ShaderNodeBsdfPrincipled":
                return shader
    return next((node for node in nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"), None)


def _managed_normal_map_node(material):
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeNormalMap" and node.get(MANAGED_NODE_FLAG):
            return node
    return None


def _connect_normal(material, image_node) -> MaterialConnectionResult:
    principled = _principled_node(material)
    if principled is None:
        return MaterialConnectionResult(material.name, "normal", False, "No Principled BSDF node found.")
    normal_input = principled.inputs.get("Normal")
    if normal_input is None:
        return MaterialConnectionResult(material.name, "normal", False, "Principled Normal input is unavailable.")
    node_tree = material.node_tree
    normal_map = _managed_normal_map_node(material)
    managed_color_input = normal_map.inputs.get("Color") if normal_map is not None else None
    if normal_input.is_linked:
        if (
            normal_map is not None
            and managed_color_input is not None
            and any(link.from_node == normal_map for link in normal_input.links)
            and any(link.from_node == image_node for link in managed_color_input.links)
        ):
            return MaterialConnectionResult(material.name, "normal", True)
        return MaterialConnectionResult(material.name, "normal", False, "Principled Normal input already has a link.")
    if normal_map is None:
        normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
        normal_map.name = "Simple Baker - Normal Map"
        normal_map.label = "Simple Baker: Normal Map"
        normal_map[MANAGED_NODE_FLAG] = True
        normal_map[MANAGED_NODE_MAP_KEY] = "normal_map"

    color_input = normal_map.inputs.get("Color")
    if color_input is None:
        return MaterialConnectionResult(material.name, "normal", False, "Normal Map Color input is unavailable.")
    if color_input.is_linked:
        return MaterialConnectionResult(material.name, "normal", False, "Simple Baker Normal Map already has a color link.")

    node_tree.links.new(image_node.outputs["Color"], color_input)
    node_tree.links.new(normal_map.outputs["Normal"], normal_input)
    return MaterialConnectionResult(material.name, "normal", True)


def _connect_image_output(material, image_node, map_spec: BakeMapSpec) -> MaterialConnectionResult:
    socket_name = {
        "diffuse": "Base Color",
        "roughness": "Roughness",
        "emit": "Emission Color",
    }[map_spec.key]
    principled = _principled_node(material)
    if principled is None:
        return MaterialConnectionResult(material.name, map_spec.key, False, "No Principled BSDF node found.")
    socket = principled.inputs.get(socket_name)
    if socket is None:
        return MaterialConnectionResult(material.name, map_spec.key, False, f"Principled {socket_name} input is unavailable.")
    if socket.is_linked:
        if any(link.from_node == image_node for link in socket.links):
            return MaterialConnectionResult(material.name, map_spec.key, True)
        return MaterialConnectionResult(material.name, map_spec.key, False, f"Principled {socket_name} input already has a link.")
    node_tree = material.node_tree
    node_tree.links.new(image_node.outputs["Color"], socket)
    return MaterialConnectionResult(material.name, map_spec.key, True)


def apply_material_connections(target, image, map_spec: BakeMapSpec) -> tuple[MaterialConnectionResult, ...]:
    """Connect only supported maps, never replacing existing shader input links."""
    if map_spec.key not in {"diffuse", "normal", "roughness", "emit"}:
        return ()

    results: list[MaterialConnectionResult] = []
    seen_materials: set[int] = set()
    for slot in target.material_slots:
        material = slot.material
        if material is None or material.as_pointer() in seen_materials:
            continue
        seen_materials.add(material.as_pointer())
        image_node = _managed_node(material, map_spec.key)
        if image_node is None or image_node.image != image:
            results.append(
                MaterialConnectionResult(
                    material.name,
                    map_spec.key,
                    False,
                    "Simple Baker Image Texture node was not prepared.",
                )
            )
            continue
        if map_spec.key == "normal":
            results.append(_connect_normal(material, image_node))
        else:
            results.append(_connect_image_output(material, image_node, map_spec))
    return tuple(results)
