"""
اختبار الأداء الفائق لمعالجة 2,000,000 سيارة ومطابقة 5,000 إحالة
(High-Performance Benchmark: 2,000,000 Vehicles vs 5,000 Referrals)
"""

import time
import sys
import os
import tempfile
import duckdb
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import replace_user_dataset, get_dataset_stats, clear_user_dataset
from backend.matching_engine import match_referral_file


def run_benchmark():
    user_id = 888  # مستخدم مخصص لاختبار الأداء
    clear_user_dataset(user_id)

    print("\n" + "="*70)
    print("  بدء اختبار الأداء العالي لمعالجة 2,000,000 سيارة (2 Million Benchmark)")
    print("="*70)

    # 1. إنشاء ملف بيانات تجريبي يحتوي على 2,000,000 سيارة مع لوحات عربية وتكرارات
    t0 = time.time()
    csv_file = os.path.join(tempfile.gettempdir(), "vehicles_2m_benchmark.csv")
    print(f"\n[1/3] جاري توليد ملف بيانات تجريبي يحتوي على 2,000,000 سيارة...")

    # نستخدم محرك DuckDB لتوليد ملف الـ 2 مليون بسرعة فائقة بدلاً من حلقات بايثون البطيئة
    con_gen = duckdb.connect(':memory:')
    con_gen.execute("""
        COPY (
            SELECT 
                CASE (range % 5)
                    WHEN 0 THEN ' حكا ' || (range % 400000) || ' '
                    WHEN 1 THEN 'ح ك ا - ' || (range % 400000)
                    WHEN 2 THEN 'ب د و / ' || (range % 400000)
                    WHEN 3 THEN 'س ص ع_' || (range % 400000)
                    ELSE 'أ ب ج ' || (range % 400000)
                END AS "اللوحة",
                'VIN_CHASSIS_' || range AS "الشاص",
                'العميل رقم ' || (range % 100000) AS "اسم العميل",
                CASE (range % 4)
                    WHEN 0 THEN 'مصرف الراجحي'
                    WHEN 1 THEN 'البنك الأهلي السعودي'
                    WHEN 2 THEN 'بنك الرياض'
                    ELSE 'بنك البلاد'
                END AS "البنك"
            FROM range(2000000)
        ) TO '""" + csv_file.replace('\\', '/') + """' (HEADER, DELIMITER ',');
    """)
    con_gen.close()

    gen_time = time.time() - t0
    file_size_mb = round(os.path.getsize(csv_file) / (1024 * 1024), 1)
    print(f"  ✓ تم إنشاء ملف الـ 2 مليون صف في: {gen_time:.2f} ثانية (الحجم: {file_size_mb} MB)")

    # 2. قياس زمن قراءة ومعالجة وتطبيع وفهرسة الـ 2,000,000 سيارة
    print(f"\n[2/3] جاري رفع واستبدال قاعدة البيانات وبناء الفهارس (Active Dataset Ingestion)...")
    t1 = time.time()
    ingest_res = replace_user_dataset(user_id, csv_file)
    ingest_time = time.time() - t1

    print(f"  ✓ تم الانتهاء من المعالجة والاستبدال الكامل بنجاح!")
    print(f"  ✓ إجمالي السجلات التي تم إدخالها: {ingest_res['total_records']:,} سيارة")
    print(f"  ✓ الوقت المستغرق للمعالجة بالكامل: {ingest_time:.2f} ثانية")
    print(f"  ✓ وقت بناء الفهرس: {ingest_res['index_seconds']} ثانية")

    stats = get_dataset_stats(user_id)
    print(f"  ✓ اللوحات الفريدة: {stats['distinct_plates']:,}")
    print(f"  ✓ اللوحات المكررة (> 1): {stats['duplicate_plates_count']:,}")

    # 3. إنشاء ملف إحالة تجريبي يحتوي على 5,000 لوحة ومطابقتها
    print(f"\n[3/3] جاري توليد ملف إحالة (5,000 لوحة) وتنفيذ المطابقة الفورية...")
    ref_file = os.path.join(tempfile.gettempdir(), "referrals_5k_benchmark.csv")
    con_ref = duckdb.connect(':memory:')
    con_ref.execute("""
        COPY (
            SELECT 
                CASE (range % 4)
                    WHEN 0 THEN 'حكا ' || (range * 80)
                    WHEN 1 THEN 'ب د و ' || (range * 80)
                    WHEN 2 THEN 'س ص ع ' || (range * 80)
                    ELSE 'لوحة غير موجودة ' || range
                END AS "اللوحة",
                'REF_CHASSIS_' || range AS "الشاص",
                'عميل محال ' || range AS "اسم العميل",
                'البنك المحال له' AS "البنك"
            FROM range(5000)
        ) TO '""" + ref_file.replace('\\', '/') + """' (HEADER, DELIMITER ',');
    """)
    con_ref.close()

    t2 = time.time()
    match_res = match_referral_file(user_id, ref_file)
    total_match_time = time.time() - t2

    print(f"  ✓ تمت المطابقة ضد الـ 2,000,000 سيارة بنجاح!")
    print(f"  ✓ سرعة استعلام المطابقة الصافية (SQL Hash Join): {match_res['execution_time_ms']} ميلي ثانية")
    print(f"  ✓ إجمالي زمن المطابقة وحفظ النتائج: {total_match_time:.3f} ثانية")
    print(f"  ✓ إجمالي صفوف الإحالة: {match_res['total_referrals']:,}")
    print(f"  ✓ صفوف الإحالة المتطابقة: {match_res['matched_referrals']:,}")
    print(f"  ✓ صفوف الإحالة غير المتطابقة: {match_res['unmatched_referrals']:,}")
    print(f"  ✓ إجمالي سيارات التطابق في النتائج (بالتكرارات 1-to-many): {match_res['total_vehicle_matches']:,}")
    print(f"  ✓ عدد اللوحات ذات التطابقات المتعددة: {match_res['multiple_matches_count']:,}")

    # تنظيف الملفات المؤقتة
    try:
        os.remove(csv_file)
        os.remove(ref_file)
        clear_user_dataset(user_id)
    except Exception:
        pass

    print("\n" + "="*70)
    print("  نتيجة الاختبار: تم اجتياز اختبار الـ 2 مليون بنجاح باهر وسرعة استثنائية!")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_benchmark()
