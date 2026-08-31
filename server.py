# Feature: HTTP backend server for OmniStitch Studio
# Author: HalogenBr
# Purpose: Provides APIs for scanning source folders, automated stitching, saving to data/result, streaming progress, and serving DeepZoom Tiles
# Path: server.py

import os
import sys
import json
import base64
import threading
import urllib.parse
import mimetypes
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure backend module is importable. Installed wheels keep writable data out of site-packages.
tool_dir = os.path.dirname(os.path.abspath(__file__))
default_workspace = tool_dir if os.path.isdir(os.path.join(tool_dir, ".git")) else os.path.join(os.path.expanduser("~"), ".omnistitch-studio")
workspace_dir = os.path.abspath(os.environ.get("OMNISTITCH_WORKSPACE_DIR", default_workspace))
for p in [workspace_dir, tool_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Automatically allocate memory budget based on system RAM capacity
if "IMAGE_ALIGNMENT_MAX_MEMORY_MB" not in os.environ:
    try:
        import psutil
        avail_mb = int(psutil.virtual_memory().available * 0.75 / (1024 * 1024))
        os.environ["IMAGE_ALIGNMENT_MAX_MEMORY_MB"] = str(max(64, avail_mb))
    except Exception:
        os.environ["IMAGE_ALIGNMENT_MAX_MEMORY_MB"] = "2048"

import cv2
from backend.io_utils import read_image, save_tiff, create_thumbnail, get_image_metadata
from backend.pipeline import run_wsi_stitching_pipeline

PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "127.0.0.1")
WORKSPACE_DIR = workspace_dir
NHUOM_MO_DIR = os.path.join(WORKSPACE_DIR, "NhuomMo")
DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
OUTPUTS_DIR = os.path.join(DATA_DIR, "result")
UPLOADS_DIR = os.path.join(WORKSPACE_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# Trạng thái tiến trình ghép ảnh toàn cục (In-memory Task State)
stitching_task = {
    "is_running": False,
    "progress": 0,
    "step_name": "Sẵn sàng",
    "logs": [],
    "result": None,
    "error": None
}
stitching_task_lock = threading.RLock()
MAX_JSON_REQUEST_BYTES = 4 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = 256 * 1024 * 1024
MAX_UPLOAD_DECODED_BYTES = 128 * 1024 * 1024
IMAGE_EXTENSIONS = ('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp')
FILE_STREAM_CHUNK_BYTES = 1024 * 1024


def _contained_path(root, candidate):
    root = os.path.realpath(root)
    candidate = os.path.realpath(candidate)
    try:
        contained = os.path.commonpath([root, candidate]) == root
    except ValueError:
        contained = False
    if not contained:
        raise ValueError("Đường dẫn nằm ngoài workspace được phép")
    return candidate


def _same_origin_cors_value(origin, host):
    return origin if origin and host and origin == f"http://{host}" else None


def _is_allowed_image_path(candidate):
    candidate = os.path.realpath(candidate)
    try:
        in_allowed_root = any(
            os.path.commonpath([os.path.realpath(root), candidate]) == os.path.realpath(root)
            for root in (DATA_DIR, NHUOM_MO_DIR, UPLOADS_DIR)
        )
    except ValueError:
        return False
    return in_allowed_root and os.path.splitext(candidate)[1].lower() in IMAGE_EXTENSIONS

def update_stitching_progress(percent, step_name, details):
    global stitching_task
    with stitching_task_lock:
        stitching_task["progress"] = percent
        stitching_task["step_name"] = step_name
        stitching_task["logs"].append({
            "percent": percent,
            "step": step_name,
            "details": details
        })
        if percent >= 100:
            stitching_task["result"] = details
            stitching_task["is_running"] = False

def background_stitching_worker(image_paths, options):
    global stitching_task
    try:
        result = run_wsi_stitching_pipeline(
            image_paths=image_paths,
            output_dir=OUTPUTS_DIR,
            feature_method=options.get("featureMethod", "sift"),
            motion_model=options.get("motionModel", "affine"),
            background_mode=options.get("backgroundMode", "white"),
            auto_crop=options.get("autoCrop", False),
            export_format=options.get("exportFormat", None),
            custom_output_name=options.get("customOutputName", None),
            progress_callback=update_stitching_progress,
            project_layers=options.get("project_layers")
        )
        with stitching_task_lock:
            stitching_task["result"] = result

        # Tự động cập nhật layer_transforms vào project file trên đĩa
        folder_name = options.get("customOutputName") or "stitched_wsi"
        try:
            from backend.project_store import load_project, save_project
            proj = load_project(folder_name)
            if proj and result.get("layer_transforms"):
                lt = result["layer_transforms"]
                for idx, layer in enumerate(proj.layers):
                    transform = lt.get(str(idx), lt.get(idx))
                    if transform:
                        layer.sourceToWorld = transform
                save_project(proj)
                result["project_revision"] = proj.revision
        except Exception as e_save:
            print("Auto-save stitched project error:", e_save)
    except Exception as e:
        import traceback
        with stitching_task_lock:
            stitching_task["error"] = str(e)
            stitching_task["logs"].append({
                "percent": stitching_task["progress"],
                "step": "Error!",
                "details": {"error": str(e), "traceback": traceback.format_exc()}
            })
    finally:
        with stitching_task_lock:
            stitching_task["is_running"] = False

class AlignmentToolRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host')
        allowed_origin = _same_origin_cors_value(origin, host)
        if allowed_origin:
            self.send_header('Access-Control-Allow-Origin', allowed_origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # Web Static Assets
        if path in ["/", "/index.html"]:
            self.serve_file(os.path.join(tool_dir, "index.html"), "text/html; charset=utf-8")
        elif path == "/styles.css":
            self.serve_file(os.path.join(tool_dir, "styles.css"), "text/css; charset=utf-8")
        elif path == "/app.js":
            self.serve_file(os.path.join(tool_dir, "app.js"), "application/javascript; charset=utf-8")
        elif path.startswith("/frontend/"):
            rel_file = path[len("/frontend/"):]
            try:
                f_path = _contained_path(os.path.join(tool_dir, "frontend"), os.path.join(tool_dir, "frontend", rel_file))
            except ValueError:
                self.send_error(403, "Path outside frontend directory")
                return
            if os.path.exists(f_path):
                self.serve_file(f_path, "application/javascript; charset=utf-8")
            else:
                self.send_error(404, "File Not Found")

        # Project Persistence API (GET)
        elif path.startswith("/api/projects/"):
            proj_id = urllib.parse.unquote(path[len("/api/projects/"):])
            self.handle_get_project(proj_id)

        # API Health Check
        elif path == "/api/health":
            self.send_json({"status": "ok", "service": "OmniStitch Studio"})

        # API: Danh sách ảnh
        elif path == "/api/images":
            self.handle_list_images()

        # API: Danh sách thư mục có sẵn trong hệ thống (Auto-detect Datasets)
        elif path == "/api/available_folders":
            self.handle_available_folders()

        # API: Thumbnail on-the-fly (hỗ trợ .tif, .tiff, .png, .jpg)
        elif path == "/api/thumbnail":
            self.handle_thumbnail(query)

        # API: Tải file ảnh trực tiếp
        elif path == "/api/image":
            self.handle_serve_image(query)

        # API: Tiến trình ghép ảnh
        elif path == "/api/stitch/status":
            self.handle_stitch_status()

        # Phục vụ DZI XML & DeepZoom Pyramid Tiles từ data/output
        elif path.startswith("/dzi/"):
            self.handle_serve_dzi(path)

        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        limit = MAX_UPLOAD_REQUEST_BYTES if path in ("/api/upload", "/api/upload_batch") else MAX_JSON_REQUEST_BYTES
        if not self._validate_request_size(limit):
            return

        if path == "/api/stitch/auto":
            self.handle_start_auto_stitching()
        elif path.startswith("/api/projects/") and path.endswith("/inspect"):
            proj_id = urllib.parse.unquote(path.split("/")[3])
            self.handle_inspect_patches(proj_id)
        elif path.startswith("/api/projects/") and path.endswith("/patch"):
            proj_id = urllib.parse.unquote(path.split("/")[3])
            self.handle_native_patch(proj_id)
        elif path.startswith("/api/projects/") and path.endswith("/exports"):
            proj_id = urllib.parse.unquote(path.split("/")[3])
            self.handle_manual_export(proj_id)
        elif path == "/api/scan_folder":
            self.handle_scan_folder()
        elif path == "/api/upload":
            self.handle_upload_file()
        elif path == "/api/upload_batch":
            self.handle_upload_batch()
        elif path == "/api/save_wsi":
            self.handle_save_wsi()
        elif path == "/api/save":
            self.handle_save_legacy()
        else:
            self.send_error(404, "Not Found")

    def do_PUT(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if not self._validate_request_size(MAX_JSON_REQUEST_BYTES):
            return
        if path.startswith("/api/projects/"):
            proj_id = urllib.parse.unquote(path[len("/api/projects/"):])
            self.handle_save_project(proj_id)
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, filepath, content_type):
        try:
            content_length = os.path.getsize(filepath)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(content_length))
            self.end_headers()
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(FILE_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            self.send_error(500, f"Internal Server Error: {str(e)}")

    def send_json(self, data, status=200):
        response_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_data)))
        self.end_headers()
        self.wfile.write(response_data)

    def _validate_request_size(self, limit):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            self.send_json({"error": "Content-Length is invalid"}, status=400)
            return False
        if content_length <= 0:
            self.send_json({"error": "Content-Length bắt buộc và phải lớn hơn 0"}, status=411)
            return False
        if content_length > limit:
            self.send_json({"error": f"Request exceeds limit {limit} bytes"}, status=413)
            return False
        return True

    def resolve_path(self, rel_or_abs_path):
        """Resolve a user path while preventing traversal outside the workspace."""
        if not isinstance(rel_or_abs_path, str) or not rel_or_abs_path.strip():
            raise ValueError("Đường dẫn is invalid")
        if os.path.isabs(rel_or_abs_path):
            return _contained_path(WORKSPACE_DIR, rel_or_abs_path)
        if rel_or_abs_path.startswith("uploads/"):
            return _contained_path(UPLOADS_DIR, os.path.join(tool_dir, rel_or_abs_path))
        if rel_or_abs_path.startswith(("pair/", "unpair/")):
            return _contained_path(NHUOM_MO_DIR, os.path.join(NHUOM_MO_DIR, rel_or_abs_path))
        if rel_or_abs_path.startswith("data/"):
            return _contained_path(DATA_DIR, os.path.join(WORKSPACE_DIR, rel_or_abs_path))
        return _contained_path(WORKSPACE_DIR, os.path.join(WORKSPACE_DIR, rel_or_abs_path))

    def handle_scan_folder(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            folder_input = data.get('folderPath', '').strip()

            if not folder_input:
                self.send_json({"error": "Vui lòng nhập đường dẫn thư mục!"}, status=400)
                return

            abs_folder = self.resolve_path(folder_input)
            if not os.path.exists(abs_folder) or not os.path.isdir(abs_folder):
                self.send_json({"error": f"Directory does not exist: {folder_input}"}, status=404)
                return

            valid_exts = ('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp')
            files = sorted([
                f for f in os.listdir(abs_folder)
                if os.path.isfile(os.path.join(abs_folder, f)) and f.lower().endswith(valid_exts)
            ])

            folder_name = os.path.basename(os.path.normpath(abs_folder))
            # Trả về đường dẫn tương đối so với workspace nếu nằm trong workspace, ngược lại tuyệt đối
            image_items = []
            for f in files:
                full_p = os.path.join(abs_folder, f)
                try:
                    rel = os.path.relpath(full_p, WORKSPACE_DIR).replace('\\', '/')
                except Exception:
                    rel = full_p.replace('\\', '/')

                meta = {"width": 2000, "height": 1500}
                try:
                    meta = get_image_metadata(full_p)
                except Exception as ex:
                    print(f"Warning: Không đọc được metadata {full_p}: {ex}")

                image_items.append({
                    "name": f,
                    "path": rel,
                    "fullPath": full_p,
                    "width": meta.get("width", 2000),
                    "height": meta.get("height", 1500)
                })

            self.send_json({
                "status": "success",
                "folderName": folder_name,
                "folderPath": abs_folder,
                "total": len(image_items),
                "images": image_items
            })
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_list_images(self):
        try:
            result = {"pair": [], "unpair": [], "uploads": []}
            valid_exts = ('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp')

            # 1. Thư mục NhuomMo (pair, unpair)
            for category in ["pair", "unpair"]:
                cat_dir = os.path.join(NHUOM_MO_DIR, category)
                if os.path.exists(cat_dir):
                    files = sorted([f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))])
                    result[category] = [f"{category}/{f}" for f in files if f.lower().endswith(valid_exts)]

            # 2. Thư mục uploads
            if os.path.exists(UPLOADS_DIR):
                up_files = sorted([f for f in os.listdir(UPLOADS_DIR) if os.path.isfile(os.path.join(UPLOADS_DIR, f))])
                result["uploads"] = [f"uploads/{f}" for f in up_files if f.lower().endswith(valid_exts)]

            self.send_json(result)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_thumbnail(self, query):
        if 'path' not in query:
            self.send_error(400, "Missing path parameter")
            return

        rel_path = query['path'][0]
        abs_path = self.resolve_path(rel_path)

        # The current frontend uses the historical data/output fallback URL while
        # generated artifacts are published under data/result.
        if not os.path.exists(abs_path) and rel_path.replace('\\', '/').startswith('data/output/'):
            fallback = os.path.join(OUTPUTS_DIR, os.path.basename(abs_path))
            abs_path = _contained_path(OUTPUTS_DIR, fallback)

        if not os.path.exists(abs_path):
            self.send_error(404, "Image Not Found")
            return

        try:
            img = read_image(abs_path)
            thumb = create_thumbnail(img, max_size=(320, 320))
            thumb_bgr = cv2.cvtColor(thumb, cv2.COLOR_RGB2BGR)
            _, encoded = cv2.imencode('.jpg', thumb_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])

            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded.tobytes())
        except Exception as e:
            self.send_error(500, f"Thumbnail Error: {str(e)}")

    def handle_serve_image(self, query):
        if 'path' not in query:
            self.send_error(400, "Missing path parameter")
            return
        rel_path = query['path'][0]
        try:
            abs_path = self.resolve_path(rel_path)
            if not _is_allowed_image_path(abs_path):
                raise ValueError("Image path outside approved data directories")
        except (ValueError, OSError):
            self.send_error(403, "Image path outside approved data directories")
            return

        if not os.path.isfile(abs_path):
            self.send_error(404, "Image Not Found")
            return

        ext = os.path.splitext(abs_path)[1].lower()
        mime, _ = mimetypes.guess_type(abs_path)
        self.serve_file(abs_path, mime or 'application/octet-stream')

    def handle_start_auto_stitching(self):
        global stitching_task
        with stitching_task_lock:
            if stitching_task["is_running"]:
                self.send_json({"status": "busy", "message": "Quá trình ghép ảnh đang chạy!"}, status=409)
                return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(body)

        image_rel_paths = data.get("images", [])
        folder_name = data.get("folderName", None)

        if not isinstance(image_rel_paths, list) or not all(isinstance(path, str) for path in image_rel_paths):
            self.send_json({"status": "error", "message": "Invalid image list"}, status=400)
            return
        if len(image_rel_paths) > 512:
            self.send_json({"status": "error", "message": "Image list exceeds 512 files limit"}, status=413)
            return
        if len(image_rel_paths) < 2:
            self.send_json({"status": "error", "message": "At least 2 images required for stitching!"}, status=400)
            return

        # Chuyển thành đường dẫn tuyệt đối
        abs_paths = []
        for rel in image_rel_paths:
            p = self.resolve_path(rel)
            if os.path.exists(p):
                abs_paths.append(p)

        if len(abs_paths) < 2:
            self.send_json({"status": "error", "message": "Image files do not exist on system!"}, status=400)
            return

        # Xác định tên file xuất theo tên thư mục nguồn
        if not folder_name:
            folder_name = os.path.basename(os.path.dirname(abs_paths[0]))

        project_layers = None
        if data.get("project") and isinstance(data["project"], dict) and data["project"].get("layers"):
            project_layers = data["project"]["layers"]
        else:
            try:
                from backend.project_store import load_project
                proj = load_project(folder_name)
                if proj and proj.layers:
                    project_layers = [l.to_dict() if hasattr(l, 'to_dict') else l.__dict__ for l in proj.layers]
            except Exception:
                project_layers = None

        options = {
            "featureMethod": data.get("featureMethod", "sift"),
            "motionModel": data.get("motionModel", "affine"),
            "backgroundMode": data.get("backgroundMode", "white"),
            "autoCrop": data.get("autoCrop", False),
            "exportFormat": data.get("exportFormat", None),
            "customOutputName": folder_name,
            "project_layers": project_layers if data.get("useCanvasLayout") else None
        }

        # Khởi chạy trong Background Thread
        with stitching_task_lock:
            if stitching_task["is_running"]:
                self.send_json({"status": "busy", "message": "Quá trình ghép ảnh đang chạy!"}, status=409)
                return
            stitching_task.update({"is_running": True, "progress": 0, "logs": [], "error": None, "result": None})
        thread = threading.Thread(target=background_stitching_worker, args=(abs_paths, options), daemon=True)
        thread.start()

        self.send_json({"status": "started", "total_images": len(abs_paths), "outputFolder": "data/result", "outputName": folder_name})

    def handle_stitch_status(self):
        with stitching_task_lock:
            snapshot = json.loads(json.dumps(stitching_task))
        self.send_json(snapshot)

    def handle_serve_dzi(self, req_path):
        # /dzi/... ví dụ: /dzi/1033-YCT26_A_dzi/1033-YCT26_A.dzi hoặc /dzi/1033-YCT26_A_dzi/1033-YCT26_A_files/10/0_0.jpg
        rel = urllib.parse.unquote(req_path[len("/dzi/"):])

        # Thử 1: Trực tiếp trong OUTPUTS_DIR (data/output)
        target_path = os.path.abspath(os.path.join(OUTPUTS_DIR, rel))
        try:
            target_path = _contained_path(OUTPUTS_DIR, target_path)
        except ValueError:
            self.send_error(403, "DZI path outside output directory")
            return

        # Thử 2: Trong data/output nếu path thiếu
        if not os.path.exists(target_path):
            alt_path = os.path.abspath(os.path.join(WORKSPACE_DIR, "data", "output", rel))
            try:
                alt_path = _contained_path(os.path.join(WORKSPACE_DIR, "data", "output"), alt_path)
            except ValueError:
                alt_path = ""
            if alt_path and os.path.exists(alt_path):
                target_path = alt_path

        if not os.path.exists(target_path) or os.path.isdir(target_path):
            self.send_error(404, f"DZI Tile Not Found: {rel}")
            return

        ext = os.path.splitext(target_path)[1].lower()
        if ext == '.dzi':
            content_type = "application/xml"
        elif ext in ['.jpg', '.jpeg']:
            content_type = "image/jpeg"
        elif ext == '.png':
            content_type = "image/png"
        else:
            content_type = "application/octet-stream"

        self.serve_file(target_path, content_type)

    def handle_available_folders(self):
        """Tự động quét các thư mục chứa ảnh trong workspace (data/4X, data/10X, data/input, NhuomMo)"""
        try:
            valid_exts = ('.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp')
            found_folders = []

            # Các thư mục gốc cần quét
            search_roots = [
                os.path.join(WORKSPACE_DIR, "data", "4X"),
                os.path.join(WORKSPACE_DIR, "data", "10X"),
                os.path.join(WORKSPACE_DIR, "data", "input"),
                os.path.join(WORKSPACE_DIR, "NhuomMo")
            ]

            for s_root in search_roots:
                if not os.path.exists(s_root):
                    continue
                # Quét trực tiếp s_root
                direct_images = [f for f in os.listdir(s_root) if os.path.isfile(os.path.join(s_root, f)) and f.lower().endswith(valid_exts)]
                if len(direct_images) >= 2:
                    rel_p = os.path.relpath(s_root, WORKSPACE_DIR).replace('\\', '/')
                    found_folders.append({
                        "name": f"{os.path.basename(s_root)} ({len(direct_images)} ảnh)",
                        "folderName": os.path.basename(s_root),
                        "path": rel_p,
                        "count": len(direct_images)
                    })

                # Quét các thư mục con cấp 1 & 2
                for root, dirs, files in os.walk(s_root):
                    if root == s_root:
                        continue
                    imgs = [f for f in files if f.lower().endswith(valid_exts)]
                    if len(imgs) >= 2:
                        rel_p = os.path.relpath(root, WORKSPACE_DIR).replace('\\', '/')
                        folder_base = os.path.basename(root)
                        parent_base = os.path.basename(os.path.dirname(root))
                        found_folders.append({
                            "name": f"{parent_base}/{folder_base} ({len(imgs)} ảnh)",
                            "folderName": folder_base,
                            "path": rel_p,
                            "count": len(imgs)
                        })

            self.send_json({"status": "success", "folders": found_folders})
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_upload_file(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            file_name = data.get('fileName')
            data_url = data.get('dataUrl')
            folder_name = data.get('folderName', 'uploads').strip()

            if not file_name or not data_url:
                self.send_json({"error": "Missing parameters"}, status=400)
                return
            if os.path.basename(file_name) != file_name:
                self.send_json({"error": "Tên file is invalid"}, status=400)
                return
            if folder_name != 'uploads' and (os.path.basename(folder_name) != folder_name or folder_name in ('.', '..')):
                self.send_json({"error": "Tên folder is invalid"}, status=400)
                return

            header, encoded = data_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            if len(image_bytes) > MAX_UPLOAD_DECODED_BYTES:
                self.send_json({"error": "File upload quá lớn"}, status=413)
                return

            if folder_name and folder_name != 'uploads':
                target_folder = os.path.join(WORKSPACE_DIR, "data", "input", folder_name)
                rel_path = f"data/input/{folder_name}/{file_name}"
            else:
                target_folder = UPLOADS_DIR
                rel_path = f"uploads/{file_name}"

            os.makedirs(target_folder, exist_ok=True)
            containment_root = DATA_DIR if folder_name and folder_name != 'uploads' else UPLOADS_DIR
            save_path = _contained_path(containment_root, os.path.join(target_folder, file_name))
            with open(save_path, 'wb') as f:
                f.write(image_bytes)

            self.send_json({"status": "success", "path": rel_path, "fileName": file_name, "folderName": folder_name})
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_upload_batch(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            folder_name = data.get('folderName', 'uploads').strip()
            files = data.get('files', [])

            if not isinstance(files, list) or not files:
                self.send_json({"error": "Danh sách file trống"}, status=400)
                return
            if len(files) > 256:
                self.send_json({"error": "Upload batch exceeds limit 256 file"}, status=413)
                return
            if folder_name != 'uploads' and (os.path.basename(folder_name) != folder_name or folder_name in ('.', '..')):
                self.send_json({"error": "Tên folder is invalid"}, status=400)
                return

            if folder_name and folder_name != 'uploads':
                target_folder = os.path.join(WORKSPACE_DIR, "data", "input", folder_name)
                prefix = f"data/input/{folder_name}"
            else:
                target_folder = UPLOADS_DIR
                prefix = "uploads"

            os.makedirs(target_folder, exist_ok=True)
            saved_items = []

            for item in files:
                f_name = item.get('fileName')
                d_url = item.get('dataUrl')
                if f_name and d_url:
                    if os.path.basename(f_name) != f_name:
                        continue
                    header, encoded = d_url.split(",", 1)
                    img_bytes = base64.b64decode(encoded)
                    if len(img_bytes) > MAX_UPLOAD_DECODED_BYTES:
                        continue
                    containment_root = DATA_DIR if folder_name and folder_name != 'uploads' else UPLOADS_DIR
                    s_path = _contained_path(containment_root, os.path.join(target_folder, f_name))
                    with open(s_path, 'wb') as f:
                        f.write(img_bytes)

                    meta = {"width": 2000, "height": 1500}
                    try:
                        meta = get_image_metadata(s_path)
                    except Exception:
                        pass

                    saved_items.append({
                        "name": f_name,
                        "path": f"{prefix}/{f_name}",
                        "width": meta.get("width", 2000),
                        "height": meta.get("height", 1500)
                    })

            self.send_json({
                "status": "success",
                "folderName": folder_name,
                "total": len(saved_items),
                "images": saved_items
            })
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_get_project(self, proj_id):
        try:
            from backend.project_store import load_project
            proj = load_project(proj_id)
            if proj:
                self.send_json({"status": "success", "project": proj.to_dict()})
            else:
                self.send_json({"status": "not_found", "message": "Project không tồn tại"}, status=404)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_save_project(self, proj_id):
        try:
            from backend.project_schemas import ProjectState
            from backend.project_store import save_project
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            proj = ProjectState.from_dict(data)
            if proj.id != proj_id:
                self.send_json({"error": "Project id trong body không khớp URL"}, status=400)
                return
            from backend.project_store import load_project
            existing = load_project(proj_id)
            if existing:
                persisted_paths = {layer.id: layer.sourcePath for layer in existing.layers}
                for layer in proj.layers:
                    if layer.id in persisted_paths:
                        layer.sourcePath = persisted_paths[layer.id]
            for layer in proj.layers:
                resolved_source = self.resolve_path(layer.sourcePath)
                if not os.path.isfile(resolved_source):
                    self.send_json({"error": f"Source không tồn tại: {layer.sourcePath}"}, status=400)
                    return
                layer.sourcePath = os.path.relpath(resolved_source, WORKSPACE_DIR).replace('\\', '/')
            res = save_project(proj)
            self.send_json(res, status=409 if res.get("status") == "conflict" else 200)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_inspect_patches(self, proj_id):
        try:
            from backend.project_schemas import ProjectState
            from backend.patch_inspector import inspect_patches_at_world_region

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if content_length > 0 else {}

            shape_type = data.get("shapeType", "rectangle")
            points_world = data.get("pointsWorld")
            world_rect = data.get("worldRect")
            output_size = data.get("outputSize", 256)
            layer_ids = data.get("layerIds")
            
            proj = None
            if "project" in data and isinstance(data["project"], dict) and data["project"].get("layers"):
                try:
                    proj = ProjectState.from_dict(data["project"])
                except Exception:
                    proj = None
            if not proj:
                from backend.project_store import load_project
                proj = load_project(proj_id)

            if not proj:
                self.send_json({"error": "Project không tồn tại"}, status=404)
                return

            if not points_world and not world_rect:
                self.send_json({"error": "pointsWorld hoặc worldRect is invalid"}, status=400)
                return

            res = inspect_patches_at_world_region(
                project_state=proj,
                shape_type=shape_type,
                points_world=points_world,
                world_rect=world_rect,
                output_size=output_size,
                layer_ids=layer_ids,
                workspace_root=WORKSPACE_DIR
            )

            self.send_json({"status": "success", **res})
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_native_patch(self, proj_id):
        try:
            from backend.project_schemas import ProjectState
            from backend.patch_inspector import extract_native_patch_image

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if content_length > 0 else {}

            layer_id = data.get("layerId")
            points_world = data.get("pointsWorld")
            shape_type = data.get("shapeType", "rectangle")
            max_pixels = data.get("maxPixels", 16777216)
            
            proj = None
            if "project" in data and isinstance(data["project"], dict) and data["project"].get("layers"):
                try:
                    proj = ProjectState.from_dict(data["project"])
                except Exception:
                    proj = None
            if not proj:
                from backend.project_store import load_project
                proj = load_project(proj_id)

            if not proj:
                self.send_json({"error": "Project không tồn tại"}, status=404)
                return

            layer = next((l for l in proj.layers if l.id == layer_id), None)
            if not layer or not layer.visible:
                self.send_json({"error": f"Layer {layer_id} không tồn tại trong project"}, status=404)
                return

            if not points_world or len(points_world) < 3:
                # Nếu chỉ có worldRect
                world_rect = data.get("worldRect")
                if world_rect and len(world_rect) >= 4:
                    rx, ry, rw, rh = world_rect[:4]
                    points_world = [[rx, ry], [rx+rw, ry], [rx+rw, ry+rh], [rx, ry+rh]]
                else:
                    self.send_json({"error": "pointsWorld is invalid"}, status=400)
                    return

            patch_result = extract_native_patch_image(
                layer=layer,
                points_world=points_world,
                shape_type=shape_type,
                max_pixels=max_pixels,
                workspace_root=WORKSPACE_DIR
            )

            png_bytes = patch_result["png_bytes"]
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png_bytes)))
            self.send_header("X-Patch-Width", str(patch_result["width"]))
            self.send_header("X-Patch-Height", str(patch_result["height"]))
            self.send_header("X-Resolution-Limited", "true" if patch_result["is_resolution_limited"] else "false")
            self.send_header("X-Sampling-Scale", str(patch_result["sampling_scale"]))
            self.send_header("X-Valid-Coverage", str(patch_result["valid_coverage"]))
            self.end_headers()
            self.wfile.write(png_bytes)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_manual_export(self, proj_id):
        try:
            from backend.project_schemas import ProjectState
            from backend.manual_export import export_manual_project

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if content_length > 0 else {}

            from backend.project_store import load_project
            proj = load_project(proj_id)

            if not proj or not proj.layers:
                self.send_json({"error": "Project không có layer nào để xuất"}, status=400)
                return

            def update_progress(percent, step):
                global stitching_task
                with stitching_task_lock:
                    stitching_task["is_running"] = True
                    stitching_task["progress"] = percent
                    stitching_task["step_name"] = step
                    stitching_task["logs"].append({"percent": percent, "step": step})

            with stitching_task_lock:
                if stitching_task["is_running"]:
                    self.send_json({"status": "busy", "message": "Một task đang chạy"}, status=409)
                    return
                stitching_task.update({
                    "is_running": True,
                    "progress": 5,
                    "step_name": "Khởi tạo xuất ảnh thủ công...",
                    "logs": [],
                    "error": None,
                    "result": None
                })

            def run_export():
                global stitching_task
                try:
                    res = export_manual_project(
                        proj,
                        output_dir=OUTPUTS_DIR,
                        workspace_root=WORKSPACE_DIR,
                        output_name=proj.folderName or proj_id,
                        export_format=data.get("exportFormat") or "tif",
                        background_mode=data.get("backgroundMode") or "white",
                        progress_callback=update_progress
                    )
                    with stitching_task_lock:
                        stitching_task["is_running"] = False
                        stitching_task["progress"] = 100
                        stitching_task["step_name"] = "Xuất hoàn tất!"
                        stitching_task["result"] = res
                except Exception as ex:
                    with stitching_task_lock:
                        stitching_task["is_running"] = False
                        stitching_task["error"] = str(ex)

            thread = threading.Thread(target=run_export)
            thread.daemon = True
            thread.start()

            self.send_json({"status": "started", "projectId": proj_id})
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_save_wsi(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            folder_name = data.get('folderName', 'stitched_wsi')
            target_dir = data.get('targetDir', 'data/result').strip()
            export_format = data.get('exportFormat', 'tif')
            source_preview_file = data.get('sourcePreviewFile') # ví dụ data/result/2586A.tif

            if os.path.basename(folder_name) != folder_name or export_format.lower() not in ('tif', 'tiff', 'png', 'jpg', 'jpeg', 'bmp'):
                self.send_json({"error": "Tên output hoặc định dạng is invalid"}, status=400)
                return
            abs_target_dir = self.resolve_path(target_dir)

            os.makedirs(abs_target_dir, exist_ok=True)
            out_filename = f"{folder_name}.{export_format}"
            final_out_path = os.path.join(abs_target_dir, out_filename)

            # Tìm file nguồn preview
            src = None
            if source_preview_file:
                candidate = self.resolve_path(source_preview_file)
                if os.path.exists(candidate):
                    src = candidate
            else:
                default_preview = os.path.join(WORKSPACE_DIR, "data", "result", out_filename)
                if not os.path.exists(default_preview):
                    default_preview = os.path.join(WORKSPACE_DIR, "data", "output", out_filename)
                if os.path.exists(default_preview):
                    src = os.path.abspath(default_preview)

            if not src or not os.path.exists(src):
                return self.send_json({"error": "Không tìm thấy dữ liệu ảnh đã ghép. Hãy bấm Ghép Ảnh trước."}, status=400)

            # Nếu đường dẫn nguồn và đích khác nhau, thực hiện copy
            if os.path.normpath(src) != os.path.normpath(final_out_path):
                import shutil
                try:
                    shutil.copy2(src, final_out_path)
                except Exception as copy_err:
                    # Thử đọc bytes và ghi lại nếu copy2 bị lock metadata
                    with open(src, 'rb') as f_in, open(final_out_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

            self.send_json({
                "status": "success",
                "savedPath": final_out_path,
                "fileName": out_filename,
                "folder": abs_target_dir
            })
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def handle_save_legacy(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            image_data_url = data.get('imageData')
            file_name = data.get('fileName')
            save_dir = data.get('saveDir', 'aligned')

            if not image_data_url or os.path.basename(file_name or '') != file_name:
                self.send_json({"error": "Dữ liệu hoặc tên file is invalid"}, status=400)
                return

            header, encoded = image_data_url.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            if len(image_bytes) > MAX_UPLOAD_DECODED_BYTES:
                self.send_json({"error": "Ảnh quá lớn"}, status=413)
                return

            target_dir = self.resolve_path(save_dir)
            os.makedirs(target_dir, exist_ok=True)
            target_path = _contained_path(target_dir, os.path.join(target_dir, file_name))
            with open(target_path, 'wb') as f:
                f.write(image_bytes)

            self.send_json({"status": "success", "savedPath": target_path})
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

def run(server_class=ThreadingHTTPServer, handler_class=AlignmentToolRequestHandler, port=PORT):
    for p in [port, 5051, 8080, 8888, 3000]:
        try:
            server_address = (HOST, p)
            httpd = server_class(server_address, handler_class)
            print(f"==================================================")
            print(f"  OMNISTITCH STUDIO SERVER ĐANG CHẠY")
            print(f"  URL: http://localhost:{p}")
            print(f"  Output Directory: data/output/")
            print(f"==================================================")
            httpd.serve_forever()
            break
        except Exception as e:
            print(f"Port {p} không khả dụng ({e}), thử port tiếp theo...")

def main():
    """Launch the local OmniStitch Studio HTTP server."""
    run()


if __name__ == '__main__':
    main()
