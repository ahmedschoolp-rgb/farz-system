"""
محرك المطابقة الفوري الشامل والمنظم (High-Performance Vectorized Matching Engine)
- ترتيب الأعمدة الدقيق وفق توجيهات المستخدم:
  1. حالة المطابقة
  2. اللوحة من ملف الداتا
  3. اللوحة من ملف الإحالة
  4. بيانات الداتا: النوع/الموديل، الملاحظات، الشارع، الحي، التاريخ
  5. بيانات الإحالة: صانع وطراز المركبة (النوع)، سنة الصنع، اسم العميل، اللون، نوع اللوحة
  6. الموقع أو الرابط من ملف الداتا
  7. باقي الأعمدة المتبقية من كلا الملفين
- المطابقة الصارمة: By Plate Only (بعد التطبيع الدقيق)
- دعم تكرار اللوحات (1-to-Many): إرجاع كافة السجلات المرتبطة باللوحة
- تصدير النتائج بالكامل إلى Excel منسق واحترافي أو CSV بترميز UTF-8 سليم
"""

import time
import json
import os
import re
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import duckdb
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from backend.config import EXPORTS_DIR
from backend.normalization import normalize_plate, DIGIT_TRANSLATION, CLEANUP_PATTERN
from backend.database import get_user_duckdb_path, detect_columns


def order_matching_columns(veh_cols: List[str], ref_cols: List[str]) -> List[tuple[str, str]]:
    """
    ترتيب أعمدة جدول النتائج وفق الترتيب المنطقي الدقيق المطلوب مع تنظيف تام للمسميات:
    1. حالة المطابقة
    2. اللوحة (من ملف الداتا)
    3. لوحة الإحالة (من ملف الإحالة)
    4. بيانات الداتا: النوع، الملاحظات، الشارع، الحي، التاريخ
    5. بيانات الإحالة: سنة الصنع، اسم العميل، اللون، نوع اللوحة
    6. الموقع أو الرابط من ملف الداتا
    7. باقي أعمدة الداتا المتبقية (إن وجدت)
    8. باقي أعمدة الإحالة المتبقية (إن وجدت)
    """
    ordered_pairs = []
    used_raw = set()
    used_clean = set()

    def add_col(raw_name, clean_name=None):
        if not raw_name or raw_name in used_raw:
            return
        if not clean_name:
            # تنظيف تلقائي للبادئات
            clean_name = raw_name.replace('[الإحالة]', '').replace('[السيارة]', '').strip()
            if not clean_name:
                clean_name = raw_name

        # التأكد من عدم تكرار اسم العمود النظيف
        final_clean = clean_name
        idx = 2
        while final_clean in used_clean:
            final_clean = f"{clean_name}_{idx}"
            idx += 1

        ordered_pairs.append((raw_name, final_clean))
        used_raw.add(raw_name)
        used_clean.add(final_clean)

    def find_cols(col_list, keywords, exclude_keywords=None):
        matched = []
        for c in col_list:
            if c in used_raw:
                continue
            name = c.replace('[الإحالة]', '').replace('[السيارة]', '').strip().lower()
            if exclude_keywords and any(ex in name for ex in exclude_keywords):
                continue
            if any(kw in name for kw in keywords):
                matched.append(c)
        return matched

    # 1. حالة المطابقة
    add_col("حالة المطابقة", "حالة المطابقة")

    # 2. اللوحة من ملف الداتا
    for c in find_cols(veh_cols, ['لوحة', 'plate', 'اللوحه']):
        add_col(c, "اللوحة")
        break

    # 3. اللوحة من ملف الإحالة
    for c in find_cols(ref_cols, ['لوحة', 'plate', 'اللوحه'], exclude_keywords=['نوع']):
        add_col(c, "لوحة الإحالة")
        break

    # 4. بيانات الداتا: النوع، الملاحظات، الشارع، الحي، التاريخ
    for c in find_cols(veh_cols, ['نوع', 'موديل', 'طراز', 'صانع', 'ماركة', 'model', 'make', 'type'], exclude_keywords=['لوحة', 'عقد']):
        add_col(c, "النوع")
    for c in find_cols(veh_cols, ['ملاحظ', 'بيان', 'notes', 'remarks', 'وصف']):
        add_col(c, "الملاحظات")
    for c in find_cols(veh_cols, ['شارع', 'الشارع', 'street']):
        add_col(c, "الشارع")
    for c in find_cols(veh_cols, ['حي', 'الحي', 'district', 'neighborhood']):
        add_col(c, "الحي")
    for c in find_cols(veh_cols, ['تاريخ', 'التاريخ', 'date', 'وقت', 'time']):
        add_col(c, "التاريخ")

    # 5. بيانات الإحالة: سنة الصنع، اسم العميل، اللون، نوع اللوحة
    for c in find_cols(ref_cols, ['سنة', 'سنه', 'عام الصنع', 'سنة الصنع', 'سنه الصنع', 'سنة الموديل', 'سنه الموديل', 'عام', 'year'], exclude_keywords=['معامل']):
        add_col(c, "سنة الصنع")
    for c in find_cols(ref_cols, ['عميل', 'اسم العميل', 'العميل', 'مالك', 'اسم المالك', 'صاحب المركبة', 'client', 'customer', 'name']):
        add_col(c, "اسم العميل")
    for c in find_cols(ref_cols, ['لون', 'اللون', 'color']):
        add_col(c, "اللون")
    for c in find_cols(ref_cols, ['نوع اللوحة', 'نوع_اللوحة', 'نوع اللوحه', 'فئة اللوحة']):
        add_col(c, "نوع اللوحة")
    for c in find_cols(ref_cols, ['طراز', 'نوع المركبة', 'نوع السيارة', 'الموديل', 'موديل', 'النوع', 'نوع', 'صانع', 'make', 'الماركة'], exclude_keywords=['لوحة', 'لوحه', 'معامل']):
        add_col(c, "طراز الإحالة")

    # 6. الموقع أو الرابط من ملف الداتا
    for c in find_cols(veh_cols, ['موقع', 'الموقع', 'رابط', 'الرابط', 'لوكيشن', 'خريطة', 'location', 'map', 'url', 'link', 'gps', 'احداثي', 'إحداثي']):
        add_col(c, "الموقع")

    # 7. باقي أعمدة الداتا (إن وجدت، مثل الشاص، البنك، رقم العقد، إلخ)
    for c in veh_cols:
        if not c.startswith('__') and c not in used_raw:
            add_col(c)

    # 8. باقي أعمدة الإحالة (إن وجدت، مثل رقم المعاملة، جهة الإحالة، إلخ)
    for c in ref_cols:
        if not c.startswith('__') and c not in used_raw:
            add_col(c)

    return ordered_pairs


def match_referral_file(
    user_id: int,
    file_path: Union[str, Path, List[Union[str, Path]]],
    plate_col: Optional[str] = None,
    chassis_col: Optional[str] = None,
    client_col: Optional[str] = None,
    bank_col: Optional[str] = None
) -> Dict[str, Any]:
    """
    تنفيذ مطابقة ملف أو ملفات الإحالة ضد قاعدة بيانات المستخدم الحالية (2M سجل)
    مع الترتيب المنطقي الدقيق وحصر النتائج على المتطابق فقط وتنظيف كافة المسميات
    """
    start_time = time.time()
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        raise FileNotFoundError("لم يتم العثور على قاعدة بيانات نشطة لهذا المستخدم. يرجى رفع ملف البيانات أولاً.")

    # تجهيز قائمة الملفات
    file_list = file_path if isinstance(file_path, (list, tuple)) else [file_path]
    dfs = []

    for f_item in file_list:
        p = Path(f_item)
        if not p.exists():
            continue
        file_ext = p.suffix.lower()

        # قراءة ملف الإحالة بالكامل مع كافة الأعمدة
        if file_ext in ['.xlsx', '.xls']:
            sub_df = pd.read_excel(p, dtype=str, keep_default_na=False).reset_index(drop=True)
        elif file_ext in ['.csv', '.txt', '.tsv']:
            try:
                sub_df = pd.read_csv(p, dtype=str, keep_default_na=False, index_col=False, encoding='utf-8').reset_index(drop=True)
            except Exception:
                sub_df = pd.read_csv(p, dtype=str, keep_default_na=False, index_col=False, encoding='latin1').reset_index(drop=True)
        else:
            continue

        if len(sub_df) > 0:
            sub_df.columns = [str(c).strip() for c in sub_df.columns]
            if len(file_list) > 1:
                sub_df['ملف الإحالة'] = p.name
            dfs.append(sub_df)

    if not dfs:
        return {
            "success": True,
            "total_referrals": 0,
            "matched_referrals": 0,
            "unmatched_referrals": 0,
            "total_vehicle_matches": 0,
            "multiple_matches_count": 0,
            "match_rate_percent": 0.0,
            "execution_time_ms": 0.0,
            "columns": [],
            "records": []
        }

    # دمج كافة ملفات الإحالة في DataFrame موحد
    ref_df = pd.concat(dfs, ignore_index=True)
    total_referral_rows = len(ref_df)

    # تنظيف أسماء الأعمدة واكتشاف عمود اللوحة
    detected = detect_columns(list(ref_df.columns))
    p_col = plate_col or detected['plate']

    if not p_col or p_col not in ref_df.columns:
        raise ValueError(f"تعذر تحديد عمود اللوحة في ملفات الإحالة المرفوعة. الأعمدة المتوفرة: {list(ref_df.columns)}")

    # 2. تطبيع لوحات الإحالة وتجهيز الأعمدة مع بادئة واضحة
    norm_plates = (
        ref_df[p_col].astype(str)
        .str.normalize('NFKC')
        .str.translate(DIGIT_TRANSLATION)
        .str.replace(CLEANUP_PATTERN, '', regex=True)
        .str.lower()
        .str.strip()
    )

    clean_ref_df = ref_df.copy()
    clean_ref_df.columns = [f"[الإحالة] {c}" for c in clean_ref_df.columns]
    clean_ref_df['__ref_row_id__'] = list(range(1, total_referral_rows + 1))
    clean_ref_df['__ref_plate_norm__'] = norm_plates

    # 3. الربط الفوري عبر DuckDB وترتيب الأعمدة وتنظيف المسميات
    con = duckdb.connect(str(db_path))
    try:
        con.register("ref_table", clean_ref_df)

        con.execute("DROP TABLE IF EXISTS temp_match;")
        con.execute("""
            CREATE TABLE temp_match AS 
            SELECT 
                r.__ref_row_id__ AS "__row_id__",
                CASE 
                    WHEN v.__veh_plate_norm__ IS NULL THEN 'غير متطابق'
                    WHEN COUNT(v.__veh_plate_norm__) OVER (PARTITION BY r.__ref_row_id__) > 1 THEN 'تطابق متعدد'
                    ELSE 'متطابق'
                END AS "حالة المطابقة",
                r.* EXCLUDE (__ref_row_id__, __ref_plate_norm__),
                v.* EXCLUDE (__veh_id__, __veh_plate_norm__),
                CASE WHEN v.__veh_plate_norm__ IS NOT NULL THEN 1 ELSE 0 END AS "__is_matched__"
            FROM ref_table r
            LEFT JOIN vehicles v ON r.__ref_plate_norm__ = v.__veh_plate_norm__ AND r.__ref_plate_norm__ != ''
            ORDER BY r.__ref_row_id__;
        """)
        con.unregister("ref_table")

        # ترتيب الأعمدة وتحديد المسميات النظيفة بدون أقواس أو بادئات
        all_raw_cols = [c[0] for c in con.execute('DESCRIBE temp_match').fetchall()]
        veh_cols = [c for c in all_raw_cols if c.startswith('[السيارة]')]
        ref_cols = [c for c in all_raw_cols if c.startswith('[الإحالة]')]
        ordered_pairs = order_matching_columns(veh_cols, ref_cols)

        # إنشاء جدول last_match بالمسميات النظيفة تماماً وحصر السجلات على المتطابق فقط (المتطابق والمتعدد)
        cols_sql = ', '.join([f'"{raw}" AS "{clean}"' for raw, clean in ordered_pairs])
        con.execute("DROP TABLE IF EXISTS last_match;")
        con.execute(f'''
            CREATE TABLE last_match AS 
            SELECT "__row_id__", "__is_matched__", {cols_sql} 
            FROM temp_match 
            WHERE "__is_matched__" = 1;
        ''')

        # 4. حساب الإحصائيات الدقيقة
        matched_stats = con.execute("""
            SELECT 
                COUNT(*) AS total_vehicle_matches,
                COUNT(DISTINCT __row_id__) AS matched_referrals_count
            FROM last_match;
        """).fetchone()

        total_vehicle_matches = int(matched_stats[0])
        total_output_rows = total_vehicle_matches
        matched_referrals_count = int(matched_stats[1])
        unmatched_referrals_count = total_referral_rows - matched_referrals_count

        multiple_matches_count = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT __row_id__ FROM last_match GROUP BY __row_id__ HAVING COUNT(*) > 1
            );
        """).fetchone()[0]

        con.execute("DROP TABLE IF EXISTS temp_match;")

    finally:
        con.close()

    execution_time_ms = round((time.time() - start_time) * 1000, 2)
    match_rate = round((matched_referrals_count / total_referral_rows * 100), 1) if total_referral_rows > 0 else 0.0

    return {
        "success": True,
        "total_referrals": total_referral_rows,
        "matched_referrals": matched_referrals_count,
        "unmatched_referrals": unmatched_referrals_count,
        "total_vehicle_matches": total_vehicle_matches,
        "multiple_matches_count": multiple_matches_count,
        "match_rate_percent": match_rate,
        "execution_time_ms": execution_time_ms,
        "total_output_rows": total_output_rows
    }


def get_match_results_page(
    user_id: int,
    page: int = 1,
    page_size: int = 50,
    filter_status: str = 'all',
    search_query: str = ''
) -> Dict[str, Any]:
    """
    استرجاع صفحة من نتائج المطابقة الأخيرة مع الأعمدة المرتبة بدقة
    """
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        return {"total": 0, "pages": 0, "page": page, "columns": [], "records": []}

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'last_match';").fetchone()[0]
        if table_check == 0:
            return {"total": 0, "pages": 0, "page": page, "columns": [], "records": []}

        # جلب قائمة كافة الأعمدة المتاحة بالترتيب المحفوظ
        all_cols = [c[0] for c in con.execute('DESCRIBE last_match').fetchall() if not c[0].startswith('__')]

        where_clauses = []
        params = []

        if filter_status == 'matched':
            where_clauses.append("__is_matched__ = 1")
        elif filter_status == 'unmatched':
            where_clauses.append("__is_matched__ = 0")
        elif filter_status == 'multiple':
            where_clauses.append('"حالة المطابقة" = \'تطابق متعدد\'')

        if search_query:
            sq = search_query.strip()
            conditions = [f'CAST("{col}" AS VARCHAR) LIKE ?' for col in all_cols]
            where_clauses.append(f"({' OR '.join(conditions)})")
            params.extend([f"%{sq}%"] * len(conditions))

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        count_sql = f"SELECT COUNT(*) FROM last_match {where_sql};"
        total_records = con.execute(count_sql, params).fetchone()[0]

        total_pages = (total_records + page_size - 1) // page_size if page_size > 0 else 1
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * page_size

        cols_select = ', '.join([f'"{c}"' for c in all_cols])
        select_sql = f"""
            SELECT {cols_select} 
            FROM last_match 
            {where_sql}
            ORDER BY __row_id__
            LIMIT ? OFFSET ?;
        """
        page_params = params + [page_size, offset]
        df_page = con.execute(select_sql, page_params).df().fillna('')
        records = df_page.to_dict(orient='records')

        return {
            "total": total_records,
            "pages": total_pages,
            "page": page,
            "columns": all_cols,
            "records": records
        }
    finally:
        con.close()


def export_match_results(user_id: int, file_format: str = 'xlsx', filter_status: str = 'all') -> str:
    """
    تصدير نتائج المطابقة كاملة بالأعمدة المرتبة بدقة إلى Excel (.xlsx) احترافي أو CSV بترميز UTF-8
    """
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        raise FileNotFoundError("لا توجد نتائج مطابقة لتصديرها.")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'last_match';").fetchone()[0]
        if table_check == 0:
            raise FileNotFoundError("لا توجد نتائج مطابقة مسجلة.")

        all_cols = [c[0] for c in con.execute('DESCRIBE last_match').fetchall() if not c[0].startswith('__')]
        cols_select = ', '.join([f'"{c}"' for c in all_cols])

        where_sql = ""
        if filter_status == 'matched':
            where_sql = "WHERE __is_matched__ = 1"
        elif filter_status == 'unmatched':
            where_sql = "WHERE __is_matched__ = 0"
        elif filter_status == 'multiple':
            where_sql = 'WHERE "حالة المطابقة" = \'تطابق متعدد\''

        query = f"SELECT {cols_select} FROM last_match {where_sql} ORDER BY __row_id__;"
        df = con.execute(query).df().fillna('')
    finally:
        con.close()

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    if file_format == 'csv':
        out_filename = f"matching_result_ordered_{user_id}_{timestamp}.csv"
        out_path = EXPORTS_DIR / out_filename
        df.to_csv(out_path, index=False, encoding='utf-8-sig')
        return str(out_path)

    # تصدير Excel منسق واحترافي كجدول رسمي بخط واضح وثقيل
    out_filename = f"matching_result_ordered_{user_id}_{timestamp}.xlsx"
    out_path = EXPORTS_DIR / out_filename

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "نتائج المطابقة"
    ws.views.sheetView[0].rightToLeft = True
    ws.sheet_properties.tabColor = "2563EB"

    headers = list(df.columns)
    ws.append(headers)

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")

    # خط واضح وتقيل للبيانات
    data_font = Font(name="Segoe UI", size=11, bold=True, color="0F172A")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    matched_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    multiple_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    unmatched_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    for row_idx, row in enumerate(df.itertuples(index=False), 2):
        ws.row_dimensions[row_idx].height = 24
        status = str(row[0]) if len(row) > 0 else ''
        status_fill = matched_fill if status == 'متطابق' else (multiple_fill if status == 'تطابق متعدد' else unmatched_fill)

        for col_idx, value in enumerate(row, 1):
            val_str = "" if pd.isna(value) else str(value)
            cell = ws.cell(row=row_idx, column=col_idx, value=val_str)
            cell.font = data_font
            cell.border = thin_border

            # محاذاة متناسقة تمنع التداخل
            if col_idx == 1:
                cell.fill = status_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif any(k in headers[col_idx-1] for k in ['اللوحة', 'تاريخ', 'شاص', 'عقد', 'هاتف', 'رقم']):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")

    # حساب أبعاد الأعمدة بدقة مع هوامش تمنع التداخل أو القص
    for col_idx, col in enumerate(ws.columns, 1):
        max_len = 0
        for cell in col:
            val = str(cell.value or '')
            w = sum(1.3 if ord(ch) > 127 else 1.0 for ch in val)
            if w > max_len:
                max_len = w
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 18), 45)

    ws.row_dimensions[1].height = 32

    # إنشاء جدول Excel رسمي (Excel Table) مع فلاتر وأسهم مدمجة
    if len(df) > 0:
        last_col = get_column_letter(len(headers))
        last_row = len(df) + 1
        tab = Table(displayName="VehicleMatchesTable", ref=f"A1:{last_col}{last_row}")
        tab.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False
        )
        ws.add_table(tab)

    wb.save(out_path)
    return str(out_path)


def quick_search_single_plate(user_id: int, query_plate: str) -> List[Dict[str, Any]]:
    """
    البحث الفوري عن لوحة واحدة وإرجاع كافة أعمدة السيارة بالكامل
    """
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        return []

    norm_query = normalize_plate(query_plate)
    if not norm_query:
        return []

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'vehicles';").fetchone()[0]
        if table_check == 0:
            return []

        query = "SELECT * EXCLUDE (__veh_id__, __veh_plate_norm__) FROM vehicles WHERE __veh_plate_norm__ = ?;"
        df = con.execute(query, [norm_query]).df().fillna('')
        df.columns = [c.replace('[السيارة] ', '').strip() for c in df.columns]
        return df.to_dict(orient='records')
    finally:
        con.close()


_RESOLVED_URL_CACHE: Dict[str, str] = {}


def resolve_short_maps_url(url: str, timeout: float = 2.5) -> str:
    """
    فك اختصار روابط خرائط جوجل (مثل maps.app.goo.gl أو goo.gl/maps)
    لجلب الرابط الحقيقي الذي يحتوي على إحداثيات خط الطول والعرض.
    """
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if not ('goo.gl' in url or 'maps.app' in url):
        return url

    if url in _RESOLVED_URL_CACHE:
        return _RESOLVED_URL_CACHE[url]

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )

        class RedirectCapture(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                self.redirect_url = newurl
                return None  # التقاط أول تحويل دون استنزاف شبكة أو تحميل صفحات ثقيلة

        h = RedirectCapture()
        h.redirect_url = None
        opener = urllib.request.build_opener(h)
        try:
            opener.open(req, timeout=timeout)
        except Exception:
            pass

        final_url = h.redirect_url or url
        _RESOLVED_URL_CACHE[url] = final_url
        return final_url
    except Exception:
        _RESOLVED_URL_CACHE[url] = url
        return url


def parse_geo_coordinates(loc_str: str) -> Optional[tuple[float, float]]:
    """
    استخراج إحداثيات خط الطول والعرض من أي رابط أو نص موقع حقيقي فقط
    يدعم:
    1. روابط خرائط جوجل المختصرة (maps.app.goo.gl / goo.gl/maps)
    2. روابط خرائط جوجل الكاملة بمختلف أنماطها (place, @, ?q=, ll=, destination)
    3. معلمات protobuf داخل روابط جوجل (!3d24.xxx!4d46.xxx)
    4. الإحداثيات الصريحة (24.7136, 46.6753)
    """
    if not loc_str or not isinstance(loc_str, str):
        return None
    loc_str = loc_str.strip()
    if not loc_str:
        return None

    # فك الرابط المختصر إذا وجد
    if 'goo.gl' in loc_str or 'maps.app' in loc_str:
        loc_str = resolve_short_maps_url(loc_str)

    # 1. إحداثيات protobuf داخل روابط جوجل: !3d(lat)!4d(lng)
    m_proto = re.search(r'!3d([-+]?\d{1,2}\.\d+)!4d([-+]?\d{1,3}\.\d+)', loc_str)
    if m_proto:
        try:
            lat = float(m_proto.group(1))
            lng = float(m_proto.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0.0 and lng == 0.0):
                return lat, lng
        except ValueError:
            pass

    # 2. مسارات وروابط خرائط جوجل: place/LAT,LNG أو @LAT,LNG أو q=LAT,LNG أو ll=LAT,LNG
    m_url = re.search(r'(?:place/|@|[?&](?:q|query|ll|loc|destination|saddr|daddr)=)([-+]?\d{1,2}\.\d+)[,\s]+([-+]?\d{1,3}\.\d+)', loc_str, re.IGNORECASE)
    if m_url:
        try:
            lat = float(m_url.group(1))
            lng = float(m_url.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0.0 and lng == 0.0):
                return lat, lng
        except ValueError:
            pass

    # 3. أي تطابق لإحداثيات صريحة LAT, LNG في أي موضع من النص
    for match in re.finditer(r'([-+]?\d{1,2}\.\d+)\s*[,|\s]\s*([-+]?\d{1,3}\.\d+)', loc_str):
        try:
            lat = float(match.group(1))
            lng = float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0.0 and lng == 0.0):
                return lat, lng
        except ValueError:
            continue

    return None


def extract_row_location_and_coords(row: Dict[str, Any]) -> tuple[Optional[tuple[float, float]], str]:
    """
    فحص الصف بالكامل للعثور على أي رابط أو إحداثيات جغرافية حقيقية في أي عمود كان
    (سواء كان العمود اسمه الموقع، الرابط، الحي، الشارع، الملاحظات، أو أي عمود آخر)
    """
    # 1. فحص الأعمدة ذات المسميات المرجحة للموقع أولاً
    priority_keys = [
        'الموقع', 'رابط الموقع', 'الرابط', 'اللوكيشن', 'لوكيشن',
        'الاحداثيات', 'الإحداثيات', 'احداثيات', 'خريطة', 'الخريطة',
        'موقع', 'location', 'map', 'maps', 'gps', 'coordinates', 'url', 'link'
    ]
    for k in priority_keys:
        val = str(row.get(k, '') or '').strip()
        if val:
            c = parse_geo_coordinates(val)
            if c:
                return c, val

    # 2. فحص كافة الأعمدة الأخرى التي تحتوي على نصوص أو أرقام
    for k, v in row.items():
        if k.startswith('__') or k in priority_keys:
            continue
        v_str = str(v or '').strip()
        if not v_str:
            continue
        if any(x in v_str for x in ['http', 'maps', 'goo.gl']) or ('.' in v_str and any(ch.isdigit() for ch in v_str)):
            c = parse_geo_coordinates(v_str)
            if c:
                return c, v_str

    return None, ""


def get_match_map_points(user_id: int) -> List[Dict[str, Any]]:
    """
    استرجاع بيانات ومواقع السيارات المتطابقة التي تملك موقعاً أو إحداثيات حقيقية فقط
    مع الفحص الشامل لكافة أعمدة البيانات وحل الروابط المختصرة تلقائياً
    """
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        return []

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'last_match';").fetchone()[0]
        if table_check == 0:
            return []

        df = con.execute("SELECT * FROM last_match WHERE __is_matched__ = 1 LIMIT 5000;").df().fillna('')
        if len(df) == 0:
            return []

        # استخراج مسبق لكافة الروابط المختصرة وحلها بالتوازي لسرعة فائقة
        short_urls = set()
        for _, row in df.iterrows():
            for v in row.values:
                v_str = str(v or '')
                if 'maps.app' in v_str or 'goo.gl' in v_str:
                    m = re.search(r'https?://[^\s<>"\']+', v_str)
                    if m:
                        short_urls.add(m.group(0))

        if short_urls:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(short_urls))) as executor:
                list(executor.map(resolve_short_maps_url, short_urls))

        points = []
        for idx, row in df.iterrows():
            row_dict = dict(row)
            coords, loc_val = extract_row_location_and_coords(row_dict)

            # إدراج السيارة فقط إذا كانت تملك إحداثيات حقيقية مستخرجة
            if coords is not None:
                lat, lng = coords
                plate_str = str(row_dict.get('اللوحة', '') or row_dict.get('لوحة الإحالة', ''))
                ref_plate_str = str(row_dict.get('لوحة الإحالة', '') or row_dict.get('اللوحة', ''))

                points.append({
                    "id": int(row_dict.get('__row_id__', idx + 1)),
                    "plate": plate_str,
                    "ref_plate": ref_plate_str,
                    "status": str(row_dict.get('حالة المطابقة', 'متطابق')),
                    "type": str(row_dict.get('النوع', '') or row_dict.get('طراز الإحالة', '') or ''),
                    "client": str(row_dict.get('اسم العميل', '')),
                    "street": str(row_dict.get('الشارع', '')),
                    "district": str(row_dict.get('الحي', '')),
                    "date": str(row_dict.get('التاريخ', '')),
                    "location_raw": loc_val,
                    "lat": lat,
                    "lng": lng,
                    "is_real_coords": True
                })

        return points
    finally:
        con.close()
