"""
إدارة المصادقة والأمان والجلسات (Authentication & Session Management)
"""

import sqlite3
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import SYSTEM_DB_PATH, SESSION_EXPIRY_HOURS
from backend.database import hash_password

security_bearer = HTTPBearer(auto_error=False)


def get_db_connection():
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """التحقق من صحة بيانات الدخول"""
    conn = get_db_connection()
    cur = conn.cursor()
    pwd_hash = hash_password(password)

    cur.execute(
        "SELECT id, username, display_name, role FROM users WHERE username = ? AND password_hash = ?",
        (username.strip(), pwd_hash)
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def create_session(user_id: int) -> str:
    """إنشاء جلسة دخول آمنة للمستخدم وإرجاع الـ Token"""
    token = secrets.token_hex(32)
    expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRY_HOURS)

    conn = get_db_connection()
    cur = conn.cursor()
    # حذف أي جلسات منتهية قديمة
    cur.execute("DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP")
    cur.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at.strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    return token


def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """التحقق من صلاحية الـ Token وجلب بيانات المستخدم"""
    if not token:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.username, u.display_name, u.role
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
    """, (token,))
    row = cur.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def destroy_session(token: str):
    """تسجيل خروج وإنهاء الجلسة"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def get_current_active_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> Dict[str, Any]:
    """Dependency لـ FastAPI للتحقق من هوية المستخدم في كل طلب"""
    if not credentials:
        raise HTTPException(status_code=401, detail="لم يتم توفير رمز المصادقة. يرجى تسجيل الدخول.")

    token = credentials.credentials
    user = validate_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="انتهت صلاحية الجلسة أو الرمز غير صالح.")

    return user


def get_all_users_list() -> List[Dict[str, Any]]:
    """استرجاع قائمة المستخدمين المسجلين (لإتاحة التبديل السريع والاختيار)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, display_name, role FROM users ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
