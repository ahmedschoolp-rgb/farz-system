"""
اختبارات تكامل الـ API من البداية للنهاية (End-to-End API Integration Tests)
"""

import unittest
import sys
import os
from starlette.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.main import app
from backend.database import init_system_db, clear_user_dataset


class TestAPIEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_system_db()
        cls.client = TestClient(app)
        cls.test_user_id = 1

    def setUp(self):
        clear_user_dataset(self.test_user_id)

    def test_full_api_workflow(self):
        # 1. فحص الصحة
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "healthy")

        # 2. جلب قائمة المستخدمين الـ 50
        res = self.client.get("/api/auth/users")
        self.assertEqual(res.status_code, 200)
        users = res.json()["users"]
        self.assertGreaterEqual(len(users), 51)  # المدير + 50 مستخدم

        # 3. تسجيل الدخول السريع
        res = self.client.post("/api/auth/quick-switch", json={"user_id": self.test_user_id})
        self.assertEqual(res.status_code, 200)
        token = res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 4. فحص الإحصائيات قبل الرفع
        res = self.client.get("/api/dataset/stats", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["stats"]["total_records"], 0)

        # 5. رفع ملف بيانات سيارات تجريبي
        sample_veh_path = os.path.join("data", "samples", "sample_vehicles_daily.csv")
        with open(sample_veh_path, "rb") as f:
            res = self.client.post(
                "/api/dataset/upload",
                headers=headers,
                files={"file": ("sample_vehicles.csv", f, "text/csv")}
            )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["data"]["total_records"], 6)

        # 6. فحص الإحصائيات بعد الرفع
        res = self.client.get("/api/dataset/stats", headers=headers)
        self.assertEqual(res.status_code, 200)
        stats = res.json()["stats"]
        self.assertEqual(stats["total_records"], 6)
        self.assertTrue(stats["exists"])

        # 7. البحث السريع عن لوحة مفردة
        res = self.client.post(
            "/api/dataset/quick-search",
            headers=headers,
            json={"plate": "حكا 9053"}
        )
        self.assertEqual(res.status_code, 200)
        search_data = res.json()
        self.assertEqual(search_data["total_matches"], 3)  # يجب أن يجد كل السجلات الـ 3 المكررة
        self.assertIn("النوع / الموديل", search_data["results"][0])
        self.assertIn("الشارع", search_data["results"][0])

        # 8. رفع ومطابقة ملف الإحالة
        sample_ref_path = os.path.join("data", "samples", "sample_referral.csv")
        with open(sample_ref_path, "rb") as f:
            res = self.client.post(
                "/api/referral/match",
                headers=headers,
                files={"file": ("sample_referral.csv", f, "text/csv")}
            )
        self.assertEqual(res.status_code, 200)
        match_summary = res.json()["summary"]
        self.assertEqual(match_summary["total_referrals"], 4)
        self.assertEqual(match_summary["matched_referrals"], 3)
        self.assertEqual(match_summary["unmatched_referrals"], 1)
        # إجمالي سيارات التطابق = 3 لـ حكا9053 + 1 لـ بدو1111 + 1 لـ سصع2222 = 5
        self.assertEqual(match_summary["total_vehicle_matches"], 5)
        self.assertEqual(match_summary["multiple_matches_count"], 1)

        # 9. تصفح نتائج المطابقة عبر الـ Pagination والفلترة والتحقق من الترتيب الدقيق للأعمدة
        res = self.client.get("/api/referral/results?page=1&page_size=10&filter_status=all", headers=headers)
        self.assertEqual(res.status_code, 200)
        cols = res.json()["data"]["columns"]
        records = res.json()["data"]["records"]
        self.assertEqual(len(records), 5)  # المتطابق فقط (3 لـ حكا + 1 لبدو + 1 لسصع)

        # التأكد من الترتيب المنطقي الدقيق ونظافة الأعمدة من البادئات
        self.assertEqual(cols[0], "حالة المطابقة")
        self.assertEqual(cols[1], "اللوحة")
        self.assertEqual(cols[2], "لوحة الإحالة")
        self.assertIn("النوع", cols)
        self.assertIn("الملاحظات", cols)
        self.assertIn("الشارع", cols)
        self.assertIn("الحي", cols)
        self.assertIn("التاريخ", cols)
        self.assertIn("سنة الصنع", cols)
        self.assertIn("اسم العميل", cols)
        self.assertIn("اللون", cols)
        self.assertIn("نوع اللوحة", cols)
        self.assertIn("الموقع", cols)

        # 10. اختبار تصدير Excel
        res = self.client.get("/api/referral/export?format=xlsx&filter_status=all", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.content) > 1000)

        # 11. اختبار تصدير CSV
        res = self.client.get("/api/referral/export?format=csv&filter_status=all", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.content.startswith(b'\xef\xbb\xbf'))  # التحقق من وجود UTF-8 BOM للإكسل


if __name__ == '__main__':
    unittest.main()
