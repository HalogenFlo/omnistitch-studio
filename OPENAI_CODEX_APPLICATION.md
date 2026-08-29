# OpenAI Codex for Open Source - Application Guide & Field Answers

This document contains pre-vetted, character-capped (under 500 characters) responses ready to be submitted to:
👉 **[https://openai.com/form/codex-for-oss/](https://openai.com/form/codex-for-oss/)**

---

## STEP 1: Push OmniStitch Studio to Your Public GitHub Account

1. Go to [GitHub](https://github.com) and create a **New Repository**:
   - **Repository name**: `omnistitch-studio`
   - **Description**: `Cross-domain Gigapixel Image Stitching & Multi-Focus / De-Clouding Clarity Inspector for Microscopy & Remote Sensing`
   - **Visibility**: Select **Public** *(Mandatory for OpenAI Open Source program)*
   - **Do NOT check** "Add a README file" (as our repository is fully prepared).

2. Open your Terminal (PowerShell / Command Prompt) and run:

```bash
cd C:\Users\Admin\Desktop\NCKH\omnistitch-studio
git init
git add .
git commit -m "feat: initial open-source release of OmniStitch Studio v1.0.0"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/omnistitch-studio.git
git push -u origin main
```

*(Replace `<YOUR_GITHUB_USERNAME>` with your actual GitHub username)*

---

## STEP 2: Fill in the OpenAI Codex for OSS Form

Form URL: **[https://openai.com/form/codex-for-oss/](https://openai.com/form/codex-for-oss/)**

### 1. General & Maintainer Information
- **First Name**: Your First Name
- **Last Name**: Your Last Name
- **Email**: Your email address associated with your ChatGPT account
- **GitHub Username**: Your GitHub username
- **GitHub Repository URL**: `https://github.com/<YOUR_GITHUB_USERNAME>/omnistitch-studio`
- **Role in the project**: Select **Primary maintainer**

---

### 2. Standardized Field Responses (< 500 Characters)

#### Field: Why does this repository qualify? (Max 500 characters)
```text
OmniStitch Studio is an active open-source scientific suite for gigapixel image alignment across Whole Slide Microscopy (WSI) and Geospatial Remote Sensing (UAV/Satellite). It features 2D SIFT global homography optimization, DeepZoom (DZI) interactive pyramids, and a novel clarity inspector for multi-focus stacking and satellite de-clouding. With full CI/CD test automation (48 unit tests), it democratizes high-performance cross-domain mosaic exploration for global research teams.
```

#### Field: I’m interested in...
- [x] **Codex Security**
- [x] **API credits for my project**

#### Field: Why does your project need Codex Security? (Max 500 characters)
```text
OmniStitch Studio processes massive gigapixel biomedical slides and remote sensing mosaics. Parsing raw TIFF/BigTIFF headers, handling large image buffer decodes, and file I/O operations create critical attack surfaces for path traversal, memory exhaustion, and buffer overflows. Codex Security will help continuously scan our C-extension/Python bindings and web endpoints, ensuring air-gapped clinical labs and research institutions can deploy the software with zero security vulnerabilities.
```

#### Field: OpenAI Organization ID
- Click **`Click here`** beneath the field to retrieve your Organization ID (format: `org-xxxxxxxxxxxxxxxxxxxxxxxx`).

#### Field: How will you use API credits for your project? (Max 500 characters)
```text
We will integrate OpenAI Codex into our GitHub Actions workflows to automate pull request reviews, verify numerical invariance in coordinate matrix transformations, generate regression test cases for edge-case slide alignments, and assist in triaging bug reports from pathology researchers. Credits will also power automated release note generation and continuous documentation updates for biomedical microscopy users.
```

#### Field: Anything else we should know? (Max 500 characters)
```text
OmniStitch Studio serves dual scientific communities: pathology laboratories requiring WSI stitching without expensive hardware scanners, and environmental researchers assembling drone orthomosaics and cloud-free satellite maps. Fully compliant with open web standards (OpenSeadragon, DeepZoom, GIS-ready) and distributed under the MIT license. Active maintenance is prioritized with automated CI across Python 3.10-3.12.
```

---

## STEP 3: Submission & Review
Click **Submit** to finalize your application. OpenAI reviews applications on a rolling basis and will notify you by email upon approval of your **ChatGPT Pro, API Credits, and Codex Security Access**.
