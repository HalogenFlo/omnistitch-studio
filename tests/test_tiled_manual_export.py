import os
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np
from PIL import Image

from backend.manual_export import (
    export_manual_project,
    export_manual_project_tiled,
    render_manual_wsi_composite,
)
from backend.io_utils import read_image_region as real_read_image_region
from backend.project_schemas import (
    CropRegion,
    CropSettings,
    FocusRegion,
    MaskRegion,
    ProjectLayer,
    ProjectState,
)


class TestTiledManualExport(unittest.TestCase):
    def _fixture(self, root):
        height, width = 96, 128
        base = np.full((height, width, 4), [20, 210, 40, 255], dtype=np.uint8)
        selected = np.full((height, width, 4), [240, 30, 20, 0], dtype=np.uint8)
        selected[:, :110, 3] = 180
        base_path = os.path.join(root, "base.png")
        selected_path = os.path.join(root, "selected.png")
        cv2.imwrite(base_path, cv2.cvtColor(base, cv2.COLOR_RGBA2BGRA))
        cv2.imwrite(selected_path, cv2.cvtColor(selected, cv2.COLOR_RGBA2BGRA))
        selected_layer = ProjectLayer("selected", "selected", width, height, sourcePath=selected_path, zIndex=0)
        base_layer = ProjectLayer("base", "base", width, height, sourcePath=base_path, zIndex=1)
        focus = FocusRegion(
            "focus",
            shapeType="polygon",
            pointsWorld=[[28, 12], [105, 18], [112, 80], [24, 84]],
            selectedLayerId="selected",
            featherWorldPx=5,
            order=0,
            geometryRevision=1,
        )
        masks = [
            MaskRegion("exclude", pointsWorld=[[45, 20], [78, 76]], radiusWorld=7, operation="exclude", order=0),
            MaskRegion("restore", pointsWorld=[[61, 45], [68, 55]], radiusWorld=3, operation="restore", order=1),
        ]
        crop = CropRegion(pointsWorld=[[5.2, 3.2], [120.7, 3.2], [120.7, 90.4], [5.2, 90.4]])
        return ProjectState(
            "tiled",
            layers=[selected_layer, base_layer],
            focusRegions=[focus],
            maskRegions=masks,
            cropRegion=crop,
            cropSettings=CropSettings(trimOutputBounds=True),
        )

    def test_tiled_output_matches_full_renderer_with_bounded_tiles(self):
        with tempfile.TemporaryDirectory() as root:
            project = self._fixture(root)
            expected_image, expected_mask, expected_meta = render_manual_wsi_composite(project, root)
            source_roi_pixels = []

            def tracked_region(path, box):
                region = real_read_image_region(path, box)
                source_roi_pixels.append(region.shape[0] * region.shape[1])
                return region

            with mock.patch("backend.manual_export.read_image_region", side_effect=tracked_region):
                result = export_manual_project_tiled(
                    project,
                    root,
                    root,
                    output_name="bounded",
                    memory_budget_bytes=8 * 1024 * 1024,
                    tile_size=64,
                )
            with Image.open(result["outputFile"]) as image:
                actual_image = np.array(image)
            actual_mask = cv2.imread(os.path.join(root, result["trainingMask"]), cv2.IMREAD_GRAYSCALE)
            self.assertEqual(actual_image.shape, expected_image.shape)
            self.assertLessEqual(int(np.max(np.abs(actual_image.astype(np.int16) - expected_image.astype(np.int16)))), 1)
            np.testing.assert_array_equal(actual_mask, expected_mask)
            self.assertEqual(result["cropInfo"]["outputPixelToWorld"], expected_meta["outputPixelToWorld"])
            stats = result["cropInfo"]["tiledRender"]
            self.assertGreater(stats["tileCount"], 1)
            self.assertLessEqual(stats["maxEstimatedWorkingBytes"], stats["memoryBudgetBytes"])
            self.assertLess(stats["maxSourceRoiPixels"], 128 * 96)
            self.assertEqual(stats["maxSourceRoiPixels"], max(source_roi_pixels))
            self.assertLessEqual(stats["maxExpandedTilePixels"], (64 + 2 * stats["halo"]) ** 2)
            self.assertTrue(os.path.isfile(result["dziPath"]))

    def test_large_companion_mask_switches_to_tiled_tiff_and_png_is_capped(self):
        with tempfile.TemporaryDirectory() as root:
            project = self._fixture(root)
            api_result = export_manual_project(
                project, root, root, output_name="api_tiff", export_format="tiff", background_mode="transparent"
            )
            self.assertTrue(api_result["outputFile"].endswith(".tiff"))
            self.assertEqual(api_result["cropInfo"]["renderMode"], "tiled")
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_STREAM_PNG_PIXELS": "1"}):
                result = export_manual_project_tiled(
                    project,
                    root,
                    root,
                    output_name="tiff_mask",
                    memory_budget_bytes=8 * 1024 * 1024,
                    tile_size=64,
                )
                self.assertTrue(result["trainingMask"].endswith(".tif"))
                self.assertEqual(result["cropInfo"]["companionMaskFormat"], "tif")
                with self.assertRaisesRegex(ValueError, "Hãy chọn TIFF/BigTIFF"):
                    export_manual_project(project, root, root, output_name="too_large_png", export_format="png")

    def test_tiled_failure_keeps_existing_publication(self):
        with tempfile.TemporaryDirectory() as root:
            project = self._fixture(root)
            output_path = os.path.join(root, "stable.tif")
            with open(output_path, "wb") as stream:
                stream.write(b"stable")
            with mock.patch(
                "backend.manual_export.generate_dzi_pyramid_bounded",
                side_effect=RuntimeError("forced DZI failure"),
            ):
                with self.assertRaises(RuntimeError):
                    export_manual_project_tiled(
                        project,
                        root,
                        root,
                        output_name="stable",
                        memory_budget_bytes=8 * 1024 * 1024,
                        tile_size=64,
                    )
            with open(output_path, "rb") as stream:
                self.assertEqual(stream.read(), b"stable")
            self.assertFalse(os.path.exists(os.path.join(root, "stable_dzi")))

    def test_tiled_preflight_rejects_dimensions_tiles_and_low_disk(self):
        with tempfile.TemporaryDirectory() as root:
            project = self._fixture(root)
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_TILED_DIMENSION": "100"}):
                with self.assertRaisesRegex(ValueError, "giới hạn chiều"):
                    export_manual_project_tiled(project, root, root, output_name="dimension", memory_budget_bytes=8 * 1024 * 1024)
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_TILED_PIXELS": "100"}):
                with self.assertRaisesRegex(ValueError, "pixels"):
                    export_manual_project_tiled(project, root, root, output_name="pixels", memory_budget_bytes=8 * 1024 * 1024)
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_TILED_TILES": "1"}):
                with self.assertRaisesRegex(ValueError, "tiles"):
                    export_manual_project_tiled(project, root, root, output_name="tiles", memory_budget_bytes=8 * 1024 * 1024, tile_size=64)
            disk = mock.Mock(free=1)
            with mock.patch("backend.manual_export.shutil.disk_usage", return_value=disk):
                with self.assertRaisesRegex(OSError, "dung lượng"):
                    export_manual_project_tiled(project, root, root, output_name="disk", memory_budget_bytes=8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
