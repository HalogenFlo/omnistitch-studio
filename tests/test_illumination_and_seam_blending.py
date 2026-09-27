import unittest
import numpy as np
import cv2

from backend.blending import FastStreamingBlender, equalize_tile_illumination


class TestIlluminationAndSeamBlending(unittest.TestCase):
    def test_equalize_tile_illumination_normalizes_background(self):
        # Tạo 2 tile ảnh kính hiển vi với độ sáng nền khác nhau
        # Tile 1: nền hơi tối (RGB 180)
        tile1 = np.full((100, 100, 3), 180, dtype=np.uint8)
        # Tile 2: nền sáng hơn (RGB 215)
        tile2 = np.full((100, 100, 3), 215, dtype=np.uint8)

        source_images = {0: tile1, 1: tile2}
        eq_images = equalize_tile_illumination(source_images)

        mean1 = np.mean(eq_images[0], axis=(0, 1))
        mean2 = np.mean(eq_images[1], axis=(0, 1))

        # Sau khi đồng bộ, độ chênh lệch màu nền giữa 2 tile phải < 3 đơn vị
        diff = np.max(np.abs(mean1 - mean2))
        self.assertLess(diff, 3.0, f"Độ chênh lệch màu nền sau khi cân bằng quá lớn: {diff}")

    def test_blender_eliminates_white_seam_border(self):
        # Tạo 2 tile xám kích thước 200x200
        canvas_h, canvas_w = 200, 300
        blender = FastStreamingBlender((canvas_h, canvas_w), background_mode='white', focus_stacking=False)

        tile1 = np.full((200, 200, 3), 170, dtype=np.uint8)
        tile2 = np.full((200, 200, 3), 170, dtype=np.uint8)

        # Tile 1 đặt tại x=0, Tile 2 đặt tại x=100 (vùng overlap từ x=100 đến x=200)
        H1 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        H2 = np.array([[1.0, 0.0, 100.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)

        blender.accumulate_tile(tile1, H1)
        blender.accumulate_tile(tile2, H2)

        result, mask = blender.finalize()

        # Kiểm tra vùng ranh giới quanh x=100 và x=200
        # Không được có bất kỳ pixel nào bị bùng nổ lên màu trắng [255, 255, 255] bên trong vùng ảnh
        overlap_region = result[:, 80:220]
        white_pixels = np.all(overlap_region == 255, axis=-1)
        self.assertEqual(np.count_nonzero(white_pixels), 0, "Xuất hiện viền trắng bóc bên trong vùng chồng lấn!")

        # Giá trị pixel tại ranh giới x=100 và x=200 phải bằng đúng màu xám 170
        self.assertAlmostEqual(float(result[100, 100, 0]), 170.0, delta=2.0)
        self.assertAlmostEqual(float(result[100, 200, 0]), 170.0, delta=2.0)

    def test_blender_adaptive_seam_smooth_transition(self):
        # Tạo 2 tile có màu hơi chênh nhẹ (165 và 175)
        canvas_h, canvas_w = 200, 300
        blender = FastStreamingBlender((canvas_h, canvas_w), background_mode='white', focus_stacking=False)

        tile1 = np.full((200, 200, 3), 165, dtype=np.uint8)
        tile2 = np.full((200, 200, 3), 175, dtype=np.uint8)

        H1 = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        H2 = np.array([[1.0, 0.0, 100.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)

        blender.accumulate_tile(tile1, H1)
        blender.accumulate_tile(tile2, H2)

        result, _ = blender.finalize()

        # Kiểm tra sự biến thiên pixel theo trục X từ 100 đến 200: phải đơn điệu tăng hoặc chuyển tiếp mượt mà, không có bước nhảy đột ngột
        row = result[100, 100:200, 0].astype(np.float32)
        diffs = np.abs(np.diff(row))
        # Không có bước nhảy nào giữa 2 pixel kề nhau vượt quá 3 đơn vị
        max_jump = np.max(diffs)
    def test_gaussian_smoothing_toggle(self):
        # Kiểm tra switch bật/tắt Gaussian smoothing
        tile1 = np.full((120, 120, 3), 190, dtype=np.uint8)
        tile1[0:30, 0:30] = 130 # Đốm tối ở góc
        tile2 = np.full((120, 120, 3), 195, dtype=np.uint8)
        tile2[0:30, 0:30] = 135
        source_images = {0: tile1, 1: tile2}

        # Bật Gaussian
        res_gaussian = equalize_tile_illumination(source_images, enable_gaussian_smoothing=True)
        # Tắt Gaussian (chỉ chuẩn hóa mức sáng trung bình toàn cục)
        res_no_gaussian = equalize_tile_illumination(source_images, enable_gaussian_smoothing=False)

        self.assertIsNotNone(res_gaussian[0])
        self.assertIsNotNone(res_no_gaussian[0])
        # Khi bật Gaussian, các pixel ở góc được scale theo flat-field 2D khác với khi tắt Gaussian
        diff_corner = abs(float(res_gaussian[0][10, 10, 0]) - float(res_no_gaussian[0][10, 10, 0]))
        self.assertGreater(diff_corner, 0.5, "Khi bật Gaussian smoothing, flat-field correction phải điều chỉnh góc sáng")

    def test_cellular_clarity_enhancement(self):
        canvas_h, canvas_w = 100, 100
        blender_normal = FastStreamingBlender((canvas_h, canvas_w), focus_stacking=False, enhance_clarity=False)
        blender_clarity = FastStreamingBlender((canvas_h, canvas_w), focus_stacking=False, enhance_clarity=True)

        tile = np.full((100, 100, 3), 150, dtype=np.uint8)
        # Mô phỏng một nhân tế bào đậm ở giữa
        cv2.circle(tile, (50, 50), 10, (50, 30, 90), -1)

        H = np.eye(3, dtype=np.float64)
        blender_normal.accumulate_tile(tile, H)
        blender_clarity.accumulate_tile(tile, H)

        res_norm, _ = blender_normal.finalize()
        res_clar, _ = blender_clarity.finalize()

        # Với unsharp mask vi phân, nhân tế bào sẽ sắc nét và tương phản hơn với nền
        diff_norm = abs(float(res_norm[50, 50, 0]) - float(res_norm[50, 70, 0]))
        diff_clar = abs(float(res_clar[50, 50, 0]) - float(res_clar[50, 70, 0]))
    def test_compensate_overlap_exposure_balances_brightness(self):
        # Tạo 2 tile chồng lấn 50%: Tile 1 tối (100), Tile 2 sáng (200)
        from backend.blending import compensate_overlap_exposure
        tile1 = np.full((100, 100, 3), 100, dtype=np.uint8)
        tile2 = np.full((100, 100, 3), 200, dtype=np.uint8)

        images = {0: tile1, 1: tile2}
        transforms = {
            0: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            1: np.array([[1.0, 0.0, 50.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        }

        balanced_images = compensate_overlap_exposure(images, transforms)

        # Kiểm tra sau khi cân bằng: độ lệch độ sáng giữa 2 tile tại vùng overlap giảm rõ rệt
        mean1 = np.mean(balanced_images[0][:, 50:100])
        mean2 = np.mean(balanced_images[1][:, 0:50])
        diff = abs(mean1 - mean2)
        self.assertLess(diff, 10.0, f"Độ lệch sáng sau khi cân bằng overlap vẫn còn quá lớn: {diff}")

    def test_tissue_mask_and_defringe_filter(self):
        from backend.blending import get_tissue_mask, apply_defringe_filter
        # Ảnh có nền trắng 240 và nhân tế bào 80
        img = np.full((50, 50, 3), 240, dtype=np.uint8)
        img[10:30, 10:30] = 80
        mask = get_tissue_mask(img, threshold=215)
        self.assertEqual(mask[20, 20], 1)
        self.assertEqual(mask[0, 0], 0)

    def test_solve_tissue_specific_gains_balances_overlap(self):
        from backend.blending import solve_tissue_specific_gains
        # Tạo 2 tile chồng lấn: Tile 0 tối hơn (120), Tile 1 sáng hơn (180), đều có vùng mô (giá trị 80 và 120)
        tile0 = np.full((100, 100, 3), 120, dtype=np.uint8)
        tile0[20:80, 20:80] = 80
        tile1 = np.full((100, 100, 3), 180, dtype=np.uint8)
        tile1[20:80, 20:80] = 120

        images = {0: tile0, 1: tile1}
        transforms = {
            0: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            1: np.array([[1.0, 0.0, 50.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        }

        gains = solve_tissue_specific_gains(images, transforms, canvas_w=150, canvas_h=100)
        self.assertIn(0, gains)
        self.assertIn(1, gains)
        # Tile 0 tối hơn nên gain của tile 0 phải lớn hơn gain của tile 1
        self.assertGreater(float(gains[0][0]), float(gains[1][0]))

    def test_blend_multiband_voronoi_produces_sharp_seamless_composite(self):
        from backend.blending import blend_multiband_voronoi
        tile0 = np.full((100, 100, 3), 160, dtype=np.uint8)
        tile1 = np.full((100, 100, 3), 160, dtype=np.uint8)

        images = {0: tile0, 1: tile1}
        transforms = {
            0: np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            1: np.array([[1.0, 0.0, 50.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        }
        gains = {0: np.ones(3, dtype=np.float32), 1: np.ones(3, dtype=np.float32)}

        blended, mask = blend_multiband_voronoi(images, gains, transforms, canvas_w=150, canvas_h=100, num_bands=3)
        self.assertEqual(blended.shape, (100, 150, 3))
        # Không có pixel nào bị lỗi hoặc bùng nổ
        self.assertAlmostEqual(float(blended[50, 75, 0]), 160.0, delta=2.0)
        self.assertGreater(np.count_nonzero(mask), 1000)


if __name__ == '__main__':
    unittest.main()


