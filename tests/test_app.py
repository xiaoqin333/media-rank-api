import unittest

from app import extract_year, is_allowed_image_url, normalize_media_type, normalize_source


class NormalizationTests(unittest.TestCase):
    def test_source_aliases(self):
        self.assertEqual(normalize_source("腾讯视频"), "tencent")
        self.assertEqual(normalize_source("IQIYI"), "iqiyi")
        self.assertEqual(normalize_source("芒果tv"), "mango")
        self.assertEqual(normalize_source("TheMovieDB"), "tmdb")

    def test_media_type_aliases(self):
        self.assertEqual(normalize_media_type("电视剧"), "tv")
        self.assertEqual(normalize_media_type("anime"), "anime")
        self.assertEqual(normalize_media_type("综艺"), "variety")

    def test_extract_year(self):
        self.assertEqual(extract_year("2026 / 都市 / 爱情"), 2026)
        self.assertIsNone(extract_year("暂无"))

    def test_image_allowlist(self):
        self.assertTrue(is_allowed_image_url("https://img3.doubanio.com/poster.jpg"))
        self.assertTrue(is_allowed_image_url("https://vcover-vt-pic.puui.qpic.cn/cover/350"))
        self.assertTrue(is_allowed_image_url("https://image.tmdb.org/t/p/w500/poster.jpg"))
        self.assertFalse(is_allowed_image_url("http://127.0.0.1/private"))


if __name__ == "__main__":
    unittest.main()
