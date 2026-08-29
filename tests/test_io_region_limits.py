import os
import tempfile
import unittest
from unittest import mock

import numpy as np
import tifffile

from backend.io_utils import read_image_region


class TestImageRegionLimits(unittest.TestCase):
    def test_uncompressed_tiff_uses_memmap_region_under_decoder_cap(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "plain.tif")
            image = np.arange(100, dtype=np.uint8).reshape(10, 10)
            tifffile.imwrite(path, image)
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_TIFF_DECODE_PIXELS": "1"}):
                region = read_image_region(path, (2, 3, 5, 7))
            self.assertEqual(region.shape, (4, 3, 3))
            np.testing.assert_array_equal(region[:, :, 0], image[3:7, 2:5])

    def test_non_memmappable_tiff_is_guarded_before_pillow_decode(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "compressed.tif")
            tifffile.imwrite(path, np.zeros((20, 20), dtype=np.uint8), compression="deflate")
            with mock.patch.dict(os.environ, {"IMAGE_ALIGNMENT_MAX_TIFF_DECODE_PIXELS": "100"}):
                with self.assertRaisesRegex(MemoryError, "decoder guard"):
                    read_image_region(path, (0, 0, 2, 2))


if __name__ == "__main__":
    unittest.main()
