import os
import tempfile
import unittest

import cv2
import numpy as np

from backend.manual_export import render_manual_wsi_composite
from backend.project_schemas import CropRegion, CropSettings, MaskRegion, ProjectLayer, ProjectState


class TestCropMaskExport(unittest.TestCase):
    def test_restore_and_half_open_crop_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "white.png")
            cv2.imwrite(path, np.full((5, 5, 3), 255, dtype=np.uint8))
            layer = ProjectLayer("layer", "source", 5, 5, sourcePath=path)
            masks = [
                MaskRegion("exclude", pointsWorld=[[2, 2]], radiusWorld=2, operation="exclude", order=0),
                MaskRegion("restore", pointsWorld=[[2, 2]], radiusWorld=1, operation="restore", order=1),
            ]
            crop = CropRegion(pointsWorld=[[0.2, 0.2], [3.7, 0.2], [3.7, 3.7], [0.2, 3.7]])
            project = ProjectState("crop", layers=[layer], maskRegions=masks, cropRegion=crop,
                                   cropSettings=CropSettings(trimOutputBounds=True))
            image, valid_mask, metadata = render_manual_wsi_composite(project, temp_dir)
            self.assertEqual(image.shape[:2], (4, 4))
            self.assertEqual(metadata["cropBoundsWorld"], [0, 0, 4, 4])
            self.assertEqual(metadata["outputPixelToWorld"][2:6:3], [0.0, 0.0])
            self.assertEqual(int(valid_mask[2, 2]), 255)
            self.assertEqual(int(valid_mask[1, 1]), 0)


if __name__ == "__main__":
    unittest.main()
