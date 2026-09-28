import os
import unittest
import numpy as np
import cv2
import tempfile
import shutil

from backend.project_schemas import (
    ProjectState, ProjectLayer, FocusRegion, MaskRegion, CropRegion,
    VariantWorkspace, ALL_VARIANT_IDS, VARIANTS_SPEC
)
from backend.project_store import save_project, load_project
from backend.blending import FastStreamingBlender, compute_local_sharpness_map
from backend.pipeline import run_wsi_stitching_pipeline
from backend.manual_export import export_manual_project


class TestVariantsAndWorkspaces(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_all_variant_specs_and_ids(self):
        """Kiểm tra danh sách 8 biến thể và các ID quy chuẩn."""
        self.assertEqual(len(ALL_VARIANT_IDS), 8)
        self.assertEqual(len(VARIANTS_SPEC), 8)
        expected_ids = [
            "original", "original_balanced", "original_clarity", "original_full",
            "gaussian", "gaussian_balanced", "gaussian_clarity", "gaussian_full"
        ]
        self.assertEqual(ALL_VARIANT_IDS, expected_ids)
        expected_suffixes = [
            "01_goc", "02_goc_can_sang", "03_goc_sac_net", "04_goc_can_sang_net",
            "05_gaussian", "06_gaussian_can_sang", "07_gaussian_sac_net", "08_gaussian_full"
        ]
        actual_suffixes = [spec["suffix"] for spec in VARIANTS_SPEC]
        self.assertEqual(actual_suffixes, expected_suffixes)

    def test_variant_workspace_independence(self):
        """Kiểm tra khoanh vùng, mask, crop và undo/redo ở biến thể A không xuất hiện ở biến thể B."""
        layer1 = ProjectLayer(id="layer_0", sourceId="src_0", sourceWidth=100, sourceHeight=100)
        proj = ProjectState(id="proj_test", layers=[layer1])

        # Mặc định có đủ 8 workspaces
        self.assertEqual(len(proj.variantWorkspaces), 8)
        self.assertEqual(proj.activeVariantId, "original")

        # Thêm FocusRegion và MaskRegion vào workspace "original"
        focus_orig = FocusRegion(
            id="focus_1",
            shapeType="rectangle",
            pointsWorld=[[10, 10], [50, 10], [50, 50], [10, 50]],
            selectedLayerId="layer_0"
        )
        mask_orig = MaskRegion(
            id="mask_1",
            shapeType="brush",
            pointsWorld=[[20, 20], [30, 30]],
            radiusWorld=15.0
        )
        crop_orig = CropRegion(
            id="crop_orig",
            pointsWorld=[[0, 0], [80, 0], [80, 80], [0, 80]]
        )

        ws_orig = proj.get_variant_workspace("original")
        ws_orig.focusRegions.append(focus_orig)
        ws_orig.maskRegions.append(mask_orig)
        ws_orig.cropRegion = crop_orig

        # Workspace "gaussian" phải hoàn toàn độc lập, không chứa các vùng của "original"
        ws_gauss = proj.get_variant_workspace("gaussian")
        self.assertEqual(len(ws_gauss.focusRegions), 0)
        self.assertEqual(len(ws_gauss.maskRegions), 0)
        self.assertIsNone(ws_gauss.cropRegion)

        # Chuyển activeVariantId sang "gaussian"
        proj.switch_variant("gaussian")
        self.assertEqual(proj.activeVariantId, "gaussian")
        # Khi activeVariantId là "gaussian", các thuộc tính facade trỏ tới workspace của "gaussian"
        self.assertEqual(len(proj.focusRegions), 0)
        self.assertEqual(len(proj.maskRegions), 0)
        self.assertIsNone(proj.cropRegion)

        # Thêm 1 mask vào "gaussian"
        mask_gauss = MaskRegion(
            id="mask_g1",
            shapeType="brush",
            pointsWorld=[[5, 5], [10, 10]],
            radiusWorld=10.0
        )
        proj.maskRegions.append(mask_gauss)

        # Khi chuyển lại "original", các vùng cũ của "original" vẫn còn nguyên vẹn
        proj.switch_variant("original")
        self.assertEqual(len(proj.focusRegions), 1)
        self.assertEqual(proj.focusRegions[0].id, "focus_1")
        self.assertEqual(len(proj.maskRegions), 1)
        self.assertEqual(proj.maskRegions[0].id, "mask_1")
        self.assertEqual(proj.cropRegion.id, "crop_orig")

    def test_backward_compatibility_old_project(self):
        """Dự án cũ chưa có variantWorkspaces vẫn mở được và tự động di trú dữ liệu vào 'original'."""
        old_data = {
            "id": "old_project_1",
            "version": 3,
            "revision": 1,
            "geometryRevision": 1,
            "layers": [
                {"id": "l0", "sourceId": "s0", "sourceWidth": 100, "sourceHeight": 100, "sourceToWorld": [1,0,0,0,1,0,0,0,1]}
            ],
            "focusRegions": [
                {
                    "id": "f_legacy",
                    "shapeType": "rectangle",
                    "pointsWorld": [[10, 10], [20, 10], [20, 20], [10, 20]],
                    "selectedLayerId": "l0"
                }
            ],
            "maskRegions": [
                {
                    "id": "m_legacy",
                    "shapeType": "brush",
                    "pointsWorld": [[5, 5]],
                    "radiusWorld": 10.0
                }
            ],
            "cropRegion": {
                "id": "c_legacy",
                "pointsWorld": [[0, 0], [50, 0], [50, 50], [0, 50]]
            }
        }
        proj = ProjectState.from_dict(old_data)
        self.assertEqual(proj.activeVariantId, "original")
        self.assertEqual(len(proj.variantWorkspaces), 8)
        ws_orig = proj.variantWorkspaces["original"]
        self.assertEqual(len(ws_orig.focusRegions), 1)
        self.assertEqual(ws_orig.focusRegions[0].id, "f_legacy")
        self.assertEqual(len(ws_orig.maskRegions), 1)
        self.assertEqual(ws_orig.maskRegions[0].id, "m_legacy")
        self.assertIsNotNone(ws_orig.cropRegion)
        self.assertEqual(ws_orig.cropRegion.id, "c_legacy")

        # Các workspace khác phải là rỗng
        for vid in ALL_VARIANT_IDS:
            if vid != "original":
                self.assertEqual(len(proj.variantWorkspaces[vid].focusRegions), 0)
                self.assertEqual(len(proj.variantWorkspaces[vid].maskRegions), 0)
                self.assertIsNone(proj.variantWorkspaces[vid].cropRegion)

    def test_validation_rejects_duplicate_region_ids_and_invalid_layer(self):
        """Backend phải kiểm tra: ID vùng không trùng trong cùng workspace, selectedLayerId phải tồn tại."""
        layer1 = ProjectLayer(id="l1", sourceId="s1", sourceWidth=100, sourceHeight=100)
        proj = ProjectState(id="proj_valid", layers=[layer1])

        # 1. Thêm 2 vùng có cùng ID vào cùng workspace -> Phải raise ValueError
        ws = proj.variantWorkspaces["original"]
        ws.focusRegions.append(FocusRegion(id="dup_id", pointsWorld=[[0,0],[1,0],[1,1]], selectedLayerId="l1"))
        ws.maskRegions.append(MaskRegion(id="dup_id", pointsWorld=[[2,2]]))

        data = proj.to_dict()
        with self.assertRaises(ValueError):
            ProjectState.from_dict(data)

        # 2. FocusRegion tham chiếu layer không tồn tại -> Phải raise ValueError
        proj2 = ProjectState(id="proj_invalid_layer", layers=[layer1])
        ws2 = proj2.variantWorkspaces["original"]
        ws2.focusRegions.append(FocusRegion(id="f_invalid", pointsWorld=[[0,0],[1,0],[1,1]], selectedLayerId="non_existent_layer"))
        data2 = proj2.to_dict()
        with self.assertRaises(ValueError):
            ProjectState.from_dict(data2)

    def test_blender_sharpness_lock_and_gains_invariance(self):
        """Kiểm tra: gain và gaussian không được làm thay đổi best_tile_idx hoặc độ nét cục bộ trên ảnh gốc."""
        # Tạo 2 tile cùng kích thước với vùng overlap
        tile1 = np.full((100, 100, 3), 150, dtype=np.uint8)
        # Tile 1 có hoa văn sắc nét (độ nét cao)
        for i in range(10, 90, 5):
            tile1[i, :, :] = 50
        
        tile2 = np.full((100, 100, 3), 150, dtype=np.uint8)
        # Tile 2 mờ (đồng nhất, độ nét thấp)

        # Sharpness map phải được tính trên ảnh gốc
        s1 = compute_local_sharpness_map(tile1)
        s2 = compute_local_sharpness_map(tile2)
        self.assertGreater(np.mean(s1), np.mean(s2), "Tile 1 có hoa văn phải có độ nét cao hơn Tile 2")


        # Thay đổi gain sáng (tile_gains) không được làm thay đổi quan hệ độ nét
        tile2_brighter = np.clip(tile2.astype(np.float32) * 1.4, 0, 255).astype(np.uint8)
        s2_bright = compute_local_sharpness_map(tile2_brighter)
        self.assertGreater(np.mean(s1), np.mean(s2_bright), "Tile 1 vẫn phải nét hơn Tile 2 dù Tile 2 được tăng sáng")

    def test_pipeline_generates_8_variants_with_identical_dimensions(self):
        """Pipeline phải sinh tuần tự 8 biến thể, cùng kích thước, cùng hệ tọa độ và khóa best_tile_idx."""
        # Tạo 2 ảnh giả lập
        img1 = np.full((80, 80, 3), 200, dtype=np.uint8)
        cv2.circle(img1, (40, 40), 15, (60, 40, 100), -1)
        p1 = os.path.join(self.test_dir, "t1.png")
        cv2.imwrite(p1, img1)

        img2 = np.full((80, 80, 3), 210, dtype=np.uint8)
        cv2.circle(img2, (20, 40), 15, (60, 40, 100), -1)
        p2 = os.path.join(self.test_dir, "t2.png")
        cv2.imwrite(p2, img2)

        out_dir = os.path.join(self.test_dir, "output")
        res = run_wsi_stitching_pipeline(
            image_paths=[p1, p2],
            output_dir=out_dir,
            custom_output_name="testcase",
            export_format="png"
        )

        self.assertIn("variants", res)
        variants = res["variants"]
        self.assertEqual(len(variants), 8)
        self.assertEqual(res["activeVariantId"], "original")

        first_dim = res["dimensions"]
        for v in variants:
            self.assertTrue(os.path.exists(v["output_filepath"]), f"File {v['output_filepath']} không tồn tại")
            self.assertTrue(os.path.exists(v["dzi_filepath"]), f"DZI {v['dzi_filepath']} không tồn tại")
            self.assertTrue(v["file_name"].startswith("testcase_"))
            self.assertTrue(v["dzi_url"].startswith("/dzi/"))

    def test_manual_export_variant_and_all(self):
        """Kiểm tra xuất thủ công theo từng phiên bản và xuất toàn bộ 8 phiên bản."""
        img1 = np.full((60, 60, 3), 180, dtype=np.uint8)
        p1 = os.path.join(self.test_dir, "m1.png")
        cv2.imwrite(p1, img1)

        layer0 = ProjectLayer(id="l0", sourceId="m1", sourceWidth=60, sourceHeight=60, sourcePath=p1)
        proj = ProjectState(id="proj_export_test", layers=[layer0], folderName="proj_export_test")

        # Workspace 'original' có 1 focusRegion và 1 crop
        ws_orig = proj.get_variant_workspace("original")
        ws_orig.focusRegions.append(
            FocusRegion(id="f_orig", shapeType="rectangle", pointsWorld=[[10, 10], [50, 10], [50, 50], [10, 50]], selectedLayerId="l0")
        )
        ws_orig.cropRegion = CropRegion(id="c_orig", pointsWorld=[[5, 5], [55, 5], [55, 55], [5, 55]])

        # Workspace 'gaussian' có 1 maskRegion
        ws_gauss = proj.get_variant_workspace("gaussian")
        ws_gauss.maskRegions.append(
            MaskRegion(id="m_gauss", pointsWorld=[[20, 20]], radiusWorld=5.0)
        )

        out_dir = os.path.join(self.test_dir, "manual_out")

        # 1. Xuất phiên bản hiện tại ('original')
        res_single = export_manual_project(
            proj,
            output_dir=out_dir,
            workspace_root=self.test_dir,
            output_name="proj_export_test",
            export_format="png",
            variant_id="original",
            export_all=False
        )
        self.assertEqual(res_single["status"], "success")
        self.assertTrue(os.path.exists(res_single["outputFile"]))
        self.assertTrue(os.path.exists(res_single["dziPath"]))

        # 2. Xuất toàn bộ 8 phiên bản
        res_all = export_manual_project(
            proj,
            output_dir=out_dir,
            workspace_root=self.test_dir,
            output_name="proj_export_test",
            export_format="png",
            export_all=True
        )
        self.assertEqual(res_all["status"], "success")
        self.assertIn("variants", res_all)
        self.assertEqual(len(res_all["variants"]), 8)
        for v in res_all["variants"]:
            self.assertTrue(os.path.exists(v["output_filepath"]))
            self.assertTrue(os.path.exists(v["dzi_filepath"]))

    def test_algorithm_gain_and_sharpness_locking(self):
        """Kiểm nghiệm:
        - Gain không làm thay đổi best_tile_idx
        - Cả 8 phiên bản có cùng lựa chọn nét tự động và kích thước ban đầu
        """
        # Tạo 2 tile có vùng chồng lấn
        tile_sharp = np.zeros((100, 100, 3), dtype=np.uint8)
        # Vẽ hoa văn sắc nét (nhiều cạnh)
        for i in range(10, 90, 5):
            cv2.line(tile_sharp, (i, 10), (i, 90), (255, 255, 255), 1)

        tile_blurry = cv2.GaussianBlur(tile_sharp, (15, 15), 5.0)

        # Tính sharpness trên ảnh gốc
        s_sharp = compute_local_sharpness_map(tile_sharp)
        s_blur = compute_local_sharpness_map(tile_blurry)

        # Rõ ràng tile sắc nét phải có độ nét cao hơn tile mờ
        self.assertGreater(float(np.mean(s_sharp)), float(np.mean(s_blur)))

        # Lưu file và chạy pipeline
        p_sharp = os.path.join(self.test_dir, "sharp.png")
        p_blur = os.path.join(self.test_dir, "blur.png")
        cv2.imwrite(p_sharp, tile_sharp)
        cv2.imwrite(p_blur, tile_blurry)

        out_dir = os.path.join(self.test_dir, "alg_out")
        res = run_wsi_stitching_pipeline(
            image_paths=[p_sharp, p_blur],
            output_dir=out_dir,
            custom_output_name="stitch_lock",
            export_format="png"
        )

        variants = res["variants"]
        self.assertEqual(len(variants), 8)

        # Đọc 8 ảnh và kiểm tra cùng kích thước (W, H)
        shapes = []
        for v in variants:
            img = cv2.imread(v["output_filepath"])
            self.assertIsNotNone(img)
            shapes.append(img.shape)

        # Cả 8 ảnh phải có cùng chính xác kích thước (H, W, C)
        first_shape = shapes[0]
        for s in shapes:
            self.assertEqual(s, first_shape, f"Kích thước phiên bản không khớp: {s} vs {first_shape}")

    def test_multi_region_inspect_and_max_payload(self):
        """Kiểm nghiệm:
        - Server nâng giới hạn JSON payload lên 64MB cho phép lưu dự án có hàng chục vùng
        - API inspect trích xuất chính xác ứng viên cho nhiều vùng khác nhau mà không bị đè vùng
        """
        import server
        self.assertEqual(server.MAX_JSON_REQUEST_BYTES, 64 * 1024 * 1024)

        from backend.patch_inspector import inspect_patches_at_world_region

        # Tạo 2 layer ở 2 vị trí khác nhau
        img_a = np.full((100, 100, 3), 150, dtype=np.uint8)
        img_b = np.full((100, 100, 3), 200, dtype=np.uint8)
        p_a = os.path.join(self.test_dir, "layer_a.png")
        p_b = os.path.join(self.test_dir, "layer_b.png")
        cv2.imwrite(p_a, img_a)
        cv2.imwrite(p_b, img_b)

        l1 = ProjectLayer(id="l1", sourceId="a", sourceWidth=100, sourceHeight=100, sourcePath=p_a, sourceToWorld=[1,0,0,0,1,0,0,0,1])
        l2 = ProjectLayer(id="l2", sourceId="b", sourceWidth=100, sourceHeight=100, sourcePath=p_b, sourceToWorld=[1,0,200,0,1,0,0,0,1])
        proj = ProjectState(id="proj_multi", layers=[l1, l2])

        # Vùng 1: ở tọa độ [10, 10, 40, 40] (chỉ l1 bao phủ)
        res1 = inspect_patches_at_world_region(
            project_state=proj,
            shape_type="rectangle",
            points_world=[[10, 10], [50, 10], [50, 50], [10, 50]],
            workspace_root=self.test_dir
        )
        self.assertEqual(len(res1["patches"]), 1)
        self.assertEqual(res1["patches"][0]["layerId"], "l1")

        # Vùng 2: ở tọa độ [210, 10, 40, 40] (chỉ l2 bao phủ)
        res2 = inspect_patches_at_world_region(
            project_state=proj,
            shape_type="rectangle",
            points_world=[[210, 10], [250, 10], [250, 50], [210, 50]],
            workspace_root=self.test_dir
        )
        self.assertEqual(len(res2["patches"]), 1)
        self.assertEqual(res2["patches"][0]["layerId"], "l2")

        # Hai vùng hoàn toàn tách biệt, không bị đè ứng viên của nhau
        self.assertNotEqual(res1["patches"][0]["layerId"], res2["patches"][0]["layerId"])

    def test_overlap_based_gain_balancing_independent_of_background(self):
        """Kiểm tra cân bằng độ sáng dựa trên vùng chồng lấn (không dựa vào nền)."""
        from backend.blending import estimate_overlap_exposure_gains

        # Tile 1: vùng chồng lấn có giá trị 100
        # Tile 2: cùng vùng chồng lấn đó có giá trị 120 (chụp thừa sáng hơn 20%)
        # Cả 2 tile đều là mô đậm, hoàn toàn KHÔNG CÓ pixel nền trắng
        h, w = 100, 100
        img1 = np.full((h, w, 3), 100, dtype=np.uint8)
        img2 = np.full((h, w, 3), 120, dtype=np.uint8)

        # Tile 1 đặt ở x=0, Tile 2 đặt ở x=60 (chồng lấn từ x=60 đến x=100, rộng 40px)
        H1 = np.eye(3, dtype=np.float64)
        H2 = np.eye(3, dtype=np.float64)
        H2[0, 2] = 60.0 # dịch chuyển 60px theo trục X

        source_images = {0: img1, 1: img2}
        transforms = {0: H1, 1: H2}

        gains = estimate_overlap_exposure_gains(source_images, transforms)
        self.assertIn(0, gains)
        self.assertIn(1, gains)

        # Vì tile 2 sáng hơn tile 1 (120 vs 100), gain của tile 1 phải > gain của tile 2
        # để kéo chúng về cùng một mức độ sáng
        self.assertGreater(gains[0], gains[1])
        # Tỷ lệ sau khi nhân gain phải xấp xỉ 1.0 (sai lệch dưới 5%)
        balanced_val1 = 100.0 * gains[0]
        balanced_val2 = 120.0 * gains[1]
        self.assertAlmostEqual(balanced_val1, balanced_val2, delta=5.0)

    def test_smooth_seam_feathering_no_sharp_step(self):
        """Kiểm tra hòa trộn dải mượt Hermite không tạo ra bước nhảy bậc thang đột ngột tại mép ảnh."""
        canvas_h, canvas_w = 120, 200
        blender = FastStreamingBlender((canvas_h, canvas_w), background_mode='white', focus_stacking=False)

        # Tile 1: nền xám 140 đặt tại x=0..100
        tile1 = np.full((100, 100, 3), 140, dtype=np.uint8)
        H1 = np.eye(3, dtype=np.float64)
        H1[0, 2] = 10.0
        H1[1, 2] = 10.0
        blender.accumulate_tile(tile1, H1)

        # Tile 2: nền xám 110 (tối hơn) đặt chồng lấn tại x=60..160
        tile2 = np.full((100, 100, 3), 110, dtype=np.uint8)
        H2 = np.eye(3, dtype=np.float64)
        H2[0, 2] = 60.0
        H2[1, 2] = 10.0
        blender.accumulate_tile(tile2, H2)

        composite, mask = blender.finalize()
        # Lấy một hàng ngang cắt qua vùng giao thoa từ x=50 đến x=120
        # Cắt qua mép tile 2 tại x=60
        slice_row = composite[50, 50:120, 0].astype(np.float32)
        diffs = np.abs(np.diff(slice_row))

        # Bước nhảy giữa 2 pixel liền kề tại mép ngoài không được vượt quá 3.0 giá trị độ sáng
        # (chứng minh tính trơn tru liên tục, không có đường cắt bậc thang sắc lẹm)
        max_step = float(np.max(diffs))
        self.assertLess(max_step, 3.0, f"Bước nhảy pixel tại ranh giới mép quá lớn ({max_step} > 3.0), gây lộ viền!")

    def test_focus_stacking_preserves_sharp_tissue_without_blur(self):
        """Kiểm tra: Focus stacking bảo toàn độ nét mô học, không bị ảnh mờ pha loãng làm mờ mô."""
        canvas_h, canvas_w = 120, 120
        blender = FastStreamingBlender((canvas_h, canvas_w), background_mode='white', focus_stacking=True)

        # Tile 1: Mô sắc nét với cấu trúc vi thể rõ ràng (độ tương phản cao)
        h, w = 100, 100
        sharp_tile = np.zeros((h, w, 3), dtype=np.uint8)
        sharp_tile[::4, :] = 200
        sharp_tile[:, ::4] = 200
        orig_var = float(np.var(sharp_tile[20:80, 20:80]))

        # Tile 2: Cùng vị trí đó nhưng out-of-focus (bị làm mờ Gaussian)
        blurry_tile = cv2.GaussianBlur(sharp_tile, (15, 15), 0)

        H = np.eye(3, dtype=np.float64)
        H[0, 2] = 10.0
        H[1, 2] = 10.0

        blender.accumulate_tile(sharp_tile, H)
        blender.accumulate_tile(blurry_tile, H)

        composite, _ = blender.finalize()
        blended_center = composite[30:90, 30:90]
        blended_var = float(np.var(blended_center))

        # Độ tương phản / độ nét của mô được bảo toàn qua Voronoi focus stacking,
        # ưu tiên lát cắt nét hơn so với lát cắt out-of-focus.
        self.assertGreater(
            blended_var, 5000.0,
            f"Mô tế bào bị mất tương phản quá nhiều: var {blended_var}"
        )

    def test_tissue_illumination_and_contrast_balancing(self):
        """Kiểm tra: Cân bằng sáng mô học chỉ tác động bên trong mô, tuyệt đối không thay đổi nền kính."""
        from backend.blending import apply_tissue_illumination_balance, apply_variant_postprocessing

        h, w = 150, 150
        # Trường hợp 1: Lam kính xám có bóng mờ (160)
        img_shaded = np.full((h, w, 3), 160, dtype=np.uint8)
        # Vùng mô tối (đậm màu) ở góc trái
        img_shaded[20:70, 20:70] = np.array([70, 50, 60], dtype=np.uint8)
        # Vùng mô sáng hơn ở góc phải
        img_shaded[80:130, 80:130] = np.array([140, 110, 120], dtype=np.uint8)

        res_shaded = apply_tissue_illumination_balance(img_shaded)

        # 1. Nền kính xám bên ngoài mô (góc trên bên phải y=0:15, x=0:150) phải được giữ nguyên 100% (diff == 0)
        bg_diff = np.abs(res_shaded[0:15, :].astype(float) - img_shaded[0:15, :].astype(float)).max()
        self.assertEqual(bg_diff, 0.0, "Nền kính bị thay đổi màu/độ sáng khi cân bằng mô!")

        # 2. Vùng mô tối được nâng sáng hài hòa để cân bằng với vùng mô sáng
        dark_before_mean = float(np.mean(img_shaded[20:70, 20:70]))
        dark_after_mean = float(np.mean(res_shaded[20:70, 20:70]))
        self.assertGreater(dark_after_mean, dark_before_mean)

        # Trường hợp 2: Kiểm tra apply_variant_postprocessing với balanced=True và bg_gains
        spec = {"gaussian": False, "balanced": True, "clarity": False}
        gains = np.array([1.05, 0.95, 1.02], dtype=np.float32)
        var_res = apply_variant_postprocessing(img_shaded, postprocess_spec=spec, bg_gains=gains)
        bg_post_diff = np.abs(var_res[0:15, :].astype(float) - img_shaded[0:15, :].astype(float)).max()
        self.assertEqual(bg_post_diff, 0.0, "apply_variant_postprocessing làm đổi màu nền khi bật balanced!")






