# Chức năng: Trích xuất & Mô tả đặc trưng (SIFT / AKAZE / ORB) siêu nhạy cho mô học (đặc biệt là mô chưa nhuộm / tương phản thấp)
# Lí do tạo: Tìm kiếm keypoints và descriptors chính xác giữa các ảnh kính hiển vi với độ ổn định cao
# Đường dẫn: tool/image_alignment/backend/feature_engine.py

import cv2
import numpy as np

class FeatureEngine:
    def __init__(self, method='sift', max_features=8000, enable_clahe=True):
        """
        Khởi tạo bộ trích xuất đặc trưng tối ưu mô học.
        - method: 'sift', 'akaze', 'orb'
        - max_features: Số lượng đặc trưng tối đa (mặc định 8000 cho mô học)
        - enable_clahe: Bật tiền xử lý CLAHE tăng cường tương phản vi thể
        """
        self.method = method.lower()
        self.max_features = max_features
        self.enable_clahe = enable_clahe
        self.detector = self._create_detector()
        
        # CLAHE thích nghi đa cấp độ (Contrast Limited Adaptive Histogram Equalization)
        if self.enable_clahe:
            self.clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(12, 12))
        else:
            self.clahe = None

    def _create_detector(self):
        if self.method == 'sift':
            # contrastThreshold=0.015: Bắt được cả các vân mô chưa nhuộm trong suốt/mờ nhạt
            return cv2.SIFT_create(
                nfeatures=self.max_features,
                contrastThreshold=0.015,
                edgeThreshold=12,
                sigma=1.4
            )
        elif self.method == 'akaze':
            return cv2.AKAZE_create(
                descriptor_type=cv2.AKAZE_DESCRIPTOR_MLDB,
                threshold=0.0008,
                nOctaves=4,
                nOctaveLayers=4
            )
        elif self.method == 'orb':
            return cv2.ORB_create(
                nfeatures=self.max_features,
                scaleFactor=1.2,
                nlevels=8,
                edgeThreshold=31,
                patchSize=31,
                fastThreshold=15
            )
        else:
            raise ValueError(f"Thuật toán đặc trưng không hợp lệ: {self.method}. Hãy chọn 'sift', 'akaze', hoặc 'orb'.")

    def preprocess_for_detection(self, img_rgb):
        """
        Chuyển ảnh RGB sang Grayscale và áp dụng CLAHE tăng cường vân mô học.
        """
        if len(img_rgb.shape) == 3:
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_rgb.copy()

        if self.clahe is not None:
            gray = self.clahe.apply(gray)
        return gray

    def detect_and_compute(self, img_rgb):
        """
        Trích xuất keypoints và tính toán descriptors cho ảnh RGB.
        Trả về: (keypoints, descriptors, preprocessed_gray)
        """
        gray = self.preprocess_for_detection(img_rgb)
        keypoints, descriptors = self.detector.detectAndCompute(gray, None)
        return keypoints, descriptors, gray
