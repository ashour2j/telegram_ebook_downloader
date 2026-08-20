import unittest
from grade_parser import detect_grade

class TestGradeParser(unittest.TestCase):
    def test_primary_grades(self):
        self.assertEqual(detect_grade("كتاب_اللغة_العربية_1ب.pdf")[0], 1)
        self.assertEqual(detect_grade("قطر_عربي_2ب_الترم_الأول_2027")[0], 2)
        self.assertEqual(detect_grade("الصف الثالث الابتدائي")[0], 3)
        self.assertEqual(detect_grade("رابعة ابتدائي رياضيات")[0], 4)
        self.assertEqual(detect_grade("خامسة ابتدائي")[0], 5)
        self.assertEqual(detect_grade("الصف السادس الابتدائي")[0], 6)

    def test_prep_grades(self):
        self.assertEqual(detect_grade("اولى اعدادي علوم")[0], 7)
        self.assertEqual(detect_grade("الصف الثاني الاعدادي")[0], 8)
        self.assertEqual(detect_grade("تالتة اعدادي امتحانات")[0], 9)

    def test_sec_grades(self):
        self.assertEqual(detect_grade("اولى ثانوي الكيمياء")[0], 10)
        self.assertEqual(detect_grade("الكتب الخارجية تانية ثانوي 2027")[0], 11)
        self.assertEqual(detect_grade("دفعة تالتة ثانوي 2027")[0], 12)

    def test_english_patterns(self):
        self.assertEqual(detect_grade("1st primary math.pdf")[0], 1)
        self.assertEqual(detect_grade("Grade 8 physics.pdf")[0], 8)
        self.assertEqual(detect_grade("3rd sec english.epub")[0], 12)

if __name__ == "__main__":
    unittest.main()
