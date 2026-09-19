"""
اختبارات وحدة تطبيع اللوحات (Unit Tests for Plate Normalization)
"""

import unittest
import sys
import os

# إضافة مسار المشروع للاستيراد
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.normalization import normalize_plate, validate_plate_input


class TestPlateNormalization(unittest.TestCase):

    def test_spaces_removal(self):
        """اختبار إزالة المسافات العادية والزائدة والبادئة واللاحقة"""
        self.assertEqual(normalize_plate(" حكا 9053 "), "حكا9053")
        self.assertEqual(normalize_plate("  ح  ك  ا   9 0 5 3  "), "حكا9053")
        self.assertEqual(normalize_plate("\tحكا 9053\n"), "حكا9053")

    def test_unicode_and_zero_width_spaces(self):
        """اختبار إزالة المسافات الصفرية والمسافات غير القابلة للكسر"""
        # NBSP \u00A0
        self.assertEqual(normalize_plate("حكا\u00A09053"), "حكا9053")
        # Zero-width spaces \u200B, \u200C, \u200D, \uFEFF
        self.assertEqual(normalize_plate("ح\u200Bك\u200Cا\u200D9053\uFEFF"), "حكا9053")

    def test_eastern_arabic_digits(self):
        """اختبار تحويل الأرقام المشرقية / الهندية إلى أرقام قياسية"""
        self.assertEqual(normalize_plate("حكا ٩٠٥٣"), "حكا9053")
        self.assertEqual(normalize_plate("ب د و ١٢٣٤"), "بدو1234")
        self.assertEqual(normalize_plate("۰۱۲۳۴۵۶۷۸۹"), "0123456789")

    def test_symbols_and_punctuation(self):
        """اختبار إزالة الرموز والشرطات والفواصل"""
        self.assertEqual(normalize_plate("ح-ك-ا-9053"), "حكا9053")
        self.assertEqual(normalize_plate("ح_ك_ا_9053"), "حكا9053")
        self.assertEqual(normalize_plate("حكا / 9053"), "حكا9053")
        self.assertEqual(normalize_plate("حكا.9053"), "حكا9053")
        self.assertEqual(normalize_plate("حكا*9053~"), "حكا9053")

    def test_tashkeel_and_tatweel(self):
        """اختبار إزالة التشكيل وحركات الإعراب والتطويل (الكشيدة)"""
        self.assertEqual(normalize_plate("حَكَا 9053"), "حكا9053")
        self.assertEqual(normalize_plate("حـــــكـــــا 9053"), "حكا9053")

    def test_english_letters_case(self):
        """اختبار توحيد حالة الأحرف اللاتينية"""
        self.assertEqual(normalize_plate("ABC 1234"), "abc1234")
        self.assertEqual(normalize_plate("aBc - 1234"), "abc1234")

    def test_no_speculative_letter_alteration(self):
        """اختبار عدم التخمين في الحروف (عدم تبديل الحروف المتشابهة)"""
        # التأكد من الحفاظ على الحرف كما هو
        self.assertEqual(normalize_plate("أ ب ج 1111"), "أبج1111")
        self.assertEqual(normalize_plate("ا ب ج 1111"), "ابج1111")
        self.assertEqual(normalize_plate("ع د ل 4444"), "عدل4444")
        self.assertEqual(normalize_plate("غ ذ ل 4444"), "غذل4444")

    def test_edge_cases(self):
        """اختبار الحالات الخاصة والقيم الفارغة"""
        self.assertEqual(normalize_plate(None), "")
        self.assertEqual(normalize_plate(""), "")
        self.assertEqual(normalize_plate("    "), "")
        self.assertEqual(normalize_plate("---"), "")
        self.assertFalse(validate_plate_input(""))
        self.assertFalse(validate_plate_input("   "))
        self.assertTrue(validate_plate_input("حكا9053"))


if __name__ == '__main__':
    unittest.main()
