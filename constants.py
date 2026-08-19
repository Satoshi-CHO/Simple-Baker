"""Shared constants for the Simple Baker add-on."""

ADDON_ID = "simple_baker"
ADDON_NAME = "Simple Baker"

WORKFLOW_SELF = "SELF"
WORKFLOW_SELECTED_TO_ACTIVE = "SELECTED_TO_ACTIVE"

CONNECTION_NODES_ONLY = "NODES_ONLY"
CONNECTION_MATERIAL = "MATERIAL"

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
)

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
    "common_name",
    "output_directory",
    "resolution",
    "file_format",
    "color_depth",
    "connection_mode",
    "create_image_texture_nodes",
    "normal_format",
)
