# Hướng Dẫn Nộp Đơn Tham Gia Chương Trình OpenAI Codex for Open Source

Tài liệu này chuẩn bị sẵn toàn bộ thông tin để bạn tạo GitHub Repository và điền vào form đăng ký của OpenAI tại:
👉 **[https://openai.com/form/codex-for-oss/](https://openai.com/form/codex-for-oss/)**

---

## BƯỚC 1: Đẩy Bản Sao Mã Nguồn Lên GitHub

1. Truy cập [GitHub](https://github.com) và tạo một **New Repository**:
   - **Repository name**: `omnistitch-studio`
   - **Description**: `Cross-domain Gigapixel Image Stitching & Multi-Focus / De-Clouding Clarity Inspector for Microscopy & Remote Sensing`
   - **Visibility**: Chọn **Public** *(Bắt buộc đối với chương trình Open Source của OpenAI)*
   - **Do NOT check** "Add a README file" (vì chúng ta đã tạo sẵn README xịn).

2. Mở Terminal (PowerShell hoặc Command Prompt) tại máy tính của bạn và chạy:

```bash
cd C:\Users\Admin\Desktop\NCKH\wsi-stitching-studio
git init
git add .
git commit -m "feat: initial open-source release of OmniStitch Studio v1.0.0"
git branch -M main
git remote add origin https://github.com/<GITHUB_USERNAME_CUA_BAN>/omnistitch-studio.git
git push -u origin main
```

*(Thay `<GITHUB_USERNAME_CUA_BAN>` bằng tên tài khoản GitHub của bạn)*

---

## BƯỚC 2: Điền Form Đăng Ký OpenAI Codex for OSS

Truy cập: **[https://openai.com/form/codex-for-oss/](https://openai.com/form/codex-for-oss/)**

### 1. Thông tin cá nhân & Dự án
- **First Name**: Tên của bạn
- **Last Name**: Họ của bạn
- **Email**: Địa chỉ email liên kết với tài khoản ChatGPT của bạn
- **GitHub Username**: Tên tài khoản GitHub của bạn
- **GitHub Repository URL**: `https://github.com/<GITHUB_USERNAME_CUA_BAN>/omnistitch-studio`
- **Role in the project**: Chọn **Primary maintainer** *(Tăng tỷ lệ duyệt cao nhất)*

---

### 2. Các câu hỏi văn bản (Đã soạn sẵn chuẩn tiếng Anh, dưới 500 ký tự)

#### Câu 1: Why does this repository qualify? (Max 500 characters)
*Copy & dán đoạn văn bản dưới đây (486 ký tự):*

```text
OmniStitch Studio is an active open-source scientific suite for gigapixel image alignment across Whole Slide Microscopy (WSI) and Geospatial Remote Sensing (UAV/Satellite). It features 2D SIFT global homography optimization, DeepZoom (DZI) interactive pyramids, and a novel clarity inspector for multi-focus stacking and satellite de-clouding. With full CI/CD test automation (48 unit tests), it democratizes high-performance cross-domain mosaic exploration for global research teams.
```

---

#### Câu 2: Which benefits are you interested in?
- [x] **Codex Security** *(Quét bảo mật mã nguồn)*
- [x] **API credits** *(Tài trợ credits API cho workflow dự án)*

---

#### Câu 3: How will you use the API credits for your project? (Max 500 characters)
*Copy & dán đoạn văn bản dưới đây (488 ký tự):*

```text
We will integrate OpenAI Codex into our GitHub Actions workflows to automate pull request reviews, verify numerical invariance in coordinate matrix transformations, generate regression test cases for edge-case slide alignments, and assist in triaging bug reports from pathology researchers. Credits will also power automated release note generation and continuous documentation updates for biomedical microscopy users.
```

---

#### Câu 4: Additional Context (Optional - Max 500 characters)
*Copy & dán đoạn văn bản dưới đây (475 ký tự):*

```text
OmniStitch Studio serves dual scientific communities: pathology laboratories requiring WSI stitching without expensive hardware scanners, and environmental researchers assembling drone orthomosaics and cloud-free satellite maps. Fully compliant with open web standards (OpenSeadragon, DeepZoom, GIS-ready) and distributed under the MIT license. Active maintenance is prioritized with automated CI across Python 3.10-3.12.
```

---

## BƯỚC 3: Nhận Kết Quả

OpenAI xét duyệt hồ sơ theo hình thức **rolling basis** (duyệt liên tục). Sau khi nộp, họ sẽ gửi email thông báo cấp quyền:
- **ChatGPT Pro Access** (6 tháng miễn phí có tính năng Codex).
- **API Credits** nạp trực tiếp vào tài khoản OpenAI Organization của bạn.
- **Codex Security Scanning** trên kho GitHub.
