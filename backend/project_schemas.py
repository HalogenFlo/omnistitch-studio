"""
Chức năng: Định nghĩa Schema cho Project State, Layers, Transform 3x3 Matrices và Color Adjustments
Lí do tạo: Đảm bảo tính nhất quán giữa Frontend (Canvas Editor) và Backend (Export & Persistence)
Đường dẫn: tool/image_alignment/backend/project_schemas.py
"""

import json
import math
from typing import List, Dict, Any, Optional
import numpy as np

# Type alias cho ma trận 3x3 [m00, m01, m02, m10, m11, m12, m20, m21, m22] (Row-major)
Matrix3x3 = List[float]
CURRENT_PROJECT_VERSION = 3
MAX_HISTORY_COMMANDS = 200
MAX_REGION_POINTS = 10000


def _bounded_float(value: Any, field: str, minimum: float, maximum: float) -> float:
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ValueError(f"{field} phải hữu hạn trong khoảng [{minimum}, {maximum}]")
    return result


def _validate_points(points: Any, field: str, minimum: int = 0) -> List[List[float]]:
    if points is None:
        points = []
    if not isinstance(points, list) or len(points) < minimum:
        raise ValueError(f"{field} phải có ít nhất {minimum} điểm")
    if len(points) > MAX_REGION_POINTS:
        raise ValueError(f"{field} vượt giới hạn {MAX_REGION_POINTS} điểm")
    result = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{field} chứa điểm không hợp lệ")
        xy = [float(point[0]), float(point[1])]
        if not all(math.isfinite(value) for value in xy):
            raise ValueError(f"{field} chứa tọa độ không hữu hạn")
        result.append(xy)
    return result

def matrix_identity() -> Matrix3x3:
    return [1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0]

def matrix_translate(tx: float, ty: float) -> Matrix3x3:
    return [1.0, 0.0, float(tx),
            0.0, 1.0, float(ty),
            0.0, 0.0, 1.0]

def matrix_scale(sx: float, sy: float) -> Matrix3x3:
    return [float(sx), 0.0, 0.0,
            0.0, float(sy), 0.0,
            0.0, 0.0, 1.0]

def matrix_rotate(angle_rad: float) -> Matrix3x3:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return [c, -s, 0.0,
            s,  c, 0.0,
            0.0, 0.0, 1.0]

def matrix_multiply(m1: Matrix3x3, m2: Matrix3x3) -> Matrix3x3:
    """Nhân hai ma trận 3x3 (Row-major)"""
    a = np.array(m1, dtype=np.float64).reshape((3, 3))
    b = np.array(m2, dtype=np.float64).reshape((3, 3))
    res = np.dot(a, b)
    return res.flatten().tolist()

def matrix_inverse(m: Matrix3x3) -> Optional[Matrix3x3]:
    """Nghịch đảo ma trận 3x3. Trả về None nếu suy biến (det == 0)"""
    try:
        a = np.array(m, dtype=np.float64).reshape((3, 3))
        det = np.linalg.det(a)
        if abs(det) < 1e-12 or not np.isfinite(det):
            return None
        inv = np.linalg.inv(a)
        if not np.all(np.isfinite(inv)):
            return None
        return inv.flatten().tolist()
    except Exception:
        return None

def transform_point(m: Matrix3x3, x: float, y: float) -> List[float]:
    """Ánh xạ điểm (x, y) từ Source sang World coordinates qua ma trận m (3x3)"""
    # [m00*x + m01*y + m02, m10*x + m11*y + m12, 1]
    px = m[0] * x + m[1] * y + m[2]
    py = m[3] * x + m[4] * y + m[5]
    w = m[6] * x + m[7] * y + m[8]
    if abs(w - 1.0) > 1e-9 and abs(w) > 1e-12:
        px /= w
        py /= w
    return [float(px), float(py)]


class ProjectLayer:
    def __init__(
        self,
        id: str,
        sourceId: str,
        sourceWidth: int,
        sourceHeight: int,
        sourceToWorld: Matrix3x3 = None,
        cropRect: Optional[List[float]] = None,
        opacity: float = 1.0,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        visible: bool = True,
        locked: bool = False,
        zIndex: int = 0,
        componentId: int = 0,
        confidence: float = 1.0,
        sourcePath: str = ""
    ):
        self.id = id
        self.sourceId = sourceId
        self.sourceWidth = sourceWidth
        self.sourceHeight = sourceHeight
        self.sourceToWorld = sourceToWorld if sourceToWorld is not None else matrix_identity()
        self.cropRect = cropRect # [x, y, w, h] trong source pixel
        if int(sourceWidth) <= 0 or int(sourceHeight) <= 0:
            raise ValueError("Kích thước source phải lớn hơn 0")
        self.opacity = _bounded_float(opacity, "layers.opacity", 0.0, 1.0)
        self.brightness = _bounded_float(brightness, "layers.brightness", 0.0, 4.0)
        self.contrast = _bounded_float(contrast, "layers.contrast", 0.0, 4.0)
        self.saturation = _bounded_float(saturation, "layers.saturation", 0.0, 4.0)
        self.visible = visible
        self.locked = locked
        self.zIndex = zIndex
        self.componentId = componentId
        self.confidence = _bounded_float(confidence, "layers.confidence", 0.0, 1.0)
        self.sourcePath = sourcePath

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sourceId": self.sourceId,
            "sourceWidth": self.sourceWidth,
            "sourceHeight": self.sourceHeight,
            "sourceToWorld": self.sourceToWorld,
            "cropRect": self.cropRect,
            "opacity": self.opacity,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "visible": self.visible,
            "locked": self.locked,
            "zIndex": self.zIndex,
            "componentId": self.componentId,
            "confidence": self.confidence,
            "sourcePath": self.sourcePath
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectLayer':
        matrix = data.get("sourceToWorld", matrix_identity())
        if not isinstance(matrix, list) or len(matrix) != 9:
            raise ValueError("sourceToWorld phải là ma trận row-major 3x3")
        matrix = [float(value) for value in matrix]
        if not all(math.isfinite(value) for value in matrix):
            raise ValueError("sourceToWorld chứa giá trị không hữu hạn")
        if matrix_inverse(matrix) is None:
            raise ValueError("sourceToWorld phải khả nghịch")
        return cls(
            id=data.get("id", ""),
            sourceId=data.get("sourceId", ""),
            sourceWidth=int(data.get("sourceWidth", 0)),
            sourceHeight=int(data.get("sourceHeight", 0)),
            sourceToWorld=matrix,
            cropRect=data.get("cropRect"),
            opacity=float(data.get("opacity", 1.0)),
            brightness=float(data.get("brightness", 1.0)),
            contrast=float(data.get("contrast", 1.0)),
            saturation=float(data.get("saturation", 1.0)),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
            zIndex=int(data.get("zIndex", 0)),
            componentId=int(data.get("componentId", 0)),
            confidence=float(data.get("confidence", 1.0)),
            sourcePath=data.get("sourcePath", "")
        )

class FocusRegion:
    def __init__(
        self,
        id: str,
        shapeType: str = "rectangle",
        pointsWorld: Optional[List[List[float]]] = None,
        selectedLayerId: Optional[str] = None,
        featherWorldPx: float = 8.0,
        order: int = 0,
        locked: bool = False,
        geometryRevision: int = 1,
        createdAt: str = "",
        updatedAt: str = "",
        # Legacy compat
        featherPx: Optional[float] = None,
        worldRect: Optional[List[float]] = None
    ):
        self.id = id
        self.shapeType = shapeType if shapeType in ["rectangle", "polygon", "lasso"] else "rectangle"
        self.order = int(order)
        self.locked = bool(locked)
        self.geometryRevision = int(geometryRevision)
        self.createdAt = createdAt
        self.updatedAt = updatedAt or createdAt

        if pointsWorld is not None and len(pointsWorld) > 0:
            self.pointsWorld = _validate_points(pointsWorld, "focusRegions.pointsWorld")
        elif worldRect is not None and len(worldRect) >= 4:
            rx, ry, rw, rh = worldRect[:4]
            self.pointsWorld = [
                [float(rx), float(ry)],
                [float(rx + rw), float(ry)],
                [float(rx + rw), float(ry + rh)],
                [float(rx), float(ry + rh)]
            ]
        else:
            self.pointsWorld = []

        self.selectedLayerId = selectedLayerId
        self.featherWorldPx = _bounded_float(
            featherWorldPx if featherWorldPx is not None else (featherPx if featherPx is not None else 8.0),
            "focusRegions.featherWorldPx", 0.0, 100000.0
        )

    @property
    def featherPx(self) -> float:
        return self.featherWorldPx

    @property
    def boundingRect(self) -> List[float]:
        if not self.pointsWorld:
            return [0.0, 0.0, 0.0, 0.0]
        xs = [p[0] for p in self.pointsWorld]
        ys = [p[1] for p in self.pointsWorld]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return [min_x, min_y, max_x - min_x, max_y - min_y]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "shapeType": self.shapeType,
            "pointsWorld": self.pointsWorld,
            "selectedLayerId": self.selectedLayerId,
            "featherWorldPx": self.featherWorldPx,
            "featherPx": self.featherWorldPx,
            "order": self.order,
            "locked": self.locked,
            "geometryRevision": self.geometryRevision,
            "boundingRect": self.boundingRect,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FocusRegion':
        return cls(
            id=data.get("id", ""),
            shapeType=data.get("shapeType", "rectangle"),
            pointsWorld=data.get("pointsWorld"),
            selectedLayerId=data.get("selectedLayerId"),
            featherWorldPx=float(data.get("featherWorldPx", data.get("featherPx", 8.0))),
            order=int(data.get("order", 0)),
            locked=bool(data.get("locked", False)),
            geometryRevision=int(data.get("geometryRevision", 1)),
            createdAt=data.get("createdAt", ""),
            updatedAt=data.get("updatedAt", ""),
            worldRect=data.get("worldRect")
        )


class MaskRegion:
    def __init__(
        self,
        id: str,
        shapeType: str = "brush",
        pointsWorld: Optional[List[List[float]]] = None,
        radiusWorld: float = 20.0,
        operation: str = "exclude",
        order: int = 0,
        locked: bool = False,
        createdAt: str = "",
        updatedAt: str = ""
    ):
        self.id = id
        self.shapeType = shapeType if shapeType in ["brush", "rectangle", "polygon", "lasso"] else "brush"
        self.pointsWorld = _validate_points(pointsWorld or [], "maskRegions.pointsWorld")
        self.radiusWorld = _bounded_float(radiusWorld, "maskRegions.radiusWorld", 0.0, 100000.0)
        self.operation = operation if operation in ["exclude", "restore"] else "exclude"
        self.order = int(order)
        self.locked = bool(locked)
        self.createdAt = createdAt
        self.updatedAt = updatedAt or createdAt

    @property
    def boundingRect(self) -> List[float]:
        if not self.pointsWorld:
            return [0.0, 0.0, 0.0, 0.0]
        xs = [p[0] for p in self.pointsWorld]
        ys = [p[1] for p in self.pointsWorld]
        r = self.radiusWorld if self.shapeType == 'brush' else 0.0
        min_x, max_x = min(xs) - r, max(xs) + r
        min_y, max_y = min(ys) - r, max(ys) + r
        return [min_x, min_y, max_x - min_x, max_y - min_y]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "shapeType": self.shapeType,
            "pointsWorld": self.pointsWorld,
            "radiusWorld": self.radiusWorld,
            "operation": self.operation,
            "order": self.order,
            "locked": self.locked,
            "boundingRect": self.boundingRect,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MaskRegion':
        return cls(
            id=data.get("id", ""),
            shapeType=data.get("shapeType", "brush"),
            pointsWorld=data.get("pointsWorld", []),
            radiusWorld=float(data.get("radiusWorld", 20.0)),
            operation=data.get("operation", "exclude"),
            order=int(data.get("order", 0)),
            locked=bool(data.get("locked", False)),
            createdAt=data.get("createdAt", ""),
            updatedAt=data.get("updatedAt", "")
        )


# Backward compatibility alias
ExclusionStroke = MaskRegion


class CropRegion:
    def __init__(
        self,
        id: str = "crop_main",
        shapeType: str = "rectangle",
        pointsWorld: Optional[List[List[float]]] = None,
        locked: bool = False,
        updatedAt: str = ""
    ):
        self.id = id
        self.shapeType = shapeType if shapeType in ["rectangle", "polygon", "lasso"] else "rectangle"
        self.pointsWorld = _validate_points(pointsWorld or [], "cropRegion.pointsWorld")
        self.locked = bool(locked)
        self.updatedAt = updatedAt

    @property
    def boundingRect(self) -> List[float]:
        if not self.pointsWorld:
            return [0.0, 0.0, 0.0, 0.0]
        xs = [p[0] for p in self.pointsWorld]
        ys = [p[1] for p in self.pointsWorld]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return [min_x, min_y, max_x - min_x, max_y - min_y]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "shapeType": self.shapeType,
            "pointsWorld": self.pointsWorld,
            "locked": self.locked,
            "boundingRect": self.boundingRect,
            "updatedAt": self.updatedAt
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CropRegion':
        points = data.get("pointsWorld", [])
        world_rect = data.get("worldRect")
        if not points and world_rect and len(world_rect) >= 4:
            x, y, width, height = [float(value) for value in world_rect[:4]]
            points = [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]
        return cls(
            id=data.get("id", "crop_main"),
            shapeType=data.get("shapeType", "rectangle"),
            pointsWorld=points,
            locked=bool(data.get("locked", False)),
            updatedAt=data.get("updatedAt", "")
        )


# Backward compatibility alias
KeepRegion = CropRegion


class CropSettings:
    def __init__(
        self,
        trimOutputBounds: bool = True,
        aspectRatio: Optional[Any] = None,
        paddingWorld: float = 0.0
    ):
        self.trimOutputBounds = bool(trimOutputBounds)
        self.aspectRatio = aspectRatio
        self.paddingWorld = _bounded_float(paddingWorld, "cropSettings.paddingWorld", 0.0, 100000.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trimOutputBounds": self.trimOutputBounds,
            "aspectRatio": self.aspectRatio,
            "paddingWorld": self.paddingWorld
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CropSettings':
        return cls(
            trimOutputBounds=bool(data.get("trimOutputBounds", True)),
            aspectRatio=data.get("aspectRatio"),
            paddingWorld=float(data.get("paddingWorld", 0.0))
        )


class RegionGroup:
    def __init__(
        self,
        id: str,
        memberRefs: Optional[List[Dict[str, str]]] = None,
        locked: bool = False,
        createdAt: str = ""
    ):
        self.id = id
        self.memberRefs = memberRefs if memberRefs is not None else []
        self.locked = bool(locked)
        self.createdAt = createdAt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memberRefs": self.memberRefs,
            "locked": self.locked,
            "createdAt": self.createdAt
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegionGroup':
        return cls(
            id=data.get("id", ""),
            memberRefs=data.get("memberRefs", []),
            locked=bool(data.get("locked", False)),
            createdAt=data.get("createdAt", "")
        )


class HistoryCommand:
    def __init__(
        self,
        id: str,
        type: str,
        label: str,
        before: Any = None,
        after: Any = None,
        createdAt: str = "",
        projectRevision: int = 1
    ):
        self.id = id
        self.type = type
        self.label = label
        self.before = before
        self.after = after
        self.createdAt = createdAt
        self.projectRevision = int(projectRevision)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "before": self.before,
            "after": self.after,
            "createdAt": self.createdAt,
            "projectRevision": self.projectRevision
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryCommand':
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            label=data.get("label", ""),
            before=data.get("before"),
            after=data.get("after"),
            createdAt=data.get("createdAt", ""),
            projectRevision=int(data.get("projectRevision", 1))
        )


class ProjectState:
    def __init__(
        self,
        id: str,
        version: int = 3,
        revision: int = 1,
        geometryRevision: int = 1,
        worldUnits: str = "pixel",
        mode: str = "manual",
        layers: Optional[List[ProjectLayer]] = None,
        viewport: Optional[Dict[str, Any]] = None,
        selection: Optional[List[str]] = None,
        folderName: str = "",
        updatedAt: str = "",
        focusRegions: Optional[List[FocusRegion]] = None,
        maskRegions: Optional[List[MaskRegion]] = None,
        cropRegion: Optional[CropRegion] = None,
        cropDraft: Optional[CropRegion] = None,
        cropSettings: Optional[CropSettings] = None,
        regionGroups: Optional[List[RegionGroup]] = None,
        historyJournal: Optional[List[HistoryCommand]] = None,
        historyCursor: int = 0,
        # Legacy parameter compat
        exclusionStrokes: Optional[List[Any]] = None,
        keepRegion: Optional[Any] = None
    ):
        self.id = id
        self.version = CURRENT_PROJECT_VERSION
        self.revision = int(revision)
        self.geometryRevision = int(geometryRevision)
        self.worldUnits = worldUnits
        self.mode = mode
        self.layers = layers if layers is not None else []
        self.viewport = viewport if viewport is not None else {"center": [0, 0], "zoom": 1.0, "rotation": 0}
        self.selection = selection if selection is not None else []
        self.folderName = folderName
        self.updatedAt = updatedAt
        self.focusRegions = focusRegions if focusRegions is not None else []

        # MaskRegions with migration from legacy exclusionStrokes
        if maskRegions is not None:
            self.maskRegions = maskRegions
        elif exclusionStrokes is not None:
            self.maskRegions = [MaskRegion.from_dict(es) if isinstance(es, dict) else es for es in exclusionStrokes]
        else:
            self.maskRegions = []

        # CropRegion with migration from legacy keepRegion
        if cropRegion is not None:
            self.cropRegion = cropRegion
        elif keepRegion is not None:
            self.cropRegion = CropRegion.from_dict(keepRegion) if isinstance(keepRegion, dict) else keepRegion
        else:
            self.cropRegion = None

        self.cropDraft = cropDraft
        self.cropSettings = cropSettings if cropSettings is not None else CropSettings()
        self.regionGroups = regionGroups if regionGroups is not None else []
        journal = historyJournal if historyJournal is not None else []
        self.historyJournal = journal[-MAX_HISTORY_COMMANDS:]
        dropped = max(0, len(journal) - len(self.historyJournal))
        self.historyCursor = max(0, min(int(historyCursor) - dropped, len(self.historyJournal)))

    @property
    def exclusionStrokes(self) -> List[MaskRegion]:
        return self.maskRegions

    @property
    def keepRegion(self) -> Optional[CropRegion]:
        return self.cropRegion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "revision": self.revision,
            "geometryRevision": self.geometryRevision,
            "worldUnits": self.worldUnits,
            "mode": self.mode,
            "layers": [layer.to_dict() for layer in self.layers],
            "viewport": self.viewport,
            "selection": self.selection,
            "folderName": self.folderName,
            "updatedAt": self.updatedAt,
            "focusRegions": [fr.to_dict() for fr in self.focusRegions],
            "maskRegions": [mr.to_dict() for mr in self.maskRegions],
            "exclusionStrokes": [mr.to_dict() for mr in self.maskRegions],
            "cropRegion": self.cropRegion.to_dict() if self.cropRegion else None,
            "keepRegion": self.cropRegion.to_dict() if self.cropRegion else None,
            "cropDraft": self.cropDraft.to_dict() if self.cropDraft else None,
            "cropSettings": self.cropSettings.to_dict(),
            "regionGroups": [rg.to_dict() for rg in self.regionGroups],
            "historyJournal": [hc.to_dict() for hc in self.historyJournal],
            "historyCursor": self.historyCursor
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectState':
        if not isinstance(data, dict):
            raise ValueError("Project phải là JSON object")
        version = int(data.get("version", 1))
        if version < 1 or version > CURRENT_PROJECT_VERSION:
            raise ValueError(f"Project version không được hỗ trợ: {version}")
        layers = [ProjectLayer.from_dict(l) for l in data.get("layers", [])]
        focus_regions = [FocusRegion.from_dict(fr) for fr in data.get("focusRegions", [])]

        raw_masks = data.get("maskRegions", data.get("exclusionStrokes", []))
        mask_regions = [MaskRegion.from_dict(m) for m in raw_masks]

        raw_crop = data.get("cropRegion", data.get("keepRegion"))
        crop_region = CropRegion.from_dict(raw_crop) if raw_crop else None
        crop_draft = CropRegion.from_dict(data["cropDraft"]) if data.get("cropDraft") else None

        crop_settings = CropSettings.from_dict(data.get("cropSettings", {})) if "cropSettings" in data else CropSettings()
        region_groups = [RegionGroup.from_dict(rg) for rg in data.get("regionGroups", [])]
        history_journal = [HistoryCommand.from_dict(hc) for hc in data.get("historyJournal", [])]

        project = cls(
            id=data.get("id", ""),
            version=CURRENT_PROJECT_VERSION,
            revision=int(data.get("revision", 1)),
            geometryRevision=int(data.get("geometryRevision", 1)),
            worldUnits=data.get("worldUnits", "pixel"),
            mode=data.get("mode", "manual"),
            layers=layers,
            viewport=data.get("viewport"),
            selection=data.get("selection", []),
            folderName=data.get("folderName", ""),
            updatedAt=data.get("updatedAt", ""),
            focusRegions=focus_regions,
            maskRegions=mask_regions,
            cropRegion=crop_region,
            cropDraft=crop_draft,
            cropSettings=crop_settings,
            regionGroups=region_groups,
            historyJournal=history_journal,
            historyCursor=int(data.get("historyCursor", 0))
        )
        if not project.id:
            raise ValueError("Project id không được để trống")
        if project.revision < 0 or project.geometryRevision < 1:
            raise ValueError("Revision không hợp lệ")
        ids = [layer.id for layer in project.layers]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Layer id phải khác rỗng và duy nhất")
        region_ids = [region.id for region in project.focusRegions + project.maskRegions]
        if project.cropRegion:
            region_ids.append(project.cropRegion.id)
        if any(not value for value in region_ids) or len(region_ids) != len(set(region_ids)):
            raise ValueError("Region id phải khác rỗng và duy nhất")
        layer_ids = set(ids)
        for region in project.focusRegions:
            if region.selectedLayerId is not None and region.selectedLayerId not in layer_ids:
                raise ValueError(f"FocusRegion tham chiếu layer không tồn tại: {region.selectedLayerId}")
        return project

    @classmethod
    def from_json(cls, json_str: str) -> 'ProjectState':
        data = json.loads(json_str)
        return cls.from_dict(data)
