# Chức năng: Backend Patch Inspector & Sharpness Calculation
# Lí do tạo: Cắt patch full-resolution tại cùng tọa độ world từ nhiều layer và tính điểm nét (variance of Laplacian)
# Đường dẫn: tool/image_alignment/backend/patch_inspector.py

import os
import cv2
import numpy as np
import base64
import math
import threading
from typing import Dict, Any, List, Optional
from backend.io_utils import get_image_metadata, read_image
from backend.project_schemas import (
    ProjectState, ProjectLayer, matrix_inverse, transform_point
)

# In-memory cache cho ảnh nguồn đã đọc (giới hạn LRU đơn giản)
_IMAGE_CACHE = {}
_CACHE_MAX_ENTRIES = 20
_CACHE_MAX_BYTES = 256 * 1024 * 1024
_CACHE_BYTES = 0
_MIN_SCORE_PIXELS = 20
_CACHE_LOCK = threading.RLock()
_MAX_PREVIEW_PIXELS = 1024 * 1024
_MAX_NATIVE_PIXELS = 16_777_216
_MAX_REGION_POINTS = 10_000
_MAX_SOURCE_DECODE_PIXELS = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_PATCH_SOURCE_PIXELS", "67108864")))

def _get_cached_image(file_path: str) -> np.ndarray:
    global _IMAGE_CACHE, _CACHE_BYTES
    with _CACHE_LOCK:
        if file_path in _IMAGE_CACHE:
            img = _IMAGE_CACHE.pop(file_path)
            _IMAGE_CACHE[file_path] = img
            return img
        # Decode under the cache lock so concurrent requests cannot decode the
        # same large source repeatedly outside the cache budget.
        metadata = get_image_metadata(file_path)
        source_pixels = int(metadata["width"]) * int(metadata["height"])
        if source_pixels > _MAX_SOURCE_DECODE_PIXELS:
            raise MemoryError(
                f"Patch source {source_pixels} pixels vượt decode guard {_MAX_SOURCE_DECODE_PIXELS} pixels"
            )
        img = read_image(file_path)
        while _IMAGE_CACHE and (len(_IMAGE_CACHE) >= _CACHE_MAX_ENTRIES or _CACHE_BYTES + img.nbytes > _CACHE_MAX_BYTES):
            evicted = _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
            _CACHE_BYTES -= evicted.nbytes
        if img.nbytes <= _CACHE_MAX_BYTES:
            _IMAGE_CACHE[file_path] = img
            _CACHE_BYTES += img.nbytes
    return img


def _resolve_source_path(source_path: str, workspace_root: Optional[str]) -> Optional[str]:
    if not source_path:
        return None
    if os.path.isabs(source_path):
        candidate = os.path.realpath(source_path)
        if workspace_root and os.path.commonpath([os.path.realpath(workspace_root), candidate]) != os.path.realpath(workspace_root):
            return None
        return candidate if os.path.isfile(candidate) else None
    roots = [workspace_root] if workspace_root else [os.getcwd()]
    if workspace_root:
        roots.extend([
            os.path.join(workspace_root, "data", "input"),
            os.path.join(workspace_root, "data"),
            os.path.join(workspace_root, "NhuomMo"),
            os.path.join(workspace_root, "tool", "image_alignment")
        ])
    containment_root = os.path.realpath(workspace_root) if workspace_root else None
    for root in roots:
        candidate = os.path.realpath(os.path.join(root, source_path))
        if containment_root and os.path.commonpath([containment_root, candidate]) != containment_root:
            continue
        if os.path.isfile(candidate):
            return candidate
    return None

def inspect_patches_at_world_region(
    project_state: ProjectState,
    shape_type: str = "rectangle",
    points_world: Optional[List[List[float]]] = None,
    world_rect: Optional[List[float]] = None,
    output_size: int = 256,
    layer_ids: Optional[List[str]] = None,
    workspace_root: Optional[str] = None
) -> Dict[str, Any]:
    """
    Trích xuất các patch theo hình dạng đa giác / lasso / chữ nhật từ tất cả các layer bao phủ vùng.
    Tính điểm nét (variance of Laplacian) CHỈ trên các pixel bên trong mặt nạ đa giác.
    """
    # 1. Chuẩn hóa points_world
    if points_world is not None and len(points_world) > _MAX_REGION_POINTS:
        raise ValueError(f"points_world vượt giới hạn {_MAX_REGION_POINTS} điểm")
    if points_world is not None and len(points_world) >= 3:
        pts = np.array([[float(p[0]), float(p[1])] for p in points_world], dtype=np.float32)
    elif world_rect is not None and len(world_rect) >= 4:
        wx, wy, ww, wh = [float(v) for v in world_rect[:4]]
        pts = np.array([
            [wx, wy],
            [wx + ww, wy],
            [wx + ww, wy + wh],
            [wx, wy + wh]
        ], dtype=np.float32)
    else:
        raise ValueError("Cần cung cấp points_world hoặc world_rect hợp lệ")

    min_x, min_y = np.min(pts, axis=0)
    max_x, max_y = np.max(pts, axis=0)
    box_w = float(max_x - min_x)
    box_h = float(max_y - min_y)

    if box_w <= 0 or box_h <= 0:
        raise ValueError("Kích thước vùng chọn phải lớn hơn 0")

    if isinstance(output_size, bool):
        raise ValueError("output_size không hợp lệ")
    output_size = max(32, min(1024, int(output_size)))
    
    # Giữ đúng aspect ratio của bounding box
    if box_w >= box_h:
        out_w = output_size
        out_h = max(32, int(round(output_size * (box_h / box_w))))
    else:
        out_h = output_size
        out_w = max(32, int(round(output_size * (box_w / box_h))))
    if out_w * out_h > _MAX_PREVIEW_PIXELS:
        raise ValueError("Patch preview vượt giới hạn pixel")

    # 4 góc bounding box trong world space
    box_corners = np.array([
        [min_x, min_y],
        [max_x, min_y],
        [max_x, max_y],
        [min_x, max_y]
    ], dtype=np.float32)

    # 4 góc tương ứng trong patch output space [0, 0, out_w, out_h]
    dst_box_corners = np.array([
        [0.0, 0.0],
        [float(out_w), 0.0],
        [float(out_w), float(out_h)],
        [0.0, float(out_h)]
    ], dtype=np.float32)

    # Tọa độ polygon trong output patch space
    scale_x = out_w / box_w
    scale_y = out_h / box_h
    dst_poly_pts = np.zeros_like(pts, dtype=np.int32)
    for i, (px, py) in enumerate(pts):
        dst_poly_pts[i] = [int(round((px - min_x) * scale_x)), int(round((py - min_y) * scale_y))]

    # Tạo mặt nạ vùng chọn trong output space
    region_mask = np.zeros((out_h, out_w), dtype=np.uint8)
    if shape_type in ["polygon", "lasso"]:
        cv2.fillPoly(region_mask, [dst_poly_pts], 255)
    else:
        region_mask[:, :] = 255

    # Erode nhẹ 2px để tránh biên nét vẽ giả làm tăng điểm Laplacian sai lệch
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded_region_mask = cv2.erode(region_mask, kernel, iterations=1)
    if np.count_nonzero(eroded_region_mask) < 20:
        eroded_region_mask = region_mask.copy()

    patches = []

    for layer in project_state.layers:
        if not layer.visible or not layer.sourcePath:
            continue
        if layer_ids is not None and layer.id not in layer_ids:
            continue

        sw = layer.sourceWidth or 2000
        sh = layer.sourceHeight or 1500

        inv_m = matrix_inverse(layer.sourceToWorld)
        if inv_m is None:
            continue

        # Ánh xạ 4 góc của bounding box vào source pixel
        src_corners = []
        is_finite = True
        for (cx, cy) in box_corners:
            pt = transform_point(inv_m, cx, cy)
            if not (np.isfinite(pt[0]) and np.isfinite(pt[1])):
                is_finite = False
                break
            src_corners.append(pt)

        if not is_finite:
            continue

        src_corners = np.array(src_corners, dtype=np.float32)

        min_sx, min_sy = np.min(src_corners, axis=0)
        max_sx, max_sy = np.max(src_corners, axis=0)
        if max_sx < 0 or min_sx > sw or max_sy < 0 or min_sy > sh:
            continue

        source_path = _resolve_source_path(layer.sourcePath, workspace_root)
        if source_path is None:
            continue

        try:
            full_img = _get_cached_image(source_path)
        except Exception:
            continue

        actual_sh, actual_sw = full_img.shape[:2]

        is_perspective = (
            abs(layer.sourceToWorld[6]) > 1e-6 or
            abs(layer.sourceToWorld[7]) > 1e-6 or
            abs(layer.sourceToWorld[8] - 1.0) > 1e-6
        )

        source_rgb = full_img[:, :, :3] if full_img.ndim == 3 and full_img.shape[2] == 4 else full_img
        src_mask = full_img[:, :, 3] if full_img.ndim == 3 and full_img.shape[2] == 4 else np.full((actual_sh, actual_sw), 255, dtype=np.uint8)

        if is_perspective:
            M_warp = cv2.getPerspectiveTransform(src_corners, dst_box_corners)
            patch = cv2.warpPerspective(source_rgb, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))
            valid_source_mask = cv2.warpPerspective(src_mask, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        else:
            M_warp = cv2.getAffineTransform(src_corners[:3], dst_box_corners[:3])
            patch = cv2.warpAffine(source_rgb, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))
            valid_source_mask = cv2.warpAffine(src_mask, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

        # Tính mask hợp lệ cuối cùng kết hợp giữa source coverage và vùng vẽ
        final_valid_mask = np.minimum(valid_source_mask, region_mask)

        region_pixel_count = np.count_nonzero(region_mask > 0)
        valid_pixel_count = np.count_nonzero(final_valid_mask > 0)
        valid_coverage = float(np.sum(final_valid_mask, dtype=np.float64) / (255.0 * max(1, region_pixel_count)))

        if valid_coverage < 0.005:
            continue

        # Tính độ sắc nét Laplacian chỉ trong score_mask
        gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY) if patch.ndim == 3 else patch
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        score_weights = (final_valid_mask.astype(np.float64) / 255.0) * (eroded_region_mask > 0)
        effective_pixels = float(np.sum(score_weights))
        sufficient_pixels = effective_pixels >= _MIN_SCORE_PIXELS
        if sufficient_pixels:
            weighted_mean = float(np.sum(lap * score_weights) / effective_pixels)
            sharpness_score = float(np.sum(((lap - weighted_mean) ** 2) * score_weights) / effective_pixels)
        else:
            sharpness_score = None

        # Tạo ảnh PNG RGBA với Alpha = 0 ngoài vùng chọn
        if patch.ndim == 3:
            patch_rgba = cv2.cvtColor(patch, cv2.COLOR_RGB2RGBA)
        else:
            patch_rgba = cv2.cvtColor(patch, cv2.COLOR_GRAY2RGBA)
        patch_rgba[:, :, 3] = final_valid_mask

        # Encode patch sang PNG Base64
        patch_bgra = cv2.cvtColor(patch_rgba, cv2.COLOR_RGBA2BGRA)
        success, encoded_buf = cv2.imencode('.png', patch_bgra)
        if not success:
            continue
        data_url = "data:image/png;base64," + base64.b64encode(encoded_buf).decode('utf-8')

        patches.append({
            "layerId": layer.id,
            "sourceId": layer.sourceId,
            "sourcePath": layer.sourcePath,
            "imageDataUrl": data_url,
            # Keep the frontend's numeric display contract while status controls ranking.
            "sharpness": round(sharpness_score, 2) if sharpness_score is not None else 0.0,
            "scoreStatus": "ok" if sufficient_pixels else "insufficient_pixels",
            "validPixelCount": int(valid_pixel_count),
            "validCoverage": round(float(valid_coverage), 3),
            "outputWidth": out_w,
            "outputHeight": out_h,
            "zIndex": layer.zIndex
        })

    patches.sort(key=lambda p: (p["scoreStatus"] == "ok", p["sharpness"]), reverse=True)
    sharpest_layer_id = next((p["layerId"] for p in patches if p["scoreStatus"] == "ok"), None)

    return {
        "shapeType": shape_type,
        "pointsWorld": pts.tolist(),
        "boundingRect": [float(min_x), float(min_y), box_w, box_h],
        "outputWidth": out_w,
        "outputHeight": out_h,
        "patches": patches,
        "sharpestLayerId": sharpest_layer_id
    }


def inspect_patches_at_world_rect(
    project_state: ProjectState,
    world_rect: List[float],
    output_size: int = 256,
    layer_ids: Optional[List[str]] = None,
    workspace_root: Optional[str] = None
) -> Dict[str, Any]:
    """Hàm tương thích ngược với world_rect [x, y, w, h]"""
    return inspect_patches_at_world_region(
        project_state=project_state,
        shape_type="rectangle",
        world_rect=world_rect,
        output_size=output_size,
        layer_ids=layer_ids,
        workspace_root=workspace_root
    )


def extract_native_patch_image(
    layer: ProjectLayer,
    points_world: List[List[float]],
    shape_type: str = "rectangle",
    max_pixels: int = 16777216,
    workspace_root: Optional[str] = None
) -> Dict[str, Any]:
    """
    Trích xuất patch ở độ phân giải gốc siêu nét (Native Resolution) cho Lightbox Modal.
    Trả về bytes ảnh PNG RGBA và metadata.
    """
    if not isinstance(points_world, list) or len(points_world) < 3:
        raise ValueError("points_world phải có ít nhất 3 điểm")
    if len(points_world) > _MAX_REGION_POINTS:
        raise ValueError(f"points_world vượt giới hạn {_MAX_REGION_POINTS} điểm")
    pts = np.array([[float(p[0]), float(p[1])] for p in points_world], dtype=np.float32)
    if not np.all(np.isfinite(pts)):
        raise ValueError("points_world chứa tọa độ không hữu hạn")
    min_x, min_y = np.min(pts, axis=0)
    max_x, max_y = np.max(pts, axis=0)
    box_w = float(max_x - min_x)
    box_h = float(max_y - min_y)

    if box_w <= 0 or box_h <= 0:
        raise ValueError("Vùng chọn không hợp lệ")

    if isinstance(max_pixels, bool):
        raise ValueError("max_pixels không hợp lệ")
    max_pixels = max(1, min(int(max_pixels), _MAX_NATIVE_PIXELS))
    inv_m = matrix_inverse(layer.sourceToWorld)
    if inv_m is None:
        raise ValueError("Ma trận nghịch đảo layer không hợp lệ")

    # Native output sampling follows the source footprint, including scale/rotation.
    world_box = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    native_corners = np.array([transform_point(inv_m, x, y) for x, y in world_box], dtype=np.float64)
    native_w = max(np.linalg.norm(native_corners[1] - native_corners[0]), np.linalg.norm(native_corners[2] - native_corners[3]))
    native_h = max(np.linalg.norm(native_corners[3] - native_corners[0]), np.linalg.norm(native_corners[2] - native_corners[1]))
    if not np.isfinite(native_w) or not np.isfinite(native_h) or native_w <= 0 or native_h <= 0:
        raise ValueError("Source footprint không hợp lệ")
    total_px = max(1.0, native_w * native_h)
    scale = min(1.0, 8192.0 / native_w, 8192.0 / native_h)
    if total_px > max_pixels:
        scale = min(scale, math.sqrt(max_pixels / total_px))

    out_w = max(1, int(math.floor(native_w * scale)))
    out_h = max(1, int(math.floor(native_h * scale)))

    box_corners = np.array([
        [min_x, min_y],
        [max_x, min_y],
        [max_x, max_y],
        [min_x, max_y]
    ], dtype=np.float32)

    dst_box_corners = np.array([
        [0.0, 0.0],
        [float(out_w), 0.0],
        [float(out_w), float(out_h)],
        [0.0, float(out_h)]
    ], dtype=np.float32)

    dst_poly_pts = np.zeros_like(pts, dtype=np.int32)
    for i, (px, py) in enumerate(pts):
        dst_poly_pts[i] = [
            int(round((px - min_x) * (out_w / box_w))),
            int(round((py - min_y) * (out_h / box_h)))
        ]

    region_mask = np.zeros((out_h, out_w), dtype=np.uint8)
    if shape_type in ["polygon", "lasso"]:
        cv2.fillPoly(region_mask, [dst_poly_pts], 255)
    else:
        region_mask[:, :] = 255

    src_corners = np.array([transform_point(inv_m, cx, cy) for (cx, cy) in box_corners], dtype=np.float32)

    source_path = _resolve_source_path(layer.sourcePath, workspace_root)
    if source_path is None:
        raise FileNotFoundError(f"Không tìm thấy file ảnh nguồn: {layer.sourcePath}")

    full_img = _get_cached_image(source_path)
    actual_sh, actual_sw = full_img.shape[:2]

    is_perspective = (
        abs(layer.sourceToWorld[6]) > 1e-6 or
        abs(layer.sourceToWorld[7]) > 1e-6 or
        abs(layer.sourceToWorld[8] - 1.0) > 1e-6
    )

    source_rgb = full_img[:, :, :3] if full_img.ndim == 3 and full_img.shape[2] == 4 else full_img
    src_mask = full_img[:, :, 3] if full_img.ndim == 3 and full_img.shape[2] == 4 else np.full((actual_sh, actual_sw), 255, dtype=np.uint8)

    if is_perspective:
        M_warp = cv2.getPerspectiveTransform(src_corners, dst_box_corners)
        patch = cv2.warpPerspective(source_rgb, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))
        valid_source_mask = cv2.warpPerspective(src_mask, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    else:
        M_warp = cv2.getAffineTransform(src_corners[:3], dst_box_corners[:3])
        patch = cv2.warpAffine(source_rgb, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))
        valid_source_mask = cv2.warpAffine(src_mask, M_warp, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    final_mask = cv2.bitwise_and(valid_source_mask, region_mask)

    if patch.ndim == 3:
        patch_rgba = cv2.cvtColor(patch, cv2.COLOR_RGB2RGBA)
    else:
        patch_rgba = cv2.cvtColor(patch, cv2.COLOR_GRAY2RGBA)
    patch_rgba[:, :, 3] = final_mask

    patch_bgra = cv2.cvtColor(patch_rgba, cv2.COLOR_RGBA2BGRA)
    success, encoded_buf = cv2.imencode('.png', patch_bgra)
    if not success:
        raise RuntimeError("Không thể encode ảnh PNG")

    return {
        "png_bytes": encoded_buf.tobytes(),
        "width": out_w,
        "height": out_h,
        "sampling_scale": scale,
        "valid_coverage": float(np.count_nonzero(final_mask) / max(1, np.count_nonzero(region_mask))),
        "is_resolution_limited": (scale < 0.999)
    }
