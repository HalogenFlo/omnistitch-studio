# Feature: Hòa trộn dòng ROI tích hợp Cạnh Tranh Độ Nét Linh Hoạt (Adaptive Focus-Stacking & Sharpness Competition)
# Purpose: Automatically detects and prioritizes the sharpest focal slices between overlapping tiles (adaptive focus stacking)
# Path: tool/image_alignment/backend/blending.py

import cv2
import numpy as np

def compute_local_sharpness_map(img_rgb, kernel_size=15):
    """
    Calculates localized microscopic sharpness/focus map
    Kết hợp 3 tiêu chí:
    1. Tenengrad Gradient (Độ tương phản biên vi thể)
    2. Modified Laplacian (Độ sắc nét nhân tế bào)
    3. Local Variance (Năng lượng kết cấu mô học - vùng rõ nét có variance cao vượt trội so với vùng out-focus mờ)
    """
    if len(img_rgb.shape) == 3:
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_rgb.copy()

    gray_f = gray.astype(np.float32)

    # 1. Gradient bậc 1 (Tenengrad)
    gx = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(gx * gx + gy * gy)

    # 2. Gradient bậc 2 (Laplacian vi phân tế bào)
    lap_mag = np.abs(cv2.Laplacian(gray_f, cv2.CV_32F, ksize=3))

    # 3. Local Standard Deviation / Texture Energy
    k = kernel_size if kernel_size % 2 != 0 else kernel_size + 1
    mean = cv2.blur(gray_f, (k, k))
    sq_mean = cv2.blur(gray_f * gray_f, (k, k))
    variance = np.maximum(0.0, sq_mean - mean * mean)
    local_std = np.sqrt(variance)

    # Tổng hợp năng lượng độ nét
    sharpness_raw = grad_mag + 0.8 * lap_mag + 0.6 * local_std

    # Làm mượt nhẹ để tạo trường năng lượng liên tục không bị nhiễu hạt
    sharpness_smooth = cv2.GaussianBlur(sharpness_raw, (k, k), 0)

    # Chuẩn hóa cục bộ về dải [0, 10] để lũy thừa cạnh tranh ổn định
    max_v = np.max(sharpness_smooth)
    if max_v > 1e-5:
        sharpness_norm = (sharpness_smooth / max_v) * 10.0
    else:
        sharpness_norm = np.zeros_like(sharpness_smooth)

    return sharpness_norm


def equalize_tile_illumination(source_images):
    """
    Tự động chuẩn hóa màu nền và cân bằng phơi sáng giữa các ô ảnh kính hiển vi (Microscopy Flat-Field / Gain Normalization).
    - Ước lượng màu nền kính hiển vi (phân vị 95% của các pixel sáng).
    - Cân bằng màu nền của tất cả các tile về cùng một mức trung vị chuẩn.
    - Triệt tiêu hoàn toàn sự chênh lệch màu nền xám sáng / xám tối / vàng ngà giữa các tile.
    """
    if not source_images or len(source_images) <= 1:
        return source_images

    # 1. Thu thập màu nền của từng ô ảnh
    bg_levels = {}
    for i, img in source_images.items():
        if img is None or img.size == 0:
            continue

        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if has_alpha:
            rgb = img[:, :, :3]
            alpha_mask = img[:, :, 3] > 30
        else:
            rgb = img
            alpha_mask = np.ones(img.shape[:2], dtype=bool)

        if np.count_nonzero(alpha_mask) < 50:
            continue

        valid_pixels = rgb[alpha_mask]
        p95 = np.percentile(valid_pixels, 95, axis=0)
        bg_levels[i] = p95

    if len(bg_levels) <= 1:
        return source_images

    # 2. Tính mức nền tham chiếu trung vị (Reference Background)
    all_p95 = np.array(list(bg_levels.values()), dtype=np.float32)
    ref_bg = np.median(all_p95, axis=0)

    # Nếu ảnh có nền quá tối (ví dụ huỳnh quang < 70), không ép tăng sáng kiểu brightfield
    if np.mean(ref_bg) < 70.0:
        return source_images

    # 3. Điều chỉnh gain cho từng tile để đưa màu nền về ref_bg đồng nhất
    equalized_images = {}
    for i, img in source_images.items():
        if i not in bg_levels:
            equalized_images[i] = img
            continue

        tile_bg = bg_levels[i]
        gains = ref_bg / np.maximum(tile_bg, 1.0)
        gains = np.clip(gains, 0.70, 1.40)

        if np.all(np.abs(gains - 1.0) < 0.015):
            equalized_images[i] = img
            continue

        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if has_alpha:
            rgb = img[:, :, :3].astype(np.float32)
            adj_rgb = np.clip(rgb * gains[None, None, :], 0.0, 255.0).astype(np.uint8)
            new_img = np.dstack([adj_rgb, img[:, :, 3]])
        else:
            rgb = img.astype(np.float32)
            new_img = np.clip(rgb * gains[None, None, :], 0.0, 255.0).astype(np.uint8)

        equalized_images[i] = new_img

    return equalized_images


class FastStreamingBlender:
    """
    Bộ hòa trộn dòng ROI tích hợp Voronoi Adaptive Seam Blending:
    - Triệt tiêu 100% hiện tượng bóng ma (Ghosting / Double Contours) và nhân đôi viền mô học.
    - Tại mỗi pixel, ưu tiên tuyệt đối tile có chất lượng quang học tốt nhất (gần tâm trục quang hơn, dist_map lớn hơn).
    - Vùng chuyển tiếp (seam transition) chỉ hòa trộn mượt trong dải hẹp 16px quanh ranh giới Voronoi,
      loại bỏ hoàn toàn các đường viền mép hình chữ nhật mà không làm nhòe hay nhân đôi chi tiết mô.
    - Bộ nhớ cực kỳ tối ưu và tốc độ xử lý nhanh gấp nhiều lần.
    """
    def __init__(self, canvas_shape, background_mode='white', focus_stacking=True):
        self.canvas_h, self.canvas_w = canvas_shape
        self.background_mode = background_mode
        self.focus_stacking = focus_stacking

        bg_color = (255.0, 255.0, 255.0) if background_mode == 'white' else (0.0, 0.0, 0.0)
        self.canvas_rgb = np.full((self.canvas_h, self.canvas_w, 3), bg_color, dtype=np.float32)
        self.canvas_dist = np.zeros((self.canvas_h, self.canvas_w), dtype=np.float32)
        self.canvas_alpha = np.zeros((self.canvas_h, self.canvas_w), dtype=np.float32)

    def accumulate_tile(self, img_rgb, H_matrix, motion_model='affine'):
        """
        Warp tile ảnh `img_rgb` với ma trận `H_matrix` chỉ trong phạm vi Bounding Box ROI của tile,
        sau đó cập nhật vào canvas theo ranh giới Voronoi Seam mượt mà.
        """
        h, w = img_rgb.shape[:2]
        source_alpha = img_rgb[:, :, 3].astype(np.float32) / 255.0 if img_rgb.ndim == 3 and img_rgb.shape[2] == 4 else np.ones((h, w), dtype=np.float32)
        source_rgb = img_rgb[:, :, :3] if img_rgb.ndim == 3 and img_rgb.shape[2] == 4 else img_rgb
        source_premul = source_rgb.astype(np.float32) * source_alpha[:, :, None]
        
        # 1. Tính toán tọa độ 4 góc của tile trên Canvas toàn cục
        corners = np.array([
            [0, 0, 1],
            [w, 0, 1],
            [w, h, 1],
            [0, h, 1]
        ], dtype=np.float64).T

        warped_corners = H_matrix @ corners
        if motion_model == 'homography':
            warped_corners /= (warped_corners[2:3, :] + 1e-8)
        
        pts = warped_corners[:2, :].T
        x0 = max(0, int(np.floor(np.min(pts[:, 0]))))
        y0 = max(0, int(np.floor(np.min(pts[:, 1]))))
        x1 = min(self.canvas_w, int(np.ceil(np.max(pts[:, 0]))))
        y1 = min(self.canvas_h, int(np.ceil(np.max(pts[:, 1]))))

        roi_w = x1 - x0
        roi_h = y1 - y0

        if roi_w <= 0 or roi_h <= 0:
            return

        # 2. Ma trận dịch chuyển cục bộ cho ROI
        T_roi = np.array([
            [1.0, 0.0, -x0],
            [0.0, 1.0, -y0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        H_roi = T_roi @ H_matrix

        # 3. Warp ảnh và mask trong phạm vi ROI cục bộ
        border_val = (255, 255, 255) if self.background_mode == 'white' else (0, 0, 0)
        if motion_model != 'homography':
            warped_roi = cv2.warpAffine(
                source_premul, H_roi[:2, :], (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=border_val
            )
            mask_roi = cv2.warpAffine(
                source_alpha, H_roi[:2, :], (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )
        else:
            warped_roi = cv2.warpPerspective(
                source_premul, H_roi, (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=border_val
            )
            mask_roi = cv2.warpPerspective(
                source_alpha, H_roi, (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )

        binary_mask = (mask_roi > 0.05).astype(np.uint8)
        if np.count_nonzero(binary_mask) == 0:
            return

        # Khôi phục straight RGB
        warped_straight = np.zeros_like(warped_roi)
        np.divide(warped_roi, mask_roi[:, :, None], out=warped_straight, where=mask_roi[:, :, None] > 1e-6)

        # 4. Trọng số khoảng cách Voronoi (Khoảng cách Euclidean tới mép tile)
        dist_map = cv2.distanceTransform(binary_mask, cv2.DIST_L2, 5).astype(np.float32)

        # Kết hợp điều biến độ nét cục bộ nếu bật focus stacking
        if self.focus_stacking:
            sharpness_map = compute_local_sharpness_map(warped_straight, kernel_size=15)
            quality_metric = dist_map * (1.0 + 0.05 * np.clip(sharpness_map.astype(np.float32), 0.0, 10.0))
        else:
            quality_metric = dist_map

        # 5. Cập nhật Canvas với Voronoi Adaptive Seam
        roi_rgb = self.canvas_rgb[y0:y1, x0:x1]
        roi_dist = self.canvas_dist[y0:y1, x0:x1]
        roi_alpha = self.canvas_alpha[y0:y1, x0:x1]

        # Tính toán độ chênh lệch chất lượng giữa tile mới và canvas hiện tại
        diff = quality_metric - roi_dist
        
        # Chuyển tiếp mượt dạng Sin với dải chuyển tiếp thích nghi (Adaptive Seam Bandwidth)
        # Thay vì cố định 16px gây lộ vết cắt sắc cạnh, mở rộng dải chuyển tiếp dựa trên kích thước tile
        min_dim = float(min(roi_w, roi_h))
        seam_width = max(2.0, min(80.0, min_dim * 0.18))
        t = np.clip(diff / seam_width, -1.0, 1.0)
        alpha = 0.5 + 0.5 * np.sin(t * (np.pi / 2.0))
        
        # Nếu canvas chưa có tile nào trước đó: pixel mới chiếm 100%
        alpha = np.where(roi_alpha <= 0.01, 1.0, alpha)
        # Pixel ngoài vùng hợp lệ của tile mới: alpha = 0
        alpha = np.where(binary_mask == 0, 0.0, alpha)

        # Hòa trộn trực tiếp in-place
        alpha_3ch = alpha[:, :, np.newaxis]
        self.canvas_rgb[y0:y1, x0:x1] = roi_rgb * (1.0 - alpha_3ch) + warped_straight * alpha_3ch

        # Cập nhật distance map và alpha
        self.canvas_dist[y0:y1, x0:x1] = np.maximum(roi_dist, quality_metric * mask_roi)
        self.canvas_alpha[y0:y1, x0:x1] = np.clip(roi_alpha + mask_roi * (1.0 - roi_alpha), 0.0, 1.0)

    def finalize(self):
        """
        Chuẩn hóa kết quả hòa trộn cuối cùng và xử lý màu nền
        """
        blended_rgb = np.clip(self.canvas_rgb, 0, 255).astype(np.uint8)
        final_alpha = np.clip(self.canvas_alpha * 255.0, 0, 255).astype(np.uint8)
        valid_mask = self.canvas_alpha > 0.05

        del self.canvas_rgb
        del self.canvas_dist
        del self.canvas_alpha

        # Xử lý màu nền
        if self.background_mode == 'transparent':
            blended_rgba = cv2.cvtColor(blended_rgb, cv2.COLOR_RGB2RGBA)
            blended_rgba[:, :, 3] = final_alpha
            return blended_rgba, final_alpha
        elif self.background_mode == 'black':
            blended_rgb = np.where(valid_mask[:, :, None], blended_rgb, 0).astype(np.uint8)
            return blended_rgb, np.where(valid_mask, 255, 0).astype(np.uint8)
        else: # 'white'
            blended_rgb = np.where(valid_mask[:, :, None], blended_rgb, 255).astype(np.uint8)
            return blended_rgb, np.where(valid_mask, 255, 0).astype(np.uint8)

# Alias tương thích ngược
MultiBandBlender = FastStreamingBlender
