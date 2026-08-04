import unittest

from vladder.candidates import detect_affine, detect_clamp, detect_div_power2
from vladder.extractor import extract_function


class ExtractorTests(unittest.TestCase):
    def test_extract_and_rename(self):
        source = "#include <stddef.h>\n\nvoid transform(float *dst, const float *src, size_t n) { dst[0] = src[0]; }\n"
        fn = extract_function(source, "transform")
        self.assertIn("void transform", fn.source)
        self.assertIn("void renamed", fn.renamed("renamed"))

    def test_detect_clamp(self):
        source = """
        void transform(float *dst, const float *src, size_t n) {
            for (size_t i = 0; i < n; ++i) {
                float x = src[i];
                if (x < -1.0f) { dst[i] = -1.0f; }
                else if (x > 1.0f) { dst[i] = 1.0f; }
                else { dst[i] = x; }
            }
        }
        """
        self.assertIsNotNone(detect_clamp(extract_function(source, "transform")))

    def test_detect_affine(self):
        source = """
        void transform(float *dst, const float *src, size_t n) {
            for (size_t i = 0; i < n; ++i) {
                dst[i] = src[i] * 2.0f + 3.0f;
            }
        }
        """
        self.assertIsNotNone(detect_affine(extract_function(source, "transform")))

    def test_detect_div_power2(self):
        source = """
        void transform(float *dst, const float *src, size_t n) {
            for (size_t i = 0; i < n; ++i) {
                dst[i] = src[i] / 2.0f;
            }
        }
        """
        self.assertIsNotNone(detect_div_power2(extract_function(source, "transform")))


if __name__ == "__main__":
    unittest.main()
