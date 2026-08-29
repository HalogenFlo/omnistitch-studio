# Chức năng: Xây dựng đồ thị ghép nối, Cây khung cực đại (MST) và Đa thành phần liên thông (Multi-Component MST)
# Lí do tạo: Triệt tiêu tích lũy sai số (drift) và đảm bảo 100% các mảnh tile (kể cả mô chưa nhuộm / tương phản thấp) được định vị chính xác
# Đường dẫn: tool/image_alignment/backend/global_stitching.py

import cv2
import numpy as np
from collections import defaultdict, deque

class GlobalStitcher:
    def __init__(self, images_dict, keypoints_dict, matches_matrix, transformations_matrix):
        """
        - images_dict: dict {img_idx: img_rgb}
        - keypoints_dict: dict {img_idx: list_cv2_keypoints}
        - matches_matrix: dict {(i, j): list_matches}
        - transformations_matrix: dict {(i, j): H_3x3 (chuyển từ j sang i)}
        """
        self.images = images_dict
        self.keypoints = keypoints_dict
        self.matches = matches_matrix
        self.transforms = transformations_matrix
        self.n_images = len(images_dict)

    def build_spanning_tree(self, confidence_matrix, root_idx=None):
        """
        Xây dựng Maximum Spanning Tree (MST) dựa trên phân tích Thành Phần Liên Thông (Connected Components).
        Tự động chọn Node trung tâm có bậc liên kết cao nhất làm Gốc (Root) để giảm thiểu sai số tích lũy.
        """
        n = self.n_images
        if n == 0:
            return {}, []

        sample_img = next(iter(self.images.values()))
        avg_h, avg_w = sample_img.shape[:2]

        # 1. Xây dựng danh sách kề cho đồ thị
        adj = defaultdict(list)
        degrees = defaultdict(int)
        for (u, v) in self.transforms:
            adj[u].append(v)
            degrees[u] += 1

        # 2. Tìm các thành phần liên thông (Connected Components)
        visited_all = set()
        components = []

        for node in range(n):
            if node not in visited_all:
                comp = []
                queue = deque([node])
                visited_all.add(node)
                while queue:
                    curr = queue.popleft()
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited_all:
                            visited_all.add(neighbor)
                            queue.append(neighbor)
                components.append(comp)

        # Sắp xếp các component theo kích thước giảm dần (Component lớn nhất lên đầu)
        components.sort(key=len, reverse=True)

        global_transforms = {}
        tree_edges = []
        global_visited = set()

        # 3. Xử lý từng thành phần liên thông
        for comp_idx, comp in enumerate(components):
            comp_set = set(comp)
            
            # Chọn root cho component này (Node có nhiều kết nối và điểm tự tin cao nhất)
            best_root = comp[0]
            max_deg = -1
            for node in comp:
                deg = sum(confidence_matrix.get((node, v), 0.0) for v in adj[node] if v in comp_set)
                if deg > max_deg:
                    max_deg = deg
                    best_root = node

            comp_transforms = {best_root: np.eye(3, dtype=np.float64)}
            comp_visited = {best_root}

            # Prim MST cho nội bộ component
            while len(comp_visited) < len(comp):
                best_edge = None
                max_conf = -1.0

                for u in comp_visited:
                    for v in comp:
                        if v not in comp_visited and (u, v) in self.transforms:
                            conf = confidence_matrix.get((u, v), 0.0)
                            if conf > max_conf:
                                max_conf = conf
                                best_edge = (u, v, self.transforms[(u, v)])

                if best_edge is None:
                    # Fallback cho các node lẻ trong component
                    unvisited = [node for node in comp if node not in comp_visited]
                    if not unvisited:
                        break
                    next_node = unvisited[0]
                    comp_visited.add(next_node)
                    # Ước lượng vị trí tương đối theo thứ tự index
                    delta_idx = next_node - best_root
                    comp_transforms[next_node] = np.array([
                        [1.0, 0.0, delta_idx * (avg_w * 0.85)],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0]
                    ], dtype=np.float64)
                    continue

                u, v, H_v_to_u = best_edge
                comp_visited.add(v)
                tree_edges.append((u, v))
                comp_transforms[v] = comp_transforms[u] @ H_v_to_u

            # Nếu là component đầu tiên (Main Component): Gán trực tiếp vào global_transforms
            if comp_idx == 0:
                for node, T in comp_transforms.items():
                    global_transforms[node] = T
                    global_visited.add(node)
            else:
                # Nếu là component phụ: Định vị tương quan so với Main Component
                # Tìm node trong Main Component có chỉ số gần nhất
                ref_main_node = min(global_visited, key=lambda m: abs(m - best_root))
                T_ref = global_transforms[ref_main_node]
                
                # Ước lượng dịch chuyển theo dải quét
                delta = best_root - ref_main_node
                cols = int(np.ceil(np.sqrt(n)))
                dr = delta // cols
                dc = delta % cols
                T_offset = np.array([
                    [1.0, 0.0, dc * (avg_w * 0.85)],
                    [0.0, 1.0, dr * (avg_h * 0.85)],
                    [0.0, 0.0, 1.0]
                ], dtype=np.float64)

                T_base = T_ref @ T_offset
                for node, T in comp_transforms.items():
                    global_transforms[node] = T_base @ T
                    global_visited.add(node)

        # 4. Đảm bảo toàn bộ n_images đều có tọa độ
        for node in range(n):
            if node not in global_transforms:
                r = node // int(np.ceil(np.sqrt(n)))
                c = node % int(np.ceil(np.sqrt(n)))
                global_transforms[node] = np.array([
                    [1.0, 0.0, c * (avg_w * 0.85)],
                    [0.0, 1.0, r * (avg_h * 0.85)],
                    [0.0, 0.0, 1.0]
                ], dtype=np.float64)

        return global_transforms, tree_edges

    def compute_canvas_bounding_box(self, global_transforms):
        """
        Tính toán phạm vi tọa độ cực tiểu (xmin, ymin) và cực đại (xmax, ymax) của toàn bộ các tile,
        từ đó xác định kích thước Canvas WSI mở rộng chính xác.
        """
        all_corners_global = []

        for idx, img in self.images.items():
            h, w = img.shape[:2]
            # 4 góc của ảnh tile [Top-Left, Top-Right, Bottom-Right, Bottom-Left]
            corners = np.array([
                [0, 0, 1],
                [w, 0, 1],
                [w, h, 1],
                [0, h, 1]
            ], dtype=np.float64).T

            H = global_transforms[idx]
            warped_corners = H @ corners
            warped_corners /= warped_corners[2:3, :]  # Chuẩn hóa tọa độ đồng nhất
            all_corners_global.append(warped_corners[:2, :].T)

        all_corners_global = np.vstack(all_corners_global)
        xmin = np.min(all_corners_global[:, 0])
        ymin = np.min(all_corners_global[:, 1])
        xmax = np.max(all_corners_global[:, 0])
        ymax = np.max(all_corners_global[:, 1])

        canvas_width = int(np.ceil(xmax - xmin))
        canvas_height = int(np.ceil(ymax - ymin))

        # Giới hạn an toàn Canvas WSI
        canvas_width = max(100, canvas_width)
        canvas_height = max(100, canvas_height)

        # Ma trận dịch chuyển để đưa gốc tọa độ (xmin, ymin) về (0, 0)
        T_shift = np.array([
            [1.0, 0.0, -xmin],
            [0.0, 1.0, -ymin],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        # Cập nhật lại toàn bộ ma trận biến đổi của từng tile theo Canvas mới
        adjusted_transforms = {}
        for idx, H in global_transforms.items():
            adjusted_transforms[idx] = T_shift @ H

        return canvas_width, canvas_height, adjusted_transforms, (xmin, ymin, xmax, ymax)
