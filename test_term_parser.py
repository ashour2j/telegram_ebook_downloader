import unittest
from term_parser import detect_term

class TestTermParser(unittest.TestCase):
    def test_first_term_arabic_forms(self):
        self.assertEqual(detect_term("التأسيس_عربي_6ب_الترم_الاول_2027")[0], 1)
        self.assertEqual(detect_term("اضواء عربى 6ب ترم اول 2027")[0], 1)
        self.assertEqual(detect_term("ملحق جيم 6ب ترم أول 2027")[0], 1)
        self.assertEqual(detect_term("كتاب الفصل الدراسي الاول")[0], 1)

    def test_second_term_arabic_forms(self):
        self.assertEqual(detect_term("التأسيس_عربي_6ب_الترم_الثاني_2027")[0], 2)
        self.assertEqual(detect_term("اضواء عربى 6ب ترم تاني 2027")[0], 2)
        self.assertEqual(detect_term("كتاب العلوم ترم ثاني")[0], 2)

    def test_english_forms(self):
        self.assertEqual(detect_term("math book 1st term 2027")[0], 1)
        self.assertEqual(detect_term("history second term.pdf")[0], 2)

    def test_numeric_term(self):
        self.assertEqual(detect_term("كتاب_الرياضيات_الترم_1_2027")[0], 1)
        self.assertEqual(detect_term("كتاب_الرياضيات_الترم_2_2027")[0], 2)

    def test_no_term(self):
        self.assertIsNone(detect_term("الاضواء دراسات 6ب.pdf")[0])
        self.assertIsNone(detect_term("كتاب_اللغة_العربية_1ب.pdf")[0])

    def test_chapter_not_misdetected(self):
        self.assertIsNone(detect_term("الفصل الاول من الكتاب")[0])
        self.assertIsNone(detect_term("الفصل الثاني من الكتاب")[0])

    def test_grade_first_not_misdetected_as_term(self):
        self.assertIsNone(detect_term("الصف الأول الاعدادي")[0])

if __name__ == "__main__":
    unittest.main()
