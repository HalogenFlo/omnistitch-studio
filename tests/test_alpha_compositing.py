import os
import tempfile
import unittest

import cv2
import numpy as np

from backend.io_utils import read_image
from backend.blending import FastStreamingBlender
from backend.manual_export import render_manual_wsi_composite
from backend.project_schemas import FocusRegion, ProjectLayer, ProjectState


class TestAlphaCompositing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_rgba(self, name, rgba):
        path = os.path.join(self.temp_dir.name, name)
        cv2.imwrite(path, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        return path

    def _layer(self, layer_id, path, z_index=0):
        return ProjectLayer(layer_id, layer_id, 2, 2, sourcePath=path, zIndex=z_index)

    def test_decoder_preserves_rgba_and_rgb_order(self):
        rgba = np.array([[[250, 20, 3, 77]]], dtype=np.uint8)
        decoded = read_image(self._write_rgba("rgba.png", rgba))
        self.assertEqual(decoded.shape, (1, 1, 4))
        np.testing.assert_array_equal(decoded, rgba)

    def test_two_half_alpha_layers_use_premultiplied_over(self):
        red = np.full((2, 2, 4), [255, 0, 0, 128], dtype=np.uint8)
        blue = np.full((2, 2, 4), [0, 0, 255, 128], dtype=np.uint8)
        project = ProjectState("alpha", layers=[
            self._layer("red", self._write_rgba("red.png", red), 0),
            self._layer("blue", self._write_rgba("blue.png", blue), 1),
        ])
        image, mask, _ = render_manual_wsi_composite(project, self.temp_dir.name)
        self.assertAlmostEqual(int(image[0, 0, 3]), 192, delta=1)
        self.assertAlmostEqual(int(image[0, 0, 0]), 85, delta=2)
        self.assertAlmostEqual(int(image[0, 0, 2]), 170, delta=2)
        self.assertEqual(int(mask[0, 0]), 255)

    def test_focus_respects_source_alpha_and_stale_revision(self):
        green = np.full((2, 2, 4), [0, 255, 0, 255], dtype=np.uint8)
        red = np.full((2, 2, 4), [255, 0, 0, 0], dtype=np.uint8)
        red[:, 0, 3] = 255
        base = self._layer("base", self._write_rgba("base.png", green), 1)
        selected = self._layer("selected", self._write_rgba("selected.png", red), 0)
        selected.visible = False
        region = FocusRegion("focus", pointsWorld=[[0, 0], [2, 0], [2, 2], [0, 2]],
                             selectedLayerId="selected", featherWorldPx=0, geometryRevision=2)
        project = ProjectState("focus", geometryRevision=2, layers=[base, selected], focusRegions=[region])
        selected.visible = True
        image, _, _ = render_manual_wsi_composite(project, self.temp_dir.name)
        self.assertGreater(image[0, 0, 0], 240)
        self.assertGreater(image[0, 1, 1], 240)
        region.geometryRevision = 1
        stale_image, _, _ = render_manual_wsi_composite(project, self.temp_dir.name)
        self.assertGreater(stale_image[0, 0, 1], 240)

    def test_streaming_blender_preserves_fractional_alpha(self):
        rgba = np.full((4, 4, 4), [255, 0, 0, 128], dtype=np.uint8)
        blender = FastStreamingBlender((4, 4), background_mode="transparent", focus_stacking=False)
        blender.accumulate_tile(rgba, np.eye(3))
        image, coverage = blender.finalize()
        self.assertAlmostEqual(int(image[1, 1, 3]), 128, delta=1)
        self.assertGreater(int(image[1, 1, 0]), 250)
        self.assertEqual(int(coverage[1, 1]), 128)


if __name__ == "__main__":
    unittest.main()
