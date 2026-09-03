"""Channel packing presets and compositing services for Simple Baker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import bpy
import numpy as np

from ..models import BakeMapSpec, ImageSpec
from .paths import build_output_path


@dataclass(frozen=True)
class PackChannelSource:
    """Source channel specification for one packed RGBA component."""

    source_map_key: str | None
    source_channel: int = 0
    invert: bool = False
    default_value: float = 1.0


@dataclass(frozen=True)
class PackPresetSpec:
    """Definition of one multi-channel packed texture preset."""

    key: str
    setting_name: str
    suffix: str
    label: str
    color_space: str
    channels: tuple[PackChannelSource, PackChannelSource, PackChannelSource, PackChannelSource]

    @property
    def required_map_keys(self) -> tuple[str, ...]:
        keys = []
        for ch in self.channels:
            if ch.source_map_key and ch.source_map_key not in keys:
                keys.append(ch.source_map_key)
        return tuple(keys)


PACK_PRESET_SPECS: tuple[PackPresetSpec, ...] = (
    PackPresetSpec(
        key="orm",
        setting_name="pack_orm",
        suffix="orm",
        label="ORM (Occlusion, Roughness, Metallic)",
        color_space="Non-Color",
        channels=(
            PackChannelSource(source_map_key="ao", source_channel=0, invert=False, default_value=1.0),
            PackChannelSource(source_map_key="roughness", source_channel=0, invert=False, default_value=0.5),
            PackChannelSource(source_map_key="metallic", source_channel=0, invert=False, default_value=0.0),
            PackChannelSource(source_map_key=None, source_channel=0, invert=False, default_value=1.0),
        ),
    ),
    PackPresetSpec(
        key="gltf",
        setting_name="pack_gltf",
        suffix="metallic_roughness",
        label="glTF (Metallic, Roughness)",
        color_space="Non-Color",
        channels=(
            PackChannelSource(source_map_key=None, source_channel=0, invert=False, default_value=1.0),
            PackChannelSource(source_map_key="roughness", source_channel=0, invert=False, default_value=0.5),
            PackChannelSource(source_map_key="metallic", source_channel=0, invert=False, default_value=0.0),
            PackChannelSource(source_map_key=None, source_channel=0, invert=False, default_value=1.0),
        ),
    ),
    PackPresetSpec(
        key="unity_mask",
        setting_name="pack_unity_mask",
        suffix="mask",
        label="Unity Mask (Metallic, AO, Detail, Smoothness)",
        color_space="Non-Color",
        channels=(
            PackChannelSource(source_map_key="metallic", source_channel=0, invert=False, default_value=0.0),
            PackChannelSource(source_map_key="ao", source_channel=0, invert=False, default_value=1.0),
            PackChannelSource(source_map_key=None, source_channel=0, invert=False, default_value=0.0),
            PackChannelSource(source_map_key="smoothness", source_channel=0, invert=False, default_value=0.5),
        ),
    ),
    PackPresetSpec(
        key="base_color_alpha",
        setting_name="pack_base_color_alpha",
        suffix="base_color_alpha",
        label="Base Color + Alpha",
        color_space="sRGB",
        channels=(
            PackChannelSource(source_map_key="base_color", source_channel=0, invert=False, default_value=1.0),
            PackChannelSource(source_map_key="base_color", source_channel=1, invert=False, default_value=1.0),
            PackChannelSource(source_map_key="base_color", source_channel=2, invert=False, default_value=1.0),
            PackChannelSource(source_map_key="alpha", source_channel=0, invert=False, default_value=1.0),
        ),
    ),
)


def selected_pack_specs(settings) -> tuple[PackPresetSpec, ...]:
    """Return all packing presets enabled in current settings."""
    return tuple(spec for spec in PACK_PRESET_SPECS if getattr(settings, spec.setting_name, False))


def required_source_map_keys(settings) -> tuple[str, ...]:
    """Return all unique individual map keys required by selected pack presets."""
    required: list[str] = []
    for preset in selected_pack_specs(settings):
        for key in preset.required_map_keys:
            if key not in required:
                required.append(key)
    return tuple(required)


def build_pack_image_specs(settings) -> tuple[ImageSpec, ...]:
    """Describe requested packed output images."""
    specs: list[ImageSpec] = []
    for preset in selected_pack_specs(settings):
        map_spec = BakeMapSpec(
            key=preset.key,
            setting_name=preset.setting_name,
            bake_type="EMIT",
            suffix=preset.suffix,
            label=preset.label,
            color_space=preset.color_space,
        )
        specs.append(
            ImageSpec(
                map_spec=map_spec,
                image_name=f"{settings.common_name}_{preset.suffix}",
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
        )
    return tuple(specs)


def composite_packed_image(
    source_images: Mapping[str, bpy.types.Image],
    preset: PackPresetSpec,
    destination_image: bpy.types.Image,
) -> None:
    """Composite individual source map channels into destination_image using NumPy."""
    width, height = destination_image.size
    num_pixels = width * height
    out_pixels = np.ones((num_pixels, 4), dtype=np.float32)

    cached_buffers: dict[str, np.ndarray] = {}

    for c_idx, ch_source in enumerate(preset.channels):
        if ch_source.source_map_key is None:
            out_pixels[:, c_idx] = ch_source.default_value
            continue

        src_image = source_images.get(ch_source.source_map_key)
        if src_image is None:
            message = bpy.app.translations.pgettext(
                "Required source map is unavailable: {map}"
            ).format(map=ch_source.source_map_key)
            raise ValueError(message)

        if ch_source.source_map_key not in cached_buffers:
            buf = np.empty(num_pixels * 4, dtype=np.float32)
            src_image.pixels.foreach_get(buf)
            cached_buffers[ch_source.source_map_key] = buf.reshape((num_pixels, 4))

        src_grid = cached_buffers[ch_source.source_map_key]
        ch_val = src_grid[:, ch_source.source_channel]
        if ch_source.invert:
            ch_val = 1.0 - ch_val
        out_pixels[:, c_idx] = ch_val

    destination_image.pixels.foreach_set(out_pixels.ravel())
    destination_image.update()
