---
title: 'OmniStitch Studio: Interactive Planar Image Registration and Localized Clarity Inspection'
tags:
  - Python
  - image registration
  - digital pathology
  - whole slide imaging
  - focus measure
  - deep zoom
authors:
  - name: Tien-Phat Nguyen
    affiliation: 1
affiliations:
  - name: College of Information and Communication Technology, Can Tho University, Can Tho, Vietnam
    index: 1
date: 30 August 2026
bibliography: paper.bib
repository-code: https://github.com/Phatjhhoq8/omnistitch-studio
---

# Summary

Researchers who acquire a specimen or surface as overlapping photographs must align those images before viewing them as one mosaic. `OmniStitch Studio` is an open-source Python application for this planar workflow. It combines automatic alignment with an editable project in which users can inspect overlaps, correct placements, mask or crop regions, and export flat or zoomable outputs. The application is intended primarily for microscope-stage tiles and other approximately planar image sets. It does not perform three-dimensional photogrammetry, georeferencing, semantic cloud detection, or clinical image-quality assessment.

The automatic path offers SIFT, AKAZE, and ORB features. Pairwise transforms are propagated through a confidence-weighted graph, after which users may adjust layers manually. The *Clarity Inspector* ranks sources that overlap a selected region using a local sharpness measure [@pertuz2013analysis]. The ranking supports human review rather than automatically declaring a medically or semantically superior source. Outputs include TIFF, PNG, JPEG, and DeepZoom pyramids for multiresolution viewing with OpenSeadragon [@openseadragon].

# Statement of Need

Feature-based mosaicing is well established [@lowe2004distinctive; @fischler1981random], but a research workflow extends beyond estimating a transform. Users need to inspect overlap quality, correct failed placements, preserve an editable project, replace a defective local region without rebuilding an entire stack, and publish an output that can be navigated efficiently. These tasks are particularly relevant when a laboratory captures microscope fields with general-purpose equipment rather than a scanner-specific acquisition ecosystem.

Existing biological stitching methods provide strong automated registration [@preibisch2009globally], and QuPath provides extensive downstream whole-slide visualization and analysis [@bankhead2017qupath]. `OmniStitch Studio` addresses the intervening construction and review workflow. It combines automatic planar alignment with persistent manual editing, region-level source comparison, alpha-aware masks, and DZI publication in one locally operated application.

# State of the Field

ImageJ/Fiji Grid/Collection Stitching and BigStitcher provide established registration workflows for tiled microscopy, including globally optimized placement and support for large or multidimensional acquisitions [@preibisch2009globally; @horl2019bigstitcher]. MIST combines stage modeling with error minimization for scalable microscopy mosaics [@chalfoun2017mist]. QuPath is a mature platform for annotation and analysis of an already assembled whole-slide image [@bankhead2017qupath]. General panorama pipelines combine invariant features, geometric verification, and blending [@brown2007automatic]. Rather than reimplement downstream pathology analysis or three-dimensional reconstruction, `OmniStitch Studio` focuses on an editable planar project model and the transition from source tiles to inspectable outputs.

The build-versus-contribute rationale is the integration boundary: source-to-world transforms, region masks, crop state, focus replacements, export settings, and revisions share one validated project schema. The same state drives the browser canvas, local inspection requests, and final manual export. This makes corrections reproducible within the project instead of leaving them as unrecorded edits in separate tools.

# Software Design

The software separates six responsibilities:

1. `backend/feature_engine.py` extracts SIFT, AKAZE, or ORB features, with optional contrast enhancement.
2. `backend/matcher.py` performs one-way two-nearest-neighbor filtering with a default Lowe ratio of 0.80 and estimates rigid, affine, or projective transforms. The default affine path preferentially uses USAC-MAGSAC with a 3.5-pixel reprojection threshold and falls back to RANSAC.
3. `backend/global_stitching.py` builds a maximum-confidence spanning forest using a Prim-style greedy procedure. Pairwise transforms are multiplied along forest paths; this is not bundle adjustment and does not eliminate all accumulated error. Disconnected components receive a documented index-based fallback placement.
4. `backend/patch_inspector.py` resamples source regions into a bounded preview and computes an alpha-weighted population variance of the grayscale Laplacian. Because the score depends on texture, contrast, noise, and scale, candidate selection remains interactive.
5. `backend/manual_export.py` renders manual TIFF/BigTIFF output in bounded spatial tiles through memory-mapped intermediates. Automatic stitching uses decoded inputs and full-canvas floating-point blend buffers protected by a preflight memory estimate; PNG and JPEG export are also non-streaming.
6. The browser controller, project store, canvas engine, and OpenSeadragon viewer provide revision-aware persistence and interactive editing over the same project schema.

This separation reflects an explicit trade-off. All-pairs matching can discover overlaps without acquisition metadata, but its pair count grows quadratically. A spanning forest is simple and robust to disconnected graphs, but discards loop constraints. Tiled manual export limits working regions, whereas the automatic compositor favors implementation simplicity and remains full canvas.

# Research Impact Statement

The repository provides a privacy-safe synthetic four-tile data set, a reproducible demonstration workflow, installation instructions, issue templates, contribution and governance guidance, continuous-integration configuration, and 53 automated test methods. On 31 August 2026, the complete test command passed locally. The tests cover descriptor matching, known-transform affine estimation, spanning-forest construction, matrix contracts, schema validation, project persistence, alpha-aware compositing and downsampling, patch inspection, guarded region decoding, HTTP security, server integration, and tiled manual export.

The bundled four 600-by-600 pixel tiles exercise the automatic pipeline and produce a 1001-by-1001 pixel mosaic and DZI pyramid. This is an integration smoke test, not a claim of accuracy on real specimens or scalability. A research-use record distinguishes reproducible verification from published use. No external adoption or validated clinical use is currently claimed; evidence of actual research use must be added before JOSS submission.

# AI Usage Disclosure

OpenAI GPT-5.5 and `openai/gpt-5.6-sol` were used to audit manuscript statements against the source code, assist with copy editing, draft documentation, and scaffold deterministic tests. The author retains responsibility for reviewing, editing, and validating all AI-assisted outputs, for running the tests, and for the core problem framing and design decisions. This disclosure must be confirmed by the author before submission.

# Acknowledgements

The author thanks the maintainers of OpenCV, NumPy, Pillow, tifffile, psutil, and OpenSeadragon. No external funding supported this work. The author declares no competing interests.

# References
