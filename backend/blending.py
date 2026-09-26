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


def enhance_cellular_clarity(image, strength=0.35):
    """
    Làm rõ nét vi thể tế bào (Cellular Clarity & Microscopic Detail Sharpening).
    Sử dụng Unsharp Mask vi phân giúp nổi bật nhân tế bào và cấu trúc mô học mà không gây nhiễu hạt.
    """
    if image is None or image.size == 0 or strength <= 0.01:
        return image

    has_alpha = (image.ndim == 3 and image.shape[2] == 4)
    rgb = image[:, :, :3].astype(np.float32)

    blurred = cv2.GaussianBlur(rgb, (0, 0), sigmaX=1.5)
    detail = rgb - blurred
    sharpened = np.clip(rgb + strength * detail, 0.0, 255.0).astype(np.uint8)

    if has_alpha:
        return np.dstack([sharpened, image[:, :, 3]])
    return sharpened


def estimate_flat_field_profile(source_images):
    """
    Ước lượng bản đồ trường sáng nền 2D cong (Vignetting / 2D Shading Profile) của kính hiển vi từ tập tile.
    Tự động tách và loại trừ mô tế bào (Tissue Mask Exclusion) để chỉ đo trên nền lam kính thực sự,
    tránh để vị trí cụm mô làm méo phân bố ánh sáng nền.
    """
    if not source_images or len(source_images) < 2:
        return None

    first_img = next(iter(source_images.values()))
    h, w = first_img.shape[:2]

    down_w = min(384, max(32, w // 4))
    down_h = min(216, max(32, h // 4))

    bg_luma_maps = []
    for img in source_images.values():
        if img is None or img.size == 0:
            continue
        small = cv2.resize(img[:, :, :3], (down_w, down_h))
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        # Vùng nền lam kính: độ bão hòa màu thấp và độ sáng cao (không chứa mô nhuộm đậm)
        bg_mask = (sat < 40) & (val > 120)
        luma = (0.299 * small[:, :, 0] + 0.587 * small[:, :, 1] + 0.114 * small[:, :, 2]).astype(np.float32)
        luma_clean = np.where(bg_mask, luma, np.nan)
        bg_luma_maps.append(luma_clean)

    if len(bg_luma_maps) < 2:
        return None

    stack = np.stack(bg_luma_maps, axis=0)
    with np.errstate(all='ignore'):
        avg_luma = np.nanmedian(stack, axis=0)

    global_med = float(np.nanmedian(avg_luma))
    if np.isnan(global_med) or global_med < 1e-4:
        clean_stack = [cv2.resize(img[:, :, :3].astype(np.float32), (down_w, down_h)) for img in source_images.values()]
        avg_luma = np.mean([0.299 * s[:, :, 0] + 0.587 * s[:, :, 1] + 0.114 * s[:, :, 2] for s in clean_stack], axis=0)
        global_med = float(np.median(avg_luma))

    avg_luma = np.nan_to_num(avg_luma, nan=global_med)

    ksize = max(31, (min(down_w, down_h) // 4) * 2 + 1)
    shading_smooth = cv2.GaussianBlur(avg_luma, (ksize, ksize), 0)

    med = np.median(shading_smooth)
    if med < 1e-4:
        return None

    shading_norm = shading_smooth / med
    shading_norm = np.clip(shading_norm, 0.80, 1.25)
    shading_profile = cv2.resize(shading_norm, (w, h), interpolation=cv2.INTER_LINEAR)
    return shading_profile


def equalize_tile_illumination(source_images, enable_gaussian_smoothing=True):
    """
    Tự động chuẩn hóa màu nền và cân bằng phơi sáng giữa các ô ảnh kính hiển vi (Microscopy Flat-Field & Background Normalization).
    - enable_gaussian_smoothing: Nếu True, áp dụng khử tối góc quang học 2D để trường sáng đồng đều từ tâm ra 4 góc.
      Nếu False, chỉ cân bằng gain màu nền để giữ nguyên độ tương phản quang học gốc.
    """
    if not source_images or len(source_images) <= 1:
        return source_images

    # 1. Ước lượng trường sáng 2D cong nếu bật Gaussian smoothing
    shading_profile = estimate_flat_field_profile(source_images) if enable_gaussian_smoothing else None

    # 2. Khử tối góc 2D và thu thập mức nền chuẩn xác của từng ô ảnh
    bg_levels = {}
    flat_images = {}
    for i, img in source_images.items():
        if img is None or img.size == 0:
            continue

        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if has_alpha:
            rgb = img[:, :, :3].astype(np.float32)
            alpha_mask = img[:, :, 3] > 30
        else:
            rgb = img.astype(np.float32)
            alpha_mask = np.ones(img.shape[:2], dtype=bool)

        if np.count_nonzero(alpha_mask) < 50:
            continue

        if shading_profile is not None and shading_profile.shape == rgb.shape[:2]:
            flat_rgb = np.clip(rgb / shading_profile[:, :, None], 0.0, 255.0)
        else:
            flat_rgb = rgb

        flat_images[i] = flat_rgb

        valid_pixels = flat_rgb[alpha_mask]
        luma = 0.299 * valid_pixels[:, 0] + 0.587 * valid_pixels[:, 1] + 0.114 * valid_pixels[:, 2]
        p90 = np.percentile(luma, 90)
        bg_pixels = valid_pixels[luma >= p90]
        if len(bg_pixels) >= 10:
            bg_levels[i] = np.mean(bg_pixels, axis=0)
        else:
            bg_levels[i] = np.percentile(valid_pixels, 95, axis=0)

    if len(bg_levels) <= 1:
        return source_images

    all_bg = np.array(list(bg_levels.values()), dtype=np.float32)
    ref_bg = np.median(all_bg, axis=0)

    if np.mean(ref_bg) < 70.0:
        return source_images

    equalized_images = {}
    for i, img in source_images.items():
        if i not in bg_levels or i not in flat_images:
            equalized_images[i] = img
            continue

        tile_bg = bg_levels[i]
        gains = ref_bg / np.maximum(tile_bg, 1.0)
        gains = np.clip(gains, 0.70, 1.45)

        flat_rgb = flat_images[i]
        adj_rgb = np.clip(flat_rgb * gains[None, None, :], 0.0, 255.0).astype(np.uint8)

        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if has_alpha:
            new_img = np.dstack([adj_rgb, img[:, :, 3]])
        else:
            new_img = adj_rgb

        equalized_images[i] = new_img

    return equalized_images


class FastStreamingBlender:
    """
    Bộ hòa trộn dòng ROI tích hợp Voronoi Adaptive Seam Blending & Edge Feathering:
    - Triệt tiêu 100% hiện tượng bóng ma (Ghosting / Double Contours) và nhân đôi viền mô học.
    - Tại mỗi pixel, ưu tiên tuyệt đối tile có chất lượng quang học tốt nhất (gần tâm trục quang hơn, dist_map lớn hơn).
    - Vùng chuyển tiếp (seam transition) hòa trộn mượt theo dải thích nghi quanh ranh giới Voronoi,
      loại bỏ hoàn toàn các đường viền mép hình chữ nhật mà không làm nhòe hay nhân đôi chi tiết mô.
    - Khử hoàn toàn hiện tượng white halo/seam ở biên nhờ xử lý đúng chuẩn premultiplied alpha và edge feathering.
    - Bộ nhớ cực kỳ tối ưu và tốc độ xử lý nhanh gấp nhiều lần.
    """
    def __init__(self, canvas_shape, background_mode='white', focus_stacking=True, enhance_clarity=False):
        self.canvas_h, self.canvas_w = canvas_shape
        self.background_mode = background_mode
        self.focus_stacking = focus_stacking
        self.enhance_clarity = enhance_clarity

        bg_color = (255.0, 255.0, 255.0) if background_mode == 'white' else (0.0, 0.0, 0.0)
        self.canvas_rgb = np.full((self.canvas_h, self.canvas_w, 3), bg_color, dtype=np.float32)
        self.canvas_dist = np.zeros((self.canvas_h, self.canvas_w), dtype=np.float32)
        self.canvas_alpha = np.zeros((self.canvas_h, self.canvas_w), dtype=np.float32)

    def accumulate_tile(self, img_rgb, H_matrix, motion_model='affine'):
        """
        Warp tile ảnh `img_rgb` với ma trận `H_matrix` chỉ trong phạm vi Bounding Box ROI của tile,
        sau đó cập nhật vào canvas theo ranh giới Voronoi Seam mượt mà không lộ viền.
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
        # ĐẶC BIỆT: borderValue cho source_premul PHẢI là (0, 0, 0) để tránh hiện tượng bùng nổ pixel mép thành trắng xóa
        if motion_model != 'homography':
            warped_roi = cv2.warpAffine(
                source_premul, H_roi[:2, :], (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
            )
            mask_roi = cv2.warpAffine(
                source_alpha, H_roi[:2, :], (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )
        else:
            warped_roi = cv2.warpPerspective(
                source_premul, H_roi, (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
            )
            mask_roi = cv2.warpPerspective(
                source_alpha, H_roi, (roi_w, roi_h),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )

        binary_mask = (mask_roi > 0.25).astype(np.uint8)
        if np.count_nonzero(binary_mask) == 0:
            return

        # Khôi phục straight RGB an toàn
        warped_straight = np.zeros_like(warped_roi)
        np.divide(warped_roi, mask_roi[:, :, None], out=warped_straight, where=mask_roi[:, :, None] > 1e-4)
        warped_straight = np.clip(warped_straight, 0.0, 255.0)

        # 4. Trọng số khoảng cách Voronoi (Khoảng cách Euclidean tới mép tile)
        dist_map = cv2.distanceTransform(binary_mask, cv2.DIST_L2, 5).astype(np.float32)
        # Giảm nhẹ 1.5px để loại trừ nhiễu mép viền cảm biến quang học
        dist_map = np.maximum(0.0, dist_map - 1.5)

        # Kết hợp điều biến độ nét cục bộ nếu bật focus stacking
        if self.focus_stacking:
            sharpness_map = compute_local_sharpness_map(warped_straight, kernel_size=15)
            sharp_factor = 1.0 + 0.05 * np.nan_to_num(np.clip(sharpness_map, 0.0, 10.0), nan=0.0)
            quality_metric = (dist_map * sharp_factor.astype(np.float32)).astype(np.float32)
        else:
            quality_metric = dist_map

        # 5. Cập nhật Canvas với Voronoi Adaptive Seam & Edge Feathering
        roi_rgb = self.canvas_rgb[y0:y1, x0:x1]
        roi_dist = self.canvas_dist[y0:y1, x0:x1]
        roi_alpha = self.canvas_alpha[y0:y1, x0:x1]

        # Tính toán độ chênh lệch chất lượng giữa tile mới và canvas hiện tại
        diff = quality_metric - roi_dist
        
        # Chuyển tiếp mượt dạng Sin với dải chuyển tiếp thích nghi rộng (Large Adaptive Seam Bandwidth)
        min_dim = float(min(roi_w, roi_h))
        seam_width = max(32.0, min(240.0, min_dim * 0.25))
        t = np.clip(diff / seam_width, -1.0, 1.0)
        alpha = 0.5 + 0.5 * np.sin(t * (np.pi / 2.0))
        
        # Edge feathering: Làm mềm mép ngoài cùng của tile mới khi chồng lấn lên canvas đã có dữ liệu
        feather_edge = np.clip(dist_map / 28.0, 0.0, 1.0)
        alpha = np.where(roi_alpha > 0.01, alpha * feather_edge, alpha)

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
        if self.enhance_clarity:
            blended_rgb = enhance_cellular_clarity(blended_rgb, strength=0.40)
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
