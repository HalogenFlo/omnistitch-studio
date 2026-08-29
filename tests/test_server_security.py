import os
import unittest

from server import (
    DATA_DIR,
    WORKSPACE_DIR,
    _contained_path,
    _is_allowed_image_path,
    _same_origin_cors_value,
)


class TestServerSecurity(unittest.TestCase):
    def test_path_containment_rejects_parent_escape(self):
        outside = os.path.join(WORKSPACE_DIR, "..", "outside.png")
        with self.assertRaises(ValueError):
            _contained_path(WORKSPACE_DIR, outside)

    def test_path_containment_accepts_workspace_file(self):
        inside = os.path.join(WORKSPACE_DIR, "data", "image.png")
        self.assertEqual(_contained_path(WORKSPACE_DIR, inside), os.path.realpath(inside))

    def test_image_endpoint_scope_rejects_source_and_non_image_files(self):
        self.assertFalse(_is_allowed_image_path(os.path.join(WORKSPACE_DIR, "server.py")))
        self.assertFalse(_is_allowed_image_path(os.path.join(DATA_DIR, "project.json")))
        self.assertTrue(_is_allowed_image_path(os.path.join(DATA_DIR, "image.tif")))

    def test_cors_only_echoes_exact_same_origin(self):
        self.assertEqual(_same_origin_cors_value("http://127.0.0.1:5050", "127.0.0.1:5050"), "http://127.0.0.1:5050")
        self.assertIsNone(_same_origin_cors_value("https://attacker.example", "127.0.0.1:5050"))
        self.assertIsNone(_same_origin_cors_value("http://localhost:9000", "127.0.0.1:5050"))


if __name__ == "__main__":
    unittest.main()
