"""
اختبارات الأمان وعزل بيانات المستخدمين الـ 50 (Security & Multi-Tenant Data Isolation Tests)
"""

import unittest
import sys
import os
import tempfile
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import init_system_db, replace_user_dataset, get_dataset_stats, clear_user_dataset
from backend.matching_engine import match_referral_file, quick_search_single_plate


class TestSecurityIsolation(unittest.TestCase):

    def setUp(self):
        init_system_db()
        self.user1_id = 101
        self.user2_id = 102
        clear_user_dataset(self.user1_id)
        clear_user_dataset(self.user2_id)

    def tearDown(self):
        clear_user_dataset(self.user1_id)
        clear_user_dataset(self.user2_id)

    def test_strict_user_data_isolation(self):
        """
        التحقق الصارم من العزل:
        - رفع بيانات سيارات للمستخدم 1 (تحتوي على لوحة: س ص ع 1111)
        - رفع بيانات سيارات للمستخدم 2 (تحتوي على لوحة: ط ك ل 2222)
        - التأكد من أن المستخدم 1 لا يرى بيانات المستخدم 2 إطلاقًا
        - التأكد من أن مطابقة المستخدم 1 لا تصل لسيارات المستخدم 2
        """
        u1_data = [{"اللوحة": "س ص ع 1111", "الشاص": "VIN_USER1", "العميل": "عميل 1"}]
        u2_data = [{"اللوحة": "ط ك ل 2222", "الشاص": "VIN_USER2", "العميل": "عميل 2"}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f1:
            pd.DataFrame(u1_data).to_csv(f1.name, index=False)
            f1_path = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f2:
            pd.DataFrame(u2_data).to_csv(f2.name, index=False)
            f2_path = f2.name

        try:
            replace_user_dataset(self.user1_id, f1_path)
            replace_user_dataset(self.user2_id, f2_path)

            # فحص إحصائيات كل مستخدم
            s1 = get_dataset_stats(self.user1_id)
            s2 = get_dataset_stats(self.user2_id)
            self.assertEqual(s1["total_records"], 1)
            self.assertEqual(s2["total_records"], 1)

            # البحث السريع للمستخدم 1 عن لوحة المستخدم 2 يجب أن يعيد قائمة فارغة
            u1_search_u2_plate = quick_search_single_plate(self.user1_id, "ط ك ل 2222")
            self.assertEqual(len(u1_search_u2_plate), 0)

            # البحث السريع للمستخدم 1 عن لوحته الخاصة يجب أن يجدها
            u1_search_own = quick_search_single_plate(self.user1_id, "س ص ع 1111")
            self.assertEqual(len(u1_search_own), 1)
            self.assertEqual(u1_search_own[0]["الشاص"], "VIN_USER1")

            # مطابقة ملف إحالة للمستخدم 1 يبحث عن لوحة المستخدم 2
            ref_data = [{"اللوحة": "ط ك ل 2222", "الشاص": "TEST"}]
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as rf:
                pd.DataFrame(ref_data).to_csv(rf.name, index=False)
                rf_path = rf.name

            try:
                # عند مطابقة المستخدم 1 لملف يحتوي على لوحة المستخدم 2 -> يجب أن تكون غير متطابقة
                m1 = match_referral_file(self.user1_id, rf_path)
                self.assertEqual(m1["matched_referrals"], 0)
                self.assertEqual(m1["unmatched_referrals"], 1)

                # بينما المستخدم 2 إذا طابق نفس الملف يجب أن يتطابق
                m2 = match_referral_file(self.user2_id, rf_path)
                self.assertEqual(m2["matched_referrals"], 1)
                self.assertEqual(m2["unmatched_referrals"], 0)
            finally:
                if os.path.exists(rf_path):
                    os.remove(rf_path)

        finally:
            if os.path.exists(f1_path):
                os.remove(f1_path)
            if os.path.exists(f2_path):
                os.remove(f2_path)


if __name__ == '__main__':
    unittest.main()
