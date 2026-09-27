# Feature: Hòa trộn dòng ROI tích hợp Cạnh Tranh Độ Nét Linh Hoạt (Adaptive Focus-Stacking & Sharpness Competition)
# Purpose: Automatically detects and prioritizes the sharpest focal slices between overlapping tiles (adaptive focus stacking)
# Path: tool/image_alignment/backend/blending.py

import cv2
import numpy as np

def compute_local_sharpness_map(img_rgb, kernel_size=15):
    """
    Calculates localized absolute microscopic sharpness/focus map
    Đo đạc năng lượng độ nét vi thể tuyệt đối:
    1. Tenengrad Gradient (Độ tương phản biên vi thể)
    2. Modified Laplacian (Độ sắc nét nhân tế bào)
    Giữ nguyên thang đo năng lượng thực tế (không chuẩn hóa co cụm cục bộ từng ảnh) để so sánh trực tiếp giữa các tile:
    Tile rõ nét (in-focus) sẽ có năng lượng cao vượt trội so với tile bị trôi nét/mờ (out-of-focus).
    """
    if img_rgb.ndim == 3:
        gray = cv2.cvtColor(img_rgb[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    else:
        gray = img_rgb.astype(np.uint8)

    gray_f = gray.astype(np.float32)

    # 1. Gradient bậc 1 (Tenengrad)
    gx = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(gx * gx + gy * gy)

    # 2. Gradient bậc 2 (Laplacian vi phân tế bào)
    lap_mag = np.abs(cv2.Laplacian(gray_f, cv2.CV_32F, ksize=3))

    # Tổng hợp năng lượng độ nét vi thể thực tế
    sharpness_raw = grad_mag + 0.8 * lap_mag

    # Làm mượt nhẹ để tạo trường năng lượng liên tục không bị nhiễu hạt
    k = kernel_size if kernel_size % 2 != 0 else kernel_size + 1
    sharpness_smooth = cv2.GaussianBlur(sharpness_raw, (k, k), 0)

    return sharpness_smooth


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

    import warnings
    stack = np.stack(bg_luma_maps, axis=0)
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore', category=RuntimeWarning)
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
    - Tự động nhận diện nền lam kính thực sự (True Microscope Background Exclusion) để tránh làm cháy sáng mô tế bào.
    """
    if not source_images or len(source_images) <= 1:
        return source_images

    # 1. Ước lượng trường sáng 2D cong nếu bật Gaussian smoothing
    shading_profile = estimate_flat_field_profile(source_images) if enable_gaussian_smoothing else None

    # 2. Khử tối góc 2D và thu thập mức nền chuẩn xác của từng ô ảnh
    bg_levels = {}
    flat_images = {}
    tissue_only_tiles = set()

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

        # Phát hiện nền lam kính thực sự dựa trên độ bão hòa màu thấp và độ sáng cao
        hsv = cv2.cvtColor(np.clip(flat_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        bg_mask = alpha_mask & (sat < 40) & (val > 110)

        n_bg_px = np.count_nonzero(bg_mask)
        total_valid = np.count_nonzero(alpha_mask)

        # Nếu tile có ít nhất 2% diện tích là nền lam kính (hoặc > 200 pixels)
        if n_bg_px >= max(200, int(total_valid * 0.02)):
            bg_pixels = flat_rgb[bg_mask]
            luma_bg = 0.299 * bg_pixels[:, 0] + 0.587 * bg_pixels[:, 1] + 0.114 * bg_pixels[:, 2]
            p80 = np.percentile(luma_bg, 80)
            clean_bg = bg_pixels[luma_bg >= p80]
            bg_levels[i] = np.mean(clean_bg, axis=0) if len(clean_bg) > 0 else np.mean(bg_pixels, axis=0)
        else:
            # Tile toàn mô tế bào (không có nền trống), không lấy percentile của mô làm nền tránh cháy sáng
            valid_pixels = flat_rgb[alpha_mask]
            luma = 0.299 * valid_pixels[:, 0] + 0.587 * valid_pixels[:, 1] + 0.114 * valid_pixels[:, 2]
            p90 = np.percentile(luma, 90)
            # Chỉ coi là nền nếu luma p90 thực sự sáng (> 160)
            if p90 > 160:
                bg_pixels = valid_pixels[luma >= p90]
                bg_levels[i] = np.mean(bg_pixels, axis=0)
            else:
                tissue_only_tiles.add(i)

    if len(bg_levels) == 0:
        return source_images

    all_bg = np.array(list(bg_levels.values()), dtype=np.float32)
    ref_bg = np.median(all_bg, axis=0)

    if np.mean(ref_bg) < 70.0:
        return source_images

    # Tính gain trung bình của các tile có nền
    valid_gains = [ref_bg / np.maximum(b, 1.0) for b in bg_levels.values()]
    avg_safe_gain = np.median(valid_gains, axis=0) if valid_gains else np.array([1.0, 1.0, 1.0], dtype=np.float32)

    equalized_images = {}
    for i, img in source_images.items():
        if i not in flat_images:
            equalized_images[i] = img
            continue

        if i in bg_levels:
            tile_bg = bg_levels[i]
            gains = ref_bg / np.maximum(tile_bg, 1.0)
            gains = np.clip(gains, 0.70, 1.45)
        elif i in tissue_only_tiles:
            # Với tile toàn mô, áp gain trung bình an toàn từ các tile có nền để màu sắc hài hòa tự nhiên
            gains = np.clip(avg_safe_gain, 0.85, 1.15)
        else:
            gains = np.array([1.0, 1.0, 1.0], dtype=np.float32)

        flat_rgb = flat_images[i]
        adj_rgb = np.clip(flat_rgb * gains[None, None, :], 0.0, 255.0).astype(np.uint8)

        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if has_alpha:
            new_img = np.dstack([adj_rgb, img[:, :, 3]])
        else:
            new_img = adj_rgb

        equalized_images[i] = new_img

    return equalized_images


def get_tissue_mask(img_rgb, threshold=215):
    """
    Trích xuất mặt nạ mô học (loại bỏ nền kính quang học).
    Thuật toán tối ưu từ kietlearntocode/stitch:
    - Điểm ảnh mô có giá trị xám < threshold và > 15 (loại trừ cả nền kính quá sáng và biên đen quá tối).
    - Sử dụng phép toán hình thái học (morphological closing) để lấp đầy các khoảng trống nhỏ bên trong nhân tế bào.
    """
    if img_rgb.ndim == 3:
        gray = cv2.cvtColor(img_rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    else:
        gray = img_rgb.astype(np.uint8)
    mask = (gray < threshold) & (gray > 15)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel)


def apply_defringe_filter(rgb_img, threshold=12, min_blue=50):
    """
    Khử hiện tượng quang sai sắc biên giới (viền tán sắc xanh dương/cyan quanh ranh giới mô học).
    Thuật toán chuẩn từ kietlearntocode/stitch:
    - Tự động nhận diện các điểm ảnh có kênh Blue vượt trội bất thường so với max(Red, Green).
    - Cắt giảm đỉnh Blue về đúng mức max(Red, Green) để khôi phục màu mô chuẩn giải phẫu bệnh.
    """
    if rgb_img is None or rgb_img.size == 0 or rgb_img.ndim < 3:
        return rgb_img

    r = rgb_img[:, :, 0]
    g = rgb_img[:, :, 1]
    b = rgb_img[:, :, 2]

    max_rg = np.maximum(r, g)
    diff = b.astype(np.int16) - max_rg.astype(np.int16)
    fringe_mask = (diff > threshold) & (b > min_blue)

    b_clean = b.copy()
    b_clean[fringe_mask] = max_rg[fringe_mask]

    res = np.dstack([r, g, b_clean])
    if rgb_img.shape[2] == 4:
        return np.dstack([res, rgb_img[:, :, 3]])
    return res


def compensate_overlap_exposure(source_images, transforms, motion_model='affine', channel_wise=True, threshold=215):
    """
    Cân bằng phơi sáng chuyên biệt trên mô học tại các vùng giao thoa (Tissue-Specific Overlap Gain Compensation).
    Học tập và tối ưu hóa từ thuật toán của kietlearntocode/stitch:
    - Phân tách vùng giao thoa giữa các ô ảnh thành 2 lớp:
      1. shared_tissue: Phần mô tế bào chung giữa 2 tile (ưu tiên cao, trọng số sqrt(n_tissue)).
      2. shared_glass: Phần lam kính trống chung khi không có mô (trọng số 0.5 * sqrt(n_glass)).
    - Dùng np.median trên vùng mô để loại trừ hoàn toàn các điểm ảnh lóa, đốm sáng hoặc bọt khí.
    - Xây dựng hệ phương trình tuyến tính Log-Linear Least Squares: log(g_i) - log(g_j) = log(I_j / I_i).
    - Ràng buộc trung bình nhân gain = 1.0 và chuẩn hóa gains / median(gains) giúp giữ độ tương phản gốc tự nhiên.
    """
    if not source_images or len(source_images) <= 1 or not transforms or len(transforms) <= 1:
        return source_images

    indices = [i for i in source_images if i in transforms and source_images[i] is not None]
    n = len(indices)
    if n <= 1:
        return source_images

    idx_to_pos = {idx: pos for pos, idx in enumerate(indices)}

    first_img = source_images[indices[0]]
    h0, w0 = first_img.shape[:2]
    scale = min(1.0, 256.0 / max(h0, w0, 1))

    # Chuẩn bị ảnh, mask hợp lệ và mặt nạ mô học (tissue mask) đã downscale
    down_images = {}
    down_masks = {}
    down_tissues = {}

    for i in indices:
        img = source_images[i]
        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        if scale < 0.95:
            sw = max(16, int(w0 * scale))
            sh = max(16, int(h0 * scale))
            small_rgb = cv2.resize(img[:, :, :3], (sw, sh), interpolation=cv2.INTER_AREA)
            if has_alpha:
                small_alpha = cv2.resize(img[:, :, 3], (sw, sh), interpolation=cv2.INTER_NEAREST) > 30
            else:
                small_alpha = np.ones((sh, sw), dtype=bool)
        else:
            small_rgb = img[:, :, :3]
            small_alpha = (img[:, :, 3] > 30) if has_alpha else np.ones(img.shape[:2], dtype=bool)

        down_images[i] = small_rgb.astype(np.float32)
        down_masks[i] = small_alpha
        down_tissues[i] = get_tissue_mask(small_rgb, threshold=threshold)

    # Tính bounding box của từng ảnh trên canvas
    bboxes = {}
    sw, sh = down_images[indices[0]].shape[1], down_images[indices[0]].shape[0]
    corners = np.array([[0, 0, 1], [sw, 0, 1], [sw, sh, 1], [0, sh, 1]], dtype=np.float64).T

    scaled_transforms = {}
    for i in indices:
        H = np.asarray(transforms[i], dtype=np.float64)
        if scale < 0.95:
            S = np.diag([scale, scale, 1.0])
            S_inv = np.diag([1.0 / scale, 1.0 / scale, 1.0])
            H_scaled = S @ H @ S_inv
        else:
            H_scaled = H.copy()
        scaled_transforms[i] = H_scaled

        pts = H_scaled @ corners
        if motion_model == 'homography':
            pts /= (pts[2:3, :] + 1e-8)
        xs = pts[0, :]
        ys = pts[1, :]
        bboxes[i] = (np.min(xs), np.min(ys), np.max(xs), np.max(ys))

    # Tìm các cặp có bounding box giao nhau
    pairs = []
    for p_i in range(n):
        i = indices[p_i]
        bx0, by0, bx1, by1 = bboxes[i]
        for p_j in range(p_i + 1, n):
            j = indices[p_j]
            jx0, jy0, jx1, jy1 = bboxes[j]
            ix0 = max(bx0, jx0)
            iy0 = max(by0, jy0)
            ix1 = min(bx1, jx1)
            iy1 = min(by1, jy1)
            if ix1 - ix0 > 3 and iy1 - iy0 > 3:
                pairs.append((i, j, int(np.floor(ix0)), int(np.floor(iy0)), int(np.ceil(ix1)), int(np.ceil(iy1))))

    if not pairs:
        return source_images

    num_channels = 3 if channel_wise else 1
    eq_rows = []
    eq_b = [[] for _ in range(num_channels)]
    weights = []

    for (i, j, ix0, iy0, ix1, iy1) in pairs:
        inter_w = ix1 - ix0
        inter_h = iy1 - iy0
        if inter_w <= 0 or inter_h <= 0:
            continue

        T_inter = np.array([[1.0, 0.0, -ix0], [0.0, 1.0, -iy0], [0.0, 0.0, 1.0]], dtype=np.float64)
        H_i = T_inter @ scaled_transforms[i]
        H_j = T_inter @ scaled_transforms[j]

        flags = cv2.INTER_LINEAR
        if motion_model != 'homography':
            warp_i = cv2.warpAffine(down_images[i], H_i[:2, :], (inter_w, inter_h), flags=flags)
            warp_j = cv2.warpAffine(down_images[j], H_j[:2, :], (inter_w, inter_h), flags=flags)
            mask_i = cv2.warpAffine(down_masks[i].astype(np.uint8), H_i[:2, :], (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            mask_j = cv2.warpAffine(down_masks[j].astype(np.uint8), H_j[:2, :], (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            tmask_i = cv2.warpAffine(down_tissues[i], H_i[:2, :], (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            tmask_j = cv2.warpAffine(down_tissues[j], H_j[:2, :], (inter_w, inter_h), flags=cv2.INTER_NEAREST)
        else:
            warp_i = cv2.warpPerspective(down_images[i], H_i, (inter_w, inter_h), flags=flags)
            warp_j = cv2.warpPerspective(down_images[j], H_j, (inter_w, inter_h), flags=flags)
            mask_i = cv2.warpPerspective(down_masks[i].astype(np.uint8), H_i, (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            mask_j = cv2.warpPerspective(down_masks[j].astype(np.uint8), H_j, (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            tmask_i = cv2.warpPerspective(down_tissues[i], H_i, (inter_w, inter_h), flags=cv2.INTER_NEAREST)
            tmask_j = cv2.warpPerspective(down_tissues[j], H_j, (inter_w, inter_h), flags=cv2.INTER_NEAREST)

        overlap_mask = (mask_i > 0) & (mask_j > 0)
        n_overlap_px = np.count_nonzero(overlap_mask)
        if n_overlap_px < 15:
            continue

        # Phân tách mô học (shared_tissue) và lam kính (shared_glass) theo kietlearntocode/stitch
        shared_tissue = overlap_mask & (tmask_i > 0) & (tmask_j > 0)
        n_tissue = np.count_nonzero(shared_tissue)

        if n_tissue >= 30:
            target_mask = shared_tissue
            w_ij = np.sqrt(float(n_tissue))
        else:
            shared_glass = overlap_mask & (~shared_tissue)
            n_glass = np.count_nonzero(shared_glass)
            if n_glass >= 40:
                target_mask = shared_glass
                w_ij = 0.5 * np.sqrt(float(n_glass))
            else:
                target_mask = overlap_mask
                w_ij = 0.3 * np.sqrt(float(n_overlap_px))

        row = np.zeros(n, dtype=np.float32)
        pos_i = idx_to_pos[i]
        pos_j = idx_to_pos[j]
        row[pos_i] = 1.0
        row[pos_j] = -1.0
        eq_rows.append(row)
        weights.append(w_ij)

        # Sử dụng np.median để chống nhiễu hạt và đốm lóa
        if channel_wise:
            for c in range(3):
                val_i = float(np.median(warp_i[:, :, c][target_mask]))
                val_j = float(np.median(warp_j[:, :, c][target_mask]))
                ratio = max(1e-2, (val_j + 1e-3) / (val_i + 1e-3))
                eq_b[c].append(float(np.log(ratio)))
        else:
            val_i = float(np.median(warp_i[target_mask]))
            val_j = float(np.median(warp_j[target_mask]))
            ratio = max(1e-2, (val_j + 1e-3) / (val_i + 1e-3))
            eq_b[0].append(float(np.log(ratio)))

    if not eq_rows:
        return source_images

    A = np.array(eq_rows, dtype=np.float32)
    W = np.array(weights, dtype=np.float32)
    A_weighted = A * W[:, None]

    # Ràng buộc trung bình log_g = 0 để neo dải sáng
    anchor_row = np.ones((1, n), dtype=np.float32) * (np.mean(W) * 2.0)
    A_final = np.vstack([A_weighted, anchor_row])

    gains_per_tile = {idx: np.ones(3, dtype=np.float32) for idx in indices}

    for c in range(num_channels):
        b_c = np.array(eq_b[c], dtype=np.float32) * W
        b_final = np.append(b_c, 0.0)

        try:
            log_g, _, _, _ = np.linalg.lstsq(A_final, b_final, rcond=None)
            g_raw = np.exp(log_g)
            # Chuẩn hóa theo median gain (như kietlearntocode/stitch) để giữ dải màu tự nhiên
            med_g = np.median(g_raw)
            if med_g > 1e-4:
                g_raw = g_raw / med_g
            g_clipped = np.clip(g_raw, 0.60, 1.65)
            for pos, idx in enumerate(indices):
                if channel_wise:
                    gains_per_tile[idx][c] = g_clipped[pos]
                else:
                    gains_per_tile[idx][:] = g_clipped[pos]
        except Exception:
            pass

    # Áp dụng gains cho từng ảnh
    compensated_images = {}
    for i, img in source_images.items():
        if i not in gains_per_tile:
            compensated_images[i] = img
            continue
        g = gains_per_tile[i]
        has_alpha = (img.ndim == 3 and img.shape[2] == 4)
        rgb = img[:, :, :3].astype(np.float32)
        adj_rgb = np.clip(rgb * g[None, None, :], 0.0, 255.0).astype(np.uint8)
        if has_alpha:
            compensated_images[i] = np.dstack([adj_rgb, img[:, :, 3]])
        else:
            compensated_images[i] = adj_rgb

    return compensated_images



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
            edge_ramp = np.clip(dist_map / 15.0, 0.0, 1.0)
            quality_metric = (edge_ramp * (sharpness_map ** 2.5 + 0.02 * dist_map)).astype(np.float32)
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


def solve_tissue_specific_gains(images, adjusted_transforms, canvas_w, canvas_h, threshold=215):
    """
    Cân bằng phơi sáng chuyên biệt trên phần mô học tại các vùng giao thoa.
    Thuật toán chuẩn tối ưu:
    - Tìm vùng giao thoa giữa các cặp ảnh trên canvas toàn cục.
    - Đo trung vị (np.median) trên phần mô tế bào chung (shared_tissue) cho từng kênh RGB.
    - Giải hệ Least Squares log-linear để san phẳng chênh lệch độ sáng phơi sáng giữa các ô ảnh.
    - Chuẩn hóa: gains = gains / np.median(gains) và clip(0.55, 1.85).
    - Triệt tiêu hoàn toàn sự chênh lệch sáng tối giữa các ô ảnh, không còn vệt cắt ranh giới.
    """
    indices = [i for i in images if i in adjusted_transforms and images[i] is not None]
    n_images = len(indices)
    if n_images <= 1:
        return {i: np.ones(3, dtype=np.float32) for i in images}

    idx_to_pos = {idx: pos for pos, idx in enumerate(indices)}

    # Tự động scale thích nghi để chạy cực nhanh và tiết kiệm RAM
    max_dim = max(canvas_w, canvas_h)
    scale = min(0.25, 2048.0 / max(max_dim, 1))
    dw = max(1, int(canvas_w * scale))
    dh = max(1, int(canvas_h * scale))
    S = np.diag([scale, scale, 1.0])

    warped_rgbs = {}
    warped_tissue_masks = {}
    warped_tile_masks = {}

    for i in indices:
        img = images[i]
        h, w = img.shape[:2]
        T = (S @ np.asarray(adjusted_transforms[i], dtype=np.float64))[:2]
        rgb = img[:, :, :3] if img.ndim == 3 and img.shape[2] == 4 else img
        warped_rgbs[i] = cv2.warpAffine(rgb, T, (dw, dh), flags=cv2.INTER_LINEAR)
        t_mask = get_tissue_mask(rgb, threshold=threshold)
        warped_tissue_masks[i] = cv2.warpAffine(t_mask, T, (dw, dh), flags=cv2.INTER_NEAREST)
        warped_tile_masks[i] = cv2.warpAffine(np.ones((h, w), dtype=np.uint8), T, (dw, dh), flags=cv2.INTER_NEAREST)

    rows_A = []
    vals_b = [[] for _ in range(3)]
    weights = []

    for p_i in range(n_images):
        i = indices[p_i]
        for p_j in range(p_i + 1, n_images):
            j = indices[p_j]
            shared_tissue = (warped_tissue_masks[i] > 0) & (warped_tissue_masks[j] > 0)
            n_tissue = np.count_nonzero(shared_tissue)

            if n_tissue > 50:
                target_mask = shared_tissue
                w_ij = np.sqrt(float(n_tissue))
            else:
                shared_glass = (warped_tile_masks[i] > 0) & (warped_tile_masks[j] > 0) & (~shared_tissue)
                n_glass = np.count_nonzero(shared_glass)
                if n_glass > 80:
                    target_mask = shared_glass
                    w_ij = 0.5 * np.sqrt(float(n_glass))
                else:
                    continue

            means_i = [float(np.median(warped_rgbs[i][target_mask, c])) for c in range(3)]
            means_j = [float(np.median(warped_rgbs[j][target_mask, c])) for c in range(3)]

            if all(m > 5.0 for m in means_i) and all(m > 5.0 for m in means_j):
                row = np.zeros(n_images, dtype=np.float32)
                row[p_i] = 1.0
                row[p_j] = -1.0
                rows_A.append(row * w_ij)
                weights.append(w_ij)
                for c in range(3):
                    ratio = means_j[c] / means_i[c]
                    vals_b[c].append(np.log(ratio) * w_ij)

    if len(rows_A) == 0:
        return {i: np.ones(3, dtype=np.float32) for i in images}

    A = np.array(rows_A, dtype=np.float32)
    constraint_row = np.ones((1, n_images), dtype=np.float32) * (np.mean(weights) * 2.0)
    constraint_val = np.zeros(1, dtype=np.float32)
    A_full = np.vstack([A, constraint_row])

    gains_per_channel = np.ones((n_images, 3), dtype=np.float32)
    for c in range(3):
        b = np.array(vals_b[c], dtype=np.float32)
        b_full = np.concatenate([b, constraint_val])
        log_g, _, _, _ = np.linalg.lstsq(A_full, b_full, rcond=None)
        g = np.exp(log_g)
        med_g = np.median(g)
        if med_g > 1e-4:
            g = g / med_g
        gains_per_channel[:, c] = np.clip(g, 0.55, 1.85)

    result_gains = {}
    for pos, idx in enumerate(indices):
        result_gains[idx] = gains_per_channel[pos].copy()
    for idx in images:
        if idx not in result_gains:
            result_gains[idx] = np.ones(3, dtype=np.float32)

    return result_gains


def blend_multiband_voronoi(images, tile_gains, adjusted_transforms, canvas_w, canvas_h, num_bands=5, background_mode='white'):
    """
    Hòa trộn đa băng tần Laplacian kết hợp phân vùng Voronoi Seam Partitioning.
    Cơ chế Sharpness-Dominant Selection:
    - Tại mọi vùng chồng lấn, tile có độ nét cao hơn (in-focus) sẽ chiến thắng áp đảo tile mờ (out-of-focus).
    - Tần số cao nhất (High-band - chi tiết tế bào) lấy 100% từ tile rõ nét nhất, loại bỏ hoàn toàn phần mờ nhòe.
    - Tần số thấp (Low-band - trường sáng nền) hòa trộn mượt qua tháp Laplacian 5 tầng, xóa sạch đường nối thẳng đứng.
    """
    indices = [i for i in images if i in adjusted_transforms and images[i] is not None]
    n_images = len(indices)
    if n_images == 0:
        bg_col = 255 if background_mode == 'white' else 0
        return np.full((canvas_h, canvas_w, 3), bg_col, dtype=np.uint8), np.zeros((canvas_h, canvas_w), dtype=np.uint8)

    # 1. Cân bằng phơi sáng an toàn
    compensated_images = {}
    for i in indices:
        img = images[i]
        rgb = img[:, :, :3] if img.ndim == 3 and img.shape[2] == 4 else img
        g = tile_gains.get(i, np.ones(3, dtype=np.float32))
        img_f = rgb.astype(np.float32) * g[None, None, :]
        compensated_images[i] = np.clip(img_f, 0.0, 255.0).astype(np.uint8)

    # 2. Tạo mặt nạ Voronoi Seam Partitioning với Sharpness Dominance
    max_dist = np.zeros((canvas_h, canvas_w), dtype=np.float32)
    best_tile_idx = np.full((canvas_h, canvas_w), -1, dtype=np.int16)
    tile_rois = {}

    for i in indices:
        h, w = images[i].shape[:2]
        H = np.asarray(adjusted_transforms[i], dtype=np.float64)

        padded_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        padded_mask[1:-1, 1:-1] = 1
        dist_map = cv2.distanceTransform(padded_mask, cv2.DIST_L2, 5)[1:-1, 1:-1].astype(np.float32)

        corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64).T
        warped_corners = H @ corners
        pts = warped_corners[:2, :].T
        x0 = max(0, int(np.floor(np.min(pts[:, 0]))))
        y0 = max(0, int(np.floor(np.min(pts[:, 1]))))
        x1 = min(canvas_w, int(np.ceil(np.max(pts[:, 0]))))
        y1 = min(canvas_h, int(np.ceil(np.max(pts[:, 1]))))
        rw, rh = x1 - x0, y1 - y0

        if rw <= 0 or rh <= 0:
            continue

        T_roi = np.array([[1.0, 0.0, -x0], [0.0, 1.0, -y0], [0.0, 0.0, 1.0]], dtype=np.float64)
        H_roi = (T_roi @ H)[:2]

        warped_dist = cv2.warpAffine(dist_map, H_roi, (rw, rh), flags=cv2.INTER_LINEAR, borderValue=0.0)
        warped_mask = cv2.warpAffine(np.ones((h, w), dtype=np.uint8), H_roi, (rw, rh), flags=cv2.INTER_NEAREST, borderValue=0)

        # Tính độ sắc nét vi thể thực tế của tile i (Ưu tiên tuyệt đối tile rõ nét, loại bỏ tile mờ)
        sharpness_map = compute_local_sharpness_map(compensated_images[i], kernel_size=15)
        warped_sharpness = cv2.warpAffine(sharpness_map, H_roi, (rw, rh), flags=cv2.INTER_LINEAR, borderValue=0.0)

        # Trọng số chất lượng:
        # edge_ramp đảm bảo mép cắt ngoài cùng 15px được làm mượt
        edge_ramp = np.clip(warped_dist / 15.0, 0.0, 1.0)
        # Độ nét vi thể là yếu tố thống trị: tile rõ nét (sharpness cao) áp đảo tuyệt đối tile mờ
        tile_quality = (edge_ramp * (warped_sharpness ** 2.5 + 0.02 * warped_dist)).astype(np.float32)

        canvas_d_sub = max_dist[y0:y1, x0:x1]
        canvas_idx_sub = best_tile_idx[y0:y1, x0:x1]

        better = (tile_quality > canvas_d_sub) & (warped_mask > 0)
        canvas_d_sub[better] = tile_quality[better]
        canvas_idx_sub[better] = i

        tile_rois[i] = (x0, y0, x1, y1, H_roi)

    # 3. Nạp vào MultiBandBlender của OpenCV
    actual_bands = max(1, min(num_bands, 8))
    blender = cv2.detail.MultiBandBlender(0, actual_bands)
    blender.prepare((0, 0, canvas_w, canvas_h))

    for i in indices:
        if i not in tile_rois:
            continue
        img = compensated_images[i]
        x0, y0, x1, y1, H_roi = tile_rois[i]
        rw, rh = x1 - x0, y1 - y0

        warped_img = cv2.warpAffine(img, H_roi, (rw, rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        tile_seam_mask = (best_tile_idx[y0:y1, x0:x1] == i).astype(np.uint8) * 255
        blender.feed(warped_img.astype(np.int16), tile_seam_mask, (x0, y0))

    result_img, result_mask = blender.blend(None, None)
    final_rgb = np.clip(result_img, 0, 255).astype(np.uint8)

    bg_val = 255 if background_mode == 'white' else 0
    bg_mask = (result_mask == 0)
    final_rgb[bg_mask] = bg_val

    global_mask = (result_mask > 0).astype(np.uint8) * 255
    return final_rgb, global_mask


# Alias tương thích ngược
MultiBandBlender = FastStreamingBlender
