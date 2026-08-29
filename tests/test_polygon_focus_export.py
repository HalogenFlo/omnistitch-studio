import unittest
import numpy as np
import cv2
from backend.project_schemas import ProjectState, ProjectLayer, FocusRegion, ExclusionStroke, KeepRegion, CropSettings
from backend.patch_inspector import inspect_patches_at_world_region, extract_native_patch_image
from backend.manual_export import render_manual_wsi_composite

class TestPolygonFocusAndExport(unittest.TestCase):
    def setUp(self):
        self.layer1 = ProjectLayer(
            id="layer_1",
            sourceId="test1.png",
            sourceWidth=200,
            sourceHeight=200,
            sourceToWorld=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            sourcePath="test1.png"
        )
        self.project = ProjectState(
            id="test_project",
            layers=[self.layer1]
        )

    def test_polygon_focus_region_schema(self):
        poly_pts = [[10.0, 10.0], [50.0, 10.0], [40.0, 60.0]]
        fr = FocusRegion(id="fr_1", shapeType="polygon", pointsWorld=poly_pts, selectedLayerId="layer_1")
        self.assertEqual(fr.shapeType, "polygon")
        self.assertEqual(len(fr.pointsWorld), 3)
        self.assertEqual(fr.boundingRect, [10.0, 10.0, 40.0, 50.0])

    def test_legacy_world_rect_migration(self):
        fr = FocusRegion(id="fr_legacy", worldRect=[10.0, 20.0, 100.0, 50.0], selectedLayerId="layer_1")
        self.assertEqual(fr.shapeType, "rectangle")
        self.assertEqual(len(fr.pointsWorld), 4)
        self.assertEqual(fr.pointsWorld[0], [10.0, 20.0])
        self.assertEqual(fr.pointsWorld[2], [110.0, 70.0])

    def test_exclusion_stroke_schema(self):
        stroke = ExclusionStroke(id="strk_1", pointsWorld=[[10, 10], [20, 20]], radiusWorld=15.0, operation="exclude")
        self.assertEqual(stroke.operation, "exclude")
        self.assertEqual(stroke.radiusWorld, 15.0)

    def test_keep_region_and_crop_settings(self):
        kr = KeepRegion(shapeType="polygon", pointsWorld=[[0, 0], [100, 0], [100, 100], [0, 100]])
        self.assertEqual(kr.boundingRect, [0.0, 0.0, 100.0, 100.0])
        cs = CropSettings(trimOutputBounds=True, paddingWorld=10.0)
        self.assertTrue(cs.trimOutputBounds)
        self.assertEqual(cs.paddingWorld, 10.0)

if __name__ == '__main__':
    unittest.main()
