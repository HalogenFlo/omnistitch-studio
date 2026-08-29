import unittest
import os
import tempfile
from unittest import mock

import numpy as np

from backend.wsi_exporter import _downsample_rgba, _publish_staged_artifacts, export_wsi_multiformat


class TestDziAlpha(unittest.TestCase):
    def test_downsample_is_premultiplied_alpha_aware(self):
        pixels = np.array([[[255, 0, 0, 255], [0, 0, 255, 0]]], dtype=np.uint8)
        reduced = _downsample_rgba(pixels, (1, 1))[0, 0]
        self.assertAlmostEqual(int(reduced[3]), 127, delta=1)
        self.assertGreater(int(reduced[0]), 250)
        self.assertLess(int(reduced[2]), 2)

    def test_failed_dzi_does_not_publish_partial_artifacts(self):
        image = np.full((2, 2, 4), [1, 2, 3, 255], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = os.path.join(output_dir, "sample.png")
            with open(output_path, "wb") as stream:
                stream.write(b"old-output")
            with mock.patch(
                "backend.wsi_exporter.generate_dzi_pyramid",
                side_effect=RuntimeError("forced DZI failure")
            ):
                with self.assertRaises(RuntimeError):
                    export_wsi_multiformat(image, output_dir, folder_name="sample", target_ext="png")
            with open(output_path, "rb") as stream:
                self.assertEqual(stream.read(), b"old-output")
            self.assertFalse(os.path.exists(os.path.join(output_dir, "sample_dzi")))

    def test_publication_replace_failure_restores_prior_artifact_set(self):
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory(dir=output_dir) as stage:
            destinations = [os.path.join(output_dir, "image.tif"), os.path.join(output_dir, "meta.json")]
            staged = [os.path.join(stage, "image.tif"), os.path.join(stage, "meta.json")]
            for index, path in enumerate(destinations):
                with open(path, "wb") as stream:
                    stream.write(f"old-{index}".encode())
            for index, path in enumerate(staged):
                with open(path, "wb") as stream:
                    stream.write(f"new-{index}".encode())
            real_replace = os.replace
            calls = 0

            def fail_second_publish(source, destination):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("forced publication failure")
                return real_replace(source, destination)

            with mock.patch("backend.wsi_exporter.os.replace", side_effect=fail_second_publish):
                with self.assertRaises(OSError):
                    _publish_staged_artifacts(stage, list(zip(staged, destinations)))
            for index, path in enumerate(destinations):
                with open(path, "rb") as stream:
                    self.assertEqual(stream.read(), f"old-{index}".encode())

    def test_publication_directory_replace_succeeds_when_destination_exists(self):
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory(dir=output_dir) as stage:
            dest_dir = os.path.join(output_dir, "sample_dzi")
            staged_dir = os.path.join(stage, "sample_dzi")
            os.makedirs(os.path.join(dest_dir, "sub"), exist_ok=True)
            with open(os.path.join(dest_dir, "sub", "old.txt"), "w") as f:
                f.write("old-tile")
            os.makedirs(os.path.join(staged_dir, "sub"), exist_ok=True)
            with open(os.path.join(staged_dir, "sub", "new.txt"), "w") as f:
                f.write("new-tile")

            _publish_staged_artifacts(stage, [(staged_dir, dest_dir)])
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "sub", "new.txt")))
            with open(os.path.join(dest_dir, "sub", "new.txt"), "r") as f:
                self.assertEqual(f.read(), "new-tile")


if __name__ == "__main__":
    unittest.main()
