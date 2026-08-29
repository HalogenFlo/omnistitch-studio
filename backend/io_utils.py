# Chức năng: Xử lý Đọc & Ghi ảnh định dạng TIFF / TIF (.tif, .tiff) chuyên dụng cho kính hiển vi mô học
# Lí do tạo: Đảm bảo đọc nguyên vẹn dải màu, độ phân giải gốc 100% không suy hao (zero-loss), hỗ trợ 8-bit/16-bit, nén LZW và tạo thumbnail xem web
# Đường dẫn: tool/image_alignment/backend/io_utils.py

import os
import cv2
import numpy as np
import tifffile
from PIL import Image

def read_image(file_path):
    """
    Đọc ảnh từ file_path, hỗ trợ toàn diện .tif, .tiff, .png, .jpg, .bmp.
    Trả về uint8 RGB hoặc RGBA theo đúng thứ tự kênh. Alpha nguồn không bị bỏ.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File không tồn tại: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    img = None
    if ext in ['.tif', '.tiff']:
        try:
            # Đọc bằng tifffile để hỗ trợ đầy đủ các chuẩn TIFF của kính hiển vi
            raw = tifffile.imread(file_path)
            
            # Xử lý các dạng shape khác nhau
            if raw.ndim == 2:  # Grayscale
                # Nếu là 16-bit, chuẩn hóa về 8-bit
                if raw.dtype == np.uint16:
                    raw = (raw / 256).astype(np.uint8)
                elif raw.dtype != np.uint8:
                    raw = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                img = cv2.cvtColor(raw, cv2.COLOR_GRAY2RGB)
            elif raw.ndim == 3:
                # Kiểm tra kênh màu (H, W, C) hoặc (C, H, W)
                if raw.shape[0] in [1, 3, 4] and raw.shape[2] not in [1, 3, 4]:
                    raw = np.transpose(raw, (1, 2, 0))
                
                if raw.shape[2] == 1:
                    raw = cv2.cvtColor(raw[:, :, 0], cv2.COLOR_GRAY2RGB)
                
                if raw.dtype == np.uint16:
                    raw = (raw / 256).astype(np.uint8)
                elif raw.dtype != np.uint8:
                    raw = cv2.normalize(raw, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                img = raw
            elif raw.ndim == 4: # Trường hợp multi-page hoặc time/z-stack, lấy frame đầu tiên
                frame = raw[0]
                if frame.ndim == 2:
                    if frame.dtype == np.uint16:
                        frame = (frame / 256).astype(np.uint8)
                    elif frame.dtype != np.uint8:
                        frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    img = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                elif frame.ndim == 3:
                    if frame.shape[0] in [1, 3, 4] and frame.shape[2] not in [1, 3, 4]:
                        frame = np.transpose(frame, (1, 2, 0))
                    if frame.dtype == np.uint16:
                        frame = (frame / 256).astype(np.uint8)
                    elif frame.dtype != np.uint8:
                        frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    img = frame[:, :, :4]
        except Exception as e:
            # Fallback sang OpenCV
            raw = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
            if raw is not None:
                img = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA) if raw.ndim == 3 and raw.shape[2] == 4 else cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
    else:
        # Với định dạng thông thường dùng OpenCV
        raw = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
        if raw is not None:
            if raw.ndim == 2:
                img = cv2.cvtColor(raw, cv2.COLOR_GRAY2RGB)
            elif raw.shape[2] == 4:
                img = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
            else:
                img = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
        else:
            # Fallback PIL
            with Image.open(file_path) as pil_img:
                img = np.array(pil_img.convert('RGBA' if 'A' in pil_img.getbands() else 'RGB'))
                
    if img is None:
        raise ValueError(f"Không thể đọc file ảnh: {file_path}")
        
    return img

def save_tiff(file_path, image_data, compression=None):
    """
    Lưu ảnh ra định dạng .tif / .tiff chất lượng cao không suy hao.
    image_data: numpy array uint8 RGB (H, W, 3) hoặc RGBA (H, W, 4).
    """
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    is_rgba = (image_data.ndim == 3 and image_data.shape[2] == 4)
    photometric = 'rgb'
    
    # Tự động dùng BigTIFF nếu kích thước mảng > 2GB
    use_bigtiff = (image_data.nbytes > 2 * 1024 * 1024 * 1024)
    
    try:
        if compression:
            tifffile.imwrite(
                file_path,
                image_data,
                photometric=photometric,
                compression=compression,
                bigtiff=use_bigtiff,
                extrasamples=['unassalpha'] if is_rgba else None
            )
        else:
            tifffile.imwrite(
                file_path,
                image_data,
                photometric=photometric,
                bigtiff=use_bigtiff,
                extrasamples=['unassalpha'] if is_rgba else None
            )
    except Exception:
        # Fallback lưu uncompressed hoặc dùng Pillow
        try:
            tifffile.imwrite(file_path, image_data, photometric=photometric, bigtiff=use_bigtiff,
                             extrasamples=['unassalpha'] if is_rgba else None)
        except Exception:
            pil_img = Image.fromarray(image_data)
            pil_img.save(file_path, format='TIFF')
            
    return file_path

def create_thumbnail(image_data, max_size=(512, 512)):
    """
    Tạo thumbnail thu nhỏ từ ảnh gốc để preview nhanh trên giao diện web.
    """
    h, w = image_data.shape[:2]
    scale = min(max_size[0] / w, max_size[1] / h, 1.0)
    if scale >= 1.0:
        return image_data
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image_data, (new_w, new_h), interpolation=cv2.INTER_AREA)

def get_image_metadata(file_path):
    """
    Đọc nhanh kích thước width, height, channels, dtype từ file mà không cần giải mã toàn bộ pixel.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File không tồn tại: {file_path}")
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.tif', '.tiff']:
        try:
            with tifffile.TiffFile(file_path) as tif:
                page = tif.pages[0]
                shape = page.shape
                # shape có thể là (H, W), (H, W, C), hoặc (C, H, W)
                if len(shape) == 2:
                    h, w = shape
                    c = 1
                elif len(shape) == 3:
                    if shape[0] in [1, 3, 4] and shape[2] not in [1, 3, 4]:
                        c, h, w = shape
                    else:
                        h, w, c = shape
                else:
                    h, w = shape[1], shape[2]
                    c = 3
                return {"width": int(w), "height": int(h), "channels": int(c), "dtype": str(page.dtype)}
        except Exception:
            pass
    try:
        with Image.open(file_path) as img:
            w, h = img.size
            return {"width": int(w), "height": int(h), "channels": len(img.getbands()), "dtype": "uint8"}
    except Exception:
        # Fallback OpenCV
        raw = cv2.imread(file_path)
        if raw is not None:
            h, w = raw.shape[:2]
            c = raw.shape[2] if raw.ndim == 3 else 1
            return {"width": int(w), "height": int(h), "channels": int(c), "dtype": str(raw.dtype)}
    raise ValueError(f"Không thể đọc metadata ảnh: {file_path}")

def resolve_file_path(file_path: str, workspace_root: str = None) -> str:
    if workspace_root:
        root = os.path.realpath(workspace_root)
        resolved = os.path.realpath(file_path if os.path.isabs(file_path) else os.path.join(root, file_path))
        if os.path.commonpath([root, resolved]) != root:
            raise ValueError("Source path nằm ngoài workspace")
        return resolved
    if os.path.isabs(file_path):
        return os.path.realpath(file_path)
    return os.path.abspath(file_path)

def read_image_universal(file_path: str):
    """
    Đọc ảnh tổng quát, trả về (img_rgb, alpha, is_16bit).
    Đây là adapter cho mã cũ; màu luôn là RGB và alpha là uint8 nếu có.
    """
    if not os.path.exists(file_path):
        return None, None, False
    try:
        decoded = read_image(file_path)
        if decoded is None:
            return None, None, False
        alpha = decoded[:, :, 3].copy() if decoded.ndim == 3 and decoded.shape[2] == 4 else None
        img_rgb = decoded[:, :, :3] if alpha is not None else decoded
        return img_rgb, alpha, False
    except Exception:
        return None, None, False


def read_image_region(file_path: str, box):
    """Read a source rectangle, rejecting TIFF decodes that cannot fit the configured guard."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File không tồn tại: {file_path}")
    x1, y1, x2, y2 = [int(value) for value in box]
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Source ROI không hợp lệ")
    is_tiff = os.path.splitext(file_path)[1].lower() in ('.tif', '.tiff')
    if is_tiff:
        try:
            with tifffile.TiffFile(file_path) as tif:
                page = tif.pages[0]
                if page.is_memmappable:
                    width, height = int(page.imagewidth), int(page.imagelength)
                    x1, y1 = max(0, min(x1, width)), max(0, min(y1, height))
                    x2, y2 = max(x1, min(x2, width)), max(y1, min(y2, height))
                    if x2 <= x1 or y2 <= y1:
                        return np.zeros((0, 0, 3), dtype=np.uint8)
                    mapped = tifffile.memmap(file_path, page=0)
                    region = np.asarray(mapped[y1:y2, x1:x2])
                    if region.dtype == np.uint16:
                        region = (region / 256).astype(np.uint8)
                    elif region.dtype != np.uint8:
                        region = cv2.normalize(region, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    if region.ndim == 2:
                        region = cv2.cvtColor(region, cv2.COLOR_GRAY2RGB)
                    return np.asarray(region[:, :, :4], dtype=np.uint8).copy()
        except (ValueError, OSError, tifffile.TiffFileError):
            pass
    with Image.open(file_path) as image:
        width, height = image.size
        if is_tiff:
            decoder_cap = max(1, int(os.environ.get("IMAGE_ALIGNMENT_MAX_TIFF_DECODE_PIXELS", "33554432")))
            if width * height > decoder_cap:
                raise MemoryError(
                    f"TIFF {width}x{height} vượt decoder guard {decoder_cap} pixels; "
                    "cài pyvips/OpenSlide để hỗ trợ region decode cho WSI lớn"
                )
        x1 = max(0, min(x1, width))
        y1 = max(0, min(y1, height))
        x2 = max(x1, min(x2, width))
        y2 = max(y1, min(y2, height))
        if x2 <= x1 or y2 <= y1:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        cropped = image.crop((x1, y1, x2, y2))
        raw = np.asarray(cropped)
        if raw.dtype == np.uint16:
            raw = (raw / 256).astype(np.uint8)
            if raw.ndim == 2:
                return cv2.cvtColor(raw, cv2.COLOR_GRAY2RGB)
        has_alpha = 'A' in image.getbands() or 'transparency' in image.info
        region = cropped.convert('RGBA' if has_alpha else 'RGB')
        return np.asarray(region, dtype=np.uint8).copy()

def save_image_universal(image_data: np.ndarray, file_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.tif', '.tiff']:
        save_tiff(file_path, image_data)
    else:
        if image_data.ndim == 3 and image_data.shape[2] == 4:
            encoded = cv2.cvtColor(image_data, cv2.COLOR_RGBA2BGRA)
        elif image_data.ndim == 3 and image_data.shape[2] == 3:
            encoded = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)
        else:
            encoded = image_data
        cv2.imwrite(file_path, encoded)
    return file_path
