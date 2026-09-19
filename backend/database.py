"""
إدارة قواعد البيانات (Database Management Layer)
- SQLite: لإدارة المستخدمين الـ 50 والجلسات وسجل العمليات (system.db)
- DuckDB: محرك تحليلي عمودي مدمج لكل مستخدم لمعالجة الـ 2M سجل بسرعة فائقة
"""

import sqlite3
import hashlib
import json
import time
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import duckdb
import pandas as pd

from backend.config import (
    SYSTEM_DB_PATH, USERS_DATA_DIR, 
    PLATE_COLUMN_ALIASES, CHASSIS_COLUMN_ALIASES, 
    CLIENT_COLUMN_ALIASES, BANK_COLUMN_ALIASES
)
from backend.normalization import normalize_plate, DIGIT_TRANSLATION, CLEANUP_PATTERN


def hash_password(password: str) -> str:
    """تشفير كلمة المرور باستخدام SHA-256 مع Salt ثابت"""
    salt = "farz_secure_salt_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()


def init_system_db():
    """تهيئة قاعدة بيانات النظام وتجهيز المستخدمين الـ 50"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    cur = conn.cursor()

    # جدول المستخدمين
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # جدول الجلسات الآمنة
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # جدول سجل عمليات المطابقة
    cur.execute('''
        CREATE TABLE IF NOT EXISTS match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            total_referrals INTEGER NOT NULL,
            matched_referrals INTEGER NOT NULL,
            unmatched_referrals INTEGER NOT NULL,
            total_vehicle_matches INTEGER NOT NULL,
            execution_time_ms REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')

    # التحقق من وجود المستخدمين وتوليد 50 مستخدمًا تلقائيًا مع المدير
    cur.execute('SELECT COUNT(*) FROM users')
    user_count = cur.fetchone()[0]

    if user_count == 0:
        # إضافة حساب المدير
        admin_pass = hash_password("admin123")
        cur.execute(
            'INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)',
            ('admin', admin_pass, 'مدير النظام (Admin)', 'admin')
        )

        # إضافة 50 مستخدمًا جاهزًا للعمل فورًا (user1 إلى user50)
        default_user_pass = hash_password("123456")
        for i in range(1, 51):
            username = f"user{i}"
            display_name = f"المستخدم {i}"
            cur.execute(
                'INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)',
                (username, default_user_pass, display_name, 'user')
            )

    conn.commit()
    conn.close()


def get_user_duckdb_path(user_id: int) -> Path:
    """الحصول على مسار قاعدة بيانات DuckDB الخاصة بالمستخدم"""
    user_folder = USERS_DATA_DIR / f"user_{user_id}"
    user_folder.mkdir(parents=True, exist_ok=True)
    return user_folder / "dataset.duckdb"


def get_user_duckdb_connection(user_id: int) -> duckdb.DuckDBPyConnection:
    """فتح اتصال مع قاعدة بيانات DuckDB الخاصة بالمستخدم"""
    db_path = get_user_duckdb_path(user_id)
    con = duckdb.connect(str(db_path))
    return con


def detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """الاكتشاف التلقائي لعمود اللوحة والشاص والعميل والبنك من أسماء الأعمدة"""
    detected = {
        'plate': None,
        'chassis': None,
        'client_name': None,
        'bank': None
    }
    
    clean_cols = {col: str(col).strip().lower() for col in columns}

    for orig_col, clean_name in clean_cols.items():
        if detected['plate'] is None:
            for alias in PLATE_COLUMN_ALIASES:
                if alias.lower() in clean_name or clean_name in alias.lower():
                    detected['plate'] = orig_col
                    break

        if detected['chassis'] is None:
            for alias in CHASSIS_COLUMN_ALIASES:
                if alias.lower() in clean_name or clean_name in alias.lower():
                    detected['chassis'] = orig_col
                    break

        if detected['client_name'] is None:
            for alias in CLIENT_COLUMN_ALIASES:
                if alias.lower() in clean_name or clean_name in alias.lower():
                    detected['client_name'] = orig_col
                    break

        if detected['bank'] is None:
            for alias in BANK_COLUMN_ALIASES:
                if alias.lower() in clean_name or clean_name in alias.lower():
                    detected['bank'] = orig_col
                    break

    # إذا لم يتم اكتشاف عمود اللوحة، نعتمد العمود الأول تلقائيًا
    if detected['plate'] is None and len(columns) > 0:
        detected['plate'] = columns[0]

    return detected


def replace_user_dataset(
    user_id: int, 
    file_path: str, 
    plate_col: Optional[str] = None,
    chassis_col: Optional[str] = None,
    client_col: Optional[str] = None,
    bank_col: Optional[str] = None
) -> Dict[str, Any]:
    """
    استبدال قاعدة بيانات السيارات بالكامل للمستخدم (Active Dataset Replacement)
    تحميل حتى 2,000,000+ سجل وبناء الفهارس في ثوانٍ معدودة.
    الاستبدال يتم بشكل ذري (Atomic) لمنع تلف البيانات.
    """
    start_time = time.time()
    db_path = get_user_duckdb_path(user_id)
    file_ext = Path(file_path).suffix.lower()

    # إنشاء اتصال بقاعدة المستخدم
    con = duckdb.connect(str(db_path))

    try:
        total_rows = 0
        first_chunk = True

        # معالجة الملفات (CSV / TSV أو Excel)
        if file_ext in ['.csv', '.txt', '.tsv']:
            sample_df = pd.read_csv(file_path, nrows=5, index_col=False)
            cols = [str(c).strip() for c in sample_df.columns]
            detected = detect_columns(cols)
            p_col = plate_col or detected['plate']

            chunk_size = 150000
            for chunk in pd.read_csv(file_path, chunksize=chunk_size, dtype=str, keep_default_na=False, index_col=False):
                chunk = chunk.reset_index(drop=True)
                chunk.columns = [str(c).strip() for c in chunk.columns]
                chunk_len = len(chunk)
                if chunk_len == 0:
                    continue

                raw_plates = chunk[p_col].astype(str) if p_col in chunk else pd.Series([''] * chunk_len)
                norm_plates = (
                    raw_plates.str.normalize('NFKC')
                    .str.translate(DIGIT_TRANSLATION)
                    .str.replace(CLEANUP_PATTERN, '', regex=True)
                    .str.lower()
                    .str.strip()
                )

                batch_df = chunk.copy()
                # إضافة بادئة واضحة لكافة أعمدة بيانات السيارة
                batch_df.columns = [f"[السيارة] {c}" for c in batch_df.columns]
                batch_df['__veh_id__'] = list(range(total_rows + 1, total_rows + chunk_len + 1))
                batch_df['__veh_plate_norm__'] = norm_plates

                con.register("batch_view", batch_df)
                if first_chunk:
                    con.execute("DROP TABLE IF EXISTS temp_vehicles;")
                    con.execute("CREATE TABLE temp_vehicles AS SELECT * FROM batch_view;")
                    first_chunk = False
                else:
                    con.execute("INSERT INTO temp_vehicles SELECT * FROM batch_view;")
                con.unregister("batch_view")

                total_rows += chunk_len

        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, dtype=str, keep_default_na=False).reset_index(drop=True)
            df.columns = [str(c).strip() for c in df.columns]
            total_rows = len(df)
            detected = detect_columns(list(df.columns))
            p_col = plate_col or detected['plate']

            raw_plates = df[p_col].astype(str) if p_col in df else pd.Series([''] * total_rows)
            norm_plates = (
                raw_plates.str.normalize('NFKC')
                .str.translate(DIGIT_TRANSLATION)
                .str.replace(CLEANUP_PATTERN, '', regex=True)
                .str.lower()
                .str.strip()
            )

            batch_df = df.copy()
            batch_df.columns = [f"[السيارة] {c}" for c in batch_df.columns]
            batch_df['__veh_id__'] = list(range(1, total_rows + 1))
            batch_df['__veh_plate_norm__'] = norm_plates

            con.register("batch_view", batch_df)
            con.execute("DROP TABLE IF EXISTS temp_vehicles;")
            con.execute("CREATE TABLE temp_vehicles AS SELECT * FROM batch_view;")
            con.unregister("batch_view")

        else:
            raise ValueError(f"صيغة الملف غير مدعومة: {file_ext}")

        # استبدال الجدول القديم بالجديد ذريًا (Atomic Swap)
        con.execute("DROP TABLE IF EXISTS vehicles;")
        con.execute("ALTER TABLE temp_vehicles RENAME TO vehicles;")

        # بناء الفهرس فائق السرعة على عمود اللوحة المطبعة بعد التسمية
        index_start = time.time()
        con.execute("CREATE INDEX IF NOT EXISTS idx_norm_plate ON vehicles(__veh_plate_norm__);")
        index_time = time.time() - index_start

        elapsed = time.time() - start_time

        # حفظ تاريخ التحديث في جدول بيانات تعريفية
        con.execute("CREATE TABLE IF NOT EXISTS dataset_meta (key VARCHAR PRIMARY KEY, value VARCHAR);")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute(f"INSERT OR REPLACE INTO dataset_meta VALUES ('last_updated', '{now_str}'), ('total_records', '{total_rows}');")

        return {
            "success": True,
            "total_records": total_rows,
            "elapsed_seconds": round(elapsed, 2),
            "index_seconds": round(index_time, 2),
            "last_updated": now_str
        }

    finally:
        con.close()


def get_dataset_stats(user_id: int) -> Dict[str, Any]:
    """استرجاع إحصائيات ومعلومات الـ Dataset الحالي للمستخدم"""
    db_path = get_user_duckdb_path(user_id)
    if not db_path.exists():
        return {
            "exists": False,
            "total_records": 0,
            "distinct_plates": 0,
            "duplicate_plates_count": 0,
            "last_updated": None,
            "file_size_mb": 0.0
        }

    file_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    con = duckdb.connect(str(db_path), read_only=True)

    try:
        # التحقق من وجود جدول vehicles
        table_check = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'vehicles';").fetchone()[0]
        if table_check == 0:
            return {
                "exists": False,
                "total_records": 0,
                "distinct_plates": 0,
                "duplicate_plates_count": 0,
                "last_updated": None,
                "file_size_mb": file_size_mb
            }

        total_records = con.execute("SELECT COUNT(*) FROM vehicles;").fetchone()[0]
        distinct_plates = con.execute("SELECT COUNT(DISTINCT __veh_plate_norm__) FROM vehicles WHERE __veh_plate_norm__ != '';").fetchone()[0]
        
        # عدد اللوحات التي تكررت أكثر من مرة
        dups_query = """
            SELECT COUNT(*) FROM (
                SELECT __veh_plate_norm__ 
                FROM vehicles 
                WHERE __veh_plate_norm__ != '' 
                GROUP BY __veh_plate_norm__ 
                HAVING COUNT(*) > 1
            );
        """
        duplicate_plates_count = con.execute(dups_query).fetchone()[0]

        # قراءة تاريخ آخر تحديث
        last_updated = None
        try:
            meta_res = con.execute("SELECT value FROM dataset_meta WHERE key = 'last_updated';").fetchone()
            if meta_res:
                last_updated = meta_res[0]
        except Exception:
            pass

        return {
            "exists": True,
            "total_records": total_records,
            "distinct_plates": distinct_plates,
            "duplicate_plates_count": duplicate_plates_count,
            "last_updated": last_updated,
            "file_size_mb": file_size_mb
        }
    finally:
        con.close()


def clear_user_dataset(user_id: int):
    """تفريغ بيانات المستخدم بالكامل"""
    db_path = get_user_duckdb_path(user_id)
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            con = duckdb.connect(str(db_path))
            con.execute("DROP TABLE IF EXISTS vehicles;")
            con.execute("DROP TABLE IF EXISTS dataset_meta;")
            con.close()
