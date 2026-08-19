"""Creation and controlled update of Simple Baker image data-blocks."""

from __future__ import annotations

from typing import Iterable

import bpy

from ..constants import BAKE_MAPS
from ..models import BakeMapSpec, ImageSpec
from .paths import build_output_path

MANAGED_IMAGE_KEY = "simple_baker_image_key"
MANAGED_IMAGE_FLAG = "simple_baker_managed"

MAP_SPECS = tuple(
    BakeMapSpec(
        key=key,
        setting_name=f"map_{key}",
        bake_type=bake_type,
        suffix=suffix,
        label=key.replace("_", " ").title(),
        color_space="Non-Color" if key in {"ao", "normal", "roughness", "uv"} else "sRGB",
    )
    for key, bake_type, suffix in BAKE_MAPS
)


def selected_map_specs(settings) -> tuple[BakeMapSpec, ...]:
    """Return selected maps in the fixed, user-visible output order."""
    return tuple(spec for spec in MAP_SPECS if getattr(settings, spec.setting_name))


def build_image_specs(settings) -> tuple[ImageSpec, ...]:
    """Describe requested output images without creating Blender data-blocks."""
    return tuple(
        ImageSpec(
            map_spec=map_spec,
            image_name=f"{settings.common_name}_{map_spec.suffix}",
            output_path=build_output_path(
                settings.output_directory,
                settings.common_name,
                map_spec,
                settings.file_format,
            ),
            width=settings.resolution,
            height=settings.resolution,
            file_format=settings.file_format,
            color_depth=settings.color_depth,
        )
        for map_spec in selected_map_specs(settings)
    )


def _managed_image_for_key(image_key: str):
    for image in bpy.data.images:
        if image.get(MANAGED_IMAGE_FLAG) and image.get(MANAGED_IMAGE_KEY) == image_key:
            return image
    return None


def _set_image_color_space(image, color_space: str) -> None:
    """Set a known color space when it is available in this Blender installation."""
    try:
        image.colorspace_settings.name = color_space
    except (TypeError, ValueError):
        # OCIO configurations can omit names such as Non-Color. Keeping Blender's
        # existing setting is safer than failing after creating a new image.
        pass


def create_bake_image(image_spec: ImageSpec):
    """Create an isolated image for one bake attempt.

    Re-baking never writes into the previous managed image.  This makes a
    failed bake recoverable: existing material nodes can keep their original
    image until the new result has both baked and saved successfully.
    """
    is_float = image_spec.color_depth == "32" or image_spec.file_format == "OPEN_EXR"
    image = bpy.data.images.new(
        name=image_spec.image_name,
        width=image_spec.width,
        height=image_spec.height,
        alpha=True,
        float_buffer=is_float,
    )
    image[MANAGED_IMAGE_FLAG] = True
    image[MANAGED_IMAGE_KEY] = image_spec.output_path

    image.filepath_raw = image_spec.output_path
    image.file_format = image_spec.file_format
    _set_image_color_space(image, image_spec.map_spec.color_space)
    return image


def remove_unused_managed_images(image_key: str, keep_image) -> None:
    """Discard superseded internal images once no Blender user references them."""
    for image in tuple(bpy.data.images):
        if (
            image != keep_image
            and image.get(MANAGED_IMAGE_FLAG)
            and image.get(MANAGED_IMAGE_KEY) == image_key
            and image.users == 0
        ):
            bpy.data.images.remove(image)


def create_or_update_bake_images(image_specs: Iterable[ImageSpec]) -> list:
    """Create isolated managed images in output order.

    Kept for callers that need a batch of fresh image targets.
    """
    return [create_bake_image(spec) for spec in image_specs]
