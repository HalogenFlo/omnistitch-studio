import os
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.global_stitching import GlobalStitcher
from backend.matcher import FeatureMatcher


def translation(x, y=0.0):
    return np.array(
        [[1.0, 0.0, x], [0.0, 1.0, y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


class TestRegistrationCore(unittest.TestCase):
    def test_binary_descriptor_matching_applies_ratio_filter(self):
        desc1 = np.array([[0], [255]], dtype=np.uint8)
        desc2 = np.array([[0], [15], [255], [240]], dtype=np.uint8)
        matcher = FeatureMatcher(method="orb", ratio_threshold=0.8)

        matches = matcher.match_pair(desc1, desc2)

        self.assertEqual([match.queryIdx for match in matches], [0, 1])
        self.assertEqual([match.trainIdx for match in matches], [0, 2])

    def test_affine_estimation_recovers_known_transform(self):
        source = np.array(
            [
                [0, 0], [20, 0], [40, 0], [0, 20], [20, 20], [40, 20],
                [0, 40], [20, 40], [40, 40], [10, 30], [30, 10], [35, 25],
            ],
            dtype=np.float32,
        )
        expected = np.array(
            [[1.05, 0.08, 13.0], [-0.04, 0.97, -7.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        target = cv2.transform(source.reshape(-1, 1, 2), expected[:2]).reshape(-1, 2)
        kp1 = [cv2.KeyPoint(float(x), float(y), 1) for x, y in target]
        kp2 = [cv2.KeyPoint(float(x), float(y), 1) for x, y in source]
        matches = [cv2.DMatch(i, i, 0.0) for i in range(len(source))]

        matcher = FeatureMatcher(method="sift", min_inliers=8, motion_model="affine")
        actual, mask, inliers, confidence = matcher.estimate_transformation(kp1, kp2, matches)

        self.assertEqual(inliers, len(source))
        self.assertTrue(np.all(mask == 1))
        self.assertGreater(confidence, 0.0)
        np.testing.assert_allclose(actual, expected, atol=1e-5)

    def test_estimation_rejects_too_few_matches(self):
        matcher = FeatureMatcher(method="orb", min_inliers=8, motion_model="affine")
        actual, mask, inliers, confidence = matcher.estimate_transformation([], [], [])
        self.assertIsNone(actual)
        self.assertIsNone(mask)
        self.assertEqual(inliers, 0)
        self.assertEqual(confidence, 0.0)

    def test_spanning_forest_selects_high_confidence_edges(self):
        images = {index: np.zeros((10, 10, 3), dtype=np.uint8) for index in range(3)}
        transforms = {
            (0, 1): translation(10),
            (1, 0): translation(-10),
            (1, 2): translation(20),
            (2, 1): translation(-20),
            (0, 2): translation(100),
            (2, 0): translation(-100),
        }
        confidence = {
            (0, 1): 10.0, (1, 0): 10.0,
            (1, 2): 9.0, (2, 1): 9.0,
            (0, 2): 1.0, (2, 0): 1.0,
        }

        stitcher = GlobalStitcher(images, {}, {}, transforms)
        global_transforms, edges = stitcher.build_spanning_tree(confidence)

        self.assertEqual(edges, [(1, 0), (1, 2)])
        np.testing.assert_allclose(global_transforms[1], np.eye(3))
        np.testing.assert_allclose(global_transforms[0], translation(-10))
        np.testing.assert_allclose(global_transforms[2], translation(20))

    def test_spanning_forest_places_disconnected_images(self):
        images = {index: np.zeros((20, 30, 3), dtype=np.uint8) for index in range(2)}
        stitcher = GlobalStitcher(images, {}, {}, {})

        global_transforms, edges = stitcher.build_spanning_tree({})

        self.assertEqual(edges, [])
        self.assertEqual(set(global_transforms), {0, 1})
        self.assertFalse(np.allclose(global_transforms[0], global_transforms[1]))


if __name__ == "__main__":
    unittest.main()
