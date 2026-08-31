# OpenAI Codex Application Notes

This document is retained as a conservative project-summary draft.

OmniStitch Studio is a local, open-source web application for approximately planar image stitching. It includes automatic feature-based registration, project persistence, manual layer adjustment, localized clarity inspection, alpha-aware masks, and DeepZoom export.

Security-relevant areas for automated review include:

- path containment for image and project files,
- request-size limits,
- image decoder limits,
- memory-budget checks for large outputs,
- tiled TIFF export and temporary artifact publication,
- project revision validation,
- unauthenticated local HTTP endpoints.

Unsupported claims must not be used in applications or papers until measured with reproducible artifacts. These include automatic de-clouding, GIS-ready orthomosaics, clinical deployment readiness, zero vulnerabilities, 100% test coverage, and validated gigapixel performance.
