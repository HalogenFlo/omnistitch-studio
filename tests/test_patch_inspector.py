import unittest
import numpy as np
import cv2
import tempfile
import os
import sys
import json
import threading
import time
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.project_schemas import ProjectState, ProjectLayer, matrix_translate, matrix_scale
from backend import patch_inspector
from backend.patch_inspector import inspect_patches_at_world_rect, extract_native_patch_image
from backend.io_utils import save_tiff

class TestPatchInspector(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
        # Tạo 1 ảnh nét (chứa nhiều chi tiết sắc cạnh)
        sharp_img = np.zeros((400, 400, 3), dtype=np.uint8)
        for i in range(0, 400, 20):
            cv2.rectangle(sharp_img, (i, i), (i + 10, i + 10), (255, 255, 255), -1)
            cv2.line(sharp_img, (i, 0), (i, 400), (200, 100, 50), 2)
            
        # Tạo 1 ảnh mờ (Gaussian blur của ảnh nét)
        blur_img = cv2.GaussianBlur(sharp_img, (25, 25), 0)

        self.sharp_path = os.path.join(self.temp_dir, "sharp.png")
        self.blur_path = os.path.join(self.temp_dir, "blur.png")
        
        cv2.imwrite(self.sharp_path, cv2.cvtColor(sharp_img, cv2.COLOR_RGB2BGR))
        cv2.imwrite(self.blur_path, cv2.cvtColor(blur_img, cv2.COLOR_RGB2BGR))

    def test_sharp_vs_blur_score(self):
        # 2 layer chồng lên nhau ở cùng tọa độ (0, 0)
        layer_sharp = ProjectLayer(
            id="layer_sharp",
            sourceId="sharp.png",
            sourceWidth=400,
            sourceHeight=400,
            sourceToWorld=matrix_translate(100, 100),
            sourcePath=self.sharp_path
        )
        layer_blur = ProjectLayer(
            id="layer_blur",
            sourceId="blur.png",
            sourceWidth=400,
            sourceHeight=400,
            sourceToWorld=matrix_translate(100, 100),
            sourcePath=self.blur_path
        )

        project = ProjectState(
            id="test_proj",
            layers=[layer_sharp, layer_blur]
        )

        # Inspect vùng worldRect [150, 150, 100, 100]
        res = inspect_patches_at_world_rect(
            project_state=project,
            world_rect=[150, 150, 100, 100],
            output_size=128,
            workspace_root=self.temp_dir
        )

        self.assertEqual(len(res["patches"]), 2)
        # Ảnh nét phải có điểm sharpness cao hơn ảnh mờ
        patch_sharp = next(p for p in res["patches"] if p["layerId"] == "layer_sharp")
        patch_blur = next(p for p in res["patches"] if p["layerId"] == "layer_blur")
        
        self.assertGreater(patch_sharp["sharpness"], patch_blur["sharpness"])
        self.assertEqual(res["sharpestLayerId"], "layer_sharp")

    def test_non_overlapping_region(self):
        layer_sharp = ProjectLayer(
            id="layer_sharp",
            sourceId="sharp.png",
            sourceWidth=400,
            sourceHeight=400,
            sourceToWorld=matrix_translate(100, 100),
            sourcePath=self.sharp_path
        )
        project = ProjectState(
            id="test_proj",
            layers=[layer_sharp]
        )

        # Vùng ở rất xa [2000, 2000, 100, 100]
        res = inspect_patches_at_world_rect(
            project_state=project,
            world_rect=[2000, 2000, 100, 100],
            output_size=128
        )
        self.assertEqual(len(res["patches"]), 0)
        self.assertIsNone(res["sharpestLayerId"])

    def test_visibility_and_source_alpha_filter_coverage(self):
        rgba = np.full((100, 100, 4), [255, 0, 0, 0], dtype=np.uint8)
        rgba[:, :50, 3] = 255
        alpha_path = os.path.join(self.temp_dir, "alpha.png")
        cv2.imwrite(alpha_path, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        visible = ProjectLayer("visible", "alpha", 100, 100, sourcePath=alpha_path)
        hidden = ProjectLayer("hidden", "alpha", 100, 100, sourcePath=alpha_path, visible=False)
        result = inspect_patches_at_world_rect(
            ProjectState("alpha_project", layers=[visible, hidden]), [0, 0, 100, 100], 100, workspace_root=self.temp_dir
        )
        self.assertEqual([patch["layerId"] for patch in result["patches"]], ["visible"])
        self.assertAlmostEqual(result["patches"][0]["validCoverage"], 0.5, delta=0.03)
        json.dumps(result)

    def test_fractional_alpha_is_weighted_for_coverage_and_scoring(self):
        rgba = np.full((100, 100, 4), [255, 0, 0, 1], dtype=np.uint8)
        alpha_path = os.path.join(self.temp_dir, "faint.png")
        cv2.imwrite(alpha_path, cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        layer = ProjectLayer("faint", "faint", 100, 100, sourcePath=alpha_path)
        result = inspect_patches_at_world_rect(
            ProjectState("faint_project", layers=[layer]), [0, 0, 100, 100], 100, workspace_root=self.temp_dir
        )
        self.assertEqual(result["patches"], [])

    def test_cache_deduplicates_concurrent_decodes_and_counts_once(self):
        patch_inspector._IMAGE_CACHE.clear()
        patch_inspector._CACHE_BYTES = 0
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        calls = []

        def delayed_read(_):
            calls.append(True)
            time.sleep(0.05)
            return image

        with mock.patch.object(patch_inspector, "get_image_metadata", return_value={"width": 16, "height": 16}), \
             mock.patch.object(patch_inspector, "read_image", side_effect=delayed_read):
            threads = [threading.Thread(target=patch_inspector._get_cached_image, args=("same.png",)) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(patch_inspector._CACHE_BYTES, image.nbytes)

    def test_patch_source_decode_guard_runs_before_decode(self):
        patch_inspector._IMAGE_CACHE.clear()
        patch_inspector._CACHE_BYTES = 0
        with mock.patch.object(patch_inspector, "_MAX_SOURCE_DECODE_PIXELS", 100), \
             mock.patch.object(patch_inspector, "get_image_metadata", return_value={"width": 11, "height": 10}), \
             mock.patch.object(patch_inspector, "read_image") as decode:
            with self.assertRaisesRegex(MemoryError, "decode guard"):
                patch_inspector._get_cached_image("large.png")
        decode.assert_not_called()

    def test_native_sampling_uses_inverse_source_transform(self):
        layer = ProjectLayer("scaled", "sharp", 400, 400, sourceToWorld=matrix_scale(2, 2), sourcePath=self.sharp_path)
        result = extract_native_patch_image(layer, [[0, 0], [20, 0], [20, 10], [0, 10]], max_pixels=10000,
                                            workspace_root=self.temp_dir)
        self.assertEqual((result["width"], result["height"]), (10, 5))
        self.assertEqual(result["sampling_scale"], 1.0)

    def test_native_sampling_honors_small_pixel_cap(self):
        layer = ProjectLayer("scaled", "sharp", 400, 400, sourcePath=self.sharp_path)
        result = extract_native_patch_image(
            layer, [[0, 0], [100, 0], [100, 100], [0, 100]], max_pixels=10,
            workspace_root=self.temp_dir
        )
        self.assertLessEqual(result["width"] * result["height"], 10)
        self.assertTrue(result["is_resolution_limited"])

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
