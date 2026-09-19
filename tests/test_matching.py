"""
اختبارات صحة محرك المطابقة وتكرار اللوحات وشمولية كافة الأعمدة
"""

import unittest
import sys
import os
import tempfile
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import init_system_db, replace_user_dataset, get_dataset_stats, clear_user_dataset
from backend.matching_engine import match_referral_file, quick_search_single_plate, get_match_results_page


class TestMatchingEngine(unittest.TestCase):

    def setUp(self):
        init_system_db()
        self.user_id = 999
        clear_user_dataset(self.user_id)

    def tearDown(self):
        clear_user_dataset(self.user_id)

    def test_exact_match_and_duplicates_handling(self):
        """
        اختبار محوري:
        1. التحقق من أن المطابقة باللوحة فقط (By Plate Only).
        2. اللوحة ليست Unique وتتكرر (حكا9053 متكررة 3 مرات).
        3. شمول كافة الأعمدة من كلا الملفين (الشاص، العميل، البنك، اللون، الموديل).
        4. التأكد من ظهور جميع السجلات الثلاثة مع شواصيها المختلفة.
        """
        vehicles_data = [
            {"اللوحة": " حكا 9053 ", "الشاص": "CHASSIS_A1", "العميل": "محمد أحمد", "البنك": "الراجحي", "الموديل": "كامري", "اللون": "أبيض"},
            {"اللوحة": "ح ك ا - ٩٠٥٣", "الشاص": "CHASSIS_A2", "العميل": "خالد عبد الله", "البنك": "الأهلي", "الموديل": "لاندكروزر", "اللون": "أسود"},
            {"اللوحة": "حكا9053", "الشاص": "CHASSIS_A3", "العميل": "سارة سعيد", "البنك": "الرياض", "الموديل": "يارس", "اللون": "فضي"},
            {"اللوحة": "ب دو 1111", "الشاص": "CHASSIS_B1", "العميل": "علي حسن", "البنك": "الإنماء", "الموديل": "سوناتا", "اللون": "رمادي"},
            {"اللوحة": "س ص ع 2222", "الشاص": "CHASSIS_C1", "العميل": "فهد ناصر", "البنك": "البلاد", "الموديل": "أكسنت", "اللون": "أزرق"},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            pd.DataFrame(vehicles_data).to_csv(f.name, index=False)
            vehicles_file = f.name

        try:
            ingest_res = replace_user_dataset(self.user_id, vehicles_file)
            self.assertTrue(ingest_res["success"])
            self.assertEqual(ingest_res["total_records"], 5)

            stats = get_dataset_stats(self.user_id)
            self.assertEqual(stats["total_records"], 5)
            self.assertEqual(stats["distinct_plates"], 3)
            self.assertEqual(stats["duplicate_plates_count"], 1)

            referral_data = [
                {"اللوحة": "حكا 9053", "نوع اللوحة": "خصوصي", "الشاص": "DIFFERENT_CHASSIS_X", "العميل": "عميل الإحالة 1", "البنك": "الفرنسي", "اللون المطلوب": "أبيض"},
                {"اللوحة": "ب د و ١١١١", "نوع اللوحة": "نقل خاص", "الشاص": "CHASSIS_B1", "العميل": "علي حسن", "البنك": "الإنماء", "اللون المطلوب": "رمادي"},
                {"اللوحة": "غير موجود 9999", "نوع اللوحة": "دبلوماسي", "الشاص": "CHASSIS_NONE", "العميل": "غير موجود", "البنك": "لا يوجد", "اللون المطلوب": "أحمر"}
            ]

            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as rf:
                pd.DataFrame(referral_data).to_csv(rf.name, index=False)
                referral_file = rf.name

            try:
                match_res = match_referral_file(self.user_id, referral_file)
                self.assertTrue(match_res["success"])
                self.assertEqual(match_res["total_referrals"], 3)
                self.assertEqual(match_res["matched_referrals"], 2)
                self.assertEqual(match_res["unmatched_referrals"], 1)
                self.assertEqual(match_res["multiple_matches_count"], 1)
                self.assertEqual(match_res["total_vehicle_matches"], 4)

                page_data = get_match_results_page(self.user_id, page=1, page_size=10, filter_status='all')
                records = page_data["records"]
                cols = page_data["columns"]

                # التحقق من وجود كافة أعمدة الإحالة بالكامل بمسميات نظيفة
                self.assertIn("نوع اللوحة", cols)
                self.assertIn("اللون", cols)

                # التحقق من وجود كافة أعمدة السيارة بالكامل بمسميات نظيفة
                self.assertIn("النوع", cols)
                self.assertIn("الشاص", cols)

                # التحقق من تطابق حكا9053
                hka_matches = [r for r in records if "حكا 9053" in str(r.get("لوحة الإحالة", ""))]
                self.assertEqual(len(hka_matches), 3)

                found_chassis = {r["الشاص"] for r in hka_matches}
                self.assertEqual(found_chassis, {"CHASSIS_A1", "CHASSIS_A2", "CHASSIS_A3"})

                found_models = {r["النوع"] for r in hka_matches}
                self.assertEqual(found_models, {"كامري", "لاندكروزر", "يارس"})

                # فحص استبعاد غير المتطابق من الجدول (حصر الجدول على المتطابق فقط)
                unmatched = [r for r in records if "غير موجود 9999" in str(r.get("لوحة الإحالة", ""))]
                self.assertEqual(len(unmatched), 0)

                # فحص البحث السريع المنفرد بمسميات نظيفة
                quick_res = quick_search_single_plate(self.user_id, " ح ك ا 9053 ")
                self.assertEqual(len(quick_res), 3)
                self.assertIn("الموديل", quick_res[0])

            finally:
                if os.path.exists(referral_file):
                    os.remove(referral_file)

        finally:
            if os.path.exists(vehicles_file):
                os.remove(vehicles_file)


if __name__ == '__main__':
    unittest.main()
