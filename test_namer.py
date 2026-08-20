import unittest
from namer import FilenameFormatter, sanitize_filename

class TestFilenameFormatter(unittest.TestCase):
    def setUp(self):
        self.formatter = FilenameFormatter(
            output_template="{title} - {author}.{ext}"
        )

    def test_sanitize_filename(self):
        raw = "Title: Subtitle / Part 1? <Special> | *Test*"
        sanitized = sanitize_filename(raw)
        self.assertNotIn(":", sanitized)
        self.assertNotIn("/", sanitized)
        self.assertNotIn("?", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertNotIn("|", sanitized)
        self.assertNotIn("*", sanitized)

    def test_pattern_match_title_dash_author(self):
        raw_name = "The Great Gatsby - F. Scott Fitzgerald.epub"
        ext = "epub"
        formatted, matched = self.formatter.parse_and_format(raw_name, ext)
        self.assertTrue(matched)
        self.assertEqual(formatted, "The Great Gatsby - F. Scott Fitzgerald.epub")

    def test_pattern_match_title_by_author(self):
        raw_name = "1984 by George Orwell.pdf"
        ext = "pdf"
        formatted, matched = self.formatter.parse_and_format(raw_name, ext)
        self.assertTrue(matched)
        self.assertEqual(formatted, "1984 - George Orwell.pdf")

    def test_pattern_match_bracket_author(self):
        raw_name = "[Isaac Asimov] Foundation.mobi"
        ext = "mobi"
        formatted, matched = self.formatter.parse_and_format(raw_name, ext)
        self.assertTrue(matched)
        self.assertEqual(formatted, "Foundation - Isaac Asimov.mobi")

    def test_fallback_no_match(self):
        raw_name = "SingleWordUnformattedEbook"
        ext = "azw3"
        formatted, matched = self.formatter.parse_and_format(raw_name, ext)
        self.assertFalse(matched)
        self.assertEqual(formatted, "SingleWordUnformattedEbook.azw3")

    def test_extension_detection_mime(self):
        ext = self.formatter.get_extension(None, "application/epub+zip", None)
        self.assertEqual(ext, "epub")

    def test_extension_detection_caption(self):
        ext = self.formatter.get_extension(None, None, "Check out this book: sample_book.djvu")
        self.assertEqual(ext, "djvu")

if __name__ == "__main__":
    unittest.main()
