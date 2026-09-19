"""
إعدادات وثوابت النظام (System Configuration & Constants)
"""

import os
from pathlib import Path

# المسارات الأساسية للنظام
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
USERS_DATA_DIR = DATA_DIR / "users"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"
SYSTEM_DB_PATH = DATA_DIR / "system.db"

# التأكد من وجود المجلدات المطلوبة
for directory in [DATA_DIR, USERS_DATA_DIR, UPLOADS_DIR, EXPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# إعدادات الأمان
SECRET_KEY = os.getenv("SECRET_KEY", "farz-vehicle-matching-super-secret-key-2026")
SESSION_EXPIRY_HOURS = 24

# أقصى حجم لملف الرفع (بالبايت) - 1.5 جيجابايت
MAX_UPLOAD_SIZE = 1500 * 1024 * 1024

# أسماء الأعمدة المتوقعة الشائعة لاكتشافها تلقائيًا
PLATE_COLUMN_ALIASES = [
    'اللوحة', 'لوحة', 'رقم اللوحة', 'رقم_اللوحة', 'plate', 'plate_no', 
    'plate_number', 'platenumber', 'اللوحه', 'رقم اللوحه'
]

CHASSIS_COLUMN_ALIASES = [
    'الشاص', 'شاص', 'رقم الشاص', 'رقم_الشاص', 'الهيكل', 'رقم الهيكل', 
    'chassis', 'chassis_no', 'vin', 'vin_number', 'vin_no'
]

CLIENT_COLUMN_ALIASES = [
    'اسم العميل', 'العميل', 'اسم_العميل', 'المالك', 'اسم المالك', 
    'client', 'client_name', 'customer', 'customer_name', 'owner'
]

BANK_COLUMN_ALIASES = [
    'البنك', 'اسم البنك', 'البنك التابع له', 'الجهة', 'bank', 'bank_name'
]
