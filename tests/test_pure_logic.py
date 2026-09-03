"""Tests that run with ordinary Python; Blender is not required."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


def _load_pure_module():
    path = Path(__file__).resolve().parents[1] / "services" / "pure.py"
    spec = importlib.util.spec_from_file_location("simple_baker_pure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pure = _load_pure_module()


class FilenameTests(unittest.TestCase):
    def test_sanitizes_portable_filename_stem(self):
        self.assertEqual(pure.sanitize_common_name(' chair:oak? '), "chair_oak_")

    def test_uses_default_for_empty_name(self):
        self.assertEqual(pure.sanitize_common_name("..."), "bake")

    def test_builds_stable_map_filename(self):
        self.assertEqual(pure.output_filename("chair", "normal", "PNG"), "chair_normal.png")

    def test_builds_stable_pbr_filenames(self):
        for suffix in ("base_color", "metallic", "alpha", "smoothness"):
            self.assertEqual(
                pure.output_filename("model", suffix, "PNG"),
                f"model_{suffix}.png",
            )

    def test_builds_stable_pack_filenames(self):
        for suffix in ("orm", "metallic_roughness", "mask", "base_color_alpha"):
            self.assertEqual(
                pure.output_filename("model", suffix, "PNG"),
                f"model_{suffix}.png",
            )

    def test_builds_stable_advanced_pbr_filenames(self):
        for suffix in (
            "transmission_weight",
            "specular_ior_level",
            "coat_weight",
            "coat_roughness",
            "sheen_weight",
            "subsurface_weight",
        ):
            self.assertEqual(
                pure.output_filename("model", suffix, "PNG"),
                f"model_{suffix}.png",
            )

    def test_rejects_unknown_image_format(self):
        with self.assertRaises(KeyError):
            pure.output_extension("UNKNOWN")

    def test_limits_color_depths_by_file_format(self):
        self.assertEqual(pure.supported_color_depths("PNG"), ("8", "16"))
        self.assertEqual(pure.supported_color_depths("TARGA"), ("8",))
        self.assertEqual(pure.supported_color_depths("OPEN_EXR"), ("16", "32"))
        self.assertFalse(pure.is_supported_color_depth("PNG", "32"))
        self.assertFalse(pure.is_supported_color_depth("TARGA", "16"))


if __name__ == "__main__":
    unittest.main()
