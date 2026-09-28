# Kiến trúc Hệ thống 8 Biến thể Hậu Xử lý & Workspace Độc lập

## 1. Sơ đồ Tổng quan Luồng Dữ liệu (System Architecture Diagram)

```mermaid
flowchart TD
    subgraph GĐ1 [Giai đoạn 1: Căn chỉnh & Khóa Nét trên Ảnh Gốc]
        SRC[Ảnh Nguồn Gốc] --> SIFT[SIFT Trích xuất & Căn chỉnh Transform 1 lần]
        SRC --> SHARP[Tính Bản đồ Độ nét Cục bộ trên Ảnh Gốc]
        SHARP --> BEST[Tạo Ma trận best_tile_idx & Làm sạch Đốm Nhỏ]
        BEST --> LOCK[Khóa Lựa chọn Nét Bất biến]
        SIFT --> STITCH[Ghép Panorama Gốc]
        LOCK --> STITCH
    end

    subgraph GĐ2 [Giai đoạn 2: Tính Trường Sáng & Sinh Tuần tự 8 Biến thể]
        STITCH --> PANO_GOC[01_goc: Panorama Gốc]
        PANO_GOC --> GAUSS_CALC[Tính Gaussian Flat-Field 1 lần không mờ mô]
        PANO_GOC --> COLOR_CALC[Tính Color/Exposure Balance Gains]

        %% Nhóm Gốc
        PANO_GOC --> V01[01_goc.tif + DZI]
        COLOR_CALC --> V02[02_goc_can_sang.tif + DZI]
        PANO_GOC --> V03[03_goc_sac_net.tif + DZI]
        COLOR_CALC --> V04[04_goc_can_sang_net.tif + DZI]

        %% Nhóm Gaussian
        GAUSS_CALC --> V05[05_gaussian.tif + DZI]
        GAUSS_CALC --> V06[06_gaussian_can_sang.tif + DZI]
        GAUSS_CALC --> V07[07_gaussian_sac_net.tif + DZI]
        GAUSS_CALC --> V08[08_gaussian_full.tif + DZI]
    end

    subgraph GĐ3 [Giai đoạn 3: Hệ thống 8 Workspace Độc lập]
        V01 -.-> WS01[Workspace: original]
        V02 -.-> WS02[Workspace: original_balanced]
        V03 -.-> WS03[Workspace: original_clarity]
        V04 -.-> WS04[Workspace: original_full]
        V05 -.-> WS05[Workspace: gaussian]
        V06 -.-> WS06[Workspace: gaussian_balanced]
        V07 -.-> WS07[Workspace: gaussian_clarity]
        V08 -.-> WS08[Workspace: gaussian_full]

        subgraph Thành phần Mỗi Workspace
            direction TB
            FR[Focus Regions]
            MR[Alpha / Eraser Mask]
            CR[Crop Viewport]
            HJ[History Undo / Redo Journal]
        end
    end

    subgraph GĐ4 [Giai đoạn 4: Web UI 2 Nhóm Tab & Xuất Thủ công]
        TAB_ORIG[NHÓM GỐC: Gốc | Cân màu | Nét | Full]
        TAB_GAUSS[NHÓM GAUSSIAN: Gauss | Cân màu | Nét | Full]
        SWITCH[Chuyển Tab: Giữ Center, Zoom, Rotation & Badges]
        EXP_CURR[Xuất Phiên bản Hiện tại]
        EXP_ALL[Xuất lại Cả 8 Biến thể Độc lập]
    end
```

---

## 2. Bảng Quy chuẩn 8 Biến thể Hậu Xử lý

| ID | Nhóm | File Name | Nhãn Hiển thị | Mô tả Xử lý |
| :--- | :--- | :--- | :--- | :--- |
| `original` | Gốc | `{case}_01_goc.tif` | Gốc | Panorama gốc, không hậu xử lý |
| `original_balanced` | Gốc | `{case}_02_goc_can_sang.tif` | Gốc+Cân màu | Cân màu / phơi sáng nhẹ sau ghép |
| `original_clarity` | Gốc | `{case}_03_goc_sac_net.tif` | Gốc+Nét | Cellular Clarity vi thể tế bào |
| `original_full` | Gốc | `{case}_04_goc_can_sang_net.tif` | Gốc+Full | Cân màu và Cellular Clarity |
| `gaussian` | Gaussian | `{case}_05_gaussian.tif` | Gaussian | Cân trường sáng Gaussian nền sau ghép |
| `gaussian_balanced` | Gaussian | `{case}_06_gaussian_can_sang.tif` | Gaussian+Cân màu | Gaussian và cân màu |
| `gaussian_clarity` | Gaussian | `{case}_07_gaussian_sac_net.tif` | Gaussian+Nét | Gaussian và Cellular Clarity |
| `gaussian_full` | Gaussian | `{case}_08_gaussian_full.tif` | Gaussian+Full | Gaussian, cân màu và Cellular Clarity |

---

## 3. Quy trình Xuất sau Chỉnh sửa Thủ công (Order of Operations)

Khi người dùng thực hiện xuất thủ công (xuất phiên bản hiện tại hoặc xuất cả 8):
1. **Panorama tự động của phiên bản**: Tạo hoặc tái sử dụng canvas nền của biến thể.
2. **Áp dụng Focus Region riêng của biến thể**: Ghép các lát cắt nét thủ công đè lên trước các bước hậu xử lý màu.
3. **Áp dụng Hậu xử lý tương ứng**: Áp dụng Gaussian nền, cân màu và/hoặc Cellular Clarity tùy theo phong cách của chính biến thể đó.
4. **Áp dụng Invisible Brush / Alpha Mask riêng**: Mặt nạ loại trừ / khôi phục của riêng workspace đó.
5. **Áp dụng Crop Viewport riêng**: Cắt phạm vi hiển thị xuất theo viewport đã định nghĩa của workspace.
6. **Xuất File & DeepZoom DZI**: Sinh file TIFF/PNG/JPEG và cấu trúc thư mục DZI an toàn (atomic replace).

---

## 4. Thuật toán Hòa trộn Không Vết cắt (Seam-Free Blending) & Cân màu Độc lập Nền

1. **Khử hoàn toàn vết cắt viền ô vuông (Normalized Hermite S-curve Blending)**:
   - Thay vì cắt viền 28px đột ngột, sử dụng `cv2.distanceTransform` có pad 1px viền 0 quanh mask để tính khoảng cách thực đến mép tile.
   - Áp dụng hàm mượt bậc 3 Hermite $S(u) = u^2(3 - 2u)$ với độ rộng dải chuyển tiếp tương ứng $22\%$ cạnh ngắn tile (`feather_band = max(16.0, min_dim * 0.22)`).
   - Trọng số chuẩn hóa $\sum w_i = 1.0$ trên toàn canvas, triệt tiêu hoàn toàn bước nhảy sắc tố giữa các ô ảnh (sai số viền $< 0.6$ đơn vị).

2. **Cân bằng phơi sáng dựa trên vùng chồng lấn thực sự (Overlap-based Gains)**:
   - Tuyệt đối không đo trên nền lam kính (tránh hiện tượng lệch màu giữa ô nhiều kính và ô nhiều mô).
   - Thuật toán `estimate_overlap_exposure_gains` so khớp trực tiếp tỷ lệ độ sáng của vùng mô nằm chung giữa 2 tile kề nhau.
   - Dải lấy mẫu màu mô học được giới hạn trong khoảng Luma 25 - 235, giữ nguyên độ tương phản tự nhiên của tế bào và cấu trúc mô.

3. **Tính Độc lập Tuyệt đối giữa 8 Biến thể**:
   - Vùng nét được lưu trữ theo biến thể đang kích hoạt (`variantWorkspaces[activeVariantId]`).
   - Giao diện Sidebar hiển thị rõ nhãn biến thể: `⭐ Applied Focus Regions · [Gốc] (1):` thay vì `(0)` gây hiểu nhầm.
   - Biến thể khác (`[Gốc+Nét]`, `[Gaussian]`) mặc định độc lập và có sẵn nút `📋 Chép từ Gốc` nếu người dùng muốn đồng bộ nhanh.
