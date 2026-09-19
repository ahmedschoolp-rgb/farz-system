"""
اختبار ديناميكية شمول كافة الأعمدة من كلا الملفين
(Full Dynamic Columns Verification Test)
"""

import sys
import unittest
import duckdb
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class TestDynamicColumns(unittest.TestCase):

    def test_full_columns_retained(self):
        con = duckdb.connect(':memory:')

        # 1. سيارات تحتوي على 8 أعمدة متنوعة
        veh_df = pd.DataFrame({
            'رقم اللوحة': ['حكا 9053', 'حكا 9053', 'بدو 1111'],
            'الشاص': ['VIN_A1', 'VIN_A2', 'VIN_B1'],
            'الموديل': ['تويوتا لاندكروزر', 'تويوتا كامري', 'هيونداي سوناتا'],
            'سنة الصنع': ['2023', '2022', '2024'],
            'اللون': ['أبيض لؤلؤي', 'فضي', 'أسود ملكي'],
            'البنك': ['الراجحي', 'الأهلي', 'البلاد'],
            'اسم المالك': ['شركة الأعمال', 'مؤسسة النور', 'عبد العزيز'],
            'رقم العقد': ['CNT-01', 'CNT-02', 'CNT-03']
        })
        veh_df.columns = [f'[السيارة] {c}' for c in veh_df.columns]
        veh_df['__veh_id__'] = [1, 2, 3]
        veh_df['__veh_plate_norm__'] = ['حكا9053', 'حكا9053', 'بدو1111']
        veh_df['__veh_plate_raw__'] = ['حكا 9053', 'حكا 9053', 'بدو 1111']

        # 2. ملف إحالة يحتوي على 7 أعمدة متنوعة
        ref_df = pd.DataFrame({
            'اللوحة': ['حكا 9053', 'بدو 1111', 'غير موجود 9999'],
            'نوع اللوحة': ['خصوصي', 'نقل خاص', 'دبلوماسي'],
            'اسم العميل': ['محمد أحمد', 'علي حسن', 'سالم سعيد'],
            'اللون المطلوب': ['أبيض', 'أسود', 'أحمر'],
            'رقم المعاملة': ['REF-101', 'REF-102', 'REF-103'],
            'تاريخ الإحالة': ['2026-09-01', '2026-09-02', '2026-09-03']
        })
        ref_df.columns = [f'[الإحالة] {c}' for c in ref_df.columns]
        ref_df['__ref_row_id__'] = [1, 2, 3]
        ref_df['__ref_plate_norm__'] = ['حكا9053', 'بدو1111', 'غيرموجود9999']

        con.register('veh', veh_df)
        con.register('ref', ref_df)

        query = """
            CREATE TABLE last_match AS 
            SELECT 
                r.__ref_row_id__ AS "__row_id__",
                CASE 
                    WHEN v.__veh_plate_norm__ IS NULL THEN 'غير متطابق'
                    WHEN COUNT(v.__veh_plate_norm__) OVER (PARTITION BY r.__ref_row_id__) > 1 THEN 'تطابق متعدد'
                    ELSE 'متطابق'
                END AS "حالة المطابقة",
                r.* EXCLUDE (__ref_row_id__, __ref_plate_norm__),
                v.* EXCLUDE (__veh_id__, __veh_plate_norm__, __veh_plate_raw__),
                CASE WHEN v.__veh_plate_norm__ IS NOT NULL THEN 1 ELSE 0 END AS "__is_matched__"
            FROM ref r
            LEFT JOIN veh v ON r.__ref_plate_norm__ = v.__veh_plate_norm__;
        """
        con.execute(query)

        cols = [c[0] for c in con.execute('DESCRIBE last_match').fetchall() if not c[0].startswith('__')]
        
        # التأكد من وجود كافة أعمدة الإحالة بالكامل
        self.assertIn('[الإحالة] اللوحة', cols)
        self.assertIn('[الإحالة] نوع اللوحة', cols)
        self.assertIn('[الإحالة] اسم العميل', cols)
        self.assertIn('[الإحالة] اللون المطلوب', cols)
        self.assertIn('[الإحالة] رقم المعاملة', cols)
        self.assertIn('[الإحالة] تاريخ الإحالة', cols)

        # التأكد من وجود كافة أعمدة السيارة بالكامل
        self.assertIn('[السيارة] رقم اللوحة', cols)
        self.assertIn('[السيارة] الشاص', cols)
        self.assertIn('[السيارة] الموديل', cols)
        self.assertIn('[السيارة] سنة الصنع', cols)
        self.assertIn('[السيارة] اللون', cols)
        self.assertIn('[السيارة] البنك', cols)
        self.assertIn('[السيارة] اسم المالك', cols)
        self.assertIn('[السيارة] رقم العقد', cols)

        # التأكد من وجود حالة المطابقة
        self.assertEqual(cols[0], 'حالة المطابقة')

        # فحص الصفوف والتطابق المتعدد
        df = con.execute('SELECT * FROM last_match').df()
        self.assertEqual(len(df), 4)  # 2 للوحة حكا9053 + 1 لبدو1111 + 1 لغير موجود

        # فحص تطابق حكا9053 المتعدد
        hka = df[df['[الإحالة] اللوحة'] == 'حكا 9053']
        self.assertEqual(len(hka), 2)
        self.assertEqual(list(hka['حالة المطابقة']), ['تطابق متعدد', 'تطابق متعدد'])
        # التأكد من أن الموديل واللون والشاص ظهرت لكل سيارة
        models = set(hka['[السيارة] الموديل'])
        self.assertEqual(models, {'تويوتا لاندكروزر', 'تويوتا كامري'})

        con.close()

    def test_order_matching_columns_strictly_follows_spec(self):
        from backend.matching_engine import order_matching_columns

        veh_cols = [
            '[السيارة] اللوحة',
            '[السيارة] النوع / الموديل',
            '[السيارة] الملاحظات',
            '[السيارة] الشارع',
            '[السيارة] الحي',
            '[السيارة] التاريخ',
            '[السيارة] رابط الموقع',
            '[السيارة] الشاص',
            '[السيارة] البنك',
            '[السيارة] رقم العقد'
        ]

        ref_cols = [
            '[الإحالة] اللوحة',
            '[الإحالة] صانع المركبة',
            '[الإحالة] طراز المركبة',
            '[الإحالة] سنة الصنع',
            '[الإحالة] اسم العميل',
            '[الإحالة] اللون',
            '[الإحالة] نوع اللوحة',
            '[الإحالة] رقم المعاملة',
            '[الإحالة] جهة الإحالة'
        ]

        ordered = order_matching_columns(veh_cols, ref_cols)

        # 1. حالة المطابقة
        self.assertEqual(ordered[0], 'حالة المطابقة')
        # 2. اللوحة من الداتا
        self.assertEqual(ordered[1], '[السيارة] اللوحة')
        # 3. اللوحة من الإحالة
        self.assertEqual(ordered[2], '[الإحالة] اللوحة')
        # 4. داتا: النوع، الملاحظات، الشارع، الحي، التاريخ
        self.assertEqual(ordered[3], '[السيارة] النوع / الموديل')
        self.assertEqual(ordered[4], '[السيارة] الملاحظات')
        self.assertEqual(ordered[5], '[السيارة] الشارع')
        self.assertEqual(ordered[6], '[السيارة] الحي')
        self.assertEqual(ordered[7], '[السيارة] التاريخ')
        # 5. إحالة: صانع وطراز، سنة الصنع، اسم العميل، اللون، نوع اللوحة
        self.assertEqual(ordered[8], '[الإحالة] صانع المركبة')
        self.assertEqual(ordered[9], '[الإحالة] طراز المركبة')
        self.assertEqual(ordered[10], '[الإحالة] سنة الصنع')
        self.assertEqual(ordered[11], '[الإحالة] اسم العميل')
        self.assertEqual(ordered[12], '[الإحالة] اللون')
        self.assertEqual(ordered[13], '[الإحالة] نوع اللوحة')
        # 6. الموقع / الرابط من الداتا
        self.assertEqual(ordered[14], '[السيارة] رابط الموقع')
        # 7. باقي أعمدة الداتا
        self.assertIn('[السيارة] الشاص', ordered[15:])
        self.assertIn('[السيارة] البنك', ordered[15:])
        self.assertIn('[السيارة] رقم العقد', ordered[15:])
        # 8. باقي أعمدة الإحالة
        self.assertIn('[الإحالة] رقم المعاملة', ordered[15:])
        self.assertIn('[الإحالة] جهة الإحالة', ordered[15:])

        # لا يوجد أي عمود مفقود
        self.assertEqual(len(ordered), len(veh_cols) + len(ref_cols) + 1)


if __name__ == '__main__':
    unittest.main()
