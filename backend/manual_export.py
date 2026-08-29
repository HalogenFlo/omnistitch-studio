"""
Chức năng: Render Server-side Full-Resolution WSI từ Manual Project State
Lí do tạo: Không xuất qua canvas base64 trên browser để tránh crash RAM, render theo tile/chunk chất lượng gốc
Đường dẫn: tool/image_alignment/backend/manual_export.py
"""

import os
import json
import math
import shutil
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw
from typing import Dict, Any, Optional, Tuple, Callable
from .project_schemas import ProjectState, matrix_inverse, transform_point
from .io_utils import read_image_region, read_image_universal, resolve_file_path
from .wsi_exporter import (
    _publish_staged_artifacts,
    export_wsi_multiformat,
    generate_dzi_pyramid_bounded,
    write_tiled_tiff,
)

def get_max_memory_mb():
    env_val = os.environ.get("IMAGE_ALIGNMENT_MAX_MEMORY_MB")
    if env_val:
        try:
            return max(64, int(env_val))
        except ValueError:
            pass
    try:
        import psutil
        avail_mb = int(psutil.virtual_memory().available * 0.75 / (1024 * 1024))
        return max(8192, avail_mb)
    except Exception:
        return 8192

def calculate_project_bounding_box(project: ProjectState) -> Tuple[int, int, int, int]:
    """Tính toán bounding box tổng [min_x, min_y, max_x, max_y] của toàn bộ các layer visible"""
    all_corners = []
    
    for layer in project.layers:
        if not layer.visible:
            continue
        w, h = layer.sourceWidth, layer.sourceHeight
        corners = [(0, 0), (w, 0), (w, h), (0, h)]
        m = layer.sourceToWorld
        for cx, cy in corners:
            wx, wy = transform_point(m, cx, cy)
            all_corners.append((wx, wy))
            
    if not all_corners:
        return 0, 0, 1000, 1000
        
    xs = [c[0] for c in all_corners]
    ys = [c[1] for c in all_corners]
    
    min_x = int(np.floor(min(xs)))
    min_y = int(np.floor(min(ys)))
    max_x = int(np.ceil(max(xs)))
    max_y = int(np.ceil(max(ys)))
    
    return min_x, min_y, max_x, max_y


def _manual_output_geometry(project: ProjectState):
    min_x, min_y, max_x, max_y = calculate_project_bounding_box(project)
    canvas_w = max(1, max_x - min_x)
    canvas_h = max(1, max_y - min_y)
    out_x1, out_y1, out_x2, out_y2 = min_x, min_y, max_x, max_y
    crop_obj = getattr(project, "cropRegion", getattr(project, "keepRegion", None))
    crop_info = {
        "cropApplied": False,
        "cropBoundsWorld": [min_x, min_y, canvas_w, canvas_h],
        "outputWidth": canvas_w,
        "outputHeight": canvas_h,
        "outputPixelToWorld": [1.0, 0.0, float(min_x), 0.0, 1.0, float(min_y), 0.0, 0.0, 1.0],
        "worldToOutputPixel": [1.0, 0.0, float(-min_x), 0.0, 1.0, float(-min_y), 0.0, 0.0, 1.0],
    }
    if crop_obj and crop_obj.pointsWorld and len(crop_obj.pointsWorld) >= 3:
        bx, by, bw, bh = crop_obj.boundingRect
        padding = getattr(getattr(project, "cropSettings", None), "paddingWorld", 0.0) or 0.0
        crop_x1 = max(min_x, int(np.floor(bx - padding)))
        crop_y1 = max(min_y, int(np.floor(by - padding)))
        crop_x2 = min(max_x, int(np.ceil(bx + bw + padding)))
        crop_y2 = min(max_y, int(np.ceil(by + bh + padding)))
        crop_info["cropApplied"] = True
        crop_info["cropBoundsWorld"] = [crop_x1, crop_y1, max(0, crop_x2 - crop_x1), max(0, crop_y2 - crop_y1)]
        settings = getattr(project, "cropSettings", None)
        if settings and getattr(settings, "trimOutputBounds", True) and crop_x2 > crop_x1 and crop_y2 > crop_y1:
            out_x1, out_y1, out_x2, out_y2 = crop_x1, crop_y1, crop_x2, crop_y2
            width, height = out_x2 - out_x1, out_y2 - out_y1
            crop_info.update({
                "cropBoundsWorld": [out_x1, out_y1, width, height],
                "outputWidth": width,
                "outputHeight": height,
                "outputPixelToWorld": [1.0, 0.0, float(out_x1), 0.0, 1.0, float(out_y1), 0.0, 0.0, 1.0],
                "worldToOutputPixel": [1.0, 0.0, float(-out_x1), 0.0, 1.0, float(-out_y1), 0.0, 0.0, 1.0],
            })
    return (min_x, min_y, max_x, max_y), (out_x1, out_y1, out_x2, out_y2), crop_info


def _bounds_intersect(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _points_bounds(points, padding=0.0):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs) - padding, min(ys) - padding, max(xs) + padding, max(ys) + padding


def _layer_world_bounds(layer):
    corners = [transform_point(layer.sourceToWorld, x, y) for x, y in (
        (0, 0), (layer.sourceWidth, 0), (layer.sourceWidth, layer.sourceHeight), (0, layer.sourceHeight)
    )]
    return _points_bounds(corners)


def _adjust_source_rgb(image, layer):
    adjusted = image.astype(np.float32)
    if layer.contrast != 1.0 or layer.brightness != 1.0:
        adjusted = (adjusted - 127.5) * layer.contrast + 127.5 + (layer.brightness - 1.0) * 255.0
        adjusted = np.clip(adjusted, 0.0, 255.0)
    if layer.saturation != 1.0:
        hsv = cv2.cvtColor(adjusted.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * layer.saturation, 0, 255)
        adjusted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    return adjusted


def _polygon_tile_points(points, canvas_origin, output_origin, tile_offset, use_round=False):
    canvas_x, canvas_y = canvas_origin
    output_x, output_y = output_origin
    offset_x, offset_y = tile_offset
    crop_x, crop_y = output_x - canvas_x, output_y - canvas_y
    convert = round if use_round else int
    return np.array([
        [convert(point[0] - canvas_x) - crop_x - offset_x, convert(point[1] - canvas_y) - crop_y - offset_y]
        for point in points
    ], dtype=np.int32)


def _fill_polygon(mask, points, value):
    """Rasterize polygons consistently even when points extend beyond a tile."""
    encoded = np.clip(mask * 255.0, 0, 255).astype(np.uint8)
    image = Image.fromarray(encoded, mode='L')
    ImageDraw.Draw(image).polygon([tuple(map(int, point)) for point in points], fill=int(round(value * 255.0)))
    mask[:] = np.asarray(image, dtype=np.float32) / 255.0


def _close_memmap(array):
    if isinstance(array, np.memmap):
        array.flush()
        array._mmap.close()


def _warp_layer_for_tile(layer, workspace_root, tile_world_bounds, tile_shape, memory_budget_bytes, tile_bytes, stats):
    if not _bounds_intersect(_layer_world_bounds(layer), tile_world_bounds):
        return None, None
    inverse = matrix_inverse(layer.sourceToWorld)
    if inverse is None:
        return None, None
    x1, y1, x2, y2 = tile_world_bounds
    source_corners = [transform_point(inverse, x, y) for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
    if not np.all(np.isfinite(source_corners)):
        return None, None
    sx1 = max(0, int(math.floor(min(point[0] for point in source_corners))) - 2)
    sy1 = max(0, int(math.floor(min(point[1] for point in source_corners))) - 2)
    sx2 = min(layer.sourceWidth, int(math.ceil(max(point[0] for point in source_corners))) + 2)
    sy2 = min(layer.sourceHeight, int(math.ceil(max(point[1] for point in source_corners))) + 2)
    if sx2 <= sx1 or sy2 <= sy1:
        return None, None
    roi_pixels = (sx2 - sx1) * (sy2 - sy1)
    estimated = tile_bytes + roi_pixels * 32
    if estimated > memory_budget_bytes:
        raise MemoryError(
            f"Source ROI {sx2 - sx1}x{sy2 - sy1} làm working set {estimated} bytes vượt budget {memory_budget_bytes} bytes"
        )
    stats["maxSourceRoiPixels"] = max(stats["maxSourceRoiPixels"], roi_pixels)
    stats["maxEstimatedWorkingBytes"] = max(stats["maxEstimatedWorkingBytes"], estimated)
    source_path = resolve_file_path(layer.sourcePath, workspace_root)
    decoded = read_image_region(source_path, (sx1, sy1, sx2, sy2))
    if decoded.size == 0:
        return None, None
    source_rgb = decoded[:, :, :3]
    source_alpha = decoded[:, :, 3].astype(np.float32) / 255.0 if decoded.shape[2] == 4 else np.ones(decoded.shape[:2], dtype=np.float32)
    adjusted = _adjust_source_rgb(source_rgb, layer)
    layer_alpha = source_alpha * layer.opacity
    premul = (adjusted / 255.0) * layer_alpha[:, :, None]
    source_offset = np.array([[1.0, 0.0, sx1], [0.0, 1.0, sy1], [0.0, 0.0, 1.0]], dtype=np.float64)
    tile_offset = np.array([[1.0, 0.0, -x1], [0.0, 1.0, -y1], [0.0, 0.0, 1.0]], dtype=np.float64)
    transform = tile_offset @ np.asarray(layer.sourceToWorld, dtype=np.float64).reshape(3, 3) @ source_offset
    width, height = tile_shape[1], tile_shape[0]
    perspective = abs(transform[2, 0]) > 1e-6 or abs(transform[2, 1]) > 1e-6 or abs(transform[2, 2] - 1.0) > 1e-6
    if perspective:
        warped_rgb = cv2.warpPerspective(premul, transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        warped_alpha = cv2.warpPerspective(layer_alpha, transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    else:
        warped_rgb = cv2.warpAffine(premul, transform[:2], (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        warped_alpha = cv2.warpAffine(layer_alpha, transform[:2], (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return warped_rgb, np.clip(warped_alpha, 0.0, 1.0)


def _render_manual_tile(
    project,
    workspace_root,
    canvas_bounds,
    output_bounds,
    core_box,
    halo,
    background_mode,
    memory_budget_bytes,
    stats,
):
    output_width = output_bounds[2] - output_bounds[0]
    output_height = output_bounds[3] - output_bounds[1]
    core_x1, core_y1, core_x2, core_y2 = core_box
    ext_x1 = max(0, core_x1 - halo)
    ext_y1 = max(0, core_y1 - halo)
    ext_x2 = min(output_width, core_x2 + halo)
    ext_y2 = min(output_height, core_y2 + halo)
    ext_h, ext_w = ext_y2 - ext_y1, ext_x2 - ext_x1
    tile_world = (
        output_bounds[0] + ext_x1,
        output_bounds[1] + ext_y1,
        output_bounds[0] + ext_x2,
        output_bounds[1] + ext_y2,
    )
    tile_bytes = ext_w * ext_h * 80
    if tile_bytes > memory_budget_bytes:
        raise MemoryError(f"Tile working set {tile_bytes} bytes vượt budget {memory_budget_bytes} bytes")
    stats["maxExpandedTilePixels"] = max(stats["maxExpandedTilePixels"], ext_w * ext_h)
    stats["maxEstimatedWorkingBytes"] = max(stats["maxEstimatedWorkingBytes"], tile_bytes)
    composite = np.zeros((ext_h, ext_w, 4), dtype=np.float32)

    visible_layers = sorted((layer for layer in project.layers if layer.visible), key=lambda layer: layer.zIndex)
    for layer in visible_layers:
        warped_rgb, warped_alpha = _warp_layer_for_tile(
            layer, workspace_root, tile_world, (ext_h, ext_w), memory_budget_bytes, tile_bytes, stats
        )
        if warped_rgb is None:
            continue
        inverse_alpha = 1.0 - warped_alpha
        composite[:, :, :3] = warped_rgb + composite[:, :, :3] * inverse_alpha[:, :, None]
        composite[:, :, 3] = warped_alpha + composite[:, :, 3] * inverse_alpha

    canvas_origin = canvas_bounds[:2]
    output_origin = output_bounds[:2]
    tile_offset = (ext_x1, ext_y1)
    layer_by_id = {layer.id: layer for layer in project.layers}
    for region in sorted(project.focusRegions, key=lambda item: item.order):
        if region.geometryRevision != project.geometryRevision or not region.pointsWorld:
            continue
        layer = layer_by_id.get(region.selectedLayerId)
        if not layer or not layer.visible or not _bounds_intersect(_points_bounds(region.pointsWorld), tile_world):
            continue
        warped_rgb, warped_alpha = _warp_layer_for_tile(
            layer, workspace_root, tile_world, (ext_h, ext_w), memory_budget_bytes, tile_bytes, stats
        )
        if warped_rgb is None:
            continue
        region_mask = np.zeros((ext_h, ext_w), dtype=np.float32)
        points = _polygon_tile_points(region.pointsWorld, canvas_origin, output_origin, tile_offset)
        _fill_polygon(region_mask, points, 1.0)
        feather = max(0, int(round(region.featherPx)))
        if feather:
            distance = cv2.distanceTransform((region_mask * 255).astype(np.uint8), cv2.DIST_L2, 5)
            soft_inside = region_mask * np.clip(distance / float(feather), 0.0, 1.0)
        else:
            soft_inside = region_mask
        focus_alpha = warped_alpha * soft_inside
        composite[:, :, :3] = warped_rgb * soft_inside[:, :, None] + composite[:, :, :3] * (1.0 - focus_alpha[:, :, None])
        composite[:, :, 3] = focus_alpha + composite[:, :, 3] * (1.0 - focus_alpha)

    crop_mask = np.ones((ext_h, ext_w), dtype=np.float32)
    crop = getattr(project, "cropRegion", getattr(project, "keepRegion", None))
    if crop and crop.pointsWorld and len(crop.pointsWorld) >= 3:
        crop_mask.fill(0.0)
        points = _polygon_tile_points(crop.pointsWorld, canvas_origin, output_origin, tile_offset)
        _fill_polygon(crop_mask, points, 1.0)

    mask_alpha = np.ones((ext_h, ext_w), dtype=np.float32)
    for region in sorted(project.maskRegions, key=lambda item: item.order):
        if not region.pointsWorld:
            continue
        radius = max(1, int(round(region.radiusWorld)))
        if not _bounds_intersect(_points_bounds(region.pointsWorld, radius if region.shapeType == 'brush' else 0), tile_world):
            continue
        value = 0.0 if region.operation == 'exclude' else 1.0
        points = _polygon_tile_points(region.pointsWorld, canvas_origin, output_origin, tile_offset, use_round=True)
        point_tuples = [tuple(point) for point in points]
        if region.shapeType == 'brush' or len(points) < 3:
            for index in range(len(point_tuples) - 1):
                cv2.line(mask_alpha, point_tuples[index], point_tuples[index + 1], value, thickness=radius * 2)
            for point in point_tuples:
                cv2.circle(mask_alpha, point, radius, value, thickness=-1)
        else:
            _fill_polygon(mask_alpha, points, value)

    final_alpha = composite[:, :, 3] * crop_mask * mask_alpha
    valid_mask = (final_alpha > 0.1).astype(np.uint8) * 255
    straight_rgb = np.zeros_like(composite[:, :, :3])
    covered = composite[:, :, 3] > 1e-8
    straight_rgb[covered] = composite[:, :, :3][covered] / composite[:, :, 3][covered, None]
    straight_rgb = np.clip(straight_rgb * 255.0, 0.0, 255.0)
    straight_rgb[final_alpha <= 1e-8] = 0.0
    if background_mode == 'transparent':
        result = np.dstack((straight_rgb, final_alpha * 255.0)).astype(np.uint8)
    else:
        background = 255.0 if background_mode == 'white' else 0.0
        result = np.clip(straight_rgb * final_alpha[:, :, None] + background * (1.0 - final_alpha[:, :, None]), 0, 255).astype(np.uint8)
    slice_y1, slice_x1 = core_y1 - ext_y1, core_x1 - ext_x1
    core_h, core_w = core_y2 - core_y1, core_x2 - core_x1
    return result[slice_y1:slice_y1 + core_h, slice_x1:slice_x1 + core_w], valid_mask[slice_y1:slice_y1 + core_h, slice_x1:slice_x1 + core_w]

def render_manual_wsi_composite(
    project: ProjectState,
    workspace_root: str,
    background_mode: str = "transparent",
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[np.ndarray, Optional[np.ndarray], Dict[str, Any]]:
    """
    Render toàn bộ các layer theo thứ tự zIndex từ ảnh gốc full-res.
    Áp dụng:
      1. Layer Warp & Color Adjustments.
      2. Focus Regions (Polygon, Lasso, Rectangle) với Inward-only feathering.
      3. Exclusion / Restore Strokes (Cọ xóa / khôi phục).
      4. KeepRegion & CropSettings (Cắt gọn bounding box).
      5. Background transparent (RGBA) và Companion Training Mask.
    """
    if progress_callback:
        progress_callback(10, "Đang tính toán bounding box canvas...")

    min_x, min_y, max_x, max_y = calculate_project_bounding_box(project)
    canvas_w = max(1, max_x - min_x)
    canvas_h = max(1, max_y - min_y)

    MAX_DIM = 45000
    if canvas_w > MAX_DIM or canvas_h > MAX_DIM:
        raise ValueError(f"Canvas quá lớn: {canvas_w}x{canvas_h} vượt giới hạn {MAX_DIM}px")
    max_memory_mb = get_max_memory_mb()
    estimated_bytes = canvas_w * canvas_h * 32
    if estimated_bytes > max_memory_mb * 1024 * 1024:
        raise MemoryError(
            f"Render cần khoảng {estimated_bytes / (1024 * 1024):.0f} MB, vượt budget {max_memory_mb} MB"
        )

    # Composite RGBA (Float32 để hòa trộn chính xác)
    composite = np.zeros((canvas_h, canvas_w, 4), dtype=np.float32)
    source_coverage = np.zeros((canvas_h, canvas_w), dtype=np.float32)

    # 1. Ghép các layer cơ sở
    sorted_layers = sorted(project.layers, key=lambda l: l.zIndex)
    visible_layers = [l for l in sorted_layers if l.visible]
    total_layers = len(visible_layers)

    for idx, layer in enumerate(visible_layers):
        if progress_callback:
            p = 15 + int(45 * (idx / max(1, total_layers)))
            progress_callback(p, f"Đang render layer {idx+1}/{total_layers}: {layer.sourceId}")

        src_path = resolve_file_path(layer.sourcePath, workspace_root)
        img_rgb, alpha, is_16bit = read_image_universal(src_path)
        if img_rgb is None:
            continue

        h, w = img_rgb.shape[:2]
        img_f = img_rgb.astype(np.float32)

        if layer.contrast != 1.0 or layer.brightness != 1.0:
            img_f = (img_f - 127.5) * layer.contrast + 127.5 + (layer.brightness - 1.0) * 255.0
            img_f = np.clip(img_f, 0.0, 255.0)

        if layer.saturation != 1.0:
            hsv = cv2.cvtColor(img_f.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * layer.saturation, 0, 255)
            img_f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)

        m = layer.sourceToWorld
        M_world = np.array(m, dtype=np.float64).reshape((3, 3))
        T_offset = np.array([[1.0, 0.0, -min_x],
                             [0.0, 1.0, -min_y],
                             [0.0, 0.0, 1.0]], dtype=np.float64)
        M_canvas = np.dot(T_offset, M_world)

        is_perspective = (
            abs(layer.sourceToWorld[6]) > 1e-6 or
            abs(layer.sourceToWorld[7]) > 1e-6 or
            abs(layer.sourceToWorld[8] - 1.0) > 1e-6
        )

        source_alpha = (alpha.astype(np.float32) / 255.0) if alpha is not None else np.ones((h, w), dtype=np.float32)
        layer_alpha = source_alpha * layer.opacity
        source_premul = (img_f / 255.0) * source_alpha[:, :, None] * layer.opacity
        if is_perspective:
            warped_img = cv2.warpPerspective(source_premul, M_canvas, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
            warped_mask = cv2.warpPerspective(layer_alpha, M_canvas, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
        else:
            M_affine = M_canvas[:2, :]
            warped_img = cv2.warpAffine(source_premul, M_affine, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
            warped_mask = cv2.warpAffine(layer_alpha, M_affine, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)

        # Premultiplied alpha-over. RGB stays premultiplied until final encoding.
        src_a = np.clip(warped_mask, 0.0, 1.0)
        inv_a = 1.0 - src_a
        composite[:, :, :3] = warped_img + composite[:, :, :3] * inv_a[:, :, None]
        composite[:, :, 3] = src_a + composite[:, :, 3] * inv_a
        source_coverage = composite[:, :, 3].copy()

    # 2. Áp dụng Focus Regions (Polygon, Lasso, Rectangle)
    if hasattr(project, "focusRegions") and project.focusRegions:
        if progress_callback:
            progress_callback(65, "Đang hòa trộn các vùng nét đã chọn (Focus Regions)...")

        for fr in sorted(project.focusRegions, key=lambda region: region.order):
            if fr.geometryRevision != project.geometryRevision:
                continue
            target_layer = next((l for l in project.layers if l.id == fr.selectedLayerId and l.visible), None)
            if not target_layer:
                continue

            src_path = resolve_file_path(target_layer.sourcePath, workspace_root)
            img_rgb, alpha, _ = read_image_universal(src_path)
            if img_rgb is None:
                continue

            h, w = img_rgb.shape[:2]
            img_f = img_rgb.astype(np.float32)

            if target_layer.contrast != 1.0 or target_layer.brightness != 1.0:
                img_f = (img_f - 127.5) * target_layer.contrast + 127.5 + (target_layer.brightness - 1.0) * 255.0
                img_f = np.clip(img_f, 0.0, 255.0)

            if target_layer.saturation != 1.0:
                hsv = cv2.cvtColor(img_f.astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[:, :, 1] = np.clip(hsv[:, :, 1] * target_layer.saturation, 0, 255)
                img_f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)

            m = target_layer.sourceToWorld
            M_world = np.array(m, dtype=np.float64).reshape((3, 3))
            T_offset = np.array([[1.0, 0.0, -min_x],
                                 [0.0, 1.0, -min_y],
                                 [0.0, 0.0, 1.0]], dtype=np.float64)
            M_canvas = np.dot(T_offset, M_world)

            is_perspective = (
                abs(target_layer.sourceToWorld[6]) > 1e-6 or
                abs(target_layer.sourceToWorld[7]) > 1e-6 or
                abs(target_layer.sourceToWorld[8] - 1.0) > 1e-6
            )

            source_alpha = (alpha.astype(np.float32) / 255.0) if alpha is not None else np.ones((h, w), dtype=np.float32)
            source_premul = (img_f / 255.0) * source_alpha[:, :, None] * target_layer.opacity
            source_alpha *= target_layer.opacity
            if is_perspective:
                warped_img = cv2.warpPerspective(source_premul, M_canvas, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
                warped_layer_mask = cv2.warpPerspective(source_alpha, M_canvas, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
            else:
                M_affine = M_canvas[:2, :]
                warped_img = cv2.warpAffine(source_premul, M_affine, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
                warped_layer_mask = cv2.warpAffine(source_alpha, M_affine, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)

            # Tạo polygon/lasso mask trong canvas space
            pts_canvas = np.array([[p[0] - min_x, p[1] - min_y] for p in fr.pointsWorld], dtype=np.int32)
            region_mask = np.zeros((canvas_h, canvas_w), dtype=np.float32)
            _fill_polygon(region_mask, pts_canvas, 1.0)

            # Inward-only feathering để không lấn sang ngoài vùng
            feather = max(0, int(round(fr.featherPx)))
            if feather:
                distance = cv2.distanceTransform((region_mask * 255).astype(np.uint8), cv2.DIST_L2, 5)
                soft_inside = region_mask * np.clip(distance / max(1.0, float(feather)), 0.0, 1.0)
            else:
                soft_inside = region_mask
            final_fr_mask = warped_layer_mask * soft_inside

            inv_fr = 1.0 - final_fr_mask
            # warped_img is premultiplied by layer alpha; shape/feather adds the remaining coverage.
            composite[:, :, :3] = warped_img * soft_inside[:, :, None] + composite[:, :, :3] * inv_fr[:, :, None]
            composite[:, :, 3] = final_fr_mask + composite[:, :, 3] * inv_fr
            source_coverage = composite[:, :, 3].copy()

    # 3. Áp dụng CropRegion / KeepRegion
    crop_mask = np.ones((canvas_h, canvas_w), dtype=np.float32)
    crop_obj = getattr(project, "cropRegion", getattr(project, "keepRegion", None))
    if crop_obj and crop_obj.pointsWorld and len(crop_obj.pointsWorld) >= 3:
        if progress_callback:
            progress_callback(75, "Đang áp dụng vùng cắt (CropRegion)...")
        crop_pts_canvas = np.array([[p[0] - min_x, p[1] - min_y] for p in crop_obj.pointsWorld], dtype=np.int32)
        crop_mask = np.zeros((canvas_h, canvas_w), dtype=np.float32)
        _fill_polygon(crop_mask, crop_pts_canvas, 1.0)

    # 4. Áp dụng MaskRegions (Cọ xóa tàng hình / khôi phục)
    mask_regions = getattr(project, "maskRegions", getattr(project, "exclusionStrokes", []))
    mask_alpha = np.ones((canvas_h, canvas_w), dtype=np.float32)
    if mask_regions:
        if progress_callback:
            progress_callback(80, "Đang áp dụng các nét cọ/mask (MaskRegions)...")
        # Sắp xếp theo order
        sorted_masks = sorted(mask_regions, key=lambda m: getattr(m, 'order', 0))
        for m in sorted_masks:
            if not m.pointsWorld:
                continue
            stroke_pts_canvas = [(int(round(p[0] - min_x)), int(round(p[1] - min_y))) for p in m.pointsWorld]
            radius = max(1, int(round(getattr(m, 'radiusWorld', 20.0))))
            val = 0.0 if m.operation == "exclude" else 1.0

            if m.shapeType == 'brush' or len(stroke_pts_canvas) < 3:
                for i in range(len(stroke_pts_canvas) - 1):
                    p1 = stroke_pts_canvas[i]
                    p2 = stroke_pts_canvas[i + 1]
                    cv2.line(mask_alpha, p1, p2, val, thickness=radius * 2)
                for p in stroke_pts_canvas:
                    cv2.circle(mask_alpha, p, radius, val, thickness=-1)
            else:
                pts_arr = np.array(stroke_pts_canvas, dtype=np.int32)
                _fill_polygon(mask_alpha, pts_arr, val)

    # 5. Tính Alpha cuối cùng & Companion Training Mask (Section 14 & 15)
    # Restore chỉ phục hồi tới mức composite coverage trước mask
    final_alpha = source_coverage * crop_mask * mask_alpha
    valid_training_mask = (final_alpha > 0.1).astype(np.uint8) * 255

    # Đặt RGB = 0 tại các pixel có Alpha = 0 (tránh rò dữ liệu)
    straight_rgb = np.zeros_like(composite[:, :, :3])
    covered = composite[:, :, 3] > 1e-8
    straight_rgb[covered] = composite[:, :, :3][covered] / composite[:, :, 3][covered, None]
    straight_rgb = np.clip(straight_rgb * 255.0, 0.0, 255.0)
    straight_rgb[final_alpha <= 1e-8] = 0.0

    if background_mode != "transparent":
        # Chuyển nền sang trắng hoặc đen
        bg_val = 255.0 if background_mode == "white" else 0.0
        alpha_ratio = final_alpha[:, :, None]
        composite_rgb = straight_rgb * alpha_ratio + bg_val * (1.0 - alpha_ratio)
        final_img = np.clip(composite_rgb, 0, 255).astype(np.uint8)
    else:
        final_img = np.dstack((straight_rgb, final_alpha * 255.0)).astype(np.uint8)

    # 6. Xử lý Crop Bounding Box theo CropRegion / CropSettings (Section 4 & 9)
    crop_info = {
        "cropApplied": False,
        "cropBoundsWorld": [min_x, min_y, canvas_w, canvas_h],
        "outputWidth": canvas_w,
        "outputHeight": canvas_h,
        "outputPixelToWorld": [1.0, 0.0, float(min_x), 0.0, 1.0, float(min_y), 0.0, 0.0, 1.0],
        "worldToOutputPixel": [1.0, 0.0, float(-min_x), 0.0, 1.0, float(-min_y), 0.0, 0.0, 1.0]
    }

    if crop_obj and crop_obj.pointsWorld and len(crop_obj.pointsWorld) >= 3:
        bx, by, bw, bh = crop_obj.boundingRect
        pad = getattr(getattr(project, "cropSettings", None), "paddingWorld", 0.0) or 0.0
        shape_x1 = max(min_x, int(np.floor(bx - pad)))
        shape_y1 = max(min_y, int(np.floor(by - pad)))
        shape_x2 = min(max_x, int(np.ceil(bx + bw + pad)))
        shape_y2 = min(max_y, int(np.ceil(by + bh + pad)))
        crop_info["cropApplied"] = True
        crop_info["cropBoundsWorld"] = [shape_x1, shape_y1, max(0, shape_x2 - shape_x1), max(0, shape_y2 - shape_y1)]

    if crop_obj and crop_obj.pointsWorld and len(crop_obj.pointsWorld) >= 3:
        crop_settings = getattr(project, "cropSettings", None)
        if crop_settings and getattr(crop_settings, "trimOutputBounds", True):
            bx, by, bw, bh = crop_obj.boundingRect
            pad = getattr(crop_settings, "paddingWorld", 0.0) or 0.0

            # Half-open integer bounds
            cb_x1 = max(min_x, int(np.floor(bx - pad)))
            cb_y1 = max(min_y, int(np.floor(by - pad)))
            cb_x2 = min(max_x, int(np.ceil(bx + bw + pad)))
            cb_y2 = min(max_y, int(np.ceil(by + bh + pad)))

            crop_x1 = max(0, cb_x1 - min_x)
            crop_y1 = max(0, cb_y1 - min_y)
            crop_x2 = min(canvas_w, cb_x2 - min_x)
            crop_y2 = min(canvas_h, cb_y2 - min_y)

            if crop_x2 > crop_x1 and crop_y2 > crop_y1:
                final_img = final_img[crop_y1:crop_y2, crop_x1:crop_x2]
                valid_training_mask = valid_training_mask[crop_y1:crop_y2, crop_x1:crop_x2]
                actual_w = crop_x2 - crop_x1
                actual_h = crop_y2 - crop_y1
                crop_info = {
                    "cropApplied": True,
                    "cropBoundsWorld": [cb_x1, cb_y1, actual_w, actual_h],
                    "outputWidth": actual_w,
                    "outputHeight": actual_h,
                    "outputPixelToWorld": [1.0, 0.0, float(cb_x1), 0.0, 1.0, float(cb_y1), 0.0, 0.0, 1.0],
                    "worldToOutputPixel": [1.0, 0.0, float(-cb_x1), 0.0, 1.0, float(-cb_y1), 0.0, 0.0, 1.0]
                }

    if progress_callback:
        progress_callback(88, "Hoàn tất xử lý mặt nạ và composite!")

    return final_img, valid_training_mask, crop_info


def export_manual_project_tiled(
    project: ProjectState,
    output_dir: str,
    workspace_root: str,
    output_name: Optional[str] = None,
    background_mode: str = "transparent",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    memory_budget_bytes: Optional[int] = None,
    tile_size: Optional[int] = None,
    target_ext: str = "tif",
) -> Dict[str, Any]:
    """Render and publish TIFF, mask, metadata, and DZI without full-canvas RAM arrays."""
    os.makedirs(output_dir, exist_ok=True)
    folder_name = output_name or project.folderName or "manual_wsi"
    if not folder_name or os.path.basename(folder_name) != folder_name:
        raise ValueError("Tên output không hợp lệ")
    target_ext = target_ext.lower().lstrip('.')
    if target_ext not in ("tif", "tiff"):
        raise ValueError("Tiled manual export chỉ hỗ trợ TIFF/BigTIFF")
    canvas_bounds, output_bounds, crop_info = _manual_output_geometry(project)
    width = output_bounds[2] - output_bounds[0]
    height = output_bounds[3] - output_bounds[1]
    if width <= 0 or height <= 0:
        raise ValueError("Output bounds không hợp lệ")
    max_dimension = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_TILED_DIMENSION", "100000")))
    max_pixels = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_TILED_PIXELS", "2000000000")))
    if width > max_dimension or height > max_dimension:
        raise ValueError(f"Tiled output {width}x{height} vượt giới hạn chiều {max_dimension}px")
    output_pixels = width * height
    if output_pixels > max_pixels:
        raise ValueError(f"Tiled output {output_pixels} pixels vượt giới hạn {max_pixels} pixels")
    budget = memory_budget_bytes
    if budget is None:
        budget = int(os.environ.get(
            "IMAGE_ALIGNMENT_MAX_MEMORY_BYTES",
            str(get_max_memory_mb() * 1024 * 1024),
        ))
    if budget < 8 * 1024 * 1024:
        raise ValueError("Tiled export yêu cầu memory budget tối thiểu 8388608 bytes")
    requested_tile = tile_size or int(os.environ.get("IMAGE_ALIGNMENT_TILE_SIZE", "512"))
    requested_tile = max(64, min(2048, requested_tile))
    max_feather = max((int(math.ceil(region.featherPx)) for region in project.focusRegions), default=0)
    max_brush = max((int(math.ceil(region.radiusWorld)) for region in project.maskRegions if region.shapeType == 'brush'), default=0)
    halo = max_feather + max_brush + 2
    actual_tile = requested_tile
    while actual_tile > 64 and (actual_tile + 2 * halo) ** 2 * 80 > budget:
        actual_tile //= 2
    if (actual_tile + 2 * halo) ** 2 * 80 > budget:
        raise MemoryError(f"Halo {halo}px không vừa memory budget {budget} bytes")

    channels = 4 if background_mode == 'transparent' else 3
    tile_count = int(math.ceil(width / actual_tile) * math.ceil(height / actual_tile))
    max_tiles = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_TILED_TILES", "10000000")))
    if tile_count > max_tiles:
        raise ValueError(f"Tiled output cần {tile_count} tiles, vượt giới hạn {max_tiles}")
    # Account for render memmaps, TIFF/mask output, and a conservative DZI allowance.
    required_disk = output_pixels * (3 * (channels + 1) + 2) + 256 * 1024 * 1024
    free_disk = shutil.disk_usage(output_dir).free
    if required_disk > free_disk:
        raise OSError(f"Không đủ dung lượng export: cần khoảng {required_disk} bytes, còn {free_disk} bytes")
    stage_root = tempfile.mkdtemp(prefix=f".{folder_name}.tiled.", dir=output_dir)
    image_map_path = os.path.join(stage_root, "render.dat")
    mask_map_path = os.path.join(stage_root, "mask.dat")
    image_map = np.memmap(image_map_path, mode='w+', dtype=np.uint8, shape=(height, width, channels))
    mask_map = np.memmap(mask_map_path, mode='w+', dtype=np.uint8, shape=(height, width))
    stats = {
        "tileSize": actual_tile,
        "halo": halo,
        "memoryBudgetBytes": budget,
        "maxExpandedTilePixels": 0,
        "maxSourceRoiPixels": 0,
        "maxEstimatedWorkingBytes": 0,
        "tileCount": tile_count,
        "estimatedDiskBytes": required_disk,
    }
    try:
        completed = 0
        for y in range(0, height, actual_tile):
            for x in range(0, width, actual_tile):
                x2, y2 = min(width, x + actual_tile), min(height, y + actual_tile)
                image_tile, mask_tile = _render_manual_tile(
                    project,
                    workspace_root,
                    canvas_bounds,
                    output_bounds,
                    (x, y, x2, y2),
                    halo,
                    background_mode,
                    budget,
                    stats,
                )
                image_map[y:y2, x:x2] = image_tile
                mask_map[y:y2, x:x2] = mask_tile
                completed += 1
                if progress_callback:
                    progress_callback(10 + int(65 * completed / stats["tileCount"]), f"Đang render tile {completed}/{stats['tileCount']}")
        image_map.flush()
        mask_map.flush()

        crop_info["renderMode"] = "tiled"
        crop_info["tiledRender"] = stats
        staged_output = os.path.join(stage_root, f"{folder_name}.{target_ext}")
        if progress_callback:
            progress_callback(78, "Đang ghi tiled BigTIFF...")
        write_tiled_tiff(image_map, staged_output, tile_size=actual_tile)

        mask_png_cap = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_STREAM_PNG_PIXELS", "67108864")))
        effective_mask_png_cap = min(mask_png_cap, budget // 4)
        if width * height <= effective_mask_png_cap:
            mask_name = f"{folder_name}_valid_mask.png"
            staged_mask = os.path.join(stage_root, mask_name)
            if not cv2.imwrite(staged_mask, mask_map, [cv2.IMWRITE_PNG_COMPRESSION, 4]):
                raise RuntimeError("Không thể ghi companion mask PNG")
            crop_info["companionMaskFormat"] = "png"
        else:
            mask_name = f"{folder_name}_valid_mask.tif"
            staged_mask = os.path.join(stage_root, mask_name)
            write_tiled_tiff(mask_map, staged_mask, tile_size=actual_tile, is_mask=True)
            crop_info["companionMaskFormat"] = "tif"
            crop_info["companionMaskReason"] = f"Effective PNG mask cap {effective_mask_png_cap} pixels"

        staged_meta = os.path.join(stage_root, f"{folder_name}_metadata.json")
        with open(staged_meta, 'w', encoding='utf-8') as stream:
            json.dump(crop_info, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        staged_dzi_dir = os.path.join(stage_root, f"{folder_name}_dzi")
        os.makedirs(staged_dzi_dir, exist_ok=True)
        staged_dzi = os.path.join(staged_dzi_dir, f"{folder_name}.dzi")
        if progress_callback:
            progress_callback(85, "Đang tạo DZI theo chunk...")
        generate_dzi_pyramid_bounded(image_map, staged_dzi, stage_root, tile_size=254, chunk_size=actual_tile)

        _close_memmap(image_map)
        _close_memmap(mask_map)
        del image_map
        del mask_map
        image_map = mask_map = None
        output_path = os.path.join(output_dir, f"{folder_name}.{target_ext}")
        mask_path = os.path.join(output_dir, mask_name)
        metadata_path = os.path.join(output_dir, f"{folder_name}_metadata.json")
        dzi_dir = os.path.join(output_dir, f"{folder_name}_dzi")
        _publish_staged_artifacts(stage_root, [
            (staged_output, output_path),
            (staged_mask, mask_path),
            (staged_meta, metadata_path),
            (staged_dzi_dir, dzi_dir),
        ])
        if progress_callback:
            progress_callback(100, "Xuất tiled BigTIFF hoàn tất!")
        return {
            "status": "success",
            "outputFile": output_path,
            "fileName": os.path.basename(output_path),
            "dziPath": os.path.join(dzi_dir, f"{folder_name}.dzi"),
            "trainingMask": os.path.basename(mask_path),
            "metadataFile": os.path.basename(metadata_path),
            "width": width,
            "height": height,
            "cropInfo": crop_info,
        }
    finally:
        if image_map is not None:
            _close_memmap(image_map)
            del image_map
        if mask_map is not None:
            _close_memmap(mask_map)
            del mask_map
        shutil.rmtree(stage_root, ignore_errors=True)


def export_manual_project(
    project: ProjectState,
    output_dir: str,
    workspace_root: str,
    output_name: Optional[str] = None,
    export_format: Optional[str] = None,
    background_mode: str = "transparent",
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """Xuất project thành file WSI (TIFF + DZI pyramid) kèm companion training mask"""
    os.makedirs(output_dir, exist_ok=True)
    folder_name = output_name or project.folderName or "manual_wsi"
    ext = (export_format or "tif").lower().lstrip(".")

    if ext in ("tif", "tiff"):
        return export_manual_project_tiled(
            project,
            output_dir,
            workspace_root,
            output_name=folder_name,
            background_mode=background_mode,
            progress_callback=progress_callback,
            target_ext=ext,
        )

    _, output_bounds, _ = _manual_output_geometry(project)
    output_pixels = (output_bounds[2] - output_bounds[0]) * (output_bounds[3] - output_bounds[1])
    png_cap = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_STREAM_PNG_PIXELS", "67108864")))
    memory_budget = get_max_memory_mb() * 1024 * 1024
    effective_cap = min(png_cap, memory_budget // 32)
    if output_pixels > effective_cap:
        raise ValueError(
            f".{ext} output {output_pixels} pixels không hỗ trợ streaming; giới hạn hiệu dụng {effective_cap} pixels. Hãy chọn TIFF/BigTIFF."
        )

    composite_img, training_mask, crop_info = render_manual_wsi_composite(
        project,
        workspace_root,
        background_mode=background_mode,
        progress_callback=progress_callback
    )

    if progress_callback:
        progress_callback(90, "Đang xuất định dạng và tạo DeepZoom Pyramid Tiles...")

    res = export_wsi_multiformat(
        composite_img,
        output_dir,
        folder_name=folder_name,
        target_ext=ext,
        tile_size=254,
        valid_mask=training_mask,
        metadata_dict=crop_info
    )

    mask_file_name = os.path.basename(res["mask_path"]) if res.get("mask_path") else None

    if progress_callback:
        progress_callback(100, "Xuất ảnh thủ công hoàn tất!")

    return {
        "status": "success",
        "outputFile": res["output_path"],
        "fileName": res["file_name"],
        "dziPath": res.get("dzi_path"),
        "trainingMask": mask_file_name,
        "metadataFile": os.path.basename(res["metadata_path"]) if res.get("metadata_path") else None,
        "width": composite_img.shape[1],
        "height": composite_img.shape[0],
        "cropInfo": crop_info
    }
