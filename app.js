// Feature: Studio controller logic for OmniStitch Studio & Canvas Editor
// Purpose: Bidirectional sync between Auto and Manual modes, layer management, and export pipeline
// Path: app.js

(function () {
    'use strict';

    // UI Local State
    const uiState = {
        isStitching: false,
        isUploading: false,
        pollInterval: null,
        osdViewer: null,
        osdSourceKey: null,
        osdInteractionMode: 'navigate',
        outputPixelToWorld: MatrixUtils.identity(),
        worldToOutputPixel: MatrixUtils.identity(),
        spacePressed: false
    };

    const osdDrawState = {
        drawing: false,
        pointsWorld: [],
        currentWorld: null,
        pointerId: null,
        panning: false,
        lastScreen: null
    };

    // DOM Elements Cache
    const DOM = {
        btnModeAuto: document.getElementById('btnModeAuto'),
        btnModeManual: document.getElementById('btnModeManual'),
        viewportCurrentModeLabel: document.getElementById('viewportCurrentModeLabel'),
        btnRunStitching: document.getElementById('btnRunStitching'),
        btnStitchText: document.getElementById('btnStitchText'),
        globalStatusBadge: document.getElementById('globalStatusBadge'),
        statusBadgeText: document.getElementById('statusBadgeText'),

        btnToggleSidebar: document.getElementById('btnToggleSidebar'),
        sidebar: document.getElementById('sidebar'),
        btnResetAll: document.getElementById('btnResetAll'),
        btnSaveOutput: document.getElementById('btnSaveOutput'),

        sidebarTabs: document.querySelectorAll('.tab-btn'),
        tabContents: document.querySelectorAll('.tab-content'),
        tabBtnLayers: document.getElementById('tabBtnLayers'),

        currentFolderNameDisplay: document.getElementById('currentFolderNameDisplay'),
        expectedOutputPathDisplay: document.getElementById('expectedOutputPathDisplay'),
        inputOutputDir: document.getElementById('inputOutputDir'),

        uploadDropzone: document.getElementById('uploadDropzone'),
        btnBrowseFolder: document.getElementById('btnBrowseFolder'),
        btnBrowseFiles: document.getElementById('btnBrowseFiles'),
        folderInput: document.getElementById('folderInput'),
        fileInput: document.getElementById('fileInput'),

        tileGrid: document.getElementById('tileGridContainer'),
        selectedCountBadge: document.getElementById('selectedCountBadge'),
        btnSelectAll: document.getElementById('btnSelectAll'),
        btnDeselectAll: document.getElementById('btnDeselectAll'),
        btnClearList: document.getElementById('btnClearList'),

        // Tab Layers
        layersListContainer: document.getElementById('layersListContainer'),
        layerAdjustmentsCard: document.getElementById('layerAdjustmentsCard'),
        adjustLayerName: document.getElementById('adjustLayerName'),
        sliderOpacity: document.getElementById('sliderOpacity'),
        valOpacity: document.getElementById('valOpacity'),
        sliderBrightness: document.getElementById('sliderBrightness'),
        valBrightness: document.getElementById('valBrightness'),
        sliderContrast: document.getElementById('sliderContrast'),
        valContrast: document.getElementById('valContrast'),
        sliderSaturation: document.getElementById('sliderSaturation'),
        valSaturation: document.getElementById('valSaturation'),
        btnResetAdjustments: document.getElementById('btnResetAdjustments'),
        btnLayerUp: document.getElementById('btnLayerUp'),
        btnLayerDown: document.getElementById('btnLayerDown'),
        btnLayerLock: document.getElementById('btnLayerLock'),

        // Configs
        cfgFeatureMethod: document.getElementById('cfgFeatureMethod'),
        cfgMotionModel: document.getElementById('cfgMotionModel'),
        cfgBackgroundMode: document.getElementById('cfgBackgroundMode'),
        cfgAutoCrop: document.getElementById('cfgAutoCrop'),
        cfgExportFormat: document.getElementById('cfgExportFormat'),

        // Progress Panel
        progressPanel: document.getElementById('progressPanel'),
        progressStepTitle: document.getElementById('progressStepTitle'),
        progressPercentage: document.getElementById('progressPercentage'),
        progressBarFill: document.getElementById('progressBarFill'),
        terminalLogs: document.getElementById('terminalLogs'),
        progressPanelResizer: document.getElementById('progressPanelResizer'),
        btnToggleProgressExpand: document.getElementById('btnToggleProgressExpand'),
        iconProgressExpand: document.getElementById('iconProgressExpand'),

        // Viewports & Toolbars
        viewDeepZoom: document.getElementById('view-deepzoom'),
        viewManualCanvas: document.getElementById('view-manual-canvas'),
        manualCanvasContainer: document.getElementById('manualCanvasContainer'),
        manualToolbar: document.getElementById('manualToolbar'),
        btnUndo: document.getElementById('btnUndo'),
        btnRedo: document.getElementById('btnRedo'),
        btnFitContent: document.getElementById('btnFitContent'),
        btnZoomIn: document.getElementById('btnZoomIn'),
        btnZoomOut: document.getElementById('btnZoomOut'),

        osdPlaceholder: document.getElementById('osdPlaceholder'),
        resultActions: document.getElementById('resultActions'),
        btnSaveTrigger: document.getElementById('btnSaveTrigger'),
        saveBtnText: document.getElementById('saveBtnText'),
        btnResetViewer: document.getElementById('btnResetViewer'),
        autoViewerToolbar: document.getElementById('autoViewerToolbar'),
        btnOsdNavigate: document.getElementById('btnOsdNavigate'),
        btnOsdZoomOut: document.getElementById('btnOsdZoomOut'),
        btnOsdZoomIn: document.getElementById('btnOsdZoomIn'),
        btnOsdFit: document.getElementById('btnOsdFit'),
        btnOsdOneToOne: document.getElementById('btnOsdOneToOne'),
        btnOsdReset: document.getElementById('btnOsdReset'),
        osdZoomIndicator: document.getElementById('osdZoomIndicator'),
        osdDrawingCanvas: document.getElementById('osdDrawingCanvas'),

        // Modal Save Elements
        saveModalBackdrop: document.getElementById('saveModalBackdrop'),
        modalInputFileName: document.getElementById('modalInputFileName'),
        modalSelectFormat: document.getElementById('modalSelectFormat'),
        modalInputTargetDir: document.getElementById('modalInputTargetDir'),
        modalFullTargetPathPreview: document.getElementById('modalFullTargetPathPreview'),
        btnCloseSaveModal: document.getElementById('btnCloseSaveModal'),
        btnCancelSaveModal: document.getElementById('btnCancelSaveModal'),
        btnConfirmSave: document.getElementById('btnConfirmSave'),
        btnDirectBrowserDownload: document.getElementById('btnDirectBrowserDownload'),

        // Right Inspector Elements
        btnToggleInspectMode: document.getElementById('btnToggleInspectMode'),
        inspectModeToggleText: document.getElementById('inspectModeToggleText'),
        rightInspectorPanel: document.getElementById('rightInspectorPanel'),
        btnCloseInspector: document.getElementById('btnCloseInspector'),
        drawingToolPills: document.querySelectorAll('.tool-pill'),
        brushControlsGroup: document.getElementById('brushControlsGroup'),
        sliderBrushRadius: document.getElementById('sliderBrushRadius'),
        valBrushRadius: document.getElementById('valBrushRadius'),
        brushPresetPills: document.querySelectorAll('#brushPresetPills .pill-btn-sm'),
        rectPresetGroup: document.getElementById('rectPresetGroup'),
        regionSizePills: document.querySelectorAll('#regionSizePills .pill-btn'),
        cropControlsGroup: document.getElementById('cropControlsGroup'),
        chkTrimOutputBounds: document.getElementById('chkTrimOutputBounds'),
        btnApplyCrop: document.getElementById('btnApplyCrop'),
        btnCancelCrop: document.getElementById('btnCancelCrop'),
        btnResetCrop: document.getElementById('btnResetCrop'),
        inspectorStatusBanner: document.getElementById('inspectorStatusBanner'),
        inspectorStatusText: document.getElementById('inspectorStatusText'),
        inspectorPinBar: document.getElementById('inspectorPinBar'),
        inspectorPinCoords: document.getElementById('inspectorPinCoords'),
        btnUnpinInspector: document.getElementById('btnUnpinInspector'),
        inspectorPatchesContainer: document.getElementById('inspectorPatchesContainer'),
        inspectorEmptyState: document.getElementById('inspectorEmptyState'),
        inspectorPatchesList: document.getElementById('inspectorPatchesList'),
        focusRegionsSection: document.getElementById('focusRegionsSection'),
        focusRegionCount: document.getElementById('focusRegionCount'),
        focusRegionsList: document.getElementById('focusRegionsList'),
        btnClearAllFocusRegions: document.getElementById('btnClearAllFocusRegions'),
        exclusionStrokesSection: document.getElementById('exclusionStrokesSection'),
        exclusionStrokeCount: document.getElementById('exclusionStrokeCount'),
        btnClearAllStrokes: document.getElementById('btnClearAllStrokes'),
        maskRegionsList: document.getElementById('maskRegionsList'),
        selectedRegionCount: document.getElementById('selectedRegionCount'),
        batchFocusLayerSelect: document.getElementById('batchFocusLayerSelect'),
        btnBatchApplyLayer: document.getElementById('btnBatchApplyLayer'),
        batchMaskOperation: document.getElementById('batchMaskOperation'),
        btnBatchMaskOperation: document.getElementById('btnBatchMaskOperation'),
        btnBatchLock: document.getElementById('btnBatchLock'),
        btnBatchUnlock: document.getElementById('btnBatchUnlock'),
        btnGroupRegions: document.getElementById('btnGroupRegions'),
        btnUngroupRegions: document.getElementById('btnUngroupRegions'),
        btnBatchDelete: document.getElementById('btnBatchDelete'),
        autosaveConflictBanner: document.getElementById('autosaveConflictBanner'),
        btnRetryAutosave: document.getElementById('btnRetryAutosave'),
        btnDismissAutosaveConflict: document.getElementById('btnDismissAutosaveConflict'),

        // Accordion Elements & Mobile Backdrop
        accordionCards: document.querySelectorAll('.tool-section-card[data-accordion-card]'),
        accordionHeaders: document.querySelectorAll('.accordion-header'),
        badgeClaritySummary: document.getElementById('badgeClaritySummary'),
        badgeBrushSummary: document.getElementById('badgeBrushSummary'),
        badgeCropSummary: document.getElementById('badgeCropSummary'),
        inspectorBackdrop: document.getElementById('inspectorBackdrop'),
        cardSelectMode: document.getElementById('cardSelectMode'),
        btnToolSelectMode: document.getElementById('btnToolSelectMode'),

        // Viewport Visual Region Selector Elements
        viewportSelectionOverlay: document.getElementById('viewportSelectionOverlay'),
        selectionMarquee: document.getElementById('selectionMarquee'),
        marqueeSizeBadge: document.getElementById('marqueeSizeBadge'),
        activeRegionBox: document.getElementById('activeRegionBox'),
        regionBoxTitle: document.getElementById('regionBoxTitle'),
        btnCloseRegionBox: document.getElementById('btnCloseRegionBox'),

        // Patch Clarity Lightbox Modal Elements
        patchPreviewModal: document.getElementById('patchPreviewModal'),
        patchModalTitle: document.getElementById('patchModalTitle'),
        patchModalBadge: document.getElementById('patchModalBadge'),
        btnClosePatchModal: document.getElementById('btnClosePatchModal'),
        patchViewerWrapper: document.getElementById('patchViewerWrapper'),
        patchModalImage: document.getElementById('patchModalImage'),
        btnPatchZoomIn: document.getElementById('btnPatchZoomIn'),
        btnPatchZoomOut: document.getElementById('btnPatchZoomOut'),
        btnPatchZoomReset: document.getElementById('btnPatchZoomReset'),
        patchModalSharpness: document.getElementById('patchModalSharpness'),
        patchModalCoverage: document.getElementById('patchModalCoverage'),
        patchModalDimensions: document.getElementById('patchModalDimensions'),
        patchModalCompareList: document.getElementById('patchModalCompareList'),
        btnPatchModalApply: document.getElementById('btnPatchModalApply')
    };

    // Patch Clarity Inspector State
    const inspectorState = {
        isEnabled: false,
        isPinned: false,
        currentRegion: null, // { shapeType, pointsWorld, boundingRect }
        currentWorldRect: null,
        worldSize: 256,
        outputSize: 256,
        currentTool: 'rect',
        requestGeneration: 0,
        throttleTimer: null,
        abortController: null,
        lastPatches: []
    };

    // Current preview path variable
    let currentPreviewFile = null;

    // ==========================================
    // 0. Export Modal Handler
    // ==========================================
    function openSaveModal() {
        const state = ProjectStore.getState();
        const folderName = state.folderName || 'stitched_wsi';
        const exportFormat = DOM.cfgExportFormat.value || 'tif';

        DOM.modalInputFileName.value = folderName;
        DOM.modalSelectFormat.value = exportFormat;
        DOM.modalInputTargetDir.value = DOM.inputOutputDir ? DOM.inputOutputDir.value : 'data/result';

        updateModalPreviewPath();
        DOM.saveModalBackdrop.style.display = 'flex';
    }

    function closeSaveModal() {
        DOM.saveModalBackdrop.style.display = 'none';
    }

    function updateModalPreviewPath() {
        const fileName = (DOM.modalInputFileName.value.trim() || 'stitched_wsi');
        const ext = DOM.modalSelectFormat.value || 'tif';
        const targetDir = (DOM.modalInputTargetDir.value.trim() || 'data/result');
        DOM.modalFullTargetPathPreview.textContent = `${targetDir}/${fileName}.${ext}`;
    }

    async function handleConfirmSave() {
        const fileName = DOM.modalInputFileName.value.trim() || 'stitched_wsi';
        const targetDir = DOM.modalInputTargetDir.value.trim() || 'data/result';
        const exportFormat = DOM.modalSelectFormat.value || 'tif';

        setStatus('busy', 'Saving mosaic to destination directory...');
        closeSaveModal();

        try {
            const res = await fetch('/api/save_wsi', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folderName: fileName,
                    targetDir: targetDir,
                    exportFormat: exportFormat,
                    sourcePreviewFile: currentPreviewFile || `data/output/${fileName}.${exportFormat}`
                })
            });

            const data = await res.json();
            if (data.status === 'success') {
                setStatus('ready', 'Saved successfully!');
                alert(`✅ MOSAIC SAVED SUCCESSFULLY!\n\n📁 Directory: ${data.folder}\n📄 File: ${data.fileName}\n📍 Full Path: ${data.savedPath}`);
            } else {
                setStatus('ready', 'Error saving mosaic');
                alert("❌ Error: " + (data.error || "Unable to save file"));
            }
        } catch (err) {
            setStatus('ready', 'Connection error');
            alert("❌ Server connection error: " + err.message);
        }
    }

    function handleDirectBrowserDownload() {
        const fileName = DOM.modalInputFileName.value.trim() || 'stitched_wsi';
        const exportFormat = DOM.modalSelectFormat.value || 'tif';
        const fullFileName = `${fileName}.${exportFormat}`;
        const downloadUrl = `/api/image?path=${currentPreviewFile || 'data/output/' + fullFileName}`;

        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = fullFileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        closeSaveModal();
    }

    // ==========================================
    // 1. Mode Switching: Auto <-> Manual (100% State Preservation)
    // ==========================================
    function setAppMode(mode) {
        ProjectStore.setMode(mode);

        if (mode === 'auto') {
            DOM.btnModeAuto.classList.add('active');
            DOM.btnModeManual.classList.remove('active');
            DOM.viewDeepZoom.classList.add('active');
            DOM.viewManualCanvas.classList.remove('active');
            DOM.manualToolbar.style.display = 'none';
            DOM.viewportCurrentModeLabel.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Mode: <b>Auto Stitching (DZI)</b>';
            DOM.btnStitchText.textContent = 'Auto Stitch';
            DOM.btnRunStitching.className = 'btn btn-primary';
            if (DOM.autoViewerToolbar) DOM.autoViewerToolbar.style.display = 'flex';
        } else {
            DOM.btnModeAuto.classList.remove('active');
            DOM.btnModeManual.classList.add('active');
            DOM.viewDeepZoom.classList.remove('active');
            DOM.viewManualCanvas.classList.add('active');
            DOM.manualToolbar.style.display = 'flex';
            DOM.viewportCurrentModeLabel.innerHTML = '<i class="fa-solid fa-palette"></i> Mode: <b>Manual Canvas Editor</b>';
            DOM.btnStitchText.textContent = 'Manual Export';
            DOM.btnRunStitching.className = 'btn btn-success';
            if (DOM.autoViewerToolbar) DOM.autoViewerToolbar.style.display = 'none';

            // Auto-switch tab to Layers & Color
            switchSidebarTab('tab-manual-layers');
            const state = ProjectStore.getState();
            if (state.layers && state.layers.length > 0) {
                CanvasEngine.preloadLayerImages(state.layers);
            }
            requestAnimationFrame(() => {
                CanvasEngine.resize();
                if (state.layers && state.layers.length > 0) {
                    CanvasEngine.fitToContent();
                }
                CanvasEngine.requestRender();
            });
        }
    }

    function switchSidebarTab(targetTabId) {
        DOM.sidebarTabs.forEach(btn => {
            if (btn.dataset.tab === targetTabId) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        DOM.tabContents.forEach(c => {
            if (c.id === targetTabId) {
                c.classList.add('active');
            } else {
                c.classList.remove('active');
            }
        });
    }

    // ==========================================
    // 1b. Reset All Workspace Session
    // ==========================================
    function resetEntireState() {
        ProjectStore.newProject();
        setAppMode('auto');
        inspectorState.isPinned = false;
        inspectorState.currentRegion = null;
        inspectorState.currentWorldRect = null;
        inspectorState.lastPatches = [];
        CanvasEngine.resetSession();

        // Delete session cache
        try {
            localStorage.removeItem('wsi_saved_session');
        } catch (e) {}

        // Hide result save buttons
        if (DOM.btnSaveOutput) DOM.btnSaveOutput.style.display = 'none';
        if (DOM.resultActions) DOM.resultActions.style.display = 'none';
        currentPreviewFile = null;

        // Destroy old viewer and display placeholder
        if (uiState.osdViewer) {
            uiState.osdViewer.destroy();
            uiState.osdViewer = null;
        }
        DOM.osdPlaceholder.style.display = 'block';

        // Reset tile list, layers, focus regions, and progress
        renderTileGrid();
        renderLayersList();
        renderFocusRegionsList();
        CanvasEngine.preloadLayerImages([]);
        CanvasEngine.requestRender();

        DOM.progressPanel.style.display = 'none';
        setStatus('ready', 'Workspace reset. Ready to load directory.');
    }

    // ==========================================
    // 2. Source Directory Scanning
    // ==========================================
    async function scanFolder(folderPath) {
        if (!folderPath || !folderPath.trim()) return;

        // Clean up previous results
        if (DOM.btnSaveOutput) DOM.btnSaveOutput.style.display = 'none';
        if (DOM.resultActions) DOM.resultActions.style.display = 'none';
        currentPreviewFile = null;
        if (uiState.osdViewer) {
            uiState.osdViewer.destroy();
            uiState.osdViewer = null;
        }
        DOM.osdPlaceholder.style.display = 'block';

        setStatus('busy', 'Loading images from directory...');

        try {
            const res = await fetch('/api/scan_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folderPath: folderPath.trim() })
            });
            const data = await res.json();

            if (data.status === 'success') {
                ProjectStore.newProject();
                const state = ProjectStore.getState();
                state.id = data.folderName || 'project_' + Date.now();
                state.folderName = data.folderName;
                CanvasEngine.resetSession();
                setAppMode('auto');

                // Arrange initial tiles in grid
                const n = data.images.length;
                const cols = Math.ceil(Math.sqrt(n));

                ProjectStore.beginTransaction('Import folder images', 'layer_import_batch');
                data.images.forEach((img, idx) => {
                    const tileW = img.width || 2000;
                    const tileH = img.height || 1500;
                    const r = Math.floor(idx / cols);
                    const c = idx % cols;
                    const tx = c * (tileW * 0.85); // 15% assumed overlap
                    const ty = r * (tileH * 0.85);

                    ProjectStore.addLayer({
                        id: 'layer_' + idx,
                        sourceId: img.name,
                        sourcePath: img.path,
                        sourceWidth: tileW,
                        sourceHeight: tileH,
                        sourceToWorld: MatrixUtils.translate(tx, ty),
                        zIndex: idx
                    });
                });
                ProjectStore.commitTransaction();

                updateOutputBanner();
                renderTileGrid();
                renderLayersList();
                renderFocusRegionsList();
                saveCurrentSession();
                setStatus('ready', `Loaded ${data.total} images from ${data.folderName}`);
            } else {
                alert("Directory scan error: " + (data.error || "Cannot scan directory"));
                setStatus('ready', 'Ready');
            }
        } catch (err) {
            alert("Server connection error: " + err.message);
            setStatus('ready', 'Ready');
        }
    }

    function updateOutputBanner() {
        const state = ProjectStore.getState();
        const ext = DOM.cfgExportFormat.value || 'tif';
        const targetDir = (DOM.inputOutputDir ? DOM.inputOutputDir.value : 'data/result') || 'data/result';
        if (DOM.currentFolderNameDisplay) DOM.currentFolderNameDisplay.textContent = state.folderName || 'No images loaded';
        if (DOM.expectedOutputPathDisplay) DOM.expectedOutputPathDisplay.textContent = `${targetDir}/${state.folderName || '[Folder_Name]'}.${ext}`;
    }

    function resetImageLevelToolsUI() {
        // 1. Reset Crop
        ProjectStore.clearCropRegion();
        ProjectStore.cancelCropDraft();

        // 2. Reset Mask/Brush
        ProjectStore.clearMaskRegions();

        // 3. Reset Focus Regions & Inspector
        ProjectStore.clearFocusRegions();
        unpinInspector();

        // 4. Delete drawing drafts on OpenSeadragon & Canvas
        clearOsdDrawingDraft();
        if (typeof CanvasEngine.cancelDraft === 'function') {
            CanvasEngine.cancelDraft();
        }

        // 5. Clean up inspector UI
        if (DOM.viewportSelectionOverlay) DOM.viewportSelectionOverlay.style.display = 'none';
        if (DOM.activeRegionBox) DOM.activeRegionBox.style.display = 'none';
        if (DOM.inspectorPatchesList) {
            DOM.inspectorPatchesList.style.display = 'none';
            DOM.inspectorPatchesList.innerHTML = '';
        }
        if (DOM.inspectorEmptyState) {
            DOM.inspectorEmptyState.style.display = 'block';
            DOM.inspectorEmptyState.innerHTML = `
                <i class="fa-solid fa-crosshairs text-muted"></i>
                <p>Switched to new image. Focus regions, brush masks, and crop bounds have been reset.</p>
            `;
        }
        if (DOM.inspectorStatusText) {
            DOM.inspectorStatusText.textContent = 'Switched image: reset focus regions, brush masks, and crop bounds.';
        }

        CanvasEngine.requestRender();
        renderOsdDrawingDraft();
    }
    window.resetImageToolsOnLayerChange = resetImageLevelToolsUI;

    function renderTileGrid() {
        DOM.tileGrid.innerHTML = '';
        const state = ProjectStore.getState();
        const list = state.layers || [];
        const currentSelectedId = state.selection[0];

        if (list.length === 0) {
            DOM.tileGrid.innerHTML = `
                <div class="empty-state">
                    <i class="fa-regular fa-folder-open"></i>
                    <p>Directory empty or contains no supported images (.tif, .png, .jpg)</p>
                </div>
            `;
            updateSelectedBadge();
            return;
        }

        list.forEach(layer => {
            const isCurrentActive = (layer.id === currentSelectedId);
            const card = document.createElement('div');
            card.className = `tile-card ${layer.visible ? 'selected' : ''} ${isCurrentActive ? 'active-tile' : ''}`;
            card.dataset.id = layer.id;

            const thumbUrl = `/api/thumbnail?path=${encodeURIComponent(layer.sourcePath)}`;

            card.innerHTML = `
                <img src="${thumbUrl}" class="tile-thumb" alt="${layer.sourceId}" loading="lazy">
                <div class="tile-info">
                    <span class="tile-name" title="${layer.sourceId}">${layer.sourceId}</span>
                    <span class="tile-check" title="Select for stitching">${layer.visible ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-regular fa-circle"></i>'}</span>
                </div>
            `;

            card.addEventListener('click', (e) => {
                if (e.target.closest('.tile-check')) {
                    ProjectStore.updateLayerProperties(layer.id, { visible: !layer.visible });
                    card.classList.toggle('selected', layer.visible);
                    card.querySelector('.tile-check').innerHTML = layer.visible ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-regular fa-circle"></i>';
                    updateSelectedBadge();
                    return;
                }

                // Click image: activate layer and reset old tools
                const prevId = ProjectStore.getState().selection[0];
                if (prevId !== layer.id) {
                    resetImageLevelToolsUI();
                    ProjectStore.selectLayer(layer.id);
                }
                document.querySelectorAll('.tile-card').forEach(c => c.classList.remove('active-tile'));
                card.classList.add('active-tile');
            });

            DOM.tileGrid.appendChild(card);
        });

        updateSelectedBadge();
    }

    function updateSelectedBadge() {
        const state = ProjectStore.getState();
        const visibleCount = state.layers.filter(l => l.visible).length;
        DOM.selectedCountBadge.textContent = `${visibleCount} / ${state.layers.length} selected`;
    }

    // ==========================================
    // 3. Manage Layer List & Color Sliders (Canvas Studio)
    // ==========================================
    function renderLayersList() {
        DOM.layersListContainer.innerHTML = '';
        const state = ProjectStore.getState();
        const sortedLayers = [...state.layers].sort((a, b) => b.zIndex - a.zIndex); // Display top layer first

        if (sortedLayers.length === 0) {
            DOM.layersListContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-regular fa-images"></i>
                    <p>No layers yet. Please select images in the Image Source tab.</p>
                </div>
            `;
            return;
        }

        const selectedId = state.selection[0];

        sortedLayers.forEach(layer => {
            const item = document.createElement('div');
            item.className = `layer-item ${layer.id === selectedId ? 'active' : ''}`;
            const thumbUrl = `/api/thumbnail?path=${encodeURIComponent(layer.sourcePath)}`;

            item.innerHTML = `
                <img src="${thumbUrl}" class="layer-item-thumb" alt="${layer.sourceId}">
                <span class="layer-item-name" title="${layer.sourceId}">${layer.sourceId}</span>
                <div class="layer-item-icons">
                    <i class="fa-solid ${layer.visible ? 'fa-eye' : 'fa-eye-slash'}" title="Toggle Visibility" data-action="toggle-visible"></i>
                    <i class="fa-solid ${layer.locked ? 'fa-lock' : 'fa-lock-open'}" title="Lock" data-action="toggle-lock"></i>
                </div>
            `;

            item.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                if (action === 'toggle-visible') {
                    e.stopPropagation();
                    ProjectStore.updateLayerProperties(layer.id, { visible: !layer.visible });
                } else if (action === 'toggle-lock') {
                    e.stopPropagation();
                    ProjectStore.updateLayerProperties(layer.id, { locked: !layer.locked });
                } else {
                    const prevId = ProjectStore.getState().selection[0];
                    if (prevId !== layer.id) {
                        resetImageLevelToolsUI();
                    }
                    ProjectStore.selectLayer(layer.id);
                }
            });

            DOM.layersListContainer.appendChild(item);
        });

        updateAdjustmentsCard();
    }

    function updateAdjustmentsCard() {
        const selected = ProjectStore.getSelectedLayer();
        if (!selected) {
            DOM.adjustLayerName.textContent = 'No layer selected';
            DOM.sliderOpacity.disabled = true;
            DOM.sliderBrightness.disabled = true;
            DOM.sliderContrast.disabled = true;
            DOM.sliderSaturation.disabled = true;
            return;
        }

        DOM.adjustLayerName.textContent = selected.sourceId;
        DOM.sliderOpacity.disabled = false;
        DOM.sliderBrightness.disabled = false;
        DOM.sliderContrast.disabled = false;
        DOM.sliderSaturation.disabled = false;

        DOM.sliderOpacity.value = selected.opacity;
        DOM.valOpacity.textContent = Math.round(selected.opacity * 100) + '%';

        DOM.sliderBrightness.value = selected.brightness;
        DOM.valBrightness.textContent = Math.round(selected.brightness * 100) + '%';

        DOM.sliderContrast.value = selected.contrast;
        DOM.valContrast.textContent = Math.round(selected.contrast * 100) + '%';

        DOM.sliderSaturation.value = selected.saturation;
        DOM.valSaturation.textContent = Math.round(selected.saturation * 100) + '%';
    }

    function initAdjustmentListeners() {
        const bindSliderTransaction = (slider, label, property, valueLabel) => {
            const begin = () => ProjectStore.beginTransaction(label, 'layer_adjust');
            slider.addEventListener('pointerdown', begin);
            slider.addEventListener('keydown', begin);
            slider.addEventListener('input', (e) => {
                const sel = ProjectStore.getSelectedLayer();
                if (!sel) return;
                if (!ProjectStore.activeTransaction) begin();
                const val = parseFloat(e.target.value);
                sel[property] = val;
                valueLabel.textContent = Math.round(val * 100) + '%';
                CanvasEngine.requestRender();
            });
            slider.addEventListener('change', () => ProjectStore.commitTransaction(label));
            slider.addEventListener('blur', () => ProjectStore.commitTransaction(label));
        };

        bindSliderTransaction(DOM.sliderOpacity, 'Change Opacity', 'opacity', DOM.valOpacity);
        bindSliderTransaction(DOM.sliderBrightness, 'Change Brightness', 'brightness', DOM.valBrightness);
        bindSliderTransaction(DOM.sliderContrast, 'Change Contrast', 'contrast', DOM.valContrast);
        bindSliderTransaction(DOM.sliderSaturation, 'Change Saturation', 'saturation', DOM.valSaturation);
        DOM.btnResetAdjustments.addEventListener('click', () => {
            const sel = ProjectStore.getSelectedLayer();
            if (sel) {
                ProjectStore.updateLayerProperties(sel.id, {
                    opacity: 1.0,
                    brightness: 1.0,
                    contrast: 1.0,
                    saturation: 1.0
                });
                updateAdjustmentsCard();
            }
        });

        DOM.btnLayerUp.addEventListener('click', () => {
            const sel = ProjectStore.getSelectedLayer();
            if (sel) ProjectStore.bringForward(sel.id);
        });

        DOM.btnLayerDown.addEventListener('click', () => {
            const sel = ProjectStore.getSelectedLayer();
            if (sel) ProjectStore.sendBackward(sel.id);
        });

        DOM.btnLayerLock.addEventListener('click', () => {
            const sel = ProjectStore.getSelectedLayer();
            if (sel) ProjectStore.updateLayerProperties(sel.id, { locked: !sel.locked });
        });
    }

    // ==========================================
    // 3b. Clarity Inspector Controller
    // ==========================================
    function setAccordionSection(sectionKey, expandState) {
        if (!DOM.accordionCards) return;
        DOM.accordionCards.forEach(card => {
            const key = card.dataset.accordionCard;
            if (key === sectionKey) {
                const shouldExpand = (typeof expandState === 'boolean') ? expandState : !card.classList.contains('expanded');
                card.classList.toggle('expanded', shouldExpand);
            } else {
                card.classList.remove('expanded');
            }
        });
    }

    function updateAccordionSummaries() {
        if (DOM.badgeClaritySummary) {
            const tool = inspectorState.currentTool;
            let shapeName = 'Rectangle';
            if (tool === 'polygon') shapeName = 'Polygon';
            else if (tool === 'lasso') shapeName = 'Lasso';
            const size = inspectorState.worldSize || 256;
            DOM.badgeClaritySummary.textContent = `${shapeName} · ${size}px`;
        }
        if (DOM.badgeBrushSummary && DOM.valBrushRadius) {
            const isRestore = inspectorState.currentTool === 'brush_restore';
            DOM.badgeBrushSummary.textContent = `${isRestore ? '🟢 Restore' : '🔴 Erase'} · ${DOM.valBrushRadius.textContent.trim()}`;
        }
        if (DOM.badgeCropSummary) {
            const tool = inspectorState.currentTool;
            let cropMode = 'Rectangle';
            if (tool === 'crop_polygon') cropMode = 'Polygon';
            else if (tool === 'crop_lasso') cropMode = 'Lasso';
            const state = ProjectStore.getState ? ProjectStore.getState() : {};
            const hasCrop = Boolean(state.cropDraft || state.cropRegion);
            DOM.badgeCropSummary.textContent = hasCrop ? `${cropMode} (Cropped)` : cropMode;
        }
    }

    function selectDrawingTool(toolName) {
        if (inspectorState.currentTool !== toolName) clearOsdDrawingDraft();
        inspectorState.currentTool = toolName || 'rect';
        CanvasEngine.setToolMode(toolName);

        // Update pill buttons UI
        if (DOM.drawingToolPills) {
            DOM.drawingToolPills.forEach(pill => {
                if (pill.dataset.tool === toolName) {
                    pill.classList.add('active');
                } else {
                    pill.classList.remove('active');
                }
            });
        }

        // Accordion Management: Automatically open section of selected tool
        const isBrush = (toolName === 'brush_exclude' || toolName === 'brush_restore');
        const isRect = (toolName === 'rect');
        const isClarity = (toolName === 'rect' || toolName === 'polygon' || toolName === 'lasso');
        const isCrop = Boolean(toolName && toolName.startsWith('crop'));
        const isSelect = (toolName === 'select');

        if (isSelect) {
            setAccordionSection(null, false);
            if (DOM.cardSelectMode) DOM.cardSelectMode.classList.add('is-active');
            if (DOM.btnToolSelectMode) DOM.btnToolSelectMode.classList.add('active');
        } else if (isClarity) {
            setAccordionSection('clarity', true);
            if (DOM.cardSelectMode) DOM.cardSelectMode.classList.remove('is-active');
            if (DOM.btnToolSelectMode) DOM.btnToolSelectMode.classList.remove('active');
        } else if (isBrush) {
            setAccordionSection('brush', true);
            if (DOM.cardSelectMode) DOM.cardSelectMode.classList.remove('is-active');
            if (DOM.btnToolSelectMode) DOM.btnToolSelectMode.classList.remove('active');
        } else if (isCrop) {
            setAccordionSection('crop', true);
            if (DOM.cardSelectMode) DOM.cardSelectMode.classList.remove('is-active');
            if (DOM.btnToolSelectMode) DOM.btnToolSelectMode.classList.remove('active');
        }

        updateAccordionSummaries();

        setOsdInteractionMode(isSelect ? 'navigate' : (isCrop ? 'crop' : (isBrush ? 'brush' : 'inspect')));

        if (DOM.brushControlsGroup) DOM.brushControlsGroup.style.display = isBrush ? 'block' : 'none';
        if (DOM.rectPresetGroup) DOM.rectPresetGroup.style.display = isRect ? 'block' : 'none';
        if (DOM.cropControlsGroup) DOM.cropControlsGroup.style.display = isCrop ? 'block' : 'none';

        if (toolName === 'polygon') {
            DOM.inspectorStatusText.textContent = '⬡ Click points to form polygon vertices, click first point to close';
            setStatus('ready', 'Polygon Mode: Click vertices on image to enclose region');
        } else if (toolName === 'lasso') {
            DOM.inspectorStatusText.textContent = '✏️ Hold and drag mouse to draw freehand contour';
            setStatus('ready', 'Lasso Mode: Hold and draw freehand around target area');
        } else if (toolName === 'brush_exclude') {
            DOM.inspectorStatusText.textContent = '🔴 Paint to erase artifacts to transparent alpha (Alpha = 0)';
            setStatus('ready', 'Erase Brush: Paint over regions to exclude from composite');
        } else if (toolName === 'brush_restore') {
            DOM.inspectorStatusText.textContent = '🟢 Paint to restore previously erased regions';
            setStatus('ready', 'Restore Brush: Paint over regions to restore');
        } else if (isCrop) {
            DOM.inspectorStatusText.textContent = '✂️ Drag to select crop bounding box, then click Apply Crop';
            setStatus('ready', 'Crop Tool: Define bounding box to trim mosaic');
        } else if (toolName === 'select') {
            DOM.inspectorStatusText.textContent = '↖️ Click layer on canvas to transform, rotate, or adjust color';
            setStatus('ready', 'Select & Transform Mode: Click layer on canvas to fine-tune');
        } else {
            DOM.inspectorStatusText.textContent = '🔲 Drag on image to define rectangular inspection box';
            setStatus('ready', 'Rectangle Mode: Drag to inspect region');
        }

        requestAnimationFrame(() => {
            CanvasEngine.resize();
            CanvasEngine.requestRender();
        });
    }

    function toggleInspectMode(forceState) {
        inspectorState.isEnabled = (typeof forceState === 'boolean') ? forceState : !inspectorState.isEnabled;
        CanvasEngine.isInspectMode = inspectorState.isEnabled;

        if (inspectorState.isEnabled) {
            DOM.btnToggleInspectMode.classList.add('active');
            DOM.inspectModeToggleText.innerHTML = 'Clarity Inspector: <b style="color:#38bdf8">ON</b>';
            DOM.rightInspectorPanel.classList.remove('closed');
            DOM.rightInspectorPanel.classList.add('open-mobile');
            if (DOM.inspectorBackdrop) DOM.inspectorBackdrop.classList.add('active');
            DOM.manualCanvasContainer.classList.add('inspect-active');
            selectDrawingTool(inspectorState.currentTool || 'rect');

            requestAnimationFrame(() => {
                CanvasEngine.resize();
                CanvasEngine.requestRender();
                if (uiState.osdViewer && uiState.osdViewer.viewport) {
                    uiState.osdViewer.viewport.resize();
                    if (uiState.osdViewer.navigator) {
                        uiState.osdViewer.navigator.update();
                    }
                    resizeOsdDrawingCanvas();
                    updateActiveRegionBoxScreenPosition();
                }
            });
        } else {
            DOM.btnToggleInspectMode.classList.remove('active');
            DOM.inspectModeToggleText.innerHTML = 'Clarity Inspector: <b>OFF</b>';
            DOM.rightInspectorPanel.classList.add('closed');
            DOM.rightInspectorPanel.classList.remove('open-mobile');
            if (DOM.inspectorBackdrop) DOM.inspectorBackdrop.classList.remove('active');
            DOM.manualCanvasContainer.classList.remove('inspect-active');
            CanvasEngine.setToolMode('select');
            setOsdInteractionMode('navigate');
            unpinInspector();
            requestAnimationFrame(() => {
                if (uiState.osdViewer && uiState.osdViewer.viewport) {
                    uiState.osdViewer.viewport.resize();
                    if (uiState.osdViewer.navigator) {
                        uiState.osdViewer.navigator.update();
                    }
                    resizeOsdDrawingCanvas();
                    updateActiveRegionBoxScreenPosition();
                }
            });
        }
    }

    function unpinInspector() {
        inspectorState.isPinned = false;
        inspectorState.currentRegion = null;
        inspectorState.currentWorldRect = null;
        DOM.inspectorPinBar.style.display = 'none';
        CanvasEngine.inspectorReticle = null;
        CanvasEngine.requestRender();
        updateActiveRegionBoxScreenPosition();
        renderOsdDrawingDraft();
    }

    function initViewportSelectionOverlay() {
        if (!DOM.viewportSelectionOverlay) return;
        DOM.viewportSelectionOverlay.style.display = 'none';
        if (DOM.btnCloseRegionBox) {
            DOM.btnCloseRegionBox.addEventListener('click', (e) => {
                e.stopPropagation();
                unpinInspector();
            });
        }
    }

    function outputPixelToWorld(point) {
        return MatrixUtils.transformPoint(uiState.outputPixelToWorld || MatrixUtils.identity(), point[0], point[1]);
    }

    function worldToOutputPixel(point) {
        return MatrixUtils.transformPoint(uiState.worldToOutputPixel || MatrixUtils.identity(), point[0], point[1]);
    }

    function osdScreenToWorld(screenPoint) {
        if (!uiState.osdViewer || !uiState.osdViewer.viewport) return null;
        const viewportPoint = uiState.osdViewer.viewport.pointFromPixel(new OpenSeadragon.Point(screenPoint[0], screenPoint[1]), true);
        const imagePoint = uiState.osdViewer.viewport.viewportToImageCoordinates(viewportPoint);
        return outputPixelToWorld([imagePoint.x, imagePoint.y]);
    }

    function osdWorldToScreen(worldPoint) {
        if (!uiState.osdViewer || !uiState.osdViewer.viewport) return null;
        const output = worldToOutputPixel(worldPoint);
        const viewportPoint = uiState.osdViewer.viewport.imageToViewportCoordinates(output[0], output[1]);
        const pixel = uiState.osdViewer.viewport.pixelFromPoint(viewportPoint, true);
        return [pixel.x, pixel.y];
    }

    function resizeOsdDrawingCanvas() {
        const canvas = DOM.osdDrawingCanvas;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(1, Math.round(rect.width * dpr));
        const height = Math.max(1, Math.round(rect.height * dpr));
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        renderOsdDrawingDraft();
    }

    function renderOsdDrawingDraft() {
        const canvas = DOM.osdDrawingCanvas;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const state = ProjectStore.getState();

        // 0. Draw Applied Focus Regions directly on canvas (sharp slice overlay)
        if (state.focusRegions && state.focusRegions.length > 0) {
            state.focusRegions.forEach(fr => {
                const pts = (fr.pointsWorld || []).map(osdWorldToScreen).filter(Boolean);
                if (pts.length < 3) return;

                const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
                const minX = Math.min(...xs), minY = Math.min(...ys);
                const maxX = Math.max(...xs), maxY = Math.max(...ys);
                const w = maxX - minX, h = maxY - minY;
                if (w <= 0 || h <= 0) return;

                ctx.save();
                ctx.beginPath();
                ctx.moveTo(pts[0][0], pts[0][1]);
                for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
                ctx.closePath();

                // Render cached sharp patch image if available
                if (fr._cachedImg && fr._cachedImg.complete && fr._cachedImg.naturalWidth > 0) {
                    ctx.save();
                    ctx.clip();
                    ctx.drawImage(fr._cachedImg, minX, minY, w, h);
                    ctx.restore();
                } else if (fr.imageDataUrl && !fr._loadingImg) {
                    fr._loadingImg = true;
                    const img = new Image();
                    img.onload = () => {
                        fr._cachedImg = img;
                        fr._loadingImg = false;
                        renderOsdDrawingDraft();
                    };
                    img.onerror = () => { fr._loadingImg = false; };
                    img.src = fr.imageDataUrl;
                } else if (fr.selectedLayerId && !fr._loadingImg) {
                    fr._loadingImg = true;
                    const layer = state.layers ? state.layers.find(l => l.id === fr.selectedLayerId) : null;
                    if (layer && layer.sourcePath) {
                        const img = new Image();
                        img.onload = () => {
                            fr._cachedImg = img;
                            fr._loadingImg = false;
                            renderOsdDrawingDraft();
                        };
                        img.onerror = () => { fr._loadingImg = false; };
                        img.src = `/api/thumbnail?path=${encodeURIComponent(layer.sourcePath)}&size=512`;
                    }
                }

                // Vibrant green neon border highlighting the applied sharp slice
                ctx.beginPath();
                ctx.moveTo(pts[0][0], pts[0][1]);
                for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
                ctx.closePath();
                const isJustApplied = (inspectorState.justAppliedRegionId === fr.id);
                ctx.strokeStyle = isJustApplied ? '#34d399' : '#10b981';
                ctx.lineWidth = isJustApplied ? 3.5 : 2;
                ctx.shadowColor = '#10b981';
                ctx.shadowBlur = isJustApplied ? 16 : 6;
                ctx.stroke();

                // Applied badge label on top of region
                const layer = state.layers ? state.layers.find(l => l.id === fr.selectedLayerId) : null;
                const name = layer ? layer.sourceId : 'Applied Slice';
                const label = `⭐ ${name.length > 18 ? name.substring(0, 16) + '...' : name}`;
                ctx.font = 'bold 11px Inter, sans-serif';
                const tw = ctx.measureText(label).width;
                ctx.fillStyle = isJustApplied ? 'rgba(52, 211, 153, 0.95)' : 'rgba(16, 185, 129, 0.9)';
                ctx.shadowBlur = 0;
                ctx.fillRect(minX, Math.max(0, minY - 20), tw + 14, 18);
                ctx.fillStyle = '#ffffff';
                ctx.fillText(label, minX + 6, Math.max(13, minY - 6));

                ctx.restore();
            });
        }

        // 1. Draw persistent mask regions on OpenSeadragon
        if (state.maskRegions && state.maskRegions.length > 0) {
            state.maskRegions.forEach(mask => {
                const points = (mask.pointsWorld || []).map(osdWorldToScreen).filter(Boolean);
                if (!points.length) return;
                const isRestore = (mask.operation === 'restore');
                
                // Calculate screen brush radius according to current zoom
                const center = points[0];
                const edgeWorld = [mask.pointsWorld[0][0] + (mask.radiusWorld || 20), mask.pointsWorld[0][1]];
                const edgeScreen = osdWorldToScreen(edgeWorld);
                const rScreen = edgeScreen ? Math.max(2, Math.hypot(edgeScreen[0] - center[0], edgeScreen[1] - center[1])) : (mask.radiusWorld || 20);

                ctx.save();
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.lineWidth = rScreen * 2;
                ctx.strokeStyle = isRestore ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)';
                ctx.fillStyle = isRestore ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)';

                if (points.length === 1) {
                    ctx.beginPath();
                    ctx.arc(points[0][0], points[0][1], rScreen, 0, Math.PI * 2);
                    ctx.fill();
                } else {
                    ctx.beginPath();
                    ctx.moveTo(points[0][0], points[0][1]);
                    for (let i = 1; i < points.length; i++) {
                        ctx.lineTo(points[i][0], points[i][1]);
                    }
                    ctx.stroke();
                }
                ctx.restore();
            });
        }

        // 2. Draw crop region with dimmed outer overlay on OpenSeadragon
        const activeCrop = state.cropRegion;
        if (activeCrop && activeCrop.pointsWorld && activeCrop.pointsWorld.length >= 3) {
            const screenPts = activeCrop.pointsWorld.map(osdWorldToScreen).filter(Boolean);
            if (screenPts.length >= 3) {
                const xs = screenPts.map(p => p[0]);
                const ys = screenPts.map(p => p[1]);
                const cMinX = Math.min(...xs), cMinY = Math.min(...ys);
                const cMaxX = Math.max(...xs), cMaxY = Math.max(...ys);
                const cW = cMaxX - cMinX, cH = cMaxY - cMinY;
                const vw = canvas.width / dpr, vh = canvas.height / dpr;

                ctx.save();
                // Dim all 4 corners outside crop region
                ctx.fillStyle = 'rgba(0, 0, 0, 0.55)';
                ctx.fillRect(0, 0, vw, Math.max(0, cMinY));
                ctx.fillRect(0, Math.min(vh, cMaxY), vw, Math.max(0, vh - cMaxY));
                ctx.fillRect(0, Math.max(0, cMinY), Math.max(0, cMinX), Math.max(0, cH));
                ctx.fillRect(Math.min(vw, cMaxX), Math.max(0, cMinY), Math.max(0, vw - cMaxX), Math.max(0, cH));

                // Amber bounding border
                ctx.strokeStyle = '#f59e0b';
                ctx.lineWidth = 2.5;
                ctx.setLineDash([8, 5]);
                ctx.strokeRect(cMinX, cMinY, cW, cH);

                // Dimension badge at corner of crop box
                const labelText = `✂️ Crop Box: ${Math.round(cW)} × ${Math.round(cH)} px`;
                ctx.font = '600 12px Inter, sans-serif';
                const textW = ctx.measureText(labelText).width;
                ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
                ctx.fillRect(cMinX, Math.max(0, cMinY - 24), textW + 14, 22);
                ctx.fillStyle = '#fbbf24';
                ctx.fillText(labelText, cMinX + 7, Math.max(16, cMinY - 8));
                ctx.restore();
            }
        }

        // 2b. Draw pinned inspected region (Polygon / Lasso)
        if (inspectorState.isPinned && inspectorState.currentRegion) {
            const curReg = inspectorState.currentRegion;
            const isPoly = (curReg.shapeType === 'polygon' || curReg.shapeType === 'lasso' || curReg.shapeType === 'crop_polygon' || curReg.shapeType === 'crop_lasso');
            if (!curReg.selectedLayerId && isPoly && curReg.pointsWorld && curReg.pointsWorld.length >= 3) {
                const polyPts = curReg.pointsWorld.map(osdWorldToScreen).filter(Boolean);
                if (polyPts.length >= 3) {
                    const isCropTool = Boolean(curReg.shapeType && curReg.shapeType.startsWith('crop'));
                    const polyColor = isCropTool ? '#f59e0b' : '#22d3ee';
                    ctx.save();
                    ctx.strokeStyle = polyColor;
                    ctx.fillStyle = isCropTool ? 'rgba(245, 158, 11, 0.22)' : 'rgba(34, 211, 238, 0.20)';
                    ctx.lineWidth = 2.5;
                    ctx.lineJoin = 'round';
                    ctx.setLineDash([6, 4]);
                    ctx.beginPath();
                    ctx.moveTo(polyPts[0][0], polyPts[0][1]);
                    for (let i = 1; i < polyPts.length; i++) {
                        ctx.lineTo(polyPts[i][0], polyPts[i][1]);
                    }
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();

                    // Draw vertices for polygon
                    if (curReg.shapeType.includes('polygon')) {
                        polyPts.forEach((pt, idx) => {
                            ctx.beginPath();
                            ctx.arc(pt[0], pt[1], idx === 0 ? 5.5 : 4, 0, Math.PI * 2);
                            ctx.fillStyle = idx === 0 ? '#ec4899' : polyColor;
                            ctx.fill();
                        });
                    }
                    ctx.restore();
                }
            }
        }

        // 3. Draw interactive drawing draft
        const points = osdDrawState.pointsWorld.map(osdWorldToScreen).filter(Boolean);
        const current = osdDrawState.currentWorld ? osdWorldToScreen(osdDrawState.currentWorld) : null;
        if (points.length === 0) return;
        const isCrop = inspectorState.currentTool && inspectorState.currentTool.startsWith('crop');
        const color = isCrop ? '#f59e0b' : (inspectorState.currentTool.startsWith('brush') ? '#ef4444' : '#22d3ee');
        ctx.save();
        ctx.strokeStyle = color;
        ctx.fillStyle = isCrop ? 'rgba(245,158,11,0.18)' : 'rgba(34,211,238,0.16)';
        ctx.lineWidth = inspectorState.currentTool.startsWith('brush') ? Math.max(2, CanvasEngine.brushRadius * 2) : 2;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.setLineDash(inspectorState.currentTool.startsWith('brush') ? [] : [6, 4]);
        ctx.beginPath();
        if ((inspectorState.currentTool === 'rect' || inspectorState.currentTool === 'crop') && current) {
            ctx.rect(points[0][0], points[0][1], current[0] - points[0][0], current[1] - points[0][1]);
            ctx.fill();
            ctx.stroke();
        } else {
            ctx.moveTo(points[0][0], points[0][1]);
            points.slice(1).forEach(point => ctx.lineTo(point[0], point[1]));
            if (current && inspectorState.currentTool.includes('polygon')) ctx.lineTo(current[0], current[1]);
            if (inspectorState.currentTool.includes('lasso')) ctx.closePath();
            if (inspectorState.currentTool.includes('lasso')) ctx.fill();
            ctx.stroke();
            if (inspectorState.currentTool.includes('polygon')) {
                points.forEach((point, index) => {
                    ctx.beginPath();
                    ctx.arc(point[0], point[1], index === 0 ? 6 : 4, 0, Math.PI * 2);
                    ctx.fillStyle = index === 0 ? '#ec4899' : color;
                    ctx.fill();
                });
            }
        }
        ctx.restore();
    }

    function clearOsdDrawingDraft() {
        osdDrawState.drawing = false;
        osdDrawState.pointsWorld = [];
        osdDrawState.currentWorld = null;
        osdDrawState.pointerId = null;
        osdDrawState.panning = false;
        osdDrawState.lastScreen = null;
        renderOsdDrawingDraft();
    }

    function commitOsdShape(shapeType, pointsWorld) {
        if (!pointsWorld || pointsWorld.length < 3) return;
        const xs = pointsWorld.map(point => point[0]);
        const ys = pointsWorld.map(point => point[1]);
        handleRegionSelected({
            shapeType,
            pointsWorld,
            boundingRect: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]
        });
    }

    function finishOsdPointerGesture() {
        const tool = inspectorState.currentTool;
        const points = osdDrawState.pointsWorld;
        const current = osdDrawState.currentWorld;
        if ((tool === 'rect' || tool === 'crop') && points[0] && current) {
            const minX = Math.min(points[0][0], current[0]), minY = Math.min(points[0][1], current[1]);
            const maxX = Math.max(points[0][0], current[0]), maxY = Math.max(points[0][1], current[1]);
            if (maxX - minX > 1 && maxY - minY > 1) {
                commitOsdShape(tool === 'crop' ? 'crop' : 'rectangle', [[minX, minY], [maxX, minY], [maxX, maxY], [minX, maxY]]);
            }
            clearOsdDrawingDraft();
        } else if ((tool === 'lasso' || tool === 'crop_lasso') && points.length >= 3) {
            const simplified = points.filter((point, index) => index === 0 || index === points.length - 1 || index % 2 === 0).slice(0, 2000);
            commitOsdShape(tool === 'crop_lasso' ? 'crop_lasso' : 'lasso', simplified);
            clearOsdDrawingDraft();
        } else if (tool === 'brush_exclude' || tool === 'brush_restore') {
            if (points.length > 0) {
                const center = osdWorldToScreen(points[0]);
                const edgeWorld = center ? osdScreenToWorld([center[0] + CanvasEngine.brushRadius, center[1]]) : null;
                const radiusWorld = edgeWorld ? Math.hypot(edgeWorld[0] - points[0][0], edgeWorld[1] - points[0][1]) : CanvasEngine.brushRadius;
                ProjectStore.addMaskRegion({ shapeType: 'brush', pointsWorld: points.slice(0, 4000), radiusWorld, operation: tool === 'brush_restore' ? 'restore' : 'exclude' });
            }
            clearOsdDrawingDraft();
        }
    }

    function initOsdDrawingCanvas() {
        const canvas = DOM.osdDrawingCanvas;
        if (!canvas) return;
        const eventPoint = event => {
            const rect = canvas.getBoundingClientRect();
            return [event.clientX - rect.left, event.clientY - rect.top];
        };
        canvas.addEventListener('pointerdown', event => {
            if ((event.button === 1 || uiState.spacePressed) && uiState.osdViewer) {
                osdDrawState.panning = true;
                osdDrawState.pointerId = event.pointerId;
                osdDrawState.lastScreen = eventPoint(event);
                canvas.setPointerCapture(event.pointerId);
                return;
            }
            if (event.button !== 0 || uiState.osdInteractionMode === 'navigate') return;
            const world = osdScreenToWorld(eventPoint(event));
            if (!world) return;
            const tool = inspectorState.currentTool;
            if (tool === 'polygon' || tool === 'crop_polygon') {
                if (osdDrawState.pointsWorld.length >= 3) {
                    const firstScreen = osdWorldToScreen(osdDrawState.pointsWorld[0]);
                    const point = eventPoint(event);
                    if (firstScreen && Math.hypot(point[0] - firstScreen[0], point[1] - firstScreen[1]) <= 24) {
                        commitOsdShape(tool === 'crop_polygon' ? 'crop_polygon' : 'polygon', osdDrawState.pointsWorld);
                        clearOsdDrawingDraft();
                        return;
                    }
                }
                osdDrawState.pointsWorld.push(world);
                osdDrawState.currentWorld = world;
                renderOsdDrawingDraft();
                return;
            }
            osdDrawState.drawing = true;
            osdDrawState.pointerId = event.pointerId;
            osdDrawState.pointsWorld = [world];
            osdDrawState.currentWorld = world;
            canvas.setPointerCapture(event.pointerId);
            renderOsdDrawingDraft();
        });
        canvas.addEventListener('pointermove', event => {
            if (osdDrawState.panning && event.pointerId === osdDrawState.pointerId && uiState.osdViewer) {
                const current = eventPoint(event);
                const previousViewport = uiState.osdViewer.viewport.pointFromPixel(new OpenSeadragon.Point(osdDrawState.lastScreen[0], osdDrawState.lastScreen[1]), true);
                const currentViewport = uiState.osdViewer.viewport.pointFromPixel(new OpenSeadragon.Point(current[0], current[1]), true);
                uiState.osdViewer.viewport.panBy(new OpenSeadragon.Point(previousViewport.x - currentViewport.x, previousViewport.y - currentViewport.y)).applyConstraints();
                osdDrawState.lastScreen = current;
                return;
            }
            const world = osdScreenToWorld(eventPoint(event));
            if (!world) return;
            osdDrawState.currentWorld = world;
            if (osdDrawState.drawing && (inspectorState.currentTool.includes('lasso') || inspectorState.currentTool.startsWith('brush'))) {
                const previous = osdDrawState.pointsWorld[osdDrawState.pointsWorld.length - 1];
                const previousScreen = osdWorldToScreen(previous);
                const currentScreen = eventPoint(event);
                if (!previousScreen || Math.hypot(currentScreen[0] - previousScreen[0], currentScreen[1] - previousScreen[1]) >= 3) osdDrawState.pointsWorld.push(world);
            }
            renderOsdDrawingDraft();
        });
        canvas.addEventListener('pointerup', event => {
            if (osdDrawState.panning && event.pointerId === osdDrawState.pointerId) {
                osdDrawState.panning = false;
                osdDrawState.pointerId = null;
                osdDrawState.lastScreen = null;
                return;
            }
            if (!osdDrawState.drawing || event.pointerId !== osdDrawState.pointerId) return;
            finishOsdPointerGesture();
        });
        const cancelOsdPointerGesture = () => {
            if (osdDrawState.drawing || osdDrawState.panning) clearOsdDrawingDraft();
        };
        canvas.addEventListener('pointercancel', cancelOsdPointerGesture);
        canvas.addEventListener('lostpointercapture', cancelOsdPointerGesture);
        canvas.addEventListener('dblclick', () => {
            const tool = inspectorState.currentTool;
            if ((tool === 'polygon' || tool === 'crop_polygon') && osdDrawState.pointsWorld.length >= 3) {
                commitOsdShape(tool === 'crop_polygon' ? 'crop_polygon' : 'polygon', osdDrawState.pointsWorld);
                clearOsdDrawingDraft();
            }
        });
        canvas.addEventListener('wheel', event => {
            if (!uiState.osdViewer || osdDrawState.drawing) return;
            event.preventDefault();
            const point = eventPoint(event);
            const anchor = uiState.osdViewer.viewport.pointFromPixel(new OpenSeadragon.Point(point[0], point[1]), true);
            uiState.osdViewer.viewport.zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15, anchor).applyConstraints();
        }, { passive: false });
        if (window.ResizeObserver) new ResizeObserver(resizeOsdDrawingCanvas).observe(canvas);
        resizeOsdDrawingCanvas();
    }

    function updateActiveRegionBoxScreenPosition() {
        if (!DOM.viewportSelectionOverlay || !DOM.activeRegionBox) return;
        const region = inspectorState.currentRegion;
        if (!inspectorState.isPinned || !region || !region.pointsWorld || region.pointsWorld.length < 3) {
            DOM.viewportSelectionOverlay.style.display = 'none';
            DOM.activeRegionBox.style.display = 'none';
            renderOsdDrawingDraft();
            return;
        }

        let screenPoints = [];
        let sourceElement = null;
        if (ProjectStore.getState().mode === 'auto' && uiState.osdViewer && uiState.osdViewer.viewport) {
            sourceElement = uiState.osdViewer.element || DOM.viewDeepZoom;
            screenPoints = region.pointsWorld.map(point => osdWorldToScreen(point)).filter(Boolean);
        } else if (CanvasEngine.canvas) {
            sourceElement = CanvasEngine.canvas;
            screenPoints = region.pointsWorld.map(point => CanvasEngine.worldToScreen(point[0], point[1])).filter(Boolean);
        }
        // 1. Must show overlay before measuring bounds to avoid 0x0 rect returning full window offset
        DOM.viewportSelectionOverlay.style.display = 'block';

        const overlayRect = DOM.viewportSelectionOverlay.getBoundingClientRect();
        const sourceRect = sourceElement.getBoundingClientRect();
        const offsetX = (overlayRect.width > 0) ? (sourceRect.left - overlayRect.left) : 0;
        const offsetY = (overlayRect.height > 0) ? (sourceRect.top - overlayRect.top) : 0;
        screenPoints = screenPoints.map(point => [point[0] + offsetX, point[1] + offsetY]);

        const xs = screenPoints.map(point => point[0]);
        const ys = screenPoints.map(point => point[1]);
        const minX = Math.min(...xs), minY = Math.min(...ys);
        const maxX = Math.max(...xs), maxY = Math.max(...ys);

        const isPoly = (region.shapeType === 'polygon' || region.shapeType === 'lasso' || region.shapeType === 'crop_polygon' || region.shapeType === 'crop_lasso');
        DOM.activeRegionBox.style.display = 'block';
        DOM.activeRegionBox.style.left = `${Math.round(minX)}px`;
        DOM.activeRegionBox.style.top = `${Math.round(minY)}px`;
        DOM.activeRegionBox.style.width = `${Math.max(1, Math.round(maxX - minX))}px`;
        DOM.activeRegionBox.style.height = `${Math.max(1, Math.round(maxY - minY))}px`;

        const handles = DOM.activeRegionBox.querySelectorAll('.region-handle');
        const state = ProjectStore.getState();
        const appliedLayer = region.selectedLayerId ? (state.layers ? state.layers.find(l => l.id === region.selectedLayerId) : null) : null;

        if (appliedLayer) {
            DOM.activeRegionBox.classList.add('is-applied');
            DOM.regionBoxTitle.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #34d399"></i> Đã gán: <b>${appliedLayer.sourceId}</b>`;
        } else {
            DOM.activeRegionBox.classList.remove('is-applied');
            if (isPoly) {
                DOM.regionBoxTitle.textContent = `⬡ ${region.shapeType.toUpperCase()}: ${Math.round(region.boundingRect[2])} × ${Math.round(region.boundingRect[3])} px`;
            } else {
                DOM.regionBoxTitle.textContent = `Inspected Region: ${Math.round(region.boundingRect[2])} × ${Math.round(region.boundingRect[3])} px`;
            }
        }

        if (isPoly) {
            DOM.activeRegionBox.classList.add('is-polygon-mode');
            handles.forEach(h => h.style.display = 'none');
        } else {
            DOM.activeRegionBox.classList.remove('is-polygon-mode');
            handles.forEach(h => h.style.display = 'block');
        }

        renderOsdDrawingDraft();
    }

    function handleRegionSelected(regionData) {
        let shapeType = 'rectangle';
        let pointsWorld = [];
        let boundingRect = [0, 0, 100, 100];

        if (Array.isArray(regionData)) {
            // Legacy [x, y, w, h]
            const [rx, ry, rw, rh] = regionData;
            shapeType = 'rectangle';
            pointsWorld = [
                [rx, ry],
                [rx + rw, ry],
                [rx + rw, ry + rh],
                [rx, ry + rh]
            ];
            boundingRect = [rx, ry, rw, rh];
        } else if (typeof regionData === 'object') {
            shapeType = regionData.shapeType || 'rectangle';
            pointsWorld = regionData.pointsWorld || [];
            boundingRect = regionData.boundingRect || [0, 0, 100, 100];
        }

        const [rx, ry, rw, rh] = boundingRect;
        inspectorState.currentRegion = { shapeType, pointsWorld, boundingRect };
        inspectorState.currentWorldRect = boundingRect;
        inspectorState.isPinned = true;
        updateActiveRegionBoxScreenPosition();

        if (inspectorState.currentTool && inspectorState.currentTool.startsWith('crop')) {
            const cropShape = shapeType.replace(/^crop_/, '') || 'rectangle';
            ProjectStore.setCropDraft({ shapeType: cropShape === 'crop' ? 'rectangle' : cropShape, pointsWorld });
            DOM.inspectorStatusText.textContent = `✂️ Set Crop Box [${Math.round(rw)}×${Math.round(rh)} px]. Click "Apply Crop" to finalize.`;
            setStatus('ready', `selected vùng Crop [${Math.round(rw)} × ${Math.round(rh)} px]`);
            CanvasEngine.requestRender();
            return;
        }

        DOM.inspectorPinBar.style.display = 'flex';
        DOM.inspectorPinCoords.innerHTML = `<i class="fa-solid fa-vector-square"></i> Region: ${Math.round(rw)}×${Math.round(rh)} px (${shapeType.toUpperCase()})`;
        DOM.inspectorStatusText.textContent = `📌 Region enclosed [${Math.round(rw)}×${Math.round(rh)} px]. Compare sharpness scores below and pick best slice`;

        // Tự động mở inspector panel nếu đang đóng
        DOM.rightInspectorPanel.classList.remove('closed');
        requestAnimationFrame(() => {
            if (uiState.osdViewer && uiState.osdViewer.viewport) {
                uiState.osdViewer.viewport.resize();
                if (uiState.osdViewer.navigator) {
                    uiState.osdViewer.navigator.update();
                }
                resizeOsdDrawingCanvas();
                updateActiveRegionBoxScreenPosition();
            }
        });

        triggerInspectorQuery(inspectorState.currentRegion);
    }

    function setInspectorSize(size) {
        inspectorState.worldSize = size;
        DOM.regionSizePills.forEach(btn => {
            if (parseInt(btn.dataset.size, 10) === size) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        updateAccordionSummaries();
        if (inspectorState.currentRegion) {
            const [x, y] = inspectorState.currentRegion.boundingRect;
            const newBox = [x, y, size, size];
            handleRegionSelected(newBox);
        }
    }

    function handleCanvasPointerInspectHover(worldPt) {
        if (!inspectorState.isEnabled || inspectorState.isPinned) return;
        // Hover mode
    }

    function handleCanvasPointerInspectClick(worldPt) {
        if (!inspectorState.isEnabled) return;
        const ws = inspectorState.worldSize || 256;
        const rx = worldPt[0] - ws / 2;
        const ry = worldPt[1] - ws / 2;
        handleRegionSelected([rx, ry, ws, ws]);
    }

    async function triggerInspectorQuery(regionData) {
        const state = ProjectStore.getState();
        if (!state.layers || state.layers.length === 0) return;

        // Display extraction status
        if (DOM.inspectorEmptyState) DOM.inspectorEmptyState.style.display = 'none';
        if (DOM.inspectorPatchesList) {
            DOM.inspectorPatchesList.style.display = 'flex';
            DOM.inspectorPatchesList.innerHTML = `
                <div class="inspector-loading">
                    <i class="fa-solid fa-spinner fa-spin text-cyan"></i>
                    <span>Extracting & computing sharpness scores...</span>
                </div>
            `;
        }

        inspectorState.requestGeneration++;
        const currentGen = inspectorState.requestGeneration;

        if (inspectorState.abortController) {
            inspectorState.abortController.abort();
        }
        inspectorState.abortController = new AbortController();

        try {
            const projId = encodeURIComponent(state.id || 'current_project');
            const res = await fetch(`/api/projects/${projId}/inspect`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: inspectorState.abortController.signal,
                body: JSON.stringify({
                    project: state,
                    shapeType: regionData.shapeType || 'rectangle',
                    pointsWorld: regionData.pointsWorld,
                    boundingRect: regionData.boundingRect,
                    outputSize: 256
                })
            });

            if (currentGen !== inspectorState.requestGeneration) return;

            const data = await res.json();
            if (data.status === 'success') {
                renderInspectorPatches(data);
            } else {
                if (DOM.inspectorEmptyState) {
                    DOM.inspectorEmptyState.style.display = 'block';
                    DOM.inspectorEmptyState.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-warning"></i><p>${data.error || 'Unable to extract clarity scores for this region'}</p>`;
                }
                if (DOM.inspectorPatchesList) DOM.inspectorPatchesList.style.display = 'none';
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.warn("Inspector error:", err);
                if (DOM.inspectorEmptyState) {
                    DOM.inspectorEmptyState.style.display = 'block';
                    DOM.inspectorEmptyState.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-danger"></i><p>Clarity inspector connection error: ${err.message}</p>`;
                }
                if (DOM.inspectorPatchesList) DOM.inspectorPatchesList.style.display = 'none';
            }
        }
    }

    // Lightbox state for detailed patch preview
    const lightboxState = {
        currentLayerId: null,
        zoom: 1,
        panX: 0,
        panY: 0,
        isDragging: false,
        startX: 0,
        startY: 0,
        patches: [],
        sharpestLayerId: null,
        currentBlobUrl: null,
        detailGeneration: 0
    };

    function renderInspectorPatches(data) {
        const patches = data.patches || [];
        inspectorState.lastPatches = patches;

        if (patches.length === 0) {
            DOM.inspectorEmptyState.style.display = 'block';
            DOM.inspectorEmptyState.innerHTML = `
                <i class="fa-solid fa-circle-question"></i>
                <p>Không có ảnh nào bao phủ vị trí này.<br>Hãy khoanh vùng vào phần có chứa mô tiêu bản.</p>
            `;
            DOM.inspectorPatchesList.style.display = 'none';
            return;
        }

        DOM.inspectorEmptyState.style.display = 'none';
        DOM.inspectorPatchesList.style.display = 'flex';
        DOM.inspectorPatchesList.innerHTML = '';

        const currentFocusRegion = inspectorState.currentRegion;
        const currentSelectedLayerId = currentFocusRegion ? currentFocusRegion.selectedLayerId : data.sharpestLayerId;

        patches.forEach((patch) => {
            const isSharpest = (patch.layerId === data.sharpestLayerId);
            const isApplied = (patch.layerId === currentSelectedLayerId);
            const card = document.createElement('div');
            card.className = `patch-card ${isSharpest ? 'sharpest' : ''} ${isApplied ? 'active-applied' : ''}`;

            card.innerHTML = `
                ${isSharpest ? '<div class="patch-card-badge"><i class="fa-solid fa-award"></i> SHARPEST</div>' : ''}
                <div class="patch-card-content" title="🔍 Click to view high-res preview & compare slices">
                    <div class="patch-card-thumb-wrap">
                        <img src="${patch.imageDataUrl}" class="patch-card-thumb" alt="${patch.sourceId}">
                        <div class="patch-thumb-zoom-hint"><i class="fa-solid fa-magnifying-glass-plus"></i></div>
                    </div>
                    <div class="patch-card-info">
                        <span class="patch-card-name" title="${patch.sourceId}">${patch.sourceId}</span>
                        <div class="patch-card-metric">
                            <span>Sharpness:</span>
                            <span class="metric-val ${isSharpest ? 'high' : ''}">${patch.sharpness.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                        </div>
                        <div class="patch-card-metric">
                            <span>Coverage:</span>
                            <span class="metric-val">${Math.round(patch.validCoverage * 100)}%</span>
                        </div>
                    </div>
                </div>
                <div class="patch-card-actions">
                    <button class="btn-preview-hd" data-layer-id="${patch.layerId}" title="Zoom in on this slice for detailed inspection">
                        <i class="fa-solid fa-magnifying-glass-plus"></i> HD Inspect
                    </button>
                    <button class="btn-apply-patch ${isApplied ? 'is-applied' : ''}" data-layer-id="${patch.layerId}" title="Apply this slice to region">
                        <i class="fa-solid ${isApplied ? 'fa-circle-check' : 'fa-check'}"></i> ${isApplied ? 'Applied' : 'Apply Slice'}
                    </button>
                </div>
            `;

            // 1. Click vào thumbnail hoặc nội dung card -> Unlock Lightbox so sánh chi tiết
            card.querySelector('.patch-card-content').addEventListener('click', () => {
                openPatchLightbox(patch.layerId, patches, data.sharpestLayerId);
            });

            // 2. Click vào nút "Soi Phóng To HD" -> Unlock Lightbox
            card.querySelector('.btn-preview-hd').addEventListener('click', (e) => {
                e.stopPropagation();
                openPatchLightbox(patch.layerId, patches, data.sharpestLayerId);
            });

            // 3. Click vào nút "Apply Slice"
            card.querySelector('.btn-apply-patch').addEventListener('click', (e) => {
                e.stopPropagation();
                applyPatchAsFocusRegion(patch.layerId);
            });

            DOM.inspectorPatchesList.appendChild(card);
        });
    }

    // ==========================================
    // 3d. Modal Soi Phóng To & So Sánh Ảnh Chi Tiết (Patch Clarity Lightbox)
    // ==========================================
    function initPatchLightboxEvents() {
        if (!DOM.patchPreviewModal) return;

        DOM.btnClosePatchModal.addEventListener('click', closePatchLightbox);
        DOM.patchPreviewModal.addEventListener('click', (e) => {
            if (e.target === DOM.patchPreviewModal) closePatchLightbox();
        });

        DOM.btnPatchZoomIn.addEventListener('click', () => adjustPatchZoom(0.25));
        DOM.btnPatchZoomOut.addEventListener('click', () => adjustPatchZoom(-0.25));
        DOM.btnPatchZoomReset.addEventListener('click', () => resetPatchZoom());

        DOM.btnPatchModalApply.addEventListener('click', () => {
            if (lightboxState.currentLayerId) {
                applyPatchAsFocusRegion(lightboxState.currentLayerId);
                closePatchLightbox();
            }
        });

        const wrapper = DOM.patchViewerWrapper;
        wrapper.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.15 : 0.15;
            adjustPatchZoom(delta);
        }, { passive: false });

        wrapper.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            lightboxState.isDragging = true;
            lightboxState.startX = e.clientX - lightboxState.panX;
            lightboxState.startY = e.clientY - lightboxState.panY;
        });

        window.addEventListener('mousemove', (e) => {
            if (!lightboxState.isDragging) return;
            lightboxState.panX = e.clientX - lightboxState.startX;
            lightboxState.panY = e.clientY - lightboxState.startY;
            updatePatchImageTransform();
        });

        window.addEventListener('mouseup', () => {
            lightboxState.isDragging = false;
        });
    }

    async function openPatchLightbox(selectedLayerId, patches, sharpestLayerId) {
        if (!DOM.patchPreviewModal) return;
        lightboxState.currentLayerId = selectedLayerId;
        lightboxState.patches = patches;
        lightboxState.sharpestLayerId = sharpestLayerId;
        resetPatchZoom();

        // Unlock modal ngay lập tức
        DOM.patchPreviewModal.style.display = 'flex';
        renderPatchModalDetail(selectedLayerId);
    }

    function closePatchLightbox() {
        lightboxState.detailGeneration++;
        lightboxState.currentLayerId = null;
        DOM.patchPreviewModal.style.display = 'none';
        lightboxState.isDragging = false;
        if (lightboxState.currentBlobUrl) {
            URL.revokeObjectURL(lightboxState.currentBlobUrl);
            lightboxState.currentBlobUrl = null;
        }
    }

    async function renderPatchModalDetail(layerId) {
        const detailGeneration = ++lightboxState.detailGeneration;
        lightboxState.currentLayerId = layerId;
        const patch = lightboxState.patches.find(p => p.layerId === layerId) || lightboxState.patches[0];
        if (!patch) return;

        const isSharpest = (patch.layerId === lightboxState.sharpestLayerId);
        DOM.patchModalTitle.textContent = `Region Details: ${patch.sourceId}`;
        DOM.patchModalBadge.style.display = isSharpest ? 'inline-flex' : 'none';

        // Tải patch độ phân giải gốc siêu nét từ API /patch
        if (lightboxState.currentBlobUrl) {
            URL.revokeObjectURL(lightboxState.currentBlobUrl);
            lightboxState.currentBlobUrl = null;
        }
        DOM.patchModalImage.src = patch.imageDataUrl; // placeholder ban đầu

        const state = ProjectStore.getState();
        const curRegion = inspectorState.currentRegion;

        if (curRegion && state.id) {
            try {
                const patchRes = await fetch(`/api/projects/${state.id}/patch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project: state,
                        layerId: layerId,
                        shapeType: curRegion.shapeType || 'rectangle',
                        pointsWorld: curRegion.pointsWorld,
                        maxPixels: 16777216
                    })
                });

                if (patchRes.ok && lightboxState.currentLayerId === layerId && detailGeneration === lightboxState.detailGeneration) {
                    const blob = await patchRes.blob();
                    if (lightboxState.currentLayerId !== layerId || detailGeneration !== lightboxState.detailGeneration) return;
                    if (lightboxState.currentBlobUrl) {
                        URL.revokeObjectURL(lightboxState.currentBlobUrl);
                    }
                    lightboxState.currentBlobUrl = URL.createObjectURL(blob);
                    DOM.patchModalImage.src = lightboxState.currentBlobUrl;

                    const pW = patchRes.headers.get('X-Patch-Width');
                    const pH = patchRes.headers.get('X-Patch-Height');
                    if (pW && pH) {
                        DOM.patchModalDimensions.textContent = `${pW} × ${pH} px (Native)`;
                    }
                }
            } catch (err) {
                console.warn("Native patch fetch error:", err);
            }
        }

        DOM.patchModalSharpness.textContent = patch.sharpness.toLocaleString();
        DOM.patchModalCoverage.textContent = `${Math.round(patch.validCoverage * 100)}%`;

        // Render danh sách các ảnh cùng vùng để so sánh
        DOM.patchModalCompareList.innerHTML = '';
        lightboxState.patches.forEach(p => {
            const isSelected = (p.layerId === layerId);
            const isSharp = (p.layerId === lightboxState.sharpestLayerId);
            const item = document.createElement('div');
            item.className = `patch-compare-item ${isSelected ? 'active' : ''}`;
            item.innerHTML = `
                <img src="${p.imageDataUrl}" class="patch-compare-thumb" alt="${p.sourceId}">
                <div class="patch-compare-info">
                    <span class="patch-compare-name">${p.sourceId}</span>
                    <span class="patch-compare-sub">Sharpness: <b>${p.sharpness.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b> ${isSharp ? '⭐' : ''}</span>
                </div>
            `;
            item.addEventListener('click', () => {
                renderPatchModalDetail(p.layerId);
            });
            DOM.patchModalCompareList.appendChild(item);
        });
    }

    function adjustPatchZoom(delta) {
        lightboxState.zoom = Math.max(0.5, Math.min(8.0, lightboxState.zoom + delta));
        updatePatchImageTransform();
    }

    function resetPatchZoom() {
        lightboxState.zoom = 1.0;
        lightboxState.panX = 0;
        lightboxState.panY = 0;
        updatePatchImageTransform();
    }

    function updatePatchImageTransform() {
        DOM.patchModalImage.style.transform = `translate(${lightboxState.panX}px, ${lightboxState.panY}px) scale(${lightboxState.zoom})`;
    }

    function applyPatchAsFocusRegion(layerId) {
        if (!inspectorState.currentRegion) return;
        const allPatches = [...(inspectorState.lastPatches || []), ...(lightboxState.patches || [])];
        const targetPatch = allPatches.find(p => p.layerId === layerId);
        const patchDataUrl = targetPatch ? targetPatch.imageDataUrl : null;
        const regionWithImage = {
            ...inspectorState.currentRegion,
            imageDataUrl: patchDataUrl
        };

        const newRegion = ProjectStore.setFocusRegion(
            regionWithImage,
            layerId,
            8
        );
        if (newRegion && patchDataUrl) {
            newRegion.imageDataUrl = patchDataUrl;
            const img = new Image();
            img.onload = () => {
                newRegion._cachedImg = img;
                renderOsdDrawingDraft();
            };
            img.src = patchDataUrl;
        }

        if (inspectorState.currentRegion) {
            inspectorState.currentRegion.selectedLayerId = layerId;
            inspectorState.currentRegion.imageDataUrl = patchDataUrl;
        }

        const state = ProjectStore.getState();
        const layer = state.layers ? state.layers.find(l => l.id === layerId) : null;
        const layerName = layer ? layer.sourceId : layerId;

        // Immediate visual feedback & pulse animation
        if (newRegion) {
            inspectorState.justAppliedRegionId = newRegion.id;
            updateActiveRegionBoxScreenPosition();
            renderOsdDrawingDraft();
            setTimeout(() => {
                if (inspectorState.justAppliedRegionId === newRegion.id) {
                    inspectorState.justAppliedRegionId = null;
                    renderOsdDrawingDraft();
                }
            }, 2000);
        }

        // Cập nhật trạng thái nút và card trong sidebar
        if (DOM.inspectorPatchesList) {
            const allCards = DOM.inspectorPatchesList.querySelectorAll('.patch-card');
            allCards.forEach(c => {
                const btn = c.querySelector('.btn-apply-patch');
                if (btn && btn.dataset.layerId === layerId) {
                    c.classList.add('active-applied');
                    btn.classList.add('is-applied');
                    btn.innerHTML = '<i class="fa-solid fa-circle-check"></i> Applied';
                } else if (btn) {
                    c.classList.remove('active-applied');
                    btn.classList.remove('is-applied');
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> Apply Slice';
                }
            });
        }

        if (DOM.inspectorStatusText) {
            DOM.inspectorStatusText.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 6px; padding: 8px 12px; margin-top: 6px; color: #a7f3d0; font-size: 12px; display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-circle-check" style="color: #34d399; font-size: 14px;"></i>
                    <span>Đã gán lát cắt nét từ <b>${layerName}</b> cho vùng này!</span>
                </div>
            `;
        }

        renderFocusRegionsList();
        updateOsdFocusOverlays();
        CanvasEngine.requestRender();
        setStatus('ready', `Đã gán ảnh nét [${layerName}] cho vùng [${Math.round(newRegion.boundingRect[0])}, ${Math.round(newRegion.boundingRect[1])}]`);
        showToast(`Đã gán lát cắt [${layerName}] thành công!`, 'success');
    }

    function updateOsdFocusOverlays() {
        if (!uiState.osdViewer || !uiState.osdViewer.viewport) return;
        const existingOverlays = document.querySelectorAll('.osd-focus-patch-wrap');
        existingOverlays.forEach(el => {
            try { uiState.osdViewer.removeOverlay(el); } catch(ex){}
            el.remove();
        });

        const state = ProjectStore.getState();
        if (!state.focusRegions || state.focusRegions.length === 0) return;

        state.focusRegions.forEach(fr => {
            const worldPoints = fr.pointsWorld || [];
            const outputPoints = worldPoints.map(worldToOutputPixel);
            const xs = outputPoints.map(point => point[0]);
            const ys = outputPoints.map(point => point[1]);
            const minX = Math.min(...xs), minY = Math.min(...ys);
            const w = Math.max(...xs) - minX, h = Math.max(...ys) - minY;
            if (w <= 0 || h <= 0) return;

            const container = document.createElement('div');
            container.className = 'osd-focus-patch-wrap';
            container.style.width = '100%';
            container.style.height = '100%';
            container.style.position = 'absolute';
            container.style.inset = '0';
            container.style.pointerEvents = 'none';
            container.style.zIndex = '60';

            const patchImg = document.createElement('img');
            patchImg.className = 'osd-focus-patch';
            patchImg.style.width = '100%';
            patchImg.style.height = '100%';
            patchImg.style.objectFit = 'fill';
            patchImg.style.display = 'block';
            patchImg.style.pointerEvents = 'none';
            patchImg.style.opacity = '1.0';
            patchImg.style.boxShadow = '0 0 12px rgba(34, 211, 238, 0.7)';

            const targetPatch = (inspectorState.lastPatches || []).find(p => p.layerId === fr.selectedLayerId);
            if (targetPatch && targetPatch.imageDataUrl) {
                patchImg.src = targetPatch.imageDataUrl;
            } else {
                const layer = state.layers.find(item => item.id === fr.selectedLayerId);
                if (!layer) return;
                patchImg.src = `/api/thumbnail?path=${encodeURIComponent(layer.sourcePath)}&size=512`;
            }
            const polygon = outputPoints.map(point => `${((point[0] - minX) / w) * 100}% ${((point[1] - minY) / h) * 100}%`).join(',');
            patchImg.style.clipPath = `polygon(${polygon})`;
            container.appendChild(patchImg);

            try {
                const viewportRect = uiState.osdViewer.viewport.imageToViewportRectangle(minX, minY, w, h);
                uiState.osdViewer.addOverlay({
                    element: container,
                    location: viewportRect
                });
            } catch(ex){}
        });
    }

    function renderFocusRegionsList() {
        const state = ProjectStore.getState();
        const list = state.focusRegions || [];
        if (DOM.focusRegionCount) DOM.focusRegionCount.textContent = list.length;
        if (!DOM.focusRegionsList) return;
        DOM.focusRegionsList.innerHTML = '';

        if (list.length === 0) {
            DOM.focusRegionsList.innerHTML = '<div class="empty-hint">No focus regions applied yet</div>';
            updateOsdFocusOverlays();
            return;
        }

        list.forEach((fr, idx) => {
            const layer = state.layers.find(l => l.id === fr.selectedLayerId);
            const layerName = String(layer ? layer.sourceId : (fr.selectedLayerId || 'Chưa gán'));
            const item = document.createElement('div');
            item.className = 'focus-region-item';
            item.classList.toggle('active', ProjectStore.selectedRegionIds.includes(fr.id));
            item.innerHTML = `
                <div class="region-item-main">
                    <input type="checkbox" class="region-checkbox" ${ProjectStore.selectedRegionIds.includes(fr.id) ? 'checked' : ''}>
                    <span><b>#${idx + 1}</b> ${layerName.substring(0, 16)}... (${(fr.shapeType || 'rect').toUpperCase()})</span>
                </div>
                <div class="region-item-actions">
                    <button class="btn-xs" data-action="lock" title="Lock / Unlock"><i class="fa-solid ${fr.locked ? 'fa-lock' : 'fa-lock-open'}"></i></button>
                    <button class="btn-xs text-danger" title="Delete this region" data-action="delete"><i class="fa-solid fa-trash-can"></i></button>
                </div>
            `;
            item.querySelector('.region-checkbox').addEventListener('click', e => e.stopPropagation());
            item.querySelector('.region-checkbox').addEventListener('change', (e) => {
                e.stopPropagation();
                ProjectStore.selectRegion(fr.id, true);
            });
            item.querySelector('[data-action="lock"]').addEventListener('click', (e) => {
                e.stopPropagation();
                ProjectStore.selectRegions([fr.id]);
                ProjectStore.setSelectedRegionsLocked(!fr.locked);
            });
            item.querySelector('[data-action="delete"]').addEventListener('click', (e) => {
                e.stopPropagation();
                ProjectStore.removeFocusRegion(fr.id);
            });
            item.addEventListener('click', (e) => {
                ProjectStore.selectRegion(fr.id, e.shiftKey);
                renderFocusRegionsList();

                // 1. Kích hoạt lại vùng soi trên viewport
                handleRegionSelected({
                    shapeType: fr.shapeType || 'rectangle',
                    pointsWorld: fr.pointsWorld,
                    boundingRect: fr.boundingRect
                });

                // 2. Pan tới vị trí vùng soi trên OpenSeadragon nếu ở chế độ tự động
                if (uiState.osdViewer && uiState.osdViewer.viewport && fr.boundingRect) {
                    const [rx, ry, rw, rh] = fr.boundingRect;
                    const centerWorld = [rx + rw / 2, ry + rh / 2];
                    const output = worldToOutputPixel(centerWorld);
                    const vpPoint = uiState.osdViewer.viewport.imageToViewportCoordinates(output[0], output[1]);
                    uiState.osdViewer.viewport.panTo(vpPoint, false);
                }

                // 3. Tự động mở accordion "1. Clarity Inspector"
                setAccordionSection('clarity', true);
                if (DOM.btnToggleInspectMode && !inspectorState.isEnabled) {
                    toggleInspectMode(true);
                }

                // 4. Kích hoạt lại API inspect để hiển thị danh sách các ảnh góc chụp bao phủ vùng này
                triggerInspectorQuery(inspectorState.currentRegion);
            });
            DOM.focusRegionsList.appendChild(item);
        });
        updateOsdFocusOverlays();
    }

    function renderExclusionStrokesList() {
        const state = ProjectStore.getState();
        const list = state.maskRegions || [];
        if (DOM.exclusionStrokeCount) DOM.exclusionStrokeCount.textContent = list.length;
        if (!DOM.maskRegionsList) return;
        DOM.maskRegionsList.innerHTML = '';
        list.forEach((mask, index) => {
            const item = document.createElement('div');
            item.className = 'focus-region-item';
            item.classList.toggle('active', ProjectStore.selectedRegionIds.includes(mask.id));
            item.innerHTML = `
                <div class="region-item-main">
                    <input type="checkbox" class="region-checkbox" ${ProjectStore.selectedRegionIds.includes(mask.id) ? 'checked' : ''}>
                    <span>#${index + 1} ${mask.shapeType}</span>
                </div>
                <div class="region-item-actions">
                    <select class="form-select region-operation-select"><option value="exclude" ${mask.operation === 'exclude' ? 'selected' : ''}>Exclude</option><option value="restore" ${mask.operation === 'restore' ? 'selected' : ''}>Restore</option></select>
                    <button class="btn-xs" data-action="lock"><i class="fa-solid ${mask.locked ? 'fa-lock' : 'fa-lock-open'}"></i></button>
                    <button class="btn-xs text-danger" data-action="delete"><i class="fa-solid fa-trash"></i></button>
                </div>`;
            item.querySelector('.region-checkbox').addEventListener('click', event => event.stopPropagation());
            item.querySelector('.region-checkbox').addEventListener('change', event => {
                event.stopPropagation();
                ProjectStore.selectRegion(mask.id, true);
            });
            item.querySelector('.region-operation-select').addEventListener('change', event => {
                ProjectStore.updateMaskRegion(mask.id, { operation: event.target.value });
            });
            item.querySelector('[data-action="lock"]').addEventListener('click', event => {
                event.stopPropagation();
                ProjectStore.selectRegions([mask.id]);
                ProjectStore.setSelectedRegionsLocked(!mask.locked);
            });
            item.querySelector('[data-action="delete"]').addEventListener('click', event => {
                event.stopPropagation();
                ProjectStore.removeMaskRegion(mask.id);
            });
            item.addEventListener('click', event => ProjectStore.selectRegion(mask.id, event.shiftKey));
            DOM.maskRegionsList.appendChild(item);
        });
        if (state.cropRegion) {
            const crop = state.cropRegion;
            const item = document.createElement('div');
            item.className = 'focus-region-item';
            item.classList.toggle('active', ProjectStore.selectedRegionIds.includes(crop.id));
            item.innerHTML = `<div class="region-item-main"><input type="checkbox" class="region-checkbox" ${ProjectStore.selectedRegionIds.includes(crop.id) ? 'checked' : ''}><span>Crop (${crop.shapeType})</span></div><div class="region-item-actions"><button class="btn-xs" data-action="lock"><i class="fa-solid ${crop.locked ? 'fa-lock' : 'fa-lock-open'}"></i></button><button class="btn-xs text-danger" data-action="delete"><i class="fa-solid fa-trash"></i></button></div>`;
            item.querySelector('.region-checkbox').addEventListener('click', event => event.stopPropagation());
            item.querySelector('.region-checkbox').addEventListener('change', event => { event.stopPropagation(); ProjectStore.selectRegion(crop.id, true); });
            item.querySelector('[data-action="lock"]').addEventListener('click', event => { event.stopPropagation(); ProjectStore.selectRegions([crop.id]); ProjectStore.setSelectedRegionsLocked(!crop.locked); });
            item.querySelector('[data-action="delete"]').addEventListener('click', event => { event.stopPropagation(); ProjectStore.selectRegions([crop.id]); ProjectStore.deleteSelectedRegions(); });
            item.addEventListener('click', event => ProjectStore.selectRegion(crop.id, event.shiftKey));
            DOM.maskRegionsList.appendChild(item);
        }
        renderRegionBatchControls();
    }

    function renderRegionBatchControls() {
        const state = ProjectStore.getState();
        const selected = ProjectStore.getSelectedRegions();
        if (DOM.selectedRegionCount) DOM.selectedRegionCount.textContent = `${selected.all.length} regions selected`;
        if (DOM.batchFocusLayerSelect) {
            const current = DOM.batchFocusLayerSelect.value;
            DOM.batchFocusLayerSelect.innerHTML = state.layers.filter(layer => layer.visible).map(layer => `<option value="${layer.id}">${layer.sourceId}</option>`).join('');
            if (state.layers.some(layer => layer.id === current)) DOM.batchFocusLayerSelect.value = current;
        }
        const hasSelection = selected.all.length > 0;
        if (DOM.regionBatchPanel) {
            DOM.regionBatchPanel.style.display = hasSelection ? 'flex' : 'none';
        }
        [DOM.btnBatchLock, DOM.btnBatchUnlock, DOM.btnGroupRegions, DOM.btnUngroupRegions, DOM.btnBatchDelete]
            .filter(Boolean).forEach(button => button.disabled = !hasSelection);
        if (DOM.btnBatchApplyLayer) DOM.btnBatchApplyLayer.disabled = selected.focus.length === 0;
        if (DOM.btnBatchMaskOperation) DOM.btnBatchMaskOperation.disabled = selected.masks.length === 0;
    }

    // ==========================================
    // 4. Kích Hoạt Ghép (Auto Hoặc Xuất Manual)
    // ==========================================
    async function handleMainActionButton() {
        const state = ProjectStore.getState();
        if (state.mode === 'manual') {
            startManualExport();
        } else {
            startAutoStitching();
        }
    }

    async function startAutoStitching() {
        if (uiState.isStitching || uiState.isUploading) return;
        const state = ProjectStore.getState();
        const visibleLayers = state.layers.filter(l => l.visible);

        if (visibleLayers.length < 2) {
            alert("Please select at least 2 images to stitch!");
            return;
        }

        uiState.isStitching = true;
        DOM.btnRunStitching.disabled = true;
        setStatus('busy', 'Đang ghép tự động WSI...');
        DOM.progressPanel.style.display = 'block';
        DOM.terminalLogs.innerHTML = '';
        DOM.progressBarFill.style.width = '0%';
        DOM.progressPercentage.textContent = '0%';

        const payload = {
            images: visibleLayers.map(l => l.sourcePath),
            folderName: state.folderName || 'stitched_wsi',
            featureMethod: DOM.cfgFeatureMethod.value,
            motionModel: DOM.cfgMotionModel.value,
            backgroundMode: DOM.cfgBackgroundMode.value,
            autoCrop: DOM.cfgAutoCrop.checked,
            exportFormat: DOM.cfgExportFormat.value || null,
            project: state
        };

        try {
            const res = await fetch('/api/stitch/auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'started') {
                startPollingStatus();
            } else {
                alert("Error: " + (data.message || "Cannot start stitching"));
                uiState.isStitching = false;
                DOM.btnRunStitching.disabled = false;
                setStatus('ready', 'Ready');
            }
        } catch (err) {
            alert("Server connection error: " + err.message);
            uiState.isStitching = false;
            DOM.btnRunStitching.disabled = false;
            setStatus('ready', 'Ready');
        }
    }

    async function startManualExport() {
        if (uiState.isStitching) return;
        const state = ProjectStore.getState();
        const visibleLayers = state.layers.filter(l => l.visible);

        if (visibleLayers.length === 0) {
            alert("No visible layers enabled for export!");
            return;
        }

        uiState.isStitching = true;
        DOM.btnRunStitching.disabled = true;
        setStatus('busy', 'Đang render full-res từ Canvas...');
        DOM.progressPanel.style.display = 'block';
        DOM.terminalLogs.innerHTML = '';

        try {
            const res = await fetch(`/api/projects/${state.id}/exports`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project: state,
                    exportFormat: DOM.cfgExportFormat.value || 'tif',
                    backgroundMode: DOM.cfgBackgroundMode.value || 'white'
                })
            });
            const data = await res.json();
            if (data.status === 'started') {
                startPollingStatus();
            } else {
                alert("Export error: " + (data.error || "Cannot export"));
                uiState.isStitching = false;
                DOM.btnRunStitching.disabled = false;
                setStatus('ready', 'Ready');
            }
        } catch (err) {
            alert("Server connection error: " + err.message);
            uiState.isStitching = false;
            DOM.btnRunStitching.disabled = false;
            setStatus('ready', 'Ready');
        }
    }

    function startPollingStatus() {
        if (uiState.pollInterval) clearInterval(uiState.pollInterval);
        uiState.pollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/stitch/status');
                const task = await res.json();

                DOM.progressBarFill.style.width = `${task.progress}%`;
                DOM.progressPercentage.textContent = `${task.progress}%`;
                DOM.progressStepTitle.innerHTML = `<i class="fa-solid fa-gear ${task.is_running ? 'fa-spin' : ''}"></i> ${task.step_name}`;

                if (task.logs && task.logs.length > 0) {
                    DOM.terminalLogs.innerHTML = task.logs.map(log => `<div>[${log.percent}%] ${log.step}</div>`).join('');
                    DOM.terminalLogs.scrollTop = DOM.terminalLogs.scrollHeight;
                }

                if (!task.is_running && task.progress >= 100) {
                    clearInterval(uiState.pollInterval);
                    uiState.isStitching = false;
                    DOM.btnRunStitching.disabled = false;
                    setStatus('ready', 'Đã lưu data/result!');
                    handleStitchingSuccess(task.result);
                } else if (task.error) {
                    clearInterval(uiState.pollInterval);
                    uiState.isStitching = false;
                    DOM.btnRunStitching.disabled = false;
                    setStatus('ready', 'Lỗi ghép ảnh');
                    alert("Error: " + task.error);
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, 600);
    }

    function handleStitchingSuccess(result) {
        DOM.osdPlaceholder.style.display = 'none';
        DOM.resultActions.style.display = 'flex';
        DOM.btnSaveOutput.style.display = 'inline-flex';

        const state = ProjectStore.getState();
        const folderName = state.folderName || 'stitched_wsi';
        const fileName = result.fileName || `${folderName}.${result.format || 'tif'}`;

        currentPreviewFile = `data/result/${fileName}`;

        // Cập nhật ma trận biến đổi của từng layer vào ProjectStore
        if (result.layer_transforms) {
            ProjectStore.beginTransaction('Áp dụng kết quả ghép tự động', 'auto_transform');
            state.layers.forEach((layer, idx) => {
                const transform = result.layer_transforms[idx] || result.layer_transforms[String(idx)];
                if (transform) {
                    layer.sourceToWorld = transform;
                }
            });
            if (result.project_revision) {
                state.revision = result.project_revision;
            }
            ProjectStore.commitTransaction();
            CanvasEngine.preloadLayerImages(state.layers);
            CanvasEngine.requestRender();
        }

        const dziUrl = `/dzi/${folderName}_dzi/${folderName}.dzi`;
        const directImageUrl = `/api/image?path=data/result/${fileName}`;

        const mapping = result.outputPixelToWorld || (result.metadata && result.metadata.outputPixelToWorld) || MatrixUtils.identity();
        uiState.outputPixelToWorld = mapping;
        uiState.worldToOutputPixel = MatrixUtils.inverse(mapping) || MatrixUtils.identity();
        initOpenSeadragonViewer(dziUrl, directImageUrl);
        DOM.saveBtnText.textContent = `Save Output (${fileName})`;
    }

    function initOpenSeadragonViewer(dziUrl, fallbackImageUrl) {
        persistOsdViewport();
        if (uiState.osdViewer) {
            uiState.osdViewer.destroy();
            uiState.osdViewer = null;
        }

        DOM.osdPlaceholder.style.display = 'none';

        uiState.osdViewer = OpenSeadragon({
            id: "openseadragonViewer",
            prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
            tileSources: dziUrl,
            showNavigationControl: true,
            showNavigator: true,
            navigatorPosition: "BOTTOM_RIGHT",
            navigatorSizeRatio: 0.22,
            navigatorMaintainSizeRatio: true,
            navigatorAutoFade: false,
            navigatorDisplayRegionColor: '#22d3ee',
            navigatorBorderColor: '#38bdf8',
            navigatorBackground: 'rgba(15, 23, 42, 0.85)',
            animationTime: 0.3,
            blendTime: 0.1,
            maxZoomPixelRatio: 4.0,
            defaultZoomLevel: 0,
            crossOriginPolicy: "Anonymous"
        });
        uiState.osdSourceKey = dziUrl;
        updateOsdControls(false);

        uiState.osdViewer.addHandler('open', function() {
            resizeOsdDrawingCanvas();
            const autoViewport = ProjectStore.getState().viewport.auto;
            const canRestore = autoViewport && autoViewport.sourceKey === dziUrl && Number.isFinite(autoViewport.zoom);
            if (canRestore) {
                uiState.osdViewer.viewport.panTo(new OpenSeadragon.Point(autoViewport.center[0], autoViewport.center[1]), true);
                uiState.osdViewer.viewport.zoomTo(autoViewport.zoom, null, true);
                uiState.osdViewer.viewport.setRotation(autoViewport.rotation || 0, true);
            } else {
                uiState.osdViewer.viewport.goHome(true);
            }
            setOsdInteractionMode(uiState.osdInteractionMode);
            updateOsdControls(true);

            // Hook MouseTracker để soi vùng đa tiêu cự ngay trên OpenSeadragon
            new OpenSeadragon.MouseTracker({
                element: uiState.osdViewer.canvas,
                moveHandler: function(event) {
                    if (!inspectorState.isEnabled || inspectorState.isPinned || !uiState.osdViewer || uiState.osdInteractionMode === 'navigate') return;
                    const webPoint = event.position;
                    const viewportPoint = uiState.osdViewer.viewport.pointFromPixel(webPoint);
                    const imagePoint = uiState.osdViewer.viewport.viewportToImageCoordinates(viewportPoint);
                    handleCanvasPointerInspectHover(outputPixelToWorld([imagePoint.x, imagePoint.y]));
                },
                clickHandler: function(event) {
                    if (!inspectorState.isEnabled || !uiState.osdViewer || uiState.osdInteractionMode === 'navigate') return;
                    const webPoint = event.position;
                    const viewportPoint = uiState.osdViewer.viewport.pointFromPixel(webPoint);
                    const imagePoint = uiState.osdViewer.viewport.viewportToImageCoordinates(viewportPoint);
                    handleCanvasPointerInspectClick(outputPixelToWorld([imagePoint.x, imagePoint.y]));
                }
            });

            // Cập nhật vị trí khung soi khi pan/zoom trong OpenSeadragon
            uiState.osdViewer.addHandler('animation', updateOsdViewportUi);
            uiState.osdViewer.addHandler('viewport-change', updateOsdViewportUi);
            updateOsdFocusOverlays();

            // Tự động điều chỉnh OSD Viewport và Mini Map Navigator khi layout co giãn
            if (window.ResizeObserver && DOM.viewDeepZoom) {
                if (uiState.osdResizeObserver) {
                    try { uiState.osdResizeObserver.disconnect(); } catch (e) {}
                }
                uiState.osdResizeObserver = new ResizeObserver(() => {
                    if (uiState.osdViewer && uiState.osdViewer.viewport) {
                        uiState.osdViewer.viewport.resize();
                        if (uiState.osdViewer.navigator) {
                            uiState.osdViewer.navigator.update();
                        }
                        resizeOsdDrawingCanvas();
                        updateActiveRegionBoxScreenPosition();
                    }
                });
                uiState.osdResizeObserver.observe(DOM.viewDeepZoom);
            }
        });

        uiState.osdViewer.addHandler('open-failed', function() {
            if (fallbackImageUrl && uiState.osdViewer) {
                uiState.osdViewer.open({
                    type: 'image',
                    url: fallbackImageUrl
                });
            }
            updateOsdControls(false);
        });
    }

    function setOsdInteractionMode(mode) {
        uiState.osdInteractionMode = mode || 'navigate';
        const navigate = uiState.osdInteractionMode === 'navigate';
        if (DOM.btnOsdNavigate) DOM.btnOsdNavigate.classList.toggle('active', navigate);
        if (DOM.osdDrawingCanvas) DOM.osdDrawingCanvas.classList.toggle('active', !navigate);
        if (navigate) clearOsdDrawingDraft();
        if (!uiState.osdViewer) return;
        uiState.osdViewer.gestureSettingsMouse.dragToPan = navigate;
        uiState.osdViewer.gestureSettingsTouch.dragToPan = navigate;
        uiState.osdViewer.gestureSettingsMouse.scrollToZoom = true;
        uiState.osdViewer.gestureSettingsTouch.pinchToZoom = true;
    }

    function persistOsdViewport() {
        if (!uiState.osdViewer || !uiState.osdViewer.viewport || !uiState.osdViewer.isOpen()) return;
        const viewport = uiState.osdViewer.viewport;
        const center = viewport.getCenter(true);
        ProjectStore.getState().viewport.auto = {
            center: [center.x, center.y],
            zoom: viewport.getZoom(true),
            rotation: viewport.getRotation(),
            sourceKey: uiState.osdSourceKey
        };
        clearTimeout(uiState.viewportSaveTimer);
        uiState.viewportSaveTimer = setTimeout(saveCurrentSession, 250);
    }

    function updateOsdViewportUi() {
        if (!uiState.osdViewer || !uiState.osdViewer.viewport) return;
        const imageZoom = uiState.osdViewer.viewport.viewportToImageZoom(uiState.osdViewer.viewport.getZoom(true));
        if (DOM.osdZoomIndicator) DOM.osdZoomIndicator.textContent = `${Math.round(imageZoom * 100)}%`;
        persistOsdViewport();
        updateActiveRegionBoxScreenPosition();
        renderOsdDrawingDraft();
    }

    function updateOsdControls(enabled) {
        [DOM.btnOsdZoomOut, DOM.btnOsdZoomIn, DOM.btnOsdFit, DOM.btnOsdOneToOne, DOM.btnOsdReset, DOM.btnOsdNavigate]
            .filter(Boolean).forEach(button => button.disabled = !enabled);
        if (!enabled && DOM.osdZoomIndicator) DOM.osdZoomIndicator.textContent = '--';
    }

    function setStatus(type, text) {
        DOM.globalStatusBadge.className = `status-badge ${type}`;
        DOM.statusBadgeText.textContent = text;
    }

    function showToast(text, type = 'success') {
        let toast = document.getElementById('omnistitchToast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'omnistitchToast';
            toast.className = 'omnistitch-toast';
            document.body.appendChild(toast);
        }
        const icon = (type === 'success') 
            ? '<i class="fa-solid fa-circle-check"></i>' 
            : (type === 'error' ? '<i class="fa-solid fa-circle-xmark"></i>' : '<i class="fa-solid fa-circle-info"></i>');
        toast.innerHTML = `${icon} <span>${text}</span>`;
        toast.className = `omnistitch-toast is-visible ${type}`;
        clearTimeout(toast._timeout);
        toast._timeout = setTimeout(() => {
            toast.classList.remove('is-visible');
        }, 2800);
    }

    // ==========================================
    // 5. Upload Thư Mục / File
    // ==========================================
    async function scanEntry(entry) {
        if (entry.isFile) {
            return new Promise((resolve) => {
                entry.file(f => resolve([f]), () => resolve([]));
            });
        } else if (entry.isDirectory) {
            const dirReader = entry.createReader();
            const allEntries = [];
            const readEntriesPromise = () => {
                return new Promise((resolve) => {
                    dirReader.readEntries((entries) => {
                        if (!entries.length) {
                            resolve(allEntries);
                        } else {
                            allEntries.push(...entries);
                            readEntriesPromise().then(resolve);
                        }
                    }, () => resolve(allEntries));
                });
            };
            const childEntries = await readEntriesPromise();
            const childFilesPromises = childEntries.map(e => scanEntry(e));
            const childFilesArrays = await Promise.all(childFilesPromises);
            return childFilesArrays.flat();
        }
        return [];
    }

    function initUploadDropzone() {
        DOM.btnBrowseFolder.addEventListener('click', () => DOM.folderInput.click());
        DOM.btnBrowseFiles.addEventListener('click', () => DOM.fileInput.click());

        DOM.uploadDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            DOM.uploadDropzone.classList.add('dragover');
        });

        DOM.uploadDropzone.addEventListener('dragleave', () => DOM.uploadDropzone.classList.remove('dragover'));

        DOM.uploadDropzone.addEventListener('drop', async (e) => {
            e.preventDefault();
            DOM.uploadDropzone.classList.remove('dragover');

            let files = [];
            let folderName = '';
            const items = e.dataTransfer.items;
            if (items && items.length > 0) {
                const entryPromises = [];
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    if (item.webkitGetAsEntry) {
                        const entry = item.webkitGetAsEntry();
                        if (entry) {
                            if (entry.isDirectory && !folderName) {
                                folderName = entry.name;
                            }
                            entryPromises.push(scanEntry(entry));
                        }
                    }
                }
                if (entryPromises.length > 0) {
                    const nested = await Promise.all(entryPromises);
                    files = nested.flat();
                }
            }

            if (!files || files.length === 0) {
                files = Array.from(e.dataTransfer.files || []);
            }

            if (files.length > 0) {
                handleFileUploads(files, folderName);
            }
        });

        DOM.folderInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) handleFileUploads(e.target.files);
        });

        DOM.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) handleFileUploads(e.target.files);
        });
    }

    async function handleFileUploads(rawFiles, customFolderName = '') {
        if (uiState.isUploading) return;

        const validExts = ['.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp'];
        const files = Array.from(rawFiles).filter(f => validExts.some(ext => f.name.toLowerCase().endsWith(ext)));

        if (files.length === 0) {
            alert('No valid image files (.tif, .tiff, .png, .jpg, .bmp) found in selection.');
            return;
        }

        // Clean up previous results
        if (DOM.btnSaveOutput) DOM.btnSaveOutput.style.display = 'none';
        if (DOM.resultActions) DOM.resultActions.style.display = 'none';
        currentPreviewFile = null;
        if (uiState.osdViewer) {
            uiState.osdViewer.destroy();
            uiState.osdViewer = null;
        }
        DOM.osdPlaceholder.style.display = 'block';

        uiState.isUploading = true;
        DOM.btnRunStitching.disabled = true;

        let detectedFolderName = customFolderName || ('uploaded_' + Date.now());
        if (!customFolderName && files[0].webkitRelativePath) {
            const parts = files[0].webkitRelativePath.split('/');
            if (parts.length > 1 && parts[0].trim()) {
                detectedFolderName = parts[0].trim();
            }
        }

        ProjectStore.newProject();
        CanvasEngine.resetSession();
        setAppMode('auto');
        const state = ProjectStore.getState();
        state.id = detectedFolderName;
        state.folderName = detectedFolderName;
        ProjectStore.beginTransaction('Tải lên bộ ảnh', 'layer_import_batch');

        const totalFiles = files.length;
        const BATCH_SIZE = 1; // Nạp từng file một để tránh vượt quá payload giới hạn và theo dõi tiến độ chi tiết
        const failedFiles = [];

        for (let i = 0; i < totalFiles; i += BATCH_SIZE) {
            const batch = files.slice(i, i + BATCH_SIZE);
            const batchData = [];

            for (const file of batch) {
                try {
                    const dataUrl = await readFileAsDataURL(file);
                    batchData.push({ fileName: file.name, dataUrl });
                } catch (readErr) {
                    console.error("Lỗi đọc file:", file.name, readErr);
                    failedFiles.push(file.name);
                }
            }

            if (batchData.length === 0) continue;

            const currentFileName = batch[0].name;
            setStatus('busy', `Đang tải lên ${i + 1}/${totalFiles} ảnh... (${currentFileName})`);

            try {
                const res = await fetch('/api/upload_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folderName: detectedFolderName, files: batchData })
                });
                if (!res.ok) {
                    const errJson = await res.json().catch(() => ({ error: res.statusText }));
                    console.error("Upload server error:", currentFileName, errJson);
                    failedFiles.push(currentFileName);
                    continue;
                }
                const resData = await res.json();
                if (resData.status === 'success' && resData.images) {
                    resData.images.forEach((img) => {
                        const tileW = img.width || 2000;
                        const tileH = img.height || 1500;
                        const currentLayerCount = state.layers.length;
                        ProjectStore.addLayer({
                            id: 'layer_' + currentLayerCount,
                            sourceId: img.name,
                            sourcePath: img.path,
                            sourceWidth: tileW,
                            sourceHeight: tileH,
                            sourceToWorld: MatrixUtils.translate(currentLayerCount * (tileW * 0.4), 0),
                            zIndex: currentLayerCount
                        });
                    });
                    renderTileGrid();
                    renderLayersList();
                    renderFocusRegionsList();
                }
            } catch (err) {
                console.error("Upload network error:", currentFileName, err);
                failedFiles.push(currentFileName);
            }
        }

        updateOutputBanner();
        ProjectStore.commitTransaction();
        renderTileGrid();
        renderLayersList();
        saveCurrentSession();
        uiState.isUploading = false;
        DOM.btnRunStitching.disabled = false;

        if (failedFiles.length > 0) {
            setStatus('ready', `Loaded ${state.layers.length}/${totalFiles} images into data/input/${detectedFolderName} (${failedFiles.length} failed)`);
            alert(`Loaded ${state.layers.length}/${totalFiles} images.\n${failedFiles.length} images failed to upload: ${failedFiles.slice(0, 5).join(', ')}${failedFiles.length > 5 ? '...' : ''}`);
        } else {
            setStatus('ready', `Loaded all ${state.layers.length}/${totalFiles} images into data/input/${detectedFolderName}`);
        }
    }

    function readFileAsDataURL(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    function initProgressPanelResize() {
        if (!DOM.progressPanelResizer || !DOM.terminalLogs) return;

        let isDragging = false;
        let startY = 0;
        let startHeight = 0;

        DOM.progressPanelResizer.addEventListener('mousedown', (e) => {
            isDragging = true;
            startY = e.clientY;
            startHeight = DOM.terminalLogs.offsetHeight;
            DOM.progressPanelResizer.classList.add('is-dragging');
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';
        });

        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const deltaY = startY - e.clientY;
            const newHeight = Math.max(48, Math.min(window.innerHeight * 0.65, startHeight + deltaY));
            DOM.terminalLogs.style.height = `${newHeight}px`;
            DOM.terminalLogs.style.maxHeight = '70vh';
        });

        window.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            DOM.progressPanelResizer.classList.remove('is-dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });

        if (DOM.btnToggleProgressExpand) {
            let isExpanded = false;
            let prevHeight = '90px';

            DOM.btnToggleProgressExpand.addEventListener('click', () => {
                isExpanded = !isExpanded;
                if (isExpanded) {
                    prevHeight = DOM.terminalLogs.style.height || '90px';
                    DOM.terminalLogs.style.height = '280px';
                    if (DOM.iconProgressExpand) {
                        DOM.iconProgressExpand.className = 'fa-solid fa-compress';
                    }
                    DOM.btnToggleProgressExpand.title = 'Collapse progress panel';
                } else {
                    DOM.terminalLogs.style.height = prevHeight || '90px';
                    if (DOM.iconProgressExpand) {
                        DOM.iconProgressExpand.className = 'fa-solid fa-up-right-and-down-left-from-center';
                    }
                    DOM.btnToggleProgressExpand.title = 'Expand progress panel';
                }
                DOM.terminalLogs.scrollTop = DOM.terminalLogs.scrollHeight;
            });
        }
    }

    // ==========================================
    // 6. Event Listeners Khởi Tạo
    // ==========================================
    function initEvents() {
        DOM.btnModeAuto.addEventListener('click', () => setAppMode('auto'));
        DOM.btnModeManual.addEventListener('click', () => setAppMode('manual'));

        DOM.sidebarTabs.forEach(btn => {
            btn.addEventListener('click', () => switchSidebarTab(btn.dataset.tab));
        });

        DOM.btnSelectAll.addEventListener('click', () => {
            const tx = ProjectStore.pushHistory('Hiện tất cả layer', 'layer_visibility_batch');
            const state = ProjectStore.getState();
            state.layers.forEach(l => l.visible = true);
            tx.commit();
            ProjectStore.notify('properties');
            renderTileGrid();
            renderLayersList();
            CanvasEngine.requestRender();
        });

        DOM.btnDeselectAll.addEventListener('click', () => {
            const tx = ProjectStore.pushHistory('Ẩn tất cả layer', 'layer_visibility_batch');
            const state = ProjectStore.getState();
            state.layers.forEach(l => l.visible = false);
            tx.commit();
            ProjectStore.notify('properties');
            renderTileGrid();
            renderLayersList();
            CanvasEngine.requestRender();
        });

        // Nút Reset All toàn bộ / Nạp thư mục mới
        if (DOM.btnResetAll) DOM.btnResetAll.addEventListener('click', resetEntireState);
        if (DOM.btnClearList) DOM.btnClearList.addEventListener('click', resetEntireState);

        DOM.cfgExportFormat.addEventListener('change', updateOutputBanner);
        if (DOM.inputOutputDir) DOM.inputOutputDir.addEventListener('input', updateOutputBanner);

        DOM.btnRunStitching.addEventListener('click', handleMainActionButton);

        // Nút Lưu kết quả vào thư mục đích -> Unlock Save Modal Dialog
        if (DOM.btnSaveOutput) DOM.btnSaveOutput.addEventListener('click', openSaveModal);
        if (DOM.btnSaveTrigger) DOM.btnSaveTrigger.addEventListener('click', openSaveModal);

        // Save Modal Listeners
        if (DOM.btnCloseSaveModal) DOM.btnCloseSaveModal.addEventListener('click', closeSaveModal);
        if (DOM.btnCancelSaveModal) DOM.btnCancelSaveModal.addEventListener('click', closeSaveModal);
        if (DOM.btnConfirmSave) DOM.btnConfirmSave.addEventListener('click', handleConfirmSave);
        if (DOM.btnDirectBrowserDownload) DOM.btnDirectBrowserDownload.addEventListener('click', handleDirectBrowserDownload);

        if (DOM.modalInputFileName) DOM.modalInputFileName.addEventListener('input', updateModalPreviewPath);
        if (DOM.modalSelectFormat) DOM.modalSelectFormat.addEventListener('change', updateModalPreviewPath);
        if (DOM.modalInputTargetDir) DOM.modalInputTargetDir.addEventListener('input', updateModalPreviewPath);

        initProgressPanelResize();

        // Inspector Mode Listeners
        if (DOM.btnToggleInspectMode) {
            DOM.btnToggleInspectMode.addEventListener('click', () => toggleInspectMode());
        }
        if (DOM.btnCloseInspector) {
            DOM.btnCloseInspector.addEventListener('click', () => toggleInspectMode(false));
        }

        // Accordion Headers Listener (Bấm vào header để mở / đóng nhóm công cụ)
        if (DOM.accordionHeaders) {
            DOM.accordionHeaders.forEach(header => {
                header.addEventListener('click', (e) => {
                    const targetKey = header.dataset.accordionTarget;
                    const card = header.closest('.tool-section-card');
                    const isExpanded = card && card.classList.contains('expanded');

                    if (isExpanded) {
                        setAccordionSection(null, false);
                    } else {
                        setAccordionSection(targetKey, true);
                        // Tự động kích hoạt công cụ đầu tiên của section nếu chưa thuộc section này
                        if (targetKey === 'clarity') {
                            if (!['rect', 'polygon', 'lasso'].includes(inspectorState.currentTool)) {
                                selectDrawingTool('rect');
                            }
                        } else if (targetKey === 'brush') {
                            if (!['brush_exclude', 'brush_restore'].includes(inspectorState.currentTool)) {
                                selectDrawingTool('brush_exclude');
                            }
                        } else if (targetKey === 'crop') {
                            if (!['crop', 'crop_polygon', 'crop_lasso'].includes(inspectorState.currentTool)) {
                                selectDrawingTool('crop');
                            }
                        }
                    }
                });
            });
        }

        // Inspector Backdrop Listener (Bấm ra ngoài nền mờ mobile để đóng drawer)
        if (DOM.inspectorBackdrop) {
            DOM.inspectorBackdrop.addEventListener('click', () => {
                toggleInspectMode(false);
            });
        }

        // Drawing Tool Pills Listener
        if (DOM.drawingToolPills) {
            DOM.drawingToolPills.forEach(pill => {
                pill.addEventListener('click', () => {
                    const tool = pill.dataset.tool;
                    selectDrawingTool(tool);
                });
            });
        }

        // Brush Radius Slider & Presets
        if (DOM.sliderBrushRadius) {
            DOM.sliderBrushRadius.addEventListener('input', (e) => {
                const r = parseInt(e.target.value, 10);
                DOM.valBrushRadius.textContent = `${r} px`;
                CanvasEngine.setBrushRadius(r);
                updateAccordionSummaries();
            });
        }
        if (DOM.brushPresetPills) {
            DOM.brushPresetPills.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    DOM.brushPresetPills.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const r = parseInt(btn.dataset.brush, 10);
                    DOM.sliderBrushRadius.value = r;
                    DOM.valBrushRadius.textContent = `${r} px`;
                    CanvasEngine.setBrushRadius(r);
                    updateAccordionSummaries();
                });
            });
        }

        // Crop Tool Buttons
        if (DOM.btnApplyCrop) {
            DOM.btnApplyCrop.addEventListener('click', () => {
                const trim = DOM.chkTrimOutputBounds ? DOM.chkTrimOutputBounds.checked : true;
                if (!ProjectStore.getState().cropDraft) {
                    setStatus('ready', 'Chưa có bản nháp crop để áp dụng');
                    return;
                }
                const cropRegion = ProjectStore.applyCropDraft({ trimOutputBounds: trim });
                setStatus('ready', 'Đã áp dụng vùng cắt (Crop)');
                updateAccordionSummaries();
                CanvasEngine.requestRender();

                // Ở chế độ Ghép Tự Động (OSD): Zoom mượt mà vào đúng vùng crop
                if (uiState.osdViewer && uiState.osdViewer.viewport && cropRegion && cropRegion.boundingRect) {
                    const [cx, cy, cw, ch] = cropRegion.boundingRect;
                    const outputTopLeft = worldToOutputPixel([cx, cy]);
                    const outputBottomRight = worldToOutputPixel([cx + cw, cy + ch]);
                    const outMinX = Math.min(outputTopLeft[0], outputBottomRight[0]);
                    const outMinY = Math.min(outputTopLeft[1], outputBottomRight[1]);
                    const outW = Math.abs(outputBottomRight[0] - outputTopLeft[0]);
                    const outH = Math.abs(outputBottomRight[1] - outputTopLeft[1]);
                    
                    try {
                        const vpRect = uiState.osdViewer.viewport.imageToViewportRectangle(outMinX, outMinY, outW, outH);
                        uiState.osdViewer.viewport.fitBounds(vpRect, false);
                    } catch (e) {
                        console.warn("OSD fitBounds crop error:", e);
                    }
                }
                renderOsdDrawingDraft();
            });
        }
        if (DOM.btnCancelCrop) {
            DOM.btnCancelCrop.addEventListener('click', () => {
                ProjectStore.cancelCropDraft();
                CanvasEngine.cancelDraft();
                setStatus('ready', 'Cancelled bản nháp crop, crop đã Apply được giữ nguyên');
                updateAccordionSummaries();
                renderOsdDrawingDraft();
            });
        }
        if (DOM.btnResetCrop) {
            DOM.btnResetCrop.addEventListener('click', () => {
                ProjectStore.clearCropRegion();
                setStatus('ready', 'Cancelled vùng cắt (Crop)');
                updateAccordionSummaries();
                CanvasEngine.requestRender();
                renderOsdDrawingDraft();
            });
        }

        // Clear All Strokes Button
        if (DOM.btnClearAllStrokes) {
            DOM.btnClearAllStrokes.addEventListener('click', () => {
                ProjectStore.clearMaskRegions();
                renderExclusionStrokesList();
                CanvasEngine.requestRender();
                setStatus('ready', 'Đã xóa tất cả nét cọ xóa nền');
            });
        }

        if (DOM.regionSizePills) {
            DOM.regionSizePills.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const sz = parseInt(e.target.dataset.size, 10);
                    setInspectorSize(sz);
                });
            });
        }
        if (DOM.btnUnpinInspector) {
            DOM.btnUnpinInspector.addEventListener('click', unpinInspector);
        }
        if (DOM.btnClearAllFocusRegions) {
            DOM.btnClearAllFocusRegions.addEventListener('click', () => {
                ProjectStore.clearFocusRegions();
                renderFocusRegionsList();
                CanvasEngine.requestRender();
            });
        }

        if (DOM.btnBatchApplyLayer) DOM.btnBatchApplyLayer.addEventListener('click', () => {
            if (DOM.batchFocusLayerSelect.value) ProjectStore.setLayerForSelectedFocusRegions(DOM.batchFocusLayerSelect.value);
        });
        if (DOM.btnBatchMaskOperation) DOM.btnBatchMaskOperation.addEventListener('click', () => {
            ProjectStore.setSelectedMaskOperation(DOM.batchMaskOperation.value);
        });
        if (DOM.btnBatchLock) DOM.btnBatchLock.addEventListener('click', () => ProjectStore.setSelectedRegionsLocked(true));
        if (DOM.btnBatchUnlock) DOM.btnBatchUnlock.addEventListener('click', () => ProjectStore.setSelectedRegionsLocked(false));
        if (DOM.btnGroupRegions) DOM.btnGroupRegions.addEventListener('click', () => ProjectStore.groupSelectedRegions());
        if (DOM.btnUngroupRegions) DOM.btnUngroupRegions.addEventListener('click', () => ProjectStore.ungroupSelectedRegions());
        if (DOM.btnBatchDelete) DOM.btnBatchDelete.addEventListener('click', () => ProjectStore.deleteSelectedRegions());
        if (DOM.btnRetryAutosave) DOM.btnRetryAutosave.addEventListener('click', () => {
            ProjectStore.saveQueued = true;
            ProjectStore.flushAutosave();
        });
        if (DOM.btnDismissAutosaveConflict) DOM.btnDismissAutosaveConflict.addEventListener('click', () => {
            DOM.autosaveConflictBanner.style.display = 'none';
        });

        // Responsive Sidebar Toggle
        if (DOM.btnToggleSidebar) {
            DOM.btnToggleSidebar.addEventListener('click', () => {
                DOM.sidebar.classList.toggle('open');
            });
        }

        // Toolbar Buttons
        DOM.btnUndo.addEventListener('click', () => ProjectStore.undo());
        DOM.btnRedo.addEventListener('click', () => ProjectStore.redo());
        DOM.btnFitContent.addEventListener('click', () => CanvasEngine.fitToContent());
        DOM.btnZoomIn.addEventListener('click', () => {
            CanvasEngine.viewport.scale *= 1.25;
            CanvasEngine.requestRender();
        });
        DOM.btnZoomOut.addEventListener('click', () => {
            CanvasEngine.viewport.scale *= 0.8;
            CanvasEngine.requestRender();
        });

        DOM.btnResetViewer.addEventListener('click', () => {
            if (uiState.osdViewer) uiState.osdViewer.viewport.goHome();
        });
        if (DOM.btnOsdNavigate) DOM.btnOsdNavigate.addEventListener('click', () => setOsdInteractionMode('navigate'));
        if (DOM.btnOsdZoomIn) DOM.btnOsdZoomIn.addEventListener('click', () => {
            if (uiState.osdViewer) uiState.osdViewer.viewport.zoomBy(1.4).applyConstraints();
        });
        if (DOM.btnOsdZoomOut) DOM.btnOsdZoomOut.addEventListener('click', () => {
            if (uiState.osdViewer) uiState.osdViewer.viewport.zoomBy(1 / 1.4).applyConstraints();
        });
        if (DOM.btnOsdFit) DOM.btnOsdFit.addEventListener('click', () => {
            if (uiState.osdViewer) uiState.osdViewer.viewport.goHome();
        });
        if (DOM.btnOsdOneToOne) DOM.btnOsdOneToOne.addEventListener('click', () => {
            if (!uiState.osdViewer) return;
            const zoom = uiState.osdViewer.viewport.imageToViewportZoom(1);
            uiState.osdViewer.viewport.zoomTo(zoom).applyConstraints();
        });
        if (DOM.btnOsdReset) DOM.btnOsdReset.addEventListener('click', () => {
            if (!uiState.osdViewer) return;
            uiState.osdViewer.viewport.setRotation(0);
            uiState.osdViewer.viewport.goHome();
        });

        // Lắng nghe thay đổi store
        ProjectStore.subscribe((state, changeType) => {
            renderLayersList();
            renderFocusRegionsList();
            renderExclusionStrokesList();
            CanvasEngine.requestRender();
            renderOsdDrawingDraft();
            saveCurrentSession();
            updateHistoryControls();
            if (changeType === 'autosaveConflict') {
                if (DOM.autosaveConflictBanner) DOM.autosaveConflictBanner.style.display = 'flex';
                setStatus('ready', 'Xung đột autosave - bản cục bộ chưa được lưu');
            } else if (!ProjectStore.autosaveConflict && DOM.autosaveConflictBanner) {
                DOM.autosaveConflictBanner.style.display = 'none';
            }
        });

        // Phím tắt toàn cục Undo (Ctrl+Z) & Redo (Ctrl+Y / Ctrl+Shift+Z)
        window.addEventListener('keydown', (e) => {
            const editable = e.target.matches('input, textarea, select, [contenteditable="true"]');
            if (e.code === 'Space' && !editable) {
                uiState.spacePressed = true;
                CanvasEngine.setSpacePressed(true);
            }
            if (editable) return;

            if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'z') {
                e.preventDefault();
                const undone = ProjectStore.undo();
                if (undone) {
                    setStatus('ready', '↩️ Đã hoàn tác (Undo)');
                }
            } else if ((e.ctrlKey && e.key.toLowerCase() === 'y') || (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'z')) {
                e.preventDefault();
                const redone = ProjectStore.redo();
                if (redone) {
                    setStatus('ready', '↪️ Đã làm lại (Redo)');
                }
            } else if (e.key === 'Escape') {
                CanvasEngine.cancelDraft();
                clearOsdDrawingDraft();
                if (ProjectStore.getState().cropDraft) ProjectStore.cancelCropDraft();
                if (inspectorState.isPinned) unpinInspector();
                else if (inspectorState.isEnabled) toggleInspectMode(false);
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
                if (ProjectStore.selectedRegionIds.length > 0) ProjectStore.deleteSelectedRegions();
                else {
                    const selected = ProjectStore.getSelectedLayer();
                    if (selected && CanvasEngine.toolMode === 'select') ProjectStore.removeLayer(selected.id);
                }
            } else if (e.ctrlKey && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                const state = ProjectStore.getState();
                let ids = [];
                if (CanvasEngine.toolMode.startsWith('brush')) ids = state.maskRegions.map(region => region.id);
                else if (CanvasEngine.toolMode.startsWith('crop')) ids = state.cropRegion ? [state.cropRegion.id] : [];
                else ids = state.focusRegions.map(region => region.id);
                ProjectStore.selectRegions(ids);
            }
        });
        window.addEventListener('keyup', (e) => {
            if (e.code === 'Space') {
                uiState.spacePressed = false;
                CanvasEngine.setSpacePressed(false);
            }
        });
    }

    function updateHistoryControls() {
        if (DOM.btnUndo) {
            const command = ProjectStore.getState().historyJournal[ProjectStore.getState().historyCursor - 1];
            DOM.btnUndo.disabled = !ProjectStore.canUndo();
            DOM.btnUndo.title = command ? `Undo: ${command.label}` : 'No action to undo';
        }
        if (DOM.btnRedo) {
            const command = ProjectStore.getState().historyJournal[ProjectStore.getState().historyCursor];
            DOM.btnRedo.disabled = !ProjectStore.canRedo();
            DOM.btnRedo.title = command ? `Redo: ${command.label}` : 'No action to redo';
        }
    }

    // ==========================================
    // 7. Session Persistence (Giữ nguyên hình ảnh khi load lại trang / F5)
    // ==========================================
    function saveCurrentSession() {
        try {
            const state = ProjectStore.getState();
            if (state && state.layers && state.layers.length > 0) {
                const sessionData = {
                    project: state,
                    exportFormat: DOM.cfgExportFormat ? DOM.cfgExportFormat.value : 'tif',
                    targetDir: DOM.inputOutputDir ? DOM.inputOutputDir.value : 'data/result'
                };
                localStorage.setItem('wsi_saved_session', JSON.stringify(sessionData));
            }
        } catch (e) {
            console.warn("Không thể lưu session vào localStorage:", e);
        }
    }

    function restoreSession() {
        try {
            const saved = localStorage.getItem('wsi_saved_session');
            if (saved) {
                const sessionData = JSON.parse(saved);
                const savedProject = sessionData.project || sessionData;
                if (savedProject && savedProject.layers && savedProject.layers.length > 0) {
                    ProjectStore.loadState(savedProject);
                    const state = ProjectStore.getState();

                    if (sessionData.exportFormat && DOM.cfgExportFormat) {
                        DOM.cfgExportFormat.value = sessionData.exportFormat;
                    }
                    if (sessionData.targetDir && DOM.inputOutputDir) {
                        DOM.inputOutputDir.value = sessionData.targetDir;
                    }

                    renderTileGrid();
                    renderLayersList();
                    renderFocusRegionsList();
                    CanvasEngine.preloadLayerImages(state.layers);
                    CanvasEngine.requestRender();
                    setStatus('ready', `Đã giữ lại ${state.layers.length} ảnh (${state.folderName})`);
                    return true;
                }
            }
        } catch (e) {
            console.warn("Lỗi khôi phục session:", e);
        }
        return false;
    }

    async function checkBackgroundStitchingTask() {
        try {
            const res = await fetch('/api/stitch/status');
            const task = await res.json();
            if (task) {
                if (task.is_running) {
                    uiState.isStitching = true;
                    DOM.btnRunStitching.disabled = true;
                    DOM.progressPanel.style.display = 'block';
                    setStatus('busy', 'Tiến trình ghép ảnh đang tiếp tục...');
                    startPollingStatus();
                } else if (task.progress >= 100 && task.result) {
                    handleStitchingSuccess(task.result);
                }
            }
        } catch (e) {
            console.warn("Không thể kiểm tra background task:", e);
        }
    }

    // Khởi chạy
    function init() {
        initEvents();
        initUploadDropzone();
        initAdjustmentListeners();
        CanvasEngine.init(DOM.manualCanvasContainer);
        initOsdDrawingCanvas();
        initViewportSelectionOverlay();
        initPatchLightboxEvents();

        // Kết nối sự kiện di chuột, click và kéo chọn vùng trên Canvas Engine sang Bộ Soi Điểm Ảnh
        CanvasEngine.onPointerHover = (worldPt) => handleCanvasPointerInspectHover(worldPt);
        CanvasEngine.onPointerClick = (worldPt) => handleCanvasPointerInspectClick(worldPt);
        CanvasEngine.onRegionSelected = (worldRect) => handleRegionSelected(worldRect);
        CanvasEngine.onRenderPost = () => updateActiveRegionBoxScreenPosition();

        restoreSession();
        const state = ProjectStore.getState();
        setAppMode(state.mode || 'auto');
        if (state.viewport && state.viewport.manual) {
            CanvasEngine.viewport = Object.assign({}, CanvasEngine.viewport, state.viewport.manual);
            CanvasEngine.requestRender();
        }
        updateHistoryControls();
        updateOsdControls(false);
        updateAccordionSummaries();
        setAccordionSection('clarity', true);
        checkBackgroundStitchingTask();
    }

    document.addEventListener('DOMContentLoaded', init);
})();
