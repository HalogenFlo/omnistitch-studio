# Chức năng: Khớp đặc trưng hai ảnh (Pairwise Matching) và ước lượng biến đổi hình học
# Lí do tạo: Tìm ma trận tương thích giữa 2 ảnh tile với bộ lọc nhiễu Lowe's Ratio Test + USAC_MAGSAC/RANSAC + Phase Correlation Fallback cho mô chưa nhuộm
# Đường dẫn: tool/image_alignment/backend/matcher.py

import cv2
import numpy as np

class FeatureMatcher:
    def __init__(self, method='sift', ratio_threshold=0.80, min_inliers=8, motion_model='affine'):
        """
        - method: 'sift', 'akaze', 'orb'
        - ratio_threshold: Lowe's ratio test threshold (mặc định 0.80 cho mô học)
        - min_inliers: Số lượng inliers tối thiểu để coi là 2 ảnh có sự chồng lặp hợp lệ (8 inliers)
        - motion_model: 'rigid' (Euclidean), 'affine' (Affine 2x3), 'homography' (Perspective 3x3)
        """
        self.method = method.lower()
        self.ratio_threshold = ratio_threshold
        self.min_inliers = min_inliers
        self.motion_model = motion_model.lower()
        self.matcher = self._create_matcher()

    def _create_matcher(self):
        if self.method in ['sift']:
            # Dùng FLANN Matcher với KDTree cho SIFT (float descriptors)
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            return cv2.FlannBasedMatcher(index_params, search_params)
        else:
            # Dùng BFMatcher với Hamming distance cho binary descriptors (ORB, AKAZE)
            return cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def match_pair(self, desc1, desc2):
        """
        Khớp descriptors giữa ảnh 1 và ảnh 2 bằng k-NN (k=2) và lọc Lowe's ratio test.
        """
        if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
            return []

        if self.method in ['sift'] and desc1.dtype != np.float32:
            desc1 = desc1.astype(np.float32)
            desc2 = desc2.astype(np.float32)

        try:
            raw_matches = self.matcher.knnMatch(desc1, desc2, k=2)
        except Exception:
            return []

        good_matches = []
        for m_pair in raw_matches:
            if len(m_pair) == 2:
                m, n = m_pair
                if m.distance < self.ratio_threshold * n.distance:
                    good_matches.append(m)

        return good_matches

    def estimate_transformation(self, kp1, kp2, matches):
        """
        Ước lượng ma trận biến đổi từ ảnh 2 về hệ tọa độ ảnh 1 (hoặc ngược lại) bằng USAC_MAGSAC / RANSAC.
        Trả về: (H_3x3, inlier_mask, num_inliers, confidence_score)
        """
        if len(matches) < self.min_inliers:
            return None, None, 0, 0.0

        pts1 = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 2)
        pts2 = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 2)

        # Chọn thuật toán RANSAC
        ransac_method = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)

        H_3x3 = np.eye(3, dtype=np.float64)
        inlier_mask = None

        if self.motion_model == 'rigid':
            # Biến đổi bảo toàn góc và khoảng cách (Euclidean / Rigid)
            M, inliers = cv2.estimateAffinePartial2D(
                pts2, pts1,
                method=ransac_method,
                ransacReprojThreshold=3.5,
                maxIters=2500,
                confidence=0.995
            )
            if M is not None:
                H_3x3[:2, :] = M
                inlier_mask = inliers.ravel() if inliers is not None else None

        elif self.motion_model == 'affine':
            # Biến đổi Affine 2x3 (Rotation + Translation + Scale + Shear)
            M, inliers = cv2.estimateAffine2D(
                pts2, pts1,
                method=ransac_method,
                ransacReprojThreshold=3.5,
                maxIters=2500,
                confidence=0.995
            )
            if M is not None:
                H_3x3[:2, :] = M
                inlier_mask = inliers.ravel() if inliers is not None else None

        else: # 'homography'
            # Biến đổi phối cảnh 3x3
            H, inliers = cv2.findHomography(
                pts2, pts1,
                method=ransac_method,
                ransacReprojThreshold=3.5,
                maxIters=2500,
                confidence=0.995
            )
            if H is not None:
                H_3x3 = H
                inlier_mask = inliers.ravel() if inliers is not None else None

        if inlier_mask is None:
            return None, None, 0, 0.0

        num_inliers = int(np.sum(inlier_mask))
        if num_inliers < self.min_inliers:
            return None, None, 0, 0.0

        # Tính điểm tự tin (Confidence score)
        confidence_score = float(num_inliers) / (len(matches) + 1e-5) * np.log1p(num_inliers)

        return H_3x3, inlier_mask, num_inliers, confidence_score

    def estimate_phase_correlation(self, gray1, gray2):
        """
        Phương pháp tương quan pha Fourier (Phase Correlation) để tìm độ dời tịnh tiến (dx, dy)
        khi vùng mô quá thưa/trong suốt không đủ keypoints SIFT.
        """
        try:
            g1_f = gray1.astype(np.float32)
            g2_f = gray2.astype(np.float32)
            # Áp dụng cửa sổ Hanning để giảm biên Fourier
            h, w = g1_f.shape[:2]
            win = cv2.createHanningWindow((w, h), cv2.CV_32F)
            (shift_x, shift_y), response = cv2.phaseCorrelate(g1_f, g2_f, window=win)
            
            if response > 0.15:
                H = np.array([
                    [1.0, 0.0, shift_x],
                    [0.0, 1.0, shift_y],
                    [0.0, 0.0, 1.0]
                ], dtype=np.float64)
                return H, response
        except Exception:
            pass
        return None, 0.0
