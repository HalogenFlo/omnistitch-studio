# Privacy Policy

**Effective Date**: January 1, 2026

## 1. Overview
**OmniStitch Studio** processes images locally and does not include application telemetry. Users remain responsible for assessing whether their deployment and data handling satisfy institutional and legal requirements.

## 2. No Data Collection & No Telemetry
- **Zero Application Telemetry**: OmniStitch Studio contains no tracking scripts, analytics, or telemetry.
- **No Third-Party Transmission**: None of your whole slide images (WSI), tiles, alignment coordinates, or diagnostic annotations are ever uploaded or transmitted to external servers or cloud services.
- **Browser Dependencies**: The current browser interface references fonts, icons, and OpenSeadragon assets hosted by third-party content delivery networks. Image processing remains local, but loading the interface can produce network requests for those assets. Air-gapped deployment requires vendoring or replacing these resources.

## 3. Local Data Processing
All calculations—including:
- SIFT feature extraction,
- Matrix coordinate optimization,
- DeepZoom (DZI) pyramid generation,
- Localized focus region analysis,

occur strictly within your local machine's runtime environment (`localhost`).

## 4. Regulatory Responsibility
- **No compliance certification**: The project has not been independently assessed or certified for HIPAA, GDPR, diagnostic, or clinical use.
- **De-identification Responsibility**: Users are responsible for ensuring that digital slide metadata (e.g., patient labels embedded in TIFF/DICOM headers) complies with their institutional review boards (IRB) and ethical guidelines before sharing exported slides publicly.

## 5. Contact
For privacy questions, open a GitHub issue that contains no sensitive data. Use a private GitHub security advisory if disclosure could create a security risk.
