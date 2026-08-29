"""
Chức năng: Quản lý lưu trữ, truy xuất Project State và kiểm tra Revision Conflict
Lí do tạo: Đảm bảo tính bền vững (Persistence) của dự án, autosave không mất dữ liệu
Đường dẫn: tool/image_alignment/backend/project_store.py
"""

import os
import json
import time
import tempfile
import threading
import contextlib
import errno
import time as time_module
from typing import Optional, Dict, Any, List
from .project_schemas import ProjectState

PROJECTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "projects"))
_STORE_LOCK = threading.RLock()


@contextlib.contextmanager
def _project_file_lock(project_id: str, timeout: float = 30.0):
    """Serialize project CAS across threads and server processes."""
    lock_path = os.path.join(get_projects_dir(), f".{project_id}.lock")
    lock_file = open(lock_path, "a+b")
    acquired = False
    try:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time_module.monotonic() + timeout
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EDEADLK, errno.EAGAIN) or time_module.monotonic() >= deadline:
                        raise TimeoutError(f"Không thể khóa project {project_id}") from exc
                    time_module.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            acquired = True
        yield
    finally:
        try:
            if acquired:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()

def get_projects_dir() -> str:
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    return PROJECTS_DIR

def get_project_file_path(project_id: str) -> str:
    safe_id = "".join(c for c in project_id if c.isalnum() or c in ("-", "_")).rstrip()
    if not safe_id or safe_id != project_id:
        raise ValueError("Project id không hợp lệ")
    return os.path.join(get_projects_dir(), f"{safe_id}.json")

def save_project(state: ProjectState) -> Dict[str, Any]:
    """Lưu project state vào đĩa, kiểm tra và tăng revision"""
    file_path = get_project_file_path(state.id)
    with _STORE_LOCK, _project_file_lock(state.id):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            existing_rev = int(existing_data.get("revision", 1))
            if state.revision != existing_rev:
                return {
                    "status": "conflict",
                    "message": f"Revision yêu cầu {state.revision}, revision hiện tại {existing_rev}",
                    "currentRevision": existing_rev
                }
        elif state.revision != 1:
            return {
                "status": "conflict",
                "message": f"Project mới phải bắt đầu ở revision 1, nhận {state.revision}",
                "currentRevision": None
            }

        next_revision = state.revision + 1
        next_updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        serialized = state.to_dict()
        serialized["revision"] = next_revision
        serialized["updatedAt"] = next_updated_at
        fd, temp_path = tempfile.mkstemp(prefix=f".{state.id}.", suffix=".tmp", dir=os.path.dirname(file_path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
            state.revision = next_revision
            state.updatedAt = next_updated_at
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    return {
        "status": "success",
        "projectId": state.id,
        "revision": state.revision,
        "updatedAt": state.updatedAt
    }

def load_project(project_id: str) -> Optional[ProjectState]:
    """Đọc project state từ đĩa"""
    file_path = get_project_file_path(project_id)
    if not os.path.exists(file_path):
        return None
    try:
        with _STORE_LOCK:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        return ProjectState.from_dict(data)
    except Exception as e:
        print(f"Lỗi load project {project_id}: {e}")
        return None

def list_projects() -> List[Dict[str, Any]]:
    """Liệt kê danh sách project đã lưu"""
    p_dir = get_projects_dir()
    results = []
    for f in os.listdir(p_dir):
        if f.endswith(".json"):
            p_id = f[:-5]
            full_path = os.path.join(p_dir, f)
            try:
                with open(full_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                results.append({
                    "id": p_id,
                    "folderName": data.get("folderName", ""),
                    "revision": data.get("revision", 1),
                    "layerCount": len(data.get("layers", [])),
                    "updatedAt": data.get("updatedAt", "")
                })
            except Exception:
                continue
    return results
