"""Shared constants for the Simple Baker add-on."""

# Extensions are imported below ``bl_ext.<repository>`` while a source checkout
# is imported as ``simple_baker``. The package owning this module is the exact
# identifier Blender uses for Add-on Preferences in either installation form.
ADDON_ID = __package__
ADDON_NAME = "Simple Baker"

WORKFLOW_SELF = "SELF"
WORKFLOW_SELECTED_TO_ACTIVE = "SELECTED_TO_ACTIVE"

NORMAL_FORMAT_OPENGL = "OPENGL"
NORMAL_FORMAT_DIRECTX = "DIRECTX"
NORMAL_FORMAT_CUSTOM = "CUSTOM"

BAKE_MAPS = (
    ("combined", "COMBINED", "combined"),
    ("ao", "AO", "ao"),
    ("shadow", "SHADOW", "shadow"),
    ("normal", "NORMAL", "normal"),
    ("uv", "UV", "uv"),
    ("roughness", "ROUGHNESS", "roughness"),
    ("emit", "EMIT", "emit"),
    ("environment", "ENVIRONMENT", "environment"),
    ("diffuse", "DIFFUSE", "color"),
    ("glossy", "GLOSSY", "glossy"),
    ("transmission", "TRANSMISSION", "transmission"),
    ("base_color", "EMIT", "base_color"),
    ("metallic", "EMIT", "metallic"),
    ("alpha", "EMIT", "alpha"),
    ("smoothness", "EMIT", "smoothness"),
    ("transmission_weight", "EMIT", "transmission_weight"),
    ("specular_ior_level", "EMIT", "specular_ior_level"),
    ("coat_weight", "EMIT", "coat_weight"),
    ("coat_roughness", "EMIT", "coat_roughness"),
    ("sheen_weight", "EMIT", "sheen_weight"),
    ("subsurface_weight", "EMIT", "subsurface_weight"),
)

PBR_MAP_KEYS = (
    "base_color",
    "metallic",
    "alpha",
    "smoothness",
    "transmission_weight",
    "specular_ior_level",
    "coat_weight",
    "coat_roughness",
    "sheen_weight",
    "subsurface_weight",
)

ADVANCED_PBR_MAP_KEYS = (
    "transmission_weight",
    "specular_ior_level",
    "coat_weight",
    "coat_roughness",
    "sheen_weight",
    "subsurface_weight",
)

PACK_PRESETS = (
    ("orm", "pack_orm", "orm", "ORM (Occlusion, Roughness, Metallic)"),
    ("gltf", "pack_gltf", "metallic_roughness", "glTF (Metallic, Roughness)"),
    ("unity_mask", "pack_unity_mask", "mask", "Unity Mask (Metallic, AO, Detail, Smoothness)"),
    ("base_color_alpha", "pack_base_color_alpha", "base_color_alpha", "Base Color + Alpha"),
)

PACK_PRESET_KEYS = tuple(item[0] for item in PACK_PRESETS)

PERSISTED_FIELDS = (
    "workflow",
    "map_combined",
    "map_ao",
    "map_shadow",
    "map_normal",
    "map_uv",
    "map_roughness",
    "map_emit",
    "map_environment",
    "map_diffuse",
    "map_glossy",
    "map_transmission",
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
    "pack_orm",
    "pack_gltf",
    "pack_unity_mask",
    "pack_base_color_alpha",
    "common_name",
    "output_directory",
    "resolution",
    "file_format",
    "color_depth",
    "create_image_texture_nodes",
    "normal_format",
)
