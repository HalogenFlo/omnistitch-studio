# Privacy Policy

**Effective Date**: January 1, 2026

## 1. Overview
**WSI Stitching Studio** is committed to protecting the privacy and confidentiality of clinical, pathological, and biomedical research data. Because this software is designed for use in academic institutions, hospitals, and clinical laboratories, privacy-by-design is a fundamental principle.

## 2. No Data Collection & No Telemetry
- **Zero Telemetry**: WSI Stitching Studio contains **no tracking scripts, analytics, or telemetry**.
- **No Third-Party Transmission**: None of your whole slide images (WSI), tiles, alignment coordinates, or diagnostic annotations are ever uploaded or transmitted to external servers or cloud services.
- **Offline & Air-Gapped Operation**: The entire pipeline operates completely offline on local machines, internal institutional servers, or air-gapped laboratory workstations.

## 3. Local Data Processing
All calculations—including:
- SIFT feature extraction,
- Matrix coordinate optimization,
- DeepZoom (DZI) pyramid generation,
- Localized focus region analysis,

occur strictly within your local machine's runtime environment (`localhost`).

## 4. Compliance with Biomedical Standards
- **HIPAA / GDPR Compatibility**: Because no Protected Health Information (PHI) or Personally Identifiable Information (PII) is stored or sent outside your system, WSI Stitching Studio seamlessly fits into HIPAA-compliant and GDPR-compliant institutional environments.
- **De-identification Responsibility**: Users are responsible for ensuring that digital slide metadata (e.g., patient labels embedded in TIFF/DICOM headers) complies with their institutional review boards (IRB) and ethical guidelines before sharing exported slides publicly.

## 5. Contact
For questions or inquiries regarding privacy practices in this software, please contact the maintainers via GitHub Discussions or at **privacy@wsi-stitching-studio.org**.
