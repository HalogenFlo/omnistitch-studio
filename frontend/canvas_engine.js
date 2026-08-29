/**
 * Chức năng: Canva-Style Manual Interactive Canvas Engine
 * Lí do tạo: Cung cấp trải nghiệm chỉnh ghép ảnh WSI trực quan (Move, Rotate, Scale, Layer, Color Adjustments)
 *            Hỗ trợ chọn vùng nét tùy ý (Rectangle, Polygon, Lasso), Cọ xóa nền (Brush Exclude/Restore) và Crop Tool.
 * Đường dẫn: tool/image_alignment/frontend/canvas_engine.js
 */

const CanvasEngine = (function () {
    'use strict';

    class Engine {
        constructor() {
            this.container = null;
            this.canvas = null;
            this.ctx = null;
            this.preMaskCanvas = document.createElement('canvas');
            this.restoreCanvas = document.createElement('canvas');
            this.imageCache = new Map(); // sourceId -> HTMLImageElement (proxy/thumb)
            
            // Viewport pan & zoom
            this.viewport = {
                x: 0,
                y: 0,
                scale: 0.2 // Tỉ lệ zoom thế giới sang màn hình
            };

            // Chế độ công cụ vẽ hiện tại: 'select' | 'rect' | 'polygon' | 'lasso' | 'brush_exclude' | 'brush_restore' | 'crop'
            this.toolMode = 'select';
            this.brushRadius = 24; // CSS pixels
            this.spacePressed = false;
            this.mouseScreenPos = [0, 0];
            this.mouseWorldPos = [0, 0];

            // Trạng thái tương tác layer
            this.interaction = {
                mode: 'idle', // 'idle' | 'panning' | 'moving' | 'rotating' | 'scaling' | 'drawing_rect' | 'drawing_lasso' | 'brushing' | 'crop_adjust'
                activeHandle: null, // 'rot' | 'tl' | 'tr' | 'br' | 'bl'
                startX: 0,
                startY: 0,
                initialMatrix: null,
                initialCenter: null,
                initialAngle: 0,
                initialScale: 1
            };

            // Drafts vẽ vùng
            this.polygonDraftPoints = []; // [[wx, wy], ...]
            this.lassoDraftPoints = [];   // [[wx, wy], ...]
            this.brushDraftPoints = [];   // [[wx, wy], ...]
            this.cropDraft = null;        // { pointsWorld: [[...]], isDragging: false }
            this.regionMarquee = null;

            this.inspectorReticle = null; // { shapeType, pointsWorld, boundingRect, isPinned: boolean }
            this.dpr = window.devicePixelRatio || 1;
            this.cssWidth = 0;
            this.cssHeight = 0;
            this.animationFrameId = null;

            // Callbacks
            this.onRegionSelected = null; // (regionData: { shapeType, pointsWorld, boundingRect }) => void
            this.onPointerHover = null;   // (worldPoint, screenPoint) => void
            this.onRenderPost = null;     // () => void
        }

        init(containerElement) {
            this.container = containerElement;
            this.canvas = document.createElement('canvas');
            this.canvas.className = 'manual-canvas-overlay';
            this.ctx = this.canvas.getContext('2d');
            this.container.innerHTML = '';
            this.container.classList.add('alpha-preview');
            this.container.appendChild(this.canvas);

            this.resize();
            this.bindEvents();
            
            // ResizeObserver để tự động nhận biết khi mở sidebar / inspector drawer
            if (window.ResizeObserver && this.container) {
                this.resizeObserver = new ResizeObserver((entries) => {
                    for (const entry of entries) {
                        if (entry.contentRect.width > 0 && entry.contentRect.height > 0) {
                            if (this.resize()) {
                                this.requestRender();
                            }
                        }
                    }
                });
                this.resizeObserver.observe(this.container);
            }

            // Lắng nghe store changes
            ProjectStore.subscribe((state, changeType) => {
                this.preloadLayerImages(state.layers);
                this.requestRender();
            });

            window.addEventListener('resize', () => {
                this.resize();
                this.requestRender();
            });
        }

        setToolMode(mode) {
            this.cancelDraft(true);
            this.toolMode = mode || 'select';
            this.requestRender();
        }

        setSpacePressed(pressed) {
            this.spacePressed = Boolean(pressed);
        }

        cancelDraft(rollbackTransaction = true) {
            if (rollbackTransaction && ProjectStore.activeTransaction) {
                ProjectStore.cancelTransaction(true);
            }
            this.polygonDraftPoints = [];
            this.lassoDraftPoints = [];
            this.brushDraftPoints = [];
            this.regionMarquee = null;
            this.interaction.mode = 'idle';
            this.interaction.pointerId = null;
            this.requestRender();
        }

        isCropTool(mode = this.toolMode) {
            return mode === 'crop' || mode === 'crop_polygon' || mode === 'crop_lasso';
        }

        persistViewport() {
            const state = ProjectStore.getState();
            if (state.viewport && state.viewport.manual) {
                state.viewport.manual = Object.assign({}, this.viewport);
            }
        }

        resetSession() {
            this.cancelDraft();
            this.inspectorReticle = null;
            this.imageCache.clear();
            this.viewport = { x: 0, y: 0, scale: 0.2 };
            this.requestRender();
        }

        setBrushRadius(radius) {
            this.brushRadius = Math.max(2, Math.min(200, Number(radius) || 24));
            this.requestRender();
        }

        resize() {
            if (!this.container || !this.canvas) return false;
            const rect = this.container.getBoundingClientRect();
            const width = Math.floor(rect.width);
            const height = Math.floor(rect.height);
            if (width <= 0 || height <= 0) return false;

            const dpr = window.devicePixelRatio || 1;
            this.dpr = dpr;
            this.cssWidth = width;
            this.cssHeight = height;

            this.canvas.width = Math.round(width * dpr);
            this.canvas.height = Math.round(height * dpr);
            this.preMaskCanvas.width = this.canvas.width;
            this.preMaskCanvas.height = this.canvas.height;
            this.restoreCanvas.width = this.canvas.width;
            this.restoreCanvas.height = this.canvas.height;
            this.canvas.style.width = width + 'px';
            this.canvas.style.height = height + 'px';
            return true;
        }

        preloadLayerImages(layers) {
            layers.forEach(layer => {
                const cacheKey = this.getLayerCacheKey(layer);
                if (!this.imageCache.has(cacheKey)) {
                    const img = new Image();
                    img.crossOrigin = 'anonymous';
                    // Tải thumbnail/proxy để vẽ mượt trên Canvas
                    img.src = `/api/thumbnail?path=${encodeURIComponent(layer.sourcePath)}&size=1024`;
                    img.onload = () => this.requestRender();
                    this.imageCache.set(cacheKey, img);
                }
            });
        }

        getLayerCacheKey(layer) {
            return `${layer.id || ''}\u0000${layer.sourcePath || layer.sourceId || ''}`;
        }

        requestRender() {
            if (this.animationFrameId) return;
            this.animationFrameId = requestAnimationFrame(() => {
                this.animationFrameId = null;
                this.render();
            });
        }

        // ==========================================
        // Chuyển đổi tọa độ World <-> Screen (CSS Pixels)
        // ==========================================
        worldToScreen(wx, wy) {
            const w = this.cssWidth || (this.canvas.width / (this.dpr || 1));
            const h = this.cssHeight || (this.canvas.height / (this.dpr || 1));
            const sx = (wx + this.viewport.x) * this.viewport.scale + w / 2;
            const sy = (wy + this.viewport.y) * this.viewport.scale + h / 2;
            return [sx, sy];
        }

        screenToWorld(sx, sy) {
            const w = this.cssWidth || (this.canvas.width / (this.dpr || 1));
            const h = this.cssHeight || (this.canvas.height / (this.dpr || 1));
            const wx = (sx - w / 2) / this.viewport.scale - this.viewport.x;
            const wy = (sy - h / 2) / this.viewport.scale - this.viewport.y;
            return [wx, wy];
        }

        zoomToFit() {
            const state = ProjectStore.getState();
            if (!state.layers || state.layers.length === 0) return;

            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            state.layers.forEach(l => {
                if (!l.visible) return;
                const sw = l.sourceWidth || 2000;
                const sh = l.sourceHeight || 1500;
                const corners = [[0, 0], [sw, 0], [sw, sh], [0, sh]];
                corners.forEach(([cx, cy]) => {
                    const [wx, wy] = MatrixUtils.transformPoint(l.sourceToWorld, cx, cy);
                    minX = Math.min(minX, wx);
                    minY = Math.min(minY, wy);
                    maxX = Math.max(maxX, wx);
                    maxY = Math.max(maxY, wy);
                });
            });

            const contentW = maxX - minX;
            const contentH = maxY - minY;
            if (contentW <= 0 || contentH <= 0) return;

            const w = this.cssWidth || (this.canvas.width / this.dpr);
            const h = this.cssHeight || (this.canvas.height / this.dpr);
            if (w <= 0 || h <= 0) return;

            const padding = 60;
            const scaleX = (w - padding * 2) / contentW;
            const scaleY = (h - padding * 2) / contentH;
            this.viewport.scale = Math.max(0.001, Math.min(scaleX, scaleY, 1.0));
            this.viewport.x = -(minX + contentW / 2);
            this.viewport.y = -(minY + contentH / 2);
            this.requestRender();
        }

        render() {
            if (!this.ctx || !this.canvas) return;
            const ctx = this.ctx;
            const dpr = this.dpr || 1;
            const w = this.cssWidth || (this.canvas.width / dpr);
            const h = this.cssHeight || (this.canvas.height / dpr);

            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            // 1. Lưới nền Studio Dark Glassmorphism
            this.drawBackgroundGrid(ctx, w, h);

            const state = ProjectStore.getState();
            const selectedLayer = ProjectStore.getSelectedLayer();

            // 2. Vẽ Layer theo zIndex
            const sortedLayers = [...state.layers].sort((a, b) => a.zIndex - b.zIndex);
            sortedLayers.forEach(layer => {
                if (!layer.visible) return;
                this.drawLayer(ctx, layer);
            });

            // 3. Vẽ Focus Regions (Polygon, Lasso, Rectangle)
            this.drawFocusRegions(ctx, state);

            // 4. Apply only committed crop alpha before capturing pre-mask pixels.
            this.drawKeepRegion(ctx, state);

            // Capture the authoritative composite immediately before ordered masks.
            const preMaskCtx = this.preMaskCanvas.getContext('2d');
            preMaskCtx.setTransform(1, 0, 0, 1, 0, 0);
            preMaskCtx.clearRect(0, 0, this.preMaskCanvas.width, this.preMaskCanvas.height);
            preMaskCtx.drawImage(this.canvas, 0, 0);

            // 5. Vẽ Exclusion / Restore theo đúng thứ tự trên pre-mask composite
            this.drawExclusionStrokes(ctx, state, this.preMaskCanvas);
            this.drawFocusAnnotations(ctx, state);
            this.drawCropAnnotation(ctx, state);

            // 6. Vẽ Bounding Box & Transform Handles cho layer được chọn
            if (this.toolMode === 'select' && selectedLayer && selectedLayer.visible) {
                this.drawSelectionBox(ctx, selectedLayer);
            }
            if (this.toolMode === 'select') this.drawRegionSelections(ctx, state);

            // 7. Vẽ Reticle & Drafts công cụ vẽ
            this.drawDrawingDrafts(ctx);

            // 8. Vẽ Con trỏ Brush nếu đang ở chế độ cọ
            if (this.toolMode === 'brush_exclude' || this.toolMode === 'brush_restore') {
                this.drawBrushCursor(ctx);
            }

            // 9. Vẽ Bản Đồ Thu Nhỏ Điều Hướng (Mini-Map Navigator)
            this.drawMiniMap(ctx, state);

            if (typeof this.onRenderPost === 'function') {
                this.onRenderPost();
            }
        }

        drawMiniMap(ctx, state) {
            if (!state.layers || state.layers.length === 0) return;

            const w = this.cssWidth || (this.canvas.width / this.dpr);
            const h = this.cssHeight || (this.canvas.height / this.dpr);

            const mmW = 180;
            const mmH = 130;
            const pad = 14;
            const mmX = w - mmW - pad;
            const mmY = h - mmH - pad;

            this.miniMapRect = [mmX, mmY, mmW, mmH];

            // 1. Tính tổng bounding box toàn bộ layers
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            state.layers.forEach(l => {
                if (!l.visible) return;
                const sw = l.sourceWidth || 2000;
                const sh = l.sourceHeight || 1500;
                const corners = [[0, 0], [sw, 0], [sw, sh], [0, sh]];
                corners.forEach(([cx, cy]) => {
                    const [wx, wy] = MatrixUtils.transformPoint(l.sourceToWorld, cx, cy);
                    minX = Math.min(minX, wx);
                    minY = Math.min(minY, wy);
                    maxX = Math.max(maxX, wx);
                    maxY = Math.max(maxY, wy);
                });
            });

            if (!isFinite(minX) || !isFinite(maxX)) return;
            const totalW = Math.max(1, maxX - minX);
            const totalH = Math.max(1, maxY - minY);

            const scaleX = (mmW - 16) / totalW;
            const scaleY = (mmH - 16) / totalH;
            const mmScale = Math.min(scaleX, scaleY);

            const offsetX = mmX + (mmW - totalW * mmScale) / 2;
            const offsetY = mmY + (mmH - totalH * mmScale) / 2;

            ctx.save();
            // Nền hộp Mini-map
            ctx.fillStyle = 'rgba(10, 15, 30, 0.88)';
            ctx.fillRect(mmX, mmY, mmW, mmH);
            ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(mmX, mmY, mmW, mmH);

            // Tiêu đề Mini-map
            ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
            ctx.font = 'bold 10px Outfit, sans-serif';
            ctx.fillText('🧭 BẢN ĐỒ ĐIỀU HƯỚNG', mmX + 8, mmY + 12);

            // Vẽ các lớp ảnh dạng thumbnail mini
            state.layers.forEach(layer => {
                if (!layer.visible) return;
                const sw = layer.sourceWidth || 2000;
                const sh = layer.sourceHeight || 1500;
                const p0 = MatrixUtils.transformPoint(layer.sourceToWorld, 0, 0);
                const p1 = MatrixUtils.transformPoint(layer.sourceToWorld, sw, 0);
                const p2 = MatrixUtils.transformPoint(layer.sourceToWorld, sw, sh);
                const p3 = MatrixUtils.transformPoint(layer.sourceToWorld, 0, sh);

                const mpts = [p0, p1, p2, p3].map(([wx, wy]) => [
                    offsetX + (wx - minX) * mmScale,
                    offsetY + (wy - minY) * mmScale
                ]);

                ctx.beginPath();
                ctx.moveTo(mpts[0][0], mpts[0][1]);
                ctx.lineTo(mpts[1][0], mpts[1][1]);
                ctx.lineTo(mpts[2][0], mpts[2][1]);
                ctx.lineTo(mpts[3][0], mpts[3][1]);
                ctx.closePath();
                ctx.fillStyle = 'rgba(99, 102, 241, 0.35)';
                ctx.fill();
                ctx.strokeStyle = 'rgba(129, 140, 248, 0.6)';
                ctx.lineWidth = 0.8;
                ctx.stroke();
            });

            // Vẽ Khung Đỏ / Xanh đại diện vùng Viewport đang nhìn thấy
            const vpW0 = this.screenToWorld(0, 0);
            const vpW1 = this.screenToWorld(w, h);
            const vpMinX = Math.min(vpW0[0], vpW1[0]);
            const vpMinY = Math.min(vpW0[1], vpW1[1]);
            const vpMaxX = Math.max(vpW0[0], vpW1[0]);
            const vpMaxY = Math.max(vpW0[1], vpW1[1]);

            const vScreenX = Math.max(mmX, offsetX + (vpMinX - minX) * mmScale);
            const vScreenY = Math.max(mmY, offsetY + (vpMinY - minY) * mmScale);
            const vScreenW = Math.min(mmW, (vpMaxX - vpMinX) * mmScale);
            const vScreenH = Math.min(mmH, (vpMaxY - vpMinY) * mmScale);

            ctx.fillStyle = 'rgba(236, 72, 153, 0.18)';
            ctx.fillRect(vScreenX, vScreenY, vScreenW, vScreenH);
            ctx.strokeStyle = '#ec4899';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(vScreenX, vScreenY, vScreenW, vScreenH);

            ctx.restore();
        }

        drawFocusRegions(ctx, state) {
            if (!state.focusRegions || state.focusRegions.length === 0) return;

            state.focusRegions.forEach(fr => {
                const layer = state.layers.find(l => l.id === fr.selectedLayerId && l.visible);
                if (!layer) return;

                const points = fr.pointsWorld || [];
                if (points.length < 3) return;

                const screenPoints = points.map(p => this.worldToScreen(p[0], p[1]));

                ctx.save();
                ctx.beginPath();
                ctx.moveTo(screenPoints[0][0], screenPoints[0][1]);
                for (let i = 1; i < screenPoints.length; i++) {
                    ctx.lineTo(screenPoints[i][0], screenPoints[i][1]);
                }
                ctx.closePath();
                ctx.clip();

                // Vẽ layer nét trong vùng clip
                this.drawLayer(ctx, layer);
                ctx.restore();

            });
        }

        drawFocusAnnotations(ctx, state) {
            if (!state.focusRegions || state.focusRegions.length === 0) return;
            state.focusRegions.forEach(fr => {
                const layer = state.layers.find(item => item.id === fr.selectedLayerId && item.visible);
                const points = fr.pointsWorld || [];
                if (!layer || points.length < 3) return;
                const screenPoints = points.map(point => this.worldToScreen(point[0], point[1]));
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(screenPoints[0][0], screenPoints[0][1]);
                for (let i = 1; i < screenPoints.length; i++) {
                    ctx.lineTo(screenPoints[i][0], screenPoints[i][1]);
                }
                ctx.closePath();
                ctx.strokeStyle = '#10b981';
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 4]);
                ctx.stroke();

                // Label tag
                ctx.fillStyle = '#10b981';
                ctx.font = 'bold 11px Outfit, sans-serif';
                ctx.fillText(`★ Focus: ${layer.sourceId.substring(0, 15)}`, screenPoints[0][0] + 4, screenPoints[0][1] - 4);
                ctx.restore();
            });
        }

        drawKeepRegion(ctx, state) {
            const region = state.cropRegion;
            if (!region || !region.pointsWorld || region.pointsWorld.length < 3) return;
            const points = region.pointsWorld.map(p => this.worldToScreen(p[0], p[1]));
            const w = this.cssWidth || (this.canvas.width / (this.dpr || 1));
            const h = this.cssHeight || (this.canvas.height / (this.dpr || 1));

            ctx.save();
            // Nền đen bán trong suốt che toàn bộ phần ngoài vùng crop (Dim outside mask)
            ctx.beginPath();
            ctx.rect(0, 0, w, h);
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = points.length - 1; i >= 0; i--) {
                ctx.lineTo(points[i][0], points[i][1]);
            }
            ctx.closePath();
            ctx.fillStyle = 'rgba(0, 0, 0, 1)';
            ctx.globalCompositeOperation = 'destination-out';
            ctx.fill('evenodd');
            ctx.restore();
        }

        drawCropAnnotation(ctx, state) {
            const region = state.cropDraft || state.cropRegion;
            if (!region || !region.pointsWorld || region.pointsWorld.length < 3) return;
            const points = region.pointsWorld.map(point => this.worldToScreen(point[0], point[1]));
            const w = this.cssWidth || this.canvas.width / this.dpr;
            const h = this.cssHeight || this.canvas.height / this.dpr;
            ctx.save();
            if (state.cropDraft) {
                ctx.beginPath();
                ctx.rect(0, 0, w, h);
                ctx.moveTo(points[0][0], points[0][1]);
                for (let i = points.length - 1; i >= 0; i--) ctx.lineTo(points[i][0], points[i][1]);
                ctx.closePath();
                ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
                ctx.fill('evenodd');
            }
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; i++) {
                ctx.lineTo(points[i][0], points[i][1]);
            }
            ctx.closePath();
            ctx.strokeStyle = '#f59e0b';
            ctx.lineWidth = 2.5;
            ctx.setLineDash([6, 3]);
            ctx.stroke();

            ctx.fillStyle = '#f59e0b';
            ctx.font = 'bold 12px Outfit, sans-serif';
            ctx.fillText(state.cropDraft ? 'CROP DRAFT - Apply hoặc Cancel' : 'CROP ĐÃ ÁP DỤNG', points[0][0] + 6, points[0][1] - 8);
            ctx.restore();
        }

        drawExclusionStrokes(ctx, state, preMaskCanvas) {
            if (!state.maskRegions || state.maskRegions.length === 0) return;

            ctx.save();
            [...state.maskRegions].sort((a, b) => (a.order || 0) - (b.order || 0)).forEach(stroke => {
                if (!stroke.pointsWorld || stroke.pointsWorld.length === 0) return;
                const isExclude = (stroke.operation !== 'restore');
                const radiusScreen = stroke.radiusWorld * this.viewport.scale;

                ctx.globalCompositeOperation = isExclude ? 'destination-out' : 'source-over';
                ctx.strokeStyle = 'rgba(0, 0, 0, 1)';
                ctx.fillStyle = 'rgba(0, 0, 0, 1)';
                ctx.lineWidth = Math.max(2, radiusScreen * 2);
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';

                const screenPts = stroke.pointsWorld.map(p => this.worldToScreen(p[0], p[1]));
                ctx.beginPath();
                if (screenPts.length === 1) {
                    ctx.arc(screenPts[0][0], screenPts[0][1], Math.max(1, radiusScreen), 0, Math.PI * 2);
                } else {
                    ctx.moveTo(screenPts[0][0], screenPts[0][1]);
                    for (let i = 1; i < screenPts.length; i++) {
                        ctx.lineTo(screenPts[i][0], screenPts[i][1]);
                    }
                }
                if (isExclude) {
                    if (screenPts.length === 1) ctx.fill();
                    else ctx.stroke();
                } else {
                    const w = this.cssWidth || this.canvas.width / this.dpr;
                    const h = this.cssHeight || this.canvas.height / this.dpr;
                    const restoreCtx = this.restoreCanvas.getContext('2d');
                    restoreCtx.setTransform(1, 0, 0, 1, 0, 0);
                    restoreCtx.globalCompositeOperation = 'source-over';
                    restoreCtx.clearRect(0, 0, this.restoreCanvas.width, this.restoreCanvas.height);
                    restoreCtx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
                    restoreCtx.strokeStyle = '#000';
                    restoreCtx.fillStyle = '#000';
                    restoreCtx.lineWidth = Math.max(2, radiusScreen * 2);
                    restoreCtx.lineCap = 'round';
                    restoreCtx.lineJoin = 'round';
                    restoreCtx.beginPath();
                    if (screenPts.length === 1) {
                        restoreCtx.arc(screenPts[0][0], screenPts[0][1], Math.max(1, radiusScreen), 0, Math.PI * 2);
                        restoreCtx.fill();
                    } else {
                        restoreCtx.moveTo(screenPts[0][0], screenPts[0][1]);
                        for (let i = 1; i < screenPts.length; i++) restoreCtx.lineTo(screenPts[i][0], screenPts[i][1]);
                        restoreCtx.stroke();
                    }
                    restoreCtx.setTransform(1, 0, 0, 1, 0, 0);
                    restoreCtx.globalCompositeOperation = 'source-in';
                    restoreCtx.drawImage(preMaskCanvas, 0, 0);
                    ctx.save();
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.drawImage(this.restoreCanvas, 0, 0, w, h);
                    ctx.restore();
                }
            });
            ctx.globalCompositeOperation = 'source-over';
            ctx.restore();
        }

        getRegionBounds(region) {
            const points = region && region.pointsWorld ? region.pointsWorld : [];
            if (points.length === 0) return null;
            const radius = region.shapeType === 'brush' ? Number(region.radiusWorld || 0) : 0;
            const xs = points.map(point => point[0]);
            const ys = points.map(point => point[1]);
            return [Math.min(...xs) - radius, Math.min(...ys) - radius, Math.max(...xs) + radius, Math.max(...ys) + radius];
        }

        drawRegionSelections(ctx, state) {
            const selected = ProjectStore.getSelectedRegions().all;
            selected.forEach(region => {
                const bounds = this.getRegionBounds(region);
                if (!bounds) return;
                const p0 = this.worldToScreen(bounds[0], bounds[1]);
                const p1 = this.worldToScreen(bounds[2], bounds[3]);
                ctx.save();
                ctx.strokeStyle = region.locked ? '#94a3b8' : '#38bdf8';
                ctx.lineWidth = 2;
                ctx.setLineDash(region.locked ? [3, 3] : []);
                ctx.strokeRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
                if (!region.locked && selected.length === 1) {
                    [[p0[0], p0[1]], [p1[0], p0[1]], [p1[0], p1[1]], [p0[0], p1[1]]].forEach(([x, y]) => {
                        ctx.fillStyle = '#fff';
                        ctx.fillRect(x - 4, y - 4, 8, 8);
                        ctx.strokeRect(x - 4, y - 4, 8, 8);
                    });
                }
                ctx.restore();
            });

            if (this.regionMarquee) {
                const [x0, y0] = this.regionMarquee.startScreen;
                const [x1, y1] = this.mouseScreenPos;
                ctx.save();
                ctx.fillStyle = 'rgba(56, 189, 248, 0.12)';
                ctx.strokeStyle = '#38bdf8';
                ctx.setLineDash([5, 3]);
                ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
                ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
                ctx.restore();
            }
        }

        pointInPolygon(point, polygon) {
            let inside = false;
            for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
                const xi = polygon[i][0], yi = polygon[i][1];
                const xj = polygon[j][0], yj = polygon[j][1];
                if (((yi > point[1]) !== (yj > point[1])) &&
                    point[0] < (xj - xi) * (point[1] - yi) / ((yj - yi) || 1e-12) + xi) inside = !inside;
            }
            return inside;
        }

        distanceToSegment(point, a, b) {
            const dx = b[0] - a[0], dy = b[1] - a[1];
            const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
            return Math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy));
        }

        hitTestRegions(worldPoint) {
            const state = ProjectStore.getState();
            const candidates = [
                ...[...state.maskRegions].reverse().map(region => ({ kind: 'mask', region })),
                ...[...state.focusRegions].reverse().map(region => ({ kind: 'focus', region })),
                ...(state.cropRegion ? [{ kind: 'crop', region: state.cropRegion }] : [])
            ];
            for (const item of candidates) {
                const points = item.region.pointsWorld || [];
                if (item.region.shapeType === 'brush') {
                    const radius = Number(item.region.radiusWorld || 0) + 6 / this.viewport.scale;
                    for (let i = 0; i < points.length; i++) {
                        if (i === 0 && Math.hypot(worldPoint[0] - points[i][0], worldPoint[1] - points[i][1]) <= radius) return item;
                        if (i > 0 && this.distanceToSegment(worldPoint, points[i - 1], points[i]) <= radius) return item;
                    }
                } else if (points.length >= 3 && this.pointInPolygon(worldPoint, points)) return item;
            }
            return null;
        }

        hitTestRegionHandle(mouseScreen) {
            const selected = ProjectStore.getSelectedRegions().all;
            if (selected.length !== 1 || selected[0].locked) return null;
            const bounds = this.getRegionBounds(selected[0]);
            if (!bounds) return null;
            const p0 = this.worldToScreen(bounds[0], bounds[1]);
            const p1 = this.worldToScreen(bounds[2], bounds[3]);
            const corners = [[p0[0], p0[1]], [p1[0], p0[1]], [p1[0], p1[1]], [p0[0], p1[1]]];
            for (let i = 0; i < corners.length; i++) {
                if (Math.hypot(mouseScreen[0] - corners[i][0], mouseScreen[1] - corners[i][1]) <= 10) return ['tl', 'tr', 'br', 'bl'][i];
            }
            return null;
        }

        startRegionTransform(mode, handle, mouseWorld) {
            ProjectStore.expandSelectionToGroups();
            const selected = ProjectStore.getSelectedRegions().all.filter(region => !region.locked);
            if (selected.length === 0) return false;
            ProjectStore.beginTransaction(mode === 'region_moving' ? 'Di chuyển vùng' : 'Đổi kích thước vùng', 'region_transform');
            this.interaction.mode = mode;
            this.interaction.activeHandle = handle;
            this.interaction.startWorld = [...mouseWorld];
            this.interaction.initialRegions = selected.map(region => ({ region, pointsWorld: region.pointsWorld.map(point => [...point]), radiusWorld: region.radiusWorld }));
            const allBounds = selected.map(region => this.getRegionBounds(region));
            this.interaction.regionBounds = [
                Math.min(...allBounds.map(bounds => bounds[0])), Math.min(...allBounds.map(bounds => bounds[1])),
                Math.max(...allBounds.map(bounds => bounds[2])), Math.max(...allBounds.map(bounds => bounds[3]))
            ];
            return true;
        }

        updateRegionBounds(region) {
            const bounds = this.getRegionBounds(region);
            if (bounds) region.boundingRect = [bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]];
            region.updatedAt = new Date().toISOString();
        }

        drawDrawingDrafts(ctx) {
            // 1. Rectangle Drag Marquee
            if (this.toolMode === 'rect' && this.interaction.mode === 'drawing_rect') {
                const s0 = this.interaction.startScreen;
                const s1 = this.mouseScreenPos;
                const sx = Math.min(s0[0], s1[0]);
                const sy = Math.min(s0[1], s1[1]);
                const sw = Math.abs(s1[0] - s0[0]);
                const sh = Math.abs(s1[1] - s0[1]);

                ctx.save();
                ctx.fillStyle = 'rgba(6, 182, 212, 0.2)';
                ctx.fillRect(sx, sy, sw, sh);
                ctx.strokeStyle = '#06b6d4';
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 3]);
                ctx.strokeRect(sx, sy, sw, sh);

                const ww = Math.round(sw / this.viewport.scale);
                const wh = Math.round(sh / this.viewport.scale);
                ctx.fillStyle = '#06b6d4';
                ctx.font = 'bold 11px Outfit, sans-serif';
                ctx.fillText(`📐 ${ww} × ${wh} px`, sx + 6, sy - 6);
                ctx.restore();
            }

            // 2. Polygon Draft Points
            if (this.polygonDraftPoints.length > 0) {
                const pts = this.polygonDraftPoints.map(p => this.worldToScreen(p[0], p[1]));
                ctx.save();
                ctx.strokeStyle = '#06b6d4';
                ctx.lineWidth = 2;
                ctx.setLineDash([4, 2]);

                ctx.beginPath();
                ctx.moveTo(pts[0][0], pts[0][1]);
                for (let i = 1; i < pts.length; i++) {
                    ctx.lineTo(pts[i][0], pts[i][1]);
                }
                // Live line to cursor
                ctx.lineTo(this.mouseScreenPos[0], this.mouseScreenPos[1]);
                ctx.stroke();

                // Draw vertices
                pts.forEach(([px, py], i) => {
                    ctx.fillStyle = (i === 0) ? '#ec4899' : '#06b6d4';
                    ctx.beginPath();
                    ctx.arc(px, py, (i === 0) ? 6 : 4, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.strokeStyle = '#ffffff';
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                });

                ctx.fillStyle = '#ec4899';
                ctx.font = 'bold 11px Outfit, sans-serif';
                ctx.fillText(`Click điểm đầu để khép kín`, pts[0][0] + 10, pts[0][1] - 10);
                ctx.restore();
            }

            // 3. Lasso Draft Path (Smooth & Closed polygon preview)
            if (this.lassoDraftPoints.length > 1) {
                const pts = this.lassoDraftPoints.map(p => this.worldToScreen(p[0], p[1]));
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(pts[0][0], pts[0][1]);
                for (let i = 1; i < pts.length; i++) {
                    ctx.lineTo(pts[i][0], pts[i][1]);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(168, 85, 247, 0.22)';
                ctx.fill();

                ctx.strokeStyle = '#c084fc';
                ctx.lineWidth = 2.5;
                ctx.stroke();

                // Dashed line from cursor to start
                ctx.beginPath();
                ctx.moveTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
                ctx.lineTo(pts[0][0], pts[0][1]);
                ctx.strokeStyle = 'rgba(236, 72, 153, 0.7)';
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 4]);
                ctx.stroke();

                ctx.fillStyle = '#c084fc';
                ctx.font = 'bold 11px Outfit, sans-serif';
                ctx.fillText(`✏️ Vẽ tự do (Nhả chuột để chọn)`, pts[0][0] + 10, pts[0][1] - 10);
                ctx.restore();
            }

            // 4. Brush Drawing Live Draft (Tô cọ xóa / khôi phục hiển thị trực tiếp ngay khi vuốt chuột)
            if ((this.toolMode === 'brush_exclude' || this.toolMode === 'brush_restore') && this.brushDraftPoints.length > 0) {
                const isExclude = (this.toolMode === 'brush_exclude');
                const radiusScreen = this.brushRadius;
                ctx.save();
                ctx.strokeStyle = isExclude ? 'rgba(239, 68, 68, 0.65)' : 'rgba(20, 184, 166, 0.65)';
                ctx.fillStyle = isExclude ? 'rgba(239, 68, 68, 0.65)' : 'rgba(20, 184, 166, 0.65)';
                ctx.lineWidth = Math.max(2, radiusScreen * 2);
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';

                const screenPts = this.brushDraftPoints.map(p => this.worldToScreen(p[0], p[1]));
                if (screenPts.length === 1) {
                    ctx.beginPath();
                    ctx.arc(screenPts[0][0], screenPts[0][1], radiusScreen, 0, Math.PI * 2);
                    ctx.fill();
                } else {
                    ctx.beginPath();
                    ctx.moveTo(screenPts[0][0], screenPts[0][1]);
                    for (let i = 1; i < screenPts.length; i++) {
                        ctx.lineTo(screenPts[i][0], screenPts[i][1]);
                    }
                    ctx.stroke();
                }
                ctx.restore();
            }

            // 5. Crop Marquee Live Draft (Kéo chuột chọn khung cắt)
            if (this.isCropTool() && this.interaction.mode === 'drawing_crop') {
                const s0 = this.interaction.startScreen;
                const s1 = this.mouseScreenPos;
                const sx = Math.min(s0[0], s1[0]);
                const sy = Math.min(s0[1], s1[1]);
                const sw = Math.abs(s1[0] - s0[0]);
                const sh = Math.abs(s1[1] - s0[1]);

                ctx.save();
                ctx.fillStyle = 'rgba(245, 158, 11, 0.22)';
                ctx.fillRect(sx, sy, sw, sh);
                ctx.strokeStyle = '#f59e0b';
                ctx.lineWidth = 2.5;
                ctx.setLineDash([6, 4]);
                ctx.strokeRect(sx, sy, sw, sh);

                const ww = Math.round(sw / this.viewport.scale);
                const wh = Math.round(sh / this.viewport.scale);
                ctx.fillStyle = '#f59e0b';
                ctx.font = 'bold 12px Outfit, sans-serif';
                ctx.fillText(`✂️ Cắt: ${ww} × ${wh} px`, sx + 6, sy - 6);
                ctx.restore();
            }

            // 6. Reticle của Vùng Đã Ghim
            if (this.inspectorReticle && this.inspectorReticle.pointsWorld && this.inspectorReticle.pointsWorld.length >= 3) {
                const pts = this.inspectorReticle.pointsWorld.map(p => this.worldToScreen(p[0], p[1]));
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(pts[0][0], pts[0][1]);
                for (let i = 1; i < pts.length; i++) {
                    ctx.lineTo(pts[i][0], pts[i][1]);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(236, 72, 153, 0.15)';
                ctx.fill();
                ctx.strokeStyle = '#ec4899';
                ctx.lineWidth = 2;
                ctx.stroke();

                ctx.fillStyle = '#ec4899';
                ctx.font = 'bold 11px Outfit, sans-serif';
                ctx.fillText(`📌 VÙNG ĐÃ CHỌN`, pts[0][0] + 6, pts[0][1] - 8);
                ctx.restore();
            }
        }

        drawBrushCursor(ctx) {
            const [mx, my] = this.mouseScreenPos;
            const r = this.brushRadius;
            const isExclude = (this.toolMode === 'brush_exclude');

            ctx.save();
            ctx.beginPath();
            ctx.arc(mx, my, r, 0, Math.PI * 2);
            ctx.fillStyle = isExclude ? 'rgba(239, 68, 68, 0.25)' : 'rgba(20, 184, 166, 0.25)';
            ctx.fill();
            ctx.strokeStyle = isExclude ? '#ef4444' : '#14b8a6';
            ctx.lineWidth = 1.5;
            ctx.stroke();
            ctx.restore();
        }

        drawBackgroundGrid(ctx, w, h) {
            // The checkerboard belongs to the container CSS, not the alpha bitmap.
        }

        drawLayer(ctx, layer) {
            const img = this.imageCache.get(this.getLayerCacheKey(layer));
            const sw = layer.sourceWidth || 2000;
            const sh = layer.sourceHeight || 1500;

            ctx.save();
            const w = this.cssWidth || (this.canvas.width / (this.dpr || 1));
            const h = this.cssHeight || (this.canvas.height / (this.dpr || 1));

            // Viewport Transform (CSS pixels)
            ctx.translate(w / 2, h / 2);
            ctx.scale(this.viewport.scale, this.viewport.scale);
            ctx.translate(this.viewport.x, this.viewport.y);

            // Layer Transform 3x3
            const m = layer.sourceToWorld;
            ctx.transform(m[0], m[3], m[1], m[4], m[2], m[5]);

            ctx.globalAlpha = layer.opacity !== undefined ? layer.opacity : 1.0;
            
            let filterStr = '';
            if (layer.brightness !== 1.0) filterStr += `brightness(${layer.brightness * 100}%) `;
            if (layer.contrast !== 1.0) filterStr += `contrast(${layer.contrast * 100}%) `;
            if (layer.saturation !== 1.0) filterStr += `saturate(${layer.saturation * 100}%) `;
            if (filterStr) ctx.filter = filterStr.trim();

            if (img && img.complete) {
                ctx.drawImage(img, 0, 0, sw, sh);
            } else {
                ctx.fillStyle = 'rgba(99, 102, 241, 0.2)';
                ctx.fillRect(0, 0, sw, sh);
                ctx.strokeStyle = '#6366f1';
                ctx.lineWidth = 4;
                ctx.strokeRect(0, 0, sw, sh);
            }

            ctx.restore();
        }

        drawSelectionBox(ctx, layer) {
            const sw = layer.sourceWidth || 2000;
            const sh = layer.sourceHeight || 1500;
            const m = layer.sourceToWorld;

            const p0 = this.worldToScreen(...MatrixUtils.transformPoint(m, 0, 0));
            const p1 = this.worldToScreen(...MatrixUtils.transformPoint(m, sw, 0));
            const p2 = this.worldToScreen(...MatrixUtils.transformPoint(m, sw, sh));
            const p3 = this.worldToScreen(...MatrixUtils.transformPoint(m, 0, sh));

            ctx.save();
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);

            ctx.beginPath();
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p1[0], p1[1]);
            ctx.lineTo(p2[0], p2[1]);
            ctx.lineTo(p3[0], p3[1]);
            ctx.closePath();
            ctx.stroke();
            ctx.setLineDash([]);

            // 4 Handles
            [p0, p1, p2, p3].forEach(([cx, cy]) => {
                ctx.fillStyle = '#ffffff';
                ctx.strokeStyle = '#0284c7';
                ctx.lineWidth = 2;
                ctx.fillRect(cx - 5, cy - 5, 10, 10);
                ctx.strokeRect(cx - 5, cy - 5, 10, 10);
            });

            // Rotation Handle
            const topMid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
            const angle = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);
            const rotDist = 28;
            const rotHandle = [
                topMid[0] - Math.sin(angle) * rotDist,
                topMid[1] + Math.cos(angle) * rotDist
            ];

            ctx.beginPath();
            ctx.moveTo(topMid[0], topMid[1]);
            ctx.lineTo(rotHandle[0], rotHandle[1]);
            ctx.strokeStyle = '#38bdf8';
            ctx.stroke();

            ctx.beginPath();
            ctx.arc(rotHandle[0], rotHandle[1], 6, 0, Math.PI * 2);
            ctx.fillStyle = '#ec4899';
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            ctx.stroke();

            ctx.restore();
        }

        // ==========================================
        // Event Handling & Unified Pointer Events
        // ==========================================
        bindEvents() {
            const canvas = this.canvas;

            canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
                const mousePos = [e.offsetX, e.offsetY];
                const worldBefore = this.screenToWorld(...mousePos);

                this.viewport.scale = Math.max(0.01, Math.min(10.0, this.viewport.scale * zoomFactor));
                const worldAfter = this.screenToWorld(...mousePos);

                this.viewport.x += (worldAfter[0] - worldBefore[0]);
                this.viewport.y += (worldAfter[1] - worldBefore[1]);
                this.persistViewport();
                this.requestRender();
            });

            canvas.addEventListener('pointermove', (e) => {
                const rect = canvas.getBoundingClientRect();
                this.mouseScreenPos = [e.clientX - rect.left, e.clientY - rect.top];
                this.mouseWorldPos = this.screenToWorld(...this.mouseScreenPos);

                if (this.onPointerHover) {
                    this.onPointerHover(this.mouseWorldPos, this.mouseScreenPos);
                }

                // 0. Mini-map Drag Panning
                if (this.interaction.mode === 'minimap_pan') {
                    this.handleMiniMapPan(this.mouseScreenPos);
                    return;
                }

                // 1. Lasso Dragging (Tối ưu mượt mà với khoảng cách tối thiểu)
                if ((this.toolMode === 'lasso' || this.toolMode === 'crop_lasso') && this.interaction.mode === 'drawing_lasso') {
                    if (this.lassoDraftPoints.length > 0) {
                        const lastPt = this.lassoDraftPoints[this.lassoDraftPoints.length - 1];
                        const lastScreen = this.worldToScreen(lastPt[0], lastPt[1]);
                        const dist = Math.hypot(this.mouseScreenPos[0] - lastScreen[0], this.mouseScreenPos[1] - lastScreen[1]);
                        if (dist >= 3) {
                            this.lassoDraftPoints.push([...this.mouseWorldPos]);
                            this.requestRender();
                        }
                    } else {
                        this.lassoDraftPoints.push([...this.mouseWorldPos]);
                        this.requestRender();
                    }
                    return;
                }

                // 2. Brush Dragging
                if ((this.toolMode === 'brush_exclude' || this.toolMode === 'brush_restore') && this.interaction.mode === 'brushing') {
                    this.brushDraftPoints.push([...this.mouseWorldPos]);
                    this.requestRender();
                    return;
                }

                // 3. Rectangle / Crop Dragging
                if ((this.toolMode === 'rect' && this.interaction.mode === 'drawing_rect') ||
                    (this.toolMode === 'crop' && this.interaction.mode === 'drawing_crop')) {
                    this.requestRender();
                    return;
                }

                // 4. Polygon live preview
                if (this.polygonDraftPoints.length > 0) {
                    this.requestRender();
                    return;
                }

                // 5. Layer Transforms / Panning
                if (this.interaction.mode === 'panning') {
                    const dx = (this.mouseScreenPos[0] - this.interaction.startX) / this.viewport.scale;
                    const dy = (this.mouseScreenPos[1] - this.interaction.startY) / this.viewport.scale;
                    this.viewport.x += dx;
                    this.viewport.y += dy;
                    this.interaction.startX = this.mouseScreenPos[0];
                    this.interaction.startY = this.mouseScreenPos[1];
                    this.persistViewport();
                    this.requestRender();
                    return;
                }

                if (this.interaction.mode === 'region_moving') {
                    const dx = this.mouseWorldPos[0] - this.interaction.startWorld[0];
                    const dy = this.mouseWorldPos[1] - this.interaction.startWorld[1];
                    this.interaction.initialRegions.forEach(item => {
                        item.region.pointsWorld = item.pointsWorld.map(point => [point[0] + dx, point[1] + dy]);
                        this.updateRegionBounds(item.region);
                    });
                    this.requestRender();
                    return;
                }

                if (this.interaction.mode === 'region_scaling') {
                    const bounds = this.interaction.regionBounds;
                    const handle = this.interaction.activeHandle;
                    const anchorX = handle.includes('l') ? bounds[2] : bounds[0];
                    const anchorY = handle.includes('t') ? bounds[3] : bounds[1];
                    const sourceX = handle.includes('l') ? bounds[0] : bounds[2];
                    const sourceY = handle.includes('t') ? bounds[1] : bounds[3];
                    let scaleX = (this.mouseWorldPos[0] - anchorX) / ((sourceX - anchorX) || 1);
                    let scaleY = (this.mouseWorldPos[1] - anchorY) / ((sourceY - anchorY) || 1);
                    scaleX = Math.max(0.05, scaleX);
                    scaleY = Math.max(0.05, scaleY);
                    const hasBrush = this.interaction.initialRegions.some(item => item.region.shapeType === 'brush');
                    if (hasBrush || e.shiftKey) {
                        const uniform = Math.max(0.05, Math.min(scaleX, scaleY));
                        scaleX = uniform;
                        scaleY = uniform;
                    }
                    this.interaction.initialRegions.forEach(item => {
                        item.region.pointsWorld = item.pointsWorld.map(point => [
                            anchorX + (point[0] - anchorX) * scaleX,
                            anchorY + (point[1] - anchorY) * scaleY
                        ]);
                        if (item.region.shapeType === 'brush') item.region.radiusWorld = item.radiusWorld * scaleX;
                        this.updateRegionBounds(item.region);
                    });
                    this.requestRender();
                    return;
                }

                if (this.interaction.mode === 'region_marquee') {
                    this.requestRender();
                    return;
                }

                const selectedLayer = ProjectStore.getSelectedLayer();
                if (!selectedLayer || this.toolMode !== 'select') return;

                if (this.interaction.mode === 'moving') {
                    const dx = this.mouseWorldPos[0] - this.interaction.startX;
                    const dy = this.mouseWorldPos[1] - this.interaction.startY;
                    const t = MatrixUtils.translate(dx, dy);
                    const newMatrix = MatrixUtils.multiply(t, this.interaction.initialMatrix);
                    ProjectStore.updateLayerTransform(selectedLayer.id, newMatrix, true);
                    this.requestRender();
                } else if (this.interaction.mode === 'rotating') {
                    const center = this.interaction.initialCenter;
                    const curAngle = Math.atan2(this.mouseWorldPos[1] - center[1], this.mouseWorldPos[0] - center[0]);
                    const deltaAngle = curAngle - this.interaction.initialAngle;
                    
                    let finalAngle = deltaAngle;
                    if (e.shiftKey) {
                        const step = (15 * Math.PI) / 180;
                        finalAngle = Math.round(finalAngle / step) * step;
                    }

                    const t1 = MatrixUtils.translate(-center[0], -center[1]);
                    const r = MatrixUtils.rotate(finalAngle);
                    const t2 = MatrixUtils.translate(center[0], center[1]);
                    const newMatrix = MatrixUtils.multiply(t2, MatrixUtils.multiply(r, MatrixUtils.multiply(t1, this.interaction.initialMatrix)));
                    ProjectStore.updateLayerTransform(selectedLayer.id, newMatrix, true);
                    this.requestRender();
                } else if (this.interaction.mode === 'scaling') {
                    const center = this.interaction.initialCenter;
                    const initDist = Math.hypot(this.interaction.startX - center[0], this.interaction.startY - center[1]);
                    const curDist = Math.hypot(this.mouseWorldPos[0] - center[0], this.mouseWorldPos[1] - center[1]);
                    const scaleFactor = Math.max(0.1, curDist / Math.max(1, initDist));

                    const t1 = MatrixUtils.translate(-center[0], -center[1]);
                    const s = MatrixUtils.scale(scaleFactor, scaleFactor);
                    const t2 = MatrixUtils.translate(center[0], center[1]);
                    const newMatrix = MatrixUtils.multiply(t2, MatrixUtils.multiply(s, MatrixUtils.multiply(t1, this.interaction.initialMatrix)));
                    ProjectStore.updateLayerTransform(selectedLayer.id, newMatrix, true);
                    this.requestRender();
                }
            });

            canvas.addEventListener('pointerdown', (e) => {
                if (this.interaction.mode !== 'idle') return;
                const rect = canvas.getBoundingClientRect();
                const mouseScreen = [e.clientX - rect.left, e.clientY - rect.top];
                const mouseWorld = this.screenToWorld(...mouseScreen);
                this.mouseScreenPos = mouseScreen;
                this.mouseWorldPos = mouseWorld;
                this.interaction.pointerId = e.pointerId;

                // 0. Kiểm tra click vào Bản Đồ Thu Nhỏ (Mini-map)
                if (this.miniMapRect) {
                    const [mmX, mmY, mmW, mmH] = this.miniMapRect;
                    if (mouseScreen[0] >= mmX && mouseScreen[0] <= mmX + mmW && mouseScreen[1] >= mmY && mouseScreen[1] <= mmY + mmH) {
                        this.interaction.mode = 'minimap_pan';
                        try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                        this.handleMiniMapPan(mouseScreen);
                        return;
                    }
                }

                // Giữ chuột giữa hoặc Space để Pan bất kỳ lúc nào
                if (e.button === 1 || this.spacePressed) {
                    this.interaction.mode = 'panning';
                    this.interaction.startX = mouseScreen[0];
                    this.interaction.startY = mouseScreen[1];
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    return;
                }

                // 1. Tool Mode: Rectangle / Crop
                if (this.toolMode === 'rect' || this.toolMode === 'crop') {
                    this.interaction.mode = this.toolMode === 'crop' ? 'drawing_crop' : 'drawing_rect';
                    this.interaction.startScreen = mouseScreen;
                    this.interaction.startWorld = mouseWorld;
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    return;
                }

                // 2. Tool Mode: Polygon
                if (this.toolMode === 'polygon' || this.toolMode === 'crop_polygon') {
                    if (this.polygonDraftPoints.length > 2) {
                        // Kiểm tra nếu click gần điểm đầu tiên (<= 20px) -> Hoàn tất Polygon
                        const firstScreen = this.worldToScreen(this.polygonDraftPoints[0][0], this.polygonDraftPoints[0][1]);
                        if (Math.hypot(mouseScreen[0] - firstScreen[0], mouseScreen[1] - firstScreen[1]) < 20) {
                            this.commitPolygonRegion();
                            return;
                        }
                    }
                    this.polygonDraftPoints.push([...mouseWorld]);
                    this.requestRender();
                    return;
                }

                // 3. Tool Mode: Lasso
                if (this.toolMode === 'lasso' || this.toolMode === 'crop_lasso') {
                    this.interaction.mode = 'drawing_lasso';
                    this.lassoDraftPoints = [[...mouseWorld]];
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    this.requestRender();
                    return;
                }

                // 4. Tool Mode: Brush (Exclude / Restore)
                if (this.toolMode === 'brush_exclude' || this.toolMode === 'brush_restore') {
                    this.interaction.mode = 'brushing';
                    this.brushDraftPoints = [[...mouseWorld]];
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    this.requestRender();
                    return;
                }

                // 5. Tool Mode: Select (Transform / Move / Click chọn layer)
                const regionHandle = this.hitTestRegionHandle(mouseScreen);
                if (regionHandle && this.startRegionTransform('region_scaling', regionHandle, mouseWorld)) {
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    return;
                }

                const hitRegion = this.hitTestRegions(mouseWorld);
                if (hitRegion) {
                    ProjectStore.selectRegion(hitRegion.region.id, e.shiftKey);
                    ProjectStore.expandSelectionToGroups();
                    if (!e.shiftKey && !hitRegion.region.locked && this.startRegionTransform('region_moving', null, mouseWorld)) {
                        try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    }
                    this.requestRender();
                    return;
                }

                if (e.shiftKey) {
                    this.regionMarquee = { startScreen: mouseScreen, startWorld: mouseWorld };
                    this.interaction.mode = 'region_marquee';
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                    this.requestRender();
                    return;
                }

                ProjectStore.selectRegions([]);
                const selectedLayer = ProjectStore.getSelectedLayer();
                if (selectedLayer && !selectedLayer.locked) {
                    const handle = this.hitTestHandles(selectedLayer, mouseScreen);
                    if (handle) {
                        try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                        this.startTransform(handle, selectedLayer, mouseWorld, mouseScreen);
                        return;
                    }
                }

                const hitLayer = this.hitTestLayers(mouseWorld);
                if (hitLayer) {
                    const prevId = ProjectStore.getState().selection[0];
                    if (prevId && prevId !== hitLayer.id && typeof window.resetImageToolsOnLayerChange === 'function') {
                        window.resetImageToolsOnLayerChange();
                    }
                    ProjectStore.selectLayer(hitLayer.id);
                    if (!hitLayer.locked) {
                        try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                        this.startTransform('move', hitLayer, mouseWorld, mouseScreen);
                    }
                } else {
                    ProjectStore.selectLayer(null);
                    this.interaction.mode = 'panning';
                    this.interaction.startX = mouseScreen[0];
                    this.interaction.startY = mouseScreen[1];
                    try { canvas.setPointerCapture(e.pointerId); } catch(ex){}
                }
                this.requestRender();
            });

            window.addEventListener('pointerup', (e) => {
                if (this.interaction.pointerId !== null && this.interaction.pointerId !== undefined && e.pointerId !== this.interaction.pointerId) return;
                // 0. Kết thúc Mini-map Pan
                if (this.interaction.mode === 'minimap_pan') {
                    this.interaction.mode = 'idle';
                    return;
                }

                // 1. Hoàn tất kéo Rectangle / Crop
                if ((this.toolMode === 'rect' && this.interaction.mode === 'drawing_rect') ||
                    (this.toolMode === 'crop' && this.interaction.mode === 'drawing_crop')) {
                    const isCrop = this.toolMode === 'crop';
                    this.interaction.mode = 'idle';
                    const w0 = this.interaction.startWorld;
                    const w1 = this.mouseWorldPos;
                    const minX = Math.min(w0[0], w1[0]);
                    const minY = Math.min(w0[1], w1[1]);
                    const maxX = Math.max(w0[0], w1[0]);
                    const maxY = Math.max(w0[1], w1[1]);
                    const ww = maxX - minX;
                    const wh = maxY - minY;

                    if (ww >= 10 && wh >= 10) {
                        const pointsWorld = [
                            [minX, minY],
                            [maxX, minY],
                            [maxX, maxY],
                            [minX, maxY]
                        ];
                        this.commitRegion(isCrop ? 'crop' : 'rectangle', pointsWorld, [minX, minY, ww, wh]);
                    }
                    this.requestRender();
                    return;
                }

                // 2. Hoàn tất kéo Lasso (Tự động khép kín & tính độ nét ngay)
                if ((this.toolMode === 'lasso' || this.toolMode === 'crop_lasso') && this.interaction.mode === 'drawing_lasso') {
                    this.interaction.mode = 'idle';
                    if (this.lassoDraftPoints.length >= 3) {
                        const simplified = this.simplifyPoints(this.lassoDraftPoints, 2.0);
                        const xs = simplified.map(p => p[0]);
                        const ys = simplified.map(p => p[1]);
                        const minX = Math.min(...xs), minY = Math.min(...ys);
                        const maxX = Math.max(...xs), maxY = Math.max(...ys);

                        this.commitRegion(this.toolMode === 'crop_lasso' ? 'crop_lasso' : 'lasso', simplified, [minX, minY, maxX - minX, maxY - minY]);
                    }
                    this.lassoDraftPoints = [];
                    this.requestRender();
                    return;
                }

                // 3. Hoàn tất nét Brush
                if ((this.toolMode === 'brush_exclude' || this.toolMode === 'brush_restore') && this.interaction.mode === 'brushing') {
                    this.interaction.mode = 'idle';
                    if (this.brushDraftPoints.length > 0) {
                        const simplified = this.simplifyPoints(this.brushDraftPoints, 3.0);
                        const radiusWorld = this.brushRadius / this.viewport.scale;
                        ProjectStore.addExclusionStroke({
                            pointsWorld: simplified,
                            radiusWorld: radiusWorld,
                            operation: (this.toolMode === 'brush_restore' ? 'restore' : 'exclude')
                        });
                    }
                    this.brushDraftPoints = [];
                    this.requestRender();
                    return;
                }

                // 4. Kết thúc Transform
                if (this.interaction.mode === 'region_moving' || this.interaction.mode === 'region_scaling') {
                    this.interaction.initialRegions.forEach(item => {
                        if (item.region.geometryRevision !== undefined) item.region.geometryRevision = Number(item.region.geometryRevision || 0) + 1;
                    });
                    ProjectStore.commitTransaction(this.interaction.mode === 'region_moving' ? 'Di chuyển vùng' : 'Đổi kích thước vùng');
                    this.interaction.mode = 'idle';
                    this.interaction.activeHandle = null;
                    return;
                }

                if (this.interaction.mode === 'region_marquee' && this.regionMarquee) {
                    const start = this.regionMarquee.startWorld;
                    const end = this.mouseWorldPos;
                    const marquee = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])];
                    const state = ProjectStore.getState();
                    const regions = [...state.focusRegions, ...state.maskRegions, ...(state.cropRegion ? [state.cropRegion] : [])];
                    const ids = regions.filter(region => {
                        const bounds = this.getRegionBounds(region);
                        return bounds && bounds[0] <= marquee[2] && bounds[2] >= marquee[0] && bounds[1] <= marquee[3] && bounds[3] >= marquee[1];
                    }).map(region => region.id);
                    ProjectStore.selectRegions(ids, true);
                    ProjectStore.expandSelectionToGroups();
                    this.regionMarquee = null;
                    this.interaction.mode = 'idle';
                    this.requestRender();
                    return;
                }

                if (this.interaction.mode !== 'idle' && this.interaction.mode !== 'panning') {
                    ProjectStore.commitTransaction('Transform Layer');
                }
                this.interaction.mode = 'idle';
                this.interaction.activeHandle = null;
                this.interaction.pointerId = null;
            });

            const cancelPointerGesture = () => {
                if (this.interaction.mode !== 'idle') this.cancelDraft(true);
            };
            canvas.addEventListener('pointercancel', cancelPointerGesture);
            canvas.addEventListener('lostpointercapture', cancelPointerGesture);

            // Double-click để hoàn tất Polygon nhanh
            canvas.addEventListener('dblclick', () => {
                if ((this.toolMode === 'polygon' || this.toolMode === 'crop_polygon') && this.polygonDraftPoints.length >= 3) {
                    this.commitPolygonRegion();
                }
            });
        }

        handleMiniMapPan(screenPt) {
            const state = ProjectStore.getState();
            if (!state.layers || state.layers.length === 0 || !this.miniMapRect) return;

            const [mmX, mmY, mmW, mmH] = this.miniMapRect;

            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            state.layers.forEach(l => {
                if (!l.visible) return;
                const sw = l.sourceWidth || 2000;
                const sh = l.sourceHeight || 1500;
                const corners = [[0, 0], [sw, 0], [sw, sh], [0, sh]];
                corners.forEach(([cx, cy]) => {
                    const [wx, wy] = MatrixUtils.transformPoint(l.sourceToWorld, cx, cy);
                    minX = Math.min(minX, wx);
                    minY = Math.min(minY, wy);
                    maxX = Math.max(maxX, wx);
                    maxY = Math.max(maxY, wy);
                });
            });

            if (!isFinite(minX) || !isFinite(maxX)) return;
            const totalW = Math.max(1, maxX - minX);
            const totalH = Math.max(1, maxY - minY);

            const scaleX = (mmW - 16) / totalW;
            const scaleY = (mmH - 16) / totalH;
            const mmScale = Math.min(scaleX, scaleY);

            const offsetX = mmX + (mmW - totalW * mmScale) / 2;
            const offsetY = mmY + (mmH - totalH * mmScale) / 2;

            const targetWorldX = minX + (screenPt[0] - offsetX) / mmScale;
            const targetWorldY = minY + (screenPt[1] - offsetY) / mmScale;

            this.viewport.x = -targetWorldX;
            this.viewport.y = -targetWorldY;
            this.requestRender();
        }

        commitPolygonRegion() {
            if (this.polygonDraftPoints.length < 3) return;
            const pointsWorld = [...this.polygonDraftPoints];
            const xs = pointsWorld.map(p => p[0]);
            const ys = pointsWorld.map(p => p[1]);
            const minX = Math.min(...xs), minY = Math.min(...ys);
            const maxX = Math.max(...xs), maxY = Math.max(...ys);

            this.polygonDraftPoints = [];
            this.commitRegion(this.toolMode === 'crop_polygon' ? 'crop_polygon' : 'polygon', pointsWorld, [minX, minY, maxX - minX, maxY - minY]);
            this.requestRender();
        }

        commitRegion(shapeType, pointsWorld, boundingRect) {
            this.inspectorReticle = {
                shapeType: shapeType,
                pointsWorld: pointsWorld,
                boundingRect: boundingRect,
                isPinned: true
            };

            if (typeof this.onRegionSelected === 'function') {
                this.onRegionSelected({
                    shapeType: shapeType,
                    pointsWorld: pointsWorld,
                    boundingRect: boundingRect
                });
            }
        }

        simplifyPoints(pts, tolerance = 2.0) {
            if (pts.length <= 4) return pts;
            const res = [pts[0]];
            for (let i = 1; i < pts.length - 1; i++) {
                const prev = res[res.length - 1];
                const cur = pts[i];
                if (Math.hypot(cur[0] - prev[0], cur[1] - prev[1]) >= tolerance) {
                    res.push(cur);
                }
            }
            res.push(pts[pts.length - 1]);
            return res;
        }

        startTransform(handleType, layer, mouseWorld, mouseScreen) {
            ProjectStore.beginTransaction('Transform Layer', 'layer_transform');
            this.interaction.mode = handleType === 'move' ? 'moving' : (handleType === 'rot' ? 'rotating' : 'scaling');
            this.interaction.activeHandle = handleType;
            this.interaction.startX = mouseWorld[0];
            this.interaction.startY = mouseWorld[1];
            this.interaction.initialMatrix = [...layer.sourceToWorld];

            const sw = layer.sourceWidth || 2000;
            const sh = layer.sourceHeight || 1500;
            this.interaction.initialCenter = MatrixUtils.transformPoint(layer.sourceToWorld, sw / 2, sh / 2);
            
            const center = this.interaction.initialCenter;
            this.interaction.initialAngle = Math.atan2(mouseWorld[1] - center[1], mouseWorld[0] - center[0]);
        }

        hitTestHandles(layer, mouseScreen) {
            const sw = layer.sourceWidth || 2000;
            const sh = layer.sourceHeight || 1500;
            const m = layer.sourceToWorld;

            const p0 = this.worldToScreen(...MatrixUtils.transformPoint(m, 0, 0));
            const p1 = this.worldToScreen(...MatrixUtils.transformPoint(m, sw, 0));
            const p2 = this.worldToScreen(...MatrixUtils.transformPoint(m, sw, sh));
            const p3 = this.worldToScreen(...MatrixUtils.transformPoint(m, 0, sh));

            // Test Top Rotate Handle
            const topMid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
            const angle = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);
            const rotDist = 28;
            const rotHandle = [
                topMid[0] - Math.sin(angle) * rotDist,
                topMid[1] + Math.cos(angle) * rotDist
            ];
            if (Math.hypot(mouseScreen[0] - rotHandle[0], mouseScreen[1] - rotHandle[1]) < 12) {
                return 'rot';
            }

            // Test 4 Corners
            const corners = [p0, p1, p2, p3];
            for (let i = 0; i < corners.length; i++) {
                if (Math.hypot(mouseScreen[0] - corners[i][0], mouseScreen[1] - corners[i][1]) < 10) {
                    return ['tl', 'tr', 'br', 'bl'][i];
                }
            }

            return null;
        }

        hitTestLayers(mouseWorld) {
            const state = ProjectStore.getState();
            const sortedLayers = [...state.layers].sort((a, b) => b.zIndex - a.zIndex);

            for (const layer of sortedLayers) {
                if (!layer.visible) continue;
                const sw = layer.sourceWidth || 2000;
                const sh = layer.sourceHeight || 1500;
                const inv = MatrixUtils.inverse(layer.sourceToWorld);
                if (!inv) continue;

                const [sx, sy] = MatrixUtils.transformPoint(inv, mouseWorld[0], mouseWorld[1]);
                if (sx >= 0 && sx <= sw && sy >= 0 && sy <= sh) {
                    return layer;
                }
            }
            return null;
        }

        zoomToFit() {
            const state = ProjectStore.getState();
            if (!state.layers || state.layers.length === 0) return;

            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            state.layers.forEach(l => {
                if (!l.visible) return;
                const sw = l.sourceWidth || 2000;
                const sh = l.sourceHeight || 1500;
                const corners = [[0, 0], [sw, 0], [sw, sh], [0, sh]];
                corners.forEach(([cx, cy]) => {
                    const [wx, wy] = MatrixUtils.transformPoint(l.sourceToWorld, cx, cy);
                    minX = Math.min(minX, wx);
                    minY = Math.min(minY, wy);
                    maxX = Math.max(maxX, wx);
                    maxY = Math.max(maxY, wy);
                });
            });

            if (!isFinite(minX) || !isFinite(maxX)) return;
            const w = this.cssWidth || (this.canvas ? this.canvas.width / (this.dpr || 1) : 800);
            const h = this.cssHeight || (this.canvas ? this.canvas.height / (this.dpr || 1) : 600);
            const totalW = Math.max(10, maxX - minX);
            const totalH = Math.max(10, maxY - minY);

            const scale = Math.min((w - 60) / totalW, (h - 60) / totalH, 2.0);
            this.viewport.scale = Math.max(0.01, scale);
            this.viewport.x = (w / scale - totalW) / 2 - minX;
            this.viewport.y = (h / scale - totalH) / 2 - minY;
            this.requestRender();
        }

        fitToContent() {
            this.zoomToFit();
        }
    }

    return new Engine();
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CanvasEngine;
}
