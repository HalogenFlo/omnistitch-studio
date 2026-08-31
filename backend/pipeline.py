# Feature: End-to-end pipeline orchestrator for automated gigapixel mosaic stitching
# Author: HalogenBr
# Purpose: Receives tile paths -> Extract features -> Match -> MST -> Blend -> Export
# Path: backend/pipeline.py

import os
import time
import cv2
import numpy as np

from backend.io_utils import read_image, save_tiff
from backend.feature_engine import FeatureEngine
from backend.matcher import FeatureMatcher
from backend.global_stitching import GlobalStitcher
from backend.blending import FastStreamingBlender
from backend.postprocessing import find_largest_inscribed_rectangle
from backend.wsi_exporter import export_wsi_multiformat


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
        return max(64, avail_mb)
    except Exception:
        return 2048


def _output_coordinate_metadata(bbox, crop_x=0, crop_y=0):
    world_origin_x = float(bbox[0] + crop_x)
    world_origin_y = float(bbox[1] + crop_y)
    return (
        [1.0, 0.0, world_origin_x, 0.0, 1.0, world_origin_y, 0.0, 0.0, 1.0],
        [1.0, 0.0, -world_origin_x, 0.0, 1.0, -world_origin_y, 0.0, 0.0, 1.0]
    )

def run_wsi_stitching_pipeline(
    image_paths,
    output_dir,
    feature_method='sift',
    motion_model='affine',
    background_mode='white',
    auto_crop=False,
    export_format=None,
    custom_output_name=None,
    progress_callback=None,
    project_layers=None
):
    """
    Automated gigapixel mosaic stitching pipeline:
    - image_paths: List of image tile paths (.tif, .png, .jpg, .bmp)
    - output_dir: Thư mục lưu kết quả (mặc định data/output)
    - feature_method: 'sift', 'akaze', 'orb'
    - motion_model: 'affine', 'rigid', 'homography'
    - background_mode: 'white', 'transparent'
    - auto_crop: True/False (Cắt hình chữ nhật nội tiếp lớn nhất)
    - export_format: 'tif', 'png', 'jpg', 'bmp' hoặc None
    - custom_output_name: Tên file xuất
    - progress_callback: hàm nhận (progress_percent, step_name, details_dict)
    - project_layers: Tọa độ ma trận layers từ project (nếu có, ưu tiên sử dụng để WSI trùng khớp 100% bản vẽ)
    """
    def report(percent, step_name, details=None):
        if progress_callback:
            progress_callback(percent, step_name, details or {})

    start_time = time.time()
    n_images = len(image_paths)
    if n_images == 0:
        raise ValueError("Không có ảnh nào được cung cấp.")

    # Xác định định dạng xuất tự động nếu không chỉ định
    if not export_format:
        export_format = os.path.splitext(image_paths[0])[1].lstrip('.').lower()
        if export_format == 'tiff':
            export_format = 'tif'

    # Xác định tên file xuất theo tên thư mục nguồn
    if not custom_output_name:
        parent_dir = os.path.dirname(os.path.abspath(image_paths[0]))
        base_folder = os.path.basename(parent_dir)
        custom_output_name = base_folder if base_folder and base_folder not in ['.', '', 'uploads'] else "stitched_wsi"

    report(5, "Reading image tiles...", {"total_images": n_images})

    # 1. Đọc toàn bộ ảnh
    images = {}
    source_images = {}
    for i, path in enumerate(image_paths):
        source_images[i] = read_image(path)
        images[i] = source_images[i][:, :, :3] if source_images[i].ndim == 3 and source_images[i].shape[2] == 4 else source_images[i]
        report(5 + int(20 * (i + 1) / n_images), f"Loaded tile {i+1}/{n_images}: {os.path.basename(path)}")

    # Kiểm tra xem có thể tái sử dụng tọa độ layers đã căn chỉnh chuẩn từ Studio không
    has_valid_project = False
    adjusted_transforms = {}
    global_transforms = {}
    matches_graph_data = []
    bbox = None
    canvas_w, canvas_h = 0, 0

    def _is_unaligned_linear_layout(layers):
        if not layers or len(layers) < 2:
            return False
        ys = []
        xs = []
        for l in layers:
            raw_m = l.get('sourceToWorld') if isinstance(l, dict) else getattr(l, 'sourceToWorld', None)
            if not raw_m or len(raw_m) != 9:
                return False
            xs.append(float(raw_m[2]))
            ys.append(float(raw_m[5]))
        # Nếu tất cả y xấp xỉ 0 và x tăng đều (bố cục trải phẳng mặc định lúc tải ảnh lên)
        return all(abs(y) < 1e-3 for y in ys) and xs == sorted(xs)

    if project_layers and len(project_layers) == n_images and not _is_unaligned_linear_layout(project_layers):
        try:
            all_corners = []
            layer_mats = []
            for i in range(n_images):
                pl = project_layers[i]
                raw_m = pl.get('sourceToWorld') if isinstance(pl, dict) else getattr(pl, 'sourceToWorld', None)
                if not raw_m or len(raw_m) != 9:
                    raise ValueError("Thiếu ma trận sourceToWorld")
                m = np.asarray(raw_m, dtype=np.float64).reshape(3, 3)
                layer_mats.append(m)
                h, w = source_images[i].shape[:2]
                corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64).T
                all_corners.append((m @ corners)[:2].T)
            
            all_corners = np.vstack(all_corners)
            min_x = int(np.floor(np.min(all_corners[:, 0])))
            min_y = int(np.floor(np.min(all_corners[:, 1])))
            max_x = int(np.ceil(np.max(all_corners[:, 0])))
            max_y = int(np.ceil(np.max(all_corners[:, 1])))

            canvas_w = max_x - min_x
            canvas_h = max_y - min_y
            bbox = (min_x, min_y, max_x, max_y)

            T_canvas = np.array([[1.0, 0.0, -min_x], [0.0, 1.0, -min_y], [0.0, 0.0, 1.0]], dtype=np.float64)
            for i in range(n_images):
                adjusted_transforms[i] = T_canvas @ layer_mats[i]

            global_transforms = {i: layer_mats[i] for i in range(n_images)}
            matches_graph_data = []
            has_valid_project = True
            report(60, "Synchronized coordinates from Studio...")
        except Exception as e_pl:
            has_valid_project = False

    if not has_valid_project:
        # 2. Trích xuất đặc trưng
        report(25, f"Extracting multi-scale features ({feature_method.upper()})...")
        feature_engine = FeatureEngine(method=feature_method, max_features=8000, enable_clahe=True)
        keypoints = {}
        descriptors = {}
        grays = {}
        for i, img in source_images.items():
            kp, desc, gray = feature_engine.detect_and_compute(img)
            keypoints[i] = kp
            descriptors[i] = desc
            grays[i] = gray

        # 3. Khớp đặc trưng từng cặp (Pairwise Matching)
        report(40, "Computing pairwise feature matches (RANSAC)...")
        matcher = FeatureMatcher(method=feature_method, ratio_threshold=0.80, min_inliers=8, motion_model=motion_model)
        
        matches_matrix = {}
        transforms_matrix = {}
        confidence_matrix = {}
        matches_graph_data = []

        for i in range(n_images):
            for j in range(i + 1, n_images):
                matches = matcher.match_pair(descriptors[i], descriptors[j])
                H_j_to_i = None
                conf = 0.0
                num_inliers = 0

                if len(matches) >= matcher.min_inliers:
                    H_j_to_i, inlier_mask, num_inliers, conf = matcher.estimate_transformation(keypoints[i], keypoints[j], matches)

                # Fallback Phase Correlation cho các cặp ảnh lân cận nếu SIFT không đủ inliers
                if H_j_to_i is None and abs(i - j) <= 2:
                    H_pc, resp = matcher.estimate_phase_correlation(grays[i], grays[j])
                    if H_pc is not None and resp > 0.2:
                        H_j_to_i = H_pc
                        conf = float(resp)
                        num_inliers = int(resp * 50)

                if H_j_to_i is not None:
                    transforms_matrix[(i, j)] = H_j_to_i
                    transforms_matrix[(j, i)] = np.linalg.inv(H_j_to_i)
                    confidence_matrix[(i, j)] = conf
                    confidence_matrix[(j, i)] = conf
                    matches_matrix[(i, j)] = matches
                    
                    matches_graph_data.append({
                        "source": i,
                        "target": j,
                        "inliers": num_inliers,
                        "confidence": float(conf)
                    })

        # 4. Tối ưu đồ thị ghép MST & Tính toán Canvas mở rộng
        report(60, "Optimizing global coordinate alignment...")
        global_stitcher = GlobalStitcher(images, keypoints, matches_matrix, transforms_matrix)
        global_transforms, tree_edges = global_stitcher.build_spanning_tree(confidence_matrix, root_idx=0)
        
        canvas_w, canvas_h, adjusted_transforms, bbox = global_stitcher.compute_canvas_bounding_box(global_transforms)

    max_memory_mb = get_max_memory_mb()
    estimated_canvas_bytes = canvas_w * canvas_h * 20
    if estimated_canvas_bytes > max_memory_mb * 1024 * 1024:
        raise MemoryError(
            f"Canvas {canvas_w}x{canvas_h} cần khoảng {estimated_canvas_bytes / (1024 * 1024):.0f} MB, exceed budget {max_memory_mb} MB"
        )

    # 5. Tích lũy và hòa trộn Voronoi Adaptive Seam Blending
    report(75, f"Initializing Gigapixel Canvas ({canvas_w}x{canvas_h} px)...")
    blender = FastStreamingBlender((canvas_h, canvas_w), background_mode=background_mode, focus_stacking=True)

    for i, img in source_images.items():
        H = adjusted_transforms[i]
        blender.accumulate_tile(img, H, motion_model=motion_model)
        report(75 + int(15 * (i + 1) / n_images), f"Blending tile {i+1}/{n_images} into canvas...")

    # 6. Chuẩn hóa kết quả ảnh hoàn chỉnh
    report(90, "Extracting sharp panorama composite...")
    blended_image, global_mask = blender.finalize()

    # 7. Tự động Crop hình chữ nhật nếu bật
    crop_x = crop_y = 0
    if auto_crop:
        report(92, "Auto-cropping largest inscribed bounding rectangle...")
        crop_x, crop_y, crop_w, crop_h = find_largest_inscribed_rectangle(global_mask)
        if crop_w > 0 and crop_h > 0:
            blended_image = blended_image[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
            global_mask = global_mask[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]

    # 8. Xuất file kết quả đúng định dạng vào output_dir (data/output)
    report(95, f"Exporting gigapixel mosaic format .{export_format} and generating DeepZoom pyramids (DZI)...")
    os.makedirs(output_dir, exist_ok=True)
    out_filename = f"{custom_output_name}.{export_format}"
    export_result = export_wsi_multiformat(
        blended_image,
        output_dir,
        folder_name=custom_output_name,
        target_ext=export_format
    )
    out_filepath = export_result["output_path"]
    dzi_filepath = export_result["dzi_path"]

    elapsed_time = round(time.time() - start_time, 2)
    final_h, final_w = blended_image.shape[:2]
    output_pixel_to_world, world_to_output_pixel = _output_coordinate_metadata(bbox, crop_x, crop_y)

    serializable_transforms = {}
    # Persist source-to-world transforms, not the internal canvas-shifted matrices.
    # outputPixelToWorld carries the canvas shift and optional auto-crop offset.
    for idx, H in global_transforms.items():
        serializable_transforms[idx] = H.flatten().tolist()

    report(100, "Mosaic stitching completed successfully!", {
        "output_file": out_filepath,
        "dzi_file": dzi_filepath,
        "format": export_format,
        "file_name": out_filename,
        "width": final_w,
        "height": final_h,
        "total_images": n_images,
        "matches_graph": matches_graph_data,
        "layer_transforms": serializable_transforms,
        "elapsed_time_sec": elapsed_time,
        "outputPixelToWorld": output_pixel_to_world,
        "worldToOutputPixel": world_to_output_pixel
    })

    return {
        "output_filepath": out_filepath,
        "dzi_filepath": dzi_filepath,
        "file_name": out_filename,
        "format": export_format,
        "dimensions": (final_w, final_h),
        "elapsed_time": elapsed_time,
        "layer_transforms": serializable_transforms,
        "graph_data": matches_graph_data,
        "outputPixelToWorld": output_pixel_to_world,
        "worldToOutputPixel": world_to_output_pixel
    }
