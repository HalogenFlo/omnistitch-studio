# Feature: Calculates largest inscribed rectangle for automatic seam-free boundary cropping
# Purpose: Removes irregular boundary artifacts when Auto-Crop is enabled
# Path: tool/image_alignment/backend/postprocessing.py

import cv2
import numpy as np

def find_largest_inscribed_rectangle(mask_binary):
    """
    Finds bounding rectangle (x, y, w, h) with maximum area inside mask > 0.
    mask_binary: numpy array uint8 (0 và 255)
    """
    h, w = mask_binary.shape[:2]
    # Thu nhỏ mask để tính toán nhanh nếu kích thước quá lớn
    scale = 1.0
    max_dim = 1000
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        scaled_mask = cv2.resize(mask_binary, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_NEAREST)
    else:
        scaled_mask = mask_binary

    sh, sw = scaled_mask.shape
    # Dynamic programming: histogram heights
    heights = np.zeros(sw, dtype=np.int32)
    max_area = 0
    best_rect_scaled = (0, 0, sw, sh)

    for r in range(sh):
        row = scaled_mask[r] > 0
        heights = np.where(row, heights + 1, 0)

        # Tìm diện tích lớn nhất trong histogram bằng Stack
        stack = []
        for i, height in enumerate(heights):
            start = i
            while stack and stack[-1][1] > height:
                idx, h_val = stack.pop()
                area = h_val * (i - idx)
                if area > max_area:
                    max_area = area
                    best_rect_scaled = (idx, r - h_val + 1, i - idx, h_val)
                start = idx
            stack.append((start, height))

        while stack:
            idx, h_val = stack.pop()
            area = h_val * (sw - idx)
            if area > max_area:
                max_area = area
                best_rect_scaled = (idx, r - h_val + 1, sw - idx, h_val)

    # Scale ngược lại về kích thước gốc
    rx, ry, rw, rh = best_rect_scaled
    x = int(np.floor(rx / scale))
    y = int(np.floor(ry / scale))
    w_orig = int(np.ceil(rw / scale))
    h_orig = int(np.ceil(rh / scale))

    # Giới hạn an toàn
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    w_orig = min(w_orig, w - x)
    h_orig = min(h_orig, h - y)

    return (x, y, w_orig, h_orig)

def crop_inscribed_rectangle(image_data, mask_binary):
    """
    Cắt ảnh theo hình chữ nhật nội tiếp lớn nhất.
    """
    x, y, w, h = find_largest_inscribed_rectangle(mask_binary)
    if w <= 0 or h <= 0:
        return image_data
    return image_data[y:y+h, x:x+w]
