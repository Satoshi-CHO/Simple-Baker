"""Extraction of PBR channels via temporary emission shader routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..models import BakeMapSpec, ValidationIssue

PBR_TEMPORARY_NODE_FLAG = "simple_baker_pbr_temporary"


@dataclass(frozen=True)
class SuspendedOutputLink:
    """A material output surface link suspended during PBR extraction."""

    node_tree: object
    from_socket: object
    to_socket: object


@dataclass(frozen=True)
class PreparedPbrMaterial:
    """State of one material prepared for PBR channel baking."""

    material: object
    output_node: object
    temporary_nodes: tuple[object, ...]
    suspended_links: tuple[SuspendedOutputLink, ...]


def find_active_material_output(material):
    """Find the deterministic active Material Output node for this material."""
    if not material or not material.node_tree:
        return None
    outputs = [
        node
        for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeOutputMaterial"
    ]
    if not outputs:
        return None
    if len(outputs) == 1:
        return outputs[0]
    active_outputs = [node for node in outputs if getattr(node, "is_active_output", False)]
    if len(active_outputs) == 1:
        return active_outputs[0]
    return None


def find_principled_bsdf(material, output_node):
    """Find the single directly connected Principled BSDF feeding the output."""
    if not output_node:
        return None
    surface_input = output_node.inputs.get("Surface")
    if not surface_input or not surface_input.is_linked:
        return None
    from_node = surface_input.links[0].from_node
    if from_node.bl_idname == "ShaderNodeBsdfPrincipled":
        return from_node
    return None


def inspect_pbr_compatibility(material, map_spec: BakeMapSpec) -> ValidationIssue | None:
    """Check if a material can support PBR channel extraction for map_spec."""
    if material is None:
        return None
    if not material.node_tree:
        return ValidationIssue(
            "pbr_no_node_tree",
            "Material '{mat_name}' does not use nodes.",
            {"mat_name": material.name},
        )
    output_node = find_active_material_output(material)
    if output_node is None:
        return ValidationIssue(
            "pbr_no_active_output",
            "Material '{mat_name}' has no active Material Output node.",
            {"mat_name": material.name},
        )
    principled = find_principled_bsdf(material, output_node)
    if principled is None:
        return ValidationIssue(
            "pbr_unsupported_shader",
            "Material '{mat_name}' must have a single Principled BSDF directly connected to Material Output.",
            {"mat_name": material.name},
        )
    target_socket = principled.inputs.get(map_spec.pbr_socket_name)
    if target_socket is None:
        return ValidationIssue(
            "pbr_missing_socket",
            "Principled BSDF in material '{mat_name}' is missing the '{socket_name}' input.",
            {"mat_name": material.name, "socket_name": map_spec.pbr_socket_name or ""},
        )
    return None


def collect_source_materials(objects: Sequence[object]) -> tuple[object, ...]:
    """Return all unique non-empty materials from the given mesh objects."""
    materials: list[object] = []
    seen: set[int] = set()
    for obj in objects:
        if obj is None or getattr(obj, "type", None) != "MESH":
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.as_pointer() not in seen:
                seen.add(mat.as_pointer())
                materials.append(mat)
    return tuple(materials)


def prepare_pbr_channel_extraction(
    materials: Sequence[object],
    map_spec: BakeMapSpec,
) -> tuple[PreparedPbrMaterial, ...]:
    """Temporarily route the requested PBR channel to an Emission shader."""
    prepared: list[PreparedPbrMaterial] = []
    seen: set[int] = set()

    for material in materials:
        if material is None or material.as_pointer() in seen:
            continue
        seen.add(material.as_pointer())
        node_tree = material.node_tree
        output_node = find_active_material_output(material)
        principled = find_principled_bsdf(material, output_node)
        if principled is None:
            continue

        socket = principled.inputs.get(map_spec.pbr_socket_name)
        if socket is None:
            continue

        temp_nodes: list[object] = []
        suspended_links: list[SuspendedOutputLink] = []
        try:
            # 1. Create temporary Emission shader
            emission = node_tree.nodes.new("ShaderNodeEmission")
            emission.name = "Simple Baker - PBR Emission"
            emission[PBR_TEMPORARY_NODE_FLAG] = True
            temp_nodes.append(emission)

            # 2. Connect or copy value to Emission Color
            if map_spec.invert:
                # Smoothness: 1.0 - Roughness
                math_node = node_tree.nodes.new("ShaderNodeMath")
                math_node.name = "Simple Baker - PBR Invert"
                math_node.operation = "SUBTRACT"
                math_node.inputs[0].default_value = 1.0
                math_node[PBR_TEMPORARY_NODE_FLAG] = True
                temp_nodes.append(math_node)

                if socket.is_linked:
                    node_tree.links.new(socket.links[0].from_socket, math_node.inputs[1])
                else:
                    math_node.inputs[1].default_value = float(socket.default_value)

                node_tree.links.new(math_node.outputs["Value"], emission.inputs["Color"])
            else:
                if socket.is_linked:
                    node_tree.links.new(socket.links[0].from_socket, emission.inputs["Color"])
                else:
                    val = socket.default_value
                    if isinstance(val, (int, float)):
                        fval = float(val)
                        emission.inputs["Color"].default_value = (fval, fval, fval, 1.0)
                    elif hasattr(val, "__len__") and len(val) >= 3:
                        emission.inputs["Color"].default_value = (val[0], val[1], val[2], 1.0)
                    else:
                        emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)

            # 3. Suspend existing surface link
            surface_input = output_node.inputs.get("Surface")
            if surface_input:
                for link in tuple(surface_input.links):
                    suspended_links.append(
                        SuspendedOutputLink(node_tree, link.from_socket, link.to_socket)
                    )
                    node_tree.links.remove(link)
                # 4. Connect temporary emission to Surface
                node_tree.links.new(emission.outputs["Emission"], surface_input)

        except Exception:
            # Include the material currently being modified. It has not yet
            # reached the normal append below, but may already have temporary
            # nodes or a suspended Surface link that must be restored.
            current = PreparedPbrMaterial(
                material=material,
                output_node=output_node,
                temporary_nodes=tuple(temp_nodes),
                suspended_links=tuple(suspended_links),
            )
            restore_pbr_channel_extraction((*prepared, current))
            raise

        prepared.append(
            PreparedPbrMaterial(
                material=material,
                output_node=output_node,
                temporary_nodes=tuple(temp_nodes),
                suspended_links=tuple(suspended_links),
            )
        )

    return tuple(prepared)


def restore_pbr_channel_extraction(prepared: tuple[PreparedPbrMaterial, ...]) -> None:
    """Restore all materials to their original state and remove temporary PBR nodes."""
    errors: list[Exception] = []
    for item in reversed(prepared):
        material = item.material
        node_tree = material.node_tree
        if not node_tree:
            continue

        # 1. Remove temporary emission connection from Surface
        try:
            surface_input = item.output_node.inputs.get("Surface")
            if surface_input:
                for link in tuple(surface_input.links):
                    if link.from_node in item.temporary_nodes:
                        node_tree.links.remove(link)
        except Exception as error:
            errors.append(error)

        # 2. Restore suspended original links
        for suspended in item.suspended_links:
            try:
                node_tree.links.new(suspended.from_socket, suspended.to_socket)
            except Exception as error:
                errors.append(error)

        # 3. Remove temporary nodes
        for node in item.temporary_nodes:
            try:
                if node.name in node_tree.nodes:
                    node_tree.nodes.remove(node)
            except Exception as error:
                errors.append(error)

    if errors:
        raise RuntimeError(
            f"Could not fully restore {len(errors)} PBR material change(s)."
        ) from errors[0]
