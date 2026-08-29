/**
 * Feature: Project store state management, revision tracking, and command undo/redo history
 * Purpose: Complies with project architecture schemas and persistent specifications
 * Path: tool/image_alignment/frontend/project_store.js
 */

const ProjectStore = (function () {
    'use strict';

    class Store {
        constructor() {
            this.state = this.createDefaultState();
            this.activeTransaction = null;
            this.listeners = new Set();
            this.isDirty = false;
            this.autosaveTimer = null;
            this.selectedRegionIds = []; // Multi-selection for focus/mask/crop regions
            this.saveInFlight = false;
            this.saveQueued = false;
            this.saveGeneration = 0;
            this.autosaveConflict = null;
            this.autosaveRetryCount = 0;
            this.maxAutosaveRetries = 5;
        }

        createDefaultState() {
            return {
                id: 'default_project',
                version: 3,
                revision: 1,
                geometryRevision: 1,
                worldUnits: 'pixel',
                mode: 'auto', // 'auto' | 'manual'
                layers: [],
                viewport: {
                    manual: { x: 0, y: 0, scale: 0.2 },
                    auto: { center: [0.5, 0.5], zoom: null, rotation: 0, sourceKey: null }
                },
                selection: [], // array of selected layer IDs
                folderName: '',
                updatedAt: new Date().toISOString(),
                focusRegions: [], // FocusRegion items
                maskRegions: [],  // MaskRegion items (erase / restore brush)
                cropRegion: null, // Committed CropRegion
                cropDraft: null,  // Transient CropRegion being edited
                cropSettings: {
                    trimOutputBounds: true,
                    aspectRatio: null,
                    paddingWorld: 0
                },
                regionGroups: [], // RegionGroup items
                historyJournal: [], // Persistent undo/redo command journal
                historyCursor: 0
            };
        }

        subscribe(callback) {
            this.listeners.add(callback);
            return () => this.listeners.delete(callback);
        }

        notify(changeType) {
            this.state.updatedAt = new Date().toISOString();
            this.listeners.forEach(cb => {
                try { cb(this.state, changeType); } catch (e) { console.error('Store observer error:', e); }
            });
            this.scheduleAutosave();
        }

        loadState(newState) {
            this.activeTransaction = null;
            const raw = JSON.parse(JSON.stringify(newState));
            this.state.id = raw.id || 'default_project';
            this.state.version = raw.version || 3;
            this.state.revision = raw.revision || 1;
            this.state.geometryRevision = raw.geometryRevision || 1;
            this.state.worldUnits = raw.worldUnits || 'pixel';
            this.state.mode = raw.mode || 'auto';
            this.state.layers = Array.isArray(raw.layers) ? raw.layers : [];
            const defaultViewport = this.createDefaultState().viewport;
            this.state.viewport = raw.viewport && (raw.viewport.manual || raw.viewport.auto)
                ? Object.assign(defaultViewport, raw.viewport)
                : defaultViewport;
            this.state.selection = Array.isArray(raw.selection) ? raw.selection : [];
            this.state.folderName = raw.folderName || '';
            this.state.updatedAt = raw.updatedAt || new Date().toISOString();

            // Migrate FocusRegions
            this.state.focusRegions = (raw.focusRegions || []).map(fr => {
                let pts = fr.pointsWorld || [];
                if ((!pts || pts.length === 0) && fr.worldRect) {
                    const [rx, ry, rw, rh] = fr.worldRect;
                    pts = [[rx, ry], [rx + rw, ry], [rx + rw, ry + rh], [rx, ry + rh]];
                }
                const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
                const minX = xs.length ? Math.min(...xs) : 0, minY = ys.length ? Math.min(...ys) : 0;
                const maxX = xs.length ? Math.max(...xs) : 0, maxY = ys.length ? Math.max(...ys) : 0;
                return {
                    id: fr.id || ('fr_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4)),
                    shapeType: fr.shapeType || 'rectangle',
                    pointsWorld: pts,
                    selectedLayerId: fr.selectedLayerId || null,
                    featherWorldPx: Number(fr.featherWorldPx || fr.featherPx || 8),
                    featherPx: Number(fr.featherWorldPx || fr.featherPx || 8),
                    order: Number(fr.order || 0),
                    locked: Boolean(fr.locked),
                    geometryRevision: Number(fr.geometryRevision || 1),
                    boundingRect: [minX, minY, maxX - minX, maxY - minY],
                    createdAt: fr.createdAt || new Date().toISOString(),
                    updatedAt: fr.updatedAt || fr.createdAt || new Date().toISOString()
                };
            });

            // Migrate MaskRegions from exclusionStrokes if present
            const rawMasks = raw.maskRegions || raw.exclusionStrokes || [];
            this.state.maskRegions = rawMasks.map((mr, idx) => {
                const pts = mr.pointsWorld || [];
                const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
                const minX = xs.length ? Math.min(...xs) : 0, minY = ys.length ? Math.min(...ys) : 0;
                const maxX = xs.length ? Math.max(...xs) : 0, maxY = ys.length ? Math.max(...ys) : 0;
                return {
                    id: mr.id || ('mask_' + Date.now() + '_' + idx),
                    shapeType: mr.shapeType || 'brush',
                    pointsWorld: pts,
                    radiusWorld: Number(mr.radiusWorld || 20),
                    operation: mr.operation === 'restore' ? 'restore' : 'exclude',
                    order: Number(mr.order !== undefined ? mr.order : idx),
                    locked: Boolean(mr.locked),
                    boundingRect: [minX, minY, maxX - minX, maxY - minY],
                    createdAt: mr.createdAt || new Date().toISOString(),
                    updatedAt: mr.updatedAt || mr.createdAt || new Date().toISOString()
                };
            });

            // Migrate CropRegion from keepRegion if present
            const rawCrop = raw.cropRegion || raw.keepRegion;
            if (rawCrop && rawCrop.pointsWorld && rawCrop.pointsWorld.length >= 3) {
                const pts = rawCrop.pointsWorld;
                const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
                const minX = Math.min(...xs), minY = Math.min(...ys);
                const maxX = Math.max(...xs), maxY = Math.max(...ys);
                this.state.cropRegion = {
                    id: rawCrop.id || 'crop_main',
                    shapeType: rawCrop.shapeType || 'rectangle',
                    pointsWorld: pts,
                    locked: Boolean(rawCrop.locked),
                    boundingRect: [minX, minY, maxX - minX, maxY - minY],
                    updatedAt: rawCrop.updatedAt || new Date().toISOString()
                };
            } else {
                this.state.cropRegion = null;
            }

            this.state.cropDraft = null;
            this.state.cropSettings = Object.assign({ trimOutputBounds: true, aspectRatio: null, paddingWorld: 0 }, raw.cropSettings || {});
            this.state.regionGroups = Array.isArray(raw.regionGroups) ? raw.regionGroups : [];
            this.state.historyJournal = Array.isArray(raw.historyJournal) ? raw.historyJournal : [];
            this.state.historyCursor = raw.historyCursor === undefined
                ? this.state.historyJournal.length
                : Math.max(0, Math.min(Number(raw.historyCursor), this.state.historyJournal.length));

            this.selectedRegionIds = [];
            this.isDirty = false;
            this.notify('load');
        }

        getState() {
            return this.state;
        }

        // Atomic Project Reset (Section 13)
        newProject() {
            this.activeTransaction = null;
            this.state = this.createDefaultState();
            this.selectedRegionIds = [];
            this.isDirty = false;
            this.notify('newProject');
        }

        // ======================================================
        // Command Journal & Transaction Boundaries (Section 12)
        // ======================================================
        captureSnapshotPayload() {
            return {
                layers: JSON.parse(JSON.stringify(this.state.layers)),
                focusRegions: JSON.parse(JSON.stringify(this.state.focusRegions)),
                maskRegions: JSON.parse(JSON.stringify(this.state.maskRegions)),
                cropRegion: this.state.cropRegion ? JSON.parse(JSON.stringify(this.state.cropRegion)) : null,
                cropSettings: JSON.parse(JSON.stringify(this.state.cropSettings)),
                regionGroups: JSON.parse(JSON.stringify(this.state.regionGroups))
            };
        }

        beginTransaction(label = 'Action', type = 'generic') {
            if (this.activeTransaction) return this.activeTransaction;
            this.activeTransaction = {
                label,
                type,
                before: this.captureSnapshotPayload()
            };
            return this.activeTransaction;
        }

        commitTransaction(label) {
            if (!this.activeTransaction) return false;
            const tx = this.activeTransaction;
            this.activeTransaction = null;
            const after = this.captureSnapshotPayload();
            if (JSON.stringify(tx.before) === JSON.stringify(after)) return false;
            this.pushCommand(tx.type, label || tx.label, tx.before, after);
            this.notify(tx.type);
            return true;
        }

        cancelTransaction(rollback = false) {
            const tx = this.activeTransaction;
            this.activeTransaction = null;
            if (rollback && tx && tx.before) this.restorePayload(tx.before);
        }

        pushCommand(type, label, beforePayload, afterPayload) {
            if (JSON.stringify(beforePayload) === JSON.stringify(afterPayload)) return false;
            if (this.state.historyCursor < this.state.historyJournal.length) {
                this.state.historyJournal = this.state.historyJournal.slice(0, this.state.historyCursor);
            }

            const cmd = {
                id: 'cmd_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
                type: type,
                label: label,
                before: beforePayload,
                after: afterPayload,
                createdAt: new Date().toISOString(),
                projectRevision: this.state.revision
            };

            this.state.historyJournal.push(cmd);
            if (this.state.historyJournal.length > 150) {
                this.state.historyJournal.shift();
            }
            this.state.historyCursor = this.state.historyJournal.length;
            this.isDirty = true;
            return true;
        }

        pushHistory(label = 'Action', type = 'generic') {
            const tx = this.beginTransaction(label, type);
            return {
                commit: (customLabel) => {
                    if (this.activeTransaction === tx) return this.commitTransaction(customLabel);
                    return false;
                }
            };
        }

        canUndo() {
            return this.state.historyCursor > 0;
        }

        canRedo() {
            return this.state.historyCursor < this.state.historyJournal.length;
        }

        undo() {
            if (!this.canUndo()) return false;
            this.state.historyCursor -= 1;
            const cmd = this.state.historyJournal[this.state.historyCursor];
            if (cmd && cmd.before) {
                this.restorePayload(cmd.before);
                this.notify('undo');
                return true;
            }
            return false;
        }

        redo() {
            if (!this.canRedo()) return false;
            const cmd = this.state.historyJournal[this.state.historyCursor];
            this.state.historyCursor += 1;
            if (cmd && cmd.after) {
                this.restorePayload(cmd.after);
                this.notify('redo');
                return true;
            }
            return false;
        }

        restorePayload(payload) {
            if (!payload) return;
            if (payload.layers) this.state.layers = JSON.parse(JSON.stringify(payload.layers));
            if (payload.focusRegions) this.state.focusRegions = JSON.parse(JSON.stringify(payload.focusRegions));
            if (payload.maskRegions) this.state.maskRegions = JSON.parse(JSON.stringify(payload.maskRegions));
            this.state.cropRegion = payload.cropRegion ? JSON.parse(JSON.stringify(payload.cropRegion)) : null;
            if (payload.cropSettings) this.state.cropSettings = JSON.parse(JSON.stringify(payload.cropSettings));
            if (payload.regionGroups) this.state.regionGroups = JSON.parse(JSON.stringify(payload.regionGroups));
        }

        // ======================================================
        // Focus Regions Management (Section 5 & 6)
        // ======================================================
        setFocusRegion(regionConfig, selectedLayerId, featherPx = 8) {
            const tx = this.pushHistory('Gán ảnh nét cho vùng', 'focus_set');

            let shapeType = 'rectangle';
            let pointsWorld = [];
            let targetLayerId = selectedLayerId;
            let targetFeather = featherPx;

            if (typeof regionConfig === 'object' && !Array.isArray(regionConfig)) {
                shapeType = regionConfig.shapeType || 'rectangle';
                pointsWorld = regionConfig.pointsWorld || [];
                targetLayerId = regionConfig.selectedLayerId !== undefined ? regionConfig.selectedLayerId : selectedLayerId;
                targetFeather = regionConfig.featherWorldPx !== undefined ? regionConfig.featherWorldPx : (regionConfig.featherPx || featherPx);
            } else if (Array.isArray(regionConfig) && regionConfig.length >= 4 && typeof regionConfig[0] === 'number') {
                const [rx, ry, rw, rh] = regionConfig;
                shapeType = 'rectangle';
                pointsWorld = [[rx, ry], [rx + rw, ry], [rx + rw, ry + rh], [rx, ry + rh]];
            } else if (Array.isArray(regionConfig)) {
                pointsWorld = regionConfig;
                shapeType = 'polygon';
            }

            const xs = pointsWorld.map(p => p[0]), ys = pointsWorld.map(p => p[1]);
            const minX = xs.length ? Math.min(...xs) : 0, minY = ys.length ? Math.min(...ys) : 0;
            const maxX = xs.length ? Math.max(...xs) : 0, maxY = ys.length ? Math.max(...ys) : 0;

            const requestedId = regionConfig && !Array.isArray(regionConfig) ? regionConfig.id : null;
            const existing = this.state.focusRegions.find(fr => fr.id === requestedId) || this.state.focusRegions.find(fr =>
                fr.shapeType === shapeType && JSON.stringify(fr.pointsWorld) === JSON.stringify(pointsWorld)
            );
            if (existing && !existing.locked) {
                existing.selectedLayerId = targetLayerId;
                existing.featherWorldPx = Number(targetFeather) || 8;
                existing.featherPx = existing.featherWorldPx;
                existing.updatedAt = new Date().toISOString();
                tx.commit('Cập nhật ảnh nét cho vùng');
                this.notify('focusRegions');
                return existing;
            }

            const regionId = 'fr_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4);

            const newRegion = {
                id: regionId,
                shapeType: shapeType,
                pointsWorld: pointsWorld,
                boundingRect: [minX, minY, maxX - minX, maxY - minY],
                worldRect: [minX, minY, maxX - minX, maxY - minY],
                selectedLayerId: targetLayerId,
                featherWorldPx: Number(targetFeather) || 8,
                featherPx: Number(targetFeather) || 8,
                order: this.state.focusRegions.length,
                locked: false,
                geometryRevision: 1,
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString()
            };

            this.state.focusRegions.push(newRegion);
            tx.commit();
            this.notify('focusRegions');
            return newRegion;
        }

        updateFocusRegion(regionId, updates) {
            const fr = this.state.focusRegions.find(r => r.id === regionId);
            if (!fr || fr.locked) return;
            const tx = this.pushHistory('Chỉnh sửa vùng nét', 'focus_update');
            Object.assign(fr, updates, { updatedAt: new Date().toISOString() });
            if (updates.pointsWorld) {
                const xs = updates.pointsWorld.map(p => p[0]), ys = updates.pointsWorld.map(p => p[1]);
                fr.boundingRect = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
                fr.geometryRevision = (fr.geometryRevision || 1) + 1;
            }
            tx.commit();
            this.notify('focusRegions');
        }

        removeFocusRegion(regionId) {
            const region = this.state.focusRegions.find(item => item.id === regionId);
            if (!region || region.locked) return false;
            const tx = this.pushHistory('Xóa vùng nét', 'focus_remove');
            this.state.focusRegions = this.state.focusRegions.filter(fr => fr.id !== regionId);
            tx.commit();
            this.notify('focusRegions');
            return true;
        }

        clearFocusRegions() {
            if (!this.state.focusRegions || this.state.focusRegions.length === 0) return;
            const tx = this.pushHistory('Xóa tất cả vùng nét', 'focus_clear');
            this.state.focusRegions = this.state.focusRegions.filter(region => region.locked);
            tx.commit();
            this.notify('focusRegions');
        }

        // ======================================================
        // Mask Regions Management (Section 5 & 8: Exclude / Restore)
        // ======================================================
        addMaskRegion(config) {
            const isRestore = config.operation === 'restore';
            const tx = this.pushHistory(isRestore ? 'Cọ khôi phục' : 'Cọ xóa tàng hình', 'mask_add');
            const maskId = 'mask_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4);

            const pts = config.pointsWorld || [];
            const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
            const r = Number(config.radiusWorld || 20);
            const minX = xs.length ? Math.min(...xs) - r : 0, minY = ys.length ? Math.min(...ys) - r : 0;
            const maxX = xs.length ? Math.max(...xs) + r : 0, maxY = ys.length ? Math.max(...ys) + r : 0;

            const newMask = {
                id: maskId,
                shapeType: config.shapeType || 'brush',
                pointsWorld: pts,
                radiusWorld: r,
                operation: isRestore ? 'restore' : 'exclude',
                order: this.state.maskRegions.length,
                locked: false,
                boundingRect: [minX, minY, maxX - minX, maxY - minY],
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString()
            };

            this.state.maskRegions.push(newMask);
            tx.commit();
            this.notify('maskRegions');
            return newMask;
        }

        // Legacy compatibility alias
        addExclusionStroke(strokeConfig) {
            return this.addMaskRegion(strokeConfig);
        }

        updateMaskRegion(maskId, updates) {
            const mr = this.state.maskRegions.find(m => m.id === maskId);
            if (!mr || mr.locked) return;
            const tx = this.pushHistory('Chỉnh sửa mask', 'mask_update');
            Object.assign(mr, updates, { updatedAt: new Date().toISOString() });
            tx.commit();
            this.notify('maskRegions');
        }

        removeMaskRegion(maskId) {
            const region = this.state.maskRegions.find(item => item.id === maskId);
            if (!region || region.locked) return false;
            const tx = this.pushHistory('Xóa nét cọ/mask', 'mask_remove');
            this.state.maskRegions = this.state.maskRegions.filter(m => m.id !== maskId);
            tx.commit();
            this.notify('maskRegions');
            return true;
        }

        clearMaskRegions() {
            if (this.state.maskRegions.length === 0) return;
            const tx = this.pushHistory('Xóa tất cả nét cọ/mask', 'mask_clear');
            this.state.maskRegions = this.state.maskRegions.filter(region => region.locked);
            tx.commit();
            this.notify('maskRegions');
        }

        // Legacy alias
        clearExclusionStrokes() {
            this.clearMaskRegions();
        }

        // ======================================================
        // Crop Region Lifecycle (Section 9: Draft -> Apply/Cancel/Reset)
        // ======================================================
        setCropDraft(cropConfig) {
            if (!cropConfig || !cropConfig.pointsWorld || cropConfig.pointsWorld.length < 3) {
                this.state.cropDraft = null;
            } else {
                const pts = cropConfig.pointsWorld;
                const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
                const minX = Math.min(...xs), minY = Math.min(...ys);
                const maxX = Math.max(...xs), maxY = Math.max(...ys);

                this.state.cropDraft = {
                    id: 'crop_draft',
                    shapeType: cropConfig.shapeType || 'rectangle',
                    pointsWorld: pts,
                    locked: false,
                    boundingRect: [minX, minY, maxX - minX, maxY - minY],
                    updatedAt: new Date().toISOString()
                };
            }
            this.notify('cropDraft');
        }

        applyCropDraft(settings) {
            if (!this.state.cropDraft) return;
            const tx = this.pushHistory('Áp dụng Cắt toàn bộ (Crop)', 'crop_apply');
            this.state.cropRegion = Object.assign({}, this.state.cropDraft, { id: 'crop_main' });
            if (settings) this.state.cropSettings = Object.assign({}, this.state.cropSettings, settings);
            this.state.cropDraft = null;
            tx.commit();
            this.notify('cropRegion');
        }

        cancelCropDraft() {
            this.state.cropDraft = null;
            this.notify('cropDraft');
        }

        clearCropRegion() {
            if (!this.state.cropRegion) {
                if (this.state.cropDraft) this.cancelCropDraft();
                return;
            }
            const tx = this.pushHistory('Hủy vùng Cắt (Crop)', 'crop_clear');
            this.state.cropRegion = null;
            this.state.cropDraft = null;
            tx.commit();
            this.notify('cropRegion');
        }

        // Legacy compatibility alias
        setKeepRegion(regionConfig) {
            if (!regionConfig) {
                this.clearCropRegion();
            } else {
                this.setCropDraft(regionConfig);
            }
        }

        clearKeepRegion() {
            this.clearCropRegion();
        }

        updateCropSettings(settings) {
            const tx = this.pushHistory('Cập nhật thiết lập Cắt', 'crop_settings');
            this.state.cropSettings = Object.assign({}, this.state.cropSettings, settings);
            tx.commit();
            this.notify('cropSettings');
        }

        // ======================================================
        // Multi-Selection & Batch Operations (Section 11)
        // ======================================================
        selectRegion(id, isMulti = false) {
            if (!isMulti) {
                this.selectedRegionIds = id ? [id] : [];
            } else {
                const idx = this.selectedRegionIds.indexOf(id);
                if (idx >= 0) this.selectedRegionIds.splice(idx, 1);
                else if (id) this.selectedRegionIds.push(id);
            }
            this.expandSelectionToGroups();
            this.notify('regionSelection');
        }

        selectRegions(ids, additive = false) {
            const next = Array.from(new Set((ids || []).filter(Boolean)));
            this.selectedRegionIds = additive
                ? Array.from(new Set([...this.selectedRegionIds, ...next]))
                : next;
            this.expandSelectionToGroups();
            this.notify('regionSelection');
        }

        getRegionById(id) {
            const focus = this.state.focusRegions.find(region => region.id === id);
            if (focus) return { kind: 'focus', region: focus };
            const mask = this.state.maskRegions.find(region => region.id === id);
            if (mask) return { kind: 'mask', region: mask };
            if (this.state.cropRegion && this.state.cropRegion.id === id) return { kind: 'crop', region: this.state.cropRegion };
            return null;
        }

        getSelectedRegions() {
            const focus = this.state.focusRegions.filter(fr => this.selectedRegionIds.includes(fr.id));
            const masks = this.state.maskRegions.filter(mr => this.selectedRegionIds.includes(mr.id));
            const crop = (this.state.cropRegion && this.selectedRegionIds.includes(this.state.cropRegion.id)) ? [this.state.cropRegion] : [];
            return { focus, masks, crop, all: [...focus, ...masks, ...crop] };
        }

        deleteSelectedRegions() {
            if (this.selectedRegionIds.length === 0) return;
            const tx = this.pushHistory('Xóa các vùng đang chọn', 'batch_delete');
            this.state.focusRegions = this.state.focusRegions.filter(fr => !this.selectedRegionIds.includes(fr.id) || fr.locked);
            this.state.maskRegions = this.state.maskRegions.filter(mr => !this.selectedRegionIds.includes(mr.id) || mr.locked);
            if (this.state.cropRegion && this.selectedRegionIds.includes(this.state.cropRegion.id) && !this.state.cropRegion.locked) {
                this.state.cropRegion = null;
            }
            const deletedIds = new Set(this.selectedRegionIds);
            this.state.regionGroups = this.state.regionGroups.map(group => ({
                ...group,
                memberRefs: group.memberRefs.filter(ref => !deletedIds.has(ref.id))
            })).filter(group => group.memberRefs.length > 1);
            this.selectedRegionIds = [];
            tx.commit();
            this.notify('batch');
        }

        setLayerForSelectedFocusRegions(selectedLayerId) {
            const focus = this.state.focusRegions.filter(fr => this.selectedRegionIds.includes(fr.id) && !fr.locked);
            if (focus.length === 0) return;
            const tx = this.pushHistory('Gán ảnh nét cho nhiều vùng', 'batch_focus');
            focus.forEach(fr => {
                fr.selectedLayerId = selectedLayerId;
                fr.updatedAt = new Date().toISOString();
            });
            tx.commit();
            this.notify('focusRegions');
        }

        setSelectedRegionsLocked(locked) {
            const selected = this.getSelectedRegions().all;
            if (selected.length === 0) return false;
            const tx = this.pushHistory(locked ? 'Khóa các vùng' : 'Mở khóa các vùng', 'batch_lock');
            selected.forEach(region => region.locked = Boolean(locked));
            tx.commit();
            this.notify('batch');
            return true;
        }

        setSelectedMaskOperation(operation) {
            const masks = this.getSelectedRegions().masks.filter(region => !region.locked);
            if (masks.length === 0) return false;
            const nextOperation = operation === 'restore' ? 'restore' : 'exclude';
            const tx = this.pushHistory('Đổi thao tác các mask', 'batch_mask_operation');
            masks.forEach(region => {
                region.operation = nextOperation;
                region.updatedAt = new Date().toISOString();
            });
            tx.commit();
            this.notify('maskRegions');
            return true;
        }

        groupSelectedRegions() {
            const refs = this.selectedRegionIds.map(id => this.getRegionById(id)).filter(Boolean);
            if (refs.length < 2) return false;
            const tx = this.pushHistory('Nhóm các vùng', 'region_group');
            const memberRefs = refs.map(item => ({ kind: item.kind, id: item.region.id }));
            this.state.regionGroups = this.state.regionGroups.filter(group =>
                !group.memberRefs.some(ref => memberRefs.some(member => member.kind === ref.kind && member.id === ref.id))
            );
            this.state.regionGroups.push({
                id: 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
                memberRefs,
                locked: false,
                createdAt: new Date().toISOString()
            });
            tx.commit();
            this.notify('regionGroups');
            return true;
        }

        ungroupSelectedRegions() {
            const selected = new Set(this.selectedRegionIds);
            const matching = this.state.regionGroups.filter(group => group.memberRefs.some(ref => selected.has(ref.id)));
            if (matching.length === 0) return false;
            const tx = this.pushHistory('Bỏ nhóm các vùng', 'region_ungroup');
            const removeIds = new Set(matching.map(group => group.id));
            this.state.regionGroups = this.state.regionGroups.filter(group => !removeIds.has(group.id));
            tx.commit();
            this.notify('regionGroups');
            return true;
        }

        expandSelectionToGroups() {
            const selected = new Set(this.selectedRegionIds);
            this.state.regionGroups.forEach(group => {
                if (group.memberRefs.some(ref => selected.has(ref.id))) {
                    group.memberRefs.forEach(ref => selected.add(ref.id));
                }
            });
            this.selectedRegionIds = Array.from(selected);
        }

        // ======================================================
        // Layer Operations
        // ======================================================
        addLayer(layerData) {
            const ownsTransaction = !this.activeTransaction;
            if (ownsTransaction) this.beginTransaction('Thêm layer', 'layer_add');
            const newLayer = {
                id: layerData.id || 'layer_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
                sourceId: layerData.sourceId || '',
                sourceWidth: layerData.sourceWidth || 1000,
                sourceHeight: layerData.sourceHeight || 1000,
                sourceToWorld: layerData.sourceToWorld || [1,0,0, 0,1,0, 0,0,1],
                cropRect: layerData.cropRect || null,
                opacity: layerData.opacity !== undefined ? Number(layerData.opacity) : 1.0,
                brightness: layerData.brightness !== undefined ? Number(layerData.brightness) : 1.0,
                contrast: layerData.contrast !== undefined ? Number(layerData.contrast) : 1.0,
                saturation: layerData.saturation !== undefined ? Number(layerData.saturation) : 1.0,
                visible: layerData.visible !== undefined ? Boolean(layerData.visible) : true,
                locked: layerData.locked !== undefined ? Boolean(layerData.locked) : false,
                zIndex: layerData.zIndex || this.state.layers.length,
                confidence: layerData.confidence !== undefined ? Number(layerData.confidence) : 1.0,
                sourcePath: layerData.sourcePath || ''
            };
            this.state.layers.push(newLayer);
            if (ownsTransaction) this.commitTransaction();
            return newLayer;
        }

        updateLayerTransform(layerId, newMatrix3x3, transient = false) {
            const layer = this.state.layers.find(l => l.id === layerId);
            if (layer && !layer.locked) {
                layer.sourceToWorld = newMatrix3x3;
                if (!transient) this.notify('transform');
            }
        }

        removeLayer(layerId) {
            const layer = this.state.layers.find(l => l.id === layerId);
            if (!layer || layer.locked) return false;
            const tx = this.pushHistory('Xóa layer', 'layer_remove');
            this.state.layers = this.state.layers.filter(l => l.id !== layerId);
            this.state.selection = this.state.selection.filter(id => id !== layerId);
            tx.commit();
            this.notify('deleteLayer');
            return true;
        }

        updateLayerProperties(layerId, props) {
            const layer = this.state.layers.find(l => l.id === layerId);
            if (layer) {
                const tx = this.pushHistory('Chỉnh sửa layer', 'layer_props');
                Object.assign(layer, props);
                tx.commit();
                this.notify('properties');
            }
        }

        bringForward(layerId) {
            const idx = this.state.layers.findIndex(l => l.id === layerId);
            if (idx >= 0 && idx < this.state.layers.length - 1) {
                const tx = this.pushHistory('Đưa layer lên trước', 'layer_reorder');
                const temp = this.state.layers[idx];
                this.state.layers[idx] = this.state.layers[idx + 1];
                this.state.layers[idx + 1] = temp;
                this.reindexZ();
                tx.commit();
                this.notify('reorder');
            }
        }

        sendBackward(layerId) {
            const idx = this.state.layers.findIndex(l => l.id === layerId);
            if (idx > 0) {
                const tx = this.pushHistory('Đưa layer xuống sau', 'layer_reorder');
                const temp = this.state.layers[idx];
                this.state.layers[idx] = this.state.layers[idx - 1];
                this.state.layers[idx - 1] = temp;
                this.reindexZ();
                tx.commit();
                this.notify('reorder');
            }
        }

        reindexZ() {
            this.state.layers.forEach((l, i) => l.zIndex = i);
        }

        resetImageTools() {
            this.state.cropRegion = null;
            this.state.cropDraft = null;
            this.state.maskRegions = [];
            this.state.focusRegions = [];
            this.selectedRegionIds = [];
        }

        selectLayer(layerId) {
            const prevId = this.state.selection[0] || null;
            this.state.selection = layerId ? [layerId] : [];
            if (prevId && layerId && prevId !== layerId) {
                this.resetImageTools();
            }
            this.notify('selection');
        }

        getSelectedLayer() {
            if (this.state.selection.length === 0) return null;
            return this.state.layers.find(l => l.id === this.state.selection[0]) || null;
        }

        setMode(newMode) {
            if (this.state.mode !== newMode) {
                this.state.mode = newMode;
                this.notify('modeChange');
            }
        }

        scheduleAutosave() {
            if (this.autosaveTimer) clearTimeout(this.autosaveTimer);
            this.saveGeneration += 1;
            this.saveQueued = true;
            this.autosaveRetryCount = 0;
            this.autosaveTimer = setTimeout(() => this.flushAutosave(), 1000);
        }

        async flushAutosave() {
            if (this.saveInFlight || !this.saveQueued) return false;
            this.saveInFlight = true;
            this.saveQueued = false;
            const generation = this.saveGeneration;
            const projectId = this.state.id;
            const payload = JSON.parse(JSON.stringify(this.state));
            try {
                const res = await fetch(`/api/projects/${projectId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (res.status === 409) {
                    let details = null;
                    try { details = await res.json(); } catch (e) {}
                    if (details && details.currentRevision && projectId === this.state.id) {
                        this.state.revision = details.currentRevision;
                    }
                    this.autosaveConflict = { projectId, generation, details, occurredAt: new Date().toISOString() };
                    this.isDirty = true;
                    this.listeners.forEach(cb => {
                        try { cb(this.state, 'autosaveConflict'); } catch (e) { console.error('Store observer error:', e); }
                    });
                    return false;
                }
                if (!res.ok) throw new Error(`Autosave HTTP ${res.status}`);
                const data = await res.json();
                if (data && data.revision && projectId === this.state.id) this.state.revision = data.revision;
                if (projectId === this.state.id) this.autosaveConflict = null;
                this.autosaveRetryCount = 0;
                if (generation === this.saveGeneration && projectId === this.state.id) this.isDirty = false;
                return true;
            } catch (err) {
                this.isDirty = true;
                this.saveQueued = true;
                this.autosaveRetryCount += 1;
                if (this.autosaveRetryCount <= this.maxAutosaveRetries) {
                    const retryDelay = Math.min(30000, 1000 * Math.pow(2, this.autosaveRetryCount - 1));
                    clearTimeout(this.autosaveTimer);
                    this.autosaveTimer = setTimeout(() => this.flushAutosave(), retryDelay);
                }
                console.warn('Autosave failed:', err);
                return false;
            } finally {
                this.saveInFlight = false;
                if (this.saveGeneration > generation) {
                    this.saveQueued = true;
                    clearTimeout(this.autosaveTimer);
                    this.autosaveTimer = setTimeout(() => this.flushAutosave(), 0);
                }
            }
        }
    }

    return new Store();
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ProjectStore;
}
