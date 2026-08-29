import unittest
import os
import sys
import shutil
import tempfile
import multiprocessing
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.project_schemas import ProjectState, ProjectLayer, matrix_translate
from backend import project_store
from backend.project_store import save_project, load_project, list_projects


def _concurrent_save_worker(projects_dir, ready, start, results):
    project_store.PROJECTS_DIR = projects_dir
    state = project_store.load_project("concurrent")
    ready.put(True)
    start.wait(10)
    results.put(project_store.save_project(state)["status"])

class TestProjectStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_patch = mock.patch.object(project_store, "PROJECTS_DIR", self.temp_dir.name)
        self.projects_patch.start()

    def test_save_load_revision(self):
        layer = ProjectLayer("l1", "s1", 100, 100, sourceToWorld=matrix_translate(10, 20))
        proj = ProjectState("test_proj_1", revision=1, layers=[layer])
        
        # Initial save
        res1 = save_project(proj)
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["revision"], 2)
        
        # Reload project
        loaded = load_project("test_proj_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.revision, 2)
        self.assertEqual(len(loaded.layers), 1)

        # Attempt saving with stale revision -> Conflict
        old_proj = ProjectState("test_proj_1", revision=1, layers=[layer])
        res_conflict = save_project(old_proj)
        self.assertEqual(res_conflict["status"], "conflict")

        future_proj = ProjectState("test_proj_1", revision=99, layers=[layer])
        self.assertEqual(save_project(future_proj)["status"], "conflict")

    def test_schema_rejects_future_version_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            ProjectState.from_dict({"id": "future", "version": 999, "layers": []})
        duplicate = ProjectLayer("same", "s1", 1, 1).to_dict()
        with self.assertRaises(ValueError):
            ProjectState.from_dict({"id": "duplicate", "version": 3, "layers": [duplicate, duplicate]})

    def test_failed_atomic_replace_does_not_advance_revision(self):
        project = ProjectState("test_replace_failure", revision=1)
        with mock.patch(
            "backend.project_store.os.replace",
            side_effect=OSError("forced replace failure")
        ):
            with self.assertRaises(OSError):
                save_project(project)
        self.assertEqual(project.revision, 1)
        self.assertEqual(project.updatedAt, "")

    def test_cross_process_compare_and_swap_allows_only_one_writer(self):
        self.assertEqual(save_project(ProjectState("concurrent", revision=1))["status"], "success")
        context = multiprocessing.get_context("spawn")
        ready = context.Queue()
        results = context.Queue()
        start = context.Event()
        workers = [context.Process(target=_concurrent_save_worker, args=(self.temp_dir.name, ready, start, results)) for _ in range(2)]
        for worker in workers:
            worker.start()
        for _ in workers:
            ready.get(timeout=15)
        start.set()
        statuses = sorted(results.get(timeout=15) for _ in workers)
        for worker in workers:
            worker.join(15)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(statuses, ["conflict", "success"])

    def tearDown(self):
        self.projects_patch.stop()
        self.temp_dir.cleanup()

if __name__ == "__main__":
    unittest.main()
