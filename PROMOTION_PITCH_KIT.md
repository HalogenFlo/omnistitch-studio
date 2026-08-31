# Promotion Notes

Use conservative, evidence-backed wording for public communication.

Recommended short description:

> OmniStitch Studio is an open-source local web application for approximately planar image stitching. It combines automatic feature registration, persistent manual layer editing, localized Laplacian-based clarity inspection, and DeepZoom export.

Avoid claims that are not yet supported by reproducible benchmarks:

- Do not claim validated gigapixel scalability.
- Do not claim sub-millisecond viewport performance.
- Do not claim 100% test coverage.
- Do not claim automatic de-clouding, GIS orthomosaic reconstruction, or clinical diagnostic validation.
- Do not claim superiority over ImageJ, Hugin, WebODM, or commercial scanners without controlled benchmark data.

Current evidence that can be stated:

- The repository includes a synthetic 2 x 2 demo data set.
- The automatic pipeline can stitch the demo into a 1001 x 1001 output and DZI pyramid.
- The test suite currently contains 53 automated test methods.
- Manual TIFF/BigTIFF export uses tiled rendering and memory-mapped intermediates.
