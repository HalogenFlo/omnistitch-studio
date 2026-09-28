import unittest
import os
from backend.io_utils import extract_case_code

class TestCaseGrouping(unittest.TestCase):
    def test_extract_case_code_color_and_raw(self):
        # 123 tho và 123 mau theo đúng ví dụ của người dùng
        self.assertEqual(extract_case_code("123_tho"), "123")
        self.assertEqual(extract_case_code("123_mau"), "123")
        self.assertEqual(extract_case_code("123 tho"), "123")
        self.assertEqual(extract_case_code("123 mau"), "123")
        self.assertEqual(extract_case_code("123"), "123")

    def test_extract_case_code_clinical_specimens(self):
        # Bộ dữ liệu thực tế tại phòng lab NCKH
        self.assertEqual(extract_case_code("1033-YCT26_A"), "1033-YCT26")
        self.assertEqual(extract_case_code("1033-YCT26_B"), "1033-YCT26")
        self.assertEqual(extract_case_code("1033-YCT26_THO_A"), "1033-YCT26")
        self.assertEqual(extract_case_code("1033-YCT26_THO_B"), "1033-YCT26")
        
        # Các ca có biến thể số thứ tự
        self.assertEqual(extract_case_code("1254-YCT26_THO_1_A"), "1254-YCT26")
        self.assertEqual(extract_case_code("1254-YCT26_A"), "1254-YCT26")
        self.assertEqual(extract_case_code("1117-YCT26_THO_B"), "1117-YCT26")
        self.assertEqual(extract_case_code("1117-YCT26_B"), "1117-YCT26")

    def test_extract_case_code_with_paths_and_extensions(self):
        # Đường dẫn file và đuôi mở rộng
        self.assertEqual(extract_case_code("data/4X/1033-YCT26_A"), "1033-YCT26")
        self.assertEqual(extract_case_code("data/result/1033-YCT26_THO_A.tif"), "1033-YCT26")
        self.assertEqual(extract_case_code("C:\\data\\10X\\1058-YCT26_A.tiff"), "1058-YCT26")

    def test_edge_cases(self):
        self.assertEqual(extract_case_code(""), "ungrouped")
        self.assertEqual(extract_case_code(None), "ungrouped")

if __name__ == '__main__':
    unittest.main()
