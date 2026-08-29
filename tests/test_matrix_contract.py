import unittest
import numpy as np
import json
import os
import sys

# Add project path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.project_schemas import (
    CropSettings, FocusRegion, MaskRegion, Matrix3x3, ProjectLayer, ProjectState,
    matrix_identity, matrix_translate, matrix_rotate, matrix_scale,
    matrix_multiply, matrix_inverse, transform_point
)
from backend.pipeline import _output_coordinate_metadata

class TestMatrixContract(unittest.TestCase):
    def test_identity(self):
        m = matrix_identity()
        self.assertEqual(len(m), 9)
        p = transform_point(m, 100, 200)
        self.assertAlmostEqual(p[0], 100.0)
        self.assertAlmostEqual(p[1], 200.0)

    def test_translation(self):
        m = matrix_translate(50, -30)
        p = transform_point(m, 100, 200)
        self.assertAlmostEqual(p[0], 150.0)
        self.assertAlmostEqual(p[1], 170.0)

    def test_rotation_scale_composition(self):
        # Scale 2x then Rotate 90 degrees around origin
        s = matrix_scale(2.0, 2.0)
        r = matrix_rotate(np.pi / 2) # 90 deg
        composed = matrix_multiply(r, s)
        
        # Point (10, 0) -> scale 2x = (20, 0) -> rot 90 = (0, 20)
        p = transform_point(composed, 10, 0)
        self.assertAlmostEqual(p[0], 0.0, places=5)
        self.assertAlmostEqual(p[1], 20.0, places=5)

    def test_round_trip_inverse(self):
        # Tạo ma trận tổng hợp: Translate -> Rotate -> Scale
        t = matrix_translate(120, 450)
        r = matrix_rotate(0.35)
        s = matrix_scale(1.2, 1.2)
        m = matrix_multiply(t, matrix_multiply(r, s))
        
        inv = matrix_inverse(m)
        self.assertIsNotNone(inv)
        
        # Test point
        orig_pt = (250.0, 780.0)
        world_pt = transform_point(m, *orig_pt)
        recovered_pt = transform_point(inv, *world_pt)
        
        self.assertAlmostEqual(recovered_pt[0], orig_pt[0], places=4)
        self.assertAlmostEqual(recovered_pt[1], orig_pt[1], places=4)

    def test_singular_matrix_rejection(self):
        # Ma trận suy biến (det = 0)
        singular_m = [0, 0, 0, 0, 0, 0, 0, 0, 1]
        inv = matrix_inverse(singular_m)
        self.assertIsNone(inv)

    def test_auto_crop_output_mapping_includes_canvas_origin(self):
        output_to_world, world_to_output = _output_coordinate_metadata((-10.5, 20.25, 100, 200), 3, 4)
        self.assertEqual(output_to_world[2], -7.5)
        self.assertEqual(output_to_world[5], 24.25)
        point = transform_point(output_to_world, 12, 9)
        recovered = transform_point(world_to_output, *point)
        np.testing.assert_allclose(recovered, [12, 9], atol=1e-9)

class TestProjectSchema(unittest.TestCase):
    def test_rejects_invalid_compositing_numbers(self):
        for field, value in (("opacity", -0.1), ("opacity", 1.1), ("brightness", float("nan")),
                             ("contrast", float("inf")), ("saturation", -1), ("confidence", 2)):
            kwargs = {field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                ProjectLayer("layer", "source", 1, 1, **kwargs)

    def test_rejects_non_positive_source_dimensions(self):
        with self.assertRaises(ValueError):
            ProjectLayer("layer", "source", 0, 1)

    def test_rejects_invalid_region_numeric_fields(self):
        with self.assertRaises(ValueError):
            FocusRegion("focus", featherWorldPx=float("nan"))
        with self.assertRaises(ValueError):
            MaskRegion("mask", radiusWorld=-1)
        with self.assertRaises(ValueError):
            CropSettings(paddingWorld=float("inf"))

    def test_serialize_deserialize_project(self):
        layer = ProjectLayer(
            id="layer-1",
            sourceId="src-1001",
            sourceWidth=2000,
            sourceHeight=1500,
            sourceToWorld=matrix_translate(100, 200),
            opacity=0.85,
            brightness=1.1,
            contrast=1.05,
            saturation=1.0,
            visible=True,
            locked=False,
            zIndex=0
        )
        proj = ProjectState(
            id="proj-demo",
            version=1,
            revision=1,
            mode="manual",
            layers=[layer]
        )
        
        json_str = proj.to_json()
        restored = ProjectState.from_json(json_str)
        
        self.assertEqual(restored.id, "proj-demo")
        self.assertEqual(restored.revision, 1)
        self.assertEqual(len(restored.layers), 1)
        self.assertEqual(restored.layers[0].sourceId, "src-1001")
        self.assertAlmostEqual(restored.layers[0].opacity, 0.85)
        self.assertAlmostEqual(restored.layers[0].sourceToWorld[2], 100.0) # dx

if __name__ == "__main__":
    unittest.main()
